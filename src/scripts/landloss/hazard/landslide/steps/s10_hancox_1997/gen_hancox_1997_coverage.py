r"""Generate Hancox model 3 large-landslide coverage.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s10_hancox_1997/gen_hancox_1997_coverage.py

The 10 m slope comes from landslide step 3 and NLM flatland from step 4.
Modified Mercalli intensity comes from each shaking realisation's PGV through
the PGV-only relation of Worden et al. (2012). Hancox et al. (1997) set the
intensity and distance envelope, Hancox (2010) sets the distribution by slope
class, and Marc et al. (2016) sets the event-wide area. The Marc interface
inputs are explicit beta settings in ``config.py`` until an NSHM interface
source geometry replaces them.
"""

import sys

import geopandas as gpd
import numpy as np
import rioxarray
from rasterio.enums import Resampling

from landloss.common.utils.terrain import cell_size, write_raster
from landloss.hazard.landslide.calibration.marc_2016 import Source, total_landsliding
from landloss.hazard.landslide.ground_map import flatland_cell_mask
from landloss.hazard.landslide.models.hancox_1997 import model
from landloss.hazard.shaking.pgv import mmi_from_pgv
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_multiscale_slope,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s10_hancox_1997 import config
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "hancox-1997-coverage"
RESOLUTION_M = 10
COVERAGE_NAME = "hancox_1997_coverage"
RULE = "-" * 72


def coverage_path(realisation_id, *, extent):
    """Return the Hancox coverage raster for one shaking realisation."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.tif"


def read_grid(path):
    """Read a raster as a loaded two-dimensional array with NaN nodata."""
    with rioxarray.open_rasterio(path, masked=True) as opened:
        grid = opened.squeeze("band", drop=True).load()
    grid.encoding.pop("_FillValue", None)
    return grid.rio.write_nodata(np.nan)


def align_pgv(pgv, slope):
    """Put the 100 m PGV field on the 10 m slope cells by nearest neighbour."""
    same_grid = (
        pgv.shape == slope.shape
        and np.array_equal(pgv["x"], slope["x"])
        and np.array_equal(pgv["y"], slope["y"])
    )
    if same_grid:
        return pgv
    aligned = pgv.rio.reproject_match(slope, resampling=Resampling.nearest)
    nodata = aligned.rio.nodata
    if nodata is not None and np.isfinite(nodata):
        aligned = aligned.where(aligned != nodata)
    return aligned.assign_coords(x=slope["x"], y=slope["y"])


def read_flatland_mask(*, extent, template):
    """Read the step 4 ground map and rasterise its flatland pieces."""
    ground = gpd.read_parquet(ground_map_path(extent=extent))
    return flatland_cell_mask(ground, template)


def marc_event_total_area_km2(
    *,
    mw,
    r0_km,
    fault_type,
    onshore_fraction,
    modal_slope_deg,
    a_topo,
):
    """Return Marc et al.'s event-wide landslide area for the run settings."""
    source = Source(
        mw=mw,
        r0_km=r0_km,
        fault_type=fault_type,
        onshore_fraction=onshore_fraction,
    )
    return total_landsliding(
        [source],
        modal_slope_deg=modal_slope_deg,
        a_topo=a_topo,
        quantity="area",
    )


def build_coverage(
    slope,
    pgv_m_s,
    *,
    on_flatland,
    mw,
    site_distance_km,
    event_total_area_km2,
):
    """Build a Hancox coverage grid on the slope raster."""
    pgv = align_pgv(pgv_m_s, slope)
    mm = mmi_from_pgv(pgv.to_numpy() * 100.0)
    cell_area_km2 = cell_size(slope) ** 2 / 1_000_000.0
    model_slope = slope.where(~np.asarray(on_flatland, dtype=bool))
    result = model.run(
        slope_deg=model_slope.to_numpy(),
        mm_intensity=mm,
        site_distance_km=site_distance_km,
        cell_area_km2=cell_area_km2,
        mw=mw,
        event_total_area_km2=event_total_area_km2,
    )
    coverage = slope.copy(data=result.coverage).rename(COVERAGE_NAME)
    coverage = coverage.rio.write_nodata(np.nan)
    return coverage, result


def describe(result, coverage, *, realisation_id):
    """Print the totals and coverage range for one realisation."""
    finite = coverage.to_numpy()
    finite = finite[np.isfinite(finite)]
    print(RULE)
    print(f"Realisation {realisation_id}")
    print(f"  Marc event total       : {result.event_total_area_km2:.3f} km2")
    print(f"  eligible study ground  : {result.eligible_area_km2:.3f} km2")
    print(f"  apportioned study total: {result.study_target_area_km2:.3f} km2")
    if finite.size:
        print(
            f"  coverage               : median {np.median(finite):.5f}, "
            f"max {finite.max():.5f}"
        )


def main(
    *,
    extent,
    realisation_ids,
    scenario_mw,
    site_distance_km,
    marc_r0_km,
    marc_fault_type,
    marc_onshore_fraction,
    marc_modal_slope_deg,
    marc_a_topo,
):
    """Write one Hancox coverage raster per shaking realisation."""
    slope_file = gen_multiscale_slope.slope_path(RESOLUTION_M, extent=extent)
    slope = read_grid(slope_file)
    on_flatland = read_flatland_mask(extent=extent, template=slope)
    event_total = marc_event_total_area_km2(
        mw=scenario_mw,
        r0_km=marc_r0_km,
        fault_type=marc_fault_type,
        onshore_fraction=marc_onshore_fraction,
        modal_slope_deg=marc_modal_slope_deg,
        a_topo=marc_a_topo,
    )

    print(RULE)
    print(f"Slope: {slope_file}")
    print(
        f"Scenario: Mw {scenario_mw:g}, {site_distance_km:g} km; Marc R0 "
        f"{marc_r0_km:g} km, {marc_fault_type}, onshore fraction "
        f"{marc_onshore_fraction:g}, modal slope {marc_modal_slope_deg:g} degrees, "
        f"A_topo {marc_a_topo:g}"
    )
    for realisation_id in realisation_ids:
        pgv_file = pgv_path(realisation_id, extent=extent)
        pgv = read_grid(pgv_file)
        coverage, result = build_coverage(
            slope,
            pgv,
            on_flatland=on_flatland,
            mw=scenario_mw,
            site_distance_km=site_distance_km,
            event_total_area_km2=event_total,
        )
        describe(result, coverage, realisation_id=realisation_id)
        out_path = coverage_path(realisation_id, extent=extent)
        write_raster(coverage.astype("float32"), out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        scenario_mw=config.SCENARIO_MW,
        site_distance_km=config.SITE_DISTANCE_KM,
        marc_r0_km=config.MARC_R0_KM,
        marc_fault_type=config.MARC_FAULT_TYPE,
        marc_onshore_fraction=config.MARC_ONSHORE_FRACTION,
        marc_modal_slope_deg=config.MARC_MODAL_SLOPE_DEG,
        marc_a_topo=config.MARC_A_TOPO,
    )
