"""Compute the probability of a retaining wall on each insured property.

Reads the insured land extent step 5 wrote, samples the slope and downhill
direction at each property off the LINZ elevation model, attaches the evidence
from GNS Science's mapped retaining walls, its cut slope and fill body mapping
and the National Liquefaction Model's landform classes, and writes one row per
property carrying the probability of a wall, the distribution of its height and
the probability that it is in poor condition.

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_probability.py

Needs the Koordinates key in ``.env`` the first time a layer is fetched.

**The slope-driven part is a beta stand-in and none of it is evidence about
Wellington.** The GNS mapping is one-sided evidence: it covers Wellington City
only and shows only the walls visible from above, so it raises a probability
where a wall is mapped and never lowers one where none is. The reasoning behind
every number is in `landloss.exposure.rw.wall_probability` and
`landloss.exposure.rw.beta_population`.

This is run once. ``gen_wall_population.py`` draws each realisation from the
file it writes.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np
import rioxarray

from landloss.common.utils.terrain import (
    DOWNHILL_AZIMUTH_NAME,
    SLOPE_NAME,
    cell_size,
    downhill_azimuth_degrees,
    sample_at_points,
    slope_degrees,
    write_raster,
)
from landloss.domain import constants
from landloss.exposure.rw.wall_probability import (
    MIN_MAPPED_WALL_LENGTH_M,
    attach_evidence,
    wall_probability_table,
)
from landloss.io.readers import (
    get_dem,
    get_gns_slide_morphology,
    get_nlm_geomorphology,
    get_slide_genesis,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "wall-probability"

# The property's own point is where the slope is sampled, so the extent grows by
# enough that a property on the edge still sits inside the elevation model.
DEM_MARGIN_M = 200.0

# The GNS layers are read over the properties' extent grown by the coverage
# buffer, so a wall mapped just outside the edge property is not clipped away.
LAYER_MARGIN_M = 10.0

SLOPE_COLUMN = "slope_deg"
AZIMUTH_COLUMN = "downhill_azimuth_deg"

RULE = "-" * 72


def wall_probability_path(*, pilot):
    """Return the file a run writes the probabilities to.

    Args:
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def sample_terrain(properties, *, use_cached_dem):
    """Return the properties with slope and downhill azimuth attached.

    The two are derived from the elevation model over the properties' own
    extent and sampled at each property's representative point. A property whose
    point falls outside the elevation model comes back with NaN rather than a
    guess, and draws no wall.

    Args:
        properties: The insured land extent, one row per property.
        use_cached_dem: Whether to reuse an already-fetched elevation model.

    Returns:
        A copy carrying the slope and azimuth columns, with point geometry, and
        the elevation model's cell size in metres.
    """
    points = properties.geometry.representative_point()
    minx, miny, maxx, maxy = points.total_bounds
    bbox = (
        minx - DEM_MARGIN_M,
        miny - DEM_MARGIN_M,
        maxx + DEM_MARGIN_M,
        maxy + DEM_MARGIN_M,
    )

    print("Fetching the elevation model over the properties ...", flush=True)
    dem_path = get_dem(bbox, crs=constants.DEFAULT_CRS, use_cache=use_cached_dem)
    print(f"  {dem_path}")

    # Loaded rather than left lazy: an open GDAL handle finalised during
    # interpreter shutdown surfaces as a bare "Error in sys.excepthook".
    with rioxarray.open_rasterio(dem_path, masked=True) as opened:
        dem = opened.squeeze(drop=True).load()
    resolution = cell_size(dem)

    # Written then sampled, because the sampler reads from a file.
    slope_path = WORK_DIR / f"{OUT_STEM}-slope.tif"
    azimuth_path = WORK_DIR / f"{OUT_STEM}-azimuth.tif"
    write_raster(slope_degrees(dem, resolution).rename(SLOPE_NAME), slope_path)
    write_raster(
        downhill_azimuth_degrees(dem, resolution).rename(DOWNHILL_AZIMUTH_NAME),
        azimuth_path,
    )

    attached = properties.copy()
    attached[SLOPE_COLUMN] = sample_at_points(slope_path, points).to_numpy()
    attached[AZIMUTH_COLUMN] = sample_at_points(azimuth_path, points).to_numpy()
    return attached, resolution


