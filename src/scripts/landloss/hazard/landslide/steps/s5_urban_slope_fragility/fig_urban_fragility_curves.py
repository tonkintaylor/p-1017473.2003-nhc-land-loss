"""Draw the fragility curves the urban slope model draws its polygons against.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_urban_slope_fragility/fig_urban_fragility_curves.py

The curves for review, on the model's own measure, PGV in m/s. Where
``fig_urban_slope_model.py`` maps each polygon's median, this draws the curves
themselves:

- **No wall.** The localised curve at the mid rating of each Kingsbury zone,
  from the median's two constants in
  ``landloss.hazard.landslide.urban.fragility`` and
  ``constants.LOCALISED_FRAGILITY_BETA``.
- **Wall under 2 m** and **wall 2 m and over.** The curve of each wall type in
  that height class, from the packaged ``retaining-wall-type-fragility.csv``,
  converted from PGA to PGV at the median PGV/PGA ratio of the walled polygons
  in the run's model file. The top axis gives the PGA at that ratio.
- **At the study's demand.** Each curve's probability of failure at the two
  ends of the study's 2,500-year PGV range, one row per curve.

Every curve is drawn as the model holds it before the polygon's own
adjustments: the medium rate setting, no topographic amplification and a wall
of unknown position. In the model a polygon's median is divided by its
amplification factor (1.0 to 1.5) and multiplied by the rate factor, and a
fill wall's median is 0.85 times the drawn one and a cut wall's 1.15 times.

Reads ``config.py`` beside it and the model file
``gen_urban_slope_fragility.py`` wrote for the first of its ``WORLD_IDS``, for
the PGV/PGA ratio only, so step 5 must have been run over ``EXTENT`` first.
The figure goes under ``report/hazard/landslide/urban-slope-model/fig/``,
which is gitignored.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import fragility, wall_type_fragility
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import config
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-model" / "fig"
FIG_STEM = "urban-fragility-curves"
DPI = 200

# The PGV axis the curves are drawn over, m/s.
PGV_AXIS_M_S = np.logspace(-1.0, 1.0, 300)

# The study's PGV at 2,500 years over the four territorial authorities, m/s
# (plan section 6), as fig_urban_slope_model.py marks it.
STUDY_PGV_RANGE_M_S = (0.96, 2.11)
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

RULE = "-" * 72


def zone_mid_ratings():
    """Return the mid rating of each Kingsbury zone, keyed by its rank."""
    edges = (0.0, *susceptibility.ZONE_BREAKS, float(susceptibility.MAX_RATING))
    return {
        rank: 0.5 * (edges[i] + edges[i + 1])
        for i, rank in enumerate(susceptibility.ZONE_RANKS)
    }


def wall_ratio_m_s_per_g(model):
    """Return the median PGV/PGA ratio over the model's walled polygons.

    Raises:
        ValueError: If no walled polygon carries a ratio.
    """
    ratio = model.loc[
        model["fragility_basis"] == fragility.WALL_BASIS, "pgv_pga_ratio_m_s_per_g"
    ].to_numpy(dtype=float)
    ratio = ratio[np.isfinite(ratio)]
    if ratio.size == 0:
        msg = "No walled polygon in the model file carries a PGV/PGA ratio."
        raise ValueError(msg)
    return float(np.median(ratio)), np.percentile(ratio, [5, 95])


def curves_table(wall_table, *, ratio_m_s_per_g):
    """Collect every curve drawn, one row each, with its PGV median and dispersion."""
    labels = (
        pd.read_csv(wall_type_fragility.WALL_TYPES_PATH)
        .set_index("wall_type")["label"]
        .to_dict()
    )
    rows = [
        {
            "group": "no_wall",
            "key": f"zone {rank}",
            "label": (
                f"Zone {rank} {susceptibility.ZONE_LABELS[rank].lower()} "
                f"(rating {rating:.0f})"
            ),
            "theta_m_s": float(
                fragility.localised_theta_base_m_s(np.array([rating]))[0]
            ),
            "beta": constants.LOCALISED_FRAGILITY_BETA,
            "zone": rank,
        }
        for rank, rating in zone_mid_ratings().items()
    ]
    for _, row in wall_table.iterrows():
        rows.append(
            {
                "group": row["height_class"],
                "key": row["wall_type"],
                "label": labels.get(row["wall_type"], row["wall_type"]),
                "theta_m_s": float(row["theta"]) * ratio_m_s_per_g,
                "beta": float(row["beta"]),
                "zone": np.nan,
            }
        )
    table = pd.DataFrame(rows)
    for end, pgv in zip(("low", "high"), STUDY_PGV_RANGE_M_S, strict=True):
        table[f"p_fail_at_{end}"] = fragility.lognormal_failure_probability(
            np.full(len(table), pgv), table["theta_m_s"], table["beta"]
        )
    return table


def curve(theta, beta):
    """Evaluate a lognormal on the drawn PGV axis."""
    return fragility.lognormal_failure_probability(
        PGV_AXIS_M_S,
        np.full_like(PGV_AXIS_M_S, theta),
        np.full_like(PGV_AXIS_M_S, beta),
    )


def style_curve_ax(ax, *, title):
    """Mark the study range, set the log axis and the labels."""
    ax.axvspan(*STUDY_PGV_RANGE_M_S, color=STUDY_COLOUR, alpha=0.25, lw=0)
    ax.text(
        STUDY_PGV_RANGE_M_S[0] * 1.03,
        0.02,
        "study PGV,\n2,500 yr",
        fontsize=7,
        ha="left",
        va="bottom",
    )
    ax.axhline(0.5, color="#bdbdbd", linewidth=0.6, zorder=0)
    ax.set(
        xscale="log",
        xlim=(PGV_AXIS_M_S[0], PGV_AXIS_M_S[-1]),
        ylim=(0, 1),
        xlabel="PGV (m/s)",
        ylabel="probability of failure",
    )
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
    ax.set_title(title, fontsize=9)


def draw_no_wall(ax, curves):
    """Draw the localised curve at each zone's mid rating."""
    rows = curves[curves["group"] == "no_wall"]
    cmap = plt.get_cmap(ZONE_CMAP)
    ranks = susceptibility.ZONE_RANKS
    for _, row in rows.iterrows():
        colour = cmap((row["zone"] - ranks[0]) / (ranks[-1] - ranks[0]))
        ax.plot(
            PGV_AXIS_M_S,
            curve(row["theta_m_s"], row["beta"]),
            color=colour,
            linewidth=1.5,
            label=f"{row['label']}, {row['theta_m_s']:.2f} m/s",
        )
    style_curve_ax(
        ax,
        title=(
            "No wall - localised curve, median "
            f"{fragility.LOCALISED_THETA_AT_ZERO_RATING_M_S:g} to "
            f"{fragility.LOCALISED_THETA_AT_MAX_RATING_M_S:g} m/s over rating 0 to "
            f"{susceptibility.MAX_RATING}, beta {constants.LOCALISED_FRAGILITY_BETA:g}"
        ),
    )
    ax.legend(fontsize=7, frameon=False, loc="upper left")


