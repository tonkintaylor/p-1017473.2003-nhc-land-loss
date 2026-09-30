import numpy as np
import pytest

from landloss.hazard.landslide import calibration as cal
from landloss.hazard.landslide.models.hancox_1997 import relationships as hancox


def test_scaling_preserves_the_pattern_and_hits_the_target():
    coverage = np.array([0.001, 0.002, 0.004, 0.0, np.nan])
    scaled, factor = cal.scale_to_total(coverage, 0.0625, target_km2=0.001)
    assert np.nansum(scaled * 0.0625) == pytest.approx(0.001)
    assert scaled[:3] / coverage[:3] == pytest.approx([factor] * 3)
    assert scaled[3] == 0.0
    assert np.isnan(scaled[4])


def test_scaling_caps_each_cell_and_still_hits_the_target():
    coverage = np.array([0.1, 0.5])
    scaled, _ = cal.scale_to_total(coverage, 1.0, target_km2=1.2)
    assert scaled.max() == pytest.approx(1.0)
    assert scaled.sum() == pytest.approx(1.2)


def test_an_unreachable_target_is_refused():
    with pytest.raises(ValueError, match="cannot be reached"):
        cal.scale_to_total(np.array([0.1, 0.0]), 1.0, target_km2=1.5)


def test_the_mask_removes_only_cells_beyond_the_envelope():
    reach = float(hancox.max_distance_km(7.0))
    distance = np.array([0.0, reach - 1, reach + 1])
    assert cal.extent_mask(distance, 7.0).tolist() == [True, True, False]


def test_the_mask_applies_the_intensity_threshold():
    keep = cal.extent_mask(np.array([5.0, 5.0]), 7.0, mm=np.array([6.5, 7.0]))
    assert keep.tolist() == [False, True]
    keep = cal.extent_mask(
        np.array([5.0]), 7.0, mm=np.array([6.5]), mm_threshold=hancox.MM_THRESHOLD_NZ
    )
    assert keep.tolist() == [True]


def test_transfer_function_is_monotone_and_recovers_a_known_map():
    rng = np.random.default_rng(0)
    hazard = rng.uniform(0, 1, 20_000)
    truth = 0.05 * hazard**2
    observed = np.clip(truth + rng.normal(0, 0.01, hazard.size), 0, 1)
    tf = cal.fit_transfer_function(hazard, observed, n_bins=20)
    assert np.all(np.diff(tf.coverage) >= 0)
    assert tf(np.array([0.25, 0.5, 0.9])) == pytest.approx(
        0.05 * np.array([0.25, 0.5, 0.9]) ** 2, abs=0.003
    )


def test_calibrate_reports_what_each_step_changed():
    coverage = np.array([0.02, 0.02, 0.02])
    keep = np.array([True, True, False])
    scaled, report = cal.calibrate(coverage, 1.0, keep, mw=7.0, target_km2=0.1)
    assert report.total_before_km2 == pytest.approx(0.06)
    assert report.removed_by_extent_km2 == pytest.approx(0.02)
    assert report.total_after_km2 == pytest.approx(0.1)
    assert report.scale_factor == pytest.approx(2.5)
    assert report.footprint_km2 == pytest.approx(2.0)
    assert scaled[2] == 0.0
    lo, mid, hi = report.area_affected_km2
    assert lo < mid < hi
