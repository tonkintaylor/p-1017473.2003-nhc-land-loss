"""Tests for how ground step 3 searches only near the buildings."""

import geopandas as gpd
import numpy as np
import shapely
from rasterio import windows
from rasterio.transform import Affine

from landloss.common.utils import tiles
from landloss.domain import constants
from landloss.hazard.landslide import instability_zones as zones
from landloss.hazard.landslide.slope_elements import GROUND_GROUPS
from scripts.landloss.ground.steps.s3_instability_zones import tiled

# A 1 m raster 1,000 cells square with its top left corner at (0, 1000).
RASTER = Affine(1, 0, 0, 0, -1, 1000)
TILE = tiles.Tile(
    row=0,
    col=0,
    core=windows.Window(0, 0, 600, 600),
    outer=windows.Window(0, 0, 900, 900),
    core_bounds=(0.0, 400.0, 600.0, 1000.0),
)


def buildings(*boxes):
    """Building outlines, one per (minx, miny, maxx, maxy)."""
    return gpd.GeoDataFrame(
        geometry=[shapely.box(*b) for b in boxes], crs=constants.DEFAULT_CRS
    )


def test_a_tile_is_cut_down_to_its_buildings_grown_by_reach_and_pad():
    # One house 10 m square at x 400-410, y 500-510: rows 490-500, cols 400-410.
    cropped = tiled.crop_tile(
        TILE, RASTER, buildings((400, 500, 410, 510)), reach_m=100, pad_m=50
    )
    outer = cropped.outer
    # 150 m each way, the start snapped back onto the 3 m blocks.
    assert (outer.col_off, outer.row_off) == (249, 339)
    assert (outer.col_off + outer.width, outer.row_off + outer.height) == (560, 650)
    assert outer.col_off % 3 == 0
    assert outer.row_off % 3 == 0
    assert cropped.core_bounds == TILE.core_bounds


def test_the_cut_stays_inside_the_tile():
    cropped = tiled.crop_tile(
        TILE, RASTER, buildings((10, 900, 20, 990)), reach_m=100, pad_m=100
    )
    assert (cropped.outer.col_off, cropped.outer.row_off) == (0, 0)


def test_a_tile_with_no_building_is_skipped_and_no_pad_keeps_it_whole():
    far = buildings((950, 10, 960, 20))
    assert tiled.crop_tile(TILE, RASTER, far, reach_m=100, pad_m=50) is None
    near = buildings((400, 500, 410, 510))
    assert tiled.crop_tile(TILE, RASTER, near, reach_m=100, pad_m=None) == TILE


def test_pips_outside_the_pip_area_are_dropped_before_the_pifs_are_joined():
    # A 1 m wall falling east down all 30 rows; only its north half may hold pips.
    shape = (30, 80)
    cols = np.arange(shape[1])
    dem = np.tile(np.where(cols <= 20, 1.0, 0.0), (shape[0], 1))
    ground = np.full(shape, GROUND_GROUPS.index("soil_like"), dtype=np.int8)
    transform = Affine(1, 0, 0, 0, -1, shape[0])
    area = np.zeros(shape, dtype=bool)
    area[:15] = True
    whole = zones.find_instability_zones(dem, ground, transform)
    half = zones.find_instability_zones(dem, ground, transform, pip_area=area)
    assert int((whole.pif_labels > 0).sum()) == 30
    assert int((half.pif_labels > 0).sum()) == 15
    assert not (half.pif_labels[15:] > 0).any()
    assert not half.pips.mask[15:].any()
    assert (half.pips.direction[15:] == -1).all()
    assert len(half.sizs) == 1
