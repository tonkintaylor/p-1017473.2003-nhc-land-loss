"""Ground step 5: the cut and fill class of every pif, before the wall probability.

Reads the pifs ground step 4 wrote (the siz table, with each pip's fall
direction as ground step 3 found it) and the same sea-masked 1 m DEM, walks
every pip to the foot of its face, fits each pif's anchor surface to the ground
off the faces and classes the pif as cut, fill, cut and fill, uncertain or
natural (:mod:`landloss.hazard.landslide.pif_cut_fill`). The wall probability
(exposure rw step 6, wall probability and wall units) reads the class from
here: a wall is less likely on a cut, particularly in rock.

The DEM is read a block of pifs at a time (:func:`cut_fill_by_block`), never
whole: a pif's class depends only on the ground within about 70 m of its pips,
so each block reads that window, and the classes are those of a whole-grid run.

Run from the repository root, after ground step 4::

    uv run --frozen python \
        src/scripts/landloss/ground/steps/s5_pif_cut_fill/gen_pif_cut_fill.py

Settings are in ``config.py``.
"""

import math
import time

import numpy as np
import pandas as pd
import rioxarray
import shapely
from rasterio import features, windows

from landloss.common.utils import tiles
from landloss.hazard.landslide.instability_zones import read_siz_table
from landloss.hazard.landslide.pif_cut_fill import (
    CLASSES,
    FACE_BUFFER_M,
    FIT_RADIUS_M,
    FOOT_MAX_M,
    gen_pif_cut_fill,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_coastline_polygons
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import dem_path
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    CRS,
    WORK_DIR,
    dem_bbox,
)
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import siz_table_path
from scripts.landloss.ground.steps.s5_pif_cut_fill import config

# The side of a block of pifs, in metres: the pifs whose pips start in it are
# classed together, on one window of the DEM.
BLOCK_M = 1_000.0

# How far past a block's own pips the other pips are walked, in metres: a fit
# reaches FIT_RADIUS_M past a foot, a foot lies up to FOOT_MAX_M past its pip,
# and the fit skips the faces (grown by FACE_BUFFER_M) of any walk reaching
# it, which starts up to FOOT_MAX_M further on. Three metres to spare.
NEIGHBOUR_REACH_M = 2 * FOOT_MAX_M + FIT_RADIUS_M + FACE_BUFFER_M + 3.0

# How far past a block's own pips its DEM window reaches: every walk counted
# above runs to its end inside it.
WINDOW_REACH_M = NEIGHBOUR_REACH_M + FOOT_MAX_M + 3.0


def pif_cut_fill_path(*, extent):
    """Where the class of every pif is written, one row per pif."""
    return WORK_DIR / f"urban-slope-pif-cut-fill{extent_suffix(extent)}.parquet"


def pif_cut_fill_pips_path(*, extent):
    """Where every pip, its foot and the anchor surface at both are written."""
    return WORK_DIR / f"urban-slope-pif-cut-fill-pips{extent_suffix(extent)}.parquet"


def pip_cells(table, transform):
    """Every pip of the siz table as ``(pif_ids, rows, cols)``."""
    pips = table[["geometry"]].explode(index_parts=False)
    col, row = ~transform * (pips.geometry.x.to_numpy(), pips.geometry.y.to_numpy())
    return (
        pips.index.to_numpy(),
        np.floor(row).astype(int),
        np.floor(col).astype(int),
    )


def pip_directions(table):
    """Each pip's fall direction, in the order :func:`pip_cells` lists the pips.

    Ground step 3 writes the directions beside the pips (``pip_direction``),
    so they are not found again here.

    Raises:
        ValueError: If the directions do not line up with the pips.
    """
    directions = np.concatenate(table["pip_direction"].to_numpy()).astype(np.int8)
    n_pips = int(shapely.get_num_geometries(table.geometry.to_numpy()).sum())
    if directions.size != n_pips or (directions < 0).any():
        msg = (
            "The siz table's pip directions do not match its pips: rerun ground "
            "steps 3 and 4 (gen_instability_zones.py, then gen_slope_faces.py)."
        )
        raise ValueError(msg)
    return directions


def read_dem_window(dem_file, window, land):
    """One window of the 1 m DEM with the cells off the land set to no data.

    The same cells as ground step 3's ``get_dem`` holds at those rows and
    columns.

    Returns:
        ``(dem, transform)``.
    """
    grid = tiles.read_window(dem_file, window)
    dem = grid.to_numpy().astype("float64")
    transform = grid.rio.transform()
    # Cut to the window first: a burn costs time in the coastline's vertices.
    near = tiles.clip_to_window(land, grid.rio.bounds(), 2 * abs(transform.a))
    on_land = np.zeros(dem.shape, dtype=bool)
    if not near.empty:
        on_land = features.rasterize(
            [(geometry, 1) for geometry in near.geometry],
            out_shape=dem.shape,
            transform=transform,
            fill=0,
            dtype="uint8",
        ).astype(bool)
    return np.where(on_land, dem, np.nan), transform


