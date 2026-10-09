"""Reads and figure styling shared by the SME validation scripts.

Every read goes through the path function of the step that wrote the file, so a
test cannot read a different run from the one the pipeline last made.
"""

import geopandas as gpd
import matplotlib as mpl
import numpy as np
import pandas as pd

from landloss.common.utils.terrain import sample_at_points
from landloss.io.readers import get_nz_building_outlines
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
    land_value_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.exposure.steps.s3_dwellings_per_property.gen_dwellings_per_property import (
    address_to_claim_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)

DPI = 200
# The model's values in the one hue, experience in ink, so the two read apart.
MODEL = mpl.colormaps["Blues"](0.85)
MODEL_LIGHT = mpl.colormaps["Blues"](0.45)
INK = "#333333"
MUTED = "#6b6b6b"
GRID = "#e5e5e5"
EXPECTED_BAND = "#d9d9d9"

EVACUATED = "evacuated land"


def style_axes(ax, *, grid_axis="x"):
    """Thin, recessive axes: no box, a light grid behind the marks."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, fig_dir, name):
    """Write a figure and return its path."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    out_path = fig_dir / name
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    print(f"Wrote {out_path}")
    return out_path


def read_insured_land(*, extent):
    """Return the insured land polygon of every claim."""
    return gpd.read_parquet(insured_land_path(extent=extent))


def read_walls(world_id, *, extent):
    """Return one exposure world's wall population."""
    return gpd.read_parquet(wall_population_path(world_id, extent=extent))


def read_failures(world_id, realisation_id, *, extent):
    """Return the evacuated land of one world and earthquake's slope failures."""
    landslides = gpd.read_parquet(
        combined_realisation_path(world_id, realisation_id, extent=extent)
    )
    return landslides[landslides["land_class"] == EVACUATED]


def property_landform(*, extent):
    """Return each claim's landform, hill or flat, and its suburb.

    A claim takes the landform most of its addresses were given by the land
    value step, with elevated flat counted as flat; ties go to hill.
    """
    addresses = gpd.read_parquet(land_value_path(extent=extent))
    links = pd.read_parquet(address_to_claim_path(extent=extent))
    merged = links.merge(
        addresses[["address_id", "landform_class", "suburb_locality"]],
        on="address_id",
    )
    merged["is_hill"] = merged["landform_class"].eq("hill")
    claims = merged.groupby("claim_id").agg(
        hill_share=("is_hill", "mean"),
        suburb=("suburb_locality", lambda s: s.mode().iloc[0]),
    )
    claims["landform"] = np.where(claims["hill_share"] >= 0.5, "hill", "flat")
    return claims[["landform", "suburb"]]


def dwelling_elevations(insured, *, extent):
    """Return the ground level at each claim's dwelling, from the 1 m DEM.

    The dwelling is the largest building outline standing in the claim's
    insured land, which is buffered off its dwellings.
    """
    buildings = get_nz_building_outlines(
        bbox=tuple(insured.total_bounds), crs=insured.crs
    )
    points = gpd.GeoDataFrame(
        {"area_m2": buildings.area.to_numpy()},
        geometry=buildings.geometry.representative_point().to_numpy(),
        crs=buildings.crs,
    )
    placed = gpd.sjoin(points, insured[["claim_id", "geometry"]], predicate="within")
    dwellings = placed.sort_values("area_m2").groupby("claim_id").tail(1)
    dwellings = dwellings.set_index("claim_id")
    return sample_at_points(dem_path(1, extent=extent), dwellings.geometry)
