"""Toy terrain for developing the slope elements: stage D1 of the plan.

Each case of the Development table in
``.agents/plans/building-face-based-urban-slope-polygons.md`` is built here as
a 1 m DEM on a north-up grid with a ground group grid beside it, so the
growth and polygon rules can be watched on ground whose answer is known. The
expected outcome of every case is written down in
``src/scripts/landloss/hazard/landslide/research/slope_elements/toy_slope_elements.md``
before it is run, and each case is a regression test.

Every profile but case 6 runs west to east along the columns, the ground
falling to the east (a downhill bearing of 90 degrees), and is the same along
every row. Elevations are the profile read at each cell centre, so a vertical
wall between two cell centres is a clean step. Each case keeps a margin of
level ground or plain slope at its edges wider than the 9 m step estimator and
the 3 m slope reach, so the grid edge, where those read NaN, touches no
feature.

LiDAR-like noise is optional: independent normal errors per cell, drawn from a
seeded numpy generator so a noisy case is the same every run. Real LiDAR DEM
error is spatially correlated and smoothed by gridding, so the noisy cases
test robustness to noise, not to a survey's error.

Any profile case can be turned to fall towards another bearing
(:func:`rotate_toy_case`), on a square grid, so the measurement can be checked
off the grid's axes. Cases 13 (two 3 m soil-like batters, at 37 and 33
degrees, either side of the soil-like step test angle) were added in stage D1
after the review of the first build; they are not in the plan's table.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray
from rasterio.transform import Affine

from landloss.hazard.landslide.slope_elements import (
    SOIL_LIKE_CODE,
    WEAK_ROCK_CODE,
)

# The NZTM corner every toy grid hangs from: a round point in Wellington, the
# origin the terrain tests use.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0

# The cell size of every toy grid, in metres: the LINZ 1 m DEM's.
CELL_SIZE_M = 1.0

# Judgement: the standard deviation of the LiDAR-like noise, in metres. LINZ
# states the vertical accuracy of its LiDAR surveys as about 0.1 m at 95%
# confidence, which is a standard deviation of about 0.05 m; that statement is
# not yet a doc/references.bib entry, so the value is held as judgement.
BETA_LIDAR_NOISE_SD_M = 0.05

# How many rows (north to south) every profile case spans, in metres.
PROFILE_WIDTH_M = 40.0

# The side of the square grid a turned profile case is drawn on, in metres.
ROTATED_SIZE_M = 80.0


@dataclass(frozen=True)
class ToyTerrain:
    """One toy case.

    Attributes:
        name: The case's key in :data:`TOY_CASES`.
        description: What the case is, in the plan's words.
        dem: Ground elevation in metres, north-up.
        ground_group: The ground group code of every cell.
        transform: The grid's affine transform, cell corner based.
        features_x_m: Named positions along the profile, in metres east of the
            grid's west edge (the wall, the crest, the toe), for checks and
            figures; on a turned case, metres along the fall line from the
            profile's start.
        profile: For a profile case, the elevation along the profile as a
            function of the distance from its start; None otherwise.
        profile_length_m: The profile's length, None where there is none.
    """

    name: str
    description: str
    dem: NDArray[np.float64]
    ground_group: NDArray[np.int8]
    transform: Affine
    features_x_m: dict[str, float]
    profile: Callable[[NDArray[np.float64]], NDArray[np.float64]] | None = None
    profile_length_m: float | None = None


def _transform() -> Affine:
    return Affine(CELL_SIZE_M, 0.0, ORIGIN_EASTING, 0.0, -CELL_SIZE_M, ORIGIN_NORTHING)


def _centres(length_m: float) -> NDArray[np.float64]:
    """The cell centre positions along a profile ``length_m`` long."""
    return (np.arange(round(length_m / CELL_SIZE_M)) + 0.5) * CELL_SIZE_M


def _drop(
    x: NDArray[np.float64], start: float, end: float, angle_deg: float
) -> NDArray[np.float64]:
    """The fall of a straight slope from ``start`` to ``end`` at ``angle_deg``."""
    return np.clip(x - start, 0.0, end - start) * math.tan(math.radians(angle_deg))


def _profile_case(
    name: str,
    description: str,
    length_m: float,
    profile: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    group: int,
    features_x_m: dict[str, float],
) -> ToyTerrain:
    """A case whose ground is one west-to-east profile on every row."""
    x = _centres(length_m)
    rows = round(PROFILE_WIDTH_M / CELL_SIZE_M)
    dem = np.tile(profile(x), (rows, 1))
    return ToyTerrain(
        name=name,
        description=description,
        dem=dem,
        ground_group=np.full(dem.shape, group, dtype=np.int8),
        transform=_transform(),
        features_x_m=features_x_m,
        profile=profile,
        profile_length_m=length_m,
    )


def retaining_wall(height_m: float = 2.0) -> ToyTerrain:
    """Case 1: a vertical wall on fill, level ground above and below.

    Args:
        height_m: The wall's height; the plan's case 1 is 2 m.

    Returns:
        The case.
    """
    wall = 20.0
    return _profile_case(
        "01_wall",
        f"A {height_m:g} m vertical retaining wall, level ground above and below",
        40.0,
        lambda x: np.where(x < wall, height_m, 0.0),
        SOIL_LIKE_CODE,
        {"wall": wall},
    )


def wall_with_rising_ground() -> ToyTerrain:
    """Case 2: the case 1 wall with ground rising at 20 degrees behind it."""
    top, wall = 12.0, 27.0
    return _profile_case(
        "02_wall_rising_behind",
        "The same wall with ground rising at 20 degrees behind it",
        45.0,
        lambda x: (
            np.where(x < wall, 2.0, 0.0)
            + _drop(x, top, wall, 20.0)[-1]
            - _drop(x, top, wall, 20.0)
        ),
        SOIL_LIKE_CODE,
        {"bank_crest": top, "wall": wall},
    )


def _excavated_toe(name: str, cut_height_m: float, bank_angle_deg: float) -> ToyTerrain:
    """A 60 degree cut of ``cut_height_m`` at the foot of a 26 m long bank."""
    crest = 10.0
    bank_toe = crest + 26.0
    cut_toe = bank_toe + cut_height_m / math.tan(math.radians(60.0))
    bank = _drop(_centres(65.0), crest, bank_toe, bank_angle_deg)[-1]
    top = bank + cut_height_m

    def profile(x: NDArray[np.float64]) -> NDArray[np.float64]:
        return (
            top
            - _drop(x, crest, bank_toe, bank_angle_deg)
            - _drop(x, bank_toe, cut_toe, 60.0)
        )

    return _profile_case(
        name,
        f"A {cut_height_m:g} m cut at 60 degrees at the foot of a "
        f"{bank_angle_deg:g} degree slope {bank:.1f} m high, soil-like ground",
        65.0,
        profile,
        SOIL_LIKE_CODE,
        {"bank_crest": crest, "cut_crest": bank_toe, "cut_toe": cut_toe},
    )


def excavated_toe_4m() -> ToyTerrain:
    """Case 3: a 4 m cut at 60 degrees under a 30 degree bank 15 m high."""
    return _excavated_toe("03_excavated_toe_4m", 4.0, 30.0)


def excavated_toe_2m() -> ToyTerrain:
    """Case 3, second part: the same with a 2 m cut."""
    return _excavated_toe("03_excavated_toe_2m", 2.0, 30.0)


def cut_under_gentle_slope() -> ToyTerrain:
    """Case 4: the 4 m cut under a 15 degree slope."""
    return _excavated_toe("04_cut_under_gentle_slope", 4.0, 15.0)


def _terraces(name: str, bench_m: float) -> ToyTerrain:
    upper = 20.0
    lower = upper + bench_m
    return _profile_case(
        name,
        f"Two terraces, each with a 2 m wall, with a bench {bench_m:g} m wide "
        "between them",
        45.0,
        lambda x: np.where(x < upper, 2.0, 0.0) + np.where(x < lower, 2.0, 0.0),
        SOIL_LIKE_CODE,
        {"upper_wall": upper, "lower_wall": lower},
    )


def terraces_narrow_bench() -> ToyTerrain:
    """Case 5: two 2 m walls with a 1 m bench between them."""
    return _terraces("05_terraces_narrow_bench", 1.0)


def terraces_wide_bench() -> ToyTerrain:
    """Case 5, second part: two 2 m walls with an 8 m bench between them."""
    return _terraces("05_terraces_wide_bench", 8.0)


def gullies_at_ridge() -> ToyTerrain:
    """Case 6: two gullies whose steep heads meet at a ridge.

    A ridge runs north to south at x = 40 m with flanks falling west and east
    at 15 degrees, under the grow angle, so the flanks are not elements. A
    gully is cut into each flank on the same row, its depth growing from zero
    1 m from the ridge line to 5 m 6 m from it, so each gully head is a bowl
    steeper than 45 degrees that meets the other's at the ridge top.
    """
    ridge, depth, head, sides = 40.0, 5.0, 5.0, 4.0
    x = _centres(80.0)
    y = _centres(40.0)
    centre = 20.0
    across = np.abs(x - ridge)
    flank = 20.0 - across * math.tan(math.radians(15.0))
    deepening = depth * np.clip((across - 1.0) / head, 0.0, 1.0)
    shape = np.exp(-(((y - centre) / sides) ** 2))
    dem = flank[None, :] - shape[:, None] * deepening[None, :]
    return ToyTerrain(
        name="06_gullies_at_ridge",
        description="Two adjacent gullies whose steep heads meet at a ridge",
        dem=dem,
        ground_group=np.full(dem.shape, SOIL_LIKE_CODE, dtype=np.int8),
        transform=_transform(),
        features_x_m={"ridge": ridge, "gully_row_m": centre},
    )


def _gradually(
    x: NDArray[np.float64], start: float, length: float, angle_deg: float
) -> NDArray[np.float64]:
    """The fall over a rounding whose gradient grows evenly from 0 to ``angle_deg``."""
    gradient = math.tan(math.radians(angle_deg))
    along = np.clip(x - start, 0.0, length)
    return gradient * along**2 / (2.0 * length)


def convex_crest() -> ToyTerrain:
    """Case 7: a 45 degree slope rounding gradually over its crest.

    Level ground to x = 10 m, a rounding over 12 m whose gradient grows evenly
    to 45 degrees, a straight 45 degree slope 10 m long, and a sharp toe.
    """
    start, rounding, straight = 10.0, 12.0, 10.0
    gradient = math.tan(math.radians(45.0))
    toe = start + rounding + straight
    round_fall = gradient * rounding / 2.0
    total = round_fall + gradient * straight

    def profile(x: NDArray[np.float64]) -> NDArray[np.float64]:
        return (
            total
            - _gradually(x, start, rounding, 45.0)
            - _drop(x, start + rounding, toe, 45.0)
        )

    def at_gradient(angle_deg: float) -> float:
        return start + rounding * math.tan(math.radians(angle_deg)) / gradient

    return _profile_case(
        "07_convex_crest",
        "A convex slope, rounding gradually over its crest",
        50.0,
        profile,
        SOIL_LIKE_CODE,
        {
            "rounding_start": start,
            "at_30_deg": at_gradient(30.0),
            "at_grow_angle": at_gradient(18.4),
            "straight_start": start + rounding,
            "toe": toe,
        },
    )


def concave_toe() -> ToyTerrain:
    """Case 8: a 45 degree slope easing gradually into its toe.

    Case 7 turned end for end: a sharp crest, a straight 45 degree slope 10 m
    long, and an easing over 12 m whose gradient falls evenly to level.
    """
    crest, straight, easing = 10.0, 10.0, 12.0
    gradient = math.tan(math.radians(45.0))
    ease_start = crest + straight
    total = gradient * straight + gradient * easing / 2.0

    def profile(x: NDArray[np.float64]) -> NDArray[np.float64]:
        along = np.clip(x - ease_start, 0.0, easing)
        eased = gradient * (along - along**2 / (2.0 * easing))
        return total - _drop(x, crest, ease_start, 45.0) - eased

    def at_gradient(angle_deg: float) -> float:
        return ease_start + easing * (
            1.0 - math.tan(math.radians(angle_deg)) / gradient
        )

    return _profile_case(
        "08_concave_toe",
        "A concave slope, easing gradually into its toe",
        50.0,
        profile,
        SOIL_LIKE_CODE,
        {
            "crest": crest,
            "ease_start": ease_start,
            "at_30_deg": at_gradient(30.0),
            "at_grow_angle": at_gradient(18.4),
            "toe": ease_start + easing,
        },
    )


def road_cut() -> ToyTerrain:
    """Case 9: a road cut 200 m long and 4 m high in weak rock.

    A level road along the foot of a 10 degree hillside, with the hillside cut
    back at 60 degrees: the cut is 4 m high for 200 m along the road, and at
    each end the ground above it ramps down to the road over 20 m, so the
    ends are gentle ground (under 15 degrees) rather than steep end walls.
    """
    cut_x, length, ramp = 25.0, 200.0, 20.0
    x = _centres(45.0)
    y = _centres(length + 2 * ramp + 20.0)
    start = 10.0 + ramp
    along = np.clip(
        np.minimum(y - (start - ramp), (start + length + ramp) - y) / ramp, 0.0, 1.0
    )
    height = 4.0 * along
    behind = np.clip(cut_x - x, 0.0, None) * math.tan(math.radians(10.0))
    face = height[:, None] - np.clip(x - cut_x, 0.0, None)[None, :] * math.tan(
        math.radians(60.0)
    )
    dem = np.clip(face, 0.0, None) + behind[None, :]
    return ToyTerrain(
        name="09_road_cut",
        description="A road cut 200 m long and 4 m high",
        dem=dem,
        ground_group=np.full(dem.shape, WEAK_ROCK_CODE, dtype=np.int8),
        transform=_transform(),
        features_x_m={
            "cut_crest": cut_x,
            "cut_start_y_m": start,
            "cut_length_m": length,
        },
    )


def wall_in_bank() -> ToyTerrain:
    """Case 10: a 1.5 m wall halfway down a 25 degree bank."""
    crest, wall, toe = 10.0, 25.0, 40.0
    bank = _drop(_centres(55.0), crest, toe, 25.0)[-1]
    return _profile_case(
        "10_wall_in_bank",
        "A 1.5 m wall halfway down a 25 degree bank",
        55.0,
        lambda x: (
            bank + 1.5 - _drop(x, crest, toe, 25.0) - np.where(x < wall, 0.0, 1.5)
        ),
        SOIL_LIKE_CODE,
        {"bank_crest": crest, "wall": wall, "bank_toe": toe},
    )


def small_step() -> ToyTerrain:
    """Case 11: a 0.3 m step on level ground."""
    step = 20.0
    return _profile_case(
        "11_small_step",
        "A 0.3 m step on level ground",
        40.0,
        lambda x: np.where(x < step, 0.3, 0.0),
        SOIL_LIKE_CODE,
        {"step": step},
    )


def _weak_rock_bank(name: str, height_m: float) -> ToyTerrain:
    crest = 12.0
    toe = crest + height_m / math.tan(math.radians(40.0))
    return _profile_case(
        name,
        f"A bank on weak rock at 40 degrees, {height_m:g} m high",
        toe + 15.0,
        lambda x: height_m - _drop(x, crest, toe, 40.0),
        WEAK_ROCK_CODE,
        {"crest": crest, "toe": toe},
    )


def weak_rock_bank_3m() -> ToyTerrain:
    """Case 12: a bank on weak rock at 40 degrees, 3 m high."""
    return _weak_rock_bank("12_weak_rock_bank_3m", 3.0)


def weak_rock_bank_12m() -> ToyTerrain:
    """Case 12, second part: the same bank 12 m high."""
    return _weak_rock_bank("12_weak_rock_bank_12m", 12.0)


def _soil_batter(name: str, angle_deg: float) -> ToyTerrain:
    height, crest = 3.0, 15.0
    toe = crest + height / math.tan(math.radians(angle_deg))
    return _profile_case(
        name,
        f"A 3 m batter at {angle_deg:g} degrees on soil-like ground, level above "
        "and below",
        toe + 15.0,
        lambda x: height - _drop(x, crest, toe, angle_deg),
        SOIL_LIKE_CODE,
        {"crest": crest, "toe": toe},
    )


def soil_batter_37deg() -> ToyTerrain:
    """Case 13 (added in stage D1): a 3 m soil-like batter at 37 degrees."""
    return _soil_batter("13_soil_batter_37deg", 37.0)


def soil_batter_33deg() -> ToyTerrain:
    """Case 13, second part: the same batter at 33 degrees."""
    return _soil_batter("13_soil_batter_33deg", 33.0)


def gullies_at_bent_ridge() -> ToyTerrain:
    """Case 14 (added in stage D1): two gully heads 60 degrees apart.

    Case 6's ridge is straight, its two gully heads facing 180 degrees apart
    (a mirror pair: each flank's fall bearing is the other's reflection
    across the ridge trace). This ridge bends at a nose instead: the ground
    north of the nose falls towards 60 degrees, the ground south of it
    towards 120 degrees (still a mirror pair, but across a ridge trace
    turned 90 degrees from the bisector of the two bearings, the only axis
    that reflects 60 into 120), both at 15 degrees, under the grow angle, so
    the nose is a true ridge, not two unrelated slopes. Each side stays
    untouched for the first 5 m of fall away from the nose, so the gullies
    cannot merge into one feature at the nose itself, then a gully cuts in
    over the next 5 m, the same shape as case 6's, to 8 m deep. The bend
    pulls the measured aspect in from the nominal bearings (about 67 and 113
    degrees, not 60 and 120, roughly 46 degrees apart), well under
    :data:`~landloss.hazard.landslide.slope_polygons.BETA_FACING_APART_DEG`
    (90 degrees). Their catchments are disjoint, like case 6's, but because
    they do not face apart by more than that threshold, the ground they both
    reach near the nose is kept by both under the width-behind-crest rule
    (:data:`~landloss.hazard.landslide.slope_polygons.WITHIN_WIDTH`), not
    :data:`~landloss.hazard.landslide.slope_polygons.SEPARATE_CATCHMENTS`, as
    stage D1 found case 6's is.
    """
    depth, head, sides, flank_angle, start = 8.0, 5.0, 2.0, 15.0, 5.0
    size = 100.0
    apex_east, apex_north = 50.0, 50.0
    bearings_deg = (60.0, 120.0)
    base_height = 30.0

    col = _centres(size)
    row = _centres(size)
    east = col[None, :] - apex_east
    north = (size - row[:, None]) - apex_north
    north_of_nose = north >= 0.0

    def flank(bearing_deg: float) -> NDArray[np.float64]:
        bearing = math.radians(bearing_deg)
        downhill = np.clip(
            east * math.sin(bearing) + north * math.cos(bearing), 0.0, None
        )
        across = east * math.cos(bearing) - north * math.sin(bearing)
        plane = base_height - downhill * math.tan(math.radians(flank_angle))
        deepening = depth * np.clip((downhill - start) / head, 0.0, 1.0)
        shape = np.exp(-((across / sides) ** 2))
        return plane - shape * deepening

    dem = np.where(north_of_nose, flank(bearings_deg[0]), flank(bearings_deg[1]))

    return ToyTerrain(
        name="14_gullies_at_bent_ridge",
        description="Two gully heads on a bent ridge, meeting 60 degrees apart",
        dem=dem,
        ground_group=np.full(dem.shape, SOIL_LIKE_CODE, dtype=np.int8),
        transform=_transform(),
        features_x_m={
            "apex_east_m": apex_east,
            "apex_north_m": apex_north,
            # The nose's own map northing, where the dem's north_of_nose
            # partition flips; north increases towards row 0, so this is
            # ORIGIN_NORTHING less the nose's distance back from the north
            # edge (size - apex_north).
            "apex_northing_m": ORIGIN_NORTHING - (size - apex_north),
            "bearing_1_deg": bearings_deg[0],
            "bearing_2_deg": bearings_deg[1],
        },
    )


def undulating_hills() -> ToyTerrain:
    """Case 15 (added in stage D1): a bigger grid of undulating hills.

    A 220 m square of rolling ground built from a few sine waves along and
    across the grid, none of them over 15 degrees anywhere, under the grow
    angle, on soil-like ground. Every other case carries one feature the
    growth and polygon rules are meant to find; this one carries none, so it
    is a negative control at a scale closer to a real hillside: no element
    should grow anywhere, with or without LiDAR-like noise.
    """
    size = 220.0
    x = _centres(size)
    y = _centres(size)
    dem = (
        1.5 * np.sin(2.0 * math.pi * x[None, :] / 150.0)
        + 1.5 * np.cos(2.0 * math.pi * y[:, None] / 160.0)
        + 1.2
        * np.sin(2.0 * math.pi * x[None, :] / 90.0 + 1.0)
        * np.cos(2.0 * math.pi * y[:, None] / 110.0 + 0.5)
        + 0.9 * np.sin(2.0 * math.pi * (x[None, :] + y[:, None]) / 80.0)
    )
    return ToyTerrain(
        name="15_undulating_hills",
        description="Rolling hills, none of them steeper than 15 degrees anywhere",
        dem=dem,
        ground_group=np.full(dem.shape, SOIL_LIKE_CODE, dtype=np.int8),
        transform=_transform(),
        features_x_m={},
    )


# Every toy case by its key, in the order of the plan's table.
TOY_CASES: dict[str, Callable[[], ToyTerrain]] = {
    "01_wall": retaining_wall,
    "02_wall_rising_behind": wall_with_rising_ground,
    "03_excavated_toe_4m": excavated_toe_4m,
    "03_excavated_toe_2m": excavated_toe_2m,
    "04_cut_under_gentle_slope": cut_under_gentle_slope,
    "05_terraces_narrow_bench": terraces_narrow_bench,
    "05_terraces_wide_bench": terraces_wide_bench,
    "06_gullies_at_ridge": gullies_at_ridge,
    "07_convex_crest": convex_crest,
    "08_concave_toe": concave_toe,
    "09_road_cut": road_cut,
    "10_wall_in_bank": wall_in_bank,
    "11_small_step": small_step,
    "12_weak_rock_bank_3m": weak_rock_bank_3m,
    "12_weak_rock_bank_12m": weak_rock_bank_12m,
    "13_soil_batter_37deg": soil_batter_37deg,
    "13_soil_batter_33deg": soil_batter_33deg,
    "14_gullies_at_bent_ridge": gullies_at_bent_ridge,
    "15_undulating_hills": undulating_hills,
}


def rotate_toy_case(
    terrain: ToyTerrain, bearing_deg: float, *, size_m: float = ROTATED_SIZE_M
) -> ToyTerrain:
    """Turn a profile case so its ground falls towards another bearing.

    The profile is read at each cell centre's distance along the new fall
    line, the grid's centre at the profile's middle, and held at its end
    values beyond its ends, on a square grid.

    Args:
        terrain: A profile case (one with a ``profile``).
        bearing_deg: The downhill bearing, clockwise from north; 90 is the
            profile cases' own east.
        size_m: The side of the square grid.

    Returns:
        The turned case, its ``features_x_m`` in metres along the fall line
        from the profile's start.

    Raises:
        ValueError: If the case has no profile.
    """
    if terrain.profile is None or terrain.profile_length_m is None:
        msg = f"The toy case {terrain.name!r} is not a profile case."
        raise ValueError(msg)
    centres = _centres(size_m)
    north = size_m / 2.0 - centres
    east = centres - size_m / 2.0
    bearing = math.radians(bearing_deg)
    along = east[None, :] * math.sin(bearing) + north[:, None] * math.cos(bearing)
    length = terrain.profile_length_m
    x = np.clip(along + length / 2.0, 0.0, length)
    dem = terrain.profile(x.ravel()).reshape(x.shape)
    group = int(terrain.ground_group.flat[0])
    return replace(
        terrain,
        name=f"{terrain.name}_bearing_{bearing_deg:g}",
        description=f"{terrain.description}, falling to {bearing_deg:g} degrees",
        dem=dem,
        ground_group=np.full(dem.shape, group, dtype=np.int8),
    )


def add_lidar_noise(terrain: ToyTerrain, *, sd_m: float, seed: int) -> ToyTerrain:
    """Add independent normal noise to a toy DEM.

    Args:
        terrain: The case to add noise to.
        sd_m: The noise's standard deviation in metres, for example
            :data:`BETA_LIDAR_NOISE_SD_M`.
        seed: The seed of the numpy generator, so the noise is repeatable.

    Returns:
        The case with the noisy DEM; nodata stays nodata.
    """
    generator = np.random.default_rng(seed)
    noise = generator.normal(0.0, sd_m, size=terrain.dem.shape)
    return replace(terrain, dem=terrain.dem + noise)


def build_toy_case(name: str, *, noise_sd_m: float, seed: int) -> ToyTerrain:
    """Build one toy case, with noise if ``noise_sd_m`` is over zero.

    Args:
        name: A key of :data:`TOY_CASES`.
        noise_sd_m: The standard deviation of the noise in metres; zero for
            none.
        seed: The seed of the noise generator.

    Returns:
        The case.

    Raises:
        KeyError: If there is no such case.
    """
    if name not in TOY_CASES:
        msg = f"There is no toy case {name!r}; the cases are {sorted(TOY_CASES)}."
        raise KeyError(msg)
    terrain = TOY_CASES[name]()
    if noise_sd_m > 0:
        terrain = add_lidar_noise(terrain, sd_m=noise_sd_m, seed=seed)
    return terrain
