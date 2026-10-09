import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from landloss.exposure.rw.wall_age import (
    AGE_BASES,
    AGE_SHARE_COLUMNS,
    BETA_LOT_OLDER_GAP_YEARS,
    combine_wall_ages,
    own_lot_dates,
    property_qv_ages,
    qv_age_shares,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_age as script,
)

CRS = "EPSG:2193"
X0, Y0 = 1_750_000.0, 5_430_000.0

EXTENT_DEFAULT = pd.Series([0.4, 0.3, 0.2, 0.1], index=list(AGE_SHARE_COLUMNS))


def roll_frame(*rows):
    """QV rating units as (roll, assessment, suffix, building_age_indicator)."""
    return pd.DataFrame(
        rows,
        columns=[
            "valuation_no_roll",
            "valuation_no_assessment",
            "valuation_no_suffix",
            "building_age_indicator",
        ],
    )


def shares(*values):
    return pd.DataFrame([values], columns=list(AGE_SHARE_COLUMNS))


def qv_frame(rows):
    """QV ages as {property_id: (p_pre_1970, ..., p_2005_on, qv_year)}."""
    return pd.DataFrame.from_dict(
        rows, orient="index", columns=[*AGE_SHARE_COLUMNS, "qv_year"]
    )


def titles_frame(rows):
    """Lot ages as {property_id: (est_year, age_bin)}."""
    return pd.DataFrame.from_dict(rows, orient="index", columns=["est_year", "age_bin"])


def fallback_frame(rows):
    """Suburb shares as {property_id: (p_pre_1970, ..., p_2005_on)}."""
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(AGE_SHARE_COLUMNS))


NO_QV = qv_frame({})
NO_TITLES = titles_frame({})
NO_FALLBACK = fallback_frame({})


# --- parsing the QV code ------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected", "year"),
    [
        ("196", (1.0, 0.0, 0.0, 0.0), 1965.0),
        ("191", (1.0, 0.0, 0.0, 0.0), 1915.0),
        ("197", (0.0, 1.0, 0.0, 0.0), 1975.0),
        ("198", (0.0, 1.0, 0.0, 0.0), 1985.0),
        ("199", (0.0, 0.0, 1.0, 0.0), 1995.0),
        ("200", (0.0, 0.0, 0.5, 0.5), 2005.0),
        ("201", (0.0, 0.0, 0.0, 1.0), 2015.0),
        ("202", (0.0, 0.0, 0.0, 1.0), 2025.0),
        ("PRE", (1.0, 0.0, 0.0, 0.0), 1900.0),
        (" 196 ", (1.0, 0.0, 0.0, 0.0), 1965.0),
        ("pre", (1.0, 0.0, 0.0, 0.0), 1900.0),
    ],
)
def test_a_known_code_reads_as_its_decade_shares(code, expected, year):
    out = qv_age_shares(pd.Series([code]))

    assert tuple(out.loc[0, list(AGE_SHARE_COLUMNS)]) == expected
    assert out.loc[0, "qv_year"] == year


@pytest.mark.parametrize("code", ["XXX", "AAA", "MIX", "", "   ", None, "19", "1960"])
def test_an_unknown_code_reads_as_no_age(code):
    out = qv_age_shares(pd.Series([code], dtype=object))

    assert out.loc[0].isna().all()


def test_the_shares_keep_the_index_of_the_codes():
    codes = pd.Series(["196", "XXX"], index=[7, 3])

    out = qv_age_shares(codes)

    assert out.index.tolist() == [7, 3]
    assert list(out.columns) == [*AGE_SHARE_COLUMNS, "qv_year"]


def test_no_codes_give_an_empty_frame_with_the_columns():
    out = qv_age_shares(pd.Series([], dtype=object))

    assert out.empty
    assert list(out.columns) == [*AGE_SHARE_COLUMNS, "qv_year"]


# --- joining the roll to the properties ---------------------------------------


def test_the_oldest_rating_unit_on_a_property_stands_for_it():
    roll = roll_frame(
        ("17110", "302", "A", "199"),
        ("17110", "302", "B", "196"),
        ("17110", "303", None, "201"),
        ("17110", "304", None, "XXX"),
    )
    boundaries = pd.DataFrame(
        {
            "source_id": [1, 1, 2, 3, 4],
            "valuation_reference": [
                "17110-00302-A",
                "17110-00302-B",
                "17110-00303",
                "17110-00304",
                None,
            ],
        }
    )

    out = property_qv_ages(roll, boundaries)

    assert out.index.name == "property_id"
    assert out.index.tolist() == ["1", "2"]
    assert out.loc["1", "qv_year"] == 1965.0
    assert out.loc["1", "p_pre_1970"] == 1.0
    assert out.loc["2", "p_2005_on"] == 1.0


