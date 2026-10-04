"""Tests for the Kritikos et al. (2015) fuzzy-logic landslide model."""

import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr
from shapely.geometry import LineString

from landloss.hazard.landslide.models.kritikos_2015 import (
    evaluation,
    inputs,
    memberships,
    model,
)
from landloss.io import active_faults

pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

CRS = "EPSG:2193"


def _grid(values: np.ndarray, cell: float) -> xr.DataArray:
    ny, nx = values.shape
    grid = xr.DataArray(
        values.astype(float),
        dims=("y", "x"),
        coords={
            "y": 5_400_000.0 - cell * (np.arange(ny) + 0.5),
            "x": 1_700_000.0 + cell * (np.arange(nx) + 0.5),
        },
    )
    return grid.rio.write_crs(CRS)


class TestMemberships:
    def test_all_memberships_lie_between_zero_and_one(self):
        mm = np.linspace(3, 11, 81)
        slope = np.linspace(0, 90, 91)
        distance = np.concatenate([np.linspace(0, 80, 81), [np.inf]])
        for result in (
            memberships.mm_membership(mm),
            memberships.slope_membership(slope),
            memberships.fault_membership(distance),
            memberships.slope_position_membership([0, 1, 2, 3]),
        ):
            assert np.all((result >= 0) & (result <= 1))

    def test_intensity_and_slope_rise_and_fault_distance_falls(self):
        assert np.all(np.diff(memberships.mm_membership(np.linspace(5, 9, 40))) >= 0)
        assert np.all(
            np.diff(memberships.slope_membership(np.linspace(2, 53, 40))) >= 0
        )
        assert np.all(
            np.diff(memberships.fault_membership(np.linspace(2, 55, 40))) <= 0
        )

    def test_digitised_anchor_values(self):
        assert memberships.mm_membership(7.5) == pytest.approx(0.495)
        assert memberships.slope_membership(17.5) == pytest.approx(0.387)
        assert memberships.fault_membership(2.5) == pytest.approx(1.0)

    def test_fault_membership_is_flat_beyond_the_far_field(self):
        assert memberships.fault_membership(np.inf) == pytest.approx(
            memberships.fault_membership(55.0)
        )

    def test_slope_position_order(self):
        flat, valley, midslope, ridge = memberships.slope_position_membership(
            [
                memberships.FLAT,
                memberships.VALLEY,
                memberships.MIDSLOPE,
                memberships.RIDGE,
            ]
        )
        assert ridge > midslope > valley > flat

    def test_slope_position_nan_stays_nan(self):
        assert np.isnan(memberships.slope_position_membership(np.nan))


class TestFuzzyGamma:
    def test_matches_hand_computation(self):
        mu = [0.5, 0.4, 0.8]
        product = 0.5 * 0.4 * 0.8
        fuzzy_sum = 1 - (0.5 * 0.6 * 0.2)
        expected = product**0.1 * fuzzy_sum**0.9
        assert model.fuzzy_gamma(mu, 0.9) == pytest.approx(expected)

    def test_gamma_zero_is_the_product_and_one_is_the_sum(self):
        mu = [0.5, 0.4]
        assert model.fuzzy_gamma(mu, 0.0) == pytest.approx(0.2)
        assert model.fuzzy_gamma(mu, 1.0) == pytest.approx(1 - 0.5 * 0.6)

    def test_nan_propagates(self):
        assert np.isnan(model.fuzzy_gamma([np.nan, 0.5]))

    @pytest.mark.parametrize(
        ("values", "gamma"),
        [([0.5], 0.9), ([0.5, 0.5], 1.5), ([0.5, 1.2], 0.9)],
    )
    def test_rejects_bad_input(self, values, gamma):
        with pytest.raises(ValueError, match=r"."):
            model.fuzzy_gamma(values, gamma)


