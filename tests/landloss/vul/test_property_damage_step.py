"""Vul step 10 end to end on synthetic inputs, with no disk.

The step reads twelve files per world and earthquake: the insured land, the
world's wall population, the liquefaction and landslide land damage, the wall
damage states and wall landslide flags, the structure damage states and the
crossing landslide flags, and, for a slip's new wall, the candidate stretches,
wall probabilities, urban slope model and combined realisation. Here each is a
small hand-built frame written where the step looks for it (each producing
step's work directory pointed at ``tmp_path``), so the test is of what the step
writes -- the four files, their columns and the rows they hold -- and not of the
data it normally reads.
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
    LANDSLIDE_WALL_COLUMNS,
    RW_COLUMNS,
)
from landloss.vul.landslide.flags import WALL_DAMAGE_COLUMNS
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population import (
    gen_crossing_population,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    gen_insured_land,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_population,
    gen_wall_probability,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import (
    gen_urban_slope_fragility,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
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
            "area_m2": [400.0, 900.0],
            "property_area_m2": [600.0, 900.0],
            "footprint_area_m2": [120.0, 200.0],
            "suburb_locality": ["Kelburn", "Karori"],
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
            "area_cost_nzd": [1_500.0, 0.0],
            "damaged_area_m2": [180.0, 0.0],
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
            "landslide_footprint_area_m2": [30.0],
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
            "wall_type": "concrete_block",
            "age_bin": "1992_2004",
            "height_m": [0.8, 3.0, 1.5],
            "length_m": [12.0, 30.0, 8.0],
            "wall_position": "fill",
            "is_flatland": [flat for _, flat in WALLS],
            "source": "property_boundary",
            "material": "alluvium",
            "insured_lengths_m": [
                [{"claim_id": rw_id.split("-")[0], "length_m": length}]
                for (rw_id, _), length in zip(WALLS, [12.0, 30.0, 8.0], strict=True)
            ],
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
    flat["pga_g"] = 0.6
    flat["failure_probability"] = [0.9, 0.1]
    flat["damage_state"] = ["replace", "no damage"]
    return flat


def insured_stretches(world_id=0):
    """Exposure rw step 6's stretches: each wall is one claim's, whole."""
    walls = wall_population(world_id)
    return gpd.GeoDataFrame(
        {
            "wall_line_id": walls["wall_line_id"],
            "rw_id": walls["rw_id"],
            "claim_id": walls["claim_id"],
            "length_m": walls.geometry.length,
            "world_id": world_id,
        },
        geometry=walls.geometry,
        crs=CRS,
    )


def wall_landslide_flags(world_id=0, realisation_id=0):
    """The wall landslide step's file: the sloping wall failed with its polygon.

    The standing flat-land wall is clipped over its first 10 m by evacuated
    ground.
    """
    clipped = LineString([(0, 5), (10, 5)])
    lines = [LineString(), clipped, LineString([(100, 0), (108, 0)])]
    flags = pd.DataFrame(
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
            "evacuated_length_m": [0.0, 10.0, 0.0],
            "inundated_length_m": [12.0, 0.0, 0.0],
            "damaged_length_m": [0.0, 10.0, 8.0],
            "damaged_line": lines,
        }
    )
    assert tuple(flags.columns[-4:]) == WALL_DAMAGE_COLUMNS
    return gpd.GeoDataFrame(flags, geometry="damaged_line", crs=CRS)


# The unit each wall stands on, and the claim's stretch of it: one stretch per
# wall, so a failure on none of the walls' units has nothing to build on.
def candidate_stretches():
    """Exposure rw step 6's candidate stretches: the walls' units, drawn or not."""
    walls = wall_population()
    return gpd.GeoDataFrame(
        {
            "wall_line_id": walls["wall_line_id"],
            "claim_id": walls["claim_id"],
            "length_m": walls.geometry.length,
        },
        geometry=walls.geometry,
        crs=CRS,
    )


def wall_probability():
    """The probability table's id and face height: the walls' units' only."""
    walls = wall_population()
    return pd.DataFrame(
        {"wall_line_id": walls["wall_line_id"], "face_height_m": walls["height_m"]}
    )


def urban_slope_model(world_id=0):
    """The model file's slope and unit ids: SP0000001 stands on the sloping wall."""
    return pd.DataFrame(
        {"slope_id": ["SP0000001"], "wall_line_id": ["WL0000003"], "world_id": world_id}
    )


