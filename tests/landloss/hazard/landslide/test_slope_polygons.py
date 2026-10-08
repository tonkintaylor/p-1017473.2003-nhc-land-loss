"""Tests for the failure polygons, on the stage D1 toy terrain.

Each toy case of ``.agents/plans/building-face-based-urban-slope-polygons.md``
runs through :func:`find_slope_elements` and :func:`build_slope_polygons`,
without noise and with LiDAR-like noise, and the polygon outcome the plan's
Development table asks for is checked. Positions are in metres east of each
grid's west edge, a cell's centre at ``column + 0.5``.

The walls of cases 1, 2 and 5 stand on fill (the plan's case 1 says so); the
ground rising behind case 2's wall is natural, and every other case is cut or
natural ground. Every case runs out as a dry debris avalanche.

What the 1 m grid does to the numbers, worked once here for case 1, a 2 m
vertical wall: the element is the two cells either side of the wall (centres
19.5 and 20.5 m), its crest cell's centre half a metre behind the wall. The
fill wedge is ``2 x tan(45 - 42/2) = 0.89 m`` behind that centre, under a
cell, so the polygon is the element alone. Its depth is to the slip plane
from the toe cell (z 0, 1 m in front of the crest cell) to the back of the
wedge (z 2, 0.89 m behind it): 0.94 m at the crest cell and nothing at the
toe cell, about 0.94 m3 per metre of wall against the triangle's
``0.5 x 2 x 0.89 = 0.89``. Imminent: the repose line from the toe cell at 35
degrees meets the level ground at ``2 / tan 35 - 1 = 1.86 m`` behind the crest
cell, past the T-45 band of 0.89 + 1.0 m, so one cell (centre 18.5 m).
Inundated: every failure runs out as a dry debris avalanche, and one of
about 36 m3 has ``H/L = 10^(0.0315 - 0.033 log10 36) = 0.95``, so the line
from the crest cell (z 2) meets the ground 2.09 m out, at 21.59 m: the cell
centred 21.5 m, one metre past the toe, well under the caps of three heights
and of the volume at 0.3 m deep.
"""

import math
import os

import numpy as np
import pandas as pd
import pytest
import shapely

from landloss.hazard.landslide import slope_polygons
from landloss.hazard.landslide.slope_elements import (
    BANK,
    CREST,
    FREE_FACE,
    SlopeElements,
    find_slope_elements,
)
from landloss.hazard.landslide.slope_polygons import (
    BETA_MAX_DEPOSIT_DEPTH_H,
    BETA_MAX_DEPOSIT_DEPTH_SOURCE,
    BETA_MAX_RUNOUT_H_STEEP,
    BETA_MIN_EVACUATED_WIDTH_H,
    BETA_MIN_EVACUATED_WIDTH_M,
    BETA_REPOSE_ANGLE_DEG,
    BETA_SEGMENT_VOLUME_M3,
    CUT_SLOPE,
    DOWNSLOPE,
    EVACUATED,
    FILL_BANK_WEDGE,
    FILL_PHI_DEG,
    HEADSCARP_BAND,
    IMMINENT,
    INUNDATED,
    SEPARATE_CATCHMENTS,
    STACK_OVERLAP,
    WALL_WEDGE,
    WITHIN_WIDTH,
    SlopePolygons,
    build_slope_polygons,
    conditional_failure_probability,
    cut_reach_past_toe_m,
    deposit_overlap_m2,
    element_depth_m,
    imminent_width_m,
    inundated_length_m,
    max_runout_h,
    min_evacuated_width_m,
    planar_depth_m,
    polygon_geometries,
    reach_ratio,
    seismic_runout_m,
    smooth_cell_outline,
    source_angle_deg,
    width_behind_crest_m,
)
from landloss.hazard.landslide.synthetic_terrain import (
    BETA_LIDAR_NOISE_SD_M,
    ORIGIN_EASTING,
    TOY_CASES,
    ToyTerrain,
    build_toy_case,
)
from landloss.hazard.landslide.urban.face_polygons import BETA_OFF_MAP_GROUND

pytestmark = [
    pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning"),
    pytest.mark.usefixtures("legacy_step_table"),
]

NOISE_LEVELS = (0.0, BETA_LIDAR_NOISE_SD_M)
SEED = int(os.environ.get("SLOPE_ELEMENTS_TEST_SEED", "7"))

# The cases whose walls stand on fill; their free-faces are on fill, any
# ground rising behind them natural.
FILL_CASES = ("01", "02", "05")


def run_case(
    name: str, noise: float, **kwargs
) -> tuple[ToyTerrain, SlopeElements, SlopePolygons]:
    terrain = build_toy_case(name, noise_sd_m=noise, seed=SEED)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    if name[:2] in FILL_CASES:
        kwargs.setdefault("is_fill", found.elements["element_type"] == FREE_FACE)
    result = build_slope_polygons(found, terrain.dem, terrain.transform, **kwargs)
    return terrain, found, result


def long_elements(found: SlopeElements, kind: str) -> pd.Index:
    """The elements of a kind running most of a profile, not noise fragments."""
    elements = found.elements
    chosen = (elements["element_type"] == kind) & (elements["length_m"] > 20.0)
    return elements.index[chosen]


def zone_cells(result: SlopePolygons, zone: str, polygon=None) -> pd.DataFrame:
    cells = result.cells[result.cells["zone"] == zone]
    if polygon is None:
        return cells
    polygons = [polygon] if np.isscalar(polygon) else list(polygon)
    return cells[cells["polygon"].isin(polygons)]


def in_front(result: SlopePolygons, polygon=None) -> pd.DataFrame:
    """The inundated cells off the polygons' own evacuated ground.

    A deep deposit spreads back over its own scar as well; these are the
    cells of the strip below the toe.
    """
    inundated = zone_cells(result, INUNDATED, polygon)
    evac = zone_cells(result, EVACUATED, polygon)[["polygon", "row", "col"]]
    merged = inundated.merge(
        evac, on=["polygon", "row", "col"], how="left", indicator=True
    )
    return merged[merged["_merge"] == "left_only"].drop(columns="_merge")


def x_of(cells: pd.DataFrame) -> np.ndarray:
    return cells["col"].to_numpy() + 0.5


def middle(cells: pd.DataFrame, rows: int) -> pd.DataFrame:
    """The cells away from the north and south ends of a profile case."""
    return cells[(cells["row"] > 5) & (cells["row"] < rows - 6)]


def polygons_of(result: SlopePolygons, found: SlopeElements, kind: str):
    types = found.elements["element_type"]
    return result.polygons[result.polygons["element"].map(types) == kind]


def nearest_element(found: SlopeElements, x_m: float) -> int:
    x = found.elements["centroid_x"] - ORIGIN_EASTING
    return int((x - x_m).abs().idxmin())


def crest_x(found: SlopeElements, label: int) -> float:
    """The westmost crest cell centre of an element, in metres east."""
    _, cols = np.nonzero((found.labels == label) & ((found.edge_roles & CREST) > 0))
    return float(cols.min() + 0.5)


