"""The settlement step's own arithmetic, where it is not in the library.

`land_repair_by_claim` lives in `src/scripts` because it orchestrates rather
than calculates, but the rule it encodes is a policy decision worth pinning
down: **one wall stands on a property, so a claim is charged for one wall.**
Where a wall is already there it is replaced; where there is none, one is
invented to hold the ground. Never both.

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
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    beta_wall_height_m,
    beta_wall_rate_excl_gst_nzd_per_m2,
    classify_landslide_wall_size,
    landslide_wall_length_m,
)
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    ACCESS_COLUMN,
    CONSTRUCTABILITY_COLUMN,
    EARTHWORKS_COLUMN,
    LAND_REPAIR_COLUMN,
    LANDSLIDE_REPAIR_AREA_COLUMN,
    NEW_WALL_LENGTH_COLUMN,
    NEW_WALL_SIZE_COLUMN,
    REPLACEMENT_WALL_LENGTH_COLUMN,
    REPLACEMENT_WALL_RATE_COLUMN,
    REPLACEMENT_WALL_SIZE_COLUMN,
    SYNTHETIC_WALL_COLUMN,
    WALL_ENLARGED_COLUMN,
    WALL_REPAIR_COLUMN,
    land_repair_by_claim,
    landslide_ground_by_claim,
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
    """Hold the claim's land, given whether its own wall is being replaced."""
    return land_repair_by_claim(
        land,
        ratings,
        ground=landslide_ground_by_claim(land),
        walled=walled,
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


def walls(*shapes: tuple[str, float], claim: str = CLAIM) -> pd.DataFrame:
    """Return damaged walls on one claim, each a (size class, length) pair."""
    return pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [claim] * len(shapes),
            RW_ID_COLUMN: [f"rw{i}" for i in range(len(shapes))],
            RW_SIZE_COLUMN: [size for size, _ in shapes],
            RW_LENGTH_COLUMN: [length for _, length in shapes],
            IS_DAMAGED_BY_SHAKING_COLUMN: [True] * len(shapes),
            IS_EVACUATED_COLUMN: [False] * len(shapes),
            IS_INUNDATED_COLUMN: [False] * len(shapes),
        }
    )


def slip(area_m2: float) -> pd.DataFrame:
    """Return the ground on the claim, with no inundated deposit."""
    return landslide_ground_by_claim(
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
    size, length = replacement_wall_shape(walls(("medium", 7.0)), slip(0.0))
    assert list(size) == ["medium"]
    assert length == pytest.approx([7.0])


def test_a_replacement_is_never_smaller_than_the_wall_it_replaces():
    # A 1.4 m2 slip wants a small wall 5.7 m long; the 18.7 m medium wall
    # beside it is replaced as it was.
    size, length = replacement_wall_shape(walls(("medium", 18.7)), slip(1.4))
    assert list(size) == ["medium"]
    assert length == pytest.approx([18.7])


def test_a_large_slip_enlarges_the_replacement_in_both_dimensions():
    area = 208.8
    size, length = replacement_wall_shape(walls(("medium", 9.6)), slip(area))
    assert list(size) == list(classify_landslide_wall_size([area], [0.0])) == ["large"]
    assert length == pytest.approx(landslide_wall_length_m(area))
    assert length[0] > 9.6


def test_each_dimension_takes_the_larger_on_its_own():
    # The slip wants a medium wall 8.8 m long; the large wall there is 8.2 m.
    # The replacement keeps the larger class and takes the longer length.
    size, length = replacement_wall_shape(walls(("large", 8.2)), slip(11.6))
    assert list(size) == ["large"]
    assert length == pytest.approx(landslide_wall_length_m(11.6))


def test_only_the_largest_of_several_walls_is_sized_against_the_slip():
    # The slip is one piece of ground and wants one wall.
    size, length = replacement_wall_shape(
        walls(("small", 4.0), ("medium", 6.0)), slip(208.8)
    )
    assert list(size) == ["small", "large"]
    assert length[0] == pytest.approx(4.0)
    assert length[1] == pytest.approx(landslide_wall_length_m(208.8))


def test_an_enlarged_wall_costs_more_and_is_priced_on_its_new_height(ratings):
    policy = PolicySettings()
    kept = wall_repair_by_claim(
        walls(("medium", 9.6)), ratings, ground=slip(0.0), policy=policy
    ).loc[CLAIM]
    grown = wall_repair_by_claim(
        walls(("medium", 9.6)), ratings, ground=slip(208.8), policy=policy
    ).loc[CLAIM]
    assert not kept[WALL_ENLARGED_COLUMN]
    assert grown[WALL_ENLARGED_COLUMN]
    assert grown[WALL_REPAIR_COLUMN] > kept[WALL_REPAIR_COLUMN]
    assert grown[REPLACEMENT_WALL_SIZE_COLUMN] == "large"
    assert grown[REPLACEMENT_WALL_LENGTH_COLUMN] == pytest.approx(
        landslide_wall_length_m(208.8)
    )
    # Concrete stays concrete, and a timber wall takes the pile its new height
    # calls for -- either way, the rate of wall rw0 at the large height.
    assert grown[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(
        beta_wall_rate_excl_gst_nzd_per_m2("rw0", beta_wall_height_m("large"))
    )


def test_a_claim_with_several_walls_reports_a_face_weighted_rate(ratings):
    out = wall_repair_by_claim(
        walls(("small", 4.0), ("large", 6.0)),
        ratings,
        ground=slip(0.0),
        policy=PolicySettings(),
    ).loc[CLAIM]
    faces = np.array([0.75 * 4.0, 2.75 * 6.0])
    rates = beta_wall_rate_excl_gst_nzd_per_m2(
        np.array(["rw0", "rw1"]), np.array([0.75, 2.75])
    )
    assert out[REPLACEMENT_WALL_RATE_COLUMN] == pytest.approx(
        (faces * rates).sum() / faces.sum()
    )
