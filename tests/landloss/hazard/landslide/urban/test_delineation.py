"""Tests for the urban candidate delineation, on hand-built terrain.

The ground here is a terrace and a face: two flats at different heights joined
by a short steep ramp, built out of numpy so that what each cell's band and
patch should be can be worked out on paper. Nothing is downloaded. The step
script is exercised at the end on the same ground, with every upstream file
written to ``tmp_path`` and every reader of a LINZ or NLM layer replaced by a
synthetic frame.
"""

import importlib.util

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from rasterio.transform import Affine
from shapely.geometry import LineString, Polygon, box

from landloss.common.utils import terrain
from landloss.common.utils.terrain import (
    block_mean,
    downhill_azimuth_degrees,
    slope_degrees,
    write_raster,
)
from landloss.domain import constants
from landloss.hazard.landslide.urban import delineation
from landloss.hazard.landslide.urban.delineation import (
    ASPECT_OCTANTS,
    CANDIDATE_COLUMNS,
    NO_CLASS,
    OUTSIDE,
    SLOPE_BAND_LABELS,
    aspect_octant,
    contour_length_m,
    delineate_candidates,
    label_patches,
    merge_small_patches,
    patches_to_polygons,
    slope_band,
    split_long_patches,
    urban_domain,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0

# The terrace-and-face ground: a square grid of 1 m cells, the upper terrace
# on the west, a face dropping FACE_DROP_M per cell over FACE_CELLS cells, the
# lower terrace on the east. The drop per cell is steep enough (76 degrees) that
# Horn's kernel, which halves the gradient on the cells either side of the
# ramp, still puts every cell it touches in the "60+" band: one face patch.
GRID_CELLS = 45
FACE_START = 21
FACE_CELLS = 3
FACE_DROP_M = 4.0
STEEP_BAND = SLOPE_BAND_LABELS[-1]
GENTLE_BAND = SLOPE_BAND_LABELS[0]
MIN_PATCH_CELLS = 9
MAX_LENGTH_M = 1000.0


def make_dem(elevation, resolution: float = 10.0):
    """Wrap an elevation array as a north-up DEM in NZTM."""
    elevation = np.asarray(elevation, dtype=float)
    rows, columns = elevation.shape
    eastings = ORIGIN_EASTING + resolution * (np.arange(columns) + 0.5)
    northings = ORIGIN_NORTHING + resolution * (np.arange(rows)[::-1] + 0.5)
    dem = xr.DataArray(
        elevation, dims=("y", "x"), coords={"y": northings, "x": eastings}
    )
    return dem.rio.write_crs(constants.DEFAULT_CRS)


def terrace_and_face(cells: int = GRID_CELLS):
    """Elevation of the terrace-and-face ground, one row per metre."""
    column = np.arange(cells, dtype=float)
    upper = FACE_DROP_M * FACE_CELLS
    profile = np.clip(upper - FACE_DROP_M * (column - FACE_START + 1), 0.0, upper)
    return np.tile(profile, (cells, 1))


# The bank-with-face ground, for the nesting across scales: the upper terrace,
# a 25 m bank at 20 degrees with a 2 m face part way down it, the lower
# terrace. At 1 m the face is a patch of its own inside the bank; at 3 m the
# face is smeared into the cells around it and reads as one steeper, wider
# piece of bank.
BANK_START = 10
BANK_CELLS = 25
BANK_GRADIENT = np.tan(np.radians(20.0))
BANK_FACE_COLUMN = 23
BANK_FACE_DROP_M = 2.0


def bank_with_face(cells: int = GRID_CELLS):
    """Elevation of the bank-with-face ground, one row per metre."""
    column = np.arange(cells, dtype=float)
    top = BANK_GRADIENT * BANK_CELLS + BANK_FACE_DROP_M
    profile = top - BANK_GRADIENT * np.clip(column - BANK_START, 0, BANK_CELLS)
    profile -= BANK_FACE_DROP_M * (column >= BANK_FACE_COLUMN)
    return np.tile(profile, (cells, 1))


def grid_box(dem):
    """The rectangle a DEM covers, as a shapely polygon."""
    minx, miny, maxx, maxy = dem.rio.bounds()
    return box(minx, miny, maxx, maxy)


def slope_and_aspect(dem, resolution):
    return (
        slope_degrees(dem, resolution),
        downhill_azimuth_degrees(dem, resolution),
    )


def candidates_at(dem, resolution, *, max_length_m=MAX_LENGTH_M):
    slope, aspect = slope_and_aspect(dem, resolution)
    return delineate_candidates(
        slope,
        aspect,
        grid_box(dem),
        scale_m=resolution,
        min_patch_cells=MIN_PATCH_CELLS,
        max_length_m=max_length_m,
    )


# -- bands and octants -------------------------------------------------------


def test_a_slope_on_a_break_falls_in_the_band_above():
    band = slope_band(np.array([0.0, 9.9, 10.0, 29.9, 30.0, 45.0, 59.9, 60.0, 85.0]))
    assert band.tolist() == [0, 0, 1, 2, 3, 4, 4, 5, 5]
    assert np.asarray(SLOPE_BAND_LABELS)[band[2]] == "10-20"


def test_a_nan_slope_has_no_band():
    assert slope_band(np.array([np.nan, 5.0])).tolist() == [NO_CLASS, 0]


def test_octants_are_centred_on_the_compass_points():
    azimuth = np.array([0.0, 22.4, 22.5, 90.0, 180.0, 270.0, 337.4, 337.5, 359.9])
    assert aspect_octant(azimuth).tolist() == [0, 0, 1, 2, 4, 6, 7, 0, 0]


def test_level_ground_has_no_octant():
    assert aspect_octant(np.array([np.nan])).tolist() == [NO_CLASS]
    assert aspect_octant(np.array([360.0])).tolist() == [0]
    assert ASPECT_OCTANTS == 8


# -- labelling and merging ---------------------------------------------------


def test_patches_are_four_connected_and_classes_do_not_share_labels():
    band = np.array(
        [
            [1, 1, 0, 0],
            [1, 0, 2, 0],
            [0, 0, 0, 2],
        ]
    )
    octant = np.zeros_like(band)
    labels = label_patches(band, octant)
    # The two band-2 cells touch only at a corner, so they are two patches.
    assert labels[1, 2] != labels[2, 3]
    assert labels[0, 0] == labels[0, 1] == labels[1, 0]
    # The band-0 cells form two runs: the corner at [1, 1] is not an edge.
    assert labels[0, 2] == labels[0, 3] == labels[1, 3]
    assert labels[1, 1] == labels[2, 0] == labels[2, 1] == labels[2, 2]
    assert labels[0, 2] != labels[1, 1]
    # Five patches: one of band 1, two of band 0, two single cells of band 2.
    assert len(np.unique(labels)) == 5
    assert labels.min() == 1


def test_cells_without_a_band_are_outside():
    band = np.array([[NO_CLASS, 0], [0, 0]])
    labels = label_patches(band, np.zeros_like(band))
    assert labels[0, 0] == OUTSIDE
    assert (labels[band != NO_CLASS] > OUTSIDE).all()


def test_a_level_run_joins_its_gentle_sloping_neighbour():
    band = np.zeros((3, 4), dtype=int)
    octant = np.array(
        [
            [NO_CLASS, NO_CLASS, 2, 2],
            [NO_CLASS, NO_CLASS, 2, 2],
            [4, 4, 4, 4],
        ]
    )
    labels = label_patches(band, octant)
    # The level block shares two edges with the octant-2 patch (right) and two
    # with the octant-4 patch (below); the tie goes to the lower label, and
    # either way the level block is no longer a patch of its own.
    assert len(np.unique(labels)) == 2
    assert labels[0, 0] in {labels[0, 2], labels[2, 0]}


def test_a_level_run_with_no_gentle_neighbour_stays_a_patch():
    band = np.array([[0, 0, 3, 3]])
    octant = np.array([[NO_CLASS, NO_CLASS, 1, 1]])
    labels = label_patches(band, octant)
    assert labels[0, 0] == labels[0, 1] != labels[0, 2]


def test_a_small_patch_merges_into_the_neighbour_sharing_the_longest_edge():
    labels = np.array(
        [
            [1, 1, 1, 1],
            [1, 2, 2, 3],
            [1, 2, 2, 3],
            [1, 1, 1, 1],
        ]
    )
    merged = merge_small_patches(labels, min_cells=5)
    # Patch 2 (4 cells) shares 4 edges with patch 1 and 2 with patch 3, so it
    # joins patch 1; patch 3 (2 cells) shares 3 edges with patch 1 and 2 with
    # patch 2, so it joins patch 1 too.
    assert len(np.unique(merged)) == 1
    assert merged.min() == 1


def test_two_small_patches_that_choose_each_other_become_one():
    labels = np.array([[1, 1, 2, 2]])
    merged = merge_small_patches(labels, min_cells=3)
    assert len(np.unique(merged)) == 1


def test_a_patch_at_the_minimum_is_kept():
    labels = np.array([[1, 1, 1, 2, 2, 2]])
    assert len(np.unique(merge_small_patches(labels, min_cells=3))) == 2


def test_an_island_with_no_neighbour_is_kept():
    labels = np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]])
    merged = merge_small_patches(labels, min_cells=9)
    assert merged[1, 1] == 1
    assert (merged[labels == OUTSIDE] == OUTSIDE).all()


