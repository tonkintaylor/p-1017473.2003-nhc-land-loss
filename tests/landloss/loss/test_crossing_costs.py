"""Tests for pricing damaged culverts and bridges, and summing them per claim."""

import numpy as np
import pandas as pd
import pytest

from landloss.loss.claims import (
    CROSSING_REPAIR_COLUMN,
    CROSSING_UDV_COLUMN,
    CROSSINGS_CLEARED_COLUMN,
    CROSSINGS_REPLACED_COLUMN,
    crossing_costs_by_claim,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    crossing_clearing_cost_incl_gst_nzd,
    crossing_replacement_cost_incl_gst_nzd,
)

POLICY = PolicySettings()
REPLACEMENT = 75_000.0 * 1.15
CLEARING = 1_000.0 * 1.15


def culverts(rows):
    """(claim, is_damaged, is_evacuated, is_inundated) per culvert."""
    return pd.DataFrame(
        rows, columns=["claim_id", "is_damaged", "is_evacuated", "is_inundated"]
    )


def bridges(rows):
    """(claim, is_damaged_by_shaking, is_evacuated, is_inundated) per bridge."""
    return pd.DataFrame(
        rows,
        columns=["claim_id", "is_damaged_by_shaking", "is_evacuated", "is_inundated"],
    )


NO_BRIDGES = bridges([])


# --- the prices ------------------------------------------------------------------


def test_a_replacement_is_fifteen_thousand_a_metre_over_five_metres():
    assert float(crossing_replacement_cost_incl_gst_nzd(policy=POLICY)) == (
        pytest.approx(REPLACEMENT)
    )


def test_a_known_span_takes_the_place_of_the_default():
    cost = crossing_replacement_cost_incl_gst_nzd(
        np.array([8.0, np.nan]), policy=POLICY
    )
    assert cost == pytest.approx([15_000 * 8 * 1.15, REPLACEMENT])


def test_a_negative_span_is_refused():
    with pytest.raises(ValueError, match="span_m"):
        crossing_replacement_cost_incl_gst_nzd(-1.0, policy=POLICY)


def test_a_clearing_is_a_thousand_dollars():
    assert crossing_clearing_cost_incl_gst_nzd(policy=POLICY) == pytest.approx(CLEARING)


# --- which remedy, and the claim's sum ---------------------------------------------


def test_a_culvert_broken_by_liquefaction_is_replaced():
    costs = crossing_costs_by_claim(
        culverts([("c1", True, False, False)]), NO_BRIDGES, policy=POLICY
    )
    assert costs.loc["c1", CROSSING_REPAIR_COLUMN] == pytest.approx(REPLACEMENT)
    assert costs.loc["c1", CROSSINGS_REPLACED_COLUMN] == 1


def test_a_crossing_whose_ground_went_is_replaced():
    costs = crossing_costs_by_claim(
        culverts([]), bridges([("c1", False, True, False)]), policy=POLICY
    )
    assert costs.loc["c1", CROSSING_REPAIR_COLUMN] == pytest.approx(REPLACEMENT)


def test_a_crossing_only_buried_is_cleared():
    costs = crossing_costs_by_claim(
        culverts([("c1", False, False, True)]), NO_BRIDGES, policy=POLICY
    )
    assert costs.loc["c1", CROSSING_REPAIR_COLUMN] == pytest.approx(CLEARING)
    assert costs.loc["c1", CROSSINGS_CLEARED_COLUMN] == 1


def test_a_crossing_broken_and_buried_is_replaced_and_not_cleared_too():
    costs = crossing_costs_by_claim(
        culverts([("c1", True, False, True)]), NO_BRIDGES, policy=POLICY
    )
    assert costs.loc["c1", CROSSING_REPAIR_COLUMN] == pytest.approx(REPLACEMENT)
    assert costs.loc["c1", CROSSINGS_CLEARED_COLUMN] == 0


def test_a_cleared_crossing_is_still_worth_its_replacement():
    costs = crossing_costs_by_claim(
        culverts([("c1", False, False, True)]), NO_BRIDGES, policy=POLICY
    )
    assert costs.loc["c1", CROSSING_UDV_COLUMN] == pytest.approx(REPLACEMENT)


def test_a_claims_crossings_are_summed_across_both_tables():
    costs = crossing_costs_by_claim(
        culverts([("c1", True, False, False), ("c1", False, False, True)]),
        bridges([("c1", True, False, False)]),
        policy=POLICY,
    )
    assert costs.loc["c1", CROSSING_REPAIR_COLUMN] == pytest.approx(
        2 * REPLACEMENT + CLEARING
    )
    assert costs.loc["c1", CROSSING_UDV_COLUMN] == pytest.approx(3 * REPLACEMENT)


def test_an_undamaged_crossing_costs_nothing_and_is_left_out():
    costs = crossing_costs_by_claim(
        culverts([("c1", False, False, False)]), NO_BRIDGES, policy=POLICY
    )
    assert costs.empty


def test_no_crossings_at_all_gives_an_empty_table_with_the_columns():
    costs = crossing_costs_by_claim(culverts([]), NO_BRIDGES, policy=POLICY)
    assert costs.empty
    assert CROSSING_REPAIR_COLUMN in costs.columns
