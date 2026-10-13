"""Draw the fragility curves the urban slope model draws its polygons against.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_urban_slope_fragility/fig_urban_fragility_curves.py

The curves for review, on the model's own measure, site PGA in g (the project
lead, 2026-10-12). Where ``fig_urban_slope_model.py`` maps each polygon's
median, this draws the curves themselves:

- **No wall.** The localised curve at the mid rating of each Kingsbury zone,
  from the packaged ``urban-localised-fragility.csv``: a p15 and a p50 at
  zone 3 and at zone 5, run in straight lines in log PGA against the rating
  (``landloss.hazard.landslide.urban.fragility.localised_curve_pga_g``).
- **Wall under 2 m** and **wall 2 m and over.** The curve of each wall type,
  from the packaged ``retaining-wall-type-fragility.csv``, which holds the
  curve under 2 m; 2 m and over is that curve times the height factor.
- **p15 and p50.** Dashed horizontal lines at 0.15 and 0.5 on each curve
  panel, where each curve's two stored percentiles sit.
- **At the study's demand.** Each curve's probability of failure at the two
  ends of the study's 2,500-year site PGA range, one row per curve: the
  no-wall curves first, in the colours of the no-wall panel, then each wall
  type under 2 m and 2 m and over together.

Every legend and the demand rows run weakest curve (lowest median) to
strongest. Every curve is drawn as the model holds it before the polygon's
own adjustments: the medium rate setting, no topographic amplification and a
wall of unknown position. In the model a polygon's median is divided by its
amplification factor (1.3 off NLM flatland, 1.0 on it) and multiplied by
the rate factor, and a
fill wall's median is 0.85 times the drawn one and a cut wall's 1.15 times.

Reads only the packaged tables, so it runs without any step having been run.
``config.py`` beside it names the extent, which only labels the file. The
figure, ``urban-fragility-curves``, goes under
``report/hazard/landslide/urban-slope-model/fig/``, which is gitignored.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import fragility, wall_type_fragility
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import config
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-model" / "fig"
FIG_STEM = "urban-fragility-curves"
DPI = 200

# The site PGA axis the curves are drawn over, g.
PGA_AXIS_G = np.logspace(np.log10(0.05), np.log10(10.0), 300)

# The study's site PGA at 2,500 years over the four territorial authorities, g:
# the least and greatest cell of the TS1170.5 PGA on shaking step 2's site
# class grid (2026-10-12), as fig_urban_slope_model.py marks it.
STUDY_PGA_RANGE_G = (0.93, 2.02)
STUDY_COLOUR = "#fdae61"

# One colour per wall type, in WALL_TYPES order; weaker types warm.
WALL_TYPE_COLOURS = {
    "brick_rock": "#d7191c",
    "reinforced_concrete_pre_1992": "#fdae61",
    "crib_gabion": "#a6611a",
    "timber_pole_pre_1992": "#e7298a",
    "concrete_block": "#2c7bb6",
    "timber_pole_post_1992": "#1b7837",
    "garden_timber": "#7f7f7f",
    "reinforced_concrete_post_1992": "#1a1a1a",
}
ZONE_CMAP = "viridis_r"

NO_WALL = "no_wall"
SHORTER, TALLER = wall_type_fragility.HEIGHT_CLASSES
HEIGHT_LABELS = {SHORTER: "under 2 m", TALLER: "2 m and over"}
HEIGHT_STYLES = {SHORTER: "-", TALLER: (0, (3, 1.5))}

RULE = "-" * 72


def zone_mid_ratings():
    """Return the mid rating of each Kingsbury zone, keyed by its rank."""
    edges = (0.0, *susceptibility.ZONE_BREAKS, float(susceptibility.MAX_RATING))
    return {
        rank: 0.5 * (edges[i] + edges[i + 1])
        for i, rank in enumerate(susceptibility.ZONE_RANKS)
    }


def zone_colour(rank):
    """Return the no-wall panel's colour for a Kingsbury zone."""
    ranks = susceptibility.ZONE_RANKS
    return plt.get_cmap(ZONE_CMAP)((rank - ranks[0]) / (ranks[-1] - ranks[0]))


