"""Tests for the retaining wall candidate evidence."""

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from landloss.hazard.landslide import bend_split
from landloss.hazard.landslide.wall_candidates import (
    GNS_ONLY_CLASS,
    LOW_HEIGHT_CLASS,
    NOT_CANDIDATE,
    SIZ_CLASS,
    _property_frame,
    boundary_positions,
    gen_gns_only_candidates,
    property_of_pifs,
    wall_candidate_evidence,
)

CRS = 2193


def _layer(geometries, **columns):
    return gpd.GeoDataFrame(columns, geometry=list(geometries), crs=CRS)


@pytest.fixture
def pifs():
    """Three pifs along x: a siz, a non-siz beside a wall, a non-siz alone."""
    centres = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
    table = _layer(
        [shapely.MultiPoint([(x, y), (x + 1, y)]) for x, y in centres],
        x=[c[0] for c in centres],
        y=[c[1] for c in centres],
        is_siz=[True, False, False],
        max_delta_h_m=[4.0, 0.3, 0.3],
    )
    table.index = pd.Index([1, 2, 3], name="pif_id")
    return table


def _evidence(pifs, **overrides):
    empty = _layer([])
    layers = {
        "walls": _layer([shapely.LineString([(100.5, 1.0), (100.5, 5.0)])]),
        "cut_fill_lines": empty,
        "cut_slopes": _layer([shapely.box(-5, -5, 5, 5)]),
        "fill_bodies": empty,
        "ground_map": _layer(
            [shapely.box(-10, -10, 150, 10)],
            material=["rock"],
            modification=["cut"],
        ),
        "buildings": _layer([shapely.box(0, 20, 10, 30)]),
    }
    layers.update(overrides)
    return wall_candidate_evidence(pifs, wall_match_m=2.0, search_m=50.0, **layers)


def test_a_siz_is_a_candidate_and_a_mapped_wall_makes_a_low_height_one(pifs):
    evidence = _evidence(pifs)
    assert evidence["candidate_class"].tolist() == [
        SIZ_CLASS,
        LOW_HEIGHT_CLASS,
        NOT_CANDIDATE,
    ]
    assert evidence["is_wall_candidate"].tolist() == [True, True, False]


def test_distances_are_nan_beyond_the_search_distance(pifs):
    evidence = _evidence(pifs)
    assert evidence.loc[2, "gns_wall_m"] == pytest.approx(1.118, abs=1e-3)
    assert evidence["gns_wall_m"].isna().tolist() == [True, False, True]
    assert evidence.loc[1, "building_m"] == pytest.approx(20.0)
    assert evidence["building_m"].isna().tolist() == [False, True, True]


def test_the_slide_polygons_and_ground_map_are_read_onto_the_pifs(pifs):
    evidence = _evidence(pifs)
    assert evidence["in_slide_cut"].tolist() == [True, False, False]
    assert not evidence["in_slide_fill"].any()
    assert evidence["ground_material"].tolist()[:2] == ["rock", "rock"]
    assert pd.isna(evidence.loc[3, "ground_material"])


def test_every_layer_may_be_empty(pifs):
    empty = _layer([])
    evidence = _evidence(
        pifs,
        walls=empty,
        buildings=empty,
        cut_slopes=empty,
        ground_map=_layer([], material=[], modification=[]),
    )
    assert evidence["candidate_class"].tolist() == [
        SIZ_CLASS,
        NOT_CANDIDATE,
        NOT_CANDIDATE,
    ]
    assert evidence["gns_wall_m"].isna().all()


@pytest.fixture
def properties():
    """Two rateable properties side by side, a road parcel and a far one."""
    return _layer(
        [
            shapely.box(-10, -10, 50, 10),
            shapely.box(50, -10, 150, 10),
            shapely.box(150, -10, 250, 10),
            shapely.box(290, -10, 340, 10),
        ],
        source_id=[1, 2, 3, 4],
        source=["NZ Unit of Property"] * 2
        + ["NZ Primary Parcels - Road", "NZ Unit of Property"],
        valuation_reference=["A", "B", None, "D"],
        title_type=["Freehold", "Unit", None, "Freehold"],
    )


def _pif_table(point_sets):
    table = _layer([shapely.MultiPoint(points) for points in point_sets])
    table.index = pd.Index(range(1, len(point_sets) + 1), name="pif_id")
    return table


def test_a_pif_takes_the_property_holding_most_of_its_points(properties):
    sizs = _pif_table(
        [
            [(0, 0), (1, 0)],
            [(48, 0), (49, 0), (51, 0)],
            [(200, 0)],
            [(500, 500)],
        ]
    )
    result = property_of_pifs(sizs, properties)
    assert result["property_id"].tolist()[:3] == ["1", "1", "3"]
    assert result["valuation_reference"].tolist()[:2] == ["A", "A"]
    assert result["property_is_road"].tolist()[:3] == [False, False, True]
    assert result["property_share"].tolist() == pytest.approx([1.0, 2 / 3, 1.0, 0.0])
    assert result["n_properties"].tolist() == [1, 2, 1, 0]
    assert pd.isna(result.loc[4, "property_id"])


