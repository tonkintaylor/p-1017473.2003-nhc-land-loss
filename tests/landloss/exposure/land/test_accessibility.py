"""Tests for the accessibility attributes the land value model reads.

Every fixture is built in memory or written to ``tmp_path``, apart from the two
tests that read the packaged centres asset, which check it loads and not what
is in it.
"""

import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from landloss.exposure.land.accessibility import (
    CENTRE_COLUMNS,
    DUPLICATE_STATION_M,
    add_stations,
    distance_to_nearest,
    gravity_accessibility,
    load_centres,
    load_extra_stations,
)

CRS = "EPSG:2193"


def make_centres(rows: list[tuple[str, float, float, float, float]]):
    """Build centres from (name, x, y, weight, decay length) rows."""
    return gpd.GeoDataFrame(
        {
            "name": [row[0] for row in rows],
            "weight": [row[3] for row in rows],
            "decay_length_m": [row[4] for row in rows],
        },
        geometry=[Point(row[1], row[2]) for row in rows],
        crs=CRS,
    )


def points(*coordinates):
    """Build a GeoSeries of points in the study CRS."""
    return gpd.GeoSeries([Point(x, y) for x, y in coordinates], crs=CRS)


# --- the centres asset --------------------------------------------------------


def test_the_packaged_centres_load_in_the_study_crs() -> None:
    """The asset is WGS84 on disk and comes back projected, one point a centre."""
    centres = load_centres()

    assert centres.crs.to_epsg() == 2193
    assert set(CENTRE_COLUMNS) <= set(centres.columns)
    assert centres["name"].is_unique


def test_the_wellington_cbd_is_the_heaviest_packaged_centre() -> None:
    """The plan sets the Wellington CBD at 1.00 and every other centre below it."""
    centres = load_centres().set_index("name")

    assert centres["weight"].idxmax() == "Wellington CBD"
    assert centres.loc["Wellington CBD", "weight"] == pytest.approx(1.0)


def write_centres(tmp_path, **overrides):
    """Write a one-centre asset, with any column overridden, and return its path."""
    row = {
        "name": "Somewhere",
        "kind": "local",
        "weight": 0.1,
        "decay_length_m": 3000,
        "lon": 174.78,
        "lat": -41.28,
        "basis": "test",
        **overrides,
    }
    path = tmp_path / "centres.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


def test_a_zero_decay_length_is_rejected(tmp_path) -> None:
    """A zero decay length would divide by zero inside the gravity sum."""
    with pytest.raises(ValueError, match="decay_length_m"):
        load_centres(write_centres(tmp_path, decay_length_m=0))


def test_a_negative_weight_is_rejected(tmp_path) -> None:
    """A negative weight is a typo, and would subtract value near a centre."""
    with pytest.raises(ValueError, match="weight"):
        load_centres(write_centres(tmp_path, weight=-0.1))


def test_a_missing_column_is_named(tmp_path) -> None:
    """A renamed column names itself rather than raising a bare KeyError."""
    path = write_centres(tmp_path)
    pd.read_csv(path).drop(columns="decay_length_m").to_csv(path, index=False)

    with pytest.raises(ValueError, match="decay_length_m"):
        load_centres(path)


# --- gravity accessibility ----------------------------------------------------


def test_at_a_centre_the_accessibility_is_its_weight() -> None:
    """Distance zero leaves exp(0) = 1, so a lone centre contributes its weight."""
    centres = make_centres([("A", 0, 0, 0.3, 3000)])

    result = gravity_accessibility(points((0, 0)), centres)

    assert result.iloc[0] == pytest.approx(0.3)


def test_one_decay_length_out_the_accessibility_falls_to_1_over_e() -> None:
    """The decay length is the distance over which a centre's pull falls by e."""
    centres = make_centres([("A", 0, 0, 1.0, 6000)])

    result = gravity_accessibility(points((6000, 0)), centres)

    assert result.iloc[0] == pytest.approx(math.exp(-1))


def test_the_centres_are_summed_rather_than_the_nearest_taken() -> None:
    """A point between two centres gains from both at once."""
    centres = make_centres([("A", 0, 0, 1.0, 1000), ("B", 2000, 0, 0.5, 1000)])

    result = gravity_accessibility(points((1000, 0)), centres)

    assert result.iloc[0] == pytest.approx(1.5 * math.exp(-1))


def test_accessibility_falls_with_distance() -> None:
    """Further from the only centre is always less accessible."""
    centres = make_centres([("A", 0, 0, 1.0, 3000)])

    result = gravity_accessibility(points((100, 0), (1000, 0), (10_000, 0)), centres)

    assert result.is_monotonic_decreasing