def test_merging_refuses_a_minimum_under_one():
    with pytest.raises(ValueError, match="min_cells"):
        merge_small_patches(np.array([[1]]), min_cells=0)


# -- polygons, contour length and the split ----------------------------------


def test_patches_become_one_polygon_each_of_the_right_area():
    labels = np.array([[1, 1, 0], [1, 2, 0], [2, 2, 2]])
    transform = Affine(10.0, 0.0, ORIGIN_EASTING, 0.0, -10.0, ORIGIN_NORTHING)
    polygons = patches_to_polygons(labels, transform, constants.DEFAULT_CRS)
    assert list(polygons.columns) == ["label", "geometry"]
    assert polygons["label"].tolist() == [1, 2]
    assert polygons.geometry.area.tolist() == [300.0, 400.0]
    assert polygons.crs == constants.DEFAULT_CRS
    assert (polygons.geometry.geom_type == "Polygon").all()


def test_contour_length_is_the_extent_across_the_slope():
    strip = gpd.GeoSeries([box(0, 0, 10, 60)], crs=constants.DEFAULT_CRS)
    # Facing north the contour runs east-west: the strip is 10 m across.
    assert contour_length_m(strip, np.array([0.0])) == pytest.approx([10.0])
    # Facing east the contour runs north-south: 60 m across.
    assert contour_length_m(strip, np.array([90.0])) == pytest.approx([60.0])
    # Facing north-east the diagonal of the box is projected.
    diagonal = (10 + 60) / np.sqrt(2)
    assert contour_length_m(strip, np.array([45.0])) == pytest.approx([diagonal])


