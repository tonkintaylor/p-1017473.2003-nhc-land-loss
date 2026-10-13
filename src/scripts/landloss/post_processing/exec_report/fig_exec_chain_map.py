"""Map the whole chain on one small window: exposure, hazard, damage and cost.

    uv run --frozen python src/scripts/landloss/post_processing/exec_report/fig_exec_chain_map.py

Four panels of the same 600 by 450 m window, for the exec report, read left
to right and top to bottom:

1. **Exposure**: what is insured. Property boundaries, buildings, the insured
   land, the insured retaining walls by type and the culverts and bridges.
2. **Hazard**: what the earthquake does to the ground. The liquefaction land
   damage state drawn on 100 m cells, the landslide realisation's imminent,
   evacuated and inundated ground, and the site PGA with the topographic
   amplification the slope fragility applies off flatland.
3. **Damage**: the state of the insured assets. Each wall and crossing damaged or not, the
   landslide ground that falls on insured land, and each property's
   liquefaction land damage state.
4. **Cost**: what it costs to put right, on one colour scale for every item.

The loss module settles per claim, not per item, so panel 4 hands each claim's
cost to the items it belongs to: the wall repair cost to the claim's damaged
walls (split by length), the crossing cost to its crossings, the land repair
and spoil removal to its landslide ground on insured land (split by area), and
the liquefaction cost to its insured land. These are repair costs before the
cap and excess, and the professional fees are left off; the run prints the
window's totals for the caption.

Every layer is read through its step's path function for ``config.EXTENT``,
so run the chain (``gen_all.py``) and the loss module (``loss/gen_loss.py``)
over that extent first. Liquefaction cracks and ejecta are not drawn: the
model gives them as areas per property, with no location. The basemap and the
LINZ building and property layers are fetched over the network.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import contextily as cx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.patheffects import Stroke, withStroke
from rasterio import features
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.hazard.landslide.urban.geometry import amplification_factor
from landloss.io.readers import get_nz_building_outlines, get_nz_property_boundaries
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population.gen_crossing_population import (
    crossing_population_path,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
)
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation.gen_pga_realisations import (
    pga_path,
)
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    settlement_path,
)
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.post_processing.exec_report import config
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

FIG_DIR = REPORT_DIR / "exec" / "chain" / "fig"
FIG_NAME = "exec-chain-map.png"
DPI = 300
NZTM = constants.DEFAULT_CRS

# A4 portrait at report width: two 4:3 map panels across, each with its key
# beneath it.
FIGSIZE = (7.4, 8.1)
FONT_SIZE = 7
RULE = "-" * 72

BASEMAP = cx.providers.Esri.WorldImagery
# Panels 2 to 4 lay a white veil over the imagery so their data reads first.
VEIL_ALPHA = {"exposure": 0.0, "hazard": 0.35, "damage": 0.45, "cost": 0.45}

# The wall types grouped to three for an executive reader, in the first three
# slots of the validated categorical order, which hold apart for every pair.
WALL_GROUPS = {
    "timber_pole_pre_1992": "Timber",
    "timber_pole_post_1992": "Timber",
    "garden_timber": "Timber",
    "reinforced_concrete_pre_1992": "Concrete",
    "reinforced_concrete_post_1992": "Concrete",
    "concrete_block": "Concrete",
    "brick_rock": "Masonry, crib or gabion",
    "crib_gabion": "Masonry, crib or gabion",
}
WALL_GROUP_COLOUR = {
    "Timber": "#2a78d6",
    "Concrete": "#eb6834",
    "Masonry, crib or gabion": "#1baf7a",
}
CROSSING_COLOUR = "#e87ba4"
# Most walls are 3 to 10 m long, a few pixels at this scale, so a line much
# wider than this is wider than the wall is long.
WALL_WIDTH = 1.1
CROSSING_WIDTH = 1.6
CASING_WIDTH = 0.9
# Crossings closer than this share one label.
LABEL_GROUP_M = 40.0

BUILDING_COLOUR = "#1a1a19"
INSURED_LAND_COLOUR = "#fcfcfb"
PROPERTY_COLOUR = "#3a3a38"
PROPERTY_WIDTH = 0.25
INSURED_LAND_EDGE_WIDTH = 0.4

# The landslide ground, by the realisation's land class. Inundated is drawn
# last and translucent, so the evacuated ground shows through it.
EVACUATED_COLOUR = "#8c2d04"
INUNDATED_COLOUR = "#f4a259"
IMMINENT_COLOUR = "#f6b40e"
INUNDATED_ALPHA = 0.45

# The land damage states as the National Liquefaction Model colours them, as
# in vul/liquefaction/land/report/fig_land_damage_maps.py.
LD_STATE_COLOURS = {
    1: "#3AB04A",
    2: "#A6D96A",
    3: "#FEE900",
    4: "#F8951D",
    5: "#D7301F",
    6: "#9D1C1F",
}
LD_STATE_LABELS = {
    1: "None",
    2: "Minor",
    3: "Moderate",
    4: "Major",
    5: "Severe",
    6: "Very severe",
}
LD_CELL_ALPHA = 0.45
# The lowest state drawn. State 1 (none) covers most ground and says nothing
# happened there, so it is left as imagery.
LD_LOWEST_STATE_SHOWN = 2
LD_PROPERTY_ALPHA = 0.55

# Damaged or not: the status pair, told apart by line style as well as colour.
DAMAGED_COLOUR = "#d03b3b"
UNDAMAGED_COLOUR = "#0ca30c"
NO_COST_COLOUR = "#52514e"

# The NZD bands every cost is read on, the low end of the QGIS e2e build's
# COST_BREAKS, with the top band open.
COST_BREAKS_NZD = [0, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5]
COST_CMAP = "YlOrRd"


# ----------------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------------


def window_frame():
    """The window as a one-row frame, for the panels to be held to."""
    return gpd.GeoDataFrame(geometry=[box(*config.WINDOW_NZTM)], crs=NZTM)


def clip(frame, margin_m=0.0):
    """The rows of a frame that touch the window, in NZTM."""
    frame = frame.to_crs(NZTM)
    minx, miny, maxx, maxy = config.WINDOW_NZTM
    return frame.cx[
        minx - margin_m : maxx + margin_m, miny - margin_m : maxy + margin_m
    ].copy()


def read_raster(path):
    """One band of a raster over the window, with its plotting extent.

    Read a cell beyond the window on every side, so the cells snapped to the
    grid still reach the frame; the axes and the PGA zones are clipped to it.
    """
    margin = 100.0
    minx, miny, maxx, maxy = config.WINDOW_NZTM
    minx, miny, maxx, maxy = minx - margin, miny - margin, maxx + margin, maxy + margin
    with rasterio.open(path) as source:
        window = from_bounds(minx, miny, maxx, maxy, source.transform)
        window = window.round_offsets().round_lengths()
        values = source.read(1, window=window, boundless=True, fill_value=np.nan)
        bounds = rasterio.windows.bounds(window, source.transform)
        transform = source.window_transform(window)
    left, bottom, right, top = bounds
    return values.astype(float), (left, right, bottom, top), transform


def read_layers(extent, world_id, realisation_id):
    """Read every layer the four panels draw, clipped to the window."""
    w, r = world_id, realisation_id
    bbox = config.WINDOW_NZTM
    land = clip(gpd.read_parquet(insured_land_path(extent=extent)))
    vul_land = clip(
        gpd.read_parquet(world_loss_input_path("land", w, r, extent=extent))
    )
    slides = clip(gpd.read_parquet(combined_realisation_path(w, r, extent=extent)))
    walls = clip(gpd.read_parquet(wall_population_path(w, extent=extent)))
    vul_walls = clip(gpd.read_parquet(world_loss_input_path("rw", w, r, extent=extent)))
    crossings = clip(gpd.read_parquet(crossing_population_path(r, extent=extent)))
    vul_crossings = pd.concat(
        [
            clip(
                gpd.read_parquet(world_loss_input_path(table, w, r, extent=extent))
            ).rename(columns={column: "crossing_id"})
            for table, column in (("bridges", "bridge_id"), ("culverts", "culvert_id"))
        ],
        ignore_index=True,
    )
    ground = clip(
        gpd.read_parquet(
            ground_map_path(extent=extent), columns=["is_flatland", "geometry"]
        )
    )
    settlement = pd.read_parquet(settlement_path(w, r, extent=extent))
    return {
        "land": land,
        "vul_land": vul_land,
        "slides": slides,
        "walls": walls,
        "vul_walls": vul_walls,
        "crossings": crossings,
        "vul_crossings": gpd.GeoDataFrame(vul_crossings, crs=NZTM),
        "ground": ground,
        "settlement": settlement[settlement["claim_id"].isin(land["claim_id"])],
        "buildings": get_nz_building_outlines(bbox=bbox, crs=NZTM),
        "properties": get_nz_property_boundaries(bbox=bbox, crs=NZTM),
        "ld_state": read_raster(ld_state_path(r, extent=extent)),
        "pga": read_raster(pga_path(r, extent=extent)),
    }


# ----------------------------------------------------------------------------
# Deriving
# ----------------------------------------------------------------------------


def wall_damage(vul_walls):
    """Whether each insured wall is damaged, by shaking or by a landslide."""
    return (
        vul_walls["is_damaged_by_shaking"].astype(bool)
        | vul_walls["is_evacuated"].astype(bool)
        | vul_walls["is_inundated"].astype(bool)
    )


def crossing_damage(vul_crossings):
    """Whether each crossing is damaged: a bridge by shaking or a landslide,
    a culvert by shaking (``is_damaged``) or by inundation."""
    flags = [
        column
        for column in (
            "is_damaged_by_shaking",
            "is_damaged",
            "is_evacuated",
            "is_inundated",
        )
        if column in vul_crossings
    ]
    return vul_crossings[flags].fillna(False).astype(bool).any(axis=1)


def landslide_on_insured_land(slides, land):
    """The evacuated and inundated ground that falls on insured land, per claim."""
    ground = slides[slides["land_class"].isin(["evacuated land", "inundated land"])]
    pieces = gpd.overlay(
        ground[["land_class", "geometry"]],
        land[["claim_id", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    return pieces[pieces.area > 0]


def amplified_pga_zones(pga, ground):
    """The site PGA times the topographic amplification, as zones with a value.

    The PGA grid steps only with the site class, and the slope fragility
    divides its median by one amplification factor off NLM flatland
    (``amplification_factor``), so the PGA a slope feels is the cell's PGA
    times that factor. Each 100 m cell is cut by the ground map's flatland
    pieces and the pieces of one value are dissolved together.
    """
    values, _, transform = pga
    cells = gpd.GeoDataFrame(
        [
            {"pga_g": value, "geometry": shape(geometry)}
            for geometry, value in features.shapes(
                values.astype("float32"),
                mask=np.isfinite(values),
                transform=transform,
            )
        ],
        crs=NZTM,
    )
    pieces = gpd.overlay(
        cells,
        ground[["is_flatland", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    pieces["amplified_pga_g"] = (
        pieces["pga_g"] * amplification_factor(pieces["is_flatland"].to_numpy(bool))
    ).round(2)
    zones = pieces.dissolve(by="amplified_pga_g").reset_index()
    return gpd.clip(zones, box(*config.WINDOW_NZTM))


def share_of_claim(sizes, claim_ids):
    """Each item's share of its claim's total length or area."""
    sizes = pd.Series(np.asarray(sizes, dtype=float), index=claim_ids.index)
    return sizes / sizes.groupby(claim_ids).transform("sum")


def item_costs(layers, slide_pieces):
    """Each claim's repair cost handed to the items it belongs to.

    Returns:
        A dict of frames, one per item kind, each with a ``cost_nzd`` column.
    """
    costs = layers["settlement"].set_index("claim_id")

    walls = layers["vul_walls"].assign(damaged=wall_damage(layers["vul_walls"]))
    damaged = walls[walls["damaged"]].copy()
    damaged["cost_nzd"] = damaged["claim_id"].map(
        costs["wall_repair_cost_incl_gst_nzd"]
    ).fillna(0) * share_of_claim(damaged.length, damaged["claim_id"])

    crossings = layers["vul_crossings"]
    hit = crossings[crossing_damage(crossings)].copy()
    hit["cost_nzd"] = hit["claim_id"].map(
        costs["crossing_repair_cost_incl_gst_nzd"]
    ).fillna(0) / hit.groupby("claim_id")["claim_id"].transform("size")

    landslide = (
        costs["land_repair_cost_incl_gst_nzd"]
        + costs["spoil_removal_cost_incl_gst_nzd"]
    )
    pieces = slide_pieces.copy()
    pieces["cost_nzd"] = pieces["claim_id"].map(landslide).fillna(0) * share_of_claim(
        pieces.area, pieces["claim_id"]
    )

    land = layers["land"].copy()
    land["cost_nzd"] = (
        land["claim_id"].map(costs["liquefaction_repair_cost_incl_gst_nzd"]).fillna(0)
    )

    return {
        "walls": damaged,
        "crossings": hit,
        "landslide": pieces,
        "liquefaction": land[land["cost_nzd"] > 0],
    }


# ----------------------------------------------------------------------------
# Drawing
# ----------------------------------------------------------------------------


def start_panel(ax, kind):
    """Hold a panel to the window over the imagery, veiled for panels 2 to 4."""
    style_basemap_ax(
        ax,
        window_frame(),
        basemap=BASEMAP,
        arrow_kwargs={"scale": 0.16, "label_size": 5},
        scalebar_kwargs={"font_size": 5},
    )
    if VEIL_ALPHA[kind]:
        minx, miny, maxx, maxy = config.WINDOW_NZTM
        ax.add_patch(
            Rectangle(
                (minx, miny),
                maxx - minx,
                maxy - miny,
                facecolor="white",
                alpha=VEIL_ALPHA[kind],
                linewidth=0,
                zorder=0.5,
            )
        )


def draw_lines(ax, frame, *, colour, width, style="-", zorder=6):
    """Draw lines at their true geometry."""
    if frame.empty:
        return
    frame.plot(ax=ax, color=colour, linewidth=width, linestyle=style, zorder=zorder)


def label_crossings(ax, crossings):
    """Name the crossings beside them: a culvert is a 3 m line, so its true
    geometry is a short stroke that needs pointing out, not a bigger symbol.
    Crossings within ``LABEL_GROUP_M`` of each other share one label."""
    if crossings.empty:
        return
    groups = crossings.buffer(LABEL_GROUP_M / 2).union_all()
    for group in getattr(groups, "geoms", [groups]):
        members = crossings[crossings.intersects(group)]
        names = members["structure"].value_counts()
        text = ", ".join(
            f"{count} {name}s" if count > 1 else name for name, count in names.items()
        ).capitalize()
        anchor = (group.centroid.x + 45, group.centroid.y + 45)
        for position, (_, row) in enumerate(members.iterrows()):
            point = row.geometry.interpolate(0.5, normalized=True)
            ax.annotate(
                text if position == 0 else "",
                xy=(point.x, point.y),
                xytext=anchor,
                textcoords="data",
                fontsize=FONT_SIZE - 1,
                color="black",
                arrowprops={"arrowstyle": "-", "color": "black", "linewidth": 0.5},
                path_effects=[withStroke(linewidth=2, foreground="white")],
                zorder=9,
            )


def draw_ld_cells(ax, ld_state):
    """The land damage state drawn on 100 m cells, translucent, state 2 and up."""
    values, extent, _ = ld_state
    values = np.where(values >= LD_LOWEST_STATE_SHOWN, values, np.nan)
    cmap = ListedColormap([LD_STATE_COLOURS[state] for state in LD_STATE_COLOURS])
    norm = BoundaryNorm(np.arange(0.5, 7.5), cmap.N)
    ax.imshow(
        np.ma.masked_invalid(values),
        extent=extent,
        cmap=cmap,
        norm=norm,
        alpha=LD_CELL_ALPHA,
        interpolation="nearest",
        zorder=1,
    )
    return sorted(int(state) for state in np.unique(values[np.isfinite(values)]))


def draw_exposure(ax, layers):
    """Panel 1: what is insured."""
    start_panel(ax, "exposure")
    layers["land"].plot(
        ax=ax, facecolor=INSURED_LAND_COLOUR, alpha=0.3, edgecolor="none", zorder=2
    )
    layers["land"].boundary.plot(
        ax=ax, color=INSURED_LAND_COLOUR, linewidth=INSURED_LAND_EDGE_WIDTH, zorder=3
    )
    layers["properties"].boundary.plot(
        ax=ax, color=PROPERTY_COLOUR, linewidth=PROPERTY_WIDTH, zorder=3
    )
    layers["buildings"].plot(
        ax=ax, facecolor="none", edgecolor=BUILDING_COLOUR, linewidth=0.5, zorder=4
    )
    walls = layers["walls"].assign(group=layers["walls"]["wall_type"].map(WALL_GROUPS))
    for group, colour in WALL_GROUP_COLOUR.items():
        draw_lines(ax, walls[walls["group"] == group], colour=colour, width=WALL_WIDTH)
    draw_lines(
        ax, layers["crossings"], colour=CROSSING_COLOUR, width=CROSSING_WIDTH, zorder=7
    )
    label_crossings(ax, layers["crossings"])

    groups = walls["group"].value_counts()
    return [
        Patch(
            facecolor=INSURED_LAND_COLOUR,
            alpha=0.6,
            edgecolor="#9c9b97",
            linewidth=INSURED_LAND_EDGE_WIDTH,
            label=f"Insured land ({len(layers['land']):,} claims)",
        ),
        Line2D(
            [],
            [],
            color=PROPERTY_COLOUR,
            linewidth=0.6,
            label="Property boundary",
        ),
        Patch(
            facecolor="none", edgecolor=BUILDING_COLOUR, linewidth=0.6, label="Building"
        ),
        *[
            Line2D(
                [],
                [],
                color=colour,
                linewidth=WALL_WIDTH,
                label=f"Insured wall: {group.lower()} ({groups.get(group, 0)})",
            )
            for group, colour in WALL_GROUP_COLOUR.items()
        ],
        Line2D(
            [],
            [],
            color=CROSSING_COLOUR,
            linewidth=CROSSING_WIDTH,
            label=f"Insured culvert or bridge ({len(layers['crossings'])})",
        ),
    ]


def draw_hazard(ax, layers):
    """Panel 2: what the earthquake does to the ground."""
    start_panel(ax, "hazard")
    states = draw_ld_cells(ax, layers["ld_state"])
    slides = layers["slides"]
    by_class = {
        name: slides[slides["land_class"] == name]
        for name in slides["land_class"].unique()
    }
    imminent = by_class.get("imminent land", slides.iloc[:0])
    evacuated = by_class.get("evacuated land", slides.iloc[:0])
    inundated = by_class.get("inundated land", slides.iloc[:0])
    if not imminent.empty:
        imminent.plot(ax=ax, facecolor=IMMINENT_COLOUR, edgecolor="none", zorder=4)
    if not evacuated.empty:
        evacuated.plot(ax=ax, facecolor=EVACUATED_COLOUR, edgecolor="none", zorder=5)
    if not inundated.empty:
        inundated.plot(
            ax=ax,
            facecolor=INUNDATED_COLOUR,
            alpha=INUNDATED_ALPHA,
            edgecolor="none",
            zorder=6,
        )
        inundated.plot(
            ax=ax, facecolor="none", edgecolor=INUNDATED_COLOUR, linewidth=0.7, zorder=6
        )

    pga = amplified_pga_zones(layers["pga"], layers["ground"])["amplified_pga_g"]
    ax.text(
        0.02,
        0.03,
        f"PGA {pga.min():.1f} to {pga.max():.1f} g\nwith hill slope amplification",
        transform=ax.transAxes,
        fontsize=FONT_SIZE - 1,
        ha="left",
        va="bottom",
        zorder=9,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2},
    )

    n_slides = slides["landslide_id"].nunique()
    return [
        Patch(
            facecolor=EVACUATED_COLOUR,
            label=f"Evacuated ground ({n_slides} landslides)",
        ),
        Patch(
            facecolor=INUNDATED_COLOUR,
            alpha=0.6,
            edgecolor=INUNDATED_COLOUR,
            label="Inundated ground",
        ),
        Patch(facecolor=IMMINENT_COLOUR, label="Imminent ground"),
        *[
            Patch(
                facecolor=LD_STATE_COLOURS[state],
                alpha=0.7,
                label=f"Liquefaction {state}, {LD_STATE_LABELS[state].lower()}",
            )
            for state in states
        ],
    ]


def draw_damage(ax, layers, slide_pieces):
    """Panel 3: the state of the insured assets."""
    start_panel(ax, "damage")
    land = layers["vul_land"]
    states = land["Liq_LD_state"]
    liquefied = land[states.fillna(0) >= LD_LOWEST_STATE_SHOWN]
    for state, rows in liquefied.groupby(liquefied["Liq_LD_state"].astype(int)):
        rows.plot(
            ax=ax,
            facecolor=LD_STATE_COLOURS[state],
            alpha=LD_PROPERTY_ALPHA,
            edgecolor="none",
            zorder=2,
        )
    layers["land"].boundary.plot(ax=ax, color="#52514e", linewidth=0.3, zorder=3)

    off_land = layers["slides"][layers["slides"]["land_class"] != "imminent land"]
    off_land.plot(ax=ax, facecolor="none", edgecolor="#52514e", linewidth=0.4, zorder=4)
    for name, colour in (
        ("evacuated land", EVACUATED_COLOUR),
        ("inundated land", INUNDATED_COLOUR),
    ):
        part = slide_pieces[slide_pieces["land_class"] == name]
        if not part.empty:
            part.plot(ax=ax, facecolor=colour, edgecolor="none", zorder=5)

    walls = layers["vul_walls"].assign(damaged=wall_damage(layers["vul_walls"]))
    crossings = layers["vul_crossings"].assign(
        damaged=crossing_damage(layers["vul_crossings"])
    )
    draw_lines(
        ax,
        walls[~walls["damaged"]],
        colour=UNDAMAGED_COLOUR,
        width=WALL_WIDTH - 0.4,
        style=(0, (3, 1.5)),
    )
    draw_lines(ax, walls[walls["damaged"]], colour=DAMAGED_COLOUR, width=WALL_WIDTH)
    draw_lines(
        ax,
        crossings[~crossings["damaged"]],
        colour=UNDAMAGED_COLOUR,
        width=CROSSING_WIDTH - 0.4,
        style=(0, (3, 1.5)),
        zorder=7,
    )
    draw_lines(
        ax,
        crossings[crossings["damaged"]],
        colour=DAMAGED_COLOUR,
        width=CROSSING_WIDTH,
        zorder=7,
    )
    label_crossings(ax, layers["crossings"])

    n_damaged = int(walls["damaged"].sum())
    shown = sorted(int(state) for state in liquefied["Liq_LD_state"].unique())
    return [
        Line2D(
            [],
            [],
            color=DAMAGED_COLOUR,
            linewidth=WALL_WIDTH,
            label=f"Wall or culvert damaged ({n_damaged} of {len(walls)} walls, "
            f"{int(crossings['damaged'].sum())} of {len(crossings)} culverts)",
        ),
        Line2D(
            [],
            [],
            color=UNDAMAGED_COLOUR,
            linewidth=WALL_WIDTH - 0.4,
            linestyle=(0, (3, 1.5)),
            label="Wall or culvert not damaged",
        ),
        Patch(facecolor=EVACUATED_COLOUR, label="Evacuated ground on insured land"),
        Patch(facecolor=INUNDATED_COLOUR, label="Inundated ground on insured land"),
        Patch(
            facecolor="none",
            edgecolor="#52514e",
            linewidth=0.4,
            label="Landslide ground outside insured land",
        ),
        *[
            Patch(
                facecolor=LD_STATE_COLOURS[state],
                alpha=0.8,
                label=f"Property liquefaction {state}, {LD_STATE_LABELS[state].lower()}",
            )
            for state in shown
        ],
    ]


def draw_cost(ax, layers, costs):
    """Panel 4: what it costs, every item on one scale."""
    start_panel(ax, "cost")
    cmap = plt.get_cmap(COST_CMAP, len(COST_BREAKS_NZD))
    norm = BoundaryNorm(COST_BREAKS_NZD, cmap.N, extend="max")

    def colour(frame):
        return [cmap(norm(value)) for value in frame["cost_nzd"]]

    layers["land"].boundary.plot(ax=ax, color="#52514e", linewidth=0.3, zorder=2)
    if not costs["liquefaction"].empty:
        costs["liquefaction"].plot(
            ax=ax,
            color=colour(costs["liquefaction"]),
            alpha=0.45,
            edgecolor="none",
            zorder=2,
        )
    if not costs["landslide"].empty:
        costs["landslide"].plot(
            ax=ax,
            color=colour(costs["landslide"]),
            edgecolor="#1a1a19",
            linewidth=0.2,
            zorder=5,
        )

    walls = layers["vul_walls"]
    undamaged = walls[~wall_damage(walls)]
    if not undamaged.empty:
        undamaged.plot(
            ax=ax, color=NO_COST_COLOUR, linewidth=WALL_WIDTH - 0.3, zorder=6
        )
    for kind, width, zorder in (
        ("walls", WALL_WIDTH + 0.2, 6),
        ("crossings", CROSSING_WIDTH, 7),
    ):
        frame = costs[kind]
        for (_, row), line_colour in zip(frame.iterrows(), colour(frame), strict=True):
            ax.plot(
                *row.geometry.xy,
                color=line_colour,
                linewidth=width,
                zorder=zorder,
                solid_capstyle="butt",
                path_effects=[
                    Stroke(linewidth=width + CASING_WIDTH, foreground="#1a1a19"),
                    Stroke(),
                ],
            )
    label_crossings(ax, layers["crossings"])
    return cmap, norm


def draw_key(ax, handles, title):
    """One panel's key, in the strip beneath it."""
    ax.axis("off")
    ax.legend(
        handles=handles,
        loc="upper left",
        ncol=1,
        frameon=False,
        fontsize=FONT_SIZE - 1,
        handlelength=2.2,
        borderaxespad=0.2,
        title=title,
        title_fontsize=FONT_SIZE,
        alignment="left",
    )


