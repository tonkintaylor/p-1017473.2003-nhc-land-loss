"""Draw the slope elements and their polygons on the stage D1 toy terrain.

Stage D1 of ``.agents/plans/building-face-based-urban-slope-polygons.md``:
every toy case of ``landloss.hazard.landslide.synthetic_terrain`` is run
through ``find_slope_elements`` and ``build_slope_polygons``, without noise and
with LiDAR-like noise, and drawn as a plan view over hillshade with contours
beside a cross-section along the middle row (the fall line of every case). The
elements are coloured free-face or bank, the polygon (the evacuated ground) is
outlined, and the imminent and inundated zones are filled, all at their true
size, cell edges and all.

Each case's expected outcome, the plan's Development table, is checked by a
function here, on the noise-free case and on every noise seed in the config,
and the pass counts and timings are printed for the findings document beside
this script, ``toy_slope_elements.md``.

The walls of cases 1, 2 and 5 stand on fill (their free-faces are fill, the
ground rising behind case 2's wall natural); every other case is cut or
natural ground, so it runs out as a dry debris avalanche. Every free-face
takes a wall's wedge until phase 2 decides which carry a wall. Cases 13 (two
soil-like batters either side of 35 degrees) were added in stage D1.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/slope_elements/fig_toy_slope_elements.py

Writes one PNG per case and an overview panel to
``report/hazard/landslide/slope-elements/fig/``. Needs no data: the terrain is
synthetic.
"""

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
import shapely.ops
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from rasterio import features
from rasterio.transform import Affine
from shapely.affinity import translate
from shapely.geometry import shape as to_shape

from landloss.hazard.landslide.slope_elements import (
    BANK,
    CREST,
    FREE_FACE,
    OUTSIDE,
    SOIL_LIKE_CODE,
    TOE,
    SlopeElements,
    find_slope_elements,
)
from landloss.hazard.landslide.slope_polygons import (
    BETA_FACING_APART_DEG,
    BETA_SEGMENT_VOLUME_M3,
    EVACUATED,
    IMMINENT,
    INUNDATED,
    SEPARATE_CATCHMENTS,
    SlopePolygons,
    build_slope_polygons,
    polygon_geometries,
)
from landloss.hazard.landslide.synthetic_terrain import (
    ORIGIN_EASTING,
    ORIGIN_NORTHING,
    TOY_CASES,
    ToyTerrain,
    build_toy_case,
)
from scripts.landloss.hazard.landslide.research.slope_elements import config
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "slope-elements" / "fig"

# Colours: the first four slots of the reference categorical palette, in order.
INUNDATED_COLOUR = "#2a78d6"
FREE_FACE_COLOUR = "#eb6834"
BANK_COLOUR = "#1baf7a"
IMMINENT_COLOUR = "#eda100"
INK = "#0b0b0b"
MUTED = "#898781"
TYPE_COLOUR = {FREE_FACE: FREE_FACE_COLOUR, BANK: BANK_COLOUR}

# The plan's table, one line per case, for the figure titles.
EXPECTED = {
    "01": "One free-face; polygon the level-ground wedge, about 0.45 H on fill",
    "02": "A free-face with a bank stacked on it; the polygon takes the wall's "
    "width only, the bank linked by retrogression",
    "03_excavated_toe_4m": "The cut carries the MM6 flag, so the polygon runs "
    "to the bank's crest",
    "03_excavated_toe_2m": "The cut's width only, the bank linked by retrogression",
    "04": "The slope is under the grow angle, so not an element: the cut's width only",
    "05_terraces_narrow_bench": "Narrow bench: one stack",
    "05_terraces_wide_bench": "Wide bench: two separate polygons",
    "06": "Two elements in different catchments; their polygons may overlap at "
    "the ridge top and nowhere else",
    "07": "Where the crest lands; free-face or bank by its overall angle, not "
    "its peak cell",
    "08": "Where the toe lands",
    "09": "One element, cut into segments by volume (the check also accepts end "
    "pieces under 10 m where the cut fades out)",
    "10": "Three stacked elements (bank, wall, bank), not one bank",
    "11": "No element",
    "12_weak_rock_bank_3m": "A bank at 3 m (test angle 45 degrees)",
    "12_weak_rock_bank_12m": "A free-face at 12 m (test angle 34 degrees)",
    "13_soil_batter_37deg": "Added in D1: a free-face (test angle 35 degrees)",
    "13_soil_batter_33deg": "Added in D1: a bank (test angle 35 degrees)",
    "14_gullies_at_bent_ridge": "Added in D1: two gully heads under "
    "BETA_FACING_APART_DEG apart; disjoint catchments, kept by both under "
    "within_width, not separate_catchments",
    "15_undulating_hills": "Added in D1: no element — undulating hills stay "
    "under the grow angle",
}

# The rows this close to a profile case's north or south edge, in cells, are
# shaded on the plans: the 3 m slope and the 9 m step reach off the grid there,
# so what is drawn on them is the grid's edge, not the method.
EDGE_ROWS = 5


def expected_outcome(name):
    return EXPECTED.get(name, EXPECTED.get(name[:2], ""))


def figure_path(name):
    return FIG_DIR / f"toy-{name.replace('_', '-')}.png"


@dataclass(frozen=True)
class Run:
    terrain: ToyTerrain
    found: SlopeElements
    result: SlopePolygons
    elements_s: float
    polygons_s: float


