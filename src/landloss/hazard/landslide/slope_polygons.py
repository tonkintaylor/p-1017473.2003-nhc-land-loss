"""Failure polygons from the slope elements: phase 3 of the plan.

A failure on a slope element is the element, the ground behind its crest that
goes with it, and the ground below its toe that the debris covers. The first
two are the **polygon** (the evacuated ground); the **imminent** band behind it
and the **inundated** ground below it are zones attached to the polygon. This
is phase 3 of ``.agents/plans/building-face-based-urban-slope-polygons.md``,
built on the elements of :mod:`landloss.hazard.landslide.slope_elements`, and
the terms are that plan's.

Everything is read off the elements' label grid along fall-line rays, one ray
from every crest cell, all rays marched together as whole arrays; Python loops
run only over elements and polygons. The rules, each where the plan sets it:

1. **The width behind the crest by rule** (the lead, 2026-10-02), measured
   horizontally back from the crest cell's centre over whatever ground lies
   behind it, with no pseudo-static calculation
   (:func:`width_behind_crest_m`):

   - a free-face (taken as a wall, cut or fill): the active wedge
     ``H x tan(45 - phi'/2)`` [nzgs_mbie_2017] on the retained ground's
     friction angle, 0.45 H on the fill's 42 degrees [monteith_2020];
   - a fill bank: :data:`BETA_FILL_BANK_WIDTH_H` of its height;
   - a cut or natural bank: the T-44 headscarp band, half a metre or a metre
     on ground over 30 degrees (:mod:`landloss.hazard.landslide.urban.geometry`).

2. **Stacks.** A free-face carrying the MM6 flag (steeper than 50 degrees and
   higher than 3 m [brabhaharan_2018; hancox_2015]) takes the whole stack
   above it: its rays climb into every element above that faces the same way
   and starts within the width behind the crest of the element below it, and
   stop at the first bench wider than that width, or at a ridge. Ground past
   the top element's crest is that element's own width. Every other element
   takes only its own width, even where that reaches into the element above
   [kingsbury_1995].
3. **Retrogression.** Past the end of its polygon, each ray looks on uphill,
   up to :data:`~landloss.hazard.landslide.slope_elements.BETA_STACK_SEARCH_M`
   past the last element it was in, for the first element above that it did
   not take; that element is linked to the polygon, below to above, and step 9
   raises its failure probability when the polygon fails, by
   :func:`conditional_failure_probability` with
   :data:`BETA_RETROGRESSION_P` [de_vilder_2024; hancox_perrin_2010].
4. **Segments.** An element is cut along its contour wherever the evacuated
   volume of the run so far reaches :data:`BETA_SEGMENT_VOLUME_M3`, with no
   segment shorter than the element's height; each segment is one polygon
   [hancox_2013_slope_types; hancox_brabhaharan_1995].
5. **Overlap.** Ground two polygons both reach is kept by both where one
   polygon is a stack that took the other's element; where their upslope
   catchments are disjoint and the two elements face apart by more than
   :data:`BETA_FACING_APART_DEG` (two gully heads meeting at a ridge; the
   plan's rule asks only for disjoint catchments, and the facing test is
   ours); and where one polygon's width behind its crest reaches into the
   other's element (the plan's stack rule 3: an element takes its own width
   "even where that reaches into the element above", which is linked to it by
   retrogression, not swallowed). Otherwise it goes to the polygon whose crest
   is nearer, so the polygons tile. The plan's overlap rule 2 (nearest crest)
   and stack rule 3 disagree for an element directly above another; rule 3
   is followed here, and the choice is the lead's (stage D1 findings).
6. **Imminent ground** runs from the back of the polygon to where a line from
   the toe at :data:`BETA_REPOSE_ANGLE_DEG` meets the ground behind the crest
   [de_vilder_2024], never narrower than the T-45 band (the headscarp band's
   width again, behind the polygon).
7. **Inundated ground**, below the toe, ends where a line from the polygon's
   crest dipping at the reach angle meets the ground, traced down the crest
   cell's fall line [hunter_fell_2003; de_vilder_2022]: the dry debris
   avalanche relation for cuts and natural ground, the fill flow slide
   relation for fill (:func:`reach_ratio`), on the segment's evacuated volume.
   A stack's polygon also takes the reach from its free-face's own crest, so
   taking the slope above never shortens the runout below the toe (stage
   D1). An optional barrier grid (buildings, roads) stops it at the first
   barrier cell.

Depths, for the volume: a free-face's own ground (its face and the width
behind its crest) is cut by a straight slip plane from its toe to the back of
the width, so its cross section is the triangle toe, crest, back
(:func:`planar_depth_m`), ``0.5 H w`` per metre behind a vertical wall
[nzgs_mbie_2017]; a fill bank takes the fill thickness where it is known,
otherwise the volume-area relation (A-06) [massey_2020]; a cut or natural bank
the cover depth the old urban chain used [kingsbury_1995]. A cell takes the
depth of the element whose ground it is: the element it lies on, or the one
whose crest it is behind. :func:`element_depth_m` gives each element's mean.

On a tile, the elements in the halo (``in_core`` False, see
:func:`landloss.hazard.landslide.slope_elements.find_slope_elements`) take
part in everything, the stacks, the shared ground and the links, and only
their polygons are dropped at the end, with the links and overlaps that start
from them.

What the grid does to the widths: a crest is a cell centre, and a vertical
wall's crest cell sits half a metre behind the wall, so a band of under a cell
adds no cell behind it; a wall's wedge on a 1 m grid is mostly its crest cell.
Each polygon carries the width as the rule gives it and the width it kept
(``width_realised_m``).

What is not here yet: the wall state. Phase 2 decides which free-faces carry a
wall; until then every free-face takes the wall's wedge. The amplification
and the Kingsbury rating per element are separate items of phase 3.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import ArrayLike, NDArray
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import shape as to_shape

from landloss.hazard.landslide.geometry import ALPHA, GAMMA, mean_depth_m
from landloss.hazard.landslide.slope_elements import (
    BETA_RIDGE_DROP_M,
    BETA_STACK_SEARCH_M,
    CREST,
    FREE_FACE,
    OUTSIDE,
    WALK_STEP_CELLS,
    SlopeElements,
)
from landloss.hazard.landslide.urban.geometry import (
    BETA_HEADSCARP_BAND_M,
    BETA_HEADSCARP_BAND_STEEP_M,
    COLLUVIUM_DEPTH_M,
    HEADSCARP_STEEP_SLOPE_DEG,
)

# The friction angle of Wellington fill, in degrees: the S52 set GNS supplied
# for modelling the Priscilla and Orchy Crescent fills [monteith_2020]
# (sr2019-051-F14), which the lead accepted for the ground map on 2026-10-02.
# Its active wedge is 0.45 of the retained height.
FILL_PHI_DEG = 42.0

# Judgement, a stand-in until the ground map carries a friction angle per
# material: the friction angle a free-face's wedge takes where none is passed
# in, the fill's. The plan reads a cut wall's from the cover; colluvium at 24
# to 28 degrees [lyndsell_2019; monteith_2020] would give about 0.6 H, not
# 0.45 H.
BETA_DEFAULT_RETAINED_PHI_DEG = FILL_PHI_DEG

# Judgement, a proposal for the lead: the width behind the crest of a fill bank
# with no wall, as a share of its height. The same wedge as a wall on the
# fill's 42 degrees; the low case 0.25 H is our reading of the Priscilla
# section at SRF 1 and the high case 0.65 H the buried colluvium's 23.7 degrees
# as a Coulomb wedge [monteith_2020; brown_larkin_2005; lyndsell_2019].
BETA_FILL_BANK_WIDTH_H = 0.45

# Judgement, a proposal for the lead: the angle of repose the imminent band
# runs to, from the toe, for every material. Checked against the Cook Strait
# cliff GNS judged near its natural angle of repose, 30 to 35 degrees, under
# shaking (sr2013-042-F19); the screening by a repose angle from the slope
# base is [de_vilder_2024] (devilder2024-F08).
BETA_REPOSE_ANGLE_DEG = 35.0

# Judgement, a proposal for the lead: an element is cut along its contour
# wherever the evacuated volume of the run so far reaches this, in cubic
# metres. The top of the SH58 forecast of 10 to 1,000 m3 failures
# [hancox_brabhaharan_1995] (sr1995-005-F08) and the middle of the 10^2 to
# 10^4 m3 Wellington cut failures [hancox_2013_slope_types] (sr2013-058-F12).
BETA_SEGMENT_VOLUME_M3 = 1000.0

# Judgement, a proposal for the lead: the chance that an element fails when
# the polygon below it, linked by retrogression, fails, added to its own as
# ``1 - (1 - p_above) x (1 - BETA_RETROGRESSION_P)`` in step 9. The literature
# gives the direction and no size [de_vilder_2024; hancox_perrin_2010;
# anderson_2015; kingsbury_1995]; an even chance is a placeholder.
BETA_RETROGRESSION_P = 0.5

# Reach angle against volume, log10(H/L) = slope x log10(V) + intercept, from
# the crest of the source to the toe of the deposit [de_vilder_2022]: dry
# debris avalanches under 100,000 m3 (Figure 2.3, sr2019-038-F03, R2 0.113,
# N 144) and fill flow slides (Figure 2.6, sr2019-038-F20, R2 0.299). Both
# read against the figure images on 2026-10-02; the medians, the 50%
# exceedance lines (sr2019-038-F02).
DRY_REACH_LOG_SLOPE = -0.033
DRY_REACH_LOG_INTERCEPT = 0.0315
FILL_REACH_LOG_SLOPE = -0.090
FILL_REACH_LOG_INTERCEPT = -0.148

# The two failure styles, which pick the reach angle relation.
DRY_DEBRIS_AVALANCHE = "dry_debris_avalanche"
FILL_FLOW_SLIDE = "fill_flow_slide"

# The three width rules behind the crest.
WALL_WEDGE = "wall_wedge"
FILL_BANK_WEDGE = "fill_bank_wedge"
HEADSCARP_BAND = "headscarp_band"

# The three zones of a polygon, as written to the cell table.
EVACUATED = "evacuated"
IMMINENT = "imminent"
INUNDATED = "inundated"
ZONES = (EVACUATED, IMMINENT, INUNDATED)

# Why two polygons keep the same evacuated ground.
STACK_OVERLAP = "stack"
SEPARATE_CATCHMENTS = "separate_catchments"
WITHIN_WIDTH = "within_width"

# The volume the reach angle relations are read at is never under this, in
# cubic metres, so a sliver of a polygon does not take a logarithm of zero.
_MIN_VOLUME_M3 = 1.0

# Judgement: elements whose aspects differ by more than this, in degrees, face
# apart, so the ground between them is a divide, not one slope. The plan's
# overlap rule 1 asks only for disjoint catchments; this adds that the two
# face apart, because on a 3 m D8 grid two elements side by side on one slope
# often drain to different cells below and read as disjoint.
BETA_FACING_APART_DEG = 90.0

# Distances are compared with this much slack in metres, so a band whose width
# is a whole number of cells keeps its last cell whatever the rounding.
_DISTANCE_SLACK_M = 1e-6


@dataclass(frozen=True)
class SlopePolygons:
    """The failure polygons built on one grid of slope elements.

    Attributes:
        polygons: One row per polygon, indexed from 1 by ``polygon``: the
            element it is a segment of (``element``, ``segment``), the
            element's ``element_type`` and ``ground_group``, ``is_fill``,
            ``style``, ``width_rule``, ``width_behind_crest_m`` (the rule's),
            ``width_realised_m`` (the median over its rays of how far behind
            the crest cell's centre the furthest cell it kept lies),
            ``is_stack`` (an MM6 free-face whose rays climb),
            ``top_element`` and ``n_stack_elements`` (the elements above it
            the polygon took), ``base_height_m`` (the element's height),
            ``height_m`` (the polygon's, toe of the element to the crest of
            the highest element in it, median over its rays), ``length_m``
            (along the contour), ``area_m2``, ``depth_m``, ``volume_m3``,
            ``reach_hl`` (H/L of the runout), ``imminent_area_m2``,
            ``inundated_area_m2``, ``n_rays``, ``centroid_x``,
            ``centroid_y``.
        cells: The cells of every zone of every polygon, one row each:
            ``polygon``, ``zone`` (one of :data:`ZONES`), ``row``, ``col``
            and, for an evacuated cell, ``depth_m``, its evacuated depth.
            A cell can be in more than one polygon's zone (see
            :attr:`overlaps`; imminent and inundated zones overlap freely).
        element_links: The elements' stack links with the lower element's
            ``lower_width_m`` behind its crest and ``makes_stack``, a bench
            narrower than that width (the plan's stack rule 1).
        retrogression_links: One row per pair where a polygon's rays met an
            element above that the polygon did not take: ``lower_polygon``,
            ``lower_element``, ``upper_element``, ``upper_polygon`` (the
            segment met), ``bench_width_m`` (median over the rays) and
            ``n_rays``.
        overlaps: Pairs of polygons that keep the same evacuated ground:
            ``polygon_a``, ``polygon_b``, ``n_cells`` and ``reason``
            (:data:`STACK_OVERLAP`, :data:`SEPARATE_CATCHMENTS` or
            :data:`WITHIN_WIDTH`).
        shape: The grid's ``(rows, columns)``.
        transform: The grid's affine transform.
    """

    polygons: pd.DataFrame
    cells: pd.DataFrame
    element_links: pd.DataFrame
    retrogression_links: pd.DataFrame
    overlaps: pd.DataFrame
    shape: tuple[int, int]
    transform: Affine


def headscarp_band_width_m(angle_deg: ArrayLike) -> NDArray[np.float64]:
    """The T-44 headscarp band for elements at these angles, in metres.

    Args:
        angle_deg: The elements' overall angles.

    Returns:
        :data:`~landloss.hazard.landslide.urban.geometry.BETA_HEADSCARP_BAND_STEEP_M`
        at or over
        :data:`~landloss.hazard.landslide.urban.geometry.HEADSCARP_STEEP_SLOPE_DEG`,
        otherwise
        :data:`~landloss.hazard.landslide.urban.geometry.BETA_HEADSCARP_BAND_M`,
        as :func:`landloss.hazard.landslide.urban.geometry.headscarp_band_m`
        gives it. The T-45 imminent band is the same width again.
    """
    angles = np.asarray(angle_deg, dtype=float)
    return np.where(
        angles >= HEADSCARP_STEEP_SLOPE_DEG,
        BETA_HEADSCARP_BAND_STEEP_M,
        BETA_HEADSCARP_BAND_M,
    )


def width_behind_crest_m(
    element_type: ArrayLike,
    height_m: ArrayLike,
    angle_deg: ArrayLike,
    *,
    is_fill: ArrayLike,
    phi_deg: ArrayLike,
) -> tuple[NDArray[np.float64], NDArray[np.str_]]:
    """The evacuated width behind each element's crest, by element type.

    Args:
        element_type: ``"free_face"`` or ``"bank"`` per element.
        height_m: The elements' heights.
        angle_deg: Their overall angles, for the headscarp band.
        is_fill: Whether each element is on fill.
        phi_deg: The retained ground's friction angle per element, for a
            free-face's wedge.

    Returns:
        ``(width_m, rule)``: the horizontal width behind the crest and the
        rule that set it (:data:`WALL_WEDGE`, :data:`FILL_BANK_WEDGE` or
        :data:`HEADSCARP_BAND`).
    """
    types = np.asarray(element_type)
    heights = np.asarray(height_m, dtype=float)
    fill = np.asarray(is_fill, dtype=bool)
    phi = np.asarray(phi_deg, dtype=float)
    free_face = types == FREE_FACE
    wedge = heights * np.tan(np.radians(45.0 - phi / 2.0))
    band = headscarp_band_width_m(angle_deg)
    width = np.where(
        free_face, wedge, np.where(fill, BETA_FILL_BANK_WIDTH_H * heights, band)
    )
    rule = np.where(
        free_face, WALL_WEDGE, np.where(fill, FILL_BANK_WEDGE, HEADSCARP_BAND)
    )
    return width.astype(float), rule


def element_depth_m(
    element_type: ArrayLike,
    height_m: ArrayLike,
    *,
    is_fill: ArrayLike,
    fill_thickness_m: ArrayLike,
    width_m: ArrayLike,
    run_m: ArrayLike,
) -> NDArray[np.float64]:
    """The mean evacuated depth of each element's ground, NaN where it is by area.

    Args:
        element_type: ``"free_face"`` or ``"bank"`` per element.
        height_m: The elements' heights.
        is_fill: Whether each element is on fill.
        fill_thickness_m: The fill thickness per element, NaN where unknown.
        width_m: The width behind each element's crest.
        run_m: Each element's horizontal run, crest to toe.

    Returns:
        For a free-face, the mean depth over its plan (its run and the width
        behind its crest) of the wedge between the ground and a straight
        plane from its toe to the back of the width, ``0.5 H w / (run + w)``:
        half the height behind a vertical wall [nzgs_mbie_2017], less on a
        face that leans back, whose plan the wedge's area is spread over
        (:func:`planar_depth_m` gives it cell by cell). For a fill bank, the
        fill thickness, or NaN where it is unknown, meaning the volume-area
        relation (A-06) [massey_2020]; for a cut or natural bank the cover
        depth :data:`~landloss.hazard.landslide.urban.geometry.COLLUVIUM_DEPTH_M`
        [kingsbury_1995].
    """
    types = np.asarray(element_type)
    heights = np.asarray(height_m, dtype=float)
    fill = np.asarray(is_fill, dtype=bool)
    thickness = np.asarray(fill_thickness_m, dtype=float)
    width = np.asarray(width_m, dtype=float)
    run = np.nan_to_num(np.asarray(run_m, dtype=float))
    plan = width + run
    with np.errstate(invalid="ignore", divide="ignore"):
        wedge = np.where(plan > 0, 0.5 * heights * width / plan, heights / 2.0)
    return np.where(
        types == FREE_FACE,
        wedge,
        np.where(fill, thickness, COLLUVIUM_DEPTH_M),
    ).astype(float)


def planar_depth_m(
    ground_z: ArrayLike,
    behind_crest_m: ArrayLike,
    *,
    toe_z: ArrayLike,
    run_m: ArrayLike,
    back_z: ArrayLike,
    width_m: ArrayLike,
) -> NDArray[np.float64]:
    """The depth of a free-face's evacuated ground to its slip plane, per cell.

    The slip plane is straight, from the toe (``run_m`` in front of the crest,
    at ``toe_z``) to the back of the width behind the crest (``width_m``
    behind it, at the ground there, ``back_z``), so the evacuated cross
    section is the triangle toe, crest, back: ``0.5 H w`` per metre of crest
    on level ground behind a vertical wall [nzgs_mbie_2017].

    Args:
        ground_z: The ground elevation of each cell.
        behind_crest_m: Each cell's horizontal distance behind the crest along
            the fall line, negative in front of it (on the face).
        toe_z: The toe's elevation.
        run_m: The toe's distance in front of the crest.
        back_z: The ground elevation at the back of the width.
        width_m: The width behind the crest.

    Returns:
        The ground's height over the plane, zero where it is on or under it.
    """
    z = np.asarray(ground_z, dtype=float)
    position = np.asarray(behind_crest_m, dtype=float)
    toe = np.asarray(toe_z, dtype=float)
    run = np.asarray(run_m, dtype=float)
    back = np.asarray(back_z, dtype=float)
    width = np.asarray(width_m, dtype=float)
    span = width + run
    with np.errstate(invalid="ignore", divide="ignore"):
        rise = np.where(span > 0, (back - toe) / span, 0.0)
    plane = toe + (position + run) * rise
    return np.maximum(z - plane, 0.0)


def reach_ratio(volume_m3: ArrayLike, style: ArrayLike) -> NDArray[np.float64]:
    """H/L of a failure's runout, from its volume and style [de_vilder_2022].

    Args:
        volume_m3: The evacuated volume; read at no less than 1 m3.
        style: :data:`DRY_DEBRIS_AVALANCHE` or :data:`FILL_FLOW_SLIDE`.

    Returns:
        The median H/L: 0.86 for a dry failure of 1,000 m3 and 0.38 for a
        fill flow slide.
    """
    log_volume = np.log10(np.maximum(np.asarray(volume_m3, dtype=float), 1.0))
    fill = np.asarray(style) == FILL_FLOW_SLIDE
    slope = np.where(fill, FILL_REACH_LOG_SLOPE, DRY_REACH_LOG_SLOPE)
    intercept = np.where(fill, FILL_REACH_LOG_INTERCEPT, DRY_REACH_LOG_INTERCEPT)
    return np.power(10.0, slope * log_volume + intercept)


def conditional_failure_probability(
    p_above: ArrayLike, *, retrogression_p: float = BETA_RETROGRESSION_P
) -> NDArray[np.float64]:
    """An element's failure probability once the polygon below it has failed.

    Args:
        p_above: The element's own failure probability.
        retrogression_p: The chance added by the failure below.

    Returns:
        ``1 - (1 - p_above) x (1 - retrogression_p)``.
    """
    p = np.asarray(p_above, dtype=float)
    return 1.0 - (1.0 - p) * (1.0 - retrogression_p)


def _area_depth_m(area_m2: ArrayLike) -> NDArray[np.float64]:
    """The volume-area relation's mean depth over an area [massey_2020]."""
    areas = np.asarray(area_m2, dtype=float)
    return np.asarray(mean_depth_m(ALPHA * areas**GAMMA, areas), dtype=float)


def _per_element(
    values: pd.Series | None, index: pd.Index, *, default: float
) -> NDArray[np.float64]:
    """A per-element input as an array in element order, defaults filled."""
    if values is None:
        return np.full(len(index), default, dtype=float)
    series = pd.Series(values).reindex(index)
    return series.astype(float).fillna(float(default)).to_numpy()


def _march_within(
    labels: NDArray[np.int32],
    rows: NDArray[np.intp],
    cols: NDArray[np.intp],
    d_row: NDArray[np.float64],
    d_col: NDArray[np.float64],
) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    """March from cells along a direction until each leaves its own label.

    Returns:
        The last cell of each march still on its own label.
    """
    own = labels[rows, cols]
    last_rows = rows.copy()
    last_cols = cols.copy()
    active = np.ones(own.shape, dtype=bool)
    max_steps = int(2 * (labels.shape[0] + labels.shape[1]) / WALK_STEP_CELLS)
    for k in range(1, max_steps + 1):
        index = np.nonzero(active)[0]
        if index.size == 0:
            break
        r = np.rint(rows[index] + k * WALK_STEP_CELLS * d_row[index]).astype(np.intp)
        c = np.rint(cols[index] + k * WALK_STEP_CELLS * d_col[index]).astype(np.intp)
        inside = (r >= 0) & (r < labels.shape[0]) & (c >= 0) & (c < labels.shape[1])
        same = np.zeros(index.shape, dtype=bool)
        same[inside] = labels[r[inside], c[inside]] == own[index[inside]]
        last_rows[index[same]] = r[same]
        last_cols[index[same]] = c[same]
        active[index[~same]] = False
    return last_rows, last_cols


@dataclass
class _Rays:
    """One fall-line ray from every crest cell, uphill unit vectors."""

    row: NDArray[np.intp]
    col: NDArray[np.intp]
    up_row: NDArray[np.float64]
    up_col: NDArray[np.float64]
    base: NDArray[np.int32]
    toe_z: NDArray[np.float64]
    run_m: NDArray[np.float64]


@dataclass
class _UphillResult:
    """What the uphill march found, per ray and per marked cell."""

    evacuated: pd.DataFrame  # ray, cell, dist, owner
    imminent: pd.DataFrame  # ray, cell
    absorbed: pd.DataFrame  # ray, element
    probe: pd.DataFrame  # ray, element, cell, bench_width_m
    top_z: NDArray[np.float64]
    top_d: NDArray[np.float64]


def _crest_rays(
    found: SlopeElements, dem: NDArray[np.float64], cell_size_m: float
) -> _Rays:
    """Set out a ray from every crest cell, with its own toe below it."""
    labels = found.labels
    rows, cols = np.nonzero((found.edge_roles & CREST) > 0)
    base = labels[rows, cols]
    down_row = found.layers.downhill_row[rows, cols]
    down_col = found.layers.downhill_col[rows, cols]
    # A crest cell always has a fall line (slope_elements marks the crest off
    # it), but an element's aspect stands in should one be missing.
    aspect = np.radians(
        np.nan_to_num(found.elements["aspect_deg"].to_numpy(), nan=90.0)
    )
    missing = ~(np.isfinite(down_row) & np.isfinite(down_col))
    down_row = np.where(missing, -np.cos(aspect)[base - 1], down_row)
    down_col = np.where(missing, np.sin(aspect)[base - 1], down_col)

    toe_rows, toe_cols = _march_within(labels, rows, cols, down_row, down_col)
    run = ((toe_rows - rows) * down_row + (toe_cols - cols) * down_col) * cell_size_m
    toe_z = dem[toe_rows, toe_cols]
    # A ray across a crest cell that is also the toe falls back on the
    # element's own transect medians, its toe no nearer than half a cell in
    # front of the crest cell's centre, where a face the DEM reads as
    # vertical stands.
    height = found.elements["height_m"].to_numpy()[base - 1]
    element_run = found.elements["run_m"].to_numpy()[base - 1]
    flat = run <= 0
    toe_z = np.where(flat, dem[rows, cols] - height, toe_z)
    run = np.where(
        flat, np.maximum(np.nan_to_num(element_run, nan=0.0), 0.5 * cell_size_m), run
    )
    return _Rays(
        row=rows.astype(np.intp),
        col=cols.astype(np.intp),
        up_row=-down_row,
        up_col=-down_col,
        base=base.astype(np.int32),
        toe_z=toe_z,
        run_m=run,
    )


def _march_uphill(
    found: SlopeElements,
    dem: NDArray[np.float64],
    rays: _Rays,
    *,
    width_m: NDArray[np.float64],
    t45_m: NDArray[np.float64],
    climbs: NDArray[np.bool_],
    cell_size_m: float,
) -> _UphillResult:
    """March every ray uphill: the evacuated band, the imminent band, the probe.

    ``width_m``, ``t45_m`` and ``climbs`` are indexed by element label (0
    unused). A ray is in three phases at once, each ending on its own:

    - evacuated: it marks cells while within the current element's width
      behind the crest it last left; a climbing ray (an MM6 free-face's)
      takes every element facing the same way that it enters while still
      evacuating, and that element's width then holds;
    - imminent: from the end of the evacuated band, it marks cells within the
      T-45 band or above the repose line from its own toe;
    - probe: the first element facing the same way that it meets and did not
      take, within the stack search distance past the last element it was in.

    Every phase ends at a ridge (the ground falling more than
    :data:`~landloss.hazard.landslide.slope_elements.BETA_RIDGE_DROP_M` below
    the highest point the ray has passed), at nodata and at the edge of the
    grid.
    """
    labels = found.labels
    down_row_grid = found.layers.downhill_row
    down_col_grid = found.layers.downhill_col
    n_rays = rays.row.size
    shape = labels.shape
    z0 = dem[rays.row, rays.col]
    tan_repose = math.tan(math.radians(BETA_REPOSE_ANGLE_DEG))
    inside_elements = (labels > OUTSIDE) & np.isfinite(dem)
    n_labels = int(labels.max()) + 1
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_z = np.bincount(
            labels[inside_elements], weights=dem[inside_elements], minlength=n_labels
        ) / np.bincount(labels[inside_elements], minlength=n_labels)

    exit_d = np.zeros(n_rays)
    current = rays.base.copy()
    top_z = z0.copy()
    top_d = np.zeros(n_rays)
    highest = z0.copy()
    evac = np.ones(n_rays, dtype=bool)
    imminent = np.ones(n_rays, dtype=bool)
    probe = np.ones(n_rays, dtype=bool)
    evac_end = np.full(n_rays, np.nan)

    evac_parts: list[pd.DataFrame] = []
    imminent_parts: list[pd.DataFrame] = []
    absorbed_parts: list[pd.DataFrame] = []
    probe_parts: list[pd.DataFrame] = []

    max_steps = int(2 * (shape[0] + shape[1]) / WALK_STEP_CELLS)
    for k in range(1, max_steps + 1):
        index = np.nonzero(evac | imminent | probe)[0]
        if index.size == 0:
            break
        step = k * WALK_STEP_CELLS
        r = np.rint(rays.row[index] + step * rays.up_row[index]).astype(np.intp)
        c = np.rint(rays.col[index] + step * rays.up_col[index]).astype(np.intp)
        inside = (r >= 0) & (r < shape[0]) & (c >= 0) & (c < shape[1])
        r_in = np.where(inside, r, 0)
        c_in = np.where(inside, c, 0)
        # The horizontal distance of the cell's centre behind the crest cell's,
        # along the ray.
        dist = (
            (r - rays.row[index]) * rays.up_row[index]
            + (c - rays.col[index]) * rays.up_col[index]
        ) * cell_size_m
        lab = np.where(inside, labels[r_in, c_in], OUTSIDE)
        z = np.where(inside, dem[r_in, c_in], np.nan)
        highest[index] = np.fmax(highest[index], z)
        with np.errstate(invalid="ignore"):
            ridge = z < highest[index] - BETA_RIDGE_DROP_M
        stop = ~inside | ~np.isfinite(z) | ridge
        # An element above faces the same way down the fall line and stands
        # higher, on the mean, than the element the ray set out from.
        with np.errstate(invalid="ignore"):
            facing = (
                (lab > OUTSIDE)
                & (
                    down_row_grid[r_in, c_in] * -rays.up_row[index]
                    + down_col_grid[r_in, c_in] * -rays.up_col[index]
                    > 0
                )
                & (mean_z[lab] > mean_z[rays.base[index]])
            )
        own = lab == rays.base[index]
        cell = r_in * shape[1] + c_in

        # The evacuated band.
        e = evac[index] & ~stop
        absorb = e & climbs[rays.base[index]] & facing & ~own
        in_own = e & own & (current[index] == rays.base[index])
        exit_d[index[in_own]] = dist[in_own]
        took = index[absorb]
        exit_d[took] = dist[absorb]
        current[took] = lab[absorb]
        top_z[took] = z[absorb]
        top_d[took] = dist[absorb]
        band = e & ~absorb & ~own
        within = band & (
            dist - exit_d[index] <= width_m[current[index]] + _DISTANCE_SLACK_M
        )
        marked = absorb | within
        if marked.any():
            evac_parts.append(
                pd.DataFrame(
                    {
                        "ray": index[marked],
                        "cell": cell[marked],
                        "dist": dist[marked],
                        "owner": current[index[marked]],
                    }
                )
            )
        if absorb.any():
            absorbed_parts.append(pd.DataFrame({"ray": took, "element": lab[absorb]}))
        ended = band & ~within
        evac_end[index[ended]] = exit_d[index[ended]] + width_m[current[index[ended]]]
        evac[index[ended | (evac[index] & stop)]] = False

        # The imminent band, from the first cell past the evacuated one.
        i = imminent[index] & ~evac[index] & ~stop
        repose_z = rays.toe_z[index] + (rays.run_m[index] + dist) * tan_repose
        with np.errstate(invalid="ignore"):
            keep = i & (
                (dist <= evac_end[index] + t45_m[current[index]] + _DISTANCE_SLACK_M)
                | (z > repose_z)
            )
        if keep.any():
            imminent_parts.append(
                pd.DataFrame({"ray": index[keep], "cell": cell[keep]})
            )
        imminent[index[(i & ~keep) | (imminent[index] & stop)]] = False

        # The probe for the element above that the polygon did not take.
        p = probe[index] & ~stop
        hit = p & facing & ~own & ~absorb & (lab != current[index])
        if hit.any():
            bench = np.maximum(dist[hit] - exit_d[index[hit]] - cell_size_m, 0.0)
            probe_parts.append(
                pd.DataFrame(
                    {
                        "ray": index[hit],
                        "element": lab[hit],
                        "cell": cell[hit],
                        "bench_width_m": bench,
                    }
                )
            )
        too_far = p & (dist - exit_d[index] > BETA_STACK_SEARCH_M)
        probe[index[hit | too_far | (probe[index] & stop)]] = False

    def frame(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
        if not parts:
            return pd.DataFrame({name: pd.Series(dtype=float) for name in columns})
        return pd.concat(parts, ignore_index=True)

    return _UphillResult(
        evacuated=frame(evac_parts, ["ray", "cell", "dist", "owner"]),
        imminent=frame(imminent_parts, ["ray", "cell"]),
        absorbed=frame(absorbed_parts, ["ray", "element"]).drop_duplicates(),
        probe=frame(probe_parts, ["ray", "element", "cell", "bench_width_m"]),
        top_z=top_z,
        top_d=top_d,
    )


def _march_downhill(
    labels: NDArray[np.int32],
    dem: NDArray[np.float64],
    rays: _Rays,
    *,
    top_z: NDArray[np.float64],
    top_d: NDArray[np.float64],
    reach_hl: NDArray[np.float64],
    barriers: NDArray[np.bool_] | None,
    cell_size_m: float,
) -> pd.DataFrame:
    """March every ray down its fall line past its toe: the inundated ground.

    A ray first crosses its own element; from the first cell off it, a cell is
    inundated while the ground lies under the line from the polygon's crest
    (``top_z``, ``top_d`` behind the ray's crest cell) dipping at
    ``reach_hl``. The ray stops at the first cell at or over the line, at a
    barrier cell, at nodata and at the edge of the grid.

    Returns:
        ``ray`` and ``cell`` of every inundated cell.
    """
    shape = labels.shape
    n_rays = rays.row.size
    on_base = np.ones(n_rays, dtype=bool)
    active = np.isfinite(reach_hl) & np.isfinite(top_z)
    parts: list[pd.DataFrame] = []
    max_steps = int(2 * (shape[0] + shape[1]) / WALK_STEP_CELLS)
    for k in range(1, max_steps + 1):
        index = np.nonzero(active)[0]
        if index.size == 0:
            break
        step = k * WALK_STEP_CELLS
        r = np.rint(rays.row[index] - step * rays.up_row[index]).astype(np.intp)
        c = np.rint(rays.col[index] - step * rays.up_col[index]).astype(np.intp)
        inside = (r >= 0) & (r < shape[0]) & (c >= 0) & (c < shape[1])
        r_in = np.where(inside, r, 0)
        c_in = np.where(inside, c, 0)
        dist = (
            -(
                (r - rays.row[index]) * rays.up_row[index]
                + (c - rays.col[index]) * rays.up_col[index]
            )
            * cell_size_m
        )
        z = np.where(inside, dem[r_in, c_in], np.nan)
        lab = np.where(inside, labels[r_in, c_in], OUTSIDE)
        on_base[index] &= lab == rays.base[index]
        blocked = ~inside | ~np.isfinite(z)
        if barriers is not None:
            blocked |= inside & barriers[r_in, c_in]
        line_z = top_z[index] - (top_d[index] + dist) * reach_hl[index]
        past = ~on_base[index] & ~blocked
        with np.errstate(invalid="ignore"):
            covered = past & (z < line_z)
        if covered.any():
            parts.append(
                pd.DataFrame(
                    {"ray": index[covered], "cell": (r_in * shape[1] + c_in)[covered]}
                )
            )
        active[index[blocked | (past & ~covered)]] = False
    if not parts:
        return pd.DataFrame({"ray": pd.Series(dtype=int), "cell": pd.Series(dtype=int)})
    return pd.concat(parts, ignore_index=True).drop_duplicates()


def _crest_distance(
    found: SlopeElements, cell_size_m: float
) -> tuple[NDArray[np.intp], NDArray[np.float64], NDArray[np.intp]]:
    """Each element cell's flat index, distance below its crest, and crest cell."""
    labels = found.labels
    rows, cols = np.nonzero(labels > OUTSIDE)
    d_row = found.layers.downhill_row[rows, cols]
    d_col = found.layers.downhill_col[rows, cols]
    has = np.isfinite(d_row) & np.isfinite(d_col)
    up_row = np.where(has, -d_row, 0.0)
    up_col = np.where(has, -d_col, 0.0)
    crest_rows, crest_cols = _march_within(labels, rows, cols, up_row, up_col)
    distance = np.hypot(crest_rows - rows, crest_cols - cols) * cell_size_m
    n_cols = labels.shape[1]
    return rows * n_cols + cols, distance, crest_rows * n_cols + crest_cols


def _along_contour(
    cells: NDArray[np.intp], aspect_deg: NDArray[np.float64], n_cols: int
) -> NDArray[np.float64]:
    """Each cell's position along the contour of its element's aspect, in cells.

    In array axes the downhill bearing's unit vector is ``(-cos, sin)`` along
    (rows, columns), so the contour runs along ``(sin, cos)``.
    """
    rows, cols = np.divmod(cells, n_cols)
    radians = np.radians(np.nan_to_num(aspect_deg, nan=0.0))
    return rows * np.sin(radians) + cols * np.cos(radians)


def _segments(
    claims: pd.DataFrame,
    element_height_m: NDArray[np.float64],
    cell_area_m2: float,
    cell_size_m: float,
) -> pd.Series:
    """Cut each element along its contour by the volume of the run so far.

    ``claims`` holds one row per evacuated cell of each element (``element``,
    ``u`` the position along the contour in cells, ``depth`` NaN where the
    volume-area relation holds). A cell read by area takes the mean depth of a
    volume-area failure of :data:`BETA_SEGMENT_VOLUME_M3`, so a polygon read
    wholly by area is cut at that volume too. Where a run as long as the
    element is high holds more than the segment volume, at the element's mean
    volume per metre, the segment holds that instead, so no segment is shorter
    than its element's height; the remainder at the end of the run joins the
    segment before it where it is shorter.

    Returns:
        The segment of each claim, from 0, aligned to ``claims``.
    """
    area_at_volume = (BETA_SEGMENT_VOLUME_M3 / ALPHA) ** (1.0 / GAMMA)
    depth_at_volume = BETA_SEGMENT_VOLUME_M3 / area_at_volume
    volume = claims["depth"].fillna(depth_at_volume).to_numpy() * cell_area_m2
    bins = pd.DataFrame(
        {
            "element": claims["element"].to_numpy(),
            "bin": np.floor(claims["u"].to_numpy()).astype(np.int64),
            "volume": volume,
        }
    )
    per_bin = bins.groupby(["element", "bin"], sort=True)["volume"].sum().reset_index()
    by_element = per_bin.groupby("element")["volume"]
    before = by_element.cumsum() - per_bin["volume"]
    # A segment holds the segment volume, or the volume of a run as long as
    # the element is high where that is more, at the element's mean volume per
    # metre of contour, so no segment is shorter than its element's height.
    heights = element_height_m[per_bin["element"].to_numpy() - 1]
    per_metre = by_element.transform("mean").to_numpy() / cell_size_m
    limit = np.maximum(BETA_SEGMENT_VOLUME_M3, per_metre * np.nan_to_num(heights))
    per_bin["segment"] = np.floor(before.to_numpy() / limit).astype(np.int64)

    # No segment shorter than its element's height: the last one, the
    # remainder of the run, joins the one before it.
    extent = per_bin.groupby(["element", "segment"])["bin"].agg(["min", "max"])
    length = (extent["max"] - extent["min"] + 1) * cell_size_m
    last = per_bin.groupby("element")["segment"].transform("max")
    lengths = length.reindex(
        pd.MultiIndex.from_arrays([per_bin["element"], per_bin["segment"]])
    ).to_numpy()
    short = (
        (per_bin["segment"] == last)
        & (last > 0)
        & (lengths < element_height_m[per_bin["element"].to_numpy() - 1])
    )
    per_bin.loc[short, "segment"] -= 1
    keyed = per_bin.set_index(["element", "bin"])["segment"]
    found = keyed.reindex(pd.MultiIndex.from_arrays([bins["element"], bins["bin"]]))
    return pd.Series(found.to_numpy(), index=claims.index)


def _ancestors(drainage: pd.DataFrame) -> Callable[[int], frozenset[int]]:
    """Every element's upslope elements, itself included, by the drainage links.

    Returns:
        A function from an element to the set, computed once per element.
    """
    uppers: dict[int, list[int]] = {}
    for upper, lower in zip(
        drainage["upper"].astype(int), drainage["lower"].astype(int), strict=True
    ):
        uppers.setdefault(lower, []).append(upper)

    @cache
    def of(element: int) -> frozenset[int]:
        seen = {element}
        queue = [element]
        while queue:
            for upper in uppers.get(queue.pop(), ()):
                if upper not in seen:
                    seen.add(upper)
                    queue.append(upper)
        return frozenset(seen)

    return of


def _contest(
    claims: pd.DataFrame,
    polygons: pd.DataFrame,
    absorbed: dict[int, set[int]],
    entered: dict[int, set[int]],
    found: SlopeElements,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Settle the evacuated cells two or more polygons reach.

    Two polygons both keep the cells they share where one is a stack that
    took the other's element (:data:`STACK_OVERLAP`); where their elements'
    catchments are disjoint and they face apart (:data:`SEPARATE_CATCHMENTS`);
    and where one reached into the other's element within its own width
    behind its crest (:data:`WITHIN_WIDTH`, the plan's stack rule 3: an
    element takes its own width even where that reaches into the element
    above). Otherwise each shared cell goes to the polygon whose crest is
    nearer, so the polygons tile.

    Returns:
        ``(claims, overlaps)``: the claims each polygon keeps, and the pairs
        that keep the same cells with their reason.
    """
    counts = claims.groupby("cell")["polygon"].transform("size")
    multi = claims[counts > 1]
    overlap_columns = ["polygon_a", "polygon_b", "n_cells", "reason"]
    if multi.empty:
        return claims, pd.DataFrame(columns=overlap_columns)
    pairs = multi.merge(multi, on="cell", suffixes=("_p", "_q"))
    pairs = pairs[pairs["polygon_p"] != pairs["polygon_q"]]

    base = polygons["element"]
    aspect = found.elements["aspect_deg"]
    ancestors = _ancestors(found.drainage_links)
    unique_pairs = pairs[["polygon_p", "polygon_q"]].drop_duplicates()
    reasons: dict[tuple[int, int], str | None] = {}
    for p, q in zip(unique_pairs["polygon_p"], unique_pairs["polygon_q"], strict=True):
        base_p, base_q = int(base[p]), int(base[q])
        if base_q in absorbed.get(p, set()) or base_p in absorbed.get(q, set()):
            reasons[p, q] = STACK_OVERLAP
            continue
        apart = abs((aspect[base_p] - aspect[base_q] + 180.0) % 360.0 - 180.0)
        if apart > BETA_FACING_APART_DEG and not (
            ancestors(base_p) & ancestors(base_q)
        ):
            reasons[p, q] = SEPARATE_CATCHMENTS
            continue
        if base_q in entered.get(p, set()) or base_p in entered.get(q, set()):
            reasons[p, q] = WITHIN_WIDTH
            continue
        reasons[p, q] = None
    keys = list(zip(pairs["polygon_p"], pairs["polygon_q"], strict=True))
    reason = pd.Series([reasons[key] for key in keys], index=pairs.index)
    beaten = reason.isna() & (
        (pairs["dist_q"] < pairs["dist_p"])
        | (
            (pairs["dist_q"] == pairs["dist_p"])
            & (pairs["polygon_q"] < pairs["polygon_p"])
        )
    )
    losers = pairs.loc[beaten, ["cell", "polygon_p"]].drop_duplicates()
    losers = losers.rename(columns={"polygon_p": "polygon"})
    flagged = claims.merge(losers.assign(lost=True), on=["cell", "polygon"], how="left")
    kept = flagged[flagged["lost"].isna()].drop(columns=["lost"])

    still = kept.groupby("cell")["polygon"].transform("size") > 1
    shared = kept[still]
    both = shared.merge(shared, on="cell", suffixes=("_a", "_b"))
    both = both[both["polygon_a"] < both["polygon_b"]]
    if both.empty:
        return kept, pd.DataFrame(columns=overlap_columns)
    keys = list(zip(both["polygon_a"], both["polygon_b"], strict=True))
    both = both.assign(reason=[reasons.get(key) or STACK_OVERLAP for key in keys])
    overlaps = (
        both.groupby(["polygon_a", "polygon_b", "reason"])
        .size()
        .rename("n_cells")
        .reset_index()[overlap_columns]
    )
    return kept, overlaps


def _fill_gaps(
    cells: pd.DataFrame,
    shape: tuple[int, int],
    taken: NDArray[np.bool_] | None = None,
) -> pd.DataFrame:
    """Close the one-cell gaps diverging rays leave in each polygon's zone.

    A cell joins a polygon's zone where the zone holds both of its neighbours
    along a row or along a column, unless ``taken`` (a flat mask over the
    grid) marks it as another polygon's. Whole arrays: each polygon's cells
    are keyed ``polygon x cells + cell`` and looked up by binary search.

    Returns:
        ``cells`` with the gap cells added, keeping the zone of each polygon.
    """
    if cells.empty:
        return cells
    n_cells = shape[0] * shape[1]
    polygon = cells["polygon"].to_numpy(dtype=np.int64)
    cell = cells["cell"].to_numpy(dtype=np.int64)
    keys = np.unique(polygon * n_cells + cell)
    position = keys % n_cells
    rows, cols = np.divmod(position, shape[1])

    def present(candidate: NDArray[np.int64]) -> NDArray[np.bool_]:
        found = np.searchsorted(keys, candidate)
        found = np.minimum(found, keys.size - 1)
        return keys[found] == candidate

    added = []
    for step, fits in ((1, cols + 2 < shape[1]), (shape[1], rows + 2 < shape[0])):
        gap = keys + step
        across = fits & present(keys + 2 * step) & ~present(gap)
        added.append(gap[across])
    gaps = np.unique(np.concatenate(added))
    gap_polygon, gap_cell = np.divmod(gaps, n_cells)
    if taken is not None:
        free = ~taken[gap_cell]
        gap_polygon, gap_cell = gap_polygon[free], gap_cell[free]
    if gap_cell.size == 0:
        return cells
    zone = cells.drop_duplicates("polygon").set_index("polygon")["zone"]
    extra = pd.DataFrame(
        {
            "polygon": gap_polygon,
            "cell": gap_cell,
            "zone": zone.reindex(gap_polygon).to_numpy(),
        }
    )
    return pd.concat([cells, extra[cells.columns]], ignore_index=True)


def _element_links(
    stack_links: pd.DataFrame, width_m: NDArray[np.float64]
) -> pd.DataFrame:
    """The stack links with the lower element's width and whether they stack."""
    links = stack_links.copy()
    lower = links["lower"].to_numpy(dtype=np.intp) if len(links) else np.zeros(0, int)
    links["lower_width_m"] = width_m[lower - 1] if len(links) else np.zeros(0)
    links["makes_stack"] = (
        links["bench_width_m"].to_numpy(dtype=float) < links["lower_width_m"]
        if len(links)
        else np.zeros(0, dtype=bool)
    )
    return links


def _empty(
    found: SlopeElements, shape: tuple[int, int], transform: Affine
) -> SlopePolygons:
    polygon_columns = [
        "element",
        "segment",
        "element_type",
        "ground_group",
        "is_fill",
        "style",
        "width_rule",
        "width_behind_crest_m",
        "width_realised_m",
        "is_stack",
        "top_element",
        "n_stack_elements",
        "base_height_m",
        "height_m",
        "length_m",
        "area_m2",
        "depth_m",
        "volume_m3",
        "reach_hl",
        "imminent_area_m2",
        "inundated_area_m2",
        "n_rays",
        "centroid_x",
        "centroid_y",
    ]
    polygons = pd.DataFrame(columns=polygon_columns)
    polygons.index.name = "polygon"
    return SlopePolygons(
        polygons=polygons,
        cells=pd.DataFrame(columns=["polygon", "zone", "row", "col", "depth_m"]),
        element_links=_element_links(found.stack_links, np.zeros(0)),
        retrogression_links=pd.DataFrame(
            columns=[
                "lower_polygon",
                "lower_element",
                "upper_element",
                "upper_polygon",
                "bench_width_m",
                "n_rays",
            ]
        ),
        overlaps=pd.DataFrame(columns=["polygon_a", "polygon_b", "n_cells", "reason"]),
        shape=shape,
        transform=transform,
    )


def _claims(
    found: SlopeElements, rays: _Rays, uphill: _UphillResult, cell_size_m: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The evacuated claims of each element, one per element and cell.

    An element claims its own cells, with their distance below its crest, and
    the cells its rays marked behind its crest, with their distance behind it.
    Each claim carries ``position`` (behind the crest, negative on the face),
    ``owner`` (the element whose ground it is), ``ray`` (-1 for an own cell),
    ``plane_ray`` (the ray whose slip plane its depth is read on: its own for
    a marked cell, its crest cell's for an own cell, -1 where its crest cell
    set out none) and ``on_element`` (the label of the cell).

    Returns:
        ``(claims, band)``: the claims, and every cell the rays marked before
        a cell reached twice by one element was kept once.
    """
    labels = found.labels
    flat_labels = labels.ravel()
    n_cols = labels.shape[1]
    own_cells, below_crest, crest_cells = _crest_distance(found, cell_size_m)
    own_element = flat_labels[own_cells]
    ray_at = np.full(labels.size, -1, dtype=np.int64)
    ray_at[rays.row * n_cols + rays.col] = np.arange(rays.row.size)
    own = pd.DataFrame(
        {
            "element": own_element,
            "cell": own_cells,
            "dist": below_crest,
            "position": -below_crest,
            "owner": own_element,
            "ray": -1,
            "plane_ray": ray_at[crest_cells],
            "on_element": own_element,
        }
    )
    marked = uphill.evacuated
    ray = marked["ray"].to_numpy(dtype=np.int64)
    cell = marked["cell"].to_numpy(dtype=np.intp)
    dist = marked["dist"].to_numpy(dtype=float)
    band = pd.DataFrame(
        {
            "element": rays.base[ray],
            "cell": cell,
            "dist": dist,
            "position": dist,
            "owner": marked["owner"].to_numpy(dtype=np.int64),
            "ray": ray,
            "plane_ray": ray,
            "on_element": flat_labels[cell],
        }
    )
    claims = pd.concat([own, band], ignore_index=True)
    claims = claims.sort_values(["element", "cell", "dist"], kind="stable")
    claims = claims.drop_duplicates(["element", "cell"]).reset_index(drop=True)
    return claims, band


def _set_planar_depths(
    claims: pd.DataFrame,
    dem: NDArray[np.float64],
    rays: _Rays,
    *,
    planar: NDArray[np.bool_],
    width_m: NDArray[np.float64],
    cell_size_m: float,
) -> None:
    """Give a free-face's own claims their depth to its slip plane, in place.

    ``planar`` and ``width_m`` are indexed by element label. A claim is read on
    the plane of its ``plane_ray`` where it is the free-face's own ground (its
    own cells and its wedge, not an element its stack took); every other
    claim keeps the depth it has.
    """
    element = claims["element"].to_numpy(dtype=np.intp)
    ray = claims["plane_ray"].to_numpy(dtype=np.intp)
    chosen = planar[element] & (claims["owner"].to_numpy() == element) & (ray >= 0)
    if not chosen.any():
        return
    # The ground at the back of each ray's width, read between cell centres.
    ray_width = width_m[rays.base] / cell_size_m
    back_z = ndimage.map_coordinates(
        dem,
        [rays.row + ray_width * rays.up_row, rays.col + ray_width * rays.up_col],
        order=1,
        mode="nearest",
    )
    back_z = np.where(np.isfinite(back_z), back_z, dem[rays.row, rays.col])
    r = ray[chosen]
    claims.loc[chosen, "depth"] = planar_depth_m(
        dem.ravel()[claims.loc[chosen, "cell"].to_numpy(dtype=np.intp)],
        claims.loc[chosen, "position"].to_numpy(dtype=float),
        toe_z=rays.toe_z[r],
        run_m=rays.run_m[r],
        back_z=back_z[r],
        width_m=width_m[element[chosen]],
    )


def _realised_width(
    kept: pd.DataFrame, ray_polygon: NDArray[np.int64], index: pd.Index
) -> NDArray[np.float64]:
    """The median over each polygon's rays of how far behind its crest it kept.

    Per ray, the distance behind the crest cell's centre of the furthest cell
    centre the ray kept after the shared ground was settled, zero where it
    kept none behind the crest.
    """
    marked = kept[kept["ray"] >= 0]
    furthest = marked.groupby("ray")["dist"].max()
    per_ray = np.zeros(ray_polygon.size)
    per_ray[furthest.index.to_numpy(dtype=np.intp)] = furthest.to_numpy()
    frame = pd.DataFrame({"polygon": ray_polygon, "width": per_ray})
    median = frame.groupby("polygon")["width"].median()
    return median.reindex(index).fillna(0.0).to_numpy()


def _retrogression(
    probe: pd.DataFrame,
    absorbed_frame: pd.DataFrame,
    ray_polygon: NDArray[np.int64],
    rays: _Rays,
    core_polygon: NDArray[np.int64],
) -> pd.DataFrame:
    """The retrogression links: elements above a polygon that it did not take."""
    columns = [
        "lower_polygon",
        "lower_element",
        "upper_element",
        "upper_polygon",
        "bench_width_m",
        "n_rays",
    ]
    if probe.empty:
        return pd.DataFrame(columns=columns)
    probe = probe.copy()
    ray_index = probe["ray"].to_numpy(dtype=np.intp)
    probe["lower_polygon"] = ray_polygon[ray_index]
    probe["lower_element"] = rays.base[ray_index]
    probe["upper_element"] = probe["element"].astype(np.int64)
    probe["upper_polygon"] = core_polygon[probe["cell"].to_numpy(dtype=np.intp)]
    # An element the polygon took is not linked to it.
    took = absorbed_frame.assign(
        lower_polygon=absorbed_frame["polygon"],
        upper_element=absorbed_frame["element"],
    )[["lower_polygon", "upper_element"]].drop_duplicates()
    probe = probe.merge(took.assign(taken=True), how="left")
    probe = probe[probe["taken"].isna()]
    return (
        probe.groupby(
            ["lower_polygon", "lower_element", "upper_element", "upper_polygon"]
        )["bench_width_m"]
        .agg(["median", "size"])
        .reset_index()
        .rename(columns={"median": "bench_width_m", "size": "n_rays"})
    )[columns]


def _keep_core(found: SlopeElements, result: SlopePolygons) -> SlopePolygons:
    """Drop the polygons of elements outside the tile's core, and their links.

    Called once the shared ground is settled, so a core polygon has met the
    halo's polygons as it would on the whole grid. A link or an overlap is
    kept where its lower or either polygon is the core's; the polygon ids it
    names in the halo are this tile's, and the halo element is found again on
    its own tile by its ``seed_x`` and ``seed_y``.
    """
    if "in_core" not in found.elements or found.elements["in_core"].all():
        return result
    core_elements = found.elements.index[found.elements["in_core"].to_numpy(bool)]
    keep = result.polygons.index[result.polygons["element"].isin(core_elements)]
    overlaps = result.overlaps
    return replace(
        result,
        polygons=result.polygons.loc[keep],
        cells=result.cells[result.cells["polygon"].isin(keep)].reset_index(drop=True),
        element_links=result.element_links[
            result.element_links["lower"].isin(core_elements)
        ].reset_index(drop=True),
        retrogression_links=result.retrogression_links[
            result.retrogression_links["lower_polygon"].isin(keep)
        ].reset_index(drop=True),
        overlaps=overlaps[
            overlaps["polygon_a"].isin(keep) | overlaps["polygon_b"].isin(keep)
        ].reset_index(drop=True),
    )


def build_slope_polygons(
    found: SlopeElements,
    dem: ArrayLike,
    transform: Affine,
    *,
    is_fill: pd.Series | None = None,
    retained_phi_deg: pd.Series | None = None,
    fill_thickness_m: pd.Series | None = None,
    barriers: ArrayLike | None = None,
) -> SlopePolygons:
    """Build the failure polygons and their zones from the slope elements.

    Args:
        found: The elements, from
            :func:`landloss.hazard.landslide.slope_elements.find_slope_elements`
            on the same DEM.
        dem: The ground elevation the elements were found on, NaN for nodata.
        transform: The grid's affine transform, north-up with square cells.
        is_fill: Per element (indexed by label), whether it is on fill, for
            example from its majority material or modification. Missing
            elements are not fill.
        retained_phi_deg: Per element, the friction angle of the ground a
            free-face retains, for its wedge; missing elements take
            :data:`BETA_DEFAULT_RETAINED_PHI_DEG`.
        fill_thickness_m: Per element, the fill thickness, for a fill bank's
            depth; missing elements are read by area.
        barriers: A boolean grid of the cells debris stops at (building
            outlines, roads); none where not given.

    Returns:
        The polygons, their cells by zone, and their links.

    Raises:
        ValueError: If the DEM or the barrier grid does not match the
            elements' grid, or the transform is not north-up with square
            cells.
    """
    elevation = np.asarray(dem, dtype=float)
    shape = found.labels.shape
    if elevation.shape != shape:
        msg = f"The DEM is {elevation.shape}, the elements' grid {shape}."
        raise ValueError(msg)
    barrier_grid = None
    if barriers is not None:
        barrier_grid = np.asarray(barriers, dtype=bool)
        if barrier_grid.shape != shape:
            msg = f"The barrier grid is {barrier_grid.shape}, the elements' {shape}."
            raise ValueError(msg)
    if transform.b != 0 or transform.d != 0 or transform.e >= 0:
        msg = "The grid has to be north-up with no rotation."
        raise ValueError(msg)
    if not math.isclose(transform.a, -transform.e):
        msg = f"The cells have to be square, not {transform.a} by {-transform.e}."
        raise ValueError(msg)
    cell_size_m = float(transform.a)
    cell_area_m2 = cell_size_m**2
    elements = found.elements
    if elements.empty:
        return _empty(found, shape, transform)

    # Per element, indexed by label with 0 unused.
    fill = _per_element(is_fill, elements.index, default=0.0).astype(bool)
    phi = _per_element(
        retained_phi_deg, elements.index, default=BETA_DEFAULT_RETAINED_PHI_DEG
    )
    thickness = _per_element(fill_thickness_m, elements.index, default=np.nan)
    element_type = elements["element_type"].to_numpy()
    height = elements["height_m"].to_numpy()
    angle = elements["overall_angle_deg"].to_numpy()
    width, rule = width_behind_crest_m(
        element_type, height, angle, is_fill=fill, phi_deg=phi
    )
    depth = element_depth_m(
        element_type,
        height,
        is_fill=fill,
        fill_thickness_m=thickness,
        width_m=width,
        run_m=elements["run_m"].to_numpy(),
    )
    climbs = (element_type == FREE_FACE) & elements["mm6_cut"].to_numpy(dtype=bool)

    def by_label(values: NDArray, fill_value: float) -> NDArray:
        return np.r_[np.asarray([fill_value], dtype=values.dtype), values]

    width_l = by_label(width, 0.0)
    t45_l = by_label(headscarp_band_width_m(angle), 0.0)
    climbs_l = by_label(climbs, fill_value=False)
    depth_l = by_label(depth, np.nan)
    aspect = elements["aspect_deg"].to_numpy()
    n_cols = shape[1]

    rays = _crest_rays(found, elevation, cell_size_m)
    uphill = _march_uphill(
        found,
        elevation,
        rays,
        width_m=width_l,
        t45_m=t45_l,
        climbs=climbs_l,
        cell_size_m=cell_size_m,
    )

    claims, band = _claims(found, rays, uphill, cell_size_m)
    claims["depth"] = depth_l[claims["owner"].to_numpy(dtype=np.intp)]
    _set_planar_depths(
        claims,
        elevation,
        rays,
        planar=by_label(element_type == FREE_FACE, fill_value=False),
        width_m=width_l,
        cell_size_m=cell_size_m,
    )
    # A ray's cells sit along the contour where its crest cell does.
    ray_cell = rays.row * n_cols + rays.col
    position_cell = np.where(
        claims["ray"].to_numpy() >= 0,
        ray_cell[np.maximum(claims["ray"].to_numpy(), 0)],
        claims["cell"].to_numpy(),
    )
    claims["u"] = _along_contour(
        position_cell, aspect[claims["element"].to_numpy() - 1], n_cols
    )
    claims["segment"] = _segments(claims, height, cell_area_m2, cell_size_m)

    # One polygon per element segment, numbered from 1 in element order.
    keys = claims[["element", "segment"]].drop_duplicates()
    keys = keys.sort_values(["element", "segment"]).reset_index(drop=True)
    keys.index = pd.RangeIndex(1, len(keys) + 1, name="polygon")
    polygon_of = pd.Series(
        keys.index, index=pd.MultiIndex.from_frame(keys[["element", "segment"]])
    )
    claims["polygon"] = polygon_of.reindex(
        pd.MultiIndex.from_frame(claims[["element", "segment"]])
    ).to_numpy()

    # Each ray belongs to the polygon of its crest cell.
    core_polygon = np.zeros(shape[0] * n_cols, dtype=np.int64)
    own_cells = claims[claims["ray"] < 0]
    core_polygon[own_cells["cell"].to_numpy()] = own_cells["polygon"].to_numpy()
    ray_polygon = core_polygon[ray_cell]

    absorbed_frame = uphill.absorbed.assign(
        polygon=ray_polygon[uphill.absorbed["ray"].to_numpy(dtype=np.intp)]
    )
    absorbed: dict[int, set[int]] = {
        int(polygon): set(group["element"].astype(int))
        for polygon, group in absorbed_frame.groupby("polygon")
    }
    # The elements whose ground each polygon's rays reached within its own
    # width behind its crest (not by climbing a stack).
    reached = band[
        (band["on_element"] > OUTSIDE)
        & (band["on_element"] != band["element"])
        & (band["owner"] == band["element"])
    ]
    entered: dict[int, set[int]] = {
        int(polygon): set(group["on_element"].astype(int))
        for polygon, group in reached.assign(
            polygon=ray_polygon[reached["ray"].to_numpy(dtype=np.intp)]
        ).groupby("polygon")
    }

    kept, overlaps = _contest(
        claims[["cell", "polygon", "dist", "depth", "ray"]],
        keys,
        absorbed,
        entered,
        found,
    )
    evacuated = kept[["polygon", "cell"]].assign(zone=EVACUATED)
    taken = np.zeros(shape[0] * n_cols, dtype=bool)
    taken[kept["cell"].to_numpy(dtype=np.intp)] = True
    evacuated = _fill_gaps(evacuated, shape, taken)

    # Polygon attributes.
    polygons = keys.copy()
    base = polygons["element"].to_numpy()
    polygons["element_type"] = element_type[base - 1]
    polygons["ground_group"] = elements["ground_group"].to_numpy()[base - 1]
    polygons["is_fill"] = fill[base - 1]
    polygons["style"] = np.where(fill[base - 1], FILL_FLOW_SLIDE, DRY_DEBRIS_AVALANCHE)
    polygons["width_rule"] = rule[base - 1]
    polygons["width_behind_crest_m"] = width[base - 1]
    polygons["width_realised_m"] = _realised_width(kept, ray_polygon, polygons.index)
    polygons["is_stack"] = climbs[base - 1]
    tops = pd.DataFrame(
        {
            "polygon": ray_polygon,
            "top": np.zeros(ray_polygon.size, dtype=np.int64),
            # The element's own height, toe to crest between the breaks in
            # slope, and the rise from its crest cell to the top of the stack.
            "rise": height[rays.base - 1]
            + (uphill.top_z - elevation[rays.row, rays.col]),
        }
    )
    current_top = absorbed_frame.groupby("ray")["element"].last()
    tops.loc[current_top.index, "top"] = current_top.to_numpy()
    tops["top"] = np.where(tops["top"] > 0, tops["top"], rays.base)
    by_polygon = tops.groupby("polygon")
    top_counts = tops.groupby(["polygon", "top"]).size().reset_index(name="n")
    top_counts = top_counts.sort_values(
        ["polygon", "n", "top"], ascending=[True, False, True]
    )
    polygons["top_element"] = (
        top_counts.drop_duplicates("polygon").set_index("polygon")["top"]
    ).reindex(polygons.index)
    polygons["top_element"] = (
        polygons["top_element"]
        .fillna(pd.Series(base, index=polygons.index))
        .astype(int)
    )
    polygons["n_stack_elements"] = [
        len(absorbed.get(int(p), set())) for p in polygons.index
    ]
    polygons["base_height_m"] = height[base - 1]
    polygon_height = by_polygon["rise"].median().reindex(polygons.index)
    polygons["height_m"] = polygon_height.fillna(
        pd.Series(height[base - 1], index=polygons.index)
    )
    own_u = claims[claims["ray"] < 0].groupby("polygon")["u"]
    polygons["length_m"] = ((own_u.max() - own_u.min() + 1.0) * cell_size_m).reindex(
        polygons.index
    )

    # Volumes: each evacuated cell's depth; a cell the gap filling added takes
    # its polygon's mean, and a polygon read by area the volume-area depth.
    evac_cells = evacuated[["polygon", "cell"]].drop_duplicates()
    area = evac_cells.groupby("polygon").size().reindex(polygons.index, fill_value=0)
    polygons["area_m2"] = area.to_numpy() * cell_area_m2
    cell_depth = kept.groupby(["polygon", "cell"])["depth"].first()
    mean_depth = kept.groupby("polygon")["depth"].mean()
    evac_index = pd.MultiIndex.from_frame(evac_cells[["polygon", "cell"]])
    gap = ~evac_index.isin(cell_depth.index)
    evac_cells = evac_cells.assign(depth=cell_depth.reindex(evac_index).to_numpy())
    gap_depth = mean_depth.reindex(evac_cells["polygon"]).to_numpy()
    evac_cells.loc[gap, "depth"] = gap_depth[gap]
    area_depth = pd.Series(
        _area_depth_m(polygons["area_m2"].to_numpy()), index=polygons.index
    )
    evac_cells["depth"] = evac_cells["depth"].fillna(
        area_depth.reindex(evac_cells["polygon"]).set_axis(evac_cells.index)
    )
    volume = (
        evac_cells.groupby("polygon")["depth"].sum().reindex(polygons.index).fillna(0)
        * cell_area_m2
    ).to_numpy()
    polygons["volume_m3"] = volume
    with np.errstate(invalid="ignore", divide="ignore"):
        polygons["depth_m"] = volume / polygons["area_m2"].to_numpy()
    polygons["reach_hl"] = reach_ratio(
        np.maximum(volume, _MIN_VOLUME_M3), polygons["style"].to_numpy()
    )
    polygons["n_rays"] = by_polygon.size().reindex(polygons.index, fill_value=0)

    # The imminent band, less the polygon's own evacuated ground as kept.
    imminent = uphill.imminent.assign(
        polygon=ray_polygon[uphill.imminent["ray"].to_numpy(dtype=np.intp)]
    )[["polygon", "cell"]].drop_duplicates()
    imminent = _fill_gaps(imminent.assign(zone=IMMINENT), shape)
    imminent = imminent.merge(
        evac_cells[["polygon", "cell"]].assign(evac=True),
        on=["polygon", "cell"],
        how="left",
    )
    imminent = imminent[imminent["evac"].isna()].drop(columns="evac")

    # The inundated ground: the reach from the polygon's crest, and for a
    # stack the reach from its own free-face's crest as well, so taking the
    # stack never runs out shorter than the free-face alone would.
    hl = polygons["reach_hl"].reindex(ray_polygon).to_numpy()
    runout = pd.concat(
        [
            _march_downhill(
                found.labels,
                elevation,
                rays,
                top_z=top_z,
                top_d=top_d,
                reach_hl=hl,
                barriers=barrier_grid,
                cell_size_m=cell_size_m,
            )
            for top_z, top_d in (
                (uphill.top_z, uphill.top_d),
                (elevation[rays.row, rays.col], np.zeros(rays.row.size)),
            )
        ],
        ignore_index=True,
    )
    inundated = runout.assign(
        polygon=ray_polygon[runout["ray"].to_numpy(dtype=np.intp)]
    )
    inundated = inundated[["polygon", "cell"]].drop_duplicates().assign(zone=INUNDATED)
    inundated = _fill_gaps(inundated, shape)
    # A polygon's debris does not cover its own evacuated ground (a ray whose
    # fall line wanders back over its element under noise).
    inundated = inundated.merge(
        evac_cells[["polygon", "cell"]].assign(evac=True),
        on=["polygon", "cell"],
        how="left",
    )
    inundated = inundated[inundated["evac"].isna()].drop(columns="evac")
    if barrier_grid is not None:
        inundated = inundated[~barrier_grid.ravel()[inundated["cell"].to_numpy()]]

    cells = pd.concat([evacuated, imminent, inundated], ignore_index=True)
    cells = cells.drop_duplicates(["polygon", "zone", "cell"])
    cells = cells.merge(
        evac_cells.assign(zone=EVACUATED), on=["polygon", "zone", "cell"], how="left"
    )
    rows, cols = np.divmod(cells["cell"].to_numpy(dtype=np.int64), n_cols)
    cells = pd.DataFrame(
        {
            "polygon": cells["polygon"].to_numpy(dtype=np.int64),
            "zone": cells["zone"].to_numpy(),
            "row": rows,
            "col": cols,
            "depth_m": cells["depth"].to_numpy(dtype=float),
        }
    ).sort_values(["polygon", "zone", "row", "col"], ignore_index=True)

    zone_area = (
        cells.pivot_table(
            index="polygon", columns="zone", values="row", aggfunc="size", fill_value=0
        )
        * cell_area_m2
    ).reindex(index=polygons.index, columns=list(ZONES), fill_value=0)
    polygons["imminent_area_m2"] = zone_area[IMMINENT].astype(float)
    polygons["inundated_area_m2"] = zone_area[INUNDATED].astype(float)
    evac_rows = cells[cells["zone"] == EVACUATED]
    x = transform.c + (evac_rows["col"] + 0.5) * transform.a
    y = transform.f + (evac_rows["row"] + 0.5) * transform.e
    polygons["centroid_x"] = (
        x.groupby(evac_rows["polygon"]).mean().reindex(polygons.index)
    )
    polygons["centroid_y"] = (
        y.groupby(evac_rows["polygon"]).mean().reindex(polygons.index)
    )

    links = _element_links(found.stack_links, width)
    retrogression = _retrogression(
        uphill.probe, absorbed_frame, ray_polygon, rays, core_polygon
    )
    return _keep_core(
        found,
        SlopePolygons(
            polygons=polygons,
            cells=cells,
            element_links=links,
            retrogression_links=retrogression,
            overlaps=overlaps,
            shape=shape,
            transform=transform,
        ),
    )


def polygon_geometries(
    result: SlopePolygons, *, zone: str, crs: object
) -> gpd.GeoDataFrame:
    """Draw one zone of every polygon as shapely geometry, cell edges and all.

    Args:
        result: The polygons, from :func:`build_slope_polygons`.
        zone: One of :data:`ZONES`.
        crs: The grid's coordinate reference system.

    Returns:
        One row per polygon with cells in the zone: ``polygon`` and its
        ``geometry`` (a polygon or multipolygon), true to the cells.

    Raises:
        ValueError: If the zone is not one of :data:`ZONES`.
    """
    if zone not in ZONES:
        msg = f"The zone has to be one of {ZONES}, not {zone!r}."
        raise ValueError(msg)
    chosen = result.cells[result.cells["zone"] == zone]
    names: list[int] = []
    shapes: list[shapely.Geometry] = []
    for polygon, group in chosen.groupby("polygon"):
        rows = group["row"].to_numpy()
        cols = group["col"].to_numpy()
        r0, c0 = int(rows.min()), int(cols.min())
        grid = np.zeros((rows.max() - r0 + 1, cols.max() - c0 + 1), dtype=np.uint8)
        grid[rows - r0, cols - c0] = 1
        window = result.transform * Affine.translation(c0, r0)
        pieces = [
            to_shape(geometry)
            for geometry, value in features.shapes(
                grid, mask=grid > 0, transform=window
            )
            if value > 0
        ]
        names.append(int(polygon))
        shapes.append(shapely.union_all(pieces))
    return gpd.GeoDataFrame({"polygon": names}, geometry=shapes, crs=crs)
