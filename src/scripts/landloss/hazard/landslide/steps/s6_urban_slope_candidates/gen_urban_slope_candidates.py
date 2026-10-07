"""Delineate the candidate urban failure polygons at each scale.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s6_urban_slope_candidates/gen_urban_slope_candidates.py

Run landslide step 3 (``s3_multiscale_slope/gen_multiscale_slope.py`` and
``gen_terrain_derivatives.py``) and step 4 (``s4_ground_map/gen_ground_map.py``)
first, over the same extent: this reads the slope, aspect and DEM rasters, the
terrain derivatives and the ground map they write. Needs ``LINZ_API_KEY`` in
``.env`` for the building outlines, roads and property boundaries, and a mapped
T: drive for the NLM flatland.

A candidate is a piece of sloping ground, off the NLM flatland and within
``config.BUILDING_DISTANCE_M`` of a building outline, bounded by its crest and
toe breaks in slope: the object the urban slope failure model draws against
once step 7 has reconciled it to the wall lines. The candidates are found from
the terrain alone, at each scale in ``config.SCALES_M``, so that a 1 m face is
one polygon inside the 10 m bank that contains it. Nesting across scales is
kept; nothing here chooses between scales.

1. The urban domain is the building outlines buffered, less the flatland
   (:func:`landloss.hazard.landslide.urban.delineation.urban_domain`).
2. At each scale the slope is banded and the aspect binned into octants, cells
   of one band and one octant that share an edge form a patch, patches under
   ``config.MIN_PATCH_CELLS`` are merged into the neighbour sharing the most
   edges, and patches longer than ``config.MAX_PATCH_LENGTH_M`` along the
   contour are cut into equal pieces
   (:func:`landloss.hazard.landslide.urban.delineation.delineate_candidates`).
   Every band produces candidates, the gentlest included.
3. The terrain derivatives, the slope at every scale and the 1 m relief are
   read onto each candidate as zonal statistics; the distances to the nearest
   building, road centreline and property boundary and the position against
   the nearest building are measured; the ground map's attributes are copied
   from the polygon under the representative point.
4. ``candidate_id`` is minted by scale descending and then location.

Writes ``urban-slope-candidates{extent_suffix}.geoparquet`` under
``temp/hazard/landslide/``, one row per candidate.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray
import shapely

from landloss.common.utils import terrain, tiles
from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.hazard.landslide.urban.delineation import (
    SLOPE_BAND_LABELS,
    delineate_candidates,
    urban_domain,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.nlm import get_nlm_flatland
from landloss.io.readers import (
    get_nz_address_roads,
    get_nz_building_outlines,
    get_nz_property_boundaries,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    aspect_path,
    dem_path,
    resolve_extent,
    slope_path,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "urban-slope-candidates"

# The DEM the relief and the building position are read from, in metres.
FINE_RESOLUTION_M = 1

# The terrain derivative layers step 3 writes, keyed as its `terrain_path`
# takes them, with the column each lands in and the statistic read over the
# patch. The face height is the largest step inside the patch; the rest are
# means.
TERRAIN_ATTRIBUTES = {
    "face-height-5m": ("face_height_5m", "max"),
    "face-height-10m": ("face_height_10m", "max"),
    "cut-fill-residual-30m": ("cut_fill_residual_30m", "mean"),
    "cut-fill-residual-100m": ("cut_fill_residual_100m", "mean"),
    "profile-curvature": ("profile_curvature", "mean"),
    "topographic-position-20m": ("topographic_position_20m", "mean"),
    "topographic-position-100m": ("topographic_position_100m", "mean"),
    "vegetation-height": ("vegetation_height_m", "mean"),
}

# The ground map columns copied onto a candidate from the polygon under its
# representative point.
GROUND_COLUMNS = (
    "ground_id",
    "material",
    "modification",
    "prior_failure",
    "gw_depth_class",
    "gw_depth_m",
    "fill_thickness_m",
    "geology_value",
)

# A candidate whose centroid is within this many metres of the nearest
# building's centroid elevation is beside it rather than above or below.
BESIDE_TOLERANCE_M = 1.0
ABOVE, BELOW, BESIDE = "above", "below", "beside"

# The output columns, in the order of contract section 3.4.
OUTPUT_COLUMNS = (
    "candidate_id",
    "scale_m",
    "slope_band",
    "aspect_octant",
    "slope_degrees",
    "aspect_degrees",
    "slope_1m",
    "slope_3m",
    "slope_10m",
    "slope_30m",
    "face_height_5m",
    "face_height_10m",
    "cut_fill_residual_30m",
    "cut_fill_residual_100m",
    "profile_curvature",
    "topographic_position_20m",
    "topographic_position_100m",
    "vegetation_height_m",
    "building_distance_m",
    "building_position",
    "road_distance_m",
    "boundary_distance_m",
    *GROUND_COLUMNS,
    "relief_m",
    "area_m2",
    "contour_length_m",
    "geometry",
)

RULE = "-" * 72


def urban_slope_candidates_path(*, extent):
    """Return the file a run writes the candidates to.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The output path, under ``temp/hazard/landslide/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def read_raster(path):
    """Read one of step 3's rasters, with nodata masked to NaN."""
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def read_zonal(path, polygons, *, statistic):
    """Read a raster statistic over each polygon, falling back to a point read.

    A patch at a fine scale can be smaller than a cell of a coarse raster, so
    that no cell centre falls inside it and the zonal statistic is NaN. Those
    polygons take the raster's value at their representative point instead,
    which is the cell they sit in.

    Args:
        path: The raster to read.
        polygons: The polygons to read over, in the raster's system.
        statistic: ``mean``, ``max`` or ``min``, as `terrain.zonal_statistic`
            takes it.

    Returns:
        One value per polygon, on the polygons' index.
    """
    values = terrain.zonal_statistic(path, polygons, statistic=statistic)
    missing = values.isna()
    if missing.any():
        points = polygons[missing].representative_point()
        values[missing] = terrain.sample_at_points(path, points)
    return values