def retro(result: SlopePolygons) -> pd.DataFrame:
    return result.retrogression_links


@pytest.fixture
def type_rules_only(monkeypatch):
    """Turn the minimum evacuated width off, so a toy case reads its type's rule.

    The stage D1 toy cases were set against the type rules; the floor is
    tested on its own and on case 1 with it on.
    """
    monkeypatch.setattr(slope_polygons, "BETA_MIN_EVACUATED_WIDTH_H", 0.0)
    monkeypatch.setattr(slope_polygons, "BETA_MIN_EVACUATED_WIDTH_M", 0.0)


# The rules ------------------------------------------------------------------


def test_the_minimum_width_is_half_the_height_and_never_under_a_metre():
    assert BETA_MIN_EVACUATED_WIDTH_H == 0.5
    assert BETA_MIN_EVACUATED_WIDTH_M == 1.0
    assert min_evacuated_width_m([0.5, 2.0, 3.0, 10.0, np.nan]) == pytest.approx(
        [1.0, 1.0, 1.5, 5.0, 1.0]
    )


def test_the_minimum_width_sets_every_type_where_it_is_wider():
    width, rule = width_behind_crest_m(
        [FREE_FACE, BANK, BANK, BANK, FREE_FACE],
        [2.0, 4.0, 3.0, 3.0, 10.0],
        [63.0, 30.0, 30.0, 20.0, 60.0],
        is_fill=[True, True, False, False, False],
        phi_deg=[FILL_PHI_DEG, FILL_PHI_DEG, FILL_PHI_DEG, FILL_PHI_DEG, 28.0],
    )
    # A metre over the 2 m wall's 0.89 m wedge; half the height over the fill
    # bank's 0.45 H and the T-44 bands; the wedge on 28 degree ground, 0.60 H,
    # is wider than the floor and stands.
    assert width[4] == pytest.approx(10.0 * math.tan(math.radians(31.0)))
    assert width == pytest.approx([1.0, 2.0, 1.5, 1.5, 6.01], abs=1e-2)
    # The rule is still the type's.
    assert rule.tolist() == [
        WALL_WEDGE,
        FILL_BANK_WEDGE,
        HEADSCARP_BAND,
        HEADSCARP_BAND,
        WALL_WEDGE,
    ]


@pytest.mark.usefixtures("type_rules_only")
def test_widths_behind_the_crest_by_element_type():
    width, rule = width_behind_crest_m(
        [FREE_FACE, BANK, BANK, BANK],
        [2.0, 4.0, 3.0, 3.0],
        [63.0, 30.0, 30.0, 20.0],
        is_fill=[True, True, False, False],
        phi_deg=[FILL_PHI_DEG, FILL_PHI_DEG, FILL_PHI_DEG, FILL_PHI_DEG],
    )
    # The fill's wedge, tan(45 - 21) = 0.445 of the height; the fill bank
    # 0.45 H; the T-44 band, a metre at 30 degrees and half a metre under.
    assert width == pytest.approx([0.890, 1.8, 1.0, 0.5], abs=1e-3)
    assert rule.tolist() == [
        WALL_WEDGE,
        FILL_BANK_WEDGE,
        HEADSCARP_BAND,
        HEADSCARP_BAND,
    ]


def test_a_free_face_wedge_widens_on_weaker_retained_ground():
    width, _ = width_behind_crest_m(
        [FREE_FACE, FREE_FACE],
        [2.0, 2.0],
        [60.0, 60.0],
        is_fill=[False, False],
        phi_deg=[42.0, 32.0],
    )
    # Brown and Larkin's 32 degree low case gives 0.55 H.
    assert width[1] / 2.0 == pytest.approx(math.tan(math.radians(29.0)))
    assert width[1] > width[0]


def test_depths_by_element_type():
    depth = element_depth_m(
        [FREE_FACE, FREE_FACE, BANK, BANK, BANK],
        [4.0, 4.0, 3.0, 3.0, 3.0],
        is_fill=[False, False, True, True, False],
        fill_thickness_m=[np.nan, np.nan, 2.5, np.nan, np.nan],
        width_m=[1.8, 1.8, 1.35, 1.35, 1.0],
        run_m=[0.0, 2.3, 4.0, 4.0, 4.0],
    )
    # Half the height behind a vertical wall; a face leaning back spreads the
    # same wedge, 0.5 H w, over its run as well.
    assert depth[0] == pytest.approx(2.0)
    assert depth[1] == pytest.approx(0.5 * 4.0 * 1.8 / (1.8 + 2.3))
    # A fill bank takes the same wedge, no deeper than its fill: thick fill
    # or unknown, the wedge; thin fill, the fill.
    wedge = 0.5 * 3.0 * 1.35 / (1.35 + 4.0)
    assert depth[2] == pytest.approx(wedge)
    assert depth[3] == pytest.approx(wedge)
    assert depth[4] == pytest.approx(1.5)
    thin = element_depth_m(
        [BANK],
        [3.0],
        is_fill=[True],
        fill_thickness_m=[0.2],
        width_m=[1.35],
        run_m=[4.0],
    )
    assert thin[0] == pytest.approx(0.2)


def test_planar_depth_is_the_triangle_toe_crest_back():
    # A 60 degree cut 4 m high (run 2.31 m) with a 1.8 m wedge on level ground:
    # the plane from the toe to the back of the wedge, integrated across the
    # face and the wedge, is 0.5 x 4 x 1.8 per metre.
    run, width, height = 4.0 / math.tan(math.radians(60.0)), 1.8, 4.0
    x = np.linspace(-run, width, 20001)
    ground = np.where(x < 0, height + x * math.tan(math.radians(60.0)), height)
    depth = planar_depth_m(
        ground, x, toe_z=0.0, run_m=run, back_z=height, width_m=width
    )
    area = np.trapezoid(depth, x)
    assert area == pytest.approx(0.5 * height * width, rel=1e-3)
    assert depth[0] == pytest.approx(0.0)
    assert depth[-1] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("source", "downslope", "hl", "style"),
    [
        # Cuts onto near-horizontal ground: 0.78 (tan a_cut)^0.5.
        (45.0, 0.0, 0.78, CUT_SLOPE),
        (60.0, 5.0, 0.78 * math.sqrt(math.tan(math.radians(60.0))), CUT_SLOPE),
        # Not read below the toe: the cut relation.
        (45.0, np.nan, 0.78, CUT_SLOPE),
        # A vertical step is read at the steepest cut.
        (90.0, 0.0, 0.78 * math.sqrt(math.tan(math.radians(80.0))), CUT_SLOPE),
        # Steep ground below the toe: 0.77 tan a2 + 0.087.
        (45.0, 20.0, 0.77 * math.tan(math.radians(20.0)) + 0.087, DOWNSLOPE),
        (30.0, 30.0, 0.77 * math.tan(math.radians(30.0)) + 0.087, DOWNSLOPE),
        # Read no steeper than the steepest unconfined case, tan a2 0.93.
        (45.0, 60.0, 0.77 * 0.93 + 0.087, DOWNSLOPE),
    ],
)
def test_reach_ratio_follows_hunter_and_fell(source, downslope, hl, style):
    got_hl, got_style = reach_ratio([source], [downslope])
    assert got_hl[0] == pytest.approx(hl)
    assert got_style[0] == style


