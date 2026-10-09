r"""Generate Kritikos model 2 relative landslide hazard.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s8_kritikos_2015/gen_kritikos_2015_hazard.py

The 10 m DEM comes from ground step 1 and is aggregated to the model's 60 m
grid. Modified Mercalli intensity comes from each shaking realisation's PGV
through the PGV-only relation of Worden et al. (2012). Kritikos et al. (2015)
[kritikos_2015] set the memberships and the fuzzy gamma combination, and the
active faults are the GNS NZ Active Faults Database (read off ``R:``).

The output is the relative hazard H, 0 to 1, and the areal coverage the transfer
function fitted by ``gen_kritikos_2015_transfer_function.py`` on Northridge and
Wenchuan gives for it. The coverage is what landslide step 3 reads when its
``COVERAGE_MODEL`` is ``kritikos_2015``.
"""

import sys

import numpy as np

from landloss.common.utils.terrain import cell_size, write_raster
from landloss.hazard.landslide.models.kritikos_2015 import evaluation, inputs, model
from landloss.hazard.shaking.pgv import mmi_from_pgv
from landloss.io.active_faults import get_active_faults
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.ground.steps.s1_terrain import (
    gen_multiscale_slope,
)
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997.gen_hancox_1997_coverage import (
    align_pgv,
    read_grid,
)
from scripts.landloss.hazard.landslide.steps.s8_kritikos_2015 import config
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "kritikos-2015-hazard"
COVERAGE_STEM = "kritikos-2015-coverage"
SOURCE_RESOLUTION_M = 10
HAZARD_NAME = "kritikos_2015_hazard"
COVERAGE_NAME = "kritikos_2015_coverage"
FAULT_TERMS = ("mapped", "far_field")
RULE = "-" * 72


def hazard_path(realisation_id, *, extent):
    """Return the Kritikos relative hazard raster for one shaking realisation."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.tif"


def coverage_path(realisation_id, *, extent):
    """Return the Kritikos areal coverage raster for one shaking realisation.

    Landslide step 3 reads this when it runs with ``COVERAGE_MODEL`` set to
    ``kritikos_2015``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{COVERAGE_STEM}-r{realisation_id:03d}{suffix}.tif"


def check_transfer_function(transfer, *, gamma, tpi_window_m, fault_term):
    """Refuse a transfer function fitted for a hazard built differently.

    The curve maps this hazard to coverage only if the hazard was built the way
    it was when the curve was fitted.

    Raises:
        ValueError: If the curve's fitting settings differ from this run's.
    """
    wanted = {"gamma": gamma, "tpi_window_m": tpi_window_m, "fault_term": fault_term}
    if transfer.settings != wanted:
        msg = (
            f"The transfer function was fitted with {transfer.settings} but this "
            f"run uses {wanted}. Rerun gen_kritikos_2015_transfer_function.py."
        )
        raise ValueError(msg)


def build_inputs(dem, *, tpi_window_m, tpi_sd_m, fault_term, get_faults):
    """Build the realisation-independent layers on the 60 m grid.

    Args:
        dem: The DEM from ground step 1.
        tpi_window_m: The TPI neighbourhood width.
        tpi_sd_m: The TPI standardising deviation, or None to take it from
            the grid.
        fault_term: "mapped" or "far_field".
        get_faults: Called with a bbox in the DEM's CRS to read the mapped
            faults; not called for "far_field".

    Returns:
        The slope in degrees, the slope position class, and the fault distance
        in km, all on the 60 m grid.
    """
    if fault_term not in FAULT_TERMS:
        msg = f"fault_term must be one of {FAULT_TERMS}, not {fault_term!r}"
        raise ValueError(msg)

    dem_60m, slope = inputs.gen_slope_60m(dem)
    position = inputs.gen_slope_position(
        dem_60m, slope, window_m=tpi_window_m, tpi_sd_m=tpi_sd_m
    )
    if fault_term == "mapped":
        reach_m = inputs.FAULT_FAR_FIELD_KM * 1000.0
        left, bottom, right, top = dem_60m.rio.bounds()
        faults = get_faults(
            (left - reach_m, bottom - reach_m, right + reach_m, top + reach_m)
        )
        fault_km = inputs.gen_fault_distance_km(faults, dem_60m)
    else:
        fault_km = dem_60m.copy(data=np.where(np.isnan(dem_60m), np.nan, np.inf))
    return slope, position, fault_km.rename("fault_distance_km")


def build_hazard(slope, position, fault_km, pgv_m_s, *, gamma):
    """Build the relative hazard on the 60 m grid for one PGV realisation."""
    pgv = align_pgv(pgv_m_s, slope)
    mm = mmi_from_pgv(pgv.to_numpy() * 100.0)
    result = model.run(
        mm=mm,
        slope_deg=slope.to_numpy(),
        fault_distance_km=fault_km.to_numpy(),
        slope_position=position.to_numpy(),
        gamma=gamma,
    )
    hazard = slope.copy(data=result.hazard).rename(HAZARD_NAME)
    return hazard.rio.write_nodata(np.nan), mm, result.gentle