def run_case(name, *, noise_sd_m, seed, fill_cases):
    terrain = build_toy_case(name, noise_sd_m=noise_sd_m, seed=seed)
    start = time.perf_counter()
    found = find_slope_elements(terrain.dem, terrain.ground_group, terrain.transform)
    middle = time.perf_counter()
    kwargs = {}
    if name[:2] in fill_cases:
        # The walls stand on fill; ground rising behind them is natural.
        kwargs["is_fill"] = found.elements["element_type"] == FREE_FACE
    result = build_slope_polygons(found, terrain.dem, terrain.transform, **kwargs)
    end = time.perf_counter()
    return Run(terrain, found, result, middle - start, end - middle)


# Reading the outcome -------------------------------------------------------
def element_x(found):
    return found.elements["centroid_x"] - ORIGIN_EASTING


def middle_rows(rows, n_rows):
    return (rows > 5) & (rows < n_rows - 6)


def edge_x(found, label, role):
    """The mean position of an element's crest or toe cells, metres east."""
    rows, cols = np.nonzero((found.labels == label) & ((found.edge_roles & role) > 0))
    keep = middle_rows(rows, found.labels.shape[0])
    return float(np.mean(cols[keep] + 0.5)) if keep.any() else np.nan


def zone(result, name, polygons=None):
    cells = result.cells[result.cells["zone"] == name]
    if polygons is not None:
        cells = cells[cells["polygon"].isin(list(polygons))]
    return cells


def polygons_of(result, label):
    return result.polygons.index[result.polygons["element"] == label]


def westmost_evacuated_x(run, label):
    """The median over the middle rows of the westmost evacuated cell, metres."""
    cells = zone(run.result, EVACUATED, polygons_of(run.result, label))
    cells = cells[middle_rows(cells["row"], run.found.labels.shape[0])]
    return float(cells.groupby("row")["col"].min().median() + 0.5)


def link(table, lower, upper, lower_column="lower", upper_column="upper"):
    match = table[(table[lower_column] == lower) & (table[upper_column] == upper)]
    return None if match.empty else match.iloc[0]


def retro(result, lower, upper):
    return link(
        result.retrogression_links,
        lower,
        upper,
        lower_column="lower_element",
        upper_column="upper_element",
    )


def of_type(found, kind):
    return found.elements[found.elements["element_type"] == kind]


def nearest(found, x_m):
    return int(element_x(found).sub(x_m).abs().idxmin())


# The expected outcomes, one check per case. Each returns (passed, detail).
def check_wall(run):
    elements = run.found.elements
    if len(elements) != 1:
        return False, f"{len(elements)} elements"
    element = elements.iloc[0]
    polygon = run.result.polygons.iloc[0]
    # The 0.89 m wedge is under a cell: the polygon is the wall's two cells.
    cells = zone(run.result, EVACUATED)
    cells = cells[middle_rows(cells["row"], run.found.labels.shape[0])]
    wall = run.terrain.features_x_m["wall"]
    passed = (
        element["element_type"] == FREE_FACE
        and abs(element["height_m"] - 2.0) <= 0.2
        and len(run.result.polygons) == 1
        and set(cells["col"] + 0.5) == {wall - 0.5, wall + 0.5}
    )
    return passed, (
        f"H {element['height_m']:.2f} m, width {polygon['width_behind_crest_m']:.2f}"
        " m, polygon the wall's two cells"
    )


def check_wall_rising_behind(run):
    found, features_x = run.found, run.terrain.features_x_m
    wall = nearest(found, features_x["wall"])
    above = of_type(found, BANK)
    above = above[element_x(found)[above.index] < features_x["wall"]]
    if found.elements.loc[wall, "element_type"] != FREE_FACE or len(above) != 1:
        return False, f"{len(above)} banks above the wall"
    bank = above.index[0]
    polygon = run.result.polygons.loc[polygons_of(run.result, wall)[0]]
    # Its own width behind its crest cell, to within a cell.
    reach = edge_x(found, wall, CREST) - polygon["width_behind_crest_m"] - 1.0
    passed = (
        link(found.stack_links, wall, bank) is not None
        and polygon["n_stack_elements"] == 0
        and westmost_evacuated_x(run, wall) >= reach
        and retro(run.result, wall, bank) is not None
    )
    return passed, (
        f"wall H {found.elements.loc[wall, 'height_m']:.2f} m, bank H "
        f"{found.elements.loc[bank, 'height_m']:.2f} m"
    )


def long_of_type(found, kind):
    """Elements of a kind running most of the profile, not noise fragments."""
    chosen = of_type(found, kind)
    return chosen[chosen["length_m"] > 20.0]


def _the_cut(run):
    cuts = long_of_type(run.found, FREE_FACE)
    return None if len(cuts) != 1 else cuts.index[0]


def check_cut_takes_the_bank(run):
    cut = _the_cut(run)
    if cut is None:
        return False, "not one free-face"
    element = run.found.elements.loc[cut]
    polygon = run.result.polygons.loc[polygons_of(run.result, cut)[0]]
    reach = westmost_evacuated_x(run, cut)
    passed = (
        bool(element["mm6_cut"])
        and polygon["n_stack_elements"] >= 1
        and reach <= run.terrain.features_x_m["bank_crest"] + 2.0
    )
    return passed, (
        f"cut H {element['height_m']:.2f} m at {element['overall_angle_deg']:.1f}"
        f" deg, MM6 {bool(element['mm6_cut'])}, polygon back to x {reach:.1f} m"
    )


