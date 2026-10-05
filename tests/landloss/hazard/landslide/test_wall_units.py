"""Tests for the wall units: joining, prior, floor, count update and draw."""

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
    FILL,
    GNS_FLOOR,
    GNS_ONLY,
    NATURAL,
    NZMM,
    PRIOR,
    ROCK_CUT,
    gen_claim_holdout,
    gen_count_update,
    gen_element_walls,
    gen_gns_floor,
    gen_gns_wall_features,
    gen_pif_wall_heights,
    gen_property_wall_records,
    gen_wall_draws,
    gen_wall_members,
    gen_wall_prior,
    gen_wall_unit_probability,
    gen_wall_units,
    poisson_binomial_pmf,
)

CRS = 2193

JOIN = {
    "gns_match_m": 2.0,
    "join_gap_m": 5.0,
    "max_offset_m": 1.5,
    "bearing_tol_deg": 30.0,
    "corner_gap_m": 3.0,
    "corner_max_deg": 90.0,
    "gns_only_merge_m": 5.0,
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
NO_FEATURES = _layer([])


def _cut_fill(sizs, *, classes=None, heights=None):
    """Step 13 per pif: uncertain (neutral) at the pif's largest drop by default."""
    return pd.DataFrame(
        {
            "cut_fill_class": classes or ["uncertain"] * len(sizs),
            "wall_height_m": heights or sizs["max_delta_h_m"].tolist(),
        },
        index=sizs.index,
    )


def _units(
    sizs, gns_only=NO_GNS_ONLY, features=NO_FEATURES, cut_fill=None, **overrides
):
    cut_fill = _cut_fill(sizs) if cut_fill is None else cut_fill
    return gen_wall_units(
        gen_wall_members(sizs, gns_only, cut_fill),
        features,
        **{**JOIN, **overrides},
    )


def test_two_pifs_end_to_end_on_one_property_are_one_unit():
    units = _units(_pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 13), (0, 23), 90.0)))
    assert len(units) == 1
    unit = units.iloc[0]
    assert unit["member_pif_ids"] == [1, 2]
    assert unit["n_pifs"] == 2
    assert unit["length_m"] == pytest.approx(20.0)
    assert units.index[0] == f"{constants.WALL_UNIT_ID_PREFIX}0000001"
    assert units.index.name == "wall_unit_id"
    assert units.geometry.iloc[0].geom_type == "MultiLineString"


def test_pifs_stacked_down_the_slope_stay_two_units():
    top = 10.0 + np.sqrt(4.0**2 - 2.0**2)
    units = _units(_pifs(_pif((0, 0), (0, 10), 90.0), _pif((2, top), (2, 23), 90.0)))
    assert len(units) == 2


def test_parallel_pifs_stacked_down_the_slope_do_not_join_as_a_corner():
    # Both fall south; the second is 2.5 m down the slope (more than the 1.5 m
    # offset) with its facing end 2.7 m away, inside the 3 m corner gap.
    units = _units(
        _pifs(_pif((0, 0), (10, 0), 180.0), _pif((11, -2.5), (21, -2.5), 180.0))
    )
    assert len(units) == 2


def test_ends_facing_different_ways_do_not_join_beyond_the_corner_distance():
    units = _units(_pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 14), (0, 24), 150.0)))
    assert len(units) == 2


def test_a_corner_joins_within_three_metres_at_ninety_degrees():
    units = _units(_pifs(_pif((0, 0), (0, 10), 90.0), _pif((2, 12), (12, 12), 0.0)))
    assert len(units) == 1


def test_pifs_on_different_properties_never_join():
    units = _units(
        _pifs(
            _pif((0, 0), (0, 10), 90.0, property_id="1"),
            _pif((0, 13), (0, 23), 90.0, property_id="2"),
        )
    )
    assert len(units) == 2
    assert sorted(units["property_id"]) == ["1", "2"]


def test_one_gns_wall_joins_pifs_further_apart_than_the_gap():
    sizs = _pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 20), (0, 30), 90.0))
    features = gen_gns_wall_features(
        _layer([shapely.LineString([(0.5, -1), (0.5, 31)])]), snap_m=0.5
    )
    assert len(_units(sizs)) == 2
    assert len(_units(sizs, features=features)) == 1