@pytest.mark.parametrize("downslope", [22.0, 25.0, 30.0, 40.0, 60.0])
def test_the_downslope_line_is_flatter_than_steep_ground(downslope):
    # Over about 21 degrees, so debris off a face on a steep slope runs on
    # down it.
    hl, _ = reach_ratio([35.0], [downslope])
    assert hl[0] < math.tan(math.radians(downslope))


@pytest.mark.parametrize(
    ("reach", "height", "volume", "toe", "seismic", "expected"),
    [
        # The rays' reach plus the seismic distance, under the cap.
        (5.0, 4.0, 400.0, 10.0, 1.0, 6.0),
        # No reach past the toe: the seismic distance alone.
        (0.0, 4.0, 400.0, 10.0, 0.5, 0.5),
        # The deposit depth cap holds the reach, not the seismic distance.
        (5.0, 4.0, 1.0, 10.0, 2.0, 1.0 / 3.0 + 2.0),
        # The sum is held to two heights past the toe on flat ground.
        (60.0, 2.0, 400.0, 10.0, 1.0, 4.0),
        (3.5, 2.0, 400.0, 10.0, 1.0, 4.0),
        # A small face's cap holds the seismic distance too.
        (0.0, 0.5, 400.0, 10.0, 3.0, 1.0),
    ],
)
def test_inundated_length_is_the_reach_plus_the_seismic_distance_capped(
    reach, height, volume, toe, seismic, expected
):
    length = inundated_length_m(
        reach,
        height_m=height,
        volume_m3=volume,
        toe_length_m=toe,
        downslope_angle_deg=0.0,
        seismic_m=seismic,
    )
    assert length == pytest.approx(expected)


@pytest.mark.parametrize(
    ("zone", "metres"),
    [(1, 0.5), (2, 0.5), (3, 1.0), (4, 2.0), (5, 3.0), (pd.NA, 1.0), (np.nan, 1.0)],
)
def test_the_seismic_distance_follows_the_kingsbury_zone(zone, metres):
    assert seismic_runout_m([zone])[0] == pytest.approx(metres)


@pytest.mark.parametrize(
    ("downslope", "heights"),
    [(np.nan, 2.0), (0.0, 2.0), (19.9, 2.0), (20.0, 3.0), (34.9, 3.0), (35.0, 4.0)],
)
def test_the_runout_cap_rises_with_the_ground_below_the_toe(downslope, heights):
    assert max_runout_h(downslope) == pytest.approx(heights)
    length = inundated_length_m(
        60.0,
        height_m=2.0,
        volume_m3=400.0,
        toe_length_m=10.0,
        downslope_angle_deg=downslope,
        seismic_m=0.0,
    )
    assert length == pytest.approx(heights * 2.0)


@pytest.mark.parametrize(
    ("height", "run", "expected"),
    [
        # A vertical step reads a cell of run: read vertical.
        (2.0, 1.0, 90.0),
        (2.0, 0.0, 90.0),
        # A 45 degree read on 2 m of run is 63 degrees on the 1 m left.
        (2.0, 2.0, math.degrees(math.atan(2.0))),
        (3.0, 4.0, 45.0),
        (3.0, np.nan, 90.0),
    ],
)
def test_the_source_angle_takes_off_the_run_the_dem_adds(height, run, expected):
    assert source_angle_deg(height, run) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("reach", "height", "band", "expected"),
    [
        (2.0, 4.0, 1.0, 2.0),
        # Never under the T-45 band.
        (0.2, 4.0, 1.0, 1.0),
        # Never past where the repose line from the toe meets level ground.
        (40.0, 2.0, 1.0, 2.0 / math.tan(math.radians(BETA_REPOSE_ANGLE_DEG))),
        # The band governs where it is the wider.
        (40.0, 0.5, 1.0, 1.0),
    ],
)
def test_imminent_width_is_the_reach_floored_and_capped(reach, height, band, expected):
    width = imminent_width_m(reach, height_m=height, band_m=band)
    assert width == pytest.approx(expected)


@pytest.mark.parametrize("name", sorted(TOY_CASES))
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_zones_stay_within_their_caps_of_the_evacuated_ground(name, noise):
    _, _, result = run_case(name, noise)
    tan_repose = math.tan(math.radians(BETA_REPOSE_ANGLE_DEG))
    evacuated = zone_cells(result, EVACUATED)
    # A cell centre is up to a diagonal from the line it is measured along.
    slack = math.sqrt(2.0)
    for polygon, row in result.polygons.iterrows():
        own = evacuated[evacuated["polygon"] == polygon][["row", "col"]].to_numpy()
        caps = {
            INUNDATED: BETA_MAX_RUNOUT_H_STEEP * row["height_m"],
            IMMINENT: max(row["height_m"] / tan_repose, 1.0),
        }
        for zone, cap in caps.items():
            cells = zone_cells(result, zone, polygon)[["row", "col"]].to_numpy()
            if cells.size == 0:
                continue
            gaps = np.hypot(
                *(cells[:, None, :] - own[None, :, :]).transpose(2, 0, 1)
            ).min(axis=1)
            assert gaps.max() <= cap + slack, (polygon, zone)


@pytest.mark.parametrize(
    ("volume", "height", "depth", "strip", "expected"),
    [
        # Shallow enough on the strip in front: no overlap.
        (10.0, 2.0, 5.0, 10.0, 0.0),
        # 40 m3 on 10 m2 is 4 m deep against a 2 m limit (the height): 10 m2
        # more.
        (40.0, 2.0, 5.0, 10.0, 10.0),
        # No strip at all: the whole deposit lies on the evacuated ground.
        (40.0, 2.0, 5.0, 0.0, 20.0),
        # A shallow failure on a high face: twice its 0.5 m source depth, not
        # its 10 m height, is the limit, so 20 m3 needs 20 m2: 15 m2 more.
        (20.0, 10.0, 0.5, 5.0, 15.0),
    ],
)
def test_deposit_overlap_is_the_area_that_brings_it_under_the_limit(
    volume, height, depth, strip, expected
):
    assert BETA_MAX_DEPOSIT_DEPTH_H == 1.0
    assert BETA_MAX_DEPOSIT_DEPTH_SOURCE == 2.0
    overlap = deposit_overlap_m2(
        volume, height_m=height, depth_m=depth, strip_area_m2=strip
    )
    assert overlap == pytest.approx(expected)


