import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from landloss.hazard.landslide import land_class as hazard_land_class
from landloss.vul.landslide.land import damaged_area
from landloss.vul.landslide.land.damaged_area import (
    EVACUATED,
    IGNORED_LAND_CLASSES,
    IMMINENT,
    INUNDATED,
    UNION_AREA_COLUMN,
    check_within_insured_area,
    damaged_area_per_failure,
    damaged_area_per_property,
    failures_per_property,
)

CRS = "EPSG:2193"


def insured(*bounds_and_ids):
    ids, geoms = [], []
    for address, bounds in bounds_and_ids:
        ids.append(address)
        geoms.append(box(*bounds))
    frame = gpd.GeoDataFrame({"claim_id": ids}, geometry=geoms, crs=CRS)
    frame["area_m2"] = frame.geometry.area
    return frame


def slides(*specs):
    classes, depths, geoms = [], [], []
    for land_class, depth, shape in specs:
        classes.append(land_class)
        depths.append(depth)
        geoms.append(box(*shape) if isinstance(shape, tuple) else shape)
    return gpd.GeoDataFrame(
        {"land_class": classes, "depth_m": depths}, geometry=geoms, crs=CRS
    )


def test_the_overlap_with_a_property_is_the_damaged_area():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (10, 0, 30, 20)))
    damaged = damaged_area_per_property(land, hazard)
    assert damaged["evacuated_area_m2"].iloc[0] == pytest.approx(200.0)


def test_the_two_kinds_of_ground_are_kept_apart():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 10, 20)), (INUNDATED, 0.5, (10, 0, 20, 20)))
    damaged = damaged_area_per_property(land, hazard)
    assert damaged["evacuated_area_m2"].iloc[0] == pytest.approx(200.0)
    assert damaged["inundated_area_m2"].iloc[0] == pytest.approx(200.0)


def test_two_landslides_burying_the_same_ground_are_counted_once():
    # Inundated polygons may overlap; ground buried twice is buried once.
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides(
        (INUNDATED, 1.0, (0, 0, 20, 20)),
        (INUNDATED, 2.0, (0, 0, 20, 20)),
    )
    damaged = damaged_area_per_property(land, hazard)
    assert damaged["inundated_area_m2"].iloc[0] == pytest.approx(400.0)


def test_depth_is_weighted_by_how_much_each_landslide_contributed():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides(
        (EVACUATED, 1.0, (0, 0, 15, 20)),  # 300 m2 of the property
        (EVACUATED, 3.0, (15, 0, 20, 20)),  # 100 m2 of it
    )
    damaged = damaged_area_per_property(land, hazard)
    assert damaged["evacuated_depth_m"].iloc[0] == pytest.approx(1.5)


def test_a_property_no_landslide_reached_is_absent():
    land = insured(("A-001", (0, 0, 20, 20)), ("A-002", (100, 100, 120, 120)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 20, 20)))
    damaged = damaged_area_per_property(land, hazard)
    assert damaged["claim_id"].tolist() == ["A-001"]


def test_an_untouched_kind_of_ground_is_zero_not_unknown():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 20, 20)))
    damaged = damaged_area_per_property(land, hazard)
    assert damaged["inundated_area_m2"].iloc[0] == 0.0


def test_no_landslides_damages_nothing():
    land = insured(("A-001", (0, 0, 20, 20)))
    empty = gpd.GeoDataFrame(
        {"land_class": [], "depth_m": []}, geometry=gpd.GeoSeries([], crs=CRS), crs=CRS
    )
    assert damaged_area_per_property(land, empty).empty


def test_damage_never_exceeds_the_property_it_sits_on():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (-50, -50, 50, 50)))
    damaged = damaged_area_per_property(land, hazard)
    assert check_within_insured_area(damaged, land).empty


def test_a_crs_mismatch_is_refused():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 20, 20))).to_crs("EPSG:4326")
    with pytest.raises(ValueError, match="insured land is"):
        damaged_area_per_property(land, hazard)


def test_landslides_without_a_land_class_are_refused():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 20, 20))).drop(columns=["land_class"])
    with pytest.raises(ValueError, match="land_class"):
        damaged_area_per_property(land, hazard)


