"""Check the modelled land values against what is known independently of the model.

Four checks, run over the output of the land value step. They are checks on an
output rather than unit tests of a function: the arithmetic is already covered by
``tests/landloss/exposure/test_land_value.py``, and what this script is looking
for is the thing a passing test suite cannot see -- a silently wrong input, a
territorial authority that lost half its addresses somewhere upstream, a rate
column full of zeroes.

    uv run --frozen python src/scripts/landloss/exposure/land/validations/check_land_value_totals.py

The checks are:

1. TOTALS -- each territorial authority's modelled mean land value against its
   published QV average, indexed onto the common valuation date. True by
   construction, so this one is a tripwire on the normalisation.
2. COUNTS -- the address count per territorial authority against the published
   rating unit count. An excess is expected and is reported as a ratio rather
   than passed or failed on; only an implausible ratio is flagged.
3. SUBURB RANKING -- the modelled suburb medians against the market order anyone
   in Wellington already knows. Informational, and expected to be weak in Phase 1.
4. DISTRIBUTION -- no zero, negative or null rates, a right-skewed distribution,
   and a sane spread between the 10th and 90th percentiles.

The input defaults to what s4_estimate_land_value.py writes over the extent set
by EXTENT in the land value step's config.py,
``temp/exposure/land-value-by-address<suffix>.geoparquet`` where ``<suffix>`` is
``extent_suffix(extent)``. Pass --extent to check another extent's output; any
extent other than "full" makes the COUNTS check report rather than enforce,
because it covers only part of each territorial authority. Pass --input to point
at a land value output written somewhere else.

No .env keys and no network access are needed. Everything read is either the step
output already on disk or the packaged base rates asset, which is what makes this
runnable as a check on a run someone else did.
"""

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

import geopandas as gpd
import pandas as pd

# Suburb names in the study area are macronised -- Owhiro Bay, Pauatahanui,
# Korokoro are all spelled with macrons in the LINZ layer -- and the default
# cp1252 Windows console cannot encode them, so printing a ranking table raises
# without this. See fig_waterway_map.py for the same note.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from landloss.exposure.land.land_value import (
    COMMON_VALUATION_DATE,
    index_base_rates,
    load_base_rates,
    ta_mean_land_value,
)
from landloss.io.area_of_interest import EXTENTS, extent_suffix, is_full_extent
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.paths import TEMP_DIR

# Where s4_estimate_land_value.py writes. These names track that script, so a
# rename there shows up as this script failing to find its input rather than as
# the checks quietly passing over a stale file.
WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "land-value-by-address"

STEP_COMMAND = (
    "uv run --frozen python "
    "src/scripts/landloss/exposure/land/steps/s2_land_value/s4_estimate_land_value.py"
)

REQUIRED_COLUMNS = (
    "territorial_authority",
    "suburb_locality",
    "landform_class",
    "land_value_nzd",
    "land_rate_nzd_per_m2",
)

RULE = "-" * 72

PASS = "PASS"
FAIL = "FAIL"
INFO = "INFO"

# The TA mean is the indexed published average by construction, so the only
# tolerance needed is for floating point accumulation over tens of thousands of
# addresses. Anything looser would let a genuinely broken normalisation through.
TOTALS_RELATIVE_TOLERANCE = 1e-6

# Addresses per published rating unit. Well above 1.0 is the expected state, not
# a problem: a block of flats is many addresses and one rating unit. The band is
# deliberately wide because it is only meant to catch a count that is wrong by a
# factor -- a TA filtered down to a suburb, or the address layer double counted.
COUNT_RATIO_MIN = 0.80
COUNT_RATIO_MAX = 3.00

# Suburbs whose place in the Wellington market is not seriously disputed. They
# are the yardstick the modelled ranking is held against, and they are named here
# rather than derived so that a reader can argue with the list.
EXPECTED_HIGH_SUBURBS = (
    "Seatoun",
    "Oriental Bay",
    "Khandallah",
    "Days Bay",
    "Eastbourne",
)
EXPECTED_LOW_SUBURBS = ("Wainuiomata", "Stokes Valley", "Taita")

# Below this a suburb's median is one or two properties and says nothing, so it
# is left out of the ranking rather than ranked on noise.
MIN_SUBURB_ADDRESSES = 30

# A suburb counts as correctly placed if it sits in the top (or bottom) this
# fraction of the ranking.
RANKING_HALF = 0.5

