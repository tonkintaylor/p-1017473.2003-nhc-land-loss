"""Tests for the retaining wall candidate evidence."""

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from landloss.hazard.landslide.wall_candidates import (
    NOT_CANDIDATE,
    SIZ_CLASS,
    SMALL_CLASS,
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


def test_a_siz_is_a_candidate_and_a_mapped_wall_makes_a_small_one(pifs):
    evidence = _evidence(pifs)
    assert evidence["candidate_class"].tolist() == [
        SIZ_CLASS,
        SMALL_CLASS,
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