def draw_cost_key(fig, ax, cmap, norm):
    """The cost scale as a banded bar, with what is and is not on it."""
    ax.axis("off")
    bar = ax.inset_axes((0.02, 0.72, 0.94, 0.1))
    colourbar = fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap),
        cax=bar,
        orientation="horizontal",
        extend="max",
        spacing="uniform",
    )
    colourbar.set_ticks(COST_BREAKS_NZD)
    colourbar.set_ticklabels(
        [f"${value / 1e3:,.0f}k" if value else "$0" for value in COST_BREAKS_NZD]
    )
    colourbar.ax.tick_params(labelsize=FONT_SIZE - 1.5, length=2)
    colourbar.outline.set_linewidth(0.4)
    ax.text(
        0.02,
        1.0,
        "Repair cost per item, NZD incl GST",
        fontsize=FONT_SIZE,
        va="top",
        transform=ax.transAxes,
    )
    ax.text(
        0.02,
        0.5,
        "Walls and culverts are coloured by their line; landslide ground on\n"
        "insured land by its fill; liquefaction repair by the property's fill.\n"
        "Grey walls cost nothing. Each claim's cost is split over its items.",
        fontsize=FONT_SIZE - 1,
        va="top",
        transform=ax.transAxes,
        linespacing=1.3,
    )


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------