def test_contour_length_is_nan_for_level_ground():
    strip = gpd.GeoSeries([box(0, 0, 10, 60)], crs=constants.DEFAULT_CRS)
    assert np.isnan(contour_length_m(strip, np.array([np.nan])))[0]


def test_a_long_strip_splits_into_equal_pieces_across_the_slope():
    patches = gpd.GeoDataFrame(
        {"label": [1]}, geometry=[box(0, 0, 60, 10)], crs=constants.DEFAULT_CRS
    )
    # Facing north, the strip is 60 m along the contour: three 20 m pieces.
    pieces = split_long_patches(patches, np.array([0.0]), max_length_m=25.0)
    assert len(pieces) == 3
    assert pieces["label"].tolist() == [1, 1, 1]
    assert pieces.geometry.area.to_numpy() == pytest.approx([200.0, 200.0, 200.0])
    assert pieces.geometry.union_all().area == pytest.approx(600.0)
    assert contour_length_m(pieces.geometry, np.zeros(3)) == pytest.approx([20.0] * 3)
    assert list(pieces.index) == [0, 1, 2]


def test_a_strip_within_the_limit_is_not_split():
    patches = gpd.GeoDataFrame(
        {"label": [7]}, geometry=[box(0, 0, 60, 10)], crs=constants.DEFAULT_CRS
    )
    # Facing east, the strip is only 10 m along the contour.
    pieces = split_long_patches(patches, np.array([90.0]), max_length_m=25.0)
    assert len(pieces) == 1
    assert pieces.geometry.iloc[0].equals(patches.geometry.iloc[0])


