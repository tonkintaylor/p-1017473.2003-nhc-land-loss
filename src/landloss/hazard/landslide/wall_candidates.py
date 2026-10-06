"""Evidence for retaining wall candidates, read onto the pifs.

A pif piece (a group of potential instability points) is a retaining wall
candidate when it is a siz, or when a GNS mapped wall lies within 2 m of its
pips: the 1 m grid cannot resolve a wall under about half a metre, so a mapped
wall with no step under it stays a candidate, classed ``low_height`` (a
low-height wall; ``small`` until 2026-10-07). A stretch of GNS mapped wall
more than 2 m from every pip becomes candidates of its own, classed
``gns_only``, cut by the shared line rules
(:mod:`landloss.hazard.landslide.bend_split`), so no mapped wall is lost. A
mapped wall within 2 m of a pif piece is no candidate of its own; it sets that
piece's ``gns_wall`` flag. Every candidate is independent (the lead,
2026-10-07). Every candidate is tied to the property it lies on. This module attaches
what is known about each candidate and does not put a probability on it; every
weight for that is judgement until the claim report extraction (T-50).
"""

from itertools import pairwise

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.exposure.land.extent import stack_representatives
from landloss.hazard.landslide import bend_split
from landloss.hazard.landslide.slope_elements import height_band

SIZ_CLASS = "siz"
LOW_HEIGHT_CLASS = "low_height"
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
        ``low_height`` for a mapped wall with no siz, else ``none``).
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
        is_siz,
        SIZ_CLASS,
        np.where(evidence["gns_wall"], LOW_HEIGHT_CLASS, NOT_CANDIDATE),
    )
    return evidence