def check_cut_width_only(run, *, needs_bank):
    cut = _the_cut(run)
    if cut is None:
        return False, "not one free-face"
    element = run.found.elements.loc[cut]
    polygon = run.result.polygons.loc[polygons_of(run.result, cut)[0]]
    reach = westmost_evacuated_x(run, cut)
    banks = long_of_type(run.found, BANK)
    if needs_bank:
        linked = len(banks) == 1 and retro(run.result, cut, banks.index[0]) is not None
        passed = not bool(element["mm6_cut"]) and linked
    else:
        passed = len(run.found.elements) == 1
    # Its own width behind its crest cell, to within a cell.
    limit = edge_x(run.found, cut, CREST) - polygon["width_behind_crest_m"] - 1.0
    passed = passed and polygon["n_stack_elements"] == 0 and reach >= limit
    return passed, (
        f"cut H {element['height_m']:.2f} m, MM6 {bool(element['mm6_cut'])}, "
        f"polygon back to x {reach:.1f} m, {len(banks)} banks"
    )


def check_narrow_bench(run):
    features_x = run.terrain.features_x_m
    cells = zone(run.result, EVACUATED)
    cells = cells[middle_rows(cells["row"], run.found.labels.shape[0])]
    x = cells["col"] + 0.5
    upper = set(cells.loc[(x - features_x["upper_wall"]).abs() < 1.0, "polygon"])
    lower = set(cells.loc[(x - features_x["lower_wall"]).abs() < 1.0, "polygon"])
    passed = len(run.result.polygons) == 1 and upper == lower and len(upper) == 1
    return passed, (
        f"{len(run.found.elements)} element(s), {len(run.result.polygons)} "
        "polygon(s) over both walls"
    )


def check_wide_bench(run):
    found, features_x = run.found, run.terrain.features_x_m
    faces = of_type(found, FREE_FACE)
    if len(faces) != 2:
        return False, f"{len(faces)} free-faces"
    upper = nearest(found, features_x["upper_wall"])
    lower = nearest(found, features_x["lower_wall"])
    joined = link(found.stack_links, lower, upper)
    passed = (
        len(run.result.polygons) == 2
        and run.result.overlaps.empty
        and retro(run.result, lower, upper) is not None
    )
    bench = np.nan if joined is None else joined["bench_width_m"]
    return passed, f"bench read {bench:.1f} m, {len(run.result.polygons)} polygons"


def check_gullies(run):
    ridge = run.terrain.features_x_m["ridge"]
    faces = of_type(run.found, FREE_FACE)
    sides = np.sign(element_x(run.found)[faces.index] - ridge)
    if len(faces) != 2 or sides.nunique() != 2:
        return False, f"{len(faces)} free-faces"
    # The two gully heads' polygons; any other element (a strip of gully floor
    # steepened by the noise) may share their ground within their width.
    heads = run.result.polygons.index[run.result.polygons["element"].isin(faces.index)]
    cells = zone(run.result, EVACUATED, heads)
    x = cells["col"] + 0.5
    away = (x - ridge).abs() > 2.0
    one_side = (
        cells[away].assign(east=x[away] > ridge).groupby("polygon")["east"].nunique()
    )
    shared = cells.groupby(["row", "col"])["polygon"].transform("nunique") > 1
    shared_x = x[shared]
    passed = bool((one_side == 1).all()) and bool(
        ((shared_x - ridge).abs() <= 2.0).all()
    )
    return passed, f"{int(shared.sum())} cell-polygon pairs on shared ground"


def check_gullies_at_bent_ridge(run):
    apex_northing = run.terrain.features_x_m["apex_northing_m"]
    faces = of_type(run.found, FREE_FACE)
    sides = np.sign(faces["centroid_y"] - apex_northing)
    if len(faces) != 2 or sides.nunique() != 2:
        return False, f"{len(faces)} free-faces"
    aspects = sorted(faces["aspect_deg"])
    apart = aspects[1] - aspects[0]
    disjoint = run.found.drainage_links.empty and set(
        np.unique(run.found.catchments[run.found.catchments > 0])
    ) == set(faces.index)
    overlaps = run.result.overlaps
    no_separate_catchments = not bool((overlaps["reason"] == SEPARATE_CATCHMENTS).any())
    passed = apart < BETA_FACING_APART_DEG and disjoint and no_separate_catchments
    return passed, (
        f"aspects {apart:.1f} deg apart, catchments disjoint {disjoint}, "
        f"overlap reasons {sorted(overlaps['reason'].unique())}"
    )


def check_crest(run):
    faces = of_type(run.found, FREE_FACE)
    if len(faces) != 1:
        return False, f"{len(faces)} free-faces"
    face = faces.index[0]
    element = faces.loc[face]
    crest = edge_x(run.found, face, CREST)
    target = run.terrain.features_x_m["at_30_deg"]
    passed = (
        abs(crest - target) <= 2.0
        and element["overall_angle_deg"] < element["slope_max_deg"]
        and element["overall_angle_deg"] > element["threshold_angle_deg"]
    )
    return passed, f"crest at x {crest:.1f} m (30 deg at {target:.1f} m)"


def check_toe(run):
    faces = of_type(run.found, FREE_FACE)
    if len(faces) != 1:
        return False, f"{len(faces)} free-faces"
    toe = edge_x(run.found, faces.index[0], TOE)
    target = run.terrain.features_x_m["at_30_deg"]
    return abs(toe - target) <= 2.0, f"toe at x {toe:.1f} m (30 deg at {target:.1f} m)"