def test_the_split_refuses_a_geographic_frame():
    patches = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    with pytest.raises(ValueError, match="geographic"):
        split_long_patches(patches, np.array([0.0]), max_length_m=25.0)


# -- the domain ---------------------------------------------------------------


def test_the_domain_is_the_buffered_buildings_less_the_flatland():
    buildings = gpd.GeoDataFrame(
        geometry=[box(0, 0, 10, 10), box(500, 500, 510, 510)],
        crs=constants.DEFAULT_CRS,
    )
    flatland = gpd.GeoDataFrame(
        geometry=[box(-200, -200, 200, 200)], crs=constants.DEFAULT_CRS
    )
    domain = urban_domain(buildings, flatland, building_distance_m=100.0)
    # The first building and its whole buffer lie on the flatland.
    assert not domain.intersects(box(-50, -50, 50, 50))
    assert domain.contains(box(400, 400, 610, 610).centroid)
    assert domain.area == pytest.approx(
        box(500, 500, 510, 510).buffer(100.0).area, rel=1e-6
    )


def test_an_empty_flatland_leaves_the_buffer_whole():
    buildings = gpd.GeoDataFrame(
        geometry=[box(0, 0, 10, 10)], crs=constants.DEFAULT_CRS
    )
    flatland = gpd.GeoDataFrame(geometry=[], crs=constants.DEFAULT_CRS)
    domain = urban_domain(buildings, flatland, building_distance_m=100.0)
    assert domain.area == pytest.approx(box(0, 0, 10, 10).buffer(100.0).area)


def test_the_domain_refuses_a_geographic_system():
    buildings = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    flatland = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    with pytest.raises(ValueError, match="geographic"):
        urban_domain(buildings, flatland, building_distance_m=100.0)


# -- the terrace and face ----------------------------------------------------


def test_the_terrace_and_face_gives_three_patches_at_one_metre():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    candidates = candidates_at(dem, 1)

    assert list(candidates.columns) == list(CANDIDATE_COLUMNS)
    assert len(candidates) == 3
    assert candidates["slope_band"].value_counts().to_dict() == {
        GENTLE_BAND: 2,
        STEEP_BAND: 1,
    }
    face = candidates[candidates["slope_band"] == STEEP_BAND].iloc[0]
    # The face drops east, so its downhill azimuth is 90 and its octant east.
    assert face["aspect_degrees"] == pytest.approx(90.0)
    assert face["aspect_octant"] == 2
    assert face["slope_degrees"] > 60.0
    # The face runs the full north-south length of the grid less Horn's border.
    assert face["contour_length_m"] == pytest.approx(GRID_CELLS - 2)
    assert face["area_m2"] == pytest.approx(face.geometry.area)
    assert (candidates["scale_m"] == 1).all()
    assert candidates["scale_m"].dtype == np.int64
    assert candidates.crs == constants.DEFAULT_CRS


def test_the_gentlest_band_produces_candidates_with_no_cut_off():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    candidates = candidates_at(dem, 1)
    terraces = candidates[candidates["slope_band"] == GENTLE_BAND]
    assert len(terraces) == 2
    # Level ground has no downhill direction, so no octant and no contour.
    assert (terraces["aspect_octant"] == NO_CLASS).all()
    assert terraces["aspect_degrees"].isna().all()
    assert terraces["contour_length_m"].isna().all()
    assert (terraces["slope_degrees"] == 0.0).all()


