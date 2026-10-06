"""Step 12: the evacuated, imminent and inundated zones of the wall draws.

First every wall unit none of whose pifs grew an element (the GNS-only
units and the units of ``low_height`` pifs) gets an element along its line
(:func:`landloss.hazard.landslide.instability_zones.add_line_elements`), so
its wall has the minimum polygon too; the elements with these added are
written to ``urban-slope-wall-elements.parquet``, which landslide step 8
reads. A unit whose line found no free cell (all of them on other elements,
or off the DEM) gets its minimum polygon drawn as geometry from its line
instead, overlapping what it must
(:mod:`landloss.hazard.landslide.forced_polygons`, the lead, 2026-10-07): its
element is added to that file with the evacuated band as geometry, and its
zones are added to every zones file after the built ones. Then the zones are built twice as the bounds, every element walled
(``walled``) and none (``bare``), and once per exposure world from the wall
units ``gen_urban_slope_wall_units.py`` drew: an element is walled where its
pif is a member of a walled unit, or its line is a walled unit's
(:func:`landloss.hazard.landslide.wall_units.gen_element_walls`). The world
zones are what downstream reads.

Writes ``urban-slope-zones-walled.parquet``, ``urban-slope-zones-bare.parquet``
and ``urban-slope-zones-wNNN.parquet`` per world under
``temp/hazard/landslide/``. It reads the
elements the faces script found (``urban-slope-found.pkl``) rather than
finding them again, so the pip to element pipeline runs once per extent.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/gen_urban_slope_wall_zones.py

Run ``gen_urban_slope_faces.py`` and then ``gen_urban_slope_wall_units.py``
first. Settings are in ``config.py``.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.hazard.landslide.forced_polygons import (
    gen_forced_elements,
    gen_forced_zones,
)
from landloss.hazard.landslide.instability_zones import add_line_elements, with_walls
from landloss.hazard.landslide.slope_polygons import build_slope_polygons
from landloss.hazard.landslide.wall_units import gen_element_walls
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    SCENARIOS,
    element_polygons,
    fill_by_element,
    found_path,
    get_inputs,
    read_found,
    siz_table_path,
    wall_elements_path,
    zone_polygons,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_wall_units import (
    wall_draws_path,
    wall_units_path,
)


def units_without_element(units, elements):
    """The wall units none of whose pifs grew an element.

    Every wall gets a polygon (the lead, 2026-10-06): these units, the
    GNS-only units and the units of ``low_height`` pifs (a GNS mapped wall on a
    pif that is not a siz, which seeds no growth), get an element along their
    line (:func:`landloss.hazard.landslide.instability_zones.add_line_elements`).
    A low-height pif's unit takes a line element rather than growth from its pips:
    its pif failed the siz test, so growth at the siz threshold would keep
    only its own pips and measure a face the test called not steep enough,
    while the line takes the unit's own wall height and the same width floor
    as every other wall.
    """
    grown = set(elements["siz_id"].astype(np.int64))
    has_element = units["member_pif_ids"].map(
        lambda ids: any(int(i) in grown for i in ids)
    )
    return units[~has_element.to_numpy(dtype=bool)]


def ground_rows(geometries, ground_map):
    """The ground map row (by position) under each geometry's representative point.

    -1 where no ground map polygon holds it, as an element off the map.
    """
    points = gpd.GeoDataFrame(
        geometry=geometries.representative_point().to_numpy(), crs=geometries.crs
    )
    frame = ground_map[["geometry"]].reset_index(drop=True)
    joined = gpd.sjoin(points, frame, predicate="within", how="left")
    first = joined[~joined.index.duplicated()]["index_right"]
    return first.fillna(-1).astype(np.int64).to_numpy()


def with_forced(result, scenario, forced, walled, is_fill, thickness):
    """A scenario's built zones with the forced polygons' zones after them."""
    zones = zone_polygons(result, scenario=scenario)
    zones["forced"] = False
    zones["side_unknown"] = False
    first = int(result.polygons.index.max()) + 1 if len(result.polygons) else 1
    extra = gen_forced_zones(
        forced,
        walled,
        is_fill=is_fill,
        fill_thickness_m=thickness,
        first_polygon=first,
        scenario=scenario,
    )
    if extra.empty:
        return zones
    return gpd.GeoDataFrame(
        pd.concat([zones, extra], ignore_index=True), geometry="geometry", crs=zones.crs
    )


def describe_forced(forced, zones):
    """Print the forced polygons, those on unknown sides and those overlapping."""
    evacuated = zones[zones["zone"] == "evacuated"]
    built = evacuated[~evacuated["forced"].astype(bool)]
    own = evacuated[evacuated["forced"].astype(bool)]
    tree = shapely.STRtree(built.geometry.to_numpy())
    overlap = 0
    for geometry in own.geometry:
        near = tree.query(geometry, predicate="intersects")
        if (
            len(near)
            and shapely.area(
                shapely.intersection(geometry, built.geometry.to_numpy()[near])
            ).sum()
            > 0.01
        ):
            overlap += 1
    print(
        f"{len(forced):,} forced polygons (no free cell for a line element), "
        f"{int(forced['side_unknown'].sum()):,} with the uphill side unknown, "
        f"{overlap:,} overlapping a built polygon"
    )


def world_scenario(world_id):
    """The scenario name, and zones file tag, of one world's wall draw."""
    return f"w{world_id:03d}"


