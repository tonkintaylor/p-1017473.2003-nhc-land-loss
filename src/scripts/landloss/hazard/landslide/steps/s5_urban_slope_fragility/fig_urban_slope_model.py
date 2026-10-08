"""Draw the fragility medians of the urban failure polygons on the map.

Reads the model file ``gen_urban_slope_fragility.py`` writes for each world
and produces the figure the medians get checked by eye against:

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_urban_slope_fragility/fig_urban_slope_model.py

It reads ``config.py`` beside it, the same file the generation reads, and asks
``gen_urban_slope_fragility.urban_slope_model_path`` where that run's output
went, so the figure cannot draw a different world or extent from the one last
run.

Two panels.

- **Where.** The whole extent, with the polygons at the finest scale coloured
  by their median PGV ``theta`` on one sequential scale. What this panel is
  for is the pattern: the lowest medians should sit on the steep cut faces,
  the crests and the walled fills, and the gentle ground should read pale.
- **How spread.** The distribution of ``theta`` per wall state, as a
  cumulative curve on a log axis, with the study's 2,500-year PGV range marked
  so the eye can see what share of each state sits below the demand.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/landslide/urban-slope-model/fig/``, which is gitignored --
the script is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.landslide.urban import fragility, geometry
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import config
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic, so a figure says
# which step drew it without the file name having to.
FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-model" / "fig"
DPI = 200

# One sequential scale for the median: dark is a low median, which fails first.
THETA_CMAP = "viridis"

# The three wall states, in a fixed order with a fixed colour each.
STATE_COLOURS = {
    geometry.NO_WALL: "#4d4d4d",
    geometry.FILL_WALL: "#1b7837",
    geometry.CUT_WALL: "#762a83",
}

# The study's PGV at 2,500 years over the four territorial authorities, m/s
# (plan section 6), marked on the distribution panel.
STUDY_PGV_RANGE_M_S = (0.96, 2.11)

RULE = "-" * 72


def draw_medians(ax, model, extent, *, title):
    """Colour the finest-scale polygons by their median PGV."""
    finest = model[model[geometry.SCALE_COLUMN] == model[geometry.SCALE_COLUMN].min()]
    theta = finest["theta"].to_numpy(dtype=float)
    finite = theta[np.isfinite(theta)]
    norm = LogNorm(vmin=finite.min(), vmax=finite.max()) if finite.size else None
    finest.plot(
        ax=ax,
        column="theta",
        cmap=THETA_CMAP,
        norm=norm,
        linewidth=0.2,
        edgecolor="none",
        legend=True,
        legend_kwds={"label": "median PGV (m/s)", "shrink": 0.6},
        missing_kwds={"color": "#bdbdbd", "label": "no median"},
    )
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    ax.set_title(title, fontsize=9)


def draw_distribution(ax, model, *, title):
    """Draw the cumulative distribution of the median per wall state."""
    for state, colour in STATE_COLOURS.items():
        theta = model.loc[model[fragility.STATE_COLUMN] == state, "theta"]
        theta = np.sort(theta.to_numpy(dtype=float))
        theta = theta[np.isfinite(theta)]
        if theta.size == 0:
            continue
        share = np.arange(1, theta.size + 1) / theta.size
        ax.step(
            theta,
            share,
            where="post",
            color=colour,
            linewidth=1.5,
            label=f"{state.replace('_', ' ')} ({theta.size:,})",
        )
    ax.axvspan(*STUDY_PGV_RANGE_M_S, color="#fdae61", alpha=0.3, lw=0)
    ax.text(
        STUDY_PGV_RANGE_M_S[0],
        1.01,
        "study PGV, 2,500 yr",
        fontsize=7,
        ha="left",
        va="bottom",
    )
    ax.set_xscale("log")
    ax.set_xlabel("median PGV, theta (m/s)")
    ax.set_ylabel("share of polygons with a lower median")
    ax.set_ylim(0, 1.05)
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    ax.set_title(title, fontsize=9)


def build_figure(model, *, world_id, rate_setting):
    """Assemble the two panels."""
    fig, (ax_map, ax_dist) = plt.subplots(1, 2, figsize=(11, 5.5))
    extent = gpd.GeoDataFrame(geometry=[box(*model.total_bounds)], crs=model.crs)
    finest_scale = int(model[geometry.SCALE_COLUMN].min())
    draw_medians(
        ax_map,
        model,
        extent,
        title=(
            f"Where - world {world_id}, {finest_scale} m scale, "
            f"rate setting {rate_setting!r}"
        ),
    )
    draw_distribution(
        ax_dist, model, title=f"How spread - {len(model):,} polygons, every scale"
    )
    fig.tight_layout()
    return fig


def main(*, extent, world_ids):
    """Draw the medians of each world's model file.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
            Must match the setting the generation was run with.
        world_ids: Which worlds' model files to draw.
    """
    for world_id in world_ids:
        model_path = urban_slope_model_path(world_id, extent=extent)
        figure_path = FIG_DIR / f"{model_path.stem}.png"
        print(f"Reading the model from {model_path} ...")
        model = gpd.read_parquet(model_path)
        rate_setting = str(model["rate_setting"].iloc[0]) if len(model) else "none"
        print(RULE)
        print(
            f"World {world_id}: {len(model):,} polygons, rate setting {rate_setting!r}"
        )

        fig = build_figure(model, world_id=world_id, rate_setting=rate_setting)
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(figure_path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, world_ids=config.WORLD_IDS)
