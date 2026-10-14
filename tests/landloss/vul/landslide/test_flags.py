import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import GeometryCollection, LineString, Point, box

from landloss.hazard.landslide.land_class import EVACUATED, IMMINENT, INUNDATED
from landloss.hazard.landslide.urban.realisation import (
    ABSORBED,
    FAILED_WITH_POLYGON,
    OUTCOMES,
    STANDING,
    SUPERSEDED,
)
from landloss.vul.landslide.flags import (
    DAMAGED_LENGTH_COLUMN,
    DAMAGED_LINE_COLUMN,
    EVACUATED_LENGTH_COLUMN,
    INUNDATED_LENGTH_COLUMN,
    OUTCOME_FLAGS,
    WALL_DAMAGE_COLUMNS,
    WALL_FLAG_COLUMNS,
    landslide_flags,
    outcome_flags,
    wall_flags,
)

CRS = "EPSG:2193"


def assets(*ids_and_geoms, crs=CRS):
    ids = [asset_id for asset_id, _ in ids_and_geoms]
    geoms = [geom for _, geom in ids_and_geoms]
    return gpd.GeoDataFrame({"rw_id": ids}, geometry=geoms, crs=crs)


def slides(*classes_and_geoms, crs=CRS):
    classes = [land_class for land_class, _ in classes_and_geoms]
    geoms = [geom for _, geom in classes_and_geoms]
    return gpd.GeoDataFrame({"land_class": classes}, geometry=geoms, crs=crs)


def outcomes(*rows):
    """One outcome row per (rw_id, slope_id, outcome)."""
    return pd.DataFrame(
        {
            "rw_id": [rw_id for rw_id, _, _ in rows],
            "slope_id": [slope_id for _, slope_id, _ in rows],
            "outcome": [outcome for _, _, outcome in rows],
        }
    )


EVACUATED_CIRCLE = (EVACUATED, Point(0, 0).buffer(10))
INUNDATED_CIRCLE = (INUNDATED, Point(100, 0).buffer(10))
IMMINENT_CIRCLE = (IMMINENT, Point(200, 0).buffer(10))


def test_a_line_crossing_evacuated_ground_is_evacuated():
    walls = assets(("A-RW01", LineString([(-20, 0), (20, 0)])))
    flags = landslide_flags(walls, slides(EVACUATED_CIRCLE), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True]
    assert flags["is_inundated"].tolist() == [False]


def test_a_line_crossing_inundated_ground_is_inundated():
    walls = assets(("A-RW01", LineString([(80, 0), (120, 0)])))
    flags = landslide_flags(walls, slides(INUNDATED_CIRCLE), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]
    assert flags["is_inundated"].tolist() == [True]


def test_a_line_through_both_kinds_of_ground_carries_both_flags():
    walls = assets(("A-RW01", LineString([(-20, 0), (120, 0)])))
    hazard = slides(EVACUATED_CIRCLE, INUNDATED_CIRCLE)
    flags = landslide_flags(walls, hazard, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True]
    assert flags["is_inundated"].tolist() == [True]


def test_an_asset_clear_of_every_landslide_carries_neither_flag():
    walls = assets(("A-RW01", LineString([(40, 50), (60, 50)])))
    hazard = slides(EVACUATED_CIRCLE, INUNDATED_CIRCLE)
    flags = landslide_flags(walls, hazard, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]
    assert flags["is_inundated"].tolist() == [False]


def test_imminent_ground_sets_no_flag():
    walls = assets(("A-RW01", LineString([(180, 0), (220, 0)])))
    flags = landslide_flags(walls, slides(IMMINENT_CIRCLE), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]
    assert flags["is_inundated"].tolist() == [False]


