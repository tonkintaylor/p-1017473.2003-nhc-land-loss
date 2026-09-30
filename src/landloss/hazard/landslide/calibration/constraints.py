"""The extent and amount constraints applied to every large-landslide model.

Three operations, used in this order by each large model
(``.agents/plans/building-hancox-landslide-model-and-calibration.md``, phase
3):

1. :func:`fit_transfer_function` turns a relative hazard (models 2 and 7,
   which rank cells rather than predict coverage) into areal coverage, fitted
   on an observed inventory by binning, as Nowicki Jessee et al. (2018) did for
   their equation 9.
2. :func:`extent_mask` removes cells where Hancox et al. (1997) say no
   landsliding of the given size occurs: beyond the maximum epicentral
   distance for the magnitude, or below the intensity threshold.
3. :func:`scale_to_total` scales what remains so the total landslide area
   matches a target, from Marc et al. (2016) or from an inventory.

:func:`calibrate` runs steps 2 and 3 and reports what each changed.

Hancox's area affected is **not** used as a mask. The areas are irregular and
asymmetric about the epicentre (Hancox et al. 1997, section 3.3), and for a
long rupture such as Kaikōura, whose epicentre is at one end, a circle of that
area around the epicentre would clip landsliding that occurred. It is reported
instead, against the area over which the model predicts any landsliding.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from landloss.hazard.landslide.models.hancox_1997 import relationships as hancox


def scale_to_total(
    coverage: npt.ArrayLike,
    cell_area_km2: npt.ArrayLike,
    target_km2: float,
    max_coverage: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Scale a coverage grid so its total landslide area equals a target.

    Coverage is multiplied by one factor everywhere and capped at
    ``max_coverage`` per cell, so the pattern is preserved except where the cap
    binds. With the cap the total is not linear in the factor, so the factor is
    found by bisection.

    Args:
        coverage: Areal coverage per cell, 0 to 1. NaN cells are left NaN.
        cell_area_km2: Cell area in km², scalar or shaped like ``coverage``.
        target_km2: The total landslide area to reach, km².
        max_coverage: The largest coverage a cell may take.

    Returns:
        A tuple of the scaled coverage and the factor applied.

    Raises:
        ValueError: If the target is negative, or larger than the area the
            capped cells can hold.
    """
    coverage = np.asarray(coverage, dtype=float)
    area = np.broadcast_to(np.asarray(cell_area_km2, dtype=float), coverage.shape)
    valid = np.isfinite(coverage) & (coverage > 0)
    capacity = float((max_coverage * area[valid]).sum())
    if target_km2 < 0 or target_km2 > capacity:
        msg = (
            f"target_km2 = {target_km2} cannot be reached: the cells with any "
            f"coverage can hold at most {capacity:.4g} km²"
        )
        raise ValueError(msg)
    c, a = coverage[valid], area[valid]

    def total(k: float) -> float:
        return float((np.minimum(k * c, max_coverage) * a).sum())

    if target_km2 == 0:
        k = 0.0
    else:
        lo, hi = 0.0, target_km2 / float((c * a).sum())
        while total(hi) < target_km2:
            hi *= 2.0
        for _ in range(200):
            k = 0.5 * (lo + hi)
            if total(k) < target_km2:
                lo = k
            else:
                hi = k
            if hi - lo <= 1e-12 * hi:
                break
        k = hi
    scaled = coverage.copy()
    scaled[valid] = np.minimum(k * c, max_coverage)
    return scaled, k


def extent_mask(
    epicentral_distance_km: npt.ArrayLike,
    mw: float,
    mm: npt.ArrayLike | None = None,
    *,
    size_class: str = "small",
    mm_threshold: float = hancox.MM_THRESHOLD_WELLINGTON,
) -> np.ndarray:
    """Cells where Hancox et al. (1997) allow landsliding of a given size.

    Args:
        epicentral_distance_km: Distance of each cell from the epicentre, km.
            Epicentral, because that is what the relationships are fitted on.
        mw: The earthquake's magnitude.
        mm: MM intensity per cell, shaped like the distances, or None to skip
            the intensity threshold.
        size_class: The Hancox size class, one of
            :data:`~landloss.hazard.landslide.models.hancox_1997.relationships.SIZE_CLASSES`.
            The default, the smallest, gives the widest extent.
        mm_threshold: The intensity below which there is no landsliding: MM7
            in the Wellington Region, MM6 elsewhere in New Zealand.

    Returns:
        A boolean array, true where landsliding is allowed.
    """
    distance = np.asarray(epicentral_distance_km, dtype=float)
    keep = distance <= hancox.max_distance_km(mw, size_class)
    if mm is not None:
        keep &= np.asarray(mm, dtype=float) >= mm_threshold
    return keep


