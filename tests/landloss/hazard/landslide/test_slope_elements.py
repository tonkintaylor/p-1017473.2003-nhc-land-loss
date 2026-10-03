"""Tests for the slope elements, on toy terrain whose answer is known.

The unit tests build small numpy grids worked out on paper: a plane, a sharp
step, a bank. The toy case tests run every stage D1 case of
``.agents/plans/building-face-based-urban-slope-polygons.md`` from
:mod:`landloss.hazard.landslide.synthetic_terrain`, without noise and with
LiDAR-like noise, and check the element-level outcome the plan's Development
table asks for. Positions are in metres east of each grid's west edge.

Two things about a 1 m grid shape the tolerances. Horn's kernel spreads a
sharp step over the two cells either side of it, so a vertical wall is a
two-cell element; the ground falls across the one interval between their
centres, which the DEM cannot resolve, so it is read as vertical. And an
element's crest and toe cells are cell centres, so they land within a cell of
the break they mark; its height and run are measured between the breaks.
"""

import math
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from rasterio.transform import Affine
from shapely.geometry import box

from landloss.domain.constants import MIN_WALL_HEIGHT_M
from landloss.hazard.landslide.ground_map import MATERIALS
from landloss.hazard.landslide.slope_elements import (
    BANK,
    BANK_PASS,
    BETA_GROW_ANGLE_DEG,
    CREST,
    FREE_FACE,
    FREE_FACE_PASS,
    GROUND_GROUPS,
    HEIGHT_BANDS_M,
    MATERIAL_GROUND_GROUP,
    OUTSIDE,
    SOIL_LIKE_CODE,
    STEP_ANGLE_DEG,
    STRONGER_ROCK_CODE,
    TOE,
    WEAK_ROCK,
    WEAK_ROCK_CODE,
    SlopeElements,
    find_slope_elements,
    ground_group_codes,
    height_band,
    rasterise_ground_map,
    step_angle_deg,
    step_height_raster,
    terrain_layers,
)
from landloss.hazard.landslide.slope_polygons import BETA_FACING_APART_DEG
from landloss.hazard.landslide.synthetic_terrain import (
    BETA_LIDAR_NOISE_SD_M,
    ORIGIN_EASTING,
    ORIGIN_NORTHING,
    TOY_CASES,
    ToyTerrain,
    add_lidar_noise,
    build_toy_case,
    retaining_wall,
    rotate_toy_case,
)

pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

TRANSFORM = Affine(1.0, 0.0, ORIGIN_EASTING, 0.0, -1.0, ORIGIN_NORTHING)
NOISE_LEVELS = (0.0, BETA_LIDAR_NOISE_SD_M)
SEED = int(os.environ.get("SLOPE_ELEMENTS_TEST_SEED", "7"))


def profile_dem(profile: np.ndarray, rows: int = 30) -> np.ndarray:
    """A grid that is one west-to-east profile on every row."""
    return np.tile(np.asarray(profile, dtype=float), (rows, 1))


def centres(length: int) -> np.ndarray:
    return np.arange(length) + 0.5


def run_case(name: str, noise: float) -> tuple[ToyTerrain, SlopeElements]:
    terrain = build_toy_case(name, noise_sd_m=noise, seed=SEED)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    return terrain, found


def mean_x(found: SlopeElements, label: int, role: int) -> float:
    """The mean position of an element's crest or toe cells, in metres east."""
    rows, cols = np.nonzero((found.labels == label) & ((found.edge_roles & role) > 0))
    middle = (rows > 5) & (rows < found.labels.shape[0] - 6)
    return float(np.mean(cols[middle] + 0.5))


def element_x(found: SlopeElements) -> pd.Series:
    return found.elements["centroid_x"] - ORIGIN_EASTING


def free_faces(found: SlopeElements) -> pd.DataFrame:
    return found.elements[found.elements["element_type"] == FREE_FACE]


def banks(found: SlopeElements) -> pd.DataFrame:
    return found.elements[found.elements["element_type"] == BANK]


def link(found: SlopeElements, lower: int, upper: int) -> pd.Series | None:
    links = found.stack_links
    match = links[(links["lower"] == lower) & (links["upper"] == upper)]
    return None if match.empty else match.iloc[0]


