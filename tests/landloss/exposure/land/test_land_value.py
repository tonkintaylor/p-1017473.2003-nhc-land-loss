"""Tests for the land value model.

The assets these functions read by default are written by hand and live under
``src/landloss/io/assets``. Nothing here touches them: every fixture is built in
memory or written to ``tmp_path``, so the tests describe the model rather than
the particular numbers that happen to be in the asset this week.
"""

import datetime

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from landloss.exposure.land.accessibility import (
    GRAVITY_COLUMN,
    STATION_DISTANCE_COLUMN,
)
from landloss.exposure.land.land_value import (
    SLOPE_COLUMN,
    TERRAIN_GROUP_COLUMNS,
    TOPOGRAPHIC_POSITION_COLUMN,
    accessibility_modifier,
    estimate_land_value,
    index_base_rates,
    load_base_rates,
    load_factors,
    solve_normalising_constant,
    summarise_by_suburb,
    ta_mean_land_value,
    terrain_modifier,
)
from landloss.exposure.land.landform import ELEVATED_FLAT, FLAT, HILL

# The published QV anchors for the four study area territorial authorities, with
# an index onto the common valuation date. Real figures, so that a number that
# looks wrong in a failure message is recognisable.
ANCHORS = [
    ("044", "Porirua City", "2025-09-01", 21481, 830_000, 420_000, 1.000, 600),
    ("045", "Upper Hutt City", "2025-06-01", 18474, 776_000, 438_000, 1.010, 700),
    ("046", "Lower Hutt City", "2025-08-01", 43576, 775_000, 415_000, 1.005, 550),
    ("047", "Wellington City", "2024-09-01", 82591, 1_086_000, 621_000, 1.020, 450),
]


@pytest.fixture
def base_rates():
    """The published anchors, as load_base_rates would return them."""
    return pd.DataFrame(
        ANCHORS,
        columns=[
            "ta_code",
            "ta_name",
            "valuation_date",
            "rating_units",
            "avg_capital_value_nzd",
            "avg_land_value_nzd",
            "index_to_2025_09",
            "median_lot_size_m2",
        ],
    ).assign(source_url="https://example.invalid/revaluation")


@pytest.fixture
def factors():
    """Model parameters with a clip band wide enough that it never binds."""
    return {
        "landform_factor_hill": 0.85,
        "landform_factor_flat": 1.15,
        "landform_factor_elevated_flat": 1.05,
        "rate_clip_min_multiple": 0.25,
        "rate_clip_max_multiple": 4.0,
    }


def make_addresses(rows: list[tuple[str, str, str]]):
    """Build an address frame from (territorial authority, suburb, landform) rows."""
    return gpd.GeoDataFrame(
        {
            "address_id": list(range(len(rows))),
            "territorial_authority": [row[0] for row in rows],
            "suburb_locality": [row[1] for row in rows],
            "landform_class": [row[2] for row in rows],
        },
        geometry=[Point(index, index) for index in range(len(rows))],
        crs="EPSG:2193",
    )


@pytest.fixture
def addresses():
    """A mixed population: four TAs, differing sizes and differing landform mixes."""
    return make_addresses(
        [
            ("Wellington City", "Kelburn", HILL),
            ("Wellington City", "Kelburn", HILL),
            ("Wellington City", "Kilbirnie", FLAT),
            ("Lower Hutt City", "Petone", FLAT),
            ("Lower Hutt City", "Petone", FLAT),
            ("Lower Hutt City", "Wainuiomata", HILL),
            ("Lower Hutt City", "Wainuiomata", HILL),
            ("Porirua City", "Titahi Bay", FLAT),
            ("Upper Hutt City", "Totara Park", HILL),
        ]
    )


def indexed_average(base_rates: pd.DataFrame, ta_name: str) -> float:
    """Return one TA's published average, indexed onto the common valuation date."""
    indexed = index_base_rates(base_rates).set_index("ta_name")
    return float(indexed.loc[ta_name, "indexed_land_value_nzd"])


# --- reading the assets -------------------------------------------------------


def test_the_base_rates_round_trip_through_a_csv(tmp_path, base_rates) -> None:
    """The anchors are held as a CSV a valuer can open and check against QV."""
    path = tmp_path / "land-value-base-rates.csv"
    base_rates.to_csv(path, index=False)

    loaded = load_base_rates(path)

    assert list(loaded["ta_name"]) == list(base_rates["ta_name"])
    assert list(loaded["avg_land_value_nzd"]) == list(base_rates["avg_land_value_nzd"])


def test_a_ta_code_keeps_its_leading_zero(tmp_path, base_rates) -> None:
    """Porirua is "044"; read as a number it becomes 44 and stops matching."""
    path = tmp_path / "land-value-base-rates.csv"
    base_rates.to_csv(path, index=False)

    loaded = load_base_rates(path)

    assert "044" in set(loaded["ta_code"])


def test_the_valuation_date_is_parsed_to_a_date(tmp_path, base_rates) -> None:
    """The four councils revalue on different dates, so the date has to be usable."""
    path = tmp_path / "land-value-base-rates.csv"
    base_rates.to_csv(path, index=False)

    loaded = load_base_rates(path)

    assert isinstance(loaded["valuation_date"].iloc[0], datetime.date)


def test_a_missing_territorial_authority_is_named(tmp_path, base_rates) -> None:
    """Silently modelling three of the four TAs would understate the whole study."""
    path = tmp_path / "land-value-base-rates.csv"
    base_rates[base_rates["ta_code"] != "045"].to_csv(path, index=False)

    with pytest.raises(ValueError, match="045"):
        load_base_rates(path)


def test_the_factors_load_as_a_plain_mapping_of_floats(tmp_path) -> None:
    """The basis column documents each number for a reader; the model wants floats."""
    path = tmp_path / "land-value-factors.csv"
    pd.DataFrame(
        {
            "parameter": ["landform_factor_hill", "rate_clip_max_multiple"],
            "value": ["0.85", "4"],
            "basis": ["Judgement, hill sections", "Judgement"],
        }
    ).to_csv(path, index=False)

    loaded = load_factors(path)

    assert loaded == {"landform_factor_hill": 0.85, "rate_clip_max_multiple": 4.0}


