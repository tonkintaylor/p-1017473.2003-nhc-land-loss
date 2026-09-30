import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, Point, box

from landloss.exposure.rw.beta_population import (
    BETA_MAX_PREVALENCE,
    SIZE_CLASSES,
    beta_wall_prevalence,
)
from landloss.exposure.rw.wall_probability import (
    BETA_MAPPED_WALL_PROBABILITY,
    BETA_PLAIN_MAX_PREVALENCE,
    MAPPED_WALL_TYPE,
    PROBABILITY_COLUMNS,
    attach_evidence,
    draw_walls,
    engineered_share,
    landform_at,
    mapped_wall_length_m,
    size_class_probabilities,
    wall_probability,
    wall_probability_table,
)
from landloss.hazard.realisation import realisation_seed

CRS = "EPSG:2193"
X0, Y0 = 1_750_000.0, 5_424_000.0


def rng():
    return realisation_seed(1, 0, "exposure")


def section(i=0, size=20.0):
    return box(X0 + i * 100, Y0, X0 + i * 100 + size, Y0 + size)


def properties(n=400, slope=20.0, azimuth=90.0, area=400.0):
    """Points with the terrain and evidence columns, the table's input."""
    return gpd.GeoDataFrame(
        {
            "claim_id": [f"A-{i:04d}" for i in range(n)],
            "slope_deg": np.full(n, slope),
            "downhill_azimuth_deg": np.full(n, azimuth),
            "area_m2": np.full(n, area),
            "mapped_wall_length_m": np.zeros(n),
            "engineered_share": np.zeros(n),
            "landform": np.full(n, "Hills, ranges and mountains"),
            "on_plain": np.zeros(n, dtype=bool),
        },
        geometry=[Point(X0 + i, Y0) for i in range(n)],
        crs=CRS,
    )


def lines(*coords, kind=MAPPED_WALL_TYPE):
    return gpd.GeoDataFrame(
        {"Type": [kind] * len(coords)},
        geometry=[LineString(c) for c in coords],
        crs=CRS,
    )


# --- the evidence ------------------------------------------------------------


def test_a_mapped_wall_on_the_section_is_measured_inside_it():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    wall = lines([(X0 + 5, Y0 + 10), (X0 + 15, Y0 + 10)])
    assert mapped_wall_length_m(polygons, wall)[0] == pytest.approx(10.0)


def test_a_mapped_wall_beside_the_section_counts_within_the_buffer():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    # 1 m outside the east edge, inside the 2 m buffer.
    wall = lines([(X0 + 21, Y0 + 5), (X0 + 21, Y0 + 15)])
    assert mapped_wall_length_m(polygons, wall)[0] == pytest.approx(10.0)


def test_a_mapped_wall_far_from_the_section_is_not_counted():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    wall = lines([(X0 + 60, Y0), (X0 + 60, Y0 + 10)])
    assert mapped_wall_length_m(polygons, wall)[0] == 0.0


def test_only_retaining_walls_count_as_mapped_walls():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    cliff = lines([(X0 + 5, Y0 + 10), (X0 + 15, Y0 + 10)], kind="Cliff")
    assert mapped_wall_length_m(polygons, cliff)[0] == 0.0


def test_a_wall_is_measured_against_its_own_section_only():
    polygons = gpd.GeoSeries([section(0), section(1)], crs=CRS)
    wall = lines([(X0 + 105, Y0 + 10), (X0 + 115, Y0 + 10)])
    lengths = mapped_wall_length_m(polygons, wall)
    assert lengths[0] == 0.0
    assert lengths[1] == pytest.approx(10.0)


def test_no_mapped_walls_gives_zero_everywhere():
    polygons = gpd.GeoSeries([section(0), section(1)], crs=CRS)
    assert not mapped_wall_length_m(polygons, lines(kind="Cliff")).any()


def test_the_engineered_share_is_the_area_on_a_cut_or_fill():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    genesis = gpd.GeoDataFrame(
        {"Type": ["Cut slope"]},
        geometry=[box(X0, Y0, X0 + 10, Y0 + 20)],
        crs=CRS,
    )
    assert engineered_share(polygons, genesis)[0] == pytest.approx(0.5)


