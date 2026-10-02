"""Map the modelled land rate per square metre across the study area.

Draws one point per address, coloured by ``land_rate_nzd_per_m2`` from
s4_estimate_land_value.py, over the four territorial authority boundaries.

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/fig_land_value_map.py

What the map is for is checking the shape of the model, not reading a value off
an address. In Phase 1 the rate an address takes depends on exactly two things --
which territorial authority it is in, and whether the National Liquefaction
Model calls its land flat or hill -- so the surface is piecewise constant with at
most eight distinct values. The map is therefore drawn with one colour per
distinct rate rather than with quantile bins, because binning a surface that
takes eight values into five classes invents boundaries that are not in the
model. Seeing the flat land pick itself out of the hills, and each city step to
its own level, is the check worth making; anything smoother than that would be a
bug. The continuous fallback exists for later phases, when terrain, accessibility
and amenity give every address its own rate.

The whole study area is 59 by 54 km, at which size a suburb is a few pixels. Pass
``--ta`` to draw one territorial authority instead, zoomed to it, or ``--ta all``
to write one figure per authority:

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/fig_land_value_map.py --ta all

A per-authority map is framed on where its addresses are rather than on its
boundary, because Wellington City's boundary runs west over Makara and Ohariu to
the open coast -- most of its area, a few hundred of its 102,000 addresses --
and framing on it would put the city in a corner. The boundary is still drawn,
and runs off the page where that happens. The colour classes come from the whole
study area rather than from the authority being drawn, so a rate is the same
colour on every map in the set and the four can be compared side by side; only
the classes present in an authority reach its legend.

Reads the valued addresses written by s4_estimate_land_value.py and does not
rebuild them, so run that first. Pass --extent to choose the extent drawn; it
defaults to EXTENT in the config.py beside this script.

Needs no API key: everything it reads is already on disk, apart from the basemap
tiles, which are what makes a zoomed-in run take a minute or two.
"""

import argparse
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io.area_of_interest import (
    EXTENTS,
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
    is_full_extent,
)
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR, TEMP_DIR

# Suburb and place names are macronised, which the default cp1252 Windows console
# cannot encode. See the note in s4_estimate_land_value.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Any directory named fig is gitignored, so the figure is regenerated rather
# than committed and this script is the record of how it was made.
FIG_DIR = REPORT_DIR / "exposure" / "land" / "land-value" / "fig"
# Both names carry extent_suffix(extent), so figures and inputs over different
# extents sit side by side.
FIG_STEM = "land-value-rate"

WORK_DIR = TEMP_DIR / "exposure"
VALUED_STEM = "land-value-by-address"

RATE_COLUMN = "land_rate_nzd_per_m2"

# Above this many distinct rates the per-value legend stops being readable and
# the script falls back to quantile classes. Eight is what Phase 1 produces, so
# the fallback is dormant until a later phase adds within-cohort variation.
MAX_DISCRETE_CLASSES = 12
QUANTILE_CLASSES = 5

# Sequential, perceptually ordered and colour-vision safe, so the classes read in
# the right order in greyscale and in print.
COLOURMAP = "viridis"
BOUNDARY_COLOUR = "#333333"

# Address points are dense enough over a city that a marker of any real size
# fills in solid, so they are drawn small and slightly transparent; the pilot
# holds a few hundred, where the same marker would be invisible.
MARKER_SIZE = 1.2
AOI_MARKER_SIZE = 4.0
# One territorial authority fills the page at roughly a tenth of the width of the
# whole study area, so its addresses carry a marker between the two.
TA_MARKER_SIZE = 2.0
MARKER_ALPHA = 0.85

# How far outside the framed area a per-authority map is drawn, as a fraction of
# its width. Without it the coastline sits hard against the frame and the
# harbour, which is what makes a Wellington map readable, is cropped away.
TA_MARGIN = 0.04

# A per-authority map is framed on where the addresses are, not on the authority
# boundary. Wellington City's boundary runs out over Makara and Ohariu to the
# west coast, which is most of its area and a few hundred of its 102,000
# addresses; framing on the boundary puts the city in a corner. This is the
# share of addresses trimmed from each edge before the frame is taken, so the
# map covers where people actually live and the boundary runs off the page.
TA_FRAME_TRIM = 0.01

DPI = 250
RULE = "-" * 72


