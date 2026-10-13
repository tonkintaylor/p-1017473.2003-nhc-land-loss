"""The settlement step's own arithmetic, where it is not in the library.

`land_repair_by_claim` lives in `src/scripts` because it orchestrates rather
than calculates, but the rule it encodes is a policy decision worth pinning
down: **each separate slip is held by one wall** (T-124). A slip that came
with a wall is held by that wall's replacement; any other slip gets a new wall
of its own, even beside a wall that failed elsewhere. Ground of unknown origin,
from a land table that lists no failures, is pooled as one slip and held as
before: by the claim's largest damaged wall, or one new wall.

**A replacement is never smaller than the wall it replaces, but a landslide can
make it larger.** `replacement_wall_shape` sizes the wall the slip would need and
takes the larger of that and the existing wall, in each dimension.
"""

import numpy as np
import pandas as pd
import pytest

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_AREAS_COLUMN,
    LANDSLIDE_IDS_COLUMN,
    LANDSLIDE_INUNDATED_AREAS_COLUMN,
    LANDSLIDE_INUNDATED_DEPTHS_COLUMN,
    LANDSLIDE_RW_IDS_COLUMN,
    LIQ_LD_COST_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    RW_TYPE_COLUMN,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    LIQ_COST_ESCALATION,
    beta_wall_height_m,
    classify_landslide_wall_size,
    landslide_wall_length_m,
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
    NEW_WALL_LENGTH_COLUMN,
    NEW_WALL_SIZE_COLUMN,
    REPLACEMENT_WALL_LENGTH_COLUMN,
    REPLACEMENT_WALL_RATE_COLUMN,
    REPLACEMENT_WALL_SIZE_COLUMN,
    SYNTHETIC_WALL_COLUMN,
    WALL_ENLARGED_COLUMN,
    WALL_REPAIR_COLUMN,
    attach_failures_to_walls,
    land_repair_by_claim,
    landslide_failures,
    liquefaction_repair_by_claim,
    replacement_wall_shape,
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


def slip(area_m2: float) -> pd.DataFrame:
    """Return the claim's ground as one pooled slip, with no inundated deposit."""
    return landslide_failures(
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: [CLAIM],
                LANDSLIDE_AREA_COLUMN: [area_m2],
                INUNDATED_AREA_COLUMN: [0.0],
                INUNDATED_MEAN_DEPTH_COLUMN: [0.0],
            }
        )
    )


def test_a_wall_with_no_slip_is_replaced_as_it_was():
    size, height, length = replacement_wall_shape(walls(("medium", 7.0)), slip(0.0))
    assert list(size) == ["medium"]
    assert height == pytest.approx([1.75])
    assert length == pytest.approx([7.0])


def test_a_replacement_is_never_smaller_than_the_wall_it_replaces():
    # A 1.4 m2 slip wants a small wall 5.7 m long; the 18.7 m medium wall
    # beside it is replaced as it was.
    size, _height, length = replacement_wall_shape(walls(("medium", 18.7)), slip(1.4))
    assert list(size) == ["medium"]
    assert length == pytest.approx([18.7])


def test_a_large_slip_enlarges_the_replacement_in_both_dimensions():
    area = 208.8
    size, height, length = replacement_wall_shape(walls(("medium", 9.6)), slip(area))
    assert list(size) == list(classify_landslide_wall_size([area], [0.0])) == ["large"]
    assert height == pytest.approx([beta_wall_height_m("large")])
    assert length == pytest.approx(landslide_wall_length_m(area))
    assert length[0] > 9.6


def test_each_dimension_takes_the_larger_on_its_own():
    # The slip wants a medium wall 8.8 m long; the large wall there is 8.2 m.
    # The replacement keeps the larger class and takes the longer length.
    size, _height, length = replacement_wall_shape(walls(("large", 8.2)), slip(11.6))
    assert list(size) == ["large"]
    assert length == pytest.approx(landslide_wall_length_m(11.6))


def test_pooled_ground_is_sized_against_only_the_largest_of_several_walls():
    # Ground of unknown origin is one piece of ground and wants one wall.
    size, _height, length = replacement_wall_shape(
        walls(("small", 4.0), ("medium", 6.0)), slip(208.8)
    )
    assert list(size) == ["small", "large"]
    assert length[0] == pytest.approx(4.0)
    assert length[1] == pytest.approx(landslide_wall_length_m(208.8))


