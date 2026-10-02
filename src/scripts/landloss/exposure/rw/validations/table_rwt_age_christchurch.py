"""Check the retaining wall age rules against Christchurch's building ages.

The study area holds no record of when its houses were built, which is why
exposure step 8 dates them from their titles. Christchurch does: its District
Valuation Roll is open (LINZ table 114085) and codes the decade every rating
unit's main building was built in. This script runs the step's rules over
Christchurch exactly as they run over Wellington, on claim properties built the
same way, and scores them against the roll:

    uv run --frozen python src/scripts/landloss/exposure/rw/validations/table_rwt_age_christchurch.py

It reads ``USE_CACHED_EXTENT`` from the step's ``config.py``. Needs
``LINZ_API_KEY`` in ``.env``: the property boundaries, addresses, titles and
valuation roll are all read from LINZ (CC BY 4.0).

The truth for a claim is the **oldest** building the roll dates on its
footprint, since a lot's walls are usually built with its first dwelling, and
building age is taken as wall age. Only residential rating units (category
``R``, vacant ``RV`` excluded) dated to a decade count; mixed-age (``MIX``)
and pre-decade codes are left out.

The roll dates to a decade, and two decades straddle a bin break, so a
property's truth is spread over the bins in proportion to its decade's years
(the 1990s are a quarter ``1970_1991``). The score of a property is the share
of its truth in the bin it was put in; the best possible over Christchurch is
about 0.92, not 1.

Each rule is switched off in turn, so the table shows what each one adds. The
Christchurch rebuild after 2010-2011 put new houses on old titles and plans,
which no title rule can see and Wellington has no equivalent of, so every
variant is scored twice: over all claims, and without the rebuild suspects.
Leaving them out selects on the truth and flatters every variant alike, so it
is the comparison between variants that it is read for, not the level. Each is
also scored per suburb, as the error in a suburb's share of one bin, pooled
over the bins and the suburbs with enough properties.

Three tables go under ``report/exposure/rw/rwt-age/tab/``: the summary per
variant, the score per rule that set the year, and the shares per suburb.
Findings are written up in ``rwt_age_christchurch.md`` beside this script.
"""

import sys

import numpy as np
import pandas as pd

