"""Vul step 10 end to end on synthetic inputs, with no disk.

The step reads eight files per world and earthquake: the insured land, the
world's wall population, the liquefaction and landslide land damage, the wall
damage states and wall landslide flags, the structure damage states and the
crossing landslide flags. Here each is a small hand-built frame written where
the step looks for it (each producing step's work directory pointed at
``tmp_path``), so the test is of what the step writes -- the four files, their
columns and the rows they hold -- and not of the data it normally reads.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from landloss.domain import constants
from landloss.domain.loss_contract import (
    BRIDGE_COLUMNS,
    CULVERT_COLUMNS,
    LAND_COLUMNS,
    RW_COLUMNS,
)
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population import (
    gen_crossing_population,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    gen_insured_land,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import gen_wall_population
from scripts.landloss.vul.landslide.culverts_bridges.steps.s11_crossing_landslide_damage import (  # noqa: E501
    gen_crossing_landslide_damage,
)
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import (
    gen_landslide_land_damage,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import (
    gen_wall_landslide_damage,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    gen_liq_land_damage,
)
from scripts.landloss.vul.shaking.culverts_bridges.steps.s9_structure_damage_state import (  # noqa: E501
    gen_structure_damage_state,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import (
    gen_wall_damage_state,
)
from scripts.landloss.vul.steps.s10_property_damage import (
    gen_property_damage as step,
)

CRS = constants.DEFAULT_CRS


def insured_land():
    return gpd.GeoDataFrame(
        {
            "land_id": ["C01-L01", "C02-L01"],
            "claim_id": ["C01", "C02"],
            "land_rate_excl_gst_nzd_per_m2": [500.0, 700.0],
            "land_rate_incl_gst_nzd_per_m2": [575.0, 805.0],
            "area_m2": [400.0, 900.0],
            "dwelling_count": [1, 2],
        },
        geometry=[box(0, 0, 20, 20), box(100, 0, 130, 30)],
        crs=CRS,
    )


def liq_land_damage(realisation_id=0):
    return pd.DataFrame(
        {
            "realisation_id": realisation_id,
            "land_id": ["C01-L01", "C02-L01"],
            "claim_id": ["C01", "C02"],
            "ld_state": [3, None],
            "cost_nzd": [12_000.0, 0.0],
            "damaged_area_m2": [250.0, 0.0],
        }
    )


def landslide_land_damage(world_id=0, realisation_id=0):
    return pd.DataFrame(
        {
            "realisation_id": [realisation_id],
            "world_id": [world_id],
            "land_id": ["C01-L01"],
            "claim_id": ["C01"],
            "evacuated_area_m2": [100.0],
            "inundated_area_m2": [150.0],
            "landslide_area_m2": [200.0],
            "evacuated_depth_m": [2.0],
            "inundated_depth_m": [1.5],
            "cause_evacuated": [str(constants.Cause.LANDSLIDE_EVACUATED)],
            "cause_inundated": [str(constants.Cause.LANDSLIDE_INUNDATED)],
        }
    )


# rw_id, flat land: two flat-land walls on the first claim, one sloping wall
# on the second.
WALLS = [("C01-RW01", True), ("C01-RW02", True), ("C02-RW01", False)]


def wall_population(world_id=0):
    return gpd.GeoDataFrame(
        {
            "rw_id": [rw_id for rw_id, _ in WALLS],
            "claim_id": [rw_id.split("-")[0] for rw_id, _ in WALLS],
            "wall_line_id": [f"WL{i + 1:07d}" for i in range(len(WALLS))],
            "world_id": world_id,
            "size_class": ["small", "large", "medium"],
            "initial_condition": "modern",
            "height_m": [0.8, 3.0, 1.5],
            "length_m": [12.0, 30.0, 8.0],
            "wall_position": "fill",
            "is_flatland": [flat for _, flat in WALLS],
            "source": "property_boundary",
            "material": "alluvium",
        },
        geometry=[
            LineString([(0, 0), (12, 0)]),
            LineString([(0, 5), (30, 5)]),
            LineString([(100, 0), (108, 0)]),
        ],
        crs=CRS,
    )


def wall_damage_states(world_id=0, realisation_id=0):
    """The shaking step's file: flat-land walls only, the first one replaced."""
    walls = wall_population(world_id)
    flat = walls[walls["is_flatland"]].copy()
    flat.insert(0, "realisation_id", realisation_id)
    flat["pgv_m_s"] = 0.6
    flat["failure_probability"] = [0.9, 0.1]
    flat["damage_state"] = ["replace", "no damage"]
    return flat