def _pool_adjacent_violators(y: npt.ArrayLike, w: npt.ArrayLike) -> np.ndarray:
    """The weighted least-squares non-decreasing fit to ``y`` (isotonic)."""
    blocks = []  # [mean, weight, count]
    for yi, wi in zip(y, w, strict=True):
        blocks.append([yi, wi, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            m2, w2, n2 = blocks.pop()
            m1, w1, n1 = blocks.pop()
            wt = w1 + w2
            blocks.append([(m1 * w1 + m2 * w2) / wt, wt, n1 + n2])
    return np.concatenate([np.full(n, m) for m, _, n in blocks])


@dataclass(frozen=True)
class TransferFunction:
    """A monotone map from relative hazard to areal coverage.

    Attributes:
        hazard: The mean relative hazard of each bin, increasing.
        coverage: The fitted coverage of each bin, non-decreasing.
    """

    hazard: np.ndarray
    coverage: np.ndarray

    def __call__(self, relative_hazard: npt.ArrayLike) -> np.ndarray:
        """Coverage at each hazard value, linear between bins, flat beyond them."""
        return np.interp(
            np.asarray(relative_hazard, dtype=float), self.hazard, self.coverage
        )


def fit_transfer_function(
    relative_hazard: npt.ArrayLike, observed_coverage: npt.ArrayLike, n_bins: int = 20
) -> TransferFunction:
    """Fit a monotone map from a relative hazard to observed areal coverage.

    Cells are binned by quantile of hazard; in each bin the observed coverage
    is averaged, and the bin means are made non-decreasing by pooling adjacent
    violators, weighted by the number of cells in each bin.

    Args:
        relative_hazard: The model's relative hazard per cell. NaN is ignored.
        observed_coverage: The observed coverage per cell, 0 to 1, from an
            inventory, same shape. NaN is ignored.
        n_bins: The number of quantile bins.

    Returns:
        The fitted :class:`TransferFunction`.
    """
    x = np.asarray(relative_hazard, dtype=float).ravel()
    y = np.asarray(observed_coverage, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    edges = np.unique(np.quantile(x, np.linspace(0, 1, n_bins + 1)))
    idx = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, len(edges) - 2)
    counts = np.bincount(idx, minlength=len(edges) - 1)
    present = counts > 0
    mean_x = np.bincount(idx, weights=x, minlength=len(edges) - 1)[present]
    mean_y = np.bincount(idx, weights=y, minlength=len(edges) - 1)[present]
    n = counts[present]
    mean_x, mean_y = mean_x / n, mean_y / n
    return TransferFunction(
        hazard=mean_x, coverage=_pool_adjacent_violators(mean_y, n.astype(float))
    )


@dataclass(frozen=True)
class CalibrationReport:
    """What each constraint changed.

    Attributes:
        total_before_km2: Landslide area as the model predicted it.
        removed_by_extent_km2: Landslide area in cells the extent mask removed.
        total_after_km2: Landslide area after masking and scaling.
        scale_factor: The factor :func:`scale_to_total` applied.
        footprint_km2: Area of the cells left with any landsliding, to set
            against Hancox's area affected.
        area_affected_km2: Hancox's area affected for the magnitude, as
            (lower, mean, upper) at one standard error.
    """

    total_before_km2: float
    removed_by_extent_km2: float
    total_after_km2: float
    scale_factor: float
    footprint_km2: float
    area_affected_km2: tuple[float, float, float]


def calibrate(
    coverage: npt.ArrayLike,
    cell_area_km2: npt.ArrayLike,
    keep: npt.ArrayLike,
    mw: float,
    target_km2: float,
    max_coverage: float = 1.0,
) -> tuple[np.ndarray, CalibrationReport]:
    """Apply an extent mask, then scale to a target total, and report both.

    Args:
        coverage: Areal coverage per cell, 0 to 1.
        cell_area_km2: Cell area in km², scalar or shaped like ``coverage``.
        keep: The boolean mask from :func:`extent_mask`.
        mw: The earthquake's magnitude, for the area-affected comparison.
        target_km2: The total landslide area to reach, km².
        max_coverage: The largest coverage a cell may take.

    Returns:
        A tuple of the calibrated coverage and a :class:`CalibrationReport`.
    """
    coverage = np.asarray(coverage, dtype=float)
    area = np.broadcast_to(np.asarray(cell_area_km2, dtype=float), coverage.shape)
    landslide_area = np.where(np.isfinite(coverage), coverage * area, 0.0)
    keep = np.asarray(keep, dtype=bool)
    masked = np.where(keep, coverage, np.where(np.isfinite(coverage), 0.0, np.nan))
    scaled, factor = scale_to_total(masked, area, target_km2, max_coverage)
    report = CalibrationReport(
        total_before_km2=float(landslide_area.sum()),
        removed_by_extent_km2=float(landslide_area[~keep].sum()),
        total_after_km2=float(np.nansum(scaled * area)),
        scale_factor=factor,
        footprint_km2=float(area[np.nan_to_num(scaled) > 0].sum()),
        area_affected_km2=tuple(
            float(hancox.area_affected_km2(mw, n_se=s)) for s in (-1, 0, 1)
        ),
    )
    return scaled, report