def test_gns_segments_that_touch_are_one_feature():
    walls = _layer(
        [
            shapely.LineString([(100, 0), (110, 0)]),
            shapely.LineString([(0, 0), (10, 0)]),
            shapely.LineString([(10, 0), (10, 10)]),
        ]
    )
    features = gen_gns_wall_features(walls, snap_m=0.5)
    assert features.index.name == "gns_feature_id"
    assert features.index.tolist() == [0, 1]
    assert len(features.geometry.iloc[0].geoms) == 1
    assert len(features.geometry.iloc[1].geoms) == 2
    assert features.geometry.iloc[1].length == pytest.approx(20.0)
    assert gen_gns_wall_features(_layer([]), snap_m=0.5).empty


def _probability(units):
    prior = gen_wall_prior(units)
    return prior, gen_gns_floor(units, prior)


def test_a_gns_only_piece_within_five_metres_joins_the_pif_and_takes_the_floor():
    sizs = _pifs(_pif((0, 0), (0, 10), 90.0))
    near = _units(sizs, _gns_only([(4, 0), (4, 10)]))
    assert len(near) == 1
    assert near.iloc[0]["member_gns_only_ids"] == [0]
    assert near.iloc[0]["unit_source"] == "pif"
    _, floor = _probability(near)
    assert floor["p_floor"].iloc[0] == pytest.approx(constants.BETA_GNS_WALL_UNIT_FLOOR)
    assert floor["p_floor_basis"].iloc[0] == GNS_FLOOR

    far = _units(sizs, _gns_only([(6, 0), (6, 10)]))
    assert len(far) == 2
    prior, floor = _probability(far)
    by_source = floor.join(far["unit_source"]).set_index("unit_source")
    assert by_source.loc["gns_only", "p_floor"] == pytest.approx(
        constants.BETA_GNS_ONLY_WALL_PROBABILITY
    )
    assert by_source.loc["gns_only", "p_floor_basis"] == GNS_ONLY
    assert by_source.loc["pif", "p_floor"] == pytest.approx(0.5)
    assert prior.loc[far["unit_source"] == "gns_only", "p_prior"].isna().all()


def test_a_gns_only_piece_on_a_road_is_out_of_the_exposure():
    units = _units(
        _pifs(_pif((0, 0), (0, 10), 90.0)),
        _gns_only([(50, 0), (50, 10)], property_id=None),
    )
    gns = units[units["unit_source"] == "gns_only"].iloc[0]
    assert pd.isna(gns["property_id"])
    assert not gns["in_exposure"]
    assert units.loc[units["unit_source"] == "pif", "in_exposure"].all()


def test_a_unit_takes_the_highest_face_nearest_building_and_longest_ground():
    sizs = _pifs(
        _pif(
            (0, 0),
            (0, 10),
            90.0,
            max_delta_h_m=2.0,
            building_m=5.0,
            ground_material="rock",
        ),
        _pif(
            (0, 12),
            (0, 17),
            90.0,
            max_delta_h_m=4.0,
            building_m=3.0,
            ground_material="soil",
            height_band=2,
        ),
    )
    units = _units(sizs, cut_fill=_cut_fill(sizs, heights=[1.5, 2.5]))
    unit = units.iloc[0]
    # The height is the highest member's wall height; the largest pip drop
    # stays for reference.
    assert unit["max_delta_h_m"] == pytest.approx(4.0)
    assert unit["height_m"] == pytest.approx(2.5)
    assert unit["building_m"] == pytest.approx(3.0)
    assert unit["ground_material"] == "rock"
    assert unit["height_band"] == 1
    assert unit["length_m"] == pytest.approx(15.0)


def _unit_frame(**columns):
    defaults = {
        "unit_source": "pif",
        "is_siz": True,
        "gns_wall": False,
        "height_band": 1,
        "ground_material": "soil",
        "height_m": 2.0,
        "cut_fill_class": "uncertain",
    }
    n = max(len(v) for v in columns.values())
    data = {k: columns.get(k, [v] * n) for k, v in defaults.items()}
    return pd.DataFrame(data, index=[f"WU{i:07d}" for i in range(1, n + 1)])


