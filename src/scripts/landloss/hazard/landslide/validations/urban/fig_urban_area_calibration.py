"""Draw the urban fragility calibration against the record, the anchors and Kingsbury.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/urban/fig_urban_area_calibration.py

Reads what ``table_urban_area_calibration.py`` reads (the bare polygons, the
non-flat ground and the TS1170.5 grids, built by its ``read_inputs``), fits
the same curves (the adopted fit to the Kaikoura record A16 and the polygon
anchors, and the two rejected area fits) and draws four panels. The adopted
curve is on every one.

1. The expected damaged share of the whole non-flat pilot against rock PGA,
   for the adopted, committed and rejected area curves. It is drawn against
   the Kaikoura record A16 (fitted by the adopted curve), Kingsbury's High
   fractions A10 to A12 as bars across each scenario's PGA range (A12 an
   upper limit for the adopted curve), and the share the footprints cover,
   the ceiling no curve can pass.
2. The same on the non-flat cells nearest a Moderate polygon, against the
   Moderate fractions A07 to A09 (a check).
3. The rejected footprint fit and the adopted curve on the footprint cells.
4. The polygon anchors A17 to A21: the share of matching polygons each curve
   expects to fail, against the anchor's fraction (fitted by the adopted
   curve).

Run settings come from ``config.py`` beside this script. The figure goes under
``report/hazard/landslide/urban-fragility/fig/``.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np

from landloss.hazard.landslide.urban import area_calibration
from scripts.landloss.hazard.landslide.validations.urban import config
from scripts.landloss.hazard.landslide.validations.urban import (
    table_urban_area_calibration as calibration,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-fragility" / "fig"
FIG_NAME = "urban-area-calibration.png"
DPI = 200

# The rock PGA axis the shares are drawn over, g.
PGA_AXIS_G = np.geomspace(0.01, 2.0, 30)
SHARE_LIMITS = (1e-4, 1.0)

CURVE_STYLES = {
    "adopted": {"color": "#1a1a1a", "linestyle": "-", "linewidth": 2.0},
    "area": {"color": "#d7191c", "linestyle": "-", "linewidth": 1.2},
    "committed": {"color": "#2c7bb6", "linestyle": "--", "linewidth": 1.2},
    "previous": {"color": "#7f7f7f", "linestyle": ":", "linewidth": 1.2},
    "footprint": {"color": "#1b7837", "linestyle": "-.", "linewidth": 1.4},
}
TARGET_COLOUR = "#6a3d9a"
CEILING_COLOUR = "#9e9e9e"


def share_curve(inputs, curve, cells):
    """The expected damaged share at every PGA of the drawn axis."""
    polygons = inputs.on_rock()
    return np.array(
        [
            area_calibration.expected_damaged_share(
                inputs.incidence,
                area_calibration.polygon_failure_probability(pga, polygons, curve),
                cells=cells,
            )
            for pga in PGA_AXIS_G
        ]
    )


def draw_targets(ax, anchors):
    """Draw each anchor as a bar across its PGA range at its fraction."""
    for _, anchor in anchors.iterrows():
        low, high = anchor["pga_rock_g_min"], anchor["pga_rock_g_max"]
        fraction = anchor["fail_fraction"]
        if low == high:
            ax.plot(low, fraction, "D", color=TARGET_COLOUR, ms=5, zorder=4)
        else:
            ax.plot([low, high], [fraction, fraction], color=TARGET_COLOUR, lw=3)
        ax.annotate(
            anchor["anchor_id"],
            (np.sqrt(low * high), fraction),
            xytext=(0, 5),
            textcoords="offset points",
            fontsize=7,
            ha="center",
        )


def draw_share_panel(ax, inputs, curves, *, cells, anchors, title):
    """Draw the share curves on one reference with its targets and ceiling."""
    for name, curve in curves.items():
        ax.plot(
            PGA_AXIS_G,
            share_curve(inputs, curve, cells),
            label=(
                f"{name}: {curve.theta_at_zero_rating_m_s:.3g} to "
                f"{curve.theta_at_max_rating_m_s:.3g} m/s, beta {curve.beta:.2f}"
            ),
            **CURVE_STYLES[name],
        )
    covered = calibration.covered_cells(inputs)
    ceiling = covered.mean() if cells is None else covered[cells].mean()
    ax.axhline(
        ceiling,
        color=CEILING_COLOUR,
        lw=1.0,
        label=f"share under a footprint ({ceiling:.1%})",
    )
    draw_targets(ax, anchors)
    ax.set(
        xscale="log",
        yscale="log",
        ylim=SHARE_LIMITS,
        xlim=(PGA_AXIS_G[0], PGA_AXIS_G[-1]),
        xlabel="PGA on rock (g)",
        ylabel="expected damaged share",
    )
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
    ax.legend(fontsize=6, loc="lower right")
    ax.set_title(title, fontsize=9)


def draw_polygon_panel(ax, table, curves):
    """Draw each polygon anchor's fraction against what each curve expects."""
    x = np.arange(len(table))
    ax.scatter(
        x,
        table["target"],
        marker="D",
        color=TARGET_COLOUR,
        zorder=4,
        label="anchor fraction",
    )
    for name in curves:
        style = CURVE_STYLES[name]
        ax.scatter(
            x,
            table[f"predicted_{name}"],
            marker="o",
            s=22,
            facecolor="white",
            edgecolor=style["color"],
            label=name,
        )
    ax.set_xticks(
        x,
        [
            f"{row.anchor_id}\n{row.applies_to}, n={row.n_polygons}"
            for row in table.itertuples()
        ],
        fontsize=7,
    )
    ax.set(ylim=(0, 1.02), ylabel="share of matching polygons failing")
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
    ax.legend(fontsize=7)
    ax.set_title("Polygon anchors A17 to A21 (fitted by the adopted curve)", fontsize=9)