class TestRun:
    def test_hazard_rises_with_intensity_and_slope(self):
        base = {
            "fault_distance_km": 5.0,
            "slope_position": float(memberships.RIDGE),
        }
        weak = model.run(mm=6.0, slope_deg=10.0, **base).hazard
        strong = model.run(mm=8.5, slope_deg=35.0, **base).hazard
        assert strong > weak

    def test_far_fault_lowers_hazard(self):
        kwargs = {
            "mm": 8.0,
            "slope_deg": 30.0,
            "slope_position": float(memberships.MIDSLOPE),
        }
        near = model.run(fault_distance_km=2.5, **kwargs).hazard
        far = model.run(fault_distance_km=np.inf, **kwargs).hazard
        assert near > far

    def test_flags_gentle_ground(self):
        result = model.run(
            mm=np.array([8.0, 8.0]),
            slope_deg=np.array([3.0, 20.0]),
            fault_distance_km=np.array([5.0, 5.0]),
            slope_position=np.array([2.0, 2.0]),
        )
        assert result.gentle.tolist() == [True, False]

    def test_nan_input_gives_nan_hazard(self):
        result = model.run(
            mm=8.0,
            slope_deg=np.nan,
            fault_distance_km=5.0,
            slope_position=2.0,
        )
        assert np.isnan(result.hazard)


class TestInputs:
    def test_slope_60m_aggregates_a_10m_dem(self):
        # A 30 degree ramp rising to the east, on a 10 m grid.
        x = np.arange(60) * 10.0
        dem = _grid(np.tile(x * np.tan(np.radians(30)), (60, 1)), 10.0)
        dem_60m, slope = inputs.gen_slope_60m(dem)
        assert dem_60m.shape == (10, 10)
        assert float(slope[5, 5]) == pytest.approx(30.0, abs=0.1)

    def test_slope_60m_rejects_a_cell_size_that_does_not_divide_60(self):
        dem = _grid(np.zeros((20, 20)), 25.0)
        with pytest.raises(ValueError, match="divide"):
            inputs.gen_slope_60m(dem)

    def test_slope_position_classes(self):
        # A ridge down the middle with valleys either side and flat margins.
        cols = np.arange(41)
        profile = 100.0 * np.cos(cols / 40 * 2 * np.pi * 2)
        dem = _grid(np.tile(profile, (41, 1)), 60.0)
        slope = _grid(np.full((41, 41), 20.0), 60.0)
        classes = inputs.gen_slope_position(dem, slope, window_m=600.0).to_numpy()
        interior = classes[:, 6:-6]
        assert np.isnan(classes[:, :3]).all()
        assert memberships.RIDGE in interior
        assert memberships.VALLEY in interior
        assert memberships.MIDSLOPE in interior

    def test_flat_ground_is_flat(self):
        dem = _grid(np.random.default_rng(0).normal(0, 0.01, (31, 31)), 60.0)
        slope = _grid(np.full((31, 31), 1.0), 60.0)
        classes = inputs.gen_slope_position(
            dem, slope, window_m=600.0, tpi_sd_m=1.0
        ).to_numpy()
        assert np.all(classes[~np.isnan(classes)] == memberships.FLAT)

    def test_fault_distance_to_a_trace(self):
        template = _grid(np.zeros((10, 10)), 60.0)
        x0 = float(template["x"].min())
        y_mid = float(template["y"].mean())
        trace = LineString([(x0 - 5000, y_mid - 3000), (x0 + 5000, y_mid - 3000)])
        faults = gpd.GeoDataFrame(geometry=[trace], crs=CRS)
        distance = inputs.gen_fault_distance_km(faults, template).to_numpy()
        # The 600 m grid sits 3 km from the trace, centred on it.
        assert distance.min() == pytest.approx(2.73, abs=0.02)
        assert distance.max() == pytest.approx(3.27, abs=0.02)

    def test_fault_distance_is_inf_beyond_the_far_field_and_nan_on_nodata(self):
        template = _grid(np.zeros((4, 4)), 60.0)
        template[0, 0] = np.nan
        x0 = float(template["x"].min())
        far = LineString([(x0, 5_400_000 - 200_000), (x0 + 100, 5_400_000 - 200_000)])
        faults = gpd.GeoDataFrame(geometry=[far], crs=CRS)
        distance = inputs.gen_fault_distance_km(faults, template).to_numpy()
        assert np.isnan(distance[0, 0])
        assert np.isinf(distance[1:, 1:]).all()

    def test_no_faults_gives_inf(self):
        template = _grid(np.zeros((3, 3)), 60.0)
        faults = gpd.GeoDataFrame(geometry=[], crs=CRS)
        assert np.isinf(inputs.gen_fault_distance_km(faults, template).to_numpy()).all()


