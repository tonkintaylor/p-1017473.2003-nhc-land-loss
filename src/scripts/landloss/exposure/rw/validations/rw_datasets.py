"""What the retaining wall dataset comparison scripts share.

The per-property layer ``gen_rw_dataset_properties.py`` writes, the flags read
off it, and the populations each comparison is made over. Each population is
the properties on which the datasets being compared can all say something, so a
property is never counted as a disagreement because one dataset does not cover
it.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from scripts.landloss.exposure.rw.validations import config
from scripts.landloss.exposure.rw.validations.gen_rw_dataset_properties import (
    gns_column,
)

GNS = "GNS SLIDE"
NHC = "NHC NZMM"
CLAIMS = "Claim reports"

# Which combination of datasets records a wall, in reading order.
BOTH = "Both"
GNS_ONLY = "GNS only"
NHC_ONLY = "NHC only"
NEITHER = "Neither"


def load_properties() -> gpd.GeoDataFrame:
    """Read the per-property layer, with a boolean GNS flag at ``TOLERANCE_M``.

    Raises:
        FileNotFoundError: If ``gen_rw_dataset_properties.py`` has not been run.
    """
    if not config.PROPERTIES_PATH.exists():
        msg = (
            f"{config.PROPERTIES_PATH} is missing: run "
            "gen_rw_dataset_properties.py first."
        )
        raise FileNotFoundError(msg)
    properties = gpd.read_parquet(config.PROPERTIES_PATH)
    for tolerance in config.TOLERANCES_M:
        properties[gns_flag(tolerance)] = gns_wall(properties, tolerance)
    properties["gns_wall"] = properties[gns_flag(config.TOLERANCE_M)]
    properties["gns_walls"] = properties[gns_column(config.TOLERANCE_M, "walls")]
    return properties


def gns_flag(tolerance_m: float) -> str:
    """Return the column name of the GNS flag at a tolerance."""
    return f"gns_wall_{tolerance_m:g}m"


def gns_wall(properties: pd.DataFrame, tolerance_m: float) -> pd.Series:
    """Return whether GNS mapped a wall on each property, missing outside its area."""
    walls = properties[gns_column(tolerance_m, "walls")]
    return (walls > 0).where(walls.notna()).astype("boolean")


def gns_nhc_population(properties: pd.DataFrame) -> pd.DataFrame:
    """Return the properties both GNS and NHC cover: urban Wellington City."""
    return properties.loc[properties["in_gns_coverage"] & properties["has_nzmm"]]


def claims_population(properties: pd.DataFrame) -> pd.DataFrame:
    """Return the claimed properties whose reports say how many walls they hold."""
    return properties.loc[properties["claim_wall"].notna()]


def category(gns: pd.Series, nhc: pd.Series) -> pd.Series:
    """Return which of GNS and NHC records a wall on each property."""
    index = gns.index
    gns = gns.fillna(value=False).to_numpy(dtype=bool)
    nhc = nhc.fillna(value=False).to_numpy(dtype=bool)
    return pd.Series(
        np.select([gns & nhc, gns, nhc], [BOTH, GNS_ONLY, NHC_ONLY], default=NEITHER),
        index=index,
    )


def hex_grid(bounds: tuple[float, float, float, float], side_m: float) -> gpd.GeoSeries:
    """Return flat-topped hexagons of side ``side_m`` tiling ``bounds``."""
    minx, miny, maxx, maxy = bounds
    width = 1.5 * side_m
    height = np.sqrt(3.0) * side_m
    angles = np.deg2rad(np.arange(0, 360, 60))
    corners = np.column_stack([np.cos(angles), np.sin(angles)]) * side_m

    hexagons = []
    for column, x in enumerate(np.arange(minx, maxx + width, width)):
        offset = height / 2 if column % 2 else 0.0
        for y in np.arange(miny - offset, maxy + height, height):
            hexagons.append(shapely.Polygon(corners + np.array([x, y])))
    return gpd.GeoSeries(hexagons)
