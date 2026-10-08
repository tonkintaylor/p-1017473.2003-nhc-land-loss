"""Tests for the Kritikos transfer-function fit and the event coverage it reads."""

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import box

from landloss.hazard.landslide.models.kritikos_2015 import evaluation
from scripts.landloss.hazard.landslide.steps.s8_kritikos_2015 import (
    gen_kritikos_2015_transfer_function as fit,
)
from scripts.landloss.hazard.landslide.validations.kritikos_2015 import event_inputs

pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

CELL = event_inputs.RESOLUTION_M


def template(rows, columns):
    return xr.DataArray(
        np.zeros((rows, columns)),
        dims=("y", "x"),
        coords={
            "y": 600_000.0 - CELL * (np.arange(rows) + 0.5),
            "x": 300_000.0 + CELL * (np.arange(columns) + 0.5),
        },
    )


def points_event(total_area_km2):
    return event_inputs.Event(
        name="test",
        utm_crs="EPSG:32611",
        gfdb_event_name="",
        gfdb_inventory="",
        gfdb_layer="points",
        shakemap_url="",
        published_auc=0.0,
        published_auc_over_5deg=0.0,
        total_area_km2=total_area_km2,
    )


class TestSpreadFootprint:
    def test_weights_sum_to_one_and_are_symmetric(self):
        weights = event_inputs.spread_footprint_weights(13_490.0)
        assert weights.sum() == pytest.approx(1.0)
        assert weights.shape == (3, 3)
        assert np.allclose(weights, weights.T)
        assert np.allclose(weights, weights[::-1, ::-1])

    def test_a_footprint_smaller_than_a_cell_stays_in_it(self):
        weights = event_inputs.spread_footprint_weights(1_000.0)
        assert weights.shape == (1, 1)


class TestPointCoverage:
    def test_the_published_area_is_conserved_away_from_the_edge(self):
        grid = template(21, 21)
        counts = np.zeros(grid.shape)
        counts[10, 10] = 1.0
        counts[5, 14] = 1.0
        counts[15, 4] = 1.0
        event = points_event(total_area_km2=3 * 13_490.0 / 1e6)
        landslides = [None] * 3
        coverage = event_inputs.gen_coverage(event, landslides, counts, grid)
        assert coverage.sum() * CELL**2 == pytest.approx(3 * 13_490.0, rel=1e-2)
        assert coverage.max() <= 1.0

    def test_coverage_is_capped_at_the_whole_cell(self):
        grid = template(9, 9)
        counts = np.zeros(grid.shape)
        counts[4, 4] = 5.0
        event = points_event(total_area_km2=5 * 13_490.0 / 1e6)
        coverage = event_inputs.gen_coverage(event, [None] * 5, counts, grid)
        assert coverage.max() == 1.0

    def test_a_points_inventory_with_no_total_area_is_refused(self):
        grid = template(3, 3)
        with pytest.raises(ValueError, match="no total area"):
            event_inputs.gen_coverage(
                points_event(None), [None], np.zeros(grid.shape), grid
            )


class TestPolygonCoverage:
    def test_polygon_area_is_the_fraction_of_the_cell_it_covers(self):
        grid = template(4, 4)
        # Half of the cell at row 1, column 2.
        left = 300_000.0 + 2 * CELL
        top = 600_000.0 - 1 * CELL
        landslides = gpd.GeoSeries([box(left, top - CELL, left + CELL / 2, top)])
        event = event_inputs.Event(
            name="test",
            utm_crs="EPSG:32611",
            gfdb_event_name="",
            gfdb_inventory="",
            gfdb_layer="polygons",
            shakemap_url="",
            published_auc=0.0,
            published_auc_over_5deg=0.0,
        )
        coverage = event_inputs.gen_coverage(
            event, gpd.GeoDataFrame(geometry=landslides), np.zeros(grid.shape), grid
        )
        assert coverage[1, 2] == pytest.approx(0.5)
        assert coverage.sum() == pytest.approx(0.5)


class TestStudyAreaCells:
    def layers(self):
        x = 300_000.0 + CELL * (np.arange(6) + 0.5)
        y = 600_000.0 - CELL * (np.arange(5) + 0.5)
        return {
            "mm": np.full((5, 6), 8.0),
            "slope": np.full((5, 6), 20.0),
            "fault_km": np.full((5, 6), 2.0),
            "position": {600.0: np.full((5, 6), 3.0)},
            "coverage": np.arange(30.0).reshape(5, 6) / 100.0,
            "x": x,
            "y": y,
            "bounds": (x[1], y[3], x[3], y[1]),
        }

    def test_only_cells_inside_the_study_area_are_returned(self):
        hazard, coverage = fit.gen_study_area_cells(
            self.layers(),
            gamma=0.9,
            tpi_window_m=600.0,
            fault_term="mapped",
            margin_m=0.0,
        )
        assert hazard.size == coverage.size == 9
        assert sorted(coverage) == [
            0.07,
            0.08,
            0.09,
            0.13,
            0.14,
            0.15,
            0.19,
            0.20,
            0.21,
        ]

    def test_a_margin_widens_the_study_area(self):
        hazard, _ = fit.gen_study_area_cells(
            self.layers(),
            gamma=0.9,
            tpi_window_m=600.0,
            fault_term="mapped",
            margin_m=CELL,
        )
        assert hazard.size == 25

    def test_far_field_lowers_the_hazard_near_a_fault(self):
        mapped, _ = fit.gen_study_area_cells(
            self.layers(),
            gamma=0.9,
            tpi_window_m=600.0,
            fault_term="mapped",
            margin_m=0.0,
        )
        far, _ = fit.gen_study_area_cells(
            self.layers(),
            gamma=0.9,
            tpi_window_m=600.0,
            fault_term="far_field",
            margin_m=0.0,
        )
        assert far.mean() < mapped.mean()

    def test_unknown_fault_term_is_refused(self):
        with pytest.raises(ValueError, match="fault_term"):
            fit.gen_study_area_cells(
                self.layers(),
                gamma=0.9,
                tpi_window_m=600.0,
                fault_term="nearest",
                margin_m=0.0,
            )


def test_compare_curves_reports_the_ratio_where_both_events_have_coverage():
    pooled = evaluation.TransferFunction(
        hazard=np.array([0.2, 0.5, 0.8]), coverage=np.array([0.0, 0.01, 0.03])
    )
    per_event = {
        "a": evaluation.TransferFunction(
            hazard=np.array([0.2, 0.8]), coverage=np.array([0.0, 0.02])
        ),
        "b": evaluation.TransferFunction(
            hazard=np.array([0.2, 0.8]), coverage=np.array([0.0, 0.04])
        ),
    }
    cells = {
        "a": (np.array([0.2, 0.8]), np.array([0.0, 0.02])),
        "b": (np.array([0.2, 0.8]), np.array([0.0, 0.04])),
    }
    table, totals = fit.compare_curves(pooled, per_event, cells)
    assert np.isnan(table["ratio_max_to_min"].iloc[0])
    assert table["ratio_max_to_min"].iloc[2] == pytest.approx(2.0)
    assert totals.loc["a", "observed_mean_coverage"] == pytest.approx(0.01)
