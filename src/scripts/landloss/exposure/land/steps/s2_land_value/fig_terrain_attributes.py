"""Map the two terrain attributes that drive the Phase 2 land value modifier.

Draws one point per address in two panels -- slope in degrees, and topographic
position in metres -- from the terrain attributes s1_build_terrain_attributes.py
samples off the LINZ DEM.

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/fig_terrain_attributes.py

What the figure is for is checking that the two attributes describe the ground
before they are allowed to move anybody's land value. Slope should pick out the
Wellington town belt, the Ngauranga gorge and the Eastern Hutt hills, and should
sit near zero across the Hutt Valley floor, Petone and the Porirua basin.
Topographic position should show the valley floors as a broad negative field
with the terraces, spurs and ridgelines standing out of it. If the two panels
disagree with the coastline and the contours a Wellingtonian carries in their
head, the DEM read or the window is wrong and nothing downstream is worth
looking at.

The two panels are coloured differently on purpose. Slope starts at zero and
only goes up, so it takes a sequential colourmap. Topographic position is signed
-- its whole meaning is whether an address stands above the land around it or
sits below it -- so it takes a diverging colourmap held symmetric about zero. A
sequential ramp would put the zero crossing at whatever colour the data happened
to make it, and the one thing the panel exists to show would be the one thing it
hid.

The whole study area is 59 by 54 km, at which size a suburb is a few pixels.
Pass ``--ta`` to draw one territorial authority instead, zoomed to it, or
``--ta all`` to write one figure per authority:

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/fig_terrain_attributes.py --ta all

As in fig_land_value_map.py, a per-authority map is framed on where its
addresses are rather than on its boundary, and the colour limits come from the
whole study area rather than from the authority being drawn, so that a slope is
the same colour on every map in the set and the four can be compared side by
side.

Reads the terrain attributes written by s1_build_terrain_attributes.py and does
not rebuild them, so run that first. Fetching and differencing a DEM from inside
a figure script is a slow surprise, and it is not this script's job. Pass
--extent to choose the extent drawn; it defaults to EXTENT in the config.py
beside this script.

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
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.exposure.land.land_value import SLOPE_COLUMN, TOPOGRAPHIC_POSITION_COLUMN
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
FIG_STEM = "terrain-attributes"

WORK_DIR = TEMP_DIR / "exposure"
TERRAIN_STEM = "terrain-by-address"

# The script that owns the DEM read, named in the refusal below so that a run
# against a missing input says what to run rather than what went wrong.
BUILDER = "s1_build_terrain_attributes.py"
BUILDER_PATH = "src/scripts/landloss/exposure/land/steps/s2_land_value/" + BUILDER

BOUNDARY_COLOUR = "#333333"

# s1_build_terrain_attributes.py writes the address id, the two attributes and
# the point, and nothing else -- terrain is a property of the ground, not of a
# council -- so --ta tags the addresses here instead of expecting the column.
TA_COLUMN = "territorial_authority"

# Colour limits are taken at this quantile rather than at the extremes, because
# a handful of cliff cells would otherwise compress every ordinary section into
# the bottom of the ramp. Addresses beyond the limit take the end colour, which
# is what the arrow on the colour bar says.
ROBUST_QUANTILE = 0.98

# The two panels, in the order they are drawn. Each one says how its attribute
# is coloured; everything else about them is deliberately identical, because the
# figure is read by comparing one against the other.
PANELS = (
    {
        "column": SLOPE_COLUMN,
        "title": "Slope",
        "label": "Slope (degrees)",
        # Sequential, perceptually uniform and colour-vision safe, reversed so
        # that the steep addresses are the dark ones. On a pale basemap the dark
        # end is the legible end, and steep land is what the panel is for.
        "colourmap": "magma_r",
        "diverging": False,
        # Slope is bounded below at zero by definition, so the ramp starts there
        # rather than at the flattest address; otherwise the Hutt Valley floor
        # would use half the colourmap to show a tenth of a degree. Only the top
        # of the ramp is robust, hence an arrow on that end alone.
        "floor": 0.0,
        "extend": "max",
        # The width used when every value is all but identical, which would
        # otherwise normalise to a zero-width range.
        "min_span": 1.0,
    },
    {
        "column": TOPOGRAPHIC_POSITION_COLUMN,
        "title": "Topographic position (above, below the surrounding land)",
        "label": "Topographic position (m)",
        # Diverging, held symmetric about zero by build_norm. Red above the
        # surrounding land, blue below it, pale at the crossing; red-blue is the
        # diverging pair that survives the common colour vision deficiencies.
        "colourmap": "RdBu_r",
        "diverging": True,
        "floor": None,
        "extend": "both",
        "min_span": 1.0,
    },
)

# Address points are dense enough over a city that a marker of any real size
# fills in solid, so they are drawn small and slightly transparent; the pilot
# holds a few hundred, where the same marker would be invisible. Each marker is
# a little smaller than in fig_land_value_map.py because two panels share the
# width of that script's one.
MARKER_SIZE = 0.9
AOI_MARKER_SIZE = 3.0
# One territorial authority fills the panel at roughly a tenth of the width of
# the whole study area, so its addresses carry a marker between the two.
TA_MARKER_SIZE = 1.5
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

# The map furniture is sized for a panel about five inches across rather than
# for the seven-inch single panel fig_land_value_map.py draws.
ARROW_KWARGS = {"scale": 0.22, "label_size": 7}
SCALEBAR_KWARGS = {"font_size": 7}

# The figure is sized from the extent it draws rather than fixed, because the
# panels hold an equal aspect ratio: a fixed height leaves a wide extent like
# the pilot box floating in a band of white, and crushes a tall one. This is the
# width of the whole figure, the room the two panels give up to the margin
# between them, and the room the titles and colour bars need above and below.
FIGURE_WIDTH_IN = 11.0
PANEL_MARGIN_IN = 1.0
FURNITURE_HEIGHT_IN = 1.5
# Held between these so a long thin extent still produces a usable page.
MIN_FIGURE_HEIGHT_IN = 4.0
MAX_FIGURE_HEIGHT_IN = 9.5

DPI = 250
DECILE_STEP = 10
RULE = "-" * 72


def build_norm(values, panel):
    """Return the colour normalisation for one panel.

    Args:
        values: The attribute the colours come from. Passing the whole study
            area while drawing one territorial authority keeps a value the same
            colour on every map in the set; without it, Upper Hutt's gentlest
            slopes would take the same colour as Wellington's flattest land.
        panel: The entry in :data:`PANELS` being drawn. ``diverging`` holds the
            ramp symmetric about zero, so that the middle colour lands on zero
            and equal departures either side read equally strongly, which is
            what makes the sign of a topographic position legible; ``floor``
            pins the bottom of the ramp instead of taking it from the robust low
            quantile, and ``min_span`` is the width used when the values are all
            but identical.

    Returns:
        A :class:`matplotlib.colors.Normalize` for the panel.
    """
    min_span = panel["min_span"]
    finite = values.dropna()
    if finite.empty:
        # Nothing will be drawn, but the colour bar is still printed, and one
        # that put zero off centre would misread as a real result.
        if panel["diverging"]:
            return Normalize(vmin=-min_span / 2, vmax=min_span / 2)
        return Normalize(vmin=0.0, vmax=min_span)

    high = float(finite.quantile(ROBUST_QUANTILE))
    low = float(finite.quantile(1 - ROBUST_QUANTILE))

    if panel["diverging"]:
        # One limit either side of zero, so that the pale middle of the ramp is
        # exactly the point where an address stops standing above the land
        # around it and starts sitting below it.
        limit = max(abs(high), abs(low), min_span / 2)
        return Normalize(vmin=-limit, vmax=limit)

    low = low if panel["floor"] is None else panel["floor"]
    return Normalize(vmin=low, vmax=max(high, low + min_span))


def draw_panel(ax, terrain, panel, extent, study_areas, *, marker_size, norm):
    """Draw one attribute as coloured address points over a basemap.

    Addresses the DEM had no value for are left off this panel rather than off
    the figure, so an address that has a slope but no topographic position --
    which happens along the edge of the DEM, where the wider window runs out
    first -- still appears in the panel that can describe it.
    """
    values = terrain[panel["column"]].astype(float)
    drawable = terrain.loc[values.notna()]

    if not drawable.empty:
        # Ordered so that the emphatic addresses are drawn last and are not
        # buried under their neighbours where the points crowd: on the diverging
        # panel that is the addresses furthest from zero either way, on the
        # sequential one the steepest.
        present = values.loc[drawable.index]
        emphasis = present.abs() if panel["diverging"] else present
        drawable = drawable.loc[emphasis.sort_values().index]

        ax.scatter(
            drawable.geometry.x,
            drawable.geometry.y,
            c=values.loc[drawable.index],
            cmap=panel["colourmap"],
            norm=norm,
            s=marker_size,
            alpha=MARKER_ALPHA,
            linewidths=0,
            zorder=3,
        )

    if study_areas is not None:
        study_areas.boundary.plot(
            ax=ax, color=BOUNDARY_COLOUR, linewidth=0.7, linestyle="--", zorder=4
        )

    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs=ARROW_KWARGS,
        scalebar_kwargs=SCALEBAR_KWARGS,
    )

    bar = ax.figure.colorbar(
        ScalarMappable(norm=norm, cmap=panel["colourmap"]),
        ax=ax,
        orientation="horizontal",
        fraction=0.046,
        pad=0.02,
        extend=panel["extend"],
    )
    bar.set_label(panel["label"], fontsize=8)
    bar.ax.tick_params(labelsize=7)

    if study_areas is not None:
        ax.legend(
            handles=[
                Line2D(
                    [],
                    [],
                    color=BOUNDARY_COLOUR,
                    linewidth=0.7,
                    linestyle="--",
                    label="Territorial authority boundary",
                )
            ],
            loc="upper left",
            fontsize=7,
            framealpha=0.9,
        )

    ax.set_title(panel["title"], fontsize=10)


def figure_size(extent):
    """Return the figure size that suits the shape of the extent being drawn.

    The panels hold an equal aspect ratio, so a figure of fixed height leaves a
    wide extent -- the pilot box is twice as wide as it is tall -- floating in a
    band of white, and crushes a tall one.
    """
    minx, miny, maxx, maxy = extent.total_bounds
    width = maxx - minx
    shape = (maxy - miny) / width if width > 0 else 1.0

    panel_width = (FIGURE_WIDTH_IN - PANEL_MARGIN_IN) / len(PANELS)
    height = panel_width * shape + FURNITURE_HEIGHT_IN
    height = min(max(height, MIN_FIGURE_HEIGHT_IN), MAX_FIGURE_HEIGHT_IN)
    return (FIGURE_WIDTH_IN, height)


def plot_terrain(terrain, extent, study_areas, *, marker_size, reference=None, title):
    """Plot slope and topographic position side by side, and return the figure."""
    source = terrain if reference is None else reference

    fig, axes = plt.subplots(
        ncols=len(PANELS), figsize=figure_size(extent), layout="constrained"
    )

    for ax, panel in zip(axes, PANELS, strict=True):
        draw_panel(
            ax,
            terrain,
            panel,
            extent,
            study_areas,
            marker_size=marker_size,
            norm=build_norm(source[panel["column"]].astype(float), panel),
        )

    fig.suptitle(title, fontsize=11)
    return fig


def describe(terrain):
    """Print the deciles, so the figure can be checked against numbers."""
    slope = terrain[SLOPE_COLUMN].astype(float)
    position = terrain[TOPOGRAPHIC_POSITION_COLUMN].astype(float)

    print(RULE)
    print(f"Addresses read            : {len(terrain):,}")
    print(f"Without a slope           : {int(slope.isna().sum()):,}")
    print(f"Without a topo position   : {int(position.isna().sum()):,}")

    above = int((position > 0).sum())
    below = int((position < 0).sum())
    print(f"Above surrounding land    : {above:,}")
    print(f"Below surrounding land    : {below:,}")
    print()

    print(f"{'Decile':<10}{'Slope (deg)':>16}{'Topo position (m)':>20}")
    for percent in range(0, 101, DECILE_STEP):
        quantile = percent / 100
        print(
            f"{f'p{percent}':<10}"
            f"{slope.quantile(quantile):>16.1f}"
            f"{position.quantile(quantile):>20.1f}"
        )


def with_territorial_authority(terrain, study_areas):
    """Tag every address with the authority it falls in, unless it is tagged already.

    The terrain attributes come out of s1 carrying the address id, the two
    derivatives and the point, because which council an address is in has
    nothing to do with what the ground under it does. --ta needs the tag, so it
    is taken here off the packaged boundaries rather than by reading the whole
    valued address layer back in for one column.
    """
    if TA_COLUMN in terrain.columns:
        return terrain

    print("Tagging   : addresses by territorial authority, from the boundaries")
    tagged = terrain.sjoin(
        study_areas[["name", "geometry"]], how="left", predicate="within"
    )
    # An address on a shared boundary can match two authorities and come back
    # twice; the first is as good as the second, and a duplicated point would
    # otherwise be drawn and counted twice.
    tagged = tagged.loc[~tagged.index.duplicated(keep="first")]
    tagged = tagged.drop(
        columns=[column for column in ("index_right",) if column in tagged.columns]
    )
    return tagged.rename(columns={"name": TA_COLUMN})


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


def draw_one_ta(terrain, study_areas, name, out=None):
    """Draw and write the figure for one territorial authority, and return its path.

    The colour limits come from the whole study area rather than from this
    authority, so that a slope reads as the same colour on every map in the set.
    """
    boundary = study_areas.loc[study_areas["name"] == name]
    subset = terrain.loc[terrain[TA_COLUMN] == name]

    print(RULE)
    print(f"{name}")

    if subset.empty:
        print("  No addresses with terrain in this authority; nothing drawn.")
        return None

    fig = plot_terrain(
        subset,
        ta_extent(subset),
        boundary,
        marker_size=TA_MARKER_SIZE,
        reference=terrain,
        title=f"Terrain attributes by address — {name}",
    )
    describe(subset)

    out = out or FIG_DIR / f"terrain-attributes-{ta_slug(name)}.png"
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
        "--terrain",
        type=Path,
        default=None,
        help=(
            f"The terrain attributes from {BUILDER}. Defaults to "
            f"{WORK_DIR / TERRAIN_STEM}<suffix>.geoparquet, where <suffix> is "
            "extent_suffix(extent)."
        ),
    )
    parser.add_argument(
        "--ta",
        default=None,
        help=(
            "Draw one territorial authority, zoomed to its addresses, e.g. "
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
    terrain_path = args.terrain or WORK_DIR / f"{TERRAIN_STEM}{suffix}.geoparquet"
    out = args.out or FIG_DIR / f"{FIG_STEM}{suffix}.png"

    print(RULE)
    print(f"Repo root : {REPO_ROOT}")
    print(f"Reading   : {terrain_path}")

    # Refused rather than rebuilt. Rebuilding would mean fetching a DEM from
    # inside a figure script, which is a slow surprise; s1 is the step that owns
    # that read, and this is the same stance fig_land_value_map.py takes.
    if not terrain_path.exists():
        print(f"\nNo terrain attributes at {terrain_path}.")
        print(
            f"Run {BUILDER} first:\n"
            f"  uv run --frozen python {BUILDER_PATH}"
            + (
                ""
                if is_full_extent(extent)
                else f'\n  with EXTENT = "{extent}" in the config.py beside it'
            )
        )
        return 1

    terrain = gpd.read_parquet(terrain_path)

    if terrain.empty:
        print("\nThe terrain attributes are empty; there is nothing to draw.")
        return 1

    missing = [
        panel["column"] for panel in PANELS if panel["column"] not in terrain.columns
    ]
    if missing:
        print(f"\n{terrain_path} carries no {', '.join(missing)} column.")
        print(f"Columns found: {', '.join(terrain.columns)}")
        return 1

    study_areas = get_study_areas(constants.DEFAULT_CRS)

    if args.ta:
        names = resolve_ta_names(args.ta, study_areas)
        if not names:
            known = ", ".join(sorted(study_areas["name"]))
            print(f"\n{args.ta!r} is not in the study area. Available: {known}")
            return 1

        tagged = with_territorial_authority(terrain, study_areas)
        written = [
            draw_one_ta(
                tagged, study_areas, name, args.out if len(names) == 1 else None
            )
            for name in names
        ]

        print(RULE)
        # An authority with no terrain-tagged addresses draws nothing and comes
        # back as None, which is reported above rather than as a written file.
        for path in [path for path in written if path is not None]:
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

    fig = plot_terrain(
        terrain,
        view,
        boundaries,
        marker_size=marker_size,
        title="Terrain attributes by address",
    )
    describe(terrain)

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