def build_figure(inputs, fits):
    """Assemble the four panels.

    Args:
        inputs: From ``table_urban_area_calibration.read_inputs``.
        fits: From ``table_urban_area_calibration.fit_all``.

    Returns:
        The figure.
    """
    every = calibration.curves_to_compare(fits)
    curves = {name: curve for name, curve in every.items() if name != "footprint"}
    zone_area = inputs.zone_area_anchors()
    high = zone_area[
        (zone_area["zone"] == calibration.FIT_ZONE) | zone_area["zone"].isna()
    ]
    moderate = zone_area[zone_area["zone"] == calibration.MODERATE_ZONE]
    moderate_cells = inputs.zone_of_cell == calibration.MODERATE_ZONE
    fig, axes = plt.subplots(2, 2, figsize=(13, 9.5), constrained_layout=True)
    draw_share_panel(
        axes[0, 0],
        inputs,
        curves,
        cells=None,
        anchors=high,
        title=(
            "Whole non-flat pilot: adopted fits A16 (A12 an upper limit); "
            "rejected area fit to A10-A12"
        ),
    )
    draw_share_panel(
        axes[0, 1],
        inputs,
        curves,
        cells=moderate_cells,
        anchors=moderate,
        title="Non-flat cells nearest a Moderate polygon: A07-A09 (check)",
    )
    draw_share_panel(
        axes[1, 0],
        inputs,
        {"adopted": fits.adopted.curve, "footprint": fits.footprint.curve},
        cells=calibration.covered_cells(inputs),
        anchors=high,
        title="Footprint cells only: rejected footprint fit to A10-A12",
    )
    draw_polygon_panel(
        axes[1, 1], calibration.polygon_anchor_table(inputs, every), every
    )
    fig.suptitle(
        "Urban localised (no wall) fragility: adopted fit to the Kaikoura record "
        "and the polygon anchors, against Kingsbury (1995) shares - bare polygons",
        fontsize=11,
    )
    return fig


def draw(inputs, path):
    """Fit the curves from the built inputs and write the figure to ``path``."""
    fits = calibration.fit_all(inputs)
    curves = calibration.curves_to_compare(fits)
    calibration.report_fit(fits, calibration.upper_limit_table(inputs, curves))
    fig = build_figure(inputs, fits)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {path}")


def main(*, extent, return_period_yr):
    """Fit the curves and draw them against the shares and the polygon anchors.

    Args:
        extent: The extent to read, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        return_period_yr: The return period of the TS1170.5 grids.
    """
    inputs = calibration.read_inputs(extent=extent, return_period_yr=return_period_yr)
    draw(inputs, FIG_DIR / FIG_NAME)


if __name__ == "__main__":
    main(extent=config.EXTENT, return_period_yr=config.RETURN_PERIOD_YR)
