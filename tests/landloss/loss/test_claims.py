import numpy as np
import pandas as pd
import pytest

from landloss.domain import loss_contract
from landloss.exposure.land import extent
from landloss.loss.claims import (
    CLAIM_ID_COLUMN,
    DAMAGED_AREA_COLUMN,
    DWELLING_COUNT_COLUMN,
    LAND_RATE_COLUMN,
    damaged_area_m2,
    damaged_walls,
    dwelling_counts,
    land_by_claim,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.settlement import DamagedClaim, settle

ACT = PolicySettings()


def property_table(counts):
    return pd.DataFrame(
        {
            CLAIM_ID_COLUMN: list(counts),
            DWELLING_COUNT_COLUMN: list(counts.values()),
        }
    )


# ---------------------------------------------------------------------------
# The contract with exposure. The four top-level modules exchange data files
# rather than symbols, so the column names are written out in both places --
# which is exactly why something has to hold them to each other.
# ---------------------------------------------------------------------------


def test_the_column_names_match_what_exposure_writes():
    assert CLAIM_ID_COLUMN == extent.CLAIM_ID_COLUMN
    assert DWELLING_COUNT_COLUMN == extent.DWELLING_COUNT_COLUMN


# ---------------------------------------------------------------------------
# Reading the count.
# ---------------------------------------------------------------------------


def test_counts_come_back_in_the_order_asked_for():
    # Not the order of the property table: the result has to line up with the
    # other arrays the caller is settling.
    table = property_table({"c1": 1, "c2": 4, "c3": 2})
    assert dwelling_counts(["c3", "c1", "c2"], table) == pytest.approx([2.0, 1.0, 4.0])


def test_a_claim_can_be_asked_for_more_than_once():
    table = property_table({"c1": 3})
    assert dwelling_counts(["c1", "c1"], table) == pytest.approx([3.0, 3.0])


def test_properties_not_asked_for_are_ignored():
    table = property_table({"c1": 1, "c2": 9})
    assert dwelling_counts(["c1"], table) == pytest.approx([1.0])


def test_counts_come_back_as_floats_for_the_sub_cap_arithmetic():
    counts = dwelling_counts(["c1"], property_table({"c1": 2}))
    assert counts.dtype == float


def test_an_empty_request_gives_an_empty_result():
    assert len(dwelling_counts([], property_table({"c1": 1}))) == 0


# ---------------------------------------------------------------------------
# What it refuses. Each of these would otherwise reach `settle` as a silently
# wrong multiplier on both sub-caps and the excess.
# ---------------------------------------------------------------------------


def test_a_claim_with_no_count_is_refused_rather_than_defaulted():
    table = property_table({"c1": 1})
    with pytest.raises(ValueError, match="no dwelling count for 'c9'"):
        dwelling_counts(["c1", "c9"], table)


def test_the_refusal_names_the_claims_and_stops_at_five():
    table = property_table({"c1": 1})
    missing = [f"m{i}" for i in range(8)]
    with pytest.raises(ValueError, match="and 3 more"):
        dwelling_counts(missing, table)


def test_a_duplicated_claim_is_refused_as_ambiguous():
    table = pd.DataFrame({CLAIM_ID_COLUMN: ["c1", "c1"], DWELLING_COUNT_COLUMN: [1, 4]})
    with pytest.raises(ValueError, match="more than once"):
        dwelling_counts(["c1"], table)


def test_a_count_below_one_is_refused():
    with pytest.raises(ValueError, match="below one"):
        dwelling_counts(["c1"], property_table({"c1": 0}))


def test_a_missing_column_is_refused():
    table = property_table({"c1": 1}).rename(columns={DWELLING_COUNT_COLUMN: "n"})
    with pytest.raises(ValueError, match="no 'dwelling_count' column"):
        dwelling_counts(["c1"], table)


# ---------------------------------------------------------------------------
# End to end: the count reaches the settlement it is supposed to scale.
# ---------------------------------------------------------------------------


def test_the_count_feeds_straight_into_a_settlement():
    table = property_table({"c1": 1, "c2": 4})
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=np.array([500_000.0, 500_000.0]),
            damaged_area_m2=np.array([0.0, 0.0]),
            land_rate_incl_gst_nzd_per_m2=750.0,
            retaining_wall_udv_incl_gst_nzd=np.array([300_000.0, 300_000.0]),
            n_dwellings=dwelling_counts(["c1", "c2"], table),
        ),
        policy=ACT,
    )
    # Four dwellings carry four times the wall sub-cap, and an excess of
    # $2,000 rather than $500.
    assert result.land_cover_cap_nzd == pytest.approx([57_500.0, 230_000.0])
    assert result.excess_nzd == pytest.approx([500.0, 2_000.0])
    assert list(result.retaining_wall_sub_cap_bound) == [True, True]


def test_the_sub_caps_and_the_excess_scale_with_dwellings():
    # The dwelling count reaches both sub-caps and the excess, which is $500 a
    # dwelling and stops growing at ten.
    table = property_table({"c1": 20})
    counts = dwelling_counts(["c1"], table)
    assert ACT.retaining_wall_limit_nzd(counts) == pytest.approx(20 * 57_500.0)
    assert ACT.excess_nzd(6_000.0, counts) == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# Bringing vul's tables onto the claim. The damaged area is assembled from two
