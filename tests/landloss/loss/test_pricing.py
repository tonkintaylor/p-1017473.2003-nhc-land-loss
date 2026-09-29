import numpy as np
import pytest

from landloss.exposure.rw.beta_population import (
    BETA_MAX_HEIGHT_M,
    BETA_MIN_HEIGHT_M,
    MEDIUM_MAX_HEIGHT_M,
    SIZE_CLASSES,
    SMALL_MAX_HEIGHT_M,
    classify_wall_size,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    BETA_SIZE_CLASS_HEIGHT_M,
    BETA_WALL_RATE_EXCL_GST_NZD_PER_M2,
    BETA_WALL_TYPES,
    DIFFICULT,
    EASY,
    EASY_ACCESS_MAX_DRIVEWAY_M,
    EASY_CONSTRUCTABILITY_MAX_SLOPE_DEG,
    EASY_INUNDATION_MAX_VOLUME_M3,
    LANDSLIDE_WALL_MARGIN_M,
    MAX_SITE_MULTIPLIER,
    MEDIUM_LANDSLIDE_MAX_AREA_M2,
    MEDIUM_LANDSLIDE_MAX_VOLUME_M3,
    MIN_LANDSLIDE_WALL_LENGTH_M,
    MODERATE,
    MODERATE_ACCESS_MAX_DRIVEWAY_M,
    MODERATE_CONSTRUCTABILITY_MAX_SLOPE_DEG,
    MODERATE_INUNDATION_MAX_VOLUME_M3,
    SMALL_LANDSLIDE_MAX_AREA_M2,
    WALL_RATE_EXCL_GST_NZD_PER_M2,
    SiteRatings,
    beta_wall_face_area_m2,
    beta_wall_height_m,
    beta_wall_repair_cost_incl_gst_nzd,
    beta_wall_udv_incl_gst_nzd,
    classify_constructability,
    classify_construction_access,
    classify_inundation_earthworks,
    classify_landslide_wall_size,
    inundation_volume_m3,
    landslide_wall_length_m,
    wall_face_area_m2,
    wall_rate_excl_gst_nzd_per_m2,
    wall_repair_cost_incl_gst_nzd,
    wall_udv_incl_gst_nzd,
)

ACT = PolicySettings()

# Every repair cost carries this on top of the site multiplier; an
# undepreciated value carries neither.
SPEC = 1.0 + ACT.replacement_spec_uplift

# The costing tool's own combination table, transcribed row for row. The three
# letters are construction access, earthworks required, and constructability
# and reinstatement, in the order the duty report's table lists them. This is
# the oracle: the module computes the multiplier rather than storing the table,
# so these 27 rows are what says the formula reproduces the tool.
TOOL_COMBINATION_TABLE = {
    "EEE": 0.00,
    "EEM": 0.05,
    "EED": 0.10,
    "EME": 0.05,
    "EMM": 0.10,
    "EMD": 0.15,
    "EDE": 0.10,
    "EDM": 0.15,
    "EDD": 0.20,
    "MEE": 0.05,
    "MEM": 0.10,
    "MED": 0.15,
    "MME": 0.10,
    "MMM": 0.15,
    "MMD": 0.20,
    "MDE": 0.15,
    "MDM": 0.20,
    "MDD": 0.25,
    "DEE": 0.10,
    "DEM": 0.15,
    "DED": 0.20,
    "DME": 0.15,
    "DMM": 0.20,
    "DMD": 0.25,
    "DDE": 0.20,
    "DDM": 0.25,
    "DDD": 0.30,
}


def ratings_from(combo):
    access, earthworks, constructability = tuple(combo)
    return SiteRatings(
        construction_access=access,
        earthworks_required=earthworks,
        constructability_reinstatement=constructability,
    )


# ---------------------------------------------------------------------------
# The site multiplier, against the costing tool's table.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("combo", "expected"), TOOL_COMBINATION_TABLE.items())
def test_multiplier_matches_the_costing_tool_table(combo, expected):
    assert ratings_from(combo).multiplier == pytest.approx(expected)


