"""Draw what one pair's urban draw wrote: survivors, absorbed and superseded walls.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s9_urban_slope_realisation/fig_urban_slope_realisation.py

Reads the two files ``gen_urban_slope_realisation.py`` wrote for the pair,
through its ``combined_realisation_path`` and ``urban_wall_outcome_path``, so
the figure shows the draw the run wrote and nothing drawn again. The model file
of the world (step 8's ``urban_slope_model_path``) supplies only the faces
behind the map and the evacuated polygons of the walls' polygons the outcome
table names; every ``slope_id`` the run wrote has to be in it, or the script
stops and asks for step 9 to be rerun. It reads ``config.py`` beside it, the
same file the run reads, and draws the first world and earthquake listed there.

One map over the extent: every model polygon's face, faint; the evacuated
polygons of the surviving urban failures, from the combined realisation; the
evacuated polygons of the walls' polygons the outcome table records as absorbed
by a larger failure or superseded by a large-model landslide; and the
large-model evacuated polygons outlined over the top so a superseded polygon
can be seen inside the landslide that took it. The run writes no per-polygon
outcome, so an absorbed or superseded polygon that carries no wall is not
coloured; it lies under the survivor or the large landslide that took it, both
of which are drawn.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/landslide/urban-slope-realisation/fig/``, which is gitignored;
the script is the record of how it was made.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.landslide.land_class import EVACUATED, LAND_CLASS_COLUMN
from landloss.hazard.landslide.urban import realisation as urban
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import config
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
    urban_wall_outcome_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic.
FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-realisation" / "fig"
DPI = 200

# One colour per layer, keyed by the outcome it shows. The model faces sit
# under everything, faint, so the failures read against them; the three taken
# kinds are told apart by hue because they are settled differently downstream.
LAYER_COLOURS = {
    urban.STANDING: ("#bdbdbd", "Modelled polygon"),
    urban.FAILED_WITH_POLYGON: ("#a50026", "Failed, surviving"),
    urban.ABSORBED: ("#f46d43", "Wall's polygon absorbed by a larger failure"),
    urban.SUPERSEDED: (
        "#542788",
        "Wall's polygon superseded by a large-model landslide",
    ),
}
FILL_ALPHA = {
    urban.STANDING: 0.35,
    urban.FAILED_WITH_POLYGON: 0.9,
    urban.ABSORBED: 0.8,
    urban.SUPERSEDED: 0.8,
}
LARGE_EDGE_COLOUR = "#1a1a1a"

RULE = "-" * 72


def read_outputs(world_id, realisation_id, *, extent):
    """Read what the run wrote for the pair, and the world's model file.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        ``(model, combined, outcomes)``: the model file, the combined
        realisation and the wall outcome table.
    """
    model = gpd.read_parquet(urban_slope_model_path(world_id, extent=extent))
    combined = gpd.read_parquet(
        combined_realisation_path(world_id, realisation_id, extent=extent)
    )
    outcomes = pd.read_parquet(
        urban_wall_outcome_path(world_id, realisation_id, extent=extent)
    )
    return model, combined, outcomes


def outcome_layers(model, combined, outcomes):
    """Split what the run wrote into the layers the map draws.

    Args:
        model: The world's model file, for the faces and the evacuated
            polygons of the walls' polygons.
        combined: The combined realisation the run wrote.
        outcomes: The wall outcome table the run wrote.

    Returns:
        ``(layers, large_evacuated)``: one frame per key of
        :data:`LAYER_COLOURS` -- the model faces under ``standing``, the
        surviving urban evacuated polygons under ``failed_with_polygon``, and
        the evacuated polygons of the walls' polygons recorded as ``absorbed``
        or ``superseded`` -- and the large-model evacuated polygons.

    Raises:
        ValueError: If the run wrote a ``slope_id`` the model file does not
            carry, which means step 7 or 8 was rerun after step 9.
    """
    evacuated = combined[combined[LAND_CLASS_COLUMN] == EVACUATED]
    population = evacuated[urban.POPULATION_COLUMN]
    surviving = evacuated[population == urban.URBAN]
    large_evacuated = evacuated[population == urban.LARGE]

    written = pd.concat(
        [surviving[urban.SLOPE_ID_COLUMN], outcomes[urban.SLOPE_ID_COLUMN]]
    ).dropna()
    missing = sorted(set(written) - set(model[urban.SLOPE_ID_COLUMN]))
    if missing:
        msg = (
            f"{len(missing):,} slope_ids the run wrote are not in the model file "
            f"(first {missing[:3]}); step 7 or 8 was rerun after step 9, so rerun "
            "step 9 before drawing it"
        )
        raise ValueError(msg)

    polygon_evacuated = gpd.GeoDataFrame(
        {urban.SLOPE_ID_COLUMN: model[urban.SLOPE_ID_COLUMN].to_numpy()},
        geometry=gpd.GeoSeries(model[urban.EVACUATED_GEOMETRY_COLUMN]).to_numpy(),
        crs=model.crs,
    )
    layers = {
        urban.STANDING: model[["geometry"]],
        urban.FAILED_WITH_POLYGON: surviving,
    }
    for outcome in (urban.ABSORBED, urban.SUPERSEDED):
        slope_ids = outcomes.loc[
            outcomes[urban.OUTCOME_COLUMN] == outcome, urban.SLOPE_ID_COLUMN
        ].dropna()
        layers[outcome] = polygon_evacuated[
            polygon_evacuated[urban.SLOPE_ID_COLUMN].isin(slope_ids)
        ]
    return layers, large_evacuated


def draw_map(ax, layers, large_evacuated, extent):
    """Draw the layers in order, then the large evacuated outlines over them."""
    for name, (colour, _) in LAYER_COLOURS.items():
        layer = layers[name]
        if layer.empty:
            continue
        layer.plot(
            ax=ax,
            color=colour,
            edgecolor=colour,
            linewidth=0.3,
            alpha=FILL_ALPHA[name],
        )
    if not large_evacuated.empty:
        large_evacuated.plot(
            ax=ax, facecolor="none", edgecolor=LARGE_EDGE_COLOUR, linewidth=0.8
        )
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )


def build_figure(model, layers, large_evacuated, *, title):
    """Assemble the map and its legend."""
    fig, ax = plt.subplots(figsize=(9, 8))
    extent = gpd.GeoDataFrame(geometry=[box(*model.total_bounds)], crs=model.crs)
    draw_map(ax, layers, large_evacuated, extent)
    ax.set_title(title, fontsize=9)

    handles = [
        Patch(
            facecolor=colour,
            edgecolor="none",
            label=f"{label} ({len(layers[name]):,})",
        )
        for name, (colour, label) in LAYER_COLOURS.items()
    ]
    handles.append(
        Line2D(
            [0],
            [0],
            color=LARGE_EDGE_COLOUR,
            linewidth=0.8,
            label=f"Large-model evacuated polygon ({len(large_evacuated):,})",
        )
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=2,
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(bottom=0.12)
    return fig


def main(*, extent, world_id, realisation_id):
    """Draw what the run wrote for one pair over the extent it was run for.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
            Must match the setting the generation was run with.
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
    """
    combined_path = combined_realisation_path(world_id, realisation_id, extent=extent)
    figure_path = FIG_DIR / f"{combined_path.stem}.png"
    print(
        f"Reading what the run wrote for world {world_id}, earthquake {realisation_id}"
    )
    model, combined, outcomes = read_outputs(world_id, realisation_id, extent=extent)
    layers, large_evacuated = outcome_layers(model, combined, outcomes)

    print(RULE)
    for name, (_, label) in LAYER_COLOURS.items():
        print(f"{label}: {len(layers[name]):,} polygons")
    print(f"Large-model evacuated polygons: {len(large_evacuated):,}")

    fig = build_figure(
        model,
        layers,
        large_evacuated,
        title=(
            f"Urban slope failures, world {world_id}, earthquake {realisation_id} "
            f"— {len(model):,} polygons"
        ),
    )
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_IDS[0],
        realisation_id=config.REALISATION_IDS[0],
    )