def delineate_at_scales(
    domain,
    *,
    scales_m,
    extent,
    min_patch_cells,
    max_patch_length_m,
    max_untiled_cells,
    tile_core_m,
    tile_margin_m,
):
    """Delineate the candidates at each scale and stack them.

    A scale whose grid holds more than ``max_untiled_cells`` is delineated
    tile by tile (:func:`delineate_tiled`); the rest are delineated whole.

    Args:
        domain: The urban domain, from `urban_domain`.
        scales_m: The cell sizes to delineate at, in metres.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        min_patch_cells: The smallest patch kept unmerged, in cells.
        max_patch_length_m: The longest contour length kept uncut, in metres.
        max_untiled_cells: The largest grid delineated whole, in cells.
        tile_core_m: The side of a tile's core, in metres.
        tile_margin_m: The width read around each core, in metres.

    Returns:
        The candidates of every scale in one frame, with the columns
        `delineate_candidates` returns, on a fresh index.
    """
    frames = []
    for scale_m in scales_m:
        print(f"\nDelineating at {scale_m} m ...", flush=True)
        slope_file = slope_path(scale_m, extent=extent)
        aspect_file = aspect_path(scale_m, extent=extent)
        settings = {
            "scale_m": scale_m,
            "min_patch_cells": min_patch_cells,
            "max_length_m": max_patch_length_m,
        }
        if tiles.raster_cells(slope_file) > max_untiled_cells:
            candidates = delineate_tiled(
                slope_file,
                aspect_file,
                domain,
                core_m=tile_core_m,
                margin_m=tile_margin_m,
                **settings,
            )
        else:
            candidates = delineate_candidates(
                read_raster(slope_file), read_raster(aspect_file), domain, **settings
            )
        print(f"  {len(candidates):,} candidates")
        frames.append(candidates)
    return pd.concat(frames, ignore_index=True)


