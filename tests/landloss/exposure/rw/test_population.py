"""Tests for the per-world wall draw, and the step that writes it."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from landloss.domain import constants
from landloss.exposure.rw.age import AGE_BINS
from landloss.exposure.rw.population import (
    POPULATION_COLUMNS,
    REQUIRED_COLUMNS,
    attach_rw_ids,
    draw_wall_population,
)
from landloss.exposure.rw.wall_age import AGE_SHARE_COLUMNS
from landloss.hazard.landslide.urban.wall_type_fragility import WALL_TYPES
from landloss.hazard.realisation import realisation_seed
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_population as script,
)

CRS = constants.DEFAULT_CRS
X0, Y0 = 1_750_000.0, 5_424_000.0

# The columns gen_wall_population.py writes, section 3.7 of the contract with
# the wall type and age bin in place of the condition.
OUTPUT_COLUMNS = (
    "rw_id",
    "claim_id",
    "wall_line_id",
    "world_id",
    "size_class",
    "wall_type",
    "age_bin",
    "height_m",
    "length_m",
    "wall_position",
    "is_flatland",
    "source",
    "material",
    "geometry",
)

# The script's fixture lines carry a property, which the walls carry over.
SCRIPT_OUTPUT_COLUMNS = (*OUTPUT_COLUMNS[:-1], "property_id", "geometry")


def rng(world_id=0):
    return realisation_seed(constants.EXPOSURE_BASE_SEED, world_id, "exposure")


def probabilities(
    n=1,
    *,
    p_wall=0.5,
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
            "length_m": np.full(n, 10.0),
            "p_wall": np.full(n, p_wall, dtype=float),
            "p_wall_basis": ["source_prior"] * n,
        },
        geometry=[
            LineString([(X0 + 20 * i, Y0 + y), (X0 + 20 * i + 10, Y0 + y)])
            for i in range(n)
        ],
        crs=CRS,
    )


def types_for(table, *, wall_type="crib_gabion", age_bin="1970_1991"):
    """A type draw giving every line of the table one type and age bin."""
    return pd.DataFrame(
        {"wall_type": wall_type, "age_bin": age_bin},
        index=pd.Index(table["wall_line_id"].to_numpy()),
    )


def drawn(table, generator=None, **kwargs):
    """Draw the table's walls with every line typed alike."""
    return draw_wall_population(
        table,
        rng() if generator is None else generator,
        types=types_for(table),
        **kwargs,
    )


def stacked(*frames):
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=CRS)


# --- the draw -----------------------------------------------------------------


def test_a_line_at_probability_one_always_draws_and_at_zero_never():
    table = stacked(
        probabilities(n=50, p_wall=1.0), probabilities(n=50, p_wall=0.0, first_id=51)
    )
    walls = drawn(table)
    assert len(walls) == 50
    assert walls["wall_line_id"].tolist() == table["wall_line_id"].iloc[:50].tolist()


def test_the_share_drawn_tracks_the_probability():
    table = probabilities(n=4000, p_wall=0.3)
    walls = drawn(table)
    assert abs(len(walls) / len(table) - 0.3) < 0.03


def test_the_existence_draw_is_the_first_of_two_uniforms_per_line():
    # The stream is unchanged from when the second uniform drew the condition,
    # so earlier worlds keep which lines are walls.
    table = probabilities(n=300, p_wall=0.4)
    expected = rng().random((300, 2))[:, 0] < 0.4
    walls = drawn(table)
    assert (
        walls["wall_line_id"].tolist() == table.loc[expected, "wall_line_id"].tolist()
    )


def test_each_wall_takes_its_own_type_and_age_bin_by_line_id():
    table = probabilities(n=3, p_wall=1.0)
    # In reverse order and with a line the table does not hold, to show the
    # join is by id, not by position.
    types = pd.DataFrame(
        {
            "wall_type": ["engineered", "crib_gabion", "brick_rock", "crib_gabion"],
            "age_bin": ["2005_on", "1970_1991", "pre_1970", "pre_1970"],
        },
        index=pd.Index(["WL0000003", "WL0000002", "WL0000001", "WL0000099"]),
    )
    walls = draw_wall_population(table, rng(), types=types)
    assert walls["wall_type"].tolist() == [
        "brick_rock",
        "crib_gabion",
        "engineered",
    ]
    assert walls["age_bin"].tolist() == ["pre_1970", "1970_1991", "2005_on"]