def test_the_table_is_a_complete_enumeration():
    # 3 ratings across 3 factors. If the tool ever grows a fourth rating or a
    # fourth factor, this is what notices.
    assert len(TOOL_COMBINATION_TABLE) == 27


def test_multiplier_never_exceeds_the_line_item_ceiling():
    worst = max(ratings_from(combo).multiplier for combo in TOOL_COMBINATION_TABLE)
    assert worst == pytest.approx(MAX_SITE_MULTIPLIER)
    assert worst == pytest.approx(0.30)


def test_an_all_easy_site_adds_nothing():
    assert ratings_from("EEE").multiplier == pytest.approx(0.0)


def test_the_order_of_the_three_ratings_does_not_matter():
    # The markup is a sum, so a site rated easy/moderate/difficult costs the
    # same however the three are assigned. Worth pinning: it is the reason the
    # module can compute the figure instead of looking the combination up.
    assert ratings_from("EMD").multiplier == pytest.approx(
        ratings_from("DME").multiplier
    )


def test_ratings_are_case_insensitive():
    assert ratings_from("emd").multiplier == pytest.approx(
        ratings_from("EMD").multiplier
    )


def test_an_unknown_rating_is_refused():
    ratings = ratings_from("EXD")
    with pytest.raises(ValueError, match="earthworks_required must be one of"):
        _ = ratings.multiplier


def test_ratings_apply_across_a_population():
    ratings = SiteRatings(
        construction_access=np.array(["E", "M", "D"]),
        earthworks_required=np.array(["E", "M", "D"]),
        constructability_reinstatement=np.array(["E", "M", "D"]),
    )
    assert ratings.multiplier == pytest.approx([0.00, 0.15, 0.30])


# ---------------------------------------------------------------------------
# The rates.
# ---------------------------------------------------------------------------


def test_every_wall_type_the_tool_carries_is_priced():
    assert len(WALL_RATE_EXCL_GST_NZD_PER_M2) == 29


def test_rate_lookup_returns_the_tools_figure():
    assert wall_rate_excl_gst_nzd_per_m2("Concrete Block") == pytest.approx(1_010.58)
    assert wall_rate_excl_gst_nzd_per_m2("Shotcrete") == pytest.approx(226.67)


def test_rate_lookup_works_across_a_population():
    rates = wall_rate_excl_gst_nzd_per_m2(np.array(["Shotcrete", "UC: 310mm x 158mm"]))
    assert rates == pytest.approx([226.67, 4_736.23])


def test_an_unknown_wall_type_is_refused():
    # The rates are a closed list, so an unrecognised type means the mapping
    # from the wall population picked a name the tool does not price.
    with pytest.raises(ValueError, match="unknown wall type"):
        wall_rate_excl_gst_nzd_per_m2("Mud Brick")


# ---------------------------------------------------------------------------
# Face area.
# ---------------------------------------------------------------------------


def test_face_area_is_retained_height_by_length():
    assert wall_face_area_m2(1.8, 10.0) == pytest.approx(18.0)


def test_face_area_refuses_a_negative_height():
    with pytest.raises(ValueError, match="height_m must be finite"):
        wall_face_area_m2(-1.0, 10.0)


# ---------------------------------------------------------------------------
# Repair cost.
# ---------------------------------------------------------------------------


def test_repair_cost_is_rate_by_area_by_multiplier_grossed_up():
    # A 1.8 m by 10 m timber pole wall on a site rated easy access, moderate
    # earthworks, moderate constructability: $744.69 x 18 m2 x 1.10 x 1.15.
    cost = wall_repair_cost_incl_gst_nzd(
        "Timber Pole: 250mm SED",
        wall_face_area_m2(1.8, 10.0),
        ratings=ratings_from("EMM"),
        policy=ACT,
    )
    assert cost == pytest.approx(744.69 * 18.0 * 1.10 * SPEC * 1.15)


