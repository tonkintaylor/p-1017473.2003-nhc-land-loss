"""Wall units on the pifs: which faces are one wall, and how likely it is there.

A retaining wall can be several pifs (a long wall is cut at the pif span, and a
wall with a gap is two pifs) and a GNS mapped wall too low for the grid is a
``gns_only`` piece with no pif, so the model counts walls, not pifs. This
module:

1. **Units.** Joins the candidate pifs (classes ``siz`` and ``small``) and the
   ``gns_only`` pieces of one property into wall units, end to end only: pieces
   one GNS mapped wall reaches are one unit; a ``gns_only`` piece near a pif
   joins it; elsewhere two pifs join where their facing ends are close, level
   along the fall and facing the same way, or close enough to be a corner.
2. **Prior.** Puts a prior on each unit from whether it holds a siz, its height
   band, a rock cut and fill (:func:`gen_wall_prior`).
3. **Floor.** Lifts a unit with a GNS mapped wall on it to a floor
   (:func:`gen_gns_floor`). GNS is the only dataset that locates a wall, so it
   is the only evidence on a candidate, and it is one-sided: GNS maps only the
   walls visible from above, so the part of a unit no mapped wall reaches is
   not evidence against a wall there.
4. **Update.** The claim reports and NZMM count walls per property, not which
   candidate is the wall, so each property's units are updated on the count
   with the Poisson-binomial (:func:`gen_count_update`); no probability falls.
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

**What the prior does not read yet.** Landslide step 13 classes every pif as
cut, fill, natural or unknown (``urban-slope-pif-cut-fill{suffix}.parquet``,
``cut_fill_class``). It is not read here; when it is settled it becomes a
further factor on the prior, the source of a true "cut" for the rock cut rule
(which now reads any face in rock as a cut) and of a unit's wall position.
The ground map's ``modification`` is not read either: it is ``fill`` on 88% of
the pilot's candidate pifs, rock included, so it would lift nearly every unit.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import ArrayLike, NDArray
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.exposure.land.extent import stack_representatives
from landloss.hazard.landslide.ground_map import ROCK_MATERIALS
from landloss.hazard.landslide.wall_candidates import SIZ_CLASS, SMALL_CLASS
from landloss.hazard.realisation import realisation_seed

# The two kinds of member a wall unit is made of.
PIF_MEMBER, GNS_ONLY_MEMBER = "pif", "gns_only"
UNIT_SOURCES = (PIF_MEMBER, GNS_ONLY_MEMBER)

# The pif candidate classes that become members.
CANDIDATE_CLASSES = (SIZ_CLASS, SMALL_CLASS)

# The basis strings: the last rule that set a unit's probability.
P_WALL_BASES = ("prior", "rock_cut", "fill", "gns_floor", "gns_only", "claims", "nzmm")
PRIOR, ROCK_CUT, FILL, GNS_FLOOR, GNS_ONLY, CLAIMS, NZMM = P_WALL_BASES

# The two updates written to the candidates missing table.
UPDATES = ("claims", "claims_nzmm")

# The stream each exposure world's wall unit draw comes from.
DRAW_STREAM = "wall_units"

# The ground map materials read as fill.
FILL_MATERIALS = ("fill_engineered", "fill_uncontrolled")

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
    sizs: gpd.GeoDataFrame, gns_only: gpd.GeoDataFrame
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

    Returns:
        On a fresh index: ``member_type`` (:data:`PIF_MEMBER` or
        :data:`GNS_ONLY_MEMBER`), ``member_id`` (the pif_id or gns_only_id),
        ``property_id`` (the rateable property, by one rule for both: the
        non-road property holding most of the pif or line, ties to the lowest
        id, NA where none), ``length_m`` (the spine or the line),
        the end columns (a GNS-only piece's ends are its line's ends and its
        falls are NaN), ``max_delta_h_m`` (NaN for GNS-only), ``height_m``
        (``max_delta_h_m``, or ``step_height_m`` for GNS-only),
        ``building_m``, ``ground_group``, ``ground_material``, ``height_band``
        (0 for GNS-only), ``in_slide_fill`` (False for GNS-only), ``gns_wall``
        (True for GNS-only), ``is_siz``, and ``footprint`` (the pips or the
        line). The active geometry is the spine or the line.

    Raises:
        ValueError: If either frame is missing a column it needs.
    """
    _require(sizs, PIF_COLUMNS, "sizs")
    _require(gns_only, GNS_ONLY_COLUMNS, "gns_only")
    crs = sizs.crs
    pifs = sizs[sizs["candidate_class"].isin(CANDIDATE_CLASSES)]
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
            "height_m": pifs["max_delta_h_m"].to_numpy(dtype=float),
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
    groups: NDArray[np.int64], members: NDArray[np.int64], keys: NDArray[np.int64]
) -> NDArray[np.int64]:
    """Edges joining the members that share a group and a property key."""
    if len(members) == 0:
        return np.zeros((0, 2), dtype=np.int64)
    frame = pd.DataFrame({"group": groups, "member": members, "key": keys[members]})
    first = frame.groupby(["group", "key"])["member"].transform("min")
    return np.column_stack([first.to_numpy(), members]).astype(np.int64)


