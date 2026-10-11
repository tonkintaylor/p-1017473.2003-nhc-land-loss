"""Tests for valuing damaged land from the QV roll in three tiers."""

import numpy as np
import pandas as pd
import pytest

from landloss.domain import loss_contract
from landloss.domain.gst import add_gst
from landloss.loss.qv_land_value import (
    DAMAGED_LAND_RATE_COLUMN,
    FOOTPRINT_RATE_COLUMN,
    FROM_ROLL,
    FROM_RUN,
    FROM_SUBURB,
    INSURED_RATE_COLUMN,
    LAND_VALUE_COLUMN,
    QV_LAND_VALUE_COLUMN,
    QV_UNITS_COLUMN,
    VALUE_SOURCE_COLUMN,
    claim_land_values,
    damaged_land_rates,
    footprint_rate,
    qv_land_value_by_claim,
)

CLAIM = loss_contract.CLAIM_ID_COLUMN


def series(*values):
    return pd.Series(values, dtype=float)


# ---------------------------------------------------------------------------
# The tiers add back to the property's value.
# ---------------------------------------------------------------------------


def test_the_worked_example_in_the_method_note():
    # A 3,000 m2 section worth $600,000, a 150 m2 house and 800 m2 insured.
    rate = footprint_rate(series(600_000), series(150), series(800), series(3_000))
    assert rate.iloc[0] == pytest.approx(600_000 / (150 + 0.5 * 650 + 0.15 * 2_200))
    assert rate.iloc[0] == pytest.approx(745.34, abs=0.01)


def test_the_three_tiers_add_back_to_the_land_value():
    value, footprint, insured, area = 900_000.0, 180.0, 600.0, 1_400.0
    rate = footprint_rate(
        series(value),
        series(footprint),
        series(insured),
        series(area),
        insured_ratio=0.4,
        uninsured_ratio=0.1,
    ).iloc[0]
    total = (
        rate * footprint
        + 0.4 * rate * (insured - footprint)
        + 0.1 * rate * (area - insured)
    )
    assert total == pytest.approx(value)


def test_flat_ratios_give_the_plain_average():
    rate = footprint_rate(
        series(500_000),
        series(100),
        series(400),
        series(1_000),
        insured_ratio=1.0,
        uninsured_ratio=1.0,
    )
    assert rate.iloc[0] == pytest.approx(500.0)


def test_insured_land_short_of_the_footprint_is_taken_as_the_footprint():
    # Layers disagreeing slightly cannot leave a negative ring.
    rate = footprint_rate(series(100_000), series(200), series(150), series(200))
    assert rate.iloc[0] == pytest.approx(500.0)


@pytest.mark.parametrize(
    ("insured", "uninsured"), [(0.2, 0.5), (1.2, 0.1), (0.5, -0.1)]
)
def test_ratios_that_do_not_step_down_are_refused(insured, uninsured):
    with pytest.raises(ValueError, match="uninsured_ratio <= insured_ratio"):
        footprint_rate(
            series(1),
            series(1),
            series(1),
            series(1),
            insured_ratio=insured,
            uninsured_ratio=uninsured,
        )


# ---------------------------------------------------------------------------
# A claim not on the roll takes its suburb's median rate.
# ---------------------------------------------------------------------------


def suburb_land(rows):
    """(claim, property area, suburb) per row."""
    return pd.DataFrame(
        {
            CLAIM: [row[0] for row in rows],
            loss_contract.LAND_PROPERTY_AREA_COLUMN: [row[1] for row in rows],
            loss_contract.LAND_SUBURB_COLUMN: [row[2] for row in rows],
        }
    )


def test_a_claim_on_the_roll_keeps_its_own_value():
    land = suburb_land([("c1", 500.0, "Kelburn")])
    values = claim_land_values(land, pd.Series({"c1": 400_000.0}))
    assert values.loc["c1", LAND_VALUE_COLUMN] == pytest.approx(400_000.0)
    assert values.loc["c1", VALUE_SOURCE_COLUMN] == FROM_ROLL


