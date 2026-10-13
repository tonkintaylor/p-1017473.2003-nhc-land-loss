"""Tests for the derived layers the end-to-end QGIS build adds."""

import geopandas as gpd
import pandas as pd
import shapely

from scripts.landloss.qgis import gen_qgis_e2e_build as build

CRS = 2193


def line(x):
    return shapely.LineString([(x, 0), (x + 5, 0)])


def test_crossings_are_labelled_by_what_damaged_them():
    bridges = gpd.GeoDataFrame(
        {
            "bridge_id": [1, 2],
            "claim_id": [10, 11],
            "is_damaged_by_shaking": [True, False],
            "is_evacuated": [False, False],
            "is_inundated": [False, True],
        },
        geometry=[line(0), line(10)],
        crs=CRS,
    )
    culverts = gpd.GeoDataFrame(
        {
            "culvert_id": [3, 4],
            "claim_id": [12, 13],
            "is_damaged": [True, False],
            "is_evacuated": [True, False],
            "is_inundated": [False, False],
        },
        geometry=[line(20), line(30)],
        crs=CRS,
    )

    crossings = build.gen_crossing_damage(bridges, culverts)

    assert crossings["outcome"].tolist() == [
        "bridge_shaking",
        "bridge_landslide",
        "culvert_shaking_and_landslide",
        "culvert_none",
    ]
    assert set(crossings["outcome"]) <= set(build.CROSSING_COLOUR)
    assert crossings.crs.to_epsg() == CRS


def test_faces_take_their_spine_and_class_and_drop_a_face_with_no_spine():
    index = pd.Index([5, 6, 7], name="pif_id")
    sizs = gpd.GeoDataFrame(
        {
            "is_siz": [True, False, True],
            "n_pips": [4, 3, 2],
            "ground_modification": ["cut", "natural", "fill"],
            "spine": gpd.GeoSeries([line(0), line(10), None], crs=CRS).array,
        },
        geometry=[shapely.MultiPoint([(0, 0), (1, 0)])] * 3,
        crs=CRS,
        index=index,
    )
    cut_fill = pd.DataFrame(
        {
            "face_drop_m": [2.0, 1.5, 1.0],
            "excess_drop_m": [1.8, 0.2, 1.1],
            "position": [-0.9, 0.0, 0.8],
            "cut_fill_class": ["cut", "natural", "fill"],
        },
        index=index,
    )

    faces = build.gen_face_classes(sizs, cut_fill)

    assert faces["pif_id"].tolist() == [5, 6]
    assert faces["cut_fill_class"].tolist() == ["cut", "natural"]
    assert (faces.geom_type == "LineString").all()
    assert set(faces["cut_fill_class"]) <= set(build.CUT_FILL_CLASS_COLOUR)