def combined_realisation():
    """The combined realisation with no landslide on any land."""
    return gpd.GeoDataFrame(
        {
            "landslide_id": ["SP0000001"],
            "slope_id": ["SP0000001"],
            "land_class": ["evacuated land"],
        },
        geometry=[box(500, 500, 501, 501)],
        crs=CRS,
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
    hazard = tmp_path / "hazard"
    for module in (
        gen_insured_land,
        gen_wall_population,
        gen_wall_probability,
        gen_crossing_population,
    ):
        monkeypatch.setattr(module, "WORK_DIR", exposure)
    for module in (gen_urban_slope_fragility, gen_urban_slope_realisation):
        monkeypatch.setattr(module, "WORK_DIR", hazard)
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
    hazard.mkdir()

    insured_land().to_parquet(gen_insured_land.insured_land_path(extent="wlg-pilot"))
    candidate_stretches().to_parquet(
        gen_wall_population.candidate_stretches_path(extent="wlg-pilot")
    )
    wall_probability().to_parquet(
        gen_wall_probability.wall_probability_path(extent="wlg-pilot")
    )
    for world_id in (0, 1):
        urban_slope_model(world_id).to_parquet(
            gen_urban_slope_fragility.urban_slope_model_path(
                world_id, extent="wlg-pilot"
            )
        )
        wall_population(world_id).to_parquet(
            gen_wall_population.wall_population_path(world_id, extent="wlg-pilot")
        )
        insured_stretches(world_id).to_parquet(
            gen_wall_population.insured_stretches_path(world_id, extent="wlg-pilot")
        )
        for realisation_id in (0, 1):
            combined_realisation().to_parquet(
                gen_urban_slope_realisation.combined_realisation_path(
                    world_id, realisation_id, extent="wlg-pilot"
                )
            )
            landslide_land_damage(world_id, realisation_id).to_parquet(
                gen_landslide_land_damage.landslide_land_damage_path(
                    world_id, realisation_id, extent="wlg-pilot"
                )
            )
            wall_damage_states(world_id, realisation_id).to_parquet(
                gen_wall_damage_state.wall_damage_state_path(
                    world_id, realisation_id, extent="wlg-pilot"
                )
            )
            wall_landslide_flags(world_id, realisation_id).to_parquet(
                gen_wall_landslide_damage.wall_landslide_damage_path(
                    world_id, realisation_id, extent="wlg-pilot"
                )
            )
            crossing_landslide_flags(world_id, realisation_id).to_parquet(
                gen_crossing_landslide_damage.crossing_landslide_damage_path(
                    world_id, realisation_id, extent="wlg-pilot"
                )
            )
    for realisation_id in (0, 1):
        liq_land_damage(realisation_id).to_parquet(
            gen_liq_land_damage.liq_land_damage_path(realisation_id, extent="wlg-pilot")
        )
        structure_damage_states(realisation_id).to_parquet(
            gen_structure_damage_state.structure_damage_state_path(
                realisation_id, extent="wlg-pilot"
            )
        )


def read_table(table, world_id, realisation_id):
    return gpd.read_parquet(
        step.world_loss_input_path(table, world_id, realisation_id, extent="wlg-pilot")
    )


# --- path function --------------------------------------------------------------


def test_the_path_names_the_table_the_world_the_realisation_and_the_extent():
    assert (
        step.world_loss_input_path("rw", 0, 3, extent="wlg-pilot").name
        == "loss-input-rw-w000-r003-pilot.geoparquet"
    )
    assert (
        step.world_loss_input_path("land", 12, 1, extent="full").name
        == "loss-input-land-w012-r001.geoparquet"
    )
    assert (
        step.world_loss_input_path("rw", 0, 0, extent="wlg-pilot").parent
        == step.WORK_DIR
    )


def test_an_unknown_table_is_refused():
    with pytest.raises(ValueError, match="unknown loss table"):
        step.world_loss_input_path("walls", 0, 0, extent="wlg-pilot")


# --- end to end ------------------------------------------------------------------


def test_every_table_carries_the_contract_columns_after_the_two_ids(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])

    land = read_table("land", 0, 0)
    rw = read_table("rw", 0, 0)
    culverts = read_table("culverts", 0, 0)
    bridges = read_table("bridges", 0, 0)

    ids = ["realisation_id", "world_id"]
    assert list(land.columns) == [*ids, *LAND_COLUMNS, "dwelling_count", "geometry"]
    assert list(rw.columns) == [
        *ids,
        *RW_COLUMNS,
        "parent_rw_id",
        "rw_damaged_length",
        "geometry",
    ]
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
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
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
    # Shaking takes the whole wall; the clipped wall only its 10 m of 30 m; the
    # inundated wall that stands has none.
    assert rw["rw_damaged_length"].tolist() == pytest.approx([12.0, 10.0, 8.0])