def test_polygon_and_collection_assets_are_flagged():
    crossings = assets(
        ("A-X01", box(-5, -5, 5, 5)),
        (
            "B-X01",
            GeometryCollection([LineString([(90, 0), (110, 0)]), box(0, 50, 1, 51)]),
        ),
    )
    hazard = slides(EVACUATED_CIRCLE, INUNDATED_CIRCLE)
    flags = landslide_flags(crossings, hazard, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True, False]
    assert flags["is_inundated"].tolist() == [False, True]


def test_no_landslides_leaves_every_asset_unflagged():
    walls = assets(("A-RW01", LineString([(-20, 0), (20, 0)])))
    flags = landslide_flags(walls, slides(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]
    assert flags["is_inundated"].tolist() == [False]


def test_no_assets_gives_an_empty_frame_with_boolean_flags():
    flags = landslide_flags(assets(), slides(EVACUATED_CIRCLE), id_column="rw_id")
    assert flags.empty
    assert list(flags.columns) == ["rw_id", "is_evacuated", "is_inundated"]
    assert flags["is_evacuated"].dtype == bool
    assert flags["is_inundated"].dtype == bool


def test_a_crs_mismatch_is_refused():
    walls = assets(("A-RW01", LineString([(-20, 0), (20, 0)])))
    with pytest.raises(ValueError, match="landslides are"):
        landslide_flags(
            walls, slides(EVACUATED_CIRCLE, crs="EPSG:3857"), id_column="rw_id"
        )


def test_repeated_ids_are_refused():
    walls = assets(
        ("A-RW01", LineString([(-20, 0), (20, 0)])),
        ("A-RW01", LineString([(40, 50), (60, 50)])),
    )
    with pytest.raises(ValueError, match="repeat"):
        landslide_flags(walls, slides(EVACUATED_CIRCLE), id_column="rw_id")


def test_landslides_without_a_land_class_are_refused():
    walls = assets(("A-RW01", LineString([(-20, 0), (20, 0)])))
    hazard = slides(EVACUATED_CIRCLE).drop(columns="land_class")
    with pytest.raises(ValueError, match="land_class"):
        landslide_flags(walls, hazard, id_column="rw_id")


def test_the_output_follows_the_input_order():
    walls = assets(
        ("C-RW01", LineString([(40, 50), (60, 50)])),
        ("A-RW01", LineString([(80, 0), (120, 0)])),
        ("B-RW01", LineString([(-20, 0), (20, 0)])),
    )
    hazard = slides(EVACUATED_CIRCLE, INUNDATED_CIRCLE)
    flags = landslide_flags(walls, hazard, id_column="rw_id")
    assert flags["rw_id"].tolist() == ["C-RW01", "A-RW01", "B-RW01"]
    assert flags["is_evacuated"].tolist() == [False, False, True]
    assert flags["is_inundated"].tolist() == [False, True, False]


# The outcome mapping, contract section 5.2.


def test_the_mapping_covers_every_outcome_but_standing():
    assert set(OUTCOME_FLAGS) == set(OUTCOMES) - {STANDING}


def test_each_outcome_sets_the_flag_the_contract_says():
    table = outcomes(
        ("A-RW01", "SP0000001", FAILED_WITH_POLYGON),
        ("A-RW02", "SP0000002", ABSORBED),
        ("A-RW03", "SP0000003", SUPERSEDED),
        ("A-RW04", "SP0000004", STANDING),
        ("A-RW05", None, STANDING),
    )
    flags = outcome_flags(table, id_column="rw_id")
    assert list(flags.columns) == ["rw_id", "slope_id", "outcome", *WALL_FLAG_COLUMNS]
    assert flags["is_damaged_by_shaking"].tolist() == [True, False, False, False, False]
    assert flags["is_evacuated"].tolist() == [False, True, True, False, False]
    # No outcome sets the inundated flag; that is geometry's alone.
    assert flags["is_inundated"].tolist() == [False] * 5
    assert flags["slope_id"].tolist()[:4] == [f"SP000000{n}" for n in range(1, 5)]
    assert flags["slope_id"].iloc[4] is None
    for column in WALL_FLAG_COLUMNS:
        assert flags[column].dtype == bool


def test_an_unknown_outcome_is_refused():
    table = outcomes(("A-RW01", "SP0000001", "vanished"))
    with pytest.raises(ValueError, match="vanished"):
        outcome_flags(table, id_column="rw_id")


def test_a_repeated_wall_in_the_outcomes_is_refused():
    table = outcomes(
        ("A-RW01", "SP0000001", STANDING), ("A-RW01", "SP0000002", ABSORBED)
    )
    with pytest.raises(ValueError, match="repeat"):
        outcome_flags(table, id_column="rw_id")


def test_an_outcome_table_missing_a_column_is_refused():
    table = outcomes(("A-RW01", "SP0000001", STANDING)).drop(columns="slope_id")
    with pytest.raises(ValueError, match="slope_id"):
        outcome_flags(table, id_column="rw_id")


def test_no_outcomes_gives_an_empty_frame_with_boolean_flags():
    flags = outcome_flags(outcomes(), id_column="rw_id")
    assert flags.empty
    for column in WALL_FLAG_COLUMNS:
        assert flags[column].dtype == bool


# The two routes OR-ed, per wall.


def test_the_outcome_and_the_geometry_are_or_ed():
    walls = assets(
        # Failed with its polygon, clear of every landslide polygon.
        ("A-RW01", LineString([(40, 50), (60, 50)])),
        # Standing, but its line crosses inundated ground.
        ("A-RW02", LineString([(80, 0), (120, 0)])),
        # Absorbed, and also crossing evacuated ground.
        ("A-RW03", LineString([(-20, 0), (20, 0)])),
        # A flat-land wall: no outcome row, clear of everything.
        ("A-RW04", LineString([(40, 80), (60, 80)])),
    )
    hazard = slides(EVACUATED_CIRCLE, INUNDATED_CIRCLE)
    table = outcomes(
        ("A-RW01", "SP0000001", FAILED_WITH_POLYGON),
        ("A-RW02", "SP0000002", STANDING),
        ("A-RW03", "SP0000003", ABSORBED),
    )
    flags = wall_flags(walls, hazard, table, id_column="rw_id")
    assert list(flags.columns) == [
        "rw_id",
        "slope_id",
        "outcome",
        *WALL_FLAG_COLUMNS,
        *WALL_DAMAGE_COLUMNS,
    ]
    assert flags["rw_id"].tolist() == ["A-RW01", "A-RW02", "A-RW03", "A-RW04"]
    assert flags["is_damaged_by_shaking"].tolist() == [True, False, False, False]
    assert flags["is_evacuated"].tolist() == [False, False, True, False]
    assert flags["is_inundated"].tolist() == [False, True, False, False]
    assert flags["slope_id"].tolist() == ["SP0000001", "SP0000002", "SP0000003", None]
    assert flags["outcome"].tolist() == [
        FAILED_WITH_POLYGON,
        STANDING,
        ABSORBED,
        None,
    ]
    for column in WALL_FLAG_COLUMNS:
        assert flags[column].dtype == bool


def test_a_superseded_wall_is_evacuated_even_off_every_polygon():
    walls = assets(("A-RW01", LineString([(40, 50), (60, 50)])))
    table = outcomes(("A-RW01", "SP0000001", SUPERSEDED))
    flags = wall_flags(walls, slides(), table, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True]
    assert flags["is_damaged_by_shaking"].tolist() == [False]


def test_an_outcome_for_a_wall_not_in_the_population_is_refused():
    walls = assets(("A-RW01", LineString([(40, 50), (60, 50)])))
    table = outcomes(("Z-RW09", "SP0000001", STANDING))
    with pytest.raises(ValueError, match="not in the population"):
        wall_flags(walls, slides(), table, id_column="rw_id")


def test_walls_without_outcomes_take_geometry_alone():
    walls = assets(
        ("A-RW01", LineString([(-20, 0), (20, 0)])),
        ("A-RW02", LineString([(40, 50), (60, 50)])),
    )
    hazard = slides(EVACUATED_CIRCLE)
    flags = wall_flags(walls, hazard, outcomes(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True, False]
    assert flags["is_damaged_by_shaking"].tolist() == [False, False]
    assert flags["outcome"].tolist() == [None, None]


# A wall is reached only where its line lies inside the polygon.

# Two urban polygons tiling the ground, sharing the edge x = 10.
NEIGHBOUR = box(0, 0, 10, 10)
OWN_POLYGON = box(10, 0, 20, 10)
SHARED_EDGE = LineString([(10, 0), (10, 10)])


def test_a_wall_along_the_edge_of_a_failed_neighbour_is_not_flagged():
    walls = assets(("A-RW01", SHARED_EDGE))
    hazard = slides((EVACUATED, NEIGHBOUR), (INUNDATED, NEIGHBOUR))
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    flags = wall_flags(walls, hazard, table, id_column="rw_id")
    for column in WALL_FLAG_COLUMNS:
        assert flags[column].tolist() == [False]


def test_a_wall_within_noise_of_the_edge_is_not_flagged():
    walls = assets(("A-RW01", LineString([(10 - 1e-6, 0), (10 - 1e-6, 10)])))
    hazard = slides((EVACUATED, NEIGHBOUR))
    flags = wall_flags(walls, hazard, outcomes(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]


def test_a_wall_touching_a_polygon_at_a_point_is_not_flagged():
    walls = assets(("A-RW01", LineString([(10, 5), (15, 5)])))
    hazard = slides((EVACUATED, NEIGHBOUR))
    flags = wall_flags(walls, hazard, outcomes(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]


def test_a_wall_with_a_length_inside_the_polygon_is_flagged():
    walls = assets(
        # Crosses the neighbour's edge and runs a metre into it.
        ("A-RW01", LineString([(15, 5), (9, 5)])),
        # Runs along the edge, then turns into the neighbour.
        ("A-RW02", LineString([(10, 0), (10, 10), (5, 10), (5, 5)])),
    )
    hazard = slides((EVACUATED, NEIGHBOUR), (EVACUATED, OWN_POLYGON.buffer(-5)))
    flags = wall_flags(walls, hazard, outcomes(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True, True]


def test_a_wall_index_that_is_not_a_range_still_lines_up():
    walls = assets(
        ("A-RW01", SHARED_EDGE),
        ("A-RW02", LineString([(15, 5), (5, 5)])),
    ).set_index(pd.Index([7, 3]))
    hazard = slides((EVACUATED, NEIGHBOUR))
    flags = wall_flags(walls, hazard, outcomes(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False, True]


def test_any_other_structure_on_the_edge_is_still_caught():
    crossings = assets(("A-X01", SHARED_EDGE))
    flags = landslide_flags(
        crossings, slides((EVACUATED, NEIGHBOUR)), id_column="rw_id"
    )
    assert flags["is_evacuated"].tolist() == [True]


# A wall's own polygon does not evacuate it (the lead, 2026-10-13).


def slides_with_slopes(*rows, crs=CRS):
    """Landslide rows of (land_class, slope_id, geometry)."""
    return gpd.GeoDataFrame(
        {
            "land_class": [land_class for land_class, _, _ in rows],
            "slope_id": [slope_id for _, slope_id, _ in rows],
        },
        geometry=[geom for _, _, geom in rows],
        crs=crs,
    )


INSIDE_BOTH = LineString([(2, 5), (18, 5)])


def test_a_wall_inside_only_its_own_evacuated_polygon_is_not_evacuated():
    walls = assets(("A-RW01", LineString([(12, 5), (18, 5)])))
    hazard = slides_with_slopes((EVACUATED, "SP0000002", OWN_POLYGON))
    table = outcomes(("A-RW01", "SP0000002", FAILED_WITH_POLYGON))
    flags = wall_flags(walls, hazard, table, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]
    assert flags["is_damaged_by_shaking"].tolist() == [True]


def test_another_slopes_evacuated_polygon_still_evacuates_the_wall():
    walls = assets(("A-RW01", INSIDE_BOTH))
    hazard = slides_with_slopes(
        (EVACUATED, "SP0000001", NEIGHBOUR), (EVACUATED, "SP0000002", OWN_POLYGON)
    )
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    flags = wall_flags(walls, hazard, table, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True]


def test_the_own_polygons_inundated_ground_does_not_flag_the_wall():
    walls = assets(("A-RW01", LineString([(12, 5), (18, 5)])))
    hazard = slides_with_slopes(
        (EVACUATED, "SP0000002", OWN_POLYGON), (INUNDATED, "SP0000002", OWN_POLYGON)
    )
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    flags = wall_flags(walls, hazard, table, id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [False]
    assert flags["is_inundated"].tolist() == [False]


def test_another_slopes_inundated_ground_still_flags_the_wall():
    walls = assets(("A-RW01", INSIDE_BOTH))
    hazard = slides_with_slopes(
        (INUNDATED, "SP0000001", NEIGHBOUR), (INUNDATED, "SP0000002", OWN_POLYGON)
    )
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    flags = wall_flags(walls, hazard, table, id_column="rw_id")
    assert flags["is_inundated"].tolist() == [True]


def test_a_wall_with_no_outcome_is_evacuated_by_any_polygon():
    walls = assets(("A-RW01", LineString([(12, 5), (18, 5)])))
    hazard = slides_with_slopes((EVACUATED, "SP0000002", OWN_POLYGON))
    flags = wall_flags(walls, hazard, outcomes(), id_column="rw_id")
    assert flags["is_evacuated"].tolist() == [True]


# How much of a wall a landslide damages (T-158).


def damage(walls, hazard, table):
    """Return the flags and damaged lengths of ``walls``, by wall id."""
    return wall_flags(walls, hazard, table, id_column="rw_id").set_index("rw_id")


def test_a_wall_clipped_by_a_neighbour_is_damaged_over_the_clipped_length_only():
    # 4 m of a 10 m wall lies inside the neighbour's evacuated ground.
    walls = assets(("A-RW01", LineString([(-6, 5), (4, 5)])))
    hazard = slides_with_slopes((EVACUATED, "SP0000001", NEIGHBOUR))
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row["is_evacuated"]
    assert row[EVACUATED_LENGTH_COLUMN] == pytest.approx(4.0, abs=0.02)
    assert row[DAMAGED_LENGTH_COLUMN] == pytest.approx(4.0, abs=0.02)
    assert row[DAMAGED_LINE_COLUMN].length == pytest.approx(4.0, abs=0.02)
    assert row[DAMAGED_LINE_COLUMN].bounds[0] == pytest.approx(0.0, abs=0.02)


def test_a_wall_damaged_by_shaking_is_damaged_over_its_whole_line_even_when_clipped():
    line = LineString([(-6, 5), (4, 5)])
    walls = assets(("A-RW01", line))
    hazard = slides_with_slopes((EVACUATED, "SP0000001", NEIGHBOUR))
    table = outcomes(("A-RW01", "SP0000002", FAILED_WITH_POLYGON))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row[DAMAGED_LENGTH_COLUMN] == pytest.approx(10.0)
    assert row[DAMAGED_LINE_COLUMN].equals(line)


def test_a_wall_in_inundated_ground_only_keeps_the_flag_but_is_not_damaged():
    walls = assets(("A-RW01", LineString([(-6, 5), (4, 5)])))
    hazard = slides_with_slopes((INUNDATED, "SP0000001", NEIGHBOUR))
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row["is_inundated"]
    assert not row["is_evacuated"]
    assert row[INUNDATED_LENGTH_COLUMN] == pytest.approx(4.0, abs=0.02)
    assert row[EVACUATED_LENGTH_COLUMN] == 0.0
    assert row[DAMAGED_LENGTH_COLUMN] == 0.0
    assert row[DAMAGED_LINE_COLUMN].is_empty


def test_evacuated_and_inundated_lengths_are_measured_apart():
    walls = assets(("A-RW01", LineString([(-6, 5), (4, 5)])))
    hazard = slides_with_slopes(
        (EVACUATED, "SP0000001", box(0, 0, 10, 10)),
        (INUNDATED, "SP0000003", box(-3, 0, 2, 10)),
    )
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row[EVACUATED_LENGTH_COLUMN] == pytest.approx(4.0, abs=0.02)
    assert row[INUNDATED_LENGTH_COLUMN] == pytest.approx(5.0, abs=0.02)
    assert row[DAMAGED_LENGTH_COLUMN] == pytest.approx(4.0, abs=0.02)


def test_a_line_along_a_failures_edge_is_not_damaged():
    walls = assets(("A-RW01", SHARED_EDGE))
    hazard = slides_with_slopes((EVACUATED, "SP0000001", NEIGHBOUR))
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row[DAMAGED_LENGTH_COLUMN] == 0.0
    assert row[DAMAGED_LINE_COLUMN].is_empty


def test_overlapping_failures_count_a_stretch_once():
    walls = assets(("A-RW01", LineString([(-6, 5), (10, 5)])))
    hazard = slides_with_slopes(
        (EVACUATED, "SP0000001", box(0, 0, 6, 10)),
        (EVACUATED, "SP0000003", box(4, 0, 8, 10)),
    )
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row[DAMAGED_LENGTH_COLUMN] == pytest.approx(8.0, abs=0.03)


def test_the_walls_own_polygon_is_not_measured():
    walls = assets(("A-RW01", LineString([(12, 5), (18, 5)])))
    hazard = slides_with_slopes((EVACUATED, "SP0000002", OWN_POLYGON))
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row[DAMAGED_LENGTH_COLUMN] == 0.0


def test_an_absorbed_wall_is_measured_from_the_absorbing_failures_ground():
    walls = assets(("A-RW01", LineString([(-6, 5), (3, 5)])))
    hazard = slides_with_slopes((EVACUATED, "SP0000001", NEIGHBOUR))
    table = outcomes(("A-RW01", "SP0000002", ABSORBED))
    row = damage(walls, hazard, table).loc["A-RW01"]
    assert row["is_evacuated"]
    assert row[DAMAGED_LENGTH_COLUMN] == pytest.approx(3.0, abs=0.02)


def test_a_large_model_landslide_with_no_slope_id_is_measured():
    # The realisation holds slope_id as a string column, so a large-model
    # landslide's is pandas' NA (Wellington pilot, 2026-10-14).
    walls = assets(
        ("A-RW01", LineString([(-6, 5), (4, 5)])),
        ("B-RW01", LineString([(-6, 2), (2, 2)])),
    )
    hazard = slides_with_slopes((EVACUATED, None, NEIGHBOUR))
    hazard["slope_id"] = hazard["slope_id"].astype("string")
    table = outcomes(("A-RW01", "SP0000002", STANDING))
    rows = damage(walls, hazard, table)
    assert rows.loc["A-RW01", DAMAGED_LENGTH_COLUMN] == pytest.approx(4.0, abs=0.02)
    assert rows.loc["B-RW01", DAMAGED_LENGTH_COLUMN] == pytest.approx(2.0, abs=0.02)


def test_a_wall_no_landslide_reached_has_no_damaged_length():
    walls = assets(("A-RW01", LineString([(40, 50), (60, 50)])))
    row = damage(walls, slides(EVACUATED_CIRCLE), outcomes()).loc["A-RW01"]
    assert row[DAMAGED_LENGTH_COLUMN] == 0.0
    assert row[DAMAGED_LINE_COLUMN].is_empty