# The tables ----------------------------------------------------------------


def test_every_material_has_a_group():
    assert set(MATERIAL_GROUND_GROUP) == set(MATERIALS)
    assert set(MATERIAL_GROUND_GROUP.values()) <= set(GROUND_GROUPS)


def test_ground_group_codes_map_materials_and_off_map_ground():
    codes = ground_group_codes(
        ["fill_uncontrolled", "rock", "rock_uw_mw", "rock_crushed", None, "unknown"]
    )
    weak = GROUND_GROUPS.index(WEAK_ROCK)
    expected = [SOIL_LIKE_CODE, weak, STRONGER_ROCK_CODE, SOIL_LIKE_CODE, weak, weak]
    assert codes.tolist() == expected


def test_ground_group_codes_reject_an_unknown_material():
    with pytest.raises(ValueError, match="not ground map materials"):
        ground_group_codes(["granite"])


def test_the_step_test_table_has_24_entries():
    assert len(HEIGHT_BANDS_M) == 8
    assert sorted(STEP_ANGLE_DEG) == sorted(GROUND_GROUPS)
    assert all(len(row) == 8 for row in STEP_ANGLE_DEG.values())


@pytest.mark.parametrize(
    ("height", "band"),
    [
        (0.49, 0),
        (MIN_WALL_HEIGHT_M, 1),
        (0.99, 1),
        (1.0, 2),
        (2.0, 3),
        (3.5, 5),
        (9.9, 6),
        (12.0, 7),
        (16.0, 8),
        (80.0, 8),
        (math.nan, 0),
    ],
)
def test_height_band_breaks(height, band):
    assert height_band(height) == band


def test_step_angle_lookup_reads_the_table_and_band_zero_as_band_one():
    groups = [SOIL_LIKE_CODE, WEAK_ROCK_CODE, WEAK_ROCK_CODE, STRONGER_ROCK_CODE, 1]
    bands = [3, 5, 7, 6, 0]
    assert step_angle_deg(groups, bands).tolist() == [35.0, 45.0, 34.0, 45.0, 45.0]


# The per-cell layers -------------------------------------------------------


def test_slopes_and_fall_line_on_a_plane():
    # A plane falling one metre per metre to the east: 45 degrees at both
    # scales, downhill along the columns.
    dem = profile_dem(30.0 - centres(30))
    layers = terrain_layers(dem, 1.0)
    inner = (slice(5, -5), slice(5, -5))
    assert np.allclose(layers.slope_fine_deg[inner], 45.0)
    assert np.allclose(layers.slope_coarse_deg[inner], 45.0)
    assert np.allclose(layers.downhill_col[inner], 1.0)
    assert np.allclose(layers.downhill_row[inner], 0.0)
    assert np.isnan(layers.slope_fine_deg[0, 10])
    assert np.isnan(layers.slope_coarse_deg[3, 10])


def test_step_height_is_zero_on_an_even_hillside():
    dem = profile_dem(30.0 - 0.6 * centres(40))
    layers = terrain_layers(dem, 1.0)
    assert np.allclose(layers.step_height_m[10:-10, 10:-10], 0.0)