def test_a_claim_off_the_roll_takes_its_suburbs_median_rate_times_its_area():
    land = suburb_land(
        [
            ("c1", 500.0, "Kelburn"),  # $800/m2
            ("c2", 1_000.0, "Kelburn"),  # $600/m2
            ("c3", 400.0, "Kelburn"),  # $1,000/m2
            ("c4", 2_000.0, "Karori"),  # $100/m2, another suburb
            ("c5", 700.0, "Kelburn"),  # not on the roll
        ]
    )
    qv = pd.Series({"c1": 400_000.0, "c2": 600_000.0, "c3": 400_000.0, "c4": 200_000.0})
    values = claim_land_values(land, qv)
    assert values.loc["c5", LAND_VALUE_COLUMN] == pytest.approx(800.0 * 700.0)
    assert values.loc["c5", VALUE_SOURCE_COLUMN] == FROM_SUBURB


def test_a_suburb_with_nothing_on_the_roll_takes_the_runs_median_rate():
    land = suburb_land(
        [
            ("c1", 500.0, "Kelburn"),
            ("c2", 1_000.0, "Karori"),
            ("c3", 200.0, "Brooklyn"),
            ("c4", 300.0, None),
        ]
    )
    values = claim_land_values(land, pd.Series({"c1": 400_000.0, "c2": 200_000.0}))
    # $800 and $200 a m2: the median is $500.
    assert values.loc["c3", LAND_VALUE_COLUMN] == pytest.approx(500.0 * 200.0)
    assert values.loc[["c3", "c4"], VALUE_SOURCE_COLUMN].tolist() == [FROM_RUN] * 2


# ---------------------------------------------------------------------------
# The damaged land is valued by the tier it lies in.
# ---------------------------------------------------------------------------


def damage_land(rows):
    """(claim, liquefied, landslide, landslide on footprint) per row, all on
    one property of 1,000 m2 with a 100 m2 footprint and 400 m2 insured."""
    return pd.DataFrame(
        {
            CLAIM: [row[0] for row in rows],
            loss_contract.LIQ_LD_AREA_COLUMN: [row[1] for row in rows],
            loss_contract.LANDSLIDE_AREA_COLUMN: [row[2] for row in rows],
            loss_contract.LANDSLIDE_FOOTPRINT_AREA_COLUMN: [row[3] for row in rows],
            loss_contract.TOTAL_INSURED_LAND_AREA_COLUMN: 400.0,
            loss_contract.LAND_FOOTPRINT_AREA_COLUMN: 100.0,
            loss_contract.LAND_PROPERTY_AREA_COLUMN: 1_000.0,
        }
    )


def rated(rows, value=280_000.0):
    land = damage_land(rows)
    claims = land[CLAIM].unique()
    values = pd.DataFrame(
        {LAND_VALUE_COLUMN: value, VALUE_SOURCE_COLUMN: FROM_ROLL},
        index=pd.Index(claims, name=CLAIM),
    )
    return damaged_land_rates(land, values)


# $280,000 over 100 + 0.5 x 300 + 0.15 x 600 = 340 weighted m2 is $823.53 at
# the footprint excluding GST.
FULL = add_gst(280_000.0 / 340.0)
INSURED_AVERAGE = FULL * (100 + 0.5 * 300) / 400


def test_liquefaction_takes_the_insured_lands_average():
    out = rated([("c1", 150.0, 0.0, 0.0)])
    assert out[FOOTPRINT_RATE_COLUMN].iloc[0] == pytest.approx(FULL)
    assert out[INSURED_RATE_COLUMN].iloc[0] == pytest.approx(INSURED_AVERAGE)
    assert out[DAMAGED_LAND_RATE_COLUMN].iloc[0] == pytest.approx(INSURED_AVERAGE)


def test_landslide_ground_under_the_house_takes_the_full_rate():
    out = rated([("c1", 0.0, 80.0, 80.0)])
    assert out[DAMAGED_LAND_RATE_COLUMN].iloc[0] == pytest.approx(FULL)


