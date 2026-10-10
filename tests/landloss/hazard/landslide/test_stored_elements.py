"""Tests that slope elements stored without their layers restore exactly."""

import dataclasses
import pickle

import numpy as np
import pandas as pd
import pytest
from rasterio.transform import Affine

from landloss.hazard.landslide import instability_zones as zones
from landloss.hazard.landslide import slope_elements
from landloss.hazard.landslide.slope_elements import GROUND_GROUPS

SHAPE = (40, 90)
TRANSFORM = Affine(1, 0, 0, 0, -1, SHAPE[0])


def found_on_a_cut():
    """The elements found on a 1.5 m soil cut across a gentle slope, sea in a corner."""
    _, cols = np.indices(SHAPE)
    dem = 20.0 - 0.05 * cols + np.where(cols <= 30, 1.5, 0.0)
    dem[:5, 80:] = np.nan
    ground = np.full(SHAPE, GROUND_GROUPS.index("soil_like"), dtype=np.int8)
    return dem, zones.find_instability_zones(dem, ground, TRANSFORM).found


def test_stored_elements_restore_to_the_elements_found():
    dem, found = found_on_a_cut()
    assert len(found.elements) > 0

    restored = slope_elements.restore_elements(
        slope_elements.store_elements(found), dem, 1.0
    )

    np.testing.assert_array_equal(restored.labels, found.labels)
    assert restored.labels.dtype == found.labels.dtype
    np.testing.assert_array_equal(restored.edge_roles, found.edge_roles)
    np.testing.assert_array_equal(restored.catchments, found.catchments)
    assert restored.catchment_transform == found.catchment_transform
    for name in ("elements", "stack_links", "drainage_links"):
        pd.testing.assert_frame_equal(getattr(restored, name), getattr(found, name))
    for field in dataclasses.fields(found.layers):
        np.testing.assert_array_equal(
            getattr(restored.layers, field.name), getattr(found.layers, field.name)
        )


def test_the_stored_elements_are_a_small_part_of_the_found():
    _, found = found_on_a_cut()
    stored = slope_elements.store_elements(found)
    assert len(pickle.dumps(stored)) < len(pickle.dumps(found)) / 3


def test_restoring_on_another_grid_is_refused():
    dem, found = found_on_a_cut()
    stored = slope_elements.store_elements(found)
    with pytest.raises(ValueError, match="stored elements"):
        slope_elements.restore_elements(stored, dem[:-1], 1.0)
