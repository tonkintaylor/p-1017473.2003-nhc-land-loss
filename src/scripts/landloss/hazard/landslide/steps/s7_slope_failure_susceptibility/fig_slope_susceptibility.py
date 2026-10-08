"""Put the rebuilt susceptibility zones beside Greater Wellington's published ones.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s7_slope_failure_susceptibility/fig_slope_susceptibility.py

Reads the rating `gen_slope_susceptibility.py` wrote, so run that first. The
extent and the file names come from ``config.py`` beside them, which is what
keeps this drawing the run that was actually made.

The two panels share one colour scale, because the rebuilt zones band onto the
same 1 to 5 ranks the published layer uses. That is the whole point of the
figure: the scope decision for this step is that validation is by looking, and
looking only works if the scales agree.

The published layer is drawn **unchanged**. It is CC BY-ND, so displaying it is
inside the licence and deriving anything from it is not. Nothing here reads a
value off it.

Expect the rebuilt panel to be tamer than the published one. Three reasons, all
of them stated rather than hidden: the 1995 generalisation rules are not
applied, the landslide factor is zero for want of an inventory, and slope
modification is scored only inside mapped earthworks polygons. The point of
drawing them together is to see how much each of those costs.

Needs ``KOORDINATES_PUBLIC_API_KEY`` in ``.env`` for the published layer.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rioxarray
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from shapely import box

from landloss.common.utils.colors import GWRC_SEVERITY_COLOURS
from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.io.area_of_interest import get_area_of_interest, get_study_areas
from landloss.io.readers import get_gwrc_slope_failure
from scripts.landloss.hazard.landslide.steps.s7_slope_failure_susceptibility import (
    config,
    gen_slope_susceptibility,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "slope-failure-susceptibility" / "fig"
FIG_NAME = "slope-susceptibility-rebuilt-against-gwrc.png"
DPI = 200

RULE = "-" * 72


def zone_colourmap():
    """Return the colour map and norm the five ranks are drawn with.

    Shared between the two panels, and taken from the published layer's own
    palette so that a rank means the same colour in both.

    Returns:
        ``(cmap, norm)`` for a raster of zone ranks 1 to 5.
    """
    ranks = sorted(susceptibility.ZONE_RANKS)
    cmap = ListedColormap([GWRC_SEVERITY_COLOURS[rank][0] for rank in ranks])

    # Half-open boundaries around each integer rank, so rank 3 lands in the
    # third colour rather than on a boundary between two.
    boundaries = [rank - 0.5 for rank in ranks] + [ranks[-1] + 0.5]
    return cmap, BoundaryNorm(boundaries, cmap.N)


def extent_frame(raster):
    """Return the raster's own extent as a frame, for the map styling helper."""
    west, south, east, north = raster.rio.bounds()
    return gpd.GeoDataFrame(
        geometry=[box(west, south, east, north)], crs=raster.rio.crs
    )


def draw_rebuilt(ax, zone, cmap, norm):
    """Draw the rebuilt zone raster."""
    west, south, east, north = zone.rio.bounds()
    ax.imshow(
        zone.to_numpy(),
        extent=(west, east, south, north),
        origin="upper",
        cmap=cmap,
        norm=norm,
        alpha=0.75,
        zorder=2,
        interpolation="nearest",
    )
    ax.set_title("Rebuilt: Kingsbury (1995) scheme on modern data", fontsize=9)


def draw_published(ax, zones, extent):
    """Draw the published layer, unchanged, clipped to the same extent."""
    for rank in sorted(susceptibility.ZONE_RANKS):
        subset = zones.loc[zones["severity_rank"] == rank]
        if not subset.empty:
            subset.plot(
                ax=ax,
                color=GWRC_SEVERITY_COLOURS[rank][0],
                linewidth=0,
                alpha=0.75,
                zorder=2 + rank / 10,
            )

    covered = zones.clip(extent).union_all().area / extent.union_all().area
    ax.set_title(
        f"Published: GWRC layer 4069, unchanged ({covered:.0%} of the extent mapped)",
        fontsize=9,
    )