def check_road_cut(run):
    long = run.found.elements[run.found.elements["length_m"] > 20.0]
    if len(long) != 1:
        return False, f"{len(long)} long elements"
    cut = long.iloc[0]
    segments = run.result.polygons[run.result.polygons["element"] == long.index[0]]
    segments = segments.sort_values("segment")
    others = run.found.elements.drop(index=long.index)
    # Segmented as its volume asks: every segment but the last holds the
    # segment volume, and the last no more than about that (one segment where
    # the whole cut holds less).
    volumes = segments["volume_m3"].to_numpy()
    by_volume = bool(
        (
            abs(volumes[:-1] - BETA_SEGMENT_VOLUME_M3) < 0.05 * BETA_SEGMENT_VOLUME_M3
        ).all()
        and volumes[-1] < 2.0 * BETA_SEGMENT_VOLUME_M3
    )
    passed = (
        cut["element_type"] == FREE_FACE
        and cut["length_m"] >= run.terrain.features_x_m["cut_length_m"]
        and by_volume
        and bool((segments["length_m"] >= cut["height_m"]).all())
        and bool((others["length_m"] < 10.0).all())
    )
    return passed, (
        f"cut {cut['length_m']:.0f} m long, {volumes.sum():.0f} m3 in "
        f"{len(segments)} segment(s), {len(others)} end pieces under 10 m"
    )


def check_wall_in_bank(run):
    found = run.found
    if len(found.elements) != 3:
        return False, f"{len(found.elements)} elements"
    above, wall, below = element_x(found).sort_values().index
    types = found.elements["element_type"]
    passed = (
        types[above] == BANK
        and types[wall] == FREE_FACE
        and types[below] == BANK
        and link(found.stack_links, wall, above) is not None
        and link(found.stack_links, below, wall) is not None
    )
    return passed, f"wall H {found.elements.loc[wall, 'height_m']:.2f} m"


def check_no_element(run):
    return run.found.elements.empty, f"{len(run.found.elements)} elements"


def check_batter(run, *, kind):
    elements = run.found.elements
    if len(elements) != 1:
        return False, f"{len(elements)} elements"
    element = elements.iloc[0]
    passed = element["element_type"] == kind and abs(element["height_m"] - 3.0) < 0.2
    return passed, (
        f"H {element['height_m']:.2f} m at {element['overall_angle_deg']:.1f} deg, "
        f"test {element['threshold_angle_deg']:g} deg"
    )


def check_weak_rock_bank(run, *, kind, threshold):
    elements = run.found.elements
    if len(elements) != 1:
        return False, f"{len(elements)} elements"
    element = elements.iloc[0]
    passed = (
        element["element_type"] == kind and element["threshold_angle_deg"] == threshold
    )
    return passed, (
        f"H {element['height_m']:.2f} m at {element['overall_angle_deg']:.1f} deg, "
        f"test {element['threshold_angle_deg']:g} deg"
    )


CHECKS: dict[str, Callable[[Run], tuple[bool, str]]] = {
    "01_wall": check_wall,
    "02_wall_rising_behind": check_wall_rising_behind,
    "03_excavated_toe_4m": check_cut_takes_the_bank,
    "03_excavated_toe_2m": lambda run: check_cut_width_only(run, needs_bank=True),
    "04_cut_under_gentle_slope": lambda run: check_cut_width_only(
        run, needs_bank=False
    ),
    "05_terraces_narrow_bench": check_narrow_bench,
    "05_terraces_wide_bench": check_wide_bench,
    "06_gullies_at_ridge": check_gullies,
    "07_convex_crest": check_crest,
    "08_concave_toe": check_toe,
    "09_road_cut": check_road_cut,
    "10_wall_in_bank": check_wall_in_bank,
    "11_small_step": check_no_element,
    "12_weak_rock_bank_3m": lambda run: check_weak_rock_bank(
        run, kind=BANK, threshold=45.0
    ),
    "12_weak_rock_bank_12m": lambda run: check_weak_rock_bank(
        run, kind=FREE_FACE, threshold=34.0
    ),
    "13_soil_batter_37deg": lambda run: check_batter(run, kind=FREE_FACE),
    "13_soil_batter_33deg": lambda run: check_batter(run, kind=BANK),
    "14_gullies_at_bent_ridge": check_gullies_at_bent_ridge,
    "15_undulating_hills": check_no_element,
}


# Drawing -------------------------------------------------------------------
def local_transform(terrain):
    """The grid's transform in metres from its south-west corner."""
    rows = terrain.dem.shape[0]
    return Affine(1.0, 0.0, 0.0, 0.0, -1.0, float(rows))


def to_local(geometry, terrain):
    rows = terrain.dem.shape[0]
    return translate(geometry, -ORIGIN_EASTING, -(ORIGIN_NORTHING - rows))


def element_shapes(run):
    labels = run.found.labels.astype(np.int32)
    pieces = [
        (int(value), to_shape(geometry))
        for geometry, value in features.shapes(
            labels, mask=labels > OUTSIDE, transform=local_transform(run.terrain)
        )
    ]
    if not pieces:
        return gpd.GeoDataFrame({"label": [], "element_type": []}, geometry=[])
    frame = pd.DataFrame(pieces, columns=["label", "geometry"])
    merged = frame.groupby("label")["geometry"].apply(shapely.union_all)
    types = run.found.elements["element_type"].reindex(merged.index)
    return gpd.GeoDataFrame(
        {"label": merged.index, "element_type": types.to_numpy()},
        geometry=merged.to_numpy(),
    )


