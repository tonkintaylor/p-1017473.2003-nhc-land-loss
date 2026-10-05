"""Evidence for retaining wall candidates, read onto the pifs.

A pif (a group of potential instability points) is a retaining wall candidate
when it is a siz, or when a GNS mapped wall lies on it: the 1 m grid cannot
resolve a wall under about half a metre, so a mapped wall with no step under it
stays a candidate, classed ``small``. A GNS mapped wall with no pip near it at
all becomes a candidate of its own, classed ``gns_only``, so no mapped wall is
lost. Every candidate is tied to the property it lies on. This module attaches
what is known about each candidate and does not put a probability on it; every
weight for that is judgement until the claim report extraction (T-50).
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.ops import substring

from landloss.hazard.landslide.slope_elements import height_band

SIZ_CLASS = "siz"
SMALL_CLASS = "small"
GNS_ONLY_CLASS = "gns_only"
NOT_CANDIDATE = "none"

# The columns of the LINZ property boundaries layer a candidate carries, under
# these names. ``source`` says whether the polygon is a rateable property or a
# road parcel.
PROPERTY_COLUMNS = {
    "source_id": "property_id",
    "source": "property_source",
    "valuation_reference": "valuation_reference",
    "title_type": "title_type",
}
ROAD_SOURCE_MARK = "Road"


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


def _ground_at(
    candidates: gpd.GeoDataFrame, ground_map: gpd.GeoDataFrame
) -> pd.DataFrame:
    """The ground map's material and modification at each candidate's x, y."""
    centres = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(
            candidates["x"], candidates["y"], crs=candidates.crs
        ),
        index=candidates.index,
    )
    ground = gpd.sjoin(
        centres, ground_map[["material", "modification", "geometry"]], how="left"
    )
    ground = ground[~ground.index.duplicated()]
    return ground[["material", "modification"]].reindex(candidates.index)


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

    ground = _ground_at(sizs, ground_map)
    evidence["ground_material"] = ground["material"]
    evidence["ground_modification"] = ground["modification"]
    evidence["building_m"] = _nearest_m(pifs, buildings, max_distance_m=search_m)
    evidence["height_band"] = height_band(sizs["max_delta_h_m"].to_numpy())

    is_siz = sizs["is_siz"].astype(bool)
    evidence["is_wall_candidate"] = is_siz | evidence["gns_wall"]
    evidence["candidate_class"] = np.where(
        is_siz, SIZ_CLASS, np.where(evidence["gns_wall"], SMALL_CLASS, NOT_CANDIDATE)
    )
    return evidence


def _property_frame(properties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The property polygons with only the columns a candidate carries."""
    frame = properties.rename(columns=PROPERTY_COLUMNS)[
        [*PROPERTY_COLUMNS.values(), "geometry"]
    ].copy()
    frame["property_id"] = frame["property_id"].astype(str)
    frame["property_is_road"] = frame["property_source"].str.contains(
        ROAD_SOURCE_MARK, na=False
    )
    return frame


