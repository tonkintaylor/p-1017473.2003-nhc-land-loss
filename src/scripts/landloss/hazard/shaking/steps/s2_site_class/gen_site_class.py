r"""Write the TS1170.5 site class per 100 m cell over the extent, from Foster Vs30.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s2_site_class/gen_site_class.py

Reads the Foster et al. (2019) Vs30 model over the extent and assigns each cell
its TS1170.5:2025 Table 3.3 site class from Vs30 alone
(``landloss.hazard.shaking.site_class``; see its docstring for what Vs30 alone
leaves out). Cells the model leaves without a Vs30 value, along the harbour
edge, take the class of the nearest classed cell within 200 m
(``fill_site_class_gaps``). Cells still unclassed take the class of a default
Vs30 for their majority material on the ground map
(``fill_site_class_from_ground_map``, ``BETA_GROUND_MAP_DEFAULT_VS30_M_S``), so
ground step 2 (``ground/steps/s2_ground_map/gen_ground_map.py``) has to have been run over
the same extent first. A raster coding where each cell's class came from is
written beside the grid. The model's own grid -- 100 m NZTM cells on 100
m-aligned bounds -- is the grid written, and the grid the shaking steps that
read the site class put their demand on.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np
import rioxarray
import xarray as xr

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.shaking.site_class import (
    GAP_FILL_MAX_DISTANCE_M,
    SITE_CLASS_SOURCES,
    fill_site_class_from_ground_map,
    fill_site_class_gaps,
    site_class_source,
    ts1170_site_class_from_vs30,
)
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.io.ts1170 import SITE_CLASS_NUMERALS
from landloss.io.vs30 import get_foster_2019_vs30
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class import config
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "shaking"

RULE = "-" * 72


def resolve_extent(*, extent):
    """Return the bounding box, in NZTM, and its name for this run.

    The shaking steps all run over this extent: this step sets the grid, and
    the steps after it read the grid this step wrote.
    """
    aoi = get_area_of_interest(extent)
    if aoi is not None:
        return aoi.bbox(constants.DEFAULT_CRS), aoi.name
    areas = get_study_areas(constants.DEFAULT_CRS)
    return tuple(areas.total_bounds), "Four territorial authorities"


def site_class_path(*, extent):
    """Return the file a run writes the site class grid to.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/hazard/shaking/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"site-class-100m{suffix}.tif"


def source_path(*, extent):
    """Return the file a run writes the site class source codes to.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/hazard/shaking/``. Codes as in
        ``landloss.hazard.shaking.site_class.SITE_CLASS_SOURCES``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"site-class-source-100m{suffix}.tif"


def read_ground_map(*, extent):
    """Read ground step 2's ground map materials over the extent.

    Raises:
        FileNotFoundError: If ground step 2 has not been run over this
            extent.
    """
    path = ground_map_path(extent=extent)
    if not path.exists():
        msg = f"No ground map at {path}. Shaking step 2 reads ground step 2's "
        msg += "materials for the cells Foster leaves unclassed: run "
        msg += "ground/steps/s2_ground_map/gen_ground_map.py with "
        msg += f'EXTENT = "{extent}" first.'
        raise FileNotFoundError(msg)
    return gpd.read_parquet(path, columns=["material", "geometry"])


def read_site_class(*, extent):
    """Read the site class grid this step wrote, for the steps after it.

    Raises:
        FileNotFoundError: If step 2 has not been run over this extent.
    """
    path = site_class_path(extent=extent)
    if not path.exists():
        msg = f"No site class grid at {path}. Run s2_site_class/gen_site_class.py "
        msg += f'with EXTENT = "{extent}" first.'
        raise FileNotFoundError(msg)
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def main(*, extent):
    """Write the site class grid over the extent.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
    """
    bbox, extent_name = resolve_extent(extent=extent)
    ground = read_ground_map(extent=extent)

    print("Reading the Foster et al. (2019) Vs30 model ...", flush=True)
    vs30 = get_foster_2019_vs30(bbox)
    site_class, nearest_filled = fill_site_class_gaps(ts1170_site_class_from_vs30(vs30))
    print("Classing the rest from the ground map ...", flush=True)
    site_class, ground_filled, materials = fill_site_class_from_ground_map(
        site_class, ground.to_crs(vs30.rio.crs)
    )
    source = site_class_source(vs30.values, nearest_filled.values, ground_filled.values)

    values = vs30.values[np.isfinite(vs30.values)]
    classes = site_class.values[np.isfinite(site_class.values)]
    print(RULE)
    print(f"Extent: {extent_name}")
    print(f"Grid: {vs30.shape[0]} by {vs30.shape[1]} cells at 100 m")
    if values.size:
        print(
            f"Vs30 (m/s): min {values.min():.0f}   median {np.median(values):.0f}   "
            f"max {values.max():.0f}"
        )
    print("Cells by where their site class came from:")
    for code, name in SITE_CLASS_SOURCES.items():
        print(f"  {code} {name:<26} {int((source == code).sum()):>9,}")
    print(
        f"  (nearest classed cell within {GAP_FILL_MAX_DISTANCE_M:.0f} m; "
        "none is mostly open sea)"
    )
    filled_from = materials[ground_filled.values]
    if filled_from.size:
        print("Ground map default cells by majority material:")
        names, counts = np.unique(filled_from.astype(str), return_counts=True)
        for name, count in zip(names, counts, strict=True):
            vs30_default = constants.BETA_GROUND_MAP_DEFAULT_VS30_M_S[name]
            print(f"  {name:<20} {count:>7,}  ({vs30_default:.0f} m/s)")
    print("Site class share of cells:")
    for numeral, cls in SITE_CLASS_NUMERALS.items():
        share = np.mean(classes == cls) if classes.size else 0.0
        print(f"  {numeral:>3}: {share:6.1%}")

    print(RULE)
    path = site_class_path(extent=extent)
    write_raster(site_class.astype("float32"), path)
    print(f"Wrote {path}")
    path = source_path(extent=extent)
    # A fresh array: the Vs30 grid's float nodata does not fit uint8 codes, and
    # code 0 (no class) is a value here, not nodata.
    codes = xr.DataArray(
        source, coords=vs30.coords, dims=vs30.dims, name="site_class_source"
    ).rio.write_crs(vs30.rio.crs)
    write_raster(codes, path)
    print(f"Wrote {path}")
    print(
        "Site class is from Vs30 alone, without the profile criteria of TS1170.5 "
        "Table 3.3, and Class VII is taken as Class VI (L-38)."
    )


if __name__ == "__main__":
    main(extent=config.EXTENT)
