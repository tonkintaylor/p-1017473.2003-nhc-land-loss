"""Give every urban failure polygon its fragility for one exposure world.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s8_urban_slope_fragility/gen_urban_slope_fragility.py

Run landslide step 7 (the polygons), exposure retaining wall step 6 (the walls
each world drew) and shaking steps 2 and 3 (the site class grid and the PGV
grid) first, over the same extent.

The run settings -- the extent, which worlds, the
rate setting and the return period of the demand -- come from ``config.py``
beside this script rather than from the command line.

For each world ``w`` the step joins each polygon to the walls drawn on its
edge in that world (at most one per line, and every line on the edge is read,
because a wall split at a property boundary is several lines), insured or
not: step 6's drawn walls are
every wall the world drew before the claim and coverage filters, because those
decide what is insured, not whether a wall holds the slope (decision 36 of the
build contract). An uninsured wall gives its polygon the wall state and curve
with ``rw_id`` null. It writes one fragility row per polygon
(``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``
section 4; the build contract, sections 3.8, 6 and 7.7):

1. **The wall state.** A polygon any of whose edge lines drew a sloping-land
   wall in world ``w``, insured or not, is in the ``fill_wall`` or
   ``cut_wall`` state of its own ``wall_position`` and takes the curve of the
   first such wall in edge order; every other polygon is ``no_wall``. A flat-land
   wall is never taken, even on a polygon edge: vul shaking rw step 9 draws
   it (when insured), and nowhere else does. The state picks the fixed
   geometry and depths step 7 computed for it.
2. **The median.** A polygon with a wall takes the published wall curve for
   the wall's size and condition (``retaining-wall-fragility.csv``,
   [koutsoupaki_2023]), converted from PGA to PGV by the study's own PGV/PGA
   ratio at the polygon's representative point: shaking step 3's PGV grid over
   the unscaled TS1170.5 PGA grid on the same cells. A polygon without a wall
   takes the localised median from its continuous Kingsbury rating
   (``landloss.hazard.landslide.urban.fragility.localised_theta_base_m_s``).
3. **The adjustments.** The median is divided by the topographic amplification
   factor step 7 put on the polygon and multiplied by the rate factor of the
   run's setting (``URBAN_RATE_FACTORS``), both recorded on the row.

A fragility is a probability of failure at a level of shaking: step 9 samples
the earthquake's PGV at the representative point and draws against the row's
lognormal. Nothing is drawn here.

Writes one GeoParquet per world, sorted by ``slope_id`` with a fresh index,
under ``temp/hazard/landslide/``, with the extent's ``extent_suffix``
(``-pilot`` for the small Wellington pilot).
"""

import sys

import geopandas as gpd
import numpy as np
import rioxarray