def main(*, extent, use_cached_layers, world_ids):
    """Build and write the zones of each world's wall draw.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ layers.
        world_ids: The exposure worlds to build; each must be in the draws.

    Raises:
        ValueError: If the faces were found again after the wall units were
            built, so the units may name other pifs, or a world is not in the
            draws.
    """
    units_path = wall_units_path(extent=extent)
    for upstream in (found_path(extent=extent), siz_table_path(extent=extent)):
        if upstream.exists() and upstream.stat().st_mtime > units_path.stat().st_mtime:
            msg = (
                f"{upstream.name} is newer than the wall units; rerun "
                "gen_urban_slope_wall_units.py"
            )
            raise ValueError(msg)
    units = gpd.read_parquet(units_path)
    draws = pd.read_parquet(wall_draws_path(extent=extent))
    dem, transform, _, ground_map, group, position = get_inputs(
        extent=extent, use_cached_layers=use_cached_layers
    )
    found = read_found(extent=extent)
    lineless = units_without_element(units, found.elements)
    found = add_line_elements(
        found,
        lineless.geometry,
        lineless["height_m"],
        dem=dem,
        ground_group=group,
        transform=transform,
        categories={"ground_row": position},
    )
    elements = found.elements
    on_line = elements["wall_unit_id"].notna()
    print(
        f"{len(lineless):,} wall units with no element "
        f"({lineless['unit_source'].value_counts().to_dict()}, "
        f"{int((~lineless['is_siz']).sum()):,} with no siz); "
        f"{int(on_line.sum()):,} given an element along their line (the rest "
        "lie on another element or off the DEM)"
    )
    still = lineless[~lineless.index.isin(elements["wall_unit_id"].dropna())]
    forced = gen_forced_elements(
        still.geometry,
        still["height_m"],
        dem=dem,
        transform=transform,
        first_label=int(elements.index.max()) + 1 if len(elements) else 1,
    )
    forced["majority_ground_row"] = ground_rows(forced.geometry, ground_map)
    forced_fill, forced_thickness = fill_by_element(forced, ground_map)
    element_frame = element_polygons(found, transform)
    element_frame["forced"] = False
    element_frame = gpd.GeoDataFrame(
        pd.concat([element_frame, forced.drop(columns=["line"]).assign(forced=True)]),
        geometry="geometry",
        crs=element_frame.crs,
    )
    element_frame.to_parquet(wall_elements_path(extent=extent))
    is_fill, thickness = fill_by_element(elements, ground_map)
    in_unit = elements["siz_id"].isin(units["member_pif_ids"].explode().dropna())
    print(
        "Elements of a siz whose pif is in no wall unit: "
        f"{int((~in_unit & ~on_line).sum()):,}"
    )

    for scenario, walled in SCENARIOS.items():
        result = build_slope_polygons(
            with_walls(found, walled),
            dem,
            transform,
            is_fill=is_fill,
            fill_thickness_m=thickness,
        )
        zones = with_forced(
            result,
            scenario,
            forced,
            pd.Series(walled, index=forced.index),
            forced_fill,
            forced_thickness,
        )
        zones.to_parquet(zones_path(scenario, extent=extent))
        if scenario == "walled":
            describe_forced(forced, zones)
        print(
            f"{scenario}: {len(result.polygons):,} polygons, "
            f"{result.polygons['area_m2'].sum():,.0f} m2 evacuated"
        )

    for world_id in world_ids:
        rows = draws[draws["world_id"] == world_id]
        if rows.empty:
            msg = (
                f"world {world_id} not drawn; add it to config WORLD_IDS and rerun "
                "gen_urban_slope_wall_units.py"
            )
            raise ValueError(msg)
        walled = rows.set_index("wall_unit_id")["walled"]
        flags = gen_element_walls(units, walled, elements)
        result = build_slope_polygons(
            with_walls(found, flags),
            dem,
            transform,
            is_fill=is_fill,
            fill_thickness_m=thickness,
        )
        scenario = world_scenario(world_id)
        forced_walled = pd.Series(
            forced["wall_unit_id"].map(walled).fillna(value=False).to_numpy(dtype=bool),
            index=forced.index,
        )
        with_forced(
            result, scenario, forced, forced_walled, forced_fill, forced_thickness
        ).to_parquet(zones_path(scenario, extent=extent))
        print(
            f"World {world_id}: {flags.mean():.1%} of elements walled, "
            f"{len(result.polygons):,} polygons, "
            f"{result.polygons['area_m2'].sum():,.0f} m2 evacuated"
        )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        world_ids=config.WORLD_IDS,
    )
