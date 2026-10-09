"""Plot the waterways used by the liquefaction assessment.

Draws every watercourse across the study area, with the named rivers picked out
from the smaller streams and creeks. Distance to a river free-face is what drives
lateral spreading, so the figure shows both: the rivers the assessment measures
to, and the watercourses it does not, which is the part a reader has to be able
to check.

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/report/fig_waterway_map.py

The first run downloads the national river name lines layer from LINZ, which is
slow; later runs read it from the cache. Pass --extent wlg-pilot to work over
the small Wellington box instead of all four territorial authorities -- though
note that this layer holds no features there, central Wellington's streams having
long since been piped, so --extent wlg-pilot reports an empty extent rather than
drawing a map.

Requires LINZ_API_KEY in .env.
"""

import argparse
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

# Watercourse names are macronised -- Ōhariu, Pāuatahanui -- which the default
# cp1252 Windows console cannot encode, so printing one raises. Ask for UTF-8
# rather than dropping to the layer's name_ascii column, because the names are
# worth getting right.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import requests
from matplotlib.lines import Line2D

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.hazard.liquefaction.waterways import get_waterways
from landloss.io.area_of_interest import (
    EXTENTS,
    FULL_EXTENT,
    get_area_of_interest,
    get_study_areas,
)
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "liquefaction" / "fig"
FIG_NAME = "waterways.png"
DPI = 200

# The named rivers carry the analysis, so they get the saturated colour; the rest
# are drawn thinner and greyer, present for context rather than for reading off.
RIVER_COLOUR = "#1f78b4"
OTHER_COLOUR = "#9ecae1"
BOUNDARY_COLOUR = "#4d4d4d"

STYLES = {
    "other": {"color": OTHER_COLOUR, "linewidth": 0.4, "zorder": 2},
    "river": {"color": RIVER_COLOUR, "linewidth": 1.1, "zorder": 3},
}
LABELS = {
    "other": "Other watercourses (streams, creeks)",
    "river": "Named rivers",
}
RULE = "-" * 72


def describe(waterways):
    """Print what came back, so the classification can be sanity checked."""
    print(RULE)
    print(f"Loaded {len(waterways):,} watercourse features")

    counts = waterways["wtype"].value_counts()
    for wtype in ("river", "other"):
        print(f"  {LABELS[wtype]:<38} {counts.get(wtype, 0):>7,}")

    if "feat_type" in waterways:
        print("\nfeat_type values in the extent:")
        for value, count in waterways["feat_type"].value_counts().items():
            print(f"  {value!s:<38} {count:>7,}")

    rivers = waterways.loc[waterways["wtype"] == "river", "name"].dropna()
    if not rivers.empty:
        named = sorted(rivers.unique())
        print(f"\n{len(named)} distinct named rivers, first few:")
        for name in named[:10]:
            print(f"  {name}")


def plot_waterways(waterways, extent, study_areas=None):
    """Plot the watercourses over a basemap, rivers picked out from the rest."""
    fig, ax = plt.subplots(figsize=(7.0, 7.4))

    # Draw the minor watercourses first so the named rivers sit on top of them.
    for wtype in ("other", "river"):
        subset = waterways.loc[waterways["wtype"] == wtype]
        if not subset.empty:
            subset.plot(ax=ax, **STYLES[wtype])

    if study_areas is not None:
        study_areas.boundary.plot(
            ax=ax, color=BOUNDARY_COLOUR, linewidth=0.7, linestyle="--", zorder=4
        )

    style_basemap_ax(ax, extent)

    handles = [Line2D([], [], label=LABELS[w], **STYLES[w]) for w in ("river", "other")]
    if study_areas is not None:
        handles.append(
            Line2D(
                [],
                [],
                color=BOUNDARY_COLOUR,
                linewidth=0.7,
                linestyle="--",
                label="Territorial authority boundary",
            )
        )
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.9)

    ax.set_title("Waterways across the study area", fontsize=10)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extent",
        default=FULL_EXTENT,
        choices=[FULL_EXTENT, *EXTENTS],
        help="The extent to draw: the full study area, or a named pilot box.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore the extent cache and re-read from the source layer.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=FIG_DIR / FIG_NAME,
        help="Where to write the figure.",
    )
    args = parser.parse_args()

    study_areas = get_study_areas(constants.DEFAULT_CRS)

    aoi = get_area_of_interest(args.extent)
    if aoi is not None:
        extent = aoi.to_geoseries(constants.DEFAULT_CRS).to_frame("geometry")
        extent = extent.set_geometry("geometry")
        bbox = aoi.bbox(constants.DEFAULT_CRS)
        print(f"Extent: {aoi.name}")
    else:
        extent = study_areas
        bbox = tuple(float(value) for value in study_areas.total_bounds)
        print(f"Extent: {', '.join(study_areas['name'])}")

    minx, miny, maxx, maxy = bbox
    print(f"  NZTM  : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size  : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")

    print("\nReading the LINZ river name lines layer ...")
    try:
        # Cut to the real territorial authority boundaries, not just their
        # bounding box, which would also take in much of the Wairarapa.
        waterways = get_waterways(
            bbox=bbox,
            clip_to=None if aoi is not None else study_areas,
            use_cache=not args.fresh,
        )
    except ValueError as exc:
        # Raised by resolve_api_key when LINZ_API_KEY is missing.
        print(f"\nCould not read the layer: {exc}")
        return 1
    except requests.exceptions.RequestException as exc:
        print(f"\nThe request to LINZ failed: {exc}")
        print(
            "\nLINZ takes many minutes to build a national export and an occasional\n"
            "status poll returns a 502 during that wait, which ttpy treats as fatal.\n"
            "Re-running starts the wait over; the export usually completes server\n"
            "side regardless."
        )
        return 1

    if waterways.empty:
        print("\nNo watercourses found within the extent.")
        return 1

    describe(waterways)

    fig = plot_waterways(waterways, extent, study_areas if aoi is None else None)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    # Only raise on failure. Falling off the end already exits 0, so the shell
    # contract is unchanged, but running this under an IPython or PyCharm console
    # no longer ends in a "SystemExit: 0" traceback that reads like a crash.
    status = main()
    if status:
        raise SystemExit(status)
