import numpy as np
import pytest

from landloss.hazard.landslide.geometry import (
    ALPHA,
    GAMMA,
    landslide_volume_m3,
    mean_depth_m,
)


def depth_of(area):
    return mean_depth_m(landslide_volume_m3(area), area)


def test_volume_follows_the_power_law():
    assert landslide_volume_m3(100.0) == pytest.approx(ALPHA * 100.0**GAMMA)


def test_depth_grows_far_more_slowly_than_area():
    # The substance of the relationship: ten times the area is about three times
    # the depth, not ten times.
    ratio = depth_of(1000.0) / depth_of(100.0)
    assert 2.5 < ratio < 3.5


def test_a_bigger_landslide_is_deeper():
    areas = np.array([3.0, 50.0, 500.0, 3000.0])
    depths = depth_of(areas)
    assert np.all(np.diff(depths) > 0)


def test_depths_over_the_sampled_range_are_physically_plausible():
    # The step samples 3 to 3000 m2; depths outside roughly 0.1 to 5 m would
    # mean alpha is wrong, which is the number most likely to be replaced.
    depths = depth_of(np.array([3.0, 3000.0]))
    assert np.all(depths > 0.1)
    assert np.all(depths < 5.0)


def test_conserving_volume_makes_a_wider_runout_shallower():
    volume = landslide_volume_m3(500.0)
    source = mean_depth_m(volume, 500.0)
    spread = mean_depth_m(volume, 1500.0)
    assert spread == pytest.approx(source / 3.0)


def test_an_equal_footprint_gives_an_equal_depth():
    # True of the beta, where the runout circle is rebuilt at the source radius.
    volume = landslide_volume_m3(200.0)
    assert mean_depth_m(volume, 200.0) == pytest.approx(depth_of(200.0))


def test_a_footprint_of_zero_gives_no_depth_rather_than_an_infinity():
    assert np.isnan(mean_depth_m(10.0, 0.0))


def test_negative_inputs_are_refused():
    with pytest.raises(ValueError, match="area_m2"):
        landslide_volume_m3(-1.0)
    with pytest.raises(ValueError, match="footprint_m2"):
        mean_depth_m(1.0, -1.0)
