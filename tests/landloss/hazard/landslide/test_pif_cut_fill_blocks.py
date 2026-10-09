"""Tests that ground step 5 classes the pifs a block at a time as it would whole."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
import shapely
from affine import Affine

from landloss.domain import constants
from landloss.hazard.landslide.instability_zones import cluster_pifs, find_pips
from landloss.hazard.landslide.pif_cut_fill import gen_pif_cut_fill
from scripts.landloss.ground.steps.s5_pif_cut_fill import gen_pif_cut_fill as step

SIZE = (240, 300)
TRANSFORM = Affine(1.0, 0.0, 1000.0, 0.0, -1.0, 5000.0)


def terraced_slope():
    """A slope falling east, cut by benches every 25 m and crossed by a road."""
    rows, cols = np.indices(SIZE)
    dem = 200.0 - 0.15 * cols - 0.05 * rows
    for step_col in range(20, SIZE[1], 25):
        dem[:, step_col:] -= 2.0
    dem[100:104, :] -= 1.5
    return dem


def write_dem(dem, path):
    """Write the DEM as the step's 1 m GeoTIFF."""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=dem.shape[0],
        width=dem.shape[1],
        count=1,
        dtype="float32",
        crs=constants.DEFAULT_CRS,
        transform=TRANSFORM,
        nodata=-9999.0,
    ) as raster:
        raster.write(dem.astype("float32"), 1)


# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
@pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning")
def test_blocks_class_every_pif_as_the_whole_grid_does(tmp_path, monkeypatch):
    dem = terraced_slope().astype("float32").astype("float64")
    dem_file = tmp_path / "dem.tif"
    write_dem(dem, dem_file)
    pips = find_pips(dem, 1.0)
    labels, _ = cluster_pifs(pips.mask, 1.0)
    rows, cols = np.nonzero(labels > 0)
    # The terraces join into one long pif; cut it into 15 m pieces per terrace.
    pif_ids = (rows // 15) * 1000 + cols // 25 + 1
    direction = pips.direction[rows, cols]
    # Blocks of 60 m: many blocks, each window far smaller than the grid.
    monkeypatch.setattr(step, "BLOCK_M", 60.0)
    west, north = TRANSFORM.c, TRANSFORM.f
    land = gpd.GeoDataFrame(
        geometry=[
            shapely.box(
                west - 10, north - SIZE[0] - 10, west + SIZE[1] + 10, north + 10
            )
        ],
        crs=constants.DEFAULT_CRS,
    )

    whole = gen_pif_cut_fill(dem, TRANSFORM, pif_ids, rows, cols, direction)
    pifs, pips_table = step.cut_fill_by_block(
        dem_file, land, pif_ids, rows, cols, direction
    )

    assert len(np.unique(pif_ids)) > 20
    pd.testing.assert_frame_equal(pifs, whole.pifs, rtol=1e-9, atol=1e-6)
    pd.testing.assert_frame_equal(pips_table, whole.pips, rtol=1e-9, atol=1e-6)