# causes that are measured differently, which is where the reading lives.
# ---------------------------------------------------------------------------


def land_table(rows):
    """Build a land table from (claim, liquefied area, total area, landslide
    area, market rate, dwellings)."""
    return pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [row[0] for row in rows],
            loss_contract.LIQ_LD_AREA_COLUMN: [row[1] for row in rows],
            loss_contract.TOTAL_INSURED_LAND_AREA_COLUMN: [row[2] for row in rows],
            loss_contract.LANDSLIDE_AREA_COLUMN: [row[3] for row in rows],
            loss_contract.MARKET_VALUE_COLUMN: [row[4] for row in rows],
            DWELLING_COUNT_COLUMN: [row[5] for row in rows],
        }
    )


def test_liquefaction_damages_the_area_vul_sends_not_the_whole_polygon():
    land = land_table([("c1", 180.0, 500.0, 0.0, 750.0, 1)])
    assert damaged_area_m2(land).tolist() == [180.0]


def test_a_missing_liquefied_area_is_no_damage():
    land = land_table(
        [("c1", 0.0, 500.0, 0.0, 750.0, 1), ("c2", np.nan, 500.0, 0.0, 750.0, 1)]
    )
    assert damaged_area_m2(land).tolist() == [0.0, 0.0]


def test_the_two_causes_are_combined_with_a_maximum_not_a_sum():
    # Ground both liquefied and buried is one piece of damaged ground. Adding
    # would value the overlap twice, which on this row would give 500.
    land = land_table([("c1", 300.0, 500.0, 200.0, 750.0, 1)])
    assert damaged_area_m2(land).tolist() == [300.0]


def test_landslide_alone_is_the_damaged_area_where_nothing_liquefied():
    land = land_table([("c1", 0.0, 500.0, 200.0, 750.0, 1)])
    assert damaged_area_m2(land).tolist() == [200.0]


def test_the_polygons_of_a_claim_have_their_damaged_areas_added():
    land = land_table(
        [("c1", 0.0, 500.0, 100.0, 750.0, 1), ("c1", 0.0, 500.0, 300.0, 750.0, 1)]
    )
    claims = land_by_claim(land)
    assert claims.loc["c1", DAMAGED_AREA_COLUMN] == pytest.approx(400.0)


def test_the_rate_is_weighted_by_the_damaged_area_it_values():
    # 100 m2 at $1,000 and 300 m2 at $500 is $250,000 over 400 m2, so the one
    # rate that values the claim the same is $625 -- not the plain mean of $750.
    land = land_table(
        [("c1", 0.0, 500.0, 100.0, 1000.0, 1), ("c1", 0.0, 500.0, 300.0, 500.0, 1)]
    )
    claims = land_by_claim(land)
    assert claims.loc["c1", LAND_RATE_COLUMN] == pytest.approx(625.0)
    area = claims.loc["c1", DAMAGED_AREA_COLUMN]
    assert area * claims.loc["c1", LAND_RATE_COLUMN] == pytest.approx(250_000.0)


def test_a_claim_with_no_damaged_ground_falls_back_to_the_plain_rate():
    land = land_table([("c1", 0.0, 500.0, 0.0, 800.0, 1)])
    claims = land_by_claim(land)
    assert claims.loc["c1", DAMAGED_AREA_COLUMN] == 0.0
    assert claims.loc["c1", LAND_RATE_COLUMN] == pytest.approx(800.0)


def test_polygons_disagreeing_about_the_dwelling_count_are_refused():
    land = land_table(
        [("c1", 0.0, 500.0, 0.0, 750.0, 1), ("c1", 0.0, 500.0, 0.0, 750.0, 4)]
    )
    with pytest.raises(ValueError, match="disagree about the dwelling count"):
        land_by_claim(land)


def test_the_aggregated_land_table_can_supply_its_own_dwelling_counts():
    # The land table carries the count the contract sends, so the reader that
    # validates it works against this frame as well as against exposure's.
    land = land_table([("c1", 300.0, 500.0, 0.0, 750.0, 2)])
    claims = land_by_claim(land)
    assert dwelling_counts(claims.index.to_numpy(), claims.reset_index()) == [2.0]


# ---------------------------------------------------------------------------
# Which walls a cap has to count.
# ---------------------------------------------------------------------------


def wall_table(flags):
    """Build a wall table from (shaking, evacuated, inundated) triples."""
    return pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [f"c{number}" for number in range(len(flags))],
            loss_contract.IS_DAMAGED_BY_SHAKING_COLUMN: [row[0] for row in flags],
            loss_contract.IS_EVACUATED_COLUMN: [row[1] for row in flags],
            loss_contract.IS_INUNDATED_COLUMN: [row[2] for row in flags],
        }
    )


def test_any_damage_flag_keeps_a_wall():
    walls = wall_table(
        [(True, False, False), (False, True, False), (False, False, True)]
    )
    assert len(damaged_walls(walls)) == 3


def test_an_undamaged_wall_is_dropped_rather_than_priced_at_zero():
    walls = wall_table([(False, False, False), (True, False, False)])
    kept = damaged_walls(walls)
    assert kept[CLAIM_ID_COLUMN].tolist() == ["c1"]


def test_a_wall_damaged_three_ways_is_still_one_wall():
    walls = wall_table([(True, True, True)])
    assert len(damaged_walls(walls)) == 1
