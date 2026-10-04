"""Evidence for retaining wall candidates, read onto the pifs.

A pif (a group of potential instability points) is a retaining wall candidate
when it is a siz, or when a GNS mapped wall lies on it: the 1 m grid cannot
resolve a wall under about half a metre, so a mapped wall with no step under it
stays a candidate, classed ``small``. This module attaches what is known about
each pif and does not put a probability on it; every weight for that is
judgement until the claim report extraction (T-50).
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.hazard.landslide.slope_elements import height_band

SIZ_CLASS = "siz"
SMALL_CLASS = "small"
NOT_CANDIDATE = "none"


def _nearest_m(
    pifs: gpd.GeoDataFrame, other: gpd.GeoDataFrame, *, max_distance_m: float
) -> pd.Series:
    """The distance from each pif to the nearest feature, NaN beyond the maximum."""
    result = pd.Series(np.nan, index=pifs.index, dtype=float)
    if other.empty:
        return result
    joined = gpd.sjoin_nearest(
        pifs[["geometry"]],
        other[["geometry"]],
        max_distance=max_distance_m,
        distance_col="distance_m",
    )
    nearest = joined.groupby(level=0)["distance_m"].min()
    result.loc[nearest.index] = nearest
    return result


def _touches(pifs: gpd.GeoDataFrame, other: gpd.GeoDataFrame) -> pd.Series:
    """Whether any point of each pif lies in one of the polygons."""
    if other.empty:
        return pd.Series(data=False, index=pifs.index)
    joined = gpd.sjoin(pifs[["geometry"]], other[["geometry"]], predicate="intersects")
    return pd.Series(pifs.index.isin(joined.index.unique()), index=pifs.index)


def wall_candidate_evidence(
    sizs: gpd.GeoDataFrame,
    *,
    walls: gpd.GeoDataFrame,
    cut_fill_lines: gpd.GeoDataFrame,
    cut_slopes: gpd.GeoDataFrame,
    fill_bodies: gpd.GeoDataFrame,
    ground_map: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    wall_match_m: float,
    search_m: float,
) -> pd.DataFrame:
    """Read the evidence for a retaining wall onto every pif.

    Args:
        sizs: The siz table with each pif's pips as geometry
            (:func:`landloss.hazard.landslide.instability_zones.gen_siz_table`),
            in the CRS of every other layer.
        walls: GNS mapped retaining walls (lines).
        cut_fill_lines: GNS cut/fill lines.
        cut_slopes: SLIDE cut slope polygons.
        fill_bodies: SLIDE fill body polygons.
        ground_map: The ground map (``material`` and ``modification``).
        buildings: Building outlines.
        wall_match_m: A mapped wall or line within this many metres of a pif's
            points is on it.
        search_m: Walls, lines and buildings further than this, in metres, are
            not recorded (their distance is NaN). At least ``wall_match_m``.

    Returns:
        A frame indexed like ``sizs`` with ``gns_wall_m``, ``gns_wall`` (a wall
        within ``wall_match_m``), ``cut_fill_line_m``,  ``in_slide_cut``,
        ``in_slide_fill``, ``ground_material``, ``ground_modification``,
        ``building_m``, ``height_band`` (of its largest delta_h),
        ``is_wall_candidate`` and ``candidate_class`` (``siz`` for a siz,
        ``small`` for a mapped wall with no siz, else ``none``).
    """
    pifs = sizs[["geometry"]]
    evidence = pd.DataFrame(index=sizs.index)
    evidence["gns_wall_m"] = _nearest_m(pifs, walls, max_distance_m=search_m)
    evidence["gns_wall"] = evidence["gns_wall_m"] <= wall_match_m
    evidence["cut_fill_line_m"] = _nearest_m(
        pifs, cut_fill_lines, max_distance_m=search_m
    )
    evidence["in_slide_cut"] = _touches(pifs, cut_slopes)
    evidence["in_slide_fill"] = _touches(pifs, fill_bodies)

    centres = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(sizs["x"], sizs["y"], crs=sizs.crs),
        index=sizs.index,
    )
    ground = gpd.sjoin(
        centres, ground_map[["material", "modification", "geometry"]], how="left"
    )
    ground = ground[~ground.index.duplicated()]
    evidence["ground_material"] = ground["material"].reindex(sizs.index)
    evidence["ground_modification"] = ground["modification"].reindex(sizs.index)

    evidence["building_m"] = _nearest_m(pifs, buildings, max_distance_m=search_m)
    evidence["height_band"] = height_band(sizs["max_delta_h_m"].to_numpy())

    is_siz = sizs["is_siz"].astype(bool)
    evidence["is_wall_candidate"] = is_siz | evidence["gns_wall"]
    evidence["candidate_class"] = np.where(
        is_siz, SIZ_CLASS, np.where(evidence["gns_wall"], SMALL_CLASS, NOT_CANDIDATE)
    )
    return evidence
