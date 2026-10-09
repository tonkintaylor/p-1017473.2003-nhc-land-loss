"""Find where insured accessways cross water, and put a culvert or bridge there.

Reads the driveway corridors step 5 wrote, intersects them against both LINZ
river layers, keeps the crossings lying wholly inside their claim's insured
land, and draws a culvert or a bridge at each one kept.

    uv run --frozen python src/scripts/landloss/exposure/culverts_bridges/steps/s7_crossing_population/gen_crossing_population.py

The exposure is the **crossing**, not the structure: a culvert or a bridge
exists to carry the accessway over water, so where the accessway crosses nothing
there is nothing to find. Both river layers are read, because a narrow stream
exists only as a centreline while a river wide enough to need a bridge has an
areal extent, and the lines alone would miss exactly the crossings most likely
to carry a bridge.

Two limits are worth holding on to when reading the output. Both LINZ layers
carry **named** watercourses only, so the unnamed streams where most small
accessway crossings sit are invisible here, and the count is a floor rather than
an estimate. And the accessway itself is generated -- a straight line from the
building to the nearest road -- so a crossing is found where that line meets
water, not where a real driveway does.

The reasoning behind the 80/20 split is in
`landloss.exposure.culverts_bridges.crossings`. What it runs over, and for which
realisations, comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd

from landloss.domain import constants
from landloss.domain.loss_contract import CLAIM_ID_COLUMN, CROSSING_ID_COLUMN
from landloss.exposure.asset_ids import (
    CROSSING_ID_SUFFIX,
    mint_asset_ids,
    sort_by_location,
)
from landloss.exposure.coverage import keep_crossings_within_insured_land
from landloss.exposure.culverts_bridges.crossings import (
    describe_crossings,
    detect_crossings,
    sample_structures,
)
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_river_name_lines, get_nz_river_name_polygons
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population import (
    config,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    driveway_path,
    insured_land_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington river names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "crossing-population"

# The stream these draws come from, shared with the rest of the exposure module
# so the crossings of realisation 3 belong to the same modelled earthquake.
RNG_STREAM = "exposure"

# The rivers are fetched a little beyond the accessways, so a watercourse whose
# geometry starts just outside the extent is still there to be crossed.
FETCH_MARGIN_M = 50.0

RULE = "-" * 72


def crossing_population_path(realisation_id, *, extent):
    """Return the file a run writes one realisation's crossings to.

    Args:
        realisation_id: Which modelled earthquake this is.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.geoparquet"


def fetch_extent(accessways):
    """Return the bounding box the river layers are fetched over.

    Args:
        accessways: The driveway corridors.

    Returns:
        The accessways' own extent grown by :data:`FETCH_MARGIN_M`.
    """
    minx, miny, maxx, maxy = accessways.total_bounds
    return (
        minx - FETCH_MARGIN_M,
        miny - FETCH_MARGIN_M,
        maxx + FETCH_MARGIN_M,
        maxy + FETCH_MARGIN_M,
    )


def describe_inputs(accessways, lines, polygons):
    """Print what the crossing test is run over."""
    print(RULE)
    print(f"Accessways: {len(accessways):,}")
    print(f"River name lines: {len(lines):,}")
    print(f"River name polygons: {len(polygons):,}")
    if lines.empty and polygons.empty:
        print(
            "  Neither river layer returned anything over this extent, so no "
            "crossing can be found. That is a statement about the extent, not "
            "about the accessways."
        )


def describe_coverage(detected, kept):
    """Print how many crossings the insured land filter kept and dropped.

    Args:
        detected: How many crossings were detected on the accessways.
        kept: How many lie wholly inside their claim's insured land.
    """
    dropped = detected - kept
    share = f" ({dropped / detected:.0%})" if detected else ""
    print(RULE)
    print(f"Crossings detected: {detected:,}")
    print(f"Kept, wholly inside the claim's insured land: {kept:,}")
    print(f"Dropped: {dropped:,}{share}")
    if dropped:
        print(
            "  A dropped crossing lies partly outside the insured land, for "
            "example on the road reserve, because the driveways are not "
            "clipped to the property."
        )


def main(*, extent, realisation_ids, use_cached_extent):
    """Draw a crossing population per realisation and write each one out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to draw for.
        use_cached_extent: Whether to reuse the already-clipped river layers.
    """
    in_path = driveway_path(extent=extent)
    print(f"Reading the accessways from {in_path} ...", flush=True)
    accessways = gpd.read_parquet(in_path)
    insured_path = insured_land_path(extent=extent)
    print(f"Reading the insured land from {insured_path} ...", flush=True)
    insured = gpd.read_parquet(insured_path)

    bbox = fetch_extent(accessways)
    print("Fetching the river layers ...", flush=True)
    lines = get_nz_river_name_lines(
        bbox=bbox, crs=constants.DEFAULT_CRS, use_cache=use_cached_extent
    )
    polygons = get_nz_river_name_polygons(
        bbox=bbox, crs=constants.DEFAULT_CRS, use_cache=use_cached_extent
    )
    describe_inputs(accessways, lines, polygons)

    crossings = detect_crossings(accessways, lines, polygons)
    kept = keep_crossings_within_insured_land(crossings, insured)
    describe_coverage(len(crossings), len(kept))

    # The id is minted once, before any draw, so a crossing keeps the same id
    # in every realisation whichever structure it is given.
    kept = sort_by_location(kept)
    kept.insert(
        0, CROSSING_ID_COLUMN, mint_asset_ids(kept[CLAIM_ID_COLUMN], CROSSING_ID_SUFFIX)
    )

    for realisation_id in realisation_ids:
        print(RULE)
        print(f"Realisation {realisation_id}, stream {RNG_STREAM!r}")
        rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
        drawn = sample_structures(kept, rng)
        print(describe_crossings(drawn, len(accessways)).to_string())

        out_path = crossing_population_path(realisation_id, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        drawn.to_parquet(out_path)
        print(f"Wrote {len(drawn):,} crossings to {out_path}")

    print(RULE)
    print(
        "Both river layers carry named watercourses only, so the unnamed "
        "streams most small accessway crossings sit on are not counted here. "
        "This is a floor, not an estimate."
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        use_cached_extent=config.USE_CACHED_EXTENT,
    )
