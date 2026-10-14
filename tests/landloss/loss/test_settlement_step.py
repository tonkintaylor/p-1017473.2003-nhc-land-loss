"""The settlement step's own arithmetic, where it is not in the library.

`land_repair_by_claim` lives in `src/scripts` because it orchestrates rather
than calculates, but the rule it encodes is a policy decision worth pinning
down: **each separate slip is held by one wall** (T-124). A slip that came
with a wall is held by that wall's replacement; any other slip gets a new wall
of its own, even beside a wall that failed elsewhere. Ground of unknown origin,
from a land table that lists no failures, is pooled as one slip and held as
before: by the claim's largest damaged wall, or one new wall.

**A replacement keeps the wall's own height, type and size class, and takes its
length from the margin rule** (2026-10-14): the damaged length plus 1 m at each
end, at least 3 m, worked once per wall and shared over its pieces. A slip does
not enlarge it.
"""

import numpy as np
import pandas as pd
import pytest

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_AREAS_COLUMN,
    LANDSLIDE_EVACUATED_AREAS_COLUMN,
    LANDSLIDE_IDS_COLUMN,
    LANDSLIDE_INUNDATED_AREAS_COLUMN,
    LANDSLIDE_INUNDATED_DEPTHS_COLUMN,
    LANDSLIDE_RW_IDS_COLUMN,
    LANDSLIDE_WALL_HEIGHTS_COLUMN,
    LANDSLIDE_WALL_LENGTHS_COLUMN,
    LANDSLIDE_WALL_SOURCES_COLUMN,
    LIQ_LD_COST_COLUMN,
    RW_DAMAGED_LENGTH_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    RW_TYPE_COLUMN,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    LANDSLIDE_WALL_MARGIN_M,
    LIQ_COST_ESCALATION,
    MIN_LANDSLIDE_WALL_LENGTH_M,
    beta_wall_height_m,
    landslide_wall_length_m,
    margin_rule_length_m,
    timber_pole_rate_excl_gst_nzd_per_m2,
    wall_type_rate_excl_gst_nzd_per_m2,
)
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    ACCESS_COLUMN,
    CONSTRUCTABILITY_COLUMN,
    EARTHWORKS_COLUMN,
    LAND_REPAIR_COLUMN,
    LANDSLIDE_REPAIR_AREA_COLUMN,
    NEW_WALL_COUNT_COLUMN,
    NEW_WALL_FACE_COLUMN,
    NEW_WALL_FROM_MAPPED_COLUMN,
    NEW_WALL_LENGTH_COLUMN,
    NEW_WALL_SIZE_COLUMN,
    REPLACEMENT_WALL_FACE_COLUMN,
    REPLACEMENT_WALL_LENGTH_COLUMN,
    REPLACEMENT_WALL_RATE_COLUMN,
    REPLACEMENT_WALL_SIZE_COLUMN,
    SYNTHETIC_WALL_COLUMN,
    WALL_REPAIR_COLUMN,
    attach_failures_to_walls,
    describe_failures,
    land_repair_by_claim,
    landslide_failures,
    liquefaction_repair_by_claim,
    replacement_wall_shape,
    spoil_by_claim,
    wall_repair_by_claim,
)

CLAIM = "claim-1"
NO_WALLS = pd.Index([], dtype=object)
HAS_A_WALL = pd.Index([CLAIM])


def land_with(area_m2: float) -> pd.DataFrame:
    """Return one claim carrying the given landslide ground."""
    return pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [CLAIM],
            LANDSLIDE_AREA_COLUMN: [area_m2],
            INUNDATED_AREA_COLUMN: [min(area_m2, 10.0)],
            INUNDATED_MEAN_DEPTH_COLUMN: [0.3],
        }
    )


@pytest.fixture
def land() -> pd.DataFrame:
    """One claim with 40 m2 of landslide ground and a shallow deposit."""
    return land_with(40.0)


