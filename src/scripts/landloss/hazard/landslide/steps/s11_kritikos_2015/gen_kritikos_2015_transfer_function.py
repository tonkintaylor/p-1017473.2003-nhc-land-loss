r"""Fit the Kritikos hazard-to-coverage transfer function on Northridge and Wenchuan.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s11_kritikos_2015/gen_kritikos_2015_transfer_function.py

Kritikos et al. (2015) [kritikos_2015] give a relative hazard and no amount, so
one map from hazard to areal landslide coverage is fitted on the model's own
training events, not on Kaikoura, which keeps model 2 an independent estimate
(plan phase 6). For each event the relative hazard is built exactly as the
Wellington run builds it (``config.py``), over the inventory's bounding box, and
the observed coverage of each cell is the fraction of it inside landslide
polygons (Northridge) or the inventory's mean landslide area times the points
in it (Wenchuan, whose points carry no area). A monotone curve is fitted to each
event alone for the spread, and to the two pooled with the events weighted
equally for the curve the Wellington run uses.

The inputs are the stand-ins described in
``validations/kritikos_2015/event_inputs.py``: Copernicus 30 m for the paper's
60 m DEMs and the GEM fault database for each region's mapped faults.

Writes the pooled curve to ``landloss.io.ASSETS_DIR`` (tracked, read by
``gen_kritikos_2015_hazard.py``) and a table of the three curves to the report
folder's ``hazard/landslide/kritikos-2015-validation/tab``.
"""

import sys

import numpy as np
import pandas as pd

from landloss.hazard.landslide.models.kritikos_2015 import evaluation, model
from scripts.landloss.hazard.landslide.steps.s11_kritikos_2015 import config
from scripts.landloss.hazard.landslide.validations.kritikos_2015 import event_inputs
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TAB_DIR = REPORT_DIR / "hazard" / "landslide" / "kritikos-2015-validation" / "tab"
TAB_NAME = "kritikos_2015_transfer_function.csv"
RULE = "-" * 72

# Coverage under this is treated as none when comparing the events' curves, so
# that a ratio of two near-zero numbers is not read as a disagreement.
MIN_COMPARED_COVERAGE = 1e-4


def gen_study_area_cells(layers, *, gamma, tpi_window_m, fault_term, margin_m):
    """Return the hazard and observed coverage of every cell in the study area.

    Args:
        layers: One event's layers from ``event_inputs.build_event_layers``.
        gamma: The fuzzy gamma.
        tpi_window_m: The TPI window the layers were built with.
        fault_term: "mapped" or "far_field", as in ``config.py``.
        margin_m: How far the study area extends beyond the inventory's
            bounding box.

    Returns:
        The hazard and the coverage of the cells with a hazard, as 1D arrays.
    """
    fault_km = layers["fault_km"]
    if fault_term == "far_field":
        fault_km = np.where(np.isfinite(fault_km), np.inf, np.nan)
    elif fault_term != "mapped":
        msg = f"fault_term must be 'mapped' or 'far_field', not {fault_term!r}"
        raise ValueError(msg)
    result = model.run(
        mm=layers["mm"],
        slope_deg=layers["slope"],
        fault_distance_km=fault_km,
        slope_position=layers["position"][tpi_window_m],
        gamma=gamma,
    )
    minx, miny, maxx, maxy = layers["bounds"]
    x, y = layers["x"], layers["y"]
    in_area = (
        (x[None, :] >= minx - margin_m)
        & (x[None, :] <= maxx + margin_m)
        & (y[:, None] >= miny - margin_m)
        & (y[:, None] <= maxy + margin_m)
    )
    keep = in_area & np.isfinite(result.hazard)
    return result.hazard[keep], layers["coverage"][keep]


def compare_curves(pooled, per_event, cells):
    """Return the curves side by side at the pooled knots, with their ratio.

    Args:
        pooled: The pooled :class:`~evaluation.TransferFunction`.
        per_event: Each event's own curve, by name.
        cells: Each event's (hazard, coverage) cells, by name.

    Returns:
        A table with one row per pooled knot, and the pooled curve's mean
        coverage over each event's cells beside the observed one.
    """
    table = pd.DataFrame({"hazard": pooled.hazard, "pooled": pooled.coverage})
    for name, curve in per_event.items():
        table[name] = curve(pooled.hazard)
    values = table[list(per_event)].to_numpy()
    compared = (values > MIN_COMPARED_COVERAGE).all(axis=1)
    table["ratio_max_to_min"] = np.where(
        compared, values.max(axis=1) / np.maximum(values.min(axis=1), 1e-12), np.nan
    )

    totals = pd.DataFrame(
        {
            name: {
                "observed_mean_coverage": float(coverage.mean()),
                "pooled_curve_mean_coverage": float(pooled(hazard).mean()),
            }
            for name, (hazard, coverage) in cells.items()
        }
    ).T
    return table, totals


def main(*, events, gamma, tpi_window_m, fault_term, margin_m, n_bins, use_cache):
    """Fit and write the transfer function."""
    cells = {}
    for name in events:
        event = event_inputs.EVENTS[name]
        layers = event_inputs.build_event_layers(
            event,
            tpi_windows_m=[tpi_window_m],
            max_margin_m=margin_m,
            use_cache=use_cache,
        )
        cells[name] = gen_study_area_cells(
            layers,
            gamma=gamma,
            tpi_window_m=tpi_window_m,
            fault_term=fault_term,
            margin_m=margin_m,
        )
        print(
            f"{name}: {layers['n_landslides']:,} landslides, "
            f"{cells[name][0].size:,} cells, observed mean coverage "
            f"{cells[name][1].mean():.4%}"
        )
        del layers

    per_event = {
        name: evaluation.fit_transfer_function(h, c, n_bins=n_bins)
        for name, (h, c) in cells.items()
    }
    pooled = evaluation.fit_transfer_function(
        np.concatenate([h for h, _ in cells.values()]),
        np.concatenate([c for _, c in cells.values()]),
        n_bins=n_bins,
        weights=np.concatenate(
            [np.full(h.size, 1.0 / h.size) for h, _ in cells.values()]
        ),
    )
    pooled = evaluation.TransferFunction(
        hazard=pooled.hazard,
        coverage=pooled.coverage,
        settings={
            "gamma": gamma,
            "tpi_window_m": tpi_window_m,
            "fault_term": fault_term,
        },
    )

    table, totals = compare_curves(pooled, per_event, cells)
    print(RULE)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.5f}"))
    print(RULE)
    print(totals.to_string(float_format=lambda v: f"{v:.4%}"))
    ratios = table["ratio_max_to_min"].dropna()
    if ratios.size:
        print(
            f"The events' curves differ by a factor of {ratios.min():.1f} to "
            f"{ratios.max():.1f} where both exceed {MIN_COMPARED_COVERAGE:g} coverage."
        )

    pooled.to_frame().to_csv(evaluation.TRANSFER_FUNCTION_PATH, index=False)
    print(f"Wrote {evaluation.TRANSFER_FUNCTION_PATH}")
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(TAB_DIR / TAB_NAME, index=False)
    totals.to_csv(TAB_DIR / TAB_NAME.replace(".csv", "_totals.csv"))
    print(f"Wrote {TAB_DIR / TAB_NAME}")


if __name__ == "__main__":
    main(
        events=config.FIT_EVENTS,
        gamma=config.GAMMA,
        tpi_window_m=config.TPI_WINDOW_M,
        fault_term=config.FAULT_TERM,
        margin_m=config.FIT_MARGIN_M,
        n_bins=config.FIT_N_BINS,
        use_cache=config.USE_CACHE,
    )
