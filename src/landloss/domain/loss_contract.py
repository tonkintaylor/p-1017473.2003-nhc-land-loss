"""Column names of the tables the vulnerability module hands to the loss module.

The contract is set out in section 1 of
``.agents/plans/asset-pricing-approach.md``: per realisation, vul hands loss four
tables -- land, retaining walls, culverts and bridges -- each row carrying the
claim id and its own asset id. Every producer imports the names from here rather
than retyping them, so a renamed column changes in one place.
"""

from collections.abc import Iterable, Sequence

# Keys, asset-pricing-approach.md section 1. The claim is the LINZ property
# established by the insured land step; every asset row carries it.
CLAIM_ID_COLUMN = "claim_id"
REALISATION_ID_COLUMN = "realisation_id"
LAND_ID_COLUMN = "land_id"
RW_ID_COLUMN = "rw_id"
# The exposure-side id of one detected crossing. Not a contract column: it is
# renamed to the culvert or bridge id by structure kind when the tables are built.
CROSSING_ID_COLUMN = "crossing_id"
CULVERT_ID_COLUMN = "culvert_id"
BRIDGE_ID_COLUMN = "bridge_id"

# Land table columns, asset-pricing-approach.md section 1.
#
# No land value: the loss module values land itself, from the QV rating roll
# (landloss.loss.qv_land_value). What it needs from vul is where the land lies:
# the claim property's footprint, insured and whole areas, how much of the
# landslide ground fell on the footprint, and the suburb, which a property not
# on the roll is valued at the median of. The areas are m2.
LAND_FOOTPRINT_AREA_COLUMN = "footprint_area"
LAND_PROPERTY_AREA_COLUMN = "property_area"
LANDSLIDE_FOOTPRINT_AREA_COLUMN = "land_slide_footprint_area"
LAND_SUBURB_COLUMN = "suburb"
LIQ_LD_STATE_COLUMN = "Liq_LD_state"
# The Canterbury settled cost the state indexes, carried so that `loss` has a
# land repair cost to compare a cap against. **2010/2011 dollars excluding
# GST**, which is how the Canterbury rates are stated; the basis is in the name
# because nothing else in the table says it and grossing up twice is silent.
LIQ_LD_COST_COLUMN = "Liq_LD_cost_excl_gst_nzd"
# The insured area liquefaction damaged -- evacuated plus inundated, less their
# overlap, no more than the polygon -- which the land cover cap is valued over
# (T-56). Zero where the polygon carries no state.
LIQ_LD_AREA_COLUMN = "Liq_LD_damaged_area"
TOTAL_INSURED_LAND_AREA_COLUMN = "total_insured_land_area"
LANDSLIDE_AREA_COLUMN = "land_slide_total_insured_land_area"
INUNDATED_AREA_COLUMN = "inundated_insured_area"
INUNDATED_MEAN_DEPTH_COLUMN = "inundated_mean_depth"
EVACUATED_AREA_COLUMN = "evacuated_area"

# Retaining wall, culvert and bridge columns, asset-pricing-approach.md section 1.
RW_SIZE_COLUMN = "rw_size"
RW_LENGTH_COLUMN = "rw_length"
IS_DAMAGED_BY_SHAKING_COLUMN = "is_damaged_by_shaking"
IS_EVACUATED_COLUMN = "is_evacuated"
IS_INUNDATED_COLUMN = "is_inundated"
IS_DAMAGED_COLUMN = "is_damaged"

# The contract columns of each table in contract order,
# asset-pricing-approach.md section 1. Geometry, the realisation id and any
# extra columns are not part of them.
LAND_COLUMNS = (
    LAND_ID_COLUMN,
    CLAIM_ID_COLUMN,
    LIQ_LD_STATE_COLUMN,
    LIQ_LD_COST_COLUMN,
    LIQ_LD_AREA_COLUMN,
    TOTAL_INSURED_LAND_AREA_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    EVACUATED_AREA_COLUMN,
    LAND_FOOTPRINT_AREA_COLUMN,
    LAND_PROPERTY_AREA_COLUMN,
    LANDSLIDE_FOOTPRINT_AREA_COLUMN,
    LAND_SUBURB_COLUMN,
)
RW_COLUMNS = (
    RW_ID_COLUMN,
    CLAIM_ID_COLUMN,
    RW_SIZE_COLUMN,
    RW_LENGTH_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
)
CULVERT_COLUMNS = (
    CULVERT_ID_COLUMN,
    CLAIM_ID_COLUMN,
    IS_INUNDATED_COLUMN,
    IS_DAMAGED_COLUMN,
)
BRIDGE_COLUMNS = (
    BRIDGE_ID_COLUMN,
    CLAIM_ID_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
)


def check_contract_columns(
    columns: Iterable[str], required: Sequence[str], *, table: str
) -> None:
    """Refuse a table that is missing any of its contract columns.

    Args:
        columns: The columns the table carries.
        required: The contract columns it must carry, such as
            :data:`LAND_COLUMNS`.
        table: The table's name, used in the error message.

    Raises:
        ValueError: If any required column is missing, naming every one of them.
    """
    present = set(columns)
    missing = [column for column in required if column not in present]
    if missing:
        msg = f"the {table} table is missing contract columns {missing}"
        raise ValueError(msg)
