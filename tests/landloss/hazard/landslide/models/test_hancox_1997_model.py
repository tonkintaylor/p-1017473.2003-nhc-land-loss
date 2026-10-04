import numpy as np
import pytest

from landloss.hazard.landslide.models.hancox_1997 import model
from landloss.hazard.landslide.models.hancox_1997 import relationships as h


def run_model(
    slope_deg,
    *,
    mm_intensity=8.0,
    site_distance_km=25.0,
    cell_area_km2=1.0,
    event_total_fraction=0.1,
):
    event_total = event_total_fraction * float(h.area_affected_km2(8.1))
    return model.run(
        slope_deg=np.asarray(slope_deg, dtype=float),
        mm_intensity=mm_intensity,
        site_distance_km=site_distance_km,
        cell_area_km2=cell_area_km2,
        mw=8.1,
        event_total_area_km2=event_total,
    )


def test_landslide_area_follows_the_hancox_slope_class_shares():
    result = run_model([10.0, 20.0, 30.0, 40.0, 50.0])

    assert result.study_target_area_km2 == pytest.approx(0.5)
    assert result.coverage.sum() == pytest.approx(result.study_target_area_km2)
    assert result.coverage / result.coverage.sum() == pytest.approx(
        list(h.SLOPE_SHARES.values())
    )


def test_the_study_gets_its_share_of_the_event_total():
    cell_areas = np.array([2.0, 3.0])
    result = run_model([30.0, 40.0], cell_area_km2=cell_areas)

    assert result.eligible_area_km2 == pytest.approx(5.0)
    assert result.study_target_area_km2 == pytest.approx(0.5)
    assert np.sum(result.coverage * cell_areas) == pytest.approx(0.5)
    assert result.report.total_after_km2 == pytest.approx(0.5)


def test_mm_threshold_removes_a_cell_and_its_share_of_the_total():
    result = run_model([30.0, 30.0], mm_intensity=[6.9, 7.0])

    assert result.eligible_area_km2 == pytest.approx(1.0)
    assert result.study_target_area_km2 == pytest.approx(0.1)
    assert result.coverage == pytest.approx([0.0, 0.1])


def test_maximum_distance_removes_a_cell_and_nan_stays_nan():
    result = run_model(
        [30.0, 30.0, np.nan],
        site_distance_km=[25.0, 400.0, 25.0],
    )

    assert result.coverage[:2] == pytest.approx([0.1, 0.0])
    assert np.isnan(result.coverage[2])


def test_the_study_share_cannot_exceed_the_whole_event():
    area_affected = float(h.area_affected_km2(8.1))
    result = model.run(
        slope_deg=np.full(2, 30.0),
        mm_intensity=8.0,
        site_distance_km=25.0,
        cell_area_km2=area_affected,
        mw=8.1,
        event_total_area_km2=10.0,
    )

    assert result.study_target_area_km2 == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("event total", {"event_total_area_km2": -1.0}),
        ("cell area", {"cell_area_km2": -1.0}),
    ],
)
def test_negative_areas_are_refused(name, kwargs):
    arguments = {
        "slope_deg": [30.0],
        "mm_intensity": [8.0],
        "site_distance_km": [25.0],
        "cell_area_km2": [1.0],
        "mw": 8.1,
        "event_total_area_km2": 1.0,
    }
    arguments.update(kwargs)

    with pytest.raises(ValueError, match=name):
        model.run(**arguments)