def wall_landslide_flags(world_id=0, realisation_id=0):
    """The wall landslide step's file: the sloping wall failed with its polygon."""
    return pd.DataFrame(
        {
            "realisation_id": realisation_id,
            "world_id": world_id,
            "rw_id": [rw_id for rw_id, _ in WALLS],
            "claim_id": [rw_id.split("-")[0] for rw_id, _ in WALLS],
            "slope_id": [None, None, "SP0000001"],
            "outcome": [None, None, "failed_with_polygon"],
            "is_damaged_by_shaking": [False, False, True],
            "is_evacuated": [False, True, False],
            "is_inundated": [True, False, False],
        }
    )


def structure_damage_states(realisation_id=0):
    return gpd.GeoDataFrame(
        {
            "realisation_id": realisation_id,
            "crossing_id": ["C01-X01", "C01-X02", "C02-X01"],
            "claim_id": ["C01", "C01", "C02"],
            "asset": ["culvert", "bridge", "culvert"],
            "pga_g": 0.5,
            "failure_probability": [0.9, 0.9, 0.1],
            "damage_state": ["replace", "replace", "no damage"],
        },
        geometry=[Point(1, 1), Point(2, 2), Point(110, 10)],
        crs=CRS,
    )


def crossing_landslide_flags(world_id=0, realisation_id=0):
    return pd.DataFrame(
        {
            "realisation_id": realisation_id,
            "world_id": world_id,
            "crossing_id": ["C01-X01", "C01-X02", "C02-X01"],
            "claim_id": ["C01", "C01", "C02"],
            "is_evacuated": [True, False, False],
            "is_inundated": [False, True, True],
        }
    )


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    """Every input the step reads, written where it looks for it."""
    exposure = tmp_path / "exposure"
    vul = tmp_path / "vul"
    for module in (gen_insured_land, gen_wall_population, gen_crossing_population):
        monkeypatch.setattr(module, "WORK_DIR", exposure)
    for module in (
        gen_liq_land_damage,
        gen_landslide_land_damage,
        gen_wall_damage_state,
        gen_wall_landslide_damage,
        gen_structure_damage_state,
        gen_crossing_landslide_damage,
        step,
    ):
        monkeypatch.setattr(module, "WORK_DIR", vul)
    exposure.mkdir()
    vul.mkdir()

    insured_land().to_parquet(gen_insured_land.insured_land_path(pilot=True))
    for world_id in (0, 1):
        wall_population(world_id).to_parquet(
            gen_wall_population.wall_population_path(world_id, pilot=True)
        )
        for realisation_id in (0, 1):
            landslide_land_damage(world_id, realisation_id).to_parquet(
                gen_landslide_land_damage.landslide_land_damage_path(
                    world_id, realisation_id, pilot=True
                )
            )
            wall_damage_states(world_id, realisation_id).to_parquet(
                gen_wall_damage_state.wall_damage_state_path(
                    world_id, realisation_id, pilot=True
                )
            )
            wall_landslide_flags(world_id, realisation_id).to_parquet(
                gen_wall_landslide_damage.wall_landslide_damage_path(
                    world_id, realisation_id, pilot=True
                )
            )
            crossing_landslide_flags(world_id, realisation_id).to_parquet(
                gen_crossing_landslide_damage.crossing_landslide_damage_path(
                    world_id, realisation_id, pilot=True
                )
            )
    for realisation_id in (0, 1):
        liq_land_damage(realisation_id).to_parquet(
            gen_liq_land_damage.liq_land_damage_path(realisation_id, pilot=True)
        )
        structure_damage_states(realisation_id).to_parquet(
            gen_structure_damage_state.structure_damage_state_path(
                realisation_id, pilot=True
            )
        )


def read_table(table, world_id, realisation_id):
    return gpd.read_parquet(
        step.world_loss_input_path(table, world_id, realisation_id, pilot=True)
    )


# --- path function --------------------------------------------------------------


def test_the_path_names_the_table_the_world_the_realisation_and_the_extent():
    assert (
        step.world_loss_input_path("rw", 0, 3, pilot=True).name
        == "loss-input-rw-w000-r003-pilot.geoparquet"
    )
    assert (
        step.world_loss_input_path("land", 12, 1, pilot=False).name
        == "loss-input-land-w012-r001.geoparquet"
    )
    assert step.world_loss_input_path("rw", 0, 0, pilot=True).parent == step.WORK_DIR


def test_an_unknown_table_is_refused():
    with pytest.raises(ValueError, match="unknown loss table"):
        step.world_loss_input_path("walls", 0, 0, pilot=True)


@pytest.mark.parametrize("pilot", [True, False])
@pytest.mark.parametrize("table", ["land", "rw", "culverts", "bridges"])
@pytest.mark.parametrize("realisation_id", [0, 7])
def test_the_deprecated_path_resolves_world_0(table, realisation_id, pilot):
    # The loss module's five callers pass no world (contract decision 37).
    assert step.loss_input_path(
        table, realisation_id, pilot=pilot
    ) == step.world_loss_input_path(table, 0, realisation_id, pilot=pilot)