def _end_edges(
    members: gpd.GeoDataFrame,
    keys: NDArray[np.int64],
    *,
    join_gap_m: float,
    max_offset_m: float,
    bearing_tol_deg: float,
    corner_gap_m: float,
    corner_max_deg: float,
) -> NDArray[np.int64]:
    """Edges joining pif members end to end, on one property."""
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
    pair = pair[keys[pif[pair[:, 0]]] == keys[pif[pair[:, 1]]]]
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
) -> gpd.GeoDataFrame:
    """Join the members of one property into wall units.

    Members join only within one property; members with no property share one
    "no property" key, so they join each other but nothing on a property.
    Three rules join them, and a unit is everything joined directly or through
    others:

    - **GNS feature:** members whose footprint lies within ``gns_match_m`` of
      one GNS mapped wall feature are one unit; where GNS maps the wall it is
      the join.
    - **GNS-only merge:** a GNS-only piece within ``gns_only_merge_m`` of a
      pif's footprint joins it, whatever their directions, so one wall is not
      counted twice.
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

    Returns:
        One row per unit, indexed by ``wall_unit_id`` (minted by location
        behind :data:`~landloss.domain.constants.WALL_UNIT_ID_PREFIX`), with
        ``member_pif_ids`` and ``member_gns_only_ids`` (sorted lists),
        ``n_pifs``, ``n_gns_only``, ``unit_source`` (``pif`` where any member
        is a pif, else ``gns_only``), ``is_siz`` and ``gns_wall`` (any member),
        ``property_id``, ``in_exposure`` (it has a property),
        ``max_delta_h_m`` (the highest pif), ``height_m`` (the highest
        member), ``building_m`` (the nearest), ``length_m`` (the sum),
        :data:`LONGEST_MEMBER_COLUMNS` from the longest member (ties to the
        lowest member type and id), ``x`` and ``y`` (a representative point)
        and a MultiLineString of the member geometries.
    """
    crs = members.crs
    n = len(members)
    keys = pd.factorize(members["property_id"], use_na_sentinel=False)[0].astype(
        np.int64
    )
    footprints = gpd.GeoSeries(members["footprint"], crs=crs).to_numpy()
    edges = []

    if n and len(gns_features):
        near = shapely.STRtree(footprints).query(
            gns_features.geometry.to_numpy(), predicate="dwithin", distance=gns_match_m
        )
        edges.append(_within_groups(near[0], near[1], keys))

    is_pif = members["member_type"].to_numpy() == PIF_MEMBER
    gns_rows = np.flatnonzero(~is_pif)
    pif_rows = np.flatnonzero(is_pif)
    if len(gns_rows) and len(pif_rows):
        near = shapely.STRtree(footprints[pif_rows]).query(
            footprints[gns_rows], predicate="dwithin", distance=gns_only_merge_m
        )
        pairs = np.column_stack([gns_rows[near[0]], pif_rows[near[1]]])
        edges.append(pairs[keys[pairs[:, 0]] == keys[pairs[:, 1]]].astype(np.int64))

    edges.append(
        _end_edges(
            members,
            keys,
            join_gap_m=join_gap_m,
            max_offset_m=max_offset_m,
            bearing_tol_deg=bearing_tol_deg,
            corner_gap_m=corner_gap_m,
            corner_max_deg=corner_max_deg,
        )
    )
    frame = pd.DataFrame(members.drop(columns=["geometry", "footprint"]))
    frame["unit"] = _components(n, edges) if n else np.zeros(0, dtype=np.int64)
    return _unit_rows(frame, members.geometry.to_numpy(), crs=crs)