# --- the packaged assets ------------------------------------------------------
#
# The tests above describe the model against fixtures, on purpose, so that they
# do not have to be edited every time a judgement number is retuned. That leaves
# one thing nothing else covers: whether the asset the model reads by default
# still carries the parameters the code asks it for. The names below are a
# contract between a CSV a reviewer edits by hand and code that reads it by key,
# and a row renamed on one side of that contract is not a failure anybody sees
# until a run reaches the line that wanted it. So these three name no values at
# all -- they only insist the packaged assets can still be valued against.


def test_the_packaged_assets_value_every_landform_class_in_every_authority() -> None:
    """The default path is the one every script takes, and no fixture exercises it."""
    addresses = make_addresses(
        [
            (ta_name, "Somewhere", landform)
            for _, ta_name, *_ in ANCHORS
            for landform in (HILL, FLAT, ELEVATED_FLAT)
        ]
    )

    valued = estimate_land_value(addresses)

    assert not valued["land_value_nzd"].isna().any()
    assert (valued["land_value_nzd"] > 0).all()


def test_the_packaged_factors_carry_what_the_terrain_modifier_reads() -> None:
    """The four coefficients are read only once a run has a DEM behind it."""
    addresses = make_terrain_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 2.0, 1.0),
            ("Porirua City", "Titahi Bay", FLAT, 12.0, -3.0),
        ]
    )

    modifier = terrain_modifier(addresses, load_factors())

    assert modifier.iloc[0] > modifier.iloc[1]


def test_the_packaged_factors_carry_what_the_accessibility_modifier_reads() -> None:
    """The five accessibility parameters are read only once s2 has been run."""
    addresses = make_accessibility_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 0.4, 300.0),
            ("Porirua City", "Titahi Bay", FLAT, 0.1, 5000.0),
        ]
    )

    modifier = accessibility_modifier(addresses, load_factors())

    assert modifier.iloc[0] > modifier.iloc[1]


def test_the_packaged_factors_carry_the_two_rows_the_step_scripts_read() -> None:
    """The elevated flat promotion lives in a script, so nothing else guards these."""
    factors = load_factors()

    assert "elevated_flat_min_topographic_position_m" in factors
    assert "topographic_position_window_m" in factors


# --- indexing -----------------------------------------------------------------


def test_indexing_adds_a_column_without_touching_the_published_figure(
    base_rates,
) -> None:
    """A reviewer has to see both what QV published and what the model used."""
    indexed = index_base_rates(base_rates)

    assert list(indexed["avg_land_value_nzd"]) == list(base_rates["avg_land_value_nzd"])
    assert "indexed_land_value_nzd" in indexed.columns


def test_indexing_applies_the_index_factor(base_rates) -> None:
    """Wellington was valued a year early, so its average is carried forward."""
    indexed = index_base_rates(base_rates).set_index("ta_name")

    assert indexed.loc["Wellington City", "indexed_land_value_nzd"] == pytest.approx(
        621_000 * 1.020
    )


def test_indexing_does_not_modify_the_caller_s_frame(base_rates) -> None:
    """Indexing returns a copy, so the anchors can be re-used unchanged."""
    index_base_rates(base_rates)

    assert "indexed_land_value_nzd" not in base_rates.columns


# --- the normalising constant -------------------------------------------------


def test_the_constant_puts_the_mean_on_target() -> None:
    """This is the arithmetic the whole model rests on."""
    constant = solve_normalising_constant([0.85, 1.15], target_mean=500_000)

    assert constant == pytest.approx(500_000 / 1.0)


def test_the_constant_does_not_depend_on_how_many_addresses_there_are() -> None:
    """A TA with more addresses is not worth more per address than a small one."""
    small = solve_normalising_constant([0.85, 1.15], target_mean=500_000)
    large = solve_normalising_constant([0.85] * 500 + [1.15] * 500, 500_000)

    assert large == pytest.approx(small)


def test_the_constant_does_depend_on_the_mix_of_factors() -> None:
    """A TA that is mostly hill has to scale up to reach the same published mean."""
    balanced = solve_normalising_constant([0.85, 1.15], target_mean=500_000)
    hilly = solve_normalising_constant([0.85, 0.85, 0.85, 1.15], 500_000)

    assert hilly > balanced


def test_an_empty_set_of_factors_is_rejected() -> None:
    """There is nothing to spread the published average across, so this is a bug."""
    with pytest.raises(ValueError, match="empty"):
        solve_normalising_constant([], target_mean=500_000)


def test_a_non_positive_mean_factor_is_rejected() -> None:
    """A zero or negative mean means the factors asset is wrong, not the data."""
    with pytest.raises(ValueError, match="positive"):
        solve_normalising_constant([1.0, -1.0], target_mean=500_000)


# --- valuing addresses --------------------------------------------------------