# The spread between a cheap address and an expensive one, as the ratio of the
# 90th to the 10th percentile rate. Below about 1.1 the model has flattened into
# a single number; above about 25 a decile has run away.
SPREAD_RATIO_MIN = 1.1
SPREAD_RATIO_MAX = 25.0

PERCENTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

# Skewness only says something about the model once the model produces a spread
# of rates. While land is classified into flat and hill alone, every address
# takes one of two values per territorial authority, and the sign of the skew is
# then decided entirely by the flat/hill share. The check is therefore reported
# while the surface is this coarse, and enforced once the terrain and amenity
# phases make it continuous.
SKEW_MIN_DISTINCT_RATES = 10


class Distribution(NamedTuple):
    """What the DISTRIBUTION check measured, kept together so it prints as one."""

    status: str
    checks: list
    quantiles: pd.Series | None
    mean: float
    median: float
    skew: float
    spread: float


def read_valued(path):
    """Read the valued addresses, whatever format the step wrote them in.

    The step writes geoparquet. The other formats are accepted so that a table
    someone exported by hand can be run through the same checks, which is the
    usual way a query about one territorial authority arrives.
    """
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".geoparquet"}:
        try:
            return gpd.read_parquet(path)
        except (ValueError, AttributeError):
            # Written without geometry metadata. The attributes are all these
            # checks need, so a plain table is perfectly usable.
            return pd.read_parquet(path)
    return gpd.read_file(path)


def missing_columns(valued):
    """Return the required columns the input does not carry."""
    return [column for column in REQUIRED_COLUMNS if column not in valued.columns]


def check_totals(valued, indexed):
    """Check each TA's modelled mean against its indexed published average."""
    rows = []
    status = PASS

    # Each property counted once, the mean estimate_land_value holds.
    modelled = ta_mean_land_value(valued)

    for ta_name in sorted(modelled.index):
        published = float(indexed.loc[ta_name, "indexed_land_value_nzd"])
        actual = float(modelled.loc[ta_name])

        # Relative rather than absolute, because the four TAs differ by a factor
        # of roughly 1.5 in the size of the number being compared.
        difference = abs(actual - published) / published
        ok = difference <= TOTALS_RELATIVE_TOLERANCE
        if not ok:
            status = FAIL

        rows.append((ta_name, published, actual, difference, PASS if ok else FAIL))

    return status, rows


def report_totals(status, rows):
    """Print the TOTALS check."""
    print(RULE)
    print("1. TOTALS -- modelled TA mean against the published average")
    print(
        "The normalising constant makes each TA mean equal its published average\n"
        "by construction, so this check cannot fail because the market moved or\n"
        "because the data is unusual. A failure here means the normalisation is\n"
        "broken -- the clip binding on every address, a TA the base rates do not\n"
        "carry, or a land value column written from somewhere other than the\n"
        "model. It is a tripwire, not a measurement."
    )
    print(f"Published averages indexed onto {COMMON_VALUATION_DATE}.")
    print()
    print(
        f"  {'Territorial authority':<22} {'Published':>14} {'Modelled':>14} "
        f"{'Rel. diff.':>12}  Result"
    )
    for ta_name, published, actual, difference, result in rows:
        print(
            f"  {ta_name:<22} {published:>14,.0f} {actual:>14,.0f} "
            f"{difference:>12.2e}  {result}"
        )
    print()
    print(f"  Tolerance: {TOTALS_RELATIVE_TOLERANCE:.0e} relative.  Check: {status}")


def check_counts(valued, indexed, *, partial=False):
    """Compare address counts per TA with the published rating unit counts.

    ``partial`` says the input covers only part of each territorial authority, as
    a pilot run does. The ratios are still worth printing there, but they cannot
    be compared with a whole-authority rating unit count, so nothing is enforced.
    """
    rows = []
    status = INFO if partial else PASS

    counts = valued.groupby("territorial_authority").size()

    for ta_name in sorted(counts.index):
        rating_units = float(indexed.loc[ta_name, "rating_units"])
        addresses = int(counts.loc[ta_name])
        ratio = addresses / rating_units

        if partial:
            rows.append((ta_name, rating_units, addresses, ratio, INFO))
            continue

        ok = COUNT_RATIO_MIN <= ratio <= COUNT_RATIO_MAX
        if not ok:
            status = FAIL

        rows.append((ta_name, rating_units, addresses, ratio, PASS if ok else FAIL))

    return status, rows


