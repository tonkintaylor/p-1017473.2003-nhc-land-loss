"""Proposed retaining wall fragility by wall type, against published curves.

    uv run --frozen python src/scripts/landloss/vul/research/fig_rw_type_fragility.py

A proposal for the project lead, not the model's curves. Each wall type's curve
is read from ``retaining-wall-type-fragility.csv`` through
:mod:`landloss.hazard.landslide.urban.wall_type_fragility`, which stores it as
the PGA at which 15% and 50% of walls are replaced. Each sits on one of the
five initial-condition rungs of Koutsoupaki et al. (2023) [koutsoupaki_2023],
Fs = 1.5 to 1.1 (Tables A1 to A5), on the moderate damage state (DS2, 5% of
H), since moderate damage usually leads to replacement in a claim (the lead,
2026-10-06). New timber pole walls take that rung times 1.3 and reinforced concrete from July 1992
walls times 1.5. Each type has one curve per height class, under 2 m
and 2 m and over (the lead, 2026-10-07): gravity masonry, old timber pole,
block or RC cantilever and landscaper timber take the published height effect
switched (the 6 m curve under 2 m, the 3 m curve at 2 m and over), and crib,
new timber pole and reinforced concrete from July 1992 take the 3 m curve for both. The figure
sets those choices beside the other evidence, each on its moderate state too:

- the same curve for a wall retaining fill and a wall retaining a cut, scaled
  by the module's position factors;
- the other published PGA curves that are credible for a wall type: a gravity
  road wall about 3.6 m high (Cosentini et al. 2019 [cosentini_2019]), a 9 m
  concrete gravity wall (Li et al. 2024 [li_2024]), an RC cantilever abutment
  6 m high (SYNER-G D3.7 [kaynia_2011]), and the
  generalised road wall curve of de Silva et al. (2026) [de_silva_2026] at the
  yield acceleration :data:`DE_SILVA_YIELD_ACCELERATION_G`;
- the share of walls that failed in the Port Hills in 2010 to 2011, by type:
  Very Poor in Anderson, Wood and Scott (2015) [anderson_2015], the only class
  it gives by type, and Moderate plus Major in Stone et al. (2015)
  [stone_2015], Table 3, plotted at the range of PGA recorded there;
- the model's no-wall (localised) urban slope curve, in green, at the mid
  rating of each Kingsbury zone, converted from PGV to free-field PGA at
  :data:`PILOT_PGV_PGA_RATIO_M_S_PER_G` with no topographic amplification.

The Canterbury shares are cumulative over the sequence, lean to council road
walls, and include walls facing strong loess, so they are an upper bound on one
event's rate at one PGA, not points on a curve. The published comparators are
converted to the same stored form, the 15th and 50th percentiles, and back.

Writes ``rw-type-fragility.png`` and ``rw-type-fragility-by-position.png`` to
``report/vul/rw/fig/``. The findings are in
``fig_rw_type_fragility.md`` beside this script.
"""

from dataclasses import dataclass

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.exposure.rw.lines import CUT, FILL
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import fragility as urban_fragility
from landloss.hazard.landslide.urban import wall_type_fragility as wtf
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "vul" / "rw" / "fig"
FIG_NAME = "rw-type-fragility.png"
VARIANTS_FIG_NAME = "rw-type-fragility-by-position.png"
DPI = 200

G = 9.81  # m/s2 in one g, for Cosentini et al.'s medians given in m/s2

# Koutsoupaki et al. (2023) Tables A1 to A5: free-field PGA median (g) and
# total dispersion for DS2, moderate, horizontal displacement Ux = 5% of H, by
# initial factor of safety, for the 3 m (R.W.3) and 6 m (R.W.6) walls. The
# moderate state is read as replace because moderate damage usually leads to
# replacement in a claim (the lead, 2026-10-06). Drawn as the ladder; the wall
# type table holds the rungs it uses.
KOUTSOUPAKI_DS2 = {
    1.5: {3: (0.8623, 0.6540), 6: (1.0883, 0.6791)},
    1.4: {3: (0.6952, 0.6044), 6: (0.8568, 0.6293)},
    1.3: {3: (0.6496, 0.6090), 6: (0.7982, 0.6439)},
    1.2: {3: (0.5872, 0.6171), 6: (0.7128, 0.6607)},
    1.1: {3: (0.5104, 0.6296), 6: (0.6272, 0.6577)},
}