def test_the_mean_value_in_each_ta_is_the_published_average(
    addresses, base_rates, factors
) -> None:
    """The one property the model guarantees: judgement moves value, never totals."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    means = valued.groupby("territorial_authority")["land_value_nzd"].mean()

    for ta_name, modelled_mean in means.items():
        assert modelled_mean == pytest.approx(indexed_average(base_rates, ta_name))


def test_clipping_does_not_break_the_ta_mean(addresses, base_rates) -> None:
    """The clip is a sanity bound on one address, not a licence to lose value."""
    # A hill factor far enough below the clip floor that every hill address is
    # pushed back up to it, which is what makes the re-solve do some work.
    binding = {
        "landform_factor_hill": 0.20,
        "landform_factor_flat": 1.00,
        "landform_factor_elevated_flat": 1.05,
        "rate_clip_min_multiple": 0.50,
        "rate_clip_max_multiple": 2.00,
    }

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=binding)

    hutt = valued[valued["territorial_authority"] == "Lower Hutt City"]
    assert hutt["land_value_nzd"].mean() == pytest.approx(
        indexed_average(base_rates, "Lower Hutt City")
    )


def test_the_clip_floor_is_respected(addresses, base_rates) -> None:
    """The clip is there so that no single address is modelled at an absurd value."""
    binding = {
        "landform_factor_hill": 0.20,
        "landform_factor_flat": 1.00,
        "landform_factor_elevated_flat": 1.05,
        "rate_clip_min_multiple": 0.50,
        "rate_clip_max_multiple": 2.00,
    }

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=binding)

    hutt = valued[valued["territorial_authority"] == "Lower Hutt City"]
    floor = 0.50 * indexed_average(base_rates, "Lower Hutt City")
    assert hutt["land_value_nzd"].min() >= floor - 1e-6


def test_a_flat_address_is_worth_more_than_a_hill_address_in_the_same_ta(
    base_rates, factors
) -> None:
    """The landform factors are the whole reason two addresses differ in Phase 1."""
    addresses = make_addresses(
        [("Porirua City", "Titahi Bay", FLAT), ("Porirua City", "Titahi Bay", HILL)]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    assert valued["land_value_nzd"].iloc[0] > valued["land_value_nzd"].iloc[1]


def test_the_rate_is_the_value_over_the_assumed_lot_size(
    addresses, base_rates, factors
) -> None:
    """Lot size is a per-TA median, so the rate is reported next to the size it used."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    expected = valued["land_value_nzd"] / valued["assumed_lot_size_m2"]
    assert valued["land_rate_nzd_per_m2"].tolist() == pytest.approx(expected.tolist())


def test_the_assumed_lot_size_comes_from_the_matching_ta(
    addresses, base_rates, factors
) -> None:
    """A Wellington address must not be sized with Porirua's median section."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    wellington = valued[valued["territorial_authority"] == "Wellington City"]
    assert set(wellington["assumed_lot_size_m2"]) == {450.0}


def test_a_missing_column_is_named(base_rates, factors) -> None:
    """Failing here beats producing a column of NaN that nobody notices."""
    addresses = make_addresses([("Porirua City", "Titahi Bay", FLAT)]).drop(
        columns=["landform_class"]
    )

    with pytest.raises(ValueError, match="landform_class"):
        estimate_land_value(addresses, base_rates=base_rates, factors=factors)


def test_a_missing_factor_is_named_rather_than_raising_a_bare_key_error(
    base_rates, factors
) -> None:
    """The factors are a hand-edited CSV, so a typo in one has to say which row."""
    addresses = make_addresses([("Porirua City", "Titahi Bay", FLAT)])
    without_elevated_flat = {
        name: value
        for name, value in factors.items()
        if name != "landform_factor_elevated_flat"
    }

    with pytest.raises(ValueError, match="landform_factor_elevated_flat"):
        estimate_land_value(
            addresses, base_rates=base_rates, factors=without_elevated_flat
        )


def test_an_unknown_territorial_authority_is_rejected(base_rates, factors) -> None:
    """Dropping the address would quietly shrink the exposure the study reports."""
    addresses = make_addresses([("Kapiti Coast District", "Paraparaumu", FLAT)])

    with pytest.raises(ValueError, match="Kapiti Coast District"):
        estimate_land_value(addresses, base_rates=base_rates, factors=factors)


def test_an_unknown_landform_class_is_rejected(base_rates, factors) -> None:
    """There is no factor to value it with, and no factor means no defensible value."""
    addresses = make_addresses([("Porirua City", "Titahi Bay", "swamp")])

    with pytest.raises(ValueError, match="swamp"):
        estimate_land_value(addresses, base_rates=base_rates, factors=factors)


def test_an_empty_address_frame_is_handled(base_rates, factors) -> None:
    """A pilot extent can contain no addresses at all, and that is not an error."""
    valued = estimate_land_value(
        make_addresses([]), base_rates=base_rates, factors=factors
    )

    assert len(valued) == 0
    assert "land_value_nzd" in valued.columns


def test_the_input_is_not_modified(addresses, base_rates, factors) -> None:
    """Valuing returns a copy, leaving the caller's frame untouched."""
    estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    assert "land_value_nzd" not in addresses.columns


# --- the terrain modifier -----------------------------------------------------


def make_terrain_addresses(rows: list[tuple[str, str, str, float, float]]):
    """Build an address frame from (TA, suburb, landform, slope, position) rows."""
    return gpd.GeoDataFrame(
        {
            "address_id": list(range(len(rows))),
            "territorial_authority": [row[0] for row in rows],
            "suburb_locality": [row[1] for row in rows],
            "landform_class": [row[2] for row in rows],
            SLOPE_COLUMN: [row[3] for row in rows],
            TOPOGRAPHIC_POSITION_COLUMN: [row[4] for row in rows],
        },
        geometry=[Point(index, index) for index in range(len(rows))],
        crs="EPSG:2193",
    )


@pytest.fixture
def terrain_factors(factors):
    """The Phase 1 parameters plus the terrain coefficients and their clip band."""
    return factors | {
        "beta_slope": -0.10,
        "beta_tpi": 0.05,
        "terrain_modifier_clip_min": 0.70,
        "terrain_modifier_clip_max": 1.40,
    }


@pytest.fixture
def terrain_addresses():
    """A population carrying every cohort shape the modifier has to survive.

    Four territorial authorities; a cohort with a spread of terrain, a cohort
    holding an address the DEM had no value for, a cohort whose addresses are
    identical, and a cohort of one.
    """
    return make_terrain_addresses(
        [
            ("Wellington City", "Kelburn", HILL, 25.0, 12.0),
            ("Wellington City", "Kelburn", HILL, 8.0, -4.0),
            ("Wellington City", "Kelburn", HILL, 17.0, 3.0),
            ("Wellington City", "Kilbirnie", FLAT, 2.0, 0.5),
            ("Wellington City", "Kilbirnie", FLAT, float("nan"), float("nan")),
            ("Lower Hutt City", "Petone", FLAT, 1.0, 0.0),
            ("Lower Hutt City", "Petone", FLAT, 1.0, 0.0),
            ("Lower Hutt City", "Wainuiomata", HILL, 30.0, 6.0),
            ("Lower Hutt City", "Wainuiomata", HILL, 11.0, -2.0),
            ("Porirua City", "Titahi Bay", FLAT, 3.0, 1.0),
            ("Upper Hutt City", "Totara Park", ELEVATED_FLAT, 4.0, 8.0),
            ("Upper Hutt City", "Totara Park", ELEVATED_FLAT, 6.0, 5.0),
        ]
    )