def property_of_pifs(
    sizs: gpd.GeoDataFrame, properties: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Tie every pif to the property most of its points lie in.

    A pif on a boundary wall has points in two properties; it is given the one
    holding most of them, and ``property_share`` and ``n_properties`` say how
    clean that is.

    Args:
        sizs: The siz table with each pif's pips as geometry.
        properties: LINZ property boundaries
            (:func:`landloss.io.readers.get_nz_property_boundaries`), in the
            CRS of ``sizs``.

    Returns:
        A frame indexed like ``sizs`` with ``property_id``, ``property_source``,
        ``valuation_reference``, ``title_type``, ``property_is_road``,
        ``property_share`` (the fraction of the pif's points in that property)
        and ``n_properties`` (how many properties its points touch). A pif with
        no point in any property has NaN in the property columns and 0 in
        ``n_properties`` and ``property_share``.
    """
    parts = sizs.geometry.explode(index_parts=False)
    points = gpd.GeoDataFrame(
        {"pif": parts.index.to_numpy()}, geometry=parts.to_numpy(), crs=sizs.crs
    )
    frame = _property_frame(properties).reset_index(drop=True)
    joined = gpd.sjoin(points, frame[["geometry"]], how="left")
    joined = joined[~joined.index.duplicated()]

    n_points = joined.groupby("pif").size()
    per_property = (
        joined.dropna(subset=["index_right"])
        .groupby(["pif", "index_right"])
        .size()
        .rename("n")
        .reset_index()
    )
    best = per_property.sort_values(["pif", "n"], ascending=[True, False])
    best = best.drop_duplicates("pif").set_index("pif")

    columns = [c for c in frame.columns if c != "geometry"]
    chosen = frame.loc[best["index_right"].astype(int), columns]
    chosen.index = best.index

    result = chosen.reindex(sizs.index)
    result["property_share"] = (best["n"] / n_points.reindex(best.index)).reindex(
        sizs.index
    )
    result["property_share"] = result["property_share"].fillna(0.0)
    result["n_properties"] = (
        per_property.groupby("pif").size().reindex(sizs.index).fillna(0).astype(int)
    )
    return result


def _split_line(line: shapely.LineString, max_length_m: float) -> list:
    """Cut a line into equal pieces none longer than the maximum."""
    n = int(np.ceil(line.length / max_length_m))
    step = line.length / n
    return [substring(line, i * step, (i + 1) * step) for i in range(n)]


def gen_gns_only_candidates(
    sizs: gpd.GeoDataFrame,
    *,
    walls: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    ground_map: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    wall_match_m: float,
    min_length_m: float,
    max_length_m: float,
    search_m: float,
) -> gpd.GeoDataFrame:
    """Make a candidate of every stretch of GNS mapped wall that no pif covers.

    A mapped wall too low for the 1 m grid to resolve, or lost to smoothing in
    the DEM, has no pip near it, so it is on no pif. Each stretch of mapped wall
    further than ``wall_match_m`` from every pip becomes a candidate of its own,
    classed ``gns_only``, cut into pieces no longer than ``max_length_m`` so a
    candidate is the size of a pif.

    Args:
        sizs: The siz table with each pif's pips as geometry.
        walls: GNS mapped retaining walls (lines).
        properties: LINZ property boundaries.
        ground_map: The ground map (``material`` and ``modification``).
        buildings: Building outlines.
        wall_match_m: A wall within this many metres of a pip is on its pif.
        min_length_m: Stretches shorter than this are dropped.
        max_length_m: Stretches longer than this are cut into equal pieces.
        search_m: The building distance is NaN beyond this.

    Returns:
        Line candidates with ``length_m``, ``x`` and ``y`` (the midpoint),
        ``candidate_class``, the property columns of :func:`property_of_pifs`
        (the property holding most of the line's length), ``ground_material``,
        ``ground_modification`` and ``building_m``.
    """
    pips = shapely.get_parts(sizs.geometry.to_numpy())
    tree = shapely.STRtree(pips)
    pieces = []
    for line in shapely.get_parts(walls.geometry.to_numpy()):
        near = tree.query(line, predicate="dwithin", distance=wall_match_m)
        if len(near):
            line = line.difference(
                shapely.union_all(shapely.buffer(pips[near], wall_match_m))
            )
        pieces.extend(
            part
            for stretch in shapely.get_parts(line)
            if isinstance(stretch, shapely.LineString)
            for part in (
                _split_line(stretch, max_length_m)
                if stretch.length >= min_length_m
                else []
            )
        )

    candidates = gpd.GeoDataFrame(geometry=pieces, crs=sizs.crs)
    candidates["length_m"] = candidates.length
    midpoints = candidates.interpolate(0.5, normalized=True)
    candidates["x"] = midpoints.x
    candidates["y"] = midpoints.y
    candidates["candidate_class"] = GNS_ONLY_CLASS

    candidates = candidates.join(_property_of_lines(candidates, properties))
    ground = _ground_at(candidates, ground_map)
    candidates["ground_material"] = ground["material"]
    candidates["ground_modification"] = ground["modification"]
    candidates["building_m"] = _nearest_m(
        candidates, buildings, max_distance_m=search_m
    )
    return candidates


def _property_of_lines(
    lines: gpd.GeoDataFrame, properties: gpd.GeoDataFrame
) -> pd.DataFrame:
    """The property holding the longest part of each line, NaN where none."""
    frame = _property_frame(properties).reset_index(drop=True)
    joined = gpd.sjoin(lines[["geometry"]], frame[["geometry"]], how="inner")
    overlap = shapely.length(
        shapely.intersection(
            joined.geometry.to_numpy(),
            frame.geometry.to_numpy()[joined["index_right"].to_numpy()],
        )
    )
    joined = joined.assign(overlap_m=overlap).sort_values("overlap_m", ascending=False)
    best = joined[~joined.index.duplicated()]
    columns = [c for c in frame.columns if c != "geometry"]
    chosen = frame.loc[best["index_right"], columns]
    chosen.index = best.index
    return chosen.reindex(lines.index)
