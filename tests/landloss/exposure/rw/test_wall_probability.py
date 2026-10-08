"""Tests for the probability on each candidate wall and the step writing it."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import MultiLineString, box

from landloss.domain import constants
from landloss.exposure.land.extent import build_claim_properties
from landloss.exposure.rw import wall_probability
from landloss.exposure.rw.population import REQUIRED_COLUMNS
from landloss.exposure.rw.wall_probability import (
    claim_of_properties,
    gen_unit_probability_table,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_probability as script,
)

CRS = constants.DEFAULT_CRS
X0, Y0 = 1_750_000.0, 5_424_000.0


# --- the wall probability -----------------------------------------------------


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


# --- the wall units -----------------------------------------------------------


def units_frame(*, height_m=(2.0,), property_id=("P1",), is_fill=(False,)):
    """A wall unit table with the columns the unit table reads."""
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


def test_gen_wall_probability_main_says_to_run_exposure_rw_step_6_first(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        script, "wall_units_path", lambda *, extent: tmp_path / "missing.geoparquet"
    )
    with pytest.raises(
        FileNotFoundError, match=r"exposure rw step 6 \(gen_wall_units\.py\)"
    ):
        script.main(extent="wlg-pilot", use_cached_layers=True)
