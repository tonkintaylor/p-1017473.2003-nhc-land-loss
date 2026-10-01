import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from landloss.domain.loss_contract import (
    BRIDGE_COLUMNS,
    CULVERT_COLUMNS,
    LAND_COLUMNS,
    RW_COLUMNS,
)
from landloss.loss.pricing import beta_wall_height_m
from landloss.vul.landslide.land.damaged_area import UNION_AREA_COLUMN
from landloss.vul.loss_input import (
    build_crossing_tables,
    build_land_table,
    build_rw_table,
)

CRS = "EPSG:2193"


def insured():
    return gpd.GeoDataFrame(
        {
            "land_id": ["1-L01", "2-L01"],
            "claim_id": [1, 2],
            "land_rate_excl_gst_nzd_per_m2": [500.0, 700.0],
            "land_rate_incl_gst_nzd_per_m2": [575.0, 805.0],
            "area_m2": [400.0, 900.0],
            "dwelling_count": [1, 2],
        },
        geometry=[box(0, 0, 20, 20), box(100, 0, 130, 30)],
        crs=CRS,
    )


def liquefaction():
    return pd.DataFrame(
        {
            "land_id": ["1-L01", "2-L01"],
            "ld_state": [3, 1],
            "cost_nzd": [12_000.0, 0.0],
            "damaged_area_m2": [180.0, 0.0],
        }
    )


def landslide():
    return pd.DataFrame(
        {
            "land_id": ["1-L01"],
            "evacuated_area_m2": [100.0],
            "inundated_area_m2": [150.0],
            UNION_AREA_COLUMN: [200.0],
            "inundated_depth_m": [1.5],
        }
    )


def walls():
    return gpd.GeoDataFrame(
        {
            "rw_id": ["1-RW01", "1-RW02"],
            "claim_id": [1, 1],
            "size_class": ["small", "large"],
            "length_m": [12, 30],
            "damage_state": ["replace", "no damage"],
        },
        geometry=[LineString([(0, 0), (12, 0)]), LineString([(0, 5), (30, 5)])],
        crs=CRS,
    )


def wall_flags():
    return pd.DataFrame(
        {
            "rw_id": ["1-RW02", "1-RW01"],
            "is_evacuated": [True, False],
            "is_inundated": [False, True],
        }
    )


def crossings():
    return gpd.GeoDataFrame(
        {
            "crossing_id": ["1-X01", "1-X02", "2-X01"],
            "claim_id": [1, 1, 2],
            "asset": ["culvert", "bridge", "culvert"],
            "damage_state": ["replace", "replace", "no damage"],
        },
        geometry=[Point(1, 1), Point(2, 2), Point(110, 10)],
        crs=CRS,
    )


def crossing_flags():
    return pd.DataFrame(
        {
            "crossing_id": ["1-X01", "1-X02", "2-X01"],
            "is_evacuated": [True, False, False],
            "is_inundated": [False, True, True],
        }
    )


def test_the_land_table_carries_the_contract_columns_and_the_extras():
    land = build_land_table(insured(), liquefaction(), landslide())
    assert list(land.columns) == [*LAND_COLUMNS, "dwelling_count", "geometry"]
    assert land.crs == CRS
    assert land["Liq_LD_state"].tolist() == [3, 1]
    # Only the GST-inclusive rate is handed on.
    assert land["$/m2 market value"].tolist() == [575.0, 805.0]
    assert land["total_insured_land_area"].tolist() == [400.0, 900.0]


def test_the_liquefied_area_is_passed_through_and_missing_land_has_none():
    liquefied = liquefaction().iloc[:1]
    land = build_land_table(insured(), liquefied, landslide()).set_index("land_id")
    assert land.loc["1-L01", "Liq_LD_damaged_area"] == pytest.approx(180.0)
    assert land.loc["2-L01", "Liq_LD_damaged_area"] == 0.0