def delineate_tiled(slope_file, aspect_file, domain, *, core_m, margin_m, **settings):
    """Delineate one scale tile by tile, keeping each candidate once.

    Each tile reads its core and a margin of ``margin_m`` and is delineated
    against the whole domain; a candidate is kept by the tile whose core holds
    its representative point (`landloss.common.utils.tiles.owned_by`). Every
    step of the delineation reads only the cells near a patch, so a candidate
    smaller than the margin comes out as it would from the whole grid.

    Args:
        slope_file: The slope raster at this scale.
        aspect_file: The aspect raster on the same grid.
        domain: The urban domain.
        core_m: The side of a tile's core, in metres.
        margin_m: The width read around each core, in metres.
        **settings: Passed to `delineate_candidates`.

    Returns:
        The candidates of the scale, on a fresh index.
    """
    grid = tiles.tile_grid(slope_file, core_m=core_m, margin_m=margin_m)
    print(
        f"  {len(grid)} tiles of {core_m:,.0f} m with a {margin_m:,.0f} m margin",
        flush=True,
    )
    shapely.prepare(domain)
    frames = []
    for tile in grid:
        core = shapely.box(*tile.core_bounds)
        if not domain.intersects(core):
            continue
        made = delineate_candidates(
            tiles.read_window(slope_file, tile.outer),
            tiles.read_window(aspect_file, tile.outer),
            domain,
            **settings,
        )
        frames.append(made.loc[tiles.owned_by(made, tile.core_bounds)])
    return pd.concat(frames, ignore_index=True)


def read_terrain_attributes(candidates, *, scales_m, extent):
    """Read the slope at every scale, the derivatives and the relief onto each row.

    Args:
        candidates: The candidates, in the rasters' system.
        scales_m: The scales whose slope rasters are read, in metres.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The candidates with the terrain columns added.
    """
    candidates = candidates.copy()
    polygons = candidates.geometry
    for scale_m in scales_m:
        candidates[f"slope_{scale_m}m"] = read_zonal(
            slope_path(scale_m, extent=extent), polygons, statistic="mean"
        )
    for layer, (column, statistic) in TERRAIN_ATTRIBUTES.items():
        candidates[column] = read_zonal(
            terrain_path(layer, extent=extent), polygons, statistic=statistic
        )
    dem = dem_path(FINE_RESOLUTION_M, extent=extent)
    highest = read_zonal(dem, polygons, statistic="max")
    lowest = read_zonal(dem, polygons, statistic="min")
    candidates["relief_m"] = highest - lowest
    return candidates


def nearest(candidates, targets):
    """Find the nearest target to each candidate.

    Args:
        candidates: The candidates.
        targets: The geometries to measure to, in the same system.

    Returns:
        A frame on the candidates' index with ``distance`` in metres and
        ``target``, the target's index label; NaN where there are no targets.
    """
    if targets.empty:
        return pd.DataFrame(
            {"distance": np.nan, "target": None}, index=candidates.index
        )
    joined = gpd.sjoin_nearest(
        candidates[["geometry"]],
        gpd.GeoDataFrame(geometry=targets.geometry, crs=targets.crs),
        how="left",
        distance_col="distance",
    )
    # Several targets at one distance give several rows; the first is enough.
    joined = joined[~joined.index.duplicated()]
    return pd.DataFrame(
        {"distance": joined["distance"], "target": joined["index_right"]},
        index=candidates.index,
    )