from landloss.exposure.land.extent import (
    CLAIM_ID_COLUMN,
    build_claim_properties,
    count_dwellings,
)
from landloss.exposure.rw import age
from landloss.io.area_of_interest import CHRISTCHURCH
from landloss.io.readers import (
    get_nz_addresses,
    get_nz_district_valuation_roll,
    get_nz_property_boundaries,
    get_nz_property_titles_list,
)
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age import config
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age.table_rwt_age_by_suburb import (
    TAB_DIR,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Christchurch City's district code in the open roll, which drops the leading
# zero of the territorial authority code 060.
CHRISTCHURCH_DISTRICT = "60"
VACANT_CATEGORY = "RV"
TRUTH_DECADE_COLUMN = "dvr_decade"

# The decade of the roll's newest dwelling from which a claim on an older title
# and plan is read as a rebuild.
REBUILD_DECADE = 2010

# The fewest scored properties a suburb needs to be compared on its own.
MIN_SUBURB_PROPERTIES = 100

SHARE_COLUMNS = [f"p_{name}" for name in age.AGE_BINS]

# The variants scored: each switches one rule off, or changes one choice made.
VARIANTS = {
    "title date only": {"reissue_min_gap_years": np.inf, "infill_max_lots": 0},
    "with the reissue rule": {"infill_max_lots": 0},
    "rules as coded": {},
    "cross-leases dated by their own title": {
        "title_dated_types": ("Cross Lease", "Unit")
    },
}
CODED = "rules as coded"

# The two sets of claims each variant is scored over.
ALL_CLAIMS = "all"
WITHOUT_REBUILDS = "rebuild suspects left out"

RULE = "-" * 72


def table_path(name):
    """Return the CSV one of the validation tables is written to."""
    return TAB_DIR / f"rwt-age-christchurch-{name}.csv"


def residential_decades(roll):
    """Return the decade each residential Christchurch rating unit was built in."""
    roll = roll[roll["district_ta_code"].eq(CHRISTCHURCH_DISTRICT)]
    category = roll["property_category"].fillna("")
    residential = category.str.startswith("R") & ~category.str.startswith(
        VACANT_CATEGORY
    )
    code = roll["building_age_indicator"]
    decade_coded = code.str.fullmatch(r"\d{3}", na=False)
    roll = roll[residential & decade_coded]
    return pd.DataFrame(
        {
            "unit_of_property_id": roll["unit_of_property_id"].to_numpy(),
            TRUTH_DECADE_COLUMN: roll["building_age_indicator"].astype(int).to_numpy()
            * 10,
        }
    )


def truth_shares(decades):
    """Spread each decade over the bins in proportion to its years."""
    return np.vstack([age.bin_shares_of_span(d, d + 10) for d in decades])


def score(scored):
    """Score one set of ages against the truth.

    Args:
        scored: One row per claim, carrying the truth decade, the age bin and
            the estimated year.

    Returns:
        A dict of the measures in the summary table.
    """
    truth = truth_shares(scored[TRUTH_DECADE_COLUMN])
    codes = pd.Series(scored[age.AGE_BIN_COLUMN]).cat.codes.to_numpy()
    dated = codes >= 0
    credit = truth[np.flatnonzero(dated), codes[dated]]
    predicted = np.bincount(codes[dated], minlength=len(age.AGE_BINS)) / dated.sum()
    actual = truth[dated].mean(axis=0)
    decade = np.floor(scored[age.EST_YEAR_COLUMN].to_numpy() / 10) * 10
    exact = decade[dated] == scored[TRUTH_DECADE_COLUMN].to_numpy()[dated]
    measures = {
        "properties": len(scored),
        "undated": int((~dated).sum()),
        "bin_score": credit.mean(),
        "decade_exact": exact.mean(),
        "share_error_sum": np.abs(predicted - actual).sum(),
    }
    for name, p, t in zip(age.AGE_BINS, predicted, actual, strict=True):
        measures[f"p_{name}"] = p
        measures[f"true_p_{name}"] = t
    return measures


def suburb_comparison(scored):
    """Return the estimated and true bin shares of each suburb."""
    estimated = age.bin_shares(scored, ["suburb_locality"]).set_index("suburb_locality")
    truth = pd.DataFrame(
        truth_shares(scored[TRUTH_DECADE_COLUMN]),
        columns=[f"true_{c}" for c in SHARE_COLUMNS],
        index=scored.index,
    ).assign(suburb_locality=scored["suburb_locality"].to_numpy())
    actual = truth.groupby("suburb_locality").mean()
    table = estimated.join(actual, how="inner")
    table = table[table["properties"] >= MIN_SUBURB_PROPERTIES]
    for column in SHARE_COLUMNS:
        table[f"error_{column}"] = table[column] - table[f"true_{column}"]
    return table.reset_index()


def suburb_errors(table):
    """Summarise a suburb comparison as the error in one bin's share, pooled."""
    errors = table[[f"error_{c}" for c in SHARE_COLUMNS]].abs().to_numpy().ravel()
    return {
        "suburbs": len(table),
        "suburb_median_error": float(np.median(errors)),
        "suburb_p90_error": float(np.quantile(errors, 0.9)),
    }


def rebuild_suspects(scored):
    """Return the claims whose dwelling is newer than both its title and plan.

    Over Christchurch these are overwhelmingly the houses rebuilt after the
    2010-2011 earthquakes. The test reads only the title and plan dates, which
    no rule changes, so it picks out the same claims in every variant.
    """
    return (
        (scored[TRUTH_DECADE_COLUMN] >= REBUILD_DECADE)
        & (scored[age.TITLE_YEAR_COLUMN] < REBUILD_DECADE)
        & (scored[age.DP_YEAR_COLUMN].fillna(0) < REBUILD_DECADE)
    )


def describe_suburbs(table):
    """Print how far the suburb shares are from the roll's."""
    errors = table[[f"error_{c}" for c in SHARE_COLUMNS]].abs()
    print(
        f"Suburbs with at least {MIN_SUBURB_PROPERTIES} scored properties: {len(table)}"
    )
    print("Absolute error in each bin's share, across those suburbs:")
    summary = pd.DataFrame(
        {
            "median": errors.median(),
            "90th percentile": errors.quantile(0.9),
            "worst": errors.max(),
        }
    )
    summary.index = list(age.AGE_BINS)
    print(summary.round(3).to_string())


def main(*, use_cached_extent):
    """Score the age rules against the Christchurch roll and write the tables.

    Args:
        use_cached_extent: Whether to reuse the already-fetched Christchurch
            boundaries and addresses.
    """
    bbox = CHRISTCHURCH.bbox()
    print("Fetching the Christchurch property boundaries ...", flush=True)
    boundaries = get_nz_property_boundaries(bbox=bbox, use_cache=use_cached_extent)
    boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())
    claims = build_claim_properties(boundaries)

    print("Reading the titles and the valuation roll ...", flush=True)
    titles = get_nz_property_titles_list()
    decades = residential_decades(get_nz_district_valuation_roll())
    units = age.footprint_rows(
        boundaries, claims, CLAIM_ID_COLUMN, ["unit_of_property_id"]
    )
    truth = (
        units.merge(decades, on="unit_of_property_id")
        .groupby(CLAIM_ID_COLUMN)[TRUTH_DECADE_COLUMN]
        .min()
    )

    print("Fetching the Christchurch addresses ...", flush=True)
    addresses = get_nz_addresses(bbox=bbox, use_cache=use_cached_extent)
    suburbs = age.claim_suburbs(
        count_dwellings(claims, addresses), addresses, CLAIM_ID_COLUMN
    )

    print(RULE)
    print(f"Claim properties: {len(claims):,}; with a dated dwelling: {len(truth):,}")
    summary = []
    coded = None
    for name, settings in VARIANTS.items():
        print(f"Scoring {name} ...", flush=True)
        ages = age.infer_claim_ages(
            claims, boundaries, titles, id_column=CLAIM_ID_COLUMN, **settings
        )
        scored = ages.join(truth, on=CLAIM_ID_COLUMN, how="inner").join(
            suburbs, on=CLAIM_ID_COLUMN
        )
        rebuilt = rebuild_suspects(scored)
        for claims_scored, subset in (
            (ALL_CLAIMS, scored),
            (WITHOUT_REBUILDS, scored[~rebuilt]),
        ):
            summary.append(
                {
                    "variant": name,
                    "claims": claims_scored,
                    **score(subset),
                    **suburb_errors(suburb_comparison(subset)),
                }
            )
        if name == CODED:
            coded = scored
    summary = pd.DataFrame(summary)
    rebuilt = rebuild_suspects(coded)

    by_basis = pd.DataFrame(
        [
            {"age_basis": basis, **score(group)}
            for basis, group in coded.groupby(age.AGE_BASIS_COLUMN, observed=True)
        ]
    )
    by_suburb = suburb_comparison(coded)

    for name, table in (
        ("summary", summary),
        ("by-basis", by_basis),
        ("by-suburb", by_suburb),
    ):
        out_path = table_path(name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(out_path, index=False, float_format="%.4f")
        print(f"Wrote {out_path}")

    shown = [
        "variant",
        "claims",
        "bin_score",
        "decade_exact",
        "share_error_sum",
        "suburb_median_error",
        "suburb_p90_error",
    ]
    print(RULE)
    print(summary[shown].to_string(index=False, float_format="%.3f"))
    print(RULE)
    print("The estimated shares, and the roll's own:")
    true_columns = [f"true_{c}" for c in SHARE_COLUMNS]
    print(
        summary[["variant", "claims", *SHARE_COLUMNS]].to_string(
            index=False, float_format="%.3f"
        )
    )
    print(
        summary.drop_duplicates("claims")[["claims", *true_columns]].to_string(
            index=False, float_format="%.3f"
        )
    )
    print(
        f"Rebuild suspects (a {REBUILD_DECADE}s or later dwelling on an older title "
        f"and plan): {int(rebuilt.sum()):,}, {rebuilt.mean():.1%} of claims"
    )
    print(RULE)
    print(
        by_basis[["age_basis", "properties", "bin_score"]].to_string(
            index=False, float_format="%.3f"
        )
    )
    print(RULE)
    describe_suburbs(by_suburb)


if __name__ == "__main__":
    main(use_cached_extent=config.USE_CACHED_EXTENT)