@pytest.mark.parametrize("name", sorted(TOY_CASES))
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_a_deep_deposit_spreads_back_over_the_lowest_evacuated_ground(name, noise):
    terrain, _, result = run_case(name, noise)
    z = terrain.dem
    for polygon, row in result.polygons.iterrows():
        evac = zone_cells(result, EVACUATED, polygon)
        inundated = zone_cells(result, INUNDATED, polygon)
        if inundated.empty:
            continue
        evac_keys = set(zip(evac["row"], evac["col"], strict=True))
        on_evac = [
            (r, c)
            for r, c in zip(inundated["row"], inundated["col"], strict=True)
            if (r, c) in evac_keys
        ]
        depth = row["volume_m3"] / len(inundated)
        limit = min(
            BETA_MAX_DEPOSIT_DEPTH_H * row["height_m"],
            BETA_MAX_DEPOSIT_DEPTH_SOURCE * row["depth_m"],
        )
        if on_evac:
            # Spread back only as far as it must (one cell of slack), and
            # over the lowest of the evacuated ground first.
            assert depth > limit * (1 - 1 / len(inundated)) - 1e-9 or len(
                on_evac
            ) == len(evac_keys)
            highest_covered = max(z[r, c] for r, c in on_evac)
            uncovered = evac_keys - set(on_evac)
            if uncovered:
                assert highest_covered <= min(z[r, c] for r, c in uncovered)
        else:
            assert depth <= limit + 1e-9


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_a_wall_runs_out_the_same_length_along_its_whole_toe(noise):
    terrain, _, result = run_case("01_wall", noise)
    runout = middle(zone_cells(result, INUNDATED), terrain.dem.shape[0])
    reach = runout.groupby("row")["col"].max()
    assert reach.nunique() == 1


def test_a_wall_onto_level_ground_runs_out_by_the_cut_relation():
    _, _, result = run_case("01_wall", 0.0)
    assert result.polygons["is_fill"].all()
    assert (result.polygons["style"] == CUT_SLOPE).all()
    assert (result.polygons["downslope_angle_deg"].abs() < 1.0).all()


def test_conditional_failure_probability():
    assert conditional_failure_probability(0.2, retrogression_p=0.5) == pytest.approx(
        0.6
    )
    assert conditional_failure_probability(0.0, retrogression_p=0.3) == pytest.approx(
        0.3
    )


def test_no_elements_give_no_polygons():
    _, _, result = run_case("11_small_step", 0.0)
    assert result.polygons.empty
    assert result.cells.empty


def test_mismatched_grids_are_refused():
    terrain = build_toy_case("01_wall", noise_sd_m=0.0, seed=0)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    with pytest.raises(ValueError, match="DEM"):
        build_slope_polygons(found, terrain.dem[:, :-1], terrain.transform)
    with pytest.raises(ValueError, match="barrier"):
        build_slope_polygons(
            found, terrain.dem, terrain.transform, barriers=np.zeros((3, 3), bool)
        )


def test_barriers_stop_the_runout():
    terrain = build_toy_case("01_wall", noise_sd_m=0.0, seed=0)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    barriers = np.zeros(terrain.dem.shape, dtype=bool)
    barriers[:, 22] = True
    fill = pd.Series(data=True, index=found.elements.index)
    result = build_slope_polygons(
        found, terrain.dem, terrain.transform, is_fill=fill, barriers=barriers
    )
    assert set(in_front(result)["col"]) == {21}


def test_geometries_are_true_to_the_cells():
    _, _, result = run_case("03_excavated_toe_4m", 0.0)
    for zone in (EVACUATED, IMMINENT, INUNDATED):
        drawn = polygon_geometries(result, zone=zone, crs="EPSG:2193", smooth=False)
        counts = zone_cells(result, zone).groupby("polygon").size()
        assert drawn.set_index("polygon").area.to_dict() == pytest.approx(
            counts.astype(float).to_dict()
        )
    with pytest.raises(ValueError, match="zone"):
        polygon_geometries(result, zone="debris", crs="EPSG:2193")


@pytest.mark.parametrize("name", sorted(TOY_CASES))
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_polygons_tile_except_where_the_rules_let_them_overlap(name, noise):
    _, _, result = run_case(name, noise)
    evacuated = zone_cells(result, EVACUATED)
    if result.polygons.empty:
        return
    assert (result.polygons["area_m2"] > 0).all()
    assert (result.polygons["volume_m3"] > 0).all()
    shared = evacuated[evacuated.duplicated(["row", "col"], keep=False)]
    pairs = shared.merge(shared, on=["row", "col"], suffixes=("_a", "_b"))
    pairs = pairs[pairs["polygon_a"] < pairs["polygon_b"]]
    found = set(zip(pairs["polygon_a"], pairs["polygon_b"], strict=True))
    listed = set(
        zip(result.overlaps["polygon_a"], result.overlaps["polygon_b"], strict=True)
    )
    assert found == listed


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
def test_case_1_wall_takes_the_minimum_width_behind_its_crest(noise):
    terrain, found, result = run_case("01_wall", noise)
    polygon = result.polygons.iloc[0]
    height = found.elements["height_m"].iloc[0]
    assert polygon["width_floored"]
    assert polygon["width_behind_crest_m"] == pytest.approx(max(0.5 * height, 1.0))
    # A metre behind the crest cell's centre is the next cell's centre, so the
    # polygon takes a cell of level ground behind the wall's two.
    rows = terrain.dem.shape[0]
    assert set(x_of(middle(zone_cells(result, EVACUATED), rows))) == {
        18.5,
        19.5,
        20.5,
    }


@pytest.mark.usefixtures("type_rules_only")
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_1_wall_polygon_is_the_level_ground_wedge(noise):
    terrain, found, result = run_case("01_wall", noise)
    assert len(result.polygons) == 1
    polygon = result.polygons.iloc[0]
    assert polygon["width_rule"] == WALL_WEDGE
    assert polygon["style"] == CUT_SLOPE
    assert polygon["width_behind_crest_m"] == pytest.approx(
        0.445 * found.elements["height_m"].iloc[0], abs=0.01
    )
    assert not polygon["is_stack"]
    rows = terrain.dem.shape[0]
    # The wedge is under a cell, so the polygon is the element's two cells.
    assert set(x_of(middle(zone_cells(result, EVACUATED), rows))) == {19.5, 20.5}
    # Its volume is the wedge's triangle, 0.5 H w per metre, cut to cells.
    triangle = 0.5 * 2.0 * polygon["width_behind_crest_m"] * polygon["length_m"]
    assert polygon["volume_m3"] == pytest.approx(
        triangle, rel=0.1 if not noise else 0.2
    )
    # The repose line clears the level ground at the next cell (centre 17.5
    # m) by about 0.1 m, so under noise that cell is imminent in some rows.
    imminent = set(x_of(middle(zone_cells(result, IMMINENT), rows)))
    assert {18.5} <= imminent <= ({17.5, 18.5} if noise else {18.5})
    runout = set(x_of(middle(zone_cells(result, INUNDATED), rows)))
    assert {21.5} <= runout <= {21.5, 22.5}


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_2_wall_takes_its_own_width_and_links_the_bank(noise):
    terrain, found, result = run_case("02_wall_rising_behind", noise)
    wall = nearest_element(found, terrain.features_x_m["wall"])
    assert found.elements.loc[wall, "element_type"] == FREE_FACE
    polygons = result.polygons[result.polygons["element"] == wall]
    assert len(polygons) == 1
    polygon = polygons.iloc[0]
    assert not polygon["is_stack"]
    assert polygon["n_stack_elements"] == 0
    # The polygon reaches no further behind the wall than its own width.
    evacuated = x_of(zone_cells(result, EVACUATED, polygons.index[0]))
    reach = crest_x(found, wall) - polygon["width_behind_crest_m"]
    assert evacuated.min() >= reach - 0.5
    links = retro(result)
    linked = links[links["lower_polygon"] == polygons.index[0]]
    linked = linked[linked["n_rays"] == linked["n_rays"].max()]
    assert len(linked) == 1
    bank = int(linked["upper_element"].iloc[0])
    assert found.elements.loc[bank, "element_type"] == BANK
    # The ground rising behind the wall is natural, not fill.
    bank_polygon = result.polygons[result.polygons["element"] == bank].iloc[0]
    assert bank_polygon["width_rule"] == HEADSCARP_BAND
    assert linked["bench_width_m"].iloc[0] == 0.0
    element_link = result.element_links[
        (result.element_links["lower"] == wall)
        & (result.element_links["upper"] == bank)
    ]
    assert bool(element_link["makes_stack"].iloc[0])


