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
  damaged by shaking when either says so.
- **Culverts and bridges** are detected together as crossings and split here by
  structure kind, the crossing id becoming the culvert or bridge id.

Every builder returns the full schema, with boolean flags and the input's CRS,
even when there are no rows, and checks the contract columns before returning.
"""

import geopandas as gpd
import pandas as pd
import pyproj

from landloss.domain.loss_contract import (
    BRIDGE_COLUMNS,
    BRIDGE_ID_COLUMN,
    CLAIM_ID_COLUMN,
    CROSSING_ID_COLUMN,
    CULVERT_COLUMNS,
    CULVERT_ID_COLUMN,
    EVACUATED_AREA_COLUMN,
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
    LANDSLIDE_FOOTPRINT_AREA_COLUMN,
    LIQ_LD_AREA_COLUMN,
    LIQ_LD_COST_COLUMN,
    LIQ_LD_STATE_COLUMN,
    RW_COLUMNS,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    TOTAL_INSURED_LAND_AREA_COLUMN,
    check_contract_columns,
)
from landloss.exposure.culverts_bridges.crossings import BRIDGE, CULVERT
from landloss.exposure.land.extent import (
    AREA_COLUMN,
    DWELLING_COUNT_COLUMN,
    FOOTPRINT_AREA_COLUMN,
    PROPERTY_AREA_COLUMN,
    SUBURB_COLUMN,
)
from landloss.vul.landslide.land.damaged_area import (
    AREA_COLUMNS,
    DEPTH_COLUMNS,
    EVACUATED,
    INUNDATED,
    UNION_AREA_COLUMN,
)
from landloss.vul.landslide.land.damaged_area import (
    FOOTPRINT_AREA_COLUMN as SLIDE_FOOTPRINT_COLUMN,
)
from landloss.vul.shaking.fragility import DAMAGE_STATE_COLUMN, REPLACE

LOSS_TABLES = ("land", "rw", "culverts", "bridges")

# The exposure world a table was built for, written after the realisation id on
# every table (contract section 3.15). Not a contract column: the loss module
# reads the world from the file name.
WORLD_ID_COLUMN = "world_id"

# Exposure's column names for what the contract renames.
SIZE_CLASS_COLUMN = "size_class"
LENGTH_COLUMN = "length_m"
ASSET_COLUMN = "asset"

FLAG_COLUMNS = (IS_EVACUATED_COLUMN, IS_INUNDATED_COLUMN)


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
            damaged ground under the footprint per ``land_id``. Land without a
            row has no damaged area.
        ld_state_column: The damage state's column in ``liquefaction``.
        ld_cost_column: The settled cost's column in ``liquefaction``.
        ld_area_column: The damaged area's column in ``liquefaction``.

    Returns:
        :data:`~landloss.domain.loss_contract.LAND_COLUMNS`, then the dwelling
        count as an extra column (pending Q-07), then the geometry, in the order
        and CRS of ``insured``.

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
    land = _geo(table, [*LAND_COLUMNS, DWELLING_COUNT_COLUMN], insured.crs)
    check_contract_columns(land.columns, LAND_COLUMNS, table="land")
    return land


def build_rw_table(
    walls: gpd.GeoDataFrame, states: pd.DataFrame, flags: pd.DataFrame
) -> gpd.GeoDataFrame:
    """Assemble the retaining wall table, one row per insured wall.

    The table is spined on the world's wall population, so a wall on sloping
    ground, which the shaking step never sees, appears beside the flat-land
    walls it does (contract section 7.14).

    Args:
        walls: The world's wall population, carrying ``rw_id``, ``claim_id``,
            ``size_class``, ``length_m`` and the line geometry.
        states: The shaking step's ``damage_state`` per ``rw_id``, for the
            flat-land walls only. A wall with no row has no shaking damage
            from this source.
        flags: The wall landslide step's ``is_damaged_by_shaking``,
            ``is_evacuated`` and ``is_inundated`` per ``rw_id``, for every
            wall.

    Returns:
        :data:`~landloss.domain.loss_contract.RW_COLUMNS` then the geometry, in
        the order and CRS of ``walls``. A wall is damaged by shaking when its
        damage state is replace or the landslide step's flag says so.

    Raises:
        ValueError: If ``rw_id`` repeats in ``walls`` or ``states``, a state
            names a wall not in the population, any wall has no flags row, or
            a contract column is missing.
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
