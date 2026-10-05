"""Cut, fill or natural ground at each pif.

A pif (:mod:`landloss.hazard.landslide.instability_zones`) is a step in the 1 m
DEM. Whether it is a cut face, a fill batter or a benched terrace's face (both)
depends on where the step sits against the ground that was there before the
earthworks. That ground is not measured, so it is estimated per pif by an
**anchor surface**: a quadratic fitted to the DEM within :data:`FIT_RADIUS_M` of
the pif, using only ground off the faces, reweighted by Tukey's bisquare so a
platform well off the trend counts for less (:func:`fit_quadratic`).

The comparison needs both ends of each face, because a pip is the crest of a
drop and stands above any smoothed surface. Each pip is walked down its own fall
direction to the foot of the face (:func:`face_feet`); every cell passed over,
for every pif, grown by :data:`FACE_BUFFER_M`, is left out of the fits
(:func:`face_mask`). Then, per pif, with the crest and foot residuals the
medians over its pips of the DEM minus its surface (:func:`classify`):

- the **excess drop**, crest residual minus foot residual, is how much further
  the ground falls across the face than the natural surface does; no more than
  :data:`EXCESS_DROP_M` is natural ground, and no more than :data:`SCALE_K` of
  the fit's own residual scatter is uncertain;
- the **position**, crest plus foot residual over the excess drop, runs from -1
  (all of the excess below the surface: cut) to +1 (all above: fill); beyond
  :data:`POSITION_SPLIT` either way is a cut or a fill, between is cut and fill.

The surface is fitted to today's ground, so a fill tens of metres across *is*
the local surface: the class says how a face sits against the platforms around
it, not against the pre-development ground under a large fill. The research
behind it, and its agreement with the GNS SLIDE cut slopes and fill bodies, is
in ``src/scripts/landloss/hazard/landslide/research/cut_fill/pif_cut_fill.md``.
Every threshold is judgement, untuned.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from rasterio.transform import Affine
from scipy import ndimage

from landloss.hazard.landslide.instability_zones import DIRECTIONS

CUT = "cut"
FILL = "fill"
CUT_AND_FILL = "cut_and_fill"
UNCERTAIN = "uncertain"
NATURAL = "natural"
UNKNOWN = "unknown"
CLASSES = (CUT, CUT_AND_FILL, FILL, UNCERTAIN, NATURAL, UNKNOWN)

# The walk to the foot of a face stops at the first step flatter than this, in
# degrees, or after FOOT_MAX_M metres.
FOOT_SLOPE_DEG = 20.0
FOOT_MAX_M = 15.0
# The anchor surface is fitted to cells within this many metres of any of the
# pif's pips or feet.
FIT_RADIUS_M = 20.0
# The cells a walk passes over are grown by this many metres before they are
# left out of the fits.
FACE_BUFFER_M = 1.0
# Bisquare reweighting passes after the first fit, stopping early once no
# coefficient moves by more than ROBUST_TOL_M.
ROBUST_ITERATIONS = 10
ROBUST_TOL_M = 1e-3
# Tukey's bisquare tuning constant (95% efficiency under normal errors), and
# the factor from a median absolute deviation to a standard deviation.
BISQUARE_C = 4.685
MAD_TO_SD = 1.4826
# A fit needs this many cells: five for each of its six coefficients.
MIN_FIT_CELLS = 30
# No more excess drop than this, in metres, is natural ground.
EXCESS_DROP_M = 1.0
# An excess drop within this many robust standard deviations of the fit's
# residuals is uncertain.
SCALE_K = 2.0
# Beyond this position either way a pif is a cut or a fill.
POSITION_SPLIT = 1.0 / 3.0

QUADRATIC_TERMS = ("a", "b", "c", "d", "e", "f")
_N_TERMS = len(QUADRATIC_TERMS)


@dataclass(frozen=True)
class FaceWalk:
    """The feet of the faces below a set of pips.

    Attributes:
        rows: The row of each pip's foot.
        cols: The column of each pip's foot.
        face: True on every cell a walk passed over, pips and feet included.
    """

    rows: NDArray[np.intp]
    cols: NDArray[np.intp]
    face: NDArray[np.bool_]


def face_feet(
    dem: NDArray[np.floating],
    rows: NDArray[np.integer],
    cols: NDArray[np.integer],
    direction: NDArray[np.integer],
    cell_size_m: float,
) -> FaceWalk:
    """Walk each pip down its own fall direction to the foot of its face.

    A walk moves a cell at a time while each step falls at least
    :data:`FOOT_SLOPE_DEG`, so it stops on the first flatter ground (a
    platform, a road, the natural slope below a batter), at no data or after
    :data:`FOOT_MAX_M`.

    Args:
        dem: Ground elevation in metres, NaN for no data.
        rows: The row of each pip.
        cols: The column of each pip.
        direction: Each pip's fall direction, an index into
            :data:`~landloss.hazard.landslide.instability_zones.DIRECTIONS`.
        cell_size_m: The cell size.

    Returns:
        The feet and the cells the walks passed over.
    """
    steps = np.asarray(DIRECTIONS)[np.asarray(direction)]
    step_m = cell_size_m * np.hypot(steps[:, 0], steps[:, 1])
    need = math.tan(math.radians(FOOT_SLOPE_DEG)) * step_m
    height, width = dem.shape
    r = np.asarray(rows, dtype=np.intp).copy()
    c = np.asarray(cols, dtype=np.intp).copy()
    z = dem[r, c]
    travelled = np.zeros(len(r))
    face = np.zeros(dem.shape, dtype=bool)
    face[r, c] = True
    # Only the walks still going are carried from one step to the next.
    live = np.arange(len(r))
    while live.size:
        nr = r[live] + steps[live, 0]
        nc = c[live] + steps[live, 1]
        inside = (nr >= 0) & (nr < height) & (nc >= 0) & (nc < width)
        nz = np.full(live.size, np.nan)
        nz[inside] = dem[nr[inside], nc[inside]]
        with np.errstate(invalid="ignore"):
            go = (
                inside
                & (z[live] - nz >= need[live])
                & (travelled[live] + step_m[live] <= FOOT_MAX_M)
            )
        live = live[go]
        r[live], c[live], z[live] = nr[go], nc[go], nz[go]
        travelled[live] += step_m[live]
        face[r[live], c[live]] = True
    return FaceWalk(rows=r, cols=c, face=face)


def face_mask(face: NDArray[np.bool_], cell_size_m: float) -> NDArray[np.bool_]:
    """The face cells grown by :data:`FACE_BUFFER_M`: the ground the fits skip.

    Args:
        face: True on the cells the walks passed over (:func:`face_feet`).
        cell_size_m: The cell size.

    Returns:
        The grown mask.
    """
    cells = max(round(FACE_BUFFER_M / cell_size_m), 0)
    if cells == 0:
        return face
    structure = np.ones((2 * cells + 1, 2 * cells + 1), dtype=bool)
    return ndimage.binary_dilation(face, structure=structure)


def _median(values: NDArray[np.floating]) -> float:
    """The median of a 1-D array with no NaN, without ``np.median``'s overhead."""
    n = values.size
    half = n // 2
    if n % 2:
        return float(np.partition(values, half)[half])
    part = np.partition(values, (half - 1, half))
    return float(0.5 * (part[half - 1] + part[half]))


