"""Retaining wall line rules shared by ground step 3 and the wall units.

The GNS SLIDE morphology types that mark a mapped wall and a cut/fill line
[townsend_2020], the two wall positions (``fill`` and ``cut``), and the step a
wall line makes in the 1 m DEM (:func:`step_height_m`), which the wall units
read as a GNS-only wall's height. The candidate wall lines this module once
built for exposure rw step 6 (``gen_wall_lines.py``) were removed on
2026-10-08: the wall population is now drawn from the wall units of exposure rw
step 6.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import (
    Point,
)

from landloss.common.utils.terrain import sample_at_points

# The GNS SLIDE morphology ``Type`` that is a retaining wall [townsend_2020].
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"

# The GNS SLIDE morphology ``Type`` that marks the line between a cut and a fill
# [townsend_2020]; 2,421 lines, about 240 km, over Wellington City.
CUT_FILL_LINE_TYPE = "Cut/fill line"


# How often the face height raster is read along a line.
FACE_SAMPLE_SPACING_M = 1.0

# The step test for a property boundary or a road frontage, read off the 1 m
# DEM at every sample along the line: the rise across a short span either side
# (twice STEP_NEAR_M) against the rise across a span three times as long
# (twice STEP_FAR_M). An even hillside rises three times as far over the long
# span as over the short one, so the excess, (3 x short - long) / 2, is zero
# on it and equals the height of a step concentrated at the line. A short span
# of 3 m allows for the surveyed boundary lying a metre or so off the wall.
STEP_NEAR_M = 1.5
STEP_FAR_M = 3.0 * STEP_NEAR_M


# The two wall positions. A fill wall holds the platform above it; a cut wall
# holds the face behind it.
WALL_POSITIONS = ("fill", "cut")
FILL, CUT = WALL_POSITIONS


# A split point closer than this to a line's end is the end, not a cut.
_END_TOLERANCE_M = 1e-6


def step_height_m(
    lines: gpd.GeoSeries,
    dem_path: Path,
    *,
    spacing_m: float,
    near_m: float = STEP_NEAR_M,
    far_m: float = STEP_FAR_M,
) -> pd.Series:
    """Measure the step the ground makes across each line, from the 1 m DEM.

    At samples ``spacing_m`` apart along the line the DEM is read at
    ``near_m`` and ``far_m`` either side, square to the line. With ``short``
    and ``long`` the rises across the two spans, the step is
    ``(r * short - long) / (r - 1)`` for ``r = far_m / near_m``: zero on an
    even hillside, whose rise grows with the span, and the height of a step
    concentrated at the line, which the two spans share. A step against the
    fall of the slope reads as positive too. The line's step is the median
    over its samples, so a boundary with a step along half its length or less
    reads below that step.

    Args:
        lines: The lines, in a projected system.
        dem_path: The 1 m DEM, in metres.
        spacing_m: How far apart the samples are along the line. A line
            shorter than this is read at its midpoint.
        near_m: Half the short span, in metres.
        far_m: Half the long span, in metres; more than ``near_m``.

    Returns:
        The median step per line in metres, on ``lines.index``; NaN where no
        sample could be read on both spans.

    Raises:
        ValueError: If ``far_m`` is not more than ``near_m``.
    """
    owners, _, steps = _station_steps(
        lines, dem_path, spacing_m=spacing_m, near_m=near_m, far_m=far_m
    )
    if owners.size == 0:
        return pd.Series(np.nan, index=lines.index, dtype=float)
    values = pd.Series(steps, index=owners)
    # A pandas median skips NaN, and an all-NaN group is NaN.
    return values.groupby(level=0, sort=False).median().reindex(lines.index)


def _station_steps(
    lines: gpd.GeoSeries,
    dem_path: Path,
    *,
    spacing_m: float,
    near_m: float,
    far_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the owner, distance along and step at every sample of every line.

    The estimator of :func:`step_height_m`, before the median: one row per
    sample, in line order and then distance order. Samples where the line has
    no direction are skipped.

    Raises:
        ValueError: If ``far_m`` is not more than ``near_m``.
    """
    if far_m <= near_m:
        msg = f"far_m ({far_m}) must be more than near_m ({near_m})"
        raise ValueError(msg)
    empty = np.empty(0)
    if lines.empty:
        return np.empty(0, dtype=object), empty, empty
    owners: list[object] = []
    stations: list[Point] = []
    along: list[float] = []
    normals: list[tuple[float, float]] = []
    for label, line in lines.items():
        length = line.length
        if length < spacing_m:
            distances = np.array([length / 2.0])
        else:
            distances = np.arange(0.0, length + _END_TOLERANCE_M, spacing_m)
        for distance in distances:
            ahead = line.interpolate(min(float(distance) + 0.5, length))
            behind = line.interpolate(max(float(distance) - 0.5, 0.0))
            east, north = ahead.x - behind.x, ahead.y - behind.y
            norm = float(np.hypot(east, north))
            if norm == 0.0:
                continue
            owners.append(label)
            along.append(float(distance))
            stations.append(line.interpolate(float(distance)))
            # The unit normal, a quarter turn left of the line's direction.
            normals.append((-north / norm, east / norm))
    if not stations:
        return np.empty(0, dtype=object), empty, empty
    x = np.array([point.x for point in stations])
    y = np.array([point.y for point in stations])
    normal = np.asarray(normals)

    def read(offset: float) -> np.ndarray:
        points = gpd.GeoSeries(
            shapely.points(x + offset * normal[:, 0], y + offset * normal[:, 1]),
            crs=lines.crs,
        )
        return sample_at_points(dem_path, points).to_numpy(dtype=float)

    short = read(near_m) - read(-near_m)
    long = read(far_m) - read(-far_m)
    ratio = far_m / near_m
    steps = np.abs(ratio * short - long) / (ratio - 1.0)
    owner_array = np.empty(len(owners), dtype=object)
    owner_array[:] = owners
    return owner_array, np.asarray(along), steps
