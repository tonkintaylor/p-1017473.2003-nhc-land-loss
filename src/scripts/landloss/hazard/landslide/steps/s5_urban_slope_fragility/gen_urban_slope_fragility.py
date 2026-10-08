"""Give every urban failure polygon its fragility for one exposure world.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_urban_slope_fragility/gen_urban_slope_fragility.py

Run ground step 4 (the faces), exposure retaining wall step 6 (the wall units
and the walls each world drew), landslide step 4 (each world's zones of that
draw), ground step 1 (the 100 m topographic position)
and shaking steps 2 and 3 (the site class grid and the PGV grid) first, over
the same extent.

The run settings -- the extent, which worlds, the
rate setting and the return period of the demand -- come from ``config.py``
beside this script rather than from the command line.

The polygons are landslide step 4's zones of each world's wall draw
(``urban-slope-zones-wNNN``), not the polygons of a whole-scenario bound:
exposure rw step 6 draws which wall units are walled once per world, landslide
step 4 builds that world's zones with those walls, and rw step 6 writes the
same draw as its drawn walls, so a wall that
holds the slope in the hazard is the wall that is exposed. Each polygon's wall
is the wall unit its element's pif belongs to, named ``wall_line_id`` on both
sides (``landloss.hazard.landslide.urban.face_polygons``). Landslide step 4's two
whole-scenario zone files, every siz walled and none, are bounds for the
figures and are not read here.

For each world ``w`` the step joins each polygon to the drawn wall of its
unit, insured or not: exposure rw step 6's drawn walls are every wall the world drew
before the claim and coverage filters, because those decide what is insured,
not whether a wall holds the slope (decision 36 of the build contract). An
uninsured wall gives its polygon the wall state and curve with ``rw_id`` null.
It first checks that the zones and the drawn walls are one draw
(``face_polygons.check_zones_match_walls``): a polygon is walled in the zones
exactly where its unit is a drawn wall. It writes one fragility row per
polygon (``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``
section 4; the build contract, sections 3.8, 6 and 7.7):

1. **The wall state.** A polygon whose unit drew a sloping-land wall in world
   ``w``, insured or not, is in the ``fill_wall`` or ``cut_wall`` state of the
   unit's position (fill where the unit is on fill); every other polygon is
   ``no_wall``. A flat-land wall is never taken: vul shaking rw step 9 draws
   it (when insured), and nowhere else does. The geometry and depths are the
   zones landslide step 4 built for the world.
2. **The median.** A polygon with a wall takes the wall type curve for the
   wall's type and height class, under 2 m or 2 m and over
   (``retaining-wall-type-fragility.csv``,
   [koutsoupaki_2023]), its PGA median scaled by the wall's own fill or cut
   position, converted from PGA to PGV by the study's own PGV/PGA ratio at
   the polygon's representative point: shaking step 3's PGV grid over
   the unscaled TS1170.5 PGA grid on the same cells. A polygon without a wall
   takes the localised median from its continuous Kingsbury rating, scored
   from its element and the ground map
   (``landloss.hazard.landslide.urban.fragility.localised_theta_base_m_s``).
3. **The adjustments.** The median is divided by the topographic amplification
   factor (the placeholder on ground step 1's 100 m topographic position at the
   representative point and the element's slope) and multiplied by the rate
   factor of the run's setting (``URBAN_RATE_FACTORS``), both recorded on the
   row.

A fragility is a probability of failure at a level of shaking: landslide step 6 samples
the earthquake's PGV at the representative point and draws against the row's
lognormal. Nothing is drawn here.

Writes one GeoParquet per world, sorted by ``slope_id`` with a fresh index,
under ``temp/hazard/landslide/``, with the extent's ``extent_suffix``
(``-pilot`` for the small Wellington pilot). The ``slope_id`` is minted per
world, by location, because each world's zones are built anew.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray

from landloss.common.utils.terrain import sample_at_points
from landloss.domain.loss_contract import RW_ID_COLUMN
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import (
    face_polygons,
    fragility,
    geometry,
    wall_type_fragility,
)
from landloss.hazard.shaking.site_class import demand_on_site_class_grid
from landloss.io.area_of_interest import extent_suffix, get_area_of_interest
from landloss.io.ts1170 import get_ts1170_pga
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    drawn_walls_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    wall_units_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.gen_wall_zones import (
    wall_elements_path,
    world_scenario,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import config
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
    """Print how many flat-land walls the join leaves out, and how many name a polygon.

    A flat-land wall is drawn by vul shaking rw step 9 alone, so a polygon whose
    unit drew one stays ``no_wall`` (``fragility.sloping_walls``).
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
        f"step 9), {int(on_edge.sum()):,} of them a polygon's unit (the wall "
        "units are faces of sloping ground, so this should be zero)"
    )