def test_a_mapped_wall_with_no_pip_near_it_becomes_a_gns_only_candidate(properties):
    sizs = _pif_table([[(100, 0), (101, 0)]])
    walls = _layer(
        [
            shapely.LineString([(100.5, 1.0), (100.5, 5.0)]),
            shapely.LineString([(300.0, 0.0), (330.0, 0.0)]),
            shapely.LineString([(400.0, 0.0), (401.0, 0.0)]),
        ]
    )
    candidates = gen_gns_only_candidates(
        sizs,
        walls=walls,
        properties=properties,
        ground_map=_layer([], material=[], modification=[]),
        buildings=_layer([shapely.box(300, 20, 310, 30)]),
        wall_match_m=2.0,
        min_length_m=3.5,
        max_length_m=20.0,
        search_m=50.0,
        max_bends=3,
        stray_tolerance_m=2.0,
        max_turn_deg=185.0,
    )
    assert len(candidates) == 2
    assert (candidates["candidate_class"] == GNS_ONLY_CLASS).all()
    assert candidates["length_m"].tolist() == pytest.approx([15.0, 15.0])
    assert candidates["x"].tolist() == pytest.approx([307.5, 322.5])
    assert candidates["property_id"].tolist() == ["4", "4"]
    assert candidates["building_m"].tolist() == pytest.approx([20.0, 20.6155], abs=1e-3)


def _gns_only(sizs, walls, properties):
    return gen_gns_only_candidates(
        sizs,
        walls=walls,
        properties=properties,
        ground_map=_layer([], material=[], modification=[]),
        buildings=_layer([]),
        wall_match_m=2.0,
        min_length_m=3.5,
        max_length_m=20.0,
        search_m=50.0,
        max_bends=3,
        stray_tolerance_m=2.0,
        max_turn_deg=185.0,
    )


def test_gns_only_candidates_are_indexed_by_gns_only_id(properties):
    sizs = _pif_table([[(100, 0), (101, 0)]])
    walls = _layer([shapely.LineString([(300.0, 0.0), (330.0, 0.0)])])
    candidates = _gns_only(sizs, walls, properties)
    assert candidates.index.name == "gns_only_id"
    assert candidates.index.tolist() == [0, 1]


def test_a_pif_mostly_on_a_road_goes_to_the_next_rateable_property(properties):
    sizs = _pif_table([[(148, 0), (149, 0), (151, 0), (152, 0), (153, 0)]])
    result = property_of_pifs(sizs, properties)
    assert result.loc[1, "property_id"] == "3"
    assert bool(result.loc[1, "property_is_road"])
    assert result.loc[1, "rateable_property_id"] == "2"
    assert result.loc[1, "rateable_share"] == pytest.approx(2 / 5)


def test_a_pif_only_on_road_has_no_rateable_property(properties):
    sizs = _pif_table([[(200, 0), (201, 0)], [(0, 0)], [(500, 500)]])
    result = property_of_pifs(sizs, properties)
    assert pd.isna(result.loc[1, "rateable_property_id"])
    assert result.loc[1, "rateable_share"] == 0.0
    assert result.loc[2, "rateable_property_id"] == "1"
    assert result.loc[2, "rateable_share"] == pytest.approx(1.0)
    assert pd.isna(result.loc[3, "rateable_property_id"])
    assert result.loc[3, "rateable_share"] == 0.0


def test_a_gns_only_stretch_is_cut_by_the_line_rules(properties):
    # A stretch 2 m off no pip, zig-zagging in 10 m square steps: the turning
    # cap allows two right angles a piece, and every piece keeps the rules.
    sizs = _pif_table([[(100, 0), (101, 0)]])
    xy = [(300.0, 0.0)]
    for k in range(6):
        x, y = xy[-1]
        xy.append((x + 10.0, y) if k % 2 == 0 else (x, y + 10.0))
    walls = _layer([shapely.LineString(xy)])
    candidates = gen_gns_only_candidates(
        sizs,
        walls=walls,
        properties=properties,
        ground_map=_layer([], material=[], modification=[]),
        buildings=_layer([]),
        wall_match_m=2.0,
        min_length_m=3.0,
        max_length_m=50.0,
        search_m=50.0,
        max_bends=3,
        stray_tolerance_m=2.0,
        max_turn_deg=185.0,
    )
    assert len(candidates) == 2
    for line in candidates.geometry:
        assert not bend_split.rule_breaks(
            line, max_bends=3, min_length_m=3.0, max_length_m=50.0, max_turn_deg=185.0
        )
    assert candidates["length_m"].sum() == pytest.approx(60.0, abs=3.0)


def test_boundary_positions_cut_once_per_property():
    lots = _property_frame(
        _layer(
            [shapely.box(x, -5, x + 20, 5) for x in (0, 20, 40)],
            source_id=[1, 2, 3],
            source=["NZ Primary Parcels"] * 3,
            valuation_reference=["a", "b", "c"],
            title_type=["Freehold"] * 3,
        )
    )
    line = shapely.LineString([(1, 0), (59, 0)])
    assert boundary_positions(line, lots, 3.0) == pytest.approx([19.0, 39.0])
    # A stretch under 3 m joins its neighbour.
    assert boundary_positions(shapely.LineString([(1, 0), (21, 0)]), lots, 3.0) == []
