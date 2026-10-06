"""Wall units on the pifs: which faces are one wall, and how likely it is there.

A retaining wall can be several pifs (a long wall is cut at the pif span, and a
wall with a gap is two pifs) and a GNS mapped wall too low for the grid is a
``gns_only`` piece with no pif, so the model counts walls, not pifs. This
module:

1. **Units.** Joins the candidate pifs (classes ``siz`` and ``small``) and the
   ``gns_only`` pieces into wall units, end to end only and across property
   boundaries (the lead, 2026-10-06: one wall is one unit wherever the
   boundaries run): pieces one GNS mapped wall reaches are one unit; a
   ``gns_only`` piece near a pif and running roughly along its face joins it;
   elsewhere two pifs join where their facing ends are close, level along the
   fall and facing the same way, or close enough to be a corner. The joined
   members are chained end to end and cut into walls that each follow the
   chain within a tolerance with at most a few bends, and a wall over a set
   length is cut again at the property boundaries it crosses
   (:func:`gen_unit_lines`); each wall is a unit with the members nearest it,
   and carries its length in every property it enters
   (:func:`gen_unit_properties`).
2. **Prior.** Puts a prior on each unit from whether it holds a siz, the height
   band of its wall height and the cut and fill class of landslide step 13:
   higher on fill and cut and fill, lower on a cut in rock and on natural
   ground (:func:`gen_wall_prior`).
3. **Floor.** Lifts a unit with a GNS mapped wall on it to a floor
   (:func:`gen_gns_floor`). GNS is the only dataset that locates a wall, so it
   is the only evidence on a candidate, and it is one-sided: GNS maps only the
   walls visible from above, so the part of a unit no mapped wall reaches is
   not evidence against a wall there.
4. **Update.** The claim reports and NZMM count walls per property, not which
   candidate is the wall, so each property's units are updated on the count
   with the Poisson-binomial (:func:`gen_count_update`); no probability falls.
   A unit is a wall on every property it enters by at least
   :data:`BETA_MIN_WALL_LENGTH_IN_PROPERTY_M`, so it takes part in each of
   their updates and keeps the highest.
   NZMM, unreliable, takes only a share of its update
   (``BETA_NZMM_UPDATE_WEIGHT``).
5. **Draw.** Draws each unit walled per exposure world, and turns the draw
   into the element flags the polygon builder reads (:func:`gen_wall_draws`,
   :func:`gen_element_walls`).

Every weight is a ``BETA_`` constant in :mod:`landloss.domain.constants`,
judgement until the claim report extraction (**T-50**) calibrates it.

**What the candidates miss.** A wall under about 0.7 m (about 1.0 m where it
faces a diagonal) makes no pips, because that is the drop a pip needs at 1, 3
and 5 m (``PIP_DROP_M`` and ``PIP_OFFSETS_M`` in
:mod:`landloss.hazard.landslide.instability_zones`); such a wall is a
candidate only where GNS maps it. No prior is lowered for it.

**Height from the siz table, class from landslide step 13.** A pif's
wall height is the siz table's ``near_drop_p80_m`` (since 2026-10-06): a
quantile over its pips of the drop to the lowest cell within 3 m below each
pip along its fall
(:func:`~landloss.hazard.landslide.instability_zones.gen_pif_near_drops`).
Neither its largest pip drop ``max_delta_h_m`` nor step 13's walk to the
foot of the face, which runs on down a long batter or hillside, is used:
both overstated the retained height. Step 13 classes every pif
(``urban-slope-pif-cut-fill{suffix}``), and its ``cut_fill_class`` sets the prior's
fill, rock cut and natural factors; the ground map's material says only
whether a cut is in rock. Fill on the ground map (its fill materials and its
``modification``) and the SLIDE fill bodies no longer set the prior: the
modification is ``fill`` on 88% of the pilot's candidate pifs, rock
included, so it lifted nearly every unit.
"""

from collections import Counter
from itertools import pairwise

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import ArrayLike, NDArray
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, minimum_spanning_tree
from scipy.spatial import cKDTree
from scipy.spatial.distance import pdist, squareform

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.exposure.land.extent import stack_representatives
from landloss.hazard.landslide import bend_split, pif_cut_fill
from landloss.hazard.landslide.bend_split import (
    cut_path,
    tree_paths,
)
from landloss.hazard.landslide.ground_map import ROCK_MATERIALS
from landloss.hazard.landslide.slope_elements import height_band
from landloss.hazard.landslide.wall_candidates import (
    SIZ_CLASS,
    SMALL_CLASS,
    _property_frame,
)
from landloss.hazard.realisation import realisation_seed

# The two kinds of member a wall unit is made of.
PIF_MEMBER, GNS_ONLY_MEMBER = "pif", "gns_only"
UNIT_SOURCES = (PIF_MEMBER, GNS_ONLY_MEMBER)

# Judgement (the lead, 2026-10-06): a wall unit counts as a wall on every
# property it enters by at least this many metres of its line, with that
# length; less is a line drawn a little over the boundary.
BETA_MIN_WALL_LENGTH_IN_PROPERTY_M = 1.0

# A unit's members are walked as points this far apart, at most, when they
# are chained into one line; a long unit's points are spaced further so that
# there are no more than _MAX_LINE_POINTS.
_LINE_SPACING_M = 0.5
_MAX_LINE_POINTS = 1500

# The pif candidate classes that become members.
CANDIDATE_CLASSES = (SIZ_CLASS, SMALL_CLASS)

# The basis strings: the last rule that set a unit's probability.
P_WALL_BASES = (
    "prior",
    "rock_cut",
    "fill",
    "natural",
    "property_boundary",
    "road_frontage",
    "tall_face",
    "gns_floor",
    "gns_only",
    "claims",
    "nzmm",
)
(
    PRIOR,
    ROCK_CUT,
    FILL,
    NATURAL,
    PROPERTY_BOUNDARY,
    ROAD_FRONTAGE,
    TALL_FACE,
    GNS_FLOOR,
    GNS_ONLY,
    CLAIMS,
    NZMM,
) = P_WALL_BASES

# The two updates written to the candidates missing table.
UPDATES = ("claims", "claims_nzmm")

# The stream each exposure world's wall unit draw comes from.
DRAW_STREAM = "wall_units"

# The landslide step 13 classes that take the fill factor: the front of a
# platform and a benched face with fill at its crest.
FILL_CLASSES = (pif_cut_fill.FILL, pif_cut_fill.CUT_AND_FILL)

# The landslide step 13 column a pif member reads, per pif: its class.
CUT_FILL_COLUMNS = ("cut_fill_class",)

# The siz table columns a pif member reads, and the GNS-only columns.
PIF_COLUMNS = (
    "candidate_class",
    "rateable_property_id",
    "spine",
    "spine_length_m",
    "end_a_x",
    "end_a_y",
    "end_b_x",
    "end_b_y",
    "end_a_fall_deg",
    "end_b_fall_deg",
    "max_delta_h_m",
    "near_drop_p80_m",
    "building_m",
    "ground_group",
    "ground_material",
    "height_band",
    "in_slide_fill",
    "gns_wall",
    "is_siz",
)
GNS_ONLY_COLUMNS = (
    "rateable_property_id",
    "length_m",
    "building_m",
    "ground_material",
    "step_height_m",
)

# The record layer columns carried through where the layer has them: the NZMM
# slope class and the GNS mapped walls within 2 m, for the strata check.
OPTIONAL_RECORD_COLUMNS = ("nzmm_slope_class", "gns_walls_2m")

# The columns a unit takes from its longest member.
LONGEST_MEMBER_COLUMNS = (
    "ground_group",
    "ground_material",
    "height_band",
    "in_slide_fill",
)


