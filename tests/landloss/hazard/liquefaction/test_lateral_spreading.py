"""Tests for the lateral spreading adjustment."""

import geopandas as gpd
import numpy as np
import pytest

# Registers the ``.rio`` accessor the zone grid reads.
import rioxarray  # noqa: F401
import xarray as xr
from shapely.geometry import LineString

from landloss.domain import constants
from landloss.hazard.liquefaction.lateral_spreading import (
    FAR_FIELD_M,
    KNEE,
    NEAR_FIELD_M,
    apply_lateral_spreading,
    correct_major_or_worse,
    far_weight_grid,
    lateral_spreading_zones,
    zone_grid,
)

NEAR, MIDDLE, FAR = 0.0, 0.5, 1.0


def corrected(p: float, far_weight: float) -> float:
    return float(correct_major_or_worse(np.array([p]), np.array([far_weight]))[0])


# --- the piecewise map ----------------------------------------------------------


def test_the_nlm_worked_example_near_a_free_face() -> None:
    """A baseline 20% becomes 35% in the near field, as on Ryan's figure."""
    assert corrected(0.20, NEAR) == pytest.approx(0.35)


def test_the_nlm_worked_example_far_from_a_free_face() -> None:
    """A baseline 20% becomes 15% in the far field."""
    assert corrected(0.20, FAR) == pytest.approx(0.15)


def test_below_the_knee_the_map_multiplies() -> None:
    """Under the knee the near map triples and the far map takes a third."""
    assert corrected(0.03, NEAR) == pytest.approx(0.09)
    assert corrected(0.03, FAR) == pytest.approx(0.01)


@pytest.mark.parametrize("far_weight", [NEAR, FAR])
def test_the_map_is_continuous_at_the_knee(far_weight: float) -> None:
    """The multiplying and adding branches meet at the knee."""
    below = corrected(KNEE - 1e-9, far_weight)
    above = corrected(KNEE + 1e-9, far_weight)
    assert below == pytest.approx(above, abs=1e-6)


def test_the_middle_band_takes_the_midpoint_of_the_blend() -> None:
    """Between the buffers the probability sits halfway between the two maps."""
    near, far = corrected(0.20, NEAR), corrected(0.20, FAR)
    assert corrected(0.20, MIDDLE) == pytest.approx((near + far) / 2)


def test_the_result_stays_a_probability() -> None:
    """A high baseline lifted near a free face is clipped at one."""
    assert corrected(0.95, NEAR) == 1.0
    assert corrected(0.0, FAR) == 0.0


def test_a_missing_baseline_stays_missing() -> None:
    """A cell outside the NLM grid is not given a probability."""
    assert np.isnan(corrected(np.nan, NEAR))


# --- zones ----------------------------------------------------------------------


def make_faces() -> gpd.GeoDataFrame:
    """One straight free face along y = 0."""
    return gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (1000, 0)])], crs=constants.DEFAULT_CRS
    )


def make_grid(ys: list[float], value: float = 0.2) -> xr.DataArray:
    """A grid of 100 m cells, two columns either side of x = 500, at the given ys.

    Two columns rather than one, because a single column gives rioxarray no
    cell width to build the transform from.
    """
    grid = xr.DataArray(
        np.full((len(ys), 2), value),
        dims=("y", "x"),
        coords={"y": ys, "x": [450.0, 550.0]},
    )
    return grid.rio.write_crs(constants.DEFAULT_CRS)


def test_the_zones_are_the_two_buffers() -> None:
    """The near zone reaches 100 m, and the middle zone from there to 200 m."""
    zones = lateral_spreading_zones(make_faces()).set_index("zone_name")

    assert zones.loc["near"].geometry.contains(
        gpd.points_from_xy([500], [NEAR_FIELD_M - 1])[0]
    )
    middle = zones.loc["middle"].geometry
    assert middle.contains(gpd.points_from_xy([500], [NEAR_FIELD_M + 1])[0])
    assert not middle.contains(gpd.points_from_xy([500], [FAR_FIELD_M + 1])[0])


def test_a_cell_takes_the_zone_its_centre_is_in() -> None:
    """Cells 50 m, 150 m and 250 m from the face are near, middle and far."""
    grid = make_grid([250.0, 150.0, 50.0])
    zones = zone_grid(lateral_spreading_zones(make_faces()), grid)

    assert zones.to_numpy()[:, 0].tolist() == [2, 1, 0]


def test_no_free_faces_leaves_everything_far() -> None:
    """An extent without free faces is all far field."""
    faces = gpd.GeoDataFrame(geometry=[], crs=constants.DEFAULT_CRS)
    grid = make_grid([250.0, 150.0, 50.0])

    zones = zone_grid(lateral_spreading_zones(faces), grid)

    assert set(zones.to_numpy().ravel()) == {2}


def test_zones_in_another_crs_are_refused() -> None:
    """A zone grid burned in the wrong CRS would land in the wrong place."""
    zones = lateral_spreading_zones(make_faces()).to_crs(4326)

    with pytest.raises(ValueError, match="zones are"):
        zone_grid(zones, make_grid([50.0]))


def test_a_cell_is_weighted_by_its_share_of_each_zone() -> None:
    """A cell wholly near is 0, wholly far is 1, and one astride a boundary between."""
    # Cells of 100 m: wholly far, wholly far, wholly middle, wholly near.
    grid = make_grid([350.0, 250.0, 150.0, 50.0])
    weights = far_weight_grid(lateral_spreading_zones(make_faces()), grid)
    assert weights.to_numpy()[:, 0] == pytest.approx([1.0, 1.0, 0.5, 0.0])

    # Shifted half a cell: far, then half middle and half far (0.75), then half
    # near and half middle (0.25).
    shifted = make_grid([300.0, 200.0, 100.0])
    weights = far_weight_grid(lateral_spreading_zones(make_faces()), shifted)
    assert weights.to_numpy()[:, 0] == pytest.approx([1.0, 0.75, 0.25])


# --- applying it ----------------------------------------------------------------


def test_major_is_capped_at_moderate() -> None:
    """Tripled near a face, Major cannot exceed Moderate; the cap is reported."""
    grid = make_grid([50.0, 350.0], value=0.05)
    moderate = grid.copy(data=np.full(grid.shape, 0.10))
    weights = far_weight_grid(lateral_spreading_zones(make_faces()), grid)

    major, capped = apply_lateral_spreading(moderate, grid, weights)

    assert major.to_numpy()[:, 0] == pytest.approx([0.10, 0.05 / 3])
    assert capped.to_numpy()[:, 0].tolist() == [True, False]
