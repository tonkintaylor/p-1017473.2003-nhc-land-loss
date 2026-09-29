"""The settlement step's own arithmetic, where it is not in the library.

`land_repair_by_claim` lives in `src/scripts` because it orchestrates rather
than calculates, but the rule it encodes is a policy decision worth pinning
down: **one wall stands on a property, so a claim is charged for one wall.**
Where a wall is already there it is replaced; where there is none, one is
invented to hold the ground. Never both.
"""

import pandas as pd
import pytest

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    LANDSLIDE_AREA_COLUMN,
)
from landloss.loss.policy import PolicySettings
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    ACCESS_COLUMN,
    CONSTRUCTABILITY_COLUMN,
    EARTHWORKS_COLUMN,
    LAND_REPAIR_COLUMN,
    LANDSLIDE_REPAIR_AREA_COLUMN,
    NEW_WALL_LENGTH_COLUMN,
    NEW_WALL_SIZE_COLUMN,
    SYNTHETIC_WALL_COLUMN,
    land_repair_by_claim,
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
    return land_repair_by_claim(land, ratings, walled=walled, policy=PolicySettings())


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