def test_the_land_table_is_spined_on_the_insured_land(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
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


def test_the_liquefaction_cost_handed_on_is_priced_from_the_ground_lost(
    synthetic_run,
):
    """Loss settles the per-m2 cost, not the per-state percentile lookup."""
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    land = read_table("land", 0, 0).set_index("land_id")

    assert land.loc["C01-L01", "Liq_LD_cost_excl_gst_nzd"] == pytest.approx(1_500.0)


def test_the_crossings_split_into_culverts_and_bridges(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    culverts = read_table("culverts", 0, 0)
    bridges = read_table("bridges", 0, 0)

    assert culverts["culvert_id"].tolist() == ["C01-X01", "C02-X01"]
    assert culverts["is_damaged"].tolist() == [True, False]
    assert culverts["is_inundated"].tolist() == [False, True]
    assert bridges["bridge_id"].tolist() == ["C01-X02"]
    assert bridges["is_damaged_by_shaking"].tolist() == [True]
    assert bridges["is_inundated"].tolist() == [True]


def test_one_set_of_files_is_written_per_world_and_realisation(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0, 1], realisation_ids=[0, 1])
    for world_id in (0, 1):
        for realisation_id in (0, 1):
            for table in ("land", "rw", "culverts", "bridges"):
                written = read_table(table, world_id, realisation_id)
                assert (written["world_id"] == world_id).all()
                assert (written["realisation_id"] == realisation_id).all()


def test_a_wall_without_landslide_flags_stops_the_run(synthetic_run):
    short = wall_landslide_flags().iloc[:2]
    short.to_parquet(
        gen_wall_landslide_damage.wall_landslide_damage_path(0, 0, extent="wlg-pilot")
    )
    with pytest.raises(ValueError, match="no landslide flags"):
        step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])


def test_a_wall_with_insured_stretches_is_split_at_their_lengths(
    synthetic_run, monkeypatch
):
    walls = wall_population(0)
    walls["insured_lengths_m"] = [
        [{"claim_id": "C01", "length_m": 12.0}],
        [
            {"claim_id": "C01", "length_m": 20.0},
            {"claim_id": "C02", "length_m": 5.0},
        ],
        [],
    ]
    walls.to_parquet(gen_wall_population.wall_population_path(0, extent="wlg-pilot"))

    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])

    rw = read_table("rw", 0, 0)
    assert rw["rw_id"].tolist() == ["C01-RW01", "C01-RW02-P1", "C01-RW02-P2"]
    assert rw["claim_id"].tolist() == ["C01", "C01", "C02"]
    assert rw["rw_length"].tolist() == pytest.approx([12.0, 20.0, 5.0])
    assert rw["parent_rw_id"].tolist() == ["C01-RW01", "C01-RW02", "C01-RW02"]
    # The clipped wall's damage is on C01's stretch only: C02's piece has none,
    # so it is undamaged and loses its flag.
    assert rw["rw_damaged_length"].tolist() == pytest.approx([12.0, 10.0, 0.0])
    assert rw["is_evacuated"].tolist() == [False, True, False]


# --- a slip's new wall on the mapped wall (section 4) ----------------------------

FAILURES = [
    # id, wall it failed with, slope id (None: a large-model landslide), unit.
    ("SP0000009", None, "SP0000009", "WLX1"),
    ("SP0000010", None, "SP0000010", "WLX1"),
    ("LG0000001", None, None, None),
    ("SP0000011", "C01-RW02", "SP0000011", "WLX1"),
    ("SP0000012", None, "SP0000012", None),
    ("SP0000013", None, "SP0000013", "WLX2"),
    ("SP0000014", None, "SP0000014", "WLX3"),
]
# Each failure's evacuated ground on C01's land: the first two overlap along
# the unit's stretch; the last is nowhere near its unit's stretch.
EVACUATED_GROUND = [
    box(5, 9, 9, 12),
    box(8, 9, 12, 12),
    box(1, 1, 3, 3),
    box(1, 1, 3, 3),
    box(1, 1, 3, 3),
    box(1, 1, 3, 3),
    box(0, 0, 1, 1),
]