@pytest.fixture
def ratings() -> pd.DataFrame:
    """An easy site, so the multiplier does not move between cases."""
    return pd.DataFrame(
        {
            ACCESS_COLUMN: ["E"],
            EARTHWORKS_COLUMN: ["E"],
            CONSTRUCTABILITY_COLUMN: ["E"],
        },
        index=pd.Index([CLAIM], name=CLAIM_ID_COLUMN),
    )


def repair(land, ratings, *, walled: pd.Index) -> pd.DataFrame:
    """Hold the claim's land, given whether its own wall is being replaced.

    The land here lists no separate failures, so the claim's ground is pooled
    as one slip of unknown origin, held by the claim's wall where it has one.
    """
    rw = walls(("medium", 9.6)) if len(walled) else walls()
    return land_repair_by_claim(
        land,
        ratings,
        failures=landslide_failures(land),
        rw=rw,
        policy=PolicySettings(),
    )


def test_a_claim_with_no_wall_gets_one_invented(land, ratings):
    out = repair(land, ratings, walled=NO_WALLS)
    assert out.loc[CLAIM, SYNTHETIC_WALL_COLUMN]
    assert out.loc[CLAIM, LAND_REPAIR_COLUMN] > 0
    assert out.loc[CLAIM, NEW_WALL_LENGTH_COLUMN] > 0


def test_a_claim_whose_own_wall_is_replaced_is_not_charged_a_second_one(land, ratings):
    # The defect this rule fixes: a 1.4 m2 slip beside an 18.7 m wall was
    # charged $39,706 to replace the wall and $34,596 to invent another.
    out = repair(land, ratings, walled=HAS_A_WALL)
    assert not out.loc[CLAIM, SYNTHETIC_WALL_COLUMN]
    assert out.loc[CLAIM, LAND_REPAIR_COLUMN] == 0.0
    assert out.loc[CLAIM, NEW_WALL_SIZE_COLUMN] == ""
    assert out.loc[CLAIM, NEW_WALL_LENGTH_COLUMN] == 0.0


@pytest.mark.parametrize("area", [0.5, 4.0, 40.0, 500.0])
def test_no_slip_is_small_or_large_enough_to_earn_a_second_wall(area, ratings):
    out = repair(land_with(area), ratings, walled=HAS_A_WALL)
    assert out.loc[CLAIM, LAND_REPAIR_COLUMN] == 0.0


def test_the_damaged_area_is_reported_either_way(ratings):
    # The ground is still recorded as damaged when the wall path pays for it,
    # because the cap values that ground whoever holds it.
    for walled in (NO_WALLS, HAS_A_WALL):
        out = repair(land_with(40.0), ratings, walled=walled)
        assert out.loc[CLAIM, LANDSLIDE_REPAIR_AREA_COLUMN] == pytest.approx(40.0)


def test_an_invented_wall_grows_with_the_ground_it_holds(ratings):
    costs = [
        repair(land_with(area), ratings, walled=NO_WALLS).loc[CLAIM, LAND_REPAIR_COLUMN]
        for area in (5.0, 25.0, 100.0, 400.0)
    ]
    assert costs == sorted(costs)
    assert costs[0] > 0


def test_a_claim_with_no_landslide_ground_builds_nothing(ratings):
    out = repair(land_with(0.0), ratings, walled=NO_WALLS)
    assert out.loc[CLAIM, LAND_REPAIR_COLUMN] == 0.0
    assert out.loc[CLAIM, NEW_WALL_LENGTH_COLUMN] == 0.0
    assert not out.loc[CLAIM, SYNTHETIC_WALL_COLUMN]


# ---------------------------------------------------------------------------
# Sizing the replacement for a wall a landslide came with.
# ---------------------------------------------------------------------------


# The type every wall below is, unless a test says otherwise: a timber pole
# type, so its rate moves with its height.
WALL_TYPE = "timber_pole_post_1992"