def test_an_easy_site_pays_the_bare_rate_plus_gst():
    cost = wall_repair_cost_incl_gst_nzd(
        "Concrete Block",
        10.0,
        ratings=ratings_from("EEE"),
        policy=ACT,
    )
    assert cost == pytest.approx(1_010.58 * 10.0 * SPEC * 1.15)


def test_the_hardest_site_pays_thirty_percent_more_than_the_easiest():
    easy = wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 10.0, ratings=ratings_from("EEE"), policy=ACT
    )
    hard = wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 10.0, ratings=ratings_from("DDD"), policy=ACT
    )
    assert hard == pytest.approx(easy * 1.30)


def test_repair_cost_is_gst_inclusive_on_the_scenarios_rate():
    # The rates arrive excluding GST and settlement compares on a GST-inclusive
    # basis, so the gross-up has to happen here rather than at the call site.
    zero_gst = PolicySettings(gst_rate=0.0)
    assert wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 10.0, ratings=ratings_from("EEE"), policy=zero_gst
    ) == pytest.approx(1_010.58 * 10.0 * SPEC)


def test_a_portfolio_prices_in_one_call():
    cost = wall_repair_cost_incl_gst_nzd(
        np.array(["Shotcrete", "Concrete Block"]),
        wall_face_area_m2(np.array([1.0, 2.0]), np.array([5.0, 5.0])),
        ratings=SiteRatings(
            construction_access=np.array(["E", "D"]),
            earthworks_required=np.array(["E", "D"]),
            constructability_reinstatement=np.array(["E", "D"]),
        ),
        policy=ACT,
    )
    assert cost == pytest.approx(
        [226.67 * 5.0 * SPEC * 1.15, 1_010.58 * 10.0 * 1.30 * SPEC * 1.15]
    )


def test_an_undamaged_wall_costs_nothing():
    assert wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 0.0, ratings=ratings_from("DDD"), policy=ACT
    ) == pytest.approx(0.0)


def test_a_negative_area_is_refused():
    with pytest.raises(ValueError, match="face_area_m2 must be finite"):
        wall_repair_cost_incl_gst_nzd(
            "Concrete Block", -1.0, ratings=ratings_from("EEE"), policy=ACT
        )


# ---------------------------------------------------------------------------
# The beta rate, standing in until a wall type mapping is settled.
# ---------------------------------------------------------------------------


def test_the_beta_rate_averages_the_four_non_driven_timber_pole_walls():
    assert BETA_WALL_TYPES == (
        "Timber Pole: 175mm SED",
        "Timber Pole: 250mm SED",
        "Timber Pole: 300mm SED",
        "Timber Pole: 350mm SED",
    )
    assert (
        pytest.approx((643.19 + 744.69 + 798.80 + 879.87) / 4)
        == BETA_WALL_RATE_EXCL_GST_NZD_PER_M2
    )
    assert pytest.approx(766.6375) == BETA_WALL_RATE_EXCL_GST_NZD_PER_M2


def test_the_beta_rate_excludes_the_driven_timber_poles():
    # The driven rates are a separate and cheaper family; including them would
    # pull the average down without anything saying it should.
    assert not any("Driven" in wall_type for wall_type in BETA_WALL_TYPES)


def test_beta_cost_is_the_flat_rate_by_area_by_multiplier_grossed_up():
    cost = beta_wall_repair_cost_incl_gst_nzd(
        wall_face_area_m2(1.8, 10.0), ratings=ratings_from("EMM"), policy=ACT
    )
    assert cost == pytest.approx(766.6375 * 18.0 * 1.10 * SPEC * 1.15)


def test_beta_cost_sits_between_the_cheapest_and_dearest_timber_pole():
    area, ratings = 10.0, ratings_from("EEE")
    beta = beta_wall_repair_cost_incl_gst_nzd(area, ratings=ratings, policy=ACT)
    smallest = wall_repair_cost_incl_gst_nzd(
        "Timber Pole: 175mm SED", area, ratings=ratings, policy=ACT
    )
    largest = wall_repair_cost_incl_gst_nzd(
        "Timber Pole: 350mm SED", area, ratings=ratings, policy=ACT
    )
    assert smallest < beta < largest