def _unit_rows(
    frame: pd.DataFrame, geometries: NDArray[np.object_], *, crs: object
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
    units["property_id"] = grouped["property_id"].first()
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

    unit = frame["unit"].to_numpy()
    order = np.argsort(unit, kind="mergesort")
    _, indices = np.unique(unit[order], return_inverse=True)
    geometry = (
        shapely.multilinestrings(geometries[order], indices=indices)
        if len(unit)
        else np.array([], dtype=object)
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


def gen_wall_prior(units: pd.DataFrame) -> pd.DataFrame:
    """The prior probability that each wall unit is a wall.

    Applied in this order: :data:`~landloss.domain.constants.BETA_SIZ_WALL_PRIOR`
    for a unit holding a siz, else
    :data:`~landloss.domain.constants.BETA_SMALL_WALL_PRIOR`; times the factor
    of its height band
    (:data:`~landloss.domain.constants.BETA_WALL_PRIOR_HEIGHT_BAND_FACTOR`);
    times :data:`~landloss.domain.constants.BETA_ROCK_CUT_FACTOR` for a rock
    cut, a unit on a rock material whose highest face is over
    :data:`~landloss.domain.constants.BETA_ROCK_CUT_MIN_HEIGHT_M` (under it the
    face is in the soil cover); times
    :data:`~landloss.domain.constants.BETA_FILL_WALL_FACTOR` on fill, a unit
    on a fill material or touching a SLIDE fill body. The prior is clipped to
    [0, 1]. The basis is the last rule that applied. A GNS-only unit has no
    prior: its probability is set by the floor.

    The landslide step 13 cut and fill class is the slot for a further factor
    here, and for a true "cut" in the rock cut rule, once it is settled.

    Args:
        units: From :func:`gen_wall_units`.

    Returns:
        A frame indexed like ``units`` with ``p_prior`` (NaN for a GNS-only
        unit), ``p_prior_basis``, ``is_rock_cut`` and ``is_fill`` (computed for
        every unit).
    """
    material = units["ground_material"]
    is_rock_cut = material.isin(ROCK_MATERIALS) & (
        units["max_delta_h_m"].to_numpy(dtype=float)
        > constants.BETA_ROCK_CUT_MIN_HEIGHT_M
    )
    is_fill = material.isin(FILL_MATERIALS) | units["in_slide_fill"].astype(bool)

    prior = np.where(
        units["is_siz"].to_numpy(dtype=bool),
        constants.BETA_SIZ_WALL_PRIOR,
        constants.BETA_SMALL_WALL_PRIOR,
    )
    band = units["height_band"].map(
        lambda b: constants.BETA_WALL_PRIOR_HEIGHT_BAND_FACTOR.get(int(b), 1.0)
    )
    prior = prior * band.to_numpy(dtype=float)
    basis = np.full(len(units), PRIOR, dtype=object)
    rock = is_rock_cut.to_numpy(dtype=bool)
    prior = np.where(rock, prior * constants.BETA_ROCK_CUT_FACTOR, prior)
    basis[rock] = ROCK_CUT
    fill = is_fill.to_numpy(dtype=bool)
    prior = np.where(fill, prior * constants.BETA_FILL_WALL_FACTOR, prior)
    basis[fill] = FILL
    prior = np.clip(prior, 0.0, 1.0)

    gns_only = units["unit_source"].to_numpy() == GNS_ONLY_MEMBER
    prior[gns_only] = np.nan
    basis[gns_only] = GNS_ONLY
    return pd.DataFrame(
        {
            "p_prior": prior,
            "p_prior_basis": basis,
            "is_rock_cut": rock,
            "is_fill": fill,
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
    on_property = property_id.notna().to_numpy()
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
    positions = (
        pd.Series(np.flatnonzero(on_property))
        .groupby(ids[on_property])
        .agg(list)
        .to_dict()
    )
    for pid in sorted(set(positions) | set(n_claims_of.index) | set(n_nzmm_of.index)):
        rows = np.asarray(positions.get(pid, []), dtype=np.int64)
        n_claims = int(n_claims_of.get(pid, 0))
        n_both = max(n_claims, int(n_nzmm_of.get(pid, 0)))
        by_claims, short_claims = gen_count_update(p[rows], n_claims)
        full, short_both = gen_count_update(p[rows], n_both)
        p_claims[rows] = by_claims
        p_claims_nzmm[rows] = (
            by_claims + nzmm_weight * (full - by_claims)
            if n_both > n_claims
            else by_claims
        )
        for update, n, short in (
            (UPDATES[0], n_claims, short_claims),
            (UPDATES[1], n_both, short_both),
        ):
            if short:
                missing.append((pid, update, n, len(rows), short))

    n_claims_unit = n_claims_of.reindex(ids, fill_value=0).to_numpy(dtype=np.int64)
    n_nzmm_unit = n_nzmm_of.reindex(ids, fill_value=0).to_numpy(dtype=np.int64)
    chosen = p_claims_nzmm if use_nzmm else p_claims
    basis = p_floor["p_floor_basis"].to_numpy(dtype=object).copy()
    raised = chosen > p
    by_nzmm = use_nzmm & (n_nzmm_unit > n_claims_unit)
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
    return (
        elements["siz_id"]
        .map(pif_walled)
        .astype("boolean")
        .fillna(value=False)
        .astype(bool)
    )