def walls(
    *shapes: tuple[str, float], claim: str = CLAIM, wall_type: str = WALL_TYPE
) -> pd.DataFrame:
    """Return damaged walls on one claim, each a (size class, length) pair.

    Each is as tall as its class's set height.
    """
    return pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [claim] * len(shapes),
            RW_ID_COLUMN: [f"rw{i}" for i in range(len(shapes))],
            RW_SIZE_COLUMN: [size for size, _ in shapes],
            RW_TYPE_COLUMN: [wall_type] * len(shapes),
            RW_HEIGHT_COLUMN: [float(beta_wall_height_m(size)) for size, _ in shapes],
            RW_LENGTH_COLUMN: [length for _, length in shapes],
            IS_DAMAGED_BY_SHAKING_COLUMN: [True] * len(shapes),
            IS_EVACUATED_COLUMN: [False] * len(shapes),
            IS_INUNDATED_COLUMN: [False] * len(shapes),
        }
    )


MARGIN = 2.0 * LANDSLIDE_WALL_MARGIN_M


def test_the_margin_rule_numbers_are_the_leads():
    assert LANDSLIDE_WALL_MARGIN_M == 1.0
    assert MIN_LANDSLIDE_WALL_LENGTH_M == 3.0


def test_a_wall_that_failed_whole_keeps_its_shape_and_gains_the_margin():
    size, height, length = replacement_wall_shape(walls(("medium", 7.0)))
    assert list(size) == ["medium"]
    assert height == pytest.approx([1.75])
    assert length == pytest.approx([7.0 + MARGIN])


def test_a_slip_does_not_enlarge_the_wall_it_came_with(ratings):
    # The wall's own height and size class stand whatever the slip was: the
    # replacement is the 9.6 m medium wall plus the margin, not a large one.
    out = wall_repair_by_claim(
        walls(("medium", 9.6)), ratings, policy=PolicySettings()
    ).loc[CLAIM]
    assert out[REPLACEMENT_WALL_SIZE_COLUMN] == "medium"
    assert out[REPLACEMENT_WALL_LENGTH_COLUMN] == pytest.approx(9.6 + MARGIN)
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(
        wall_type_rate_excl_gst_nzd_per_m2(WALL_TYPE, beta_wall_height_m("medium"))
    )


def test_a_wall_only_buried_by_inundated_ground_costs_nothing(ratings):
    buried = walls(("medium", 20.0)).assign(
        **{IS_DAMAGED_BY_SHAKING_COLUMN: [False], IS_INUNDATED_COLUMN: [True]}
    )
    assert wall_repair_by_claim(buried, ratings, policy=PolicySettings()).empty


def test_a_wall_keeps_its_own_height():
    shaped = walls(("large", 8.0)).assign(**{RW_HEIGHT_COLUMN: 1.4})
    _, height, _ = replacement_wall_shape(shaped)
    assert height == pytest.approx([1.4])


def test_a_clipped_wall_is_replaced_over_its_damaged_length_plus_the_margin():
    # 46 m long, clipped for 3.96 m by a neighbour: 3.96 + 2 m, not 46 m.
    clipped = walls(("medium", 46.0)).assign(
        **{RW_DAMAGED_LENGTH_COLUMN: [3.96], IS_DAMAGED_BY_SHAKING_COLUMN: [False]}
    )
    _, _, length = replacement_wall_shape(clipped)
    assert length == pytest.approx([3.96 + MARGIN])


def test_a_short_damaged_length_is_replaced_at_the_minimum():
    clipped = walls(("medium", 46.0)).assign(
        **{RW_DAMAGED_LENGTH_COLUMN: [0.5], IS_DAMAGED_BY_SHAKING_COLUMN: [False]}
    )
    _, _, length = replacement_wall_shape(clipped)
    assert length == pytest.approx([MIN_LANDSLIDE_WALL_LENGTH_M])


def test_a_wall_damaged_by_shaking_is_replaced_whole_whatever_its_damaged_length():
    shaken = walls(("medium", 20.0)).assign(
        **{RW_DAMAGED_LENGTH_COLUMN: [3.0], IS_DAMAGED_BY_SHAKING_COLUMN: [True]}
    )
    _, _, length = replacement_wall_shape(shaken)
    assert length == pytest.approx([20.0 + MARGIN])


