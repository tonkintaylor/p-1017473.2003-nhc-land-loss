"""Tests for the area calibration of the localised urban fragility."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scipy import sparse
from shapely.geometry import Point, box

from landloss.hazard.landslide.urban import area_calibration as ac

CRS = "EPSG:2193"

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)


def strips():
    """A non-flat reference 8 m wide and three footprints across it on 2 m cells.

    A covers x 0-4, B x 2-6 (overlapping A on x 2-4), C x 6-10, half of it
    on flat land beyond x 8.
    """
    grid = ac.reference_grid(gpd.GeoSeries([box(0, 0, 8, 10)], crs=CRS))
    footprints = gpd.GeoSeries(
        [box(0, 0, 4, 10), box(2, 0, 6, 10), box(6, 0, 10, 10)], crs=CRS
    )
    return grid, footprints


def test_the_reference_grid_counts_the_non_flat_cells():
    grid, _ = strips()
    assert grid.reference.shape == (5, 4)
    assert grid.n_reference_cells == 20
    assert grid.reference_area_m2 == pytest.approx(80.0)


def test_the_expected_share_unions_overlaps_and_drops_runout_onto_flat_land():
    # Arrange
    grid, footprints = strips()
    incidence = ac.footprint_incidence(footprints, grid)

    # Act
    share = ac.expected_damaged_share(incidence, [0.5, 0.5, 1.0])

    # Assert: x 0-2 at 0.5, x 2-4 at 1 - 0.5 * 0.5, x 4-6 at 0.5, x 6-8 at 1;
    # C's half on flat land counts for nothing.
    assert incidence.sum(axis=0).tolist() == [10, 10, 5]
    assert share == pytest.approx((0.5 + 0.75 + 0.5 + 1.0) / 4)


def test_the_share_can_be_read_on_a_subset_of_cells():
    grid, footprints = strips()
    incidence = ac.footprint_incidence(footprints, grid)
    xs, _ = grid.reference_centres()
    share = ac.expected_damaged_share(incidence, [0.5, 0.5, 1.0], cells=xs > 6)
    assert share == pytest.approx(1.0)


def test_no_failure_damages_nothing_and_a_nan_probability_is_refused():
    grid, footprints = strips()
    incidence = ac.footprint_incidence(footprints, grid)
    assert ac.expected_damaged_share(incidence, [0.0, 0.0, 0.0]) == 0.0
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        ac.damaged_cell_probability(incidence, [np.nan, 0.0, 0.0])


def test_a_footprint_is_the_union_of_the_evacuated_and_inundated_zones():
    evacuated = gpd.GeoSeries([box(0, 0, 2, 2), box(5, 5, 6, 6)], crs=CRS)
    inundated = gpd.GeoSeries([box(0, -2, 2, 0), None], crs=CRS)
    footprints = ac.damage_footprints(evacuated, inundated)
    np.testing.assert_allclose(footprints.area, [8.0, 1.0])


def test_each_cell_takes_the_label_of_the_nearest_polygon():
    grid, _ = strips()
    labels = ac.nearest_labels(
        grid, gpd.GeoSeries([box(0, 0, 1, 10), box(7, 0, 8, 10)], crs=CRS), [3, 4]
    )
    xs, _ = grid.reference_centres()
    assert (labels[xs < 4] == 3).all()
    assert (labels[xs > 4] == 4).all()


def grid_of(values, cell, x0=1_750_000.0, y0=5_425_000.0):
    data = np.asarray(values, dtype=float)
    rows, cols = data.shape
    out = xr.DataArray(
        data,
        dims=("y", "x"),
        coords={
            "y": y0 - (np.arange(rows) + 0.5) * cell,
            "x": x0 + (np.arange(cols) + 0.5) * cell,
        },
    )
    return out.rio.write_crs(CRS)


@ignore_affine_matmul
def test_the_demand_is_site_pgv_per_g_of_rock_pga():
    # Arrange: a 100 m site PGV grid inside a coarse rock PGA cell.
    pgv = grid_of([[1.0, 2.0], [1.5, 0.5]], 100.0)
    rock = grid_of([[0.5, 0.5], [0.5, 0.5]], 10_000.0, x0=1_745_000.0, y0=5_430_000.0)
    points = gpd.GeoSeries(
        [Point(1_750_050.0, 5_424_950.0), Point(1_750_150.0, 5_424_850.0)], crs=CRS
    )

    # Act
    ratio = ac.pgv_per_rock_pga_m_s_per_g(pgv, rock, points)

    # Assert
    np.testing.assert_allclose(ratio, [2.0, 1.0])


def test_the_amplification_lowers_the_median_unless_the_demand_already_carries_it():
    polygons = ac.LocalisedPolygons(
        rating=np.array([0.0]), amp_factor=np.array([2.0]), pgv_per_g=np.array([1.0])
    )
    curve = ac.LocalisedCurve(1.0, 0.2, 0.5)
    amplified = ac.polygon_failure_probability(0.5, polygons, curve)
    plain = ac.polygon_failure_probability(0.5, polygons, curve, amplified=False)
    # PGV 0.5 m/s against a median of 0.5 amplified, 1.0 not.
    np.testing.assert_allclose(amplified, [0.5])
    assert plain[0] < 0.5


def test_a_polygon_anchor_picks_its_cuts_slopes_and_material():
    anchor = pd.Series(
        {
            "applies_to": "cut",
            "slope_min_deg": 45.0,
            "slope_max_deg": 50.0,
            "material": "rock",
        }
    )
    mask = ac.anchor_polygon_mask(
        anchor,
        position=["cut", "cut", "fill", "cut", "cut"],
        slope_degrees=[47.0, 45.0, 47.0, 50.0, 48.0],
        material=["rock", "rock", "rock", "rock", "colluvium"],
    )
    assert mask.tolist() == [True, False, False, True, False]
    every = pd.Series(
        {
            "applies_to": "all",
            "slope_min_deg": np.nan,
            "slope_max_deg": np.nan,
            "material": np.nan,
        }
    )
    assert ac.anchor_polygon_mask(
        every, position=["cut", "fill"], slope_degrees=[10, 80], material=[None, None]
    ).all()


def test_the_fit_recovers_the_curve_the_targets_were_made_from():
    # Arrange: forty polygons, each on its own cell, over a spread of ratings.
    n = 40
    polygons = ac.LocalisedPolygons(
        rating=np.linspace(40.0, 140.0, n),
        amp_factor=np.full(n, 1.2),
        pgv_per_g=np.full(n, 0.8),
    )
    incidence = sparse.csr_array(np.eye(n))
    truth = ac.LocalisedCurve(2.0, 2.0 / ac.FIXED_THETA_RATIO, 0.7)
    ranges = [(0.02, 0.06), (0.1, 0.2), (0.5, 0.8)]
    targets = pd.DataFrame(
        [
            {
                "anchor_id": f"T{k}",
                "pga_rock_g_min": low,
                "pga_rock_g_max": high,
                "fail_fraction": ac.scenario_share(
                    incidence,
                    polygons,
                    truth,
                    pga_rock_g_min=low,
                    pga_rock_g_max=high,
                ),
            }
            for k, (low, high) in enumerate(ranges)
        ]
    )

    # Act
    fit = ac.fit_area_calibration(incidence, polygons, targets)

    # Assert
    assert fit.curve.theta_at_zero_rating_m_s == pytest.approx(2.0, rel=1e-3)
    assert fit.curve.theta_at_max_rating_m_s == pytest.approx(0.4, rel=1e-3)
    assert fit.curve.beta == pytest.approx(0.7, rel=1e-3)
    assert fit.rms_logit_residual < 1e-4
    np.testing.assert_allclose(
        fit.targets["predicted"], targets["fail_fraction"], rtol=1e-3
    )


def test_a_fit_needs_two_targets():
    polygons = ac.LocalisedPolygons(np.ones(1), np.ones(1), np.ones(1))
    targets = pd.DataFrame(
        {"pga_rock_g_min": [0.1], "pga_rock_g_max": [0.2], "fail_fraction": [0.1]}
    )
    with pytest.raises(ValueError, match="needs two"):
        ac.fit_area_calibration(sparse.csr_array(np.eye(1)), polygons, targets)


# --- the adopted fit: the Kaikoura record and the polygon anchors ----------------


def own_cell_polygons(n=40):
    """Polygons each on their own cell, over a spread of ratings."""
    polygons = ac.LocalisedPolygons(
        rating=np.linspace(40.0, 140.0, n),
        amp_factor=np.full(n, 1.2),
        pgv_per_g=np.full(n, 0.8),
    )
    return polygons, sparse.csr_array(np.eye(n))


RECORD = pd.Series(
    {
        "anchor_id": "A16",
        "pga_rock_g_min": 0.15,
        "pga_rock_g_max": 0.15,
        "fail_fraction": 0.001,
    }
)


def polygon_targets_on(curve, polygons):
    """Three polygon anchors lying exactly on ``curve``; the last one recorded."""
    n = len(polygons.rating)
    picks = [
        ("P1", np.arange(n) < n // 2, 0.2, 0.5, True),
        ("P2", np.arange(n) >= n // 2, 0.5, 0.8, True),
        ("P3", np.ones(n, dtype=bool), 1.0, 2.0, False),
    ]
    targets = []
    for anchor_id, mask, low, high, amplified in picks:
        subset = polygons.subset(mask)
        targets.append(
            ac.PolygonTarget(
                anchor_id=anchor_id,
                polygons=subset,
                pga_g_min=low,
                pga_g_max=high,
                fail_fraction=ac.mean_polygon_failure(
                    subset, curve, pga_g_min=low, pga_g_max=high, amplified=amplified
                ),
                amplified=amplified,
            )
        )
    return targets


def test_the_adopted_fit_recovers_the_curve_its_targets_were_made_from():
    # Arrange
    polygons, incidence = own_cell_polygons()
    truth = ac.LocalisedCurve(4.0, 4.0 / ac.FIXED_THETA_RATIO, 0.55)
    record = RECORD.copy()
    record["fail_fraction"] = ac.scenario_share(
        incidence, polygons, truth, pga_rock_g_min=0.15, pga_rock_g_max=0.15
    )
    targets = polygon_targets_on(truth, polygons)

    # Act
    fit = ac.fit_record_and_polygons(incidence, polygons, record, targets)

    # Assert
    assert fit.curve.theta_at_zero_rating_m_s == pytest.approx(4.0, rel=1e-3)
    assert fit.curve.theta_at_max_rating_m_s == pytest.approx(0.8, rel=1e-3)
    assert fit.curve.beta == pytest.approx(0.55, rel=1e-3)
    assert fit.targets["anchor_id"].tolist() == ["A16", "P1", "P2", "P3"]
    assert fit.targets["kind"].tolist() == ["zone_area", *["polygon"] * 3]
    assert fit.rms_logit_residual < 1e-4


def test_the_record_weighs_as_much_as_the_polygon_anchors_together():
    # Arrange: polygon anchors from a weak curve, a record that disagrees.
    polygons, incidence = own_cell_polygons()
    targets = polygon_targets_on(ac.LocalisedCurve(1.0, 0.2, 0.6), polygons)

    # Act
    weighted = ac.fit_record_and_polygons(incidence, polygons, RECORD, targets)
    even = ac.fit_record_and_polygons(
        incidence, polygons, RECORD, targets, record_weight=1.0
    )

    # Assert
    assert weighted.targets["weight"].tolist() == [3.0, 1.0, 1.0, 1.0]
    record_miss = abs(weighted.targets["logit_residual"].iloc[0])
    assert record_miss < abs(even.targets["logit_residual"].iloc[0])


def test_a_polygon_anchor_matching_no_polygon_is_refused():
    polygons, incidence = own_cell_polygons()
    empty = ac.PolygonTarget(
        "P0", polygons.subset(np.zeros(40, dtype=bool)), 0.2, 0.5, 0.3
    )
    with pytest.raises(ValueError, match="match no polygon"):
        ac.fit_record_and_polygons(incidence, polygons, RECORD, [empty])
    with pytest.raises(ValueError, match="at least one polygon anchor"):
        ac.fit_record_and_polygons(incidence, polygons, RECORD, [])


def test_the_upper_limit_holds_a_weak_curve_and_catches_a_strong_one():
    polygons, incidence = own_cell_polygons()
    limit = pd.Series(
        {"pga_rock_g_min": 0.5, "pga_rock_g_max": 0.8, "fail_fraction": 0.25}
    )
    weak_share, weak_ok = ac.within_upper_limit(
        incidence, polygons, ac.LocalisedCurve(10.0, 2.0, 0.6), limit
    )
    strong_share, strong_ok = ac.within_upper_limit(
        incidence, polygons, ac.LocalisedCurve(0.1, 0.02, 0.6), limit
    )
    assert weak_ok
    assert weak_share <= 0.25
    assert not strong_ok
    assert strong_share > 0.25


# --- the validation scripts, on synthetic inputs ------------------------------------


def synthetic_inputs():
    """Forty bare polygons, each a 2 m strip across an 80 m by 10 m slope."""
    from landloss.hazard.landslide.urban import fragility  # noqa: PLC0415
    from scripts.landloss.hazard.landslide.validations.urban import (  # noqa: PLC0415
        table_urban_area_calibration as table,
    )

    n = 40
    strips_ = [box(2 * k, 0, 2 * k + 2, 10) for k in range(n)]
    polygons = gpd.GeoDataFrame(
        {
            "continuous_rating": np.linspace(60.0, 120.0, n),
            "amp_factor": np.full(n, 1.2),
            "pgv_per_rock_pga": np.full(n, 0.8),
            "pgv_per_site_pga": np.full(n, 0.6),
            "wall_position": np.where(np.arange(n) % 4 == 3, "fill", "cut"),
            "slope_degrees": np.linspace(40.0, 80.0, n),
            "material": "rock",
            "kingsbury_zone": pd.array(np.where(np.arange(n) < 30, 3, 4), "Int64"),
            "evacuated": gpd.GeoSeries(strips_, crs=CRS),
            "inundated": gpd.GeoSeries([None] * n, crs=CRS),
        },
        geometry=strips_,
        crs=CRS,
    )
    grid = ac.reference_grid(gpd.GeoSeries([box(0, 0, 80, 10)], crs=CRS))
    footprints = ac.damage_footprints(polygons["evacuated"], polygons["inundated"])
    inputs = table.CalibrationInputs(
        polygons=polygons,
        grid=grid,
        incidence=ac.footprint_incidence(footprints, grid),
        zone_of_cell=ac.nearest_labels(
            grid, polygons["evacuated"], polygons["kingsbury_zone"].to_numpy(int)
        ),
        anchors=fragility.load_urban_fragility_anchors(),
    )
    return table, inputs


def test_the_table_script_writes_the_adopted_fit_and_the_rejected_ones(
    tmp_path, monkeypatch
):
    # Arrange
    table, inputs = synthetic_inputs()
    monkeypatch.setattr(table, "TAB_DIR", tmp_path)

    # Act
    table.write_tables(inputs, model_path=tmp_path / "no-model.geoparquet")

    # Assert
    fits = pd.read_csv(tmp_path / table.FIT_NAME)
    assert fits["curve"].tolist()[:2] == ["adopted", "committed"]
    assert {"area", "footprint"} <= set(fits["curve"])
    limits = pd.read_csv(tmp_path / table.LIMITS_NAME)
    assert limits.loc[limits["curve"] == "adopted", "anchor_id"].item() == "A12"
    anchors = pd.read_csv(tmp_path / table.POLYGON_ANCHORS_NAME)
    assert anchors["anchor_id"].tolist() == ["A17", "A18", "A19", "A20", "A21"]
    assert "predicted_adopted" in anchors.columns
    zones = pd.read_csv(tmp_path / table.ZONE_SHARES_NAME)
    record = zones[zones["anchor_id"] == "A16"]
    assert record["role"].tolist() == ["adopted fit"]


def test_the_figure_script_draws_the_adopted_curve(tmp_path):
    from scripts.landloss.hazard.landslide.validations.urban import (  # noqa: PLC0415
        fig_urban_area_calibration as fig,
    )

    _, inputs = synthetic_inputs()
    fig.draw(inputs, tmp_path / fig.FIG_NAME)
    assert (tmp_path / fig.FIG_NAME).exists()