def read_step12_inputs(*, extent):
    """Read the world-free inputs of the face polygons: elements, units, ground map.

    Returns:
        ``(elements, units, ground_map)``: landslide step 4's elements (indexed
        by element label), exposure rw step 6's wall units (indexed by
        ``wall_unit_id``) and the ground step 2 ground map.
    """
    # The elements with the GNS-only units' lines added, which the zones
    # were built on (landslide step 4's gen_wall_zones.py).
    elements = pd.read_parquet(
        wall_elements_path(extent=extent),
        columns=[*face_polygons.ELEMENT_COLUMNS, "wall_unit_id"],
    )
    units = gpd.read_parquet(wall_units_path(extent=extent))
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    return elements, units, ground_map


def read_polygons(world_id, *, extent, elements, units, ground_map):
    """One world's polygons: landslide step 4's zones of its wall draw, one row each.

    Reads ``urban-slope-zones-wNNN`` (``gen_wall_zones.py``),
    turns it into one row per polygon
    (:func:`landloss.hazard.landslide.urban.face_polygons.face_polygons`) and
    adds the amplification on ground step 1's 100 m topographic position at each
    representative point.

    Raises:
        FileNotFoundError: If landslide step 4 has not written the world's zones.
    """
    path = zones_path(world_scenario(world_id), extent=extent)
    if not path.exists():
        msg = (
            f"{path} not found: add world {world_id} to exposure rw step 6's "
            "WORLD_IDS, run exposure rw step 6 (gen_wall_units.py), "
            "then landslide step 4 (gen_wall_zones.py)"
        )
        raise FileNotFoundError(msg)
    print(f"World {world_id}: reading the zones from {path} ...")
    zones = gpd.read_parquet(path)
    aoi = get_area_of_interest(extent)
    bbox = None if aoi is None else aoi.bbox(zones.crs)
    polygons = face_polygons.face_polygons(
        zones, elements, units, ground_map, bbox=bbox
    )
    n_zone_polygons = int(zones["polygon"].nunique())
    print(
        f"  {n_zone_polygons - len(polygons):,} polygons outside the extent left "
        "out (landslide step 4's DEM margin, where the shaking grids give no demand)"
    )
    tpi = sample_at_points(
        terrain_path("topographic-position-100m", extent=extent),
        representative_points(polygons),
    )
    polygons = face_polygons.with_amplification(polygons, tpi.to_numpy(dtype=float))
    walled = polygons[face_polygons.IS_WALLED_COLUMN]
    print(
        f"  {len(polygons):,} polygons, {int(walled.sum()):,} walled, "
        f"{int(polygons[geometry.WALL_LINE_ID_COLUMN].notna().sum()):,} on a wall unit"
    )
    return polygons


def build_model(polygons, walls, *, wall_table, rate_setting, pgv, pga, extent):
    """Assemble one world's model from the polygons and that world's walls.

    Args:
        polygons: One world's polygons, from :func:`read_polygons`.
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
        ValueError: If the zones and the drawn walls are not one wall draw
            (``face_polygons.check_zones_match_walls``).
    """
    face_polygons.check_zones_match_walls(polygons, walls)
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

    print("Reading landslide step 4's elements and exposure rw step 6's wall units ...")
    elements, units, ground_map = read_step12_inputs(extent=extent)
    print(f"  {len(elements):,} elements, {len(units):,} wall units")
    wall_table = wall_type_fragility.load_wall_type_fragility()

    # The ratio is realisation-free: shaking step 3's PGV over the unscaled PGA, both
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
        polygons = read_polygons(
            world_id,
            extent=extent,
            elements=elements,
            units=units,
            ground_map=ground_map,
        )

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