def test_land_no_landslide_reached_has_no_damaged_area_and_no_depth():
    land = build_land_table(insured(), liquefaction(), landslide()).set_index("land_id")
    unreached = land.loc["2-L01"]
    assert unreached["land_slide_total_insured_land_area"] == 0.0
    assert unreached["inundated_insured_area"] == 0.0
    assert unreached["evacuated_area"] == 0.0
    assert np.isnan(unreached["inundated_mean_depth"])


def test_the_landslide_area_is_the_union_passed_through_not_the_sum():
    land = build_land_table(insured(), liquefaction(), landslide()).set_index("land_id")
    reached = land.loc["1-L01"]
    assert reached["land_slide_total_insured_land_area"] == pytest.approx(200.0)
    assert reached["evacuated_area"] == pytest.approx(100.0)
    assert reached["inundated_insured_area"] == pytest.approx(150.0)
    assert reached["inundated_mean_depth"] == pytest.approx(1.5)


def test_a_duplicated_land_id_is_refused():
    land = insured()
    land["land_id"] = "1-L01"
    with pytest.raises(ValueError, match="duplicated"):
        build_land_table(land, liquefaction(), landslide())


def test_the_rw_table_maps_size_and_length_and_derives_the_shaking_flag():
    rw = build_rw_table(walls(), wall_flags())
    assert list(rw.columns) == [*RW_COLUMNS, "geometry"]
    assert rw["rw_size"].tolist() == ["small", "large"]
    assert rw["rw_length"].dtype == np.float64
    assert rw["rw_length"].tolist() == [12.0, 30.0]
    assert rw["is_damaged_by_shaking"].tolist() == [True, False]
    assert rw["is_evacuated"].tolist() == [False, True]
    assert rw["is_inundated"].tolist() == [True, False]
    assert rw["is_evacuated"].dtype == bool
    assert rw.crs == CRS


def test_a_wall_without_flags_is_refused():
    with pytest.raises(ValueError, match="no landslide flags"):
        build_rw_table(walls(), wall_flags().iloc[:1])


def test_crossings_split_into_culverts_and_bridges_with_renamed_ids():
    culverts, bridges = build_crossing_tables(crossings(), crossing_flags())
    assert list(culverts.columns) == [*CULVERT_COLUMNS, "is_evacuated", "geometry"]
    assert list(bridges.columns) == [*BRIDGE_COLUMNS, "geometry"]
    assert culverts["culvert_id"].tolist() == ["1-X01", "2-X01"]
    assert culverts["is_damaged"].tolist() == [True, False]
    assert culverts["is_evacuated"].tolist() == [True, False]
    assert culverts["is_inundated"].tolist() == [False, True]
    assert bridges["bridge_id"].tolist() == ["1-X02"]
    assert bridges["is_damaged_by_shaking"].tolist() == [True]
    assert bridges["is_inundated"].tolist() == [True]


def test_a_crossing_without_flags_is_refused():
    with pytest.raises(ValueError, match="no landslide flags"):
        build_crossing_tables(crossings(), crossing_flags().iloc[:2])


def test_no_crossings_gives_two_empty_tables_with_the_full_schema():
    empty = crossings().iloc[:0]
    culverts, bridges = build_crossing_tables(empty, crossing_flags().iloc[:0])
    assert culverts.empty
    assert bridges.empty
    assert list(culverts.columns) == [*CULVERT_COLUMNS, "is_evacuated", "geometry"]
    assert list(bridges.columns) == [*BRIDGE_COLUMNS, "geometry"]
    assert culverts.crs == CRS
    assert bridges.crs == CRS
    assert culverts["is_damaged"].dtype == bool
    assert bridges["is_evacuated"].dtype == bool


def test_the_rw_sizes_are_ones_the_loss_module_prices():
    rw = build_rw_table(walls(), wall_flags())
    heights = beta_wall_height_m(rw["rw_size"].to_numpy())
    assert heights.shape == (2,)