def zone_shapes(run, name):
    shapes = polygon_geometries(run.result, zone=name, crs=None)
    shapes["geometry"] = [to_local(g, run.terrain) for g in shapes.geometry]
    return shapes


def contour_interval(dem, intervals, max_contours, *, noise_sd_m):
    """The smallest interval drawing no more than ``max_contours`` lines.

    The relief is read off the noise-free DEM, and on a noisy DEM the interval
    is at least four noise standard deviations, so the contours trace the
    ground rather than the noise.
    """
    relief = float(np.nanmax(dem) - np.nanmin(dem))
    for interval in intervals:
        if relief / interval <= max_contours and interval >= 4.0 * noise_sd_m:
            return interval
    return intervals[-1]


def plan_window(runs, margin_m):
    """The columns every run's elements and zones lie in, plus a margin."""
    cols = runs[0].terrain.dem.shape[1]
    first, last = cols, 0
    for run in runs:
        _, element_cols = np.nonzero(run.found.labels > OUTSIDE)
        zone_cols = run.result.cells["col"].to_numpy(dtype=int)
        every = np.concatenate([element_cols, zone_cols])
        if every.size:
            first = min(first, int(every.min()))
            last = max(last, int(every.max()) + 1)
    if first >= last:
        return 0.0, float(cols)
    return max(0.0, first - margin_m), min(float(cols), last + margin_m)


def hillshade(dem, *, azimuth_deg=315.0, altitude_deg=45.0):
    """The ground lit from the north-west, not stretched, so level ground is grey.

    Matplotlib's ``LightSource.hillshade`` stretches the light to the full
    range of each grid, which makes LiDAR-like noise on level ground look like
    relief; this keeps the plain cosine of the angle to the light.
    """
    east = np.gradient(dem, axis=1)
    north = -np.gradient(dem, axis=0)
    normal = np.stack([-east, -north, np.ones_like(dem)])
    normal /= np.linalg.norm(normal, axis=0)
    azimuth, altitude = np.radians(azimuth_deg), np.radians(altitude_deg)
    light = np.array(
        [
            np.sin(azimuth) * np.cos(altitude),
            np.cos(azimuth) * np.cos(altitude),
            np.sin(altitude),
        ]
    )
    return np.clip(np.tensordot(light, normal, axes=1), 0.0, 1.0)


def swap_axes(frame):
    """The geometries with east and north exchanged, for a plan drawn on its side."""
    frame = frame.copy()
    frame["geometry"] = [
        shapely.ops.transform(lambda x, y, z=None: (y, x), g) for g in frame.geometry
    ]
    return frame


def draw_plan(ax, run, *, interval, window, on_side):
    """Draw the plan; ``on_side`` puts north along the horizontal axis."""
    dem = run.terrain.dem
    rows, cols = dem.shape
    shade = hillshade(dem)
    orient = swap_axes if on_side else (lambda frame: frame)
    if on_side:
        # Column k of the turned image is row rows - 1 - k, so north grows to
        # the right; east grows upwards.
        ax.imshow(
            shade.T[:, ::-1],
            cmap="gray",
            extent=(0, rows, 0, cols),
            origin="lower",
            vmin=0,
            vmax=1,
        )
    else:
        ax.imshow(
            shade,
            cmap="gray",
            extent=(0, cols, 0, rows),
            origin="upper",
            vmin=0,
            vmax=1,
        )
    shapes = orient(element_shapes(run))
    for kind, colour in TYPE_COLOUR.items():
        chosen = shapes[shapes["element_type"] == kind]
        if not chosen.empty:
            chosen.plot(ax=ax, color=colour, alpha=0.7, edgecolor="white", lw=0.4)
    if not run.result.polygons.empty:
        imminent = orient(zone_shapes(run, IMMINENT))
        imminent.plot(
            ax=ax,
            facecolor=IMMINENT_COLOUR,
            alpha=0.45,
            edgecolor=IMMINENT_COLOUR,
            hatch="////",
            lw=0.5,
        )
        inundated = orient(zone_shapes(run, INUNDATED))
        if not inundated.empty:
            inundated.plot(ax=ax, color=INUNDATED_COLOUR, alpha=0.45, lw=0)
        evacuated = orient(zone_shapes(run, EVACUATED))
        evacuated.boundary.plot(ax=ax, color=INK, lw=1.3)
        for _, row in evacuated.iterrows():
            point = row.geometry.representative_point()
            ax.annotate(
                f"P{row['polygon']}",
                (point.x, point.y),
                fontsize=6,
                color=INK,
                ha="center",
                va="center",
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "alpha": 0.7},
            )
    levels = np.arange(
        np.floor(np.nanmin(dem) / interval) * interval,
        np.nanmax(dem) + interval,
        interval,
    )
    east = np.arange(cols) + 0.5
    north = rows - (np.arange(rows) + 0.5)
    section = rows - (section_row(run.terrain) + 0.5)
    if on_side:
        ax.contour(
            north[::-1],
            east,
            dem.T[:, ::-1],
            levels=levels,
            colors=MUTED,
            linewidths=0.4,
        )
        ax.plot([section, section], [0, cols], color=INK, lw=0.8, ls="--")
        ax.set_xlim(0, rows)
        ax.set_ylim(*window)
        ax.set_xlabel("Metres north of the grid's south edge")
        ax.set_ylabel("Metres east")
    else:
        ax.contour(east, north, dem, levels=levels, colors=MUTED, linewidths=0.4)
        ax.plot([0, cols], [section, section], color=INK, lw=0.8, ls="--")
        ax.set_xlim(*window)
        ax.set_ylim(0, rows)
        ax.set_xlabel("Metres east of the grid's west edge")
        ax.set_ylabel("Metres north")
    if run.terrain.profile is not None:
        shade_edge_rows(ax, rows, on_side=on_side)
    ax.set_aspect("equal")


