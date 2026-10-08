"""Build the address spine every later exposure step hangs off.

Reads the LINZ NZ Addresses layer over the four Wellington territorial
authorities, cuts it back to the current land addresses, and writes the result as
a geoparquet. Everything downstream -- landform, land value, hazard sampling,
loss -- joins onto this one file, so it is built once and re-read rather than
re-fetched.

The read is clipped to the real territorial authority boundaries, not to their
bounding box, over every extent. The four authorities sit in a rectangle that
also contains most of the Wairarapa, so a bounding-box-only read would carry
tens of thousands of addresses that are not in the study, and a box over one
authority (Porirua City's reaches into the Kapiti Coast) would carry addresses
no later step can value.

    uv run --frozen python src/scripts/landloss/exposure/steps/s1_address_spine/s1_build_address_spine.py

The run also prints the address count for each territorial authority beside the
rating unit count that authority's published revaluation reports. That comparison
is the point of the printed table rather than a nicety: register task T-23 asks
for evidence of how much of the study area is multi-unit, cross-lease or shared
land, and the gap between addresses and rating units is the first cheap
measurement of it.

The run settings -- the extent, where the small Wellington pilot box is the
quick way to exercise the script end to end, whether to ignore the cache, and
where to write -- come from config.py beside this script rather than from the
command line.

Requires LINZ_API_KEY in .env.
"""

import sys
from pathlib import Path

import requests

from landloss.domain import constants
from landloss.exposure.addresses import get_addresses
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
    is_full_extent,
)
from scripts.landloss.exposure.steps.s1_address_spine import config
from scripts.landloss.paths import REPO_ROOT, TEMP_DIR

# Wellington suburb names are macronised -- Ōwhiro Bay, Pāuatahanui -- which the
# default cp1252 Windows console cannot encode, so printing one raises. Ask for
# UTF-8 rather than stripping the macrons, because the names are worth getting
# right.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# temp/ is gitignored, which is what this output wants to be: a working layer
# that is cheap to rebuild from the source and has no business in a diff.
OUT_DIR = TEMP_DIR / "exposure"
# The name carries extent_suffix(extent), so a run over one extent cannot
# overwrite another's spine.
OUT_STEM = "address-spine"

# Rating units counted by each council's most recent published district
# revaluation. These are the denominators the address counts are compared
# against; the same four revaluations supply the land values in
# landloss/io/assets/land-value-base-rates.csv.
QV_RATING_UNITS = {
    "Wellington City": 82_591,
    "Lower Hutt City": 43_576,
    "Porirua City": 21_481,
    "Upper Hutt City": 18_474,
}

RULE = "-" * 72


def describe_extent(name, bbox):
    """Print the extent being read, so a mistaken study area is obvious at once."""
    minx, miny, maxx, maxy = bbox

    print(RULE)
    print(f"Repo root : {REPO_ROOT}")
    print(f"Extent    : {name}")
    print(f"  NZTM    : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size    : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")


def describe_counts(spine, *, extent):
    """Print the per-TA address counts against the published rating unit counts.

    The ratio is the evidence register task T-23 asks for. Two things drive it
    above 1.0 and both matter to how the exposure population is read. A rating
    unit can carry several addresses -- a block of flats on one cross-lease
    title is one unit and many front doors -- and the address layer also carries
    every shop, office and warehouse, which no residential revaluation counts.
    Phase 1 cannot separate the two, because the LINZ address layer has no
    residential flag, so the number printed here is an upper bound on the
    multi-unit share rather than a measurement of it.
    """
    print(RULE)
    print(f"Addresses in the spine: {len(spine):,}")
    print()
    print(
        f"{'Territorial authority':<24}{'Addresses':>12}{'Rating units':>14}{'Ratio':>8}"
    )

    counts = spine["territorial_authority"].value_counts()

    # Iterate the published table rather than the counts, so a territorial
    # authority that came back with no addresses at all shows as a zero row
    # instead of quietly vanishing from the comparison.
    for ta_name, rating_units in QV_RATING_UNITS.items():
        count = int(counts.get(ta_name, 0))
        ratio = count / rating_units
        print(f"{ta_name:<24}{count:>12,}{rating_units:>14,}{ratio:>8.2f}")

    total = int(counts.sum())
    total_units = sum(QV_RATING_UNITS.values())
    print(f"{'Total':<24}{total:>12,}{total_units:>14,}{total / total_units:>8.2f}")

    # A pilot covers a few streets of one authority, so its ratio compares a
    # fragment against a whole city and means nothing. Said out loud, because a
    # ratio of 0.01 printed without comment reads like a failure.
    if not is_full_extent(extent):
        print(
            "\nThe extent is a pilot box, so these ratios compare part of one "
            "territorial\nauthority against its whole published count and are "
            "not meaningful."
        )

    # Anything the clip left outside the four study authorities would be a bug
    # in the boundaries rather than in the addresses, so it is worth naming.
    unexpected = sorted(set(counts.index) - set(QV_RATING_UNITS))
    if unexpected:
        print(f"\nAddresses outside the study authorities: {', '.join(unexpected)}")