def report_counts(status, rows, *, partial=False):
    """Print the COUNTS check."""
    print(RULE)
    print("2. COUNTS -- address count against the published rating unit count")
    print(
        "These two do not measure the same thing, so the ratio is reported rather\n"
        "than passed or failed on. An address is a unit and a rating valuation is\n"
        "a rating unit, so a block of flats is many addresses and one rating unit,\n"
        "and the addresses also include commercial and industrial units that the\n"
        "LINZ layer gives us no flag to exclude. An excess is EXPECTED.\n"
        "\n"
        "Quantifying that excess is exactly what evidence register task T-23 asks\n"
        "for -- what proportion of study area properties are multi-unit buildings,\n"
        "cross-lease or shared land, so that the decision to exclude them is\n"
        "evidenced. The ratios below are the first cut of that evidence, not a\n"
        "defect to be fixed."
    )
    if partial:
        print(
            "\nThis run covers only part of each territorial authority, so every\n"
            "ratio below is a partial count against a whole-authority rating unit\n"
            "count and is expected to be far below 1.00. Nothing is enforced."
        )
    else:
        print(
            f"\nOnly a ratio outside the wide sane band {COUNT_RATIO_MIN:.2f} to "
            f"{COUNT_RATIO_MAX:.2f} is flagged, because\n"
            "that would mean the address population itself is wrong -- a "
            "territorial\nauthority filtered down to one suburb, or the address "
            "layer double\ncounted -- rather than the multi-unit excess the ratio "
            "is there to show."
        )
    print()
    print(
        f"  {'Territorial authority':<22} {'Rating units':>13} {'Addresses':>11} "
        f"{'Ratio':>8}  Result"
    )
    total_units = 0.0
    total_addresses = 0
    for ta_name, rating_units, addresses, ratio, result in rows:
        total_units += rating_units
        total_addresses += addresses
        print(
            f"  {ta_name:<22} {rating_units:>13,.0f} {addresses:>11,} "
            f"{ratio:>8.2f}  {result}"
        )
    if total_units:
        label = "All listed" if partial else "All four"
        print(
            f"  {label:<22} {total_units:>13,.0f} {total_addresses:>11,} "
            f"{total_addresses / total_units:>8.2f}"
        )
    print()
    print(f"  Check: {status}")


def rank_suburbs(valued):
    """Return the suburb medians, ranked from the most to the least valuable."""
    grouped = valued.groupby("suburb_locality", dropna=True).agg(
        address_count=("land_value_nzd", "size"),
        median_land_value_nzd=("land_value_nzd", "median"),
        median_land_rate_nzd_per_m2=("land_rate_nzd_per_m2", "median"),
    )

    ranked = grouped.loc[grouped["address_count"] >= MIN_SUBURB_ADDRESSES].copy()

    # method="min" so that tied suburbs share the best rank they could have. The
    # Phase 1 model produces a great many ties -- see the count of distinct
    # medians printed below -- and averaging the ranks would hide that.
    ranked["rank"] = (
        ranked["median_land_value_nzd"].rank(ascending=False, method="min").astype(int)
    )

    return ranked.sort_values("rank")


def check_suburb_ranking(ranked):
    """Check the modelled suburb ranking against the known market order."""
    total = len(ranked)
    rows = []
    met = 0
    considered = 0

    expectations = [(name, "high") for name in EXPECTED_HIGH_SUBURBS]
    expectations += [(name, "low") for name in EXPECTED_LOW_SUBURBS]

    for suburb, expected in expectations:
        if suburb not in ranked.index:
            rows.append((suburb, expected, None, None, None, None, "NOT FOUND"))
            continue

        row = ranked.loc[suburb]
        rank = int(row["rank"])

        # Where in the ranking the suburb sits, as a fraction: 0.0 is the most
        # valuable suburb modelled and 1.0 the least.
        position = (rank - 1) / (total - 1) if total > 1 else 0.0

        ok = (
            position <= RANKING_HALF if expected == "high" else position >= RANKING_HALF
        )
        considered += 1
        met += int(ok)

        rows.append(
            (
                suburb,
                expected,
                rank,
                position,
                float(row["median_land_value_nzd"]),
                int(row["address_count"]),
                "as expected" if ok else "OUT OF PLACE",
            )
        )

    return rows, met, considered, total