def shade_edge_rows(ax, rows, *, on_side):
    """Grey out the rows by the north and south edges, where the grid's edge acts."""
    for start in (0, rows - EDGE_ROWS):
        north = rows - start - EDGE_ROWS
        if on_side:
            ax.axvspan(north, north + EDGE_ROWS, color="white", alpha=0.6, lw=0)
        else:
            ax.axhspan(north, north + EDGE_ROWS, color="white", alpha=0.6, lw=0)
    if not on_side:
        ax.text(
            0.5,
            rows - EDGE_ROWS / 2,
            "grid edge rows",
            fontsize=6,
            color=INK,
            va="center",
        )


def section_row(terrain):
    return terrain.dem.shape[0] // 2


def spans(mask):
    """The runs of True in a 1-D mask, as (first, last + 1) cell indices."""
    padded = np.concatenate([[False], mask, [False]])
    change = np.flatnonzero(np.diff(padded.astype(int)))
    return list(zip(change[::2], change[1::2], strict=True))


def draw_section(ax, run):
    dem = run.terrain.dem
    row = section_row(run.terrain)
    z = dem[row]
    cols = z.size
    centres = np.arange(cols) + 0.5
    ax.plot(centres, z, color=MUTED, lw=1.0)
    labels = run.found.labels[row]
    types = run.found.elements["element_type"]
    for label in np.unique(labels[labels > OUTSIDE]):
        for first, last in spans(labels == label):
            x = np.concatenate([[first], centres[first:last], [last]])
            ax.plot(
                x,
                np.interp(x, centres, z),
                color=TYPE_COLOUR[types[label]],
                lw=3.0,
                solid_capstyle="butt",
            )
            middle = (first + last) / 2
            ax.annotate(
                f"E{label}",
                (middle, np.interp(middle, centres, z)),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=6,
                color=INK,
            )
    z_low = float(np.nanmin(z))
    # The zone bars below the ground scale with the relief so they stay legible.
    relief = float(np.nanmax(z)) - z_low
    rug_height = max(0.5, 0.05 * relief)
    rug_gap = rug_height / 2
    on_row_all = run.result.cells[run.result.cells["row"] == section_row(run.terrain)]
    evacuated_depth = on_row_all.loc[on_row_all["zone"] == EVACUATED, "depth_m"]
    deepest = float(evacuated_depth.max()) if not evacuated_depth.empty else 0.0
    deepest = 0.0 if not np.isfinite(deepest) else deepest
    first_bar = z_low - deepest - rug_height - rug_gap
    cells = run.result.cells
    on_row = cells[cells["row"] == row]
    for depth_index, (name, colour) in enumerate(
        ((EVACUATED, INK), (IMMINENT, IMMINENT_COLOUR), (INUNDATED, INUNDATED_COLOUR))
    ):
        mask = np.zeros(cols, dtype=bool)
        mask[on_row.loc[on_row["zone"] == name, "col"].to_numpy(dtype=int)] = True
        bottom = first_bar - depth_index * (rug_height + rug_gap)
        ax.text(0.3, bottom + rug_height / 2, name, fontsize=6, color=INK, va="center")
        ax.broken_barh(
            [(first, last - first) for first, last in spans(mask)],
            (bottom, rug_height),
            facecolors=colour,
            alpha=0.8 if name == EVACUATED else 0.6,
        )
    # The evacuated ground drawn cell by cell to its depth: a free-face's own
    # ground to its slip plane, toe to the back of its width, and any other
    # ground to its element's depth (the deepest where polygons share a cell).
    evacuated = on_row[on_row["zone"] == EVACUATED]
    if not evacuated.empty:
        depth = np.zeros(cols)
        per_cell = np.nan_to_num(evacuated["depth_m"].to_numpy(dtype=float))
        np.maximum.at(depth, evacuated["col"].to_numpy(), per_cell)
        for first, last in spans(depth > 0):
            x = np.repeat(np.arange(first, last + 1), 2)[1:-1]
            top = np.interp(x, centres, z)
            base = top - np.repeat(depth[first:last], 2)
            ax.fill_between(x, base, top, color=INK, alpha=0.18, lw=0)
            ax.plot(x, base, color=INK, lw=0.6, ls=":")
    ax.set_xlim(0, cols)
    z_high = float(np.nanmax(z))
    bottom = first_bar - 2 * (rug_height + rug_gap)
    top = max(z_high + 1.0, bottom + 5.0)
    ax.set_ylim(bottom - 0.2, top)
    ax.set_aspect("equal")
    ax.set_xlabel("Metres east")
    ax.set_ylabel("Elevation (m)")
    ax.set_axisbelow(True)
    ax.grid(visible=True, color="#e6e5e1", lw=0.4)


