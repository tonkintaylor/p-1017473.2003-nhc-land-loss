"""Slope elements: free-faces and banks grown from seeds on the 1 m DEM.

A slope element is a piece of ground between a crest above it and a toe below
it, grown from one seed. Every element is either a **free-face**, steeper than
its ground can stand unsupported at its height (a retaining wall or an
unsupported oversteep cut), or a **bank**, ground under that angle. Elements
never overlap. This is phase 1 of
``.agents/plans/building-face-based-urban-slope-polygons.md``; the terms are
that plan's.

How an element is found, all of it whole-array numpy and scipy:

1. **Slopes and the fall line.** The 1 m slope is Horn's 3x3 slope on the DEM
   as it is. The 3 m slope is Horn's slope with its neighbours three cells
   away, on the DEM averaged over 3x3 cells, which is the slope of the 3 m
   grid landslide step 3 writes, evaluated at every 1 m cell. The downhill
   direction (the fall line) is read off the 3 m gradient, which is steadier
   on noisy LiDAR, and off the 1 m gradient where the 3 m one has none.
2. **Step height.** At every cell, the drop across 3 m along the fall line
   against the drop across 9 m, ``(3 x short - long) / 2``: the estimator
   :func:`landloss.exposure.rw.lines.step_height_m` uses for property
   boundaries, here as a raster. Zero on an even hillside, the height of a
   step at the cell, and negative values are read as zero.
3. **Each cell's threshold.** The cell's ground group (soil-like, weak rock,
   stronger rock; off the ground map, weak rock) and the height band its step
   height falls in give its threshold angle, ``STEP_ANGLE_DEG[group][band]``.
   The band is only an estimate: the band that decides free-face or bank is
   measured on the grown element.
4. **Seeds.** A cell is eligible where its step height is at least
   :data:`MIN_WALL_HEIGHT_M` or its 3 m slope is over its threshold. Its
   exceedance, the 3 m slope less the threshold, is its priority. A seed is a
   4-connected patch of eligible cells.
5. **Free-face pass.** The seeds grow by marker-controlled watershed on the
   negated exceedance (``scipy.ndimage.watershed_ift``), the strongest cell
   first, only into cells whose 1 m slope is over the seed's threshold less
   :data:`BETA_FREE_FACE_GROW_TOL_DEG`. Each grown region is measured, and a
   region that does not test as a free-face is released and the pass rerun
   without its seed, so the free-face pass keeps only free-faces and the bank
   ground they leave goes to the bank pass.
6. **Bank pass.** The cells left over with a 3 m and a 1 m slope of at least
   :data:`BETA_GROW_ANGLE_DEG` seed, and grow the same way into unclaimed
   cells whose 1 m slope is at least that angle.
7. **Measurement.** Every region is measured on fall-line transects, one from
   each crest cell, and a region under :data:`MIN_WALL_HEIGHT_M` high is
   dropped. Each element is put once into one of the eight
   :data:`HEIGHT_BANDS_M` and tested against ``STEP_ANGLE_DEG`` on its overall
   angle: over it, a free-face; otherwise a bank, whichever pass grew it.

A crest cell is an element cell whose neighbour one cell uphill along the fall
line lies outside the element, a toe cell one whose neighbour downhill does,
and the other boundary cells are the element's ends along the slope. The plan
words this as the outside neighbour being higher or lower; on the level
ground at the top and foot of a wall the outside neighbours are the same
height, so the side is read off the fall line instead.

The element table (:attr:`SlopeElements.elements`) has one row per element,
indexed by its label in :attr:`SlopeElements.labels` (1 to n), with columns:

- ``grown_in``: ``"free_face_pass"`` or ``"bank_pass"``;
- ``element_type``: ``"free_face"`` or ``"bank"``, the step test's answer;
- ``n_cells``, ``area_m2``;
- ``height_m``: crest minus toe elevation, the median over fall-line
  transects; ``height_max_m`` the largest transect;
- ``run_m``: the horizontal distance crest to toe, median over transects;
- ``overall_angle_deg``: ``atan(height_m / run_m)``;
- ``n_transects``: the transects the two above are taken over;
- ``slope_mean_deg``, ``slope_max_deg``: the 1 m slope over the element;
- ``length_m``: the element's extent along the contour, square to its aspect;
- ``aspect_deg``: the circular mean downhill bearing, clockwise from north;
- ``step_peak_m``: the largest step height on the element;
- ``seed_exceedance_deg``: the seed's largest exceedance;
- ``seed_row``, ``seed_col``: the seed's cell of largest exceedance;
- ``ground_group``: the majority ground group, as a :data:`GROUND_GROUPS` name;
- ``height_band``: 1 to 8, from ``height_m``;
- ``threshold_angle_deg``: ``STEP_ANGLE_DEG`` for the group and band;
- ``angle_excess_deg``: ``overall_angle_deg`` less the threshold;
- ``mm6_cut``: steeper than 50 degrees and higher than 3 m, the cut that fails
  at MM6 [brabhaharan_2018; hancox_2015];
- ``hb1995_cut``: steeper than 45 degrees and higher than 5 m, high to very
  high susceptibility in closely jointed greywacke [hancox_brabhaharan_1995];
- ``own_catchment_area_m2``: the 3 m cells whose flow reaches this element
  before any other (see :attr:`SlopeElements.catchments`);
- ``centroid_x``, ``centroid_y``: the mean cell centre, in map units;
- one ``majority_<name>`` column per categorical grid passed in.

The DEM survey year (plan phase 0) is not carried yet: no DEM source mask
exists. Material, modification and ``ground_id`` come in as categorical grids
(``categories``) rasterised by the caller, for example with
:func:`rasterise_ground_map`.

Everything takes arrays and a transform and holds no state, so a tile of a
larger grid is processed the same way as a whole grid; ``core`` keeps only the
elements whose seed lies in a tile's core.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from landloss.domain.constants import MIN_WALL_HEIGHT_M
from landloss.hazard.landslide.ground_map import MATERIALS

# The three ground groups the step test reads, in the order of their integer
# codes on a ground group grid (0, 1, 2).
SOIL_LIKE = "soil_like"
WEAK_ROCK = "weak_rock"
STRONGER_ROCK = "stronger_rock"
GROUND_GROUPS = (SOIL_LIKE, WEAK_ROCK, STRONGER_ROCK)
SOIL_LIKE_CODE = GROUND_GROUPS.index(SOIL_LIKE)
WEAK_ROCK_CODE = GROUND_GROUPS.index(WEAK_ROCK)
STRONGER_ROCK_CODE = GROUND_GROUPS.index(STRONGER_ROCK)

# Ground off the ground map is tested as weak rock (the plan, phase 1).
OFF_MAP_GROUND_GROUP = WEAK_ROCK

# The ground map's materials in their groups (the plan's step test table).
# Crushed rock joins the soil-like group because NZGS Figure 35 has no row for
# it and Grant-Taylor reduces stable angles by 5 to 10 degrees for jointing,
# which takes the weak rock 45 degrees to about 35 [grant_taylor_1964;
# nzgs_2025_torlesse]. Unknown ground is weak rock, like ground off the map.
MATERIAL_GROUND_GROUP: dict[str, str] = {
    "rock": WEAK_ROCK,
    "rock_uw_mw": STRONGER_ROCK,
    "rock_hw_cw": WEAK_ROCK,
    "rock_crushed": SOIL_LIKE,
    "colluvium": SOIL_LIKE,
    "loess": SOIL_LIKE,
    "alluvium": SOIL_LIKE,
    "fill_engineered": SOIL_LIKE,
    "fill_uncontrolled": SOIL_LIKE,
    "reclamation": SOIL_LIKE,
    "unknown": WEAK_ROCK,
}

# The lower edge of each of the eight height bands, in metres (the plan, phase
# 1, confirmed by the lead on 2026-10-02). Band k runs from its edge to the
# next; band 8 has no top. The breaks: MIN_WALL_HEIGHT_M and the small/medium
# costing break (0.5, 1.0); the Building Act consent exemption
# [nz_parliament_2004] and Anderson et al.'s classes [anderson_2015] (1.5, 2.5,
# 3.5); NZGS Figure 35 [nzgs_2025_torlesse] (6, 10, 16); above 16 m,
# Grant-Taylor's envelope [grant_taylor_1964].
HEIGHT_BANDS_M = (MIN_WALL_HEIGHT_M, 1.0, 1.5, 2.5, 3.5, 6.0, 10.0, 16.0)
N_HEIGHT_BANDS = len(HEIGHT_BANDS_M)

# The steepest overall angle, in degrees, each ground group stands unsupported
# at in each height band (bands 1 to 8); an element steeper than its entry is a
# free-face (the plan, phase 1, the 24 numbers confirmed by the lead as written
# on 2026-10-02). The rock rows are NZGS Unit 7C.2 Figure 35, the maximum
# unsupported cut angles near Wellington housing [nzgs_2025_torlesse]: highly
# and completely weathered rock 1 on 1 to 10 m and 2 on 3 to 16 m, moderately
# weathered 4 on 3 to 6 m; the degree conversions are ours, and band 8 keeps
# the 10 to 16 m angle. The soil-like 35 degrees is judgement, a round number
# inside the published friction angles for this ground and at the floor of
# Figure 35 [nzgs_2025_torlesse; brown_larkin_2005; monteith_2020;
# lyndsell_2019].
STEP_ANGLE_DEG: dict[str, tuple[float, ...]] = {
    SOIL_LIKE: (35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
    WEAK_ROCK: (45.0, 45.0, 45.0, 45.0, 45.0, 45.0, 34.0, 34.0),
    STRONGER_ROCK: (53.0, 53.0, 53.0, 53.0, 53.0, 45.0, 34.0, 34.0),
}

# Judgement, not a published stopping rule: the bank pass grows only over
# ground at least this steep, and ground under it is a bench, a platform or
# open gentle hillside. 18.4 degrees (1V:3H) is the slope above which the
# Auckland Unitary Plan flags land on soils other than recent sediments as
# possibly unstable [de_vilder_2024] (devilder2024-F12), written as a screening
# slope; its use to stop growth is ours. Proposed in the plan, to be settled in
# stages D1 and D2.
BETA_GROW_ANGLE_DEG = 18.4

# Judgement: the free-face pass grows into cells whose 1 m slope is over the
# seed's threshold angle less this many degrees, so the rounded edge cells of a
# wall stay with it while a bank under the threshold above it does not.
# Proposed in the plan, to be settled in stages D1 and D2.
BETA_FREE_FACE_GROW_TOL_DEG = 5.0

# Judgement: how far uphill of an element's crest the stack links look for the
# toe of the element above, in metres. Wider than any width behind a crest the
# plan's phase 3 rules give an element up to band 7 (1.4 H behind a vertical
# wall at 16 m is about 22 m).
BETA_STACK_SEARCH_M = 25.0

# The cut that fails at MM6: steeper than 50 degrees and higher than 3 m
# [brabhaharan_2018; hancox_2015] (brabhaharan2018-F03, sr2015-016-F05). A
# flag on each element, and the trigger of the phase 3 stack rule.
MM6_CUT_ANGLE_DEG = 50.0
MM6_CUT_HEIGHT_M = 3.0

# High to very high susceptibility in closely jointed greywacke: steeper than
# 45 degrees and higher than 5 m [hancox_brabhaharan_1995] (sr1995-005-F07).
HB1995_CUT_ANGLE_DEG = 45.0
HB1995_CUT_HEIGHT_M = 5.0

# The spans of the step estimator, in metres: the drop across 3 m (twice the
# near offset) against the drop across 9 m (twice the far offset), the spans
# landloss.exposure.rw.lines uses for property boundaries.
STEP_NEAR_M = 1.5
STEP_FAR_M = 3.0 * STEP_NEAR_M

# The span of the coarse slope, in metres: the 3 m slope that ranks the seeds.
COARSE_SLOPE_M = 3.0

# How far a fall-line transect or a stack search moves per sample, in cells.
# Half a cell, so a transect at an angle to the grid does not jump a cell.
WALK_STEP_CELLS = 0.5

# The names of the two passes and the two element types, as written to the
# element table.
FREE_FACE_PASS = "free_face_pass"
BANK_PASS = "bank_pass"
FREE_FACE = "free_face"
BANK = "bank"

# Bit flags on the edge role grid: a cell can be on the crest and the toe at
# once, where an element is one cell thick along its fall line.
CREST = 1
TOE = 2
END = 4

# The label of a cell outside every element.
OUTSIDE = 0

# The neighbourhood every label is connected over: cells sharing an edge.
FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)

# The integer cost range scipy's watershed_ift accepts (uint16). The top value
# is kept for the cells growth may not enter.
_COST_SCALE = 10.0
_BARRIER_COST = np.iinfo(np.uint16).max
_EXCEEDANCE_CAP_DEG = 90.0

# The most times the free-face pass is rerun after releasing the seeds that
# did not grow into a free-face.
_MAX_FREE_FACE_ROUNDS = 6

# A gradient smaller than this, in metres per metre, has no direction.
_LEVEL_GRADIENT = 1e-9

# Slopes are compared with this much slack in degrees, so ground built at
# exactly a limit angle reads the same whatever the floating point rounding.
_ANGLE_SLACK_DEG = 1e-6


@dataclass(frozen=True)
class TerrainLayers:
    """The per-cell layers the elements are grown from.

    Attributes:
        slope_fine_deg: Horn's slope on the DEM's own cells (the 1 m slope).
        slope_coarse_deg: Horn's slope over :data:`COARSE_SLOPE_M` (the 3 m
            slope), at every fine cell.
        downhill_row: The fall line's component along the rows (south on a
            north-up grid), a unit vector with ``downhill_col``. NaN where the
            ground has no downhill direction.
        downhill_col: The fall line's component along the columns (east).
        step_height_m: The step height at every cell, zero or more; NaN where
            the estimator reaches off the grid.
    """

    slope_fine_deg: NDArray[np.float64]
    slope_coarse_deg: NDArray[np.float64]
    downhill_row: NDArray[np.float64]
    downhill_col: NDArray[np.float64]
    step_height_m: NDArray[np.float64]


@dataclass(frozen=True)
class SlopeElements:
    """The slope elements found on one grid.

    Attributes:
        labels: The element label of every cell, :data:`OUTSIDE` off every
            element; labels run from 1 and index :attr:`elements`.
        edge_roles: Bit flags per cell, :data:`CREST`, :data:`TOE` and
            :data:`END`, zero inside an element and off it.
        elements: One row per element; the columns are listed in the module
            docstring.
        stack_links: One row per pair of elements where the toe of the upper
            meets the crest of the lower, directly or across a bench:
            ``lower``, ``upper``, ``bench_width_m`` (median over the crest
            cells that reach the upper element), ``bench_width_min_m``,
            ``n_transects`` and ``share_of_crest`` (of the lower's crest
            cells).
        catchments: On the coarse grid, the label of the first element each
            cell's D8 flow reaches (itself for an element cell), or
            :data:`OUTSIDE` where it reaches none.
        catchment_transform: The coarse grid's affine transform.
        drainage_links: One row per pair where cells of ``upper`` flow
            straight on into ``lower``, with ``n_cells``. With
            :attr:`catchments` this gives each element's whole upslope
            catchment: its own cells plus those of every element draining
            into it.
        layers: The per-cell layers the elements were grown from.
    """

    labels: NDArray[np.int32]
    edge_roles: NDArray[np.uint8]
    elements: pd.DataFrame
    stack_links: pd.DataFrame
    catchments: NDArray[np.int32]
    catchment_transform: Affine
    drainage_links: pd.DataFrame
    layers: TerrainLayers


def ground_group_codes(materials: ArrayLike) -> NDArray[np.int8]:
    """Map ground map materials onto ground group codes.

    Args:
        materials: Material names from :data:`MATERIALS`; None or NaN is ground
            off the map.

    Returns:
        The code of each material's group, the index into
        :data:`GROUND_GROUPS`. Off-map ground takes
        :data:`OFF_MAP_GROUND_GROUP`.

    Raises:
        ValueError: If a material is not one the ground map writes.
    """
    values = pd.Series(np.asarray(materials, dtype=object).ravel())
    known = values.isna() | values.isin(MATERIALS)
    if not known.all():
        unknown = sorted({str(value) for value in values[~known]})
        msg = f"These materials are not ground map materials: {unknown}."
        raise ValueError(msg)

    codes = {
        name: GROUND_GROUPS.index(group)
        for name, group in MATERIAL_GROUND_GROUP.items()
    }
    mapped = values.map(codes).fillna(GROUND_GROUPS.index(OFF_MAP_GROUND_GROUP))
    shape = np.shape(np.asarray(materials, dtype=object))
    return mapped.to_numpy(dtype=np.int8).reshape(shape)


def height_band(height_m: ArrayLike) -> NDArray[np.int8]:
    """Put heights into the eight height bands.

    Args:
        height_m: Heights in metres.

    Returns:
        The band of each height, 1 to 8, and 0 for a height under
        :data:`MIN_WALL_HEIGHT_M` or NaN. A height on a break falls in the band
        above it.
    """
    heights = np.asarray(height_m, dtype=float)
    bands = np.searchsorted(np.asarray(HEIGHT_BANDS_M), heights, side="right")
    bands = np.where(np.isfinite(heights), bands, 0)
    return bands.astype(np.int8)


def step_angle_deg(group: ArrayLike, band: ArrayLike) -> NDArray[np.float64]:
    """Look up the step test angle for ground groups and height bands.

    Args:
        group: Ground group codes, indices into :data:`GROUND_GROUPS`.
        band: Height bands, 1 to 8; a band of 0 (under the minimum height)
            reads band 1, so a cell's estimate always has a threshold.

    Returns:
        The angle in degrees, broadcast over the two inputs.
    """
    table = np.array([STEP_ANGLE_DEG[name] for name in GROUND_GROUPS], dtype=float)
    groups = np.asarray(group, dtype=np.intp)
    columns = np.clip(np.asarray(band, dtype=np.intp), 1, N_HEIGHT_BANDS) - 1
    return table[groups, columns]


def _horn_gradient(
    elevation: NDArray[np.float64], cell_size_m: float, span_cells: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Horn's gradient with its neighbours ``span_cells`` away, in array axes.

    Returns:
        ``(rise_along_rows, rise_along_cols)`` in metres per metre; NaN on the
        border the kernel does not fit and where the centre cell is NaN.
    """
    rows, cols = elevation.shape
    s = span_cells
    along_rows = np.full(elevation.shape, np.nan)
    along_cols = np.full(elevation.shape, np.nan)
    if rows <= 2 * s or cols <= 2 * s:
        return along_rows, along_cols

    def shifted(d_row: int, d_col: int) -> NDArray[np.float64]:
        return elevation[
            s + d_row * s : rows - s + d_row * s, s + d_col * s : cols - s + d_col * s
        ]

    across_cols = (shifted(-1, 1) + 2 * shifted(0, 1) + shifted(1, 1)) - (
        shifted(-1, -1) + 2 * shifted(0, -1) + shifted(1, -1)
    )
    across_rows = (shifted(1, -1) + 2 * shifted(1, 0) + shifted(1, 1)) - (
        shifted(-1, -1) + 2 * shifted(-1, 0) + shifted(-1, 1)
    )
    run = 8.0 * s * cell_size_m
    hole = np.isnan(shifted(0, 0))
    along_rows[s:-s, s:-s] = np.where(hole, np.nan, across_rows / run)
    along_cols[s:-s, s:-s] = np.where(hole, np.nan, across_cols / run)
    return along_rows, along_cols