def test_the_fine_face_nests_inside_the_coarse_bank():
    dem_1m = make_dem(bank_with_face(), resolution=1.0)
    dem_3m = block_mean(dem_1m, 3)
    fine = candidates_at(dem_1m, 1)
    coarse = candidates_at(dem_3m, 3)

    assert (coarse["scale_m"] == 3).all()
    assert list(coarse.columns) == list(CANDIDATE_COLUMNS)
    # At 1 m the face is the one patch steeper than the 20 degree bank.
    fine_faces = fine[fine["slope_degrees"] > 45.0]
    assert len(fine_faces) == 1
    fine_face = fine_faces.geometry.iloc[0]
    assert fine_face.area == pytest.approx(2 * (GRID_CELLS - 2))
    # At 3 m the face is smeared into the bank: the coarse patch under the
    # face's representative point is a wider piece of bank, in a band between
    # the bank's and the face's, and it covers the whole fine face.
    point = fine_face.representative_point()
    parents = coarse[coarse.geometry.contains(point)]
    assert len(parents) == 1
    parent = parents.iloc[0]
    assert parent["slope_band"] == "30-45"
    assert parent.geometry.area > fine_face.area
    assert fine_face.intersection(parent.geometry).area / fine_face.area >= 0.9
    # The rest of the bank is there at both scales, in its own band.
    assert "20-30" in set(fine["slope_band"])
    assert "20-30" in set(coarse["slope_band"])


def test_a_face_longer_than_the_contour_limit_is_split():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    candidates = candidates_at(dem, 1, max_length_m=25.0)
    faces = candidates[candidates["slope_band"] == STEEP_BAND]
    # 43 m of face at a 25 m limit is two equal pieces.
    assert len(faces) == 2
    assert faces["contour_length_m"].to_numpy() == pytest.approx([21.5, 21.5])
    assert faces["aspect_degrees"].to_numpy() == pytest.approx([90.0, 90.0])


def test_small_patches_are_merged_away():
    elevation = terrace_and_face()
    # A single-cell bump on the upper terrace, well inside it.
    elevation[10, 5] += 0.5
    dem = make_dem(elevation, resolution=1.0)
    candidates = candidates_at(dem, 1)
    # Without the merge the bump's ring of sloping cells would be extra patches.
    assert len(candidates) == 3


def test_candidates_are_clipped_to_the_domain():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    slope, aspect = slope_and_aspect(dem, 1)
    minx, miny, _maxx, maxy = dem.rio.bounds()
    # A domain over the west of the grid, ending a quarter cell short of the
    # tenth cell's edge: the cell centre at 9.5 m is inside, so the cell is
    # segmented, and the polygon is then trimmed back to 9.75 m.
    domain = box(minx, miny, minx + 9.75, maxy)
    candidates = delineate_candidates(
        slope,
        aspect,
        domain,
        scale_m=1,
        min_patch_cells=MIN_PATCH_CELLS,
        max_length_m=MAX_LENGTH_M,
    )
    assert len(candidates) == 1
    assert candidates.geometry.iloc[0].within(domain.buffer(1e-6))
    # Horn's border drops the first column, so 8.75 m of the nine cells remain.
    assert candidates["area_m2"].iloc[0] == pytest.approx((GRID_CELLS - 2) * 8.75)


def test_an_empty_domain_gives_no_candidates():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    slope, aspect = slope_and_aspect(dem, 1)
    candidates = delineate_candidates(
        slope,
        aspect,
        Polygon(),
        scale_m=1,
        min_patch_cells=MIN_PATCH_CELLS,
        max_length_m=MAX_LENGTH_M,
    )
    assert candidates.empty
    assert list(candidates.columns) == list(CANDIDATE_COLUMNS)
    assert candidates["scale_m"].dtype == np.int64
    assert candidates["aspect_octant"].dtype == np.int64
    assert candidates["slope_band"].dtype == object
    assert candidates.crs == constants.DEFAULT_CRS


