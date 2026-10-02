"""Draw the urban fragility curves against the anchors they are fitted to.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/urban/fig_urban_fragility_anchors.py

Reads the packaged ``urban-fragility-anchors.csv`` and the TS1170.5 site class
I grids, fits the localised median's two constants and a dispersion to the
anchors (``landloss.hazard.landslide.urban.fragility.fit_localised_fragility``)
and draws one panel per Kingsbury zone: the low, medium and high curves at the
zone's mid rating on PGV, the committed curve and the fitted one, against the
anchor points of that zone. An anchor's PGA on rock is converted to PGV at the
rock-site ratio, the median of ``pgv_m_s_from_sa_1s(sa_t1) / pga`` over the
site class I grid cells inside ``SMALL_WLG_PILOT`` (contract section 3.16).
An anchor with no zone is drawn hollow on every zone panel its rating range
overlaps.

The run prints the ratio and the fitted constants. Pasting those into
``landloss.hazard.landslide.urban.fragility`` (and the dispersion into
``landloss.domain.constants.LOCALISED_FRAGILITY_BETA``, if accepted) is how the
anchoring sets the model; this script changes nothing itself. Results are
written up in ``urban_fragility_anchors_findings.md`` beside this script
after the first run.

Reads the TS1170.5 grids through ``landloss.io.ts1170`` (the local cache,
refreshed from the versioned store when stale) and the packaged assets, so it
needs no run of any step. The figure goes under
``report/hazard/landslide/urban-fragility/fig/``.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.lines import Line2D

from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import fragility
from landloss.hazard.shaking.pgv import pgv_m_s_from_sa_1s
from landloss.hazard.shaking.site_class import ROCK_SITE_CLASS
from landloss.io.area_of_interest import SMALL_WLG_PILOT
from landloss.io.ts1170 import get_ts1170_pga, get_ts1170_sa_t1
from scripts.landloss.hazard.shaking.steps.s3_pgv import config as pgv_config
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-fragility" / "fig"
FIG_NAME = "urban-fragility-anchors.png"
DPI = 200

# The PGV axis the curves are drawn over, m/s.
PGV_AXIS_M_S = np.logspace(-2.5, 1.0, 300)

# The three rate settings in a fixed order with a fixed colour each; the
# committed medium curve is the solid line.
SETTING_COLOURS = {"low": "#1b7837", "medium": "#2c7bb6", "high": "#d7191c"}
FIT_COLOUR = "#1a1a1a"
ANCHOR_COLOUR = "#1a1a1a"
UNZONED_COLOUR = "#7f7f7f"

RULE = "-" * 72


def rock_site_ratio_m_s_per_g(sa_t1, pga, extent):
    """Return the median PGV/PGA ratio on rock over an extent.

    Args:
        sa_t1: The TS1170.5 Sa(1.0 s) grid for site class I, g.
        pga: The TS1170.5 PGA grid for site class I, g, on the same grid.
        extent: The polygon to take the median over, in the grids' system.

    Returns:
        The median of ``pgv_m_s_from_sa_1s(sa_t1) / pga`` over the cells
        whose centre lies inside the extent, m/s per g.

    Raises:
        ValueError: If no finite cell falls inside the extent.
    """
    if sa_t1.shape != pga.shape:
        msg = f"The Sa(1.0 s) grid is {sa_t1.shape} and the PGA grid {pga.shape}."
        raise ValueError(msg)
    xx, yy = np.meshgrid(sa_t1.x.to_numpy(), sa_t1.y.to_numpy())
    inside = shapely.contains_xy(extent, xx, yy)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = pgv_m_s_from_sa_1s(
            np.asarray(sa_t1.to_numpy(), dtype=float)
        ) / np.asarray(pga.to_numpy(), dtype=float)
    finite = ratio[inside & np.isfinite(ratio)]
    if finite.size == 0:
        msg = "No finite site class I cell lies inside the extent."
        raise ValueError(msg)
    return float(np.median(finite))


def read_rock_site_ratio(*, return_period_yr):
    """Read the two site class I grids and take the ratio over the pilot box."""
    sa_t1 = get_ts1170_sa_t1(return_period_yr, ROCK_SITE_CLASS)
    pga = get_ts1170_pga(return_period_yr, ROCK_SITE_CLASS)
    return rock_site_ratio_m_s_per_g(
        sa_t1, pga, SMALL_WLG_PILOT.polygon(constants.DEFAULT_CRS)
    )


def zone_rating_bands():
    """Return the rating range of each Kingsbury zone, from the zone breaks."""
    edges = (0.0, *susceptibility.ZONE_BREAKS, float(susceptibility.MAX_RATING))
    return {
        rank: (edges[i], edges[i + 1])
        for i, rank in enumerate(susceptibility.ZONE_RANKS)
    }


def curve(theta, beta):
    """Evaluate a lognormal on the drawn PGV axis."""
    return fragility.lognormal_failure_probability(
        PGV_AXIS_M_S,
        np.full_like(PGV_AXIS_M_S, theta),
        np.full_like(PGV_AXIS_M_S, beta),
    )


def anchors_for_zone(placed, rank, band):
    """Split the placed anchors into the zone's own and the unzoned overlaps."""
    zoned = placed[placed["zone"].notna() & (placed["zone"].astype(float) == rank)]
    overlaps = placed[
        placed["zone"].isna()
        & (placed["rating_max"] >= band[0])
        & (placed["rating_min"] <= band[1])
    ]
    return zoned, overlaps