# de Silva et al. (2026) Table 2, retaining walls on EC8 ground type C:
# ln(u_res) = ln(a) + b ln(amax / ac), residuals sigma, u_res in m. The
# capacity uncertainty is NIBS's 0.3 (the paper's "0.3b" did not extract
# cleanly; check against the PDF). The damage state drawn is DS2, 0.15 m of
# residual displacement, one below the paper's most severe (DS3, 0.40 m): the
# lead's choice (2026-10-06); 0.15 m is about 5% of a 3 m wall.
DE_SILVA_A = 0.021
DE_SILVA_B = 1.684
DE_SILVA_SIGMA = 0.848
DE_SILVA_BETA_C = 0.3
DE_SILVA_DS2_M = 0.15
# The wall's yield (critical) acceleration, g: set by the lead (2026-10-06)
# until it is read or approximated per wall type. The paper ran 0.05 to 0.3 g,
# so 0.5 g is above its range.
DE_SILVA_YIELD_ACCELERATION_G = 0.5

# The PGA recorded in the Port Hills on 22 February 2011 (Anderson et al. 2015,
# Table 1), drawn as the horizontal extent of every Canterbury share.
PORT_HILLS_PGA_G = (1.0, 1.7)

# The height class each panel of the main figure draws: under 2 m for every
# type but reinforced concrete from July 1992, which is drawn 2 m and over.
SHORT_HEIGHT_CLASS, TALL_HEIGHT_CLASS = wtf.HEIGHT_CLASSES
PANEL_HEIGHT_CLASS = SHORT_HEIGHT_CLASS
HEIGHT_CLASS_LABELS = {
    SHORT_HEIGHT_CLASS: "under 2 m",
    TALL_HEIGHT_CLASS: "2 m and over",
}

# The PGV/PGA ratio (m/s per g) the no-wall curves are drawn at, to put their
# PGV medians on the figures' free-field PGA axis: the median of the pilot
# model polygons' pgv_pga_ratio_m_s_per_g in the 2026-10-06 run. For plotting
# only; the model converts each wall curve at the polygon's own ratio.
PILOT_PGV_PGA_RATIO_M_S_PER_G = 0.848

# The rating each Kingsbury zone's no-wall curve is drawn at, about the middle
# of the zone's band (susceptibility.ZONE_BREAKS), and its line style. For
# plotting only: the model sets the no-wall median from the continuous rating.
NO_WALL_ZONE_RATINGS = {1: 10.0, 2: 40.0, 3: 80.0, 4: 120.0, 5: 145.0}
NO_WALL_ZONE_STYLES = {
    1: (0, (1, 1.5)),
    2: (0, (3, 1.5)),
    3: (0, (6, 2)),
    4: (0, (6, 1.5, 1, 1.5)),
    5: "-",
}


@dataclass(frozen=True)
class Comparator:
    """A published fragility curve, stored as its 15th and 50th percentiles."""

    label: str
    p15: float
    p50: float


def comparator(label: str, theta: float, beta: float) -> Comparator:
    """Store a published median and dispersion as percentiles."""
    p15, p50 = wtf.lognormal_to_percentiles(theta, beta)
    return Comparator(label, float(p15), float(p50))


def de_silva_comparator(yield_acceleration_g: float) -> Comparator:
    """Turn de Silva et al.'s displacement law into a PGA fragility at DS2."""
    ratio = (DE_SILVA_DS2_M / DE_SILVA_A) ** (1 / DE_SILVA_B)
    beta = np.hypot(DE_SILVA_SIGMA, DE_SILVA_BETA_C) / DE_SILVA_B
    return comparator(
        "de Silva et al. 2026, road wall, soil C,\n"
        f"ac = {yield_acceleration_g:g} g, DS2 0.15 m",
        yield_acceleration_g * ratio,
        beta,
    )


@dataclass(frozen=True)
class Panel:
    """One wall type's panel: its title and the evidence beside its curve.

    ``anderson`` and ``stone`` are the Canterbury failure shares, as fractions,
    of the type or of the nearest type those papers name, with that name.
    """

    wall_type: str
    title: str
    height_class: str = PANEL_HEIGHT_CLASS
    comparators: tuple[Comparator, ...] = ()
    anderson: tuple[str, float] | None = None
    stone: tuple[tuple[str, float], ...] = ()


