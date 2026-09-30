"""Tests for assigning the TS1170.5 site class from Vs30 and selecting by it."""

import numpy as np
import pytest
import xarray as xr

from landloss.hazard.shaking.site_class import (
    select_by_site_class,
    ts1170_site_class_from_vs30,
)


@pytest.mark.parametrize(
    ("vs30", "expected"),
    [
        (900.0, 1),
        (750.1, 1),
        (750.0, 2),
        (450.1, 2),
        (450.0, 3),
        (300.0, 4),
        (250.0, 5),
        (200.0, 6),
        (150.0, 6),
        (100.0, 6),
    ],
)
def test_table_3_3_bounds_are_upper_inclusive(vs30, expected) -> None:
    """Each bound belongs to the softer class; Class VII comes back as VI."""
    assert ts1170_site_class_from_vs30(np.array([vs30]))[0] == expected


def test_nan_vs30_stays_nan() -> None:
    """No Vs30, no site class."""
    result = ts1170_site_class_from_vs30(np.array([np.nan, 500.0]))

    assert np.isnan(result[0])
    assert result[1] == 2


def test_a_dataarray_keeps_its_coordinates() -> None:
    """The class grid comes back on the Vs30 grid."""
    vs30 = xr.DataArray(
        [[800.0, 220.0]], dims=("y", "x"), coords={"y": [1.0], "x": [0.0, 1.0]}
    )

    result = ts1170_site_class_from_vs30(vs30)

    assert isinstance(result, xr.DataArray)
    assert result.name == "site_class"
    np.testing.assert_array_equal(result.x, vs30.x)
    np.testing.assert_array_equal(result.values, [[1.0, 5.0]])


def grid(values):
    """A 1 by n grid on fixed coordinates."""
    values = np.asarray(values, dtype=float)[np.newaxis, :]
    return xr.DataArray(
        values,
        dims=("y", "x"),
        coords={"y": [0.0], "x": np.arange(values.shape[1], dtype=float)},
    )


def test_each_cell_takes_its_own_class_grid() -> None:
    """Class 2 cells read the class 2 grid, class 5 cells the class 5 grid."""
    site_class = grid([2, 5, np.nan, 2])
    grids = {2: grid([1.0, 1.1, 1.2, 1.3]), 5: grid([5.0, 5.1, 5.2, 5.3])}

    result = select_by_site_class(site_class, grids)

    np.testing.assert_array_equal(result.values, [[1.0, 5.1, np.nan, 1.3]])


def test_a_class_without_a_grid_is_refused() -> None:
    """A missing class would otherwise silently come back as NaN."""
    with pytest.raises(ValueError, match="site class"):
        select_by_site_class(grid([2, 3]), {2: grid([1.0, 1.0])})


def test_a_grid_of_the_wrong_shape_is_refused() -> None:
    """Grids are matched by position, so the shapes must agree."""
    with pytest.raises(ValueError, match="not"):
        select_by_site_class(grid([2, 2]), {2: grid([1.0, 1.0, 1.0])})
