"""Map the slope units, coloured by their mean aspect.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_slope_units/fig_slope_units.py

Reads ``config.py`` beside it, the same file ``gen_slope_units.py`` reads, and
asks ``gen_slope_units.slope_units_path`` where that run's layer went, so the
figure draws the extent last run.

One panel: every unit filled by its circular mean downhill azimuth on a cyclic
colour map, so north-facing and south-facing facets read as different hues and
a unit that spans a ridge shows up as a colour that belongs to neither side;
unit outlines in black. What the panel is for is the pattern: units should run
from drainage line to ridge with one hue each, and the flatland units should
sit on the valley floors and the reclaimed harbour edge.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/landslide/slope-units/fig/``, which is gitignored -- the script
is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.hazard.landslide.slope_units import M2_PER_HA
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    resolve_extent,
)
from scripts.landloss.hazard.landslide.steps.s5_slope_units import config
from scripts.landloss.hazard.landslide.steps.s5_slope_units.gen_slope_units import (
    slope_units_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "slope-units" / "fig"
DPI = 200

# A cyclic map, so 0 and 360 degrees take the same colour.
ASPECT_CMAP = "twilight"
LAYER_ALPHA = 0.7


def main(*, pilot, channel_threshold_ha):
    """Draw the slope units coloured by aspect over the extent last run.

    Args:
        pilot: Whether the run being drawn was over the pilot box.
        channel_threshold_ha: The channel threshold of the run, for the title.
    """
    units = gpd.read_parquet(slope_units_path(pilot=pilot))
    bbox, extent_name = resolve_extent(pilot=pilot)
    extent = gpd.GeoDataFrame(geometry=[box(*bbox)], crs=constants.DEFAULT_CRS)

    fig, ax = plt.subplots(figsize=(8, 8))
    units.plot(
        ax=ax,
        column="mean_aspect_degrees",
        cmap=ASPECT_CMAP,
        vmin=0,
        vmax=360,
        alpha=LAYER_ALPHA,
        edgecolor="black",
        linewidth=0.4,
        legend=True,
        legend_kwds={
            "label": "Mean downhill azimuth (degrees from north)",
            "shrink": 0.6,
        },
        zorder=2,
    )
    style_basemap_ax(ax, extent)
    median_ha = units["area_m2"].median() / M2_PER_HA
    ax.set_title(
        f"Slope units, {channel_threshold_ha:g} ha channel threshold: "
        f"{len(units):,} units, median {median_ha:.1f} ha",
        fontsize=9,
    )
    fig.suptitle(extent_name, fontsize=10)
    fig.tight_layout()

    suffix = "-pilot" if pilot else ""
    path = FIG_DIR / f"slope-units{suffix}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(pilot=config.PILOT, channel_threshold_ha=config.CHANNEL_THRESHOLD_HA)