def describe_elements(run):
    lines = []
    for label, element in run.found.elements.iterrows():
        lines.append(
            f"E{label} {element['element_type'].replace('_', '-')}: "
            f"H {element['height_m']:.2f} m, {element['overall_angle_deg']:.1f}°, "
            f"band {element['height_band']}, test {element['threshold_angle_deg']:g}°"
            + (", MM6" if element["mm6_cut"] else "")
        )
    return "\n".join(lines) if lines else "No element"


def legend_handles():
    return [
        Patch(facecolor=FREE_FACE_COLOUR, alpha=0.7, label="Free-face element"),
        Patch(facecolor=BANK_COLOUR, alpha=0.7, label="Bank element"),
        Patch(facecolor="none", edgecolor=INK, lw=1.3, label="Polygon (evacuated)"),
        Patch(
            facecolor=IMMINENT_COLOUR,
            alpha=0.45,
            hatch="////",
            edgecolor=IMMINENT_COLOUR,
            label="Imminent zone",
        ),
        Patch(facecolor=INUNDATED_COLOUR, alpha=0.45, label="Inundated zone"),
        Patch(facecolor=INK, alpha=0.18, label="Evacuated, to each cell's depth"),
        Line2D([], [], color=INK, ls="--", lw=0.8, label="Cross-section line"),
    ]


