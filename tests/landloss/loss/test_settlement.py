import numpy as np
import pytest

from landloss.loss.policy import PolicySettings
from landloss.loss.settlement import (
    DamagedClaim,
    area_cap_bound,
    damaged_land_value_nzd,
    land_cover_cap_nzd,
    settle,
    structure_contribution_nzd,
)

# One dwelling, current Act. The explainer works all three of its examples on
# these settings, so they are the baseline the worked-example tests run against.
ACT = PolicySettings()

# The explainer states a flat "$500 per dwelling, capped at $5,000" and works
# all three of its examples that way, which is what `PolicySettings` defaults
# to. Virginie Lacrosse described 10% of what is payable, per claim, and the two
# disagree by $4,500 on the explainer's own first example (**Q-12**). The worked
# examples are run against the explainer's rule by name because that is the
# document they come from; the rate is exercised separately below.
EXPLAINER = PolicySettings(excess_per_dwelling_nzd=500.0)
BY_RATE = PolicySettings(excess_per_dwelling_nzd=None)

# $50,000 + GST, the applicable retaining wall limit for a single dwelling. The
# explainer states this figure, which is what pins the GST rate at 15%.
ONE_DWELLING_WALL_LIMIT = 57_500.0

# The claim the explainer's Examples 2 and 3 share: 60 m2 of damaged land
# assessed at $45,000, on a single-dwelling property. Only the wall differs.
DAMAGED_LAND_NZD = 45_000.0

# The same claim as an area and a rate, which is how it now arrives: the
# explainer states both the 60 m2 and the $45,000, so the rate follows.
DAMAGED_LAND_M2 = 60.0
LAND_RATE_NZD_PER_M2 = DAMAGED_LAND_NZD / DAMAGED_LAND_M2


# ---------------------------------------------------------------------------
# The three worked examples in .agents/context/nhi-act-land-cover-explainer.md.
# These are the only fully specified settlements the study has, so they are the
# primary check on the arithmetic rather than one check among several.
# ---------------------------------------------------------------------------


def test_worked_example_1_wall_only_settles_on_the_sub_cap():
    # Substantial cracking to a wall, no damage to the insured land areas. The
    # wall's $70,000 undepreciated value exceeds the limit, so the limit is what
    # it contributes, and the repair cost is far above that.
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=120_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=70_000.0,
            n_dwellings=1,
        ),
        policy=EXPLAINER,
    )
    assert result.land_cover_cap_nzd == pytest.approx(ONE_DWELLING_WALL_LIMIT)
    assert result.settlement_nzd == pytest.approx(ONE_DWELLING_WALL_LIMIT - 500.0)
    assert result.capped


def test_worked_example_2_land_and_wall_settle_on_the_cap():
    # The same $70,000 wall, now with $45,000 of damaged land. The cap is the
    # sum of the two contributions, and the $210,000 repair cost is above it.
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=210_000.0,
            damaged_area_m2=DAMAGED_LAND_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=70_000.0,
            n_dwellings=1,
        ),
        policy=EXPLAINER,
    )
    assert result.land_cover_cap_nzd == pytest.approx(102_500.0)
    assert result.settlement_nzd == pytest.approx(102_000.0)
    assert result.capped


def test_worked_example_3_a_modest_wall_settles_on_the_repair_cost():
    # Same land, but a timber pole wall worth $30,000 new. The sub-cap is
    # irrelevant because the undepreciated value is below it, and the repair
    # cost now falls under the cap, so the repair cost is what is paid.
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=58_000.0,
            damaged_area_m2=DAMAGED_LAND_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=30_000.0,
            n_dwellings=1,
        ),
        policy=EXPLAINER,
    )
    assert result.land_cover_cap_nzd == pytest.approx(75_000.0)
    assert result.settlement_nzd == pytest.approx(57_500.0)
    assert not result.capped


# ---------------------------------------------------------------------------
# The misreadings the module exists to prevent.
# ---------------------------------------------------------------------------


def test_a_sub_cap_limits_the_contribution_not_the_settlement():
    # Example 2 settles at $102,000, well above the $57,500 wall sub-cap. Read
    # as a ceiling on the payout, the sub-cap would have held this to $57,500.
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=210_000.0,
            damaged_area_m2=DAMAGED_LAND_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=70_000.0,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.settlement_nzd > ONE_DWELLING_WALL_LIMIT


def test_a_modest_wall_never_reaches_its_sub_cap():
    contribution = structure_contribution_nzd(30_000.0, ONE_DWELLING_WALL_LIMIT)
    assert contribution == pytest.approx(30_000.0)