def test_other_genesis_types_are_not_earthworks():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    genesis = gpd.GeoDataFrame(
        {"Type": ["Landslide recent"]}, geometry=[section()], crs=CRS
    )
    assert engineered_share(polygons, genesis)[0] == 0.0


def test_overlapping_earthworks_cannot_exceed_the_whole_section():
    polygons = gpd.GeoSeries([section()], crs=CRS)
    genesis = gpd.GeoDataFrame(
        {"Type": ["Cut slope", "Fill body"]},
        geometry=[section(), section()],
        crs=CRS,
    )
    assert engineered_share(polygons, genesis)[0] == pytest.approx(1.0)


def test_the_landform_is_the_class_of_the_polygon_holding_the_point():
    points = gpd.GeoSeries([Point(X0 + 5, Y0 + 5), Point(X0 + 500, Y0)], crs=CRS)
    nlm = gpd.GeoDataFrame(
        {"l2_geomorphology": ["Coastal lowlands"]},
        geometry=[box(X0, Y0, X0 + 50, Y0 + 50)],
        crs=CRS,
    )
    assert list(landform_at(points, nlm)) == ["Coastal lowlands", ""]


def test_attaching_evidence_adds_the_columns_and_flags_plains():
    props = gpd.GeoDataFrame({"claim_id": ["A"]}, geometry=[section()], crs=CRS)
    nlm = gpd.GeoDataFrame(
        {"l2_geomorphology": ["Alluvial plains and river flats"]},
        geometry=[box(X0 - 10, Y0 - 10, X0 + 50, Y0 + 50)],
        crs=CRS,
    )
    genesis = gpd.GeoDataFrame({"Type": ["Fan"]}, geometry=[section()], crs=CRS)
    out = attach_evidence(
        props, morphology=lines(kind="Cliff"), genesis=genesis, geomorphology=nlm
    )
    assert bool(out["on_plain"].iloc[0])
    assert out["mapped_wall_length_m"].iloc[0] == 0.0
    assert out.geometry.iloc[0].equals(section())


# --- the probability ---------------------------------------------------------


def probability(slope, *, mapped=0.0, engineered=0.0, plain=False):
    return float(
        wall_probability(
            np.array([slope]),
            mapped_length_m=np.array([mapped]),
            engineered=np.array([engineered]),
            on_plain=np.array([plain]),
        )[0]
    )


def test_without_evidence_the_probability_is_the_slope_prevalence():
    assert probability(15.0) == pytest.approx(float(beta_wall_prevalence(15.0)))


def test_a_mapped_wall_lifts_a_flat_property_to_the_mapped_probability():
    assert probability(0.0, mapped=12.0) == pytest.approx(BETA_MAPPED_WALL_PROBABILITY)


def test_a_mapped_wall_never_lowers_a_steep_property():
    steep = probability(40.0)
    assert probability(40.0, mapped=12.0) >= steep


def test_a_sliver_of_mapped_wall_is_not_evidence():
    assert probability(0.0, mapped=0.5) == pytest.approx(0.0)


def test_earthworks_lift_a_flat_property_in_proportion_to_their_share():
    assert probability(0.0, engineered=1.0) > probability(0.0, engineered=0.5) > 0.0


def test_a_plain_caps_the_prevalence_unless_a_wall_is_mapped():
    assert probability(40.0, plain=True) == pytest.approx(BETA_PLAIN_MAX_PREVALENCE)
    assert probability(40.0, plain=True, mapped=12.0) == pytest.approx(
        BETA_MAPPED_WALL_PROBABILITY
    )


def test_no_slope_gives_no_probability():
    assert np.isnan(probability(np.nan, mapped=12.0))


def test_the_probability_is_never_above_one():
    assert probability(90.0, mapped=50.0, engineered=1.0) <= 1.0
    assert BETA_MAX_PREVALENCE <= 1.0


# --- the height distribution -------------------------------------------------