def test_landslide_ground_off_the_house_takes_the_ring_rate():
    out = rated([("c1", 0.0, 80.0, 0.0)])
    assert out[DAMAGED_LAND_RATE_COLUMN].iloc[0] == pytest.approx(0.5 * FULL)


def test_landslide_ground_partly_under_the_house_is_split_by_area():
    out = rated([("c1", 0.0, 200.0, 50.0)])
    expected = (50 * FULL + 150 * 0.5 * FULL) / 200
    assert out[DAMAGED_LAND_RATE_COLUMN].iloc[0] == pytest.approx(expected)


def test_the_larger_cause_sets_the_rate():
    out = rated([("c1", 300.0, 200.0, 50.0), ("c2", 100.0, 200.0, 200.0)])
    assert out[DAMAGED_LAND_RATE_COLUMN].tolist() == pytest.approx(
        [INSURED_AVERAGE, FULL]
    )


def test_footprint_ground_beyond_the_landslide_is_not_counted():
    out = rated([("c1", 0.0, 40.0, 60.0)])
    assert out[DAMAGED_LAND_RATE_COLUMN].iloc[0] == pytest.approx(FULL)


def test_all_the_insured_land_damaged_is_worth_its_two_tiers():
    # The footprint and the ring together: 250 of the 340 weighted m2.
    out = rated([("c1", 400.0, 0.0, 0.0)])
    insured_value = out[DAMAGED_LAND_RATE_COLUMN].iloc[0] * 400
    assert insured_value == pytest.approx(add_gst(280_000.0) * 250 / 340)


# ---------------------------------------------------------------------------
# Reading the land value off the roll.
# ---------------------------------------------------------------------------


def roll(rows):
    """(roll, assessment, land value, district, category) per unit."""
    return pd.DataFrame(
        {
            "valuation_no_roll": [row[0] for row in rows],
            "valuation_no_assessment": [row[1] for row in rows],
            "valuation_no_suffix": pd.Series([None] * len(rows), dtype=object),
            "land_value": [row[2] for row in rows],
            "district_ta_code": [row[3] for row in rows],
            "property_category": [row[4] for row in rows],
        }
    )


BASE_RATES = pd.DataFrame({"ta_code": [47], "index_to_2025_09": [0.9]})


def test_a_propertys_units_are_summed_and_indexed():
    units = roll(
        [
            ("17110", "100", 300_000.0, "47", "RD"),
            ("17110", "200", 100_000.0, "47", "RD"),
            ("17110", "300", 500_000.0, "47", "RD"),
        ]
    )
    links = pd.DataFrame(
        {
            "valuation_reference": ["17110-00100", "17110-00200", "17110-00300"],
            CLAIM: ["c1", "c1", "c2"],
        }
    )
    values = qv_land_value_by_claim(units, links, BASE_RATES)
    assert values.loc["c1", QV_LAND_VALUE_COLUMN] == pytest.approx(360_000.0)
    assert values.loc["c1", QV_UNITS_COLUMN] == 2
    assert values.loc["c2", QV_LAND_VALUE_COLUMN] == pytest.approx(450_000.0)


def test_a_unit_on_two_properties_leaves_both_out():
    units = roll([("17110", "100", 300_000.0, "47", "RD")])
    links = pd.DataFrame(
        {"valuation_reference": ["17110-00100"] * 2, CLAIM: ["c1", "c2"]}
    )
    assert qv_land_value_by_claim(units, links, BASE_RATES).empty


def test_a_unit_with_no_value_leaves_its_property_out():
    units = roll(
        [
            ("17110", "100", 300_000.0, "47", "RD"),
            ("17110", "200", np.nan, "47", "RD"),
        ]
    )
    links = pd.DataFrame(
        {"valuation_reference": ["17110-00100", "17110-00200"], CLAIM: ["c1", "c1"]}
    )
    assert qv_land_value_by_claim(units, links, BASE_RATES).empty