def curves_table(wall_table, localised_table):
    """Collect every curve drawn, one row each, weakest first within a group.

    A wall type gives two rows, the table's curve under 2 m and that curve
    times the height factor for 2 m and over; ``strength`` is the type's
    median under 2 m, so the two rows of a type sort together.
    """
    labels = (
        pd.read_csv(wall_type_fragility.WALL_TYPES_PATH)
        .set_index("wall_type")["label"]
        .to_dict()
    )
    mids = zone_mid_ratings()
    theta, beta = fragility.localised_curve_pga_g(
        np.array(list(mids.values())), localised_table
    )
    rows = [
        {
            "group": NO_WALL,
            "key": f"zone {rank}",
            "label": (
                f"Zone {rank} {susceptibility.ZONE_LABELS[rank].lower()} "
                f"(rating {rating:.0f})"
            ),
            "theta_g": float(theta[i]),
            "beta": float(beta[i]),
            "zone": rank,
            "strength": float(theta[i]),
        }
        for i, (rank, rating) in enumerate(mids.items())
    ]
    for _, row in wall_table.iterrows():
        for height, factor in wall_type_fragility.HEIGHT_FACTORS.items():
            rows.append(
                {
                    "group": height,
                    "key": row["wall_type"],
                    "label": labels.get(row["wall_type"], row["wall_type"]),
                    "theta_g": float(row["theta"]) * factor,
                    "beta": float(row["beta"]),
                    "zone": np.nan,
                    "strength": float(row["theta"]),
                }
            )
    table = pd.DataFrame(rows)
    table["p15_g"] = table["theta_g"] * np.exp(
        wall_type_fragility.LOWER_Z * table["beta"]
    )
    for end, pga in zip(("low", "high"), STUDY_PGA_RANGE_G, strict=True):
        table[f"p_fail_at_{end}"] = fragility.lognormal_failure_probability(
            np.full(len(table), pga), table["theta_g"], table["beta"]
        )
    # The no-wall rows first, then the walls; weakest first in each.
    table["is_wall"] = table["group"] != NO_WALL
    return table.sort_values(["is_wall", "strength"], kind="stable").reset_index(
        drop=True
    )


def curve(theta_g, beta):
    """Evaluate a lognormal on the drawn PGA axis."""
    return fragility.lognormal_failure_probability(
        PGA_AXIS_G,
        np.full_like(PGA_AXIS_G, theta_g),
        np.full_like(PGA_AXIS_G, beta),
    )


def style_curve_ax(ax, *, title):
    """Mark the study range, the p15 and p50 levels, the log axis and labels."""
    ax.axvspan(*STUDY_PGA_RANGE_G, color=STUDY_COLOUR, alpha=0.25, lw=0)
    ax.text(
        STUDY_PGA_RANGE_G[0] * 1.03,
        0.02,
        "study site PGA,\n2,500 yr",
        fontsize=7,
        ha="left",
        va="bottom",
    )
    # The two percentiles every curve is stored by: p15 and p50.
    for level, name in ((0.15, "p15"), (0.5, "p50")):
        ax.axhline(level, color="#7f7f7f", linewidth=0.8, linestyle="--", zorder=0)
        ax.text(
            PGA_AXIS_G[-1] * 0.97,
            level + 0.01,
            name,
            fontsize=7,
            color="#7f7f7f",
            ha="right",
            va="bottom",
        )
    ax.set(
        xscale="log",
        xlim=(PGA_AXIS_G[0], PGA_AXIS_G[-1]),
        ylim=(0, 1),
        xlabel="site PGA (g)",
        ylabel="probability of failure",
    )
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
    ax.set_title(title, fontsize=9)


def no_wall_title(localised_table):
    """Name the two points the localised curve runs through."""
    points = "; ".join(
        f"rating {row.rating:g}: p15 {row.p15:g}, p50 {row.p50:g} g"
        for row in localised_table.itertuples()
    )
    return f"No wall - localised curve through two points\n({points})"


def draw_no_wall(ax, curves, localised_table):
    """Draw the localised curve at each zone's mid rating, weakest first."""
    rows = curves[curves["group"] == NO_WALL]
    for _, row in rows.iterrows():
        ax.plot(
            PGA_AXIS_G,
            curve(row["theta_g"], row["beta"]),
            color=zone_colour(row["zone"]),
            linewidth=1.5,
            label=(
                f"{row['label']}, p15 {row['p15_g']:.2f}, p50 {row['theta_g']:.2f} g, "
                f"beta {row['beta']:.2f}"
            ),
        )
    style_curve_ax(ax, title=no_wall_title(localised_table))
    ax.legend(fontsize=7, frameon=False, loc="upper left")


def draw_walls(ax, curves, *, height_class, title):
    """Draw each wall type's curve in one height class, weakest first."""
    rows = curves[curves["group"] == height_class]
    for _, row in rows.iterrows():
        ax.plot(
            PGA_AXIS_G,
            curve(row["theta_g"], row["beta"]),
            color=WALL_TYPE_COLOURS[row["key"]],
            linewidth=1.5,
            label=(
                f"{row['label']}, p15 {row['p15_g']:.2f}, p50 {row['theta_g']:.2f} g, "
                f"beta {row['beta']:.2f}"
            ),
        )
    style_curve_ax(ax, title=title)
    ax.legend(fontsize=7, frameon=False, loc="upper left")