def test_the_sub_caps_are_grossed_up_for_gst():
    assert ACT.retaining_wall_limit_nzd(1) == pytest.approx(57_500.0)
    assert ACT.bridge_culvert_limit_nzd(1) == pytest.approx(28_750.0)


def test_the_sub_caps_multiply_by_dwellings():
    # The explainer's own illustration: five dwellings give $250,000 + GST.
    assert ACT.retaining_wall_limit_nzd(5) == pytest.approx(250_000.0 * 1.15)


# ---------------------------------------------------------------------------
# The excess.
# ---------------------------------------------------------------------------


def test_the_act_defaults_to_the_explainers_rule():
    assert ACT.excess_per_dwelling_nzd == pytest.approx(500.0)
    assert ACT.excess_nzd(6_000.0, 1) == pytest.approx(EXPLAINER.excess_nzd(6_000.0))


def test_the_excess_is_500_per_dwelling():
    # A flat amount per dwelling, taking no notice of how much is payable.
    assert ACT.excess_nzd(1_000.0, 1) == pytest.approx(500.0)
    assert ACT.excess_nzd(60_000.0, 1) == pytest.approx(500.0)
    assert ACT.excess_nzd(6_000.0, 4) == pytest.approx(2_000.0)


def test_the_excess_stops_growing_at_ten_dwellings():
    assert ACT.excess_nzd(6_000.0, 10) == pytest.approx(5_000.0)
    assert ACT.excess_nzd(6_000.0, 29) == pytest.approx(5_000.0)


def test_a_claim_paid_nothing_is_charged_no_excess():
    # Otherwise an undamaged claim acquires a $500 debt.
    assert ACT.excess_nzd(0.0) == pytest.approx(0.0)
    assert ACT.excess_nzd(0.0, 4) == pytest.approx(0.0)
    assert BY_RATE.excess_nzd(0.0) == pytest.approx(0.0)


def test_the_rate_rule_is_still_available_and_is_per_claim():
    # The two contradict each other (**Q-12**), so both can be run. Virginie
    # Lacrosse's own examples: $1,000 of damage takes the $500 floor because
    # 10% of it is less, and $6,000 takes 10%, which is $600.
    assert BY_RATE.excess_nzd(1_000.0) == pytest.approx(500.0)
    assert BY_RATE.excess_nzd(6_000.0) == pytest.approx(600.0)
    # One excess per claim, whatever the dwelling count.
    assert BY_RATE.excess_nzd(6_000.0, 29) == pytest.approx(600.0)
    # And it stops growing at $50,000 payable.
    assert BY_RATE.excess_nzd(50_000.0) == pytest.approx(5_000.0)
    assert BY_RATE.excess_nzd(500_000.0) == pytest.approx(5_000.0)


def test_a_negative_excess_per_dwelling_is_refused():
    with pytest.raises(ValueError, match="excess_per_dwelling_nzd"):
        PolicySettings(excess_per_dwelling_nzd=-1.0)


def test_a_claim_below_the_excess_settles_at_nothing_rather_than_owing():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=300.0,
            damaged_area_m2=10_000.0 / LAND_RATE_NZD_PER_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.settlement_nzd == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# The total cap, which is the setting under test rather than current law.
# ---------------------------------------------------------------------------


def test_the_current_act_has_no_total_cap():
    assert ACT.total_cap_nzd is None


def test_a_total_cap_binds_before_the_excess():
    claim = DamagedClaim(
        repair_cost_incl_gst_nzd=210_000.0,
        damaged_area_m2=DAMAGED_LAND_M2,
        land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
        retaining_wall_udv_incl_gst_nzd=70_000.0,
        n_dwellings=1,
    )
    result = settle(claim, policy=PolicySettings(total_cap_nzd=80_000.0))
    # Example 2's $102,500 cap, cut to the total cap, then the excess.
    assert result.land_cover_cap_nzd == pytest.approx(80_000.0)
    assert result.settlement_nzd == pytest.approx(80_000.0 - ACT.excess_nzd(80_000.0))


def test_a_generous_total_cap_changes_nothing():
    claim = DamagedClaim(
        repair_cost_incl_gst_nzd=210_000.0,
        damaged_area_m2=DAMAGED_LAND_M2,
        land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
        retaining_wall_udv_incl_gst_nzd=70_000.0,
        n_dwellings=1,
    )
    under_act = settle(claim, policy=ACT)
    under_cap = settle(claim, policy=PolicySettings(total_cap_nzd=10_000_000.0))
    assert under_cap.settlement_nzd == pytest.approx(under_act.settlement_nzd)