DE_SILVA = de_silva_comparator(DE_SILVA_YIELD_ACCELERATION_G)

# Li et al. (2024) [li_2024], a 9 m concrete gravity wall with flat backfill
# (S1), on PGA: moderate damage (LS1, wall top drift 0.9% of H). The paper
# prints no fragility parameters; this is fitted by eye to Fig. 18(a) (LS1
# 0.72 at 1 g and 0.875 at 2 g). The median agrees with Table 8's capacity
# through Fig. 12(a)'s demand line (slope 0.989, Table 5; intercept about
# 0.65, read off the plot): 0.46 g. The 12 degree backfill (S2) raises LS1 by
# nearly 25% at 0.4 g.
LI_2024 = comparator(
    "Li et al. 2024, concrete gravity\n9 m, moderate (LS1)", 0.46, 1.3
)

PANELS = (
    Panel(
        "brick_rock",
        "Brick or rock masonry\n(stone and brick gravity walls)",
        comparators=(
            comparator(
                "Cosentini et al. 2019, gravity\nroad wall ~3.6 m, moderate 5% H",
                3.550 / G,
                1.195,
            ),
            DE_SILVA,
        ),
        anderson=("stone masonry", 0.18),
        stone=(("stone facing", 0.35),),
    ),
    Panel(
        "reinforced_concrete_pre_1992",
        "Reinforced concrete, before July 1992\n(mass concrete gravity, RC cantilever)",
        comparators=(
            comparator(
                "SYNER-G D3.7, RC cantilever\n6 m, soil C, moderate", 0.60, 0.70
            ),
            LI_2024,
        ),
        stone=(("reinforced concrete", 0.22),),
    ),
    Panel(
        "crib_gabion",
        "Crib or gabion",
        anderson=("crib", 0.13),
        stone=(("concrete crib", 0.30), ("timber crib", 0.28)),
    ),
    Panel("timber_pole_pre_1992", "Timber pole, old\n(pre July 1992)"),
    Panel(
        "concrete_block",
        "Concrete block\n(block masonry cantilever)",
        comparators=(DE_SILVA,),
        anderson=("concrete masonry", 0.055),
    ),
    Panel(
        "timber_pole_post_1992",
        "Timber pole, new\n(engineered, post 1992)",
        anderson=("timber pole", 0.028),
        stone=(("post and panel", 0.09),),
    ),
    Panel("garden_timber", "Landscaper timber\n(unconsented, <1.5 m)"),
    Panel(
        "reinforced_concrete_post_1992",
        "Reinforced concrete, July 1992 on,\n2 m and over (MSE, soil nail, RC)",
        height_class=TALL_HEIGHT_CLASS,
        anderson=("MSE, 18 walls", 0.0),
    ),
)

# Colours: the reference categorical palette, in fixed order (dataviz skill):
# the proposed curve, the published comparators, and the two Canterbury papers.
PROPOSED = "#2a78d6"
COMPARATORS = ("#eb6834", "#eda100", "#e87ba4", "#008300")
ANDERSON = "#1baf7a"
STONE = "#4a3aa7"
NO_WALL = "#1d7a35"
GHOST = "#c9c9c4"
INK = "#3d3d3a"
# Wall position, in the reference categorical order: fill, none known, cut.
POSITION_COLOURS = {FILL: "#eb6834", "unknown": "#8a8a85", CUT: "#2a78d6"}
# The rungs are ordered, so they take one hue from light (Fs 1.5) to dark.
RUNG_COLOURS = {
    1.5: "#86b6ef",
    1.4: "#5598e7",
    1.3: "#2a78d6",
    1.2: "#1c5cab",
    1.1: "#0d366b",
}

PGA = np.linspace(0.01, 2.5, 400)


def curve(p15: float, p50: float, factor: float = 1.0) -> np.ndarray:
    """Return P(replace | PGA) over :data:`PGA` for a stored curve."""
    theta, beta = wtf.percentiles_to_lognormal(p15 * factor, p50 * factor)
    return wtf.lognormal_failure_probability(PGA, theta, beta)


@dataclass(frozen=True)
class NoWallCurve:
    """The no-wall (localised) urban slope curve at one zone's mid rating."""

    zone: int
    rating: float
    p15: float
    p50: float

    @property
    def label(self) -> str:
        """The legend entry: zone, rating and the two percentiles."""
        name = susceptibility.ZONE_LABELS[self.zone]
        return (
            f"no wall, zone {self.zone} {name} (rating {self.rating:g}): "
            f"p15/p50 {self.p15:.2f}/{self.p50:.2f} g"
        )


