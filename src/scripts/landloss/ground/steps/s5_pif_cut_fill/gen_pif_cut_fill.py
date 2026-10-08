"""Ground step 5: the cut and fill class of every pif, before the wall probability.

Reads the pifs ground step 4 wrote (the siz table) and the same sea-masked
1 m DEM, walks every pip to the foot of its face, fits each pif's anchor
surface to the ground off the faces and classes the pif as cut, fill, cut and
fill, uncertain or natural (:mod:`landloss.hazard.landslide.pif_cut_fill`). The
wall probability (exposure rw step 6, wall probability and wall units) reads
the class from here: a wall is less likely on a cut, particularly in rock.

Run from the repository root, after ground step 4::

    uv run --frozen python \
        src/scripts/landloss/ground/steps/s5_pif_cut_fill/gen_pif_cut_fill.py

Settings are in ``config.py``.
"""

import time

import numpy as np

from landloss.hazard.landslide.instability_zones import find_pips, read_siz_table
from landloss.hazard.landslide.pif_cut_fill import CLASSES, gen_pif_cut_fill
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    WORK_DIR,
    get_dem,
)
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import siz_table_path
from scripts.landloss.ground.steps.s5_pif_cut_fill import config


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


def main(*, extent, use_cached_layers):
    """Class every pif of the extent and write the pif and pip tables.

    Args:
        extent: The extent ground step 4 was run over.
        use_cached_layers: Whether to reuse the cached LINZ coastline.
    """
    dem, transform, _ = get_dem(extent=extent, use_cached_layers=use_cached_layers)
    table = read_siz_table(siz_table_path(extent=extent))
    pif_ids, rows, cols = pip_cells(table, transform)

    start = time.perf_counter()
    direction = find_pips(dem, transform.a).direction[rows, cols]
    if (direction < 0).any():
        msg = (
            f"{int((direction < 0).sum())} pips of the siz table are not pips of "
            "this DEM: rerun ground steps 3 and 4 (gen_instability_zones.py, then "
            "gen_slope_faces.py)."
        )
        raise ValueError(msg)
    result = gen_pif_cut_fill(dem, transform, pif_ids, rows, cols, direction)
    elapsed = time.perf_counter() - start

    pifs = result.pifs
    counts = pifs["cut_fill_class"].value_counts().reindex(CLASSES, fill_value=0)
    print(f"{len(pifs):,} pifs, {len(result.pips):,} pips classed in {elapsed:.1f} s")
    print(counts.to_string())

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    pifs.to_parquet(pif_cut_fill_path(extent=extent))
    result.pips.to_parquet(pif_cut_fill_pips_path(extent=extent))
    print(f"Written to {WORK_DIR}")


if __name__ == "__main__":
    main(extent=config.EXTENT, use_cached_layers=config.USE_CACHED_LAYERS)
