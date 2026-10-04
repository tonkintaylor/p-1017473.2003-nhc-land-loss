"""Map where each retaining wall dataset records walls, and where they agree.

    uv run --frozen python src/scripts/landloss/exposure/rw/validations/fig_rw_dataset_maps.py

Reads the layer ``gen_rw_dataset_properties.py`` writes, so run that first.
Settings are in ``config.py``.

Both maps are of hexagons, never of properties: the NZMM extract may not be
reproduced property by property and the claims are private, so each property
is counted into the hexagon its representative point falls in, and a hexagon
holding fewer than ``MIN_HEX_PROPERTIES`` properties (or ``MIN_HEX_CLAIMS``
claims) is left blank. Writes to ``report/exposure/rw/rw-datasets/fig/``:

- ``rw-dataset-hex-wcc.png``: four panels over the area GNS mapped -- the share
  of properties GNS records a wall on, the share NHC does, the share of the
  properties either records one on that both do, and the share of claimed
  properties whose report lists one;
- ``rw-dataset-hex-study-area.png``: the share NHC flags across the four
  councils, with the area GNS mapped outlined, beside the claims per hexagon.

Each panel's colour scale is its own, one hue each (GNS blue, NHC orange,
claims aqua, agreement grey), because the datasets flag at rates five times
apart and one scale would leave NHC blank.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io.area_of_interest import get_study_areas
from scripts.landloss.exposure.rw.validations import config
from scripts.landloss.exposure.rw.validations.rw_datasets import (
    CLAIMS,
    GNS,
    NHC,
    claims_population,
    hex_grid,
    load_properties,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CRS = constants.DEFAULT_CRS

# Single-hue ramps from near the surface to the dataset's own dark step.
RAMPS = {
    GNS: ("#eaf2fd", "#2a78d6", "#0d366b"),
    NHC: ("#fdeee7", "#eb6834", "#7a2a0b"),
    CLAIMS: ("#e6f6f0", "#1baf7a", "#0b4f37"),
    "agreement": ("#f0efec", "#8a8984", "#2b2b29"),
}
BOUNDARY = "#333333"
HEX_ALPHA = 0.85

# The hexagons over the four councils are larger, so each holds enough claims.
STUDY_AREA_HEX_FACTOR = 2.5

# The shares are drawn up to this quantile of the hexagons, so a few small
# hexagons at 100% do not flatten the rest of the scale.
SCALE_QUANTILE = 0.98

DPI = 250


def ramp(name: str) -> LinearSegmentedColormap:
    """Return the single-hue colour map for a dataset."""
    return LinearSegmentedColormap.from_list(name, RAMPS[name])


def count_into_hexagons(
    properties: gpd.GeoDataFrame, hexagons: gpd.GeoSeries, columns: list[str]
) -> gpd.GeoDataFrame:
    """Return per hexagon the number of properties and the sum of each column."""
    points = gpd.GeoDataFrame(
        properties[columns].astype(float),
        geometry=properties.geometry.representative_point(),
        crs=CRS,
    )
    cells = gpd.GeoDataFrame(geometry=hexagons, crs=CRS)
    joined = gpd.sjoin(points, cells, predicate="within")
    sums = joined.groupby("index_right")[columns].sum()
    sums["properties"] = joined.groupby("index_right").size()
    return cells.join(sums, how="inner")


def draw_share(
    ax: plt.Axes,
    cells: gpd.GeoDataFrame,
    share: pd.Series,
    cmap: str,
    title: str,
    label: str,
    extent: gpd.GeoDataFrame,
) -> None:
    """Draw one share per hexagon, over a basemap, with its own colour bar."""
    drawn = cells.assign(share=share).dropna(subset=["share"])
    vmax = max(float(drawn["share"].quantile(SCALE_QUANTILE)), 0.01)
    drawn.plot(
        ax=ax,
        column="share",
        cmap=ramp(cmap),
        vmin=0,
        vmax=vmax,
        alpha=HEX_ALPHA,
        linewidth=0.2,
        edgecolor="white",
        zorder=2,
    )
    style_basemap_ax(ax, extent, scalebar_kwargs={"font_size": 7})
    bar = plt.colorbar(
        mpl.cm.ScalarMappable(mpl.colors.Normalize(0, vmax), ramp(cmap)),
        ax=ax,
        shrink=0.6,
        pad=0.01,
        format=mpl.ticker.PercentFormatter(xmax=1.0, decimals=0),
    )
    bar.set_label(label, fontsize=8)
    bar.ax.tick_params(labelsize=7)
    ax.set_title(title, loc="left", fontsize=10)


def fig_wcc(properties: gpd.GeoDataFrame, coverage: gpd.GeoDataFrame) -> plt.Figure:
    """Map the four comparison shares over the area GNS mapped."""
    population = properties.loc[properties["in_gns_coverage"] & properties["has_nzmm"]]
    population = population.assign(
        both=population["gns_wall"].astype(bool) & population["nhc_wall"].astype(bool),
        either=population["gns_wall"].astype(bool)
        | population["nhc_wall"].astype(bool),
    )
    extent = gpd.GeoDataFrame(geometry=coverage.geometry, crs=CRS)
    hexagons = hex_grid(tuple(extent.total_bounds), config.HEX_SIDE_M)
    cells = count_into_hexagons(
        population, hexagons, ["gns_wall", "nhc_wall", "both", "either"]
    )
    cells = cells.loc[cells["properties"] >= config.MIN_HEX_PROPERTIES]

    claims = claims_population(properties.loc[properties["in_gns_coverage"]])
    claim_cells = count_into_hexagons(claims, hexagons, ["claim_wall"])
    claim_cells = claim_cells.loc[claim_cells["properties"] >= config.MIN_HEX_CLAIMS]

    fig, axes = plt.subplots(2, 2, figsize=(11.0, 12.0))
    draw_share(
        axes[0, 0],
        cells,
        cells["gns_wall"] / cells["properties"],
        GNS,
        f"(a) {GNS}: properties with a mapped wall",
        "Share of properties",
        extent,
    )
    draw_share(
        axes[0, 1],
        cells,
        cells["nhc_wall"] / cells["properties"],
        NHC,
        f"(b) {NHC}: properties flagged",
        "Share of properties",
        extent,
    )
    agreed = (cells["both"] / cells["either"]).where(
        cells["either"] >= config.MIN_HEX_CLAIMS
    )
    draw_share(
        axes[1, 0],
        cells,
        agreed,
        "agreement",
        "(c) Both, of properties either records a wall on",
        "Share recorded by both",
        extent,
    )
    draw_share(
        axes[1, 1],
        claim_cells,
        claim_cells["claim_wall"] / claim_cells["properties"],
        CLAIMS,
        f"(d) {CLAIMS}: claims listing a wall",
        "Share of claimed properties",
        extent,
    )
    for ax in axes.flat:
        coverage.boundary.plot(ax=ax, color=BOUNDARY, linewidth=0.6, zorder=3)
    fig.suptitle(
        f"Retaining walls in urban Wellington City, per {config.HEX_SIDE_M:g} m "
        f"hexagon (blank: fewer than {config.MIN_HEX_PROPERTIES} properties, or "
        f"{config.MIN_HEX_CLAIMS} claims)",
        x=0.02,
        ha="left",
        fontsize=11,
    )
    fig.tight_layout()
    return fig


def fig_study_area(
    properties: gpd.GeoDataFrame, coverage: gpd.GeoDataFrame
) -> plt.Figure:
    """Map the NHC share and the claims across the four councils."""
    study_areas = get_study_areas(CRS)
    nzmm = properties.loc[properties["has_nzmm"]]
    side = config.HEX_SIDE_M * STUDY_AREA_HEX_FACTOR
    hexagons = hex_grid(tuple(nzmm.total_bounds), side)
    cells = count_into_hexagons(nzmm, hexagons, ["nhc_wall"])
    cells = cells.loc[cells["properties"] >= config.MIN_HEX_PROPERTIES]

    claims = claims_population(properties)
    claim_cells = count_into_hexagons(claims, hexagons, ["claim_wall"])
    claim_cells = claim_cells.loc[claim_cells["properties"] >= config.MIN_HEX_CLAIMS]

    # Framed on where the properties are, not on the council boundaries, which
    # run out over farmland and the west coast.
    extent = gpd.GeoDataFrame(geometry=[cells.union_all().envelope], crs=CRS)

    fig, (ax_nhc, ax_claims) = plt.subplots(1, 2, figsize=(13.0, 5.9))
    draw_share(
        ax_nhc,
        cells,
        cells["nhc_wall"] / cells["properties"],
        NHC,
        f"(a) {NHC}: properties flagged",
        "Share of properties",
        extent,
    )
    draw_share(
        ax_claims,
        claim_cells,
        claim_cells["claim_wall"] / claim_cells["properties"],
        CLAIMS,
        f"(b) {CLAIMS}: claims listing a wall",
        "Share of claimed properties",
        extent,
    )
    for ax in (ax_nhc, ax_claims):
        study_areas.boundary.plot(ax=ax, color=BOUNDARY, linewidth=0.5, zorder=3)
        coverage.boundary.plot(
            ax=ax, color=RAMPS[GNS][1], linewidth=1.0, linestyle="--", zorder=3
        )
        ax.set_xlim(extent.total_bounds[[0, 2]])
        ax.set_ylim(extent.total_bounds[[1, 3]])
    ax_nhc.plot([], [], color=RAMPS[GNS][1], linestyle="--", label="Area GNS mapped")
    ax_nhc.legend(loc="upper left", fontsize=8, frameon=True)
    fig.suptitle(
        f"Retaining walls over the four councils, per {side:g} m hexagon "
        f"(blank: fewer than {config.MIN_HEX_PROPERTIES} properties, or "
        f"{config.MIN_HEX_CLAIMS} claims)",
        x=0.02,
        ha="left",
        fontsize=11,
    )
    fig.tight_layout()
    return fig


def main() -> int:
    """Write both maps."""
    config.FIG_DIR.mkdir(parents=True, exist_ok=True)
    properties = load_properties()
    coverage = gpd.read_parquet(config.GNS_COVERAGE_PATH)

    figures = {
        "rw-dataset-hex-wcc.png": fig_wcc(properties, coverage),
        "rw-dataset-hex-study-area.png": fig_study_area(properties, coverage),
    }
    for name, fig in figures.items():
        fig.savefig(config.FIG_DIR / name, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {config.FIG_DIR / name}")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
