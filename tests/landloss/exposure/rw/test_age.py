"""Tests for the retaining wall age inferred from property titles."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from landloss.exposure.rw import age

# --- dates and bins ------------------------------------------------------------


def test_a_date_becomes_a_decimal_year():
    years = age.decimal_year(pd.Series(["1939-06-29", "1992-07-01", "2005-01-01"]))

    assert years.tolist() == pytest.approx([1939.49, 1992.50, 2005.0], abs=0.01)


def test_an_unreadable_date_becomes_null():
    years = age.decimal_year(pd.Series(["not a date", None]))

    assert years.isna().all()


def test_each_bin_opens_on_its_start_year():
    bins = age.age_bin([1969.99, 1970.0, 1992.49, 1992.5, 2004.99, 2005.0])

    assert list(bins) == [
        "pre_1970",
        "1970_1991",
        "1970_1991",
        "1992_2004",
        "1992_2004",
        "2005_on",
    ]


def test_a_null_year_has_no_bin():
    bins = age.age_bin([np.nan, 1950.0])

    assert pd.isna(bins[0])
    assert bins[1] == "pre_1970"


def test_the_bins_are_ordered_oldest_first():
    bins = age.age_bin([2010.0])

    assert list(bins.categories) == list(age.AGE_BINS)
    assert bins.ordered


def test_the_1990s_split_a_quarter_and_three_quarters():
    shares = age.bin_shares_of_span(1990.0, 2000.0)

    assert shares.tolist() == pytest.approx([0.0, 0.25, 0.75, 0.0])


def test_the_2000s_split_evenly():
    shares = age.bin_shares_of_span(2000.0, 2010.0)

    assert shares.tolist() == pytest.approx([0.0, 0.0, 0.5, 0.5])


def test_a_span_inside_one_bin_is_wholly_that_bin():
    shares = age.bin_shares_of_span(1950.0, 1960.0)

    assert shares.tolist() == pytest.approx([1.0, 0.0, 0.0, 0.0])


def test_an_empty_span_is_refused():
    with pytest.raises(ValueError, match="end after"):
        age.bin_shares_of_span(1990.0, 1990.0)


# --- titles --------------------------------------------------------------------


def test_a_comma_separated_title_list_becomes_one_row_per_title():
    properties = pd.DataFrame(
        {"claim_id": ["a", "b", "c"], "title_no": ["WN1/1, WN2/2", "123", None]}
    )

    titles = age.split_title_numbers(properties, "claim_id")

    assert titles.to_dict("records") == [
        {"claim_id": "a", "title_no": "WN1/1"},
        {"claim_id": "a", "title_no": "WN2/2"},
        {"claim_id": "b", "title_no": "123"},
    ]


def test_a_volume_and_folio_reference_is_a_paper_title():
    paper = age.is_paper_title(pd.Series(["WN471/294", "1244058", None]))

    assert paper.tolist() == [True, False, False]


# --- plans ---------------------------------------------------------------------


def test_every_deposited_plan_in_a_legal_description_is_found():
    plans = age.dp_numbers(
        pd.Series(["Lot 4 DP 9789, Part Lot 1 DP 9535", "Part Section 36 Karori DIST"])
    )

    assert plans.tolist() == [[9535, 9789], []]


def test_only_one_whole_lot_on_one_plan_is_a_single_lot():
    lots = age.single_lots(
        pd.Series(
            ["Lot 1 DP 306105", "Lot 2 DP 9789, Lot 3 DP 9789", "Part Lot 1 DP 3"]
        )
    )

    assert lots["lot"].tolist()[0] == 1
    assert lots["dp"].tolist()[0] == 306105
    assert lots["lot"].isna().tolist() == [False, True, True]


def plan_rows(plans_and_years, district="Wellington"):
    """Boundary rows and titles for one single-titled lot per plan."""
    boundaries = pd.DataFrame(
        {
            "title_no": [f"WN{plan}/1" for plan, _ in plans_and_years],
            "legal_description": [f"Lot 1 DP {plan}" for plan, _ in plans_and_years],
        }
    )
    titles = pd.DataFrame(
        {
            "title_no": boundaries["title_no"],
            "issue_date": [f"{year}-01-01" for _, year in plans_and_years],
            "land_district": district,
        }
    )
    return boundaries, titles


def test_the_plan_dates_rise_with_the_plan_number():
    # A reissued title on plan 300 makes its earliest title look later than
    # plan 400's; the fit must not follow it.
    years = [(100, 1920), (200, 1930), (300, 1985), (400, 1950), (500, 1960)]
    boundaries, titles = plan_rows(years)

    fit = age.fit_dp_years(boundaries, age.title_issue_years(titles))

    assert fit["dp_year"].is_monotonic_increasing
    assert fit.set_index("dp").loc[300, "dp_year"] < 1985


def test_a_multi_title_row_does_not_date_a_plan():
    boundaries, titles = plan_rows([(100, 1920), (200, 1930)])
    boundaries.loc[0, "title_no"] = "WN100/1, WN999/9"

    fit = age.fit_dp_years(boundaries, age.title_issue_years(titles))

    assert fit["dp"].tolist() == [200]


def test_each_land_district_is_fitted_on_its_own():
    wellington, wellington_titles = plan_rows([(100, 1920)], "Wellington")
    canterbury, canterbury_titles = plan_rows([(100, 1960)], "Canterbury")
    canterbury["title_no"] = "CB100/1"
    canterbury_titles["title_no"] = "CB100/1"

    fit = age.fit_dp_years(
        pd.concat([wellington, canterbury]),
        age.title_issue_years(pd.concat([wellington_titles, canterbury_titles])),
    )

    years = fit.set_index("land_district")["dp_year"]
    assert years["Wellington"] == pytest.approx(1920, abs=0.1)
    assert years["Canterbury"] == pytest.approx(1960, abs=0.1)


def test_a_plan_is_dated_by_interpolation_and_clamped_beyond_the_fit():
    fit = pd.DataFrame(
        {"land_district": "Wellington", "dp": [100, 300], "dp_year": [1920.0, 1940.0]}
    )

    years = age.dp_years(
        pd.Series(["Wellington", "Wellington", "Otago", "Wellington"]),
        pd.Series([200, 900, 200, np.nan]),
        fit,
    )

    assert years.tolist()[:2] == pytest.approx([1930.0, 1940.0])
    assert np.isnan(years.tolist()[2])
    assert np.isnan(years.tolist()[3])


# --- claims --------------------------------------------------------------------


def square(x, y, size=10.0):
    return Polygon([(x, y), (x + size, y), (x + size, y + size), (x, y + size)])


def test_every_title_on_a_stacked_footprint_is_recovered():
    boundaries = gpd.GeoDataFrame(
        {"title_no": ["WN1/1", "WN1/2", "WN2/1"]},
        geometry=[square(0, 0), square(0, 0), square(50, 0)],
        crs="EPSG:2193",
    )
    claims = gpd.GeoDataFrame(
        {"claim_id": ["a", "b"]},
        geometry=[square(0, 0), square(50, 0)],
        crs="EPSG:2193",
    )

    rows = age.footprint_rows(boundaries, claims, "claim_id", ["title_no"])

    assert sorted(map(tuple, rows.to_numpy())) == [
        ("a", "WN1/1"),
        ("a", "WN1/2"),
        ("b", "WN2/1"),
    ]


def test_a_claim_is_dated_by_its_earliest_title():
    claim_titles = pd.DataFrame(
        {"claim_id": ["a", "a", "b"], "title_no": ["WN1/1", "WN1/2", "999"]}
    )
    titles = pd.DataFrame(
        {
            "title_no": ["WN1/1", "WN1/2"],
            "issue_date": ["1980-01-01", "1950-01-01"],
            "land_district": "Wellington",
        }
    )

    dates = age.claim_title_dates(
        claim_titles, age.title_issue_years(titles), "claim_id"
    )

    assert dates.loc["a", "first_title_no"] == "WN1/2"
    assert dates.loc["a", "title_year"] == pytest.approx(1950.0)
    assert dates.loc["a", "title_count"] == 2
    assert "b" not in dates.index


def test_a_claim_is_put_in_the_suburb_most_of_its_addresses_are_in():
    claim_addresses = pd.DataFrame(
        {"claim_id": ["a", "a", "a", "b", "b"], "address_id": [1, 2, 3, 4, 5]}
    )
    addresses = pd.DataFrame(
        {
            "address_id": [1, 2, 3, 4, 5],
            "territorial_authority": "Wellington City",
            "suburb_locality": [
                "Karori",
                "Karori",
                "Northland",
                "Kelburn",
                "Aro Valley",
            ],
        }
    )

    suburbs = age.claim_suburbs(claim_addresses, addresses, "claim_id")

    assert suburbs.loc["a", "suburb_locality"] == "Karori"
    # A tie goes to the first suburb alphabetically.
    assert suburbs.loc["b", "suburb_locality"] == "Aro Valley"


def test_bin_shares_sum_to_one_over_the_dated_properties():
    ages = pd.DataFrame(
        {
            "suburb_locality": ["Karori"] * 4 + ["Kelburn"],
            "age_bin": pd.Categorical(
                ["pre_1970", "pre_1970", "2005_on", None, "1970_1991"],
                categories=age.AGE_BINS,
            ),
        }
    )

    table = age.bin_shares(ages, ["suburb_locality"]).set_index("suburb_locality")

    assert table.loc["Karori", "properties"] == 4
    assert table.loc["Karori", "undated"] == 1
    assert table.loc["Karori", "p_pre_1970"] == pytest.approx(2 / 3)
    assert table.loc["Karori", "p_1992_2004"] == 0
    shares = table[[f"p_{name}" for name in age.AGE_BINS]].sum(axis=1)
    assert shares.tolist() == pytest.approx([1.0, 1.0])


def test_the_neighbourhood_year_leaves_the_property_itself_out():
    points = gpd.GeoSeries([Point(0, 0), Point(1, 0), Point(2, 0), Point(100, 0)])
    years = pd.Series([2020.0, 1920.0, 1940.0, np.nan])

    medians = age.neighbourhood_years(points, years, neighbours=2)

    # The first point's own 2020 is left out; the last point is undated itself
    # but still has dated neighbours.
    assert medians[0] == pytest.approx(1930.0)
    assert medians[3] == pytest.approx(1930.0)


def suburb():
    """Return a synthetic suburb in which each rule fires once.

    Twelve 1920s houses on DP 100 surround the properties under test, and a run
    of further plans dated 1930 to 2020 sits far away, so the plan dates have
    something to be fitted to.
    """
    rows = [
        (
            f"old{i}",
            f"WN100/{i}",
            "1925-01-01",
            f"Lot {i + 2} DP 100",
            "Freehold",
            square(20 * i, 0),
        )
        for i in range(12)
    ]
    rows += [
        # A 1985 paper title on a 1925 lot is a reissue: the plan's date.
        (
            "reissued",
            "WN30A/1",
            "1985-01-01",
            "Lot 30 DP 100",
            "Freehold",
            square(0, 20),
        ),
        # The same plan under an electronic title is a new estate: its own date.
        (
            "new_estate",
            "1234567",
            "2015-01-01",
            "Lot 31 DP 100",
            "Freehold",
            square(20, 20),
        ),
        # A unit title takes its own date even on an old plan.
        ("unit", "WN40B/1", "1995-01-01", "Lot 32 DP 100", "Unit", square(40, 20)),
        # A cross-lease follows the reissue rule like a freehold title.
        (
            "cross_lease",
            "WN41C/2",
            "1990-01-01",
            "Lot 33 DP 100",
            "Cross Lease",
            square(60, 20),
        ),
        # A two-lot infill plan: Lot 1 keeps the old house, Lot 2 is new.
        (
            "infill_1",
            "1300001",
            "2024-01-01",
            "Lot 1 DP 9000",
            "Freehold",
            square(80, 20),
        ),
        (
            "infill_2",
            "1300002",
            "2024-01-01",
            "Lot 2 DP 9000",
            "Freehold",
            square(100, 20),
        ),
        # Nothing to date it by.
        (
            "undated",
            None,
            None,
            "Part Section 5 Karori DIST",
            "Freehold",
            square(120, 20),
        ),
    ]
    rows += [
        (
            f"far{i}",
            f"WN{plan}/1",
            f"{1930 + 90 * i // 32}-01-01",
            f"Lot 1 DP {plan}",
            "Freehold",
            square(10_000 + 20 * i, 10_000),
        )
        for i, plan in enumerate(range(1000, 9000, 250))
    ]
    ids, title_nos, dates, legal, types, shapes = zip(*rows, strict=True)
    claims = gpd.GeoDataFrame(
        {
            "claim_id": ids,
            "title_no": title_nos,
            "legal_description": legal,
            "title_type": types,
        },
        geometry=list(shapes),
        crs="EPSG:2193",
    )
    titles = pd.DataFrame(
        {"title_no": title_nos, "issue_date": dates, "land_district": "Wellington"}
    ).dropna(subset=["title_no"])
    return claims, titles


@pytest.fixture
def suburb_ages():
    claims, titles = suburb()
    ages = age.infer_claim_ages(claims, claims, titles, id_column="claim_id")
    return ages.set_index("claim_id")


def test_a_reissued_paper_title_takes_its_plans_date(suburb_ages):
    row = suburb_ages.loc["reissued"]

    assert row["age_basis"] == "dp"
    assert row["age_bin"] == "pre_1970"


def test_an_electronic_title_on_an_old_plan_keeps_its_own_date(suburb_ages):
    row = suburb_ages.loc["new_estate"]

    assert row["age_basis"] == "title"
    assert row["est_year"] == pytest.approx(2015.0)


def test_a_unit_title_keeps_its_own_date(suburb_ages):
    row = suburb_ages.loc["unit"]

    assert row["age_basis"] == "title"
    assert row["age_bin"] == "1992_2004"


def test_a_reissued_cross_lease_takes_its_plans_date(suburb_ages):
    assert suburb_ages.loc["cross_lease", "age_basis"] == "dp"


def test_lot_1_of_an_infill_plan_takes_its_neighbours_date(suburb_ages):
    assert suburb_ages.loc["infill_1", "age_basis"] == "infill_lot_1"
    assert suburb_ages.loc["infill_1", "age_bin"] == "pre_1970"
    assert suburb_ages.loc["infill_2", "age_basis"] == "title"
    assert suburb_ages.loc["infill_2", "age_bin"] == "2005_on"


def test_a_property_with_nothing_to_date_it_takes_its_neighbours_date(suburb_ages):
    row = suburb_ages.loc["undated"]

    assert row["age_basis"] == "neighbourhood"
    assert row["age_bin"] == "pre_1970"


def test_every_claim_gets_a_row_in_order():
    claims, titles = suburb()

    ages = age.infer_claim_ages(claims, claims, titles, id_column="claim_id")

    assert ages["claim_id"].tolist() == claims["claim_id"].tolist()
    assert ages["age_bin"].notna().all()
