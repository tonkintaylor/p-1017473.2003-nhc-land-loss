"""Step 12 checks: the faces against the GNS mapping, and the size of the zones.

Three tables, written to ``report/hazard/landslide/urban-slope-faces/tab/``:

* ``gns-agreement.csv``: the share of the GNS mapped wall and break-in-slope
  length with a pip of a siz, or of any pif, within the match distance;
* ``polygon-sizes.csv``: the evacuated polygons of each scenario by area;
* ``sizs-by-group-band.csv``: the pifs by ground group and height band, and
  how many are sizs.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/table_urban_slope_face_checks.py

Run ``gen_urban_slope_faces.py`` first. Settings are in ``config.py``.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from landloss.hazard.landslide.instability_zones import read_siz_table
from landloss.hazard.landslide.slope_polygons import EVACUATED
from landloss.io.readers import get_gns_slide_morphology
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    CRS,
    CUT_FILL_LINE_TYPE,
    MAPPED_WALL_TYPE,
    SCENARIOS,
    siz_table_path,
    zones_path,
)
from scripts.landloss.paths import REPORT_DIR

TAB_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-faces" / "tab"

BREAK_TYPES = ("Concave break in slope", "Convex break in slope")
SHARP = "sharp"
SAMPLE_SPACING_M = 1.0


def sample_points(lines):
    """Points every ``SAMPLE_SPACING_M`` along every line, as an (n, 2) array."""
    points = []
    for line in lines.geometry.explode(index_parts=False):
        n = max(int(line.length // SAMPLE_SPACING_M), 1)
        along = np.linspace(0.0, line.length, n + 1)
        points.append(
            shapely.get_coordinates(shapely.line_interpolate_point(line, along))
        )
    return np.vstack(points) if points else np.empty((0, 2))


def pip_tree(pifs):
    """A KD-tree on the pips of the pifs, or None if there are none."""
    xy = shapely.get_coordinates(pifs.geometry)
    return cKDTree(xy) if len(xy) else None


def share_within(points, tree, distance_m):
    """The share of the points with a pip within the distance."""
    if tree is None or not len(points):
        return float("nan")
    return float((tree.query(points)[0] <= distance_m).mean())


def gns_agreement(sizs, morphology, *, wall_match_m, break_match_m):
    """The share of each GNS feature type's length near a siz and near any pif."""
    layers = {
        "GNS mapped wall": (morphology["Type"] == MAPPED_WALL_TYPE, wall_match_m),
        "GNS cut/fill line": (morphology["Type"] == CUT_FILL_LINE_TYPE, wall_match_m),
        "GNS sharp break in slope": (
            morphology["Type"].isin(BREAK_TYPES) & (morphology["Subtype"] == SHARP),
            break_match_m,
        ),
        "GNS rounded break in slope": (
            morphology["Type"].isin(BREAK_TYPES) & (morphology["Subtype"] != SHARP),
            break_match_m,
        ),
    }
    trees = {"siz": pip_tree(sizs[sizs["is_siz"]]), "any_pif": pip_tree(sizs)}
    rows = []
    for name, (mask, distance_m) in layers.items():
        points = sample_points(morphology[mask])
        row = {"feature": name, "match_m": distance_m, "sample_points": len(points)}
        for tree_name, tree in trees.items():
            row[f"share_near_{tree_name}"] = share_within(points, tree, distance_m)
        rows.append(row)
    return pd.DataFrame(rows)


def polygon_sizes(*, extent, large_polygon_m2):
    """The evacuated polygons of each scenario by area."""
    rows = []
    for scenario in SCENARIOS:
        zones = gpd.read_parquet(zones_path(scenario, extent=extent))
        area = zones.loc[zones["zone"] == EVACUATED].geometry.area
        rows.append(
            {
                "scenario": scenario,
                "polygons": len(area),
                "total_m2": area.sum(),
                "median_m2": area.median(),
                "p90_m2": area.quantile(0.9),
                "max_m2": area.max(),
                "over_review_area": int((area > large_polygon_m2).sum()),
                "review_area_m2": large_polygon_m2,
            }
        )
    return pd.DataFrame(rows)


def sizs_by_group_band(sizs):
    """The pifs by ground group and height band, with the count of sizs."""
    return (
        sizs.groupby(["ground_group", "height_band"])["is_siz"]
        .agg(pifs="size", sizs="sum")
        .reset_index()
    )


def main(
    *, extent, use_cached_layers, gns_wall_match_m, gns_break_match_m, large_polygon_m2
):
    """Write the three check tables for the extent.

    Args:
        extent: The build extent.
        use_cached_layers: Whether to reuse the cached GNS layers.
        gns_wall_match_m: Match distance for walls and cut/fill lines, in metres.
        gns_break_match_m: Match distance for breaks in slope, in metres.
        large_polygon_m2: Evacuated polygons over this area are counted.
    """
    sizs = read_siz_table(siz_table_path(extent=extent))
    morphology = get_gns_slide_morphology(
        bbox=tuple(sizs.total_bounds), crs=CRS, use_cache=use_cached_layers
    )
    tables = {
        "gns-agreement": gns_agreement(
            sizs,
            morphology,
            wall_match_m=gns_wall_match_m,
            break_match_m=gns_break_match_m,
        ),
        "polygon-sizes": polygon_sizes(
            extent=extent, large_polygon_m2=large_polygon_m2
        ),
        "sizs-by-group-band": sizs_by_group_band(sizs),
    }
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(TAB_DIR / f"{name}.csv", index=False, float_format="%.3f")
        print(f"\n{name}\n{table.to_string(index=False)}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        gns_wall_match_m=config.GNS_WALL_MATCH_M,
        gns_break_match_m=config.GNS_BREAK_MATCH_M,
        large_polygon_m2=config.LARGE_POLYGON_M2,
    )
