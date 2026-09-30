"""Check our Marc et al. (2016) implementation against the paper's own 40 earthquakes.

Runs :mod:`landloss.hazard.landslide.calibration.marc_2016` on every earthquake
of the paper's Table S1 and compares the predicted total landslide volume and
area with the paper's estimates. The decisive check is a refit: the paper
fitted its landscape sensitivity and steepness scale on 26 earthquakes (the 40,
less its 11 named outliers and the 3 with no source-depth constraint), so
refitting both on the same 26 with our code should return the paper's values if
our physics is theirs. Prints the comparison and the refit, and draws predicted
against estimated volume and area with the New Zealand events marked.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/calibration/fig_marc_2016_table_s1.py

Reads only packaged assets, so it needs neither T: nor R:. Results are written
up in ``marc_2016_table_s1_findings.md`` beside this script.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from landloss.hazard.landslide.calibration import marc_2016
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "calibration" / "fig"
FIG_NAME = "marc-2016-table-s1.png"
DPI = 200

# The paper's outliers (section 4.1), excluded from its fit of the sensitivity,
# as (year, name) in Table S1's spelling.
PAPER_OUTLIERS = {
    (1976, "Friuli"),
    (1997, "Umbria-Marche"),
    (1994, "Arthur's Pass"),
    (2002, "Avaj"),
    (2002, "Denali"),
    (2004, "Rotoehu"),
    (2009, "L'Aquila"),
    (2010, "Cucapah"),
    (2010, "Yushu"),
    (2011, "Lorca"),
    (2011, "Nagano"),
}
# The events with no source-depth constraint, also excluded from the fit.
UNCONSTRAINED = {(1855, "Wairapa"), (1950, "Assam"), (1957, "Daly city")}
# The events the paper excluded from its area fit (Figure 5 caption), besides
# the unconstrained ones.
AREA_FIT_EXCLUDED = {
    (2010, "Yushu"),
    (2002, "Denali"),
    (2011, "Nagano"),
    (1991, "Limon"),
}

FACTOR_OF_TWO = 2.0


def predict_all() -> pd.DataFrame:
    """Predict every Table S1 earthquake's total volume and area."""
    rows = []
    for (year, name), event in marc_2016.get_table_s1().groupby(
        ["year", "name"], sort=False
    ):
        sources, mw_sd, r0_sd = marc_2016.sources_from_table_s1(event)
        first = event.iloc[0]
        slope, a_topo = first["modal_slope_deg"], first["a_topo"]
        row = {
            "year": year,
            "name": name,
            "new_zealand": first["country"] == "NZ",
            "outlier": (year, name) in PAPER_OUTLIERS,
            "unconstrained": (year, name) in UNCONSTRAINED,
            "modal_slope_deg": slope,
            "a_topo": a_topo,
            "seismic_km2": marc_2016.seismic_term_km2(sources),
            "volume_km3": first["volume_km3"],
            "area_km2": first["area_km2"],
        }
        for quantity in ("volume", "area"):
            row[f"{quantity}_pred"] = marc_2016.total_landsliding(
                sources, modal_slope_deg=slope, a_topo=a_topo, quantity=quantity
            )
            p25, _, p75 = marc_2016.total_landsliding_percentiles(
                sources,
                mw_sd=mw_sd,
                r0_sd_km=r0_sd,
                modal_slope_deg=slope,
                a_topo=a_topo,
                quantity=quantity,
                samples=5_000,
            )
            row[f"{quantity}_p25"], row[f"{quantity}_p75"] = p25, p75
        rows.append(row)
    table = pd.DataFrame(rows)
    table["volume_ratio"] = table["volume_km3"] / table["volume_pred"]
    table["area_ratio"] = table["area_km2"] / table["area_pred"]
    return table


def within_factor_two(ratio: pd.Series) -> pd.Series:
    """Whether an estimate is within a factor of two of its prediction."""
    return (ratio >= 1 / FACTOR_OF_TWO) & (ratio <= FACTOR_OF_TWO)


