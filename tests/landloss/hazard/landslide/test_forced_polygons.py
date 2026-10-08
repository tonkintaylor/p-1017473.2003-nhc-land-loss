"""Tests for the minimum polygons drawn from a wall line with no element."""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
from rasterio.transform import Affine

from landloss.hazard.landslide import forced_polygons as forced
from landloss.hazard.landslide.slope_elements import BANK, FREE_FACE
from landloss.hazard.landslide.slope_polygons import (
    BETA_REPOSE_ANGLE_DEG,
    BETA_SEISMIC_RUNOUT_M,
    BETA_SEISMIC_RUNOUT_UNRATED_M,
    CUT_SLOPE,
    EVACUATED,
    IMMINENT,
    INUNDATED,
    reach_ratio,
)
from landloss.hazard.landslide.urban.face_polygons import BETA_OFF_MAP_GROUND

CRS = 2193
# A 40 m by 40 m grid rising to the north (y): 0.5 m per metre.
TRANSFORM = Affine(1, 0, 0, 0, -1, 40)
DEM = np.tile(np.linspace(20.0, 0.5, 40)[:, None], (1, 40))


def _lines(*coords):
    return gpd.GeoSeries(
        [shapely.LineString(c) for c in coords],
        index=pd.Index([f"WU{k:07d}" for k in range(1, len(coords) + 1)]),
        crs=CRS,
    )


def test_the_uphill_side_is_read_off_the_dem():
    # A line running east has the north, uphill, on its left.
    assert (
        forced.uphill_side(shapely.LineString([(5, 20), (25, 20)]), DEM, TRANSFORM) == 1
    )
    assert (
        forced.uphill_side(shapely.LineString([(25, 20), (5, 20)]), DEM, TRANSFORM)
        == -1
    )
    # Off the DEM, or on level ground, it is unknown.
    off = shapely.LineString([(100, 100), (120, 100)])
    assert forced.uphill_side(off, DEM, TRANSFORM) == 0
    level = np.zeros((40, 40))
    line = shapely.LineString([(5, 20), (25, 20)])
    assert forced.uphill_side(line, level, TRANSFORM) == 0


def test_the_band_is_the_minimum_width_on_the_uphill_side():
    lines = _lines([(5, 20), (25, 20)], [(100, 100), (110, 100)])
    elements = forced.gen_forced_elements(
        lines,
        pd.Series([4.0, 0.3], index=lines.index),
        dem=DEM,
        transform=TRANSFORM,
        first_label=7,
    )
    assert elements.index.tolist() == [7, 8]
    assert elements["wall_unit_id"].tolist() == lines.index.tolist()
    # 0.5 H for the 4 m wall; the 0.3 m one is raised to 0.5 m and takes 1 m.
    assert elements["width_m"].tolist() == pytest.approx([2.0, 1.0])
    assert elements["height_m"].tolist() == pytest.approx([4.0, 0.5])
    first = elements.geometry.iloc[0]
    assert first.area == pytest.approx(40.0)
    assert first.bounds[1] == pytest.approx(20.0)
    assert first.bounds[3] == pytest.approx(22.0)
    # Off the DEM: centred on the line, flagged.
    assert elements["side_unknown"].tolist() == [False, True]
    assert elements.geometry.iloc[1].bounds[1] == pytest.approx(99.5)


def test_a_forced_polygon_takes_the_line_elements_depth_and_zones():
    lines = _lines([(5, 20), (25, 20)], [(100, 100), (110, 100)])
    elements = forced.gen_forced_elements(
        lines,
        pd.Series([4.0, 1.0], index=lines.index),
        dem=DEM,
        transform=TRANSFORM,
        first_label=1,
    )
    walled = pd.Series([True, False], index=elements.index)
    zones = forced.gen_forced_zones(
        elements,
        walled,
        is_fill=pd.Series(data=False, index=elements.index),
        fill_thickness_m=pd.Series(np.nan, index=elements.index),
        ground=None,
        first_polygon=50,
        scenario="w000",
    )
    walled_rows = zones[zones["polygon"] == 50]
    assert set(walled_rows["zone"]) == {EVACUATED, IMMINENT, INUNDATED}
    row = walled_rows.iloc[0]
    assert row["element_type"] == FREE_FACE
    # The wall's planar slip: half the height over the band.
    assert row["depth_m"] == pytest.approx(2.0)
    assert row["volume_m3"] == pytest.approx(2.0 * 40.0)
    behind = 4.0 / math.tan(math.radians(BETA_REPOSE_ANGLE_DEG))
    imminent = walled_rows.loc[walled_rows["zone"] == IMMINENT].geometry.iloc[0]
    assert imminent.area == pytest.approx(20.0 * (behind - 2.0))
    assert imminent.bounds[1] == pytest.approx(22.0)
    inundated = walled_rows.loc[walled_rows["zone"] == INUNDATED].geometry.iloc[0]
    runout = 4.0 / float(reach_ratio([90.0], [np.nan])[0][0]) + (
        BETA_SEISMIC_RUNOUT_UNRATED_M
    )
    assert inundated.bounds[1] == pytest.approx(20.0 - runout)
    # The bare one, of unknown side: the bank rule's cover depth, no
    # imminent or inundated zone.
    bare = zones[zones["polygon"] == 51]
    assert bare["zone"].tolist() == [EVACUATED]
    assert bare["element_type"].iloc[0] == BANK
    assert bool(bare["side_unknown"].iloc[0])
    assert (zones["forced"]).all()