def building_position(candidates, buildings, nearest_building, *, extent):
    """Place each candidate above, below or beside its nearest building.

    The candidate centroid's elevation against the nearest outline's centroid
    elevation, both read off the 1 m DEM; ``beside`` within
    ``BESIDE_TOLERANCE_M`` either way.

    Args:
        candidates: The candidates.
        buildings: The building outlines.
        nearest_building: The index label of each candidate's nearest outline.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        ``above``, ``below`` or ``beside`` per candidate, on the candidates'
        index; None where either elevation is unknown.
    """
    dem = dem_path(FINE_RESOLUTION_M, extent=extent)
    candidate_elevation = terrain.sample_at_points(dem, candidates.geometry.centroid)
    building_elevation = terrain.sample_at_points(dem, buildings.geometry.centroid)
    matched = nearest_building.map(building_elevation)
    difference = candidate_elevation - matched.astype(float)
    position = pd.Series(
        np.select(
            [
                difference > BESIDE_TOLERANCE_M,
                difference < -BESIDE_TOLERANCE_M,
                difference.notna(),
            ],
            [ABOVE, BELOW, BESIDE],
            default=None,
        ),
        index=candidates.index,
        dtype=object,
    )
    return position.where(position.notna(), None)


def read_ground_attributes(candidates, ground_map):
    """Copy the ground map's attributes from the polygon under each row's point.

    Args:
        candidates: The candidates.
        ground_map: The step 4 ground map, in the same system.

    Returns:
        The candidates with `GROUND_COLUMNS` added; null where the
        representative point falls in no ground map polygon.
    """
    points = gpd.GeoDataFrame(
        geometry=candidates.geometry.representative_point(), crs=candidates.crs
    )
    ground = ground_map[[*GROUND_COLUMNS, "geometry"]]
    joined = gpd.sjoin(points, ground, how="left", predicate="within")
    joined = joined[~joined.index.duplicated()]
    candidates = candidates.copy()
    for column in GROUND_COLUMNS:
        candidates[column] = joined[column].reindex(candidates.index)
    return candidates


def nesting_depth(candidates):
    """Count, per candidate, the coarser scales with a candidate over it.

    A candidate's representative point is looked up in every candidate at a
    coarser scale; the depth is how many distinct coarser scales hold it.

    Args:
        candidates: The candidates of every scale.

    Returns:
        The depth per candidate, on the candidates' index, 0 at the coarsest
        scale.
    """
    points = gpd.GeoDataFrame(
        {"scale_m": candidates["scale_m"].to_numpy()},
        geometry=candidates.geometry.representative_point(),
        crs=candidates.crs,
    )
    joined = gpd.sjoin(
        points, candidates[["scale_m", "geometry"]], how="inner", predicate="within"
    )
    coarser = joined[joined["scale_m_right"] > joined["scale_m_left"]]
    depth = coarser.groupby(level=0)["scale_m_right"].nunique()
    return depth.reindex(candidates.index, fill_value=0).astype(np.int64)


def describe(candidates):
    """Print the counts and areas by scale and band, and the nesting depths."""
    print(RULE)
    print("Candidates by scale and slope band:")
    counts = (
        candidates.groupby(["scale_m", "slope_band"], observed=True)
        .agg(count=("candidate_id", "size"), area_ha=("area_m2", "sum"))
        .assign(area_ha=lambda frame: frame["area_ha"] / 10_000)
    )
    counts = counts.reindex(
        pd.MultiIndex.from_product(
            [sorted(candidates["scale_m"].unique()), SLOPE_BAND_LABELS],
            names=["scale_m", "slope_band"],
        ),
        fill_value=0,
    )
    print(counts.to_string(float_format=lambda value: f"{value:,.2f}"))
    print(RULE)
    print("Nesting depth (coarser scales with a candidate over the point):")
    depth = nesting_depth(candidates)
    for scale_m, group in depth.groupby(candidates["scale_m"]):
        distribution = ", ".join(
            f"{value}: {count:,}"
            for value, count in group.value_counts().sort_index().items()
        )
        print(f"  {scale_m:>3} m  {distribution}")