def test_a_table_without_damaged_lengths_settles_at_the_whole_length():
    assert RW_DAMAGED_LENGTH_COLUMN not in walls(("medium", 10.0)).columns
    _, _, length = replacement_wall_shape(walls(("medium", 10.0)))
    assert length == pytest.approx([10.0 + MARGIN])


def pieces_of_one_wall(*damaged: float, lengths: tuple[float, ...]) -> pd.DataFrame:
    """Return one wall's pieces, each on its own claim, with damaged lengths."""
    shaped = walls(*[("medium", length) for length in lengths])
    return shaped.assign(
        **{
            CLAIM_ID_COLUMN: [f"claim-{i}" for i in range(len(lengths))],
            RW_ID_COLUMN: [f"rwA-P{i}" for i in range(len(lengths))],
            "parent_rw_id": ["rwA"] * len(lengths),
            RW_DAMAGED_LENGTH_COLUMN: list(damaged),
            IS_DAMAGED_BY_SHAKING_COLUMN: [False] * len(lengths),
            IS_EVACUATED_COLUMN: [True] * len(lengths),
        }
    )


def test_a_wall_shared_by_two_claims_gets_the_margin_once():
    shared = pieces_of_one_wall(4.0, 6.0, lengths=(20.0, 20.0))
    _, _, length = replacement_wall_shape(shared)
    # 4 + 6 + 2 m once, shared in proportion to the damaged length.
    assert length.sum() == pytest.approx(4.0 + 6.0 + MARGIN)
    assert length.tolist() == pytest.approx([12.0 * 0.4, 12.0 * 0.6])


def test_a_wall_damaged_at_two_places_gets_one_margin():
    # Two pieces of one wall, 2 m damaged in each: one margin, not two.
    shared = pieces_of_one_wall(2.0, 2.0, lengths=(10.0, 10.0))
    _, _, length = replacement_wall_shape(shared)
    assert length.sum() == pytest.approx(4.0 + MARGIN)


def test_a_wall_is_replaced_at_the_minimum_once_not_per_piece():
    shared = pieces_of_one_wall(0.2, 0.2, lengths=(10.0, 10.0))
    _, _, length = replacement_wall_shape(shared)
    assert length.sum() == pytest.approx(MIN_LANDSLIDE_WALL_LENGTH_M)


def test_two_walls_on_one_claim_are_each_worked_on_their_own():
    two = walls(("medium", 10.0), ("medium", 20.0))
    _, _, length = replacement_wall_shape(two)
    assert length.tolist() == pytest.approx([10.0 + MARGIN, 20.0 + MARGIN])


def test_a_replacement_costs_the_wall_face_at_its_own_height(ratings):
    out = wall_repair_by_claim(
        walls(("medium", 9.6)), ratings, policy=PolicySettings()
    ).loc[CLAIM]
    assert out[REPLACEMENT_WALL_FACE_COLUMN] == pytest.approx(1.75 * (9.6 + MARGIN))
    assert out[WALL_REPAIR_COLUMN] > 0


def test_a_concrete_block_wall_is_rebuilt_in_kind(ratings):
    out = wall_repair_by_claim(
        walls(("medium", 9.6), wall_type="concrete_block"),
        ratings,
        policy=PolicySettings(),
    ).loc[CLAIM]
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(1_010.58)


def test_a_brick_wall_is_rebuilt_as_timber_pole(ratings):
    out = wall_repair_by_claim(
        walls(("medium", 9.6), wall_type="brick_rock"),
        ratings,
        policy=PolicySettings(),
    ).loc[CLAIM]
    # 1.75 m takes the 250 mm pile, not the mortar bed rock rate.
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(744.69)


def test_a_claim_with_several_walls_reports_a_face_weighted_rate(ratings):
    out = wall_repair_by_claim(
        walls(("small", 4.0), ("large", 6.0)),
        ratings,
        policy=PolicySettings(),
    ).loc[CLAIM]
    faces = np.array([0.75 * (4.0 + MARGIN), 2.75 * (6.0 + MARGIN)])
    rates = wall_type_rate_excl_gst_nzd_per_m2(
        np.array([WALL_TYPE, WALL_TYPE]), np.array([0.75, 2.75])
    )
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(
        (faces * rates).sum() / faces.sum()
    )