ROCK_F = constants.BETA_ROCK_CUT_FACTOR
FILL_F = constants.BETA_FILL_WALL_FACTOR
NATURAL_F = constants.BETA_NATURAL_WALL_FACTOR

# One unit per row: (class, ground material, height_m, the unit's (siz) height
# band, prior factor on 0.5, basis, is_rock_cut, is_fill, is_natural). The
# prior's band comes from height_m, not the siz band.
PRIOR_CASES = [
    ("uncertain", "soil", 2.0, 1, 1.0, PRIOR, False, False, False),
    ("cut", "rock", 3.0, 1, ROCK_F, ROCK_CUT, True, False, False),
    ("cut", "rock", 2.0, 1, 1.0, PRIOR, False, False, False),
    ("cut", "soil", 3.0, 1, 1.0, PRIOR, False, False, False),
    ("fill", "rock", 3.0, 1, FILL_F, FILL, False, True, False),
    ("cut_and_fill", "soil", 2.0, 1, FILL_F, FILL, False, True, False),
    ("natural", "soil", 2.0, 1, NATURAL_F, NATURAL, False, False, True),
    ("unknown", "rock", 3.0, 1, 1.0, PRIOR, False, False, False),
    ("uncertain", "soil", 4.0, 1, 0.8, PRIOR, False, False, False),
    ("uncertain", "soil", 2.0, 2, 1.0, PRIOR, False, False, False),
]


def test_the_prior_follows_the_siz_band_and_cut_and_fill_class():
    cases = list(zip(*PRIOR_CASES, strict=True))
    units = _unit_frame(
        cut_fill_class=list(cases[0]),
        ground_material=list(cases[1]),
        height_m=list(cases[2]),
        height_band=list(cases[3]),
    )
    prior = gen_wall_prior(units)
    assert prior["p_prior"].tolist() == pytest.approx([0.5 * f for f in cases[4]])
    assert prior["p_prior_basis"].tolist() == list(cases[5])
    assert prior["prior_height_band"].tolist() == [1] * 8 + [2, 1]
    assert prior["is_rock_cut"].tolist() == list(cases[6])
    assert prior["is_fill"].tolist() == list(cases[7])
    assert prior["is_natural"].tolist() == list(cases[8])


def test_ground_map_fill_no_longer_sets_the_prior():
    units = _unit_frame(
        ground_material=["fill_uncontrolled", "rock"],
        cut_fill_class=["uncertain", "uncertain"],
    ).assign(ground_modification="fill", in_slide_fill=True)
    prior = gen_wall_prior(units)
    assert prior["p_prior"].tolist() == pytest.approx([0.5, 0.5])
    assert not prior["is_fill"].any()


def test_the_wall_height_is_the_quantile_of_the_pips_face_drops():
    pips = pd.DataFrame(
        {
            "pif_id": [7, 7, 7, 7, 7, 3],
            "z": [11.0, 12.0, 13.0, 14.0, 15.0, 5.0],
            "foot_z": [10.0] * 5 + [4.5],
        }
    )
    heights = gen_pif_wall_heights(pips, quantile=0.8)
    assert heights.name == "wall_height_m"
    assert heights.index.name == "pif_id"
    # Drops of 1 to 5 m: the 80th percentile is 4.2 m (linear), the largest 5 m.
    assert heights.loc[7] == pytest.approx(4.2)
    assert heights.loc[3] == pytest.approx(0.5)
    assert gen_pif_wall_heights(pips, quantile=1.0).loc[7] == pytest.approx(5.0)
    with pytest.raises(ValueError, match="quantile"):
        gen_pif_wall_heights(pips, quantile=80)


def test_a_candidate_pif_missing_from_step_13_stops_the_members():
    sizs = _pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 13), (0, 23), 90.0))
    with pytest.raises(ValueError, match="step 13"):
        gen_wall_members(sizs, NO_GNS_ONLY, _cut_fill(sizs).iloc[:1])