def test_a_missing_valuation_reference_joins_nothing():
    # The unit with no roll number has no reference; nor have boundaries 2, 3.
    roll = roll_frame(
        (None, "302", None, "PRE"),
        ("17110", "303", None, "199"),
    )
    boundaries = pd.DataFrame(
        {"source_id": [1, 2, 3], "valuation_reference": ["17110-00303", None, None]}
    )

    out = property_qv_ages(roll, boundaries)

    assert out.index.tolist() == ["1"]
    assert out.loc["1", "qv_year"] == 1995.0


# --- the lot's own date -------------------------------------------------------


def test_only_a_lots_own_title_or_plan_date_is_kept():
    lot_ages = pd.DataFrame(
        {
            "est_year": [1950.0, 1960.0, 1955.0, 1965.0, np.nan],
            "age_bin": ["pre_1970", "pre_1970", "pre_1970", "pre_1970", None],
            "age_basis": pd.Categorical(
                ["title", "dp", "infill_lot_1", "neighbourhood", None],
                categories=["title", "dp", "infill_lot_1", "neighbourhood"],
            ),
        },
        index=["T", "D", "I", "N", "U"],
    )

    out = own_lot_dates(lot_ages)

    assert out.index.tolist() == ["T", "D"]
    assert list(out.columns) == ["est_year", "age_bin"]


# --- combining the evidence ---------------------------------------------------


def test_a_dwelling_alone_gives_its_own_shares():
    qv = qv_frame({"P": (0.0, 0.0, 0.5, 0.5, 2005.0)})

    out = combine_wall_ages(qv, NO_TITLES, NO_FALLBACK, EXTENT_DEFAULT)

    assert tuple(out.loc["P", list(AGE_SHARE_COLUMNS)]) == (0.0, 0.0, 0.5, 0.5)
    assert out.loc["P", "age_basis"] == "qv"


def test_a_lot_the_gap_older_than_the_dwelling_mixes_half_and_half():
    qv = qv_frame({"P": (0.0, 0.0, 1.0, 0.0, 1995.0)})
    titles = titles_frame({"P": (1995.0 - BETA_LOT_OLDER_GAP_YEARS, "pre_1970")})

    out = combine_wall_ages(qv, titles, NO_FALLBACK, EXTENT_DEFAULT)

    assert tuple(out.loc["P", list(AGE_SHARE_COLUMNS)]) == (0.5, 0.0, 0.5, 0.0)
    assert out.loc["P", "age_basis"] == "qv_and_lot"


def test_a_lot_just_short_of_the_gap_older_is_not_used():
    qv = qv_frame({"P": (0.0, 0.0, 1.0, 0.0, 1995.0)})
    titles = titles_frame({"P": (1995.0 - BETA_LOT_OLDER_GAP_YEARS + 0.5, "1970_1991")})

    out = combine_wall_ages(qv, titles, NO_FALLBACK, EXTENT_DEFAULT)

    assert tuple(out.loc["P", list(AGE_SHARE_COLUMNS)]) == (0.0, 0.0, 1.0, 0.0)
    assert out.loc["P", "age_basis"] == "qv"


def test_the_gap_can_be_set():
    qv = qv_frame({"P": (0.0, 0.0, 1.0, 0.0, 1995.0)})
    titles = titles_frame({"P": (1985.0, "1970_1991")})

    out = combine_wall_ages(
        qv, titles, NO_FALLBACK, EXTENT_DEFAULT, lot_older_gap_years=10.0
    )

    assert out.loc["P", "age_basis"] == "qv_and_lot"


def test_a_dwelling_older_than_its_lot_ignores_the_lot():
    qv = qv_frame({"P": (1.0, 0.0, 0.0, 0.0, 1955.0)})
    titles = titles_frame({"P": (1998.0, "1992_2004")})

    out = combine_wall_ages(qv, titles, NO_FALLBACK, EXTENT_DEFAULT)

    assert tuple(out.loc["P", list(AGE_SHARE_COLUMNS)]) == (1.0, 0.0, 0.0, 0.0)
    assert out.loc["P", "age_basis"] == "qv"


def test_a_lot_alone_gives_its_bin():
    titles = titles_frame({"P": (1980.0, "1970_1991")})
    fallback = fallback_frame({"P": (0.25, 0.25, 0.25, 0.25)})

    out = combine_wall_ages(NO_QV, titles, fallback, EXTENT_DEFAULT)

    assert tuple(out.loc["P", list(AGE_SHARE_COLUMNS)]) == (0.0, 1.0, 0.0, 0.0)
    assert out.loc["P", "age_basis"] == "title"