class TestEvaluation:
    def test_perfect_map_scores_near_one_and_random_scores_half(self):
        hazard = np.arange(100.0)
        landslides = np.zeros(100)
        landslides[-10:] = 1.0
        assert evaluation.success_rate_auc(hazard, landslides) > 0.94
        assert evaluation.success_rate_auc(np.ones(100), np.ones(100)) == pytest.approx(
            0.5
        )

    def test_reversed_map_scores_below_half(self):
        hazard = np.arange(100.0)
        landslides = np.zeros(100)
        landslides[:10] = 1.0
        assert evaluation.success_rate_auc(hazard, landslides) < 0.1

    def test_known_curve(self):
        # Two cells, the higher-hazard cell holds 3 of 4 landslides.
        area, found = evaluation.success_rate_curve([2.0, 1.0], [3.0, 1.0])
        assert area.tolist() == [0.0, 0.5, 1.0]
        assert found.tolist() == [0.0, 0.75, 1.0]
        assert evaluation.success_rate_auc([2.0, 1.0], [3.0, 1.0]) == pytest.approx(
            0.5 * 0.75 / 2 + 0.5 * (0.75 + 1.0) / 2
        )

    def test_nan_cells_are_left_out(self):
        assert evaluation.success_rate_auc(
            [np.nan, 2.0, 1.0], [5.0, 3.0, 1.0]
        ) == pytest.approx(evaluation.success_rate_auc([2.0, 1.0], [3.0, 1.0]))

    def test_no_landslides_raises(self):
        with pytest.raises(ValueError, match="landslide"):
            evaluation.success_rate_auc([1.0, 2.0], [0.0, 0.0])

    def test_transfer_function_is_monotone_and_flat_beyond_range(self):
        rng = np.random.default_rng(1)
        hazard = rng.uniform(0, 1, 2000)
        coverage = np.clip(0.2 * hazard + rng.normal(0, 0.05, 2000), 0, 1)
        fn = evaluation.fit_transfer_function(hazard, coverage, n_bins=10)
        assert np.all(np.diff(fn.coverage) >= -1e-12)
        assert fn(-1.0) == pytest.approx(fn.coverage[0])
        assert fn(2.0) == pytest.approx(fn.coverage[-1])
        assert fn(0.9) > fn(0.1)

    def test_transfer_function_pools_a_non_monotone_bin(self):
        hazard = np.arange(6.0)
        coverage = np.array([0.0, 0.0, 0.4, 0.0, 0.2, 0.2])
        fn = evaluation.fit_transfer_function(hazard, coverage, n_bins=6)
        assert np.all(np.diff(fn.coverage) >= 0)

    def test_transfer_function_rejects_too_few_cells(self):
        with pytest.raises(ValueError, match="valid cells"):
            evaluation.fit_transfer_function([1.0, 2.0], [0.1, 0.2], n_bins=5)


class TestActiveFaultsReader:
    def _write(self, directory, name="af250.gpkg"):
        faults = gpd.GeoDataFrame(
            {"name": ["near", "far"]},
            geometry=[
                LineString([(1_750_000, 5_430_000), (1_751_000, 5_431_000)]),
                LineString([(1_000_000, 4_000_000), (1_001_000, 4_001_000)]),
            ],
            crs=CRS,
        )
        faults.to_file(directory / name, driver="GPKG")

    def test_reads_the_single_vector_file_and_filters_by_bbox(
        self, tmp_path, monkeypatch
    ):
        self._write(tmp_path)
        monkeypatch.setattr(active_faults, "AF250_DIR", tmp_path)
        assert len(active_faults.get_active_faults(crs=CRS)) == 2
        near = active_faults.get_active_faults(
            bbox=(1_700_000, 5_400_000, 1_800_000, 5_500_000), crs=CRS
        )
        assert near["name"].tolist() == ["near"]

    def test_raises_when_there_is_not_exactly_one_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(active_faults, "AF250_DIR", tmp_path)
        with pytest.raises(ValueError, match="exactly one"):
            active_faults.get_active_faults()
        self._write(tmp_path, "a.gpkg")
        self._write(tmp_path, "b.gpkg")
        with pytest.raises(ValueError, match="exactly one"):
            active_faults.get_active_faults()