def draw_walls(ax, curves, *, height_class, ratio_m_s_per_g, title):
    """Draw each wall type's curve in one height class, on PGV."""
    rows = curves[curves["group"] == height_class]
    for _, row in rows.iterrows():
        ax.plot(
            PGV_AXIS_M_S,
            curve(row["theta_m_s"], row["beta"]),
            color=WALL_TYPE_COLOURS[row["key"]],
            linewidth=1.5,
            label=(
                f"{row['label']}, {row['theta_m_s']:.2f} m/s "
                f"({row['theta_m_s'] / ratio_m_s_per_g:.2f} g)"
            ),
        )
    style_curve_ax(ax, title=title)
    top = ax.secondary_xaxis(
        "top",
        functions=(
            lambda pgv: pgv / ratio_m_s_per_g,
            lambda pga: pga * ratio_m_s_per_g,
        ),
    )
    top.set_xlabel(f"PGA (g) at {ratio_m_s_per_g:.3f} m/s per g", fontsize=8)
    ax.legend(fontsize=7, frameon=False, loc="upper left")


def draw_at_demand(ax, curves):
    """Draw each curve's failure probability across the study's PGV range."""
    group_titles = {
        "no_wall": "No wall",
        "under_2_m": "Wall under 2 m",
        "2_m_and_over": "Wall 2 m and over",
    }
    ticks, labels, y = [], [], 0.0
    for group, group_title in group_titles.items():
        rows = curves[curves["group"] == group]
        for _, row in rows.iterrows():
            colour = WALL_TYPE_COLOURS.get(row["key"], "#4d4d4d")
            ax.plot(
                [row["p_fail_at_low"], row["p_fail_at_high"]],
                [y, y],
                color=colour,
                linewidth=2.5,
                solid_capstyle="round",
            )
            ax.plot(row["p_fail_at_low"], y, "o", color=colour, ms=4)
            ax.plot(row["p_fail_at_high"], y, "s", color=colour, ms=4)
            ticks.append(y)
            labels.append(f"{group_title}: {row['label']}")
            y += 1.0
        # A gap between the groups.
        y += 0.6
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel(
        f"probability of failure, circle at {STUDY_PGV_RANGE_M_S[0]:g} m/s, "
        f"square at {STUDY_PGV_RANGE_M_S[1]:g} m/s"
    )
    ax.grid(True, axis="x", linewidth=0.3, alpha=0.5)
    ax.set_title("At the study's demand - before amplification", fontsize=9)


