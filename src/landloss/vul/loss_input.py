"""The four tables the vulnerability module hands to the loss module.

Per exposure world and earthquake, vul hands loss one table each for land,
retaining walls, culverts and bridges, with the columns set out in section 1 of
``.agents/plans/asset-pricing-approach.md`` and named in
:mod:`landloss.domain.loss_contract`. This module only assembles them: every
number in them was worked out by an earlier vul step and is carried here keyed
on the asset id minted in exposure.

- **Land** is spined on the insured land, one row per polygon, so land no hazard
  reached still appears, with zero damaged area.
- **Retaining walls** are spined on the world's wall population, so every
  insured wall appears whether it stands on flat land or on a slope. The
  shaking step writes a damage state for flat-land walls only; the wall
  landslide step writes the three contract flags for every wall, with the
  shaking flag of a sloping wall set by its urban slope outcome. A wall is
  damaged by shaking when either says so. A wall clipped by another failure's
  evacuated ground is damaged over that length only, which each piece takes on
  its own insured stretch (:func:`damaged_piece_lengths`).
- **Culverts and bridges** are detected together as crossings and split here by
  structure kind, the crossing id becoming the culvert or bridge id.

Every builder returns the full schema, with boolean flags and the input's CRS,
even when there are no rows, and checks the contract columns before returning.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

from landloss.domain.loss_contract import (
    BRIDGE_COLUMNS,
    BRIDGE_ID_COLUMN,
    CLAIM_ID_COLUMN,
    CROSSING_ID_COLUMN,
    CULVERT_COLUMNS,
    CULVERT_ID_COLUMN,
    EVACUATED_AREA_COLUMN,
    IMMINENT_EVACUATED_AREA_COLUMN,
    IMMINENT_LAND_LIST_COLUMNS,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_DAMAGED_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LAND_COLUMNS,
    LAND_FOOTPRINT_AREA_COLUMN,
    LAND_ID_COLUMN,
    LAND_PROPERTY_AREA_COLUMN,
    LAND_SUBURB_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_EVACUATED_AREAS_COLUMN,
    LANDSLIDE_FAILURE_COLUMNS,
    LANDSLIDE_FOOTPRINT_AREA_COLUMN,
    LIQ_LD_AREA_COLUMN,
    LIQ_LD_COST_COLUMN,
    LIQ_LD_STATE_COLUMN,
    REINUNDATED_AREA_COLUMN,
    REINUNDATED_MEAN_DEPTH_COLUMN,
    REINUNDATED_VOLUME_COLUMN,
    RW_COLUMNS,
    RW_DAMAGED_LENGTH_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    RW_TYPE_COLUMN,
    TOTAL_INSURED_LAND_AREA_COLUMN,
    check_contract_columns,
)
from landloss.exposure.coverage import shared_lengths
from landloss.exposure.culverts_bridges.crossings import BRIDGE, CULVERT
from landloss.exposure.land.extent import (
    AREA_COLUMN,
    DWELLING_COUNT_COLUMN,
    FOOTPRINT_AREA_COLUMN,
    PROPERTY_AREA_COLUMN,
    SUBURB_COLUMN,
)
from landloss.exposure.rw.population import INSURED_LENGTHS_COLUMN
from landloss.hazard.landslide.wall_units import BETA_MIN_WALL_LENGTH_IN_PROPERTY_M
from landloss.vul.landslide.flags import DAMAGED_LINE_COLUMN
from landloss.vul.landslide.land.damaged_area import (
    AREA_COLUMNS,
    DEPTH_COLUMNS,
    EVACUATED,
    IMMINENT_EVACUATED_AREA_M2_COLUMN,
    INUNDATED,
    REINUNDATED_AREA_M2_COLUMN,
    REINUNDATED_DEPTH_M_COLUMN,
    REINUNDATED_VOLUME_M3_COLUMN,
    UNION_AREA_COLUMN,
)
from landloss.vul.landslide.land.damaged_area import (
    FOOTPRINT_AREA_COLUMN as SLIDE_FOOTPRINT_COLUMN,
)
from landloss.vul.shaking.fragility import DAMAGE_STATE_COLUMN, REPLACE

# What step 3 calls the imminent and re-inundated ground, against what the land
# table calls it, in the order of
# landloss.domain.loss_contract.IMMINENT_LAND_COLUMNS.
IMMINENT_LAND_SOURCES = {
    IMMINENT_EVACUATED_AREA_COLUMN: IMMINENT_EVACUATED_AREA_M2_COLUMN,
    REINUNDATED_AREA_COLUMN: REINUNDATED_AREA_M2_COLUMN,
    REINUNDATED_MEAN_DEPTH_COLUMN: REINUNDATED_DEPTH_M_COLUMN,
    REINUNDATED_VOLUME_COLUMN: REINUNDATED_VOLUME_M3_COLUMN,
}

LOSS_TABLES = ("land", "rw", "culverts", "bridges")

# The exposure world a table was built for, written after the realisation id on
# every table (contract section 3.15). Not a contract column: the loss module
# reads the world from the file name.
WORLD_ID_COLUMN = "world_id"

# Exposure's column names for what the contract renames.
SIZE_CLASS_COLUMN = "size_class"
WALL_TYPE_COLUMN = "wall_type"
HEIGHT_COLUMN = "height_m"
LENGTH_COLUMN = "length_m"
ASSET_COLUMN = "asset"

FLAG_COLUMNS = (IS_EVACUATED_COLUMN, IS_INUNDATED_COLUMN)

# The wall a row of the rw table is a piece of, written after the contract
# columns. A wall supporting one claim's land is its own piece; a wall
# supporting several is one row per claim (split_walls_by_property), each
# ``<rw_id>-P<n>``.
PARENT_RW_ID_COLUMN = "parent_rw_id"
PIECE_SUFFIX = "-P"

# The shortest damaged length, in metres, a piece damaged by landslide ground
# needs to count as damaged (T-158, 6.3, the lead, 2026-10-14). A wall is
# flagged when more than 1 cm of its whole line lies inside the ground, but one
# claim's share of that can be a few millimetres, and loss builds at least 3 m
# of wall for any damage (landloss.loss.pricing.MIN_LANDSLIDE_WALL_LENGTH_M), so
# a sliver would buy 3 m. A judgement, not a measurement. A piece damaged by
# shaking is not tested.
MIN_DAMAGED_PIECE_LENGTH_M = 0.1

# How far from a wall's damaged line a point of an insured stretch may lie, in
# metres, and still be damaged: the stretch and the damaged line are both cut
# from the one line, so this absorbs the rounding of their ends. A numerical
# tolerance, a millimetre, like
# landloss.exposure.coverage.CROSSING_COVERAGE_TOLERANCE_M.
DAMAGED_STRETCH_TOLERANCE_M = 1e-3


def _geo(
    frame: pd.DataFrame, columns: list[str], crs: pyproj.CRS | None
) -> gpd.GeoDataFrame:
    """Return ``columns`` plus the geometry as a GeoDataFrame in ``crs``."""
    return gpd.GeoDataFrame(
        frame[[*columns, "geometry"]].reset_index(drop=True),
        geometry="geometry",
        crs=crs,
    )


def _merge_flags(
    assets: gpd.GeoDataFrame,
    flags: pd.DataFrame,
    id_column: str,
    *,
    table: str,
    columns: tuple[str, ...] = FLAG_COLUMNS,
) -> pd.DataFrame:
    """Attach the landslide flags to each asset, refusing any without them."""
    flags = flags[[id_column, *columns]]
    merged = assets.merge(
        flags, on=id_column, how="left", validate="one_to_one", indicator=True
    )
    unflagged = merged.loc[merged["_merge"] == "left_only", id_column]
    if len(unflagged):
        msg = (
            f"{len(unflagged)} {table} assets have no landslide flags, "
            f"for example {unflagged.iloc[0]!r}"
        )
        raise ValueError(msg)
    merged = merged.drop(columns="_merge")
    for column in columns:
        merged[column] = merged[column].astype(bool)
    return merged


def _check_unique(frame: pd.DataFrame, id_column: str, *, what: str) -> None:
    """Refuse a frame whose ids repeat."""
    duplicated = frame[id_column].duplicated()
    if duplicated.any():
        msg = (
            f"{int(duplicated.sum())} {what} are duplicated, for example "
            f"{frame.loc[duplicated, id_column].iloc[0]!r}"
        )
        raise ValueError(msg)


def build_land_table(
    insured: gpd.GeoDataFrame,
    liquefaction: pd.DataFrame,
    landslide: pd.DataFrame,
    *,
    ld_state_column: str = "ld_state",
    ld_cost_column: str = "cost_nzd",
    ld_area_column: str = "damaged_area_m2",
) -> gpd.GeoDataFrame:
    """Assemble the land table, one row per insured land polygon.

    Args:
        insured: The insured land, carrying ``land_id``, ``claim_id``, the
            polygon, footprint and property areas, the suburb and the dwelling
            count. No land value: the loss module values the land itself.
        liquefaction: The liquefaction land damage state, settled cost and
            damaged area per ``land_id``. Land without a row keeps a missing
            state, no cost and no damaged area. The cost is 2010/2011
            dollars excluding GST, as the Canterbury rates are stated; `loss`
            puts it on the Act's basis.
        landslide: The landslide land step's areas, inundated depth and the
            damaged ground under the footprint per ``land_id``, and the
            landslides that reached it as the lists of
            :data:`~landloss.domain.loss_contract.LANDSLIDE_FAILURE_COLUMNS`
            and
            :data:`~landloss.domain.loss_contract.LANDSLIDE_EVACUATED_AREAS_COLUMN`
            where the step wrote them, and its imminent evacuated and
            re-inundated ground and their lists
            (:data:`~landloss.domain.loss_contract.IMMINENT_LAND_COLUMNS` and
            :data:`~landloss.domain.loss_contract.IMMINENT_LAND_LIST_COLUMNS`),
            likewise. Land without a row has no damaged area, no imminent or
            re-inundated ground and empty lists.
        ld_state_column: The damage state's column in ``liquefaction``.
        ld_cost_column: The settled cost's column in ``liquefaction``.
        ld_area_column: The damaged area's column in ``liquefaction``.

    Returns:
        :data:`~landloss.domain.loss_contract.LAND_COLUMNS`, then the dwelling
        count as an extra column (pending Q-07), then the imminent and
        re-inundated ground and the failure lists where ``landslide`` carries
        them, then the geometry, in the order and CRS of ``insured``. The
        imminent ground is not settled and is outside the contract: the
        viewer's CSV reads it.

    Raises:
        ValueError: If ``land_id`` is duplicated in ``insured``, or a contract
            column is missing.
    """
    _check_unique(insured, LAND_ID_COLUMN, what="land ids in the insured land")

    land_ids = insured[LAND_ID_COLUMN]
    liquefied = liquefaction.set_index(LAND_ID_COLUMN)
    states = liquefied[ld_state_column]
    costs = liquefied[ld_cost_column]
    liquefied_areas = liquefied[ld_area_column]
    slides = landslide.set_index(LAND_ID_COLUMN)

    def from_slides(column: str, fill: float | None) -> pd.Series:
        values = land_ids.map(slides[column]).astype("float64")
        return values if fill is None else values.fillna(fill)

    table = pd.DataFrame(
        {
            LAND_ID_COLUMN: land_ids,
            CLAIM_ID_COLUMN: insured[CLAIM_ID_COLUMN],
            LIQ_LD_STATE_COLUMN: land_ids.map(states),
            LIQ_LD_COST_COLUMN: land_ids.map(costs).astype("float64").fillna(0.0),
            LIQ_LD_AREA_COLUMN: land_ids.map(liquefied_areas)
            .astype("float64")
            .fillna(0.0),
            TOTAL_INSURED_LAND_AREA_COLUMN: insured[AREA_COLUMN].astype("float64"),
            LANDSLIDE_AREA_COLUMN: from_slides(UNION_AREA_COLUMN, 0.0),
            INUNDATED_AREA_COLUMN: from_slides(AREA_COLUMNS[INUNDATED], 0.0),
            INUNDATED_MEAN_DEPTH_COLUMN: from_slides(DEPTH_COLUMNS[INUNDATED], None),
            EVACUATED_AREA_COLUMN: from_slides(AREA_COLUMNS[EVACUATED], 0.0),
            LAND_FOOTPRINT_AREA_COLUMN: insured[FOOTPRINT_AREA_COLUMN].astype(
                "float64"
            ),
            LAND_PROPERTY_AREA_COLUMN: insured[PROPERTY_AREA_COLUMN].astype("float64"),
            LANDSLIDE_FOOTPRINT_AREA_COLUMN: from_slides(SLIDE_FOOTPRINT_COLUMN, 0.0),
            LAND_SUBURB_COLUMN: insured[SUBURB_COLUMN],
            DWELLING_COUNT_COLUMN: insured[DWELLING_COUNT_COLUMN],
            "geometry": insured.geometry,
        },
        index=insured.index,
    )
    # Imminent evacuated and re-inundated ground, apart from the damaged ground
    # and settled by nothing in loss; the viewer reads them. Optional, as the
    # lists are.
    imminent = [
        column
        for column in IMMINENT_LAND_SOURCES
        if IMMINENT_LAND_SOURCES[column] in slides
    ]
    for column in imminent:
        table[column] = from_slides(IMMINENT_LAND_SOURCES[column], 0.0)
    # Each failure apart, for loss to give each its own wall (T-124). A step 3
    # run from before the lists were written has none, and loss then pools a
    # claim's ground as before.
    failures = [
        column
        for column in (
            *LANDSLIDE_FAILURE_COLUMNS,
            LANDSLIDE_EVACUATED_AREAS_COLUMN,
            *IMMINENT_LAND_LIST_COLUMNS,
        )
        if column in slides
    ]
    for column in failures:
        table[column] = [_as_list(values) for values in land_ids.map(slides[column])]
    land = _geo(
        table, [*LAND_COLUMNS, DWELLING_COUNT_COLUMN, *imminent, *failures], insured.crs
    )
    check_contract_columns(land.columns, LAND_COLUMNS, table="land")
    return land


def _as_list(values: object) -> list:
    """Return a failure list as a list, a polygon no landslide reached as empty.

    Parquet hands lists back as arrays, and a polygon with no row as missing.
    """
    if values is None or (isinstance(values, float) and pd.isna(values)):
        return []
    return list(values)


def split_walls_by_property(
    rw: gpd.GeoDataFrame,
    stretches: pd.Series,
    claims: set | None = None,
) -> gpd.GeoDataFrame:
    """Return the wall table with each wall split onto the claims it supports.

    A wall's pieces are its insured stretches: one row per claim whose insured
    land the wall supports (exposure rw step 6), carrying that claim and the
    length of the stretch, and everything else -- type, height, damage -- from
    the wall, since the wall stands or fails as one. So each claim settles the
    wall over the stretch that holds up its own land, against its own sub-cap
    and excess.

    No piece takes a remainder: length that supports no claim's insured land is
    not priced. A wall with no stretch gives no row. A stretch on a claim that
    is not in ``claims`` is dropped. A wall left with one stretch keeps its own
    id. Each piece keeps the whole wall's line, since the population carries no
    line per claim.

    Args:
        rw: The retaining wall table, one row per wall, keyed on ``rw_id``.
        stretches: Each wall's stretches by ``rw_id``, each a list of
            ``{"claim_id", "length_m"}`` already cut to the minimum length and
            ordered longest first; a wall with none, or an empty list, gives no
            piece.
        claims: The claim ids a piece may land on; ``None`` keeps every piece.

    Returns:
        ``rw`` with :data:`PARENT_RW_ID_COLUMN` added, one row per piece, in the
        order of ``rw`` and, within a wall, longest stretch first.
    """
    rows = []
    for record in rw.to_dict("records"):
        parent = record[RW_ID_COLUMN]
        entries = stretches.get(parent)
        entries = [] if entries is None else list(entries)
        pieces = [
            entry
            for entry in entries
            if claims is None or entry[CLAIM_ID_COLUMN] in claims
        ]
        for number, entry in enumerate(pieces, start=1):
            # A wall left on one stretch keeps its own id.
            piece_id = parent if len(pieces) == 1 else f"{parent}{PIECE_SUFFIX}{number}"
            rows.append(
                {
                    **record,
                    RW_ID_COLUMN: piece_id,
                    CLAIM_ID_COLUMN: entry[CLAIM_ID_COLUMN],
                    RW_LENGTH_COLUMN: float(entry["length_m"]),
                    PARENT_RW_ID_COLUMN: parent,
                }
            )
    columns = [*rw.columns, PARENT_RW_ID_COLUMN]
    frame = pd.DataFrame(rows, columns=columns)
    flags = [c for c in rw.columns if rw[c].dtype == bool]
    frame = frame.astype(dict.fromkeys(flags, bool))
    return gpd.GeoDataFrame(frame, geometry=rw.geometry.name, crs=rw.crs)


def _as_lines(values: pd.Series) -> pd.Series:
    """Return a column of lines as geometries, whether read as WKB or not.

    A step's geoparquet read with ``pandas`` hands geometry back as WKB bytes. A
    missing entry is an empty line.
    """
    lines = []
    for value in values:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            lines.append(shapely.LineString())
        elif isinstance(value, bytes | bytearray):
            lines.append(shapely.from_wkb(value))
        else:
            lines.append(value)
    return pd.Series(lines, index=values.index, dtype=object)


def damaged_piece_lengths(
    pieces: pd.DataFrame,
    damaged_lines: pd.Series,
    stretches: gpd.GeoDataFrame,
) -> np.ndarray:
    """Return how much of each piece is damaged by landslide ground, in metres.

    A piece is damaged by landslide ground when it carries ``is_evacuated`` and
    is not damaged by shaking; any other piece is 0 here. Its damaged length is
    its wall's damaged line (the part of the wall inside evacuated ground, from
    the wall landslide step) cut by the claim's own insured stretch of the wall
    (exposure rw step 6), so a wall damaged only on a neighbour's stretch is
    not damaged on this claim.

    A damaged part lying in k claims' stretches, as a wall along a shared
    property boundary does, gives each 1/k of its length, by
    :func:`~landloss.exposure.coverage.shared_lengths`: the rule that shared the
    insured stretch itself, so a piece's damaged length never exceeds its
    ``rw_length``, and the damaged lengths of a wall's pieces never sum to more
    than the wall's damaged line.

    Args:
        pieces: The split wall table, one row per piece, carrying
            ``parent_rw_id``, ``claim_id``, ``rw_length`` and the shaking and
            evacuated flags.
        damaged_lines: Each wall's damaged line by ``rw_id`` (its parent id).
        stretches: Exposure rw step 6's insured stretches, one row per wall and
            claim, carrying ``rw_id``, ``claim_id`` and the stretch line.

    Returns:
        The damaged length of each piece, in the order of ``pieces``.
    """
    shaken = pieces[IS_DAMAGED_BY_SHAKING_COLUMN].to_numpy(dtype=bool)
    landslide = pieces[IS_EVACUATED_COLUMN].to_numpy(dtype=bool) & ~shaken
    lengths = np.zeros(len(pieces))
    if not landslide.any():
        return lengths
    parents = pieces.loc[landslide, PARENT_RW_ID_COLUMN].unique()
    walls = stretches[stretches[RW_ID_COLUMN].isin(parents)]
    if walls.empty:
        return lengths
    by_wall = _as_lines(damaged_lines)
    lines = np.empty(len(walls), dtype=object)
    lines[:] = [
        by_wall[wall] if wall in by_wall.index else shapely.LineString()
        for wall in walls[RW_ID_COLUMN]
    ]
    near = shapely.buffer(lines, DAMAGED_STRETCH_TOLERANCE_M, cap_style="flat")
    cut = shapely.intersection(walls.geometry.to_numpy(), near)
    has_length = shapely.length(cut) > 0
    walls, cut = walls[has_length], cut[has_length]
    if walls.empty:
        return lengths
    wall_position = pd.Series(pd.factorize(walls[RW_ID_COLUMN].to_numpy())[0])
    shares = shared_lengths(wall_position, pd.Series(cut, dtype=object))
    found = (
        pd.Series(
            shares,
            index=pd.MultiIndex.from_arrays(
                [walls[RW_ID_COLUMN].to_numpy(), walls[CLAIM_ID_COLUMN].to_numpy()]
            ),
        )
        .groupby(level=[0, 1])
        .sum()
    )
    keys = pd.MultiIndex.from_arrays(
        [pieces[PARENT_RW_ID_COLUMN].to_numpy(), pieces[CLAIM_ID_COLUMN].to_numpy()]
    )
    own = found.reindex(keys).fillna(0.0).to_numpy()
    return np.minimum(
        np.where(landslide, own, 0.0), pieces[RW_LENGTH_COLUMN].to_numpy(dtype=float)
    )


def _wall_stretches(
    walls: pd.DataFrame,
    min_length_m: float = BETA_MIN_WALL_LENGTH_IN_PROPERTY_M,
) -> pd.Series:
    """Return each wall's stretches, as exposure rw step 6 wrote them.

    Args:
        walls: The wall population, carrying ``rw_id`` and
            :data:`INSURED_LENGTHS_COLUMN`.
        min_length_m: The shortest stretch kept, in metres.

    Returns:
        A Series by ``rw_id`` of lists of ``{"claim_id", "length_m"}``.

    Raises:
        ValueError: If the population lacks :data:`INSURED_LENGTHS_COLUMN`.
    """
    if INSURED_LENGTHS_COLUMN not in walls.columns:
        msg = (
            f"The wall population has no {INSURED_LENGTHS_COLUMN!r} column: "
            "rerun exposure rw step 6 (gen_wall_population.py)"
        )
        raise ValueError(msg)
    listed = [
        [
            {CLAIM_ID_COLUMN: e[CLAIM_ID_COLUMN], "length_m": float(e["length_m"])}
            for e in _as_list(found)
            if float(e["length_m"]) >= min_length_m
        ]
        for found in walls[INSURED_LENGTHS_COLUMN]
    ]
    return pd.Series(listed, index=walls[RW_ID_COLUMN].to_numpy(), dtype=object)


def _with_damaged_lengths(
    rw: gpd.GeoDataFrame, damaged_lines: pd.Series, stretches: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Return the pieces with their damaged length, and the sliver rule applied.

    A piece damaged by shaking takes its whole ``rw_length``. A piece damaged by
    landslide ground takes :func:`damaged_piece_lengths`, or, when that is no
    more than :data:`MIN_DAMAGED_PIECE_LENGTH_M`, is undamaged: 0 and no
    ``is_evacuated`` or ``is_inundated`` flag. Any other piece is 0.
    """
    rw = rw.copy()
    shaken = rw[IS_DAMAGED_BY_SHAKING_COLUMN].to_numpy(dtype=bool)
    landslide = rw[IS_EVACUATED_COLUMN].to_numpy(dtype=bool) & ~shaken
    own = damaged_piece_lengths(rw, damaged_lines, stretches)
    sliver = landslide & (own <= MIN_DAMAGED_PIECE_LENGTH_M)
    damaged = np.where(shaken, rw[RW_LENGTH_COLUMN].to_numpy(dtype=float), own)
    rw[RW_DAMAGED_LENGTH_COLUMN] = np.where(sliver, 0.0, damaged)
    for column in FLAG_COLUMNS:
        rw[column] = rw[column].to_numpy(dtype=bool) & ~sliver
    return rw