def test_an_empty_scale_stacked_with_a_populated_one_keeps_the_integer_columns():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    slope, aspect = slope_and_aspect(dem, 1)
    populated = candidates_at(dem, 1)
    # The step stacks the scales with pd.concat; under pandas 3 an empty float
    # column takes part in the dtype inference and would turn these to float.
    empty = delineate_candidates(
        slope,
        aspect,
        Polygon(),
        scale_m=1,
        min_patch_cells=MIN_PATCH_CELLS,
        max_length_m=MAX_LENGTH_M,
    )
    for frames in ([populated, empty], [empty, populated]):
        stacked = pd.concat(frames, ignore_index=True)
        assert len(stacked) == len(populated)
        assert stacked["scale_m"].dtype == np.int64
        assert stacked["aspect_octant"].dtype == np.int64
        assert stacked["slope_band"].dtype == object
        assert stacked["slope_band"].isin(SLOPE_BAND_LABELS).all()


def test_a_north_facing_patch_reads_an_aspect_of_zero_not_a_full_turn():
    # Cells facing 10 and 350 degrees in alternating columns: one band, one
    # octant, one patch, whose resultant lies a rounding error west of north
    # (the sines sum to about -4e-16). Without the fold the modulus returns
    # exactly 360.0, outside the [0, 360) a bearing lives in.
    cells = 12
    slope = make_dem(np.full((cells, cells), 25.0), resolution=1.0)
    bearings = np.where(np.arange(cells) % 2 == 0, 10.0, 350.0)
    aspect = make_dem(np.tile(bearings, (cells, 1)), resolution=1.0)
    candidates = delineate_candidates(
        slope,
        aspect,
        grid_box(slope),
        scale_m=1,
        min_patch_cells=MIN_PATCH_CELLS,
        max_length_m=MAX_LENGTH_M,
    )
    assert len(candidates) == 1
    assert candidates["aspect_degrees"].iloc[0] == pytest.approx(0.0, abs=1e-9)
    assert (candidates["aspect_degrees"] < 360.0).all()
    assert candidates["aspect_octant"].iloc[0] == 0
    assert candidates["slope_band"].iloc[0] == "20-30"


def test_the_scale_has_to_match_the_raster():
    dem = make_dem(terrace_and_face(), resolution=1.0)
    slope, aspect = slope_and_aspect(dem, 1)
    with pytest.raises(ValueError, match="scale_m"):
        delineate_candidates(
            slope,
            aspect,
            grid_box(dem),
            scale_m=3,
            min_patch_cells=MIN_PATCH_CELLS,
            max_length_m=MAX_LENGTH_M,
        )


def test_the_snap_tolerance_is_three_metres():
    assert delineation.SNAP_TOLERANCE_M == 3.0


# -- the step, end to end on synthetic inputs ---------------------------------

# The step reads the rasters step 3 writes and the ground map step 4 writes
# through their path functions, and `terrain.zonal_statistic`. Those are
# built by other implementers of the same phase; until they exist the step
# cannot be imported, and these tests say so rather than failing on an import.
UPSTREAM = (
    "scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_terrain_derivatives",
    "scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map",
)
STEP_READY = all(importlib.util.find_spec(name) is not None for name in UPSTREAM)
if STEP_READY:
    from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
        gen_multiscale_slope,
    )

    STEP_READY = all(
        hasattr(gen_multiscale_slope, name)
        for name in ("dem_path", "slope_path", "aspect_path")
    ) and hasattr(terrain, "zonal_statistic")
if STEP_READY:
    from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates import (
        gen_urban_slope_candidates as step,
    )

needs_upstream = pytest.mark.skipif(
    not STEP_READY,
    reason=(
        "landslide step 3's extension, step 4 or terrain.zonal_statistic is not "
        "built yet"
    ),
)

# A grid every scale divides: 90 one-metre cells is 3 cells at 30 m, so the 30 m
# slope has one interior cell after Horn's border.
STEP_GRID_CELLS = 90
STEP_SCALES_M = (1, 3, 10, 30)
GROUND_ATTRIBUTES = {
    "material": "greywacke",
    "modification": "natural",
    "prior_failure": "none",
    "gw_depth_class": "well_drained",
    "gw_depth_m": 4.0,
    "fill_thickness_m": np.nan,
    "geology_value": 7.0,
}