def _window_mean(elevation: NDArray[np.float64], size: int) -> NDArray[np.float64]:
    """Mean over a ``size`` square window, NaN wherever the window is not full."""
    valid = np.isfinite(elevation)
    filled = np.where(valid, elevation, 0.0)
    total = ndimage.uniform_filter(filled, size=size, mode="constant", cval=0.0)
    share = ndimage.uniform_filter(valid.astype(float), size=size, mode="constant")
    return np.where(share > 1.0 - 1e-9, total, np.nan)


def _slope_from(
    along_rows: NDArray[np.float64], along_cols: NDArray[np.float64]
) -> NDArray[np.float64]:
    return np.degrees(np.arctan(np.hypot(along_rows, along_cols)))


def step_height_raster(
    dem: NDArray[np.float64],
    downhill_row: NDArray[np.float64],
    downhill_col: NDArray[np.float64],
    cell_size_m: float,
) -> NDArray[np.float64]:
    """Measure the step the ground makes at every cell, along the fall line.

    The drop across 3 m (``short``, from 1.5 m uphill to 1.5 m downhill)
    against the drop across 9 m (``long``), ``(3 x short - long) / 2``, with the
    DEM read by bilinear interpolation: zero on an even hillside, ``H`` at a
    step of height ``H`` in it, and a quarter of ``H`` a cell or so either side.
    It also reads a break in slope as a step, up to 1.5 m times the gradient
    below the break, 1.5 m in from it.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        downhill_row: The fall line's row component (a unit vector with
            ``downhill_col``), NaN where there is none.
        downhill_col: The fall line's column component.
        cell_size_m: The cell size in metres.

    Returns:
        The step height in metres, zero where the drop is no more than the
        hillside's (a negative reading is not a step), zero where there is no
        fall line, and NaN where a span reaches off the grid or into nodata.
    """
    rows, cols = np.indices(dem.shape, dtype=float)
    has_direction = np.isfinite(downhill_row) & np.isfinite(downhill_col)
    d_row = np.where(has_direction, downhill_row, 0.0)
    d_col = np.where(has_direction, downhill_col, 0.0)

    def drop(offset_m: float) -> NDArray[np.float64]:
        offset = offset_m / cell_size_m
        uphill = ndimage.map_coordinates(
            dem,
            [rows - offset * d_row, cols - offset * d_col],
            order=1,
            mode="constant",
            cval=np.nan,
        )
        downhill = ndimage.map_coordinates(
            dem,
            [rows + offset * d_row, cols + offset * d_col],
            order=1,
            mode="constant",
            cval=np.nan,
        )
        return uphill - downhill

    short = drop(STEP_NEAR_M)
    long = drop(STEP_FAR_M)
    step = np.maximum((3.0 * short - long) / 2.0, 0.0)
    step = np.where(has_direction, step, 0.0)
    return np.where(np.isfinite(short) & np.isfinite(long), step, np.nan)


