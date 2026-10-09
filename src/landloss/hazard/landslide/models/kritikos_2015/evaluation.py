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

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from landloss.io import ASSETS_DIR

# The number of equal-weight hazard bins the transfer function is fitted over.
DEFAULT_N_BINS = 20

# The fitted curve, written by landslide step 8's
# ``gen_kritikos_2015_transfer_function.py`` and read by its hazard script.
TRANSFER_FUNCTION_PATH = ASSETS_DIR / "kritikos-2015-transfer-function.csv"

# The columns of that file after ``hazard`` and ``coverage``: the settings the
# hazard was built with when the curve was fitted, repeated on every row. A
# curve is only meaningful for a hazard built the same way.
SETTINGS_COLUMNS = ("gamma", "tpi_window_m", "fault_term")


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
    """A monotone map from relative hazard to areal landslide coverage.

    ``settings`` records how the hazard was built when the curve was fitted
    (see :data:`SETTINGS_COLUMNS`); it is empty for a curve fitted in memory.
    """

    hazard: np.ndarray
    coverage: np.ndarray
    settings: dict = field(default_factory=dict)

    def __call__(self, hazard: npt.ArrayLike) -> np.ndarray:
        """Return the coverage at a hazard, flat beyond the fitted range."""
        return np.interp(np.asarray(hazard, dtype=float), self.hazard, self.coverage)

    def to_frame(self) -> pd.DataFrame:
        """Return the curve as the table :func:`get_transfer_function` reads."""
        table = pd.DataFrame({"hazard": self.hazard, "coverage": self.coverage})
        for name in SETTINGS_COLUMNS:
            table[name] = self.settings[name]
        return table


def get_transfer_function(path: Path = TRANSFER_FUNCTION_PATH) -> TransferFunction:
    """Read the fitted hazard-to-coverage curve.

    Args:
        path: The curve's CSV, with ``hazard``, ``coverage`` and the
            :data:`SETTINGS_COLUMNS`.

    Returns:
        The curve, carrying the settings it was fitted with.
    """
    table = pd.read_csv(path)
    settings = {name: table[name].iloc[0] for name in SETTINGS_COLUMNS}
    settings["gamma"] = float(settings["gamma"])
    settings["tpi_window_m"] = float(settings["tpi_window_m"])
    settings["fault_term"] = str(settings["fault_term"])
    return TransferFunction(
        hazard=table["hazard"].to_numpy(float),
        coverage=table["coverage"].to_numpy(float),
        settings=settings,
    )


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
    weights: npt.ArrayLike | None = None,
) -> TransferFunction:
    """Fit a monotone hazard-to-coverage curve to an inventory.

    Cells are binned by hazard into bins of equal weight (equal count when
    ``weights`` is not given), the observed coverage of each bin is the weighted
    mean over its cells, and a non-decreasing curve is fitted through the bin
    means by pooling adjacent violators, weighted by each bin's weight. Pool
    several events by concatenating their cells, weighting each cell by one over
    its event's cell count so that each event counts equally however large its
    study area; fit each alone to report the spread between events.

    Args:
        hazard: Relative hazard per cell. Cells where it is NaN are left out.
        coverage: Observed fraction of each cell covered by landslide source
            area, same shape as ``hazard``.
        n_bins: The number of bins.
        weights: Weight of each cell, same shape as ``hazard``, or None for
            equal weights.

    Returns:
        The fitted :class:`TransferFunction`, at the weighted mean hazard of
        each bin.

    Raises:
        ValueError: If the shapes differ, ``n_bins`` is under 2, or there are
            fewer valid cells than bins.
    """
    h = np.asarray(hazard, dtype=float).ravel()
    c = np.asarray(coverage, dtype=float).ravel()
    w = np.ones_like(h) if weights is None else np.asarray(weights, dtype=float).ravel()
    if not h.shape == c.shape == w.shape:
        msg = "hazard, coverage and weights must have the same shape"
        raise ValueError(msg)
    valid = np.isfinite(h) & np.isfinite(c) & (w > 0)
    h, c, w = h[valid], c[valid], w[valid]
    if n_bins < 2 or h.size < n_bins:
        msg = f"need at least {max(n_bins, 2)} valid cells for {n_bins} bins"
        raise ValueError(msg)

    order = np.argsort(h, kind="stable")
    h, c, w = h[order], c[order], w[order]
    # Each cell goes to the bin its mid-point of cumulative weight falls in.
    share = (np.cumsum(w) - w / 2.0) / w.sum()
    bin_of = np.minimum((share * n_bins).astype(int), n_bins - 1)
    bins = [np.flatnonzero(bin_of == k) for k in range(n_bins)]
    bins = [b for b in bins if b.size]
    bin_w = np.array([w[b].sum() for b in bins])
    bin_h = np.array([np.average(h[b], weights=w[b]) for b in bins])
    bin_c = np.array([np.average(c[b], weights=w[b]) for b in bins])

    # Bins of tied hazard share one x; keep one point per distinct hazard so the
    # curve can be interpolated.
    keep = np.concatenate([[True], np.diff(bin_h) > 0])
    fitted = _pool_adjacent_violators(bin_c, bin_w)
    return TransferFunction(hazard=bin_h[keep], coverage=fitted[keep])
