"""Map the observed Canterbury land damage state, one panel per event.

Three map panels across the Christchurch extent, one for each earthquake in the
sequence, with every insured property drawn at its own location and coloured by
the land damage state surveyed on the ground after that event. Reading the three
together is the point: it shows where the damage fell each time, how much of the
city was hit twice, and how far the February 2011 damage reached beyond what
September 2010 had already done.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/report/fig_land_damage_maps.py

Reads the database built by
``src/scripts/landloss/vul/liquefaction/land/steps/s1_ces_observed_damage/gen_observed_damage_db.py``
through ``landloss.io.versioned_store.read_vul`` (T: by default, or a local
cache/working copy depending on configuration). That database is masked to flat
land, so the hills around Lyttelton and the Port Hills are empty here because no
property in them is carried, not because none was damaged.

The basemap is fetched by ``contextily`` on each run, so this needs network
access.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io import versioned_store
from landloss.io.area_of_interest import CHRISTCHURCH
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.liquefaction.land.steps.s1_ces_observed_damage.gen_observed_damage_db import (
    DAMAGE_STATES,
    UNKNOWN,
)

FIG_DIR = REPORT_DIR / "vul" / "liquefaction" / "land" / "fig"
FIG_NAME = "land-damage-states-by-event.png"

# Written by ../steps/s1_ces_observed_damage/gen_observed_damage_db.py through
# landloss.io.versioned_store.save_vul, not a hardcoded T: path.
DB_SUB_DIRS = ["ces_observed_damage"]
DB_NAME = "observed_damage_db.parquet"

DPI = 200

# The Christchurch extent is about four wide to three tall. The height is chosen
# so that three equal-aspect panels of that shape fill the row without leaving a
# band of white between the panels and the legend beneath them.
FIGSIZE = (13.5, 4.7)

STATE_COLUMN = "observed_land_damage_state"
CATEGORY_COLUMN = "observed_land_damage_category"
EVENT_COLUMN = "simple_event_name"

# A green to red ramp over the six states. States 1, 3, 4 and 6 keep the National
# Liquefaction Model's colours, so a panel from this study reads against one from
# that one; 2 and 5 fill the ramp in between, which that study's coarser bands
# did not need.
STATE_COLOURS = {
    1: "#3AB04A",
    2: "#A6D96A",
    3: "#FEE900",
    4: "#F8951D",
    5: "#D7301F",
    6: "#9D1C1F",
}

# Neither of these is a state. "Unknown" is a property the mapping team covered
# but could not grade; "not surveyed" is one no observation polygon reached at
# all. Both are grey, because the map should not imply a severity for either,
# and the second is lighter because it says less.
UNKNOWN_COLOUR = "#7F7F7F"
NOT_SURVEYED_COLOUR = "#D9D9D9"
NOT_SURVEYED_LABEL = "Not surveyed"

# Small and slightly translucent: at this many properties over a 56 km panel the
# points would otherwise merge into a solid block and hide their own density.
MARKER_SIZE = 0.9
MARKER_ALPHA = 0.7

EVENT_LABELS = {
    "darfield": "Darfield, September 2010",
    "chch_feb_2011": "Christchurch, February 2011",
    "chch_feb_2016": "Christchurch, February 2016",
}

RULE = "-" * 72


def get_extent():
    """Return the Christchurch extent as a frame, for the panels to be held to."""
    return gpd.GeoDataFrame(
        geometry=CHRISTCHURCH.to_geoseries(constants.DEFAULT_CRS),
        crs=constants.DEFAULT_CRS,
    )


def split_by_state(database):
    """Split one event's properties into the classes the map draws, worst last.

    Drawing order is the point of the ordering. The undamaged properties are the
    overwhelming majority, so anything drawn before them disappears underneath;
    going up the scale puts the severe damage on top, where it can be seen.

    Args:
        database: The rows for one event.

    Returns:
        A list of ``(label, colour, rows)``, in the order they should be drawn.
    """
    states = database[STATE_COLUMN]
    categories = database[CATEGORY_COLUMN]

    layers = [
        (NOT_SURVEYED_LABEL, NOT_SURVEYED_COLOUR, database.loc[categories.isna()]),
        (UNKNOWN, UNKNOWN_COLOUR, database.loc[categories == UNKNOWN]),
    ]
    layers += [
        (f"{state} {label}", STATE_COLOURS[state], database.loc[states == state])
        for state, label in DAMAGE_STATES.items()
    ]
    return layers


def describe(database):
    """Print what the database holds, so a bad join is caught before plotting."""
    print(RULE)
    print(f"Loaded {len(database):,} property-event rows")

    header = "".join(f"{label:>8}" for label in ("1", "2", "3", "4", "5", "6"))
    print(f"\n  {'Event':<30} {'Rows':>8}{header}{'Unknown':>9}{'None':>9}")

    for event, label in EVENT_LABELS.items():
        subset = database.loc[database[EVENT_COLUMN] == event]
        if subset.empty:
            continue

        counts = subset[STATE_COLUMN].value_counts()
        states = "".join(f"{int(counts.get(state, 0)):>8,}" for state in DAMAGE_STATES)
        unknown = int((subset[CATEGORY_COLUMN] == UNKNOWN).sum())
        unsurveyed = int(subset[CATEGORY_COLUMN].isna().sum())
        print(f"  {label:<30} {len(subset):>8,}{states}{unknown:>9,}{unsurveyed:>9,}")


def draw_event(ax, database, extent, title):
    """Draw one event's properties, coloured by land damage state, over a basemap.

    Args:
        ax: The axes to draw on.
        database: The rows for this event.
        extent: The extent the panel is held to, in NZTM.
        title: The panel title.
    """
    for _, colour, rows in split_by_state(database):
        if rows.empty:
            continue
        rows.plot(
            ax=ax,
            color=colour,
            markersize=MARKER_SIZE,
            alpha=MARKER_ALPHA,
            linewidth=0,
            zorder=3,
        )

    # The panels are small, so the default north arrow and scale bar crowd them.
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.18, "label_size": 6},
        scalebar_kwargs={"font_size": 6},
    )
    ax.set_title(f"{title}\n({len(database):,} properties)", fontsize=10)


def add_legend(fig, database):
    """Put one shared key under the three panels, rather than one on each.

    The counts are over every event together, so the key doubles as a summary of
    the database and the panels are left to show where the damage fell.
    """
    handles = [
        Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markersize=5,
            markerfacecolor=colour,
            markeredgecolor="none",
            label=f"{label} ({len(rows):,})",
        )
        for label, colour, rows in split_by_state(database)
    ]
    fig.legend(
        handles=handles,
        title="Observed land damage state",
        loc="lower center",
        ncol=4,
        fontsize="small",
        title_fontsize="small",
        frameon=False,
    )


def plot_land_damage_maps(database):
    """Draw the three panel map figure.

    Args:
        database: Every property-event row, for all three events.

    Returns:
        The figure, ready to save.
    """
    extent = get_extent()
    fig, axs = plt.subplots(nrows=1, ncols=3, figsize=FIGSIZE)

    for (event, label), ax in zip(EVENT_LABELS.items(), axs, strict=True):
        draw_event(ax, database.loc[database[EVENT_COLUMN] == event], extent, label)

    add_legend(fig, database)
    fig.suptitle("Observed land damage, Canterbury earthquake sequence")

    # Room at the bottom for the legend and at the top for the suptitle, both of
    # which sit outside the panels and so are invisible to tight_layout.
    fig.tight_layout(rect=(0, 0.13, 1, 0.92))
    return fig


def main():
    database = versioned_store.read_vul(fname=DB_NAME, sub_dirs=DB_SUB_DIRS)
    database = database.to_crs(constants.DEFAULT_CRS)

    describe(database)

    fig = plot_land_damage_maps(database)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / FIG_NAME
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