def test_ground_both_evacuated_and_inundated_counts_once_in_the_union():
    land = insured(("A-001", (0, 0, 100, 100)))
    evacuated = Point(40, 50).buffer(20)
    inundated = Point(60, 50).buffer(20)
    hazard = slides((EVACUATED, 1.0, evacuated), (INUNDATED, 0.5, inundated))
    row = damaged_area_per_property(land, hazard).iloc[0]
    assert row[UNION_AREA_COLUMN] == pytest.approx(evacuated.union(inundated).area)
    assert row[UNION_AREA_COLUMN] < (
        row["evacuated_area_m2"] + row["inundated_area_m2"]
    )


def test_disjoint_kinds_of_ground_sum_in_the_union():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 10, 20)), (INUNDATED, 0.5, (10, 0, 20, 5)))
    row = damaged_area_per_property(land, hazard).iloc[0]
    assert row[UNION_AREA_COLUMN] == pytest.approx(
        row["evacuated_area_m2"] + row["inundated_area_m2"]
    )


def test_the_union_is_at_least_the_larger_kind():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 15, 20)), (INUNDATED, 0.5, (5, 0, 10, 20)))
    row = damaged_area_per_property(land, hazard).iloc[0]
    largest = max(row["evacuated_area_m2"], row["inundated_area_m2"])
    assert row[UNION_AREA_COLUMN] >= largest - 1e-9
    assert row[UNION_AREA_COLUMN] == pytest.approx(300.0)


def test_the_union_never_exceeds_the_property_it_sits_on():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides(
        (EVACUATED, 1.0, (-50, -50, 10, 50)), (INUNDATED, 0.5, (5, -50, 50, 50))
    )
    row = damaged_area_per_property(land, hazard).iloc[0]
    assert row[UNION_AREA_COLUMN] == pytest.approx(400.0)
    assert row[UNION_AREA_COLUMN] <= land["area_m2"].iloc[0] * (1 + 1e-9)


def test_no_landslides_still_carries_the_union_column():
    land = insured(("A-001", (0, 0, 20, 20)))
    empty = gpd.GeoDataFrame(
        {"land_class": [], "depth_m": []}, geometry=gpd.GeoSeries([], crs=CRS), crs=CRS
    )
    damaged = damaged_area_per_property(land, empty)
    assert damaged.empty
    assert UNION_AREA_COLUMN in damaged.columns


def test_the_output_is_keyed_on_the_named_identifier():
    land = insured(("A-001", (0, 0, 20, 20))).rename(columns={"claim_id": "land_id"})
    hazard = slides((EVACUATED, 1.0, (0, 0, 10, 20)), (INUNDATED, 0.5, (5, 0, 20, 20)))
    damaged = damaged_area_per_property(land, hazard, id_column="land_id")
    assert damaged.columns[0] == "land_id"
    assert damaged["land_id"].tolist() == ["A-001"]
    assert damaged[UNION_AREA_COLUMN].iloc[0] == pytest.approx(400.0)


def test_an_oversize_union_is_flagged():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 10, 20)))
    damaged = damaged_area_per_property(land, hazard)
    damaged[UNION_AREA_COLUMN] = 500.0
    assert check_within_insured_area(damaged, land)["claim_id"].tolist() == ["A-001"]


def test_a_union_smaller_than_either_kind_is_flagged():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = slides((EVACUATED, 1.0, (0, 0, 10, 20)))
    damaged = damaged_area_per_property(land, hazard)
    damaged[UNION_AREA_COLUMN] = 100.0
    assert check_within_insured_area(damaged, land)["claim_id"].tolist() == ["A-001"]


def test_the_land_classes_are_the_hazard_modules():
    assert damaged_area.EVACUATED is hazard_land_class.EVACUATED
    assert damaged_area.INUNDATED is hazard_land_class.INUNDATED
    assert damaged_area.IMMINENT is hazard_land_class.IMMINENT
    assert damaged_area.LAND_CLASS_COLUMN is hazard_land_class.LAND_CLASS_COLUMN


