"""Ids minted by location for the layers the landslide and wall models build.

The ground map polygons, slope units, urban failure candidates and polygons,
candidate wall lines and large-model landslides each carry an id of the form
``<prefix><7 digits>``, for example ``SP0000042``, numbered from 1. The prefix
of each kind is in :mod:`landloss.domain.constants`, every one in one block.

The number depends only on the order of the rows, so a caller sorts first with
:func:`sort_by_point` and then numbers with :func:`mint_ids`. That keeps an id
independent of the random number generator and of the order the rows happened
to arrive in: the same inputs and parameters give the same ids, and a changed
extent renumbers.

:mod:`landloss.exposure.asset_ids` mints the claim-keyed asset ids the same way.
This module is the claim-free counterpart, kept under ``common`` so that hazard
code mints without importing exposure.
"""

from collections.abc import Sequence

import geopandas as gpd
import pandas as pd

# Temporary sort key columns, removed before the frame is returned.
_SORT_X = "_sort_x"
_SORT_Y = "_sort_y"


def sort_by_point(
    frame: gpd.GeoDataFrame,
    *,
    by: Sequence[str] = (),
    ascending: Sequence[bool] | bool = True,
) -> gpd.GeoDataFrame:
    """Sort the rows by the columns given, then by where each geometry is.

    Position is the x and then y coordinate of each geometry's representative
    point, which lies on the geometry for any type; both sort ascending. The
    sort is stable, so ties keep their incoming order.

    Args:
        frame: The rows to sort, in a projected system.
        by: Columns to sort by before position, in order. A single name may be
            given as a string.
        ascending: Whether each column in ``by`` sorts ascending: one flag per
            column, or one flag for all of them.

    Returns:
        The sorted frame with a fresh index and the original columns.

    Raises:
        ValueError: If ``ascending`` gives a different number of flags from
            ``by``, or the frame is in a geographic system.
    """
    columns = [by] if isinstance(by, str) else list(by)
    if isinstance(ascending, bool):
        flags = [ascending] * len(columns)
    else:
        flags = list(ascending)
    if len(flags) != len(columns):
        msg = (
            f"ascending gives {len(flags)} flags for {len(columns)} columns in by; "
            "give one per column, or one for all of them"
        )
        raise ValueError(msg)
    if frame.crs is not None and frame.crs.is_geographic:
        msg = (
            f"{frame.crs} is a geographic system, so x and y would be degrees. "
            "Work in a projected system such as NZGD2000 / NZTM."
        )
        raise ValueError(msg)
    if frame.empty:
        return frame.reset_index(drop=True)
    points = frame.geometry.representative_point()
    keyed = frame.assign(**{_SORT_X: points.x.to_numpy(), _SORT_Y: points.y.to_numpy()})
    keyed = keyed.sort_values(
        [*columns, _SORT_X, _SORT_Y],
        ascending=[*flags, True, True],
        kind="mergesort",
    )
    return keyed.drop(columns=[_SORT_X, _SORT_Y]).reset_index(drop=True)


def mint_ids(prefix: str, count: int, *, width: int = 7) -> pd.Series:
    """Number ``count`` rows from 1 behind a prefix.

    The caller sorts first, with :func:`sort_by_point`, so the numbers follow
    location rather than arrival order.

    Args:
        prefix: The id prefix, one of the ``*_ID_PREFIX`` constants in
            :mod:`landloss.domain.constants`.
        count: How many ids to mint.
        width: How many digits each number is zero-padded to.

    Returns:
        ``f"{prefix}{n:0{width}d}"`` for ``n`` from 1 to ``count``, as strings
        on a fresh range index.

    Raises:
        ValueError: If ``count`` is negative, or more ids are asked for than
            ``width`` digits can number.
    """
    if count < 0:
        msg = f"cannot mint {count} ids"
        raise ValueError(msg)
    if count >= 10**width:
        msg = f"{count:,} ids do not fit in {width} digits behind {prefix!r}"
        raise ValueError(msg)
    ids = [f"{prefix}{n:0{width}d}" for n in range(1, count + 1)]
    return pd.Series(ids, dtype=object)