def no_wall_curves() -> tuple[NoWallCurve, ...]:
    """Return the no-wall curve at each zone's mid rating, on free-field PGA.

    The PGV median is the model's own (``localised_theta_base_m_s`` with its
    committed constants) divided by :data:`PILOT_PGV_PGA_RATIO_M_S_PER_G`, with
    no topographic amplification; the dispersion is
    ``constants.LOCALISED_FRAGILITY_BETA``.
    """
    ratings = np.array(list(NO_WALL_ZONE_RATINGS.values()), dtype=float)
    theta_pga_g = (
        urban_fragility.localised_theta_base_m_s(ratings)
        / PILOT_PGV_PGA_RATIO_M_S_PER_G
    )
    p15, p50 = wtf.lognormal_to_percentiles(
        theta_pga_g, constants.LOCALISED_FRAGILITY_BETA
    )
    return tuple(
        NoWallCurve(zone, float(rating), float(low), float(mid))
        for zone, rating, low, mid in zip(
            NO_WALL_ZONE_RATINGS, ratings, p15, p50, strict=True
        )
    )


def plot_no_wall(ax: plt.Axes, no_wall: tuple[NoWallCurve, ...]) -> list:
    """Draw the no-wall curves in green, one line style per zone.

    Returns:
        The line handles, for one shared legend.
    """
    handles = []
    for one in no_wall:
        (line,) = ax.plot(
            PGA,
            curve(one.p15, one.p50),
            color=NO_WALL,
            lw=1.1,
            ls=NO_WALL_ZONE_STYLES[one.zone],
            alpha=0.85,
            label=one.label,
        )
        handles.append(line)
    return handles


NO_WALL_NOTE = (
    "Green: the no-wall (localised) urban slope curve, drawn at each Kingsbury "
    "zone's mid rating for plotting only (the model sets the no-wall median from "
    "the continuous rating), converted from PGV at "
    f"{PILOT_PGV_PGA_RATIO_M_S_PER_G:g} m/s per g (the pilot median) with no "
    "topographic amplification. On sloping land both the wall and the no-wall "
    "medians are divided by the polygon's amplification."
)


def add_no_wall_legend(fig: plt.Figure, handles: list) -> None:
    """Put one legend entry per zone below the panels, with the note."""
    fig.legend(
        handles=handles,
        labels=[handle.get_label() for handle in handles],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.025),
        ncol=3,
        fontsize=7.5,
        frameon=False,
        handlelength=4,
    )
    fig.text(0.5, 0.005, NO_WALL_NOTE, ha="center", fontsize=7, color=INK)


def own_legend(ax: plt.Axes, no_wall_handles: list, **kwargs: object) -> None:
    """Draw the panel's legend, leaving out the shared no-wall lines."""
    own = [line for line in ax.get_lines() if line not in no_wall_handles]
    own += [
        container for container in ax.containers if container.get_label()[:1] != "_"
    ]
    own = [artist for artist in own if artist.get_label()[:1] != "_"]
    ax.legend(handles=own, labels=[artist.get_label() for artist in own], **kwargs)


def plot_ladder(ax: plt.Axes) -> None:
    """Draw the five Koutsoupaki rungs, 3 m solid and 6 m dashed."""
    for fs, by_height in KOUTSOUPAKI_DS2.items():
        colour = RUNG_COLOURS[fs]
        p15, p50 = wtf.lognormal_to_percentiles(*by_height[3])
        p15_6, p50_6 = wtf.lognormal_to_percentiles(*by_height[6])
        ax.plot(
            PGA,
            curve(p15, p50),
            color=colour,
            lw=2,
            label=f"Fs {fs}: 3 m {p15:.2f}/{p50:.2f} g, 6 m {p15_6:.2f}/{p50_6:.2f} g",
        )
        ax.plot(PGA, curve(p15_6, p50_6), color=colour, lw=1.2, ls="--")
    ax.set_title("Koutsoupaki et al. 2023 rungs\n3 m solid, 6 m dashed", fontsize=9)
    ax.legend(
        loc="lower right", fontsize=6, frameon=False, title="p15/p50", title_fontsize=7
    )