def describe(layers, slide_pieces, costs):
    """Print the window's numbers for the caption, and the checks on them."""
    settlement = layers["settlement"]
    print(RULE)
    print(
        f"Window {config.WINDOW_NZTM}, extent {config.EXTENT}, "
        f"w{config.WORLD_ID:03d} r{config.REALISATION_ID:03d}"
    )
    print(
        f"{len(layers['land']):,} claims, {len(layers['walls']):,} insured walls, "
        f"{len(layers['crossings']):,} crossings, "
        f"{layers['slides']['landslide_id'].nunique():,} landslides"
    )
    print(RULE)
    print("Repair cost over the claims in the window (NZD incl GST):")
    columns = [
        ("wall_repair_cost_incl_gst_nzd", "walls"),
        ("land_repair_cost_incl_gst_nzd", "landslide land repair"),
        ("spoil_removal_cost_incl_gst_nzd", "landslide spoil removal"),
        ("liquefaction_repair_cost_incl_gst_nzd", "liquefaction"),
        ("crossing_repair_cost_incl_gst_nzd", "culverts and bridges"),
        ("professional_fees_incl_gst_nzd", "professional fees (not drawn)"),
        ("repair_cost_incl_gst_nzd", "total repair cost"),
        ("settlement_incl_gst_nzd", "total settlement, after cap and excess"),
    ]
    for column, label in columns:
        print(f"  {settlement[column].sum():>14,.0f}  {label}")
    print(RULE)
    print("Cost handed to items, against the claims' totals:")
    landslide = (
        settlement["land_repair_cost_incl_gst_nzd"]
        + settlement["spoil_removal_cost_incl_gst_nzd"]
    )
    checks = [
        ("walls", settlement["wall_repair_cost_incl_gst_nzd"].sum()),
        ("crossings", settlement["crossing_repair_cost_incl_gst_nzd"].sum()),
        ("landslide", landslide.sum()),
        ("liquefaction", settlement["liquefaction_repair_cost_incl_gst_nzd"].sum()),
    ]
    for kind, total in checks:
        drawn = costs[kind]["cost_nzd"].sum()
        print(
            f"  {kind:<13} drawn {drawn:>12,.0f}  of {total:>12,.0f}"
            f"  ({drawn / total:.0%})"
            if total
            else f"  {kind:<13} none"
        )
    print(
        "  Short of 100% is cost on a claim in the window with no damaged item\n"
        "  of that kind drawn inside it."
    )
    print(RULE)
    vul = layers["vul_land"]
    for name, column in (
        ("evacuated land", "evacuated_area"),
        ("inundated land", "inundated_insured_area"),
    ):
        drawn = slide_pieces.loc[slide_pieces["land_class"] == name].area.sum()
        print(
            f"  {name}: {drawn:,.0f} m² drawn on insured land, "
            f"{vul[column].sum():,.0f} m² in the vul land table"
        )