def cohort_means(modifier: pd.Series, addresses: gpd.GeoDataFrame) -> pd.Series:
    """Return the mean modifier within each territorial authority and class."""
    keys = [addresses[column] for column in TERRAIN_GROUP_COLUMNS]
    return modifier.groupby(keys, sort=False).mean()


def test_the_modifier_averages_one_within_every_cohort(
    terrain_addresses, terrain_factors
) -> None:
    """Anything else would double count slope, which the landform class already has."""
    modifier = terrain_modifier(terrain_addresses, terrain_factors)

    means = cohort_means(modifier, terrain_addresses)

    assert means.tolist() == pytest.approx([1.0] * len(means))


def test_a_cohort_of_one_gets_a_modifier_of_one_rather_than_nan(
    terrain_addresses, terrain_factors
) -> None:
    """A small suburb has nothing to be steep relative to, and that is not an error."""
    modifier = terrain_modifier(terrain_addresses, terrain_factors)

    porirua = modifier[terrain_addresses["territorial_authority"] == "Porirua City"]

    assert porirua.tolist() == pytest.approx([1.0])


def test_a_cohort_with_no_spread_gets_a_modifier_of_one_rather_than_nan(
    terrain_addresses, terrain_factors
) -> None:
    """Identical terrain divides by a zero standard deviation if nothing guards it."""
    modifier = terrain_modifier(terrain_addresses, terrain_factors)

    petone = modifier[terrain_addresses["suburb_locality"] == "Petone"]

    assert petone.tolist() == pytest.approx([1.0, 1.0])


def test_an_address_the_dem_has_no_value_for_gets_a_modifier_of_one(
    terrain_addresses, terrain_factors
) -> None:
    """One NaN modifier is one NaN land value, and that hides in a quarter million."""
    modifier = terrain_modifier(terrain_addresses, terrain_factors)

    assert not modifier.isna().any()
    assert modifier.iloc[4] == pytest.approx(1.0)


def test_a_steeper_address_gets_a_smaller_modifier_than_a_gentler_one(
    terrain_addresses, terrain_factors
) -> None:
    """A steep section is harder to build on, so beta_slope is negative."""
    modifier = terrain_modifier(terrain_addresses, terrain_factors)

    steep, gentle = modifier.iloc[0], modifier.iloc[1]

    assert steep < gentle


def test_an_address_standing_higher_gets_a_larger_modifier(terrain_factors) -> None:
    """Standing above the land around you is worth a little; beta_tpi is positive."""
    addresses = make_terrain_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 3.0, 4.0),
            ("Porirua City", "Titahi Bay", FLAT, 3.0, -4.0),
        ]
    )

    modifier = terrain_modifier(addresses, terrain_factors)

    assert modifier.iloc[0] > modifier.iloc[1]


def test_the_clip_band_bounds_how_far_terrain_can_move_value(terrain_factors) -> None:
    """The clip is what stops one freak slope reading becoming a freak valuation."""
    # Coefficients far larger than the adopted ones, so that the clip has to bind.
    extreme = terrain_factors | {"beta_slope": -2.0, "beta_tpi": 0.0}
    addresses = make_terrain_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 2.0, 0.0),
            ("Porirua City", "Titahi Bay", FLAT, 40.0, 0.0),
        ]
    )

    clipped = terrain_modifier(addresses, extreme)
    unclipped = terrain_modifier(
        addresses,
        extreme | {"terrain_modifier_clip_min": 0.01, "terrain_modifier_clip_max": 100},
    )

    # Rescaling to a mean of one cannot change a ratio, so the widest spread the
    # band allows survives it exactly.
    band = extreme["terrain_modifier_clip_max"] / extreme["terrain_modifier_clip_min"]
    assert clipped.max() / clipped.min() == pytest.approx(band)
    assert unclipped.max() / unclipped.min() > band


def test_a_missing_terrain_column_is_named(terrain_addresses, terrain_factors) -> None:
    """Valuing on landform alone is a decision, not something to fall into."""
    addresses = terrain_addresses.drop(columns=[SLOPE_COLUMN])

    with pytest.raises(ValueError, match=SLOPE_COLUMN):
        terrain_modifier(addresses, terrain_factors)


def test_a_missing_terrain_parameter_is_named(
    terrain_addresses, terrain_factors
) -> None:
    """A parameter absent from the asset would otherwise raise a bare KeyError."""
    without_beta = {
        name: value for name, value in terrain_factors.items() if name != "beta_slope"
    }

    with pytest.raises(ValueError, match="beta_slope"):
        terrain_modifier(terrain_addresses, without_beta)


def test_the_modifier_is_indexed_as_the_addresses_are(
    terrain_addresses, terrain_factors
) -> None:
    """The caller multiplies it onto a column, and positional alignment is a trap."""
    addresses = terrain_addresses.set_index(
        pd.Index(range(100, 100 + len(terrain_addresses)))
    )

    modifier = terrain_modifier(addresses, terrain_factors)

    assert list(modifier.index) == list(addresses.index)


# --- valuing addresses with terrain -------------------------------------------


def test_the_ta_mean_still_holds_with_terrain(
    terrain_addresses, base_rates, terrain_factors
) -> None:
    """The whole design rests on this: terrain redistributes, it never adds value."""
    valued = estimate_land_value(
        terrain_addresses, base_rates=base_rates, factors=terrain_factors
    )

    means = valued.groupby("territorial_authority")["land_value_nzd"].mean()

    for ta_name, modelled_mean in means.items():
        assert modelled_mean == pytest.approx(indexed_average(base_rates, ta_name))