def cut_fill_by_block(dem_file, land, pif_ids, rows, cols, direction):
    """Class every pif, a block of pifs at a time on its own window of the DEM.

    A pif belongs to the block holding its pips' top left corner. The block's
    pifs are classed with every other pip within :data:`NEIGHBOUR_REACH_M`
    walked too, since the fits skip their faces, on a window reaching
    :data:`WINDOW_REACH_M` past the block's pips; only the block's own pifs
    are kept.

    Args:
        dem_file: The 1 m DEM.
        land: The LINZ land polygons.
        pif_ids: The pif of each pip.
        rows: The row of each pip on the DEM.
        cols: Its column.
        direction: Its fall direction.

    Returns:
        ``(pifs, pips)`` as :func:`gen_pif_cut_fill` returns them over the whole
        DEM: pifs by ``pif_id``, pips in the order given.
    """
    with rioxarray.open_rasterio(dem_file) as dem:
        cell = abs(dem.rio.transform().a)
        height, width = dem.rio.height, dem.rio.width
    block_cells = round(BLOCK_M / cell)
    corner = pd.DataFrame({"pif": pif_ids, "row": rows, "col": cols}).groupby("pif")
    corner = corner[["row", "col"]].min() // block_cells
    block_of_pif = corner["row"] * (width // block_cells + 1) + corner["col"]
    block = block_of_pif.reindex(pif_ids).to_numpy()
    neighbour = math.ceil(NEIGHBOUR_REACH_M / cell)
    reach = math.ceil(WINDOW_REACH_M / cell)
    pif_frames, pip_frames = [], []
    for number in np.unique(block):
        own = block == number
        r0, r1 = rows[own].min(), rows[own].max()
        c0, c1 = cols[own].min(), cols[own].max()
        near = (
            (rows >= r0 - neighbour)
            & (rows <= r1 + neighbour)
            & (cols >= c0 - neighbour)
            & (cols <= c1 + neighbour)
        )
        top, left = max(r0 - reach, 0), max(c0 - reach, 0)
        window = windows.Window(
            left,
            top,
            min(c1 + reach + 1, width) - left,
            min(r1 + reach + 1, height) - top,
        )
        dem, transform = read_dem_window(dem_file, window, land)
        result = gen_pif_cut_fill(
            dem,
            transform,
            pif_ids[near],
            rows[near] - top,
            cols[near] - left,
            direction[near],
        )
        pif_frames.append(result.pifs.loc[np.unique(pif_ids[own])])
        kept = own[near]
        pip_frames.append(result.pips.loc[kept].set_axis(np.flatnonzero(near)[kept]))
    pifs = pd.concat(pif_frames).sort_index()
    pips = pd.concat(pip_frames).sort_index().reset_index(drop=True)
    return pifs, pips


def main(*, extent, use_cached_layers):
    """Class every pif of the extent and write the pif and pip tables.

    Args:
        extent: The extent ground step 4 was run over.
        use_cached_layers: Whether to reuse the cached LINZ coastline.
    """
    dem_file = dem_path(1, extent=extent)
    land = get_nz_coastline_polygons(
        bbox=dem_bbox(extent=extent), crs=CRS, use_cache=use_cached_layers
    )
    table = read_siz_table(siz_table_path(extent=extent))
    with rioxarray.open_rasterio(dem_file) as dem:
        transform = dem.rio.transform()
    pif_ids, rows, cols = pip_cells(table, transform)
    direction = pip_directions(table)

    start = time.perf_counter()
    pifs, pips = cut_fill_by_block(dem_file, land, pif_ids, rows, cols, direction)
    elapsed = time.perf_counter() - start

    counts = pifs["cut_fill_class"].value_counts().reindex(CLASSES, fill_value=0)
    print(f"{len(pifs):,} pifs, {len(pips):,} pips classed in {elapsed:.1f} s")
    print(counts.to_string())

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    pifs.to_parquet(pif_cut_fill_path(extent=extent))
    pips.to_parquet(pif_cut_fill_pips_path(extent=extent))
    print(f"Written to {WORK_DIR}")


if __name__ == "__main__":
    main(extent=config.EXTENT, use_cached_layers=config.USE_CACHED_LAYERS)