def test_a_point_with_no_geometry_is_nan_rather_than_remote() -> None:
    """Zero would read as remote and be priced down; NaN sits it in its cohort."""
    centres = make_centres([("A", 0, 0, 1.0, 3000)])
    series = gpd.GeoSeries([Point(0, 0), None], crs=CRS)

    result = gravity_accessibility(series, centres)

    assert result.iloc[0] == pytest.approx(1.0)
    assert math.isnan(result.iloc[1])


def test_the_index_is_kept() -> None:
    """The result lines up with the addresses it was measured for."""
    centres = make_centres([("A", 0, 0, 1.0, 3000)])
    series = points((0, 0), (10, 0))
    series.index = [7, 3]

    assert list(gravity_accessibility(series, centres).index) == [7, 3]


def test_a_crs_mismatch_is_rejected() -> None:
    """Distances in degrees against decay lengths in metres would be nonsense."""
    centres = make_centres([("A", 0, 0, 1.0, 3000)]).to_crs("EPSG:4326")

    with pytest.raises(ValueError, match="EPSG"):
        gravity_accessibility(points((0, 0)), centres)


# --- distance to the nearest station ------------------------------------------


def test_the_distance_is_to_the_nearest_target() -> None:
    """Two stations, and each address is measured to the closer one."""
    stations = points((0, 0), (1000, 0))

    result = distance_to_nearest(points((100, 0), (900, 0), (500, 300)), stations)

    assert list(result.round(6)) == [100.0, 100.0, pytest.approx(math.hypot(500, 300))]


def test_no_targets_gives_nan_everywhere() -> None:
    """An extent with no stations gives no premium, rather than failing."""
    result = distance_to_nearest(points((0, 0), (1, 1)), gpd.GeoSeries([], crs=CRS))

    assert result.isna().all()


def test_a_point_with_no_geometry_has_no_distance() -> None:
    """The missing address stays NaN; the others are still measured."""
    series = gpd.GeoSeries([Point(0, 0), None, Point(30, 40)], crs=CRS)

    result = distance_to_nearest(series, points((0, 0)))

    assert result.iloc[0] == pytest.approx(0.0)
    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(50.0)


# --- stations added by hand ---------------------------------------------------


def named_points(rows):
    """Build named stations from (name, x, y) rows in the study CRS."""
    return gpd.GeoDataFrame(
        {"name": [row[0] for row in rows]},
        geometry=[Point(row[1], row[2]) for row in rows],
        crs=CRS,
    )


WIDE = (-1e6, -1e6, 1e6, 1e6)


def test_the_packaged_extra_stations_carry_wellington_station() -> None:
    """The terminus is the reason the asset exists."""
    extra = load_extra_stations()

    assert "Wellington Station" in set(extra["name"])
    assert extra.crs.to_epsg() == 2193


def test_an_added_station_is_appended_and_named() -> None:
    """The combined set carries both, and the run is told which was added."""
    fetched = named_points([("Crofton Downs Station", 0, 0)])
    extra = named_points([("Wellington Station", 3000, 0)])

    combined, added = add_stations(fetched, extra, WIDE)

    assert sorted(combined["name"]) == ["Crofton Downs Station", "Wellington Station"]
    assert added == ["Wellington Station"]


def test_an_added_station_already_in_the_layer_is_dropped() -> None:
    """Once LINZ carries it, the hand-placed copy must not stand beside it."""
    fetched = named_points([("Wellington Station", 0, 0)])
    extra = named_points([("Wellington Station", DUPLICATE_STATION_M / 2, 0)])

    combined, added = add_stations(fetched, extra, WIDE)

    assert len(combined) == 1
    assert added == []


def test_an_added_station_outside_the_fetched_extent_is_left_out() -> None:
    """A pilot run should not gain a station the LINZ read would not have had."""
    fetched = named_points([("Crofton Downs Station", 0, 0)])
    extra = named_points([("Wellington Station", 50_000, 0)])

    combined, added = add_stations(fetched, extra, (-100, -100, 100, 100))

    assert list(combined["name"]) == ["Crofton Downs Station"]
    assert added == []


def test_an_added_station_counts_when_the_layer_had_none_in_reach() -> None:
    """The pilot case: LINZ returns nothing, and the terminus is still added."""
    fetched = named_points([])
    extra = named_points([("Wellington Station", 0, 0)])

    combined, added = add_stations(fetched, extra, WIDE)

    assert list(combined["name"]) == ["Wellington Station"]
    assert added == ["Wellington Station"]
