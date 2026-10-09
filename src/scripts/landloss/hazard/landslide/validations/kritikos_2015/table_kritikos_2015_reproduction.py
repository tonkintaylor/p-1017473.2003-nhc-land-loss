"""Reproduce the Kritikos et al. (2015) success-rate AUCs for Northridge and Wenchuan.

The model is rebuilt from the paper's Figure 5, whose membership points were
read off the page, so the check that the digitisation and the model are right is
that they score what the paper scored on the paper's own events: Northridge
0.904 and Wenchuan 0.839 over the whole study area, and 0.871 and 0.845 over
slopes above 5 degrees [kritikos_2015].

The inputs are stand-ins for the paper's (see :mod:`event_inputs`): Copernicus
30 m for ASTER 60 m, the GEM fault database for each region's mapped faults,
and the study area is the inventory's bounding box, which the paper does not
define. A result within about 0.02 of the paper is a reproduction; the sensitivity
rows show how far the choices the paper leaves open move it. Chi-Chi (0.921)
cannot be reproduced because the GFDB carries only its liquefaction.

Run with:

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/kritikos_2015/table_kritikos_2015_reproduction.py

Writes ``kritikos_2015_reproduction.csv`` under the report folder's
``hazard/landslide/kritikos-2015-validation/tab``.
"""

import numpy as np
import pandas as pd

from landloss.hazard.landslide.models.kritikos_2015 import evaluation, model
from scripts.landloss.hazard.landslide.validations.kritikos_2015 import (
    config,
    event_inputs,
)
from scripts.landloss.paths import REPORT_DIR

TAB_DIR = REPORT_DIR / "hazard" / "landslide" / "kritikos-2015-validation" / "tab"
TAB_NAME = "kritikos_2015_reproduction.csv"


def score(
    layers,
    *,
    window_m,
    gamma,
    margin_m,
    min_mmi=None,
    min_slope_deg=None,
    use_faults=True,
):
    """Return the success-rate AUC of one model setting over a study area.

    Args:
        layers: The output of :func:`build_event_layers`.
        window_m: Which TPI window's slope positions to use.
        gamma: The fuzzy gamma.
        margin_m: How far the study area extends beyond the inventory's
            bounding box.
        min_mmi: If given, cells under this intensity are left out.
        min_slope_deg: If given, cells at or under this slope are left out.
        use_faults: ``False`` holds the fault term at its far-field value.
    """
    fault_km = layers["fault_km"]
    if not use_faults:
        fault_km = np.where(np.isfinite(fault_km), np.inf, np.nan)
    result = model.run(
        mm=layers["mm"],
        slope_deg=layers["slope"],
        fault_distance_km=fault_km,
        slope_position=layers["position"][window_m],
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
    hazard = np.where(in_area, result.hazard, np.nan)
    if min_mmi is not None:
        hazard = np.where(layers["mm"] >= min_mmi, hazard, np.nan)
    if min_slope_deg is not None:
        hazard = np.where(layers["slope"] > min_slope_deg, hazard, np.nan)
    return evaluation.success_rate_auc(hazard, layers["counts"])


def main(
    *,
    events,
    gamma,
    tpi_window_m,
    tpi_sensitivity_windows_m,
    gamma_sensitivity,
    study_area_margins_m,
    use_cache,
):
    windows = [tpi_window_m, *tpi_sensitivity_windows_m]
    rows = []
    for name in events:
        event = event_inputs.EVENTS[name]
        layers = event_inputs.build_event_layers(
            event,
            tpi_windows_m=windows,
            max_margin_m=max(study_area_margins_m),
            use_cache=use_cache,
        )
        print(f"{name}: {layers['n_landslides']:,} landslides")
        base = {"window_m": tpi_window_m, "gamma": gamma, "margin_m": 0.0}
        cases = [
            ("base", base, "auc"),
            ("slope > 5 deg", {**base, "min_slope_deg": 5.0}, "auc_over_5deg"),
            ("MMI >= 6", {**base, "min_mmi": 6.0}, None),
            (f"gamma {gamma_sensitivity}", {**base, "gamma": gamma_sensitivity}, None),
            ("no fault term", {**base, "use_faults": False}, None),
            *(
                (f"TPI window {w:g} m", {**base, "window_m": w}, None)
                for w in tpi_sensitivity_windows_m
            ),
            *(
                (f"study area +{m / 1000:g} km", {**base, "margin_m": m}, None)
                for m in study_area_margins_m
            ),
        ]
        for label, kwargs, published_key in cases:
            auc = score(layers, **kwargs)
            published = (
                getattr(event, f"published_{published_key}") if published_key else None
            )
            rows.append(
                {
                    "event": name,
                    "case": label,
                    "auc": round(auc, 3),
                    "published_auc": published,
                    "difference": None
                    if published is None
                    else round(auc - published, 3),
                }
            )
            print(rows[-1])

    table = pd.DataFrame(rows)
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(TAB_DIR / TAB_NAME, index=False)
    print(f"Wrote {TAB_DIR / TAB_NAME}")


if __name__ == "__main__":
    main(
        events=config.EVENTS,
        gamma=config.GAMMA,
        tpi_window_m=config.TPI_WINDOW_M,
        tpi_sensitivity_windows_m=config.TPI_SENSITIVITY_WINDOWS_M,
        gamma_sensitivity=config.GAMMA_SENSITIVITY,
        study_area_margins_m=config.STUDY_AREA_MARGINS_M,
        use_cache=config.USE_CACHE,
    )