def test_a_drawn_wall_with_no_type_is_refused():
    table = probabilities(n=3, p_wall=1.0)
    with pytest.raises(ValueError, match="no type"):
        draw_wall_population(table, rng(), types=types_for(table.iloc[:2]))


def test_an_undrawn_line_needs_no_type():
    table = stacked(
        probabilities(n=1, p_wall=1.0), probabilities(n=1, p_wall=0.0, first_id=2)
    )
    walls = draw_wall_population(table, rng(), types=types_for(table.iloc[:1]))
    assert walls["wall_line_id"].tolist() == ["WL0000001"]


def test_a_type_draw_missing_a_column_or_repeating_a_line_is_refused():
    table = probabilities(n=2, p_wall=1.0)
    with pytest.raises(ValueError, match="age_bin"):
        draw_wall_population(
            table, rng(), types=types_for(table).drop(columns=["age_bin"])
        )
    repeated = pd.concat([types_for(table), types_for(table)])
    with pytest.raises(ValueError, match="repeats"):
        draw_wall_population(table, rng(), types=repeated)


def test_the_same_generator_reproduces_and_another_world_differs():
    table = probabilities(n=400)
    first = drawn(table)
    second = drawn(table)
    other = drawn(table, rng(world_id=1))
    assert first["wall_line_id"].tolist() == second["wall_line_id"].tolist()
    assert first["wall_line_id"].tolist() != other["wall_line_id"].tolist()


def test_a_line_drawn_earlier_does_not_depend_on_lines_added_after_it():
    short = probabilities(n=100)
    longer = stacked(short, probabilities(n=100, first_id=101))
    first = drawn(short)
    second = drawn(longer)
    head = second.iloc[: len(first)]
    assert head["wall_line_id"].tolist() == first["wall_line_id"].tolist()


def test_a_wall_is_the_line_that_drew_it():
    table = probabilities(n=3, p_wall=1.0, face_height_m=1.7)
    walls = drawn(table)
    assert walls.columns.tolist() == list(POPULATION_COLUMNS)
    assert walls["height_m"].tolist() == [1.7] * 3
    assert walls["size_class"].tolist() == ["medium"] * 3
    assert walls["length_m"].tolist() == [10.0] * 3
    assert walls.geometry.geom_equals(table.geometry).all()
    assert walls.crs == CRS
    assert walls.index.tolist() == [0, 1, 2]


def test_a_wall_carries_its_lengths_in_each_property_where_the_line_has_them():
    table = probabilities(n=2, p_wall=1.0)
    table["property_id"] = ["P1", "P2"]
    table["property_lengths_m"] = [
        [{"property_id": "P1", "length_m": 10.0}],
        [
            {"property_id": "P2", "length_m": 7.0},
            {"property_id": "P3", "length_m": 3.0},
        ],
    ]
    table["n_properties"] = [1, 2]
    walls = drawn(table)
    assert walls.columns.tolist()[: len(POPULATION_COLUMNS) - 1] == list(
        POPULATION_COLUMNS[:-1]
    )
    assert walls["property_id"].tolist() == ["P1", "P2"]
    assert walls["n_properties"].tolist() == [1, 2]
    assert walls["property_lengths_m"].iloc[1][1]["length_m"] == 3.0


def test_a_line_with_no_probability_draws_nothing():
    table = probabilities(n=10, p_wall=np.nan)
    assert drawn(table).empty


def test_no_lines_gives_an_empty_population_with_the_columns():
    walls = drawn(probabilities(n=0))
    assert walls.empty
    assert walls.columns.tolist() == list(POPULATION_COLUMNS)


