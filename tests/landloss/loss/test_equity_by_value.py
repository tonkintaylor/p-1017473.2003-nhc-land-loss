import numpy as np
import pandas as pd

from landloss.loss.policy import PolicySettings
from scripts.landloss.loss.equity.gen_equity_by_value import (
    ACT_FULL,
    ACT_SHORT,
    COMBINATION,
    CROSSING,
    FIXED_FULL,
    FIXED_SHORT,
    LANDSLIDE,
    LIQUEFACTION,
    WALL,
    damage_type,
    settle_both_ways,
)


def viewer_rows(*rows) -> pd.DataFrame:
    """Build viewer rows from (liquefaction, wall, landslide, crossing cost)."""
    return pd.DataFrame(
        rows,
        columns=[
            "has_liquefaction",
            "has_damaged_wall",
            "has_landslide",
            "crossing_repair_excl_gst",
        ],
    )


def test_each_claim_takes_the_viewers_kind_of_damage() -> None:
    kinds = damage_type(
        viewer_rows(
            (1, 0, 0, 0),
            (0, 1, 0, 0),
            (0, 0, 1, 0),
            (0, 0, 0, 5000.0),
            (1, 0, 1, 0),
            (0, 0, 0, 0),
        )
    )
    assert kinds[:5].tolist() == [LIQUEFACTION, WALL, LANDSLIDE, CROSSING, COMBINATION]
    assert pd.isna(kinds[5])


def test_paid_in_full_is_the_cap_covering_the_repair_before_the_excess() -> None:
    # Repair $103,500 incl GST is $90,000 before it: the Act's cap of $92,000
    # incl GST ($80,000) falls short by $10,000; a $100,000 cap covers it.
    claims = pd.DataFrame(
        {
            "repair_cost_incl_gst_nzd": [103_500.0, 103_500.0],
            "land_cover_cap_incl_gst_nzd": [92_000.0, 2_000_000.0],
            "dwelling_count": [1, 2],
            "retaining_wall_udv_incl_gst_nzd": [0.0, 0.0],
        }
    )
    settled = settle_both_ways(claims, 100_000.0, PolicySettings())
    assert settled[ACT_FULL].tolist() == [False, True]
    assert settled[FIXED_FULL].tolist() == [True, True]
    assert np.allclose(settled[ACT_SHORT], [10_000.0, 0.0])
    assert np.allclose(settled[FIXED_SHORT], [0.0, 0.0])
