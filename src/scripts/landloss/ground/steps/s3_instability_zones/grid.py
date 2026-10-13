"""The siz table's grid columns and the element polygons, for a whole or a tiled run.

Kept apart from ``gen_instability_zones.py`` so that a tile's worker process
(:func:`tiled.build_tile`) imports them by module name, whatever script was run.
"""

import geopandas as gpd
import pandas as pd
from rasterio import features

from landloss.hazard.landslide.instability_zones import (
    gen_pif_near_drops,
    gen_pif_spines,
    gen_pif_verticality,
    gen_siz_table,
)

CRS = 2193


def wall_column(name):
    """The siz table's name for a spine column read along the wall line."""
    return {"spine": "wall_line", "spine_length_m": "wall_length_m"}.get(
        name, f"wall_{name}"
    )


def grid_table(
    zones, dem, transform, *, end_window_m, wall_height_reach_m, wall_height_quantile
):
    """The siz table with the columns read off the grid: drops, verticality, spines.

    Besides each piece's spine (its cut line) the table carries its wall line
    (the lead, 2026-10-13: ``wall_line``, ``wall_length_m``, ``wall_end_a_x`` and
    the other spine columns read along the wall line, but for
    ``fall_resultant``), None and NaN on a piece with no wall (``has_wall``
    False).
    """
    table = gen_siz_table(zones, transform, crs=CRS)
    table["near_drop_p80_m"] = gen_pif_near_drops(
        dem,
        zones.pips,
        zones.pif_labels,
        abs(transform.a),
        reach_m=wall_height_reach_m,
        quantile=wall_height_quantile,
    ).reindex(table.index)
    table["verticality"] = gen_pif_verticality(
        dem, zones.pips, zones.pif_labels
    ).reindex(table.index)
    table = table.join(
        gen_pif_spines(
            table,
            cell_size_m=abs(transform.a),
            end_window_m=end_window_m,
            lines=zones.pif_lines,
        )
    )
    walled = table[table["has_wall"]]
    walls = gen_pif_spines(
        walled,
        cell_size_m=abs(transform.a),
        end_window_m=end_window_m,
        lines=zones.wall_lines,
    ).drop(columns="fall_resultant")
    return table.join(walls.rename(columns=wall_column))


def element_polygons(found, transform):
    """The grown elements as polygons, with their attributes."""
    shapes = features.shapes(
        found.labels.astype("int32"), mask=found.labels > 0, transform=transform
    )
    rows = [
        {"type": "Feature", "geometry": g, "properties": {"label": int(v)}}
        for g, v in shapes
    ]
    # A tile can hold pifs but grow no element (a few slivers of hillside at the
    # edge of Upper Hutt did), and from_features cannot build an empty frame.
    if not rows:
        frame = gpd.GeoDataFrame(
            geometry=gpd.GeoSeries([], crs=CRS),
            index=pd.Index([], dtype="int64", name="label"),
        )
        return frame.join(found.elements, how="left")
    frame = gpd.GeoDataFrame.from_features(rows, crs=CRS)
    frame = frame.dissolve(by="label")
    return frame.join(found.elements, how="left")