def test_a_forced_polygon_on_fill_runs_out_by_the_cut_relation():
    lines = _lines([(5, 20), (25, 20)])
    elements = forced.gen_forced_elements(
        lines,
        pd.Series([4.0], index=lines.index),
        dem=DEM,
        transform=TRANSFORM,
        first_label=1,
    )
    zones = forced.gen_forced_zones(
        elements,
        pd.Series([True], index=elements.index),
        is_fill=pd.Series(data=True, index=elements.index),
        fill_thickness_m=pd.Series(np.nan, index=elements.index),
        ground=None,
        first_polygon=1,
        scenario="w000",
    )
    assert (zones["style"] == CUT_SLOPE).all()
    inundated = zones.loc[zones["zone"] == INUNDATED].geometry.iloc[0]
    runout = 4.0 / float(reach_ratio([90.0], [np.nan])[0][0]) + (
        BETA_SEISMIC_RUNOUT_UNRATED_M
    )
    assert inundated.bounds[1] == pytest.approx(20.0 - runout)


def test_a_deep_forced_deposit_spreads_back_over_its_evacuated_band():
    # A bare half-metre cut bank: the cover depth, 1.5 m, over its 1 m band
    # off a 20 m line is 30 m3. Its run, the step's reach and the unrated
    # seismic distance, is held to two heights, 1 m, and a deposit no deeper
    # than its height needs 60 m2, so it also covers the whole band behind.
    lines = _lines([(5, 20), (25, 20)])
    elements = forced.gen_forced_elements(
        lines,
        pd.Series([0.5], index=lines.index),
        dem=DEM,
        transform=TRANSFORM,
        first_label=1,
    )
    zones = forced.gen_forced_zones(
        elements,
        pd.Series([False], index=elements.index),
        is_fill=pd.Series(data=False, index=elements.index),
        fill_thickness_m=pd.Series(np.nan, index=elements.index),
        ground=None,
        first_polygon=1,
        scenario="w000",
    )
    row = zones.iloc[0]
    assert row["volume_m3"] == pytest.approx(30.0)
    assert row["runout_m"] == pytest.approx(1.0)
    inundated = zones.loc[zones["zone"] == INUNDATED].geometry.iloc[0]
    assert inundated.area == pytest.approx(20.0 * 2.0)
    assert inundated.bounds[3] == pytest.approx(21.0)
    assert inundated.bounds[1] == pytest.approx(19.0)


def test_a_forced_polygon_takes_its_zones_seismic_distance():
    lines = _lines([(5, 20), (25, 20)])
    elements = forced.gen_forced_elements(
        lines,
        pd.Series([4.0], index=lines.index),
        dem=DEM,
        transform=TRANSFORM,
        first_label=1,
    )
    ground = pd.DataFrame([BETA_OFF_MAP_GROUND], index=elements.index)
    zones = forced.gen_forced_zones(
        elements,
        pd.Series([True], index=elements.index),
        is_fill=pd.Series(data=False, index=elements.index),
        fill_thickness_m=pd.Series(np.nan, index=elements.index),
        ground=ground,
        first_polygon=1,
        scenario="w000",
    )
    row = zones.iloc[0]
    zone = int(row["kingsbury_zone"])
    assert row["seismic_runout_m"] == pytest.approx(BETA_SEISMIC_RUNOUT_M[zone])
    reach = 4.0 / float(reach_ratio([90.0], [np.nan])[0][0])
    assert row["runout_m"] == pytest.approx(
        min(reach + BETA_SEISMIC_RUNOUT_M[zone], 2.0 * 4.0)
    )


def test_a_forced_fill_bank_is_no_deeper_than_its_slip():
    # A bare 1 m bank on fill 10 m thick takes the slip from its toe, half its
    # height on the mean behind a step, not the fill.
    lines = _lines([(5, 20), (25, 20)])
    elements = forced.gen_forced_elements(
        lines,
        pd.Series([1.0], index=lines.index),
        dem=DEM,
        transform=TRANSFORM,
        first_label=1,
    )
    zones = forced.gen_forced_zones(
        elements,
        pd.Series([False], index=elements.index),
        is_fill=pd.Series(data=True, index=elements.index),
        fill_thickness_m=pd.Series([10.0], index=elements.index),
        ground=None,
        first_polygon=1,
        scenario="w000",
    )
    assert zones.iloc[0]["depth_m"] == pytest.approx(0.5)