def demand_row_label(row):
    """Name one demand row: the zone, or the wall type and its height class."""
    if row["group"] == NO_WALL:
        return f"No wall: {row['label']}"
    return f"{row['label']}, {HEIGHT_LABELS[row['group']]}"


def draw_at_demand(ax, curves):
    """Draw each curve's failure probability across the study's PGA range.

    The no-wall curves come first, in the no-wall panel's colours; then each
    wall type, weakest first, under 2 m (solid) beside 2 m and over (dashed).
    """
    ticks, labels, y = [], [], 0.0
    previous = None
    for _, row in curves.iterrows():
        is_wall = row["group"] != NO_WALL
        if previous is not None and row["key"] != previous["key"]:
            # A wide gap between no wall and the walls, a narrow one between
            # wall types; a zone's or a type's own rows sit together.
            y += 0.8 if is_wall != (previous["group"] != NO_WALL) else 0.35
        colour = WALL_TYPE_COLOURS[row["key"]] if is_wall else zone_colour(row["zone"])
        ax.plot(
            [row["p_fail_at_low"], row["p_fail_at_high"]],
            [y, y],
            color=colour,
            linewidth=2.5,
            linestyle=HEIGHT_STYLES[row["group"]] if is_wall else "-",
            solid_capstyle="round",
        )
        ax.plot(row["p_fail_at_low"], y, "o", color=colour, ms=4)
        ax.plot(row["p_fail_at_high"], y, "s", color=colour, ms=4)
        ticks.append(y)
        labels.append(demand_row_label(row))
        y += 1.0
        previous = row
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel(
        f"probability of failure, circle at {STUDY_PGA_RANGE_G[0]:g} g, "
        f"square at {STUDY_PGA_RANGE_G[1]:g} g"
    )
    ax.grid(True, axis="x", linewidth=0.3, alpha=0.5)
    ax.set_title(
        "At the study's demand - before amplification\n"
        "walls weakest first, under 2 m solid, 2 m and over dashed",
        fontsize=9,
    )


def build_figure(curves, localised_table):
    """Assemble the four panels."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 11.5), constrained_layout=True)
    ax_none, ax_under, ax_over, ax_demand = axes.ravel()
    draw_no_wall(ax_none, curves, localised_table)
    draw_walls(
        ax_under,
        curves,
        height_class=SHORTER,
        title="Wall under 2 m (or of unknown height) - wall type curve",
    )
    draw_walls(
        ax_over,
        curves,
        height_class=TALLER,
        title=(
            "Wall 2 m and over - the under 2 m curve, both percentiles "
            f"x{wall_type_fragility.TALL_HEIGHT_FACTOR:g}"
        ),
    )
    draw_at_demand(ax_demand, curves)
    fig.suptitle(
        "Urban slope model fragility curves on site PGA - medium rate setting, "
        "no topographic amplification, wall position unknown\n"
        "No wall: p15 and p50 on straight lines in log PGA against the "
        "susceptibility rating, through the lead's points at zone 3 and zone 5 "
        "(urban-localised-fragility.csv).\n"
        "In the model every median off NLM flatland is divided by 1.3 for "
        f"topographic amplification; fill x{wall_type_fragility.FILL_CAPACITY_FACTOR:g}"
        f", cut x{wall_type_fragility.CUT_CAPACITY_FACTOR:g}.",
        fontsize=10,
    )
    return fig


def report(curves):
    """Print every curve's percentiles and failure probabilities."""
    print(RULE)
    shown = curves[
        [
            "group",
            "label",
            "p15_g",
            "theta_g",
            "beta",
            "p_fail_at_low",
            "p_fail_at_high",
        ]
    ]
    with pd.option_context(
        "display.width", 160, "display.float_format", "{:.3f}".format
    ):
        print(shown.to_string(index=False))


def main(*, extent):
    """Draw the urban model's curves on site PGA.

    Args:
        extent: The extent the figure is labelled for, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
    """
    wall_table = wall_type_fragility.load_wall_type_fragility()
    localised_table = fragility.load_localised_fragility()
    curves = curves_table(wall_table, localised_table)
    report(curves)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig = build_figure(curves, localised_table)
    figure_path = FIG_DIR / f"{FIG_STEM}{extent_suffix(extent)}.png"
    fig.savefig(figure_path, dpi=DPI)
    plt.close(fig)
    print(RULE)
    print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT)