def test_the_canterbury_liquefaction_cost_is_brought_to_today_then_taxed() -> None:
    land = pd.DataFrame(
        {CLAIM_ID_COLUMN: ["a", "a", "b"], LIQ_LD_COST_COLUMN: [1000.0, 500.0, None]}
    )
    cost = liquefaction_repair_by_claim(land)
    assert cost["a"] == pytest.approx(1500.0 * LIQ_COST_ESCALATION * 1.15)
    assert cost["b"] == 0.0


# ---------------------------------------------------------------------------
# Separate failures, each with its own wall (T-124).
# ---------------------------------------------------------------------------


def failure_land(*polygons) -> pd.DataFrame:
    """Return land polygons listing their failures.

    Each polygon is (claim, [(landslide id, rw id, area, inundated area)]).
    """
    rows = [
        {
            CLAIM_ID_COLUMN: claim,
            LANDSLIDE_AREA_COLUMN: sum(f[2] for f in failures),
            INUNDATED_AREA_COLUMN: sum(f[3] for f in failures),
            INUNDATED_MEAN_DEPTH_COLUMN: 0.3,
            LANDSLIDE_IDS_COLUMN: [f[0] for f in failures],
            LANDSLIDE_RW_IDS_COLUMN: [f[1] for f in failures],
            LANDSLIDE_AREAS_COLUMN: [f[2] for f in failures],
            LANDSLIDE_INUNDATED_AREAS_COLUMN: [f[3] for f in failures],
            LANDSLIDE_INUNDATED_DEPTHS_COLUMN: [0.3 for _ in failures],
        }
        for claim, failures in polygons
    ]
    return pd.DataFrame(rows)


def hold(land, ratings, rw) -> pd.Series:
    """Hold the land, and return the claim's row."""
    return land_repair_by_claim(
        land,
        ratings,
        failures=landslide_failures(land),
        rw=rw,
        policy=PolicySettings(),
    ).loc[CLAIM]


def test_two_separate_slips_get_two_walls(ratings):
    land = failure_land((CLAIM, [("LS1", None, 40.0, 0.0), ("LS2", None, 30.0, 0.0)]))
    both = hold(land, ratings, walls())
    one = hold(failure_land((CLAIM, [("LS1", None, 40.0, 0.0)])), ratings, walls())
    other = hold(failure_land((CLAIM, [("LS2", None, 30.0, 0.0)])), ratings, walls())
    assert both[NEW_WALL_COUNT_COLUMN] == 2
    assert both[LAND_REPAIR_COLUMN] == pytest.approx(
        one[LAND_REPAIR_COLUMN] + other[LAND_REPAIR_COLUMN]
    )
    assert both[NEW_WALL_LENGTH_COLUMN] == pytest.approx(
        landslide_wall_length_m(40.0) + landslide_wall_length_m(30.0)
    )
    assert both[NEW_WALL_FACE_COLUMN] == pytest.approx(
        one[NEW_WALL_FACE_COLUMN] + other[NEW_WALL_FACE_COLUMN]
    )


def test_a_slip_that_came_with_the_wall_is_held_by_its_replacement(ratings):
    land = failure_land((CLAIM, [("S1", "rw0", 40.0, 0.0)]))
    out = hold(land, ratings, walls(("medium", 9.6)))
    assert out[NEW_WALL_COUNT_COLUMN] == 0
    assert out[LAND_REPAIR_COLUMN] == 0.0


def test_a_slip_beside_a_failed_wall_still_gets_its_own_wall(ratings):
    # The wall failed with one slip; a second, separate slip has no wall to
    # hold it, so it gets one.
    land = failure_land((CLAIM, [("S1", "rw0", 40.0, 0.0), ("LS9", None, 30.0, 0.0)]))
    out = hold(land, ratings, walls(("medium", 9.6)))
    assert out[NEW_WALL_COUNT_COLUMN] == 1
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(landslide_wall_length_m(30.0))