def test_a_unit_takes_the_class_of_its_longest_pif():
    sizs = _pifs(_pif((0, 0), (0, 10), 90.0), _pif((0, 13), (0, 18), 90.0))
    units = _units(sizs, cut_fill=_cut_fill(sizs, classes=["cut", "fill"]))
    assert len(units) == 1
    assert units["cut_fill_class"].iloc[0] == "cut"


def test_a_tie_for_the_longest_pif_takes_the_most_common_class():
    sizs = _pifs(
        _pif((0, 0), (0, 10), 90.0),
        _pif((0, 13), (0, 23), 90.0),
        _pif((0, 26), (0, 30), 90.0),
    )
    units = _units(sizs, cut_fill=_cut_fill(sizs, classes=["cut", "fill", "fill"]))
    assert len(units) == 1
    assert units["cut_fill_class"].iloc[0] == "fill"
    # An even tie goes to the class of the tied pif with the lowest id.
    units = _units(sizs, cut_fill=_cut_fill(sizs, classes=["natural", "cut", "fill"]))
    assert units["cut_fill_class"].iloc[0] == "natural"


def test_a_gns_only_unit_is_class_unknown():
    units = _units(
        _pifs(_pif((0, 0), (0, 10), 90.0)),
        _gns_only([(50, 0), (50, 10)]),
    )
    by_source = units.set_index("unit_source")["cut_fill_class"]
    assert by_source.loc["gns_only"] == "unknown"
    assert by_source.loc["pif"] == "uncertain"


def test_a_small_unit_carries_the_small_prior_and_the_floor_sets_it():
    units = _unit_frame(is_siz=[False], gns_wall=[True])
    prior, floor = _probability(units)
    assert prior["p_prior"].iloc[0] == pytest.approx(constants.BETA_SMALL_WALL_PRIOR)
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
        {"p_floor": [0.5, 0.5, 0.5, 0.0, 0.5], "p_floor_basis": PRIOR},
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


def _update(units, floor, records, held_out=None, *, use_nzmm=False, weight=1.0):
    return gen_wall_unit_probability(
        units,
        floor,
        records=records,
        held_out=pd.Series(dtype=bool) if held_out is None else held_out,
        nzmm_min_walls=constants.BETA_NZMM_MIN_WALLS,
        nzmm_weight=weight,
        use_nzmm=use_nzmm,
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
        PRIOR,
        PRIOR,
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


def test_the_nzmm_update_is_tempered_by_its_weight():
    units, floor = _two_property_units()
    records = _records(**{"1": (pd.NA, True), "2": (1, True)})
    weight = constants.BETA_NZMM_UPDATE_WEIGHT
    used, _ = _update(units, floor, records, use_nzmm=True, weight=weight)
    # Property 1: no claim, so the claims update leaves 0.5; the full NZMM
    # update on two walls takes both units to 1.
    assert used["p_wall"].iloc[:2].tolist() == pytest.approx([0.5 + weight * 0.5] * 2)
    assert used["p_claims"].iloc[:2].tolist() == pytest.approx([0.5, 0.5])
    # Property 2: one unit can be a wall, so the claim takes it to 1 and NZMM
    # adds nothing.
    assert used["p_wall"].iloc[2] == pytest.approx(1.0)
    none, _ = _update(units, floor, records, use_nzmm=True, weight=0.0)
    assert none["p_claims_nzmm"].tolist() == pytest.approx(none["p_claims"].tolist())


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


def test_nzmm_adds_two_walls_only_when_used():
    units, floor = _two_property_units()
    records = _records(**{"1": (pd.NA, True)})
    without, _ = _update(units, floor, records)
    assert without["p_wall"].tolist() == pytest.approx(floor["p_floor"].tolist())
    assert without["p_claims_nzmm"].iloc[:2].tolist() == pytest.approx([1.0, 1.0])
    used, missing = _update(units, floor, records, use_nzmm=True)
    # At full weight NZMM is as strong as a claim listing two walls.
    assert used["p_wall"].iloc[:2].tolist() == pytest.approx([1.0, 1.0])
    assert used["p_wall_basis"].iloc[:2].tolist() == [NZMM, NZMM]
    assert missing.empty


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