def test_terrain_breaks_the_tie_between_addresses_of_the_same_class(
    base_rates, terrain_factors
) -> None:
    """On landform alone a whole suburb shares one value, and that map says nothing."""
    addresses = make_terrain_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 2.0, 1.0),
            ("Porirua City", "Titahi Bay", FLAT, 9.0, 0.0),
            ("Porirua City", "Titahi Bay", FLAT, 16.0, -1.0),
        ]
    )

    with_terrain = estimate_land_value(
        addresses, base_rates=base_rates, factors=terrain_factors
    )
    without_terrain = estimate_land_value(
        addresses.drop(columns=[SLOPE_COLUMN, TOPOGRAPHIC_POSITION_COLUMN]),
        base_rates=base_rates,
        factors=terrain_factors,
    )

    assert without_terrain["land_value_nzd"].nunique() == 1
    assert with_terrain["land_value_nzd"].nunique() == len(addresses)


def test_a_steeper_address_is_worth_less_than_a_gentler_one_in_the_same_cohort(
    terrain_addresses, base_rates, terrain_factors
) -> None:
    """Two Kelburn hill sections differ by their terrain and by nothing else."""
    valued = estimate_land_value(
        terrain_addresses, base_rates=base_rates, factors=terrain_factors
    )

    kelburn = valued[valued["suburb_locality"] == "Kelburn"]

    assert kelburn["land_value_nzd"].iloc[0] < kelburn["land_value_nzd"].iloc[1]


def test_without_the_terrain_columns_the_phase_one_answer_is_unchanged(
    addresses, base_rates, factors, terrain_factors
) -> None:
    """An extent can be valued before its DEM is fetched; that path must not move."""
    phase_one = estimate_land_value(addresses, base_rates=base_rates, factors=factors)
    with_terrain_parameters = estimate_land_value(
        addresses, base_rates=base_rates, factors=terrain_factors
    )

    assert with_terrain_parameters["land_value_nzd"].tolist() == pytest.approx(
        phase_one["land_value_nzd"].tolist()
    )


def test_without_the_terrain_columns_a_class_shares_one_value(
    addresses, base_rates, terrain_factors
) -> None:
    """The Phase 1 signature is one value per TA and class, and it has to survive."""
    valued = estimate_land_value(
        addresses, base_rates=base_rates, factors=terrain_factors
    )

    kelburn = valued[valued["suburb_locality"] == "Kelburn"]

    assert kelburn["land_value_nzd"].nunique() == 1


def test_no_address_is_left_without_a_value_when_terrain_is_used(
    terrain_addresses, base_rates, terrain_factors
) -> None:
    """A single NaN land value survives every mean and median and is never seen."""
    valued = estimate_land_value(
        terrain_addresses, base_rates=base_rates, factors=terrain_factors
    )

    assert not valued["land_value_nzd"].isna().any()


# --- the cohort table ---------------------------------------------------------


def test_the_summary_has_one_row_per_ta_suburb_and_landform(
    addresses, base_rates, factors
) -> None:
    """These three columns are the cohort the Phase 1 Excel tool is keyed on."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    summary = summarise_by_suburb(valued)

    cohorts = summary[["territorial_authority", "suburb_locality", "landform_class"]]
    assert len(summary) == len(cohorts.drop_duplicates())


def test_the_summary_counts_every_address(addresses, base_rates, factors) -> None:
    """A cohort table that loses addresses understates the loss built on it."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    summary = summarise_by_suburb(valued)

    assert summary["address_count"].sum() == len(addresses)