def describe_inputs(slope, position, fault_km, *, fault_term):
    """Print the layers' coverage, including how far the fault term saturates."""
    valid = np.isfinite(slope.to_numpy())
    print(RULE)
    print(f"Grid: {cell_size(slope):g} m, {valid.sum():,} valid cells")
    classes = position.to_numpy()[valid]
    for code, label in enumerate(("flat", "valley", "midslope", "ridge")):
        print(f"  slope position {label:<9}: {np.mean(classes == code):6.1%}")
    print(f"  slope position unclassified: {np.mean(np.isnan(classes)):6.1%}")
    km = fault_km.to_numpy()[valid]
    print(f"  fault term: {fault_term}")
    if fault_term == "mapped":
        print(f"  within 10 km of a mapped fault: {np.mean(km <= 10.0):6.1%}")
        print(f"  beyond the far field          : {np.mean(np.isinf(km)):6.1%}")


def describe(hazard, mm, gentle, *, realisation_id):
    """Print the intensity saturation and hazard range for one realisation."""
    values = hazard.to_numpy()
    valid = np.isfinite(values)
    print(RULE)
    print(f"Realisation {realisation_id}")
    print(
        f"  cells at or above MM 9 (flat top of the membership): "
        f"{np.mean(mm[valid] >= 9.0):6.1%}"
    )
    print(
        f"  cells under 5 degrees (flagged gentle)             : "
        f"{np.mean(gentle[valid]):6.1%}"
    )
    if valid.any():
        p10, p50, p90 = np.percentile(values[valid], [10, 50, 90])
        print(
            f"  H: p10 {p10:.3f}, median {p50:.3f}, p90 {p90:.3f}, "
            f"max {values[valid].max():.3f}"
        )


def describe_coverage(coverage, *, realisation_id):
    """Print the coverage the transfer function gives and the area it implies."""
    values = coverage.to_numpy()
    valid = np.isfinite(values)
    cell_km2 = cell_size(coverage) ** 2 / 1e6
    print(
        f"  coverage: mean {values[valid].mean():.3%}, "
        f"p90 {np.percentile(values[valid], 90):.3%}, "
        f"max {values[valid].max():.3%}"
    )
    print(
        f"  expected landslide source area, realisation {realisation_id}: "
        f"{np.nansum(values) * cell_km2:,.2f} km2 over "
        f"{valid.sum() * cell_km2:,.1f} km2"
    )


def main(
    *,
    extent,
    realisation_ids,
    gamma,
    tpi_window_m,
    tpi_sd_m,
    fault_term,
):
    """Write one Kritikos relative hazard and coverage raster per realisation."""
    transfer = evaluation.get_transfer_function()
    check_transfer_function(
        transfer, gamma=gamma, tpi_window_m=tpi_window_m, fault_term=fault_term
    )
    dem_file = gen_multiscale_slope.dem_path(SOURCE_RESOLUTION_M, extent=extent)
    dem = read_grid(dem_file)
    slope, position, fault_km = build_inputs(
        dem,
        tpi_window_m=tpi_window_m,
        tpi_sd_m=tpi_sd_m,
        fault_term=fault_term,
        get_faults=lambda bbox: get_active_faults(bbox=bbox),
    )

    print(RULE)
    print(f"DEM: {dem_file}")
    print(f"gamma {gamma:g}, TPI window {tpi_window_m:g} m, TPI sd {tpi_sd_m}")
    describe_inputs(slope, position, fault_km, fault_term=fault_term)
    for realisation_id in realisation_ids:
        pgv = read_grid(pgv_path(realisation_id, extent=extent))
        hazard, mm, gentle = build_hazard(slope, position, fault_km, pgv, gamma=gamma)
        describe(hazard, mm, gentle, realisation_id=realisation_id)
        coverage = hazard.copy(data=transfer(hazard.to_numpy())).rename(COVERAGE_NAME)
        coverage = coverage.rio.write_nodata(np.nan)
        describe_coverage(coverage, realisation_id=realisation_id)
        out_path = hazard_path(realisation_id, extent=extent)
        write_raster(hazard.astype("float32"), out_path)
        print(f"Wrote {out_path}")
        out_path = coverage_path(realisation_id, extent=extent)
        write_raster(coverage.astype("float32"), out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        gamma=config.GAMMA,
        tpi_window_m=config.TPI_WINDOW_M,
        tpi_sd_m=config.TPI_SD_M,
        fault_term=config.FAULT_TERM,
    )
