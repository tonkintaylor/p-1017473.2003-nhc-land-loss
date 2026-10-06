"""Tests for assigning the TS1170.5 site class from Vs30 and selecting by it."""

import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr
from shapely.geometry import box

from landloss.hazard.shaking.site_class import (
    SOURCE_FOSTER,
    SOURCE_GROUND_MAP,
    SOURCE_NEAREST_CELL,
    SOURCE_NONE,
    demand_on_site_class_grid,
    fill_site_class_from_ground_map,
    fill_site_class_gaps,
    majority_material_per_cell,
    select_by_site_class,
    site_class_source,
    ts1170_site_class_from_vs30,
    vs30_from_material,
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


# rioxarray builds a raster's transform with affine's deprecated `*` operator
# when matching grids; the warning is theirs, not this module's.
@pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning")
def test_demand_is_looked_up_from_the_coarse_grid_per_class() -> None:
    """Each fine cell takes its own class's value of the coarse cell it is in."""

    # 1,000 m coarse cells per class, two rows so the grid has a y spacing; a
    # 2 by 4 fine grid of 500 m cells under the lower row.
    def coarse(left, right):
        return xr.DataArray(
            [[np.nan, np.nan], [left, right]],
            dims=("y", "x"),
            coords={"y": [1500.0, 500.0], "x": [500.0, 1500.0]},
        ).rio.write_crs("EPSG:2193")

    coarse_by_class = {2: coarse(1.0, 2.0), 5: coarse(5.0, 6.0)}
    asked = []

    def read_grid(return_period_yr, cls):
        asked.append((return_period_yr, cls))
        return coarse_by_class[cls]

    site_class = xr.DataArray(
        [[2.0, 5.0, 2.0, 5.0], [np.nan, 2.0, 5.0, 2.0]],
        dims=("y", "x"),
        coords={"y": [750.0, 250.0], "x": [250.0, 750.0, 1250.0, 1750.0]},
    ).rio.write_crs("EPSG:2193")

    result = demand_on_site_class_grid(read_grid, site_class, return_period_yr=2500)

    assert sorted(asked) == [(2500, 2), (2500, 5)]
    np.testing.assert_array_equal(
        result.values, [[1.0, 5.0, 2.0, 6.0], [np.nan, 1.0, 6.0, 2.0]]
    )


def square_grid(values, cell_m=100.0):
    """A grid of square cells, north up."""
    values = np.asarray(values, dtype=float)
    rows, cols = values.shape
    return xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": cell_m * np.arange(rows)[::-1],
            "x": cell_m * np.arange(cols),
        },
    )


def test_a_gap_takes_the_nearest_class_within_reach() -> None:
    """Gaps within 200 m are filled from the nearest cell; further ones are not."""
    nan = np.nan
    site_class = square_grid([[3.0, nan, nan, nan, nan]])

    filled, was_filled = fill_site_class_gaps(site_class, max_distance_m=200.0)

    np.testing.assert_array_equal(filled.values, [[3.0, 3.0, 3.0, nan, nan]])
    np.testing.assert_array_equal(
        was_filled.values, [[False, True, True, False, False]]
    )


def test_an_equally_near_tie_goes_to_the_softer_class() -> None:
    """Between Class II and Class V at the same distance, the gap takes V."""
    site_class = square_grid([[2.0, np.nan, 5.0]])

    filled, _ = fill_site_class_gaps(site_class, max_distance_m=200.0)

    assert filled.values[0, 1] == 5.0


def test_a_diagonal_neighbour_is_further_than_an_orthogonal_one() -> None:
    """141 m beats 200 m: the diagonal class wins over the one two cells away."""
    nan = np.nan
    site_class = square_grid([[4.0, nan, nan], [nan, nan, 2.0]])

    filled, _ = fill_site_class_gaps(site_class, max_distance_m=200.0)

    # (1, 1) is 100 m from (1, 2), Class II, and 141 m from (0, 0), Class IV.
    assert filled.values[1, 1] == 2.0
    # (1, 0) is 100 m from (0, 0), Class IV.
    assert filled.values[1, 0] == 4.0