def test_beta_cost_varies_with_size_through_area_not_rate():
    # A large wall costs more than a small one because it has more face, not
    # because it is priced differently. Worth pinning: it is the only way size
    # reaches the cost while one flat rate stands in for the type.
    ratings = ratings_from("EEE")
    small = beta_wall_repair_cost_incl_gst_nzd(
        wall_face_area_m2(0.8, 10.0), ratings=ratings, policy=ACT
    )
    large = beta_wall_repair_cost_incl_gst_nzd(
        wall_face_area_m2(3.2, 10.0), ratings=ratings, policy=ACT
    )
    assert large == pytest.approx(small * 4.0)


def test_each_size_class_is_priced_at_a_set_height():
    assert beta_wall_height_m("small") == pytest.approx(0.75)
    assert beta_wall_height_m("medium") == pytest.approx(1.75)
    assert beta_wall_height_m("large") == pytest.approx(2.75)


def test_every_size_class_the_population_emits_has_a_height():
    # If the population ever grows a fourth class, this is what notices before
    # a wall reaches pricing with no height to charge against.
    assert set(BETA_SIZE_CLASS_HEIGHT_M) == set(SIZE_CLASSES)


def test_each_height_classifies_back_to_its_own_size_class():
    # The height a class is priced at has to be a height of that class, or the
    # mapping and the bands in beta_population have drifted apart. This is what
    # ruled out pricing small at 1 m, which the bands read back as medium.
    for size_class, height in BETA_SIZE_CLASS_HEIGHT_M.items():
        assert classify_wall_size(height) == size_class


def test_each_height_lies_inside_what_its_class_can_actually_contain():
    # The population draws heights over BETA_MIN_HEIGHT_M to BETA_MAX_HEIGHT_M,
    # so a class holds that range clipped to its own band. Each set height sits
    # strictly inside its own, near the middle; small is 0.75 against a realised
    # midpoint of 0.70, rounded to a clean quarter.
    bounds = {
        "small": (BETA_MIN_HEIGHT_M, SMALL_MAX_HEIGHT_M),
        "medium": (SMALL_MAX_HEIGHT_M, MEDIUM_MAX_HEIGHT_M),
        "large": (MEDIUM_MAX_HEIGHT_M, BETA_MAX_HEIGHT_M),
    }
    for size_class, (low, high) in bounds.items():
        assert low < BETA_SIZE_CLASS_HEIGHT_M[size_class] < high


def test_the_set_heights_are_ordered_and_evenly_spaced():
    small, medium, large = (
        BETA_SIZE_CLASS_HEIGHT_M[size_class] for size_class in SIZE_CLASSES
    )
    assert small < medium < large
    assert medium - small == pytest.approx(large - medium)


def test_size_classes_are_case_insensitive():
    assert beta_wall_height_m("Medium") == pytest.approx(1.75)


def test_an_unknown_size_class_is_refused():
    with pytest.raises(ValueError, match="rw_size must be one of"):
        beta_wall_height_m("enormous")


def test_face_area_from_a_size_class_is_its_height_by_length():
    assert beta_wall_face_area_m2("medium", 12.0) == pytest.approx(21.0)


def test_face_area_from_a_size_class_works_across_a_population():
    areas = beta_wall_face_area_m2(
        np.array(["small", "medium", "large"]), np.array([10.0, 10.0, 10.0])
    )
    assert areas == pytest.approx([7.5, 17.5, 27.5])


def test_a_wall_prices_straight_from_what_vul_sends():
    # rw_size and rw_length are the only wall attributes the contract carries,
    # so this is the whole path from vul's row to a repair cost.
    cost = beta_wall_repair_cost_incl_gst_nzd(
        beta_wall_face_area_m2("medium", 12.0),
        ratings=ratings_from("EMM"),
        policy=ACT,
    )
    assert cost == pytest.approx(766.6375 * 21.0 * 1.10 * SPEC * 1.15)


