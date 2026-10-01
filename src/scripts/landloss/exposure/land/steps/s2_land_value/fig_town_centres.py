"""Map the centres the accessibility term measures against, and what it gives.

Draws each centre from the packaged centres asset as a circle sized by its
weight and labelled with its name and weight, over the address points coloured
by the gravity accessibility s2_build_accessibility.py measured.

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/fig_town_centres.py

The figure is how the centres are reviewed. Their weights and positions are
judgement, placed by hand, and the numbers only mean something once they can be
seen: whether a centre sits on its shopping street, whether the weights rank the
centres the way a Wellingtonian would, and whether the accessibility surface
falls away from the CBD the way land prices do.

Colour is on a logarithmic scale, because the land value model reads the
logarithm of gravity accessibility -- the elasticity multiplies it -- so equal
steps of colour are equal steps of effect on value.

PILOT in config.py beside this script chooses the pilot box or the full study
area, and ACCESSIBILITY the file read, so the figure draws what s2 wrote. It
reads that file and does not rebuild it, so run s2 first.

Needs no API key: everything it reads is on disk, apart from the basemap tiles.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LogNorm

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.exposure.land.accessibility import GRAVITY_COLUMN, load_centres
from landloss.io.area_of_interest import SMALL_WLG_PILOT, get_study_areas
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.exposure.land.steps.s2_land_value.s2_build_accessibility import (
    resolve_paths,
)
from scripts.landloss.paths import REPORT_DIR

# Centre names are macronised in places, which the default cp1252 Windows
# console cannot encode. See the note in s4_estimate_land_value.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Any directory named fig is gitignored, so the figure is regenerated rather
# than committed and this script is the record of how it was made.
FIG_DIR = REPORT_DIR / "exposure" / "land" / "land-value" / "fig"
FIG_NAME = "town-centres.png"
PILOT_FIG_NAME = "town-centres-pilot.png"

BUILDER_PATH = (
    "src/scripts/landloss/exposure/land/steps/s2_land_value/s2_build_accessibility.py"
)

# Sequential and colour-vision safe, reversed so the most accessible addresses
# are the dark ones, which is the legible end on a pale basemap.
COLOURMAP = "viridis_r"
BOUNDARY_COLOUR = "#333333"
CENTRE_EDGE_COLOUR = "#b2182b"

# A centre's circle area is proportional to its weight, at this many points
# squared for a weight of one, so the Wellington CBD reads as the dominant centre
# and a local shopping street as a dot.
CENTRE_SIZE_PER_WEIGHT = 900.0

MARKER_SIZE = 0.9
PILOT_MARKER_SIZE = 3.0
MARKER_ALPHA = 0.85

FIGURE_SIZE_IN = (9.0, 9.0)
DPI = 250
RULE = "-" * 72


def draw(accessibility, centres, extent, boundaries, *, marker_size, title):
    """Draw the accessibility surface and the centres, and return the figure."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_IN, layout="constrained")

    values = accessibility[GRAVITY_COLUMN].astype(float)
    drawable = accessibility.loc[values > 0]
    norm = LogNorm(vmin=float(values[values > 0].min()), vmax=float(values.max()))

    ax.scatter(
        drawable.geometry.x,
        drawable.geometry.y,
        c=values.loc[drawable.index],
        cmap=COLOURMAP,
        norm=norm,
        s=marker_size,
        alpha=MARKER_ALPHA,
        linewidths=0,
        zorder=3,
    )

    if boundaries is not None:
        boundaries.boundary.plot(
            ax=ax, color=BOUNDARY_COLOUR, linewidth=0.7, linestyle="--", zorder=4
        )

    minx, miny, maxx, maxy = extent.total_bounds
    inside = centres.cx[minx:maxx, miny:maxy]
    ax.scatter(
        inside.geometry.x,
        inside.geometry.y,
        s=CENTRE_SIZE_PER_WEIGHT * inside["weight"],
        facecolors="none",
        edgecolors=CENTRE_EDGE_COLOUR,
        linewidths=1.2,
        zorder=5,
    )
    for _, centre in inside.iterrows():
        ax.annotate(
            f"{centre['name']} ({centre['weight']:.2f})",
            (centre.geometry.x, centre.geometry.y),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=6.5,
            zorder=6,
            bbox={
                "boxstyle": "round,pad=0.15",
                "fc": "white",
                "ec": "none",
                "alpha": 0.8,
            },
        )

    style_basemap_ax(ax, extent)

    bar = fig.colorbar(
        ScalarMappable(norm=norm, cmap=COLOURMAP),
        ax=ax,
        orientation="horizontal",
        fraction=0.046,
        pad=0.02,
    )
    bar.set_label("Gravity accessibility (log scale)", fontsize=8)
    bar.ax.tick_params(labelsize=7)

    ax.set_title(title, fontsize=10)
    return fig


def describe(centres):
    """Print the centres drawn, so the figure can be read against the asset."""
    print(RULE)
    print(f"{'Centre':<18}{'Kind':<10}{'Weight':>8}{'Decay (km)':>12}")
    for _, centre in centres.sort_values("weight", ascending=False).iterrows():
        print(
            f"{centre['name']:<18}{centre['kind']:<10}{centre['weight']:>8.2f}"
            f"{centre['decay_length_m'] / 1000:>12.1f}"
        )


def main(*, pilot, spine, accessibility):
    """Draw the centres over the gravity accessibility surface.

    Args:
        pilot: Draw the small Wellington pilot box instead of the study area.
        spine: The address spine path from config.py, passed through so the path
            resolved is the one s2 used.
        accessibility: The accessibility attributes path from config.py, or
            None for the standard location.

    Raises:
        FileNotFoundError: If s2_build_accessibility.py has not been run over
            this extent, naming the command to run.
    """
    _, path = resolve_paths(pilot=pilot, spine=spine, out=accessibility)
    if not path.exists():
        msg = (
            f"No accessibility attributes at {path}. Run "
            f"uv run --frozen python {BUILDER_PATH} first."
        )
        raise FileNotFoundError(msg)

    measured = gpd.read_parquet(path)
    centres = load_centres(crs=measured.crs)
    study_areas = get_study_areas(constants.DEFAULT_CRS)

    if pilot:
        extent = gpd.GeoDataFrame(
            geometry=SMALL_WLG_PILOT.to_geoseries(constants.DEFAULT_CRS)
        )
        boundaries, marker_size, out = None, PILOT_MARKER_SIZE, PILOT_FIG_NAME
    else:
        extent, boundaries, marker_size, out = (
            study_areas,
            study_areas,
            MARKER_SIZE,
            FIG_NAME,
        )

    fig = draw(
        measured,
        centres,
        extent,
        boundaries,
        marker_size=marker_size,
        title="Centres and the gravity accessibility they give each address",
    )
    describe(centres)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {FIG_DIR / out}")


if __name__ == "__main__":
    main(pilot=config.PILOT, spine=config.SPINE, accessibility=config.ACCESSIBILITY)
