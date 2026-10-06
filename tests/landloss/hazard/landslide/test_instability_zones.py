"""Tests for the pip, pif and siz stage of the urban slope model."""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
from rasterio.transform import Affine

from landloss.hazard.landslide import bend_split, slope_elements
from landloss.hazard.landslide import instability_zones as zones
from landloss.hazard.landslide.slope_elements import BANK, FREE_FACE, GROUND_GROUPS
from landloss.hazard.landslide.slope_polygons import (
    BETA_MIN_EVACUATED_WIDTH_H,
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


def _slot(n_rows: int, height_m: float = 1.0) -> np.ndarray:
    """High ground with a slot ``n_rows`` wide cut east from column C_TOP.

    Only the slot's west end makes pips (one per row, falling east): the slot's
    sides are too close to the high ground opposite to drop at 5 m.
    """
    dem = np.full(SHAPE, height_m)
    dem[10 : 10 + n_rows, C_TOP + 1 :] = 0.0
    return dem


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
    labels, n = zones.cluster_pifs(mask, 1.0, min_pips=1)
    assert n == 2
    assert labels[5, 5] == labels[5, 7] != 0
    assert labels[5, 10] not in (0, labels[5, 5])
    assert labels[~mask].max() == 0


def test_clusters_under_three_pips_are_not_pifs_and_the_rest_are_renumbered():
    mask = np.zeros((20, 30), dtype=bool)
    mask[2, 2:4] = True  # two pips: not a pif
    mask[8, 2:5] = True  # three pips: a pif
    mask[14, 20] = True  # one pip: not a pif
    mask[16, 10:15] = True  # five pips: a pif
    labels, n = zones.cluster_pifs(mask, 1.0)
    assert zones.BETA_MIN_PIF_PIPS == 3
    assert n == 2
    assert not labels[2].any()
    assert labels[14, 20] == 0
    assert set(labels[8, 2:5]) == {1}
    assert set(labels[16, 10:15]) == {2}


def test_a_slot_of_two_pips_has_no_pif_and_one_of_three_is_a_siz():
    narrow = _zones(_slot(2), "soil_like")
    assert narrow.pips.mask.sum() == 2
    assert narrow.sizs.empty
    assert narrow.found.elements.empty
    assert zones.gen_siz_table(narrow, TRANSFORM, crs=2193).empty
    # Three pips span 2 m, under the 3 m a pif needs; four span 3 m.
    three = _zones(_slot(3), "soil_like")
    assert three.sizs.empty
    assert three.n_pifs_short == 1
    wide = _zones(_slot(4), "soil_like")
    assert len(wide.sizs) == 1
    assert wide.sizs["is_siz"].all()
    assert wide.sizs["n_pips"].iloc[0] == 4
    assert wide.pif_lines.iloc[0].length >= zones.BETA_MIN_PIF_LENGTH_M


def test_pifs_mostly_in_a_building_are_dropped_and_the_rest_renumbered():
    labels = np.zeros((10, 20), dtype=np.int32)
    labels[1, 0:4] = 1  # all four pips on a roof
    labels[4, 0:4] = 2  # two of four: not a majority, kept
    labels[7, 0:5] = 3  # none
    roof = np.zeros(labels.shape, dtype=bool)
    roof[0:2, :] = True
    roof[4, 0:2] = True
    kept, n_kept, n_dropped = zones.exclude_pifs(labels, roof)
    assert (n_kept, n_dropped) == (2, 1)
    assert not kept[1].any()
    assert set(kept[4, 0:4]) == {1}
    assert set(kept[7, 0:5]) == {2}


def test_a_wall_under_a_building_outline_is_no_pif_siz_or_element():
    dem = _wall(1.0)
    building = np.zeros(dem.shape, dtype=bool)
    building[:, C_TOP - 3 : C_TOP + 1] = True
    ground = np.full(dem.shape, GROUND_GROUPS.index("soil_like"), dtype=np.int8)
    result = zones.find_instability_zones(dem, ground, TRANSFORM, exclude=building)
    assert result.n_pifs_excluded == 1
    assert result.sizs.empty
    assert result.found.elements.empty
    assert result.pips.mask.sum() == SHAPE[0]
    assert zones.gen_siz_table(result, TRANSFORM, crs=2193).empty


def _zigzag_pif(n_turns, leg=10):
    """A one-cell-wide pif of square steps: east, south, east, south, ..."""
    labels = np.zeros((80, 80), dtype=np.int32)
    r, c = 2, 2
    for k in range(n_turns + 1):
        for _ in range(leg):
            labels[r, c] = 1
            if k % 2 == 0:
                c += 1
            else:
                r += 1
    labels[r, c] = 1
    return labels


def test_a_pif_is_cut_along_its_spine_by_the_bends_rule():
    labels = _zigzag_pif(7)
    rule = {"max_bends": 3, "stray_tolerance_m": 2.0, "min_segment_m": 3.0}
    pieces, parent, lines = zones.split_pifs(labels, 1.0, max_span_m=50.0, **rule)
    # Each piece's line is its stretch of path, and keeps every rule.
    for xy in lines[1:]:
        assert not bend_split.rule_breaks(
            shapely.LineString(xy), max_bends=3, min_length_m=3.0, max_length_m=50.0
        )
    # With the 185 degree turning cap the 90 degree steps go two to a piece.
    _turned, turned_parent, turned_lines = zones.split_pifs(
        labels, 1.0, max_span_m=50.0, max_turn_deg=185.0, **rule
    )
    assert len(turned_parent) - 1 == 3
    for xy in turned_lines[1:]:
        assert not bend_split.rule_breaks(
            shapely.LineString(xy),
            max_bends=3,
            min_length_m=3.0,
            max_length_m=50.0,
            max_turn_deg=185.0,
        )
    on_pips = labels > 0
    assert (pieces[on_pips] > 0).all()
    assert not pieces[~on_pips].any()
    assert set(parent[1:]) == {1}
    # Eight 10 m legs and seven bends: two pieces, each needing at most three.
    assert len(parent) - 1 == 2
    # Without the bends rule only the 50 m cap cuts the 80 m spine: two pieces.
    pieces, parent, _ = zones.split_pifs(labels, 1.0, max_span_m=50.0)
    assert len(parent) - 1 == 2
    # A short straight pif is one piece either way.
    short = np.zeros((10, 20), dtype=np.int32)
    short[5, 2:12] = 1
    assert len(zones.split_pifs(short, 1.0, max_span_m=50.0, **rule)[1]) == 2


def test_the_wall_height_is_the_near_drop_not_the_walk_to_the_foot():
    # A 1 m wall at the top of a long 30 degree slope: the near drop reads the
    # wall and the next 2 m of slope, not the whole slope.
    cols = np.arange(SHAPE[1], dtype=float)
    z = np.where(
        cols <= C_TOP, 20.0, 19.0 - (cols - C_TOP - 1) * math.tan(math.radians(30))
    )
    dem = np.tile(np.clip(z, 0.0, None), (SHAPE[0], 1))
    pips = zones.find_pips(dem, 1.0)
    labels, _ = zones.cluster_pifs(pips.mask, 1.0)
    heights = zones.gen_pif_near_drops(
        dem, pips, labels, 1.0, reach_m=3.0, quantile=0.8
    )
    assert heights.name == "near_drop_p80_m"
    top = heights.loc[labels[0, C_TOP]]
    assert top == pytest.approx(1.0 + 2.0 * math.tan(math.radians(30)), abs=0.05)
    assert top < 5.0


def test_a_pif_with_a_spine_under_three_metres_is_dropped():
    labels = np.zeros((10, 20), dtype=np.int32)
    labels[2, 2:5] = 1  # three pips, 2 m spine
    labels[6, 2:7] = 2  # five pips, 4 m spine
    kept, n_dropped = zones.drop_short_pifs(labels, 1.0, min_length_m=3.0)
    assert n_dropped == 1
    assert not kept[2].any()
    assert set(kept[6, 2:7]) == {1}


def test_a_piece_takes_the_siz_test_of_its_whole_pif():
    whole = pd.DataFrame(
        {
            "threshold_angle_deg": [35.0],
            "near_step_pass": [True],
            "far_angle_pass": [False],
            "is_siz": [True],
            "max_delta_h_m": [6.0],
        },
        index=pd.Index([1], name="pif_id"),
    )
    pieces = pd.DataFrame(
        {
            "threshold_angle_deg": [45.0, 45.0],
            "near_step_pass": [False, False],
            "far_angle_pass": [False, False],
            "is_siz": [False, False],
            "max_delta_h_m": [1.0, 2.0],
        },
        index=pd.Index([1, 2], name="pif_id"),
    )
    table = zones.piece_table(pieces, np.array([0, 1, 1]), whole)
    assert table["parent_pif_id"].tolist() == [1, 1]
    assert table["is_siz"].tolist() == [True, True]
    assert table["threshold_angle_deg"].tolist() == [35.0, 35.0]
    # The piece's own height stays its own.
    assert table["max_delta_h_m"].tolist() == [1.0, 2.0]


def test_a_long_pif_is_cut_into_pieces_no_longer_than_the_limit():
    labels = np.zeros((10, 100), dtype=np.int32)
    labels[5, :70] = 1
    labels[2, 90:95] = 2
    pieces, parent, _ = zones.split_pifs(labels, 1.0, max_span_m=20.0)
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


def test_a_cut_longer_than_the_span_limit_makes_several_elements_of_one_siz(
    monkeypatch,
):
    # The 30 m cut is under the 50 m cap; a 20 m cap cuts it in two.
    assert len(_zones(_ramp(6.0, 60.0), "soil_like").found.elements) == 1
    monkeypatch.setattr(zones, "MAX_PIF_SPAN_M", 20.0)
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    elements = result.found.elements
    # Each piece is a pif of its own, with its own element, under one parent
    # whose siz test it inherits.
    assert len(elements) == 2
    assert elements["siz_id"].nunique() == 2
    assert len(result.sizs) == 2
    assert set(elements["siz_id"]) == set(result.sizs.index)
    assert result.sizs["parent_pif_id"].nunique() == 1
    assert result.sizs["is_siz"].all()


def test_every_siz_grows_an_element_even_one_the_keep_rule_drops(monkeypatch):
    dem = _slot(4)
    result = _zones(dem, "soil_like")
    assert result.found.elements["kept_by_rule"].all()
    # A minimum length longer than the slot: the keep rule now drops it, and
    # the siz keeps it all the same, with a polygon behind its crest.
    monkeypatch.setattr(slope_elements, "BETA_MIN_ELEMENT_LENGTH_M", 10.0)
    result = _zones(dem, "soil_like")
    elements = result.found.elements
    assert len(elements) == 1
    assert not elements["kept_by_rule"].iloc[0]
    assert elements["siz_id"].iloc[0] == result.sizs.index[0]
    walled = True
    polygons = build_slope_polygons(
        zones.with_walls(result.found, walled), dem, TRANSFORM
    ).polygons
    assert len(polygons) == 1
    assert polygons["width_behind_crest_m"].iloc[0] >= 1.0


def test_a_rock_wall_of_2_m_makes_no_element():
    assert _zones(_wall(2.0), "weak_rock").found.elements.empty


def test_a_gentle_slope_makes_no_element():
    assert _zones(_ramp(10.0, 25.0), "soil_like").found.elements.empty


def test_with_walls_switches_the_element_type_per_element(monkeypatch):
    monkeypatch.setattr(zones, "MAX_PIF_SPAN_M", 20.0)
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
    # Half the 6 m height is wider than the fill's wedge (0.45 H) and the
    # T-44 band, so the floor sets both widths; on weaker retained ground the
    # wedge is wider than the floor and sets it.
    for result in (walled, bare):
        assert result.polygons["width_floored"].all()
        heights = result.polygons["base_height_m"].to_numpy()
        assert result.polygons["width_behind_crest_m"].to_numpy() == pytest.approx(
            BETA_MIN_EVACUATED_WIDTH_H * heights
        )
    weak = build_slope_polygons(
        zones.with_walls(found, with_wall),
        dem,
        TRANSFORM,
        retained_phi_deg=pd.Series(28.0, index=found.elements.index),
    )
    assert not weak.polygons["width_floored"].any()


def test_a_gns_only_line_gets_an_element_and_a_polygon_on_its_uphill_side():
    # A soil cut gives one element; a line on the level ground above it,
    # 0.4 m of step, gets its own, with the floor's metre behind its crest.
    dem = _ramp(6.0, 60.0)
    dem[:, :8] += np.where(np.arange(8) < 5, 0.4, 0.0)
    ground = np.full(dem.shape, GROUND_GROUPS.index("soil_like"), dtype=np.int8)
    result = zones.find_instability_zones(dem, ground, TRANSFORM)
    n_old = len(result.found.elements)
    lines = gpd.GeoSeries(
        [
            shapely.LineString([(5.0, 2.0), (5.0, 28.0)]),
            shapely.LineString([(30.0, 3.0), (30.0, 3.5)]),
        ],
        index=pd.Index(["WU0000007", "WU0000008"], name="wall_unit_id"),
    )
    found = zones.add_line_elements(
        result.found,
        lines,
        pd.Series([0.4, np.nan], index=lines.index),
        dem=dem,
        ground_group=ground,
        transform=TRANSFORM,
    )
    elements = found.elements
    # The old elements keep their labels and columns.
    pd.testing.assert_frame_equal(
        elements.loc[:n_old, result.found.elements.columns],
        result.found.elements,
        check_dtype=False,
    )
    new = elements[elements["wall_unit_id"].notna()]
    assert len(new) == 2
    assert set(new["wall_unit_id"]) == {"WU0000007", "WU0000008"}
    assert (new["grown_in"] == zones.WALL_LINE).all()
    assert (new["siz_id"] == 0).all()
    assert new["height_m"].tolist() == pytest.approx([0.5, 0.5])
    assert (new["overall_angle_deg"] == 90.0).all()
    walled = True
    polygons = build_slope_polygons(
        zones.with_walls(found, walled), dem, TRANSFORM
    ).polygons
    on_line = polygons[polygons["element"].isin(new.index)]
    assert len(on_line) >= 1
    assert (on_line["width_behind_crest_m"] == 1.0).all()


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


def test_a_straight_wall_has_a_straight_spine_facing_east_at_both_ends(
    monkeypatch,
):
    monkeypatch.setattr(zones, "MAX_PIF_SPAN_M", 100.0)
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


def test_an_l_shaped_face_turns_between_its_ends(monkeypatch):
    monkeypatch.setattr(zones, "MAX_PIF_SPAN_M", 100.0)
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