def attach_gns_evidence(properties, *, use_cached_layers):
    """Return the properties with the GNS and NLM evidence attached.

    Args:
        properties: The insured land extent, one row per property.
        use_cached_layers: Whether to reuse already-fetched clipped layers.

    Returns:
        A copy carrying the evidence columns.
    """
    minx, miny, maxx, maxy = properties.total_bounds
    bbox = (
        minx - LAYER_MARGIN_M,
        miny - LAYER_MARGIN_M,
        maxx + LAYER_MARGIN_M,
        maxy + LAYER_MARGIN_M,
    )
    print("Reading the GNS SLIDE and NLM layers over the properties ...", flush=True)
    morphology = get_gns_slide_morphology(bbox=bbox, use_cache=use_cached_layers)
    genesis = get_slide_genesis(bbox=bbox, use_cache=use_cached_layers)
    geomorphology = get_nlm_geomorphology(bbox=bbox, use_cache=use_cached_layers)
    print(
        f"  {len(morphology):,} morphology lines, {len(genesis):,} genesis "
        f"polygons, {len(geomorphology):,} NLM polygons"
    )
    return attach_evidence(
        properties,
        morphology=morphology,
        genesis=genesis,
        geomorphology=geomorphology,
    )


def describe_evidence(table):
    """Print how much of the population each source of evidence reaches."""
    print(RULE)
    total = len(table)
    mapped = table["mapped_wall_length_m"] >= MIN_MAPPED_WALL_LENGTH_M
    engineered = table["engineered_share"] > 0
    print(f"Properties: {total:,}")
    print(
        f"  with a GNS-mapped wall (at least {MIN_MAPPED_WALL_LENGTH_M:g} m): "
        f"{int(mapped.sum()):,} ({mapped.mean():.1%})"
    )
    print(
        f"  touching a cut slope or fill body: {int(engineered.sum()):,} "
        f"({engineered.mean():.1%})"
    )
    print(f"  on a plain landform: {int(table['on_plain'].sum()):,}")
    print("  landform classes:")
    print(table["landform"].replace("", "(none)").value_counts().to_string())


def describe_probabilities(table):
    """Print the probabilities the realisations will be drawn from."""
    print(RULE)
    p_wall = table["p_wall"].to_numpy(dtype=float)
    known = np.isfinite(p_wall)
    print(f"Probability of a wall known for {int(known.sum()):,} of {len(table):,}")
    if not known.any():
        return
    print(f"  expected walls: {p_wall[known].sum():,.0f} ({p_wall[known].mean():.1%})")
    quantiles = np.percentile(p_wall[known], [0, 25, 50, 75, 100])
    labels = ("min", "25%", "median", "75%", "max")
    print(
        "  p_wall: "
        + "   ".join(f"{k}={v:.2f}" for k, v in zip(labels, quantiles, strict=True))
    )
    weights = p_wall[known]
    for size in ("small", "medium", "large"):
        expected = float((weights * table.loc[known, f"p_{size}"]).sum())
        print(f"  expected {size} walls: {expected:,.0f}")


def main(*, pilot, use_cached_dem, use_cached_layers):
    """Compute the wall probabilities and write them out.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        use_cached_dem: Whether to reuse an already-fetched elevation model.
        use_cached_layers: Whether to reuse already-fetched clipped GNS and NLM
            layers.
    """
    extent_path = insured_land_path(pilot=pilot)
    print(f"Reading the insured land from {extent_path} ...")
    properties = gpd.read_parquet(extent_path)

    with_terrain, resolution = sample_terrain(properties, use_cached_dem=use_cached_dem)
    print(f"  slope and azimuth sampled off a {resolution:.0f} m DEM")
    with_evidence = attach_gns_evidence(
        with_terrain, use_cached_layers=use_cached_layers
    )
    describe_evidence(with_evidence)

    table = wall_probability_table(with_evidence)
    # Written as points: the draw places a line from the point, and the polygon
    # is read again from step 5 for the coverage filter.
    table = table.set_geometry(properties.geometry.representative_point())
    describe_probabilities(table)

    out_path = wall_probability_path(pilot=pilot)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(table):,} properties to {out_path}")
    print(
        "The slope-driven part is a beta stand-in. It is not evidence about "
        "Wellington; see T-19 for what replaces it."
    )


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        use_cached_dem=config.USE_CACHED_DEM,
        use_cached_layers=config.USE_CACHED_LAYERS,
    )
