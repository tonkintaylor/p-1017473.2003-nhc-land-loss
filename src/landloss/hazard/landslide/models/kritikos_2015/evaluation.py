"""Score a Kritikos hazard map and turn its relative hazard into coverage.

Two things the paper does and one it leaves out:

- :func:`success_rate_curve` and :func:`success_rate_auc` score a map against a
  landslide inventory the way the paper does (section 4.2): cells are ranked
  from highest hazard to lowest, and the share of landslides in the top share of
  the area is accumulated. The area under that curve is the AUC, and the paper
  treats 0.7 and above as good [kritikos_2015].
- :func:`fit_transfer_function` supplies what the paper leaves out. The hazard
  is relative, so an amount of landsliding needs one map from hazard to areal
  coverage. It is fitted on the model's own training events, not on the events
  the portfolio is tested against, so that model 2 stays an independent
  estimate (plan, phase 6).
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

# The number of equal-count hazard bins the transfer function is fitted over.
DEFAULT_N_BINS = 20


def success_rate_curve(
    hazard: npt.ArrayLike, landslides: npt.ArrayLike
) -> tuple[np.ndarray, np.ndarray]:
    """Return the success-rate curve of a hazard map against an inventory.

    Cells are taken from highest hazard to lowest. Cells with the same hazard
    are taken together, so their landslides are spread evenly over them rather
    than credited by the arbitrary order they happen to be stored in.

    Args:
        hazard: Hazard per cell. Cells where it is NaN are outside the study
            area and are left out.
        landslides: Landslides per cell, in any consistent unit (a count of
            landslide points, or landslide area), same shape as ``hazard``.

    Returns:
        The cumulative share of the study area and the cumulative share of the
        landslides taken with it, both from 0 to 1 and starting at (0, 0).

    Raises:
        ValueError: If the shapes differ, there are no valid cells, or there are
            no landslides in them.
    """
    h = np.asarray(hazard, dtype=float).ravel()
    n = np.asarray(landslides, dtype=float).ravel()
    if h.shape != n.shape:
        msg = "hazard and landslides must have the same shape"
        raise ValueError(msg)

    valid = np.isfinite(h)
    h, n = h[valid], n[valid]
    if h.size == 0 or n.sum() <= 0:
        msg = "need at least one valid cell and one landslide to score a map"
        raise ValueError(msg)

    levels, inverse = np.unique(-h, return_inverse=True)
    cells = np.bincount(inverse, minlength=levels.size)
    hits = np.bincount(inverse, weights=n, minlength=levels.size)
    area = np.concatenate([[0.0], np.cumsum(cells) / cells.sum()])
    found = np.concatenate([[0.0], np.cumsum(hits) / hits.sum()])
    return area, found


def success_rate_auc(hazard: npt.ArrayLike, landslides: npt.ArrayLike) -> float:
    """Return the area under the success-rate curve.

    Args:
        hazard: Hazard per cell, NaN outside the study area.
        landslides: Landslides per cell, same shape as ``hazard``.

    Returns:
        The AUC, 0.5 for a map no better than chance and 1 for a perfect one.
    """
    area, found = success_rate_curve(hazard, landslides)
    return float(np.sum(np.diff(area) * (found[1:] + found[:-1]) / 2.0))


@dataclass(frozen=True)
class TransferFunction:
    """A monotone map from relative hazard to areal landslide coverage."""

    hazard: np.ndarray
    coverage: np.ndarray

    def __call__(self, hazard: npt.ArrayLike) -> np.ndarray:
        """Return the coverage at a hazard, flat beyond the fitted range."""
        return np.interp(np.asarray(hazard, dtype=float), self.hazard, self.coverage)


def _pool_adjacent_violators(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return the weighted non-decreasing least-squares fit to ``values``."""
    blocks: list[list[float]] = []  # each is [mean, weight, count]
    for value, weight in zip(values, weights, strict=True):
        blocks.append([value, weight, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            mean, weight_b, count_b = blocks.pop()
            mean_a, weight_a, count_a = blocks.pop()
            total = weight_a + weight_b
            blocks.append(
                [
                    (mean_a * weight_a + mean * weight_b) / total,
                    total,
                    count_a + count_b,
                ]
            )
    return np.concatenate([np.full(int(b[2]), b[0]) for b in blocks])


def fit_transfer_function(
    hazard: npt.ArrayLike,
    coverage: npt.ArrayLike,
    *,
    n_bins: int = DEFAULT_N_BINS,
) -> TransferFunction:
    """Fit a monotone hazard-to-coverage curve to an inventory.

    Cells are binned by hazard into bins of equal count, the observed coverage
    of each bin is the mean over its cells, and a non-decreasing curve is fitted
    through the bin means by pooling adjacent violators, weighted by the cells in
    each bin. Pool several events by concatenating their cells; fit each alone
    to report the spread between events.

    Args:
        hazard: Relative hazard per cell. Cells where it is NaN are left out.
        coverage: Observed fraction of each cell covered by landslide source
            area, same shape as ``hazard``.
        n_bins: The number of equal-count bins.

    Returns:
        The fitted :class:`TransferFunction`, at the mean hazard of each bin.

    Raises:
        ValueError: If the shapes differ, ``n_bins`` is under 2, or there are
            fewer valid cells than bins.
    """
    h = np.asarray(hazard, dtype=float).ravel()
    c = np.asarray(coverage, dtype=float).ravel()
    if h.shape != c.shape:
        msg = "hazard and coverage must have the same shape"
        raise ValueError(msg)
    valid = np.isfinite(h) & np.isfinite(c)
    h, c = h[valid], c[valid]
    if n_bins < 2 or h.size < n_bins:
        msg = f"need at least {max(n_bins, 2)} valid cells for {n_bins} bins"
        raise ValueError(msg)

    order = np.argsort(h, kind="stable")
    h, c = h[order], c[order]
    bins = np.array_split(np.arange(h.size), n_bins)
    bin_h = np.array([h[b].mean() for b in bins])
    bin_c = np.array([c[b].mean() for b in bins])
    bin_n = np.array([b.size for b in bins], dtype=float)

    # Bins of tied hazard share one x; keep one point per distinct hazard so the
    # curve can be interpolated.
    keep = np.concatenate([[True], np.diff(bin_h) > 0])
    fitted = _pool_adjacent_violators(bin_c, bin_n)
    return TransferFunction(hazard=bin_h[keep], coverage=fitted[keep])
