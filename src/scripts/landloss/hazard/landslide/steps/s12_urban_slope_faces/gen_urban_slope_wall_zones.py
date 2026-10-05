"""Step 12: the evacuated, imminent and inundated zones of each world's wall draw.

``gen_urban_slope_faces.py`` builds the zones twice, every siz walled and none,
as the bounds. This script builds them once per exposure world from the wall
units ``gen_urban_slope_wall_units.py`` drew: an element is walled where its
pif is a member of a walled unit
(:func:`landloss.hazard.landslide.wall_units.gen_element_walls`). These are
the zones downstream reads.

Writes ``urban-slope-zones-wNNN.parquet`` per world under
``temp/hazard/landslide/``, in the shape of the two bounds. It reads the
elements the faces script found (``urban-slope-found.pkl``) rather than
finding them again, so the pip to element pipeline runs once per extent.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/gen_urban_slope_wall_zones.py

Run ``gen_urban_slope_faces.py`` and then ``gen_urban_slope_wall_units.py``
first. Settings are in ``config.py``.
"""

import geopandas as gpd
import pandas as pd

from landloss.hazard.landslide.instability_zones import with_walls
from landloss.hazard.landslide.slope_polygons import build_slope_polygons
from landloss.hazard.landslide.wall_units import gen_element_walls
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    fill_by_element,
    found_path,
    get_dem,
    read_found,
    siz_table_path,
    zone_polygons,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_wall_units import (
    wall_draws_path,
    wall_units_path,
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
    found = read_found(extent=extent)
    dem, transform, _ = get_dem(extent=extent, use_cached_layers=use_cached_layers)
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    elements = found.elements
    is_fill, thickness = fill_by_element(elements, ground_map)
    in_unit = elements["siz_id"].isin(units["member_pif_ids"].explode().dropna())
    print(f"Elements whose pif is in no wall unit: {int((~in_unit).sum()):,}")

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
        zone_polygons(result, scenario=scenario).to_parquet(
            zones_path(scenario, extent=extent)
        )
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
