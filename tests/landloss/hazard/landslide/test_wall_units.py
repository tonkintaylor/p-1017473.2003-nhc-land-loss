"""Tests for the wall units: candidates, points, floor, count update and draw."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
from scipy.stats import binom

from landloss.domain import constants
from landloss.hazard.landslide.wall_candidates import (
    _property_of_lines,
    property_of_pifs,
)
from landloss.hazard.landslide.wall_units import (
    CLAIMS,
    GNS_FLOOR,
    GNS_ONLY,
    POINTS,
    gen_claim_holdout,
    gen_count_update,
    gen_element_walls,
    gen_gns_floor,
    gen_property_wall_records,
    gen_unit_boundary_flags,
    gen_unit_properties,
    gen_wall_draws,
    gen_wall_members,
    gen_wall_points,
    gen_wall_unit_probability,
    gen_wall_units,
    load_wall_points,
    poisson_binomial_pmf,
    wall_probability,
)

CRS = 2193

RULES = {
    "max_bends": 3,
    "min_segment_m": 3.0,
    "max_length_m": 50.0,
    "max_turn_deg": 185.0,
}


def _layer(geometries, **columns):
    return gpd.GeoDataFrame(columns, geometry=list(geometries), crs=CRS)


def _pif(start, end, fall, *, property_id="1", **overrides):
    """One candidate pif along a straight spine, falling one way at both ends."""
    (x0, y0), (x1, y1) = sorted([start, end])
    n = max(round(np.hypot(x1 - x0, y1 - y0)) + 1, 2)
    xs, ys = np.linspace(x0, x1, n), np.linspace(y0, y1, n)
    row = {
        "candidate_class": "siz",
        "rateable_property_id": property_id,
        "spine": shapely.LineString([(x0, y0), (x1, y1)]),
        "spine_length_m": float(np.hypot(x1 - x0, y1 - y0)),
        "end_a_x": x0,
        "end_a_y": y0,
        "end_b_x": x1,
        "end_b_y": y1,
        "end_a_fall_deg": fall,
        "end_b_fall_deg": fall,
        "max_delta_h_m": 2.0,
        "near_drop_p80_m": 2.0,
        "building_m": 10.0,
        "ground_group": "soil_like",
        "ground_material": "soil",
        "height_band": 1,
        "in_slide_fill": False,
        "gns_wall": False,
        "is_siz": True,
        "geometry": shapely.MultiPoint(np.column_stack([xs, ys])),
    }
    row.update(overrides)
    return row


def _pifs(*rows):
    table = gpd.GeoDataFrame(list(rows), geometry="geometry", crs=CRS)
    table["spine"] = gpd.GeoSeries(table["spine"], crs=CRS)
    table.index = pd.Index(range(1, len(rows) + 1), name="pif_id")
    return table


def _gns_only(*lines, property_id="1", **columns):
    """GNS-only pieces on one rateable property (None for none, as on a road)."""
    frame = _layer(
        [shapely.LineString(line) for line in lines],
        rateable_property_id=pd.array([property_id] * len(lines), dtype="string"),
        building_m=columns.get("building_m", [20.0] * len(lines)),
        ground_material=columns.get("ground_material", ["soil"] * len(lines)),
        step_height_m=columns.get("step_height_m", [0.4] * len(lines)),
    )
    frame["length_m"] = frame.length
    frame.index.name = "gns_only_id"
    return frame


NO_GNS_ONLY = _gns_only()


def _cut_fill(sizs, *, classes=None):
    """Ground step 5 per pif: uncertain (neutral) by default."""
    return pd.DataFrame(
        {"cut_fill_class": classes or ["uncertain"] * len(sizs)},
        index=sizs.index,
    )


def _units(sizs, gns_only=NO_GNS_ONLY, cut_fill=None, **overrides):
    cut_fill = _cut_fill(sizs) if cut_fill is None else cut_fill
    return gen_wall_units(
        gen_wall_members(sizs, gns_only, cut_fill), **{**RULES, **overrides}
    )


def test_every_candidate_is_its_own_unit():
    # Two pifs end to end and a GNS-only piece beside them: three units, one
    # member each, nothing joined (the lead, 2026-10-07).
    sizs = _pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 13), (0, 23), 90.0))
    units = _units(sizs, _gns_only([(4, 0), (4, 10)]))
    assert len(units) == 3
    assert (units["n_pifs"] + units["n_gns_only"] == 1).all()
    assert units.geometry.geom_type.eq("LineString").all()
    assert sorted(units["length_m"].round(1)) == [10.0, 10.0, 10.0]
    assert units.index.name == "wall_unit_id"
    assert units.index[0] == f"{constants.WALL_UNIT_ID_PREFIX}0000001"


def test_a_unit_carries_its_members_height_building_and_ground():
    sizs = _pifs(
        _pif((0, 0), (0, 10), 90.0, building_m=5.0, ground_material="rock"),
    )
    sizs["near_drop_p80_m"] = [1.5]
    unit = _units(sizs).iloc[0]
    assert unit["height_m"] == pytest.approx(1.5)
    assert unit["building_m"] == pytest.approx(5.0)
    assert unit["ground_material"] == "rock"
    assert unit["length_m"] == pytest.approx(10.0)


def test_a_candidate_breaking_a_line_rule_is_refused():
    long_pif = _pif((0, 0), (0, 60), 90.0)
    with pytest.raises(ValueError, match="line rules"):
        _units(_pifs(long_pif))


BASE = 0.3
DOUBLING = 20.0
TABLE = load_wall_points()


def _points(units, **kwargs):
    return gen_wall_points(
        units,
        TABLE,
        base_p=BASE,
        low_height_base_p=constants.BETA_LOW_HEIGHT_WALL_PRIOR,
        per_doubling=DOUBLING,
        **kwargs,
    )


def _probability(units):
    prior = _points(units)
    return prior, gen_gns_floor(units, prior)


def test_a_gns_only_piece_on_a_road_is_out_of_the_exposure():
    units = _units(
        _pifs(_pif((0, 0), (0, 10), 90.0)),
        _gns_only([(50, 0), (50, 10)], property_id=None),
    )
    gns = units[units["unit_source"] == "gns_only"].iloc[0]
    assert pd.isna(gns["property_id"])
    assert not gns["in_exposure"]
    assert units.loc[units["unit_source"] == "pif", "in_exposure"].all()


def _unit_frame(**columns):
    # A neutral candidate: every attribute in a 0-point bin.
    defaults = {
        "unit_source": "pif",
        "is_siz": True,
        "gns_wall": False,
        "height_band": 1,
        "ground_material": "soil",
        "height_m": 2.0,
        "length_m": 10.0,
        "building_m": 10.0,
        "verticality": np.nan,
        "cut_fill_class": "uncertain",
        "property_id": None,
    }
    n = max(len(v) for v in columns.values())
    data = {k: columns.get(k, [v] * n) for k, v in defaults.items()}
    return pd.DataFrame(data, index=[f"WU{i:07d}" for i in range(1, n + 1)])


def _odds(p):
    p = np.asarray(p, dtype=float)
    return p / (1.0 - p)


def test_no_points_is_the_base_and_twenty_double_the_odds():
    p = wall_probability([0.0, 20.0, -20.0, 40.0], base_p=BASE, per_doubling=DOUBLING)
    assert p[0] == pytest.approx(BASE)
    assert _odds(p[1:]) / _odds(BASE) == pytest.approx([2.0, 0.5, 4.0])
    extreme = wall_probability([100.0, -100.0], base_p=BASE, per_doubling=DOUBLING)
    assert 0.0 < extreme[1] < extreme[0] < 1.0


def test_no_prior_reaches_one_on_the_points_table():
    # The highest-scoring candidate the table allows stays below 1.
    units = _unit_frame(
        verticality=[0.9],
        height_m=[3.0],
        building_m=[1.0],
        cut_fill_class=["cut"],
        ground_material=["loess"],
    ).assign(on_road_frontage=True, property_id="1")
    ages = pd.DataFrame(
        {
            "p_pre_1970": [0.0],
            "p_1970_1991": [0.0],
            "p_1992_2004": [0.0],
            "p_2005_on": [1.0],
        },
        index=["1"],
    )
    prior = _points(units, age_shares=ages, nhc_flags=pd.Series({"1": True}))
    assert prior["wall_points"].iloc[0] == pytest.approx(10 + 5 + 10 + 20 + 10 + 10 + 5)
    assert prior["p_prior"].iloc[0] < 1.0


def test_a_neutral_candidate_scores_nothing_and_takes_the_base():
    prior = _points(_unit_frame(height_m=[2.0]))
    assert prior["wall_points"].iloc[0] == 0
    assert prior["p_prior"].iloc[0] == pytest.approx(BASE)
    assert prior["p_prior_basis"].iloc[0] == POINTS
    assert prior["wall_points_explain"].iloc[0] == ""


# One numeric attribute per case: (column, values, points).
BIN_CASES = [
    ("verticality", [0.3, 0.45, 0.5, 0.9], [-20, -5, 10, 10]),
    (
        "height_m",
        [0.8, 1.0, 2.4, 2.5, 5.0, 7.9, 8.0, 12.0],
        [-5, 0, 0, 5, -20, -20, -60, -60],
    ),
    ("length_m", [3.0, 4.9, 5.0, 40.0], [-5, -5, 0, 0]),
    ("building_m", [0.5, 2.0, 4.9, 5.0, 20.0, np.nan], [10, 5, 5, 0, -20, -20]),
]


@pytest.mark.parametrize(("column", "values", "points"), BIN_CASES)
def test_each_numeric_attribute_scores_its_bin(column, values, points):
    prior = _points(_unit_frame(**{column: values}))
    assert prior["wall_points"].tolist() == pytest.approx(points)


def test_the_setting_scores_road_frontage_over_a_boundary():
    units = _unit_frame(height_m=[2.0, 2.0, 2.0]).assign(
        on_property_boundary=[True, True, False],
        on_road_frontage=[False, True, False],
    )
    prior = _points(units)
    assert prior["wall_points"].tolist() == [10, 20, 0]
    assert prior["is_road_frontage"].tolist() == [False, True, False]
    assert prior["is_property_boundary"].tolist() == [True, False, False]
    assert prior["wall_points_explain"].tolist()[:2] == [
        "setting property_boundary +10",
        "setting road_frontage +20",
    ]


# One unit per row: (class, ground material, height_m, points, is_rock_cut,
# is_soil_cut, is_fill, is_natural). Height 2.0 to 2.5 m scores 0 itself.
CLASS_CASES = [
    ("uncertain", "soil", 2.0, 0, False, False, False, False),
    ("cut", "rock", 2.1, -20, True, False, False, False),
    ("cut", "rock", 2.0, 0, False, False, False, False),
    ("cut", "rock_hw_cw", 2.1, 10, False, True, False, False),
    ("cut", "loess", 2.0, 10, False, True, False, False),
    ("cut", "fill_uncontrolled", 2.0, 10, False, True, False, False),
    ("fill", "rock", 2.1, 5, False, False, True, False),
    ("cut_and_fill", "loess", 2.0, 5, False, False, True, False),
    ("natural", "loess", 2.0, -15, False, False, False, True),
    ("unknown", "rock", 2.1, 0, False, False, False, False),
]


def test_the_class_and_a_cut_in_rock_or_soil_score():
    cases = list(zip(*CLASS_CASES, strict=True))
    units = _unit_frame(
        cut_fill_class=list(cases[0]),
        ground_material=list(cases[1]),
        height_m=list(cases[2]),
    )
    prior = _points(units)
    assert prior["wall_points"].tolist() == pytest.approx(list(cases[3]))
    assert prior["is_rock_cut"].tolist() == list(cases[4])
    assert prior["is_soil_cut"].tolist() == list(cases[5])
    assert prior["is_fill"].tolist() == list(cases[6])
    assert prior["is_natural"].tolist() == list(cases[7])


def test_ground_map_fill_no_longer_sets_the_prior():
    units = _unit_frame(
        ground_material=["fill_uncontrolled", "rock"],
        cut_fill_class=["uncertain", "uncertain"],
    ).assign(ground_modification="fill", in_slide_fill=True)
    prior = _points(units)
    assert prior["p_prior"].tolist() == pytest.approx([BASE, BASE])
    assert not prior["is_fill"].any()


def test_age_points_are_the_share_weighted_points_of_the_property():
    units = _unit_frame(property_id=["1", "2", "3"])
    ages = pd.DataFrame(
        {
            "p_pre_1970": [0.5, 0.0],
            "p_1970_1991": [0.5, 0.0],
            "p_1992_2004": [0.0, 0.5],
            "p_2005_on": [0.0, 0.5],
        },
        index=["1", "2"],
    )
    prior = _points(units, age_shares=ages)
    assert prior["age_points"].tolist() == pytest.approx([-7.5, 5.0, 0.0])
    assert prior["has_age"].tolist() == [True, True, False]
    assert prior["wall_points_explain"].iloc[0] == "age property ages -8"


def test_missing_age_shares_score_nothing():
    prior = _points(_unit_frame(property_id=["1"]), age_shares=None)
    assert prior["age_points"].tolist() == [0.0]
    assert not prior["has_age"].any()


def test_the_nhc_land_attributes_flag_is_five_points():
    units = _unit_frame(property_id=["1", "2", None])
    prior = _points(units, nhc_flags=pd.Series({"1": True, "2": False}))
    assert prior["wall_points"].tolist() == [5, 0, 0]
    assert prior["wall_points_explain"].iloc[0] == "nhc_land_attrs flagged +5"


def test_the_explain_lists_each_scoring_bin():
    units = _unit_frame(verticality=[0.6], height_m=[3.0], building_m=[1.0])
    explain = _points(units)["wall_points_explain"].iloc[0]
    assert explain == (
        "verticality 0.5 and over +10; height 2.5 to 5 m +5; building under 2 m +10"
    )


def test_the_floor_and_the_claim_update_apply_on_top_of_the_points():
    units = _unit_frame(
        height_m=[9.0, 9.0], gns_wall=[False, True], property_id=["1", "2"]
    )
    prior, floor = _probability(units)
    assert prior["p_prior"].iloc[0] < 0.06
    assert floor["p_floor"].tolist() == pytest.approx(
        [prior["p_prior"].iloc[0], constants.BETA_GNS_WALL_UNIT_FLOOR]
    )
    assert floor["p_floor_basis"].tolist() == [POINTS, GNS_FLOOR]
    probability, _ = _update(
        units.assign(property_id=pd.array(["1", "2"], dtype="string")),
        floor,
        _records(**{"1": (1, False)}),
    )
    assert probability["p_wall"].iloc[0] == pytest.approx(1.0)
    assert probability["p_wall_basis"].tolist() == [CLAIMS, GNS_FLOOR]


def test_a_gns_only_candidate_takes_its_probability_whatever_its_points():
    units = _unit_frame(unit_source=["gns_only"], is_siz=[False], height_m=[9.0])
    prior, floor = _probability(units)
    assert prior["p_prior_basis"].iloc[0] == GNS_ONLY
    assert floor["p_floor"].iloc[0] == pytest.approx(
        constants.BETA_GNS_ONLY_WALL_PROBABILITY
    )


def test_a_candidate_pif_missing_from_step_13_stops_the_members():
    sizs = _pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 13), (0, 23), 90.0))
    with pytest.raises(ValueError, match="ground step 5"):
        gen_wall_members(sizs, NO_GNS_ONLY, _cut_fill(sizs).iloc[:1])


def test_a_gns_only_unit_is_class_unknown():
    units = _units(
        _pifs(_pif((0, 0), (0, 10), 90.0)),
        _gns_only([(50, 0), (50, 10)]),
    )
    by_source = units.set_index("unit_source")["cut_fill_class"]
    assert by_source.loc["gns_only"] == "unknown"
    assert by_source.loc["pif"] == "uncertain"


def test_a_low_height_unit_carries_its_prior_and_the_floor_sets_it():
    units = _unit_frame(is_siz=[False], gns_wall=[True])
    prior, floor = _probability(units)
    assert prior["p_prior"].iloc[0] == pytest.approx(
        constants.BETA_LOW_HEIGHT_WALL_PRIOR
    )
    assert floor["p_floor"].iloc[0] == pytest.approx(constants.BETA_GNS_WALL_UNIT_FLOOR)


def test_the_pmf_sums_to_one_and_matches_the_binomial():
    pmf = poisson_binomial_pmf([0.3] * 6)
    assert pmf.sum() == pytest.approx(1.0)
    assert pmf == pytest.approx(binom.pmf(np.arange(7), 6, 0.3))
    assert poisson_binomial_pmf([]).tolist() == [1.0]
    assert poisson_binomial_pmf([0.2, 0.9]).sum() == pytest.approx(1.0)


def test_one_listed_wall_lifts_two_even_units_to_two_thirds():
    updated, missing = gen_count_update([0.5, 0.5], 1)
    assert updated == pytest.approx([2 / 3, 2 / 3])
    assert missing == 0


def test_no_probability_falls():
    rng = np.random.default_rng(7)
    for _ in range(50):
        p = rng.random(rng.integers(1, 8))
        n = int(rng.integers(0, len(p) + 2))
        updated, _ = gen_count_update(p, n)
        assert (updated >= p - 1e-12).all()
        assert (updated <= 1.0).all()


def test_a_report_listing_none_changes_nothing():
    p = np.array([0.2, 0.7])
    updated, missing = gen_count_update(p, 0)
    assert updated.tolist() == p.tolist()
    assert missing == 0


def _two_property_units():
    units = pd.DataFrame(
        {"property_id": pd.array(["1", "1", "2", "2", None], dtype="string")},
        index=[f"WU{i:07d}" for i in range(1, 6)],
    )
    floor = pd.DataFrame(
        {"p_floor": [0.5, 0.5, 0.5, 0.0, 0.5], "p_floor_basis": POINTS},
        index=units.index,
    )
    return units, floor


def _records(**rows):
    """Records by property id: (claim_walls, nzmm_wall)."""
    return pd.DataFrame(
        {
            "claim_walls": pd.array([r[0] for r in rows.values()], dtype="Int64"),
            "nzmm_wall": [r[1] for r in rows.values()],
            "ta": "Wellington",
        },
        index=pd.Index(list(rows), name="property_id"),
    )


def _update(units, floor, records, held_out=None):
    return gen_wall_unit_probability(
        units,
        floor,
        records=records,
        held_out=pd.Series(dtype=bool) if held_out is None else held_out,
    )


def test_fewer_units_than_listed_walls_go_to_one_and_report_the_shortfall():
    units, floor = _two_property_units()
    probability, missing = _update(
        units, floor, _records(**{"1": (1, False), "2": (2, False), "9": (2, False)})
    )
    assert probability["p_claims"].tolist() == pytest.approx(
        [2 / 3, 2 / 3, 1.0, 0.0, 0.5]
    )
    assert probability["p_wall_basis"].tolist() == [
        CLAIMS,
        CLAIMS,
        CLAIMS,
        POINTS,
        POINTS,
    ]
    claims = missing[missing["update"] == "claims"].set_index("property_id")
    assert claims.loc["2", "missing"] == 1
    assert claims.loc["2", "n_units"] == 2
    assert claims.loc["9", "missing"] == 2
    assert claims.loc["9", "n_units"] == 0
    assert "1" not in claims.index


def test_held_out_claims_are_not_updated():
    units, floor = _two_property_units()
    probability, missing = _update(
        units,
        floor,
        _records(**{"1": (1, False)}),
        held_out=pd.Series({"1": True}),
    )
    assert probability["p_wall"].tolist() == pytest.approx(floor["p_floor"].tolist())
    assert probability["held_out"].tolist() == [True, True, False, False, False]
    assert probability["claim_walls"].iloc[0] == 1
    assert missing.empty


def test_the_holdout_is_seeded_and_order_free():
    ids = [str(i) for i in range(10)]
    held = gen_claim_holdout(ids, share=0.3, seed=2003)
    assert held.sum() == 3
    assert held.equals(gen_claim_holdout(ids[::-1] + ids[:2], share=0.3, seed=2003))
    assert not held.equals(gen_claim_holdout(ids, share=0.3, seed=1))


def test_the_record_join_takes_the_smallest_containing_polygon():
    properties = _layer(
        [
            shapely.box(0, 0, 10, 10),
            shapely.box(20, 0, 30, 10),
            shapely.box(90, 0, 99, 9),
        ],
        source_id=[11, 12, 13],
    )
    records = _layer(
        [shapely.box(-5, -5, 40, 20), shapely.box(-1, -1, 11, 11)],
        claim_walls=[3.0, 1.0],
        nhc_wall=pd.array([pd.NA, True], dtype="boolean"),
        ta=["Wellington", "Wellington"],
        nzmm_slope_class=["steep", "moderate"],
        gns_walls_2m=[0.0, 2.0],
    )
    result = gen_property_wall_records(properties, records)
    assert sorted(result.index) == ["11", "12"]
    assert result.loc["11", "claim_walls"] == 1
    assert bool(result.loc["11", "nzmm_wall"])
    assert result.loc["12", "claim_walls"] == 3
    assert not result.loc["12", "nzmm_wall"]
    assert result.loc["11", "nzmm_slope_class"] == "moderate"
    assert result.loc["11", "gns_walls_2m"] == 2.0
    assert str(result["claim_walls"].dtype) == "Int64"


def test_stacked_titles_give_their_record_to_the_lowest_id_only():
    footprint = shapely.box(0, 0, 10, 10)
    properties = _layer([footprint, footprint, footprint], source_id=[31, 30, 32])
    records = _layer(
        [shapely.box(-1, -1, 11, 11)],
        claim_walls=[2.0],
        nhc_wall=pd.array([False], dtype="boolean"),
        ta=["Wellington"],
    )
    result = gen_property_wall_records(properties, records)
    assert result.index.tolist() == ["30"]
    assert result.loc["30", "claim_walls"] == 2


def test_the_nzmm_flag_is_no_update():
    units, floor = _two_property_units()
    probability, missing = _update(units, floor, _records(**{"1": (pd.NA, True)}))
    assert probability["p_wall"].tolist() == pytest.approx(floor["p_floor"].tolist())
    assert probability["nzmm_wall"].tolist()[:2] == [True, True]
    assert missing.empty


@pytest.mark.parametrize("source_ids", [[31, 30, 32], [9, 10, 11], [100, 99, 98]])
def test_a_stack_gives_its_pifs_and_its_record_to_one_title(source_ids):
    footprint = shapely.box(0, 0, 10, 10)
    properties = _layer(
        [footprint] * 3,
        source_id=source_ids,
        source=["NZ Primary Parcels"] * 3,
        valuation_reference=["v"] * 3,
        title_type=["Unit Title"] * 3,
    )
    records = _layer(
        [shapely.box(-1, -1, 11, 11)],
        claim_walls=[1.0],
        nhc_wall=pd.array([False], dtype="boolean"),
        ta=["Wellington"],
    )
    pifs = _layer([shapely.MultiPoint([(2, 2), (3, 2), (4, 2)])])
    pif_property = property_of_pifs(pifs, properties)
    record = gen_property_wall_records(properties, records)
    assert record.index.tolist() == [str(min(source_ids))]
    assert pif_property["rateable_property_id"].tolist() == record.index.tolist()
    assert pif_property["n_properties"].tolist() == [1]


# Unit lines -------------------------------------------------------------------


# Setting: boundaries and road frontage ---------------------------------------


def test_a_unit_along_a_boundary_or_a_road_is_flagged():
    lots = _layer(
        [
            shapely.box(0, 0, 20, 20),
            shapely.box(20, 0, 40, 20),
            shapely.box(0, -10, 40, 0),
        ],
        source_id=[1, 2, 3],
        source=["NZ Primary Parcels"] * 2 + ["NZ Primary Parcels - Road"],
        valuation_reference=["a", "b", None],
        title_type=["Freehold", "Freehold", None],
    )
    units = gpd.GeoDataFrame(
        geometry=[
            shapely.LineString([(19, 5), (19, 15)]),  # 1 m off the lots' boundary
            shapely.LineString([(5, 1), (15, 1)]),  # 1 m off the road
            shapely.LineString([(5, 10), (15, 10)]),  # in the middle of a lot
        ],
        crs=CRS,
    )
    flags = gen_unit_boundary_flags(units, lots, distance_m=2.0)
    assert flags["on_property_boundary"].tolist() == [True, True, False]
    assert flags["on_road_frontage"].tolist() == [False, True, False]


# Properties a unit enters ------------------------------------------------------


def _three_lots():
    return _layer(
        [
            shapely.box(0, 0, 10, 10),
            shapely.box(10, 0, 20, 10),
            shapely.box(20, 0, 30, 10),
        ],
        source_id=[1, 2, 3],
        source=["NZ Primary Parcels"] * 2 + ["NZ Primary Parcels - Road"],
        valuation_reference=["a", "b", None],
        title_type=["Freehold", "Freehold", None],
    )


def test_a_unit_carries_its_length_in_every_property_it_enters_by_a_metre():
    units = gpd.GeoDataFrame(
        geometry=[
            shapely.LineString([(2, 5), (19.5, 5)]),  # 8 m in lot 1, 9.5 m in 2
            shapely.LineString([(3, 5), (10.5, 5)]),  # 0.5 m in lot 2: not counted
            shapely.LineString([(21, 5), (29, 5)]),  # on the road only
        ],
        crs=CRS,
        index=pd.Index(["WU1", "WU2", "WU3"], name="wall_unit_id"),
    )
    result = gen_unit_properties(units, _three_lots())
    assert result["property_id"].tolist()[:2] == ["2", "1"]
    assert pd.isna(result["property_id"].iloc[2])
    assert result["in_exposure"].tolist() == [True, True, False]
    assert result["n_properties"].tolist() == [2, 1, 0]
    first = result["property_lengths_m"].iloc[0]
    assert [e["property_id"] for e in first] == ["2", "1"]
    assert [e["length_m"] for e in first] == pytest.approx([9.5, 8.0])
    assert result["property_lengths_m"].iloc[1][0]["length_m"] == pytest.approx(7.0)


def test_a_unit_on_two_properties_is_updated_on_both_and_keeps_the_higher():
    units = pd.DataFrame(
        {
            "property_id": pd.array(["1", "2"], dtype="string"),
            "property_lengths_m": [
                [{"property_id": "1", "length_m": 5.0}],
                [
                    {"property_id": "2", "length_m": 6.0},
                    {"property_id": "1", "length_m": 2.0},
                ],
            ],
        },
        index=["WU1", "WU2"],
    )
    floor = pd.DataFrame(
        {"p_floor": [0.5, 0.5], "p_floor_basis": POINTS}, index=units.index
    )
    probability, missing = _update(units, floor, _records(**{"1": (1, False)}))
    # Property 1 holds both units, so its one listed wall lifts both to 2/3;
    # property 2 lists none, so WU2 keeps the higher of its two.
    assert probability["p_claims"].tolist() == pytest.approx([2 / 3, 2 / 3])
    assert probability["p_wall_basis"].tolist() == [CLAIMS, CLAIMS]
    # The claim columns are the primary property's.
    assert probability["claim_walls"].tolist()[0] == 1
    assert pd.isna(probability["claim_walls"].iloc[1])
    assert missing.empty


def test_a_property_entered_by_another_unit_holds_its_listed_walls():
    units = pd.DataFrame(
        {
            "property_id": pd.array(["1", "2"], dtype="string"),
            "property_lengths_m": [
                [{"property_id": "1", "length_m": 5.0}],
                [
                    {"property_id": "2", "length_m": 6.0},
                    {"property_id": "1", "length_m": 2.0},
                ],
            ],
        },
        index=["WU1", "WU2"],
    )
    floor = pd.DataFrame(
        {"p_floor": [0.5, 0.5], "p_floor_basis": POINTS}, index=units.index
    )
    probability, missing = _update(units, floor, _records(**{"1": (2, False)}))
    # Without the crossing unit property 1 could hold one of its two walls.
    assert probability["p_claims"].tolist() == pytest.approx([1.0, 1.0])
    assert missing.empty


def test_a_gns_only_line_mostly_on_a_road_goes_to_the_lot_it_touches():
    properties = _layer(
        [shapely.box(0, 0, 10, 10), shapely.box(10, 0, 30, 10)],
        source_id=[5, 6],
        source=["NZ Primary Parcels", "NZ Primary Parcels - Road"],
        valuation_reference=["v", None],
        title_type=["Freehold", None],
    )
    lines = _layer([shapely.LineString([(7, 5), (25, 5)])])
    result = _property_of_lines(lines, properties)
    assert result["property_id"].tolist() == ["6"]
    assert result["rateable_property_id"].tolist() == ["5"]


def test_draws_reproduce_per_world_and_follow_the_probability():
    units = pd.DataFrame(
        {"p_wall": [0.0, 1.0, 0.3, np.nan]},
        index=pd.Index([f"WU{i:07d}" for i in range(1, 5)], name="wall_unit_id"),
    )
    base = constants.EXPOSURE_BASE_SEED
    draws = gen_wall_draws(units, world_ids=list(range(2000)), base_seed=base)
    by_unit = draws.groupby("wall_unit_id")["walled"].mean()
    assert by_unit["WU0000001"] == 0.0
    assert by_unit["WU0000002"] == 1.0
    assert by_unit["WU0000003"] == pytest.approx(0.3, abs=0.03)
    assert by_unit["WU0000004"] == 0.0
    alone = gen_wall_draws(units, world_ids=[5], base_seed=base)
    assert alone["walled"].tolist() == draws[draws["world_id"] == 5]["walled"].tolist()
    assert gen_wall_draws(units, world_ids=[], base_seed=base).empty


def test_an_element_is_walled_when_its_pif_is_in_a_walled_unit():
    units = pd.DataFrame(
        # Read back from parquet, the lists are arrays.
        {"member_pif_ids": [[1, 2], np.array([3]), np.array([], dtype=np.int64)]},
        index=pd.Index(["WU0000001", "WU0000002", "WU0000003"], name="wall_unit_id"),
    )
    walled = pd.Series({"WU0000001": True, "WU0000002": False, "WU0000003": True})
    elements = pd.DataFrame(
        {"siz_id": [1, 3, 7, 2]}, index=pd.Index([10, 11, 12, 13], name="label")
    )
    flags = gen_element_walls(units, walled, elements)
    assert flags.tolist() == [True, False, False, True]
    assert flags.index.tolist() == [10, 11, 12, 13]
    assert flags.dtype == bool
    # An element on a GNS-only unit's line is walled with that unit.
    on_line = pd.DataFrame(
        {"siz_id": [0, 0], "wall_unit_id": ["WU0000003", None]},
        index=pd.Index([14, 15], name="label"),
    )
    assert gen_element_walls(units, walled, on_line).tolist() == [True, False]