def draw_case(name, runs, outcomes, *, intervals, max_contours, noise_sd_m, seed):
    clean = runs[0].terrain
    rows = clean.dem.shape[0]
    window = plan_window(runs, margin_m=6.0)
    plan_aspect = rows / (window[1] - window[0])
    # A plan more than three times as long north to south as it is wide is
    # drawn on its side, the two plans one above the other.
    on_side = plan_aspect > 3.0
    section_height = 3.2
    if on_side:
        plan_height = max(1.5, 13.0 / plan_aspect)
        heights = [plan_height, plan_height, section_height, section_height]
        fig = plt.figure(figsize=(14, sum(heights) + 3.0))
        grid = fig.add_gridspec(4, 1, height_ratios=heights)
        plan_slots = [grid[0, 0], grid[1, 0]]
        section_slots = [grid[2, 0], grid[3, 0]]
    else:
        plan_height = min(8.0, max(3.0, 6.5 * plan_aspect))
        heights = [plan_height, section_height, section_height]
        fig = plt.figure(figsize=(14, sum(heights) + 2.4))
        grid = fig.add_gridspec(3, 2, height_ratios=heights)
        plan_slots = [grid[0, 0], grid[0, 1]]
        section_slots = [grid[1, :], grid[2, :]]
    titles = ("No noise", f"LiDAR-like noise, sd {noise_sd_m:g} m, seed {seed}")
    for column, (run, title, (passed, detail)) in enumerate(
        zip(runs, titles, outcomes, strict=True)
    ):
        interval = contour_interval(
            clean.dem,
            intervals,
            max_contours,
            noise_sd_m=noise_sd_m if column else 0.0,
        )
        plan = fig.add_subplot(plan_slots[column])
        draw_plan(plan, run, interval=interval, window=window, on_side=on_side)
        plan.set_title(
            f"{title}: plan{' (on its side)' if on_side else ''}, contours every "
            f"{interval:g} m",
            fontsize=9,
        )
        section = fig.add_subplot(section_slots[column])
        draw_section(section, run)
        verdict = "PASS" if passed else "FAIL"
        section.set_title(
            f"{title}: section along the dashed line, true scale "
            f"({verdict}: {detail})\n" + describe_elements(run),
            fontsize=8,
            loc="left",
        )
    fig.suptitle(
        f"Toy case {name}: {clean.description}\nExpected: {expected_outcome(name)}",
        fontsize=11,
    )
    fig.legend(
        handles=legend_handles(), loc="lower center", ncol=4, fontsize=8, frameon=False
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    path = figure_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def draw_overview(clean_runs, outcomes):
    names = list(clean_runs)
    n_cols = 3
    n_rows = int(np.ceil(len(names) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 3.2 * n_rows))
    for ax, name in zip(axes.flat, names, strict=False):
        draw_section(ax, clean_runs[name])
        passed, _ = outcomes[name]
        ax.set_title(f"{name} ({'PASS' if passed else 'FAIL'})", fontsize=9, loc="left")
        ax.set_xlabel("")
        ax.set_ylabel("")
    for ax in axes.flat[len(names) :]:
        ax.set_visible(False)
    fig.suptitle(
        "Toy cases, no noise: sections along each case's middle row, true scale. "
        "Bars below the ground: evacuated, imminent, inundated",
        fontsize=11,
    )
    fig.legend(
        handles=legend_handles()[:-1],
        loc="lower center",
        ncol=6,
        fontsize=8,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    path = FIG_DIR / "toy-overview.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# Tables for the findings document ------------------------------------------
def element_table(run):
    columns = [
        "element_type",
        "grown_in",
        "n_cells",
        "height_m",
        "overall_angle_deg",
        "slope_max_deg",
        "height_band",
        "threshold_angle_deg",
        "length_m",
        "aspect_deg",
        "mm6_cut",
    ]
    table = run.found.elements[columns].copy()
    table["x_m"] = element_x(run.found)
    return table.round(2)


def polygon_table(run):
    polygons = run.result.polygons
    if polygons.empty:
        return polygons
    row = section_row(run.terrain)
    cells = run.result.cells[run.result.cells["row"] == row]
    counts = cells.groupby(["polygon", "zone"]).size().unstack(fill_value=0)
    counts = counts.reindex(index=polygons.index, columns=list(ZONE_NAMES))
    table = polygons[
        [
            "element",
            "segment",
            "element_type",
            "width_rule",
            "width_behind_crest_m",
            "width_realised_m",
            "is_stack",
            "n_stack_elements",
            "base_height_m",
            "height_m",
            "length_m",
            "area_m2",
            "depth_m",
            "volume_m3",
            "reach_hl",
        ]
    ].copy()
    table["width_h"] = table["width_behind_crest_m"] / table["base_height_m"]
    for name in ZONE_NAMES:
        table[f"{name}_on_section_m"] = counts[name].fillna(0).to_numpy()
    return table.round(2)


ZONE_NAMES = (EVACUATED, IMMINENT, INUNDATED)


def speed_grid(tiles):
    base = TOY_CASES["10_wall_in_bank"]().dem
    pair = np.hstack([base, np.fliplr(base)])
    dem = np.tile(pair, tiles)
    terrain = TOY_CASES["10_wall_in_bank"]()
    groups = np.full(dem.shape, SOIL_LIKE_CODE, dtype=np.int8)
    start = time.perf_counter()
    found = find_slope_elements(dem, groups, terrain.transform)
    middle = time.perf_counter()
    result = build_slope_polygons(found, dem, terrain.transform)
    end = time.perf_counter()
    return (
        dem.shape,
        len(found.elements),
        len(result.polygons),
        middle - start,
        end - middle,
    )


def main(
    *,
    noise_sd_m,
    figure_seed,
    noise_seeds,
    fill_cases,
    contour_intervals_m,
    max_contours,
    speed_tiles,
):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    clean_runs = {}
    clean_outcomes = {}
    timings = []
    paths = []
    for name in TOY_CASES:
        runs = [
            run_case(name, noise_sd_m=0.0, seed=figure_seed, fill_cases=fill_cases),
            run_case(
                name, noise_sd_m=noise_sd_m, seed=figure_seed, fill_cases=fill_cases
            ),
        ]
        outcomes = [CHECKS[name](run) for run in runs]
        clean_runs[name] = runs[0]
        clean_outcomes[name] = outcomes[0]
        for label, run, (passed, detail) in zip(
            ("clean", f"noise seed {figure_seed}"), runs, outcomes, strict=True
        ):
            print(f"\n=== {name}, {label}: {'PASS' if passed else 'FAIL'} ({detail})")
            print(element_table(run).to_string())
            if not run.found.stack_links.empty:
                print("stack links\n" + run.found.stack_links.round(2).to_string())
            print(polygon_table(run).to_string())
            if not run.result.retrogression_links.empty:
                print(
                    "retrogression\n"
                    + run.result.retrogression_links.round(2).to_string()
                )
            if not run.result.overlaps.empty:
                print("overlaps\n" + run.result.overlaps.to_string())
        timings.append(
            {
                "case": name,
                "shape": runs[0].terrain.dem.shape,
                "elements_s": runs[0].elements_s,
                "polygons_s": runs[0].polygons_s,
            }
        )
        paths.append(
            draw_case(
                name,
                runs,
                outcomes,
                intervals=contour_intervals_m,
                max_contours=max_contours,
                noise_sd_m=noise_sd_m,
                seed=figure_seed,
            )
        )
    paths.append(draw_overview(clean_runs, clean_outcomes))

    print(f"\n=== Noise runs, sd {noise_sd_m:g} m, {len(noise_seeds)} seeds")
    noise_rows = []
    for name in TOY_CASES:
        results = []
        failures = []
        heights = []
        counts = []
        for seed in noise_seeds:
            run = run_case(
                name, noise_sd_m=noise_sd_m, seed=seed, fill_cases=fill_cases
            )
            passed, detail = CHECKS[name](run)
            results.append(passed)
            counts.append(len(run.found.elements))
            faces = of_type(run.found, FREE_FACE)
            if not faces.empty:
                heights.append(float(faces["height_m"].max()))
            if not passed:
                failures.append(f"seed {seed}: {detail}")
        noise_rows.append(
            {
                "case": name,
                "passed": f"{sum(results)}/{len(results)}",
                "elements": f"{min(counts)}-{max(counts)}",
                "tallest_free_face_m": (
                    f"{min(heights):.2f}-{max(heights):.2f}" if heights else "-"
                ),
                "first_failures": "; ".join(failures[:3]),
            }
        )
    print(pd.DataFrame(noise_rows).to_string(index=False))

    print("\n=== Timings, noise-free cases")
    print(pd.DataFrame(timings).round(3).to_string(index=False))
    shape, n_elements, n_polygons, elements_s, polygons_s = speed_grid(speed_tiles)
    print(
        f"Speed grid {shape}: {n_elements} elements in {elements_s:.2f} s, "
        f"{n_polygons} polygons in {polygons_s:.2f} s"
    )
    print("\nFigures:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main(
        noise_sd_m=config.NOISE_SD_M,
        figure_seed=config.FIGURE_SEED,
        noise_seeds=config.NOISE_SEEDS,
        fill_cases=config.FILL_CASES,
        contour_intervals_m=config.CONTOUR_INTERVALS_M,
        max_contours=config.MAX_CONTOURS,
        speed_tiles=config.SPEED_TILES,
    )