@pytest.mark.usefixtures("type_rules_only")
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_3_four_metre_cut_takes_the_bank_to_its_crest(noise):
    terrain, found, result = run_case("03_excavated_toe_4m", noise)
    cut = long_elements(found, FREE_FACE)[0]
    polygons = result.polygons[result.polygons["element"] == cut]
    stack_dominant = bool(found.elements.loc[cut, "stack_dominant_cut"])
    if not noise:
        assert stack_dominant
    # The polygon follows the flag either way.
    assert (polygons["is_stack"] == stack_dominant).all()
    if not stack_dominant:
        return
    bank = long_elements(found, BANK)[0]
    assert (polygons["top_element"] == bank).all()
    assert (polygons["n_stack_elements"] >= 1).all()
    # The polygon runs to the bank's crest and the bank's own T-44 band of a
    # metre behind it, and its height is the stack's, toe of the cut to crest
    # of the bank.
    evacuated = middle(zone_cells(result, EVACUATED, polygons.index), 40)
    assert x_of(evacuated).min() == pytest.approx(
        terrain.features_x_m["bank_crest"] - 1.0, abs=1.5
    )
    assert x_of(evacuated).max() == pytest.approx(
        terrain.features_x_m["cut_toe"], abs=1.0
    )
    stack_height = 4.0 + 26.0 * math.tan(math.radians(30.0))
    assert (polygons["height_m"] - stack_height).abs().max() < 1.0
    # The bank's own polygon is kept as well, nested in the stack's.
    assert STACK_OVERLAP in set(result.overlaps["reason"])
    if not noise:
        assert not retro(result)["lower_polygon"].isin(polygons.index).any()
    # The stack, a dry failure from its top, would deposit on itself; it also
    # takes the reach from the cut's own crest, so it runs out below the toe
    # as far as the cut alone does (case 4, the same cut).
    _, _, alone = run_case("04_cut_under_gentle_slope", noise)
    runout = middle(zone_cells(result, INUNDATED, polygons.index), 40)
    runout_alone = middle(zone_cells(alone, INUNDATED), 40)
    assert not runout.empty
    assert x_of(runout).max() >= x_of(runout_alone).max() - 1.0


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_3_two_metre_cut_takes_its_width_and_links_the_bank(noise):
    _terrain, found, result = run_case("03_excavated_toe_2m", noise)
    cut = long_elements(found, FREE_FACE)[0]
    bank = long_elements(found, BANK)[0]
    polygons = result.polygons[result.polygons["element"] == cut]
    assert not polygons["is_stack"].any()
    width = polygons["width_behind_crest_m"].iloc[0]
    evacuated = middle(zone_cells(result, EVACUATED, polygons.index), 40)
    westmost = evacuated.groupby("row")["col"].min() + 0.5
    # Its own width behind its crest and no more: within a cell of it.
    assert westmost.median() >= crest_x(found, cut) - width - 1.0
    links = retro(result)
    assert bank in set(
        links.loc[links["lower_polygon"].isin(polygons.index), "upper_element"]
    )
    # The cut's width reaches into the bank: the cut keeps that ground within
    # its width and so does the bank (the plan's stack rule 3).
    assert set(result.overlaps["reason"]) <= {WITHIN_WIDTH}
    imminent = x_of(zone_cells(result, IMMINENT, polygons.index))
    assert imminent.min() < x_of(evacuated).min()


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_4_cut_under_a_gentle_slope_takes_its_width_only(noise):
    _, found, result = run_case("04_cut_under_gentle_slope", noise)
    assert len(result.polygons) == 1
    polygon = result.polygons.iloc[0]
    assert polygon["is_stack"]
    assert polygon["n_stack_elements"] == 0
    evacuated = x_of(zone_cells(result, EVACUATED))
    reach = crest_x(found, int(polygon["element"])) - polygon["width_behind_crest_m"]
    assert evacuated.min() >= reach - 0.5
    assert retro(result).empty


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_5_narrow_bench_is_one_polygon(noise):
    _, _, result = run_case("05_terraces_narrow_bench", noise)
    assert len(result.polygons) == 1


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_5_wide_bench_gives_two_separate_polygons(noise):
    terrain, found, result = run_case("05_terraces_wide_bench", noise)
    assert len(result.polygons) == 2
    assert result.overlaps.empty
    upper = nearest_element(found, terrain.features_x_m["upper_wall"])
    lower = nearest_element(found, terrain.features_x_m["lower_wall"])
    links = retro(result)
    assert len(links) == 1
    assert links["lower_element"].iloc[0] == lower
    assert links["upper_element"].iloc[0] == upper
    assert links["bench_width_m"].iloc[0] == pytest.approx(6.0, abs=0.1)
    element_link = result.element_links.set_index(["lower", "upper"]).loc[
        (lower, upper)
    ]
    assert not element_link["makes_stack"]


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_6_gully_polygons_overlap_only_at_the_ridge(noise):
    terrain, found, result = run_case("06_gullies_at_ridge", noise)
    ridge = terrain.features_x_m["ridge"]
    faces = polygons_of(result, found, FREE_FACE)
    sides = np.sign(faces["centroid_x"] - ORIGIN_EASTING - ridge)
    assert set(sides) == {-1.0, 1.0}
    for polygon, side in sides.items():
        x = x_of(zone_cells(result, EVACUATED, polygon))
        across = side * (x - ridge)
        assert across.min() > -2.0

    # With a wedge as wide as the gully heads are high (phi' of zero), the two
    # polygons reach over the ridge: each keeps the shared ground, because the
    # gully heads drain apart, and only within two metres of the ridge.
    phi = pd.Series(0.0, index=found.elements.index)
    wide = build_slope_polygons(
        found, terrain.dem, terrain.transform, retained_phi_deg=phi
    )
    heads = wide.polygons.index[wide.polygons["element"].isin(faces["element"])]
    between = wide.overlaps[
        wide.overlaps["polygon_a"].isin(heads) & wide.overlaps["polygon_b"].isin(heads)
    ]
    assert set(between["reason"]) == {SEPARATE_CATCHMENTS}
    evacuated = zone_cells(wide, EVACUATED, heads)
    shared = evacuated[evacuated.duplicated(["row", "col"], keep=False)]
    assert not shared.empty
    assert np.abs(x_of(shared) - ridge).max() <= 2.0


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_7_convex_crest_segments_are_no_shorter_than_the_element(noise):
    _, found, result = run_case("07_convex_crest", noise)
    face = found.elements.index[found.elements["element_type"] == FREE_FACE][0]
    segments = result.polygons[result.polygons["element"] == face]
    height = found.elements.loc[face, "height_m"]
    assert (segments["length_m"] >= height - 1.0).all()


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_7_free_face_takes_its_whole_width_through_the_bank_above(noise):
    # The free-face's 0.45 H (6 m) reaches past the bank on the rounding
    # above it. By the plan's stack rule 3 it takes its own width even there:
    # it keeps the bank's ground within its width, shared with the bank's own
    # polygon, so along every row its polygon is one unbroken run of cells
    # reaching its width behind its crest.
    _, found, result = run_case("07_convex_crest", noise)
    face = found.elements.index[found.elements["element_type"] == FREE_FACE][0]
    polygons = result.polygons[result.polygons["element"] == face]
    cells = zone_cells(result, EVACUATED, polygons.index)
    for _, row in cells.groupby("row"):
        cols = np.sort(row["col"].to_numpy())
        assert (np.diff(cols) == 1).all()
    width = polygons["width_behind_crest_m"].to_numpy()
    realised = polygons["width_realised_m"].to_numpy()
    assert realised == pytest.approx(width, abs=1.0)
    rounding = found.elements.index[found.elements["element_type"] == BANK]
    if len(rounding):
        bank_polygons = result.polygons.index[result.polygons["element"].isin(rounding)]
        shared = result.overlaps[
            result.overlaps["polygon_a"].isin(polygons.index)
            & result.overlaps["polygon_b"].isin(bank_polygons)
        ]
        assert set(shared["reason"]) == {WITHIN_WIDTH}


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_8_concave_toe_runs_out_onto_the_easing(noise):
    terrain, found, result = run_case("08_concave_toe", noise)
    face = found.elements.index[found.elements["element_type"] == FREE_FACE][0]
    polygons = result.polygons[result.polygons["element"] == face]
    runout = middle(in_front(result, polygons.index), 40)
    # The debris lands on the easing below the free-face's toe.
    assert not runout.empty
    face_rows, face_cols = np.nonzero(found.labels == face)
    toe_x = pd.Series(face_cols).groupby(face_rows).max().median() + 0.5
    assert x_of(runout).min() >= toe_x - 1.0
    assert x_of(runout).max() <= terrain.features_x_m["toe"] + 1.0
    easing = found.elements.index[found.elements["element_type"] == BANK]
    if len(easing):
        links = retro(result)
        assert (links["lower_element"] == easing[0]).any()


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_9_road_cut_is_one_polygon_under_the_segment_volume(noise):
    # 0.5 x 4 m x 1.8 m, about 3.6 m3 per metre over 224 m, is under the
    # segment volume, so the road cut is one polygon.
    _, found, result = run_case("09_road_cut", noise)
    cut = found.elements["length_m"].idxmax()
    segments = result.polygons[result.polygons["element"] == cut]
    assert len(segments) == 1
    assert segments["volume_m3"].iloc[0] < BETA_SEGMENT_VOLUME_M3


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_9_road_cut_is_cut_into_segments_by_volume(noise):
    # With a wedge as wide as the cut is high (phi' of zero) it holds about
    # 8 m3 per metre, so it is cut into segments by volume.
    _, found, result = run_case(
        "09_road_cut",
        noise,
        retained_phi_deg=pd.Series(0.0, index=range(1, 100)),
    )
    cut = found.elements["length_m"].idxmax()
    segments = result.polygons[result.polygons["element"] == cut].sort_values("segment")
    assert len(segments) >= 2
    # Every segment but the last holds the segment volume, give or take one
    # metre of the cut's run (about 10 m3).
    assert (segments["volume_m3"].iloc[:-1] - BETA_SEGMENT_VOLUME_M3).abs().max() < 30.0
    assert (segments["length_m"] >= found.elements.loc[cut, "height_m"]).all()
    assert result.overlaps.empty
    # The segments meet end to end along the cut, with no gap between them.
    total = segments["length_m"].sum()
    assert total == pytest.approx(found.elements.loc[cut, "length_m"], abs=3.0)


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_10_wall_in_a_bank_runs_out_onto_the_lower_bank(noise):
    terrain, found, result = run_case("10_wall_in_bank", noise)
    wall = nearest_element(found, terrain.features_x_m["wall"])
    order = (found.elements["centroid_x"]).sort_values().index
    above, below = order[0], order[-1]
    polygon = result.polygons.index[result.polygons["element"] == wall][0]
    # Away from the ends of the profile, where the banks stop short of the
    # wall, the debris lands on the bank below.
    runout = middle(zone_cells(result, INUNDATED, polygon), terrain.dem.shape[0])
    assert not runout.empty
    assert (found.labels[runout["row"], runout["col"]] == below).all()
    links = retro(result)
    pairs = set(zip(links["lower_element"], links["upper_element"], strict=True))
    assert (wall, above) in pairs
    assert (below, wall) in pairs


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_11_small_step_has_no_polygon(noise):
    _, _, result = run_case("11_small_step", noise)
    assert result.polygons.empty


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_13_soil_batters_take_the_wedge_or_the_band(noise):
    _, _, steep = run_case("13_soil_batter_37deg", noise)
    _, _, gentle = run_case("13_soil_batter_33deg", noise)
    assert set(steep.polygons["width_rule"]) == {WALL_WEDGE}
    assert set(gentle.polygons["width_rule"]) == {HEADSCARP_BAND}


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_14_gully_heads_60_degrees_apart_overlap_within_width(noise):
    # Added in stage D1: facing under BETA_FACING_APART_DEG apart, the two
    # gully heads' disjoint catchments still take `within_width`, not
    # `separate_catchments` (case 6's gully heads face 180 degrees apart and
    # take the latter).
    terrain, found, result = run_case("14_gullies_at_bent_ridge", noise)
    faces = polygons_of(result, found, FREE_FACE)
    assert len(faces) == 2
    apex_northing = terrain.features_x_m["apex_northing_m"]
    sides = np.sign(faces["centroid_y"] - apex_northing)
    assert set(sides) == {-1.0, 1.0}
    between = result.overlaps[
        result.overlaps["polygon_a"].isin(faces.index)
        & result.overlaps["polygon_b"].isin(faces.index)
    ]
    assert not between.empty
    assert set(between["reason"]) <= {WITHIN_WIDTH}


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_15_undulating_hills_have_no_polygon(noise):
    _, _, result = run_case("15_undulating_hills", noise)
    assert result.polygons.empty