def build_rw_table(
    walls: gpd.GeoDataFrame,
    states: pd.DataFrame,
    flags: pd.DataFrame,
    *,
    claims: set | None = None,
    stretches: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """Assemble the retaining wall table, one row per insured wall per property.

    The table is spined on the world's wall population, so a wall on sloping
    ground, which the shaking step never sees, appears beside the flat-land
    walls it does (contract section 7.14). A wall is then split onto each claim
    whose insured land it supports (:func:`split_walls_by_property`), at the
    length of its insured stretch there, and a wall supporting none gives no
    row.

    Args:
        walls: The world's wall population, carrying ``rw_id``, ``claim_id``,
            ``size_class``, ``wall_type``, ``height_m``, ``length_m``, the
            line geometry and ``insured_lengths_m`` (exposure rw step 6).
        states: The shaking step's ``damage_state`` per ``rw_id``, for the
            flat-land walls only. A wall with no row has no shaking damage
            from this source.
        flags: The wall landslide step's ``is_damaged_by_shaking``,
            ``is_evacuated`` and ``is_inundated`` per ``rw_id``, for every
            wall.
        claims: The claims a piece of a wall may land on, normally those with
            insured land; ``None`` keeps every piece.
        stretches: Exposure rw step 6's insured stretches with their lines
            (``wall-insured-stretches``), one row per wall and claim. Given, the
            table also carries each piece's damaged length (T-158) and ``flags``
            must carry the wall landslide step's ``damaged_line``; ``None``
            writes no damaged length, and loss then takes the whole length.

    Returns:
        :data:`~landloss.domain.loss_contract.RW_COLUMNS`, then
        :data:`PARENT_RW_ID_COLUMN`, then, with ``stretches``,
        :data:`~landloss.domain.loss_contract.RW_DAMAGED_LENGTH_COLUMN` (an
        extra column, outside the contract), then the geometry, in the order
        and CRS of ``walls``. A wall is damaged by shaking when its damage state
        is replace or the landslide step's flag says so, and a piece of one is
        damaged over its whole ``rw_length``. A piece damaged by landslide
        ground is damaged over its wall's damaged line within its own stretch
        (:func:`damaged_piece_lengths`). A piece with none of that damage is 0,
        and so is one whose damaged length is no more than
        :data:`MIN_DAMAGED_PIECE_LENGTH_M`, which is then undamaged and loses
        its landslide flags (6.3). A piece only inundated keeps ``is_inundated``
        and has no damaged length: inundated ground does not damage a wall.

    Raises:
        ValueError: If ``rw_id`` repeats in ``walls`` or ``states``, a state
            names a wall not in the population, any wall has no flags row, a
            contract column is missing, or ``stretches`` is given and ``flags``
            has no damaged line.
    """
    _check_unique(walls, RW_ID_COLUMN, what="wall ids in the population")
    _check_unique(states, RW_ID_COLUMN, what="wall ids in the damage states")
    state_of = states.set_index(RW_ID_COLUMN)[DAMAGE_STATE_COLUMN]
    strangers = state_of.index[~state_of.index.isin(walls[RW_ID_COLUMN])]
    if len(strangers):
        msg = (
            f"{len(strangers)} damage states name walls not in the population, "
            f"for example {strangers[0]!r}"
        )
        raise ValueError(msg)
    # A wall the shaking step did not write (a sloping wall) is not shaking
    # damaged by that route: a missing state compares unequal to replace.
    replaced = (walls[RW_ID_COLUMN].map(state_of) == REPLACE).to_numpy()

    table = pd.DataFrame(
        {
            RW_ID_COLUMN: walls[RW_ID_COLUMN],
            CLAIM_ID_COLUMN: walls[CLAIM_ID_COLUMN],
            RW_SIZE_COLUMN: walls[SIZE_CLASS_COLUMN],
            RW_TYPE_COLUMN: walls[WALL_TYPE_COLUMN],
            RW_HEIGHT_COLUMN: walls[HEIGHT_COLUMN].astype("float64"),
            RW_LENGTH_COLUMN: walls[LENGTH_COLUMN].astype("float64"),
            "geometry": walls.geometry,
        },
        index=walls.index,
    )
    merged = _merge_flags(
        table,
        flags,
        RW_ID_COLUMN,
        table="rw",
        columns=(IS_DAMAGED_BY_SHAKING_COLUMN, *FLAG_COLUMNS),
    )
    merged[IS_DAMAGED_BY_SHAKING_COLUMN] = (
        replaced | merged[IS_DAMAGED_BY_SHAKING_COLUMN].to_numpy()
    )
    rw = _geo(merged, list(RW_COLUMNS), walls.crs)
    rw = split_walls_by_property(rw, _wall_stretches(walls), claims)
    extra = [PARENT_RW_ID_COLUMN]
    if stretches is not None:
        if DAMAGED_LINE_COLUMN not in flags.columns:
            msg = (
                f"the wall flags have no {DAMAGED_LINE_COLUMN!r} column: rerun "
                "vul landslide rw step 11 (gen_wall_landslide_damage.py)"
            )
            raise ValueError(msg)
        rw = _with_damaged_lengths(
            rw, flags.set_index(RW_ID_COLUMN)[DAMAGED_LINE_COLUMN], stretches
        )
        extra.append(RW_DAMAGED_LENGTH_COLUMN)
    rw = _geo(rw, [*RW_COLUMNS, *extra], walls.crs)
    check_contract_columns(rw.columns, RW_COLUMNS, table="rw")
    return rw


def build_crossing_tables(
    crossings: gpd.GeoDataFrame, flags: pd.DataFrame
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Split the crossings into the culvert and bridge tables.

    Args:
        crossings: The crossings with their shaking damage state, carrying
            ``crossing_id``, ``claim_id``, ``asset`` (culvert or bridge) and
            ``damage_state``.
        flags: The crossing landslide step's ``is_evacuated`` and
            ``is_inundated`` per ``crossing_id``.

    Returns:
        The culvert table, :data:`~landloss.domain.loss_contract.CULVERT_COLUMNS`
        then ``is_evacuated`` as an extra column (pending Q-09) then the
        geometry, and the bridge table,
        :data:`~landloss.domain.loss_contract.BRIDGE_COLUMNS` then the geometry.
        The crossing id becomes the culvert or bridge id. A culvert is damaged
        when its shaking damage state is replace; a bridge's shaking damage is
        reported as ``is_damaged_by_shaking``. Both keep the CRS of
        ``crossings``.

    Raises:
        ValueError: If any crossing has no flags row, or a contract column is
            missing.
    """
    if crossings.geometry.name != "geometry":
        crossings = crossings.rename_geometry("geometry")
    merged = _merge_flags(crossings, flags, CROSSING_ID_COLUMN, table="crossing")
    replaced = (merged[DAMAGE_STATE_COLUMN] == REPLACE).astype(bool)

    is_culvert = merged[ASSET_COLUMN] == CULVERT
    culverts = merged.loc[is_culvert].rename(
        columns={CROSSING_ID_COLUMN: CULVERT_ID_COLUMN}
    )
    culverts[IS_DAMAGED_COLUMN] = replaced[is_culvert]
    culvert_table = _geo(
        culverts, [*CULVERT_COLUMNS, IS_EVACUATED_COLUMN], crossings.crs
    )
    check_contract_columns(culvert_table.columns, CULVERT_COLUMNS, table="culverts")

    is_bridge = merged[ASSET_COLUMN] == BRIDGE
    bridges = merged.loc[is_bridge].rename(
        columns={CROSSING_ID_COLUMN: BRIDGE_ID_COLUMN}
    )
    bridges[IS_DAMAGED_BY_SHAKING_COLUMN] = replaced[is_bridge]
    bridge_table = _geo(bridges, list(BRIDGE_COLUMNS), crossings.crs)
    check_contract_columns(bridge_table.columns, BRIDGE_COLUMNS, table="bridges")
    return culvert_table, bridge_table