def test_beta_cost_prices_a_population_in_one_call():
    cost = beta_wall_repair_cost_incl_gst_nzd(
        wall_face_area_m2(np.array([1.0, 2.0]), np.array([5.0, 5.0])),
        ratings=SiteRatings(
            construction_access=np.array(["E", "D"]),
            earthworks_required=np.array(["E", "D"]),
            constructability_reinstatement=np.array(["E", "D"]),
        ),
        policy=ACT,
    )
    assert cost == pytest.approx(
        [
            766.6375 * 5.0 * SPEC * 1.15,
            766.6375 * 10.0 * 1.30 * SPEC * 1.15,
        ]
    )


# ---------------------------------------------------------------------------
# Inundation removal, and the earthworks rating its volume implies.
# ---------------------------------------------------------------------------


def test_volume_is_inundated_area_by_mean_depth():
    assert inundation_volume_m3(120.0, 0.5) == pytest.approx(60.0)


def test_volume_works_across_a_population():
    volumes = inundation_volume_m3(np.array([50.0, 200.0]), np.array([0.2, 1.5]))
    assert volumes == pytest.approx([10.0, 300.0])


def test_a_negative_depth_is_refused():
    with pytest.raises(ValueError, match="inundated_mean_depth_m must be finite"):
        inundation_volume_m3(100.0, -0.5)


def test_a_small_spoil_volume_is_easy():
    # A shovel, a wheelbarrow and a truck.
    assert classify_inundation_earthworks(10.0) == EASY


def test_a_mid_spoil_volume_is_moderate():
    # A mini excavator, small enough to get down a residential driveway.
    assert classify_inundation_earthworks(100.0) == MODERATE


def test_a_large_spoil_volume_is_difficult():
    # A full-size excavator and truck cartage.
    assert classify_inundation_earthworks(500.0) == DIFFICULT


def test_the_band_edges_fall_to_the_easier_rating():
    assert classify_inundation_earthworks(EASY_INUNDATION_MAX_VOLUME_M3) == EASY
    assert classify_inundation_earthworks(MODERATE_INUNDATION_MAX_VOLUME_M3) == MODERATE
    assert (
        classify_inundation_earthworks(MODERATE_INUNDATION_MAX_VOLUME_M3 + 0.1)
        == DIFFICULT
    )


def test_no_inundation_rates_easy():
    # There is no spoil to clear, which is an answer rather than a gap.
    assert classify_inundation_earthworks(0.0) == EASY


def test_the_rating_feeds_straight_into_the_site_ratings():
    # The whole point: a land claim answers its own earthworks rating from the
    # geometry vul already sends, rather than having to be told.
    ratings = SiteRatings(
        construction_access=EASY,
        earthworks_required=classify_inundation_earthworks(
            inundation_volume_m3(300.0, 1.5)
        ),
        constructability_reinstatement=EASY,
    )
    assert ratings.multiplier == pytest.approx(0.10)


def test_the_earthworks_rating_classifies_a_population_in_one_call():
    ratings = classify_inundation_earthworks(
        inundation_volume_m3(np.array([20.0, 200.0, 400.0]), np.array([0.5, 0.5, 1.0]))
    )
    assert list(ratings) == [EASY, MODERATE, DIFFICULT]


# ---------------------------------------------------------------------------
# Undepreciated value. The same rate as the repair cost, without the site
# allowance -- so the site multiplier is the whole of the difference.
# ---------------------------------------------------------------------------


def test_udv_is_the_bare_rate_by_area_grossed_up():
    assert wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=ACT) == pytest.approx(
        1_010.58 * 10.0 * 1.15
    )


def test_udv_ignores_the_site_ratings_entirely():
    # There is nowhere to pass them: what it costs to work on a site is not
    # part of what the wall cost to build.
    easy_site_repair = wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 10.0, ratings=ratings_from("EEE"), policy=ACT
    )
    # On an easy site the multiplier is zero, so what separates them is the
    # specification uplift alone.
    assert wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=ACT) == pytest.approx(
        easy_site_repair / SPEC
    )