def _property_frame(properties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The property polygons with only the columns a candidate carries.

    Stacked unit titles (identical geometry) are one piece of ground: only the
    title :func:`~landloss.exposure.land.extent.stack_representatives` picks
    for the stack is kept, so a candidate on the stack goes to the title the
    claim and NZMM records go to.
    """
    properties = properties.reset_index(drop=True)
    stack = stack_representatives(properties)
    properties = properties[stack.to_numpy() == properties.index.to_numpy()]
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
    clean that is. The wall itself goes to the rateable property: the one
    holding most of the pif's points unless that is a road parcel, in which
    case the non-road property with the next most (ties to the lowest
    ``property_id``); a pif with no point on a non-road property has none, so
    its wall is out of the exposure but still in the hazard (it still fails).
    Hydro parcels count as rateable here; they get no claim id later. A stack
    of unit titles counts once, as the title that represents it.

    Args:
        sizs: The siz table with each pif's pips as geometry.
        properties: LINZ property boundaries
            (:func:`landloss.io.readers.get_nz_property_boundaries`), in the
            CRS of ``sizs``.

    Returns:
        A frame indexed like ``sizs`` with ``property_id``, ``property_source``,
        ``valuation_reference``, ``title_type``, ``property_is_road``,
        ``property_share`` (the fraction of the pif's points in that property)
        ``n_properties`` (how many properties its points touch),
        ``rateable_property_id`` (NA where no non-road property holds a point)
        and ``rateable_share`` (the fraction of the pif's points in it, 0 where
        NA). A pif with no point in any property has NaN in the property
        columns and 0 in ``n_properties`` and ``property_share``.
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

    rows = per_property["index_right"].astype(int).to_numpy()
    rateable = per_property.assign(
        property_id=frame["property_id"].to_numpy()[rows],
        is_road=frame["property_is_road"].to_numpy()[rows],
    )
    rateable = rateable[~rateable["is_road"]].sort_values(
        ["pif", "n", "property_id"], ascending=[True, False, True]
    )
    rateable = rateable.drop_duplicates("pif").set_index("pif")
    result["rateable_property_id"] = rateable["property_id"].reindex(sizs.index)
    result["rateable_share"] = (
        (rateable["n"] / n_points.reindex(rateable.index))
        .reindex(sizs.index)
        .fillna(0.0)
    )
    return result


def boundary_positions(
    line: shapely.LineString, boundaries: gpd.GeoDataFrame, min_segment_m: float
) -> list[float]:
    """Where a line crosses property boundaries, one stretch per property.

    The line is cut at every crossing; consecutive stretches in the same
    property (the one holding each stretch's midpoint) are one, so a wall
    weaving along a boundary is not cut at every weave; and a stretch
    shorter than ``min_segment_m`` joins the one before it (or after it, for
    the first). The boundary stage of the 50 m cap
    (:func:`landloss.hazard.landslide.bend_split.cap_ranges`).

    Args:
        line: The line.
        boundaries: Property polygons with ``property_id``
            (:func:`_property_frame`).
        min_segment_m: The shortest stretch.

    Returns:
        The cuts, as distances along the line (none where it stays in one
        property).
    """
    polygons = boundaries.geometry.to_numpy()
    near = shapely.STRtree(polygons).query(line, predicate="intersects")
    if len(near) < 2:
        return []
    crossings = shapely.intersection(
        line, shapely.union_all(shapely.boundary(polygons[near]))
    )
    at = np.unique(
        shapely.line_locate_point(
            line, shapely.points(shapely.get_coordinates(crossings))
        )
    )
    length = line.length
    cuts = np.r_[0.0, at[(at > 1e-6) & (at < length - 1e-6)], length]
    middle = shapely.line_interpolate_point(line, (cuts[:-1] + cuts[1:]) / 2.0)
    ids = boundaries["property_id"].to_numpy()[near]
    inside = shapely.contains(polygons[near][None, :], middle[:, None])
    owner = [ids[row.argmax()] if row.any() else None for row in inside]
    ranges: list[list[float]] = []
    previous = object()
    for (a, b), label in zip(pairwise(cuts), owner, strict=True):
        if ranges and label == previous:
            ranges[-1][1] = b
        else:
            ranges.append([a, b])
        previous = label
    while len(ranges) > 1:
        sizes = [b - a for a, b in ranges]
        i = int(np.argmin(sizes))
        if sizes[i] >= min_segment_m:
            break
        j = i - 1 if i > 0 else 1
        low, high = min(i, j), max(i, j)
        ranges[low] = [ranges[low][0], ranges[high][1]]
        del ranges[high]
    return [float(a) for a, _ in ranges[1:]]


def split_by_rules(
    line: shapely.LineString,
    *,
    boundaries: gpd.GeoDataFrame | None,
    max_bends: int,
    stray_tolerance_m: float,
    min_segment_m: float,
    max_length_m: float,
    max_turn_deg: float,
) -> list[shapely.LineString]:
    """Cut a line into pieces that each keep the shared line rules.

    The line, walked as points every half metre, is cut by
    :func:`landloss.hazard.landslide.bend_split.cut_path` (at most
    ``max_bends`` bends within ``stray_tolerance_m``, turning at most
    ``max_turn_deg``, ends at least ``min_segment_m`` apart, and a piece over
    ``max_length_m`` cut at its bends, then at the property boundaries it
    crosses, then evenly), and each piece is its line
    (:func:`~landloss.hazard.landslide.bend_split.canonical_line`). A piece
    whose line is still under ``min_segment_m`` (a stretch folded tightly on
    itself) is left out.
    """
    xy = shapely.get_coordinates(shapely.segmentize(line, 0.5))
    if len(xy) < 2:
        return []
    pieces = []
    for start, end in bend_split.cut_path(
        xy,
        max_bends=max_bends,
        tolerance_m=stray_tolerance_m,
        min_segment_m=min_segment_m,
        max_length_m=max_length_m,
        max_turn_deg=max_turn_deg,
        boundary_cuts=None
        if boundaries is None
        else (lambda shape: boundary_positions(shape, boundaries, min_segment_m)),
    ):
        piece = shapely.LineString(
            bend_split.canonical_line(
                xy[start : end + 1],
                tolerance_m=stray_tolerance_m,
                max_bends=max_bends,
                min_segment_m=min_segment_m,
                max_turn_deg=max_turn_deg,
            )
        )
        if piece.length >= min_segment_m - 1e-6:
            pieces.append(piece)
    return pieces


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
    max_bends: int,
    stray_tolerance_m: float,
    max_turn_deg: float,
) -> gpd.GeoDataFrame:
    """Make candidates of every stretch of GNS mapped wall that no pif covers.

    A mapped wall too low for the 1 m grid to resolve, or lost to smoothing in
    the DEM, has no pip near it, so it is on no pif. Each stretch of mapped
    wall further than ``wall_match_m`` from every pip, and at least
    ``min_length_m`` long, is cut by the shared line rules
    (:func:`split_by_rules`, the lead, 2026-10-07; an equal 20 m cut before)
    and each piece is an independent candidate, classed ``gns_only``.

    Args:
        sizs: The siz table with each pif's pips as geometry.
        walls: GNS mapped retaining walls (lines).
        properties: LINZ property boundaries.
        ground_map: The ground map (``material`` and ``modification``).
        buildings: Building outlines.
        wall_match_m: A wall within this many metres of a pip is on its pif.
        min_length_m: Stretches shorter than this are dropped, and the
            shortest a piece may be.
        max_length_m: The longest a piece may be.
        search_m: The building distance is NaN beyond this.
        max_bends: The most bends a piece may have.
        stray_tolerance_m: How far a piece's line may stray from the wall.
        max_turn_deg: The most a piece's line may turn in all.

    Returns:
        Line candidates, indexed by ``gns_only_id`` (from 0), with
        ``length_m``, ``x`` and ``y`` (the midpoint),
        ``candidate_class``, the property columns of :func:`property_of_pifs`
        (the property holding most of the line's length) and its
        ``rateable_property_id`` (by the same rule as a pif's, on length),
        ``ground_material``, ``ground_modification`` and ``building_m``.
    """
    pips = shapely.get_parts(sizs.geometry.to_numpy())
    tree = shapely.STRtree(pips)
    boundaries = _property_frame(properties).reset_index(drop=True)
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
                split_by_rules(
                    stretch,
                    boundaries=boundaries,
                    max_bends=max_bends,
                    stray_tolerance_m=stray_tolerance_m,
                    min_segment_m=min_length_m,
                    max_length_m=max_length_m,
                    max_turn_deg=max_turn_deg,
                )
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
    candidates.index.name = "gns_only_id"
    return candidates


def _property_of_lines(
    lines: gpd.GeoDataFrame, properties: gpd.GeoDataFrame
) -> pd.DataFrame:
    """The property holding the longest part of each line, NaN where none.

    Also ``rateable_property_id``, by the rule :func:`property_of_pifs` uses
    with length in place of points: the non-road property holding the longest
    part, ties to the lowest ``property_id``, NA where the line touches no
    non-road property. A GNS-only piece and the pif it duplicates are then on
    one property and can join.
    """
    frame = _property_frame(properties).reset_index(drop=True)
    joined = gpd.sjoin(lines[["geometry"]], frame[["geometry"]], how="inner")
    overlap = shapely.length(
        shapely.intersection(
            joined.geometry.to_numpy(),
            frame.geometry.to_numpy()[joined["index_right"].to_numpy()],
        )
    )
    rows = joined["index_right"].to_numpy()
    joined = pd.DataFrame(
        {
            "line": joined.index.to_numpy(),
            "index_right": rows,
            "overlap_m": overlap,
            "property_id": frame["property_id"].to_numpy()[rows],
            "is_road": frame["property_is_road"].to_numpy()[rows],
        }
    ).sort_values(
        ["line", "overlap_m", "property_id"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    best = joined.drop_duplicates("line").set_index("line")
    columns = [c for c in frame.columns if c != "geometry"]
    chosen = frame.loc[best["index_right"], columns]
    chosen.index = best.index
    result = chosen.reindex(lines.index)
    rateable = joined[~joined["is_road"]].drop_duplicates("line").set_index("line")
    result["rateable_property_id"] = (
        rateable["property_id"].reindex(lines.index).astype("string")
    )
    return result
