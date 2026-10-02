"""Check how complete WCC's earthworks record is against GNS's mapped cut/fill lines.

Wellington City Council's cut and fill polygons are an index of the earthworks
the council holds plans for, so they miss anything that was never consented or
whose plans were never filed. GNS Science's SLIDE geomorphic mapping was drawn
from imagery and elevation models instead, and one of its line types is
"Cut/fill line". The two were made independently, so the share of GNS cut/fill
length that falls on or near a WCC polygon is a cheap, direct measure of how
much earthworked ground the council record captures -- and the unmatched lines
show where it is thin.

Both directions are reported:

  1. GNS -> WCC: the fraction of GNS cut/fill line length lying within a
     tolerance of any WCC cut or fill polygon. This is the completeness figure.
  2. WCC -> GNS: the fraction of WCC polygons with a GNS cut/fill line within the
     same tolerance, for the polygons inside the GNS mapping extent. A WCC
     polygon with nothing near it is earthworked ground GNS did not pick out,
     which says how far the GNS lines can stand in for the record elsewhere.

A GNS line marks the edge of an earthwork -- the crest of a cut or the toe of a
fill -- so it often sits on or just outside a WCC polygon's boundary rather than
inside it. That is why the match is made against a buffer rather than the
polygons themselves, and why the result is reported over a range of tolerances
instead of one: a fraction that keeps climbing with the buffer is picking up
neighbouring ground rather than the same earthwork.

The GNS layer does not say whether a line is a cut or a fill, so the WCC cut and
fill polygons are compared together as one earthworks footprint.

    uv run --frozen python src/scripts/landloss/hazard/landslide/research/fig_wcc_earthworks_completeness.py

Requires TNT_KOORDINATES_API_KEY in .env. See
``landloss.io.readers.get_gns_slide_morphology``, ``get_wcc_cut_areas`` and
``get_wcc_fill_areas`` for the sources and their licences. The WCC layers are
CC BY-ND 4.0 (fill: no licence recorded), so this figure is for internal use and
must not be published without the council's agreement.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG and a CSV

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_wcc_cut_areas,
    get_wcc_fill_areas,
)
from scripts.landloss.paths import RESEARCH_DIR

OUT_DIR = RESEARCH_DIR / "hazard" / "landslide" / "wcc_earthworks_completeness"
FIG_PATH = OUT_DIR / "fig" / "wcc-earthworks-vs-gns-cut-fill.png"
TAB_PATH = OUT_DIR / "tab" / "wcc-earthworks-vs-gns-cut-fill.csv"
DPI = 200

GNS_CUT_FILL_TYPE = "Cut/fill line"

# Tolerances in metres. 0 m is the strict "inside the polygon" case; the upper
# end is a street width, beyond which a match is more likely a neighbouring
# earthwork than the same one.
TOLERANCES_M = (0.0, 5.0, 10.0, 20.0, 50.0)

# The tolerance the map colours lines by: enough to absorb a line drawn along
# the polygon edge and the difference in how the two were digitised.
MAP_TOLERANCE_M = 10.0

WCC_CUT_COLOUR = "#e6a15c"
WCC_FILL_COLOUR = "#7b9fd4"
MATCHED_COLOUR = "#1a7a3a"
UNMATCHED_COLOUR = "#c0392b"

RULE = "-" * 72


def gns_length_within(lines, footprint, tolerance_m):
    """Return the length of each line lying within ``tolerance_m`` of the footprint.

    Clipped piecewise rather than as a yes/no per line, because a long GNS line
    can run along a WCC polygon for part of its length and out the other side.
    """
    zone = footprint.buffer(tolerance_m) if tolerance_m > 0 else footprint
    return lines.geometry.intersection(zone).length


def wcc_polygons_matched(wcc, lines, tolerance_m):
    """Return a boolean per WCC polygon: is any GNS cut/fill line within tolerance?"""
    zones = wcc[["geometry"]].copy()
    if tolerance_m > 0:
        zones["geometry"] = zones.geometry.buffer(tolerance_m)
    hits = gpd.sjoin(zones, lines[["geometry"]], how="left", predicate="intersects")
    return hits["index_right"].notna().groupby(level=0).any()


def completeness_table(lines, wcc, footprint, gns_extent):
    """Tabulate both directions of the comparison at every tolerance."""
    total_gns_m = lines.length.sum()
    in_extent = wcc.loc[wcc.intersects(gns_extent)]

    rows = []
    for tolerance in TOLERANCES_M:
        within_m = gns_length_within(lines, footprint, tolerance).sum()
        matched = wcc_polygons_matched(in_extent, lines, tolerance)
        rows.append(
            {
                "tolerance_m": tolerance,
                "gns_cut_fill_km": total_gns_m / 1000,
                "gns_within_wcc_km": within_m / 1000,
                "gns_within_wcc_pct": 100 * within_m / total_gns_m,
                "wcc_polygons_in_gns_extent": len(in_extent),
                "wcc_polygons_with_gns_line": int(matched.sum()),
                "wcc_polygons_with_gns_line_pct": 100 * matched.mean(),
            }
        )
    return pd.DataFrame(rows)


def describe(lines, cut, fill, wcc, gns_extent, table):
    """Print the inputs and both directions of the comparison."""
    outside = (~wcc.intersects(gns_extent)).sum()

    print(RULE)
    print(
        f"GNS cut/fill lines: {len(lines):,} lines, {lines.length.sum() / 1000:,.1f} km"
    )
    print(f"WCC cut polygons:   {len(cut):,}, {cut.area.sum() / 1e6:,.2f} km2")
    print(f"WCC fill polygons:  {len(fill):,}, {fill.area.sum() / 1e6:,.2f} km2")
    print(
        f"WCC polygons outside the GNS mapping extent: {outside:,} "
        "(left out of the WCC -> GNS direction)"
    )

    print(RULE)
    print("Tolerance   GNS length near WCC      WCC polygons with a GNS line")
    for row in table.itertuples():
        print(
            f"  {row.tolerance_m:>4.0f} m   "
            f"{row.gns_within_wcc_km:>6.1f} km ({row.gns_within_wcc_pct:>5.1f}%)   "
            f"{row.wcc_polygons_with_gns_line:>4} of "
            f"{row.wcc_polygons_in_gns_extent} "
            f"({row.wcc_polygons_with_gns_line_pct:>5.1f}%)"
        )
    print(
        "\n  GNS length far from any WCC polygon is earthworked ground the council"
        "\n  record does not hold -- or a GNS line that is not an earthwork."
    )


def plot_comparison(lines, cut, fill, footprint, gns_extent):
    """Map the WCC polygons with GNS lines coloured by whether WCC holds them."""
    near = footprint.buffer(MAP_TOLERANCE_M)
    matched = lines.geometry.intersection(near)
    unmatched = lines.geometry.difference(near)

    fig, ax = plt.subplots(figsize=(7.0, 9.0))

    cut.plot(ax=ax, color=WCC_CUT_COLOUR, linewidth=0, alpha=0.7, zorder=2)
    fill.plot(ax=ax, color=WCC_FILL_COLOUR, linewidth=0, alpha=0.7, zorder=2)
    gpd.GeoSeries(unmatched[~unmatched.is_empty], crs=lines.crs).plot(
        ax=ax, color=UNMATCHED_COLOUR, linewidth=0.6, zorder=3
    )
    gpd.GeoSeries(matched[~matched.is_empty], crs=lines.crs).plot(
        ax=ax, color=MATCHED_COLOUR, linewidth=0.6, zorder=4
    )

    extent = gpd.GeoDataFrame(geometry=[gns_extent], crs=lines.crs)
    style_basemap_ax(ax, extent)

    handles = [
        Patch(facecolor=WCC_CUT_COLOUR, alpha=0.7, label="WCC cut area"),
        Patch(facecolor=WCC_FILL_COLOUR, alpha=0.7, label="WCC fill area"),
        Line2D(
            [],
            [],
            color=MATCHED_COLOUR,
            label=f"GNS cut/fill line, within {MAP_TOLERANCE_M:.0f} m of WCC",
        ),
        Line2D(
            [],
            [],
            color=UNMATCHED_COLOUR,
            label="GNS cut/fill line, not in the WCC record",
        ),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=7, framealpha=0.9)

    ax.set_title("WCC earthworks record against GNS SLIDE cut/fill lines", fontsize=10)
    ax.set_xlabel(
        "Wellington City Council earthmoving cut and fill areas (CC BY-ND 4.0); "
        "GNS Science, SLIDE geomorphic mapping (CC BY 4.0). Internal use only.",
        fontsize=6,
    )
    return fig


def main():
    print("Reading the GNS SLIDE geomorphic lines and the WCC earthworks ...")
    morphology = get_gns_slide_morphology()
    cut = get_wcc_cut_areas()
    fill = get_wcc_fill_areas()

    lines = morphology.loc[morphology["Type"] == GNS_CUT_FILL_TYPE].reset_index(
        drop=True
    )
    if lines.empty:
        print(f"\nNo '{GNS_CUT_FILL_TYPE}' features in the GNS layer.")
        return

    wcc = pd.concat(
        [cut.assign(kind="cut"), fill.assign(kind="fill")], ignore_index=True
    )
    wcc = gpd.GeoDataFrame(wcc, geometry="geometry", crs=constants.DEFAULT_CRS)
    footprint = wcc.union_all()

    # GNS mapped the whole of urban Wellington City, not only where it found
    # earthworks, so the extent of all its features is the area it looked at.
    gns_extent = box(*morphology.total_bounds)

    table = completeness_table(lines, wcc, footprint, gns_extent)
    describe(lines, cut, fill, wcc, gns_extent, table)

    TAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.round(2).to_csv(TAB_PATH, index=False)

    fig = plot_comparison(lines, cut, fill, footprint, gns_extent)
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_PATH, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {TAB_PATH}")
    print(f"Wrote {FIG_PATH}")


if __name__ == "__main__":
    main()