from landloss.common.utils.terrain import sample_at_points
from landloss.domain.loss_contract import RW_ID_COLUMN
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import fragility, geometry
from landloss.hazard.shaking.site_class import demand_on_site_class_grid
from landloss.io.area_of_interest import extent_suffix
from landloss.io.ts1170 import get_ts1170_pga
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    drawn_walls_path,
)
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons.gen_urban_slope_polygons import (
    urban_slope_polygons_path,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import config
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    read_site_class,
    site_class_path,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv.gen_pgv import output_path
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. This is a working layer, rebuildable from the polygons
# and the drawn walls, so it has no business in a diff.
WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "urban-slope-model"

WORLD_ID_COLUMN = "world_id"

# The model file's columns: the contract's (fragility.MODEL_COLUMNS) with
# world_id inserted after slope_id (contract section 3.8).
MODEL_COLUMNS = (
    fragility.MODEL_COLUMNS[0],
    WORLD_ID_COLUMN,
    *fragility.MODEL_COLUMNS[1:],
)

RULE = "-" * 72


def urban_slope_model_path(world_id, *, extent):
    """Return the file a run writes one world's model to.

    Args:
        world_id: The exposure world the model was built for.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The output path, under ``temp/hazard/landslide/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-w{world_id:03d}{suffix}.geoparquet"


def read_grid(path):
    """Read one raster a shaking step wrote, nodata masked to NaN."""
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def representative_points(polygons):
    """Return the point each polygon's demand is read at, as a located series."""
    return gpd.GeoSeries(polygons[geometry.REP_POINT_COLUMN], crs=polygons.crs)


def sample_site_class(points, *, extent):
    """Read the TS1170.5 site class at each point, NaN off the grid."""
    return sample_at_points(site_class_path(extent=extent), points)


def add_world_id(model, world_id):
    """Insert the world id after the slope id, as the contract orders the columns."""
    model = model.copy()
    model.insert(
        model.columns.get_loc(geometry.SLOPE_ID_COLUMN) + 1,
        WORLD_ID_COLUMN,
        np.full(len(model), world_id, dtype=np.int64),
    )
    return model[list(MODEL_COLUMNS)]


def describe_demand(ratio, site_class):
    """Print the PGV/PGA ratio and the site classes the polygons read."""
    finite = ratio.to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    print(
        f"PGV/PGA ratio at the representative points: {len(finite):,} of "
        f"{len(ratio):,} on the grid"
    )
    if finite.size:
        print(
            f"  m/s per g: min {finite.min():.3f}   median {np.median(finite):.3f}   "
            f"max {finite.max():.3f}"
        )
    classes = site_class.dropna().round().astype(int)
    print("Site class at the representative points:")
    for cls, count in classes.value_counts().sort_index().items():
        print(f"  {cls}: {count:,}")


def describe_model(model, *, rate_setting):
    """Print the counts contract section 3.8 asks a run to report."""
    print(RULE)
    print(
        f"Rate setting {rate_setting!r}, factor "
        f"{fragility.rate_factor(rate_setting):.4f} on every median"
    )
    print("Polygons by wall state and fragility basis:")
    counts = (
        model.groupby([fragility.STATE_COLUMN, "fragility_basis"])
        .size()
        .rename("polygons")
    )
    print(counts.to_string())
    print("Median theta (m/s) by Kingsbury zone and wall state:")
    medians = model.groupby(["kingsbury_zone", fragility.STATE_COLUMN], dropna=False)[
        "theta"
    ].median()
    for (zone, state), value in medians.items():
        label = susceptibility.ZONE_LABELS.get(zone, "no rating")
        print(f"  zone {zone!s:>4} {label:<10} {state:<9}: {value:.3f}")
    for column, unit in (("amp_factor", ""), ("pgv_pga_ratio_m_s_per_g", "m/s per g")):
        values = model[column].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if values.size == 0:
            print(f"{column}: nothing finite")
            continue
        print(f"{column}: {values.min():.3f} to {values.max():.3f} {unit}".rstrip())


def describe_flatland_walls(polygons, walls):
    """Print how many flat-land walls the join leaves out, and how many sit on an edge.

    A flat-land wall is drawn by vul shaking rw step 9 alone, so a polygon whose
    edge line drew one stays ``no_wall`` (``fragility.sloping_walls``).
    """
    flat = walls[fragility.IS_FLATLAND_COLUMN].fillna(value=False).astype(bool)
    edge_lines = {
        line
        for cell in polygons[geometry.WALL_LINE_IDS_COLUMN]
        for line in geometry.edge_line_ids(cell)
    }
    on_edge = flat & walls[geometry.WALL_LINE_ID_COLUMN].isin(edge_lines)
    print(
        f"  {int(flat.sum()):,} flat-land walls skipped (drawn by vul shaking rw "
        f"step 9), {int(on_edge.sum()):,} of them on a polygon edge (step 7 "
        "records sloping-land lines only, so this should be zero)"
    )


def check_walls_name_polygon_lines(polygons, walls):
    """Refuse a world whose drawn walls name none of the polygons' edge lines.

    The polygons name step 7's wall lines; exposure rw step 6 now draws wall
    units from landslide step 12, whose ids are not wall line ids. Joined
    anyway, no polygon would find its wall and every polygon would be
    ``no_wall`` without an error, so the run stops instead.

    Raises:
        ValueError: If there are drawn walls and edge lines and no id is in both.
    """
    edge_lines = {
        line
        for cell in polygons[geometry.WALL_LINE_IDS_COLUMN]
        for line in geometry.edge_line_ids(cell)
    }
    drawn = set(walls[geometry.WALL_LINE_ID_COLUMN].dropna().astype(str))
    if edge_lines and drawn and not edge_lines & drawn:
        msg = (
            "no drawn wall names a polygon edge line (drawn ids such as "
            f"{min(drawn)!r}, edge lines such as {min(edge_lines)!r}): exposure "
            "rw step 6 draws landslide step 12's wall units, which steps 7 and 8 "
            "do not read yet, so every polygon would be no_wall"
        )
        raise ValueError(msg)


def build_model(polygons, walls, *, wall_table, rate_setting, pgv, pga, extent):
    """Assemble one world's model from the polygons and that world's walls.

    Args:
        polygons: The step 7 polygons.
        walls: Every wall the world drew, ``rw_id`` null where uninsured.
        wall_table: The packaged wall fragility table.
        rate_setting: ``low``, ``medium`` or ``high``.
        pgv: Shaking step 3's PGV grid.
        pga: The unscaled TS1170.5 PGA on the same grid.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The model frame of contract section 3.8 less ``world_id``.

    Raises:
        ValueError: If no drawn wall names a polygon edge line
            (:func:`check_walls_name_polygon_lines`).
    """
    check_walls_name_polygon_lines(polygons, walls)
    describe_flatland_walls(polygons, walls)
    points = representative_points(polygons)
    site_class = sample_site_class(points, extent=extent)
    ratio = fragility.pgv_pga_ratio_m_s_per_g(pgv, pga, points)
    describe_demand(ratio, site_class)
    return fragility.assign_fragility(
        polygons,
        walls,
        wall_table,
        rate_setting=rate_setting,
        site_class=site_class,
        pgv_pga_ratio=ratio,
    )


def main(*, extent, world_ids, urban_rate, return_period_yr):
    """Write a fragility per polygon for each exposure world.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        world_ids: Which exposure worlds to build a model file for.
        urban_rate: The rate setting, one of ``URBAN_RATE_FACTORS``' keys.
        return_period_yr: The return period of the TS1170.5 demand the
            PGV/PGA ratio is read at.
    """
    factor = fragility.rate_factor(urban_rate)
    print(RULE)
    print(f"Rate setting {urban_rate!r}, factor {factor:.4f}")

    polygons_path = urban_slope_polygons_path(extent=extent)
    print(f"Reading the polygons from {polygons_path} ...")
    polygons = gpd.read_parquet(polygons_path)
    print(f"  {len(polygons):,} polygons")
    wall_table = fragility.load_retaining_wall_fragility()

    # The ratio is realisation-free: step 3's PGV over the unscaled PGA, both
    # on the site class grid, so it is built once for every world.
    site_class = read_site_class(extent=extent)
    print(f"Reading the TS1170.5 PGA grids at {return_period_yr} years ...")
    pga = demand_on_site_class_grid(
        get_ts1170_pga, site_class, return_period_yr=return_period_yr
    )
    pgv = read_grid(
        output_path("pgv", return_period_yr=return_period_yr, extent=extent)
    )

    for world_id in world_ids:
        print(RULE)
        walls_path = drawn_walls_path(world_id, extent=extent)
        print(f"World {world_id}: reading the drawn walls from {walls_path} ...")
        walls = gpd.read_parquet(walls_path)
        insured = int(walls[RW_ID_COLUMN].notna().sum())
        print(f"  {len(walls):,} walls, {insured:,} of them insured (with an rw_id)")

        model = build_model(
            polygons,
            walls,
            wall_table=wall_table,
            rate_setting=urban_rate,
            pgv=pgv,
            pga=pga,
            extent=extent,
        )
        model = add_world_id(model, world_id)
        describe_model(model, rate_setting=urban_rate)

        out_path = urban_slope_model_path(world_id, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        model.to_parquet(out_path)
        print(f"Wrote {len(model):,} polygons to {out_path}")

    print(RULE)
    print(
        "The localised medians and the rate factors are placeholders until the "
        "anchoring sets them (hazard/landslide/validations/urban/); the wall "
        "curves are read out of Koutsoupaki et al. (2023) at the project lead's "
        "review."
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        urban_rate=config.URBAN_RATE,
        return_period_yr=config.RETURN_PERIOD_YR,
    )