@pytest.mark.usefixtures("type_rules_only")
@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_case_12_weak_rock_banks_take_the_band_or_the_wedge(noise):
    _, _, low = run_case("12_weak_rock_bank_3m", noise)
    assert set(low.polygons["width_rule"]) == {HEADSCARP_BAND}
    assert (low.polygons["width_behind_crest_m"] == 1.0).all()
    _, found, high = run_case("12_weak_rock_bank_12m", noise)
    assert set(high.polygons["width_rule"]) == {WALL_WEDGE}
    # Onto level ground a 40 degree cut's travel line, 0.78 (tan 40)^0.5,
    # meets level ground about 0.2 heights past its toe, and the unscored
    # seismic distance adds 1 m: the 3 m bank's debris runs two cells, the
    # 12 m bank's three or more.
    for result, cells in ((low, {2}), (high, {3, 4})):
        assert (result.polygons["style"] == CUT_SLOPE).all()
        runout = zone_cells(result, INUNDATED)
        evac = zone_cells(result, EVACUATED)[["row", "col"]]
        front = runout.merge(evac, on=["row", "col"], how="left", indicator=True)
        front = front[front["_merge"] == "left_only"]
        assert not front.empty
        assert front.groupby("row")["col"].nunique().median() in cells
    # The imminent band behind the 12 m free-face is the T-45 band alone: the
    # repose line from its toe, at 35 degrees, is under its 40 degree face.
    assert found.elements["overall_angle_deg"].iloc[0] > BETA_REPOSE_ANGLE_DEG
    assert (high.polygons["imminent_area_m2"] <= high.polygons["length_m"] + 2).all()