def test_a_slip_whose_wall_stood_on_another_property_gets_a_new_wall(ratings):
    land = failure_land((CLAIM, [("S1", "rw-next-door", 40.0, 0.0)]))
    out = hold(land, ratings, walls(("medium", 9.6)))
    assert out[NEW_WALL_COUNT_COLUMN] == 1


def with_evacuated(land: pd.DataFrame, *evacuated: list[float]) -> pd.DataFrame:
    """Return the land listing each failure's evacuated ground, polygon by polygon."""
    return land.assign(**{LANDSLIDE_EVACUATED_AREAS_COLUMN: list(evacuated)})


def test_a_new_wall_is_as_long_as_its_evacuated_ground_calls_for(ratings):
    # 40 m2 of ground, of which 10 m2 is the scar and 30 m2 the deposit below it.
    land = with_evacuated(failure_land((CLAIM, [("LS1", None, 40.0, 30.0)])), [10.0])
    out = hold(land, ratings, walls())
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(landslide_wall_length_m(10.0))


def test_a_deposit_with_no_scar_on_the_claim_gets_no_wall_but_keeps_its_clearing(
    ratings,
):
    # The slip started next door: the claim was only buried. Inundated ground
    # alone needs clearing, not a wall (2026-10-14).
    land = with_evacuated(failure_land((CLAIM, [("LS1", None, 40.0, 40.0)])), [0.0])
    out = hold(land, ratings, walls())
    assert out[NEW_WALL_COUNT_COLUMN] == 0
    assert out[LAND_REPAIR_COLUMN] == 0.0
    assert not out[SYNTHETIC_WALL_COLUMN]
    # The land is still repaired: its deposit is cleared as spoil.
    assert spoil_by_claim(land).loc[CLAIM] == pytest.approx(40.0 * 0.3)
    assert out[LANDSLIDE_REPAIR_AREA_COLUMN] == pytest.approx(40.0)


def test_a_buried_only_failure_beside_a_scarred_one_leaves_just_one_wall(ratings):
    land = with_evacuated(
        failure_land((CLAIM, [("LS1", None, 40.0, 40.0), ("LS2", None, 30.0, 0.0)])),
        [0.0, 30.0],
    )
    out = hold(land, ratings, walls())
    assert out[NEW_WALL_COUNT_COLUMN] == 1
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(landslide_wall_length_m(30.0))


def test_a_pooled_older_table_with_no_evacuated_ground_builds_no_wall(ratings):
    land = land_with(40.0).assign(**{EVACUATED_AREA_COLUMN: [0.0]})
    out = hold(land, ratings, walls())
    assert out[NEW_WALL_COUNT_COLUMN] == 0


def test_pooled_ground_measures_its_wall_off_the_evacuated_area():
    land = land_with(40.0).assign(**{EVACUATED_AREA_COLUMN: [12.0]})
    failures = landslide_failures(land)
    assert failures["evacuated"].tolist() == pytest.approx([12.0])


def test_a_table_without_evacuated_lists_measures_off_the_whole_ground():
    failures = landslide_failures(failure_land((CLAIM, [("LS1", None, 40.0, 30.0)])))
    assert failures["evacuated"].tolist() == pytest.approx([40.0])


def test_a_slip_across_two_of_a_claims_polygons_is_one_failure():
    land = failure_land(
        (CLAIM, [("LS1", None, 25.0, 5.0)]), (CLAIM, [("LS1", None, 15.0, 5.0)])
    )
    failures = landslide_failures(with_evacuated(land, [20.0], [5.0]))
    assert len(failures) == 1
    assert failures["area"].iloc[0] == pytest.approx(40.0)
    assert failures["evacuated"].iloc[0] == pytest.approx(25.0)
    assert failures["volume"].iloc[0] == pytest.approx(10.0 * 0.3)


def test_a_split_walls_piece_holds_the_slip_its_whole_wall_failed_with():
    # The failure names the whole wall; the claim holds a piece of it.
    pieces = walls(("medium", 9.6)).assign(
        **{RW_ID_COLUMN: ["rwA~2"], "parent_rw_id": ["rwA"]}
    )
    failures = landslide_failures(failure_land((CLAIM, [("S1", "rwA", 40.0, 0.0)])))
    assert list(attach_failures_to_walls(failures, pieces)) == [0]