def plot_canterbury(ax: plt.Axes, panel: Panel) -> None:
    """Draw the Port Hills failure shares at the PGA recorded there."""
    centre = np.mean(PORT_HILLS_PGA_G)
    half = (PORT_HILLS_PGA_G[1] - PORT_HILLS_PGA_G[0]) / 2
    if panel.anderson is not None:
        name, share = panel.anderson
        ax.errorbar(
            centre,
            share,
            xerr=half,
            fmt="o",
            ms=6,
            color=ANDERSON,
            mec="white",
            capsize=3,
            label=f"Anderson 2015 Very Poor, {name}: {share:.0%}",
        )
    for offset, (name, share) in enumerate(panel.stone, start=1):
        ax.errorbar(
            centre + 0.06 * offset,
            share,
            xerr=half,
            fmt="s",
            ms=6,
            color=STONE,
            mec="white",
            capsize=3,
            alpha=1.0 if offset == 1 else 0.6,
            label=f"Stone 2015 Moderate+Major, {name}: {share:.0%}",
        )


def plot_wall_type(
    ax: plt.Axes,
    panel: Panel,
    table: pd.DataFrame,
    no_wall: tuple[NoWallCurve, ...],
) -> list:
    """Draw one wall type's proposed curve with the evidence beside it.

    Returns:
        The no-wall line handles, for the shared legend.
    """
    key = (panel.wall_type, panel.height_class)
    row = table.set_index(list(wtf.TABLE_KEY)).loc[key]
    height = int(row["published_height_m"])
    for by_height in KOUTSOUPAKI_DS2.values():
        ax.plot(
            PGA,
            curve(*wtf.lognormal_to_percentiles(*by_height[height])),
            color=GHOST,
            lw=1,
        )
    handles = plot_no_wall(ax, no_wall)
    p15, p50 = row["p15"], row["p50"]
    ax.plot(
        PGA,
        curve(p15, p50),
        color=PROPOSED,
        lw=2.2,
        label=(
            f"Proposed, {HEIGHT_CLASS_LABELS[panel.height_class]}: "
            f"Fs {row['published_fs']} {height} m x{row['type_factor']:g}, "
            f"p15/p50 {p15:.2f}/{p50:.2f} g"
        ),
    )
    for position, style in ((FILL, ":"), (CUT, "-.")):
        factor = wtf.POSITION_FACTORS[position]
        ax.plot(
            PGA,
            curve(p15, p50, factor),
            color=PROPOSED,
            lw=1.1,
            ls=style,
            label=f"  {position} (x{factor:g}): {p15 * factor:.2f}/{p50 * factor:.2f} g",
        )
    for colour, published in zip(COMPARATORS, panel.comparators, strict=False):
        ax.plot(
            PGA,
            curve(published.p15, published.p50),
            color=colour,
            lw=1.8,
            ls="--",
            label=f"{published.label} ({published.p15:.2f}/{published.p50:.2f} g)",
        )
    plot_canterbury(ax, panel)
    ax.set_title(panel.title, fontsize=9)
    own_legend(ax, handles, loc="upper left", fontsize=5.5, frameon=False)
    return handles


