"""Tests for the probability on each candidate wall line and the step writing it."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from landloss.domain import constants
from landloss.exposure.rw import lines as wl
from landloss.exposure.rw.beta_population import BETA_POOR_SHARE
from landloss.exposure.rw.wall_probability import (
    BETA_FLATLAND_MAX_PROBABILITY,
    BETA_MAPPED_WALL_PROBABILITY,
    BETA_POST_1990_POOR_SHARE,
    BETA_PRE_1990_POOR_SHARE,
    BETA_ROCK_CUT_FACTOR,
    BETA_SOURCE_PROBABILITY,
    BETA_UNCONSENTED_POOR_SHARE,
    POOR_BASES,
    PROBABILITY_COLUMNS,
    WALL_BASES,
    apply_count_bounds,
    line_wall_probability,
    poor_condition_probability,
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
    age=None,
):
    """A candidate wall lines frame with every contract column, n equal rows."""
    ages = pd.array([pd.NA if age is None else age] * n, dtype="Int64")
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


# --- the condition probability -----------------------------------------------


def poor(height_m, age=None):
    ages = pd.Series(pd.array([age], dtype="Int64"))
    p, basis = poor_condition_probability(np.array([height_m]), ages)
    return float(p[0]), str(basis[0])


def test_a_tall_wall_with_no_age_takes_the_default():
    assert poor(2.0) == (pytest.approx(BETA_POOR_SHARE), "default")


def test_a_wall_under_the_consent_height_is_more_likely_poor():
    p, basis = poor(constants.UNCONSENTED_WALL_HEIGHT_M - 0.1)
    assert p == pytest.approx(BETA_UNCONSENTED_POOR_SHARE)
    assert basis == "height"
    assert BETA_UNCONSENTED_POOR_SHARE > BETA_POOR_SHARE


def test_the_consent_height_itself_is_not_under_it():
    assert poor(constants.UNCONSENTED_WALL_HEIGHT_M)[1] == "default"


def test_a_dwelling_age_overrides_the_height_rule():
    assert poor(0.8, age=1970) == (pytest.approx(BETA_PRE_1990_POOR_SHARE), "age")
    assert poor(0.8, age=2000) == (pytest.approx(BETA_POST_1990_POOR_SHARE), "age")
    assert poor(3.0, age=1990) == (pytest.approx(BETA_POST_1990_POOR_SHARE), "age")
    assert poor(3.0, age=1980) == (pytest.approx(BETA_PRE_1990_POOR_SHARE), "age")


def test_a_nan_height_takes_the_default():
    assert poor(np.nan) == (pytest.approx(BETA_POOR_SHARE), "default")


def test_the_bases_are_the_contract_vocabulary():
    assert set(POOR_BASES) == {"default", "height", "age"}
    assert set(WALL_BASES) == {"mapped", "source_prior", "rock_cut", "flatland_cap"}


def test_mismatched_condition_inputs_are_refused():
    with pytest.raises(ValueError, match="must match"):
        poor_condition_probability(
            np.array([1.0, 2.0]), pd.Series(pd.array([pd.NA], dtype="Int64"))
        )


# --- the count bounds hook ----------------------------------------------------


def bounds(**claims):
    rows = {
        claim: {"min_walls": lo, "max_walls": hi} for claim, (lo, hi) in claims.items()
    }
    return pd.DataFrame.from_dict(rows, orient="index")


def test_a_claim_under_its_minimum_is_scaled_up_to_it():
    p = np.array([0.2, 0.2, 0.2])
    claims = pd.Series(["A", "A", "A"])
    scaled = apply_count_bounds(p, claims, bounds(A=(1.5, 3)))
    assert scaled.sum() == pytest.approx(1.5)
    assert np.allclose(scaled, 0.5)


def test_a_claim_over_its_maximum_is_scaled_down_to_it():
    p = np.array([0.9, 0.9, 0.9])
    claims = pd.Series(["A", "A", "A"])
    scaled = apply_count_bounds(p, claims, bounds(A=(0, 1)))
    assert scaled.sum() == pytest.approx(1.0)


def test_a_claim_inside_its_bounds_and_an_unbounded_claim_are_unchanged():
    p = np.array([0.5, 0.5, 0.3])
    claims = pd.Series(["A", "A", "B"])
    scaled = apply_count_bounds(p, claims, bounds(A=(0.5, 2)))
    assert np.array_equal(scaled, p)


def test_no_probability_is_scaled_above_one():
    p = np.array([0.9, 0.1])
    claims = pd.Series(["A", "A"])
    scaled = apply_count_bounds(p, claims, bounds(A=(1.9, 2)))
    assert scaled.max() <= 1.0


def test_lines_at_zero_share_the_minimum_equally():
    p = np.array([0.0, 0.0])
    claims = pd.Series(["A", "A"])
    scaled = apply_count_bounds(p, claims, bounds(A=(1, 2)))
    assert np.allclose(scaled, 0.5)


def test_a_claimless_line_is_never_scaled():
    p = np.array([0.2])
    claims = pd.Series([None], dtype=object)
    assert np.array_equal(apply_count_bounds(p, claims, bounds(A=(1, 2))), p)


def test_bad_bounds_are_refused():
    with pytest.raises(ValueError, match="minimum above"):
        apply_count_bounds(np.array([0.2]), pd.Series(["A"]), bounds(A=(3, 1)))
    with pytest.raises(ValueError, match="max_walls"):
        apply_count_bounds(
            np.array([0.2]), pd.Series(["A"]), pd.DataFrame({"min_walls": [1]})
        )


# --- the table ---------------------------------------------------------------


def test_the_table_carries_every_line_column_and_the_probability_columns():
    lines = stacked(lines_frame(n=3), lines_frame(mapped=True, face_height_m=0.8))
    table = wall_probability_table(lines)
    assert table.columns.tolist() == [*lines.columns, *PROBABILITY_COLUMNS]
    assert len(table) == 4
    assert table.crs == CRS
    assert table["p_wall"].between(0, 1).all()
    assert table["p_poor_basis"].tolist() == ["default"] * 3 + ["height"]
    assert table["p_wall_basis"].iloc[3] == "mapped"
    assert table.geometry.geom_equals(lines.geometry).all()


def test_the_table_reads_the_dwelling_age_where_held():
    table = wall_probability_table(lines_frame(age=1960))
    assert table["p_poor_basis"].iloc[0] == "age"
    assert table["p_poor"].iloc[0] == pytest.approx(BETA_PRE_1990_POOR_SHARE)


def test_the_table_treats_a_missing_age_column_as_unheld():
    table = wall_probability_table(lines_frame().drop(columns=["dwelling_age_decade"]))
    assert table["p_poor_basis"].iloc[0] == "default"


def test_the_table_refuses_a_missing_input_column():
    with pytest.raises(ValueError, match="face_height_m"):
        wall_probability_table(lines_frame().drop(columns=["face_height_m"]))


# --- the script ---------------------------------------------------------------


@pytest.fixture
def redirected_script(tmp_path, monkeypatch):
    """Point gen_wall_probability.py at a synthetic lines file in tmp_path."""
    lines = stacked(
        lines_frame(n=2, source="terrain_break"),
        lines_frame(source="gns_mapped_wall", mapped=True, face_height_m=0.4),
        lines_frame(source="road_frontage", flat=True, claim_id=None),
    )
    lines_file = tmp_path / "wall-lines-pilot.geoparquet"
    lines.to_parquet(lines_file)
    monkeypatch.setattr(script, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(script, "wall_lines_path", lambda *, extent: lines_file)
    return lines


def test_gen_wall_probability_main_writes_one_row_per_line(tmp_path, redirected_script):
    script.main(extent="wlg-pilot")

    out_path = script.wall_probability_path(extent="wlg-pilot")
    assert out_path == tmp_path / "exposure" / "wall-probability-pilot.geoparquet"
    written = gpd.read_parquet(out_path)
    assert len(written) == len(redirected_script)
    assert written.columns.tolist() == [
        *redirected_script.columns,
        *PROBABILITY_COLUMNS,
    ]
    assert (
        written["wall_line_id"].tolist() == redirected_script["wall_line_id"].tolist()
    )
    assert written["p_wall_basis"].tolist() == [
        "source_prior",
        "source_prior",
        "source_prior",
        "flatland_cap",
    ]
    assert written["p_poor_basis"].tolist() == [
        "default",
        "default",
        "height",
        "default",
    ]
    assert written["dwelling_age_decade"].isna().all()
    assert written.crs == CRS