def test_a_lot_with_a_categorical_bin_is_read():
    titles = titles_frame({"P": (2010.0, "2005_on")})
    titles["age_bin"] = pd.Categorical(
        titles["age_bin"], categories=["pre_1970", "1970_1991", "1992_2004", "2005_on"]
    )

    out = combine_wall_ages(NO_QV, titles, NO_FALLBACK, EXTENT_DEFAULT)

    assert out.loc["P", "p_2005_on"] == 1.0


def test_neither_dated_takes_the_suburb_then_the_extent():
    fallback = fallback_frame(
        {"S": (0.5, 0.2, 0.2, 0.1), "N": (np.nan, np.nan, np.nan, np.nan)}
    )

    out = combine_wall_ages(NO_QV, NO_TITLES, fallback, EXTENT_DEFAULT)

    assert out.loc["S", list(AGE_SHARE_COLUMNS)].tolist() == pytest.approx(
        [0.5, 0.2, 0.2, 0.1]
    )
    assert out.loc["S", "age_basis"] == "suburb"
    assert out.loc["N", list(AGE_SHARE_COLUMNS)].tolist() == pytest.approx(
        EXTENT_DEFAULT.tolist()
    )
    assert out.loc["N", "age_basis"] == "extent"


def test_every_row_sums_to_one_and_names_a_basis():
    qv = qv_frame(
        {"A": (0.0, 0.0, 0.5, 0.5, 2005.0), "B": (0.0, 0.0, 1.0, 0.0, 1995.0)}
    )
    titles = titles_frame({"B": (1950.0, "pre_1970"), "C": (1980.0, "1970_1991")})
    # Rounded to three places, as the suburb table is written.
    fallback = fallback_frame({"D": (0.334, 0.333, 0.333, 0.001), "E": (np.nan,) * 4})

    out = combine_wall_ages(qv, titles, fallback, EXTENT_DEFAULT)

    assert sorted(out.index) == ["A", "B", "C", "D", "E"]
    assert out.index.name == "property_id"
    np.testing.assert_allclose(out[list(AGE_SHARE_COLUMNS)].sum(axis=1), 1.0)
    assert set(out["age_basis"]) == set(AGE_BASES)


def test_an_unknown_title_bin_is_refused():
    titles = titles_frame({"P": (1980.0, "1980s")})

    with pytest.raises(ValueError, match="1980s"):
        combine_wall_ages(NO_QV, titles, NO_FALLBACK, EXTENT_DEFAULT)


def test_a_default_not_summing_to_one_is_refused():
    with pytest.raises(ValueError, match="sum to 1"):
        combine_wall_ages(NO_QV, NO_TITLES, NO_FALLBACK, EXTENT_DEFAULT * 2)


# --- the script ---------------------------------------------------------------


def boundaries_frame():
    """Two stacked unit titles, two freehold titles and a road parcel."""
    stack = box(X0, Y0 - 5, X0 + 20, Y0 + 5)
    return gpd.GeoDataFrame(
        {
            "source_id": ["U2", "U1", "F1", "F2", "R1"],
            "source": [
                "NZ Unit of Property",
                "NZ Unit of Property",
                "NZ Property Titles",
                "NZ Property Titles",
                "NZ Primary Parcels - Road",
            ],
            "valuation_reference": [
                "17110-00302-A",
                "17110-00302-B",
                "17110-00303",
                "17110-00304",
                None,
            ],
        },
        geometry=[
            stack,
            stack,
            box(X0 + 20, Y0 - 5, X0 + 40, Y0 + 5),
            box(X0 + 40, Y0 - 5, X0 + 60, Y0 + 5),
            box(X0 + 60, Y0 - 5, X0 + 80, Y0 + 5),
        ],
        crs=CRS,
    )