# ---------------------------------------------------------------------------
# A new wall on the mapped wall where there is one (section 4).
# ---------------------------------------------------------------------------


def with_mapped(land: pd.DataFrame, heights, lengths, sources) -> pd.DataFrame:
    """Return the land listing each failure's mapped wall, polygon by polygon."""
    return land.assign(
        **{
            LANDSLIDE_WALL_HEIGHTS_COLUMN: list(heights),
            LANDSLIDE_WALL_LENGTHS_COLUMN: list(lengths),
            LANDSLIDE_WALL_SOURCES_COLUMN: list(sources),
        }
    )


def mapped_land(height, length, *, area=40.0, evacuated=12.0) -> pd.DataFrame:
    """One failure whose mapped wall is ``height`` m high, ``length`` m alongside."""
    land = with_evacuated(
        failure_land((CLAIM, [("LS1", None, area, 0.0)])), [evacuated]
    )
    return with_mapped(land, [[height]], [[length]], [["mapped wall"]])


def test_a_mapped_wall_is_built_at_its_height_over_its_length_plus_the_margin(
    ratings,
):
    out = hold(mapped_land(1.6, 8.0), ratings, walls())

    assert out[NEW_WALL_COUNT_COLUMN] == 1
    assert out[NEW_WALL_FROM_MAPPED_COLUMN] == 1
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(
        8.0 + 2 * LANDSLIDE_WALL_MARGIN_M
    )
    assert out[NEW_WALL_FACE_COLUMN] == pytest.approx(1.6 * 10.0)
    assert out["new_wall_height_m"] == pytest.approx(1.6)


def test_a_mapped_wall_is_priced_as_timber_pole_on_the_pile_its_height_calls_for(
    ratings,
):
    low = hold(mapped_land(1.0, 8.0), ratings, walls())
    tall = hold(mapped_land(2.6, 8.0), ratings, walls())

    for out, height in ((low, 1.0), (tall, 2.6)):
        assert out["new_wall_rate_excl_gst_nzd_per_m2"] == pytest.approx(
            float(timber_pole_rate_excl_gst_nzd_per_m2(height))
        )
    assert (
        tall["new_wall_rate_excl_gst_nzd_per_m2"]
        > low["new_wall_rate_excl_gst_nzd_per_m2"]
    )


def test_a_mapped_wall_alongside_less_than_the_minimum_is_built_at_the_minimum(
    ratings,
):
    out = hold(mapped_land(1.6, 1.0), ratings, walls())

    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(
        float(margin_rule_length_m(1.0))
    )
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(MIN_LANDSLIDE_WALL_LENGTH_M)


def test_a_mapped_wall_ignores_the_slips_size(ratings):
    small = hold(mapped_land(1.6, 8.0, area=5.0), ratings, walls())
    large = hold(mapped_land(1.6, 8.0, area=900.0, evacuated=300.0), ratings, walls())

    assert small[NEW_WALL_FACE_COLUMN] == pytest.approx(large[NEW_WALL_FACE_COLUMN])
    assert small[LAND_REPAIR_COLUMN] == pytest.approx(large[LAND_REPAIR_COLUMN])


def test_a_slip_failure_is_sized_from_the_slip_with_the_one_and_three_metre_numbers(
    ratings,
):
    land = with_evacuated(failure_land((CLAIM, [("LS1", None, 40.0, 0.0)])), [12.0])
    listed = with_mapped(land, [[None]], [[None]], [["slip"]])
    out = hold(listed, ratings, walls())
    plain = hold(land, ratings, walls())

    assert out[NEW_WALL_COUNT_COLUMN] == 1
    assert out[NEW_WALL_FROM_MAPPED_COLUMN] == 0
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(landslide_wall_length_m(12.0))
    assert out[LAND_REPAIR_COLUMN] == pytest.approx(plain[LAND_REPAIR_COLUMN])


