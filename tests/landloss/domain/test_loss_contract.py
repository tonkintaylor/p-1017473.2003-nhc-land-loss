"""Tests for the column names of the vul-to-loss contract."""

import pytest

from landloss.domain import loss_contract
from landloss.domain.loss_contract import (
    BRIDGE_COLUMNS,
    CLAIM_ID_COLUMN,
    CULVERT_COLUMNS,
    LAND_COLUMNS,
    RW_COLUMNS,
    check_contract_columns,
)

ALL_TABLES = {
    "land": LAND_COLUMNS,
    "retaining walls": RW_COLUMNS,
    "culverts": CULVERT_COLUMNS,
    "bridges": BRIDGE_COLUMNS,
}


def test_tuples_hold_the_exact_contract_strings():
    assert LAND_COLUMNS == (
        "land_id",
        "claim_id",
        "$/m2 market value",
        "Liq_LD_state",
        "Liq_LD_cost_excl_gst_nzd",
        "Liq_LD_damaged_area",
        "total_insured_land_area",
        "land_slide_total_insured_land_area",
        "inundated_insured_area",
        "inundated_mean_depth",
        "evacuated_area",
    )
    assert RW_COLUMNS == (
        "rw_id",
        "claim_id",
        "rw_size",
        "rw_length",
        "is_damaged_by_shaking",
        "is_evacuated",
        "is_inundated",
    )
    assert CULVERT_COLUMNS == ("culvert_id", "claim_id", "is_inundated", "is_damaged")
    assert BRIDGE_COLUMNS == (
        "bridge_id",
        "claim_id",
        "is_damaged_by_shaking",
        "is_evacuated",
        "is_inundated",
    )


def test_keys_outside_the_tuples():
    assert loss_contract.REALISATION_ID_COLUMN == "realisation_id"
    assert loss_contract.CROSSING_ID_COLUMN == "crossing_id"


@pytest.mark.parametrize("columns", ALL_TABLES.values(), ids=ALL_TABLES.keys())
def test_no_duplicates_in_a_tuple(columns):
    assert len(set(columns)) == len(columns)


@pytest.mark.parametrize("columns", ALL_TABLES.values(), ids=ALL_TABLES.keys())
def test_every_table_carries_the_claim_id(columns):
    assert CLAIM_ID_COLUMN in columns


def test_check_passes_on_a_full_set_with_extras():
    check_contract_columns(
        [*LAND_COLUMNS, "geometry", "dwelling_count"], LAND_COLUMNS, table="land"
    )


def test_check_names_the_table_and_every_missing_column():
    present = [c for c in RW_COLUMNS if c not in ("rw_size", "is_inundated")]
    with pytest.raises(ValueError, match="retaining walls") as info:
        check_contract_columns(present, RW_COLUMNS, table="retaining walls")
    assert "rw_size" in str(info.value)
    assert "is_inundated" in str(info.value)