def draw_zone(ax, *, rank, band, placed, fit):
    """Draw one zone's curves and anchors."""
    mid_rating = 0.5 * (band[0] + band[1])
    committed = float(fragility.localised_theta_base_m_s(np.array([mid_rating]))[0])
    for setting, colour in SETTING_COLOURS.items():
        theta = committed * fragility.rate_factor(setting)
        ax.plot(
            PGV_AXIS_M_S,
            curve(theta, constants.LOCALISED_FRAGILITY_BETA),
            color=colour,
            linewidth=1.6 if setting == "medium" else 1.0,
            linestyle="-" if setting == "medium" else "--",
        )
    if fit is not None:
        fitted = float(
            fragility.localised_theta_base_m_s(
                np.array([mid_rating]),
                theta_at_zero_rating_m_s=fit.theta_at_zero_rating_m_s,
                theta_at_max_rating_m_s=fit.theta_at_max_rating_m_s,
            )[0]
        )
        ax.plot(
            PGV_AXIS_M_S,
            curve(fitted, fit.beta),
            color=FIT_COLOUR,
            linewidth=1.2,
            linestyle=":",
        )

    zoned, overlaps = anchors_for_zone(placed, rank, band)
    for frame, colour, filled in (
        (zoned, ANCHOR_COLOUR, True),
        (overlaps, UNZONED_COLOUR, False),
    ):
        if frame.empty:
            continue
        ax.errorbar(
            frame["pgv_m_s"],
            frame["fail_fraction"],
            xerr=[
                frame["pgv_m_s"] - frame["pgv_min_m_s"],
                frame["pgv_max_m_s"] - frame["pgv_m_s"],
            ],
            fmt="o",
            ms=5,
            lw=0.8,
            color=colour,
            markerfacecolor=colour if filled else "white",
            zorder=3,
        )
        for _, row in frame.iterrows():
            ax.annotate(
                row["anchor_id"],
                (row["pgv_m_s"], row["fail_fraction"]),
                fontsize=6,
                xytext=(4, 3),
                textcoords="offset points",
                color=colour,
            )
    ax.set(xscale="log", ylim=(0, 1), xlim=(PGV_AXIS_M_S[0], PGV_AXIS_M_S[-1]))
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
    ax.set_title(
        f"Zone {rank} {susceptibility.ZONE_LABELS[rank]} - rating {band[0]:.0f} to "
        f"{band[1]:.0f}, drawn at {mid_rating:.0f}",
        fontsize=9,
    )