# ---------------------------------------------------------------------------
# Whole portfolios, and inputs that should be refused.
# ---------------------------------------------------------------------------


def test_a_portfolio_settles_in_one_call():
    # The three worked examples, settled together.
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=np.array([120_000.0, 210_000.0, 58_000.0]),
            damaged_area_m2=np.array([0.0, DAMAGED_LAND_M2, DAMAGED_LAND_M2]),
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=np.array([70_000.0, 70_000.0, 30_000.0]),
            n_dwellings=np.array([1.0, 1.0, 1.0]),
        ),
        policy=ACT,
    )
    payable = [57_500.0, 102_500.0, 58_000.0]
    assert result.settlement_nzd == pytest.approx(
        [amount - ACT.excess_nzd(amount) for amount in payable]
    )
    assert result.capped.tolist() == [True, True, False]


def test_bridges_and_culverts_add_their_own_contribution():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=500_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            bridge_culvert_udv_incl_gst_nzd=90_000.0,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.bridge_culvert_contribution_nzd == pytest.approx(28_750.0)
    assert result.land_cover_cap_nzd == pytest.approx(28_750.0)


def test_undamaged_structures_contribute_nothing():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=20_000.0,
            damaged_area_m2=DAMAGED_LAND_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.retaining_wall_contribution_nzd == pytest.approx(0.0)
    assert result.land_cover_cap_nzd == pytest.approx(DAMAGED_LAND_NZD)


def test_a_missing_dwelling_count_is_refused_rather_than_read_as_no_cover():
    with pytest.raises(ValueError, match="n_dwellings"):
        settle(
            DamagedClaim(
                repair_cost_incl_gst_nzd=10_000.0,
                damaged_area_m2=10_000.0 / LAND_RATE_NZD_PER_M2,
                land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
                n_dwellings=0,
            ),
            policy=ACT,
        )


def test_negative_amounts_are_refused():
    with pytest.raises(ValueError, match="repair_cost_incl_gst_nzd"):
        settle(
            DamagedClaim(
                repair_cost_incl_gst_nzd=-1.0,
                damaged_area_m2=10_000.0 / LAND_RATE_NZD_PER_M2,
                land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
                n_dwellings=1,
            ),
            policy=ACT,
        )


def test_a_cap_can_be_computed_without_settling():
    cap = land_cover_cap_nzd(
        land_value_incl_gst_nzd=damaged_land_value_nzd(
            DAMAGED_LAND_M2, LAND_RATE_NZD_PER_M2, policy=ACT
        ),
        retaining_wall_udv_incl_gst_nzd=70_000.0,
        n_dwellings=1,
        policy=ACT,
    )
    assert cap == pytest.approx(102_500.0)


# ---------------------------------------------------------------------------
# Which constraint bound. The study reports the share of claims binding on
# each, so each has to be readable off a settled claim rather than
# reconstructed from the total.
# ---------------------------------------------------------------------------


def test_the_sub_cap_binds_when_the_wall_is_worth_more_than_the_limit():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=120_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=70_000.0,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.retaining_wall_sub_cap_bound
    assert result.retaining_wall_contribution_nzd == pytest.approx(
        ONE_DWELLING_WALL_LIMIT
    )


def test_the_sub_cap_does_not_bind_on_a_modest_wall():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=58_000.0,
            damaged_area_m2=DAMAGED_LAND_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=30_000.0,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert not result.retaining_wall_sub_cap_bound
    assert result.retaining_wall_contribution_nzd == pytest.approx(30_000.0)


def test_a_wall_worth_exactly_the_limit_does_not_bind():
    # At the limit the sub-cap took nothing away, so it did not bind. Strict,
    # matching `capped`. The limit is taken from the policy rather than written
    # as 57_500.0, because $50,000 grossed up by 15% lands a whole float step
    # below that, and this test is about the boundary rather than about how the
    # boundary is represented.
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=120_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=ACT.retaining_wall_limit_nzd(1),
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert not result.retaining_wall_sub_cap_bound


def test_an_undamaged_structure_never_binds():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=10_000.0,
            damaged_area_m2=DAMAGED_LAND_M2,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert not result.retaining_wall_sub_cap_bound
    assert not result.bridge_culvert_sub_cap_bound