def _robust_scale(residual: NDArray[np.floating]) -> float:
    """The robust standard deviation of residuals: 1.4826 times their MAD."""
    return MAD_TO_SD * _median(np.abs(residual - _median(residual)))


def _weighted_fit(
    design: NDArray[np.floating],
    z: NDArray[np.floating],
    weights: NDArray[np.floating] | None,
) -> NDArray[np.floating]:
    """Least squares through the 6 by 6 normal equations, optionally weighted."""
    weighted = design.T if weights is None else design.T * weights
    try:
        return np.linalg.solve(weighted @ design, weighted @ z)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(design, z, rcond=None)[0]


def fit_quadratic(
    dem: NDArray[np.floating],
    transform: Affine,
    rows: NDArray[np.integer],
    cols: NDArray[np.integer],
    *,
    radius_m: float,
    exclude: NDArray[np.bool_] | None = None,
    robust_iterations: int = 0,
) -> tuple[NDArray[np.floating] | None, tuple[float, float], float]:
    """Fit a quadratic surface to the DEM around some cells.

    Every valid cell closer than ``radius_m`` to any of the given cells, and not in
    ``exclude``, is fitted with ``z = a + b u + c v + d u^2 + e u v + f v^2`` in
    coordinates ``u, v`` centred on the given cells' mean and scaled by
    ``radius_m``. With ``robust_iterations`` the fit is reweighted up to that
    many times by Tukey's bisquare on the robust scale of its residuals.

    Args:
        dem: Ground elevation in metres, NaN for no data.
        transform: The DEM's affine transform; its cells are square.
        rows: The rows of the cells the surface is fitted around.
        cols: Their columns.
        radius_m: Cells this close to any of them are fitted.
        exclude: Optionally, cells never fitted.
        robust_iterations: The most bisquare passes after the first fit.

    Returns:
        ``(coefficients, centre, scale)``: the six coefficients, the ``(x, y)``
        centre and the robust standard deviation of the fitted cells'
        residuals, or ``(None, centre, nan)`` where fewer than
        :data:`MIN_FIT_CELLS` cells were found.
    """
    cell = transform.a
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    reach = math.ceil(radius_m / cell)
    r0, c0 = max(int(rows.min()) - reach, 0), max(int(cols.min()) - reach, 0)
    r1 = min(int(rows.max()) + reach + 1, dem.shape[0])
    c1 = min(int(cols.max()) + reach + 1, dem.shape[1])
    centre_col = cols.mean() + 0.5
    centre_row = rows.mean() + 0.5
    centre = (
        transform.c + centre_col * cell,
        transform.f - centre_row * cell,
    )

    # Distance from every window cell to the nearest given cell, in metres.
    seeds = np.ones((r1 - r0, c1 - c0), dtype=bool)
    seeds[rows - r0, cols - c0] = False
    distance = ndimage.distance_transform_edt(seeds, sampling=cell)
    window = dem[r0:r1, c0:c1]
    keep = (distance < radius_m) & np.isfinite(window)
    if exclude is not None:
        keep &= ~exclude[r0:r1, c0:c1]
    kr, kc = np.nonzero(keep)
    if kr.size < MIN_FIT_CELLS:
        return None, centre, math.nan
    u = ((kc + c0 + 0.5) - centre_col) * cell / radius_m
    v = (centre_row - (kr + r0 + 0.5)) * cell / radius_m
    z = window[kr, kc]
    design = np.column_stack([np.ones_like(u), u, v, u * u, u * v, v * v])
    coefficients = _weighted_fit(design, z, None)
    for _ in range(robust_iterations):
        residual = z - design @ coefficients
        scale = _robust_scale(residual)
        if scale <= 0:
            break
        x = residual / (BISQUARE_C * scale)
        weights = np.where(np.abs(x) < 1, (1 - x * x) ** 2, 0.0)
        updated = _weighted_fit(design, z, weights)
        settled = np.max(np.abs(updated - coefficients)) < ROBUST_TOL_M
        coefficients = updated
        if settled:
            break
    scale = _robust_scale(z - design @ coefficients)
    return coefficients, centre, scale