def test_the_site_multiplier_and_spec_uplift_are_the_whole_difference():
    # Two allowances separate repair from value, and they are different things:
    # the multiplier is what this site costs to work on, the uplift is that the
    # replacement is built to a better standard than what failed (L-34).
    udv = wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=ACT)
    repair = wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 10.0, ratings=ratings_from("DDD"), policy=ACT
    )
    assert repair == pytest.approx(udv * (1.0 + MAX_SITE_MULTIPLIER) * SPEC)


def test_a_like_for_like_rebuild_differs_only_by_the_site_multiplier():
    # Turning the uplift off recovers the old behaviour exactly, which is what
    # makes it a scenario setting rather than a hardcoded change of basis.
    like_for_like = PolicySettings(replacement_spec_uplift=0.0)
    udv = wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=like_for_like)
    repair = wall_repair_cost_incl_gst_nzd(
        "Concrete Block", 10.0, ratings=ratings_from("DDD"), policy=like_for_like
    )
    assert repair == pytest.approx(udv * (1.0 + MAX_SITE_MULTIPLIER))


def test_the_uplift_never_reaches_an_undepreciated_value():
    # UDV is what the wall was worth, not what a better one would cost.
    assert wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=ACT) == pytest.approx(
        wall_udv_incl_gst_nzd(
            "Concrete Block", 10.0, policy=PolicySettings(replacement_spec_uplift=0.0)
        )
    )


@pytest.mark.parametrize("combo", TOOL_COMBINATION_TABLE)
def test_repair_cost_is_never_below_udv(combo):
    # The property the whole comparison rests on, across every site rating the
    # tool carries. It holds by construction -- the multiplier is never
    # negative -- which is worth pinning precisely because it is not evidence.
    udv = wall_udv_incl_gst_nzd("Timber Pole: 250mm SED", 18.0, policy=ACT)
    repair = wall_repair_cost_incl_gst_nzd(
        "Timber Pole: 250mm SED", 18.0, ratings=ratings_from(combo), policy=ACT
    )
    assert repair >= udv


def test_udv_carries_no_deduction_for_age_or_condition():
    # Undepreciated means exactly that. There is no age or condition argument,
    # so two walls of the same construction and size are worth the same.
    assert wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=ACT) == pytest.approx(
        wall_udv_incl_gst_nzd("Concrete Block", 10.0, policy=ACT)
    )


def test_udv_prices_a_population_in_one_call():
    values = wall_udv_incl_gst_nzd(
        np.array(["Shotcrete", "Concrete Block"]),
        np.array([5.0, 10.0]),
        policy=ACT,
    )
    assert values == pytest.approx([226.67 * 5.0 * 1.15, 1_010.58 * 10.0 * 1.15])


def test_an_unknown_wall_type_is_refused_for_udv():
    with pytest.raises(ValueError, match="unknown wall type"):
        wall_udv_incl_gst_nzd("Mud Brick", 10.0, policy=ACT)


def test_beta_udv_uses_the_beta_flat_rate():
    assert beta_wall_udv_incl_gst_nzd(
        beta_wall_face_area_m2("medium", 12.0), policy=ACT
    ) == pytest.approx(766.6375 * 21.0 * 1.15)


def test_a_wall_gives_both_numbers_from_what_vul_sends():
    # The whole path: rw_size and rw_length in, the two figures settle needs
    # out, with only the site allowance between them.
    area = beta_wall_face_area_m2("large", 10.0)
    ratings = ratings_from("EMD")
    udv = beta_wall_udv_incl_gst_nzd(area, policy=ACT)
    repair = beta_wall_repair_cost_incl_gst_nzd(area, ratings=ratings, policy=ACT)
    assert udv == pytest.approx(766.6375 * 27.5 * 1.15)
    assert repair == pytest.approx(udv * 1.15 * SPEC)


# ---------------------------------------------------------------------------
# The proxies. Every band in them is invented, so what is worth testing is the
# shape of the mapping and the bound on what it can cost -- not the numbers.
# ---------------------------------------------------------------------------