def build_figure(anchors, *, ratio_m_s_per_g, fit):
    """Assemble one panel per zone.

    Args:
        anchors: The table ``load_urban_fragility_anchors`` returns.
        ratio_m_s_per_g: The rock-site PGV/PGA ratio the anchors are placed at.
        fit: The fitted localised fragility, or ``None`` when the fit failed.

    Returns:
        The figure.
    """
    placed = fragility.anchor_points(anchors, ratio_m_s_per_g=ratio_m_s_per_g)
    bands = zone_rating_bands()
    fig, axes = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
    axes = axes.ravel()
    for ax, (rank, band) in zip(axes, bands.items(), strict=False):
        draw_zone(ax, rank=rank, band=band, placed=placed, fit=fit)
    for ax in axes[len(bands) :]:
        ax.set_axis_off()
    for ax in axes[: len(bands)]:
        ax.set_xlabel("PGV (m/s)")
        ax.set_ylabel("probability of failure")

    handles = [
        Line2D(
            [0],
            [0],
            color=colour,
            linewidth=1.6 if setting == "medium" else 1.0,
            linestyle="-" if setting == "medium" else "--",
            label=f"{setting} setting, committed median, beta {constants.LOCALISED_FRAGILITY_BETA:g}",
        )
        for setting, colour in SETTING_COLOURS.items()
    ]
    if fit is not None:
        handles.append(
            Line2D(
                [0],
                [0],
                color=FIT_COLOUR,
                linestyle=":",
                label=(
                    f"fitted: {fit.theta_at_zero_rating_m_s:.2f} to "
                    f"{fit.theta_at_max_rating_m_s:.3f} m/s, beta {fit.beta:.2f}"
                ),
            )
        )
    handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            color=ANCHOR_COLOUR,
            linestyle="none",
            label="zoned anchor (bar: PGA range on rock)",
        )
    )
    handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            color=UNZONED_COLOUR,
            markerfacecolor="white",
            linestyle="none",
            label="unzoned anchor overlapping the zone's ratings",
        )
    )
    axes[-1].legend(handles=handles, loc="center", fontsize=8, frameon=False)
    fig.suptitle(
        f"Urban failure fragility against its anchors - PGA on rock converted at "
        f"{ratio_m_s_per_g:.3f} m/s per g",
        fontsize=11,
    )
    return fig


def fit_or_none(anchors, *, ratio_m_s_per_g):
    """Fit the localised fragility, or report why it could not be."""
    try:
        return fragility.fit_localised_fragility(
            anchors, ratio_m_s_per_g=ratio_m_s_per_g
        )
    except ValueError as error:
        print(f"The fit failed: {error}")
        return None


def report(fit, *, ratio_m_s_per_g):
    """Print the ratio and the fit beside the committed constants."""
    print(RULE)
    print(
        f"Rock-site PGV/PGA ratio over the pilot box: {ratio_m_s_per_g:.4f} m/s per g"
    )
    print(
        "Committed localised median: "
        f"{fragility.LOCALISED_THETA_AT_ZERO_RATING_M_S:.3f} m/s at rating 0, "
        f"{fragility.LOCALISED_THETA_AT_MAX_RATING_M_S:.3f} m/s at "
        f"{susceptibility.MAX_RATING}, beta {constants.LOCALISED_FRAGILITY_BETA:g}"
    )
    if fit is None:
        return
    print(
        f"Fitted on {len(fit.anchors_used)} anchors ({', '.join(fit.anchors_used)}): "
        f"{fit.theta_at_zero_rating_m_s:.3f} m/s at rating 0, "
        f"{fit.theta_at_max_rating_m_s:.3f} m/s at {susceptibility.MAX_RATING}, "
        f"beta {fit.beta:.3f}"
    )
    print(
        "To adopt the fit, set LOCALISED_THETA_AT_ZERO_RATING_M_S and "
        "LOCALISED_THETA_AT_MAX_RATING_M_S in landloss.hazard.landslide.urban.fragility "
        "and LOCALISED_FRAGILITY_BETA in landloss.domain.constants to these values."
    )


def main():
    """Fit the localised fragility to the anchors and draw the curves against them."""
    anchors = fragility.load_urban_fragility_anchors()
    ratio = read_rock_site_ratio(return_period_yr=pgv_config.RETURN_PERIOD_YR)
    fit = fit_or_none(anchors, ratio_m_s_per_g=ratio)
    report(fit, ratio_m_s_per_g=ratio)

    fig = build_figure(anchors, ratio_m_s_per_g=ratio, fit=fit)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / FIG_NAME, dpi=DPI)
    plt.close(fig)
    print(RULE)
    print(f"Wrote {FIG_DIR / FIG_NAME}")
    with pd.option_context("display.width", 160):
        print(
            fragility.anchor_points(anchors, ratio_m_s_per_g=ratio)[
                [
                    "anchor_id",
                    "zone",
                    "rating",
                    "pgv_m_s",
                    "fail_fraction",
                    "class_word",
                ]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()