def test_imminent_ground_measures_nothing():
    assert IGNORED_LAND_CLASSES == (IMMINENT,)
    land = insured(("A-001", (0, 0, 20, 20)))
    only_imminent = slides((IMMINENT, float("nan"), (0, 0, 20, 20)))
    assert damaged_area_per_property(land, only_imminent).empty

    with_imminent = slides(
        (EVACUATED, 1.0, (0, 0, 10, 20)), (IMMINENT, float("nan"), (0, 0, 20, 20))
    )
    row = damaged_area_per_property(land, with_imminent).iloc[0]
    assert row["evacuated_area_m2"] == pytest.approx(200.0)
    assert row["inundated_area_m2"] == 0.0
    assert row[UNION_AREA_COLUMN] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Each failure apart (T-124).
# ---------------------------------------------------------------------------


def failures(*specs):
    """(landslide id, rw id, land class, depth, box) per polygon."""
    return gpd.GeoDataFrame(
        {
            "landslide_id": [spec[0] for spec in specs],
            "rw_id": [spec[1] for spec in specs],
            "land_class": [spec[2] for spec in specs],
            "depth_m": [spec[3] for spec in specs],
        },
        geometry=[box(*spec[4]) for spec in specs],
        crs=CRS,
    )


def test_two_separate_landslides_on_a_property_stay_apart():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = failures(
        ("LS1", None, EVACUATED, 1.0, (0, 0, 5, 20)),
        ("LS2", None, EVACUATED, 1.0, (15, 0, 20, 20)),
    )
    out = damaged_area_per_failure(land, hazard)
    assert out["landslide_id"].tolist() == ["LS1", "LS2"]
    assert out["area_m2"].tolist() == pytest.approx([100.0, 100.0])


def test_a_failures_own_deposit_over_its_scar_counts_once():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = failures(
        ("S1", "RW1", EVACUATED, 1.0, (0, 0, 10, 20)),
        ("S1", "RW1", INUNDATED, 0.4, (5, 0, 15, 20)),
    )
    row = damaged_area_per_failure(land, hazard).iloc[0]
    assert row["area_m2"] == pytest.approx(300.0)
    assert row["evacuated_area_m2"] == pytest.approx(200.0)
    assert row["inundated_area_m2"] == pytest.approx(200.0)
    assert row["inundated_depth_m"] == pytest.approx(0.4)
    assert row["rw_id"] == "RW1"


def test_two_failures_burying_the_same_ground_each_count_it():
    # Each wall holds its own slip; the property union still counts it once.
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = failures(
        ("LS1", None, INUNDATED, 0.5, (0, 0, 10, 20)),
        ("LS2", None, INUNDATED, 0.5, (0, 0, 10, 20)),
    )
    out = damaged_area_per_failure(land, hazard)
    assert out["area_m2"].tolist() == pytest.approx([200.0, 200.0])
    union = damaged_area_per_property(land, hazard)[UNION_AREA_COLUMN].iloc[0]
    assert union == pytest.approx(200.0)


def test_imminent_ground_is_no_failure_of_its_own():
    land = insured(("A-001", (0, 0, 20, 20)))
    hazard = failures(("S1", None, IMMINENT, 1.0, (0, 0, 10, 20)))
    assert damaged_area_per_failure(land, hazard).empty


def test_the_failures_are_listed_per_property_in_one_order():
    land = insured(("A-001", (0, 0, 20, 20)), ("A-002", (30, 0, 50, 20)))
    hazard = failures(
        ("LS2", None, EVACUATED, 1.0, (15, 0, 20, 20)),
        ("S1", "RW1", EVACUATED, 1.0, (0, 0, 5, 20)),
        ("LS2", None, INUNDATED, 0.5, (30, 0, 35, 20)),
    )
    lists = failures_per_property(damaged_area_per_failure(land, hazard))
    first = lists.loc["A-001"]
    assert first["landslide_ids"] == ["LS2", "S1"]
    assert first["landslide_rw_ids"] == [None, "RW1"]
    assert first["landslide_areas"] == pytest.approx([100.0, 100.0])
    assert first["landslide_evacuated_areas"] == pytest.approx([100.0, 100.0])
    assert lists.loc["A-002", "landslide_evacuated_areas"] == [0.0]
    assert first["landslide_inundated_depths"] == [None, None]
    assert lists.loc["A-002", "landslide_inundated_depths"] == [0.5]


def test_landslides_without_ids_are_refused():
    land = insured(("A-001", (0, 0, 20, 20)))
    with pytest.raises(ValueError, match="landslide_id"):
        damaged_area_per_failure(land, slides((EVACUATED, 1.0, (0, 0, 10, 20))))
