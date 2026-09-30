import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from landloss.exposure.rw.beta_population import (
    BETA_MAX_PREVALENCE,
    BETA_MIN_SLOPE_DEG,
    MEDIUM_MAX_HEIGHT_M,
    SIZE_CLASSES,
    SMALL_MAX_HEIGHT_M,
    beta_wall_height_m,
    beta_wall_prevalence,
    classify_wall_size,
    wall_lines,
)

# --- prevalence and height ---------------------------------------------------


def test_flat_ground_carries_no_walls():
    assert beta_wall_prevalence(0.0) == pytest.approx(0.0)
    assert beta_wall_prevalence(BETA_MIN_SLOPE_DEG) == pytest.approx(0.0)


def test_prevalence_rises_with_slope_and_is_capped():
    assert beta_wall_prevalence(10.0) > beta_wall_prevalence(5.0)
    assert beta_wall_prevalence(80.0) == pytest.approx(BETA_MAX_PREVALENCE)


def test_a_steeper_property_gets_a_taller_wall():
    assert beta_wall_height_m(20.0) > beta_wall_height_m(5.0)


def test_height_is_bounded_however_steep_the_ground():
    assert beta_wall_height_m(89.0) == pytest.approx(beta_wall_height_m(25.0))


# --- size classes ------------------------------------------------------------


def test_the_size_classes_split_on_the_agreed_heights():
    classes = classify_wall_size(
        np.array([0.5, SMALL_MAX_HEIGHT_M, 2.0, MEDIUM_MAX_HEIGHT_M, 4.0])
    )
    assert list(classes) == ["small", "medium", "medium", "large", "large"]


def test_every_class_is_one_of_the_three():
    classes = classify_wall_size(np.linspace(0.1, 6.0, 50))
    assert set(classes) <= set(SIZE_CLASSES)


# --- geometry ----------------------------------------------------------------


def test_a_wall_lies_across_the_slope_not_down_it():
    # Downhill due east, so the wall runs north-south.
    points = gpd.GeoSeries([Point(0.0, 0.0)], crs="EPSG:2193")
    line = wall_lines(points, np.array([90.0]), np.array([10.0])).iloc[0]
    (x0, y0), (x1, y1) = line.coords
    assert x1 - x0 == pytest.approx(0.0, abs=1e-9)
    assert abs(y1 - y0) == pytest.approx(10.0)


def test_a_wall_is_the_length_it_was_given():
    points = gpd.GeoSeries([Point(0.0, 0.0)], crs="EPSG:2193")
    line = wall_lines(points, np.array([37.0]), np.array([14.0])).iloc[0]
    assert line.length == pytest.approx(14.0)


def test_a_wall_is_centred_on_its_property():
    points = gpd.GeoSeries([Point(5.0, 7.0)], crs="EPSG:2193")
    line = wall_lines(points, np.array([0.0]), np.array([8.0])).iloc[0]
    assert line.centroid.x == pytest.approx(5.0)
    assert line.centroid.y == pytest.approx(7.0)


def test_mismatched_inputs_are_refused():
    points = gpd.GeoSeries([Point(0.0, 0.0)], crs="EPSG:2193")
    with pytest.raises(ValueError, match="must match"):
        wall_lines(points, np.array([0.0, 90.0]), np.array([8.0]))