def terrain_layers(dem: NDArray[np.float64], cell_size_m: float) -> TerrainLayers:
    """Compute the slopes, the fall line and the step height of a DEM.

    Args:
        dem: Ground elevation in metres on a north-up grid, NaN for nodata.
        cell_size_m: The cell size in metres.

    Returns:
        The layers, on the grid of ``dem``.

    Raises:
        ValueError: If the cell size is not positive or is over the coarse
            slope's span.
    """
    if cell_size_m <= 0 or cell_size_m > COARSE_SLOPE_M:
        msg = (
            f"The cell size has to be positive and no more than {COARSE_SLOPE_M} m, "
            f"but {cell_size_m} was given."
        )
        raise ValueError(msg)
    elevation = np.asarray(dem, dtype=float)
    span = max(round(COARSE_SLOPE_M / cell_size_m), 1)

    fine_rows, fine_cols = _horn_gradient(elevation, cell_size_m, 1)
    smooth = _window_mean(elevation, span) if span > 1 else elevation
    coarse_rows, coarse_cols = _horn_gradient(smooth, cell_size_m, span)

    coarse_size = np.hypot(coarse_rows, coarse_cols)
    use_coarse = np.isfinite(coarse_size) & (coarse_size > _LEVEL_GRADIENT)
    grad_rows = np.where(use_coarse, coarse_rows, fine_rows)
    grad_cols = np.where(use_coarse, coarse_cols, fine_cols)
    size = np.hypot(grad_rows, grad_cols)
    with np.errstate(invalid="ignore", divide="ignore"):
        has_direction = np.isfinite(size) & (size > _LEVEL_GRADIENT)
        downhill_row = np.where(has_direction, -grad_rows / size, np.nan)
        downhill_col = np.where(has_direction, -grad_cols / size, np.nan)

    return TerrainLayers(
        slope_fine_deg=_slope_from(fine_rows, fine_cols),
        slope_coarse_deg=_slope_from(coarse_rows, coarse_cols),
        downhill_row=downhill_row,
        downhill_col=downhill_col,
        step_height_m=step_height_raster(
            elevation, downhill_row, downhill_col, cell_size_m
        ),
    )