def test_a_claimless_line_is_drawn_and_left_for_the_script_to_drop():
    walls = drawn(probabilities(n=2, p_wall=1.0, claim_id=None))
    assert len(walls) == 2
    assert walls["claim_id"].isna().all()


def test_a_given_walled_draw_replaces_p_wall():
    table = probabilities(n=200, p_wall=0.5)
    walled = np.zeros(200, dtype=bool)
    walled[::3] = True
    given = drawn(table, walled=walled)
    assert given["wall_line_id"].tolist() == table.loc[walled, "wall_line_id"].tolist()
    assert (given["wall_type"] == "crib_gabion").all()


def test_a_walled_draw_of_the_wrong_length_is_refused():
    with pytest.raises(ValueError, match="one flag per line"):
        drawn(probabilities(n=3), walled=np.ones(2, dtype=bool))


def test_a_missing_column_is_refused():
    assert "p_poor" not in REQUIRED_COLUMNS
    with pytest.raises(ValueError, match="p_wall"):
        drawn(probabilities().drop(columns=["p_wall"]))


# --- every drawn wall, with the minted ids joined back --------------------------


def test_attach_rw_ids_keeps_every_drawn_wall_and_nulls_the_uninsured():
    walls = drawn(probabilities(n=3, p_wall=1.0))
    insured = walls.iloc[[2, 0]].copy()
    insured.insert(0, "rw_id", ["C-1-RW02", "C-1-RW01"])
    out = attach_rw_ids(walls, insured)
    assert out.columns.tolist() == ["rw_id", *POPULATION_COLUMNS]
    assert out["wall_line_id"].tolist() == walls["wall_line_id"].tolist()
    assert out["rw_id"].tolist() == ["C-1-RW01", None, "C-1-RW02"]
    assert out["rw_id"].dtype == object
    assert out.crs == CRS


def test_attach_rw_ids_with_nothing_insured_gives_every_wall_a_null_id():
    walls = drawn(probabilities(n=2, p_wall=1.0))
    insured = walls.iloc[[]].copy()
    insured.insert(0, "rw_id", pd.Series([], dtype=object))
    out = attach_rw_ids(walls, insured)
    assert len(out) == 2
    assert out["rw_id"].isna().all()


def test_attach_rw_ids_refuses_a_population_naming_an_undrawn_line():
    walls = drawn(probabilities(n=2, p_wall=1.0))
    stranger = walls.iloc[[0]].copy()
    stranger["wall_line_id"] = "WL9999999"
    stranger.insert(0, "rw_id", ["C-1-RW01"])
    with pytest.raises(ValueError, match="drew no wall"):
        attach_rw_ids(walls, stranger)
    repeated = stacked(walls, walls)
    with pytest.raises(ValueError, match="repeats wall_line_id"):
        attach_rw_ids(repeated, walls.iloc[[]].assign(rw_id=None))


# --- the script ---------------------------------------------------------------


def age_shares(rows):
    """A gen_wall_age.py table from {property_id: (shares, age_basis)}."""
    return pd.DataFrame(
        [[*values, basis] for values, basis in rows.values()],
        columns=[*AGE_SHARE_COLUMNS, "age_basis"],
        index=pd.Index(list(rows), name="property_id"),
    )