@pytest.fixture
def synthetic_step(tmp_path, monkeypatch):
    """Every input the step reads, written to tmp_path, and its readers replaced."""
    dem_1m = make_dem(bank_with_face(STEP_GRID_CELLS), resolution=1.0)
    minx, miny, maxx, maxy = dem_1m.rio.bounds()
    bbox = (minx, miny, maxx, maxy)

    def raster_path(kind, resolution_m, *, extent):
        return tmp_path / f"{kind}-{resolution_m}m.tif"

    for scale_m in STEP_SCALES_M:
        dem = dem_1m if scale_m == 1 else block_mean(dem_1m, scale_m)
        slope, aspect = slope_and_aspect(dem, scale_m)
        write_raster(dem, raster_path("dem", scale_m, extent="wlg-pilot"))
        write_raster(slope, raster_path("slope", scale_m, extent="wlg-pilot"))
        write_raster(aspect, raster_path("aspect", scale_m, extent="wlg-pilot"))

    def terrain_layer(layer, *, extent):
        return tmp_path / f"{layer}.tif"

    for position, layer in enumerate(step.TERRAIN_ATTRIBUTES):
        values = np.full(dem_1m.shape, float(position + 1))
        if layer == "vegetation-height":
            values[:] = np.nan
        write_raster(
            make_dem(values, resolution=1.0).rename(layer),
            terrain_layer(layer, extent="wlg-pilot"),
        )

    ground_map = gpd.GeoDataFrame(
        {
            "ground_id": ["GM0000001"],
            **{key: [value] for key, value in GROUND_ATTRIBUTES.items()},
        },
        geometry=[box(*bbox)],
        crs=constants.DEFAULT_CRS,
    )
    ground_path = tmp_path / "ground-map.geoparquet"
    ground_map.to_parquet(ground_path)

    # A building on each terrace, a road along the south edge, two properties
    # split down the bank, and flatland over the east end of the lower terrace.
    buildings = gpd.GeoDataFrame(
        geometry=[
            box(minx + 2, miny + 40, minx + 8, miny + 46),
            box(maxx - 30, miny + 40, maxx - 24, miny + 46),
        ],
        crs=constants.DEFAULT_CRS,
    )
    roads = gpd.GeoDataFrame(
        geometry=[LineString([(minx, miny + 3), (maxx, miny + 3)])],
        crs=constants.DEFAULT_CRS,
    )
    boundaries = gpd.GeoDataFrame(
        geometry=[box(minx, miny, minx + 20, maxy), box(minx + 20, miny, maxx, maxy)],
        crs=constants.DEFAULT_CRS,
    )
    flatland = gpd.GeoDataFrame(
        geometry=[box(maxx - 15, miny, maxx, maxy)], crs=constants.DEFAULT_CRS
    )

    monkeypatch.setattr(step, "WORK_DIR", tmp_path)
    monkeypatch.setattr(step, "resolve_extent", lambda *, extent: (bbox, "synthetic"))
    monkeypatch.setattr(
        step,
        "dem_path",
        lambda resolution_m, *, extent: raster_path("dem", resolution_m, extent=extent),
    )
    monkeypatch.setattr(
        step,
        "slope_path",
        lambda resolution_m, *, extent: raster_path(
            "slope", resolution_m, extent=extent
        ),
    )
    monkeypatch.setattr(
        step,
        "aspect_path",
        lambda resolution_m, *, extent: raster_path(
            "aspect", resolution_m, extent=extent
        ),
    )
    monkeypatch.setattr(step, "terrain_path", terrain_layer)
    monkeypatch.setattr(step, "ground_map_path", lambda *, extent: ground_path)
    monkeypatch.setattr(
        step, "get_nz_building_outlines", lambda bbox, **kwargs: buildings
    )
    monkeypatch.setattr(step, "get_nz_address_roads", lambda bbox, **kwargs: roads)
    monkeypatch.setattr(
        step, "get_nz_property_boundaries", lambda bbox, **kwargs: boundaries
    )
    monkeypatch.setattr(step, "get_nlm_flatland", lambda **kwargs: flatland)
    return {"bbox": bbox, "flatland": flatland, "buildings": buildings}