def report_suburb_ranking(ranked, rows, met, considered, total):
    """Print the SUBURB RANKING check, honestly."""
    distinct = int(ranked["median_land_value_nzd"].nunique()) if total else 0

    print(RULE)
    print("3. SUBURB RANKING -- modelled medians against the known market order")
    print(
        "INFORMATIONAL. This check is reported, never enforced, because Phase 1\n"
        "separates land only into hill and flat. Within a territorial authority a\n"
        "suburb's modelled median can therefore take one of two values, so most\n"
        "suburbs tie with most other suburbs and the ranking carries very little\n"
        "information. It is printed because the size of the mismatch is the\n"
        "evidence for how badly the amenity phases are needed -- DEM terrain,\n"
        "distance decay to centres, sea view, winter sun. It is not rigged to\n"
        "pass, and a poor result here is a finding rather than a defect."
    )
    print()
    print(
        f"  {total:,} suburbs with at least {MIN_SUBURB_ADDRESSES} addresses, "
        f"carrying {distinct:,} distinct median values between them."
    )
    print()
    print(
        f"  {'Suburb':<20} {'Expect':<7} {'Rank':>10} {'Position':>9} "
        f"{'Median LV':>13} {'Addr':>7}  Result"
    )
    for suburb, expected, rank, position, median, count, result in rows:
        if rank is None:
            print(
                f"  {suburb:<20} {expected:<7} {'-':>10} {'-':>9} "
                f"{'-':>13} {'-':>7}  {result}"
            )
            continue
        print(
            f"  {suburb:<20} {expected:<7} {rank:>4,} of{total:>4,} {position:>9.2f} "
            f"{median:>13,.0f} {count:>7,}  {result}"
        )
    print()
    if considered:
        print(
            f"  {met} of {considered} named suburbs sit in the expected half of "
            f"the ranking."
        )
    else:
        print("  None of the named suburbs met the minimum address count.")
    print(f"  Check: {INFO} (reported, not enforced)")


def check_distribution(valued):
    """Check the rate distribution for impossible values, skew and spread."""
    rates = valued["land_rate_nzd_per_m2"]

    null_count = int(rates.isna().sum())
    non_positive = int((rates <= 0).sum())

    finite = rates.dropna()
    quantiles = finite.quantile(list(PERCENTILES)) if not finite.empty else None

    mean = float(finite.mean()) if not finite.empty else float("nan")
    median = float(finite.median()) if not finite.empty else float("nan")
    skew = float(finite.skew()) if len(finite) > 2 else float("nan")

    p10 = float(quantiles.loc[0.10]) if quantiles is not None else float("nan")
    p90 = float(quantiles.loc[0.90]) if quantiles is not None else float("nan")
    spread = p90 / p10 if p10 > 0 else float("nan")

    # Fisher skewness rather than mean > median alone, because a distribution
    # with only a few distinct values can put the mean above the median while
    # still carrying its long tail on the left.
    distinct_rates = int(finite.nunique())

    checks = [
        ("No null rates", null_count == 0, f"{null_count:,} null", True),
        (
            "No zero or negative rates",
            non_positive == 0,
            f"{non_positive:,} at or below zero",
            True,
        ),
        (
            "Right-skewed",
            skew > 0,
            f"Fisher skew {skew:.3f} over {distinct_rates:,} distinct rates",
            distinct_rates >= SKEW_MIN_DISTINCT_RATES,
        ),
        (
            "Spread within band",
            SPREAD_RATIO_MIN <= spread <= SPREAD_RATIO_MAX,
            f"p90/p10 {spread:.2f}",
            True,
        ),
    ]

    status = PASS if all(ok for _, ok, _, enforced in checks if enforced) else FAIL
    return Distribution(status, checks, quantiles, mean, median, skew, spread)


def report_distribution(shape):
    """Print the DISTRIBUTION check."""
    status, checks, quantiles, mean, median, skew, spread = shape

    print(RULE)
    print("4. DISTRIBUTION -- the shape of the modelled rate per square metre")
    print(
        "A zero, negative or null rate is impossible and means an address lost its\n"
        "lot size or its landform class somewhere upstream. Land values are\n"
        "right-skewed in every market anyone has measured, so a left-skewed result\n"
        "means the landform factors are the wrong way round -- but only once there\n"
        "are enough distinct rates for the shape to say something about the model\n"
        "rather than about the flat/hill share, so it is reported until then. The\n"
        "spread band is a sanity check on the clip: a ratio near one says the\n"
        "model has flattened into a single number, and a very large one says a\n"
        "decile has run away."
    )
    print()
    if quantiles is not None:
        print("  Rate per square metre (NZD/m2):")
        for percentile in PERCENTILES:
            label = f"p{int(percentile * 100)}"
            print(f"    {label:<5} {quantiles.loc[percentile]:>12,.2f}")
        print(f"    {'mean':<5} {mean:>12,.2f}")
    print()
    print(f"  Mean / median  : {mean:,.2f} / {median:,.2f}")
    print(f"  Fisher skew    : {skew:.3f}  (positive is right-skewed)")
    print(
        f"  p90 / p10      : {spread:.2f}  "
        f"(band {SPREAD_RATIO_MIN:.1f} to {SPREAD_RATIO_MAX:.1f})"
    )
    print()
    for label, ok, detail, enforced in checks:
        result = (PASS if ok else FAIL) if enforced else INFO
        print(f"  {label:<28} {detail:<46}  {result}")
    print()
    print(f"  Check: {status}")