def classify_rates(valued, reference=None):
    """Group the addresses into the colour classes the map draws.

    Args:
        valued: Addresses carrying :data:`RATE_COLUMN`, the ones to be drawn.
        reference: Optionally, the addresses whose rates define the classes.
            Passing the whole study area while drawing one territorial authority
            keeps a rate the same colour on every map in the set; without it,
            each authority's cheapest class would take the bottom of the
            colourmap and Upper Hutt's hill land would look like Wellington's.
            A class the subset has no addresses in comes back empty rather than
            being dropped, so the colours stay aligned to the full class list.

    Returns:
        A list of (label, subset) pairs, cheapest class first, and a bool saying
        whether the classes are distinct modelled values rather than bins.
    """
    rates = valued[RATE_COLUMN]
    reference_rates = rates if reference is None else reference[RATE_COLUMN]
    distinct = sorted(reference_rates.dropna().unique())

    if len(distinct) <= MAX_DISCRETE_CLASSES:
        # One class per modelled value. The label is the value itself, which is
        # the honest thing to put in the legend when the model only produces a
        # handful of them.
        classes = [(f"${rate:,.0f}/m2", valued.loc[rates == rate]) for rate in distinct]
        return classes, True

    # Quantile bins, so each class holds roughly the same number of addresses
    # whatever the distribution turns out to look like. duplicates="drop" guards
    # the case where a value is common enough to span two bin edges. The edges
    # come from the reference so that, as above, one rate keeps one colour across
    # a set of maps.
    edges = pd.qcut(reference_rates, QUANTILE_CLASSES, duplicates="drop")
    bins = pd.cut(rates, edges.cat.categories.left.union(edges.cat.categories.right))
    classes = [
        (
            f"${interval.left:,.0f} to ${interval.right:,.0f}/m2",
            valued.loc[bins == interval],
        )
        for interval in bins.cat.categories
    ]
    return classes, False


def legend_label(label):
    """Escape a class label for matplotlib, which reads paired dollars as maths.

    Two dollar signs in one string delimit mathtext, so "$683 to $823/m2" drew as
    an italic "683to823/m2" with the dollars eaten and the range unreadable. A
    single unpaired dollar happens to render, which is why this only appeared
    once the quantile classes came into use. Escaping happens here rather than in
    the label itself so that the same label still prints cleanly to the terminal.
    """
    return label.replace("$", r"\$")


def plot_rates(valued, extent, study_areas, *, marker_size, reference=None, title=None):
    """Plot the addresses coloured by modelled land rate, over a basemap."""
    classes, discrete = classify_rates(valued, reference)

    # Sampled across the full colourmap so the cheapest and dearest classes take
    # its ends, whatever the class count turns out to be.
    colours = plt.get_cmap(COLOURMAP)(
        [index / max(len(classes) - 1, 1) for index in range(len(classes))]
    )

    fig, ax = plt.subplots(figsize=(7.0, 7.4))

    # Cheapest first, so the dearest land is drawn on top where the classes
    # overlap at a suburb edge and is not buried under its neighbours.
    for (_, subset), colour in zip(classes, colours, strict=True):
        if not subset.empty:
            subset.plot(
                ax=ax,
                color=colour,
                markersize=marker_size,
                alpha=MARKER_ALPHA,
                linewidth=0,
                zorder=3,
            )

    if study_areas is not None:
        study_areas.boundary.plot(
            ax=ax, color=BOUNDARY_COLOUR, linewidth=0.7, linestyle="--", zorder=4
        )

    style_basemap_ax(ax, extent)

    # Only the classes this map actually drew. A per-authority map shares its
    # class list with the whole study area so the colours line up, which would
    # otherwise put four rates in the legend that appear nowhere on the page.
    handles = [
        Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markersize=5,
            markerfacecolor=colour,
            markeredgecolor="none",
            label=legend_label(label),
        )
        for (label, subset), colour in zip(classes, colours, strict=True)
        if not subset.empty
    ]
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

    legend_title = "Land rate" if discrete else "Land rate (quantile classes)"
    ax.legend(
        handles=handles,
        loc="upper left",
        fontsize=7,
        framealpha=0.9,
        title=legend_title,
    )

    ax.set_title(title or "Modelled land rate per square metre", fontsize=10)
    return fig, classes


def describe(valued, classes):
    """Print what is being drawn, so the map can be checked against numbers."""
    rates = valued[RATE_COLUMN]

    print(RULE)
    print(f"Addresses plotted : {len(valued):,}")
    print(f"Rate range        : ${rates.min():,.0f} to ${rates.max():,.0f} per m2")
    print(f"Median rate       : ${rates.median():,.0f} per m2")
    print()
    print(f"{'Class':<28}{'Addresses':>12}{'Share':>9}")
    for label, subset in classes:
        # A class can be empty when the class list came from the whole study area
        # and only one authority is being drawn; it is not worth a row of zeroes.
        if subset.empty:
            continue
        share = 100 * len(subset) / len(valued)
        print(f"{label:<28}{len(subset):>12,}{share:>8.1f}%")


def resolve_ta_names(wanted, study_areas):
    """Turn the --ta argument into the list of authority names to draw."""
    names = sorted(study_areas["name"])
    if wanted.strip().lower() == "all":
        return names
    return [name for name in names if name.lower() == wanted.strip().lower()]


def ta_slug(name):
    """Turn an authority name into a file name fragment, e.g. wellington-city."""
    return name.lower().replace(" ", "-")