def _cell_size(transform: Affine) -> float:
    """The square cell size of a north-up transform."""
    if transform.b != 0 or transform.d != 0 or transform.e >= 0:
        msg = "The grid has to be north-up with no rotation."
        raise ValueError(msg)
    if not math.isclose(transform.a, -transform.e):
        msg = f"The cells have to be square, not {transform.a} by {-transform.e}."
        raise ValueError(msg)
    return float(transform.a)


def _neighbour(
    labels: NDArray[np.int32],
    rows: NDArray[np.intp],
    cols: NDArray[np.intp],
    d_row: NDArray[np.intp],
    d_col: NDArray[np.intp],
) -> NDArray[np.int32]:
    """The label of the cell at an offset from each cell, OUTSIDE off the grid."""
    target_rows = rows + d_row
    target_cols = cols + d_col
    inside = (
        (target_rows >= 0)
        & (target_rows < labels.shape[0])
        & (target_cols >= 0)
        & (target_cols < labels.shape[1])
    )
    found = np.full(rows.shape, OUTSIDE, dtype=np.int32)
    found[inside] = labels[target_rows[inside], target_cols[inside]]
    return found


def _edge_roles(labels: NDArray[np.int32], layers: TerrainLayers) -> NDArray[np.uint8]:
    """Mark each element's crest, toe and end cells."""
    roles = np.zeros(labels.shape, dtype=np.uint8)
    rows, cols = np.nonzero(labels > OUTSIDE)
    own = labels[rows, cols]
    d_row = layers.downhill_row[rows, cols]
    d_col = layers.downhill_col[rows, cols]
    has_direction = np.isfinite(d_row) & np.isfinite(d_col)
    step_rows = np.rint(np.where(has_direction, d_row, 0.0)).astype(np.intp)
    step_cols = np.rint(np.where(has_direction, d_col, 0.0)).astype(np.intp)

    uphill = _neighbour(labels, rows, cols, -step_rows, -step_cols)
    downhill = _neighbour(labels, rows, cols, step_rows, step_cols)
    crest = has_direction & (uphill != own)
    toe = has_direction & (downhill != own)

    boundary = np.zeros(rows.shape, dtype=bool)
    for d_r, d_c in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        offset_r = np.full(rows.shape, d_r, dtype=np.intp)
        offset_c = np.full(rows.shape, d_c, dtype=np.intp)
        boundary |= _neighbour(labels, rows, cols, offset_r, offset_c) != own
    end = boundary & ~crest & ~toe

    flags = crest * CREST + toe * TOE + end * END
    roles[rows, cols] = flags.astype(np.uint8)
    return roles


def _walk(
    labels: NDArray[np.int32],
    start_rows: NDArray[np.intp],
    start_cols: NDArray[np.intp],
    d_row: NDArray[np.float64],
    d_col: NDArray[np.float64],
    max_steps: int,
) -> tuple[NDArray[np.intp], NDArray[np.intp], NDArray[np.int32], NDArray[np.intp]]:
    """Walk from cells along a direction until each walk leaves its own label.

    Returns:
        ``(last_rows, last_cols, next_label, steps)``: the last cell of the
        walk's own label, the label of the first cell past it (OUTSIDE off the
        grid or when ``max_steps`` ran out), and the steps taken.
    """
    own = labels[start_rows, start_cols]
    last_rows = start_rows.copy()
    last_cols = start_cols.copy()
    next_label = np.full(own.shape, OUTSIDE, dtype=np.int32)
    steps = np.zeros(own.shape, dtype=np.intp)
    active = np.ones(own.shape, dtype=bool)
    for k in range(1, max_steps + 1):
        index = np.nonzero(active)[0]
        if index.size == 0:
            break
        rows = np.rint(start_rows[index] + k * WALK_STEP_CELLS * d_row[index])
        cols = np.rint(start_cols[index] + k * WALK_STEP_CELLS * d_col[index])
        rows = rows.astype(np.intp)
        cols = cols.astype(np.intp)
        inside = (
            (rows >= 0)
            & (rows < labels.shape[0])
            & (cols >= 0)
            & (cols < labels.shape[1])
        )
        found = np.full(index.shape, OUTSIDE, dtype=np.int32)
        found[inside] = labels[rows[inside], cols[inside]]
        same = inside & (found == own[index])
        last_rows[index[same]] = rows[same]
        last_cols[index[same]] = cols[same]
        steps[index] = k
        left = index[~same]
        next_label[left] = found[~same]
        active[left] = False
    return last_rows, last_cols, next_label, steps