def ground(*pieces):
    """A ground map of (material, (minx, miny, maxx, maxy)) pieces."""
    return gpd.GeoDataFrame(
        {"material": [material for material, _ in pieces]},
        geometry=[box(*bounds) for _, bounds in pieces],
        crs="EPSG:2193",
    )


def test_the_material_covering_most_of_a_cell_wins() -> None:
    """Cell centres at x = 0, 100 and 200; each cell spans 50 m either side."""
    site_class = square_grid([[np.nan, np.nan, np.nan]])
    ground_map = ground(
        ("fill_uncontrolled", (-50, -50, 20, 50)),
        ("rock", (20, -50, 150, 50)),
        ("alluvium", (150, -50, 160, 50)),
    )

    result = majority_material_per_cell(
        ground_map, site_class, np.array([[True, True, True]])
    )

    # Cell 0 is 70% fill and 30% rock; cell 1 is all rock; cell 2 is 10%
    # alluvium and otherwise sea.
    assert result.tolist() == [["fill_uncontrolled", "rock", "alluvium"]]


def test_unknown_ground_is_left_out_of_the_count() -> None:
    """A cell mostly unknown takes the material it does have; all unknown, none."""
    site_class = square_grid([[np.nan, np.nan]])
    ground_map = ground(
        ("unknown", (-50, -50, 40, 50)),
        ("loess", (40, -50, 50, 50)),
        ("unknown", (50, -50, 150, 50)),
    )

    result = majority_material_per_cell(
        ground_map, site_class, np.array([[True, True]])
    )

    assert result.tolist() == [["loess", None]]


def test_only_the_chosen_cells_are_looked_at() -> None:
    """A cell not asked about comes back None even with ground under it."""
    site_class = square_grid([[np.nan, np.nan]])
    ground_map = ground(("rock", (-50, -50, 150, 50)))

    result = majority_material_per_cell(
        ground_map, site_class, np.array([[False, True]])
    )

    assert result.tolist() == [[None, "rock"]]


def test_a_material_without_a_default_gives_no_vs30() -> None:
    """None, unknown and an unlisted material all give NaN."""
    materials = np.array([["fill_uncontrolled", None, "unknown", "basalt"]])

    vs30 = vs30_from_material(materials, {"fill_uncontrolled": 200.0, "unknown": None})

    np.testing.assert_array_equal(vs30, [[200.0, np.nan, np.nan, np.nan]])


def test_the_lead_s_fill_value_lands_in_class_vi() -> None:
    """200 m/s is the inclusive top of Class VI."""
    materials = np.array(["fill_uncontrolled"], dtype=object)

    assert ts1170_site_class_from_vs30(vs30_from_material(materials))[0] == 6


def test_only_unclassed_cells_are_filled_from_the_ground_map() -> None:
    """A classed cell keeps its class; an unclassed one over sea stays NaN."""
    site_class = square_grid([[2.0, np.nan, np.nan]]).rio.write_crs("EPSG:2193")
    ground_map = ground(("fill_uncontrolled", (-50, -50, 150, 50)))

    filled, was_filled, materials = fill_site_class_from_ground_map(
        site_class, ground_map, defaults={"fill_uncontrolled": 200.0}
    )

    np.testing.assert_array_equal(filled.values, [[2.0, 6.0, np.nan]])
    np.testing.assert_array_equal(was_filled.values, [[False, True, False]])
    assert materials.tolist() == [[None, "fill_uncontrolled", None]]


def test_each_cell_is_coded_by_where_its_class_came_from() -> None:
    """Foster, the nearest-cell fill, the ground map, or nothing."""
    vs30 = np.array([[400.0, np.nan, np.nan, np.nan]])
    nearest = np.array([[False, True, False, False]])
    from_ground = np.array([[False, False, True, False]])

    source = site_class_source(vs30, nearest, from_ground)

    assert source.tolist() == [
        [SOURCE_FOSTER, SOURCE_NEAREST_CELL, SOURCE_GROUND_MAP, SOURCE_NONE]
    ]