# Tiles ------------------------------------------------------------------------


def stitch(name: str, west_cols: int, east_start: int, seam: int) -> tuple:
    """Run a case whole and as two overlapping tiles split at ``seam``.

    Returns:
        ``(whole, tiled)``: per run, the evacuated cells and the retrogression
        links, keyed by each element's seed position in map units, so the
        two runs compare across tiles.
    """
    terrain = build_toy_case(name, noise_sd_m=0.0, seed=0)
    fill = FILL_CASES

    def run(dem, groups, transform, core):
        found = find_slope_elements(dem, groups, transform, core=core)
        kwargs = {}
        if name[:2] in fill:
            kwargs["is_fill"] = found.elements["element_type"] == FREE_FACE
        result = build_slope_polygons(found, dem, transform, **kwargs)
        key = found.elements[["seed_x", "seed_y"]].apply(tuple, axis=1)
        offset = round((transform.c - terrain.transform.c) / transform.a)
        cells = result.cells[result.cells["zone"] == EVACUATED].assign(
            col=lambda frame: frame["col"] + offset
        )
        polygon_key = result.polygons["element"].map(key)
        evacuated = {
            (polygon_key[p], int(r), int(c))
            for p, r, c in zip(
                cells["polygon"], cells["row"], cells["col"], strict=True
            )
        }
        links = {
            (key[int(lo)], key[int(up)])
            for lo, up in zip(
                result.retrogression_links["lower_element"],
                result.retrogression_links["upper_element"],
                strict=True,
            )
        }
        return evacuated, links

    whole = run(terrain.dem, terrain.ground_group, terrain.transform, None)
    tiled = (set(), set())
    for first, last in ((0, west_cols), (east_start, terrain.dem.shape[1])):
        window = (slice(None), slice(first, last))
        transform = terrain.transform * terrain.transform.translation(first, 0)
        core = np.zeros(terrain.dem[window].shape, dtype=bool)
        cols = np.arange(first, last)
        core[:, (cols < seam) if first == 0 else (cols >= seam)] = True
        evacuated, links = run(
            terrain.dem[window], terrain.ground_group[window], transform, core
        )
        tiled[0].update(evacuated)
        tiled[1].update(links)
    return whole, tiled


def test_two_overlapping_tiles_stitch_to_the_whole_grid():
    # Case 5's wide bench split between its walls (at x 24 m), each tile with
    # a halo of 14 m over the seam: the polygons and the retrogression link
    # from the lower wall to the upper one, across the seam, come out as on
    # the whole grid.
    whole, tiled = stitch("05_terraces_wide_bench", 38, 10, 24)
    assert tiled[0] == whole[0]
    assert tiled[1] == whole[1]
    assert whole[1]


def test_a_ray_runs_out_from_where_it_leaves_its_polygons_evacuated_ground():
    # A plane falling 2 m a metre to the east; the ray's element is column 2
    # and its polygon's evacuated ground runs on over column 3.
    dem = np.tile(-2.0 * np.arange(8, dtype=float), (3, 1))
    labels = np.zeros(dem.shape, dtype=np.int32)
    labels[:, 2] = 1
    rays = slope_polygons._Rays(  # noqa: SLF001
        row=np.array([1]),
        col=np.array([2]),
        up_row=np.array([0.0]),
        up_col=np.array([-1.0]),
        base=np.array([1], dtype=np.int32),
        toe_z=np.array([-6.0]),
        run_m=np.array([1.0]),
    )
    own = np.array([1 * dem.size + 1 * dem.shape[1] + 3], dtype=np.int64)
    toe, reach = slope_polygons._march_downhill(  # noqa: SLF001
        labels,
        dem,
        rays,
        top_z=np.array([-4.0]),
        top_d=np.array([0.0]),
        reach_hl=np.array([1.0]),
        barriers=None,
        cell_size_m=1.0,
        own_keys=own,
        ray_keys=np.array([1 * dem.size], dtype=np.int64),
    )
    assert toe.tolist() == [2.0]
    assert reach.tolist() == [4.0]


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        # Two cells down a 25 degree slope from the toe.
        (2.0, 25.0),
        # Past the slope's foot onto level ground: the mean over the window.
        (8.0, math.degrees(math.atan(4 * math.tan(math.radians(25.0)) / 8.0))),
        # The edge of the grid comes first: the last cell before it.
        (50.0, math.degrees(math.atan(4 * math.tan(math.radians(25.0)) / 9.0))),
    ],
)
def test_the_downslope_angle_is_read_along_the_fall_line_past_the_toe(window, expected):
    # A ray from column 0 down a row: its toe at column 2, 25 degree ground
    # to column 6, then level to the edge at column 11.
    x = np.arange(12, dtype=float)
    z = -np.clip(x - 2.0, 0.0, 4.0) * math.tan(math.radians(25.0))
    dem = np.tile(z, (3, 1))
    rays = slope_polygons._Rays(  # noqa: SLF001
        row=np.array([1]),
        col=np.array([0]),
        up_row=np.array([0.0]),
        up_col=np.array([-1.0]),
        base=np.array([1], dtype=np.int32),
        toe_z=np.array([0.0]),
        run_m=np.array([2.0]),
    )
    angle = slope_polygons._downslope_angle_deg(  # noqa: SLF001
        dem,
        rays,
        toe_d=np.array([2.0]),
        window_m=np.array([window]),
        cell_size_m=1.0,
    )
    assert angle[0] == pytest.approx(expected)