def eval_quadratic(
    coefficients: NDArray[np.floating] | pd.Series,
    centre: tuple[float, float],
    radius_m: float,
    x: NDArray[np.floating] | pd.Series,
    y: NDArray[np.floating] | pd.Series,
) -> NDArray[np.floating]:
    """Evaluate a fitted quadratic (:func:`fit_quadratic`) at points.

    Args:
        coefficients: The six coefficients.
        centre: The fit's ``(x, y)`` centre.
        radius_m: The fit's radius, which scales its coordinates.
        x: The points' eastings.
        y: Their northings.

    Returns:
        The surface's elevation at each point.
    """
    a, b, c, d, e, f = np.asarray(coefficients, dtype=float)
    u = (np.asarray(x, dtype=float) - centre[0]) / radius_m
    v = (np.asarray(y, dtype=float) - centre[1]) / radius_m
    return a + b * u + c * v + d * u * u + e * u * v + f * v * v


def classify(
    crest_residual: NDArray[np.floating],
    foot_residual: NDArray[np.floating],
    *,
    uncertain_m: NDArray[np.floating] | None = None,
) -> tuple[NDArray[np.floating], NDArray[np.floating], NDArray[np.object_]]:
    """Class each pif from its crest and foot residuals.

    Args:
        crest_residual: The crest's median residual against the surface, m.
        foot_residual: The foot's median residual, m.
        uncertain_m: Optionally, one number per pif: an excess drop above
            :data:`EXCESS_DROP_M` but no more than this is within the
            surface's own scatter, and ``uncertain`` rather than cut or fill.

    Returns:
        ``(excess_drop, position, classes)``; the class is ``unknown`` where
        there was no surface to compare against.
    """
    crest_residual = np.asarray(crest_residual, dtype=float)
    foot_residual = np.asarray(foot_residual, dtype=float)
    excess = crest_residual - foot_residual
    with np.errstate(invalid="ignore", divide="ignore"):
        position = np.where(
            excess > 0, (crest_residual + foot_residual) / excess, np.nan
        )
        classes = np.full(len(excess), CUT_AND_FILL, dtype=object)
        classes[position > POSITION_SPLIT] = FILL
        classes[position < -POSITION_SPLIT] = CUT
        if uncertain_m is not None:
            classes[~(excess > np.asarray(uncertain_m, dtype=float))] = UNCERTAIN
        classes[~(excess > EXCESS_DROP_M)] = NATURAL
    classes[np.isnan(excess)] = UNKNOWN
    return excess, position, classes


