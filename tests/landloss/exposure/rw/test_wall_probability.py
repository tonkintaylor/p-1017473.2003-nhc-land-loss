"""Tests for the probability on each candidate wall and the step writing it."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, MultiLineString, box

from landloss.domain import constants
from landloss.exposure.land.extent import build_claim_properties
from landloss.exposure.rw import lines as wl
from landloss.exposure.rw import wall_probability
from landloss.exposure.rw.population import REQUIRED_COLUMNS
from landloss.exposure.rw.wall_probability import (
    BETA_FLATLAND_MAX_PROBABILITY,
    BETA_MAPPED_WALL_PROBABILITY,
    BETA_ROCK_CUT_FACTOR,
    BETA_SOURCE_PROBABILITY,
    PROBABILITY_COLUMNS,
    WALL_BASES,
    claim_of_properties,
    gen_unit_probability_table,
    line_wall_probability,
    wall_probability_table,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_probability as script,
)

CRS = constants.DEFAULT_CRS
X0, Y0 = 1_750_000.0, 5_424_000.0


def lines_frame(
    n=1,
    *,
    source="property_boundary",
    mapped=False,
    rock_cut=False,
    flat=False,
    face_height_m=2.0,
    claim_id="C-1",
):
    """A candidate wall lines frame with every contract column, n equal rows."""
    ages = pd.array([pd.NA] * n, dtype="Int64")
    return gpd.GeoDataFrame(
        {
            "wall_line_id": [f"WL{i + 1:07d}" for i in range(n)],
            "source": [source] * n,
            "is_mapped_wall": [mapped] * n,
            "claim_id": [claim_id] * n,
            "face_height_m": np.full(n, face_height_m, dtype=float),
            "size_class": ["medium"] * n,
            "wall_position": ["fill"] * n,
            "is_flatland": [flat] * n,
            "ground_id": ["GM0000001"] * n,
            "material": ["greywacke_highly_weathered" if rock_cut else "fill"] * n,
            "modification": ["cut" if rock_cut else "fill"] * n,
            "is_rock_cut": [rock_cut] * n,
            "slope_degrees": np.full(n, 20.0),
            "aspect_degrees": np.full(n, 180.0),
            "dwelling_age_decade": ages,
            "length_m": np.full(n, 10.0),
        },
        geometry=[
            LineString([(X0 + 20 * i, Y0), (X0 + 20 * i + 10, Y0)]) for i in range(n)
        ],
        crs=CRS,
    )


def stacked(*frames):
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=CRS)


def probability(**kwargs):
    p, basis = line_wall_probability(lines_frame(**kwargs))
    return float(p[0]), str(basis[0])


# --- the wall probability -----------------------------------------------------


def test_every_source_has_a_prior_and_the_lines_frame_matches_the_contract():
    assert set(BETA_SOURCE_PROBABILITY) == set(wl.SOURCES)
    assert BETA_SOURCE_PROBABILITY["gns_mapped_wall"] == BETA_MAPPED_WALL_PROBABILITY
    assert set(lines_frame().columns) == {"wall_line_id", *wl.COLUMNS}


@pytest.mark.parametrize("source", wl.SOURCES)
def test_without_evidence_the_probability_is_the_source_prior(source):
    p, basis = probability(source=source)
    assert p == pytest.approx(BETA_SOURCE_PROBABILITY[source])
    assert basis == "source_prior"


def test_a_rock_cut_lowers_the_prior_by_the_factor():
    p, basis = probability(source="terrain_break", rock_cut=True)
    assert p == pytest.approx(
        BETA_SOURCE_PROBABILITY["terrain_break"] * BETA_ROCK_CUT_FACTOR
    )
    assert basis == "rock_cut"


def test_flat_land_caps_the_probability():
    p, basis = probability(source="slide_cut_fill_line", flat=True)
    assert p == pytest.approx(BETA_FLATLAND_MAX_PROBABILITY)
    assert basis == "flatland_cap"


def test_flat_land_does_not_lift_a_prior_already_under_the_cap():
    rock = lines_frame(source="property_boundary", rock_cut=True, flat=True)
    p, basis = line_wall_probability(rock)
    assert p[0] == pytest.approx(
        BETA_SOURCE_PROBABILITY["property_boundary"] * BETA_ROCK_CUT_FACTOR
    )
    assert basis[0] == "rock_cut"


def test_a_mapped_wall_lifts_a_boundary_line_to_the_mapped_probability():
    p, basis = probability(source="property_boundary", mapped=True)
    assert p == pytest.approx(BETA_MAPPED_WALL_PROBABILITY)
    assert basis == "mapped"


def test_a_mapped_wall_outranks_the_rock_cut_and_the_flat_land():
    p, basis = probability(
        source="terrain_break", mapped=True, rock_cut=True, flat=True
    )
    assert p == pytest.approx(BETA_MAPPED_WALL_PROBABILITY)
    assert basis == "mapped"


def test_a_mapped_wall_source_keeps_the_prior_basis_when_nothing_changes_it():
    p, basis = probability(source="gns_mapped_wall", mapped=True)
    assert p == pytest.approx(BETA_MAPPED_WALL_PROBABILITY)
    assert basis == "source_prior"


def test_the_rules_apply_row_by_row():
    frame = stacked(
        lines_frame(source="terrain_break"),
        lines_frame(source="terrain_break", rock_cut=True),
        lines_frame(source="terrain_break", flat=True),
        lines_frame(source="terrain_break", mapped=True),
    )
    p, basis = line_wall_probability(frame)
    assert list(basis) == ["source_prior", "rock_cut", "flatland_cap", "mapped"]
    assert set(basis) <= set(WALL_BASES)
    assert p[0] > p[1] > p[2]
    assert p[3] == pytest.approx(BETA_MAPPED_WALL_PROBABILITY)


def test_every_probability_is_between_zero_and_one():
    for source in wl.SOURCES:
        for mapped in (False, True):
            for rock_cut in (False, True):
                for flat in (False, True):
                    p, _ = probability(
                        source=source, mapped=mapped, rock_cut=rock_cut, flat=flat
                    )
                    assert 0.0 <= p <= 1.0


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError, match="driveway_edge"):
        line_wall_probability(lines_frame(source="driveway_edge"))


def test_a_missing_column_is_refused():
    with pytest.raises(ValueError, match="is_rock_cut"):
        line_wall_probability(lines_frame().drop(columns=["is_rock_cut"]))


# --- the retired condition -------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "poor_condition_probability",
        "BETA_UNCONSENTED_POOR_SHARE",
        "BETA_PRE_1990_POOR_SHARE",
        "BETA_POST_1990_POOR_SHARE",
        "BUILDING_ACT_DECADE",
        "POOR_BASES",
        "AGE_COLUMN",
    ],
)
def test_the_condition_probability_is_retired(name):
    # The wall type carries what the condition did, so none of it is left.
    assert not hasattr(wall_probability, name)


def test_the_bases_are_the_contract_vocabulary():
    assert set(WALL_BASES) == {"mapped", "source_prior", "rock_cut", "flatland_cap"}
    assert PROBABILITY_COLUMNS == ("p_wall", "p_wall_basis")


# --- the wall units -----------------------------------------------------------


def units_frame(*, height_m=(2.0,), property_id=("P1",), is_fill=(False,)):
    """A step 12 wall unit table with the columns the unit table reads."""
    n = len(height_m)
    return gpd.GeoDataFrame(
        {
            "property_id": pd.array(list(property_id), dtype="string"),
            "p_wall": np.full(n, 0.5),
            "p_wall_basis": ["prior"] * n,
            "height_m": np.asarray(height_m, dtype=float),
            "length_m": np.full(n, 8.0),
            "is_fill": list(is_fill),
            "unit_source": ["pif"] * n,
            "ground_material": ["fill_uncontrolled"] * n,
        },
        geometry=[
            MultiLineString([[(X0 + 20 * i, Y0), (X0 + 20 * i + 8, Y0)]])
            for i in range(n)
        ],
        index=pd.Index([f"WU{i + 1:07d}" for i in range(n)], name="wall_unit_id"),
        crs=CRS,
    )


def boundaries_frame():
    """Two stacked unit titles, a freehold title and a road parcel."""
    stack = box(X0, Y0 - 5, X0 + 20, Y0 + 5)
    return gpd.GeoDataFrame(
        {
            "source_id": ["U2", "U1", "F1", "R1"],
            "source": [
                "NZ Unit of Property",
                "NZ Unit of Property",
                "NZ Property Titles",
                "NZ Primary Parcels - Road",
            ],
        },
        geometry=[
            stack,
            stack,
            box(X0 + 20, Y0 - 5, X0 + 40, Y0 + 5),
            box(X0 + 40, Y0 - 5, X0 + 60, Y0 + 5),
        ],
        crs=CRS,
    )


def test_stacked_titles_map_to_one_claim_and_a_road_to_none():
    boundaries = boundaries_frame()
    claim_ids = claim_of_properties(boundaries, build_claim_properties(boundaries))
    assert claim_ids.to_dict() == {"U2": "U1", "U1": "U1", "F1": "F1"}


def test_the_unit_table_carries_what_the_draw_reads():
    units = units_frame(
        height_m=(0.8, 2.0, 3.0),
        property_id=("U2", "R1", None),
        is_fill=(True, False, False),
    )
    claim_ids = pd.Series({"U2": "U1", "U1": "U1"})
    table = gen_unit_probability_table(units, claim_ids)
    assert set(REQUIRED_COLUMNS) <= set(table.columns)
    assert table["wall_line_id"].tolist() == units.index.tolist()
    assert table["claim_id"].isna().tolist() == [False, True, True]
    assert table["claim_id"].iloc[0] == "U1"
    assert table["size_class"].tolist() == ["small", "medium", "large"]
    assert table["wall_position"].tolist() == ["fill", "cut", "cut"]
    assert not table["is_flatland"].any()
    assert table["p_wall"].tolist() == pytest.approx([0.5, 0.5, 0.5])
    assert not {"p_poor", "p_poor_basis", "dwelling_age_decade"} & set(table.columns)
    assert table.crs == CRS


def test_the_unit_table_carries_the_lengths_in_each_property():
    units = units_frame(height_m=(2.0, 2.0), property_id=("P1", "P2"))
    units["property_lengths_m"] = [
        [{"property_id": "P1", "length_m": 8.0}],
        [
            {"property_id": "P2", "length_m": 6.0},
            {"property_id": "P1", "length_m": 2.0},
        ],
    ]
    units["n_properties"] = [1, 2]
    table = gen_unit_probability_table(units, pd.Series(dtype=object))
    assert table["n_properties"].tolist() == [1, 2]
    assert table["property_lengths_m"].iloc[1][1] == {
        "property_id": "P1",
        "length_m": 2.0,
    }


def test_a_unit_with_no_height_is_small_not_large():
    table = gen_unit_probability_table(units_frame(height_m=(np.nan,)), pd.Series())
    assert table["size_class"].tolist() == ["small"]
    assert np.isnan(table["face_height_m"].iloc[0])


def test_the_unit_table_refuses_a_missing_column():
    with pytest.raises(ValueError, match="is_fill"):
        gen_unit_probability_table(units_frame().drop(columns=["is_fill"]), pd.Series())


# --- the table ---------------------------------------------------------------


def test_the_table_carries_every_line_column_and_the_probability_columns():
    lines = stacked(lines_frame(n=3), lines_frame(mapped=True, face_height_m=0.8))
    table = wall_probability_table(lines)
    assert table.columns.tolist() == [*lines.columns, *PROBABILITY_COLUMNS]
    assert len(table) == 4
    assert table.crs == CRS
    assert table["p_wall"].between(0, 1).all()
    assert table["p_wall_basis"].iloc[3] == "mapped"
    assert table.geometry.geom_equals(lines.geometry).all()


def test_the_line_table_carries_what_the_draw_reads():
    table = wall_probability_table(lines_frame(n=2))
    assert set(REQUIRED_COLUMNS) <= set(table.columns)
    assert "p_poor" not in table.columns


def test_the_table_does_not_need_a_dwelling_age():
    table = wall_probability_table(lines_frame().drop(columns=["dwelling_age_decade"]))
    assert table["p_wall_basis"].iloc[0] == "source_prior"


def test_the_table_refuses_a_missing_input_column():
    with pytest.raises(ValueError, match="face_height_m"):
        wall_probability_table(lines_frame().drop(columns=["face_height_m"]))


# --- the script ---------------------------------------------------------------


@pytest.fixture
def redirected_script(tmp_path, monkeypatch):
    """Point gen_wall_probability.py at synthetic wall units and boundaries."""
    units = units_frame(
        height_m=(0.8, 2.0, np.nan),
        property_id=("U2", "F1", "R1"),
        is_fill=(True, False, False),
    )
    units_file = tmp_path / "urban-slope-wall-units-pilot.geoparquet"
    units.to_parquet(units_file)
    monkeypatch.setattr(script, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(script, "wall_units_path", lambda *, extent: units_file)
    monkeypatch.setattr(script, "dem_bbox", lambda *, extent: (0.0, 0.0, 1.0, 1.0))
    monkeypatch.setattr(
        script, "get_nz_property_boundaries", lambda **_: boundaries_frame()
    )
    return units


def test_gen_wall_probability_main_writes_one_row_per_unit(tmp_path, redirected_script):
    script.main(extent="wlg-pilot", use_cached_layers=True)

    out_path = script.wall_probability_path(extent="wlg-pilot")
    assert out_path == tmp_path / "exposure" / "wall-probability-pilot.geoparquet"
    written = gpd.read_parquet(out_path)
    assert written["wall_line_id"].tolist() == redirected_script.index.tolist()
    assert written["claim_id"].isna().tolist() == [False, False, True]
    assert written["claim_id"].dropna().tolist() == ["U1", "F1"]
    assert written["size_class"].tolist() == ["small", "medium", "small"]
    assert set(REQUIRED_COLUMNS) <= set(written.columns)
    assert not {"p_poor", "p_poor_basis"} & set(written.columns)
    assert written.crs == CRS


def test_gen_wall_probability_main_says_to_run_step_12_first(tmp_path, monkeypatch):
    monkeypatch.setattr(
        script, "wall_units_path", lambda *, extent: tmp_path / "missing.geoparquet"
    )
    with pytest.raises(FileNotFoundError, match=r"gen_urban_slope_wall_units\.py"):
        script.main(extent="wlg-pilot", use_cached_layers=True)