def test_step_height_reads_a_step_at_the_cells_either_side_of_it():
    # A 2 m step between the cells centred 19.5 and 20.5 m east, on a 10
    # degree hillside: the full height at those two cells, a quarter of it a
    # cell further out, and nothing beyond.
    x = centres(40)
    dem = profile_dem(np.where(x < 20, 2.0, 0.0) + 10.0 - 0.176 * x)
    rows = dem.shape[0]
    east = np.ones(dem.shape)
    north = np.zeros(dem.shape)
    step = step_height_raster(dem, north, east, 1.0)[rows // 2]
    assert step[19] == pytest.approx(2.0)
    assert step[20] == pytest.approx(2.0)
    assert step[18] == pytest.approx(0.5)
    assert step[21] == pytest.approx(0.5)
    assert step[16] == pytest.approx(0.0, abs=1e-9)
    assert np.isnan(step[2])


# Growth, measurement and links ---------------------------------------------


def test_a_wall_is_one_two_cell_free_face_with_crest_above_and_toe_below():
    terrain, found = run_case("01_wall", 0.0)
    assert len(found.elements) == 1
    element = found.elements.iloc[0]
    assert element["grown_in"] == FREE_FACE_PASS
    assert element["height_m"] == pytest.approx(2.0)
    # The two cells either side of the wall: the ground falls across the one
    # interval between their centres, which the DEM cannot resolve, so the
    # face is read as vertical rather than as the grid's atan(2 / 1).
    assert element["run_m"] == pytest.approx(0.0)
    assert element["overall_angle_deg"] == pytest.approx(90.0)
    assert element["aspect_deg"] == pytest.approx(90.0)
    assert mean_x(found, 1, CREST) == pytest.approx(19.5)
    assert mean_x(found, 1, TOE) == pytest.approx(20.5)
    row = terrain.dem.shape[0] // 2
    assert found.labels[row, 18] == OUTSIDE
    assert found.labels[row, 21] == OUTSIDE


def test_a_bank_that_fails_the_step_test_is_released_to_the_bank_pass():
    _, found = run_case("12_weak_rock_bank_3m", 0.0)
    assert len(found.elements) == 1
    element = found.elements.iloc[0]
    assert element["grown_in"] == BANK_PASS
    assert element["element_type"] == BANK
    assert element["overall_angle_deg"] == pytest.approx(40.0, abs=0.5)


def test_gentle_ground_is_not_an_element():
    # A 15 degree plane: under the grow angle, and no step anywhere.
    dem = profile_dem(20.0 - math.tan(math.radians(15.0)) * centres(40))
    found = find_slope_elements(dem, np.zeros(dem.shape, np.int8), TRANSFORM)
    assert found.elements.empty
    assert (found.labels == OUTSIDE).all()


def test_core_marks_the_elements_seeded_in_it_and_keeps_the_halo():
    # The halo's elements stay, so the links across the seam are built: the
    # lower wall (east, in the halo) still links to the upper one.
    terrain = build_toy_case("05_terraces_wide_bench", noise_sd_m=0.0, seed=0)
    core = np.zeros(terrain.dem.shape, dtype=bool)
    core[:, :24] = True
    found = find_slope_elements(
        terrain.dem, terrain.ground_group, terrain.transform, core=core
    )
    assert len(found.elements) == 2
    x = element_x(found)
    assert found.elements["in_core"].to_dict() == (x < 24).to_dict()
    upper, lower = x.idxmin(), x.idxmax()
    assert link(found, lower, upper) is not None
    # The seed's map position, for matching an element across tiles.
    assert found.elements.loc[upper, "seed_x"] - ORIGIN_EASTING == pytest.approx(
        20.0, abs=1.0
    )


def test_a_core_grid_of_the_wrong_shape_is_refused():
    terrain = build_toy_case("01_wall", noise_sd_m=0.0, seed=0)
    with pytest.raises(ValueError, match="core grid"):
        find_slope_elements(
            terrain.dem,
            terrain.ground_group,
            terrain.transform,
            core=np.ones((3, 3), dtype=bool),
        )


def test_categories_take_the_majority_over_each_element():
    terrain = build_toy_case("01_wall", noise_sd_m=0.0, seed=0)
    ground = np.full(terrain.dem.shape, 3)
    ground[:8] = 9
    found = find_slope_elements(
        terrain.dem,
        terrain.ground_group,
        terrain.transform,
        categories={"ground_row": ground},
    )
    assert found.elements["majority_ground_row"].tolist() == [3]


def test_ground_group_decides_the_test_angle():
    # The 2 m wall reads vertical: a free-face on soil-like ground (35) and on
    # weak rock (45), and still one on stronger rock (53).
    terrain = build_toy_case("01_wall", noise_sd_m=0.0, seed=0)
    for code, threshold in ((SOIL_LIKE_CODE, 35.0), (STRONGER_ROCK_CODE, 53.0)):
        groups = np.full(terrain.dem.shape, code, dtype=np.int8)
        found = find_slope_elements(terrain.dem, groups, terrain.transform)
        element = found.elements.iloc[0]
        assert element["threshold_angle_deg"] == threshold
        assert element["element_type"] == FREE_FACE


def test_mismatched_grids_are_refused():
    dem = np.zeros((20, 20))
    with pytest.raises(ValueError, match="ground group grid"):
        find_slope_elements(dem, np.zeros((20, 21), np.int8), TRANSFORM)


def test_a_rotated_or_south_up_grid_is_refused():
    dem = np.zeros((20, 20))
    south_up = Affine(1.0, 0.0, ORIGIN_EASTING, 0.0, 1.0, ORIGIN_NORTHING)
    with pytest.raises(ValueError, match="north-up"):
        find_slope_elements(dem, np.zeros(dem.shape, np.int8), south_up)


def test_rasterise_ground_map_burns_groups_and_rows():
    ground_map = gpd.GeoDataFrame(
        {"material": ["fill_uncontrolled", "rock_uw_mw"]},
        geometry=[
            box(
                ORIGIN_EASTING,
                ORIGIN_NORTHING - 10,
                ORIGIN_EASTING + 5,
                ORIGIN_NORTHING,
            ),
            box(
                ORIGIN_EASTING + 5,
                ORIGIN_NORTHING - 10,
                ORIGIN_EASTING + 8,
                ORIGIN_NORTHING,
            ),
        ],
        crs="EPSG:2193",
    )
    groups, rows = rasterise_ground_map(ground_map, TRANSFORM, (10, 10))
    assert (groups[:, :5] == SOIL_LIKE_CODE).all()
    assert (groups[:, 5:8] == STRONGER_ROCK_CODE).all()
    assert (groups[:, 8:] == WEAK_ROCK_CODE).all()
    assert (rows[:, :5] == 0).all()
    assert (rows[:, 8:] == -1).all()


# The stage D1 toy cases ----------------------------------------------------


def test_every_toy_case_is_tested():
    tested = {
        name.removeprefix("test_case_")
        for name in globals()
        if name.startswith("test_case_")
    }
    keys = {key.split("_", 1)[0].lstrip("0") for key in TOY_CASES}
    assert keys <= {name.split("_", 1)[0] for name in tested}


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_1_wall_is_one_free_face(noise):
    _, found = run_case("01_wall", noise)
    assert len(found.elements) == 1
    element = found.elements.iloc[0]
    assert element["element_type"] == FREE_FACE
    assert element["height_m"] == pytest.approx(2.0, abs=0.2)
    assert element["height_band"] == 3
    assert element_x(found).iloc[0] == pytest.approx(20.0, abs=0.5)


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_2_wall_with_a_bank_stacked_on_it(noise):
    terrain, found = run_case("02_wall_rising_behind", noise)
    x = element_x(found)
    wall = x.sub(terrain.features_x_m["wall"]).abs().idxmin()
    assert found.elements.loc[wall, "element_type"] == FREE_FACE
    assert found.elements.loc[wall, "height_band"] == 3
    above = banks(found)
    above = above[x[above.index] < terrain.features_x_m["wall"]]
    assert len(above) == 1
    joined = link(found, wall, above.index[0])
    assert joined is not None
    assert joined["bench_width_m"] == 0.0


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_3_four_metre_cut_carries_the_stack_dominant_flag(noise):
    terrain, found = run_case("03_excavated_toe_4m", noise)
    cut = free_faces(found)
    assert len(cut) == 1
    # Measured between the breaks in slope, the cut reads its built 4 m at
    # 60 degrees. The bank sits exactly on the free-face pass's grow limit
    # (35 less 5 degrees), so under noise the free-face takes the bank cells
    # that read over 30 degrees as well, up to about a metre of it, which
    # lowers its overall angle; the stack-dominant flag is checked noise-free
    # only.
    assert cut["height_m"].iloc[0] >= 3.8
    assert cut["height_m"].iloc[0] <= (5.2 if noise else 4.2)
    if not noise:
        assert bool(cut["stack_dominant_cut"].iloc[0])
        assert cut["overall_angle_deg"].iloc[0] == pytest.approx(60.0, abs=1.0)
    slope = banks(found)
    above = [
        label for label in slope.index if link(found, cut.index[0], label) is not None
    ]
    assert len(above) == 1
    assert slope.loc[above[0], "overall_angle_deg"] == pytest.approx(30.0, abs=1.0)
    assert link(found, cut.index[0], above[0])["bench_width_m"] == 0.0
    assert mean_x(found, cut.index[0], TOE) == pytest.approx(
        terrain.features_x_m["cut_toe"], abs=1.5 if noise else 1.0
    )
    assert mean_x(found, cut.index[0], CREST) == pytest.approx(
        terrain.features_x_m["cut_crest"], abs=3.0 if noise else 1.0
    )


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_3_two_metre_cut_has_no_stack_dominant_flag(noise):
    _, found = run_case("03_excavated_toe_2m", noise)
    cut = free_faces(found)
    assert len(cut) == 1
    assert not bool(cut["stack_dominant_cut"].iloc[0])
    # 2 m of cut and about 0.3 m of the transition cell above it; under noise
    # up to half a metre of the bank above as well (see the 4 m case).
    assert cut["height_m"].iloc[0] >= 2.2
    assert cut["height_m"].iloc[0] <= (2.95 if noise else 2.4)
    slope = banks(found)
    assert len(slope) == 1
    assert link(found, cut.index[0], slope.index[0]) is not None


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_4_slope_under_the_grow_angle_is_not_an_element(noise):
    _, found = run_case("04_cut_under_gentle_slope", noise)
    assert len(found.elements) == 1
    cut = found.elements.iloc[0]
    assert cut["element_type"] == FREE_FACE
    assert bool(cut["stack_dominant_cut"])
    assert found.stack_links.empty


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_5_narrow_bench_is_one_stack(noise):
    # A 1 m bench is one cell, which Horn's kernel reads as part of both
    # walls, so the two walls are one free-face 4 m high.
    _, found = run_case("05_terraces_narrow_bench", noise)
    assert len(found.elements) == 1
    element = found.elements.iloc[0]
    assert element["element_type"] == FREE_FACE
    assert element["height_m"] == pytest.approx(4.0, abs=0.2)


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_5_wide_bench_gives_two_linked_free_faces(noise):
    terrain, found = run_case("05_terraces_wide_bench", noise)
    faces = free_faces(found)
    assert len(faces) == 2
    x = element_x(found)
    upper = x.sub(terrain.features_x_m["upper_wall"]).abs().idxmin()
    lower = x.sub(terrain.features_x_m["lower_wall"]).abs().idxmin()
    joined = link(found, lower, upper)
    assert joined is not None
    # The 8 m bench between the wall faces less the cell of each wall that
    # stands on it.
    assert joined["bench_width_m"] == pytest.approx(6.0)
    assert link(found, upper, lower) is None


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_6_gully_heads_are_separate_elements_in_separate_catchments(noise):
    terrain, found = run_case("06_gullies_at_ridge", noise)
    ridge = terrain.features_x_m["ridge"]
    rows, cols = np.nonzero(found.labels > OUTSIDE)
    sides = pd.Series(cols + 0.5 > ridge).groupby(found.labels[rows, cols])
    assert (sides.nunique() == 1).all()
    side = sides.first()

    faces = free_faces(found)
    assert side[faces.index].nunique() == 2
    for label in faces.index:
        face_cols = np.nonzero(found.labels == label)[1] + 0.5
        assert np.min(np.abs(face_cols - ridge)) < 3.0

    links = found.stack_links
    assert (side[links["lower"]].to_numpy() == side[links["upper"]].to_numpy()).all()

    # Every coarse cell in an element's catchment lies on its own side.
    factor = round(found.catchment_transform.a)
    c_rows, c_cols = np.nonzero(found.catchments > OUTSIDE)
    east = (c_cols + 0.5) * factor > ridge
    labels = found.catchments[c_rows, c_cols]
    away = np.abs((c_cols + 0.5) * factor - ridge) > factor
    assert (east[away] == side[labels[away]].to_numpy()).all()


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_7_convex_crest_lands_where_the_slope_eases(noise):
    terrain, found = run_case("07_convex_crest", noise)
    faces = free_faces(found)
    assert len(faces) == 1
    face = faces.index[0]
    # The free-face pass stops where the 1 m slope falls to the soil-like
    # 35 degrees less the tolerance, about the 30 degree point, and takes the
    # rounded cell beyond; under noise the first cell that dips under it can
    # stop the growth up to two cells early.
    assert mean_x(found, face, CREST) == pytest.approx(
        terrain.features_x_m["at_30_deg"], abs=2.0 if noise else 1.0
    )
    # Its type is set by its overall angle, which is gentler than its
    # steepest cell.
    element = faces.loc[face]
    assert element["overall_angle_deg"] < element["slope_max_deg"]
    assert element["overall_angle_deg"] > element["threshold_angle_deg"]
    # What is left of the rounding above it, over the grow angle, is a bank
    # where it stands half a metre or more, and its crest is where the slope
    # eases under the grow angle.
    rounding = banks(found)
    assert len(rounding) <= 1
    if len(rounding):
        assert mean_x(found, rounding.index[0], CREST) == pytest.approx(
            terrain.features_x_m["at_grow_angle"], abs=1.0
        )
        assert link(found, face, rounding.index[0]) is not None


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_8_concave_toe_lands_where_the_slope_eases(noise):
    terrain, found = run_case("08_concave_toe", noise)
    faces = free_faces(found)
    assert len(faces) == 1
    face = faces.index[0]
    # Under noise the first cell that dips under the grow limit stops the
    # growth, so the toe lands up to two cells early on the gentle easing.
    assert mean_x(found, face, TOE) == pytest.approx(
        terrain.features_x_m["at_30_deg"], abs=2.0 if noise else 1.0
    )
    easing = banks(found)
    assert len(easing) <= 1
    if len(easing):
        assert mean_x(found, easing.index[0], TOE) == pytest.approx(
            terrain.features_x_m["at_grow_angle"], abs=1.0
        )
        assert link(found, easing.index[0], face) is not None


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_9_road_cut_is_one_free_face(noise):
    terrain, found = run_case("09_road_cut", noise)
    long = found.elements[found.elements["length_m"] > 20.0]
    assert len(long) == 1
    cut = long.iloc[0]
    assert cut["element_type"] == FREE_FACE
    assert cut["length_m"] >= terrain.features_x_m["cut_length_m"]
    assert cut["height_band"] == 5
    # Where the cut fades out at each end, under 1.5 m high and easing under
    # the free-face pass's grow limit, a few cells are left as elements of
    # their own, a few metres long.
    others = found.elements.drop(index=long.index)
    assert (others["length_m"] < 10.0).all()


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_10_wall_in_a_bank_is_three_stacked_elements(noise):
    terrain, found = run_case("10_wall_in_bank", noise)
    assert len(found.elements) == 3
    order = element_x(found).sort_values().index
    above, wall, below = order
    assert found.elements.loc[wall, "element_type"] == FREE_FACE
    assert found.elements.loc[above, "element_type"] == BANK
    assert found.elements.loc[below, "element_type"] == BANK
    assert element_x(found)[wall] == pytest.approx(
        terrain.features_x_m["wall"], abs=1.0
    )
    assert found.elements.loc[wall, "step_peak_m"] == pytest.approx(1.5, abs=0.3)
    assert link(found, wall, above) is not None
    assert link(found, below, wall) is not None


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_11_small_step_is_no_element(noise):
    _, found = run_case("11_small_step", noise)
    assert found.elements.empty


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_12_three_metre_weak_rock_bank_is_a_bank(noise):
    _, found = run_case("12_weak_rock_bank_3m", noise)
    assert len(found.elements) == 1
    element = found.elements.iloc[0]
    assert element["element_type"] == BANK
    assert element["threshold_angle_deg"] == 45.0


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_12_twelve_metre_weak_rock_bank_is_a_free_face(noise):
    _, found = run_case("12_weak_rock_bank_12m", noise)
    assert len(found.elements) == 1
    element = found.elements.iloc[0]
    assert element["element_type"] == FREE_FACE
    assert element["height_band"] == 7
    assert element["threshold_angle_deg"] == 34.0


@pytest.mark.parametrize("name", ["12_weak_rock_bank_3m", "12_weak_rock_bank_12m"])
def test_a_bank_is_measured_between_its_breaks_in_slope(name):
    # Its crest and toe cells sit a cell inside the breaks; measured from the
    # breaks it reads its built height at its built angle.
    terrain, found = run_case(name, 0.0)
    element = found.elements.iloc[0]
    built = terrain.dem.max() - terrain.dem.min()
    assert element["height_m"] == pytest.approx(built, abs=0.05)
    assert element["overall_angle_deg"] == pytest.approx(40.0, abs=0.5)


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_13_soil_batters_either_side_of_the_soil_like_test_angle(noise):
    # Added in stage D1: a 3 m batter at 37 degrees is a free-face on the
    # soil-like 35 degrees, one at 33 degrees a bank.
    for name, kind, angle in (
        ("13_soil_batter_37deg", FREE_FACE, 37.0),
        ("13_soil_batter_33deg", BANK, 33.0),
    ):
        _, found = run_case(name, noise)
        assert len(found.elements) == 1
        element = found.elements.iloc[0]
        assert element["element_type"] == kind
        assert element["height_m"] == pytest.approx(3.0, abs=0.15)
        assert element["overall_angle_deg"] == pytest.approx(
            angle, abs=1.5 if noise else 0.2
        )


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_14_gully_heads_60_degrees_apart_are_separate_free_faces(noise):
    # Added in stage D1: a ridge bent at a nose, its two gully heads facing
    # under BETA_FACING_APART_DEG apart, unlike case 6's 180 degrees.
    terrain, found = run_case("14_gullies_at_bent_ridge", noise)
    faces = free_faces(found)
    assert len(faces) == 2
    apex_northing = terrain.features_x_m["apex_northing_m"]
    sides = np.sign(found.elements.loc[faces.index, "centroid_y"] - apex_northing)
    assert sides.nunique() == 2
    aspects = sorted(faces["aspect_deg"])
    assert aspects[1] - aspects[0] < BETA_FACING_APART_DEG
    # Disjoint catchments, like case 6's.
    assert found.drainage_links.empty
    assert set(np.unique(found.catchments[found.catchments > OUTSIDE])) == set(
        faces.index
    )


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_15_undulating_hills_give_no_element(noise):
    # Added in stage D1: rolling ground under the grow angle everywhere.
    _, found = run_case("15_undulating_hills", noise)
    assert found.elements.empty


# Walls and slopes off the grid's axes ---------------------------------------


def long_elements(found: SlopeElements) -> pd.DataFrame:
    """The elements running most of a turned grid, not the grid-edge pieces."""
    return found.elements[found.elements["length_m"] > 40.0]


@pytest.mark.parametrize("bearing", [90.0, 120.0, 135.0])
@pytest.mark.parametrize("height", [0.6, 0.8, 1.2, 1.6])
@pytest.mark.parametrize("group", [SOIL_LIKE_CODE, WEAK_ROCK_CODE, STRONGER_ROCK_CODE])
def test_a_low_vertical_wall_is_a_free_face_on_any_ground_and_bearing(
    bearing, height, group
):
    # A wall falls across one interval between cell centres at any bearing,
    # so it reads vertical: a free-face on every ground group, at its height
    # (bearings 90, 120 and 135 are the profile turned 0, 30 and 45 degrees).
    terrain = rotate_toy_case(retaining_wall(height), bearing)
    groups = np.full(terrain.dem.shape, group, dtype=np.int8)
    found = find_slope_elements(terrain.dem, groups, terrain.transform)
    walls = long_elements(found)
    assert len(walls) == 1
    wall = walls.iloc[0]
    assert wall["element_type"] == FREE_FACE
    assert wall["overall_angle_deg"] == pytest.approx(90.0)
    assert wall["height_m"] == pytest.approx(height, abs=0.01)
    assert wall["aspect_deg"] == pytest.approx(bearing, abs=2.5)


@pytest.mark.parametrize("bearing", [110.0, 120.0, 135.0])
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_1_wall_off_the_grid_axes(bearing, noise):
    terrain = rotate_toy_case(TOY_CASES["01_wall"](), bearing)
    if noise:
        terrain = add_lidar_noise(terrain, sd_m=noise, seed=SEED)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    walls = long_elements(found)
    assert len(walls) == 1
    assert walls["element_type"].iloc[0] == FREE_FACE
    assert walls["height_m"].iloc[0] == pytest.approx(2.0, abs=0.15)


@pytest.mark.parametrize("bearing", [110.0, 120.0, 135.0])
def test_case_3_four_metre_cut_off_the_grid_axes(bearing):
    # The cut keeps its stack-dominant flag and its bank above at any
    # bearing: it reads 60 to 62 degrees, against 55 when it was measured
    # between cell centres.
    terrain = rotate_toy_case(TOY_CASES["03_excavated_toe_4m"](), bearing)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    elements = long_elements(found)
    cut = elements[elements["element_type"] == FREE_FACE]
    bank = elements[elements["element_type"] == BANK]
    assert len(cut) == 1
    assert len(bank) == 1
    assert bool(cut["stack_dominant_cut"].iloc[0])
    assert cut["overall_angle_deg"].iloc[0] == pytest.approx(60.0, abs=3.0)
    assert bank["overall_angle_deg"].iloc[0] == pytest.approx(30.0, abs=1.0)
    assert link(found, cut.index[0], bank.index[0]) is not None


# Nodata ---------------------------------------------------------------------


def test_nodata_beside_a_bank_is_not_its_crest_or_toe():
    # A 5 by 4 m hole in case 3's bank and a nodata strip along the grid's
    # west edge, behind the bank's crest: the cells beside them are the
    # bank's ends, not its crest or toe, and the transects they cut short are
    # left out, so the bank keeps its height to within a cell's rise.
    terrain = build_toy_case("03_excavated_toe_4m", noise_sd_m=0.0, seed=0)
    clean = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    bank_height = banks(clean)["height_m"].iloc[0]
    dem = terrain.dem.copy()
    dem[18:23, 22:26] = np.nan
    dem[:, :3] = np.nan
    found = find_slope_elements(dem, terrain.ground_group, terrain.transform)
    bank = banks(found)
    assert len(bank) == 1
    rise_per_cell = math.tan(math.radians(30.0))
    assert bank["height_m"].iloc[0] == pytest.approx(bank_height, abs=rise_per_cell)
    assert bool(bank["touches_nodata"].iloc[0])
    # Every crest cell is at the bank's top, none beside the hole.
    _, cols = np.nonzero(
        (found.labels == bank.index[0]) & ((found.edge_roles & CREST) > 0)
    )
    assert cols.max() <= 12
    _, toe_cols = np.nonzero(
        (found.labels == bank.index[0]) & ((found.edge_roles & TOE) > 0)
    )
    assert toe_cols.min() >= 30


def test_ground_gentler_than_the_grow_angle_is_not_an_element():
    # The steep cells either side of each gully's axis grow along the floor
    # but measure across it, under the grow angle: dropped (stage D1 case 6).
    _, found = run_case("06_gullies_at_ridge", 0.0)
    assert (found.elements["overall_angle_deg"] >= BETA_GROW_ANGLE_DEG).all()
    assert len(found.elements) == 2


# Mixed ground ---------------------------------------------------------------


def test_a_seed_does_not_flood_ground_it_cannot_keep():
    # One 40 degree bank, 3 m high, soil-like on its north half and weak rock
    # on its south half: a free-face on the soil (35) and a bank on the rock
    # (45), each over its own half.
    terrain = build_toy_case("12_weak_rock_bank_3m", noise_sd_m=0.0, seed=0)
    groups = np.full(terrain.dem.shape, WEAK_ROCK_CODE, dtype=np.int8)
    groups[:20] = SOIL_LIKE_CODE
    found = find_slope_elements(terrain.dem, groups, terrain.transform)
    soil_rows = found.labels[8:16]
    rock_rows = found.labels[24:32]
    soil = np.unique(soil_rows[soil_rows > OUTSIDE])
    rock = np.unique(rock_rows[rock_rows > OUTSIDE])
    assert len(soil) == 1
    assert len(rock) == 1
    assert found.elements.loc[soil[0], "element_type"] == FREE_FACE
    assert found.elements.loc[rock[0], "element_type"] == BANK
    # Each half's rows hold the whole bank, not a strip of it.
    assert ((soil_rows > OUTSIDE).sum(axis=1) >= 3).all()
    assert ((rock_rows > OUTSIDE).sum(axis=1) >= 3).all()
