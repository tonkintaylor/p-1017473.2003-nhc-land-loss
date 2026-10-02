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
    """The world's population: two flat-land walls and one on a slope."""
    return gpd.GeoDataFrame(
        {
            "rw_id": ["1-RW01", "1-RW02", "2-RW01"],
            "claim_id": [1, 1, 2],
            "size_class": ["small", "large", "medium"],
            "length_m": [12, 30, 8],
            "is_flatland": [True, True, False],
        },
        geometry=[
            LineString([(0, 0), (12, 0)]),
            LineString([(0, 5), (30, 5)]),
            LineString([(100, 0), (108, 0)]),
        ],
        crs=CRS,
    )


def wall_states():
    """The shaking step's states: flat-land walls only, in its own order."""
    return pd.DataFrame(
        {
            "rw_id": ["1-RW02", "1-RW01"],
            "damage_state": ["no damage", "replace"],
        }
    )


def wall_flags():
    """The wall landslide step's flags, one row per wall in the population."""
    return pd.DataFrame(
        {
            "rw_id": ["1-RW02", "2-RW01", "1-RW01"],
            "is_damaged_by_shaking": [False, True, False],
            "is_evacuated": [True, False, False],
            "is_inundated": [False, False, True],
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


def test_the_rw_table_is_spined_on_the_population_in_its_order():
    rw = build_rw_table(walls(), wall_states(), wall_flags())
    assert list(rw.columns) == [*RW_COLUMNS, "geometry"]
    assert rw["rw_id"].tolist() == ["1-RW01", "1-RW02", "2-RW01"]
    assert rw["claim_id"].tolist() == [1, 1, 2]
    assert rw["rw_size"].tolist() == ["small", "large", "medium"]
    assert rw["rw_length"].dtype == np.float64
    assert rw["rw_length"].tolist() == [12.0, 30.0, 8.0]
    assert rw.crs == CRS
    for column in ("is_damaged_by_shaking", "is_evacuated", "is_inundated"):
        assert rw[column].dtype == bool


def test_the_shaking_flag_is_set_by_either_route():
    rw = build_rw_table(walls(), wall_states(), wall_flags()).set_index("rw_id")
    # A flat-land wall the shaking step replaced.
    assert rw.loc["1-RW01", "is_damaged_by_shaking"]
    # A flat-land wall it left standing, with no outcome to say otherwise.
    assert not rw.loc["1-RW02", "is_damaged_by_shaking"]
    # A sloping wall the shaking step never saw, failed with its polygon.
    assert rw.loc["2-RW01", "is_damaged_by_shaking"]


def test_the_landslide_flags_are_carried_by_rw_id_not_by_position():
    rw = build_rw_table(walls(), wall_states(), wall_flags()).set_index("rw_id")
    assert rw["is_evacuated"].to_dict() == {
        "1-RW01": False,
        "1-RW02": True,
        "2-RW01": False,
    }
    assert rw["is_inundated"].to_dict() == {
        "1-RW01": True,
        "1-RW02": False,
        "2-RW01": False,
    }


def test_no_damage_states_at_all_leaves_the_shaking_flag_to_the_landslide_step():
    rw = build_rw_table(walls(), wall_states().iloc[:0], wall_flags())
    assert rw["is_damaged_by_shaking"].tolist() == [False, False, True]


def test_a_wall_without_flags_is_refused():
    with pytest.raises(ValueError, match="no landslide flags"):
        build_rw_table(walls(), wall_states(), wall_flags().iloc[:2])


def test_a_damage_state_for_a_wall_not_in_the_population_is_refused():
    states = wall_states()
    states.loc[0, "rw_id"] = "9-RW09"
    with pytest.raises(ValueError, match="not in the population"):
        build_rw_table(walls(), states, wall_flags())


def test_a_repeated_wall_in_the_population_or_the_states_is_refused():
    population = walls()
    population["rw_id"] = "1-RW01"
    with pytest.raises(ValueError, match="duplicated"):
        build_rw_table(population, wall_states(), wall_flags())
    states = wall_states()
    states["rw_id"] = "1-RW01"
    with pytest.raises(ValueError, match="duplicated"):
        build_rw_table(walls(), states, wall_flags())


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
    rw = build_rw_table(walls(), wall_states(), wall_flags())
    heights = beta_wall_height_m(rw["rw_size"].to_numpy())
    assert heights.shape == (3,)
