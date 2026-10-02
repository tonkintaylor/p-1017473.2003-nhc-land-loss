"""Draw the ground map's material and modification over the extent.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s4_ground_map/fig_ground_map.py

Reads the map ``gen_ground_map.py`` wrote, so run that first. The extent and
the file name come from ``config.py`` beside them, through
``gen_ground_map.ground_map_path``, which is what keeps this drawing the run
that was actually made.

Two panels on one basemap: the material on the left, the modification on the
right, each piece coloured by its class with the flat land hatched over both.
The point of the figure is to see where each source reaches -- the SLIDE
mapping stops at its study area boundary, the WCC earthworks are a sparse
record, and everywhere else is the regional fallback -- so the legend is the
vocabulary, not the source.

Writes ``ground-map<extent_suffix>.png`` to ``report/hazard/landslide/ground-map/fig/``.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.landslide import ground_map
from landloss.io.area_of_interest import extent_suffix, get_area_of_interest
from scripts.landloss.hazard.landslide.steps.s4_ground_map import config, gen_ground_map
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "ground-map" / "fig"
DPI = 200

# One colour per vocabulary value, ordered as the legend reads. Greys for rock
# by weathering grade, earth tones for the soils, purples for placed ground.
MATERIAL_COLOURS = {
    "rock": ("#7f7f7f", "Rock, grade unknown"),
    "rock_uw_mw": ("#4d4d4d", "Rock, UW to MW"),
    "rock_hw_cw": ("#a6a6a6", "Rock, HW to CW"),
    "rock_crushed": ("#c9a0dc", "Rock, crushed and shattered"),
    "colluvium": ("#d8b365", "Colluvium"),
    "loess": ("#f6e8c3", "Loess"),
    "alluvium": ("#5ab4ac", "Alluvium"),
    "fill_engineered": ("#8c6bb1", "Engineered fill"),
    "fill_uncontrolled": ("#88419d", "Uncontrolled fill"),
    "reclamation": ("#4d004b", "Reclamation"),
    ground_map.UNKNOWN: ("#ffffff", "Unknown"),
}
MODIFICATION_COLOURS = {
    "cut": ("#d73027", "Cut"),
    "fill": ("#4575b4", "Fill"),
    ground_map.NATURAL: ("#e0e0e0", "Natural"),
    ground_map.UNKNOWN: ("#ffffff", "Unknown"),
}

RULE = "-" * 72


def fig_path(*, extent):
    """Return the file the figure is written to."""
    suffix = extent_suffix(extent)
    return FIG_DIR / f"ground-map{suffix}.png"


def draw_classes(ax, ground, column, colours, title):
    """Colour each piece by its class, and hatch the flat land over the top."""
    for value, (colour, _label) in colours.items():
        subset = ground.loc[ground[column] == value]
        if not subset.empty:
            subset.plot(ax=ax, color=colour, linewidth=0, alpha=0.8, zorder=2)
    flat = ground.loc[ground["is_flatland"]]
    if not flat.empty:
        flat.plot(
            ax=ax,
            facecolor="none",
            edgecolor="#1a1a1a",
            hatch="///",
            linewidth=0,
            zorder=3,
        )
    ax.set_title(title, fontsize=9)
    ax.legend(
        handles=[
            Patch(facecolor=colour, label=label)
            for value, (colour, label) in colours.items()
            if (ground[column] == value).any()
        ]
        + [
            Patch(
                facecolor="none",
                edgecolor="#1a1a1a",
                hatch="///",
                label="NLM flat land",
            )
        ],
        loc="upper left",
        fontsize=6,
        framealpha=0.9,
    )


def main(*, extent):
    """Draw the material and the modification panels and write the figure.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
    """
    map_file = gen_ground_map.ground_map_path(extent=extent)
    print(f"Reading {map_file}")
    ground = gpd.read_parquet(map_file)

    frame = gpd.GeoDataFrame(geometry=[box(*ground.total_bounds)], crs=ground.crs)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 6.0))
    draw_classes(axes[0], ground, "material", MATERIAL_COLOURS, "Material")
    draw_classes(axes[1], ground, "modification", MODIFICATION_COLOURS, "Modification")
    for ax in axes:
        style_basemap_ax(ax, frame, arrow_kwargs={"scale": 0.2})

    aoi = get_area_of_interest(extent)
    extent_label = aoi.name if aoi is not None else "the four territorial authorities"
    fig.suptitle(
        f"Ground map, {extent_label}",
        fontsize=11,
    )
    fig.text(
        0.5,
        0.02,
        "SLIDE materials and genesis: GNS Science / MBIE. 1:50,000 geology: "
        "GNS Science, Begg & Mazengarb (1996), CC BY 3.0 NZ. Earthworks: "
        "Wellington City Council. Geomorphology, flat land and groundwater: "
        "National Liquefaction Model, T+T.",
        ha="center",
        fontsize=6,
    )

    out_path = fig_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT)
