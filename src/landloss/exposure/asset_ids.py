"""Stable asset ids minted in exposure and carried unchanged to the loss module.

Each insured land polygon, retaining wall and crossing gets an id of the form
``<claim_id>-<suffix><n>``, numbered from 1 within its claim, for example
``123-RW01``. The id is minted once, in the exposure step that produces the
asset, so that the vulnerability outputs of every realisation can be joined back
to the same asset.

The number depends only on the order of the rows within a claim, so a caller
sorts first with :func:`sort_by_location`. That keeps the id independent of the
random number generator and of the order the rows happened to arrive in.
"""

import geopandas as gpd
import pandas as pd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN

LAND_ID_SUFFIX = "L"
RW_ID_SUFFIX = "RW"
CROSSING_ID_SUFFIX = "X"

# Temporary sort key columns, removed before the frame is returned.
_SORT_X = "_sort_x"
_SORT_Y = "_sort_y"


def mint_asset_ids(claim_ids: pd.Series, suffix: str) -> pd.Series:
    """Number the assets of each claim in their current order.

    The caller sorts first, typically with :func:`sort_by_location`, so the id
    never depends on the random number generator or on the incoming row order.

    Args:
        claim_ids: The claim id of each asset, one per row.
        suffix: The asset kind's suffix, such as :data:`RW_ID_SUFFIX`.

    Returns:
        A string id per row, ``f"{claim_id}-{suffix}{n:02d}"`` with ``n``
        starting at 1 within each claim, on the same index as ``claim_ids``.

    Raises:
        ValueError: If any claim id is null.
    """
    if claim_ids.isna().any():
        msg = f"{int(claim_ids.isna().sum())} assets carry no claim id"
        raise ValueError(msg)
    numbers = claim_ids.groupby(claim_ids, sort=False).cumcount() + 1
    ids = [
        f"{claim}-{suffix}{number:02d}"
        for claim, number in zip(claim_ids, numbers, strict=True)
    ]
    return pd.Series(ids, index=claim_ids.index, dtype=object)


def sort_by_location(
    frame: gpd.GeoDataFrame, *, id_column: str = CLAIM_ID_COLUMN
) -> gpd.GeoDataFrame:
    """Sort the assets by claim and then by where they are.

    Position is the x and then y coordinate of each geometry's representative
    point, which lies on the geometry for any type. The sort is stable, so ties
    keep their incoming order.

    Args:
        frame: The assets, carrying ``id_column``.
        id_column: The claim id column to sort by first.

    Returns:
        The sorted frame with a fresh index and the original columns.
    """
    if frame.empty:
        return frame.reset_index(drop=True)
    points = frame.geometry.representative_point()
    keyed = frame.assign(**{_SORT_X: points.x.to_numpy(), _SORT_Y: points.y.to_numpy()})
    keyed = keyed.sort_values([id_column, _SORT_X, _SORT_Y], kind="mergesort")
    return keyed.drop(columns=[_SORT_X, _SORT_Y]).reset_index(drop=True)
