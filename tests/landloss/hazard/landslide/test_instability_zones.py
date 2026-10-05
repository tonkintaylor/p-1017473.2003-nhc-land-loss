"""Tests for the pip, pif and siz stage of the urban slope model."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
from rasterio.transform import Affine

from landloss.hazard.landslide import instability_zones as zones
from landloss.hazard.landslide.slope_elements import BANK, FREE_FACE, GROUND_GROUPS
from landloss.hazard.landslide.slope_polygons import (
    HEADSCARP_BAND,
    WALL_WEDGE,
    build_slope_polygons,
)

SHAPE = (30, 80)
C_TOP = 20
TRANSFORM = Affine(1, 0, 0, 0, -1, SHAPE[0])


def _wall(height_m: float) -> np.ndarray:
    cols = np.arange(SHAPE[1])
    return np.tile(np.where(cols <= C_TOP, height_m, 0.0), (SHAPE[0], 1))


def _ramp(height_m: float, slope_deg: float) -> np.ndarray:
    cols = np.arange(SHAPE[1], dtype=float)
    z = height_m - (cols - C_TOP) * np.tan(np.radians(slope_deg))
    return np.tile(np.clip(z, 0.0, height_m), (SHAPE[0], 1))


def _assess(dem: np.ndarray, group: str) -> pd.DataFrame:
    pips = zones.find_pips(dem, 1.0)
    labels, _ = zones.cluster_pifs(pips.mask, 1.0)
    ground = np.full(dem.shape, GROUND_GROUPS.index(group), dtype=np.int8)
    return zones.assess_pifs(dem, pips, labels, ground, TRANSFORM)


def _zones(dem: np.ndarray, group: str) -> zones.InstabilityZones:
    ground = np.full(dem.shape, GROUND_GROUPS.index(group), dtype=np.int8)
    return zones.find_instability_zones(dem, ground, TRANSFORM)


# Pips and pifs --------------------------------------------------------------


def test_a_one_metre_wall_gives_a_line_of_pips_facing_east():
    pips = zones.find_pips(_wall(1.0), 1.0)
    assert pips.mask.sum() == SHAPE[0]
    assert pips.mask[:, C_TOP].all()
    assert (pips.direction[:, C_TOP] == 1).all()


def test_a_half_metre_step_is_not_a_pip():
    assert not zones.find_pips(_wall(0.5), 1.0).mask.any()


def test_a_slope_gentler_than_the_drop_gives_no_pips():
    assert not zones.find_pips(_ramp(10.0, 30.0), 1.0).mask.any()


def test_nodata_neighbours_make_no_pip():
    dem = _wall(1.0)
    dem[:, C_TOP + 1 :] = np.nan
    assert not zones.find_pips(dem, 1.0).mask.any()


def test_pips_two_metres_apart_share_a_pif_and_three_do_not():
    mask = np.zeros((20, 30), dtype=bool)
    mask[5, 5] = mask[5, 7] = mask[5, 10] = True
    labels, n = zones.cluster_pifs(mask, 1.0)
    assert n == 2
    assert labels[5, 5] == labels[5, 7] != 0
    assert labels[5, 10] not in (0, labels[5, 5])
    assert labels[~mask].max() == 0


def test_a_long_pif_is_cut_into_pieces_no_longer_than_the_limit():
    labels = np.zeros((10, 100), dtype=np.int32)
    labels[5, :70] = 1
    labels[2, 90:95] = 2
    pieces, parent = zones.split_pifs(labels, 1.0, max_span_m=20.0)
    on_pips = labels > 0
    assert (pieces[on_pips] > 0).all()
    assert not pieces[~on_pips].any()
    long_pieces = np.unique(pieces[labels == 1])
    assert long_pieces.size == 4
    assert set(parent[long_pieces]) == {1}
    for piece in long_pieces:
        cols = np.nonzero(pieces == piece)[1]
        assert cols.max() - cols.min() <= 20
    assert parent[pieces[2, 90]] == 2
    assert np.unique(pieces[labels == 2]).size == 1


def test_no_pips_make_no_pifs():
    labels, n = zones.cluster_pifs(np.zeros((5, 5), dtype=bool), 1.0)
    assert n == 0
    assert not labels.any()


def test_adjacent_step_thresholds_by_group():
    assert zones.ADJACENT_STEP_M == {
        "soil_like": 0.7,
        "weak_rock": 3.0,
        "stronger_rock": 3.0,
    }


def test_adjacent_step_loader_rejects_a_missing_column(tmp_path):
    path = tmp_path / "seed.csv"
    path.write_text(
        "ground_group,min_step_height_m,bank_min_slope_deg\nsoil_like,0.5,18.4\n"
    )
    with pytest.raises(ValueError, match="adjacent_step_m"):
        zones.load_adjacent_step_thresholds(path)


# Sizs -----------------------------------------------------------------------


def test_a_soil_wall_of_0_8_m_is_a_siz():
    table = _assess(_wall(0.8), "soil_like")
    assert table["is_siz"].all()
    assert table["near_step_pass"].all()


def test_a_rock_wall_of_2_m_is_not_a_siz_and_one_of_3_m_is():
    assert not _assess(_wall(2.0), "weak_rock")["is_siz"].any()
    assert _assess(_wall(3.0), "weak_rock")["is_siz"].all()
    assert _assess(_wall(3.0), "stronger_rock")["is_siz"].all()


def test_a_tall_rock_slope_uses_the_gentler_angle_above_3_5_m():
    # 42 degrees is under the 45 degree limit for faces under 3.5 m but over the
    # 40 degree limit from 3.5 m up, so height decides.
    tall = _assess(_ramp(10.0, 42.0), "weak_rock")
    assert tall["is_siz"].all()
    assert tall["max_angle_above_deg"].iloc[0] == pytest.approx(42.0, abs=0.5)
    assert not _assess(_ramp(3.0, 42.0), "weak_rock")["is_siz"].any()


def test_a_rock_slope_under_both_limits_is_not_a_siz():
    assert not _assess(_ramp(10.0, 38.0), "weak_rock")["is_siz"].any()


def test_a_soil_slope_of_36_degrees_is_a_siz_and_one_of_34_has_no_pips():
    assert _assess(_ramp(10.0, 36.0), "soil_like")["is_siz"].all()
    assert _assess(_ramp(10.0, 34.0), "soil_like").empty


def test_the_table_records_the_face_for_the_rw_workflow():
    row = _assess(_ramp(10.0, 50.0), "weak_rock").iloc[0]
    assert row["ground_group"] == "weak_rock"
    assert row["fall_bearing_deg"] == pytest.approx(90.0)
    assert row["crest_z_m"] == pytest.approx(10.0)
    assert row["toe_z_m"] < 1.0
    assert row["max_delta_h_m"] > 8.0
    assert row["threshold_angle_deg"] == 40.0


def test_a_pif_takes_the_ground_group_of_its_pips():
    dem = _wall(3.0)
    pips = zones.find_pips(dem, 1.0)
    labels, _ = zones.cluster_pifs(pips.mask, 1.0)
    ground = np.full(dem.shape, GROUND_GROUPS.index("weak_rock"), dtype=np.int8)
    ground[:, : C_TOP + 1] = GROUND_GROUPS.index("soil_like")
    table = zones.assess_pifs(dem, pips, labels, ground, TRANSFORM)
    assert (table["ground_group"] == "soil_like").all()


# Elements -------------------------------------------------------------------


def test_a_soil_cut_makes_one_walled_element_with_its_siz_recorded(monkeypatch):
    monkeypatch.setattr(zones, "MAX_PIF_SPAN_M", 100.0)
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    elements = result.found.elements
    assert len(elements) == 1
    row = elements.iloc[0]
    assert row["element_type"] == FREE_FACE
    assert row["grown_in"] == zones.SIZ_PASS
    assert row["height_m"] == pytest.approx(6.0, abs=1.0)
    assert row["siz_id"] in result.sizs.index
    assert row["siz_max_delta_h_m"] > 5.0


def test_a_cut_longer_than_the_span_limit_makes_several_elements_of_one_siz():
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    elements = result.found.elements
    assert len(elements) == 2
    assert elements["siz_id"].nunique() == 1
    assert len(result.sizs) == 1


def test_a_rock_wall_of_2_m_makes_no_element():
    assert _zones(_wall(2.0), "weak_rock").found.elements.empty


def test_a_gentle_slope_makes_no_element():
    assert _zones(_ramp(10.0, 25.0), "soil_like").found.elements.empty


def test_with_walls_switches_the_element_type_per_element():
    found = _zones(_ramp(6.0, 60.0), "soil_like").found
    walled, bare = True, False
    assert (zones.with_walls(found, walled).elements["element_type"] == FREE_FACE).all()
    assert (zones.with_walls(found, bare).elements["element_type"] == BANK).all()
    mixed = pd.Series([False, True], index=found.elements.index)
    types = zones.with_walls(found, mixed).elements["element_type"]
    assert types.tolist() == [BANK, FREE_FACE]


def test_the_wall_scenarios_set_the_width_rule_behind_the_crest():
    dem = _ramp(6.0, 60.0)
    found = _zones(dem, "soil_like").found
    with_wall, without_wall = True, False
    walled = build_slope_polygons(zones.with_walls(found, with_wall), dem, TRANSFORM)
    bare = build_slope_polygons(zones.with_walls(found, without_wall), dem, TRANSFORM)
    assert set(walled.polygons["width_rule"]) == {WALL_WEDGE}
    assert set(bare.polygons["width_rule"]) == {HEADSCARP_BAND}


def test_grids_of_different_shapes_are_rejected():
    with pytest.raises(ValueError, match="ground group grid"):
        zones.find_instability_zones(
            _wall(1.0), np.zeros((3, 3), dtype=np.int8), TRANSFORM
        )


# The siz file ---------------------------------------------------------------


def test_the_siz_file_round_trips_with_point_geometry(tmp_path):
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    table = zones.gen_siz_table(result, TRANSFORM, crs=2193)
    path = tmp_path / "siz.parquet"
    zones.write_siz_table(table, path)
    back = zones.read_siz_table(path)
    assert list(back.index) == list(result.sizs.index)
    assert back["is_siz"].tolist() == result.sizs["is_siz"].tolist()
    assert back.geometry.iloc[0].geom_type == "MultiPoint"
    assert back.crs.to_epsg() == 2193
    for directions, points in zip(back["pip_direction"], back.geometry, strict=True):
        assert len(directions) == len(points.geoms)


def test_the_siz_file_round_trips_with_the_spines_joined(tmp_path):
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    table = zones.gen_siz_table(result, TRANSFORM, crs=2193)
    table = table.join(zones.gen_pif_spines(table, cell_size_m=1.0, end_window_m=3.0))
    path = tmp_path / "siz.parquet"
    zones.write_siz_table(table, path)
    back = zones.read_siz_table(path)
    assert back.geometry.iloc[0].geom_type == "MultiPoint"
    assert back["spine"].iloc[0].geom_type == "LineString"


# Spines ---------------------------------------------------------------------


def _spines(dem: np.ndarray) -> pd.DataFrame:
    table = zones.gen_siz_table(_zones(dem, "soil_like"), TRANSFORM, crs=2193)
    return zones.gen_pif_spines(table, cell_size_m=1.0, end_window_m=3.0)


def _bearing_gap(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def test_a_straight_wall_has_a_straight_spine_facing_east_at_both_ends():
    spines = _spines(_wall(1.0))
    assert len(spines) == 1
    row = spines.iloc[0]
    # The path steps up to PIF_JOIN_M at a time, so it need not visit every pip.
    assert np.array(row["spine"].coords)[:, 0] == pytest.approx(20.5)
    assert row["spine_length_m"] == pytest.approx(SHAPE[0] - 1, abs=1e-6)
    assert (row["end_a_x"], row["end_a_y"]) == pytest.approx((20.5, 0.5))
    assert (row["end_b_x"], row["end_b_y"]) == pytest.approx((20.5, 29.5))
    assert row["end_a_fall_deg"] == pytest.approx(90.0)
    assert row["end_b_fall_deg"] == pytest.approx(90.0)
    assert row["fall_resultant"] == pytest.approx(1.0)


def test_an_l_shaped_face_turns_between_its_ends():
    rows, cols = np.indices(SHAPE)
    dem = np.where((cols <= C_TOP) & (rows >= 15), 2.0, 0.0)
    table = zones.gen_siz_table(_zones(dem, "soil_like"), TRANSFORM, crs=2193)
    assert len(table) == 1
    assert len(table.geometry.iloc[0].geoms) == 35
    row = zones.gen_pif_spines(table, cell_size_m=1.0, end_window_m=3.0).iloc[0]
    assert (row["end_a_x"], row["end_a_y"]) == pytest.approx((0.5, 14.5))
    assert (row["end_b_x"], row["end_b_y"]) == pytest.approx((20.5, 0.5))
    assert _bearing_gap(row["end_a_fall_deg"], 0.0) < 15.0
    assert _bearing_gap(row["end_b_fall_deg"], 90.0) < 15.0
    assert 60.0 <= _bearing_gap(row["end_a_fall_deg"], row["end_b_fall_deg"]) <= 120.0
    assert row["fall_resultant"] < 0.95
    assert row["spine_length_m"] > 20.0


def _one_pip(direction: int) -> gpd.GeoDataFrame:
    table = gpd.GeoDataFrame(
        {"pip_direction": [np.array([direction], dtype=np.int8)]},
        geometry=[shapely.MultiPoint([(10.5, 5.5)])],
        crs=2193,
    )
    table.index = pd.Index([1], name="pif_id")
    return table


def test_a_one_pip_pif_gets_a_one_cell_spine_across_its_fall():
    row = zones.gen_pif_spines(_one_pip(1), cell_size_m=1.0, end_window_m=3.0).iloc[0]
    assert row["spine_length_m"] == pytest.approx(1.0)
    assert (row["end_a_x"], row["end_a_y"]) == pytest.approx((10.5, 5.0))
    assert (row["end_b_x"], row["end_b_y"]) == pytest.approx((10.5, 6.0))
    assert row["end_a_fall_deg"] == pytest.approx(90.0)
    assert row["end_b_fall_deg"] == pytest.approx(90.0)
    assert row["fall_resultant"] == pytest.approx(1.0)


@pytest.mark.parametrize("width", [1, 2, 3])
def test_a_thick_ribbon_has_one_spine_end_at_each_end(width):
    # A face 20 cells long, falling south, one to three cells thick: the spine
    # must not fold back down the next row with both ends at one end.
    xs, ys = np.meshgrid(np.arange(20) + 0.5, np.arange(width) + 0.5)
    table = gpd.GeoDataFrame(
        {"pip_direction": [np.full(xs.size, 2, dtype=np.int8)]},
        geometry=[shapely.MultiPoint(np.column_stack([xs.ravel(), ys.ravel()]))],
        crs=2193,
    )
    table.index = pd.Index([1], name="pif_id")
    row = zones.gen_pif_spines(table, cell_size_m=1.0, end_window_m=3.0).iloc[0]
    assert row["spine_length_m"] == pytest.approx(19.0, abs=1.0)
    assert row["end_a_x"] == pytest.approx(0.5)
    assert row["end_b_x"] == pytest.approx(19.5)
    assert row["end_a_fall_deg"] == pytest.approx(180.0)
    assert row["end_b_fall_deg"] == pytest.approx(180.0)


def test_pip_directions_that_do_not_match_the_pips_are_rejected():
    table = _one_pip(1)
    table["pip_direction"] = [np.array([1, 1], dtype=np.int8)]
    with pytest.raises(ValueError, match="one direction per pip"):
        zones.gen_pif_spines(table, cell_size_m=1.0, end_window_m=3.0)