def _require(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    """Refuse a frame missing any of the columns.

    Raises:
        ValueError: If a column is missing.
    """
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        msg = f"{name} is missing {missing}"
        raise ValueError(msg)


def _components(n: int, edges: list[NDArray[np.int64]]) -> NDArray[np.int64]:
    """The connected component of each of ``n`` nodes joined by the edge pairs."""
    pairs = (
        np.concatenate(edges) if edges else np.zeros((0, 2), dtype=np.int64)
    ).reshape(-1, 2)
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(graph, directed=False)[1].astype(np.int64)


def gen_gns_wall_features(
    walls: gpd.GeoDataFrame, *, snap_m: float
) -> gpd.GeoDataFrame:
    """Group the GNS mapped wall segments into features, one per mapped wall.

    The GNS morphology layer draws one wall as several segments; segments
    within ``snap_m`` of each other, directly or through others, are one
    feature.

    Args:
        walls: GNS mapped retaining walls (lines or multilines).
        snap_m: Segments this close, in metres, are one feature.

    Returns:
        One row per feature, indexed by ``gns_feature_id`` from 0 in the order
        of each feature's first input row, with a MultiLineString geometry in
        the CRS of ``walls``.
    """
    parts, rows = shapely.get_parts(walls.geometry.to_numpy(), return_index=True)
    if len(parts) == 0:
        empty = gpd.GeoDataFrame(geometry=[], crs=walls.crs)
        empty.index.name = "gns_feature_id"
        return empty
    near = shapely.STRtree(parts).query(parts, predicate="dwithin", distance=snap_m)
    feature = _components(len(parts), [near.T.astype(np.int64)])
    first_row = pd.Series(rows).groupby(feature).min()
    order = first_row.sort_values(kind="mergesort").index.to_numpy()
    renumber = np.empty(len(order), dtype=np.int64)
    renumber[order] = np.arange(len(order))
    feature = renumber[feature]
    sort = np.argsort(feature, kind="mergesort")
    geometry = shapely.multilinestrings(parts[sort], indices=feature[sort])
    features = gpd.GeoDataFrame(geometry=geometry, crs=walls.crs)
    features.index.name = "gns_feature_id"
    return features


def gen_wall_members(
    sizs: gpd.GeoDataFrame, gns_only: gpd.GeoDataFrame, cut_fill: pd.DataFrame
) -> gpd.GeoDataFrame:
    """One row per candidate pif and per GNS-only piece, in one shape.

    Args:
        sizs: The siz table from landslide step 12 (pif_id index, the spine
            columns of
            :func:`~landloss.hazard.landslide.instability_zones.gen_pif_spines`,
            the evidence of
            :func:`~landloss.hazard.landslide.wall_candidates.wall_candidate_evidence`
            and the property columns of
            :func:`~landloss.hazard.landslide.wall_candidates.property_of_pifs`).
            Only the pifs whose ``candidate_class`` is in
            :data:`CANDIDATE_CLASSES` become members.
        gns_only: The GNS-only candidates
            (:func:`~landloss.hazard.landslide.wall_candidates.gen_gns_only_candidates`,
            gns_only_id index) with ``step_height_m``, the step the DEM shows
            across each piece.
        cut_fill: Landslide step 13 per pif, indexed by ``pif_id``, with
            :data:`CUT_FILL_COLUMNS`: ``cut_fill_class`` (one of
            :data:`~landloss.hazard.landslide.pif_cut_fill.CLASSES`). Every candidate
            pif must be in it.

    Returns:
        On a fresh index: ``member_type`` (:data:`PIF_MEMBER` or
        :data:`GNS_ONLY_MEMBER`), ``member_id`` (the pif_id or gns_only_id),
        ``property_id`` (the rateable property, by one rule for both: the
        non-road property holding most of the pif or line, ties to the lowest
        id, NA where none), ``length_m`` (the spine or the line),
        the end columns (a GNS-only piece's ends are its line's ends and its
        falls are NaN), ``max_delta_h_m`` (NaN for GNS-only), ``height_m``
        (the siz table's ``near_drop_p80_m``, or ``step_height_m`` for
        GNS-only),
        ``cut_fill_class`` (``unknown`` for GNS-only), ``building_m``,
        ``ground_group``, ``ground_material``, ``height_band`` (0 for
        GNS-only), ``in_slide_fill`` (False for GNS-only), ``gns_wall`` (True
        for GNS-only), ``is_siz``, and ``footprint`` (the pips or the line).
        The active geometry is the spine or the line.

    Raises:
        ValueError: If a frame is missing a column it needs, or a candidate
            pif has no row in ``cut_fill`` (step 13 predates the siz table).
    """
    _require(sizs, PIF_COLUMNS, "sizs")
    _require(gns_only, GNS_ONLY_COLUMNS, "gns_only")
    _require(cut_fill, CUT_FILL_COLUMNS, "cut_fill")
    crs = sizs.crs
    pifs = sizs[sizs["candidate_class"].isin(CANDIDATE_CLASSES)]
    absent = pifs.index.difference(cut_fill.index)
    if len(absent):
        msg = (
            f"{len(absent)} candidate pifs have no cut and fill class (first: "
            f"{absent[:5].tolist()}): rerun landslide step 13 on this siz table"
        )
        raise ValueError(msg)
    step13 = cut_fill.loc[pifs.index]
    spine = gpd.GeoSeries(pifs["spine"], crs=crs).to_numpy()
    pif_members = pd.DataFrame(
        {
            "member_type": PIF_MEMBER,
            "member_id": pifs.index.to_numpy(dtype=np.int64),
            "property_id": pifs["rateable_property_id"].astype(object).to_numpy(),
            "length_m": pifs["spine_length_m"].to_numpy(dtype=float),
            **{
                column: pifs[column].to_numpy(dtype=float)
                for column in (
                    "end_a_x",
                    "end_a_y",
                    "end_b_x",
                    "end_b_y",
                    "end_a_fall_deg",
                    "end_b_fall_deg",
                    "max_delta_h_m",
                )
            },
            "height_m": pifs["near_drop_p80_m"].to_numpy(dtype=float),
            "cut_fill_class": step13["cut_fill_class"].astype(object).to_numpy(),
            "building_m": pifs["building_m"].to_numpy(dtype=float),
            "ground_group": pifs["ground_group"].astype(object).to_numpy(),
            "ground_material": pifs["ground_material"].astype(object).to_numpy(),
            "height_band": pifs["height_band"].to_numpy(dtype=np.int64),
            "in_slide_fill": pifs["in_slide_fill"].to_numpy(dtype=bool),
            "gns_wall": pifs["gns_wall"].to_numpy(dtype=bool),
            "is_siz": pifs["is_siz"].to_numpy(dtype=bool),
            "geometry": spine,
            "footprint": pifs.geometry.to_numpy(),
        }
    )

    lines = gns_only.geometry.to_numpy()
    start = shapely.get_point(lines, 0)
    end = shapely.get_point(lines, -1)
    gns_members = pd.DataFrame(
        {
            "member_type": GNS_ONLY_MEMBER,
            "member_id": gns_only.index.to_numpy(dtype=np.int64),
            "property_id": gns_only["rateable_property_id"].astype(object).to_numpy(),
            "length_m": gns_only["length_m"].to_numpy(dtype=float),
            "end_a_x": shapely.get_x(start),
            "end_a_y": shapely.get_y(start),
            "end_b_x": shapely.get_x(end),
            "end_b_y": shapely.get_y(end),
            "end_a_fall_deg": np.nan,
            "end_b_fall_deg": np.nan,
            "max_delta_h_m": np.nan,
            "height_m": gns_only["step_height_m"].to_numpy(dtype=float),
            "cut_fill_class": pif_cut_fill.UNKNOWN,
            "building_m": gns_only["building_m"].to_numpy(dtype=float),
            "ground_group": None,
            "ground_material": gns_only["ground_material"].astype(object).to_numpy(),
            "height_band": 0,
            "in_slide_fill": False,
            "gns_wall": True,
            "is_siz": False,
            "geometry": lines,
            "footprint": lines,
        }
    )
    members = pd.concat([pif_members, gns_members], ignore_index=True)
    members["property_id"] = members["property_id"].astype("string")
    members["height_band"] = members["height_band"].astype(np.int64)
    for column in ("in_slide_fill", "gns_wall", "is_siz"):
        members[column] = members[column].astype(bool)
    members["footprint"] = gpd.GeoSeries(members["footprint"], crs=crs)
    return gpd.GeoDataFrame(members, geometry="geometry", crs=crs)


def _within_groups(
    groups: NDArray[np.int64], members: NDArray[np.int64]
) -> NDArray[np.int64]:
    """Edges joining the members that share a group, whatever their property."""
    if len(members) == 0:
        return np.zeros((0, 2), dtype=np.int64)
    frame = pd.DataFrame({"group": groups, "member": members})
    first = frame.groupby("group")["member"].transform("min")
    return np.column_stack([first.to_numpy(), members]).astype(np.int64)


def _end_edges(
    members: gpd.GeoDataFrame,
    *,
    join_gap_m: float,
    max_offset_m: float,
    bearing_tol_deg: float,
    corner_gap_m: float,
    corner_max_deg: float,
) -> NDArray[np.int64]:
    """Edges joining pif members end to end, whatever their property."""
    pif = np.flatnonzero(members["member_type"].to_numpy() == PIF_MEMBER)
    n = len(pif)
    if n < 2:
        return np.zeros((0, 2), dtype=np.int64)
    rows = members.iloc[pif]
    ends = np.stack(
        [
            rows[["end_a_x", "end_a_y"]].to_numpy(dtype=float),
            rows[["end_b_x", "end_b_y"]].to_numpy(dtype=float),
        ],
        axis=1,
    )
    falls = rows[["end_a_fall_deg", "end_b_fall_deg"]].to_numpy(dtype=float)
    pairs = cKDTree(ends.reshape(-1, 2)).query_pairs(
        max(join_gap_m, corner_gap_m), output_type="ndarray"
    )
    i, j = pairs[:, 0] // 2, pairs[:, 1] // 2
    keep = i != j
    pair = np.unique(np.sort(np.column_stack([i[keep], j[keep]]), axis=1), axis=0)
    if len(pair) == 0:
        return np.zeros((0, 2), dtype=np.int64)
    a, b = pair[:, 0], pair[:, 1]

    # The facing ends are the closest of the four pairs of ends.
    delta = ends[b][:, None, :, :] - ends[a][:, :, None, :]
    gaps = np.hypot(delta[..., 0], delta[..., 1]).reshape(len(pair), 4)
    best = np.argmin(gaps, axis=1)
    end_a, end_b = best // 2, best % 2
    gap = gaps[np.arange(len(pair)), best]
    dx, dy = delta[np.arange(len(pair)), end_a, end_b].T
    fall_a = falls[a, end_a]
    fall_b = falls[b, end_b]

    turn = np.abs((fall_a - fall_b + 180.0) % 360.0 - 180.0)
    rad_a, rad_b = np.radians(fall_a), np.radians(fall_b)
    mean = np.arctan2(np.sin(rad_a) + np.sin(rad_b), np.cos(rad_a) + np.cos(rad_b))
    offset = np.abs(dx * np.sin(mean) + dy * np.cos(mean))
    # A corner is where the falls turn: two faces falling the same way within
    # the corner gap are the straight case, which the offset limit keeps apart
    # when they are stacked down a slope.
    joined = (
        (gap <= join_gap_m) & (offset <= max_offset_m) & (turn <= bearing_tol_deg)
    ) | ((gap <= corner_gap_m) & (turn > bearing_tol_deg) & (turn <= corner_max_deg))
    return np.column_stack([pif[a[joined]], pif[b[joined]]]).astype(np.int64)


def _strike_angle_deg(
    lines: NDArray[np.object_], members: gpd.GeoDataFrame, pif_rows: NDArray[np.int64]
) -> NDArray[np.float64]:
    """The angle between each GNS-only line and the strike of a pif, in degrees.

    The line's bearing is its start to its end; the pif's strike is
    perpendicular to the fall at the end of its spine nearest the line
    (``end_a_fall_deg`` or ``end_b_fall_deg``), so an L-shaped pif is read
    along the leg the line is beside. Both are axes, so the angle is 0 to 90.
    NaN where the pif's fall there is unknown.
    """
    rows = members.iloc[pif_rows]
    start, end = shapely.get_point(lines, 0), shapely.get_point(lines, -1)
    bearing = np.degrees(
        np.arctan2(
            shapely.get_x(end) - shapely.get_x(start),
            shapely.get_y(end) - shapely.get_y(start),
        )
    )
    end_a = shapely.points(rows[["end_a_x", "end_a_y"]].to_numpy(dtype=float))
    end_b = shapely.points(rows[["end_b_x", "end_b_y"]].to_numpy(dtype=float))
    nearer_a = shapely.distance(lines, end_a) <= shapely.distance(lines, end_b)
    fall = np.where(
        nearer_a,
        rows["end_a_fall_deg"].to_numpy(dtype=float),
        rows["end_b_fall_deg"].to_numpy(dtype=float),
    )
    off_fall = np.abs((bearing - fall + 90.0) % 180.0 - 90.0)
    return 90.0 - off_fall


def gen_wall_units(
    members: gpd.GeoDataFrame,
    gns_features: gpd.GeoDataFrame,
    *,
    gns_match_m: float,
    join_gap_m: float,
    max_offset_m: float,
    bearing_tol_deg: float,
    corner_gap_m: float,
    corner_max_deg: float,
    gns_only_merge_m: float,
    gns_only_merge_max_angle_deg: float,
    max_bends: int,
    min_segment_m: float,
    stray_tolerance_m: float,
    max_length_m: float,
    max_turn_deg: float,
    properties: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """Join the members into wall units, across property boundaries.

    No rule looks at the property (the lead, 2026-10-06): a wall on a boundary
    is one unit, which carries its length in every property it enters
    (:func:`gen_unit_properties`). Three rules join the members, and a unit
    is everything joined directly or through others:

    - **GNS feature:** members whose footprint lies within ``gns_match_m`` of
      one GNS mapped wall feature are one unit; where GNS maps the wall it is
      the join.
    - **GNS-only merge:** a GNS-only piece within ``gns_only_merge_m`` of a
      pif's footprint joins it, so one wall is not counted twice, where it
      runs roughly along the pif's face: the angle between its bearing and
      the pif's strike at the spine end nearest it is at most
      ``gns_only_merge_max_angle_deg`` (a pif with no fall there joins
      whatever the direction). A piece across the face (on the pilot, an
      east-west mapped wall beside a north-south pif) is another wall.
    - **End to end, pifs only:** of the four pairs of ends of two pifs, the
      closest are the facing ends and their distance the gap. They join where
      the gap is within ``join_gap_m``, the ends are offset along their mean
      fall by no more than ``max_offset_m`` (so faces stacked down a slope do
      not join) and their falls differ by no more than ``bearing_tol_deg``; or
      at a corner, where the gap is within ``corner_gap_m`` and the falls turn
      by more than ``bearing_tol_deg`` and no more than ``corner_max_deg``.

    Args:
        members: From :func:`gen_wall_members`.
        gns_features: From :func:`gen_gns_wall_features`.
        gns_match_m: A member within this many metres of a feature is on it.
        join_gap_m: The largest gap between facing ends, in metres.
        max_offset_m: The largest offset of the ends along the fall, in metres.
        bearing_tol_deg: The largest difference in the facing ends' falls.
        corner_gap_m: The largest gap at a corner, in metres.
        corner_max_deg: The largest turn at a corner, in degrees; a corner
            turns by more than ``bearing_tol_deg``.
        gns_only_merge_m: A GNS-only piece this close to a pif joins it.
        gns_only_merge_max_angle_deg: The largest angle, in degrees, between
            a merging GNS-only piece and the pif's strike.
        max_bends: The most bends one wall's line has (:func:`gen_unit_lines`).
        min_segment_m: The shortest straight section of a wall's line.
        stray_tolerance_m: How far a wall's line may stray from the chained
            members it follows.
        max_length_m: The longest wall: a longer one is cut at its own bends,
            then at the property boundaries it crosses, then into equal
            pieces (the lead, 2026-10-06).
        max_turn_deg: The most a wall's line may turn in all.
        properties: LINZ property boundaries for the boundary cut; None cuts
            none.

    Raises:
        ValueError: If a unit's line breaks a rule (more than ``max_bends``
            bends, turning more than ``max_turn_deg``, shorter than
            ``min_segment_m``, longer than ``max_length_m``, more than one
            part); the rules hold by construction, so this is a bug.

    Returns:
        One row per unit, indexed by ``wall_unit_id`` (minted by location
        behind :data:`~landloss.domain.constants.WALL_UNIT_ID_PREFIX`), with
        ``member_pif_ids`` and ``member_gns_only_ids`` (sorted lists),
        ``n_pifs``, ``n_gns_only``, ``unit_source`` (``pif`` where any member
        is a pif, else ``gns_only``), ``is_siz`` and ``gns_wall`` (any member),
        ``property_id`` (provisional: the longest member's with one; set by
        :func:`gen_unit_properties`), ``in_exposure`` (it has a property),
        ``max_delta_h_m`` (the highest pif, for reference), ``height_m`` (the
        highest member's: a pif's ``wall_height_m``, a GNS-only piece's
        ``step_height_m``), ``building_m`` (the nearest), ``length_m`` (of
        the unit's simplified line), ``length_original_m`` (the members'
        summed length), ``n_bends``, :data:`LONGEST_MEMBER_COLUMNS` from the
        longest member (ties to the lowest member type and id),
        ``cut_fill_class`` (see :func:`_unit_cut_fill_class`), ``x`` and ``y``
        (a representative point) and the simplified LineString
        (:func:`gen_unit_line`).
    """
    crs = members.crs
    n = len(members)
    footprints = gpd.GeoSeries(members["footprint"], crs=crs).to_numpy()
    edges = []

    if n and len(gns_features):
        near = shapely.STRtree(footprints).query(
            gns_features.geometry.to_numpy(), predicate="dwithin", distance=gns_match_m
        )
        edges.append(_within_groups(near[0], near[1]))

    is_pif = members["member_type"].to_numpy() == PIF_MEMBER
    gns_rows = np.flatnonzero(~is_pif)
    pif_rows = np.flatnonzero(is_pif)
    if len(gns_rows) and len(pif_rows):
        near = shapely.STRtree(footprints[pif_rows]).query(
            footprints[gns_rows], predicate="dwithin", distance=gns_only_merge_m
        )
        pairs = np.column_stack([gns_rows[near[0]], pif_rows[near[1]]])
        angle = _strike_angle_deg(footprints[pairs[:, 0]], members, pairs[:, 1])
        along = ~(angle > gns_only_merge_max_angle_deg)
        edges.append(pairs[along].astype(np.int64))

    edges.append(
        _end_edges(
            members,
            join_gap_m=join_gap_m,
            max_offset_m=max_offset_m,
            bearing_tol_deg=bearing_tol_deg,
            corner_gap_m=corner_gap_m,
            corner_max_deg=corner_max_deg,
        )
    )
    frame = pd.DataFrame(members.drop(columns=["geometry", "footprint"]))
    joined = _components(n, edges) if n else np.zeros(0, dtype=np.int64)
    frame["unit"], lines, dropped_m = _split_into_walls(
        joined,
        members.geometry.to_numpy(),
        footprints,
        max_bends=max_bends,
        min_segment_m=min_segment_m,
        stray_tolerance_m=stray_tolerance_m,
        max_length_m=max_length_m,
        max_turn_deg=max_turn_deg,
        boundaries=None if properties is None else _property_frame(properties),
        counts=(counts := Counter()),
    )
    breaks = {
        label: broken
        for label, line in lines.items()
        if (
            broken := bend_split.rule_breaks(
                line,
                max_bends=max_bends,
                min_length_m=min_segment_m,
                max_length_m=max_length_m,
                max_turn_deg=max_turn_deg,
            )
        )
    }
    if breaks:
        msg = (
            f"{len(breaks)} wall units break the line rules: {list(breaks.items())[:5]}"
        )
        raise ValueError(msg)
    units = _unit_rows(frame, lines, crs=crs)
    units.attrs["dropped_wall_m"] = dropped_m
    units.attrs["cap_cuts"] = dict(counts)
    return units


def _split_into_walls(
    joined: NDArray[np.int64],
    geometries: NDArray[np.object_],
    footprints: NDArray[np.object_],
    **settings: object,
) -> tuple[NDArray[np.int64], dict[int, shapely.LineString], float]:
    """Cut each group of joined members into walls, and give each member one.

    The walls of a group are :func:`gen_unit_lines` on its members. Each
    member goes to the wall nearest most of its points (a pif's pips, a
    GNS-only line walked every half metre), ties to the first wall, so a pif
    straddling a cut goes to the wall holding most of its pips and every
    member is in exactly one unit; each wall with a member is a unit. A wall
    no member is nearest (a stretch a member only partly covers) joins the
    unit of the member nearest most of its points where the two run on end to
    end and the joined line still keeps every rule
    (:func:`~landloss.hazard.landslide.bend_split.rule_breaks`); otherwise it
    is dropped. A unit is never more than one line (the lead, 2026-10-06).

    Returns:
        ``(unit, lines, dropped_m)``: the unit of each member, numbered from
        0, the line of each unit, and the length of the walls dropped.
    """
    rules = {
        "max_bends": int(settings["max_bends"]),
        "min_length_m": float(settings["min_segment_m"]),
        "max_length_m": float(settings["max_length_m"]),
        "max_turn_deg": float(settings["max_turn_deg"]),
    }
    unit = np.zeros(len(joined), dtype=np.int64)
    lines: dict[int, shapely.LineString] = {}
    dropped_m = 0.0
    rows_of = pd.Series(np.arange(len(joined))).groupby(joined).indices
    for group in sorted(rows_of):
        rows = rows_of[group]
        walls = gen_unit_lines(list(geometries[rows]), **settings)
        if len(walls) == 1:
            owner = np.zeros(len(rows), dtype=np.int64)
        else:
            owner = np.array(
                [_nearest_wall(footprints[row], walls) for row in rows], dtype=np.int64
            )
        kept = {int(wall): walls[wall] for wall in np.unique(owner)}
        for wall in sorted(set(range(len(walls))) - set(kept)):
            member = _nearest_member(walls[wall], footprints[rows])
            target = int(owner[member])
            merged = shapely.line_merge(
                shapely.MultiLineString([kept[target], walls[wall]])
            )
            if merged.geom_type == "LineString":
                merged = shapely.simplify(merged, 1e-6, preserve_topology=False)
            if not bend_split.rule_breaks(merged, **rules):
                kept[target] = merged
            else:
                dropped_m += walls[wall].length
        for wall, line in kept.items():
            label = len(lines)
            lines[label] = line
            unit[rows[owner == wall]] = label
    return unit, lines, dropped_m


def _nearest_member(wall: shapely.LineString, footprints: NDArray[np.object_]) -> int:
    """The member nearest most of a wall's points."""
    points = shapely.points(shapely.get_coordinates(shapely.segmentize(wall, 1.0)))
    distance = shapely.distance(points[:, None], footprints[None, :])
    return int(np.bincount(distance.argmin(axis=1), minlength=len(footprints)).argmax())


def _nearest_wall(footprint: object, walls: list[shapely.LineString]) -> int:
    """The wall nearest most of a member's points."""
    points = shapely.points(
        shapely.get_coordinates(shapely.segmentize(footprint, _LINE_SPACING_M))
    )
    distance = shapely.distance(points[:, None], np.asarray(walls, dtype=object)[None])
    return int(np.bincount(distance.argmin(axis=1), minlength=len(walls)).argmax())


def _chains(lines: list[object], *, min_branch_m: float) -> list[NDArray[np.float64]]:
    """The members of one group as paths of points, end to end.

    The members are walked as points no more than :data:`_LINE_SPACING_M`
    apart and joined by their minimum spanning tree. The first path is the
    tree's longest (a double sweep), so its ends are the group's two far ends
    and a gap between two members is crossed by the shortest jump. Where the
    tree branches (a T in a mapped wall, a pif beside the main run), each
    branch left off it is a path of its own from where it joins, the longest
    first, as long as it is at least ``min_branch_m``; so no member is left
    far from every path.
    """
    total = float(np.sum(shapely.length(np.asarray(lines, dtype=object))))
    spacing = max(_LINE_SPACING_M, total / _MAX_LINE_POINTS)
    xy = shapely.get_coordinates(
        shapely.segmentize(np.asarray(lines, dtype=object), spacing)
    )
    xy = np.unique(xy, axis=0)
    if len(xy) < 2:
        return [np.repeat(xy, 2, axis=0)]
    # The small offset keeps two coincident points joined: a zero is no edge.
    tree = minimum_spanning_tree(squareform(pdist(xy)) + 1e-9)
    return tree_paths(tree + tree.T, xy, min_branch_m=min_branch_m)


def _boundary_positions(
    line: shapely.LineString, boundaries: gpd.GeoDataFrame, min_segment_m: float
) -> list[float]:
    """Where a line crosses property boundaries, one stretch per property.

    The line is cut at every crossing; consecutive stretches in the same
    property (the one holding each stretch's midpoint) are one, so a wall
    weaving along a boundary is not cut at every weave; and a stretch
    shorter than ``min_segment_m`` joins the one before it (or after it, for
    the first).

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


def gen_unit_lines(
    lines: list[object],
    *,
    max_bends: int,
    min_segment_m: float,
    stray_tolerance_m: float,
    max_length_m: float = np.inf,
    max_turn_deg: float = np.inf,
    boundaries: gpd.GeoDataFrame | None = None,
    counts: Counter | None = None,
) -> list[shapely.LineString]:
    """The walls one group of joined members makes, each a line within the rules.

    The members (pif spines, GNS-only lines) are chained end to end into
    paths, the longest first and then each branch off it (:func:`_chains`),
    and each path is cut by the rule the pifs are cut by
    (:func:`landloss.hazard.landslide.bend_split.cut_path`, the lead,
    2026-10-06): a wall runs as far as Douglas-Peucker at
    ``stray_tolerance_m`` follows the path with at most ``max_bends`` bends
    turning no more than ``max_turn_deg`` in all; a wall whose ends are under
    ``min_segment_m`` apart joins a neighbour; and a wall whose line is over
    ``max_length_m`` is cut at its own bends, then (with no bend left) where
    it crosses the boundaries of ``boundaries`` (LINZ properties, road
    parcels included; :func:`_boundary_positions`), then into equal pieces.
    Each wall's line is its stretch's
    (:func:`~landloss.hazard.landslide.bend_split.canonical_line`), so every
    wall keeps every rule.

    Args:
        lines: The group's member geometries.
        max_bends: The most bends one wall's line has.
        min_segment_m: The shortest straight section, and the least distance
            between a wall's ends.
        stray_tolerance_m: How far a wall's line may stray from the path.
        max_length_m: The longest wall.
        max_turn_deg: The most a wall's line may turn in all.
        boundaries: The property polygons with ``property_id``; None skips the
            boundary stage of the length cap.
        counts: Counts the walls the length cap cut, by stage.

    Returns:
        The walls, in order along the paths.
    """
    walls: list[shapely.LineString] = []
    paths = _chains(lines, min_branch_m=min_segment_m)
    boundary_cuts = (
        None
        if boundaries is None
        else (lambda line: _boundary_positions(line, boundaries, min_segment_m))
    )
    for k, path in enumerate(paths):
        if k > 0 and np.hypot(*(path[-1] - path[0])) < min_segment_m:
            continue
        for start, end in cut_path(
            path,
            max_bends=max_bends,
            tolerance_m=stray_tolerance_m,
            min_segment_m=min_segment_m,
            max_length_m=max_length_m,
            max_turn_deg=max_turn_deg,
            boundary_cuts=boundary_cuts,
            counts=counts,
        ):
            walls.append(
                shapely.LineString(
                    bend_split.canonical_line(
                        path[start : end + 1],
                        tolerance_m=stray_tolerance_m,
                        max_bends=max_bends,
                        min_segment_m=min_segment_m,
                        max_turn_deg=max_turn_deg,
                    )
                )
            )
    return walls


def gen_unit_properties(
    units: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    *,
    min_length_m: float = BETA_MIN_WALL_LENGTH_IN_PROPERTY_M,
) -> pd.DataFrame:
    """The properties each wall unit's line enters, and its primary one.

    A unit is a wall on every property its line enters by at least
    ``min_length_m`` (the lead, 2026-10-06), with the length inside it. The
    primary property, for what is done once per unit (the claim, the exposure
    draw), is the rule the pifs and GNS-only pieces use: the non-road
    property holding the longest part, ties to the lowest id, NA where the
    line is on no non-road property. Stacked unit titles count once, as
    :func:`~landloss.exposure.land.extent.stack_representatives` picks.

    Args:
        units: From :func:`gen_wall_units`.
        properties: LINZ property boundaries
            (:func:`landloss.io.readers.get_nz_property_boundaries`), in the
            CRS of ``units``.
        min_length_m: The least length inside a property for it to count.

    Returns:
        A frame indexed like ``units`` with ``property_id`` (the primary),
        ``in_exposure`` (it has one), ``property_lengths_m`` (a list of
        ``{"property_id": str, "length_m": float}``, longest first, of the
        non-road properties the line enters by at least ``min_length_m``, the
        primary always included) and ``n_properties`` (its length).
    """
    frame = _property_frame(properties).reset_index(drop=True)
    lines = gpd.GeoDataFrame(geometry=units.geometry.to_numpy(), crs=units.crs)
    joined = gpd.sjoin(lines, frame[["geometry"]], how="inner")
    rows = joined["index_right"].to_numpy()
    overlap = pd.DataFrame(
        {
            "unit": joined.index.to_numpy(),
            "property_id": frame["property_id"].to_numpy()[rows],
            "is_road": frame["property_is_road"].to_numpy(dtype=bool)[rows],
            "length_m": shapely.length(
                shapely.intersection(
                    joined.geometry.to_numpy(), frame.geometry.to_numpy()[rows]
                )
            ),
        }
    )
    overlap = overlap[~overlap["is_road"] & (overlap["length_m"] > 0)]
    overlap = overlap.sort_values(
        ["unit", "length_m", "property_id"],
        ascending=[True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    first = ~overlap["unit"].duplicated()
    primary = overlap.loc[first].set_index("unit")["property_id"]
    counted = overlap[first | (overlap["length_m"] >= min_length_m)]
    lengths = {
        unit: [
            {"property_id": str(pid), "length_m": float(length)}
            for pid, length in zip(group["property_id"], group["length_m"], strict=True)
        ]
        for unit, group in counted.groupby("unit", sort=False)
    }
    n = len(units)
    property_id = primary.reindex(range(n)).astype("string").to_numpy()
    lists = [lengths.get(i, []) for i in range(n)]
    out = pd.DataFrame(
        {
            "property_id": pd.array(property_id, dtype="string"),
            "n_properties": np.array([len(x) for x in lists], dtype=np.int64),
        },
        index=units.index,
    )
    out["in_exposure"] = out["property_id"].notna().to_numpy(dtype=bool)
    out["property_lengths_m"] = pd.Series(lists, index=units.index, dtype=object)
    return out[["property_id", "in_exposure", "property_lengths_m", "n_properties"]]


def gen_unit_boundary_flags(
    units: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    *,
    distance_m: float = constants.BETA_WALL_BOUNDARY_DISTANCE_M,
) -> pd.DataFrame:
    """Whether each unit lies mostly along a property boundary or a road.

    A unit is on a property boundary where at least half its line lies within
    ``distance_m`` of the boundary of a non-road property, and on a road
    frontage where at least half lies within it of the boundary of a road
    parcel (both can hold; the prior takes the road frontage).

    Args:
        units: The wall units with their lines.
        properties: LINZ property boundaries, in the CRS of ``units``.
        distance_m: How near the boundary the line must lie.

    Returns:
        A frame indexed like ``units`` with ``boundary_share`` and
        ``road_frontage_share`` (the share of the line within ``distance_m``)
        and ``on_property_boundary`` and ``on_road_frontage``.
    """
    frame = _property_frame(properties).reset_index(drop=True)
    lines = units.geometry.to_numpy()
    length = shapely.length(lines)
    out = {}
    for name, polygons in (
        ("boundary_share", frame.geometry.to_numpy()[~frame["property_is_road"]]),
        ("road_frontage_share", frame.geometry.to_numpy()[frame["property_is_road"]]),
    ):
        share = np.zeros(len(units))
        if len(polygons) and len(lines):
            edges = shapely.boundary(polygons)
            line_of, edge_of = shapely.STRtree(edges).query(
                lines, predicate="dwithin", distance=distance_m
            )
            for i in np.unique(line_of):
                band = shapely.buffer(
                    shapely.union_all(edges[edge_of[line_of == i]]), distance_m
                )
                share[i] = shapely.length(shapely.intersection(lines[i], band)) / max(
                    length[i], 1e-9
                )
        out[name] = share
    result = pd.DataFrame(out, index=units.index)
    result["on_property_boundary"] = result["boundary_share"] >= 0.5
    result["on_road_frontage"] = result["road_frontage_share"] >= 0.5
    return result


def _unit_rows(
    frame: pd.DataFrame, unit_lines: dict[int, shapely.LineString], *, crs: object
) -> gpd.GeoDataFrame:
    """Collapse the members, each carrying its ``unit``, to one row per unit."""
    is_pif = frame["member_type"] == PIF_MEMBER
    grouped = frame.groupby("unit", sort=True)
    units = pd.DataFrame(index=grouped.size().index)

    def _ids(mask: pd.Series) -> pd.Series:
        lists = {
            unit: sorted(int(i) for i in group)
            for unit, group in frame.loc[mask, "member_id"].groupby(frame["unit"])
        }
        return pd.Series(
            [lists.get(unit, []) for unit in units.index],
            index=units.index,
            dtype=object,
        )

    units["member_pif_ids"] = _ids(is_pif)
    units["member_gns_only_ids"] = _ids(~is_pif)
    units["n_pifs"] = units["member_pif_ids"].map(len).astype(np.int64)
    units["n_gns_only"] = units["member_gns_only_ids"].map(len).astype(np.int64)
    units["unit_source"] = np.where(units["n_pifs"] > 0, PIF_MEMBER, GNS_ONLY_MEMBER)
    units["is_siz"] = grouped["is_siz"].any()
    units["gns_wall"] = grouped["gns_wall"].any()
    by_length = frame.sort_values(
        ["unit", "length_m", "member_type", "member_id"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    units["property_id"] = (
        by_length.dropna(subset=["property_id"])
        .drop_duplicates("unit")
        .set_index("unit")["property_id"]
        .reindex(units.index)
        .astype("string")
    )
    units["in_exposure"] = units["property_id"].notna()
    units["max_delta_h_m"] = grouped["max_delta_h_m"].max()
    units["height_m"] = grouped["height_m"].max()
    units["building_m"] = grouped["building_m"].min()
    units["length_m"] = grouped["length_m"].sum()

    longest = frame.sort_values(
        ["unit", "length_m", "member_type", "member_id"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).drop_duplicates("unit")
    for column in LONGEST_MEMBER_COLUMNS:
        units[column] = longest.set_index("unit")[column].reindex(units.index)
    units["cut_fill_class"] = _unit_cut_fill_class(frame[is_pif]).reindex(units.index)
    units["cut_fill_class"] = units["cut_fill_class"].where(
        units["cut_fill_class"].notna(), pif_cut_fill.UNKNOWN
    )

    lines = [unit_lines[u] for u in units.index]
    geometry = np.array(lines, dtype=object) if lines else np.array([], dtype=object)
    # The members' summed length; a member's whole length counts in the unit
    # it went to, so a split group's units share it out by member.
    units["length_original_m"] = units["length_m"]
    units["length_m"] = shapely.length(geometry) if lines else np.zeros(0)
    units["n_bends"] = np.array(
        [len(line.coords) - 2 for line in lines], dtype=np.int64
    )
    units = gpd.GeoDataFrame(units.reset_index(drop=True), geometry=geometry, crs=crs)
    points = units.geometry.representative_point()
    units["x"] = points.x.to_numpy()
    units["y"] = points.y.to_numpy()

    units = sort_by_point(units)
    units.index = pd.Index(
        mint_ids(constants.WALL_UNIT_ID_PREFIX, len(units)).to_numpy(),
        name="wall_unit_id",
    )
    return units


def _unit_cut_fill_class(pifs: pd.DataFrame) -> pd.Series:
    """The cut and fill class of each unit, from its pif members.

    A unit takes the class of its longest pif. Where several pifs tie for the
    longest, it takes the tied class held by most of the unit's pifs, and
    then the class of the tied pif with the lowest id. A unit with no pif has
    no entry (the caller reads it as ``unknown``).

    Args:
        pifs: The pif members with ``unit``, ``member_id``, ``length_m`` and
            ``cut_fill_class``.

    Returns:
        The class per unit that has a pif, indexed by ``unit``.
    """
    longest = pifs.groupby("unit")["length_m"].transform("max")
    tied = pifs.loc[
        pifs["length_m"] == longest, ["unit", "member_id", "cut_fill_class"]
    ]
    held = pifs.groupby(["unit", "cut_fill_class"]).size().rename("n_held")
    tied = tied.join(held, on=["unit", "cut_fill_class"])
    chosen = tied.sort_values(
        ["unit", "n_held", "member_id"], ascending=[True, False, True], kind="mergesort"
    ).drop_duplicates("unit")
    return chosen.set_index("unit")["cut_fill_class"].astype(object)


def tall_face_factor(height_m: ArrayLike) -> NDArray[np.float64]:
    """What a unit's prior keeps for the height of its face.

    1 up to :data:`~landloss.domain.constants.BETA_TALL_FACE_TAPER_START_M`,
    falling linearly to
    :data:`~landloss.domain.constants.BETA_TALL_FACE_MIN_FACTOR` at
    :data:`~landloss.domain.constants.BETA_TALL_FACE_TAPER_END_M` and that
    above: a face too high to be retained in full is less often a wall. An
    unknown height keeps 1.
    """
    height = np.nan_to_num(np.asarray(height_m, dtype=float), nan=0.0)
    return np.interp(
        height,
        [constants.BETA_TALL_FACE_TAPER_START_M, constants.BETA_TALL_FACE_TAPER_END_M],
        [1.0, constants.BETA_TALL_FACE_MIN_FACTOR],
    )


def gen_wall_prior(units: pd.DataFrame) -> pd.DataFrame:
    """The prior probability that each wall unit is a wall.

    Applied in this order: :data:`~landloss.domain.constants.BETA_SIZ_WALL_PRIOR`
    for a unit holding a siz, else
    :data:`~landloss.domain.constants.BETA_SMALL_WALL_PRIOR`; times the factor
    (:data:`~landloss.domain.constants.BETA_WALL_PRIOR_HEIGHT_BAND_FACTOR`)
    of the height band of the unit's ``height_m``
    (:func:`~landloss.hazard.landslide.slope_elements.height_band`, 0 for
    NaN), so the wall height sets the band; the unit's ``height_band``, the
    hazard's band of its longest pif, is not read;
    then by the unit's landslide step 13 ``cut_fill_class``, one factor at
    most since the classes exclude each other (and then by its setting,
    below):

    - ``cut`` on a rock material, with a height over
      :data:`~landloss.domain.constants.BETA_ROCK_CUT_MIN_HEIGHT_M` (under it
      the face is in the soil cover), times
      :data:`~landloss.domain.constants.BETA_ROCK_CUT_FACTOR`; a cut in soil,
      or in rock under that height, is unchanged;
    - ``fill`` and ``cut_and_fill`` (:data:`FILL_CLASSES`) times
      :data:`~landloss.domain.constants.BETA_FILL_WALL_FACTOR`;
    - ``natural`` times
      :data:`~landloss.domain.constants.BETA_NATURAL_WALL_FACTOR`;
    - ``uncertain`` and ``unknown`` unchanged;

    then, where the units carry the flags of :func:`gen_unit_boundary_flags`,
    times :data:`~landloss.domain.constants.BETA_ROAD_FRONTAGE_WALL_FACTOR`
    on a road frontage, else
    :data:`~landloss.domain.constants.BETA_BOUNDARY_WALL_FACTOR` on a
    property boundary (the lead, 2026-10-06); and last by
    :func:`tall_face_factor` of ``height_m``, which falls away once a face is
    too high to be retained in full (the lead, 2026-10-06).

    The prior is clipped to [0, 1]. The GNS floor and the claim update apply
    on top (:func:`gen_gns_floor`), so a mapped wall stays at the floor. The
    basis is the rule that applied last. A GNS-only unit has no prior: its
    probability is set by the floor.

    Args:
        units: From :func:`gen_wall_units`, with ``unit_source``, ``is_siz``,
            ``height_m``, ``ground_material`` and ``cut_fill_class``.

    Returns:
        A frame indexed like ``units`` with ``p_prior`` (NaN for a GNS-only
        unit), ``p_prior_basis``, ``prior_height_band`` (the band of
        ``height_m``), ``is_rock_cut``, ``is_fill``, ``is_natural``,
        ``is_property_boundary``, ``is_road_frontage`` (False where the flags
        are not carried) and ``tall_face_factor`` (computed for every
        unit).
    """
    _require(
        units,
        (
            "unit_source",
            "is_siz",
            "height_m",
            "ground_material",
            "cut_fill_class",
        ),
        "units",
    )
    cut_fill = units["cut_fill_class"]
    rock = (
        (cut_fill == pif_cut_fill.CUT)
        & units["ground_material"].isin(ROCK_MATERIALS)
        & (
            units["height_m"].to_numpy(dtype=float)
            > constants.BETA_ROCK_CUT_MIN_HEIGHT_M
        )
    ).to_numpy(dtype=bool)
    fill = cut_fill.isin(FILL_CLASSES).to_numpy(dtype=bool)
    natural = (cut_fill == pif_cut_fill.NATURAL).to_numpy(dtype=bool)

    prior = np.where(
        units["is_siz"].to_numpy(dtype=bool),
        constants.BETA_SIZ_WALL_PRIOR,
        constants.BETA_SMALL_WALL_PRIOR,
    )
    prior_band = height_band(units["height_m"].to_numpy(dtype=float))
    prior = prior * np.array(
        [
            constants.BETA_WALL_PRIOR_HEIGHT_BAND_FACTOR.get(int(b), 1.0)
            for b in prior_band
        ],
        dtype=float,
    )
    basis = np.full(len(units), PRIOR, dtype=object)
    for applies, factor, rule in (
        (rock, constants.BETA_ROCK_CUT_FACTOR, ROCK_CUT),
        (fill, constants.BETA_FILL_WALL_FACTOR, FILL),
        (natural, constants.BETA_NATURAL_WALL_FACTOR, NATURAL),
    ):
        prior = np.where(applies, prior * factor, prior)
        basis[applies] = rule
    road = (
        units["on_road_frontage"].to_numpy(dtype=bool)
        if "on_road_frontage" in units.columns
        else np.zeros(len(units), dtype=bool)
    )
    boundary = (
        units["on_property_boundary"].to_numpy(dtype=bool)
        if "on_property_boundary" in units.columns
        else np.zeros(len(units), dtype=bool)
    ) & ~road
    for applies, factor, rule in (
        (road, constants.BETA_ROAD_FRONTAGE_WALL_FACTOR, ROAD_FRONTAGE),
        (boundary, constants.BETA_BOUNDARY_WALL_FACTOR, PROPERTY_BOUNDARY),
    ):
        prior = np.where(applies, prior * factor, prior)
        basis[applies] = rule
    tall = tall_face_factor(units["height_m"].to_numpy(dtype=float))
    prior = prior * tall
    basis[tall < 1.0] = TALL_FACE
    prior = np.clip(prior, 0.0, 1.0)

    gns_only = units["unit_source"].to_numpy() == GNS_ONLY_MEMBER
    prior[gns_only] = np.nan
    basis[gns_only] = GNS_ONLY
    return pd.DataFrame(
        {
            "p_prior": prior,
            "p_prior_basis": basis,
            "prior_height_band": prior_band.astype(np.int64),
            "is_rock_cut": rock,
            "is_fill": fill,
            "is_natural": natural,
            "is_property_boundary": boundary,
            "is_road_frontage": road,
            "tall_face_factor": tall,
        },
        index=units.index,
    )


def gen_gns_floor(units: pd.DataFrame, prior: pd.DataFrame) -> pd.DataFrame:
    """Lift each wall unit with a GNS mapped wall on it to the floor.

    A GNS-only unit is set at
    :data:`~landloss.domain.constants.BETA_GNS_ONLY_WALL_PROBABILITY`; a unit
    with a mapped wall on any member is at least
    :data:`~landloss.domain.constants.BETA_GNS_WALL_UNIT_FLOOR`, so a GNS-only
    piece that joined a pif unit takes the floor from the join; any other unit
    keeps its prior.

    Args:
        units: From :func:`gen_wall_units`.
        prior: From :func:`gen_wall_prior`, indexed like ``units``.

    Returns:
        A frame indexed like ``units`` with ``p_floor`` and ``p_floor_basis``
        (``gns_only``, ``gns_floor`` where the floor raised it, else the
        prior's basis).
    """
    p = prior["p_prior"].to_numpy(dtype=float).copy()
    basis = prior["p_prior_basis"].to_numpy(dtype=object).copy()
    gns_only = units["unit_source"].to_numpy() == GNS_ONLY_MEMBER
    mapped = units["gns_wall"].to_numpy(dtype=bool) & ~gns_only
    lifted = np.maximum(p, constants.BETA_GNS_WALL_UNIT_FLOOR)
    raised = mapped & (lifted > p)
    p = np.where(mapped, lifted, p)
    basis[raised] = GNS_FLOOR
    p[gns_only] = constants.BETA_GNS_ONLY_WALL_PROBABILITY
    basis[gns_only] = GNS_ONLY
    return pd.DataFrame({"p_floor": p, "p_floor_basis": basis}, index=units.index)


def poisson_binomial_pmf(p: ArrayLike) -> NDArray[np.float64]:
    """The distribution of the number of successes of independent trials.

    Args:
        p: The success probability of each trial.

    Returns:
        ``pmf[k]``, the probability of exactly ``k`` successes, for ``k`` from
        0 to the number of trials; ``[1.0]`` for no trials.
    """
    pmf = np.ones(1)
    for q in np.asarray(p, dtype=float):
        pmf = np.r_[pmf * (1.0 - q), 0.0] + np.r_[0.0, pmf * q]
    return pmf


def gen_count_update(p: ArrayLike, n_walls: int) -> tuple[NDArray[np.float64], int]:
    """Update one property's wall units on a count of at least ``n_walls``.

    Each unit's probability becomes ``P(wall | at least n walls) = p_i x
    P(at least n - 1 of the others) / P(at least n of all)``, each from the
    Poisson-binomial over the current probabilities. Conditioning on "at least"
    a count never lowers a probability, so the result is clipped to
    ``[p_i, 1]`` against rounding. A count of 0 or less changes nothing. Where
    the units that can be walls (``p > 0``) are no more than the count, each
    goes to 1 and the rest of the count is reported missing rather than hidden.

    Args:
        p: The current probability of each unit on the property.
        n_walls: The number of walls the property is known to have at least.

    Returns:
        ``(updated, missing)``: the updated probabilities, and the walls the
        units cannot hold.
    """
    p = np.asarray(p, dtype=float)
    if n_walls <= 0:
        return p.copy(), 0
    possible = p > 0
    k_eff = int(possible.sum())
    if k_eff <= n_walls:
        return np.where(possible, 1.0, p), n_walls - k_eff
    at_least = poisson_binomial_pmf(p)[n_walls:].sum()
    updated = p.copy()
    for i in np.flatnonzero(possible):
        others = poisson_binomial_pmf(np.delete(p, i))[n_walls - 1 :].sum()
        updated[i] = p[i] * others / at_least
    return np.clip(updated, p, 1.0), 0


def gen_claim_holdout(property_ids: ArrayLike, *, share: float, seed: int) -> pd.Series:
    """Hold out a seeded share of the claimed properties from the update.

    Args:
        property_ids: The claimed properties, in any order, repeats allowed.
        share: The fraction to hold out.
        seed: The generator seed.

    Returns:
        A bool per unique property id (sorted), True where held out; the first
        ``round(share x n)`` of a seeded permutation.
    """
    ids = np.array(sorted(set(pd.Series(property_ids).astype(str))), dtype=object)
    order = np.random.default_rng(seed).permutation(len(ids))
    held_out = np.zeros(len(ids), dtype=bool)
    held_out[order[: round(share * len(ids))]] = True
    return pd.Series(held_out, index=pd.Index(ids, name="property_id"))


def gen_property_wall_records(
    properties: gpd.GeoDataFrame, records: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Read the claim and NZMM wall records onto the LINZ property polygons.

    The record layer has no property id and its polygons overlap (one point can
    fall in up to 202), so each LINZ polygon takes the smallest record polygon
    that contains its representative point. Stacked unit titles (identical
    geometry) are one piece of ground with one record: only the title
    :func:`~landloss.exposure.land.extent.stack_representatives` picks takes
    it, the one
    :func:`~landloss.hazard.landslide.wall_candidates.property_of_pifs` gives
    the stack's pifs, so a claim is not counted once per title and lands on
    the title its candidates are on.

    Args:
        properties: LINZ property boundaries with ``source_id``.
        records: The claim and NZMM layer
            (``scripts.landloss.exposure.rw.validations.config.PROPERTIES_PATH``)
            with ``claim_walls`` (NaN where no report), ``nhc_wall`` (NZMM
            ``has_retaining_wall``, nullable), ``ta`` and, where present,
            :data:`OPTIONAL_RECORD_COLUMNS`, in the CRS of ``properties``.

    Returns:
        One row per LINZ property that falls in a record, indexed by
        ``property_id`` (the ``source_id`` as a string), with ``claim_walls``
        (Int64, NA where no report), ``nzmm_wall`` (bool, NA read as False),
        ``ta`` and :data:`OPTIONAL_RECORD_COLUMNS` (where the layer has them).
    """
    _require(records, ("claim_walls", "nhc_wall", "ta"), "records")
    columns = ["claim_walls", "nhc_wall", "ta"] + [
        column for column in OPTIONAL_RECORD_COLUMNS if column in records.columns
    ]
    properties = properties.reset_index(drop=True)
    stack = stack_representatives(properties)
    first = properties[stack.to_numpy() == properties.index.to_numpy()]
    points = gpd.GeoDataFrame(
        {"property_id": first["source_id"].astype(str).to_numpy()},
        geometry=first.geometry.representative_point().to_numpy(),
        crs=properties.crs,
    )
    frame = records[[*columns, "geometry"]].reset_index(drop=True)
    frame["record_area_m2"] = frame.geometry.area
    joined = gpd.sjoin(points, frame, predicate="within", how="inner")
    joined = joined.sort_values(
        ["property_id", "record_area_m2", "index_right"], kind="mergesort"
    ).drop_duplicates("property_id")
    result = joined.set_index("property_id")[columns].copy()
    walls = result["claim_walls"].to_numpy(dtype=float, na_value=np.nan)
    result["claim_walls"] = pd.array(
        [pd.NA if np.isnan(w) else round(w) for w in walls], dtype="Int64"
    )
    result["nzmm_wall"] = (
        result.pop("nhc_wall").astype("boolean").fillna(value=False).astype(bool)
    )
    return result[["claim_walls", "nzmm_wall", *columns[2:]]]


def gen_wall_unit_probability(
    units: pd.DataFrame,
    p_floor: pd.DataFrame,
    *,
    records: pd.DataFrame,
    held_out: pd.Series,
    nzmm_min_walls: int,
    nzmm_weight: float,
    use_nzmm: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Update every property's wall units on the claim and NZMM counts.

    A claim report listing at least one wall, on a property not held out, is
    the count for :func:`gen_count_update`; NZMM ``has_retaining_wall`` true
    stands for ``nzmm_min_walls``. ``p_claims`` updates on the claims alone.
    ``p_claims_nzmm`` updates on the larger of the two counts, but NZMM is
    unreliable, so where its count is the larger the update is applied
    modestly: ``p_claims + nzmm_weight x (p_full - p_claims)``, with ``p_full``
    the full update on the NZMM count. ``p_wall`` is ``p_claims_nzmm`` where
    ``use_nzmm``, else ``p_claims``. A unit with no property is never updated.

    A unit is a wall on every property in its ``property_lengths_m`` (where
    the column is there; else its ``property_id`` alone), the properties its
    line enters by at least :data:`BETA_MIN_WALL_LENGTH_IN_PROPERTY_M` (the
    lead, 2026-10-06). Each property is updated on its own count over all the
    units on it, each from its floor, and a unit on several properties keeps
    the highest of its updates: each is conditioned on a record of that
    property, and conditioning on "at least" never lowers a probability. A
    property's ``n_units`` in ``missing`` counts every unit on it.
    ``held_out``, ``claim_walls`` and ``nzmm_wall`` are the primary
    property's.

    Args:
        units: From :func:`gen_wall_units`.
        p_floor: From :func:`gen_gns_floor`, indexed like ``units``.
        records: From :func:`gen_property_wall_records`.
        held_out: From :func:`gen_claim_holdout`; a property not in it is not
            held out.
        nzmm_min_walls: The walls an NZMM true stands for
            (:data:`~landloss.domain.constants.BETA_NZMM_MIN_WALLS`).
        nzmm_weight: The share of the full NZMM update applied, from 0 (none)
            to 1 (as strong as a claim report listing ``nzmm_min_walls``)
            (:data:`~landloss.domain.constants.BETA_NZMM_UPDATE_WEIGHT`).
        use_nzmm: Whether ``p_wall`` takes the NZMM update.

    Returns:
        ``(probability, missing)``. ``probability`` is indexed like ``units``
        with ``held_out``, ``claim_walls``, ``nzmm_wall``, ``p_claims``,
        ``p_claims_nzmm``, ``p_wall`` and ``p_wall_basis`` (``claims`` or
        ``nzmm``, whichever count set it, where the update raised it, else the
        floor's basis). ``missing`` has one row per property and update
        (:data:`UPDATES`) where the units cannot hold the count, claimed
        properties with no unit included: ``property_id``, ``update``,
        ``listed_walls``, ``n_units`` and ``missing``.
    """
    property_id = units["property_id"].astype("string")
    ids = property_id.to_numpy(dtype=object, na_value=None)
    held = held_out.reindex(ids, fill_value=False).to_numpy(dtype=bool)
    claim = records["claim_walls"].reindex(ids).to_numpy(dtype=float, na_value=np.nan)
    nzmm = records["nzmm_wall"].reindex(ids).fillna(value=False).to_numpy(dtype=bool)

    p = p_floor["p_floor"].to_numpy(dtype=float)
    p_claims = p.copy()
    p_claims_nzmm = p.copy()
    n_claims_of = _claim_counts(records, held_out)
    n_nzmm_of = pd.Series(
        np.where(records["nzmm_wall"].to_numpy(dtype=bool), nzmm_min_walls, 0),
        index=records.index,
    )

    missing = []
    positions: dict[str, list[int]] = {}
    for row, pids in enumerate(unit_property_ids(units)):
        for pid in pids:
            positions.setdefault(pid, []).append(row)
    for pid in sorted(set(positions) | set(n_claims_of.index) | set(n_nzmm_of.index)):
        rows = np.asarray(positions.get(pid, []), dtype=np.int64)
        n_claims = int(n_claims_of.get(pid, 0))
        n_both = max(n_claims, int(n_nzmm_of.get(pid, 0)))
        by_claims, short_claims = gen_count_update(p[rows], n_claims)
        full, short_both = gen_count_update(p[rows], n_both)
        p_claims[rows] = np.maximum(p_claims[rows], by_claims)
        p_claims_nzmm[rows] = np.maximum(
            p_claims_nzmm[rows],
            by_claims + nzmm_weight * (full - by_claims)
            if n_both > n_claims
            else by_claims,
        )
        for update, n, short in (
            (UPDATES[0], n_claims, short_claims),
            (UPDATES[1], n_both, short_both),
        ):
            if short:
                missing.append((pid, update, n, len(rows), short))

    chosen = p_claims_nzmm if use_nzmm else p_claims
    basis = p_floor["p_floor_basis"].to_numpy(dtype=object).copy()
    raised = chosen > p
    # NZMM set it where its update took the unit above the claims alone.
    by_nzmm = use_nzmm & (p_claims_nzmm > p_claims)
    basis[raised & ~by_nzmm] = CLAIMS
    basis[raised & by_nzmm] = NZMM

    probability = pd.DataFrame(
        {
            "held_out": held,
            "claim_walls": pd.array(
                [pd.NA if np.isnan(c) else int(c) for c in claim], dtype="Int64"
            ),
            "nzmm_wall": nzmm,
            "p_claims": p_claims,
            "p_claims_nzmm": p_claims_nzmm,
            "p_wall": chosen,
            "p_wall_basis": basis,
        },
        index=units.index,
    )
    missing_frame = pd.DataFrame(
        missing, columns=["property_id", "update", "listed_walls", "n_units", "missing"]
    )
    return probability, missing_frame


def unit_property_ids(units: pd.DataFrame) -> list[list[str]]:
    """The properties each unit is a wall on: its ``property_lengths_m``.

    Where the frame has no ``property_lengths_m``, each unit is on its
    ``property_id`` alone (none where NA); the primary property is always
    included.
    """
    primary = units["property_id"].astype("string")
    lengths = (
        units["property_lengths_m"]
        if "property_lengths_m" in units.columns
        else pd.Series([[]] * len(units), index=units.index, dtype=object)
    )
    out = []
    for pid, entries in zip(primary, lengths, strict=True):
        ids = [] if pd.isna(pid) else [str(pid)]
        for entry in [] if entries is None else entries:
            if str(entry["property_id"]) not in ids:
                ids.append(str(entry["property_id"]))
        out.append(ids)
    return out


def _claim_counts(records: pd.DataFrame, held_out: pd.Series) -> pd.Series:
    """The walls each claimed property not held out is updated on."""
    walls = records["claim_walls"].astype("Float64").fillna(0.0)
    held = held_out.reindex(records.index, fill_value=False).to_numpy(dtype=bool)
    counts = np.where(
        (walls.to_numpy(dtype=float) >= 1) & ~held, walls.to_numpy(dtype=float), 0
    )
    return pd.Series(counts.astype(np.int64), index=records.index)


def gen_wall_draws(
    units: pd.DataFrame, *, world_ids: list[int], base_seed: int
) -> pd.DataFrame:
    """Draw which wall units are walled in each exposure world.

    Each world draws one uniform per unit, in index order, from its own
    :data:`DRAW_STREAM` stream, so a world's draw does not depend on which
    other worlds are drawn. A unit is walled where its uniform is under
    ``p_wall``; a NaN probability is never walled.

    Args:
        units: The wall units with ``p_wall``.
        world_ids: The exposure worlds to draw.
        base_seed: :data:`~landloss.domain.constants.EXPOSURE_BASE_SEED`.

    Returns:
        One row per world and unit: ``world_id``, ``wall_unit_id`` and
        ``walled``.
    """
    p = units["p_wall"].to_numpy(dtype=float)
    frames = []
    for world_id in world_ids:
        rng = realisation_seed(base_seed, world_id, DRAW_STREAM)
        frames.append(
            pd.DataFrame(
                {
                    "world_id": np.int64(world_id),
                    "wall_unit_id": units.index.to_numpy(dtype=object),
                    "walled": rng.random(len(units)) < p,
                }
            )
        )
    if not frames:
        return pd.DataFrame(
            {
                "world_id": pd.Series(dtype=np.int64),
                "wall_unit_id": pd.Series(dtype=object),
                "walled": pd.Series(dtype=bool),
            }
        )
    return pd.concat(frames, ignore_index=True)


def gen_element_walls(
    units: pd.DataFrame, walled: pd.Series, elements: pd.DataFrame
) -> pd.Series:
    """Turn one world's wall unit draw into a flag per grown element.

    Each element grew from one pif (``siz_id``); it is walled where that pif
    is a member of a walled unit, and not walled where the pif is in no unit.
    An element built on a GNS-only unit's line carries that unit as
    ``wall_unit_id`` and is walled where the unit is.

    Args:
        units: The wall units with ``member_pif_ids``.
        walled: A bool per unit, indexed by ``wall_unit_id``.
        elements: The grown elements, indexed by element label, with
            ``siz_id``.

    Returns:
        A bool per element, indexed like ``elements``, for
        :func:`~landloss.hazard.landslide.instability_zones.with_walls`.
    """
    flags = walled.reindex(units.index, fill_value=False).to_numpy(dtype=bool)
    members = pd.DataFrame(
        {"pif": units["member_pif_ids"].to_numpy(), "walled": flags}
    ).explode("pif")
    members = members.dropna(subset=["pif"])
    pif_walled = members.groupby(members["pif"].astype(np.int64))["walled"].any()
    by_pif = (
        elements["siz_id"]
        .map(pif_walled)
        .astype("boolean")
        .fillna(value=False)
        .astype(bool)
    )
    if "wall_unit_id" not in elements.columns:
        return by_pif
    unit_walled = pd.Series(flags, index=units.index)
    by_line = (
        elements["wall_unit_id"]
        .map(unit_walled)
        .astype("boolean")
        .fillna(value=False)
        .astype(bool)
    )
    return by_pif | by_line
