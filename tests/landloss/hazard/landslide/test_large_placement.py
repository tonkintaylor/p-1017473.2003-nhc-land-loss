"""Landslide step 1, the large-model placement, on a synthetic unit set and grid.

The ground is a plane rising to the west, so every cell drains east, cut into
three slope units: a west block, a narrow strip three cells wide, and an east
block. The probability grid covers all but the easternmost columns and a crest
row carries a high topographic position. Every number below can be worked out
on paper, and nothing is downloaded: the probability reader and the input
paths are replaced by hand-built grids in ``tmp_path``.
"""

import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box

from landloss.common.utils.terrain import (
    cell_size,
    downhill_azimuth_degrees,
    slope_degrees,
    write_raster,
)
from landloss.domain import constants
from landloss.hazard.landslide.land_class import EVACUATED, INUNDATED
from landloss.hazard.realisation import realisation_seed
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import (
    s1_simulate_landslides as step,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side, and the
# suite turns every warning into a failure.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, bottom left.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0
RESOLUTION = 10.0
ROWS, COLUMNS = 42, 60
CELL_AREA = RESOLUTION**2

# The unit boundaries, as column indices: the strip is columns 20 to 22.
STRIP_START, STRIP_END = 20, 23
# The crest row, and how far it stands above its surroundings.
CREST_ROW = 2
CREST_POSITION_M = 15.0
# The easternmost columns the probability grid does not reach.
UNCOVERED_COLUMNS = 5
PROBABILITY = 0.1

SETTINGS = {
    "min_source_area_m2": 700.0,
    "urban_area_share": 0.25,
    "source_aspect_ratio": 2.0,
    "crest_weight": 0.5,
}


def make_dem(elevation, resolution: float = RESOLUTION):
    """Wrap an elevation array as a north-up DEM in NZTM."""
    elevation = np.asarray(elevation, dtype=float)
    rows, columns = elevation.shape

    # y descending, which is how a GeoTIFF stores a north-up raster; x ascending.
    eastings = ORIGIN_EASTING + resolution * (np.arange(columns) + 0.5)
    northings = ORIGIN_NORTHING + resolution * (np.arange(rows)[::-1] + 0.5)

    dem = xr.DataArray(
        elevation, dims=("y", "x"), coords={"y": northings, "x": eastings}
    )
    return dem.rio.write_crs(constants.DEFAULT_CRS)


def plane_rising_west():
    """Five metres of rise per cell to the west: 26.6 degrees, draining east."""
    _, col = np.indices((ROWS, COLUMNS))
    return 5.0 * (COLUMNS - col)


def grids():
    dem = make_dem(plane_rising_west())
    resolution = cell_size(dem)
    return (
        dem,
        slope_degrees(dem, resolution),
        downhill_azimuth_degrees(dem, resolution),
    )


def probability_grid(value=PROBABILITY):
    """A flat probability with the easternmost columns unmapped."""
    values = np.full((ROWS, COLUMNS), value, dtype=float)
    values[:, COLUMNS - UNCOVERED_COLUMNS :] = np.nan
    return make_dem(values).rio.write_nodata(np.nan)


def topographic_position_grid():
    """Level everywhere but one crest row standing well above its surroundings."""
    values = np.zeros((ROWS, COLUMNS), dtype=float)
    values[CREST_ROW, :] = CREST_POSITION_M
    # The derivative has no value within half a window of the edge.
    values[0, :] = np.nan
    return make_dem(values).rio.write_nodata(np.nan)


def make_units():
    """Three units partitioning the grid: west block, strip, east block."""
    minx, miny = ORIGIN_EASTING, ORIGIN_NORTHING
    maxx = ORIGIN_EASTING + COLUMNS * RESOLUTION
    maxy = ORIGIN_NORTHING + ROWS * RESOLUTION
    strip_west = ORIGIN_EASTING + STRIP_START * RESOLUTION
    strip_east = ORIGIN_EASTING + STRIP_END * RESOLUTION
    geometry = [
        box(minx, miny, strip_west, maxy),
        box(strip_west, miny, strip_east, maxy),
        box(strip_east, miny, maxx, maxy),
    ]
    units = gpd.GeoDataFrame(
        {
            "unit_id": ["SU0000001", "SU0000002", "SU0000003"],
            "mean_slope_degrees": [26.6, 26.6, 26.6],
            "mean_aspect_degrees": [90.0, 90.0, 90.0],
        },
        geometry=geometry,
        crs=constants.DEFAULT_CRS,
    )
    units["area_m2"] = units.geometry.area
    return units


def unit_cell_counts():
    """Covered cells per unit, as the probability grid reaches them."""
    west = STRIP_START * ROWS
    strip = (STRIP_END - STRIP_START) * ROWS
    east = (COLUMNS - STRIP_END - UNCOVERED_COLUMNS) * ROWS
    return np.array([west, strip, east])


def rng():
    return realisation_seed(constants.BASE_SEED, 0, step.RNG_STREAM)


# -- the pieces --------------------------------------------------------------


def test_unit_labels_cover_every_cell_of_a_partition():
    dem = make_dem(plane_rising_west())
    labels = step.unit_labels(make_units(), dem)
    assert labels.shape == dem.shape
    assert (labels > 0).all()
    assert (labels[:, :STRIP_START] == 1).all()
    assert (labels[:, STRIP_START:STRIP_END] == 2).all()
    assert (labels[:, STRIP_END:] == 3).all()


def test_expected_failed_area_sums_probability_times_cell_area_per_unit():
    dem = make_dem(plane_rising_west())
    units = make_units()
    labels = step.unit_labels(units, dem)
    expected = step.expected_failed_area_m2(
        probability_grid().to_numpy(),
        labels,
        len(units),
        cell_area_m2=CELL_AREA,
        source_area_fraction=0.252,
        urban_area_share=0.25,
    )
    # Unmapped cells contribute nothing; everything else is p x area x the two shares.
    per_cell = PROBABILITY * CELL_AREA * 0.252 * 0.75
    assert expected == pytest.approx(unit_cell_counts() * per_cell)


def test_the_truncated_mean_matches_a_large_sample_and_the_bounds_hold():
    low, high = 700.0, 3000.0
    analytic = step.truncated_power_law_mean_m2(low, high, step.SIZE_EXPONENT)
    areas = step.sample_areas(200_000, rng(), min_area_m2=low, max_area_m2=high)
    assert low < analytic < high
    assert areas.min() >= low
    assert areas.max() <= high
    assert areas.mean() == pytest.approx(analytic, rel=0.02)


def test_the_truncated_mean_handles_the_logarithmic_exponent():
    # Density A^-2 on [1, e]: the first moment is ln e = 1 over 1 - 1/e.
    mean = step.truncated_power_law_mean_m2(1.0, np.e, 2.0)
    assert mean == pytest.approx(1.0 / (1.0 - 1.0 / np.e))


def test_the_truncated_mean_refuses_bad_bounds():
    with pytest.raises(ValueError, match="positive and increasing"):
        step.truncated_power_law_mean_m2(3000.0, 700.0, 2.1)


def test_counts_are_poisson_on_expected_area_over_mean_size():
    expected = np.array([0.0, 1306.0 * 4.0, 1306.0 * 0.5])
    generator = rng()
    draws = np.array(
        [step.draw_counts(expected, 1306.0, generator) for _ in range(2000)]
    )
    assert (draws[:, 0] == 0).all()
    assert draws[:, 1].mean() == pytest.approx(4.0, abs=0.2)
    assert draws[:, 2].mean() == pytest.approx(0.5, abs=0.1)
    assert draws.dtype.kind == "i"


def test_seeding_weight_lifts_crests_and_treats_missing_position_as_level():
    probability = np.array([[0.2, 0.2, 0.2, np.nan]])
    position = np.array([[0.0, 5.0, 20.0, 20.0]])
    weight = step.seeding_weight(probability, position, crest_weight=0.5)
    assert weight[0] == pytest.approx([0.2, 0.2 * 1.25, 0.2 * 1.5, 0.0])

    missing = np.array([[np.nan, -8.0]])
    weight = step.seeding_weight(np.array([[0.2, 0.2]]), missing, crest_weight=0.5)
    assert weight[0] == pytest.approx([0.2, 0.2])


def test_seeds_stay_in_their_unit_on_covered_cells_and_prefer_the_crest():
    dem = make_dem(plane_rising_west())
    units = make_units()
    labels = step.unit_labels(units, dem)
    probability = probability_grid().to_numpy()
    weight = step.seeding_weight(
        probability, topographic_position_grid().to_numpy(), crest_weight=0.5
    )
    counts = np.array([3, 0, 2])

    unit_index, rows, columns = step.seed_cells(labels, weight, counts, rng())

    assert unit_index.tolist() == [0, 0, 0, 2, 2]
    assert (labels[rows, columns] == unit_index + 1).all()
    assert np.isfinite(probability[rows, columns]).all()
    # Every covered unit has more than ten crest cells, so the top ten are all
    # on the crest row and every seed lands there.
    assert (rows == CREST_ROW).all()
    # Without replacement within a unit.
    assert len({(r, c) for r, c in zip(rows, columns, strict=True)}) == 5


def test_a_unit_with_no_covered_cell_seeds_nothing_even_with_a_count():
    labels = np.array([[1, 1, 2, 2]])
    weight = np.array([[0.1, 0.1, 0.0, 0.0]])
    unit_index, rows, columns = step.seed_cells(labels, weight, np.array([1, 3]), rng())
    assert unit_index.tolist() == [0]
    assert labels[rows, columns].tolist() == [1]


def test_seeds_reuse_cells_only_when_the_unit_has_fewer_than_the_count():
    labels = np.array([[1, 1]])
    weight = np.array([[0.1, 0.3]])
    unit_index, _rows, columns = step.seed_cells(labels, weight, np.array([5]), rng())
    assert unit_index.size == 5
    assert set(columns.tolist()) <= {0, 1}


def test_no_failures_gives_empty_seed_arrays():
    unit_index, rows, columns = step.seed_cells(
        np.array([[1, 1]]), np.array([[0.1, 0.1]]), np.array([0]), rng()
    )
    assert unit_index.size == rows.size == columns.size == 0


def test_an_ellipse_carries_its_area_and_lies_along_the_azimuth():
    area = 1000.0
    semi_major, semi_minor = step.ellipse_axes(area, 2.0)
    assert semi_major / semi_minor == pytest.approx(2.0)

    south = step.ellipses([0.0], [0.0], semi_major, semi_minor, [180.0])[0]
    assert south.area == pytest.approx(area, rel=1e-6)
    minx, miny, maxx, maxy = south.bounds
    assert maxy - miny == pytest.approx(2 * semi_major)
    assert maxx - minx == pytest.approx(2 * semi_minor)

    east = step.ellipses([0.0], [0.0], semi_major, semi_minor, [90.0])[0]
    minx, miny, maxx, maxy = east.bounds
    assert maxx - minx == pytest.approx(2 * semi_major)
    assert maxy - miny == pytest.approx(2 * semi_minor)
    assert east.is_valid


def test_no_centres_gives_no_ellipses():
    assert step.ellipses([], [], [], [], []).size == 0


def test_the_displacement_ramp_is_clipped_at_both_ends():
    displacement = step.displacement_from_slope(np.array([0.0, 10.0, 27.5, 45.0, 80.0]))
    assert displacement == pytest.approx([1.0, 1.0, 20.5, 40.0, 40.0])


def test_failures_are_seeded_at_the_crest_of_their_ellipse_and_grow_downslope(
    monkeypatch,
):
    _dem, slope, aspect = grids()
    units = make_units()
    # Fix the counts so the strip, three cells wide, gets two failures.
    monkeypatch.setattr(step, "draw_counts", lambda *_: np.array([0, 2, 0]))

    failures, per_unit = step.build_failures(
        probability_grid(),
        slope,
        aspect,
        topographic_position_grid(),
        units,
        rng(),
        **SETTINGS,
    )

    assert len(failures) == 2
    assert per_unit["count"].tolist() == [0, 2, 0]
    assert (failures["unit_id"] == "SU0000002").all()
    assert failures["source_area_m2"].between(700.0, step.MAX_SOURCE_AREA_M2).all()
    assert failures.geometry.area.to_numpy() == pytest.approx(
        failures["source_area_m2"].to_numpy(), rel=1e-6
    )
    # The ground drains east, so the centre is one semi-major axis east of
    # the seed and the seed lies on the ellipse's western tip.
    assert failures["downhill_azimuth_degrees"].to_numpy() == pytest.approx(90.0)
    assert (failures["easting"] - failures["seed_easting"]).to_numpy() == pytest.approx(
        failures["semi_major_m"].to_numpy()
    )
    assert failures["northing"].to_numpy() == pytest.approx(
        failures["seed_northing"].to_numpy()
    )
    seeds = gpd.GeoSeries(
        gpd.points_from_xy(failures["seed_easting"], failures["seed_northing"]),
        index=failures.index,
        crs=failures.crs,
    )
    assert failures.geometry.distance(seeds).max() < 0.5
    # A source wider than its strip crosses into the neighbouring unit.
    east_block = units.geometry.iloc[2]
    assert failures.intersects(east_block).all()
    # The runout is downslope of the source.
    assert (failures["runout_easting"] > failures["easting"]).all()


def test_a_seed_with_no_terrain_takes_its_units_mean_slope_and_aspect(monkeypatch):
    _dem, slope, aspect = grids()
    units = make_units()
    # Blank the terrain over the strip, so its seeds have no cell reading.
    slope = slope.copy()
    aspect = aspect.copy()
    slope[:, STRIP_START:STRIP_END] = np.nan
    aspect[:, STRIP_START:STRIP_END] = np.nan
    units.loc[1, ["mean_slope_degrees", "mean_aspect_degrees"]] = [30.0, 135.0]
    monkeypatch.setattr(step, "draw_counts", lambda *_: np.array([0, 1, 0]))

    failures, _ = step.build_failures(
        probability_grid(),
        slope,
        aspect,
        topographic_position_grid(),
        units,
        rng(),
        **SETTINGS,
    )
    assert failures["slope_degrees"].tolist() == [30.0]
    assert failures["downhill_azimuth_degrees"].tolist() == [135.0]


def test_drop_overlapping_keeps_the_larger_and_a_dropped_one_drops_nothing():
    semi_major, semi_minor = step.ellipse_axes(np.array([2000.0, 900.0, 800.0]), 2.0)
    # The first two overlap; the third touches only the second.
    geometry = step.ellipses(
        [0.0, 20.0, 60.0], [0.0, 0.0, 0.0], semi_major, semi_minor, [90.0, 90.0, 90.0]
    )
    failures = gpd.GeoDataFrame(
        {"source_area_m2": [2000.0, 900.0, 800.0]},
        geometry=geometry,
        crs=constants.DEFAULT_CRS,
    )
    assert failures.geometry.iloc[0].intersects(failures.geometry.iloc[1])
    assert not failures.geometry.iloc[0].intersects(failures.geometry.iloc[2])
    assert failures.geometry.iloc[1].intersects(failures.geometry.iloc[2])

    survivors = step.drop_overlapping(failures)
    assert survivors.index.tolist() == [0, 2]


def test_ids_follow_location_within_the_realisation():
    semi_major, semi_minor = step.ellipse_axes(np.array([800.0, 800.0, 800.0]), 2.0)
    geometry = step.ellipses(
        [300.0, 100.0, 100.0], [0.0, 50.0, 0.0], semi_major, semi_minor, [0.0] * 3
    )
    failures = gpd.GeoDataFrame(
        {"source_area_m2": [800.0] * 3}, geometry=geometry, crs=constants.DEFAULT_CRS
    )
    minted = step.mint_landslide_ids(failures)
    assert minted["landslide_id"].tolist() == ["LS0000001", "LS0000002", "LS0000003"]
    # West first, then south: the centre at (100, 0) before (100, 50) before (300, 0).
    assert minted.geometry.centroid.x.round(6).tolist() == [100.0, 100.0, 300.0]
    assert minted.geometry.centroid.y.round(6).tolist() == [0.0, 50.0, 0.0]
    assert minted.columns[0] == "landslide_id"


def test_to_polygons_writes_two_rows_per_landslide_with_the_runout_translated():
    semi_major, semi_minor = step.ellipse_axes(np.array([1000.0]), 2.0)
    failures = gpd.GeoDataFrame(
        {
            "landslide_id": ["LS0000001"],
            "unit_id": ["SU0000001"],
            "easting": [100.0],
            "northing": [200.0],
            "runout_easting": [130.0],
            "runout_northing": [200.0],
            "semi_major_m": semi_major,
            "semi_minor_m": semi_minor,
            "downhill_azimuth_degrees": [90.0],
            "source_area_m2": [1000.0],
        },
        geometry=step.ellipses([100.0], [200.0], semi_major, semi_minor, [90.0]),
        crs=constants.DEFAULT_CRS,
    )
    polygons = step.to_polygons(failures)

    assert polygons["land_class"].tolist() == [EVACUATED, INUNDATED]
    assert (polygons["population"] == "large").all()
    assert polygons["slope_id"].isna().all()
    assert polygons["depth_m"].iloc[0] == pytest.approx(polygons["depth_m"].iloc[1])
    assert polygons["volume_m3"].iloc[0] == pytest.approx(polygons["volume_m3"].iloc[1])
    assert polygons.geometry.area.to_numpy() == pytest.approx(1000.0, rel=1e-6)
    shift = polygons.geometry.centroid.x.iloc[1] - polygons.geometry.centroid.x.iloc[0]
    assert shift == pytest.approx(30.0)


def test_a_coarser_probability_grid_is_resampled_nearest_onto_the_working_grid():
    dem = make_dem(plane_rising_west())
    coarse = np.arange(14 * 20, dtype=float).reshape(14, 20) / 1000.0
    coarse_grid = make_dem(coarse, resolution=30.0).rio.write_nodata(np.nan)

    aligned = step.align_probability(coarse_grid, dem)

    assert aligned.shape == dem.shape
    assert aligned["x"].to_numpy() == pytest.approx(dem["x"].to_numpy())
    assert aligned["y"].to_numpy() == pytest.approx(dem["y"].to_numpy())
    # Every 10 m cell takes the value of the 30 m cell it falls in.
    blocks = aligned.to_numpy().reshape(14, 3, 20, 3)
    assert blocks == pytest.approx(
        np.broadcast_to(coarse[:, None, :, None], blocks.shape)
    )


def ground_map(flat_columns):
    """A ground map of one piece per column, flat on the columns given."""
    west, south = ORIGIN_EASTING, ORIGIN_NORTHING
    pieces = [
        box(
            west + RESOLUTION * c,
            south,
            west + RESOLUTION * (c + 1),
            south + ROWS * RESOLUTION,
        )
        for c in range(COLUMNS)
    ]
    return gpd.GeoDataFrame(
        {"is_flatland": [c in set(flat_columns) for c in range(COLUMNS)]},
        geometry=pieces,
        crs=constants.DEFAULT_CRS,
    )


def test_the_flatland_mask_marks_cells_whose_centre_is_on_flat_land():
    """Only the columns the ground map calls flat are masked."""
    mask = step.flatland_mask(
        ground_map(flat_columns=range(40, 50)), probability_grid()
    )
    assert mask.shape == (ROWS, COLUMNS)
    assert mask[:, 40:50].all()
    assert not mask[:, :40].any()
    assert not mask[:, 50:].any()


def test_masking_flat_land_removes_its_probability_and_keeps_the_rest():
    """Flat cells carry no chance of a large landslide; sloping ones keep theirs."""
    probability = probability_grid()
    mask = step.flatland_mask(ground_map(flat_columns=range(40, 50)), probability)
    masked = step.mask_flatland(probability, mask).to_numpy()
    assert np.isnan(masked[:, 40:50]).all()
    assert np.allclose(masked[:, :40], PROBABILITY)
    assert step.flatland_mask(ground_map(flat_columns=()), probability).sum() == 0


def test_a_wholly_flat_extent_draws_no_large_landslide(step_inputs, monkeypatch):
    """With every cell on flat land the step writes an empty realisation."""
    ground_map(flat_columns=range(COLUMNS)).to_parquet(step_inputs["ground_map"])
    run_step(monkeypatch, probability_grid())
    written = gpd.read_parquet(step.realisation_path(pilot=True, realisation_id=0))
    assert written.empty


# -- the step end to end -----------------------------------------------------


@pytest.fixture
def step_inputs(tmp_path, monkeypatch):
    """Steps 3 and 5's layers, synthetic, where the step looks; no network."""
    dem, slope, aspect = grids()
    paths = {
        "units": tmp_path / "slope-units-pilot.geoparquet",
        "dem": write_raster(dem.rename("dem"), tmp_path / "dem-10m-pilot.tif"),
        "slope": write_raster(slope, tmp_path / "slope-10m-pilot.tif"),
        "aspect": write_raster(aspect, tmp_path / "aspect-10m-pilot.tif"),
        "topographic_position": write_raster(
            topographic_position_grid().rename("topographic_position_m"),
            tmp_path / "terrain" / "topographic-position-100m-pilot.tif",
        ),
    }
    make_units().to_parquet(paths["units"])
    paths["ground_map"] = tmp_path / "ground-map-pilot.geoparquet"
    ground_map(flat_columns=()).to_parquet(paths["ground_map"])
    monkeypatch.setattr(step, "input_paths", lambda *, pilot: paths)
    monkeypatch.setattr(step, "WORK_DIR", tmp_path)
    return paths


def run_step(monkeypatch, probability, realisation_ids=(0,)):
    monkeypatch.setattr(step, "read_probability", lambda bbox: probability)
    step.main(
        pilot=True,
        realisation_ids=list(realisation_ids),
        large_min_source_area_m2=SETTINGS["min_source_area_m2"],
        urban_area_share=SETTINGS["urban_area_share"],
        source_aspect_ratio=SETTINGS["source_aspect_ratio"],
        crest_weight=SETTINGS["crest_weight"],
    )


def test_the_path_names_the_realisation_and_the_extent():
    assert (
        step.realisation_path(pilot=True, realisation_id=3).name
        == "landslide-realisation-r003-pilot.geoparquet"
    )
    assert (
        step.realisation_path(pilot=False, realisation_id=0).name
        == "landslide-realisation-r000.geoparquet"
    )


def test_the_step_writes_the_contract_columns(step_inputs, monkeypatch, capsys):
    run_step(monkeypatch, probability_grid(0.9))
    written = gpd.read_parquet(step.realisation_path(pilot=True, realisation_id=0))

    assert list(written.columns) == step.OUTPUT_COLUMNS
    assert written.crs == constants.DEFAULT_CRS
    assert len(written) > 0
    assert (written["realisation_id"] == 0).all()
    assert (written["population"] == "large").all()
    assert written["slope_id"].isna().all()
    assert set(written["unit_id"]) <= set(make_units()["unit_id"])
    assert (
        written["landslide_id"].map(lambda v: bool(re.fullmatch(r"LS\d{7}", v))).all()
    )
    assert set(written["land_class"]) == {EVACUATED, INUNDATED}
    # Two rows per landslide, and the ids start at one in the sort order.
    per_id = written.groupby("landslide_id")["land_class"].count()
    assert (per_id == 2).all()
    assert written["landslide_id"].iloc[0] == "LS0000001"
    # Sizes above the urban range, and no two sources overlap.
    sources = written[written["land_class"] == EVACUATED]
    assert sources["source_area_m2"].between(700.0, step.MAX_SOURCE_AREA_M2).all()
    assert sources.geometry.area.to_numpy() == pytest.approx(
        sources["source_area_m2"].to_numpy(), rel=1e-6
    )
    overlaps = sources.sjoin(sources, predicate="intersects")
    assert (overlaps.index == overlaps["index_right"]).all()
    # Seeds sit on covered cells, on the crest row, inside the grid.
    assert (sources["failure_probability"] == 0.9).all()
    crest_northing = ORIGIN_NORTHING + RESOLUTION * (ROWS - CREST_ROW - 0.5)
    assert sources["seed_northing"].to_numpy() == pytest.approx(crest_northing)
    assert written["depth_m"].gt(0).all()
    assert written["volume_m3"].gt(0).all()
    assert pd.api.types.is_integer_dtype(written["realisation_id"])

    out = capsys.readouterr().out
    assert "urban area share taken off: 0.25" in out
    assert "source area fraction of a failing cell" in out
    assert "Realisation 0" in out
    assert "Wrote" in out


def test_the_same_seed_reproduces_and_another_realisation_differs(
    step_inputs, monkeypatch
):
    run_step(monkeypatch, probability_grid(0.9), realisation_ids=(0, 1))
    first = gpd.read_parquet(step.realisation_path(pilot=True, realisation_id=0))
    second = gpd.read_parquet(step.realisation_path(pilot=True, realisation_id=1))
    run_step(monkeypatch, probability_grid(0.9), realisation_ids=(0,))
    again = gpd.read_parquet(step.realisation_path(pilot=True, realisation_id=0))

    pd.testing.assert_frame_equal(first, again)
    assert (second["realisation_id"] == 1).all()
    assert not first["source_area_m2"].equals(second["source_area_m2"])


def test_an_empty_realisation_is_written_with_the_full_schema(
    step_inputs, monkeypatch, capsys
):
    run_step(monkeypatch, probability_grid(0.0))
    written = gpd.read_parquet(step.realisation_path(pilot=True, realisation_id=0))

    assert written.empty
    assert list(written.columns) == step.OUTPUT_COLUMNS
    assert "writing an empty layer" in capsys.readouterr().out


def test_a_grid_outside_zero_to_one_is_refused(step_inputs, monkeypatch):
    with pytest.raises(ValueError, match="not a probability"):
        run_step(monkeypatch, probability_grid(12.0))