def test_an_enlarged_wall_costs_more_and_is_priced_on_its_new_height(ratings):
    policy = PolicySettings()
    kept = wall_repair_by_claim(
        walls(("medium", 9.6)), ratings, failures=slip(0.0), policy=policy
    ).loc[CLAIM]
    grown = wall_repair_by_claim(
        walls(("medium", 9.6)), ratings, failures=slip(208.8), policy=policy
    ).loc[CLAIM]
    assert not kept[WALL_ENLARGED_COLUMN]
    assert grown[WALL_ENLARGED_COLUMN]
    assert grown[WALL_REPAIR_COLUMN] > kept[WALL_REPAIR_COLUMN]
    assert grown[REPLACEMENT_WALL_SIZE_COLUMN] == "large"
    assert grown[REPLACEMENT_WALL_LENGTH_COLUMN] == pytest.approx(
        landslide_wall_length_m(208.8)
    )
    # A timber pole wall takes the pile its new height calls for.
    assert grown[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(
        wall_type_rate_excl_gst_nzd_per_m2(WALL_TYPE, beta_wall_height_m("large"))
    )
    assert grown[REPLACEMENT_WALL_RATE_COLUMN] > kept[REPLACEMENT_WALL_RATE_COLUMN]


def test_a_wall_keeps_its_own_height_when_the_slip_needs_less():
    shaped = walls(("large", 8.0)).assign(**{RW_HEIGHT_COLUMN: 3.2})
    _, height, _ = replacement_wall_shape(shaped, slip(11.6))
    assert height == pytest.approx([3.2])


def test_a_concrete_block_wall_is_rebuilt_in_kind(ratings):
    out = wall_repair_by_claim(
        walls(("medium", 9.6), wall_type="concrete_block"),
        ratings,
        failures=slip(0.0),
        policy=PolicySettings(),
    ).loc[CLAIM]
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(1_010.58)


def test_a_brick_wall_is_rebuilt_as_timber_pole(ratings):
    out = wall_repair_by_claim(
        walls(("medium", 9.6), wall_type="brick_rock"),
        ratings,
        failures=slip(0.0),
        policy=PolicySettings(),
    ).loc[CLAIM]
    # 1.75 m takes the 250 mm pile, not the mortar bed rock rate.
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(744.69)


def test_a_claim_with_several_walls_reports_a_face_weighted_rate(ratings):
    out = wall_repair_by_claim(
        walls(("small", 4.0), ("large", 6.0)),
        ratings,
        failures=slip(0.0),
        policy=PolicySettings(),
    ).loc[CLAIM]
    faces = np.array([0.75 * 4.0, 2.75 * 6.0])
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


def test_a_slip_across_two_of_a_claims_polygons_is_one_failure():
    land = failure_land(
        (CLAIM, [("LS1", None, 25.0, 5.0)]), (CLAIM, [("LS1", None, 15.0, 5.0)])
    )
    failures = landslide_failures(land)
    assert len(failures) == 1
    assert failures["area"].iloc[0] == pytest.approx(40.0)
    assert failures["volume"].iloc[0] == pytest.approx(10.0 * 0.3)


def test_a_split_walls_piece_holds_the_slip_its_whole_wall_failed_with():
    # The failure names the whole wall; the claim holds a piece of it.
    pieces = walls(("medium", 9.6)).assign(
        **{RW_ID_COLUMN: ["rwA~2"], "parent_rw_id": ["rwA"]}
    )
    failures = landslide_failures(failure_land((CLAIM, [("S1", "rwA", 40.0, 0.0)])))
    assert list(attach_failures_to_walls(failures, pieces)) == [0]


def test_each_wall_is_sized_against_its_own_slip_only():
    # Each wall failed with its own slip; the large slip enlarges only its own.
    land = failure_land((CLAIM, [("S0", "rw0", 1.4, 0.0), ("S1", "rw1", 208.8, 0.0)]))
    size, _height, length = replacement_wall_shape(
        walls(("medium", 9.6), ("medium", 6.0)), landslide_failures(land)
    )
    assert list(size) == ["medium", "large"]
    assert length[0] == pytest.approx(9.6)
    assert length[1] == pytest.approx(landslide_wall_length_m(208.8))