def test_the_size_class_probabilities_sum_to_one():
    shares = size_class_probabilities(np.linspace(0.3, 4.0, 30))
    assert shares.shape == (30, len(SIZE_CLASSES))
    assert np.allclose(shares.sum(axis=1), 1.0)
    assert (shares >= 0).all()


def test_a_taller_median_shifts_probability_towards_large():
    low, high = size_class_probabilities(np.array([0.5, 3.0]))
    assert high[2] > low[2]
    assert high[0] < low[0]


def test_a_median_at_the_boundary_is_split_evenly_across_it():
    small, _, _ = size_class_probabilities(np.array([1.0]))[0]
    assert small == pytest.approx(0.5)


# --- the table ---------------------------------------------------------------


def test_the_table_carries_every_probability_column():
    table = wall_probability_table(properties(n=5))
    for column in PROBABILITY_COLUMNS:
        assert column in table.columns
    assert table.crs == CRS
    assert len(table) == 5


def test_the_table_keeps_a_property_with_no_slope_as_nan():
    props = properties(n=3)
    props.loc[0, "slope_deg"] = np.nan
    table = wall_probability_table(props)
    assert np.isnan(table["p_wall"].iloc[0])
    assert table["p_wall"].iloc[1:].notna().all()


def test_a_missing_column_is_refused_by_the_table():
    with pytest.raises(ValueError, match="engineered_share"):
        wall_probability_table(properties().drop(columns=["engineered_share"]))


# --- the realisation ---------------------------------------------------------


def test_the_share_of_properties_with_a_wall_tracks_the_probability():
    table = wall_probability_table(properties(n=4000, slope=20.0))
    walls = draw_walls(table, rng())
    expected = float(beta_wall_prevalence(20.0))
    assert walls["claim_id"].nunique() == len(walls)
    assert abs(len(walls) / len(table) - expected) < 0.03


def test_flat_properties_draw_no_walls_at_all():
    assert draw_walls(wall_probability_table(properties(slope=0.0)), rng()).empty


def test_a_property_with_no_slope_sampled_draws_nothing():
    props = properties(n=200, slope=20.0)
    props["slope_deg"] = np.nan
    assert draw_walls(wall_probability_table(props), rng()).empty


def test_a_mapped_property_draws_a_wall_almost_always():
    props = properties(n=2000, slope=0.0)
    props["mapped_wall_length_m"] = 12.0
    walls = draw_walls(wall_probability_table(props), rng())
    assert abs(len(walls) / len(props) - BETA_MAPPED_WALL_PROBABILITY) < 0.03


def test_the_drawn_size_classes_follow_the_class_probabilities():
    table = wall_probability_table(properties(n=6000, slope=15.0))
    drawn = draw_walls(table, rng())["size_class"].value_counts(normalize=True)
    for name in SIZE_CLASSES:
        expected = table[f"p_{name}"].iloc[0]
        assert drawn.get(name, 0.0) == pytest.approx(expected, abs=0.04)


def test_the_population_carries_the_columns_the_chain_reads():
    walls = draw_walls(wall_probability_table(properties()), rng())
    for column in (
        "claim_id",
        "size_class",
        "initial_condition",
        "height_m",
        "length_m",
    ):
        assert column in walls.columns
    assert walls.geometry.geom_type.eq("LineString").all()
    assert walls.crs == CRS


def test_the_same_realisation_draws_the_same_population():
    table = wall_probability_table(properties())
    first = draw_walls(table, rng())
    second = draw_walls(table, rng())
    assert first["claim_id"].tolist() == second["claim_id"].tolist()
    assert first["height_m"].tolist() == second["height_m"].tolist()


def test_different_realisations_draw_different_populations():
    table = wall_probability_table(properties())
    first = draw_walls(table, realisation_seed(1, 0, "exposure"))
    second = draw_walls(table, realisation_seed(1, 1, "exposure"))
    assert first["claim_id"].tolist() != second["claim_id"].tolist()


def test_a_missing_probability_column_is_refused_by_the_draw():
    table = wall_probability_table(properties()).drop(columns=["p_poor"])
    with pytest.raises(ValueError, match="p_poor"):
        draw_walls(table, rng())