def test_a_table_without_the_wall_lists_sizes_every_new_wall_from_the_slip(ratings):
    land = with_evacuated(failure_land((CLAIM, [("LS1", None, 40.0, 0.0)])), [12.0])
    failures = landslide_failures(land)

    assert failures["wall_source"].tolist() == ["slip"]
    assert failures["wall_height"].isna().all()
    assert failures["wall_length"].isna().all()
    out = hold(land, ratings, walls())
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(landslide_wall_length_m(12.0))


def test_a_failure_sharing_a_mapped_wall_builds_none_of_its_own(ratings):
    land = with_evacuated(
        failure_land((CLAIM, [("LS1", None, 40.0, 0.0), ("LS2", None, 30.0, 0.0)])),
        [12.0, 9.0],
    )
    land = with_mapped(
        land, [[1.6, 1.6]], [[11.0, 0.0]], [["mapped wall", "mapped wall"]]
    )
    out = hold(land, ratings, walls())

    assert out[NEW_WALL_COUNT_COLUMN] == 1
    assert out[NEW_WALL_FROM_MAPPED_COLUMN] == 1
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(
        11.0 + 2 * LANDSLIDE_WALL_MARGIN_M
    )


def test_a_mapped_and_a_slip_failure_each_get_their_own_wall(ratings):
    land = with_evacuated(
        failure_land((CLAIM, [("LS1", None, 40.0, 0.0), ("LS2", None, 30.0, 0.0)])),
        [12.0, 9.0],
    )
    land = with_mapped(land, [[1.6, None]], [[8.0, None]], [["mapped wall", "slip"]])
    out = hold(land, ratings, walls())

    assert out[NEW_WALL_COUNT_COLUMN] == 2
    assert out[NEW_WALL_FROM_MAPPED_COLUMN] == 1
    assert out[NEW_WALL_LENGTH_COLUMN] == pytest.approx(
        8.0 + 2 * LANDSLIDE_WALL_MARGIN_M + landslide_wall_length_m(9.0)
    )


def test_a_mapped_failure_a_damaged_wall_holds_builds_nothing(ratings):
    land = with_evacuated(failure_land((CLAIM, [("S1", "rw0", 40.0, 0.0)])), [12.0])
    land = with_mapped(land, [[1.6]], [[8.0]], [["mapped wall"]])
    out = hold(land, ratings, walls(("medium", 9.6)))

    assert out[NEW_WALL_COUNT_COLUMN] == 0


def test_a_mapped_failure_with_no_evacuated_ground_builds_no_wall(ratings):
    out = hold(mapped_land(1.6, 8.0, evacuated=0.0), ratings, walls())

    assert out[NEW_WALL_COUNT_COLUMN] == 0
    assert out[LAND_REPAIR_COLUMN] == 0.0


def test_a_failure_on_two_polygons_adds_its_mapped_entries_once():
    land = with_evacuated(
        failure_land(
            (CLAIM, [("LS1", None, 25.0, 5.0)]), (CLAIM, [("LS1", None, 15.0, 5.0)])
        ),
        [20.0],
        [5.0],
    )
    land = with_mapped(
        land, [[1.6], [1.6]], [[8.0], [0.0]], [["mapped wall"], ["mapped wall"]]
    )
    failures = landslide_failures(land)

    assert len(failures) == 1
    assert failures["wall_source"].tolist() == ["mapped wall"]
    assert failures["wall_height"].tolist() == pytest.approx([1.6])
    assert failures["wall_length"].tolist() == pytest.approx([8.0])


def test_a_failure_sharing_a_mapped_wall_is_not_counted_as_a_new_wall(capsys):
    land = failure_land((CLAIM, [("LS1", None, 40.0, 0.0), ("LS2", None, 30.0, 0.0)]))
    land = with_evacuated(land, [12.0, 9.0])
    land = with_mapped(
        land,
        [[1.5, 1.5]],
        [[8.0, 0.0]],
        [["mapped wall", "mapped wall"]],
    )

    describe_failures(landslide_failures(land), walls())

    assert "1 get a new wall" in capsys.readouterr().out