def ta_extent(subset):
    """Return the map extent for one authority, framed on where its addresses are.

    The frame trims :data:`TA_FRAME_TRIM` of the addresses off each edge before
    taking the bounds, then pads by :data:`TA_MARGIN`. Framing on the authority
    boundary instead would put Wellington's city in one corner of a map that is
    mostly the Makara and Ohariu hills.
    """
    points = subset.geometry
    low, high = TA_FRAME_TRIM, 1 - TA_FRAME_TRIM
    minx, maxx = points.x.quantile(low), points.x.quantile(high)
    miny, maxy = points.y.quantile(low), points.y.quantile(high)

    pad = max(maxx - minx, maxy - miny) * TA_MARGIN
    return gpd.GeoDataFrame(
        geometry=[box(minx - pad, miny - pad, maxx + pad, maxy + pad)],
        crs=subset.crs,
    )


def draw_one_ta(valued, study_areas, name, out=None):
    """Draw and write the map for one territorial authority, and return its path.

    The colour classes come from the whole study area rather than from this
    authority, so that a rate reads as the same colour on every map in the set.
    """
    boundary = study_areas.loc[study_areas["name"] == name]
    subset = valued.loc[valued["territorial_authority"] == name]

    print(RULE)
    print(f"{name}")

    if subset.empty:
        print("  No valued addresses in this authority; nothing drawn.")
        return None

    fig, classes = plot_rates(
        subset,
        ta_extent(subset),
        boundary,
        marker_size=TA_MARKER_SIZE,
        reference=valued,
        title=f"Modelled land rate per square metre — {name}",
    )
    describe(subset, classes)

    out = out or FIG_DIR / f"land-value-rate-{ta_slug(name)}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extent",
        choices=["full", *EXTENTS],
        default=None,
        help=(
            "The extent to draw. Defaults to EXTENT in the config.py beside this "
            f"script ({config.EXTENT!r}), or to the full study area under --ta."
        ),
    )
    parser.add_argument(
        "--valued",
        type=Path,
        default=None,
        help=(
            f"The valued addresses from s4_estimate_land_value.py. Defaults to "
            f"{WORK_DIR / VALUED_STEM}<suffix>.geoparquet, where <suffix> is "
            "extent_suffix(extent)."
        ),
    )
    parser.add_argument(
        "--ta",
        default=None,
        help=(
            "Draw one territorial authority, zoomed to its boundary, e.g. "
            '--ta "Wellington City". Matched case insensitively. Pass "all" to '
            "write one figure per authority."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            f"Where to write the figure. Defaults to {FIG_DIR / FIG_STEM}"
            "<suffix>.png, where <suffix> is extent_suffix(extent). Ignored when "
            "--ta names more than one authority, which writes one file per "
            "authority."
        ),
    )
    args = parser.parse_args()

    if args.ta and args.extent not in (None, "full"):
        parser.error("--extent and --ta describe different extents; pass one or other.")

    extent = "full" if args.ta else (args.extent or config.EXTENT)
    suffix = extent_suffix(extent)
    valued_path = args.valued or WORK_DIR / f"{VALUED_STEM}{suffix}.geoparquet"
    out = args.out or FIG_DIR / f"{FIG_STEM}{suffix}.png"

    print(RULE)
    print(f"Repo root : {REPO_ROOT}")
    print(f"Reading   : {valued_path}")

    # Refused rather than rebuilt. Rebuilding would mean downloading the flatland
    # layer from inside a figure script, which is a slow surprise; s4 is the step
    # that owns that read.
    if not valued_path.exists():
        print(f"\nNo valued addresses at {valued_path}.")
        print(
            "Run s4_estimate_land_value.py first:\n"
            "  uv run --frozen python "
            "src/scripts/landloss/exposure/land/steps/s2_land_value/"
            "s4_estimate_land_value.py"
            + (
                ""
                if is_full_extent(extent)
                else f'\n  with EXTENT = "{extent}" in the config.py beside it'
            )
        )
        return 1

    valued = gpd.read_parquet(valued_path)

    if valued.empty:
        print("\nThe valued addresses are empty; there is nothing to draw.")
        return 1

    if RATE_COLUMN not in valued.columns:
        print(f"\n{valued_path} carries no {RATE_COLUMN} column.")
        print(f"Columns found: {', '.join(valued.columns)}")
        return 1

    study_areas = get_study_areas(constants.DEFAULT_CRS)

    if args.ta:
        names = resolve_ta_names(args.ta, study_areas)
        if not names:
            known = ", ".join(sorted(study_areas["name"]))
            print(f"\n{args.ta!r} is not in the study area. Available: {known}")
            return 1

        written = [
            draw_one_ta(
                valued, study_areas, name, args.out if len(names) == 1 else None
            )
            for name in names
        ]

        print(RULE)
        for path in written:
            print(f"Wrote {path}")
        return 0

    aoi = get_area_of_interest(extent)
    if aoi is not None:
        view = aoi.to_geoseries(constants.DEFAULT_CRS).to_frame("geometry")
        view = view.set_geometry("geometry")
        marker_size = AOI_MARKER_SIZE
        boundaries = None
    else:
        view = study_areas
        marker_size = MARKER_SIZE
        boundaries = study_areas

    fig, classes = plot_rates(valued, view, boundaries, marker_size=marker_size)
    describe(valued, classes)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