def test_no_toe_reads_no_downslope_angle():
    dem = np.zeros((3, 5))
    rays = slope_polygons._Rays(  # noqa: SLF001
        row=np.array([1]),
        col=np.array([0]),
        up_row=np.array([0.0]),
        up_col=np.array([-1.0]),
        base=np.array([1], dtype=np.int32),
        toe_z=np.array([0.0]),
        run_m=np.array([1.0]),
    )
    angle = slope_polygons._downslope_angle_deg(  # noqa: SLF001
        dem, rays, toe_d=np.array([np.nan]), window_m=np.array([2.0]), cell_size_m=1.0
    )
    assert np.isnan(angle[0])


@pytest.mark.parametrize("angle", [45.0, 60.0, 70.0, 80.0, 90.0])
def test_a_cut_runs_under_half_its_height_past_its_toe(angle):
    hl, _ = reach_ratio([angle], [0.0])
    past = cut_reach_past_toe_m(2.0, angle, hl)
    capped = min(angle, 80.0)
    assert past[0] == pytest.approx(
        2.0 * (1.0 / hl[0] - 1.0 / math.tan(math.radians(capped)))
    )
    assert 0.25 * 2.0 < past[0] < 0.42 * 2.0


def test_the_ground_scores_a_zone_whose_distance_the_runout_takes():
    terrain = build_toy_case("01_wall", noise_sd_m=0.0, seed=0)
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    ground = pd.DataFrame(
        [BETA_OFF_MAP_GROUND] * len(found.elements), index=found.elements.index
    )
    unscored = build_slope_polygons(found, terrain.dem, terrain.transform)
    scored = build_slope_polygons(
        found, terrain.dem, terrain.transform, element_ground=ground
    )
    assert unscored.polygons["kingsbury_zone"].isna().all()
    zones = scored.polygons["kingsbury_zone"]
    assert zones.notna().all()
    assert scored.polygons["seismic_runout_m"].to_numpy() == pytest.approx(
        seismic_runout_m(zones)
    )
    extra = scored.polygons["seismic_runout_m"] - unscored.polygons["seismic_runout_m"]
    cap = 2.0 * scored.polygons["height_m"]
    expected = np.minimum(unscored.polygons["runout_m"] + extra, cap)
    assert scored.polygons["runout_m"].to_numpy() == pytest.approx(expected.to_numpy())


def test_a_staircase_of_cells_is_redrawn_as_its_diagonal():
    # Single-cell steps: the outline runs through the midpoints between cell
    # centres, so the stepped edge becomes a straight diagonal and the
    # smoothed outline has a handful of vertices, not one per step.
    cells = [shapely.box(i, i, i + 1, i + 1) for i in range(6)] + [
        shapely.box(i + 1, i, i + 2, i + 1) for i in range(5)
    ]
    smooth = smooth_cell_outline(shapely.union_all(cells), 1.0)
    assert smooth.is_valid
    assert smooth.area == pytest.approx(11.0, rel=0.1)
    assert len(shapely.get_coordinates(smooth)) < 30
    # The middle of the band stays inside, its stepped corners do not.
    assert smooth.contains(shapely.Point(3.0, 2.5))
    assert not smooth.contains(shapely.Point(0.05, 0.95))


def test_a_straight_run_of_cells_keeps_its_edges():
    smooth = smooth_cell_outline(shapely.box(0, 0, 10, 1), 1.0)
    # The long sides stay on the cell edges; only the ends are rounded, by
    # no more than a quarter cell.
    minx, miny, maxx, maxy = smooth.bounds
    assert (miny, maxy) == pytest.approx((0.0, 1.0))
    assert 0.0 <= minx <= 0.25
    assert 9.75 <= maxx <= 10.0
    assert smooth.contains(shapely.LineString([(1.0, 0.01), (9.0, 0.01)]))
    assert 9.0 < smooth.area < 10.0


def test_a_hole_stays_a_hole():
    cells = shapely.box(0, 0, 5, 5).difference(shapely.box(2, 2, 3, 3))
    smooth = smooth_cell_outline(cells, 1.0)
    assert not smooth.contains(shapely.Point(2.5, 2.5))
    assert len(smooth.interiors) == 1


def test_smoothed_zones_lie_on_their_cells():
    _, _, result = run_case("03_excavated_toe_4m", 0.0)
    scar = polygon_geometries(
        result, zone=EVACUATED, crs="EPSG:2193", smooth=False
    ).set_index("polygon")["geometry"]
    for zone in (EVACUATED, IMMINENT, INUNDATED):
        cells = polygon_geometries(result, zone=zone, crs="EPSG:2193", smooth=False)
        smooth = polygon_geometries(result, zone=zone, crs="EPSG:2193")
        both = cells.merge(smooth, on="polygon", suffixes=("_cells", "_smooth"))
        for _, row in both.iterrows():
            own = row["geometry_cells"]
            if zone == IMMINENT:
                # It also takes the corners the evacuated outline cuts off.
                own = shapely.union(own, scar[row["polygon"]])
            # Never more than half a cell off the cells' own outline.
            assert row["geometry_smooth"].buffer(1e-9).within(own.buffer(0.5))
            if zone != IMMINENT:
                assert row["geometry_smooth"].area <= row["geometry_cells"].area


def test_the_smoothed_imminent_band_lies_against_the_evacuated_outline():
    _, _, result = run_case("03_excavated_toe_4m", 0.0)
    evacuated = polygon_geometries(result, zone=EVACUATED, crs=None)
    imminent = polygon_geometries(result, zone=IMMINENT, crs=None)
    cells = polygon_geometries(result, zone=IMMINENT, crs=None, smooth=False)
    both = evacuated.merge(imminent, on="polygon", suffixes=("_evac", "_imm"))
    assert len(both) > 0
    for _, row in both.iterrows():
        evac, imm = row["geometry_evac"], row["geometry_imm"]
        # No overlap, and no gap: the two meet along the evacuated outline.
        assert shapely.intersection(evac, imm).area == pytest.approx(0.0, abs=1e-6)
        assert shapely.union(evac, imm).area == pytest.approx(
            evac.area + imm.area, abs=1e-6
        )
        assert shapely.distance(evac, imm) == pytest.approx(0.0, abs=1e-6)
    # Within a cell or so of the band's own cells' area, not shaved off.
    drawn = imminent.set_index("polygon").area.sum()
    assert drawn == pytest.approx(cells.set_index("polygon").area.sum(), rel=0.1)