def build_figure(curves, *, ratio_m_s_per_g, extent, world_id):
    """Assemble the four panels."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 11), constrained_layout=True)
    ax_none, ax_under, ax_over, ax_demand = axes.ravel()
    draw_no_wall(ax_none, curves)
    shorter, taller = wall_type_fragility.HEIGHT_CLASSES
    draw_walls(
        ax_under,
        curves,
        height_class=shorter,
        ratio_m_s_per_g=ratio_m_s_per_g,
        title="Wall under 2 m (or of unknown height) - wall type curve",
    )
    draw_walls(
        ax_over,
        curves,
        height_class=taller,
        ratio_m_s_per_g=ratio_m_s_per_g,
        title="Wall 2 m and over - wall type curve",
    )
    draw_at_demand(ax_demand, curves)
    fig.suptitle(
        "Urban slope model fragility curves - medium rate setting, no topographic "
        "amplification, wall position unknown\n"
        f"Wall curves converted from PGA at the median PGV/PGA ratio of the walled "
        f"polygons, {ratio_m_s_per_g:.3f} m/s per g ({extent}, world {world_id}). "
        "Amplification divides a median by 1.0 to 1.5; fill x0.85, cut x1.15.",
        fontsize=10,
    )
    return fig


def report(curves, *, ratio_m_s_per_g, ratio_range):
    """Print the ratio and every curve's median and failure probabilities."""
    print(RULE)
    print(
        f"PGV/PGA ratio over the walled polygons: median {ratio_m_s_per_g:.3f}, "
        f"5th to 95th percentile {ratio_range[0]:.3f} to {ratio_range[1]:.3f} m/s per g"
    )
    print(RULE)
    shown = curves[
        ["group", "label", "theta_m_s", "beta", "p_fail_at_low", "p_fail_at_high"]
    ]
    with pd.option_context(
        "display.width", 160, "display.float_format", "{:.3f}".format
    ):
        print(shown.to_string(index=False))


def main(*, extent, world_id):
    """Draw the urban model's curves, the wall ones at the run's PGV/PGA ratio.

    Args:
        extent: The extent step 5 was run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        world_id: The world whose model file the ratio is read from.
    """
    model_path = urban_slope_model_path(world_id, extent=extent)
    print(f"Reading the PGV/PGA ratio from {model_path} ...")
    model = pd.read_parquet(
        model_path, columns=["fragility_basis", "pgv_pga_ratio_m_s_per_g"]
    )
    ratio, ratio_range = wall_ratio_m_s_per_g(model)

    wall_table = wall_type_fragility.load_wall_type_fragility()
    curves = curves_table(wall_table, ratio_m_s_per_g=ratio)
    report(curves, ratio_m_s_per_g=ratio, ratio_range=ratio_range)

    fig = build_figure(curves, ratio_m_s_per_g=ratio, extent=extent, world_id=world_id)
    figure_path = FIG_DIR / f"{FIG_STEM}{extent_suffix(extent)}.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=DPI)
    plt.close(fig)
    print(RULE)
    print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, world_id=config.WORLD_IDS[0])