def plot_chain_map(layers):
    """Draw the four panel figure and return it."""
    slide_pieces = landslide_on_insured_land(layers["slides"], layers["land"])
    costs = item_costs(layers, slide_pieces)
    describe(layers, slide_pieces, costs)

    plt.rcParams.update({"font.size": FONT_SIZE})
    fig = plt.figure(figsize=FIGSIZE)
    grid = fig.add_gridspec(
        4,
        2,
        height_ratios=[3, 1.2, 3, 1.2],
        hspace=0.06,
        wspace=0.06,
        left=0.01,
        right=0.99,
        top=0.97,
        bottom=0.04,
    )
    panels = [
        ("1  Exposure", "What is insured", grid[0, 0], grid[1, 0]),
        ("2  Hazard", "What the earthquake does to the ground", grid[0, 1], grid[1, 1]),
        ("3  Damage", "State of insured assets", grid[2, 0], grid[3, 0]),
        ("4  Cost", "What it costs to repair", grid[2, 1], grid[3, 1]),
    ]
    axes = [
        (fig.add_subplot(map_cell), fig.add_subplot(key_cell))
        for *_, map_cell, key_cell in panels
    ]
    for (title, subtitle, *_), (ax, _) in zip(panels, axes, strict=True):
        ax.set_title(
            f"$\\bf{{{title.replace(' ', '~')}}}$   {subtitle}",
            loc="left",
            fontsize=FONT_SIZE + 1,
            pad=3,
        )

    draw_key(axes[0][1], draw_exposure(axes[0][0], layers), None)
    draw_key(axes[1][1], draw_hazard(axes[1][0], layers), None)
    draw_key(axes[2][1], draw_damage(axes[2][0], layers, slide_pieces), None)
    draw_cost_key(fig, axes[3][1], *draw_cost(axes[3][0], layers, costs))

    fig.text(
        axes[2][0].get_position().x0,
        0.01,
        f"One modelled {config.RETURN_PERIOD_YR:,}-year earthquake (world {config.WORLD_ID}, "
        f"realisation {config.REALISATION_ID}). Repair costs before the land cover cap "
        "and excess; professional fees not shown.\n"
        "Imagery: Esri World Imagery. Buildings and property boundaries: LINZ, CC BY 4.0. "
        "Liquefaction cracks and ejecta are modelled as areas per property, so are not mapped.",
        fontsize=FONT_SIZE - 1.5,
        color="#52514e",
        va="bottom",
    )
    return fig


def main(*, extent, world_id, realisation_id):
    """Read the layers, draw the figure and write it."""
    layers = read_layers(extent, world_id, realisation_id)
    fig = plot_chain_map(layers)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / FIG_NAME
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(RULE)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
    )