@dataclass(frozen=True)
class PifCutFill:
    """The class of every pif and the walk of every pip.

    Attributes:
        pifs: One row per pif, indexed by ``pif_id``: ``n_pips``,
            ``face_drop_m`` (the median drop from pip to foot), the anchor
            surface (``surface_a`` to ``surface_f``, ``surface_centre_x``,
            ``surface_centre_y``, ``surface_radius_m``) and its residual scale
            ``surface_scale_m``, ``crest_residual_m``, ``foot_residual_m``,
            ``excess_drop_m``, ``uncertain_below_m``, ``position`` and
            ``cut_fill_class`` (one of :data:`CLASSES`).
        pips: One row per pip: ``pif_id``, its ``x``, ``y`` and ``z``, its
            foot's ``foot_x``, ``foot_y`` and ``foot_z``, and the surface at
            both, ``crest_surface_z`` and ``foot_surface_z``.
    """

    pifs: pd.DataFrame
    pips: pd.DataFrame


def gen_pif_cut_fill(
    dem: NDArray[np.floating],
    transform: Affine,
    pif_ids: NDArray[np.integer],
    rows: NDArray[np.integer],
    cols: NDArray[np.integer],
    direction: NDArray[np.integer],
) -> PifCutFill:
    """Class every pif as cut, fill, cut and fill, uncertain or natural.

    Args:
        dem: The 1 m DEM the pips were found on, NaN for no data.
        transform: Its affine transform; its cells are square.
        pif_ids: The pif of each pip.
        rows: The row of each pip.
        cols: Its column.
        direction: Its fall direction (``Pips.direction`` at the pip).

    Returns:
        The class of every pif and the walk of every pip.
    """
    cell = transform.a
    pif_ids = np.asarray(pif_ids)
    rows = np.asarray(rows, dtype=np.intp)
    cols = np.asarray(cols, dtype=np.intp)
    walk = face_feet(dem, rows, cols, direction, cell)
    skip = face_mask(walk.face, cell)

    order = np.argsort(pif_ids, kind="stable")
    ids, starts = np.unique(pif_ids[order], return_index=True)
    ends = np.append(starts[1:], order.size)
    crest_surface = np.full(rows.size, np.nan)
    foot_surface = np.full(rows.size, np.nan)
    fits = np.full((ids.size, _N_TERMS + 3), np.nan)
    x = transform.c + (cols + 0.5) * cell
    y = transform.f - (rows + 0.5) * cell
    foot_x = transform.c + (walk.cols + 0.5) * cell
    foot_y = transform.f - (walk.rows + 0.5) * cell
    for k, (start, end) in enumerate(zip(starts, ends, strict=True)):
        at = order[start:end]
        coefficients, centre, scale = fit_quadratic(
            dem,
            transform,
            np.concatenate([rows[at], walk.rows[at]]),
            np.concatenate([cols[at], walk.cols[at]]),
            radius_m=FIT_RADIUS_M,
            exclude=skip,
            robust_iterations=ROBUST_ITERATIONS,
        )
        if coefficients is None:
            continue
        crest_surface[at] = eval_quadratic(
            coefficients, centre, FIT_RADIUS_M, x[at], y[at]
        )
        foot_surface[at] = eval_quadratic(
            coefficients, centre, FIT_RADIUS_M, foot_x[at], foot_y[at]
        )
        fits[k] = [*coefficients, *centre, scale]

    pips = pd.DataFrame(
        {
            "pif_id": pif_ids,
            "x": x,
            "y": y,
            "z": dem[rows, cols],
            "foot_x": foot_x,
            "foot_y": foot_y,
            "foot_z": dem[walk.rows, walk.cols],
            "crest_surface_z": crest_surface,
            "foot_surface_z": foot_surface,
        }
    )
    per_pip = pd.DataFrame(
        {
            "drop": pips.z - pips.foot_z,
            "crest": pips.z - pips.crest_surface_z,
            "foot": pips.foot_z - pips.foot_surface_z,
        }
    ).groupby(pips.pif_id)
    medians = per_pip.median()
    pifs = pd.DataFrame(index=pd.Index(ids, name="pif_id"))
    pifs["n_pips"] = per_pip.size()
    pifs["face_drop_m"] = medians["drop"]
    columns = [f"surface_{term}" for term in QUADRATIC_TERMS]
    columns += ["surface_centre_x", "surface_centre_y", "surface_scale_m"]
    pifs[columns] = fits
    pifs["surface_radius_m"] = FIT_RADIUS_M
    pifs["crest_residual_m"] = medians["crest"]
    pifs["foot_residual_m"] = medians["foot"]
    uncertain = SCALE_K * pifs["surface_scale_m"].to_numpy()
    excess, position, classes = classify(
        pifs["crest_residual_m"].to_numpy(),
        pifs["foot_residual_m"].to_numpy(),
        uncertain_m=uncertain,
    )
    pifs["excess_drop_m"] = excess
    pifs["uncertain_below_m"] = uncertain
    pifs["position"] = position
    pifs["cut_fill_class"] = classes
    return PifCutFill(pifs=pifs, pips=pips)