def test_the_sub_cap_flag_is_not_recoverable_from_the_contribution():
    # A wall bound at the limit and a wall worth exactly the limit give the
    # same contribution, which is why the flag is carried rather than derived.
    bound = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=120_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=70_000.0,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    exactly = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=120_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=ACT.retaining_wall_limit_nzd(1),
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert bound.retaining_wall_contribution_nzd == pytest.approx(
        exactly.retaining_wall_contribution_nzd
    )
    assert bound.retaining_wall_sub_cap_bound
    assert not exactly.retaining_wall_sub_cap_bound


def test_a_wall_only_claim_settles_on_the_undepreciated_value():
    # Below the sub-cap the undepreciated value passes straight through to the
    # settlement, less the excess: the repair cost never enters, because the
    # cap is below it by construction.
    udv = 30_000.0
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=90_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=udv,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert not result.retaining_wall_sub_cap_bound
    assert result.settlement_nzd == pytest.approx(udv - ACT.excess_nzd(udv))


def test_the_sub_cap_flags_come_back_per_claim_across_a_portfolio():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=np.array([120_000.0, 58_000.0]),
            damaged_area_m2=np.array([0.0, DAMAGED_LAND_M2]),
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=np.array([70_000.0, 30_000.0]),
            n_dwellings=np.array([1.0, 1.0]),
        ),
        policy=ACT,
    )
    assert list(result.retaining_wall_sub_cap_bound) == [True, False]


# ---------------------------------------------------------------------------
# The area cap. Damaged land is valued over the lesser of the damaged area and
# the cap, so damage beyond it is valued as though it stopped there.
# ---------------------------------------------------------------------------


def test_land_under_the_cap_is_valued_at_its_whole_area():
    assert damaged_land_value_nzd(
        DAMAGED_LAND_M2, LAND_RATE_NZD_PER_M2, policy=ACT
    ) == pytest.approx(DAMAGED_LAND_NZD)


def test_land_beyond_the_cap_is_valued_as_though_it_stopped_there():
    # Ten times the cap is valued at the cap: the rate is unchanged, the area
    # is what the Act limits.
    value = damaged_land_value_nzd(40_000.0, LAND_RATE_NZD_PER_M2, policy=ACT)
    assert value == pytest.approx(ACT.area_cap_m2 * LAND_RATE_NZD_PER_M2)


def test_the_area_cap_is_four_thousand_square_metres_by_default():
    assert ACT.area_cap_m2 == pytest.approx(4_000.0)


def test_the_area_cap_binds_only_above_the_cap():
    assert not area_cap_bound(DAMAGED_LAND_M2, policy=ACT)
    assert not area_cap_bound(ACT.area_cap_m2, policy=ACT)
    assert area_cap_bound(ACT.area_cap_m2 + 1.0, policy=ACT)


def test_a_district_plan_minimum_below_four_thousand_binds_sooner():
    # The cap is the lesser of the district plan minimum and 4,000 m2, so a
    # scenario carrying a smaller minimum values less of the same damage.
    small_site = PolicySettings(area_cap_m2=500.0)
    assert damaged_land_value_nzd(
        800.0, LAND_RATE_NZD_PER_M2, policy=small_site
    ) == pytest.approx(500.0 * LAND_RATE_NZD_PER_M2)
    assert area_cap_bound(800.0, policy=small_site)


def test_settle_reports_the_land_value_and_whether_the_area_cap_bound():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=10_000_000.0,
            damaged_area_m2=40_000.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.area_cap_bound
    assert result.damaged_land_value_nzd == pytest.approx(
        ACT.area_cap_m2 * LAND_RATE_NZD_PER_M2
    )
    # The cap is the land value alone here, no structures being damaged.
    assert result.land_cover_cap_nzd == pytest.approx(result.damaged_land_value_nzd)


def test_a_claim_with_no_damaged_land_values_at_nothing():
    result = settle(
        DamagedClaim(
            repair_cost_incl_gst_nzd=120_000.0,
            damaged_area_m2=0.0,
            land_rate_incl_gst_nzd_per_m2=LAND_RATE_NZD_PER_M2,
            retaining_wall_udv_incl_gst_nzd=70_000.0,
            n_dwellings=1,
        ),
        policy=ACT,
    )
    assert result.damaged_land_value_nzd == pytest.approx(0.0)
    assert not result.area_cap_bound


def test_a_negative_damaged_area_is_refused():
    with pytest.raises(ValueError, match="damaged_area_m2 must be finite"):
        damaged_land_value_nzd(-1.0, LAND_RATE_NZD_PER_M2, policy=ACT)