def report_summary(results):
    """Print the one-line-per-check table and return the exit status."""
    print(RULE)
    print("SUMMARY")
    print()
    print(f"  {'Check':<16} {'Result':<6}  What it means")
    for name, status, meaning in results:
        print(f"  {name:<16} {status:<6}  {meaning}")
    print()

    failed = [name for name, status, _ in results if status == FAIL]
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1

    print("All enforced checks passed. SUBURB RANKING is informational either way.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "The land value output to check. Defaults to "
            f"{WORK_DIR / OUT_STEM}<suffix>.geoparquet, where <suffix> is "
            "extent_suffix(extent)."
        ),
    )
    parser.add_argument(
        "--extent",
        choices=["full", *EXTENTS],
        default=config.EXTENT,
        help=(
            "The extent whose output to check. Defaults to EXTENT in the land "
            f"value step's config.py ({config.EXTENT!r}). Over any extent other "
            'than "full" the address counts cover only part of each territorial '
            "authority, so the COUNTS check reports rather than enforces."
        ),
    )
    args = parser.parse_args()

    partial = not is_full_extent(args.extent)
    path = args.input or (
        WORK_DIR / f"{OUT_STEM}{extent_suffix(args.extent)}.geoparquet"
    )

    if not path.exists():
        print(f"No land value output found at {path}")
        print(f"\nRun the land value step first:\n  {STEP_COMMAND}")
        if partial:
            print(f'  with EXTENT = "{args.extent}" in the config.py beside it')
        return 1

    print(f"Reading {path}")
    valued = read_valued(path)
    print(f"  {len(valued):,} valued addresses")

    missing = missing_columns(valued)
    if missing:
        print(f"\nThe input is missing the column(s): {', '.join(missing)}")
        print(f"Expected all of: {', '.join(REQUIRED_COLUMNS)}")
        return 1

    if valued.empty:
        print("\nThe input holds no addresses, so there is nothing to check.")
        return 1

    indexed = index_base_rates(load_base_rates()).set_index("ta_name")

    unknown = sorted(set(valued["territorial_authority"]) - set(indexed.index))
    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        print(f"\nThe input carries territorial authority/authorities {listed},")
        print("which the published base rates say nothing about.")
        return 1

    print()
    totals_status, totals_rows = check_totals(valued, indexed)
    report_totals(totals_status, totals_rows)

    print()
    counts_status, counts_rows = check_counts(valued, indexed, partial=partial)
    report_counts(counts_status, counts_rows, partial=partial)

    print()
    ranked = rank_suburbs(valued)
    ranking_rows, met, considered, total = check_suburb_ranking(ranked)
    report_suburb_ranking(ranked, ranking_rows, met, considered, total)

    print()
    distribution = check_distribution(valued)
    report_distribution(distribution)

    print()
    return report_summary(
        [
            ("TOTALS", totals_status, "TA means equal the indexed published averages"),
            (
                "COUNTS",
                counts_status,
                (
                    "addresses per rating unit, over a partial extent"
                    if partial
                    else f"addresses per rating unit within "
                    f"{COUNT_RATIO_MIN:.2f}-{COUNT_RATIO_MAX:.2f}"
                ),
            ),
            (
                "SUBURB RANKING",
                INFO,
                f"{met} of {considered} named suburbs placed as expected",
            ),
            (
                "DISTRIBUTION",
                distribution.status,
                "rates positive, right-skewed and sanely spread",
            ),
        ]
    )


if __name__ == "__main__":
    # Only raise on failure, matching the other scripts in this repository:
    # falling off the end already exits 0, so the shell contract is unchanged,
    # but a run under an IPython or PyCharm console no longer ends in a
    # "SystemExit: 0" traceback that reads like a crash.
    status = main()
    if status:
        raise SystemExit(status)