def test_construction_access_worsens_with_driveway_length():
    lengths = [0.0, EASY_ACCESS_MAX_DRIVEWAY_M, MODERATE_ACCESS_MAX_DRIVEWAY_M, 1_000.0]
    assert classify_construction_access(lengths).tolist() == [
        EASY,
        EASY,
        MODERATE,
        DIFFICULT,
    ]


def test_constructability_worsens_with_slope():
    slopes = [
        0.0,
        EASY_CONSTRUCTABILITY_MAX_SLOPE_DEG,
        MODERATE_CONSTRUCTABILITY_MAX_SLOPE_DEG,
        89.0,
    ]
    assert classify_constructability(slopes).tolist() == [
        EASY,
        EASY,
        MODERATE,
        DIFFICULT,
    ]


@pytest.mark.parametrize(
    "classify", [classify_construction_access, classify_constructability]
)
def test_the_proxies_refuse_a_negative_measure(classify):
    with pytest.raises(ValueError, match="must be finite and not negative"):
        classify([-1.0])


def test_the_three_proxies_together_cannot_exceed_the_ceiling():
    # The whole point of proxying rather than waiting: all three being wrong in
    # the worst direction moves a wall's cost by the site multiplier's ceiling
    # and no further.
    worst = SiteRatings(
        construction_access=classify_construction_access([1e6]),
        earthworks_required=classify_inundation_earthworks([1e6]),
        constructability_reinstatement=classify_constructability([89.0]),
    )
    assert worst.multiplier == pytest.approx(MAX_SITE_MULTIPLIER)


# ---------------------------------------------------------------------------
# The wall invented to reinstate land a landslide took.
# ---------------------------------------------------------------------------


def test_the_invented_wall_grows_with_the_damaged_area():
    areas = [
        1.0,
        SMALL_LANDSLIDE_MAX_AREA_M2,
        MEDIUM_LANDSLIDE_MAX_AREA_M2,
        10_000.0,
    ]
    assert classify_landslide_wall_size(areas).tolist() == [
        "small",
        "small",
        "medium",
        "large",
    ]


def test_a_deep_deposit_on_a_small_footprint_is_not_a_small_job():
    # Area alone would call this small. The volume is what says otherwise, and
    # the larger of the two classes is the one taken.
    small_area = [SMALL_LANDSLIDE_MAX_AREA_M2]
    assert classify_landslide_wall_size(small_area).tolist() == ["small"]
    deep = [MEDIUM_LANDSLIDE_MAX_VOLUME_M3 + 1.0]
    assert classify_landslide_wall_size(small_area, deep).tolist() == ["large"]


def test_no_volume_falls_back_to_the_area_alone():
    areas = [MEDIUM_LANDSLIDE_MAX_AREA_M2 + 1.0]
    assert classify_landslide_wall_size(areas, [0.0]).tolist() == (
        classify_landslide_wall_size(areas).tolist()
    )


def test_the_invented_wall_follows_the_width_of_the_failure():
    # 200 m2 at two to one is 10 m deep and 20 m across, plus a margin each end.
    expected = 20.0 + 2.0 * LANDSLIDE_WALL_MARGIN_M
    assert landslide_wall_length_m([200.0]).tolist() == [pytest.approx(expected)]


def test_the_invented_wall_is_never_shorter_than_worth_mobilising_for():
    # The floor binds only on the very smallest slips: the margin at each end
    # already carries most walls past it. A no-area claim is the clear case.
    assert landslide_wall_length_m([0.0]).tolist() == [MIN_LANDSLIDE_WALL_LENGTH_M]
    areas = np.array([0.0, 0.5, 5.0, 50.0, 500.0])
    assert (landslide_wall_length_m(areas) >= MIN_LANDSLIDE_WALL_LENGTH_M).all()


def test_the_invented_wall_is_wider_than_the_ground_is_deep():
    # The old model took a side of a square, which under-read every slip.
    area = 400.0
    assert landslide_wall_length_m([area])[0] > area**0.5


def test_the_invented_wall_refuses_a_negative_area():
    with pytest.raises(ValueError, match="must be finite and not negative"):
        landslide_wall_length_m([-1.0])