def plot_type_fragility(table: pd.DataFrame) -> plt.Figure:
    """Lay out the ladder and one panel per proposed wall type."""
    fig, axes = plt.subplots(3, 3, figsize=(14, 12.5), sharex=True, sharey=True)
    flat = axes.ravel()
    plot_ladder(flat[0])
    no_wall = no_wall_curves()
    handles = []
    for ax, panel in zip(flat[1:], PANELS, strict=True):
        handles = plot_wall_type(ax, panel, table, no_wall)
    for ax in flat:
        ax.set_xlim(0, 2.5)
        ax.set_ylim(0, 1)
        ax.grid(color="#e6e6e1", lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(labelsize=8, colors=INK)
        ax.axvspan(*PORT_HILLS_PGA_G, color="#f3f1ea", zorder=0)
    for ax in axes[-1]:
        ax.set_xlabel("Free-field PGA (g)", fontsize=9)
    for ax in axes[:, 0]:
        ax.set_ylabel("P(wall replaced | PGA)", fontsize=9)
    fig.suptitle(
        "Proposed retaining wall fragility by type (moderate, DS2, displacement 5% of H; "
        "p15/p50 = PGA at 15% and 50% replaced), against published curves and "
        "Port Hills failure shares (shaded: 1.0 to 1.7 g recorded 22 Feb 2011)",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    add_no_wall_legend(fig, handles)
    return fig


def plot_variants(table: pd.DataFrame) -> plt.Figure:
    """One panel per wall type: both height classes and every wall position.

    The curves are the model's own (the stored percentiles times the position
    factor): walls under 2 m solid, walls 2 m and over dashed, each labelled
    with the published wall height its curve was read from. The no-wall curves
    are drawn in green on every panel.
    """
    curves = table.set_index(list(wtf.TABLE_KEY))
    no_wall = no_wall_curves()
    handles = []
    fig, axes = plt.subplots(2, 4, figsize=(16, 8.5), sharex=True, sharey=True)
    flat = axes.ravel()
    for ax, wall_type in zip(flat, wtf.WALL_TYPES, strict=False):
        handles = plot_no_wall(ax, no_wall)
        for height_class, style in (
            (SHORT_HEIGHT_CLASS, "-"),
            (TALL_HEIGHT_CLASS, "--"),
        ):
            row = curves.loc[(wall_type, height_class)]
            label_size = (
                f"{HEIGHT_CLASS_LABELS[height_class]} "
                f"({int(row['published_height_m'])} m curve)"
            )
            for position, colour, factor in (
                (FILL, POSITION_COLOURS[FILL], wtf.FILL_CAPACITY_FACTOR),
                ("unknown", POSITION_COLOURS["unknown"], 1.0),
                (CUT, POSITION_COLOURS[CUT], wtf.CUT_CAPACITY_FACTOR),
            ):
                ax.plot(
                    PGA,
                    curve(row["p15"], row["p50"], factor),
                    color=colour,
                    lw=1.8 if style == "-" else 1.3,
                    ls=style,
                    label=(
                        f"{label_size}, {position}: "
                        f"{row['p15'] * factor:.2f}/{row['p50'] * factor:.2f} g"
                    ),
                )
        effect = curves.loc[(wall_type, SHORT_HEIGHT_CLASS), "height_effect"]
        ax.set_title(
            f"{wall_type.replace('_', ' ')} (height effect: {effect})", fontsize=9
        )
        own_legend(
            ax,
            handles,
            loc="lower right",
            fontsize=5.5,
            frameon=False,
            title="p15/p50",
            title_fontsize=6,
        )
    flat[-1].axis("off")
    flat[-1].text(
        0.0,
        0.5,
        "Colour: wall position (fill x0.85, cut x1.15, unknown x1).\n"
        "Solid: walls under 2 m (or of unknown height).\n"
        "Dashed: walls 2 m and over.\n\n"
        "Switched (gravity masonry, old timber pole, block or RC\n"
        "cantilever, landscaper timber): under 2 m takes the 6 m curve\n"
        "and 2 m and over the 3 m curve, taller walls being the worse.\n"
        "None (crib, new timber pole, RC from July 1992): the 3 m\n"
        "curve for both, so the dashed line lies on the solid one.\n"
        "Within a height class the curve does not change with height.\n\n"
        "Koutsoupaki et al. 2023 DS2 (moderate, 5% of H), free-field PGA.\n"
        "On sloping land the model converts the median to PGV and\n"
        "divides it by the polygon's topographic amplification (1 to 1.5).",
        fontsize=8,
        color=INK,
        va="center",
    )
    for ax in flat[:-1]:
        ax.set_xlim(0, 2.5)
        ax.set_ylim(0, 1)
        ax.grid(color="#e6e6e1", lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(labelsize=8, colors=INK)
    for ax in axes[1]:
        ax.set_xlabel("Free-field PGA (g)", fontsize=9)
    for ax in axes[:, 0]:
        ax.set_ylabel("P(wall replaced | PGA)", fontsize=9)
    fig.suptitle(
        "Retaining wall fragility by type, height class and wall position, as the "
        "model reads it",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    add_no_wall_legend(fig, handles)
    return fig


def main() -> None:
    """Draw the figures and write them to the report figure directory."""
    table = wtf.load_wall_type_fragility()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for name, fig in (
        (FIG_NAME, plot_type_fragility(table)),
        (VARIANTS_FIG_NAME, plot_variants(table)),
    ):
        out = FIG_DIR / name
        fig.savefig(out, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {out}")
    print(f"de Silva et al. 2026 at ac = {DE_SILVA_YIELD_ACCELERATION_G:g} g: {DE_SILVA}")


if __name__ == "__main__":
    main()
