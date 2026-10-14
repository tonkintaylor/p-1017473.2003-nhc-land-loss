"""Step 0's wall value for the cap: valued over the length it is rebuilt over.

A damaged wall is valued over its damaged length plus the margin rule's 1 m at
each end (at least 3 m), but never over more wall than the property had. It is
worked per wall and shared over its pieces, like the repair in step 1.
"""

import pandas as pd
import pytest

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    RW_DAMAGED_LENGTH_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_TYPE_COLUMN,
)
from landloss.loss.policy import PolicySettings
from scripts.landloss.loss.steps.s0_land_cover_cap.s0_gen_land_cover_cap import (
    wall_udv_by_claim,
)

POLICY = PolicySettings()
WALL_TYPE = "timber_pole_post_1992"


def wall(length, *, damaged=None, claim="c1", rw_id="rwA", parent=None, **flags):
    """Return one wall piece, damaged by shaking unless a flag says otherwise."""
    row = {
        CLAIM_ID_COLUMN: claim,
        RW_ID_COLUMN: rw_id,
        RW_TYPE_COLUMN: WALL_TYPE,
        RW_HEIGHT_COLUMN: 1.5,
        RW_LENGTH_COLUMN: length,
        IS_DAMAGED_BY_SHAKING_COLUMN: flags.get("shaking", True),
        IS_EVACUATED_COLUMN: flags.get("evacuated", False),
        IS_INUNDATED_COLUMN: False,
    }
    if damaged is not None:
        row[RW_DAMAGED_LENGTH_COLUMN] = damaged
    if parent is not None:
        row["parent_rw_id"] = parent
    return row


def udv_of(*rows) -> pd.Series:
    return wall_udv_by_claim(pd.DataFrame(list(rows)), policy=POLICY)


def test_a_wall_that_failed_whole_is_valued_over_its_own_length():
    # Replaced over 12 + 2 m, but the property only had 12 m.
    value = udv_of(wall(12.0))["c1"]
    per_metre = udv_of(wall(1.0))["c1"]
    assert value == pytest.approx(12.0 * per_metre)


def test_a_clipped_wall_is_valued_over_its_damaged_length_plus_the_margin():
    value = udv_of(wall(46.0, damaged=3.96, shaking=False, evacuated=True))["c1"]
    per_metre = udv_of(wall(1.0))["c1"]
    assert value == pytest.approx((3.96 + 2.0) * per_metre)


def test_a_short_clip_is_valued_at_the_minimum_but_not_past_the_wall():
    per_metre = udv_of(wall(1.0))["c1"]
    long_wall = udv_of(wall(20.0, damaged=0.5, shaking=False, evacuated=True))["c1"]
    short_wall = udv_of(wall(2.0, damaged=0.5, shaking=False, evacuated=True))["c1"]
    assert long_wall == pytest.approx(3.0 * per_metre)
    assert short_wall == pytest.approx(2.0 * per_metre)


def test_the_pieces_of_one_wall_are_worked_together():
    # Two claims share a 40 m wall, 4 m and 6 m damaged: 10 + 2 m in all.
    per_metre = udv_of(wall(1.0))["c1"]
    out = udv_of(
        wall(
            20.0,
            damaged=4.0,
            claim="c1",
            rw_id="rwA-P0",
            parent="rwA",
            shaking=False,
            evacuated=True,
        ),
        wall(
            20.0,
            damaged=6.0,
            claim="c2",
            rw_id="rwA-P1",
            parent="rwA",
            shaking=False,
            evacuated=True,
        ),
    )
    assert out.sum() == pytest.approx(12.0 * per_metre)
    assert out["c1"] == pytest.approx(12.0 * 0.4 * per_metre)
    assert out["c2"] == pytest.approx(12.0 * 0.6 * per_metre)


def test_a_wall_only_buried_by_inundated_ground_is_not_valued():
    buried = wall(12.0, shaking=False)
    buried[IS_INUNDATED_COLUMN] = True
    assert udv_of(buried).empty


def test_a_wall_valued_whole_when_damaged_by_shaking_whatever_its_damaged_length():
    per_metre = udv_of(wall(1.0))["c1"]
    assert udv_of(wall(12.0, damaged=2.0))["c1"] == pytest.approx(12.0 * per_metre)


def test_a_table_without_damaged_lengths_values_the_whole_length():
    per_metre = udv_of(wall(1.0))["c1"]
    out = udv_of(wall(30.0, shaking=False, evacuated=True))
    assert out["c1"] == pytest.approx(30.0 * per_metre)
