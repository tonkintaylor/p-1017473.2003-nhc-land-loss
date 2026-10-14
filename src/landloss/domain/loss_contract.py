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
# Each landslide that reached the polygon, one entry per failure and in the same
# order in every list (T-124, 2026-10-13), so loss can hold each failure with its
# own wall: the failure's id; the retaining wall it failed with, as the hazard
# realisation names it -- the whole wall, before it is split across properties
# -- or missing; the ground it took on the polygon, evacuated and inundated
# counted once; and its inundated area and depth. Not in LAND_COLUMNS: a land
# table from before they were written has none, and loss then takes a claim's
# ground as one failure of unknown origin.
LANDSLIDE_IDS_COLUMN = "landslide_ids"
LANDSLIDE_RW_IDS_COLUMN = "landslide_rw_ids"
LANDSLIDE_AREAS_COLUMN = "landslide_areas"
LANDSLIDE_INUNDATED_AREAS_COLUMN = "landslide_inundated_areas"
LANDSLIDE_INUNDATED_DEPTHS_COLUMN = "landslide_inundated_depths"
# Each failure's evacuated ground on the polygon, in the order of the lists
# above, which the length of the wall a slip needs is taken from (2026-10-14).
# Kept out of LANDSLIDE_FAILURE_COLUMNS so a land table written before it still
# lists its failures; loss then measures the wall off the failure's whole ground.
LANDSLIDE_EVACUATED_AREAS_COLUMN = "landslide_evacuated_areas"
# Imminent ground and re-inundation, carried apart from the damaged ground for
# the viewer's page to add (2026-10-14). Not in LAND_COLUMNS and not settled by
# loss: the polygon's imminent ground less any ground evacuated on it by any
# failure, counted once; and the ground of the failures that have imminent land
# buried again, as a union, its volume summed over failures at each one's own
# depth, and its mean depth, the volume over the area (0 with no area). The two
# lists hold each failure's own imminent and re-inundated ground, in the order
# of LANDSLIDE_IDS_COLUMN. A land table from before they were written has none,
# and the viewer's CSV then reads zeros.
IMMINENT_EVACUATED_AREA_COLUMN = "imminent_evacuated_area"
REINUNDATED_AREA_COLUMN = "reinundated_insured_area"
REINUNDATED_MEAN_DEPTH_COLUMN = "reinundated_mean_depth"
REINUNDATED_VOLUME_COLUMN = "reinundated_volume"
IMMINENT_LAND_COLUMNS = (
    IMMINENT_EVACUATED_AREA_COLUMN,
    REINUNDATED_AREA_COLUMN,
    REINUNDATED_MEAN_DEPTH_COLUMN,
    REINUNDATED_VOLUME_COLUMN,
)
LANDSLIDE_IMMINENT_AREAS_COLUMN = "landslide_imminent_areas"
LANDSLIDE_REINUNDATED_AREAS_COLUMN = "landslide_reinundated_areas"
IMMINENT_LAND_LIST_COLUMNS = (
    LANDSLIDE_IMMINENT_AREAS_COLUMN,
    LANDSLIDE_REINUNDATED_AREAS_COLUMN,
)
# The wall each failure no damaged wall holds is built as, in the order of
# LANDSLIDE_IDS_COLUMN (2026-10-14, section 4 of the property damage tweaks):
# the height of the mapped wall on the failure's polygon's unit, the length of
# that wall's stretch on the claim alongside the failure's evacuated ground
# (before the margin; 0 on a failure sharing the wall another failure on the
# same unit and claim already has), and where the wall comes from, MAPPED_WALL
# or SLIP_WALL. A SLIP_WALL failure carries no height or length, and a failure a
# damaged wall holds is SLIP_WALL too, since loss never builds for it. Not in
# LAND_COLUMNS: a land table from before they were written has none, and loss
# then sizes every new wall from the slip.
LANDSLIDE_WALL_HEIGHTS_COLUMN = "landslide_wall_heights"
LANDSLIDE_WALL_LENGTHS_COLUMN = "landslide_wall_lengths"
LANDSLIDE_WALL_SOURCES_COLUMN = "landslide_wall_sources"
LANDSLIDE_WALL_COLUMNS = (
    LANDSLIDE_WALL_HEIGHTS_COLUMN,
    LANDSLIDE_WALL_LENGTHS_COLUMN,
    LANDSLIDE_WALL_SOURCES_COLUMN,
)
MAPPED_WALL = "mapped wall"
SLIP_WALL = "slip"
LANDSLIDE_FAILURE_COLUMNS = (
    LANDSLIDE_IDS_COLUMN,
    LANDSLIDE_RW_IDS_COLUMN,
    LANDSLIDE_AREAS_COLUMN,
    LANDSLIDE_INUNDATED_AREAS_COLUMN,
    LANDSLIDE_INUNDATED_DEPTHS_COLUMN,
)

# Retaining wall, culvert and bridge columns, asset-pricing-approach.md section 1.
RW_SIZE_COLUMN = "rw_size"
# The wall's type, one of the eight of
# landloss.hazard.landslide.urban.wall_type_fragility.WALL_TYPES, and its
# retained height in metres, as exposure drew them. Loss prices the wall from
# both (landloss.loss.pricing.wall_type_rate_excl_gst_nzd_per_m2).
RW_TYPE_COLUMN = "rw_type"
RW_HEIGHT_COLUMN = "rw_height"
RW_LENGTH_COLUMN = "rw_length"
# The length of a piece that is damaged, in metres, which loss replaces the wall
# over (plus its margin) instead of the whole piece. Not in RW_COLUMNS: a wall
# table written before it has none, and loss then takes the whole length as
# damaged.
RW_DAMAGED_LENGTH_COLUMN = "rw_damaged_length"
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
    RW_TYPE_COLUMN,
    RW_HEIGHT_COLUMN,
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