def _transects(
    labels: NDArray[np.int32],
    dem: NDArray[np.float64],
    roles: NDArray[np.uint8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> pd.DataFrame:
    """One fall-line transect from every crest cell to where it leaves its element.

    Returns:
        A frame with ``label``, ``height_m`` and ``run_m``, one row per transect
        that crossed at least one cell.
    """
    rows, cols = np.nonzero((roles & CREST) > 0)
    d_row = layers.downhill_row[rows, cols]
    d_col = layers.downhill_col[rows, cols]
    max_steps = int(2 * (labels.shape[0] + labels.shape[1]) / WALK_STEP_CELLS)
    last_rows, last_cols, _, _ = _walk(labels, rows, cols, d_row, d_col, max_steps)
    run = np.hypot(last_rows - rows, last_cols - cols) * cell_size_m
    height = dem[rows, cols] - dem[last_rows, last_cols]
    crossed = run > 0
    return pd.DataFrame(
        {
            "label": labels[rows, cols][crossed],
            "height_m": height[crossed],
            "run_m": run[crossed],
        }
    )


def _majority(
    labels: NDArray[np.int32], values: NDArray[np.integer], n_labels: int
) -> NDArray[np.int64]:
    """The most common value under each label, -1 where a label has no cells."""
    inside = labels > OUTSIDE
    keys = labels[inside].astype(np.int64)
    found = np.asarray(values)[inside].astype(np.int64)
    result = np.full(n_labels + 1, -1, dtype=np.int64)
    if keys.size == 0:
        return result
    pairs, counts = np.unique(np.stack([keys, found]), axis=1, return_counts=True)
    # Sort by label, then count, so the last pair of each label is its mode.
    order = np.lexsort((counts, pairs[0]))
    pairs = pairs[:, order]
    last = np.r_[pairs[0, 1:] != pairs[0, :-1], True]
    result[pairs[0, last]] = pairs[1, last]
    return result


def _measure(
    labels: NDArray[np.int32],
    n_labels: int,
    dem: NDArray[np.float64],
    ground_group: NDArray[np.int8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> tuple[pd.DataFrame, NDArray[np.uint8]]:
    """Measure each region's height, angle and step test.

    Returns:
        A frame indexed 1 to ``n_labels`` with ``n_cells``, ``height_m``,
        ``height_max_m``, ``run_m``, ``n_transects``, ``overall_angle_deg``,
        ``ground_group_code``, ``height_band``, ``threshold_angle_deg`` and
        ``is_free_face``, and the edge role grid.
    """
    index = pd.RangeIndex(1, n_labels + 1, name="label")
    roles = _edge_roles(labels, layers)
    transects = _transects(labels, dem, roles, layers, cell_size_m)
    by_label = transects.groupby("label")
    height = by_label["height_m"].median().reindex(index)
    height_max = by_label["height_m"].max().reindex(index)
    run = by_label["run_m"].median().reindex(index)
    n_transects = by_label.size().reindex(index, fill_value=0)

    # A region no transect crossed (one with no crest cell, such as one
    # bounded only by the edge of the grid) is measured by its elevation range.
    inside = labels > OUTSIDE
    flat_labels = labels[inside]
    flat_z = dem[inside]
    z_max = pd.Series(flat_z).groupby(flat_labels).max().reindex(index)
    z_min = pd.Series(flat_z).groupby(flat_labels).min().reindex(index)
    height = height.fillna(z_max - z_min)
    height_max = height_max.fillna(z_max - z_min)

    angle = np.degrees(np.arctan2(height.to_numpy(), run.to_numpy()))
    counts = np.bincount(flat_labels, minlength=n_labels + 1)[1:]
    group = _majority(labels, ground_group, n_labels)[1:]
    group = np.where(group < 0, GROUND_GROUPS.index(OFF_MAP_GROUND_GROUP), group)
    band = height_band(height.to_numpy())
    threshold = step_angle_deg(group, band)
    with np.errstate(invalid="ignore"):
        free_face = (band > 0) & (angle > threshold)

    frame = pd.DataFrame(
        {
            "n_cells": counts,
            "height_m": height.to_numpy(),
            "height_max_m": height_max.to_numpy(),
            "run_m": run.to_numpy(),
            "n_transects": n_transects.to_numpy(),
            "overall_angle_deg": angle,
            "ground_group_code": group.astype(np.int8),
            "height_band": band,
            "threshold_angle_deg": threshold,
            "is_free_face": free_face,
        },
        index=index,
    )
    return frame, roles


def _cost(exceedance: NDArray[np.float64]) -> NDArray[np.uint16]:
    """Turn an exceedance in degrees into watershed costs, highest first."""
    capped = np.clip(
        np.nan_to_num(exceedance, nan=-_EXCEEDANCE_CAP_DEG),
        -_EXCEEDANCE_CAP_DEG,
        _EXCEEDANCE_CAP_DEG,
    )
    cost = np.rint((_EXCEEDANCE_CAP_DEG - capped) * _COST_SCALE)
    return np.clip(cost, 0, _BARRIER_COST - 1).astype(np.uint16)


def _grow(
    seeds: NDArray[np.int32],
    n_seeds: int,
    cost: NDArray[np.uint16],
    allowed: NDArray[np.bool_],
) -> NDArray[np.int32]:
    """Grow seeds by watershed over allowed cells only.

    The cells growth may not enter are themselves made markers of a barrier
    label, so no flood passes through them; seed cells always keep their
    seed.
    """
    barrier = n_seeds + 1
    markers = np.where(seeds > OUTSIDE, seeds, OUTSIDE).astype(np.int32)
    markers[(markers == OUTSIDE) & ~allowed] = barrier
    if not np.any(markers == OUTSIDE):
        grown = markers
    else:
        grown = ndimage.watershed_ift(cost, markers, structure=FOUR_CONNECTED)
    grown = np.where(grown == barrier, OUTSIDE, grown).astype(np.int32)
    return grown


def _keep_reachable(
    grown: NDArray[np.int32],
    seeds: NDArray[np.int32],
    keep: NDArray[np.bool_],
) -> NDArray[np.int32]:
    """Keep each label's cells that ``keep`` allows and its seed reaches."""
    result = np.zeros_like(grown)
    for position, window in enumerate(ndimage.find_objects(grown)):
        if window is None:
            continue
        label = position + 1
        own = (grown[window] == label) & (keep[window] | (seeds[window] == label))
        components, _ = ndimage.label(own, structure=FOUR_CONNECTED)
        seeded = np.unique(components[(seeds[window] == label) & own])
        seeded = seeded[seeded > 0]
        reached = np.isin(components, seeded)
        result[window][reached] = label
    return result


def _relabel(labels: NDArray[np.int32], keep: NDArray[np.bool_]) -> NDArray[np.int32]:
    """Drop the labels ``keep`` (indexed by label) rejects and renumber from 1."""
    lookup = np.zeros(keep.size, dtype=np.int32)
    kept = np.nonzero(keep)[0]
    kept = kept[kept > OUTSIDE]
    lookup[kept] = np.arange(1, kept.size + 1, dtype=np.int32)
    return lookup[labels]


def _free_face_pass(
    dem: NDArray[np.float64],
    ground_group: NDArray[np.int8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> tuple[NDArray[np.int32], NDArray[np.int32], NDArray[np.float64]]:
    """Seed and grow the free-faces.

    Returns:
        ``(labels, seeds, exceedance)``: the grown free-faces, the seed patches
        they grew from (same labels), and the exceedance grid.
    """
    band = height_band(np.nan_to_num(layers.step_height_m, nan=0.0))
    threshold = step_angle_deg(ground_group, band)
    exceedance = layers.slope_coarse_deg - threshold
    finite = np.isfinite(dem) & np.isfinite(layers.slope_fine_deg)
    with np.errstate(invalid="ignore"):
        eligible = finite & (
            (np.nan_to_num(layers.step_height_m, nan=0.0) >= MIN_WALL_HEIGHT_M)
            | (np.nan_to_num(exceedance, nan=-np.inf) > 0)
        )
    seeds, n_seeds = ndimage.label(eligible, structure=FOUR_CONNECTED)
    seeds = seeds.astype(np.int32)
    if n_seeds == 0:
        return seeds, seeds, exceedance

    seed_index = np.arange(1, n_seeds + 1)
    peaks = ndimage.maximum_position(
        np.nan_to_num(exceedance, nan=-np.inf), seeds, seed_index
    )
    peak_rows = np.array([peak[0] for peak in peaks], dtype=np.intp)
    peak_cols = np.array([peak[1] for peak in peaks], dtype=np.intp)
    limit = np.zeros(n_seeds + 1)
    limit[1:] = threshold[peak_rows, peak_cols] - BETA_FREE_FACE_GROW_TOL_DEG
    floor = float(limit[1:].min())
    slope = np.nan_to_num(layers.slope_fine_deg, nan=-np.inf)
    allowed = finite & (slope > floor + _ANGLE_SLACK_DEG)
    cost = _cost(exceedance)

    active = np.ones(n_seeds + 1, dtype=bool)
    active[0] = False
    grown = np.zeros_like(seeds)
    for _ in range(_MAX_FREE_FACE_ROUNDS):
        live_seeds = np.where(active[seeds], seeds, OUTSIDE).astype(np.int32)
        grown = _grow(live_seeds, n_seeds, cost, allowed)
        keep = slope > limit[grown] + _ANGLE_SLACK_DEG
        grown = _keep_reachable(grown, live_seeds, keep)
        measured, _ = _measure(grown, n_seeds, dem, ground_group, layers, cell_size_m)
        passes = np.zeros(n_seeds + 1, dtype=bool)
        passes[1:] = measured["is_free_face"].to_numpy() & (
            measured["height_m"].to_numpy() >= MIN_WALL_HEIGHT_M
        )
        still = active & passes
        if np.array_equal(still, active):
            break
        active = still
    grown = np.where(active[grown], grown, OUTSIDE).astype(np.int32)
    live_seeds = np.where(active[seeds], seeds, OUTSIDE).astype(np.int32)
    return grown, live_seeds, exceedance


def _bank_pass(
    claimed: NDArray[np.bool_], dem: NDArray[np.float64], layers: TerrainLayers
) -> tuple[NDArray[np.int32], NDArray[np.int32]]:
    """Seed and grow the banks on the ground the free-faces left.

    Returns:
        ``(labels, seeds)``, numbered from 1.
    """
    fine = np.nan_to_num(layers.slope_fine_deg, nan=-np.inf)
    coarse = np.nan_to_num(layers.slope_coarse_deg, nan=-np.inf)
    allowed = ~claimed & np.isfinite(dem) & (fine >= BETA_GROW_ANGLE_DEG)
    seeds, n_seeds = ndimage.label(
        allowed & (coarse >= BETA_GROW_ANGLE_DEG), structure=FOUR_CONNECTED
    )
    seeds = seeds.astype(np.int32)
    if n_seeds == 0:
        return seeds, seeds
    cost = _cost(layers.slope_coarse_deg - BETA_GROW_ANGLE_DEG)
    grown = _grow(seeds, n_seeds, cost, allowed)
    return grown, seeds


def _circular_mean_deg(
    labels: NDArray[np.int32], layers: TerrainLayers, n_labels: int
) -> NDArray[np.float64]:
    """The circular mean downhill bearing of each label, clockwise from north."""
    inside = (labels > OUTSIDE) & np.isfinite(layers.downhill_row)
    flat = labels[inside]
    east = np.bincount(
        flat, weights=layers.downhill_col[inside], minlength=n_labels + 1
    )
    north = np.bincount(
        flat, weights=-layers.downhill_row[inside], minlength=n_labels + 1
    )
    bearing = np.degrees(np.arctan2(east, north)) % 360.0
    bearing[np.hypot(east, north) == 0] = np.nan
    return bearing[1:]


def _length_along_contour(
    labels: NDArray[np.int32], aspect_deg: NDArray[np.float64], cell_size_m: float
) -> NDArray[np.float64]:
    """Each label's extent square to its aspect, in metres."""
    rows, cols = np.nonzero(labels > OUTSIDE)
    flat = labels[rows, cols]
    radians = np.radians(np.nan_to_num(aspect_deg, nan=0.0))
    # The contour runs square to the bearing: in array axes the bearing's unit
    # vector is (-cos, sin) along (rows, cols), so the contour is (sin, cos).
    along = rows * np.sin(radians)[flat - 1] + cols * np.cos(radians)[flat - 1]
    grouped = pd.Series(along).groupby(flat)
    extent = (grouped.max() - grouped.min()).reindex(range(1, aspect_deg.size + 1))
    return (extent.to_numpy() + 1.0) * cell_size_m


def _stack_links(
    labels: NDArray[np.int32],
    roles: NDArray[np.uint8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> pd.DataFrame:
    """Find, for each element, the elements whose toe meets its crest."""
    columns = [
        "lower",
        "upper",
        "bench_width_m",
        "bench_width_min_m",
        "n_transects",
        "share_of_crest",
    ]
    rows, cols = np.nonzero((roles & CREST) > 0)
    if rows.size == 0:
        return pd.DataFrame(columns=columns)
    own = labels[rows, cols]
    max_steps = math.ceil(BETA_STACK_SEARCH_M / cell_size_m / WALK_STEP_CELLS)
    # Walk uphill: everything outside the own element is passed over until
    # another element is met, so the walk is on a grid where the bench and the
    # own element are one label.
    walk_grid = np.where(labels == OUTSIDE, -1, labels)
    hits = np.full(own.shape, OUTSIDE, dtype=np.int32)
    distance = np.full(own.shape, np.nan)
    d_row = -layers.downhill_row[rows, cols]
    d_col = -layers.downhill_col[rows, cols]
    active = np.ones(own.shape, dtype=bool)
    for k in range(1, max_steps + 1):
        index = np.nonzero(active)[0]
        if index.size == 0:
            break
        r = np.rint(rows[index] + k * WALK_STEP_CELLS * d_row[index]).astype(np.intp)
        c = np.rint(cols[index] + k * WALK_STEP_CELLS * d_col[index]).astype(np.intp)
        inside = (r >= 0) & (r < labels.shape[0]) & (c >= 0) & (c < labels.shape[1])
        found = np.full(index.shape, -1, dtype=np.int64)
        found[inside] = walk_grid[r[inside], c[inside]]
        hit = inside & (found > OUTSIDE) & (found != own[index])
        hits[index[hit]] = found[hit]
        distance[index[hit]] = np.hypot(
            r[hit] - rows[index[hit]], c[hit] - cols[index[hit]]
        )
        active[index[hit | ~inside]] = False
    linked = hits > OUTSIDE
    if not linked.any():
        return pd.DataFrame(columns=columns)
    bench = np.maximum(distance[linked] - 1.0, 0.0) * cell_size_m
    frame = pd.DataFrame(
        {"lower": own[linked], "upper": hits[linked], "bench_width_m": bench}
    )
    grouped = frame.groupby(["lower", "upper"])["bench_width_m"]
    links = grouped.agg(["median", "min", "size"]).reset_index()
    links.columns = [
        "lower",
        "upper",
        "bench_width_m",
        "bench_width_min_m",
        "n_transects",
    ]
    crest_cells = np.bincount(own, minlength=int(labels.max()) + 1)
    links["share_of_crest"] = links["n_transects"] / crest_cells[links["lower"]]
    return links[columns]


def _block_mode(labels: NDArray[np.int32], factor: int) -> NDArray[np.int32]:
    """The most common element label in each block, OUTSIDE where it has none."""
    rows = labels.shape[0] // factor
    cols = labels.shape[1] // factor
    blocks = labels[: rows * factor, : cols * factor].reshape(
        rows, factor, cols, factor
    )
    blocks = blocks.transpose(0, 2, 1, 3).reshape(rows, cols, factor * factor)
    counts = (blocks[..., :, None] == blocks[..., None, :]).sum(axis=-1)
    counts = np.where(blocks > OUTSIDE, counts, 0)
    pick = np.argmax(counts, axis=-1)
    mode = np.take_along_axis(blocks, pick[..., None], axis=-1)[..., 0]
    return np.where(counts.max(axis=-1) > 0, mode, OUTSIDE).astype(np.int32)


def _block_mean(dem: NDArray[np.float64], factor: int) -> NDArray[np.float64]:
    """The mean of each block, NaN where any cell of it is nodata."""
    rows = dem.shape[0] // factor
    cols = dem.shape[1] // factor
    blocks = dem[: rows * factor, : cols * factor].reshape(rows, factor, cols, factor)
    return blocks.mean(axis=(1, 3))


def _d8_receivers(dem: NDArray[np.float64], cell_size_m: float) -> NDArray[np.intp]:
    """The flat index of each cell's steepest downhill neighbour, or itself.

    A cell with no lower neighbour (a pit, a flat or nodata) is its own
    receiver, so its paths end there; nothing is filled.
    """
    rows, cols = dem.shape
    flat_index = np.arange(rows * cols).reshape(rows, cols)
    best = np.zeros(dem.shape)
    receiver = flat_index.copy()
    padded = np.pad(dem, 1, constant_values=np.nan)
    padded_index = np.pad(flat_index, 1, constant_values=-1)
    for d_r in (-1, 0, 1):
        for d_c in (-1, 0, 1):
            if d_r == 0 and d_c == 0:
                continue
            neighbour = padded[1 + d_r : 1 + d_r + rows, 1 + d_c : 1 + d_c + cols]
            index = padded_index[1 + d_r : 1 + d_r + rows, 1 + d_c : 1 + d_c + cols]
            with np.errstate(invalid="ignore"):
                drop = (dem - neighbour) / (math.hypot(d_r, d_c) * cell_size_m)
            better = np.nan_to_num(drop, nan=-np.inf) > best
            best = np.where(better, drop, best)
            receiver = np.where(better, index, receiver)
    return receiver.ravel()


def _catchments(
    labels: NDArray[np.int32],
    dem: NDArray[np.float64],
    transform: Affine,
    cell_size_m: float,
) -> tuple[NDArray[np.int32], Affine, pd.DataFrame]:
    """Label each coarse cell with the first element its D8 flow reaches."""
    factor = max(round(COARSE_SLOPE_M / cell_size_m), 1)
    coarse_dem = _block_mean(dem, factor)
    coarse_labels = _block_mode(labels, factor)
    coarse_transform = transform * Affine.scale(factor)
    receiver = _d8_receivers(coarse_dem, cell_size_m * factor)

    flat_labels = coarse_labels.ravel()
    own = np.arange(flat_labels.size)
    pointer = np.where(flat_labels > OUTSIDE, own, receiver)
    # Pointer doubling: each cell takes its target's target until nothing
    # moves, about log2 of the longest flow path in passes.
    while True:
        doubled = pointer[pointer]
        if np.array_equal(doubled, pointer):
            break
        pointer = doubled
    catchment = flat_labels[pointer]

    on_element = flat_labels > OUTSIDE
    downstream = catchment[receiver]
    leaves = on_element & (downstream > OUTSIDE) & (downstream != flat_labels)
    pairs = pd.DataFrame({"upper": flat_labels[leaves], "lower": downstream[leaves]})
    drainage = pairs.groupby(["upper", "lower"]).size().rename("n_cells").reset_index()
    shape = coarse_labels.shape
    return catchment.reshape(shape).astype(np.int32), coarse_transform, drainage


def find_slope_elements(
    dem: ArrayLike,
    ground_group: ArrayLike,
    transform: Affine,
    *,
    categories: Mapping[str, ArrayLike] | None = None,
    core: ArrayLike | None = None,
) -> SlopeElements:
    """Find the slope elements on a DEM.

    Args:
        dem: Ground elevation in metres on a north-up grid of square cells,
            NaN for nodata and outside the LiDAR.
        ground_group: The ground group code of every cell, an index into
            :data:`GROUND_GROUPS`; see :func:`ground_group_codes` and
            :func:`rasterise_ground_map`.
        transform: The grid's affine transform, cell corner based.
        categories: Integer grids to take the majority of over each element,
            written as ``majority_<name>`` (for example a ground map row index
            for ``ground_id``, material and modification).
        core: Where given, a boolean grid; only the elements whose seed peak
            lies on it are kept, so tiles with an overlap margin each keep the
            elements seeded in their own core.

    Returns:
        The elements and their links.

    Raises:
        ValueError: If the grids do not share a shape, or the transform is not
            north-up with square cells.
    """
    elevation = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    if groups.shape != elevation.shape:
        msg = f"The ground group grid is {groups.shape}, the DEM {elevation.shape}."
        raise ValueError(msg)
    cell_size_m = _cell_size(transform)
    layers = terrain_layers(elevation, cell_size_m)

    free_faces, free_face_seeds, exceedance = _free_face_pass(
        elevation, groups, layers, cell_size_m
    )
    present = np.bincount(free_faces.ravel()) > 0
    free_faces = _relabel(free_faces, present)
    free_face_seeds = _relabel(free_face_seeds, present[: free_face_seeds.max() + 1])
    n_free_faces = int(free_faces.max())

    banks, bank_seeds = _bank_pass(free_faces > OUTSIDE, elevation, layers)
    offset = np.where(banks > OUTSIDE, banks + n_free_faces, OUTSIDE)
    labels = np.where(free_faces > OUTSIDE, free_faces, offset).astype(np.int32)
    seeds_offset = np.where(bank_seeds > OUTSIDE, bank_seeds + n_free_faces, OUTSIDE)
    seed_grid = np.where(free_faces > OUTSIDE, free_face_seeds, seeds_offset)
    seed_grid = np.where(labels > OUTSIDE, seed_grid, OUTSIDE).astype(np.int32)

    n_labels = int(labels.max())
    measured, _ = _measure(labels, n_labels, elevation, groups, layers, cell_size_m)
    keep = np.zeros(n_labels + 1, dtype=bool)
    keep[1:] = measured["height_m"].to_numpy() >= MIN_WALL_HEIGHT_M

    seed_exceedance = np.full(n_labels + 1, np.nan)
    seed_rows = np.full(n_labels + 1, -1, dtype=np.intp)
    seed_cols = np.full(n_labels + 1, -1, dtype=np.intp)
    if n_labels:
        index = np.arange(1, n_labels + 1)
        score = np.nan_to_num(exceedance, nan=-np.inf)
        seed_exceedance[1:] = ndimage.maximum(score, seed_grid, index)
        peaks = ndimage.maximum_position(score, seed_grid, index)
        for label, peak in zip(index, peaks, strict=True):
            if peak is not None and len(peak) == 2:
                seed_rows[label], seed_cols[label] = peak
    if core is not None and n_labels:
        core_grid = np.asarray(core, dtype=bool)
        valid = seed_rows >= 0
        in_core = np.zeros(n_labels + 1, dtype=bool)
        in_core[valid] = core_grid[seed_rows[valid], seed_cols[valid]]
        keep &= in_core

    kept = np.nonzero(keep)[0]
    labels = _relabel(labels, keep)
    n_labels = int(kept.size)
    grown_in = np.where(kept <= n_free_faces, FREE_FACE_PASS, BANK_PASS)

    measured, roles = _measure(labels, n_labels, elevation, groups, layers, cell_size_m)
    elements = measured.drop(columns=["ground_group_code", "is_free_face"])
    elements.insert(0, "grown_in", grown_in)
    elements.insert(
        1, "element_type", np.where(measured["is_free_face"], FREE_FACE, BANK)
    )
    elements.insert(3, "area_m2", elements["n_cells"] * cell_size_m**2)

    inside = labels > OUTSIDE
    flat = labels[inside]
    slope = layers.slope_fine_deg[inside]
    by_label = pd.Series(slope).groupby(flat)
    index = elements.index
    elements["slope_mean_deg"] = by_label.mean().reindex(index).to_numpy()
    elements["slope_max_deg"] = by_label.max().reindex(index).to_numpy()
    aspect = _circular_mean_deg(labels, layers, n_labels)
    elements["length_m"] = _length_along_contour(labels, aspect, cell_size_m)
    elements["aspect_deg"] = aspect
    step = pd.Series(np.nan_to_num(layers.step_height_m[inside], nan=0.0))
    elements["step_peak_m"] = step.groupby(flat).max().reindex(index).to_numpy()
    elements["seed_exceedance_deg"] = seed_exceedance[kept]
    elements["seed_row"] = seed_rows[kept]
    elements["seed_col"] = seed_cols[kept]
    elements["ground_group"] = np.asarray(GROUND_GROUPS)[
        measured["ground_group_code"].to_numpy()
    ]
    elements["angle_excess_deg"] = (
        elements["overall_angle_deg"] - elements["threshold_angle_deg"]
    )
    elements["mm6_cut"] = (elements["overall_angle_deg"] > MM6_CUT_ANGLE_DEG) & (
        elements["height_m"] > MM6_CUT_HEIGHT_M
    )
    elements["hb1995_cut"] = (elements["overall_angle_deg"] > HB1995_CUT_ANGLE_DEG) & (
        elements["height_m"] > HB1995_CUT_HEIGHT_M
    )

    catchments, catchment_transform, drainage = _catchments(
        labels, elevation, transform, cell_size_m
    )
    own_catchment = np.bincount(catchments.ravel(), minlength=n_labels + 1)[1:]
    elements["own_catchment_area_m2"] = own_catchment * (
        catchment_transform.a * -catchment_transform.e
    )

    rows, cols = np.nonzero(inside)
    x, y = transform * (cols + 0.5, rows + 0.5)
    elements["centroid_x"] = pd.Series(x).groupby(flat).mean().reindex(index).to_numpy()
    elements["centroid_y"] = pd.Series(y).groupby(flat).mean().reindex(index).to_numpy()
    for name, grid in (categories or {}).items():
        values = np.asarray(grid)
        if values.shape != elevation.shape:
            msg = f"The {name} grid is {values.shape}, the DEM {elevation.shape}."
            raise ValueError(msg)
        elements[f"majority_{name}"] = _majority(labels, values, n_labels)[1:]

    return SlopeElements(
        labels=labels,
        edge_roles=roles,
        elements=elements,
        stack_links=_stack_links(labels, roles, layers, cell_size_m),
        catchments=catchments,
        catchment_transform=catchment_transform,
        drainage_links=drainage,
        layers=layers,
    )


def rasterise_ground_map(
    ground_map: gpd.GeoDataFrame, transform: Affine, shape: tuple[int, int]
) -> tuple[NDArray[np.int8], NDArray[np.int32]]:
    """Burn the ground map onto a grid as ground groups and row positions.

    Args:
        ground_map: The ground map, with a ``material`` column, on the grid's
            coordinate reference system.
        transform: The grid's affine transform.
        shape: The grid's ``(rows, columns)``.

    Returns:
        ``(ground_group, row)``: the ground group code of every cell, off-map
        cells taking :data:`OFF_MAP_GROUND_GROUP`, and the position in
        ``ground_map`` of the piece each cell centre falls in, -1 off the map.
        The position reads ``material``, ``modification`` and ``ground_id``
        back for an element's majority.
    """
    position = np.full(shape, -1, dtype=np.int32)
    if len(ground_map):
        burned = features.rasterize(
            zip(ground_map.geometry, range(len(ground_map)), strict=True),
            out_shape=shape,
            transform=transform,
            fill=-1,
            dtype="int32",
        )
        position = burned.astype(np.int32)
    codes = (
        ground_group_codes(ground_map["material"].to_numpy())
        if len(ground_map)
        else np.array([], dtype=np.int8)
    )
    group = np.full(shape, GROUND_GROUPS.index(OFF_MAP_GROUND_GROUP), dtype=np.int8)
    on_map = position >= 0
    group[on_map] = codes[position[on_map]]
    return group, position
