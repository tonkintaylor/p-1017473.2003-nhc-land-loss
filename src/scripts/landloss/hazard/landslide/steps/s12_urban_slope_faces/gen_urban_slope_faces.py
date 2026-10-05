"""Step 12: urban slope faces, from pips to evacuated zones, over an extent.

Finds the potential instability points (pips), groups them into faces (pifs),
tests every face for a seed instability zone (siz), grows the sizs into
elements and builds the evacuated, imminent and inundated zones twice: once
with every siz walled and once with none. It also reads the evidence for a
retaining wall onto each pif (:mod:`landloss.hazard.landslide.wall_candidates`).
Reads the DEM from step 3 and the ground map from step 4.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/gen_urban_slope_faces.py

Settings are in ``config.py``.
"""

import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray
from rasterio import features

from landloss.hazard.landslide.instability_zones import (
    MAX_PIF_SPAN_M,
    find_instability_zones,
    gen_siz_table,
    with_walls,
    write_siz_table,
)
from landloss.hazard.landslide.slope_elements import rasterise_ground_map
from landloss.hazard.landslide.slope_polygons import (
    ZONES,
    build_slope_polygons,
    polygon_geometries,
)
from landloss.hazard.landslide.wall_candidates import (
    gen_gns_only_candidates,
    property_of_pifs,
    wall_candidate_evidence,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_nz_building_outlines,
    get_nz_coastline_polygons,
    get_nz_property_boundaries,
    get_slide_genesis,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.paths import TEMP_DIR

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
CRS = 2193
SCENARIOS = {"walled": True, "bare": False}

# GNS morphology types (landloss.exposure.rw.lines) and SLIDE genesis types.
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"
CUT_FILL_LINE_TYPE = "Cut/fill line"
CUT_SLOPE_TYPE = "Cut slope"
FILL_BODY_TYPE = "Fill body"
FILL_MODIFICATION = "fill"


def siz_table_path(*, extent):
    """Where the siz table, with its wall evidence, is written."""
    return WORK_DIR / f"urban-slope-sizs{extent_suffix(extent)}.parquet"


def elements_path(*, extent):
    """Where the grown elements are written."""
    return WORK_DIR / f"urban-slope-elements{extent_suffix(extent)}.parquet"


def gns_only_path(*, extent):
    """Where the GNS-only wall candidates (lines) are written."""
    return WORK_DIR / f"urban-slope-gns-wall-candidates{extent_suffix(extent)}.parquet"


def zones_path(scenario, *, extent):
    """Where the evacuated, imminent and inundated zones of a scenario are written."""
    return WORK_DIR / f"urban-slope-zones-{scenario}{extent_suffix(extent)}.parquet"


def get_inputs(*, extent, use_cached_layers):
    """The DEM with the sea masked, the ground map and the ground groups.

    Returns:
        ``(dem, transform, bbox, ground_map, group, position)``. Fill is read
        as soil in ``group``, as the pip test has no fill class.
    """
    dem_da = rioxarray.open_rasterio(dem_path(1, extent=extent), masked=True).squeeze(
        "band", drop=True
    )
    dem = dem_da.to_numpy().astype("float64")
    transform = dem_da.rio.transform()
    bbox = dem_da.rio.bounds()
    land = get_nz_coastline_polygons(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    on_land = features.rasterize(
        [(geometry, 1) for geometry in land.geometry],
        out_shape=dem.shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    group, position = rasterise_ground_map(
        ground_map, transform, dem.shape, fill_as_soil=True
    )
    return np.where(on_land, dem, np.nan), transform, bbox, ground_map, group, position


def fill_by_element(elements, ground_map):
    """Whether each element is on fill, and the fill's thickness where it is."""
    rows = elements["majority_ground_row"].to_numpy()
    on_map = rows >= 0
    safe = np.maximum(rows, 0)
    is_fill = on_map & (
        ground_map["modification"].to_numpy()[safe] == FILL_MODIFICATION
    )
    thickness = np.where(
        is_fill, ground_map["fill_thickness_m"].to_numpy()[safe], np.nan
    )
    return (
        pd.Series(is_fill, index=elements.index),
        pd.Series(thickness, index=elements.index),
    )


def element_polygons(found, transform):
    """The grown elements as polygons, with their attributes."""
    shapes = features.shapes(
        found.labels.astype("int32"), mask=found.labels > 0, transform=transform
    )
    frame = gpd.GeoDataFrame.from_features(
        [
            {"type": "Feature", "geometry": g, "properties": {"label": int(v)}}
            for g, v in shapes
        ],
        crs=CRS,
    )
    frame = frame.dissolve(by="label")
    return frame.join(found.elements, how="left")


def zone_polygons(result, *, scenario):
    """Every zone of every polygon of a scenario, one row per polygon and zone."""
    parts = []
    for zone in ZONES:
        frame = polygon_geometries(result, zone=zone, crs=CRS)
        frame["zone"] = zone
        parts.append(frame)
    zones = pd.concat(parts, ignore_index=True)
    zones = zones.merge(result.polygons.reset_index(), on="polygon", how="left")
    zones["scenario"] = scenario
    return gpd.GeoDataFrame(zones, geometry="geometry", crs=CRS)


def describe(zones, elapsed, scenario_results):
    """Print the counts and timings of the run."""
    sizs = zones.sizs
    print(f"{int(zones.pips.mask.sum()):,} pips, {len(sizs):,} pifs, ", end="")
    print(f"{int(sizs['is_siz'].sum()):,} sizs, {len(zones.found.elements):,} elements")
    print(sizs.groupby("ground_group")["is_siz"].agg(["size", "sum"]).to_string())
    print(f"Pips to grown elements: {elapsed:.1f} s")
    for scenario, (result, seconds) in scenario_results.items():
        polygons = result.polygons
        print(
            f"{scenario}: {len(polygons):,} polygons in {seconds:.1f} s, "
            f"{polygons['area_m2'].sum():,.0f} m2 evacuated"
        )


def describe_properties(table):
    """Print how cleanly the pifs sit on properties."""
    has_property = table["n_properties"] > 0
    on_road = table["property_is_road"].fillna(value=False).astype(bool)
    print(
        f"{has_property.mean():.1%} of pifs in a property, "
        f"{on_road.sum():,} on road parcels, "
        f"{(table['n_properties'] > 1).sum():,} straddling two or more properties"
    )


def main(
    *,
    extent,
    use_cached_layers,
    gns_wall_match_m,
    search_m,
    gns_only_min_length_m,
):
    """Run the pipeline over the extent and write the siz table, elements and zones.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ and GNS layers.
        gns_wall_match_m: A mapped wall within this many metres of a pif is on it.
        search_m: Walls, lines and buildings further than this are not recorded.
        gns_only_min_length_m: Mapped wall with no pip near it becomes a candidate
            of its own if at least this long, in metres.
    """
    dem, transform, bbox, ground_map, group, position = get_inputs(
        extent=extent, use_cached_layers=use_cached_layers
    )
    start = time.perf_counter()
    zones = find_instability_zones(
        dem, group, transform, categories={"ground_row": position}
    )
    elapsed = time.perf_counter() - start
    elements = zones.found.elements
    is_fill, thickness = fill_by_element(elements, ground_map)

    scenario_results = {}
    for scenario, walled in SCENARIOS.items():
        start = time.perf_counter()
        found = with_walls(zones.found, walled)
        result = build_slope_polygons(
            found, dem, transform, is_fill=is_fill, fill_thickness_m=thickness
        )
        scenario_results[scenario] = (result, time.perf_counter() - start)
        output = zone_polygons(result, scenario=scenario)
        output.to_parquet(zones_path(scenario, extent=extent))
    describe(zones, elapsed, scenario_results)

    morphology = get_gns_slide_morphology(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    genesis = get_slide_genesis(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    buildings = get_nz_building_outlines(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    table = gen_siz_table(zones, transform, crs=CRS)
    properties = get_nz_property_boundaries(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    mapped_walls = morphology[morphology["Type"] == MAPPED_WALL_TYPE]
    evidence = wall_candidate_evidence(
        table,
        walls=mapped_walls,
        cut_fill_lines=morphology[morphology["Type"] == CUT_FILL_LINE_TYPE],
        cut_slopes=genesis[genesis["Type"] == CUT_SLOPE_TYPE],
        fill_bodies=genesis[genesis["Type"] == FILL_BODY_TYPE],
        ground_map=ground_map,
        buildings=buildings,
        wall_match_m=gns_wall_match_m,
        search_m=search_m,
    )
    table = table.join(evidence).join(property_of_pifs(table, properties))
    write_siz_table(table, siz_table_path(extent=extent))
    print(table["candidate_class"].value_counts().to_string())
    describe_properties(table)

    gns_only = gen_gns_only_candidates(
        table,
        walls=mapped_walls,
        properties=properties,
        ground_map=ground_map,
        buildings=buildings,
        wall_match_m=gns_wall_match_m,
        min_length_m=gns_only_min_length_m,
        max_length_m=MAX_PIF_SPAN_M,
        search_m=search_m,
    )
    gns_only.to_parquet(gns_only_path(extent=extent))
    on_property = int(gns_only["property_id"].notna().sum())
    print(
        f"{len(gns_only):,} GNS-only candidates, {gns_only['length_m'].sum():,.0f} m "
        f"of {mapped_walls.length.sum():,.0f} m mapped; {on_property:,} on a property"
    )
    element_polygons(zones.found, transform).to_parquet(elements_path(extent=extent))
    print(f"Written to {WORK_DIR}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        gns_wall_match_m=config.GNS_WALL_MATCH_M,
        search_m=config.SEARCH_M,
        gns_only_min_length_m=config.GNS_ONLY_MIN_LENGTH_M,
    )