def main(
    *,
    extent,
    use_cached_layers,
    scales_m,
    building_distance_m,
    min_patch_cells,
    max_patch_length_m,
    max_untiled_cells,
    tile_core_m,
    tile_margin_m,
):
    """Delineate the candidates at every scale, attribute them and write them.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        use_cached_layers: Whether to reuse the cached LINZ layers.
        scales_m: The cell sizes to delineate at, in metres.
        building_distance_m: How far from a building the domain reaches.
        min_patch_cells: The smallest patch kept unmerged, in cells.
        max_patch_length_m: The longest contour length kept uncut, in metres.
        max_untiled_cells: The largest grid delineated whole, in cells.
        tile_core_m: The side of a tile's core, in metres.
        tile_margin_m: The width read around each core, in metres.
    """
    bbox, extent_name = resolve_extent(extent=extent)
    minx, miny, maxx, maxy = bbox
    print(f"Extent: {extent_name}")
    print(
        f"Scales {', '.join(f'{scale} m' for scale in scales_m)}; domain within "
        f"{building_distance_m:g} m of a building; minimum patch "
        f"{min_patch_cells} cells; contour length {max_patch_length_m:g} m"
    )

    print(
        "\nReading the building outlines, roads, property boundaries and flatland ..."
    )
    buildings = get_nz_building_outlines(bbox, use_cache=use_cached_layers)
    roads = get_nz_address_roads(bbox, use_cache=use_cached_layers)
    boundaries = get_nz_property_boundaries(bbox, use_cache=use_cached_layers)
    flatland = get_nlm_flatland().to_crs(constants.DEFAULT_CRS).cx[minx:maxx, miny:maxy]
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    print(
        f"  {len(buildings):,} buildings, {len(roads):,} roads, "
        f"{len(boundaries):,} properties, {len(flatland):,} flatland polygons, "
        f"{len(ground_map):,} ground map polygons"
    )

    domain = urban_domain(buildings, flatland, building_distance_m=building_distance_m)
    print(f"Urban domain: {domain.area / 10_000:,.1f} ha")

    candidates = delineate_at_scales(
        domain,
        scales_m=scales_m,
        extent=extent,
        min_patch_cells=min_patch_cells,
        max_patch_length_m=max_patch_length_m,
        max_untiled_cells=max_untiled_cells,
        tile_core_m=tile_core_m,
        tile_margin_m=tile_margin_m,
    )

    print("\nReading the terrain onto the candidates ...", flush=True)
    candidates = read_terrain_attributes(candidates, scales_m=scales_m, extent=extent)

    print("Measuring to the buildings, roads and boundaries ...", flush=True)
    to_building = nearest(candidates, buildings)
    candidates["building_distance_m"] = to_building["distance"]
    candidates["building_position"] = building_position(
        candidates, buildings, to_building["target"], extent=extent
    )
    candidates["road_distance_m"] = nearest(candidates, roads)["distance"]
    edges = gpd.GeoDataFrame(geometry=boundaries.geometry.boundary, crs=boundaries.crs)
    candidates["boundary_distance_m"] = nearest(candidates, edges)["distance"]

    print("Reading the ground map onto the candidates ...", flush=True)
    candidates = read_ground_attributes(candidates, ground_map)

    candidates = sort_by_point(candidates, by=("scale_m",), ascending=(False,))
    candidates["candidate_id"] = mint_ids(
        constants.CANDIDATE_ID_PREFIX, len(candidates)
    )
    candidates = candidates[list(OUTPUT_COLUMNS)]
    describe(candidates)

    out_path = urban_slope_candidates_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(candidates):,} candidates to {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        scales_m=config.SCALES_M,
        building_distance_m=config.BUILDING_DISTANCE_M,
        min_patch_cells=config.MIN_PATCH_CELLS,
        max_patch_length_m=config.MAX_PATCH_LENGTH_M,
        max_untiled_cells=config.MAX_UNTILED_CELLS,
        tile_core_m=config.TILE_CORE_M,
        tile_margin_m=config.TILE_MARGIN_M,
    )