def report(table: pd.DataFrame) -> None:
    """Print the comparison, the success rates and the refit."""
    columns = [
        "year",
        "name",
        "volume_km3",
        "volume_pred",
        "volume_ratio",
        "area_km2",
        "area_pred",
        "area_ratio",
    ]
    with pd.option_context("display.width", 200, "display.precision", 4):
        print(table[columns].to_string(index=False))

    volume_ok = within_factor_two(table["volume_ratio"])
    has_area = table["area_km2"].notna()
    area_ok = within_factor_two(table.loc[has_area, "area_ratio"])
    print(
        f"\nVolume within a factor of 2: {volume_ok.sum()} of {len(table)} (paper: 63% of 40)"
    )
    print(
        f"Area within a factor of 2: {area_ok.sum()} of {has_area.sum()} (paper: 11 of 17)"
    )

    fitted = table[~table["outlier"] & ~table["unconstrained"]]
    alpha_v, t_v = marc_2016.fit_sensitivity(
        fitted["volume_km3"],
        fitted["seismic_km2"],
        fitted["a_topo"],
        fitted["modal_slope_deg"],
        quantity="volume",
    )
    print(
        f"\nVolume refit on {len(fitted)} events: alpha_V = {alpha_v:,.0f} m3/km2, "
        f"T_SV = {t_v:.1f} deg (paper: 4,174 +/- 212, 11.6 +/- 0.6, N = 26)"
    )
    keys = list(zip(table["year"], table["name"], strict=True))
    area_fit = table[
        has_area
        & ~table["unconstrained"]
        & ~pd.Series([k in AREA_FIT_EXCLUDED for k in keys], index=table.index)
    ]
    alpha_a, t_a = marc_2016.fit_sensitivity(
        area_fit["area_km2"],
        area_fit["seismic_km2"],
        area_fit["a_topo"],
        area_fit["modal_slope_deg"],
        quantity="area",
    )
    print(
        f"Area refit on {len(area_fit)} events: alpha_A = {alpha_a:,.0f} m2/km2, "
        f"T_SA = {t_a:.1f} deg (paper: 3,445 +/- 325, 15.8 +/- 1.5, N = 13)"
    )

    nz = table[table["new_zealand"]]
    print("\nNew Zealand events, volume estimated / predicted:")
    for _, row in nz.iterrows():
        print(f"  {row['year']} {row['name']:<14} {row['volume_ratio']:6.2f}")


def draw(table: pd.DataFrame) -> None:
    """Draw predicted against estimated volume and area."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), constrained_layout=True)
    for ax, quantity, unit in ((axes[0], "volume", "km³"), (axes[1], "area", "km²")):
        observed = table[f"{quantity}_km3" if quantity == "volume" else "area_km2"]
        shown = observed.notna()
        for label, mask, style in (
            (
                "Fitted events",
                ~table["outlier"] & ~table["unconstrained"],
                {"color": "#1f77b4"},
            ),
            (
                "Paper's outliers and unconstrained",
                table["outlier"] | table["unconstrained"],
                {"color": "#bbbbbb"},
            ),
        ):
            sel = shown & mask
            ax.errorbar(
                table.loc[sel, f"{quantity}_pred"],
                observed[sel],
                xerr=[
                    table.loc[sel, f"{quantity}_pred"]
                    - table.loc[sel, f"{quantity}_p25"],
                    table.loc[sel, f"{quantity}_p75"]
                    - table.loc[sel, f"{quantity}_pred"],
                ],
                fmt="o",
                ms=5,
                lw=0.7,
                label=label,
                **style,
            )
        nz = shown & table["new_zealand"]
        ax.scatter(
            table.loc[nz, f"{quantity}_pred"],
            observed[nz],
            s=90,
            facecolors="none",
            edgecolors="#d62728",
            lw=1.5,
            label="New Zealand",
            zorder=3,
        )
        for _, row in table[nz].iterrows():
            ax.annotate(
                f"{row['name']} {row['year']}",
                (
                    row[f"{quantity}_pred"],
                    row[f"{quantity}_km3" if quantity == "volume" else "area_km2"],
                ),
                fontsize=7,
                xytext=(4, 3),
                textcoords="offset points",
            )
        lo = np.nanmin([table[f"{quantity}_pred"].min(), observed.min()]) / 2
        hi = np.nanmax([table[f"{quantity}_pred"].max(), observed.max()]) * 2
        line = np.array([lo, hi])
        ax.plot(line, line, "k-", lw=0.8)
        ax.plot(line, line * FACTOR_OF_TWO, "k:", lw=0.8)
        ax.plot(line, line / FACTOR_OF_TWO, "k:", lw=0.8)
        ax.set(
            xscale="log",
            yscale="log",
            xlabel=f"Predicted total {quantity} ({unit})",
            ylabel=f"Estimated total {quantity} ({unit})",
        )
        ax.set_title(f"Total landslide {quantity}")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "Marc et al. (2016) rebuilt, against the paper's Table S1 (bars: 25th–75th percentile)"
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / FIG_NAME, dpi=DPI)
    plt.close(fig)
    print(f"\nWrote {FIG_DIR / FIG_NAME}")


def main():
    """Run the check and draw the figure."""
    table = predict_all()
    report(table)
    draw(table)


if __name__ == "__main__":
    main()