@pytest.fixture
def redirected_script(tmp_path, monkeypatch):
    """Point gen_wall_age.py at a synthetic roll, step 8 ages and suburb table.

    The stack has a 1990s dwelling on a 1950s lot; F1 has no dwelling age and
    a 1980s lot; F2 has neither and sits in a suburb with no row of the table.
    """
    roll = roll_frame(
        ("17110", "302", "A", "199"),
        ("17110", "302", "B", "XXX"),
        ("17110", "303", None, "XXX"),
    )
    ages = pd.DataFrame(
        {
            "claim_id": ["U1", "F1", "F2", "Z9"],
            "territorial_authority": ["Wellington City"] * 4,
            "suburb_locality": ["Kelburn", "Kelburn", "Nowhere", "Kelburn"],
            "est_year": [1950.0, 1982.0, np.nan, 1960.0],
            "age_bin": pd.Categorical(
                ["pre_1970", "1970_1991", None, "pre_1970"],
                categories=["pre_1970", "1970_1991", "1992_2004", "2005_on"],
                ordered=True,
            ),
            "age_basis": pd.Categorical(
                ["title", "dp", None, "title"],
                categories=["title", "dp", "infill_lot_1", "neighbourhood"],
            ),
        }
    )
    suburbs = pd.DataFrame(
        {
            "territorial_authority": ["Wellington City", "Wellington City"],
            "suburb_locality": ["Kelburn", "Karori"],
            "properties": [100, 300],
            "undated": [0, 0],
            "p_pre_1970": [0.6, 0.2],
            "p_1970_1991": [0.2, 0.4],
            "p_1992_2004": [0.1, 0.2],
            "p_2005_on": [0.1, 0.2],
        }
    )
    ages_file = tmp_path / "rwt-age.geoparquet"
    suburb_file = tmp_path / "rwt-age-by-suburb.csv"
    ages.to_parquet(ages_file)
    suburbs.to_csv(suburb_file, index=False)
    monkeypatch.setattr(script, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(script, "dem_bbox", lambda *, extent: (0.0, 0.0, 1.0, 1.0))
    monkeypatch.setattr(
        script, "get_nz_property_boundaries", lambda **_: boundaries_frame()
    )
    monkeypatch.setattr(script, "get_qv_rating_roll", lambda: roll)
    monkeypatch.setattr(script, "rwt_age_path", lambda *, extent: ages_file)
    monkeypatch.setattr(script, "table_path", lambda level, *, extent: suburb_file)
    return tmp_path


def test_gen_wall_age_main_writes_one_row_per_claimable_property(
    tmp_path, redirected_script
):
    script.main(extent="wlg-pilot", age_extent="full")

    out_path = script.wall_age_path(extent="wlg-pilot")
    assert out_path == tmp_path / "exposure" / "wall-age-pilot.parquet"
    written = pd.read_parquet(out_path)
    assert sorted(written.index) == ["F1", "F2", "U1", "U2"]
    assert written["age_basis"].to_dict() == {
        "F1": "title",
        "F2": "extent",
        "U1": "title",
        "U2": "qv_and_lot",
    }
    assert written.loc["U2", "p_pre_1970"] == 0.5
    assert written.loc["U2", "p_1992_2004"] == 0.5
    assert written.loc["F1", "p_1970_1991"] == 1.0
    # Only Kelburn holds the extent's properties, so it alone sets the default.
    assert written.loc["F2", list(AGE_SHARE_COLUMNS)].tolist() == pytest.approx(
        [0.6, 0.2, 0.1, 0.1]
    )
    np.testing.assert_allclose(written[list(AGE_SHARE_COLUMNS)].sum(axis=1), 1.0)


def test_a_missing_step_8_output_says_to_run_it(
    tmp_path, redirected_script, monkeypatch
):
    monkeypatch.setattr(
        script, "rwt_age_path", lambda *, extent: tmp_path / "missing.geoparquet"
    )

    with pytest.raises(FileNotFoundError, match=r"gen_rwt_age\.py"):
        script.main(extent="wlg-pilot", age_extent="full")


@pytest.mark.parametrize("basis", ["neighbourhood", "infill_lot_1"])
def test_a_neighbourhood_year_goes_to_the_suburb_not_the_title(
    tmp_path, redirected_script, basis
):
    ages_file = tmp_path / "rwt-age.geoparquet"
    ages = pd.read_parquet(ages_file)
    ages.loc[ages["claim_id"] == "F1", "age_basis"] = basis
    ages.to_parquet(ages_file)

    script.main(extent="wlg-pilot", age_extent="full")

    written = pd.read_parquet(script.wall_age_path(extent="wlg-pilot"))
    assert written.loc["F1", "age_basis"] == "suburb"
    assert written.loc["F1", list(AGE_SHARE_COLUMNS)].tolist() == pytest.approx(
        [0.6, 0.2, 0.1, 0.1]
    )


def test_an_infill_lot_with_a_dwelling_age_keeps_the_dwelling_alone(
    tmp_path, redirected_script
):
    # U1's lot is dated 1950 from its neighbours; its own dwelling is 1990s.
    ages_file = tmp_path / "rwt-age.geoparquet"
    ages = pd.read_parquet(ages_file)
    ages.loc[ages["claim_id"] == "U1", "age_basis"] = "infill_lot_1"
    ages.to_parquet(ages_file)

    script.main(extent="wlg-pilot", age_extent="full")

    written = pd.read_parquet(script.wall_age_path(extent="wlg-pilot"))
    assert written.loc["U2", "age_basis"] == "qv"
    assert written.loc["U2", "p_1992_2004"] == 1.0