def test_the_deprecated_path_refuses_an_unknown_table():
    with pytest.raises(ValueError, match="unknown loss table"):
        step.loss_input_path("walls", 0, pilot=True)


def test_the_deprecated_path_reads_the_file_world_0_writes(synthetic_run):
    step.main(pilot=True, world_ids=[0, 1], realisation_ids=[1])

    for table in ("land", "rw", "culverts", "bridges"):
        written = gpd.read_parquet(step.loss_input_path(table, 1, pilot=True))
        assert (written["world_id"] == 0).all()
        assert (written["realisation_id"] == 1).all()


# --- end to end ------------------------------------------------------------------


def test_every_table_carries_the_contract_columns_after_the_two_ids(synthetic_run):
    step.main(pilot=True, world_ids=[0], realisation_ids=[0])

    land = read_table("land", 0, 0)
    rw = read_table("rw", 0, 0)
    culverts = read_table("culverts", 0, 0)
    bridges = read_table("bridges", 0, 0)

    ids = ["realisation_id", "world_id"]
    assert list(land.columns) == [*ids, *LAND_COLUMNS, "dwelling_count", "geometry"]
    assert list(rw.columns) == [*ids, *RW_COLUMNS, "geometry"]
    assert list(culverts.columns) == [
        *ids,
        *CULVERT_COLUMNS,
        "is_evacuated",
        "geometry",
    ]
    assert list(bridges.columns) == [*ids, *BRIDGE_COLUMNS, "geometry"]
    for table in (land, rw, culverts, bridges):
        assert (table["realisation_id"] == 0).all()
        assert (table["world_id"] == 0).all()
        assert table.crs == CRS


def test_the_rw_table_holds_every_wall_with_the_shaking_flag_from_either_route(
    synthetic_run,
):
    step.main(pilot=True, world_ids=[0], realisation_ids=[0])
    rw = read_table("rw", 0, 0).set_index("rw_id")

    # Flat-land and sloping walls alike, in population order.
    assert rw.index.tolist() == [rw_id for rw_id, _ in WALLS]
    assert rw["rw_size"].tolist() == ["small", "large", "medium"]
    assert rw["rw_length"].tolist() == [12.0, 30.0, 8.0]
    # Replaced by the shaking step; standing; failed with its polygon.
    assert rw["is_damaged_by_shaking"].tolist() == [True, False, True]
    assert rw["is_evacuated"].tolist() == [False, True, False]
    assert rw["is_inundated"].tolist() == [True, False, False]
    assert rw.geometry.geom_type.eq("LineString").all()


def test_the_land_table_is_spined_on_the_insured_land(synthetic_run):
    step.main(pilot=True, world_ids=[0], realisation_ids=[0])
    land = read_table("land", 0, 0).set_index("land_id")

    assert land.index.tolist() == ["C01-L01", "C02-L01"]
    reached = land.loc["C01-L01"]
    assert reached["Liq_LD_state"] == 3
    assert reached["land_slide_total_insured_land_area"] == pytest.approx(200.0)
    assert reached["evacuated_area"] == pytest.approx(100.0)
    assert reached["inundated_mean_depth"] == pytest.approx(1.5)
    unreached = land.loc["C02-L01"]
    assert pd.isna(unreached["Liq_LD_state"])
    assert unreached["land_slide_total_insured_land_area"] == 0.0
    assert np.isnan(unreached["inundated_mean_depth"])


def test_the_crossings_split_into_culverts_and_bridges(synthetic_run):
    step.main(pilot=True, world_ids=[0], realisation_ids=[0])
    culverts = read_table("culverts", 0, 0)
    bridges = read_table("bridges", 0, 0)

    assert culverts["culvert_id"].tolist() == ["C01-X01", "C02-X01"]
    assert culverts["is_damaged"].tolist() == [True, False]
    assert culverts["is_inundated"].tolist() == [False, True]
    assert bridges["bridge_id"].tolist() == ["C01-X02"]
    assert bridges["is_damaged_by_shaking"].tolist() == [True]
    assert bridges["is_inundated"].tolist() == [True]


def test_one_set_of_files_is_written_per_world_and_realisation(synthetic_run):
    step.main(pilot=True, world_ids=[0, 1], realisation_ids=[0, 1])
    for world_id in (0, 1):
        for realisation_id in (0, 1):
            for table in ("land", "rw", "culverts", "bridges"):
                written = read_table(table, world_id, realisation_id)
                assert (written["world_id"] == world_id).all()
                assert (written["realisation_id"] == realisation_id).all()


def test_a_wall_without_landslide_flags_stops_the_run(synthetic_run):
    short = wall_landslide_flags().iloc[:2]
    short.to_parquet(
        gen_wall_landslide_damage.wall_landslide_damage_path(0, 0, pilot=True)
    )
    with pytest.raises(ValueError, match="no landslide flags"):
        step.main(pilot=True, world_ids=[0], realisation_ids=[0])