def test_the_summary_reports_the_median_value_and_rate(
    addresses, base_rates, factors
) -> None:
    """Medians, so that a handful of clipped extremes cannot move a cohort."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    summary = summarise_by_suburb(valued).set_index(
        ["territorial_authority", "suburb_locality", "landform_class"]
    )

    kelburn = valued[valued["suburb_locality"] == "Kelburn"]
    assert summary.loc[
        ("Wellington City", "Kelburn", HILL), "median_land_value_nzd"
    ] == pytest.approx(kelburn["land_value_nzd"].median())


def test_the_summary_is_a_plain_table_without_geometry(
    addresses, base_rates, factors
) -> None:
    """Pooled rows have no location, and carrying geometry would imply they do."""
    valued = estimate_land_value(addresses, base_rates=base_rates, factors=factors)

    summary = summarise_by_suburb(valued)

    assert not isinstance(summary, gpd.GeoDataFrame)
    assert "geometry" not in summary.columns


# --- the accessibility modifier -----------------------------------------------


def make_accessibility_addresses(rows):
    """Build addresses from (TA, suburb, landform, gravity, station distance) rows."""
    return gpd.GeoDataFrame(
        {
            "address_id": list(range(len(rows))),
            "territorial_authority": [row[0] for row in rows],
            "suburb_locality": [row[1] for row in rows],
            "landform_class": [row[2] for row in rows],
            GRAVITY_COLUMN: [row[3] for row in rows],
            STATION_DISTANCE_COLUMN: [row[4] for row in rows],
        },
        geometry=[Point(index, index) for index in range(len(rows))],
        crs="EPSG:2193",
    )


@pytest.fixture
def accessibility_factors(factors):
    """The Phase 1 parameters plus the accessibility ones and their clip band."""
    return factors | {
        "accessibility_elasticity": 0.5,
        "rail_station_premium": 0.10,
        "rail_station_decay_length_m": 400.0,
        "accessibility_modifier_clip_min": 0.60,
        "accessibility_modifier_clip_max": 1.60,
    }


@pytest.fixture
def accessibility_addresses():
    """Every cohort shape the modifier has to survive, as for terrain.

    A cohort with a spread of gravity, one holding an address with no gravity
    value, one with no station anywhere near, and a cohort of one.
    """
    nan = float("nan")
    return make_accessibility_addresses(
        [
            ("Wellington City", "Kelburn", HILL, 0.9, 1500.0),
            ("Wellington City", "Makara", HILL, 0.2, 9000.0),
            ("Wellington City", "Karori", HILL, 0.6, 4000.0),
            ("Wellington City", "Kilbirnie", FLAT, 0.8, 3000.0),
            ("Wellington City", "Kilbirnie", FLAT, nan, 3000.0),
            ("Lower Hutt City", "Petone", FLAT, 0.4, nan),
            ("Lower Hutt City", "Petone", FLAT, 0.3, nan),
            ("Porirua City", "Titahi Bay", FLAT, 0.1, 4000.0),
            ("Upper Hutt City", "Totara Park", HILL, 0.06, 200.0),
            ("Upper Hutt City", "Totara Park", HILL, 0.06, 2000.0),
        ]
    )


def test_the_accessibility_modifier_averages_one_within_every_cohort(
    accessibility_addresses, accessibility_factors
) -> None:
    """Otherwise it would pay the flat class again for its location."""
    modifier = accessibility_modifier(accessibility_addresses, accessibility_factors)

    means = cohort_means(modifier, accessibility_addresses)

    assert means.tolist() == pytest.approx([1.0] * len(means))


def test_a_more_accessible_address_gets_a_larger_modifier(
    accessibility_addresses, accessibility_factors
) -> None:
    """Kelburn over Karori over Makara: all hill, separated only by accessibility."""
    modifier = accessibility_modifier(accessibility_addresses, accessibility_factors)

    kelburn, makara, karori = modifier.iloc[0], modifier.iloc[1], modifier.iloc[2]

    assert kelburn > karori > makara


def test_the_gravity_term_acts_as_an_elasticity(accessibility_factors) -> None:
    """At elasticity 0.5, a quarter of the accessibility is half the value."""
    addresses = make_accessibility_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 0.4, float("nan")),
            ("Porirua City", "Titahi Bay", FLAT, 0.1, float("nan")),
        ]
    )

    modifier = accessibility_modifier(addresses, accessibility_factors)

    assert modifier.iloc[0] / modifier.iloc[1] == pytest.approx(2.0)


def test_a_station_at_the_door_is_worth_the_full_premium(accessibility_factors) -> None:
    """Same gravity, one at a station and one far from any: the ratio is 1 + a."""
    addresses = make_accessibility_addresses(
        [
            ("Upper Hutt City", "Totara Park", HILL, 0.06, 0.0),
            ("Upper Hutt City", "Totara Park", HILL, 0.06, 1e9),
        ]
    )

    modifier = accessibility_modifier(addresses, accessibility_factors)

    assert modifier.iloc[0] / modifier.iloc[1] == pytest.approx(1.10)


def test_no_station_in_reach_takes_no_premium_rather_than_nan(
    accessibility_addresses, accessibility_factors
) -> None:
    """Petone has no station distance at all, and is ranked on gravity alone."""
    modifier = accessibility_modifier(accessibility_addresses, accessibility_factors)

    petone = modifier[accessibility_addresses["suburb_locality"] == "Petone"]

    assert not petone.isna().any()
    assert petone.iloc[0] / petone.iloc[1] == pytest.approx((0.4 / 0.3) ** 0.5)


def test_an_address_with_no_gravity_is_never_nan(
    accessibility_addresses, accessibility_factors
) -> None:
    """NaN gravity is centred onto its cohort before the rescale, never left NaN."""
    modifier = accessibility_modifier(accessibility_addresses, accessibility_factors)

    assert not modifier.isna().any()


def test_a_cohort_of_one_gets_an_accessibility_modifier_of_one(
    accessibility_addresses, accessibility_factors
) -> None:
    """A lone address has nothing to be more accessible than."""
    modifier = accessibility_modifier(accessibility_addresses, accessibility_factors)

    ta = accessibility_addresses["territorial_authority"]

    assert modifier[ta == "Porirua City"].tolist() == pytest.approx([1.0])


def test_the_clip_band_bounds_how_far_accessibility_can_move_value(
    accessibility_factors,
) -> None:
    """The CBD fringe cannot run away from its cohort, however large the gap."""
    addresses = make_accessibility_addresses(
        [
            ("Porirua City", "Titahi Bay", FLAT, 1.0, float("nan")),
            ("Porirua City", "Titahi Bay", FLAT, 1e-6, float("nan")),
        ]
    )

    modifier = accessibility_modifier(addresses, accessibility_factors)

    band = (
        accessibility_factors["accessibility_modifier_clip_max"]
        / accessibility_factors["accessibility_modifier_clip_min"]
    )
    assert modifier.max() / modifier.min() == pytest.approx(band)


def test_a_missing_accessibility_parameter_is_named(
    accessibility_addresses, accessibility_factors
) -> None:
    """A parameter absent from the asset would otherwise raise a bare KeyError."""
    without = {
        name: value
        for name, value in accessibility_factors.items()
        if name != "accessibility_elasticity"
    }

    with pytest.raises(ValueError, match="accessibility_elasticity"):
        accessibility_modifier(accessibility_addresses, without)


def test_the_ta_mean_still_holds_with_accessibility(
    accessibility_addresses, base_rates, accessibility_factors
) -> None:
    """Accessibility redistributes within an authority and never adds value to it."""
    valued = estimate_land_value(
        accessibility_addresses, base_rates=base_rates, factors=accessibility_factors
    )

    means = valued.groupby("territorial_authority")["land_value_nzd"].mean()

    for ta_name, modelled_mean in means.items():
        assert modelled_mean == pytest.approx(indexed_average(base_rates, ta_name))


def test_without_the_accessibility_columns_the_modifier_is_not_read(
    accessibility_addresses, base_rates, factors
) -> None:
    """No columns means no modifier, so the five parameters need not even exist."""
    bare = accessibility_addresses.drop(
        columns=[GRAVITY_COLUMN, STATION_DISTANCE_COLUMN]
    )

    valued = estimate_land_value(bare, base_rates=base_rates, factors=factors)

    assert not valued["land_value_nzd"].isna().any()


# --- section size -------------------------------------------------------------


@pytest.fixture
def size_factors(factors):
    """The Phase 1 parameters plus the section area elasticity."""
    return factors | {"section_area_elasticity": 0.5, "section_area_min_m2": 150.0}


def make_sized_addresses(rows):
    """Build addresses from (TA, suburb, landform, section area) rows."""
    addresses = make_addresses([row[:3] for row in rows])
    addresses["section_area_m2"] = [row[3] for row in rows]
    return addresses


def test_a_bigger_section_is_worth_more_but_less_per_square_metre(
    base_rates, size_factors
) -> None:
    """Value grows with area, but slower than area, at an elasticity below one."""
    addresses = make_sized_addresses(
        [
            ("Wellington City", "Karori", HILL, 225.0),
            ("Wellington City", "Karori", HILL, 900.0),
        ]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    small, large = valued.iloc[0], valued.iloc[1]
    assert large["land_value_nzd"] / small["land_value_nzd"] == pytest.approx(2.0)
    assert large["land_rate_nzd_per_m2"] < small["land_rate_nzd_per_m2"]


def test_the_rate_is_divided_by_the_measured_area(base_rates, size_factors) -> None:
    """The loss multiplies the rate by damaged area, so it must be per real m2."""
    addresses = make_sized_addresses([("Wellington City", "Karori", HILL, 300.0)])

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    row = valued.iloc[0]
    assert row["lot_size_m2"] == pytest.approx(300.0)
    assert row["lot_size_source"] == "measured"
    assert row["land_rate_nzd_per_m2"] == pytest.approx(row["land_value_nzd"] / 300.0)


def test_an_unmeasured_address_falls_back_to_the_assumed_lot(
    base_rates, size_factors
) -> None:
    """No property found means today's behaviour, not a dropped address."""
    addresses = make_sized_addresses(
        [("Wellington City", "Karori", HILL, float("nan"))]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    row = valued.iloc[0]
    assert row["lot_size_source"] == "assumed"
    assert row["lot_size_m2"] == pytest.approx(row["assumed_lot_size_m2"])
    assert row["land_rate_nzd_per_m2"] == pytest.approx(
        row["land_value_nzd"] / row["assumed_lot_size_m2"]
    )


def test_the_ta_mean_still_holds_with_section_sizes(base_rates, size_factors) -> None:
    """Section size moves value between properties and never into the TA."""
    addresses = make_sized_addresses(
        [
            ("Wellington City", "Kelburn", HILL, 150.0),
            ("Wellington City", "Kelburn", HILL, 700.0),
            ("Wellington City", "Kilbirnie", FLAT, 300.0),
            ("Lower Hutt City", "Petone", FLAT, 400.0),
            ("Lower Hutt City", "Wainuiomata", HILL, float("nan")),
        ]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    means = valued.groupby("territorial_authority")["land_value_nzd"].mean()
    for ta_name, modelled_mean in means.items():
        assert modelled_mean == pytest.approx(indexed_average(base_rates, ta_name))


def test_a_missing_elasticity_is_named(base_rates, factors) -> None:
    """Measured areas without the parameter to use them is a broken asset."""
    addresses = make_sized_addresses([("Wellington City", "Karori", HILL, 300.0)])

    with pytest.raises(ValueError, match="section_area_elasticity"):
        estimate_land_value(addresses, base_rates=base_rates, factors=factors)


def test_without_section_areas_every_lot_is_assumed(base_rates, factors) -> None:
    """The column is optional, and without it the rate uses the assumed lot."""
    valued = estimate_land_value(
        make_addresses([("Wellington City", "Karori", HILL)]),
        base_rates=base_rates,
        factors=factors,
    )

    assert valued["lot_size_source"].tolist() == ["assumed"]


def test_the_packaged_factors_carry_the_section_area_elasticity() -> None:
    """Read only when s4 measures section areas, so nothing else guards it."""
    assert 0 < load_factors()["section_area_elasticity"] < 1


# --- counting each property once ----------------------------------------------


def test_weights_make_the_constant_a_mean_over_properties() -> None:
    """Two addresses on one property weigh half each, so they count as one."""
    unweighted = solve_normalising_constant([1.0, 1.0, 4.0], 500_000)
    weighted = solve_normalising_constant([1.0, 1.0, 4.0], 500_000, [0.5, 0.5, 1.0])

    assert unweighted == pytest.approx(500_000 / 2.0)
    assert weighted == pytest.approx(500_000 / 2.5)


def make_shared_addresses(rows):
    """Build addresses from (TA, suburb, landform, area, addresses on property)."""
    addresses = make_sized_addresses([row[:4] for row in rows])
    addresses["addresses_on_property"] = [row[4] for row in rows]
    return addresses


def test_a_big_shared_property_does_not_pull_an_ordinary_one_down(
    base_rates, size_factors
) -> None:
    """Thirty addresses on 30,000 m2 must count once, not thirty times.

    Counted per address, each of the thirty takes the whole estate's size factor
    and the normalisation takes value off every ordinary section to pay for it,
    which is what halved 13 Lawrence Street's rate in the pilot.
    """
    ordinary = [("Wellington City", "Newtown", FLAT, 450.0, 1)]
    estate = [("Wellington City", "Newtown", FLAT, 30_000.0, 30)] * 30

    alone = estimate_land_value(
        make_shared_addresses(ordinary + ordinary),
        base_rates=base_rates,
        factors=size_factors,
    )
    beside_estate = estimate_land_value(
        make_shared_addresses(ordinary + ordinary + estate),
        base_rates=base_rates,
        factors=size_factors | {"rate_clip_max_multiple": 1e9},
    )

    with_estate = beside_estate.iloc[0]["land_value_nzd"]
    without = alone.iloc[0]["land_value_nzd"]
    # Three properties now share the average, so the ordinary section gives up
    # some value -- but a share as one property, not as thirty.
    expected = without * 3 / (2 + (30_000 / 450) ** 0.5)
    assert with_estate == pytest.approx(expected)


def test_the_ta_mean_holds_over_properties(base_rates, size_factors) -> None:
    """The published average is per rating unit, so that is the mean held."""
    addresses = make_shared_addresses(
        [
            ("Wellington City", "Newtown", FLAT, 170.0, 3),
            ("Wellington City", "Newtown", FLAT, 170.0, 3),
            ("Wellington City", "Newtown", FLAT, 170.0, 3),
            ("Wellington City", "Kelburn", HILL, 491.0, 1),
            ("Wellington City", "Karori", HILL, 560.0, 1),
        ]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    assert ta_mean_land_value(valued)["Wellington City"] == pytest.approx(
        indexed_average(base_rates, "Wellington City")
    )


def test_addresses_on_one_property_share_one_rate(base_rates, size_factors) -> None:
    """The claim takes the mean of its addresses' rates, so they must agree."""
    addresses = make_shared_addresses(
        [("Wellington City", "Newtown", FLAT, 170.0, 3)] * 3
        + [("Wellington City", "Karori", HILL, 560.0, 1)]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    assert valued["land_rate_nzd_per_m2"].iloc[:3].nunique() == 1


# --- the rate is modelled, and a site is its rating units ---------------------


def make_sites(rows):
    """Build addresses from (TA, suburb, landform, area, addresses, rating units)."""
    addresses = make_sized_addresses([row[:4] for row in rows])
    addresses["addresses_on_property"] = [row[4] for row in rows]
    addresses["rating_units_on_property"] = [row[5] for row in rows]
    return addresses


def test_a_unit_titled_block_is_rated_as_the_sum_of_its_units(
    base_rates, size_factors
) -> None:
    """Ten units on 1,500 m2 rate like ten 150 m2 sections, not one big garden."""
    block = [("Wellington City", "Te Aro", FLAT, 1500.0, 10, 10)] * 10
    small_section = [("Wellington City", "Te Aro", FLAT, 150.0, 1, 1)]
    big_freehold = [("Wellington City", "Te Aro", FLAT, 1500.0, 1, 1)]

    valued = estimate_land_value(
        make_sites(block + small_section + big_freehold),
        base_rates=base_rates,
        factors=size_factors,
    )

    rate = valued["land_rate_nzd_per_m2"]
    assert rate.iloc[0] == pytest.approx(rate.iloc[10])
    assert rate.iloc[0] > rate.iloc[11]


def test_a_freehold_property_with_several_addresses_rates_as_one_section(
    base_rates, size_factors
) -> None:
    """13 Lawrence Street: one title, three addresses, rated on all 170 m2."""
    three_flats = [("Wellington City", "Newtown", FLAT, 170.0, 3, 1)] * 3
    one_house = [("Wellington City", "Newtown", FLAT, 170.0, 1, 1)]

    valued = estimate_land_value(
        make_sites(three_flats + one_house), base_rates=base_rates, factors=size_factors
    )

    assert valued["land_rate_nzd_per_m2"].nunique() == 1


def test_the_published_average_is_held_per_rating_unit(
    base_rates, size_factors
) -> None:
    """Total site value over total rating units, as the published figure is built."""
    addresses = make_sites(
        [("Wellington City", "Te Aro", FLAT, 1200.0, 2, 20)] * 2
        + [("Wellington City", "Kelburn", HILL, 491.0, 1, 1)]
        + [("Wellington City", "Karori", HILL, 560.0, 1, 1)]
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    total = (
        valued["site_land_value_nzd"].iloc[0]
        + valued["site_land_value_nzd"].iloc[2:].sum()
    )
    assert total / 22 == pytest.approx(indexed_average(base_rates, "Wellington City"))
    assert ta_mean_land_value(valued)["Wellington City"] == pytest.approx(
        indexed_average(base_rates, "Wellington City")
    )


def test_a_site_value_is_its_rate_times_its_area(base_rates, size_factors) -> None:
    """The rate is what is modelled; the value follows from it."""
    valued = estimate_land_value(
        make_sites([("Wellington City", "Te Aro", FLAT, 1200.0, 20, 20)] * 20),
        base_rates=base_rates,
        factors=size_factors,
    )

    row = valued.iloc[0]
    assert row["site_land_value_nzd"] == pytest.approx(
        row["land_rate_nzd_per_m2"] * 1200.0
    )
    assert row["land_value_nzd"] == pytest.approx(row["site_land_value_nzd"] / 20)


def test_a_flat_may_fall_below_the_clip_floor(base_rates, size_factors) -> None:
    """A unit's share of its block's land is legitimately small, so no floor."""
    addresses = make_sites(
        [("Wellington City", "Karori", HILL, 300.0, 10, 10)] * 10
        + [("Wellington City", "Karori", HILL, 600.0, 1, 1)] * 20
    )

    valued = estimate_land_value(addresses, base_rates=base_rates, factors=size_factors)

    floor = size_factors["rate_clip_min_multiple"] * indexed_average(
        base_rates, "Wellington City"
    )
    assert valued["land_value_nzd"].iloc[0] < floor
    assert (valued["land_value_nzd"].iloc[10:] >= floor - 1e-6).all()


def test_the_size_floor_stops_a_dense_block_extrapolating(
    base_rates, size_factors
) -> None:
    """93 units on 1,170 m2 is 12.6 m2 each; it is rated as 150 m2 each."""
    dense = make_sites([("Wellington City", "Te Aro", FLAT, 1170.0, 1, 93)])
    at_floor = make_sites([("Wellington City", "Te Aro", FLAT, 150.0, 1, 1)])
    both = pd.concat([dense, at_floor], ignore_index=True)

    # The value ceiling off, so the comparison is of the size floor alone.
    unclipped = size_factors | {"rate_clip_max_multiple": 1e9}
    valued = estimate_land_value(both, base_rates=base_rates, factors=unclipped)

    assert valued["land_rate_nzd_per_m2"].iloc[0] == pytest.approx(
        valued["land_rate_nzd_per_m2"].iloc[1]
    )


def test_the_packaged_factors_carry_the_section_area_floor() -> None:
    """Read only when s4 measures section areas, so nothing else guards it."""
    assert load_factors()["section_area_min_m2"] > 0
