"""Map the culvert and bridge crossings over the study area.

    uv run --frozen python src/scripts/landloss/exposure/culverts_bridges/report/fig_crossing_map.py

Draws each crossing step 7 found, where an insured accessway crosses a named
watercourse, as a point coloured by the structure drawn for it, over the four
territorial authorities. A crossing is a few metres long, so it is drawn at its
representative point rather than as its own geometry, which would not show at
this scale. Each crossing is taken from the run of the authority it lies in, as
``gen_report_numbers.py`` counts them.

Writes ``report/exposure/culverts_bridges/fig/crossings-study-area.png``. Reads
step 7's outputs under ``temp/`` only; the basemap tiles are fetched online.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.exposure.culverts_bridges.crossings import (
    BRIDGE,
    CULVERT,
    STRUCTURE_COLUMN,
)
from landloss.io.area_of_interest import get_study_areas
from scripts.landloss.exposure.culverts_bridges.report.gen_report_numbers import (
    FIGURES,
    REALISATION_ID,
    read_crossings,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DPI = 200
BOUNDARY_COLOUR = "#4d4d4d"
# Culverts are most crossings, so they take the quieter mark; bridges the
# saturated one so the fewer of them still read.
STYLES = {
    CULVERT: {"color": "#2a78d6", "marker": "o", "label": "Culvert"},
    BRIDGE: {"color": "#eb6834", "marker": "s", "label": "Bridge"},
}


def plot(crossings, areas):
    """Draw the crossings by structure over the authorities' boundaries."""
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    areas.boundary.plot(ax=ax, color=BOUNDARY_COLOUR, linewidth=0.8, zorder=3)
    points = crossings.representative_point()
    handles = []
    for structure, style in STYLES.items():
        rows = crossings[STRUCTURE_COLUMN] == structure
        points[rows].plot(
            ax=ax,
            color=style["color"],
            marker=style["marker"],
            markersize=14,
            edgecolor="white",
            linewidth=0.4,
            zorder=4,
        )
        handles.append(
            Line2D(
                [],
                [],
                linestyle="none",
                marker=style["marker"],
                color=style["color"],
                markeredgecolor="white",
                label=f"{style['label']} ({int(rows.sum()):,})",
            )
        )
    handles.append(Line2D([], [], color=BOUNDARY_COLOUR, label="Territorial authority"))
    style_basemap_ax(ax, areas)
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.92)
    ax.set_title("Culvert and bridge crossings on insured accessways", fontsize=10)
    return fig


def main(*, realisation_id):
    """Draw the map and write it."""
    crossings = read_crossings(realisation_id)
    areas = get_study_areas(constants.DEFAULT_CRS)
    fig = plot(gpd.GeoDataFrame(crossings), areas)
    out = FIGURES["map"]
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main(realisation_id=REALISATION_ID)