def run_step():
    step.main(
        extent="wlg-pilot",
        use_cached_layers=True,
        scales_m=STEP_SCALES_M,
        building_distance_m=100.0,
        min_patch_cells=MIN_PATCH_CELLS,
        max_patch_length_m=25.0,
    )
    return gpd.read_parquet(step.urban_slope_candidates_path(extent="wlg-pilot"))


@needs_upstream
def test_the_path_names_the_extent():
    assert (
        step.urban_slope_candidates_path(extent="wlg-pilot").name
        == "urban-slope-candidates-pilot.geoparquet"
    )
    assert (
        step.urban_slope_candidates_path(extent="full").name
        == "urban-slope-candidates.geoparquet"
    )


@needs_upstream
def test_the_step_writes_the_contracts_columns(synthetic_step):
    written = run_step()

    assert list(written.columns) == list(step.OUTPUT_COLUMNS)
    assert written.crs == constants.DEFAULT_CRS
    assert written["scale_m"].dtype == np.int64
    assert written["aspect_octant"].dtype == np.int64
    assert set(written["scale_m"]) == set(STEP_SCALES_M)
    assert written["candidate_id"].str.fullmatch(r"UC\d{7}").all()
    assert written["candidate_id"].is_unique
    assert written["candidate_id"].iloc[0] == "UC0000001"
    # Minted by scale descending, then location.
    assert written["scale_m"].is_monotonic_decreasing
    assert written["slope_band"].isin(SLOPE_BAND_LABELS).all()
    assert GENTLE_BAND in set(written["slope_band"])
    assert (written.geometry.geom_type == "Polygon").all()
    assert written["area_m2"].to_numpy() == pytest.approx(
        written.geometry.area.to_numpy()
    )


@needs_upstream
def test_the_step_reads_the_terrain_and_ground_onto_each_candidate(synthetic_step):
    written = run_step()

    # The coarse rasters carry Horn's NaN border here, which step 3's trimmed
    # rasters do not, so the coarse slopes are checked away from the grid edge.
    minx, miny, maxx, maxy = synthetic_step["bbox"]
    points = written.geometry.representative_point()
    inner = points.within(box(minx + 30, miny + 30, maxx - 30, maxy - 30))
    assert inner.any()
    assert written["slope_1m"].notna().all()
    for scale_m in STEP_SCALES_M:
        assert written.loc[inner, f"slope_{scale_m}m"].notna().all()
    for position, (column, _) in enumerate(step.TERRAIN_ATTRIBUTES.values()):
        if column == "vegetation_height_m":
            assert written[column].isna().all()
        else:
            assert written[column].to_numpy() == pytest.approx(position + 1)
    assert written["relief_m"].notna().all()
    assert (written["relief_m"] >= 0).all()
    for column, value in GROUND_ATTRIBUTES.items():
        if isinstance(value, float) and np.isnan(value):
            assert written[column].isna().all()
        else:
            assert (written[column] == value).all()
    assert (written["ground_id"] == "GM0000001").all()


@needs_upstream
def test_the_step_measures_to_buildings_roads_and_boundaries(synthetic_step):
    written = run_step()
    buildings = synthetic_step["buildings"]

    assert written["building_distance_m"].notna().all()
    assert written["road_distance_m"].notna().all()
    assert written["boundary_distance_m"].notna().all()
    assert (
        written["building_position"].isin([step.ABOVE, step.BELOW, step.BESIDE]).all()
    )
    # A candidate touching a building is at distance zero from it.
    touching = written[written.geometry.intersects(buildings.geometry.union_all())]
    assert not touching.empty
    assert (touching["building_distance_m"] == 0).all()


@needs_upstream
def test_the_step_keeps_off_the_flatland(synthetic_step):
    written = run_step()
    flatland = synthetic_step["flatland"].geometry.union_all()
    assert not written.geometry.representative_point().within(flatland).any()