@pytest.fixture
def mapped_run(synthetic_run):
    """The synthetic run with seven failures on C01 and the units they stand on."""
    land = landslide_land_damage()
    ids = [failure[0] for failure in FAILURES]
    for column, values in {
        "landslide_ids": ids,
        "landslide_rw_ids": [failure[1] for failure in FAILURES],
        "landslide_areas": [12.0] * len(ids),
        "landslide_inundated_areas": [0.0] * len(ids),
        "landslide_inundated_depths": [None] * len(ids),
        "landslide_evacuated_areas": [12.0] * len(ids),
    }.items():
        land[column] = [values]
    stretches = pd.concat(
        [
            candidate_stretches(),
            gpd.GeoDataFrame(
                {
                    "wall_line_id": ["WLX1", "WLX2", "WLX3"],
                    "claim_id": ["C01", "C02", "C01"],
                    "length_m": [20.0, 20.0, 20.0],
                },
                geometry=[
                    LineString([(0, 10), (20, 10)]),
                    LineString([(100, 10), (120, 10)]),
                    LineString([(0, 15), (20, 15)]),
                ],
                crs=CRS,
            ),
        ],
        ignore_index=True,
    )
    stretches.to_parquet(
        gen_wall_population.candidate_stretches_path(extent="wlg-pilot")
    )
    pd.concat(
        [
            wall_probability(),
            pd.DataFrame({"wall_line_id": ["WLX1", "WLX2", "WLX3"]}).assign(
                face_height_m=[1.6, 2.0, 1.2]
            ),
        ]
    ).to_parquet(gen_wall_probability.wall_probability_path(extent="wlg-pilot"))
    pd.DataFrame(
        {
            "slope_id": [failure[2] for failure in FAILURES if failure[2]],
            "wall_line_id": [failure[3] for failure in FAILURES if failure[2]],
        }
    ).to_parquet(
        gen_urban_slope_fragility.urban_slope_model_path(0, extent="wlg-pilot")
    )
    gpd.GeoDataFrame(
        {
            "landslide_id": ids,
            "slope_id": [failure[2] for failure in FAILURES],
            "land_class": "evacuated land",
        },
        geometry=EVACUATED_GROUND,
        crs=CRS,
    ).to_parquet(
        gen_urban_slope_realisation.combined_realisation_path(0, 0, extent="wlg-pilot")
    )
    land.to_parquet(
        gen_landslide_land_damage.landslide_land_damage_path(0, 0, extent="wlg-pilot")
    )


def test_a_failure_no_damaged_wall_holds_takes_its_mapped_walls_height_and_stretch(
    mapped_run,
):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    land = read_table("land", 0, 0).set_index("land_id").loc["C01-L01"]

    sources, lengths, heights = (
        land["landslide_wall_sources"],
        land["landslide_wall_lengths"],
        land["landslide_wall_heights"],
    )
    # Two failures on one unit and claim share one wall: the union of their cut
    # stretches (3 to 14 m of the unit's line) on the first, none on the other.
    assert sources[:2].tolist() == ["mapped wall", "mapped wall"]
    assert lengths[0] == pytest.approx(11.0)
    assert lengths[1] == pytest.approx(0.0)
    assert heights[:2].tolist() == pytest.approx([1.6, 1.6])
    # A large-model landslide, one a damaged wall holds, a polygon on no unit, a
    # unit with no stretch on the claim, and a stretch under a metre alongside.
    assert sources[2:].tolist() == ["slip"] * 5
    assert all(value is None or np.isnan(value) for value in lengths[2:])
    assert all(value is None or np.isnan(value) for value in heights[2:])


def test_the_per_failure_wall_lists_stay_aligned_with_the_landslide_ids(mapped_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    land = read_table("land", 0, 0).set_index("land_id").loc["C01-L01"]

    for column in LANDSLIDE_WALL_COLUMNS:
        assert len(land[column]) == len(land["landslide_ids"]) == len(FAILURES)


def test_a_land_table_without_the_failure_lists_gets_no_wall_lists(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    land = read_table("land", 0, 0)

    assert not set(LANDSLIDE_WALL_COLUMNS) & set(land.columns)