def describe_suburbs(spine, limit=10):
    """Print the largest suburbs, as a shape check on the suburb reporting unit."""
    suburbs = spine["suburb_locality"].value_counts()

    print(RULE)
    print(f"{len(suburbs):,} distinct suburb localities. The largest {limit}:")
    for suburb, count in suburbs.head(limit).items():
        print(f"  {suburb!s:<32}{count:>9,}")


def resolve_out(out, *, extent):
    """Choose where the spine is written.

    Resolved here rather than as a config default, so that a pilot run cannot
    overwrite the full spine with a few streets of Wellington and leave every
    later step reading it without noticing.

    Args:
        out: The path from config.py, or None for the standard location.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The path to write the spine to.
    """
    if out is not None:
        return Path(out)
    return OUT_DIR / f"{OUT_STEM}{extent_suffix(extent)}.geoparquet"


def main(*, extent, fresh, out):
    """Build the address spine and write it out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        fresh: Ignore the extent cache and re-read from the source layer.
        out: Where to write the spine. None writes it to the standard location
            under temp/exposure/, named with ``extent_suffix(extent)``.

    Returns:
        1 if the spine could not be built, otherwise None.
    """
    out = resolve_out(out, extent=extent)

    study_areas = get_study_areas(constants.DEFAULT_CRS)

    # Every extent is clipped to the four authorities, not only the full one: a
    # box such as Porirua City's reaches past the study boundary into the Kapiti
    # Coast, whose addresses have no land value base rate and are not in the
    # study.
    clip_to = study_areas
    aoi = get_area_of_interest(extent)
    if aoi is not None:
        bbox = aoi.bbox(constants.DEFAULT_CRS)
        describe_extent(aoi.name, bbox)
    else:
        bbox = tuple(float(value) for value in study_areas.total_bounds)
        describe_extent(", ".join(study_areas["name"]), bbox)

    print("\nReading the LINZ NZ Addresses layer ...")
    try:
        spine = get_addresses(
            bbox=bbox,
            crs=constants.DEFAULT_CRS,
            clip_to=clip_to,
            use_cache=not fresh,
        )
    except ValueError as exc:
        # Raised by resolve_api_key when LINZ_API_KEY is missing.
        print(f"\nCould not read the layer: {exc}")
        return 1
    except requests.exceptions.RequestException as exc:
        print(f"\nThe request to LINZ failed: {exc}")
        print(
            "\nThe addresses layer is a national 800 MB export, so LINZ takes many\n"
            "minutes to build it and an occasional status poll returns a 502 during\n"
            "that wait. Re-running starts the wait over; the export usually completes\n"
            "server side regardless."
        )
        return 1

    if spine.empty:
        print("\nNo addresses found within the extent.")
        return 1

    describe_counts(spine, extent=extent)
    describe_suburbs(spine)

    out.parent.mkdir(parents=True, exist_ok=True)
    spine.to_parquet(out)

    print(RULE)
    print(f"Wrote {out}")
    print(f"  Rows    : {len(spine):,}")
    print(f"  Columns : {', '.join(spine.columns)}")
    print(f"  CRS     : {spine.crs}")
    return None


if __name__ == "__main__":
    main(extent=config.EXTENT, fresh=config.FRESH, out=config.OUT)