@pytest.fixture
def redirected_script(tmp_path, monkeypatch):
    """Point gen_wall_population.py at synthetic inputs.

    Claim A has two certain lines on its land and one 50 m away; claim B has
    one certain line; a fifth line has no claim. The lines of claim A stand on
    property PA, whose walls were all built from 2005, so its walls never
    leave that bin; the others take the extent's shares, all before 1970.
    The second line is on a road frontage.
    """
    table = stacked(
        probabilities(n=2, p_wall=1.0, claim_id="A"),
        probabilities(n=1, p_wall=1.0, claim_id="A", y=50.0, first_id=3),
        probabilities(n=1, p_wall=1.0, claim_id="B", first_id=4),
        probabilities(n=1, p_wall=1.0, claim_id=None, first_id=5),
    )
    table["property_id"] = ["PA", "PA", "PA", "PB", None]
    insured = gpd.GeoDataFrame(
        {"claim_id": ["A", "B"]},
        geometry=[
            box(X0 - 5, Y0 - 5, X0 + 35, Y0 + 5),
            box(X0 - 5, Y0 - 5, X0 + 15, Y0 + 5),
        ],
        crs=CRS,
    )
    ages = age_shares(
        {
            "PA": ((0.0, 0.0, 0.0, 1.0), "qv"),
            "PX": ((1.0, 0.0, 0.0, 0.0), "extent"),
        }
    )
    units = pd.DataFrame(
        {"on_road_frontage": [False, True, False, False]},
        index=pd.Index(table["wall_line_id"].iloc[:4], name="wall_unit_id"),
    )
    table_file = tmp_path / "wall-probability-pilot.geoparquet"
    insured_file = tmp_path / "insured-land-pilot.geoparquet"
    draws_file = tmp_path / "urban-slope-wall-draws-pilot.parquet"
    ages_file = tmp_path / "wall-age-pilot.parquet"
    units_file = tmp_path / "urban-slope-wall-units-pilot.parquet"
    table.to_parquet(table_file)
    insured.to_parquet(insured_file)
    every_wall_walled(table, world_ids=(0, 1)).to_parquet(draws_file)
    ages.to_parquet(ages_file)
    units.to_parquet(units_file)
    monkeypatch.setattr(script, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(script, "wall_probability_path", lambda *, extent: table_file)
    monkeypatch.setattr(script, "insured_land_path", lambda *, extent: insured_file)
    monkeypatch.setattr(script, "wall_draws_path", lambda *, extent: draws_file)
    monkeypatch.setattr(script, "wall_age_path", lambda *, extent: ages_file)
    monkeypatch.setattr(script, "wall_units_path", lambda *, extent: units_file)
    return table


def every_wall_walled(table, *, world_ids, walled=True):
    """A landslide step 12 draws table with every candidate walled per world."""
    return pd.DataFrame(
        {
            "world_id": np.repeat(np.asarray(world_ids, dtype=np.int64), len(table)),
            "wall_unit_id": np.tile(table["wall_line_id"].to_numpy(), len(world_ids)),
            "walled": np.resize(
                np.asarray(walled, dtype=bool), len(table) * len(world_ids)
            ),
        }
    )


def test_gen_wall_population_main_writes_one_file_per_world(
    tmp_path, redirected_script
):
    script.main(extent="wlg-pilot", world_ids=[0, 1])

    for world_id in (0, 1):
        out_path = script.wall_population_path(world_id, extent="wlg-pilot")
        assert (
            out_path
            == tmp_path
            / "exposure"
            / f"wall-population-w{world_id:03d}-pilot.geoparquet"
        )
        written = gpd.read_parquet(out_path)
        assert written.columns.tolist() == list(SCRIPT_OUTPUT_COLUMNS)
        # The claimless line and the line off A's insured land are dropped.
        assert written["rw_id"].tolist() == ["A-RW01", "A-RW02", "B-RW01"]
        assert (written["world_id"] == world_id).all()
        assert written["world_id"].dtype == np.int64
        assert written["wall_line_id"].isin(redirected_script["wall_line_id"]).all()
        assert set(written["wall_type"]) <= set(WALL_TYPES)
        assert set(written["age_bin"]) <= set(AGE_BINS)
        assert written.crs == CRS


def test_the_walls_take_their_property_age_or_the_extent_default(
    redirected_script,
):
    script.main(extent="wlg-pilot", world_ids=[0])

    every_wall = gpd.read_parquet(script.drawn_walls_path(0, extent="wlg-pilot"))
    age_bin = every_wall.set_index("wall_line_id")["age_bin"]
    # PA is all 2005_on, which a rebuild cannot move on.
    assert (age_bin.loc[["WL0000001", "WL0000002", "WL0000003"]] == "2005_on").all()
    # PB is not in the age file and the fifth line has no property: both take
    # the extent's shares, all pre_1970, moved on at most one bin by a rebuild.
    assert set(age_bin.loc[["WL0000004", "WL0000005"]]) <= {"pre_1970", "1970_1991"}


def test_gen_wall_population_main_reproduces_a_world(redirected_script):
    script.main(extent="wlg-pilot", world_ids=[0])
    one = gpd.read_parquet(script.wall_population_path(0, extent="wlg-pilot"))
    script.main(extent="wlg-pilot", world_ids=[0])
    again = gpd.read_parquet(script.wall_population_path(0, extent="wlg-pilot"))
    assert one["wall_type"].tolist() == again["wall_type"].tolist()
    assert one["age_bin"].tolist() == again["age_bin"].tolist()
    assert one["rw_id"].tolist() == again["rw_id"].tolist()


def test_the_type_draw_does_not_depend_on_which_walls_are_walled(
    tmp_path, redirected_script, monkeypatch
):
    script.main(extent="wlg-pilot", world_ids=[0])
    every = gpd.read_parquet(script.drawn_walls_path(0, extent="wlg-pilot"))
    some_file = tmp_path / "some-walled.parquet"
    every_wall_walled(
        redirected_script, world_ids=(0,), walled=[False, True, False, True, True]
    ).to_parquet(some_file)
    monkeypatch.setattr(script, "wall_draws_path", lambda *, extent: some_file)

    script.main(extent="wlg-pilot", world_ids=[0])

    some = gpd.read_parquet(script.drawn_walls_path(0, extent="wlg-pilot"))
    assert some["wall_line_id"].tolist() == ["WL0000002", "WL0000004", "WL0000005"]
    joined = some.merge(every, on="wall_line_id", suffixes=("", "_every"))
    assert joined["wall_type"].tolist() == joined["wall_type_every"].tolist()
    assert joined["age_bin"].tolist() == joined["age_bin_every"].tolist()


def test_a_world_step_12_did_not_draw_is_refused(redirected_script):
    with pytest.raises(ValueError, match="world 2 not drawn"):
        script.main(extent="wlg-pilot", world_ids=[2])


def test_missing_draws_say_to_run_step_12(tmp_path, redirected_script, monkeypatch):
    monkeypatch.setattr(
        script, "wall_draws_path", lambda *, extent: tmp_path / "missing.parquet"
    )
    with pytest.raises(FileNotFoundError, match=r"gen_urban_slope_wall_units\.py"):
        script.main(extent="wlg-pilot", world_ids=[0])


def test_missing_age_shares_say_to_run_gen_wall_age(
    tmp_path, redirected_script, monkeypatch
):
    monkeypatch.setattr(
        script, "wall_age_path", lambda *, extent: tmp_path / "missing.parquet"
    )
    with pytest.raises(FileNotFoundError, match=r"gen_wall_age\.py"):
        script.main(extent="wlg-pilot", world_ids=[0])


def test_missing_wall_units_say_to_run_step_12(
    tmp_path, redirected_script, monkeypatch
):
    monkeypatch.setattr(
        script, "wall_units_path", lambda *, extent: tmp_path / "missing.parquet"
    )
    with pytest.raises(FileNotFoundError, match=r"gen_urban_slope_wall_units\.py"):
        script.main(extent="wlg-pilot", world_ids=[0])


def test_drawn_walls_path_names_the_world_and_the_extent():
    assert script.drawn_walls_path(3, extent="wlg-pilot").name == (
        "drawn-walls-w003-pilot.geoparquet"
    )
    assert script.drawn_walls_path(12, extent="full").name == (
        "drawn-walls-w012.geoparquet"
    )


def test_gen_wall_population_main_writes_every_drawn_wall_before_the_filters(
    tmp_path, redirected_script
):
    script.main(extent="wlg-pilot", world_ids=[0, 1])

    for world_id in (0, 1):
        drawn_path = script.drawn_walls_path(world_id, extent="wlg-pilot")
        assert drawn_path == (
            tmp_path / "exposure" / f"drawn-walls-w{world_id:03d}-pilot.geoparquet"
        )
        every_wall = gpd.read_parquet(drawn_path)
        insured = gpd.read_parquet(
            script.wall_population_path(world_id, extent="wlg-pilot")
        )
        assert every_wall.columns.tolist() == list(SCRIPT_OUTPUT_COLUMNS)
        # Every certain line drew, in line order, one row per line.
        assert (
            every_wall["wall_line_id"].tolist()
            == redirected_script["wall_line_id"].tolist()
        )
        assert every_wall["wall_line_id"].is_unique
        # The claimless line and the line off A's insured land carry no rw_id.
        assert every_wall["rw_id"].isna().tolist() == [False, False, True, False, True]
        assert every_wall["rw_id"].dropna().tolist() == ["A-RW01", "A-RW02", "B-RW01"]
        assert every_wall["claim_id"].isna().tolist() == [False] * 4 + [True]
        assert every_wall["claim_id"].dropna().tolist() == ["A", "A", "A", "B"]
        assert (every_wall["world_id"] == world_id).all()
        assert every_wall["world_id"].dtype == np.int64
        assert every_wall.crs == CRS
        # The insured rows agree with the population file wall for wall.
        joined = insured.merge(
            every_wall,
            on="wall_line_id",
            suffixes=("", "_drawn"),
            validate="one_to_one",
        )
        assert len(joined) == len(insured)
        for column in ("rw_id", "wall_type", "age_bin", "size_class", "height_m"):
            assert joined[column].tolist() == joined[f"{column}_drawn"].tolist()
        assert set(every_wall["wall_type"]) <= set(WALL_TYPES)
        assert every_wall["is_flatland"].dtype == bool


# --- the type draw's input ----------------------------------------------------


def test_type_candidates_read_the_property_frontage_and_height():
    table = probabilities(n=3, face_height_m=2.2)
    table["property_id"] = ["PA", None, "PZ"]
    ages = age_shares({"PA": ((0.1, 0.2, 0.3, 0.4), "qv")})
    frontage = pd.Series([True, False], index=["WL0000001", "WL0000002"])

    candidates, n_unaged = script.type_candidates(table, ages, frontage)

    assert candidates.index.tolist() == table["wall_line_id"].tolist()
    assert candidates["height_m"].tolist() == [2.2] * 3
    # A unit the step 12 table does not carry is off a road frontage.
    assert candidates["on_road_frontage"].tolist() == [True, False, False]
    assert candidates.loc["WL0000001", list(AGE_SHARE_COLUMNS)].tolist() == (
        pytest.approx([0.1, 0.2, 0.3, 0.4])
    )
    # The only aged property is the default too, as there is no extent row.
    for wall in ("WL0000002", "WL0000003"):
        assert candidates.loc[wall, list(AGE_SHARE_COLUMNS)].tolist() == (
            pytest.approx([0.1, 0.2, 0.3, 0.4])
        )
    assert n_unaged == 2


def test_type_candidates_without_a_property_column_take_the_default():
    ages = age_shares({"PA": ((0.0, 0.0, 0.0, 1.0), "qv")})
    candidates, n_unaged = script.type_candidates(
        probabilities(n=2), ages, pd.Series(dtype=bool)
    )
    assert n_unaged == 2
    assert (candidates["p_2005_on"] == 1.0).all()
    assert not candidates["on_road_frontage"].any()


def test_the_extent_default_is_the_extent_rows_where_there_are_any():
    ages = age_shares(
        {
            "PA": ((1.0, 0.0, 0.0, 0.0), "qv"),
            "PB": ((0.0, 0.5, 0.5, 0.0), "extent"),
        }
    )
    assert script.extent_default_shares(ages).tolist() == pytest.approx(
        [0.0, 0.5, 0.5, 0.0]
    )
    mean = script.extent_default_shares(ages.assign(age_basis="qv"))
    assert mean.tolist() == pytest.approx([0.5, 0.25, 0.25, 0.0])
    assert mean.sum() == pytest.approx(1.0)