def legend_handles():
    """Return one patch per zone rank, labelled as the published layer labels them."""
    return [
        Patch(
            facecolor=GWRC_SEVERITY_COLOURS[rank][0],
            label=f"{rank} {susceptibility.ZONE_LABELS[rank]}",
        )
        for rank in sorted(susceptibility.ZONE_RANKS)
    ]


def describe_agreement(zone, published, extent):
    """Print how the two zonations compare over the same ground.

    A rank correlation is not attempted. The published layer is generalised
    polygons and the rebuilt one is a grid, so most of any disagreement would be
    measuring that difference rather than anything about the ground -- which is
    the reason the scope decision for this step is to compare by eye.
    """
    values = zone.to_numpy()
    scored = np.isfinite(values)

    print(RULE)
    print("Rebuilt zones over the extent:")
    for rank in sorted(susceptibility.ZONE_RANKS):
        share = (values == rank).sum() / scored.sum() if scored.sum() else 0.0
        print(f"  {rank} {susceptibility.ZONE_LABELS[rank]:<10} {share:>6.1%}")

    if published.empty:
        print("\nThe published layer maps none of this extent, so there is")
        print("nothing to compare against here.")
        return

    area = extent.union_all().area
    print("\nPublished zones over the same extent, as a share of the whole box:")
    for rank in sorted(susceptibility.ZONE_RANKS):
        subset = published.loc[published["severity_rank"] == rank]
        share = subset.union_all().area / area if not subset.empty else 0.0
        print(f"  {rank} {GWRC_SEVERITY_COLOURS[rank][1]:<12} {share:>6.1%}")

    mapped = published.union_all().area / area
    print(f"  {'mapped at all':<14} {mapped:>6.1%}")


def main(*, extent, out_path):
    """Draw the rebuilt zones beside the published ones and write the figure.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        out_path: Where to write the figure.
    """
    zone_file = gen_slope_susceptibility.zone_path(extent=extent)
    if not zone_file.exists():
        msg = (
            f"{zone_file} does not exist. Run gen_slope_susceptibility.py first; "
            "it writes the zone raster this figure draws."
        )
        raise FileNotFoundError(msg)

    print(f"Reading {zone_file}")
    with rioxarray.open_rasterio(zone_file, masked=True) as opened:
        zone = opened.squeeze(drop=True).load()

    frame = extent_frame(zone)
    bbox = tuple(float(value) for value in frame.total_bounds)

    print("Reading the published GWRC layer ...", flush=True)
    published = get_gwrc_slope_failure(bbox=bbox).clip(frame)

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    describe_agreement(zone, published, frame)

    cmap, norm = zone_colourmap()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 6.0))

    draw_rebuilt(axes[0], zone, cmap, norm)
    draw_published(axes[1], published, frame)

    for ax in axes:
        study_areas.boundary.plot(
            ax=ax, color="#1a1a1a", linewidth=0.7, linestyle="--", zorder=4
        )
        style_basemap_ax(ax, frame, arrow_kwargs={"scale": 0.2})

    axes[0].legend(
        handles=legend_handles(),
        loc="upper left",
        fontsize=7,
        framealpha=0.9,
        title="Susceptibility zone",
        title_fontsize=7,
    )

    aoi = get_area_of_interest(extent)
    extent_label = aoi.name if aoi is not None else "Wellington City earthworks extent"
    fig.suptitle(
        f"Earthquake induced slope failure susceptibility, {extent_label}",
        fontsize=11,
    )
    fig.text(
        0.5,
        0.02,
        "Right hand panel: Greater Wellington Regional Council layer 4069 "
        "(CC BY-ND), reproduced unchanged. Left hand panel is this study's own, "
        "built from the method published in Kingsbury (1995), WRC/PP-T-95/06.",
        ha="center",
        fontsize=6,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, out_path=FIG_DIR / FIG_NAME)
