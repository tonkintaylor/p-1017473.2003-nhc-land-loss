"""Estimate a land value for every address in the spine.

Takes the address spine from step 1, tags each address as flat or hill against
the National Liquefaction Model's flatland layer, and spreads each territorial
authority's published average residential land value across its addresses in
proportion to a landform multiplier. A per-TA normalising constant pulls the
modelled mean back onto the published average, so the landform judgement moves
value between properties without changing what any authority is worth in total.
That is what the per-TA table this run prints is there to show.

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/s4_estimate_land_value.py

The run settings -- the pilot box or the full study area, whether to ignore the
caches, and the input and output paths -- come from config.py beside this
script rather than from the command line.

The script is numbered s4 within this step, not s1, because terrain,
accessibility and amenity are s1 to s3 of the same step. Terrain is
s1_build_terrain_attributes.py and accessibility s2_build_accessibility.py; the
gap at s3 is deliberate and amenity drops into it without anything being
renamed.

Terrain is joined on when that s1 output exists, and it changes the answer in
two ways. Flat addresses standing above the land around them are promoted to
elevated flat, which is the class Phase 1 had a factor for but nothing to
assign; and slope and topographic position feed a continuous modifier that
spreads value *within* each landform class. Without the modifier every address
of a class in an authority is worth exactly the same, which is why Phase 1 gave
136 suburbs only 9 distinct median rates between them. The distinct rate count
this run prints is what that fix is measured by.

The join is optional on purpose. With no terrain file the run falls back to
Phase 1 behaviour and says so, so that the two steps can be run independently
and a new extent can be valued before any DEM has been fetched for it.

Accessibility from s2_build_accessibility.py is joined on the same way when its
output exists, and feeds a second modifier that spreads value within each
landform class by closeness to the main centres and to a railway station. It is
optional for the same reason, and the run says when it goes without.

The address spine is rebuilt from LINZ if it is not already on disk, so this can
be run on its own. Set PILOT in config.py to work over the small Wellington
box.

Requires TNT_KOORDINATES_API_KEY in .env for the flatland layer, and LINZ_API_KEY
if the address spine has to be rebuilt.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from landloss.domain import constants
from landloss.exposure.addresses import get_addresses
from landloss.exposure.land.accessibility import (
    GRAVITY_COLUMN,
    STATION_DISTANCE_COLUMN,
)
from landloss.exposure.land.land_value import (
    COMMON_VALUATION_DATE,
    SLOPE_COLUMN,
    TOPOGRAPHIC_POSITION_COLUMN,
    estimate_land_value,
    index_base_rates,
    load_base_rates,
    load_factors,
    summarise_by_suburb,
)
from landloss.exposure.land.landform import (
    ELEVATED_FLAT,
    FLAT,
    HILL,
    LANDFORM_COLUMN,
    assign_elevated_flat,
    classify_landform,
    get_flatland,
)
from landloss.io.area_of_interest import SMALL_WLG_PILOT, get_study_areas
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.paths import REPO_ROOT, TEMP_DIR

# Wellington suburb names are macronised -- Ōwhiro Bay, Pāuatahanui -- which the
# default cp1252 Windows console cannot encode, so printing one raises. Ask for
# UTF-8 rather than stripping the macrons, because the names are worth getting
# right.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# temp/ is gitignored. These are working layers, rebuildable from the source and
# the packaged assets, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "exposure"
SPINE_NAME = "address-spine.geoparquet"
PILOT_SPINE_NAME = "address-spine-pilot.geoparquet"
TERRAIN_NAME = "terrain-by-address.geoparquet"
PILOT_TERRAIN_NAME = "terrain-by-address-pilot.geoparquet"
ACCESSIBILITY_NAME = "accessibility-by-address.geoparquet"
PILOT_ACCESSIBILITY_NAME = "accessibility-by-address-pilot.geoparquet"
OUT_NAME = "land-value-by-address.geoparquet"
PILOT_OUT_NAME = "land-value-by-address-pilot.geoparquet"
COHORTS_NAME = "land-value-by-suburb.csv"
PILOT_COHORTS_NAME = "land-value-by-suburb-pilot.csv"

# The join key the terrain attributes come back on, and the three columns that
# have to be there before the join is worth making.
ID_COLUMN = "address_id"
TERRAIN_COLUMNS = (ID_COLUMN, SLOPE_COLUMN, TOPOGRAPHIC_POSITION_COLUMN)
ACCESSIBILITY_COLUMNS = (ID_COLUMN, GRAVITY_COLUMN, STATION_DISTANCE_COLUMN)

# How high a flat address has to stand above its neighbourhood before it is
# elevated flat. Read from the factors asset rather than set here, because it is
# a tuned number and belongs beside the window it was tuned against.
ELEVATED_FLAT_THRESHOLD_PARAMETER = "elevated_flat_min_topographic_position_m"

# Rates are compared to the cent before being counted as distinct. Two addresses
# whose modelled rates differ in the twelfth decimal place are the same rate as
# far as any map, ranking or report is concerned, and counting them apart would
# turn the one measurement this run exists to make into a count of floating point
# noise.
RATE_DECIMALS = 2

SUBURB_LIMIT = 10
RULE = "-" * 72


def get_spine(path, bbox, clip_to, *, use_cache):
    """Read the address spine from disk, or build it from LINZ if it is absent.

    Args:
        path: The geoparquet step 1 writes.
        bbox: The extent to read, if the spine has to be rebuilt.
        clip_to: The boundary to cut a rebuilt spine back to.
        use_cache: Whether to use the extent cache when rebuilding.

    Returns:
        The address spine.
    """
    if path.exists():
        print(f"Reading the address spine from {path} ...")
        return gpd.read_parquet(path)

    # Rebuilt rather than refused, so that this script runs on a clean checkout.
    # It is written back out to the step 1 path, so the next run of either script
    # finds it there.
    print(f"No address spine at {path}; rebuilding it from LINZ ...")
    spine = get_addresses(
        bbox=bbox, crs=constants.DEFAULT_CRS, clip_to=clip_to, use_cache=use_cache
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    spine.to_parquet(path)
    print(f"Wrote the rebuilt spine to {path}")
    return spine


def read_terrain(path):
    """Read the sampled terrain attributes, or say why the run goes without them.

    Absence is a supported answer rather than a failure. The terrain step fetches
    a DEM, which over the full study area is a long background job, and an extent
    is worth valuing on its landform class alone before that has been run. What
    is not acceptable is doing it silently, because a run with no terrain looks
    exactly like a run with terrain until somebody counts the distinct rates.

    Args:
        path: The geoparquet s1_build_terrain_attributes.py writes.

    Returns:
        The attributes as a plain DataFrame, with the geometry dropped because
        the addresses already carry it, or None if the file is not there.
    """
    if not path.exists():
        print(f"\nNo terrain attributes at {path}.")
        print(
            "  Valuing on landform class alone, which is Phase 1 behaviour: no\n"
            "  address can be elevated flat, and every address of a class within a\n"
            "  territorial authority is worth exactly the same. Run\n"
            "  s1_build_terrain_attributes.py over this extent to turn the terrain\n"
            "  modifier on."
        )
        return None

    print(f"\nReading the terrain attributes from {path} ...")
    terrain = gpd.read_parquet(path)

    # Dropped to a plain DataFrame, because the addresses being joined onto carry
    # the geometry already and two geometry columns in one merge is a silent
    # rename waiting to happen.
    return pd.DataFrame(terrain.drop(columns=terrain.geometry.name, errors="ignore"))


def attach_terrain(classified, terrain, factors):
    """Join the terrain onto the addresses and promote the elevated flat ones.

    The join is validated one-to-one. A duplicated address in either frame would
    otherwise multiply rows through the merge and quietly inflate every count
    downstream of here, which is a much harder thing to notice than a crash.

    Args:
        classified: Addresses carrying their landform class and ``address_id``.
        terrain: The attributes from :func:`read_terrain`.
        factors: The land value model parameters, carrying the elevated flat
            threshold.

    Returns:
        The addresses with the two terrain columns joined on and the landform
        class updated, or the addresses unchanged if the terrain file does not
        carry what the join needs.
    """
    missing = [column for column in TERRAIN_COLUMNS if column not in terrain.columns]
    if missing:
        print(
            f"  The terrain file is missing {', '.join(missing)}, so it cannot be\n"
            "  joined. Valuing on landform class alone."
        )
        return classified

    joined = classified.merge(
        terrain[list(TERRAIN_COLUMNS)],
        on=ID_COLUMN,
        how="left",
        validate="one_to_one",
    )

    # A left join keeps every address, so an address the terrain file says
    # nothing about arrives here as NaN rather than disappearing. The model reads
    # that as "nothing distinguishes this address from its cohort", which is the
    # right default and the wrong thing to find out about later.
    unmatched = int(joined[SLOPE_COLUMN].isna().sum())
    print(f"  Addresses with terrain: {len(joined) - unmatched:,} of {len(joined):,}")
    if unmatched:
        print(
            f"  {unmatched:,} address(es) had no terrain value. These carry no\n"
            "  terrain signal and can never be elevated flat. If this is not a\n"
            "  handful, the terrain file was built over a different extent."
        )

    return assign_elevated_flat(
        joined,
        min_topographic_position_m=factors[ELEVATED_FLAT_THRESHOLD_PARAMETER],
    )


def read_accessibility(path):
    """Read the accessibility attributes, or say why the run goes without them.

    Absence is a supported answer, as it is for terrain, and is said out loud for
    the same reason.

    Args:
        path: The geoparquet s2_build_accessibility.py writes.

    Returns:
        The attributes as a plain DataFrame, or None if the file is not there.
    """
    if not path.exists():
        print(f"\nNo accessibility attributes at {path}.")
        print(
            "  Valuing without the accessibility modifier, so an address's\n"
            "  closeness to the centres and to a railway station changes nothing.\n"
            "  Run s2_build_accessibility.py over this extent to turn it on."
        )
        return None

    print(f"\nReading the accessibility attributes from {path} ...")
    accessibility = gpd.read_parquet(path)
    return pd.DataFrame(
        accessibility.drop(columns=accessibility.geometry.name, errors="ignore")
    )


def attach_accessibility(classified, accessibility):
    """Join the accessibility attributes onto the addresses, one-to-one.

    Args:
        classified: Addresses carrying ``address_id``.
        accessibility: The attributes from :func:`read_accessibility`.

    Returns:
        The addresses with the two accessibility columns joined on, or the
        addresses unchanged if the file does not carry what the join needs.
    """
    missing = [
        column
        for column in ACCESSIBILITY_COLUMNS
        if column not in accessibility.columns
    ]
    if missing:
        print(
            f"  The accessibility file is missing {', '.join(missing)}, so it\n"
            "  cannot be joined. Valuing without the accessibility modifier."
        )
        return classified

    joined = classified.merge(
        accessibility[list(ACCESSIBILITY_COLUMNS)],
        on=ID_COLUMN,
        how="left",
        validate="one_to_one",
    )

    unmatched = int(joined[GRAVITY_COLUMN].isna().sum())
    print(
        f"  Addresses with accessibility: {len(joined) - unmatched:,} of {len(joined):,}"
    )
    if unmatched:
        print(
            f"  {unmatched:,} address(es) had no accessibility value and sit at the\n"
            "  middle of their cohort. If this is not a handful, the accessibility\n"
            "  file was built over a different extent."
        )
    return joined


def describe_landform(classified):
    """Print the landform split per authority, including the elevated flat share.

    The last column is the one being tuned. Elevated flat is assigned from the
    terrain alone, so the threshold in the factors asset decides how much of the
    flat land gets the raised-terrace premium, and the only way to judge whether
    the threshold is sensible is to see what share of flat land it actually
    promotes in each authority.
    """
    print(RULE)
    print("Landform classification")
    print(
        f"{'Territorial authority':<24}{'Hill':>9}{'Flat':>9}"
        f"{'Elev flat':>11}{'Flat %':>9}{'Promoted %':>12}"
    )

    grouped = classified.groupby("territorial_authority", sort=True)
    for ta_name, rows in grouped:
        counts = rows[LANDFORM_COLUMN].value_counts()
        hill = int(counts.get(HILL, 0))
        flat = int(counts.get(FLAT, 0))
        elevated = int(counts.get(ELEVATED_FLAT, 0))

        total = hill + flat + elevated
        flat_share = 100 * (flat + elevated) / total if total else 0.0
        promoted = 100 * elevated / (flat + elevated) if flat + elevated else 0.0
        print(
            f"{ta_name:<24}{hill:>9,}{flat:>9,}{elevated:>11,}"
            f"{flat_share:>8.1f}%{promoted:>11.1f}%"
        )

    print(
        "\nFlat % is flat plus elevated flat as a share of all addresses.\n"
        "Promoted % is elevated flat as a share of the flat land alone -- the\n"
        "share the topographic position threshold is judged on."
    )


def describe_distinct_rates(valued, cohorts):
    """Print how many distinct land rates the model actually produced.

    This is the measurement Phase 2 exists to move. On landform class alone an
    address's rate depends on nothing but its territorial authority and one of
    three classes, so four authorities can produce at most twelve rates between
    them however many addresses they hold -- and Phase 1 gave 136 suburbs 9
    distinct medians. A map and a suburb ranking drawn off that many values carry
    almost no information. The continuous terrain modifier is what breaks the
    tie, and this count is the evidence that it did.
    """
    address_rates = valued["land_rate_nzd_per_m2"].round(RATE_DECIMALS).nunique()
    cohort_rates = cohorts["median_land_rate_nzd_per_m2"].round(RATE_DECIMALS).nunique()

    print(RULE)
    print("Distinct modelled land rates, to the cent")
    print(f"  Across {len(valued):>9,} addresses          : {address_rates:>9,}")
    print(f"  Across {len(cohorts):>9,} suburb cohorts     : {cohort_rates:>9,}")


def describe_calibration(valued, base_rates):
    """Print the modelled TA mean against the published average it is anchored on.

    This is the table that makes the normalisation visible. If a modelled mean
    does not equal the indexed published average, the clip bound every address in
    that authority and the residual had nowhere to go -- which means the clip
    multiples and the landform factors in the asset disagree with each other.
    """
    indexed = index_base_rates(base_rates).set_index("ta_name")

    print(RULE)
    print(
        f"Calibration against the published averages, indexed to {COMMON_VALUATION_DATE}"
    )
    print(
        f"{'Territorial authority':<24}{'Addresses':>11}"
        f"{'Modelled mean':>16}{'Published':>14}{'Diff':>9}"
    )

    grouped = valued.groupby("territorial_authority", sort=True)
    for ta_name, rows in grouped:
        modelled = float(rows["land_value_nzd"].mean())
        published = float(indexed.loc[ta_name, "indexed_land_value_nzd"])

        # Relative rather than absolute, because a few dollars on a $621,000
        # average is floating point and several thousand is a broken clip. The
        # zero is normalised because an exact hit lands on -0.0 as often as 0.0,
        # and a minus sign in front of the number that proves the calibration
        # worked reads like a fault.
        diff = round(100 * (modelled - published) / published, 2)
        diff = 0.0 if diff == 0 else diff
        print(
            f"{ta_name:<24}{len(rows):>11,}"
            f"{modelled:>16,.0f}{published:>14,.0f}{diff:>8.2f}%"
        )


def describe_suburbs(cohorts, limit=SUBURB_LIMIT):
    """Print the highest and lowest value suburbs by modelled rate."""
    ranked = cohorts.sort_values("median_land_rate_nzd_per_m2", ascending=False)

    # A pilot produces fewer cohorts than the two tables would show between them,
    # and printing the same rows twice under two headings reads like a bug rather
    # than like a short list. So below that many, the whole thing is printed once.
    if len(ranked) <= 2 * limit:
        tables = [(f"All {len(ranked)} suburb cohorts by median land rate", ranked)]
    else:
        tables = [
            (f"Top {limit} suburb cohorts by median land rate", ranked.head(limit)),
            (f"Bottom {limit} suburb cohorts by median land rate", ranked.tail(limit)),
        ]

    for heading, rows in tables:
        print(RULE)
        print(heading)
        print(f"{'Suburb':<28}{'TA':<18}{'Landform':<14}{'Rate $/m2':>11}{'Count':>9}")
        for _, row in rows.iterrows():
            print(
                f"{row['suburb_locality']!s:<28}"
                f"{row['territorial_authority']!s:<18}"
                f"{row[LANDFORM_COLUMN]!s:<14}"
                f"{row['median_land_rate_nzd_per_m2']:>11,.0f}"
                f"{row['address_count']:>9,}"
            )


def _default(path, pilot_name, name, *, pilot):
    """Return ``path`` as a Path, or the standard location under temp/exposure/."""
    if path is not None:
        return Path(path)
    return WORK_DIR / (pilot_name if pilot else name)


def resolve_outputs(*, pilot, spine, terrain, accessibility, out, cohorts):
    """Choose where the spine is read from and where the two outputs are written.

    Resolved here rather than as config defaults, so that a pilot run cannot
    overwrite the full outputs with a few streets of Wellington and leave
    everything downstream reading them without noticing.

    Args:
        pilot: Whether the run is over the pilot box.
        spine: The address spine path from config.py, or None for the default.
        terrain: The terrain attributes path, or None for the default.
        accessibility: The accessibility attributes path, or None for the
            default.
        out: The valued address path, or None for the default.
        cohorts: The cohort table path, or None for the default.

    Returns:
        The spine path, the terrain path, the accessibility path, the valued
        address path and the cohort table path.
    """
    return (
        _default(spine, PILOT_SPINE_NAME, SPINE_NAME, pilot=pilot),
        _default(terrain, PILOT_TERRAIN_NAME, TERRAIN_NAME, pilot=pilot),
        _default(
            accessibility, PILOT_ACCESSIBILITY_NAME, ACCESSIBILITY_NAME, pilot=pilot
        ),
        _default(out, PILOT_OUT_NAME, OUT_NAME, pilot=pilot),
        _default(cohorts, PILOT_COHORTS_NAME, COHORTS_NAME, pilot=pilot),
    )


def resolve_extent(study_areas, *, pilot):
    """Return the bounding box, clip boundary and name of the extent to run over.

    The clip matters as much as the box. The four authorities sit in a rectangle
    that also contains most of the Wairarapa, so the full run is cut back to the
    real boundaries; a pilot is a rectangle already and needs no clip.
    """
    if pilot:
        return SMALL_WLG_PILOT.bbox(constants.DEFAULT_CRS), None, SMALL_WLG_PILOT.name

    bbox = tuple(float(value) for value in study_areas.total_bounds)
    return bbox, study_areas, ", ".join(study_areas["name"])


def describe_extent(name, bbox):
    """Print the extent being read, so a mistaken study area is obvious at once."""
    minx, miny, maxx, maxy = bbox

    print(RULE)
    print(f"Repo root : {REPO_ROOT}")
    print(f"Extent    : {name}")
    print(f"  NZTM    : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size    : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")
    print()


def read_spine(path, bbox, clip_to, *, use_cache):
    """Read or rebuild the spine, or print why it could not be had and return None."""
    try:
        return get_spine(path, bbox, clip_to, use_cache=use_cache)
    except ValueError as exc:
        # Raised by resolve_api_key when LINZ_API_KEY is missing.
        print(f"\nCould not build the address spine: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        print(f"\nThe request to LINZ failed: {exc}")
        return None


def read_flatland(bbox, clip_to, *, use_cache):
    """Read the flatland layer, or print why it could not be read and return None."""
    try:
        return get_flatland(
            bbox=bbox,
            crs=constants.DEFAULT_CRS,
            clip_to=clip_to,
            use_cache=use_cache,
        )
    except ValueError as exc:
        # Raised by resolve_api_key when TNT_KOORDINATES_API_KEY is missing.
        print(f"\nCould not read the flatland layer: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        print(f"\nThe request to Koordinates failed: {exc}")
        print(
            "\nThe NLM flatland layer is a national export, so the first request "
            "takes\nmany minutes to build server side and an occasional status poll "
            "returns a\n502 during that wait, which ttpy treats as fatal. Re-running "
            "starts the\nwait over; the export usually completes regardless."
        )
        return None


def write_outputs(valued, cohorts, out, cohorts_out):
    """Write the valued addresses and the cohort table, and print what was written."""
    out.parent.mkdir(parents=True, exist_ok=True)
    valued.to_parquet(out)

    cohorts_out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel on Windows opens the macronised suburb names correctly
    # rather than mangling them; plain utf-8 is read as cp1252 on a double click.
    cohorts.to_csv(cohorts_out, index=False, encoding="utf-8-sig")

    print(RULE)
    print(f"Wrote {out}")
    print(f"  Rows    : {len(valued):,}")
    print(f"  Columns : {', '.join(valued.columns)}")
    print(f"Wrote {cohorts_out}")
    print(f"  Rows    : {len(cohorts):,} suburb/landform cohorts")


def main(*, pilot, fresh, spine, terrain, accessibility, out, cohorts):
    """Estimate a land value for every address in the spine.

    Args:
        pilot: Use the small Wellington pilot box instead of the full study area.
        fresh: Ignore the extent cache and re-read from the source layers.
        spine: The address spine from step 1. None reads the standard location
            under temp/exposure/, with a pilot name when ``pilot`` is True.
            Rebuilt from LINZ if it is not there.
        terrain: The terrain attributes from s1. None reads the standard
            location. If the file is not there the run falls back to valuing on
            landform class alone.
        accessibility: The accessibility attributes from s2. None reads the
            standard location. If the file is not there the run values without
            the accessibility modifier.
        out: Where to write the valued addresses. None writes to the standard
            location.
        cohorts: Where to write the per-suburb cohort table. None writes to the
            standard location.

    Returns:
        1 if the spine or the flatland layer could not be had, otherwise None.
    """
    spine_path, terrain_path, accessibility_path, out, cohorts_out = resolve_outputs(
        pilot=pilot,
        spine=spine,
        terrain=terrain,
        accessibility=accessibility,
        out=out,
        cohorts=cohorts,
    )

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox, clip_to, extent_name = resolve_extent(study_areas, pilot=pilot)
    describe_extent(extent_name, bbox)

    addresses = read_spine(spine_path, bbox, clip_to, use_cache=not fresh)
    if addresses is None:
        return 1
    if addresses.empty:
        print("\nThe address spine is empty; there is nothing to value.")
        return 1

    print(f"Addresses in the spine: {len(addresses):,}")
    print("\nReading the NLM flatland layer ...")
    flatland = read_flatland(bbox, clip_to, use_cache=not fresh)
    if flatland is None:
        return 1

    print(f"Flatland polygons: {len(flatland):,}")

    base_rates = load_base_rates()
    factors = load_factors()

    classified = classify_landform(addresses, flatland)

    attributes = read_terrain(terrain_path)
    if attributes is not None:
        classified = attach_terrain(classified, attributes, factors)

    reachable = read_accessibility(accessibility_path)
    if reachable is not None:
        classified = attach_accessibility(classified, reachable)

    describe_landform(classified)

    valued = estimate_land_value(classified, base_rates=base_rates, factors=factors)
    describe_calibration(valued, base_rates)

    cohort_table = summarise_by_suburb(valued)
    describe_distinct_rates(valued, cohort_table)
    describe_suburbs(cohort_table)

    write_outputs(valued, cohort_table, out, cohorts_out)
    return None


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        fresh=config.FRESH,
        spine=config.SPINE,
        terrain=config.TERRAIN,
        accessibility=config.ACCESSIBILITY,
        out=config.LAND_VALUE_OUT,
        cohorts=config.COHORTS_OUT,
    )
