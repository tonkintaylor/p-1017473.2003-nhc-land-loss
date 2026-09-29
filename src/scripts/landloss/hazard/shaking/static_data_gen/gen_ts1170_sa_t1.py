r"""Generate TS1170.5:2025 Sa(1.0 s) grids from Table 3.2, on the NLM's grid.

Run:

    uv run --frozen python src/scripts/landloss/hazard/shaking/static_data_gen/gen_ts1170_sa_t1.py

For every return period and site class in SNZ TS 1170.5:2025 Table 3.2 (7 x 6,
so 42 grids), this evaluates the clause 3.1.2 spectrum at T = 1.0 s at each
0.1 degree grid point (``landloss.hazard.shaking.spectrum.ts1170_sa``). It then
rasterises the points on their own 0.1 degree lat/lon grid (EPSG:4167) and
warps that raster to NZTM (EPSG:2193) by nearest neighbour.

That warp is how the National Liquefaction Model's seismic-standard PGA grids
were made. Applying it to the table's own PGA column reproduces the NLM's
``pga_2500yr_site_class_5.tif`` exactly: every cell, the nodata footprint and
the transform (149 x 114 cells, about 9,927 m a cell). So these Sa(1.0 s) grids
line up cell for cell with the NLM PGA grids and come from the same numbers.

Writes one GeoTIFF per return period and site class, named by
``landloss.io.ts1170.ts1170_sa_t1_fname``, to every folder in ``output_dirs``:
by default the local cache mirror of ``landloss.io.ts1170.TS1170_SA_T1_DIR``,
so ``get_ts1170_sa_t1`` reads them straight away, and a staging folder to copy
onto the data library from. A copy of this script is kept beside the grids
there as the record of how they were made.
"""

from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr

import tdrive_sync
from landloss.hazard.shaking.spectrum import ts1170_sa
from landloss.io import ts1170

PERIOD_S = 1.0

# The table's grid spacing, in degrees.
GRID_STEP_DEG = 0.1

# NZGD2000 geographic, the datum the TS's lat/lon grid is taken to be on. The
# warp gives the same NZTM grid whether the points are read as NZGD2000 or
# WGS84, so the choice does not change the output.
TABLE_CRS = "EPSG:4167"
OUTPUT_CRS = "EPSG:2193"


def rasterise_points(values, *, latitude, longitude) -> xr.DataArray:
    """Place grid-point values on a complete 0.1 degree lat/lon raster.

    Grid points the table does not carry (offshore) are left as NaN, and the
    axes are filled out to every 0.1 degree step so the raster's spacing is
    regular even where a whole row or column of points is missing.

    Args:
        values: One value per grid point.
        latitude: Each grid point's latitude, in degrees.
        longitude: Each grid point's longitude, in degrees.

    Returns:
        A north-up raster in :data:`TABLE_CRS`, nodata as NaN.
    """
    lat_idx = np.rint(np.asarray(latitude) / GRID_STEP_DEG).astype(int)
    lon_idx = np.rint(np.asarray(longitude) / GRID_STEP_DEG).astype(int)
    rows = lat_idx.max() - lat_idx
    cols = lon_idx - lon_idx.min()

    grid = np.full((rows.max() + 1, cols.max() + 1), np.nan, dtype="float32")
    grid[rows, cols] = values

    raster = xr.DataArray(
        grid,
        dims=("y", "x"),
        coords={
            "y": (lat_idx.max() - np.arange(grid.shape[0])) * GRID_STEP_DEG,
            "x": (lon_idx.min() + np.arange(grid.shape[1])) * GRID_STEP_DEG,
        },
    )
    return raster.rio.write_crs(TABLE_CRS).rio.write_nodata(np.nan)


def main(*, output_dirs: list[Path]) -> None:
    """Generate every Sa(1.0 s) grid and write it to each output folder.

    Args:
        output_dirs: The folders to write the GeoTIFFs to, created if missing.
    """
    table = ts1170.get_ts1170_table_3_2()

    for output_dir in output_dirs:
        output_dir.mkdir(parents=True, exist_ok=True)

    for (return_period_yr, site_class), rows in table.groupby(
        ["return_period_yr", "site_class"]
    ):
        sa_t1 = ts1170_sa(
            PERIOD_S,
            pga_g=rows["pga_g"],
            sa_s_g=rows["sa_s_g"],
            tc_s=rows["tc_s"],
            td_s=rows["td_s"],
        )
        raster = rasterise_points(
            sa_t1, latitude=rows["latitude"], longitude=rows["longitude"]
        ).rio.reproject(OUTPUT_CRS)
        raster.attrs = {
            "long_name": f"Sa({PERIOD_S} s) (g)",
            "source": "SNZ TS 1170.5:2025 Table 3.2, clause 3.1.2 spectrum",
            "return_period_yr": return_period_yr,
            "site_class": site_class,
        }

        fname = ts1170.ts1170_sa_t1_fname(int(return_period_yr), int(site_class))
        for output_dir in output_dirs:
            raster.rio.to_raster(output_dir / fname)
        print(f"Wrote {fname}")


if __name__ == "__main__":
    main(
        output_dirs=[
            tdrive_sync.get_cached_local_path(ts1170.TS1170_SA_T1_DIR),
            Path.home() / "Downloads" / "my" / ts1170.TS1170_SA_T1_DIR.name,
        ]
    )
