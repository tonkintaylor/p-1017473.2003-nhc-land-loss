"""Tests for the per-world wall draw, and the step that writes it."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from landloss.domain import constants
from landloss.exposure.rw.population import (
    POPULATION_COLUMNS,
    REQUIRED_COLUMNS,
    attach_rw_ids,
    draw_wall_population,
)
from landloss.exposure.rw.wall_probability import PROBABILITY_COLUMNS
from landloss.hazard.realisation import realisation_seed
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_population as script,
)

CRS = constants.DEFAULT_CRS
X0, Y0 = 1_750_000.0, 5_424_000.0

# The columns gen_wall_population.py writes, section 3.7 of the contract.
OUTPUT_COLUMNS = (
    "rw_id",
    "claim_id",
    "wall_line_id",
    "world_id",
    "size_class",
    "initial_condition",
    "height_m",
    "length_m",
    "wall_position",
    "is_flatland",
    "source",
    "material",
    "geometry",
)


def rng(world_id=0):
    return realisation_seed(constants.EXPOSURE_BASE_SEED, world_id, "exposure")


def probabilities(
    n=1,
    *,
    p_wall=0.5,
    p_poor=0.5,
    claim_id="C-1",
    face_height_m=2.0,
    y=0.0,
    first_id=1,
):
    """A wall probability table with every column the draw reads, n equal rows."""
    return gpd.GeoDataFrame(
        {
            "wall_line_id": [f"WL{first_id + i:07d}" for i in range(n)],
            "source": ["terrain_break"] * n,
            "is_mapped_wall": [False] * n,
            "claim_id": [claim_id] * n,
            "face_height_m": np.full(n, face_height_m, dtype=float),
            "size_class": ["medium"] * n,
            "wall_position": ["fill"] * n,
            "is_flatland": [False] * n,
            "ground_id": ["GM0000001"] * n,
            "material": ["fill"] * n,
            "modification": ["fill"] * n,
            "is_rock_cut": [False] * n,
            "slope_degrees": np.full(n, 20.0),
            "aspect_degrees": np.full(n, 180.0),
            "dwelling_age_decade": pd.array([pd.NA] * n, dtype="Int64"),
            "length_m": np.full(n, 10.0),
            "p_wall": np.full(n, p_wall, dtype=float),
            "p_wall_basis": ["source_prior"] * n,
            "p_poor": np.full(n, p_poor, dtype=float),
            "p_poor_basis": ["default"] * n,
        },
        geometry=[
            LineString([(X0 + 20 * i, Y0 + y), (X0 + 20 * i + 10, Y0 + y)])
            for i in range(n)
        ],
        crs=CRS,
    )


def stacked(*frames):
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=CRS)


# --- the draw -----------------------------------------------------------------


def test_a_line_at_probability_one_always_draws_and_at_zero_never():
    table = stacked(probabilities(n=50, p_wall=1.0), probabilities(n=50, p_wall=0.0))
    walls = draw_wall_population(table, rng())
    assert len(walls) == 50
    assert walls["wall_line_id"].tolist() == table["wall_line_id"].iloc[:50].tolist()


def test_the_share_drawn_tracks_the_probability():
    table = probabilities(n=4000, p_wall=0.3)
    walls = draw_wall_population(table, rng())
    assert abs(len(walls) / len(table) - 0.3) < 0.03


def test_the_condition_follows_its_probability():
    always = draw_wall_population(probabilities(n=20, p_wall=1.0, p_poor=1.0), rng())
    never = draw_wall_population(probabilities(n=20, p_wall=1.0, p_poor=0.0), rng())
    assert (always["initial_condition"] == "poor").all()
    assert (never["initial_condition"] == "modern").all()


def test_the_same_generator_reproduces_and_another_world_differs():
    table = probabilities(n=400)
    first = draw_wall_population(table, rng())
    second = draw_wall_population(table, rng())
    other = draw_wall_population(table, rng(world_id=1))
    assert first["wall_line_id"].tolist() == second["wall_line_id"].tolist()
    assert first["initial_condition"].tolist() == second["initial_condition"].tolist()
    assert first["wall_line_id"].tolist() != other["wall_line_id"].tolist()


def test_a_line_drawn_earlier_does_not_depend_on_lines_added_after_it():
    short = probabilities(n=100)
    longer = stacked(short, probabilities(n=100))
    first = draw_wall_population(short, rng())
    second = draw_wall_population(longer, rng())
    head = second.iloc[: len(first)]
    assert head["wall_line_id"].tolist() == first["wall_line_id"].tolist()
    assert head["initial_condition"].tolist() == first["initial_condition"].tolist()


def test_a_wall_is_the_line_that_drew_it():
    table = probabilities(n=3, p_wall=1.0, face_height_m=1.7)
    walls = draw_wall_population(table, rng())
    assert walls.columns.tolist() == list(POPULATION_COLUMNS)
    assert walls["height_m"].tolist() == [1.7] * 3
    assert walls["size_class"].tolist() == ["medium"] * 3
    assert walls["length_m"].tolist() == [10.0] * 3
    assert walls.geometry.geom_equals(table.geometry).all()
    assert walls.crs == CRS
    assert walls.index.tolist() == [0, 1, 2]


def test_a_line_with_no_probability_draws_nothing():
    table = probabilities(n=10, p_wall=np.nan)
    assert draw_wall_population(table, rng()).empty


def test_no_lines_gives_an_empty_population_with_the_columns():
    walls = draw_wall_population(probabilities(n=0), rng())
    assert walls.empty
    assert walls.columns.tolist() == list(POPULATION_COLUMNS)


def test_a_claimless_line_is_drawn_and_left_for_the_script_to_drop():
    walls = draw_wall_population(probabilities(n=2, p_wall=1.0, claim_id=None), rng())
    assert len(walls) == 2
    assert walls["claim_id"].isna().all()


def test_a_missing_column_is_refused():
    assert set(PROBABILITY_COLUMNS) & set(REQUIRED_COLUMNS) == {"p_wall", "p_poor"}
    with pytest.raises(ValueError, match="p_poor"):
        draw_wall_population(probabilities().drop(columns=["p_poor"]), rng())


# --- every drawn wall, with the minted ids joined back --------------------------


def test_attach_rw_ids_keeps_every_drawn_wall_and_nulls_the_uninsured():
    drawn = draw_wall_population(probabilities(n=3, p_wall=1.0), rng())
    insured = drawn.iloc[[2, 0]].copy()
    insured.insert(0, "rw_id", ["C-1-RW02", "C-1-RW01"])
    out = attach_rw_ids(drawn, insured)
    assert out.columns.tolist() == ["rw_id", *POPULATION_COLUMNS]
    assert out["wall_line_id"].tolist() == drawn["wall_line_id"].tolist()
    assert out["rw_id"].tolist() == ["C-1-RW01", None, "C-1-RW02"]
    assert out["rw_id"].dtype == object
    assert out.crs == CRS


def test_attach_rw_ids_with_nothing_insured_gives_every_wall_a_null_id():
    drawn = draw_wall_population(probabilities(n=2, p_wall=1.0), rng())
    insured = drawn.iloc[[]].copy()
    insured.insert(0, "rw_id", pd.Series([], dtype=object))
    out = attach_rw_ids(drawn, insured)
    assert len(out) == 2
    assert out["rw_id"].isna().all()


def test_attach_rw_ids_refuses_a_population_naming_an_undrawn_line():
    drawn = draw_wall_population(probabilities(n=2, p_wall=1.0), rng())
    stranger = drawn.iloc[[0]].copy()
    stranger["wall_line_id"] = "WL9999999"
    stranger.insert(0, "rw_id", ["C-1-RW01"])
    with pytest.raises(ValueError, match="drew no wall"):
        attach_rw_ids(drawn, stranger)
    repeated = stacked(drawn, drawn)
    with pytest.raises(ValueError, match="repeats wall_line_id"):
        attach_rw_ids(repeated, drawn.iloc[[]].assign(rw_id=None))


# --- the script ---------------------------------------------------------------


@pytest.fixture
def redirected_script(tmp_path, monkeypatch):
    """Point gen_wall_population.py at synthetic probabilities and insured land.

    Claim A has two certain lines on its land and one 50 m away; claim B has
    one certain line; a fourth line has no claim.
    """
    table = stacked(
        probabilities(n=2, p_wall=1.0, claim_id="A"),
        probabilities(n=1, p_wall=1.0, claim_id="A", y=50.0, first_id=3),
        probabilities(n=1, p_wall=1.0, claim_id="B", first_id=4),
        probabilities(n=1, p_wall=1.0, claim_id=None, first_id=5),
    )
    insured = gpd.GeoDataFrame(
        {"claim_id": ["A", "B"]},
        geometry=[
            box(X0 - 5, Y0 - 5, X0 + 35, Y0 + 5),
            box(X0 - 5, Y0 - 5, X0 + 15, Y0 + 5),
        ],
        crs=CRS,
    )
    table_file = tmp_path / "wall-probability-pilot.geoparquet"
    insured_file = tmp_path / "insured-land-pilot.geoparquet"
    table.to_parquet(table_file)
    insured.to_parquet(insured_file)
    monkeypatch.setattr(script, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(script, "wall_probability_path", lambda *, pilot: table_file)
    monkeypatch.setattr(script, "insured_land_path", lambda *, pilot: insured_file)
    return table


def test_gen_wall_population_main_writes_one_file_per_world(
    tmp_path, redirected_script
):
    script.main(pilot=True, world_ids=[0, 1])

    for world_id in (0, 1):
        out_path = script.wall_population_path(world_id, pilot=True)
        assert (
            out_path
            == tmp_path
            / "exposure"
            / f"wall-population-w{world_id:03d}-pilot.geoparquet"
        )
        written = gpd.read_parquet(out_path)
        assert written.columns.tolist() == list(OUTPUT_COLUMNS)
        # The claimless line and the line off A's insured land are dropped.
        assert written["rw_id"].tolist() == ["A-RW01", "A-RW02", "B-RW01"]
        assert (written["world_id"] == world_id).all()
        assert written["world_id"].dtype == np.int64
        assert written["wall_line_id"].isin(redirected_script["wall_line_id"]).all()
        assert set(written["initial_condition"]) <= {"modern", "poor"}
        assert written.crs == CRS


def test_gen_wall_population_main_reproduces_a_world(redirected_script):
    script.main(pilot=True, world_ids=[0])
    one = gpd.read_parquet(script.wall_population_path(0, pilot=True))
    script.main(pilot=True, world_ids=[0])
    again = gpd.read_parquet(script.wall_population_path(0, pilot=True))
    assert one["initial_condition"].tolist() == again["initial_condition"].tolist()
    assert one["rw_id"].tolist() == again["rw_id"].tolist()


def test_drawn_walls_path_names_the_world_and_the_extent():
    assert script.drawn_walls_path(3, pilot=True).name == (
        "drawn-walls-w003-pilot.geoparquet"
    )
    assert script.drawn_walls_path(12, pilot=False).name == (
        "drawn-walls-w012.geoparquet"
    )


def test_gen_wall_population_main_writes_every_drawn_wall_before_the_filters(
    tmp_path, redirected_script
):
    script.main(pilot=True, world_ids=[0, 1])

    for world_id in (0, 1):
        drawn_path = script.drawn_walls_path(world_id, pilot=True)
        assert drawn_path == (
            tmp_path / "exposure" / f"drawn-walls-w{world_id:03d}-pilot.geoparquet"
        )
        drawn = gpd.read_parquet(drawn_path)
        insured = gpd.read_parquet(script.wall_population_path(world_id, pilot=True))
        assert drawn.columns.tolist() == list(OUTPUT_COLUMNS)
        # Every certain line drew, in line order, one row per line.
        assert (
            drawn["wall_line_id"].tolist() == redirected_script["wall_line_id"].tolist()
        )
        assert drawn["wall_line_id"].is_unique
        # The claimless line and the line off A's insured land carry no rw_id.
        assert drawn["rw_id"].isna().tolist() == [False, False, True, False, True]
        assert drawn["rw_id"].dropna().tolist() == ["A-RW01", "A-RW02", "B-RW01"]
        assert drawn["claim_id"].isna().tolist() == [False] * 4 + [True]
        assert drawn["claim_id"].dropna().tolist() == ["A", "A", "A", "B"]
        assert (drawn["world_id"] == world_id).all()
        assert drawn["world_id"].dtype == np.int64
        assert drawn.crs == CRS
        # The insured rows agree with the population file wall for wall.
        joined = insured.merge(
            drawn, on="wall_line_id", suffixes=("", "_drawn"), validate="one_to_one"
        )
        assert len(joined) == len(insured)
        for column in ("rw_id", "initial_condition", "size_class", "height_m"):
            assert joined[column].tolist() == joined[f"{column}_drawn"].tolist()
        assert set(drawn["initial_condition"]) <= {"modern", "poor"}
        assert drawn["is_flatland"].dtype == bool
