"""Slope elements: free-faces and banks grown from seeds on the 1 m DEM.

A slope element is a piece of ground between a crest above it and a toe below
it, grown from one seed. Every element is either a **free-face**, steeper than
its ground can stand unsupported at its height (a retaining wall or an
unsupported oversteep cut), or a **bank**, ground under that angle. Elements
never overlap. This is phase 1 of
``.agents/plans/building-face-based-urban-slope-polygons.md``; the terms are
that plan's.

How an element is found, all of it whole-array numpy and scipy:

1. **Slopes and the fall line.** The 1 m slope is Horn's 3x3 slope on the DEM
   as it is. The 3 m slope is Horn's slope with its neighbours three cells
   away, on the DEM averaged over 3x3 cells, which is the slope of the 3 m
   grid landslide step 3 writes, evaluated at every 1 m cell. The downhill
   direction (the fall line) is read off the 3 m gradient, which is steadier
   on noisy LiDAR, and off the 1 m gradient where the 3 m one has none.
2. **Step height.** At every cell, the drop across 3 m along the fall line
   against the drop across 9 m, ``(3 x short - long) / 2``: the estimator
   :func:`landloss.exposure.rw.lines.step_height_m` uses for property
   boundaries, here as a raster. Zero on an even hillside, the height of a
   step at the cell, and negative values are read as zero.
3. **Each cell's threshold.** The cell's ground group (soil-like, weak rock,
   stronger rock; off the ground map, weak rock) and the height band its step
   height falls in give its slope threshold, ``STEP_ANGLE_DEG[group][band]``,
   from ``landslide-slope-thresholds.csv``. A cell with no step reads the first
   band. The band is only an estimate: the band that decides free-face or bank
   is measured on the grown element.
4. **Seeds.** A cell is eligible on either of two tests, a step or a slope: its
   step height is at least ``STEP_SEED_HEIGHT_M[group]``, or its 3 m slope is
   over its slope threshold (both in ``landslide-seed-thresholds.csv`` and
   ``landslide-slope-thresholds.csv``). Its
   exceedance, the 3 m slope less the threshold, is its priority. An eligible
   patch, one ground group's connected cells, is cut down to its 1 m
   footprint, the cells steep enough to grow into
   or holding at least :data:`BETA_SEED_STEP_SHARE` of the patch's largest
   step, because the 3 m slope and the 9 m step span spread a patch a few
   cells past the step it marks; each 4-connected piece left is a seed.
5. **Free-face pass.** The seeds grow by marker-controlled watershed on the
   negated exceedance (``scipy.ndimage.watershed_ift``), the strongest cell
   first, only into cells whose 1 m slope is over the seed's threshold less
   :data:`BETA_FREE_FACE_GROW_TOL_DEG`, and over the cell's own ground's
   limit; the seeds sharing a grow limit grow together, the strictest limit
   first, so no seed floods ground it could not keep. Each region then takes
   the rounded
   cells at its crest and toe, which Horn's kernel reads part way between the
   free-face and the ground beyond. Each grown region is measured, and a
   region that does not test as a free-face is released and the pass rerun
   without its seed, so the free-face pass keeps only free-faces and the bank
   ground they leave goes to the bank pass.
6. **Bank pass.** The cells left over with a 3 m and a 1 m slope of at least
   their ground group's ``BANK_SEED_SLOPE_DEG`` (:data:`BETA_GROW_ANGLE_DEG`,
   18.4 degrees, as shipped) seed, and grow the same way into unclaimed
   cells whose 1 m slope is at least that angle.
7. **Measurement.** Every region is measured on fall-line transects, one from
   each crest cell, between the breaks in slope at its ends rather than its
   end cells' centres (see :func:`_transects`): a face that falls across one
   interval between two cell centres, a wall, is read as vertical, because the
   DEM cannot resolve its run. A region under :data:`MIN_WALL_HEIGHT_M` high,
   shorter along the contour than :data:`BETA_MIN_ELEMENT_LENGTH_M`, or
   gentler overall than :data:`BETA_GROW_ANGLE_DEG`, is dropped (the free-face
   pass releases such regions to the bank pass). Each
   element is put once into one of the :data:`HEIGHT_BANDS_M` and tested
   against ``STEP_ANGLE_DEG`` on its overall angle: over it, a free-face;
   otherwise a bank, whichever pass grew it.

A crest cell is an element cell whose neighbour one cell uphill along the fall
line lies outside the element, a toe cell one whose neighbour downhill does,
and the other boundary cells are the element's ends along the slope. The plan
words this as the outside neighbour being higher or lower; on the level
ground at the top and foot of a wall the outside neighbours are the same
height, so the side is read off the fall line instead. Where the neighbour is
nodata, on its rim or off the grid, the edge of the survey stopped the
element, and the cell is an end, not a crest or a toe.

The element table (:attr:`SlopeElements.elements`) has one row per element,
indexed by its label in :attr:`SlopeElements.labels` (1 to n), with columns:

- ``grown_in``: ``"free_face_pass"`` or ``"bank_pass"``;
- ``element_type``: ``"free_face"`` or ``"bank"``, the step test's answer;
- ``n_cells``, ``area_m2``;
- ``height_m``: crest minus toe elevation, the median over fall-line
  transects, one from each crest cell, leaving out those cut short by nodata
  or the grid's edge where there are others; ``height_max_m`` the largest;
- ``run_m``: the horizontal distance crest to toe, median over transects,
  zero for a face the DEM reads as vertical;
- ``overall_angle_deg``: ``atan(height_m / run_m)``;
- ``n_transects``: the transects the two above are taken over;
- ``slope_mean_deg``, ``slope_max_deg``: the 1 m slope over the element;
- ``length_m``: the element's extent along the contour, square to its aspect;
- ``aspect_deg``: the circular mean downhill bearing, clockwise from north;
- ``step_peak_m``: the largest step height on the element;
- ``seed_exceedance_deg``: the seed's largest exceedance, as its own pass
  measured it: the 3 m slope less the step test angle for a free-face pass
  seed, less the bank seed slope for a bank pass seed;
- ``seed_row``, ``seed_col``: the seed's cell of largest exceedance, and
  ``seed_x``, ``seed_y`` its centre in map units, the same on every tile that
  holds the element;
- ``in_core``: whether the seed lies in the tile's core (see ``core``);
- ``touches_nodata``: the element reaches ground with no 1 m slope (nodata,
  its rim or the edge of the grid), so the survey's edge may have cut it;
- ``ground_group``: the majority ground group, as a :data:`GROUND_GROUPS` name;
- ``height_band``: 1 to :data:`N_HEIGHT_BANDS` (8 as shipped), from ``height_m``;
- ``threshold_angle_deg``: ``STEP_ANGLE_DEG`` for the group and band;
- ``angle_excess_deg``: ``overall_angle_deg`` less the threshold;
- ``stack_dominant_cut``: steeper than 50 degrees and higher than 3 m, the
  angle and height a cut is observed to fail at from MM6 shaking
  [brabhaharan_2018; hancox_2015]: a fixed geometric flag computed once from
  the element's own angle and height, never a read of a realisation's demand;
- ``hb1995_cut``: steeper than 45 degrees and higher than 5 m, high to very
  high susceptibility in closely jointed greywacke [hancox_brabhaharan_1995];
  both flags are geometry only, on banks as on free-faces, as the published
  criteria are (a 4 m stronger rock bank at 52 degrees carries
  ``stack_dominant_cut``); the stack rule reads ``stack_dominant_cut`` on
  free-faces only;
- ``own_catchment_area_m2``: the 3 m cells whose flow reaches this element
  before any other (see :attr:`SlopeElements.catchments`);
- ``centroid_x``, ``centroid_y``: the mean cell centre, in map units;
- one ``majority_<name>`` column per categorical grid passed in.

The DEM survey year (plan phase 0) is not carried yet: no DEM source mask
exists. Material, modification and ``ground_id`` come in as categorical grids
(``categories``) rasterised by the caller, for example with
:func:`rasterise_ground_map`.

Everything takes arrays and a transform and holds no state, so a tile of a
larger grid is processed the same way as a whole grid. Every element of a
tile is kept, its halo's too, with ``in_core`` saying whose it is, so the
links, the catchments and the polygons are built on the whole tile and only
the core's written out. An element longer along the contour than the halo is
wide (a long road cut across a seam) is still cut at the tile's edge.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from landloss.domain.constants import MIN_WALL_HEIGHT_M
from landloss.hazard.landslide.ground_map import MATERIALS
from landloss.io import ASSETS_DIR

# The three ground groups the step test reads, in the order of their integer
# codes on a ground group grid (0, 1, 2).
SOIL_LIKE = "soil_like"
WEAK_ROCK = "weak_rock"
STRONGER_ROCK = "stronger_rock"
GROUND_GROUPS = (SOIL_LIKE, WEAK_ROCK, STRONGER_ROCK)
SOIL_LIKE_CODE = GROUND_GROUPS.index(SOIL_LIKE)
WEAK_ROCK_CODE = GROUND_GROUPS.index(WEAK_ROCK)
STRONGER_ROCK_CODE = GROUND_GROUPS.index(STRONGER_ROCK)

# Ground off the ground map is tested as weak rock (the plan, phase 1).
OFF_MAP_GROUND_GROUP = WEAK_ROCK

# The ground map's materials in their groups (the plan's step test table).
# Crushed rock joins the soil-like group because NZGS Figure 35 has no row for
# it and Grant-Taylor reduces stable angles by 5 to 10 degrees for jointing,
# which takes the weak rock 45 degrees to about 35 [grant_taylor_1964;
# nzgs_2025_torlesse]. Unknown ground is weak rock, like ground off the map.
MATERIAL_GROUND_GROUP: dict[str, str] = {
    "rock": WEAK_ROCK,
    "rock_uw_mw": STRONGER_ROCK,
    "rock_hw_cw": WEAK_ROCK,
    "rock_crushed": SOIL_LIKE,
    "colluvium": SOIL_LIKE,
    "loess": SOIL_LIKE,
    "alluvium": SOIL_LIKE,
    "fill_engineered": SOIL_LIKE,
    "fill_uncontrolled": SOIL_LIKE,
    "reclamation": SOIL_LIKE,
    "unknown": WEAK_ROCK,
}

# Judgement, not a published stopping rule: ground under this slope is a bench,
# a platform or open gentle hillside, so an element gentler overall than this is
# dropped, and no bank seed may be set under it. 18.4 degrees (1V:3H) is the
# slope above which the Auckland Unitary Plan flags land on soils other than
# recent sediments as possibly unstable [de_vilder_2024] (devilder2024-F12),
# written as a screening slope; its use to stop growth is ours. Proposed in the
# plan, to be settled in stages D1 and D2. The bank pass seeds and grows at this
# slope by default, and the seed thresholds CSV can raise it per ground group.
BETA_GROW_ANGLE_DEG = 18.4

# The two threshold tables are packaged CSVs, so the numbers are edited in one
# visible place rather than found in code; assets/README.md says where each
# value came from. The files are read once, when this module is imported.
SEED_THRESHOLDS_PATH = ASSETS_DIR / "landslide-seed-thresholds.csv"
SLOPE_THRESHOLDS_PATH = ASSETS_DIR / "landslide-slope-thresholds.csv"


def load_seed_thresholds(
    path: Path = SEED_THRESHOLDS_PATH,
) -> tuple[dict[str, float], dict[str, float]]:
    """Read the seed thresholds of each ground group.

    Args:
        path: The CSV, with columns ``ground_group``, ``min_step_height_m`` and
            ``bank_min_slope_deg`` and one row per :data:`GROUND_GROUPS` name.

    Returns:
        ``(step_height_m, bank_slope_deg)``, each by group: the smallest step
        height, in metres, that makes a cell a free-face seed, and the least 3 m
        and 1 m slope, in degrees, that makes a cell a bank seed.

    Raises:
        ValueError: If a group is missing, repeated or unknown, a step height
            is missing or below :data:`MIN_WALL_HEIGHT_M` (an element lower
            than that is dropped anyway), or a bank slope is missing, over 90
            or below :data:`BETA_GROW_ANGLE_DEG` (an element gentler than that
            is dropped anyway).
    """
    table = pd.read_csv(path)
    columns = {"ground_group", "min_step_height_m", "bank_min_slope_deg"}
    if set(table.columns) != columns or sorted(table["ground_group"]) != sorted(
        GROUND_GROUPS
    ):
        msg = (
            f"{path.name} needs the columns {sorted(columns)} and one row for "
            f"each of {list(GROUND_GROUPS)}."
        )
        raise ValueError(msg)
    table = table.set_index("ground_group")
    heights = table["min_step_height_m"]
    if not (heights >= MIN_WALL_HEIGHT_M).all():
        msg = f"{path.name}: every step height must be at least {MIN_WALL_HEIGHT_M} m."
        raise ValueError(msg)
    slopes = table["bank_min_slope_deg"]
    if not ((slopes >= BETA_GROW_ANGLE_DEG) & (slopes <= 90)).all():
        msg = (
            f"{path.name}: every bank slope must be from {BETA_GROW_ANGLE_DEG} "
            "to 90 degrees."
        )
        raise ValueError(msg)
    return (
        {group: float(heights[group]) for group in GROUND_GROUPS},
        {group: float(slopes[group]) for group in GROUND_GROUPS},
    )


def load_slope_thresholds(
    path: Path = SLOPE_THRESHOLDS_PATH,
) -> tuple[tuple[float, ...], dict[str, tuple[float, ...]]]:
    """Read the height bands and the slope threshold of each ground group.

    Args:
        path: The CSV, one row per height band, with the columns
            ``height_from_m`` (the lower edge of the band) and one column of
            angles in degrees for each of :data:`GROUND_GROUPS`.

    Returns:
        ``(height_bands_m, angles)``: the lower edge of each band in metres,
        ascending, and for each group the steepest overall angle it stands
        unsupported at in each band. An element steeper than its entry is a
        free-face. Band k runs from its edge to the next; the last has no top.

    Raises:
        ValueError: If a column is missing or extra, the edges do not ascend or
            start under :data:`MIN_WALL_HEIGHT_M`, or an angle is not in
            (0, 90].
    """
    table = pd.read_csv(path)
    if set(table.columns) != {"height_from_m", *GROUND_GROUPS} or table.empty:
        msg = (
            f"{path.name} needs rows and the columns height_from_m and "
            f"{list(GROUND_GROUPS)}."
        )
        raise ValueError(msg)
    edges = table["height_from_m"]
    if (
        not edges.is_monotonic_increasing
        or edges.duplicated().any()
        or edges.iloc[0] < MIN_WALL_HEIGHT_M
    ):
        msg = (
            f"{path.name}: height_from_m must ascend from at least "
            f"{MIN_WALL_HEIGHT_M} m."
        )
        raise ValueError(msg)
    angles = table[list(GROUND_GROUPS)]
    if not ((angles > 0) & (angles <= 90)).all().all():
        msg = f"{path.name}: every angle must be above 0 and at most 90 degrees."
        raise ValueError(msg)
    return (
        tuple(float(edge) for edge in edges),
        {
            group: tuple(float(angle) for angle in angles[group])
            for group in GROUND_GROUPS
        },
    )


# The smallest step height, in metres, that makes a cell a free-face seed, and
# the least slope, in degrees, that makes it a bank seed, by ground group
# (landslide-seed-thresholds.csv).
STEP_SEED_HEIGHT_M, BANK_SEED_SLOPE_DEG = load_seed_thresholds()

# The lower edge of each height band, in metres, and the steepest overall angle,
# in degrees, each ground group stands unsupported at in each band
# (landslide-slope-thresholds.csv). The shipped bands are the plan's, phase 1,
# confirmed by the lead on 2026-10-02: MIN_WALL_HEIGHT_M and the small/medium
# costing break (0.5, 1.0); the Building Act consent exemption
# [nz_parliament_2004] and Anderson et al.'s classes [anderson_2015] (1.5, 2.5,
# 3.5); NZGS Figure 35 [nzgs_2025_torlesse] (6, 10, 16); above 16 m,
# Grant-Taylor's envelope [grant_taylor_1964]. The rock angles are NZGS Unit
# 7C.2 Figure 35, the maximum unsupported cut angles near Wellington housing
# [nzgs_2025_torlesse]: highly and completely weathered rock 1 on 1 to 10 m and
# 2 on 3 to 16 m, moderately weathered 4 on 3 to 6 m; the degree conversions are
# ours. The soil-like 35 degrees is judgement, a round number inside the
# published friction angles for this ground and at the floor of Figure 35
# [nzgs_2025_torlesse; brown_larkin_2005; monteith_2020; lyndsell_2019].
HEIGHT_BANDS_M, STEP_ANGLE_DEG = load_slope_thresholds()
N_HEIGHT_BANDS = len(HEIGHT_BANDS_M)

# Judgement: the free-face pass grows into cells whose 1 m slope is over the
# seed's threshold angle less this many degrees, so the rounded edge cells of a
# wall stay with it while a bank under the threshold above it does not.
# Proposed in the plan as 5 degrees; set to 3 in stage D1, because at 5 the
# soil-like grow limit is 30 degrees, the slope of the bank above the stage D1
# excavated toe (case 3), and under LiDAR-like noise the cut grew up into the
# bank in most draws (the stack-dominant flag held in 16 of 30, no free-face at
# all in 3);
# at 3 it held in 30 of 30 (toy_slope_elements.md). To be settled in stage D2.
BETA_FREE_FACE_GROW_TOL_DEG = 3.0

# Judgement: a fall across one interval between two cell centres is read as a
# step the DEM cannot resolve (a vertical wall) only where it is this many
# degrees steeper than the interval beyond each end. About two and a half
# times the scatter LiDAR-like noise of 0.05 m gives an interval's angle on a
# bank, so a break in slope the noise steepens is not taken for a wall, while
# a 0.5 m wall set in a 35 degree bank still clears it by 15 degrees.
BETA_STEP_MARGIN_DEG = 10.0

# Judgement: an element shorter than this along the contour, in metres, is not
# kept. The step estimator reads every break in slope steeper than about the
# grow angle as a step of at least MIN_WALL_HEIGHT_M (1.5 m times the gradient
# below it), so the crest and toe of every bank seed short pieces; the noise
# steepens a few of them past the step test, one to two cells long (stage D1
# cases 6 and 10). Three cells; to be settled in stage D2 against the mapped
# walls, the shortest of which a lot boundary sets.
BETA_MIN_ELEMENT_LENGTH_M = 3.0

# Judgement: the share of a seed patch's largest step height a cell must hold
# to stay in the seed when it is not steep enough to grow into. The step
# estimator reads the full height at the two cells either side of a sharp step
# and a quarter of it a cell further out, so a half keeps the step and drops
# the level ground beside it.
BETA_SEED_STEP_SHARE = 0.5

# Judgement: how far uphill of an element's crest the stack links look for the
# toe of the element above, in metres. Wider than any width behind a crest the
# plan's phase 3 rules give an element up to band 7 (1.4 H behind a vertical
# wall at 16 m is about 22 m).
BETA_STACK_SEARCH_M = 25.0

# Judgement: a walk uphill from a crest (the stack links here, the polygon
# rays of slope_polygons) has passed over a ridge or a hump once the ground
# falls this far, in metres, below the highest point it has crossed. The
# smallest element's height, so a fall no element could make is not a ridge.
BETA_RIDGE_DROP_M = MIN_WALL_HEIGHT_M

# Steeper than 50 degrees and higher than 3 m, the angle and height a cut is
# observed to fail at from MM6 shaking [brabhaharan_2018; hancox_2015]
# (brabhaharan2018-F03, sr2015-016-F05): evidence for a fixed geometric
# threshold. A flag on each element, computed once from its own angle and
# height, and the trigger of the phase 3 stack rule -- it must never be
# conditioned on a realisation's demand (named for what it does, not for the
# intensity that is its evidence; renamed from `MM6_CUT_*` 2026-10-03).
STACK_DOMINANT_ANGLE_DEG = 50.0
STACK_DOMINANT_HEIGHT_M = 3.0

# High to very high susceptibility in closely jointed greywacke: steeper than
# 45 degrees and higher than 5 m [hancox_brabhaharan_1995] (sr1995-005-F07).
HB1995_CUT_ANGLE_DEG = 45.0
HB1995_CUT_HEIGHT_M = 5.0

# The spans of the step estimator, in metres: the drop across 3 m (twice the
# near offset) against the drop across 9 m (twice the far offset), the spans
# landloss.exposure.rw.lines uses for property boundaries.
STEP_NEAR_M = 1.5
STEP_FAR_M = 3.0 * STEP_NEAR_M

# The span of the coarse slope, in metres: the 3 m slope that ranks the seeds.
COARSE_SLOPE_M = 3.0

# How far a fall-line transect or a stack search moves per sample, in cells.
# Half a cell, so a transect at an angle to the grid does not jump a cell.
WALK_STEP_CELLS = 0.5

# The names of the two passes and the two element types, as written to the
# element table.
FREE_FACE_PASS = "free_face_pass"
BANK_PASS = "bank_pass"
FREE_FACE = "free_face"
BANK = "bank"

# Bit flags on the edge role grid: a cell can be on the crest and the toe at
# once, where an element is one cell thick along its fall line.
CREST = 1
TOE = 2
END = 4

# The label of a cell outside every element.
OUTSIDE = 0

# The neighbourhood every label is connected over: cells sharing an edge.
FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)

# The integer cost range scipy's watershed_ift accepts (uint16). The top value
# is kept for the cells growth may not enter.
_COST_SCALE = 10.0
_BARRIER_COST = np.iinfo(np.uint16).max
_EXCEEDANCE_CAP_DEG = 90.0

# The most times the free-face pass is rerun after releasing the seeds that
# did not grow into a free-face.
_MAX_FREE_FACE_ROUNDS = 6

# A gradient smaller than this, in metres per metre, has no direction.
_LEVEL_GRADIENT = 1e-9

# The decimal places, in degrees, a seed's priority is read to when its peak
# cell is picked.
_SCORE_DECIMALS = 6

# Slopes are compared with this much slack in degrees, so ground built at
# exactly a limit angle reads the same whatever the floating point rounding.
_ANGLE_SLACK_DEG = 1e-6


@dataclass(frozen=True)
class TerrainLayers:
    """The per-cell layers the elements are grown from.

    Attributes:
        slope_fine_deg: Horn's slope on the DEM's own cells (the 1 m slope).
        slope_coarse_deg: Horn's slope over :data:`COARSE_SLOPE_M` (the 3 m
            slope), at every fine cell.
        downhill_row: The fall line's component along the rows (south on a
            north-up grid), a unit vector with ``downhill_col``. NaN where the
            ground has no downhill direction.
        downhill_col: The fall line's component along the columns (east).
        step_height_m: The step height at every cell, zero or more; NaN where
            the estimator reaches off the grid.
    """

    slope_fine_deg: NDArray[np.float64]
    slope_coarse_deg: NDArray[np.float64]
    downhill_row: NDArray[np.float64]
    downhill_col: NDArray[np.float64]
    step_height_m: NDArray[np.float64]


@dataclass(frozen=True)
class SlopeElements:
    """The slope elements found on one grid.

    Attributes:
        labels: The element label of every cell, :data:`OUTSIDE` off every
            element; labels run from 1 and index :attr:`elements`.
        edge_roles: Bit flags per cell, :data:`CREST`, :data:`TOE` and
            :data:`END`, zero inside an element and off it.
        elements: One row per element; the columns are listed in the module
            docstring.
        stack_links: One row per pair of elements where the toe of the upper
            meets the crest of the lower, directly or across a bench:
            ``lower``, ``upper``, ``bench_width_m`` (median over the crest
            cells that reach the upper element), ``bench_width_min_m``,
            ``n_transects`` and ``share_of_crest`` (of the lower's crest
            cells).
        catchments: On the coarse grid, the label of the first element each
            cell's D8 flow reaches (itself for an element cell), or
            :data:`OUTSIDE` where it reaches none.
        catchment_transform: The coarse grid's affine transform.
        drainage_links: One row per pair where cells of ``upper`` flow
            straight on into ``lower``, with ``n_cells``. With
            :attr:`catchments` this gives each element's whole upslope
            catchment: its own cells plus those of every element draining
            into it.
        layers: The per-cell layers the elements were grown from.
    """

    labels: NDArray[np.int32]
    edge_roles: NDArray[np.uint8]
    elements: pd.DataFrame
    stack_links: pd.DataFrame
    catchments: NDArray[np.int32]
    catchment_transform: Affine
    drainage_links: pd.DataFrame
    layers: TerrainLayers


def ground_group_codes(materials: ArrayLike) -> NDArray[np.int8]:
    """Map ground map materials onto ground group codes.

    Args:
        materials: Material names from :data:`MATERIALS`; None or NaN is ground
            off the map.

    Returns:
        The code of each material's group, the index into
        :data:`GROUND_GROUPS`. Off-map ground takes
        :data:`OFF_MAP_GROUND_GROUP`.

    Raises:
        ValueError: If a material is not one the ground map writes.
    """
    values = pd.Series(np.asarray(materials, dtype=object).ravel())
    known = values.isna() | values.isin(MATERIALS)
    if not known.all():
        unknown = sorted({str(value) for value in values[~known]})
        msg = f"These materials are not ground map materials: {unknown}."
        raise ValueError(msg)

    codes = {
        name: GROUND_GROUPS.index(group)
        for name, group in MATERIAL_GROUND_GROUP.items()
    }
    mapped = values.map(codes).fillna(GROUND_GROUPS.index(OFF_MAP_GROUND_GROUP))
    shape = np.shape(np.asarray(materials, dtype=object))
    return mapped.to_numpy(dtype=np.int8).reshape(shape)


def height_band(height_m: ArrayLike) -> NDArray[np.int8]:
    """Put heights into the height bands.

    Args:
        height_m: Heights in metres.

    Returns:
        The band of each height, 1 to :data:`N_HEIGHT_BANDS`, and 0 for a height
        under the first band's lower edge or NaN. A height on a break falls in
        the band above it.
    """
    heights = np.asarray(height_m, dtype=float)
    bands = np.searchsorted(np.asarray(HEIGHT_BANDS_M), heights, side="right")
    bands = np.where(np.isfinite(heights), bands, 0)
    return bands.astype(np.int8)


def step_angle_deg(group: ArrayLike, band: ArrayLike) -> NDArray[np.float64]:
    """Look up the step test angle for ground groups and height bands.

    Args:
        group: Ground group codes, indices into :data:`GROUND_GROUPS`.
        band: Height bands, 1 to :data:`N_HEIGHT_BANDS`; a band of 0 (under the
            first band's edge) reads band 1, so a cell's estimate always has a
            threshold.

    Returns:
        The angle in degrees, broadcast over the two inputs.
    """
    table = np.array([STEP_ANGLE_DEG[name] for name in GROUND_GROUPS], dtype=float)
    groups = np.asarray(group, dtype=np.intp)
    columns = np.clip(np.asarray(band, dtype=np.intp), 1, N_HEIGHT_BANDS) - 1
    return table[groups, columns]


def step_seed_height_m(group: ArrayLike) -> NDArray[np.float64]:
    """Look up the step height that makes a cell a seed, by ground group.

    Args:
        group: Ground group codes, indices into :data:`GROUND_GROUPS`.

    Returns:
        The height in metres from :data:`STEP_SEED_HEIGHT_M`, shaped as ``group``.
    """
    heights = np.array([STEP_SEED_HEIGHT_M[name] for name in GROUND_GROUPS])
    return heights[np.asarray(group, dtype=np.intp)]


def bank_seed_slope_deg(group: ArrayLike) -> NDArray[np.float64]:
    """Look up the slope that makes a cell a bank seed, by ground group.

    Args:
        group: Ground group codes, indices into :data:`GROUND_GROUPS`.

    Returns:
        The angle in degrees from :data:`BANK_SEED_SLOPE_DEG`, shaped as
        ``group``.
    """
    angles = np.array([BANK_SEED_SLOPE_DEG[name] for name in GROUND_GROUPS])
    return angles[np.asarray(group, dtype=np.intp)]


def _horn_gradient(
    elevation: NDArray[np.float64], cell_size_m: float, span_cells: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Horn's gradient with its neighbours ``span_cells`` away, in array axes.

    Returns:
        ``(rise_along_rows, rise_along_cols)`` in metres per metre; NaN on the
        border the kernel does not fit and where the centre cell is NaN.
    """
    rows, cols = elevation.shape
    s = span_cells
    along_rows = np.full(elevation.shape, np.nan)
    along_cols = np.full(elevation.shape, np.nan)
    if rows <= 2 * s or cols <= 2 * s:
        return along_rows, along_cols

    def shifted(d_row: int, d_col: int) -> NDArray[np.float64]:
        return elevation[
            s + d_row * s : rows - s + d_row * s, s + d_col * s : cols - s + d_col * s
        ]

    across_cols = (shifted(-1, 1) + 2 * shifted(0, 1) + shifted(1, 1)) - (
        shifted(-1, -1) + 2 * shifted(0, -1) + shifted(1, -1)
    )
    across_rows = (shifted(1, -1) + 2 * shifted(1, 0) + shifted(1, 1)) - (
        shifted(-1, -1) + 2 * shifted(-1, 0) + shifted(-1, 1)
    )
    run = 8.0 * s * cell_size_m
    hole = np.isnan(shifted(0, 0))
    along_rows[s:-s, s:-s] = np.where(hole, np.nan, across_rows / run)
    along_cols[s:-s, s:-s] = np.where(hole, np.nan, across_cols / run)
    return along_rows, along_cols


def _window_mean(elevation: NDArray[np.float64], size: int) -> NDArray[np.float64]:
    """Mean over a ``size`` square window, NaN wherever the window is not full."""
    valid = np.isfinite(elevation)
    filled = np.where(valid, elevation, 0.0)
    total = ndimage.uniform_filter(filled, size=size, mode="constant", cval=0.0)
    share = ndimage.uniform_filter(valid.astype(float), size=size, mode="constant")
    return np.where(share > 1.0 - 1e-9, total, np.nan)


def _slope_from(
    along_rows: NDArray[np.float64], along_cols: NDArray[np.float64]
) -> NDArray[np.float64]:
    return np.degrees(np.arctan(np.hypot(along_rows, along_cols)))


def step_height_raster(
    dem: NDArray[np.float64],
    downhill_row: NDArray[np.float64],
    downhill_col: NDArray[np.float64],
    cell_size_m: float,
) -> NDArray[np.float64]:
    """Measure the step the ground makes at every cell, along the fall line.

    The drop across 3 m (``short``, from 1.5 m uphill to 1.5 m downhill)
    against the drop across 9 m (``long``), ``(3 x short - long) / 2``, with the
    DEM read by bilinear interpolation: zero on an even hillside, ``H`` at a
    step of height ``H`` in it, and a quarter of ``H`` a cell or so either side.
    It also reads a break in slope as a step, up to 1.5 m times the gradient
    below the break, 1.5 m in from it.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        downhill_row: The fall line's row component (a unit vector with
            ``downhill_col``), NaN where there is none.
        downhill_col: The fall line's column component.
        cell_size_m: The cell size in metres.

    Returns:
        The step height in metres, zero where the drop is no more than the
        hillside's (a negative reading is not a step), zero where there is no
        fall line or either span rises along it, and NaN where a span reaches
        off the grid or into nodata.
    """
    rows, cols = np.indices(dem.shape, dtype=float)
    has_direction = np.isfinite(downhill_row) & np.isfinite(downhill_col)
    d_row = np.where(has_direction, downhill_row, 0.0)
    d_col = np.where(has_direction, downhill_col, 0.0)

    def drop(offset_m: float) -> NDArray[np.float64]:
        offset = offset_m / cell_size_m
        uphill = ndimage.map_coordinates(
            dem,
            [rows - offset * d_row, cols - offset * d_col],
            order=1,
            mode="constant",
            cval=np.nan,
        )
        downhill = ndimage.map_coordinates(
            dem,
            [rows + offset * d_row, cols + offset * d_col],
            order=1,
            mode="constant",
            cval=np.nan,
        )
        return uphill - downhill

    short = drop(STEP_NEAR_M)
    long = drop(STEP_FAR_M)
    step = np.maximum((3.0 * short - long) / 2.0, 0.0)
    # Both spans have to fall along the fall line. On level ground the fall
    # line is the noise's, and pointed away from a wall a few metres off it
    # reads the wall as a rise across 9 m and half its height as a step.
    with np.errstate(invalid="ignore"):
        falls = (short > 0) & (long > 0)
    step = np.where(has_direction & falls, step, 0.0)
    return np.where(np.isfinite(short) & np.isfinite(long), step, np.nan)


def terrain_layers(dem: NDArray[np.float64], cell_size_m: float) -> TerrainLayers:
    """Compute the slopes, the fall line and the step height of a DEM.

    Args:
        dem: Ground elevation in metres on a north-up grid, NaN for nodata.
        cell_size_m: The cell size in metres.

    Returns:
        The layers, on the grid of ``dem``.

    Raises:
        ValueError: If the cell size is not positive or is over the coarse
            slope's span.
    """
    if cell_size_m <= 0 or cell_size_m > COARSE_SLOPE_M:
        msg = (
            f"The cell size has to be positive and no more than {COARSE_SLOPE_M} m, "
            f"but {cell_size_m} was given."
        )
        raise ValueError(msg)
    elevation = np.asarray(dem, dtype=float)
    span = max(round(COARSE_SLOPE_M / cell_size_m), 1)

    fine_rows, fine_cols = _horn_gradient(elevation, cell_size_m, 1)
    smooth = _window_mean(elevation, span) if span > 1 else elevation
    coarse_rows, coarse_cols = _horn_gradient(smooth, cell_size_m, span)

    coarse_size = np.hypot(coarse_rows, coarse_cols)
    use_coarse = np.isfinite(coarse_size) & (coarse_size > _LEVEL_GRADIENT)
    grad_rows = np.where(use_coarse, coarse_rows, fine_rows)
    grad_cols = np.where(use_coarse, coarse_cols, fine_cols)
    size = np.hypot(grad_rows, grad_cols)
    with np.errstate(invalid="ignore", divide="ignore"):
        has_direction = np.isfinite(size) & (size > _LEVEL_GRADIENT)
        downhill_row = np.where(has_direction, -grad_rows / size, np.nan)
        downhill_col = np.where(has_direction, -grad_cols / size, np.nan)

    return TerrainLayers(
        slope_fine_deg=_slope_from(fine_rows, fine_cols),
        slope_coarse_deg=_slope_from(coarse_rows, coarse_cols),
        downhill_row=downhill_row,
        downhill_col=downhill_col,
        step_height_m=step_height_raster(
            elevation, downhill_row, downhill_col, cell_size_m
        ),
    )


def _cell_size(transform: Affine) -> float:
    """The square cell size of a north-up transform."""
    if transform.b != 0 or transform.d != 0 or transform.e >= 0:
        msg = "The grid has to be north-up with no rotation."
        raise ValueError(msg)
    if not math.isclose(transform.a, -transform.e):
        msg = f"The cells have to be square, not {transform.a} by {-transform.e}."
        raise ValueError(msg)
    return float(transform.a)


def _neighbour(
    labels: NDArray[np.int32],
    rows: NDArray[np.intp],
    cols: NDArray[np.intp],
    d_row: NDArray[np.intp],
    d_col: NDArray[np.intp],
) -> NDArray[np.int32]:
    """The label of the cell at an offset from each cell, OUTSIDE off the grid."""
    target_rows = rows + d_row
    target_cols = cols + d_col
    inside = (
        (target_rows >= 0)
        & (target_rows < labels.shape[0])
        & (target_cols >= 0)
        & (target_cols < labels.shape[1])
    )
    found = np.full(rows.shape, OUTSIDE, dtype=np.int32)
    found[inside] = labels[target_rows[inside], target_cols[inside]]
    return found


def _measured_ground(
    layers: TerrainLayers, rows: NDArray[np.intp], cols: NDArray[np.intp]
) -> NDArray[np.bool_]:
    """Whether each cell is on the grid and has a 1 m slope (not nodata's edge)."""
    shape = layers.slope_fine_deg.shape
    inside = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
    found = np.zeros(rows.shape, dtype=bool)
    found[inside] = np.isfinite(layers.slope_fine_deg[rows[inside], cols[inside]])
    return found


def _edge_roles(labels: NDArray[np.int32], layers: TerrainLayers) -> NDArray[np.uint8]:
    """Mark each element's crest, toe and end cells.

    A boundary cell is on the crest or the toe only where the cell beyond it
    along the fall line is measured ground: on the grid and with a 1 m slope.
    Where it is nodata, its rim (where Horn's kernel reaches nodata) or off the
    grid, the element was stopped by the edge of the survey, not by the
    ground, and the cell is one of the element's ends.
    """
    roles = np.zeros(labels.shape, dtype=np.uint8)
    rows, cols = np.nonzero(labels > OUTSIDE)
    own = labels[rows, cols]
    d_row = layers.downhill_row[rows, cols]
    d_col = layers.downhill_col[rows, cols]
    has_direction = np.isfinite(d_row) & np.isfinite(d_col)
    step_rows = np.rint(np.where(has_direction, d_row, 0.0)).astype(np.intp)
    step_cols = np.rint(np.where(has_direction, d_col, 0.0)).astype(np.intp)

    uphill = _neighbour(labels, rows, cols, -step_rows, -step_cols)
    downhill = _neighbour(labels, rows, cols, step_rows, step_cols)
    above_measured = _measured_ground(layers, rows - step_rows, cols - step_cols)
    below_measured = _measured_ground(layers, rows + step_rows, cols + step_cols)
    crest = has_direction & (uphill != own) & above_measured
    toe = has_direction & (downhill != own) & below_measured

    boundary = np.zeros(rows.shape, dtype=bool)
    for d_r, d_c in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        offset_r = np.full(rows.shape, d_r, dtype=np.intp)
        offset_c = np.full(rows.shape, d_c, dtype=np.intp)
        boundary |= _neighbour(labels, rows, cols, offset_r, offset_c) != own
    end = boundary & ~crest & ~toe

    flags = crest * CREST + toe * TOE + end * END
    roles[rows, cols] = flags.astype(np.uint8)
    return roles


# How many distinct cells a transect reads beyond each end of its element: the
# outside neighbour, and the one beyond that for the gradient of the ground
# there.
_CELLS_BEYOND = 2

# How many distinct cells a transect keeps from each end of its element: the
# end cell, the next one in and the one after, enough to trim one gentle cell
# off each end and still read the face's gradient inside it.
_CELLS_KEPT = 3

# A cell on a fall-line walk, as (rows, columns) arrays; -1 where there is none.
_Cells = tuple[NDArray[np.intp], NDArray[np.intp]]


@dataclass(frozen=True)
class _Trace:
    """The distinct cells walks along the fall line crossed, -1 where none.

    Attributes:
        head_rows: The first :data:`_CELLS_KEPT` cells of each walk's own label,
            the start first, shape ``(n, 3)``; ``head_cols`` alike.
        head_cols: Their columns.
        tail_rows: The last :data:`_CELLS_KEPT` cells of its own label, the
            last at index 2.
        tail_cols: Their columns.
        count: How many distinct cells of its own label each walk crossed.
        beyond_rows: The first :data:`_CELLS_BEYOND` distinct cells after the
            walk left its own label, -1 off the grid.
        beyond_cols: Their columns.
    """

    head_rows: NDArray[np.intp]
    head_cols: NDArray[np.intp]
    tail_rows: NDArray[np.intp]
    tail_cols: NDArray[np.intp]
    count: NDArray[np.intp]
    beyond_rows: NDArray[np.intp]
    beyond_cols: NDArray[np.intp]


def _trace(
    labels: NDArray[np.int32],
    start_rows: NDArray[np.intp],
    start_cols: NDArray[np.intp],
    d_row: NDArray[np.float64],
    d_col: NDArray[np.float64],
    *,
    leave_at_once: bool = False,
) -> _Trace:
    """Walk from cells along a direction, through their own label and beyond.

    With ``leave_at_once`` every cell after the start counts as beyond, so the
    walk reads the ground outside the start cell whatever its label.
    """
    n = start_rows.size
    shape = labels.shape
    own = labels[start_rows, start_cols]
    head_rows = np.full((n, _CELLS_KEPT), -1, dtype=np.intp)
    head_cols = np.full((n, _CELLS_KEPT), -1, dtype=np.intp)
    tail_rows = np.full((n, _CELLS_KEPT), -1, dtype=np.intp)
    tail_cols = np.full((n, _CELLS_KEPT), -1, dtype=np.intp)
    head_rows[:, 0], head_cols[:, 0] = start_rows, start_cols
    tail_rows[:, -1], tail_cols[:, -1] = start_rows, start_cols
    count = np.ones(n, dtype=np.intp)
    beyond_rows = np.full((n, _CELLS_BEYOND), -1, dtype=np.intp)
    beyond_cols = np.full((n, _CELLS_BEYOND), -1, dtype=np.intp)
    n_beyond = np.zeros(n, dtype=np.intp)
    on_label = np.full(n, not leave_at_once)
    last_rows = start_rows.astype(np.intp)
    last_cols = start_cols.astype(np.intp)
    active = np.ones(n, dtype=bool)
    max_steps = int(2 * (shape[0] + shape[1]) / WALK_STEP_CELLS)
    for k in range(1, max_steps + 1):
        index = np.nonzero(active)[0]
        if index.size == 0:
            break
        r = np.rint(start_rows[index] + k * WALK_STEP_CELLS * d_row[index])
        c = np.rint(start_cols[index] + k * WALK_STEP_CELLS * d_col[index])
        r = r.astype(np.intp)
        c = c.astype(np.intp)
        moved = (r != last_rows[index]) | (c != last_cols[index])
        index, r, c = index[moved], r[moved], c[moved]
        if index.size == 0:
            continue
        last_rows[index], last_cols[index] = r, c
        inside = (r >= 0) & (r < shape[0]) & (c >= 0) & (c < shape[1])
        found = np.full(index.shape, OUTSIDE, dtype=np.int32)
        found[inside] = labels[r[inside], c[inside]]
        stays = on_label[index] & inside & (found == own[index])

        kept = index[stays]
        count[kept] += 1
        slot = count[kept] - 1
        early = slot < _CELLS_KEPT
        head_rows[kept[early], slot[early]] = r[stays][early]
        head_cols[kept[early], slot[early]] = c[stays][early]
        tail_rows[kept, :-1] = tail_rows[kept, 1:]
        tail_cols[kept, :-1] = tail_cols[kept, 1:]
        tail_rows[kept, -1] = r[stays]
        tail_cols[kept, -1] = c[stays]

        left = index[~stays]
        on_label[left] = False
        on_grid = inside[~stays]
        slot = n_beyond[left]
        beyond_rows[left[on_grid], slot[on_grid]] = r[~stays][on_grid]
        beyond_cols[left[on_grid], slot[on_grid]] = c[~stays][on_grid]
        n_beyond[left] += 1
        active[left[~on_grid | (n_beyond[left] >= _CELLS_BEYOND)]] = False
    return _Trace(
        head_rows=head_rows,
        head_cols=head_cols,
        tail_rows=tail_rows,
        tail_cols=tail_cols,
        count=count,
        beyond_rows=beyond_rows,
        beyond_cols=beyond_cols,
    )


def _elevation(dem: NDArray[np.float64], cell: _Cells) -> NDArray[np.float64]:
    """The DEM at cells, NaN where a cell is missing (-1)."""
    rows, cols = cell
    found = (rows >= 0) & (cols >= 0)
    z = np.full(rows.shape, np.nan)
    z[found] = dem[rows[found], cols[found]]
    return z


def _distance(a: _Cells, b: _Cells, cell_size_m: float) -> NDArray[np.float64]:
    """The horizontal distance between cell centres, NaN where one is missing."""
    found = (a[0] >= 0) & (b[0] >= 0)
    gap = np.hypot(a[0] - b[0], a[1] - b[1]) * cell_size_m
    return np.where(found, gap, np.nan)


def _gradient(
    dem: NDArray[np.float64], a: _Cells, b: _Cells, cell_size_m: float
) -> NDArray[np.float64]:
    """The fall from cell ``a`` to cell ``b`` per metre between them."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (_elevation(dem, a) - _elevation(dem, b)) / _distance(a, b, cell_size_m)


def _end_correction(
    dem: NDArray[np.float64],
    cells: tuple[_Cells, _Cells, _Cells, _Cells],
    face: NDArray[np.float64],
    cell_size_m: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Move one end of each transect from its end cell's centre to the break.

    ``cells`` is ``(far, beyond, end, inward)``, in order towards the element:
    the two cells outside the end, the end cell and the next one in. The
    ground outside is read as a straight line at the gradient between the two
    outside cells, the element as a straight face falling at ``face`` (metres
    per metre), and the break is where the two meet. Where it lies outside the
    end cell (a bank's first steep cell sits inside its crest) the face is
    lengthened to it; where it lies inside (a free-face's rounded edge cell
    stands on the ground beyond) the outside ground is cut back to it. Exact
    on ground made of straight pieces.

    Returns:
        ``(run_m, rise_m)``: what the end adds to the transect's run and to its
        height, zero where any cell is missing or the face is no steeper than
        the ground outside.
    """
    far, beyond, end, inward = cells
    outside = _gradient(dem, far, beyond, cell_size_m)
    across = _gradient(dem, beyond, end, cell_size_m)
    within = _gradient(dem, end, inward, cell_size_m)
    out_m = _distance(beyond, end, cell_size_m)
    in_m = _distance(end, inward, cell_size_m)
    span = face - outside
    with np.errstate(invalid="ignore", divide="ignore"):
        steeper = span > _LEVEL_GRADIENT
        on_face = np.clip((across - outside) / span, 0.0, 1.0)
        off_face = np.clip((face - within) / span, 0.0, 1.0)
    on_face = np.where(steeper, np.nan_to_num(on_face), 0.0)
    off_face = np.where(steeper, np.nan_to_num(off_face), 0.0)
    run = np.nan_to_num(on_face * out_m) - np.nan_to_num(off_face * in_m)
    rise = np.nan_to_num(on_face * out_m * face) - np.nan_to_num(
        off_face * in_m * outside
    )
    return run, rise


def _transects(
    labels: NDArray[np.int32],
    dem: NDArray[np.float64],
    roles: NDArray[np.uint8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> pd.DataFrame:
    """One fall-line transect from every crest cell to where it leaves its element.

    A transect's height and run are measured between the breaks in slope at
    its two ends, not between the centres of its end cells, which on a 1 m
    grid sit up to a cell either side of the break:

    1. An end interval gentler than :data:`BETA_GROW_ANGLE_DEG` (a cell of
       level ground the step estimator spread the element onto, beside a wall
       at an angle to the grid) is trimmed off.
    2. Where what is left falls across one interval between two cell centres,
       more steeply by :data:`BETA_STEP_MARGIN_DEG` than the interval
       beyond each end, the DEM cannot tell how steep the face is: it is a
       step, read as vertical, half
       way between them (run 0), and its height is the fall between the two
       less the fall of the ground outside over each half interval (a wall set
       in a bank), plus any fall the interval next to an end makes beyond the
       ground's (a face that runs on past the cell). One interval that is
       not a step (a piece of an even bank) is measured between its cell
       centres.
    3. Otherwise the face's gradient is read inside the element, between the
       cells next to each end (or the steeper of the two intervals of a
       three-cell transect), and each end is moved to where the face meets a
       straight line through the two cells beyond it (:func:`_end_correction`).

    Returns:
        A frame with ``label``, ``height_m``, ``run_m`` and ``reaches_nodata``
        (the walk ran off the grid or onto ground with no 1 m slope at either
        end), one row per transect that crossed at least one cell.
    """
    rows, cols = np.nonzero((roles & CREST) > 0)
    d_row = layers.downhill_row[rows, cols]
    d_col = layers.downhill_col[rows, cols]
    down = _trace(labels, rows, cols, d_row, d_col)
    up = _trace(labels, rows, cols, -d_row, -d_col, leave_at_once=True)

    def column(
        cells_rows: NDArray[np.intp], cells_cols: NDArray[np.intp], k: int
    ) -> _Cells:
        return cells_rows[:, k], cells_cols[:, k]

    def pick(mask: NDArray[np.bool_], if_true: _Cells, if_false: _Cells) -> _Cells:
        return (
            np.where(mask, if_true[0], if_false[0]),
            np.where(mask, if_true[1], if_false[1]),
        )

    s0, s1, s2 = (column(down.head_rows, down.head_cols, k) for k in range(3))
    t2, t1, t0 = (column(down.tail_rows, down.tail_cols, k) for k in range(3))
    u1, u2 = (column(up.beyond_rows, up.beyond_cols, k) for k in range(2))
    d1, d2 = (column(down.beyond_rows, down.beyond_cols, k) for k in range(2))
    m = down.count

    tan_grow = math.tan(math.radians(BETA_GROW_ANGLE_DEG))
    with np.errstate(invalid="ignore"):
        trim_top = (m >= 3) & (_gradient(dem, s0, s1, cell_size_m) < tan_grow)
        trim_foot = (m >= 3) & (_gradient(dem, t1, t0, cell_size_m) < tan_grow)
    # A three-cell transect gentle at both ends keeps both.
    neither = trim_top & trim_foot & (m == 3)
    trim_top &= ~neither
    trim_foot &= ~neither
    n_intervals = m - 1 - trim_top.astype(np.intp) - trim_foot.astype(np.intp)

    top = pick(trim_top, s1, s0)
    top_in = pick(trim_top, s2, s1)
    top_out = pick(trim_top, s0, u1)
    top_far = pick(trim_top, u1, u2)
    foot = pick(trim_foot, t1, t0)
    foot_in = pick(trim_foot, t2, t1)
    foot_out = pick(trim_foot, t0, d1)
    foot_far = pick(trim_foot, d1, d2)

    run_between = _distance(top, foot, cell_size_m)
    fall_between = _elevation(dem, top) - _elevation(dem, foot)

    # A face across one interval: vertical, half way between the two cells,
    # the ground outside falling as it does between the two cells beyond each
    # end. Where the interval next to an end falls faster than that, the face
    # runs on into it, and the extra fall is the face's.
    ground_top = np.nan_to_num(_gradient(dem, top_far, top_out, cell_size_m))
    ground_foot = np.nan_to_num(_gradient(dem, foot_out, foot_far, cell_size_m))
    with np.errstate(invalid="ignore"):
        extra_top = np.nan_to_num(
            np.maximum(_gradient(dem, top_out, top, cell_size_m) - ground_top, 0.0)
            * _distance(top_out, top, cell_size_m)
        )
        extra_foot = np.nan_to_num(
            np.maximum(_gradient(dem, foot, foot_out, cell_size_m) - ground_foot, 0.0)
            * _distance(foot, foot_out, cell_size_m)
        )
    thin_height = (
        fall_between
        - 0.5 * run_between * (ground_top + ground_foot)
        + extra_top
        + extra_foot
    )

    # A wider face: its gradient inside the element, then each end to its break.
    face = np.where(
        n_intervals >= 3,
        _gradient(dem, top_in, foot_in, cell_size_m),
        np.fmax(
            _gradient(dem, top, top_in, cell_size_m),
            _gradient(dem, foot_in, foot, cell_size_m),
        ),
    )
    top_run, top_rise = _end_correction(
        dem, (top_far, top_out, top, top_in), face, cell_size_m
    )
    # The foot is the crest turned over: on the negated DEM its falls read
    # towards the toe, as the crest's do towards the crest.
    foot_run, foot_rise = _end_correction(
        -dem, (foot_far, foot_out, foot, foot_in), face, cell_size_m
    )
    wide_run = np.maximum(run_between + top_run + foot_run, 0.0)
    wide_height = fall_between + top_rise + foot_rise

    # One interval is a step only where it is steeper, by more than
    # BETA_STEP_MARGIN_DEG, than the interval beyond each end; one cut
    # out of an even bank (a break in slope the step estimator read as a
    # step) is measured between its two cell centres.
    def steeper_than(outside: NDArray[np.float64]) -> NDArray[np.bool_]:
        with np.errstate(invalid="ignore"):
            margin = np.degrees(np.arctan(fall_between / run_between)) - np.degrees(
                np.arctan(np.nan_to_num(outside, nan=-np.inf))
            )
        return np.nan_to_num(margin, nan=0.0) > BETA_STEP_MARGIN_DEG

    single = n_intervals == 1
    thin = (
        single
        & steeper_than(_gradient(dem, top_out, top, cell_size_m))
        & steeper_than(_gradient(dem, foot, foot_out, cell_size_m))
    )
    height = np.where(thin, thin_height, np.where(single, fall_between, wide_height))
    run = np.where(thin, 0.0, np.where(single, run_between, wide_run))
    reaches_nodata = ~_measured_ground(layers, *d1) | ~_measured_ground(layers, *u1)
    crossed = m >= 2
    return pd.DataFrame(
        {
            "label": labels[rows, cols][crossed],
            "height_m": height[crossed],
            "run_m": run[crossed],
            "reaches_nodata": reaches_nodata[crossed],
        }
    )


def _majority(
    labels: NDArray[np.int32], values: NDArray[np.integer], n_labels: int
) -> NDArray[np.int64]:
    """The most common value under each label, -1 where a label has no cells."""
    inside = labels > OUTSIDE
    keys = labels[inside].astype(np.int64)
    found = np.asarray(values)[inside].astype(np.int64)
    result = np.full(n_labels + 1, -1, dtype=np.int64)
    if keys.size == 0:
        return result
    pairs, counts = np.unique(np.stack([keys, found]), axis=1, return_counts=True)
    # Sort by label, then count, so the last pair of each label is its mode.
    order = np.lexsort((counts, pairs[0]))
    pairs = pairs[:, order]
    last = np.r_[pairs[0, 1:] != pairs[0, :-1], True]
    result[pairs[0, last]] = pairs[1, last]
    return result


def _measure(
    labels: NDArray[np.int32],
    n_labels: int,
    dem: NDArray[np.float64],
    ground_group: NDArray[np.int8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> tuple[pd.DataFrame, NDArray[np.uint8]]:
    """Measure each region's height, angle and step test.

    Returns:
        A frame indexed 1 to ``n_labels`` with ``n_cells``, ``height_m``,
        ``height_max_m``, ``run_m``, ``n_transects``, ``overall_angle_deg``,
        ``ground_group_code``, ``height_band``, ``threshold_angle_deg``,
        ``is_free_face``, ``length_m`` and ``aspect_deg``, and the edge role
        grid. A transect that reaches
        nodata or the edge of the grid is left out where its element has
        others, because the survey's edge cut it short.
    """
    index = pd.RangeIndex(1, n_labels + 1, name="label")
    roles = _edge_roles(labels, layers)
    transects = _transects(labels, dem, roles, layers, cell_size_m)
    clean = (~transects["reaches_nodata"]).groupby(transects["label"]).transform("sum")
    transects = transects[~transects["reaches_nodata"] | (clean == 0)]
    by_label = transects.groupby("label")
    height = by_label["height_m"].median().reindex(index)
    height_max = by_label["height_m"].max().reindex(index)
    run = by_label["run_m"].median().reindex(index)
    n_transects = by_label.size().reindex(index, fill_value=0)

    # A region no transect crossed (one with no crest cell, such as one
    # bounded only by the edge of the grid) is measured by its elevation range.
    inside = labels > OUTSIDE
    flat_labels = labels[inside]
    flat_z = dem[inside]
    z_max = pd.Series(flat_z).groupby(flat_labels).max().reindex(index)
    z_min = pd.Series(flat_z).groupby(flat_labels).min().reindex(index)
    height = height.fillna(z_max - z_min)
    height_max = height_max.fillna(z_max - z_min)

    angle = np.degrees(np.arctan2(height.to_numpy(), run.to_numpy()))
    counts = np.bincount(flat_labels, minlength=n_labels + 1)[1:]
    group = _majority(labels, ground_group, n_labels)[1:]
    group = np.where(group < 0, GROUND_GROUPS.index(OFF_MAP_GROUND_GROUP), group)
    band = height_band(height.to_numpy())
    threshold = step_angle_deg(group, band)
    with np.errstate(invalid="ignore"):
        free_face = (band > 0) & (angle > threshold)
    aspect = _circular_mean_deg(labels, layers, n_labels)
    length = _length_along_contour(labels, aspect, cell_size_m)

    frame = pd.DataFrame(
        {
            "n_cells": counts,
            "height_m": height.to_numpy(),
            "height_max_m": height_max.to_numpy(),
            "run_m": run.to_numpy(),
            "n_transects": n_transects.to_numpy(),
            "overall_angle_deg": angle,
            "ground_group_code": group.astype(np.int8),
            "height_band": band,
            "threshold_angle_deg": threshold,
            "is_free_face": free_face,
            "length_m": length,
            "aspect_deg": aspect,
        },
        index=index,
    )
    return frame, roles


def _cost(exceedance: NDArray[np.float64]) -> NDArray[np.uint16]:
    """Turn an exceedance in degrees into watershed costs, highest first."""
    capped = np.clip(
        np.nan_to_num(exceedance, nan=-_EXCEEDANCE_CAP_DEG),
        -_EXCEEDANCE_CAP_DEG,
        _EXCEEDANCE_CAP_DEG,
    )
    cost = np.rint((_EXCEEDANCE_CAP_DEG - capped) * _COST_SCALE)
    return np.clip(cost, 0, _BARRIER_COST - 1).astype(np.uint16)


def _grow(
    seeds: NDArray[np.int32],
    n_seeds: int,
    cost: NDArray[np.uint16],
    allowed: NDArray[np.bool_],
) -> NDArray[np.int32]:
    """Grow seeds by watershed over allowed cells only.

    The cells growth may not enter are themselves made markers of a barrier
    label, so no flood passes through them, and they take the top cost, so
    the barrier's own flood, which costs at least that, never beats a seed's
    to an allowed cell; seed cells always keep their seed.
    """
    barrier = n_seeds + 1
    markers = np.where(seeds > OUTSIDE, seeds, OUTSIDE).astype(np.int32)
    blocked = (markers == OUTSIDE) & ~allowed
    markers[blocked] = barrier
    if not np.any(markers == OUTSIDE):
        grown = markers
    else:
        costs = np.where(blocked, _BARRIER_COST, cost).astype(np.uint16)
        grown = ndimage.watershed_ift(costs, markers, structure=FOUR_CONNECTED)
    grown = np.where(grown == barrier, OUTSIDE, grown).astype(np.int32)
    return grown


def _grow_by_limit(
    seeds: NDArray[np.int32],
    n_seeds: int,
    cost: NDArray[np.uint16],
    *,
    slope: NDArray[np.float64],
    finite: NDArray[np.bool_],
    limit: NDArray[np.float64],
    cell_limit: NDArray[np.float64],
) -> NDArray[np.int32]:
    """Grow free-face seeds, each only into cells over its own grow limit.

    The seeds sharing a grow limit (one ground group and estimated band) grow
    together by watershed, strongest first; the limits are taken strictest
    first, each over the cells the stricter ones left. A cell is also entered
    only where it is over its own ground's limit (``cell_limit``, a grid), so
    a soil-like seed does not flood weak rock steeper than the soil's limit
    but not the rock's, and a seed never floods ground it cannot keep, which
    would shut out the seed whose ground it is. ``limit`` is indexed by seed
    label.
    """
    grown = np.zeros_like(seeds)
    live = np.unique(seeds[seeds > OUTSIDE])
    for value in np.unique(limit[live])[::-1]:
        members = np.zeros(n_seeds + 1, dtype=bool)
        members[live[limit[live] == value]] = True
        own = np.where(members[seeds], seeds, OUTSIDE).astype(np.int32)
        others = (seeds > OUTSIDE) & ~members[seeds]
        allowed = (
            finite
            & (slope > np.maximum(value, cell_limit) + _ANGLE_SLACK_DEG)
            & (grown == OUTSIDE)
            & ~others
        )
        found = _grow(own, n_seeds, cost, allowed)
        grown = np.where(grown == OUTSIDE, found, grown).astype(np.int32)
    return grown


def _relabel(labels: NDArray[np.int32], keep: NDArray[np.bool_]) -> NDArray[np.int32]:
    """Drop the labels ``keep`` (indexed by label) rejects and renumber from 1."""
    lookup = np.zeros(keep.size, dtype=np.int32)
    kept = np.nonzero(keep)[0]
    kept = kept[kept > OUTSIDE]
    lookup[kept] = np.arange(1, kept.size + 1, dtype=np.int32)
    return lookup[labels]


def _absorb_rounded_edges(
    grown: NDArray[np.int32], layers: TerrainLayers
) -> NDArray[np.int32]:
    """Give each free-face the rounded cells at its crest and toe.

    Horn's kernel spreads a sharp step over the cell either side of it, so the
    cell above a cut's crest and the one below its toe read a slope part way
    between the cut's and the ground's beyond. Such a cell, unclaimed, at
    least :data:`BETA_GROW_ANGLE_DEG` steep and more than
    :data:`BETA_FREE_FACE_GROW_TOL_DEG` steeper than the cell beyond it along
    the fall line, is the rounded edge of the free-face and joins it. A bank
    running on above or below the free-face is as steep as the cell beyond
    and stays out.
    """
    slope = np.nan_to_num(layers.slope_fine_deg, nan=-np.inf)
    rows, cols = np.nonzero((grown == OUTSIDE) & (slope >= BETA_GROW_ANGLE_DEG))
    if rows.size == 0:
        return grown
    d_row = layers.downhill_row[rows, cols]
    d_col = layers.downhill_col[rows, cols]
    has_direction = np.isfinite(d_row) & np.isfinite(d_col)
    rows, cols = rows[has_direction], cols[has_direction]
    step_rows = np.rint(d_row[has_direction]).astype(np.intp)
    step_cols = np.rint(d_col[has_direction]).astype(np.intp)
    padded_slope = np.pad(slope, 1, constant_values=-np.inf)
    result = grown.copy()
    for sign in (1, -1):
        # sign 1: the free-face lies downhill and the cell is above its crest.
        face = _neighbour(grown, rows, cols, sign * step_rows, sign * step_cols)
        beyond = padded_slope[1 + rows - sign * step_rows, 1 + cols - sign * step_cols]
        rounded = (face > OUTSIDE) & (
            slope[rows, cols] > beyond + BETA_FREE_FACE_GROW_TOL_DEG
        )
        result[rows[rounded], cols[rounded]] = face[rounded]
    return result


def _label_within_groups(
    mask: NDArray[np.bool_], ground_group: NDArray[np.int8]
) -> tuple[NDArray[np.int32], int]:
    """Label the 4-connected pieces of a mask, never across ground groups."""
    labels = np.zeros(mask.shape, dtype=np.int32)
    total = 0
    for code in np.unique(ground_group[mask]):
        pieces, n = ndimage.label(
            mask & (ground_group == code), structure=FOUR_CONNECTED
        )
        labels = np.where(pieces > OUTSIDE, pieces + total, labels).astype(np.int32)
        total += int(n)
    return labels, total


def _free_face_pass(
    dem: NDArray[np.float64],
    ground_group: NDArray[np.int8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> tuple[NDArray[np.int32], NDArray[np.int32], NDArray[np.float64]]:
    """Seed and grow the free-faces.

    Returns:
        ``(labels, seeds, exceedance)``: the grown free-faces, the seed patches
        they grew from (same labels), and the exceedance grid.
    """
    band = height_band(np.nan_to_num(layers.step_height_m, nan=0.0))
    threshold = step_angle_deg(ground_group, band)
    min_step = step_seed_height_m(ground_group)
    exceedance = layers.slope_coarse_deg - threshold
    finite = np.isfinite(dem) & np.isfinite(layers.slope_fine_deg)
    with np.errstate(invalid="ignore"):
        eligible = finite & (
            (np.nan_to_num(layers.step_height_m, nan=0.0) >= min_step)
            | (np.nan_to_num(exceedance, nan=-np.inf) > 0)
        )
    patches, n_patches = _label_within_groups(eligible, ground_group)
    if n_patches == 0:
        empty = patches.astype(np.int32)
        return empty, empty, exceedance

    # Each patch's threshold is the one at its cell of highest exceedance.
    score = np.nan_to_num(exceedance, nan=-np.inf)
    step = np.nan_to_num(layers.step_height_m, nan=0.0)
    slope = np.nan_to_num(layers.slope_fine_deg, nan=-np.inf)
    patch_index = np.arange(1, n_patches + 1)
    peaks = np.array(ndimage.maximum_position(score, patches, patch_index))
    patch_limit = np.zeros(n_patches + 1)
    patch_limit[1:] = threshold[peaks[:, 0], peaks[:, 1]] - BETA_FREE_FACE_GROW_TOL_DEG
    patch_step = np.zeros(n_patches + 1)
    patch_step[1:] = ndimage.maximum(step, patches, patch_index)

    # The seed is the patch's 1 m footprint: the 3 m slope and the 9 m step
    # span spread a patch a few cells past the step or the cut it marks, so a
    # patch keeps only the cells steep enough to grow into or holding most of
    # its step, and each piece left is a seed of its own.
    footprint = (patches > OUTSIDE) & (
        (slope > patch_limit[patches] + _ANGLE_SLACK_DEG)
        | (step >= np.maximum(min_step, BETA_SEED_STEP_SHARE * patch_step[patches]))
    )
    seeds, n_seeds = _label_within_groups(footprint, ground_group)
    if n_seeds == 0:
        return seeds, seeds, exceedance
    limit = np.zeros(n_seeds + 1)
    limit[1:] = ndimage.maximum(patch_limit[patches], seeds, np.arange(1, n_seeds + 1))
    cost = _cost(exceedance)

    cell_limit = np.nan_to_num(threshold - BETA_FREE_FACE_GROW_TOL_DEG, nan=np.inf)

    def grow(active: NDArray[np.bool_]) -> NDArray[np.int32]:
        live = np.where(active[seeds], seeds, OUTSIDE).astype(np.int32)
        grown = _grow_by_limit(
            live,
            n_seeds,
            cost,
            slope=slope,
            finite=finite,
            limit=limit,
            cell_limit=cell_limit,
        )
        return _absorb_rounded_edges(grown, layers)

    active = np.ones(n_seeds + 1, dtype=bool)
    active[0] = False
    for _ in range(_MAX_FREE_FACE_ROUNDS):
        grown = grow(active)
        measured, _ = _measure(grown, n_seeds, dem, ground_group, layers, cell_size_m)
        passes = np.zeros(n_seeds + 1, dtype=bool)
        passes[1:] = (
            measured["is_free_face"].to_numpy()
            & (measured["height_m"].to_numpy() >= MIN_WALL_HEIGHT_M)
            & (measured["length_m"].to_numpy() >= BETA_MIN_ELEMENT_LENGTH_M)
        )
        still = active & passes
        if np.array_equal(still, active):
            break
        active = still
    else:
        # The rounds ran out before the seeds settled: the ground of the last
        # seeds released goes back to the free-faces left before the bank pass.
        grown = grow(active)
    live_seeds = np.where(active[seeds], seeds, OUTSIDE).astype(np.int32)
    return grown, live_seeds, exceedance


def _bank_pass(
    claimed: NDArray[np.bool_],
    dem: NDArray[np.float64],
    layers: TerrainLayers,
    ground_group: NDArray[np.int8],
) -> tuple[NDArray[np.int32], NDArray[np.int32]]:
    """Seed and grow the banks on the ground the free-faces left.

    Returns:
        ``(labels, seeds)``, numbered from 1.
    """
    fine = np.nan_to_num(layers.slope_fine_deg, nan=-np.inf)
    coarse = np.nan_to_num(layers.slope_coarse_deg, nan=-np.inf)
    least = bank_seed_slope_deg(ground_group)
    allowed = ~claimed & np.isfinite(dem) & (fine >= least)
    seeds, n_seeds = ndimage.label(
        allowed & (coarse >= least), structure=FOUR_CONNECTED
    )
    seeds = seeds.astype(np.int32)
    if n_seeds == 0:
        return seeds, seeds
    cost = _cost(layers.slope_coarse_deg - least)
    grown = _grow(seeds, n_seeds, cost, allowed)
    return grown, seeds


def _circular_mean_deg(
    labels: NDArray[np.int32], layers: TerrainLayers, n_labels: int
) -> NDArray[np.float64]:
    """The circular mean downhill bearing of each label, clockwise from north."""
    inside = (labels > OUTSIDE) & np.isfinite(layers.downhill_row)
    flat = labels[inside]
    east = np.bincount(
        flat, weights=layers.downhill_col[inside], minlength=n_labels + 1
    )
    north = np.bincount(
        flat, weights=-layers.downhill_row[inside], minlength=n_labels + 1
    )
    bearing = np.degrees(np.arctan2(east, north)) % 360.0
    bearing[np.hypot(east, north) == 0] = np.nan
    return bearing[1:]


def _length_along_contour(
    labels: NDArray[np.int32], aspect_deg: NDArray[np.float64], cell_size_m: float
) -> NDArray[np.float64]:
    """Each label's extent square to its aspect, in metres."""
    rows, cols = np.nonzero(labels > OUTSIDE)
    flat = labels[rows, cols]
    radians = np.radians(np.nan_to_num(aspect_deg, nan=0.0))
    # The contour runs square to the bearing: in array axes the bearing's unit
    # vector is (-cos, sin) along (rows, cols), so the contour is (sin, cos).
    along = rows * np.sin(radians)[flat - 1] + cols * np.cos(radians)[flat - 1]
    grouped = pd.Series(along).groupby(flat)
    extent = (grouped.max() - grouped.min()).reindex(range(1, aspect_deg.size + 1))
    return (extent.to_numpy() + 1.0) * cell_size_m


def _stack_links(
    labels: NDArray[np.int32],
    dem: NDArray[np.float64],
    roles: NDArray[np.uint8],
    layers: TerrainLayers,
    cell_size_m: float,
) -> pd.DataFrame:
    """Find, for each element, the elements whose toe meets its crest."""
    columns = [
        "lower",
        "upper",
        "bench_width_m",
        "bench_width_min_m",
        "n_transects",
        "share_of_crest",
    ]
    rows, cols = np.nonzero((roles & CREST) > 0)
    if rows.size == 0:
        return pd.DataFrame(columns=columns)
    own = labels[rows, cols]
    max_steps = math.ceil(BETA_STACK_SEARCH_M / cell_size_m / WALK_STEP_CELLS)
    # Walk uphill: everything outside the own element is passed over until
    # another element is met, so the walk is on a grid where the bench and the
    # own element are one label.
    walk_grid = np.where(labels == OUTSIDE, -1, labels)
    hits = np.full(own.shape, OUTSIDE, dtype=np.int32)
    distance = np.full(own.shape, np.nan)
    d_row = -layers.downhill_row[rows, cols]
    d_col = -layers.downhill_col[rows, cols]
    # The walk ends where the ground starts to fall away again by more than
    # BETA_RIDGE_DROP_M, over a ridge or a hump, so an element on the far side
    # is not taken for one above.
    highest = dem[rows, cols].copy()
    active = np.ones(own.shape, dtype=bool)
    for k in range(1, max_steps + 1):
        index = np.nonzero(active)[0]
        if index.size == 0:
            break
        r = np.rint(rows[index] + k * WALK_STEP_CELLS * d_row[index]).astype(np.intp)
        c = np.rint(cols[index] + k * WALK_STEP_CELLS * d_col[index]).astype(np.intp)
        inside = (r >= 0) & (r < labels.shape[0]) & (c >= 0) & (c < labels.shape[1])
        found = np.full(index.shape, -1, dtype=np.int64)
        found[inside] = walk_grid[r[inside], c[inside]]
        z = np.full(index.shape, np.nan)
        z[inside] = dem[r[inside], c[inside]]
        highest[index] = np.fmax(highest[index], z)
        over = ~(z >= highest[index] - BETA_RIDGE_DROP_M)
        met = inside & ~over & (found > OUTSIDE) & (found != own[index])
        # An element above faces the same way down the fall line; one facing
        # back (the far side of a ridge, a gully's other wall) is not stacked.
        facing = np.zeros(index.shape)
        facing[met] = (
            layers.downhill_row[r[met], c[met]] * -d_row[index[met]]
            + layers.downhill_col[r[met], c[met]] * -d_col[index[met]]
        )
        hit = met & (facing > 0)
        over |= met & ~hit
        hits[index[hit]] = found[hit]
        distance[index[hit]] = np.hypot(
            r[hit] - rows[index[hit]], c[hit] - cols[index[hit]]
        )
        active[index[hit | ~inside | over]] = False
    linked = hits > OUTSIDE
    if not linked.any():
        return pd.DataFrame(columns=columns)
    bench = np.maximum(distance[linked] - 1.0, 0.0) * cell_size_m
    frame = pd.DataFrame(
        {"lower": own[linked], "upper": hits[linked], "bench_width_m": bench}
    )
    grouped = frame.groupby(["lower", "upper"])["bench_width_m"]
    links = grouped.agg(["median", "min", "size"]).reset_index()
    links.columns = [
        "lower",
        "upper",
        "bench_width_m",
        "bench_width_min_m",
        "n_transects",
    ]
    crest_cells = np.bincount(own, minlength=int(labels.max()) + 1)
    links["share_of_crest"] = links["n_transects"] / crest_cells[links["lower"]]
    return links[columns]


def _block_mode(labels: NDArray[np.int32], factor: int) -> NDArray[np.int32]:
    """The most common element label in each block, OUTSIDE where it has none."""
    rows = labels.shape[0] // factor
    cols = labels.shape[1] // factor
    blocks = labels[: rows * factor, : cols * factor].reshape(
        rows, factor, cols, factor
    )
    blocks = blocks.transpose(0, 2, 1, 3).reshape(rows, cols, factor * factor)
    counts = (blocks[..., :, None] == blocks[..., None, :]).sum(axis=-1)
    counts = np.where(blocks > OUTSIDE, counts, 0)
    pick = np.argmax(counts, axis=-1)
    mode = np.take_along_axis(blocks, pick[..., None], axis=-1)[..., 0]
    return np.where(counts.max(axis=-1) > 0, mode, OUTSIDE).astype(np.int32)


def _block_mean(dem: NDArray[np.float64], factor: int) -> NDArray[np.float64]:
    """The mean of each block, NaN where any cell of it is nodata."""
    rows = dem.shape[0] // factor
    cols = dem.shape[1] // factor
    blocks = dem[: rows * factor, : cols * factor].reshape(rows, factor, cols, factor)
    return blocks.mean(axis=(1, 3))


def _d8_receivers(dem: NDArray[np.float64], cell_size_m: float) -> NDArray[np.intp]:
    """The flat index of each cell's steepest downhill neighbour, or itself.

    A cell with no lower neighbour (a pit, a flat or nodata) is its own
    receiver, so its paths end there; nothing is filled.
    """
    rows, cols = dem.shape
    flat_index = np.arange(rows * cols).reshape(rows, cols)
    best = np.zeros(dem.shape)
    receiver = flat_index.copy()
    padded = np.pad(dem, 1, constant_values=np.nan)
    padded_index = np.pad(flat_index, 1, constant_values=-1)
    for d_r in (-1, 0, 1):
        for d_c in (-1, 0, 1):
            if d_r == 0 and d_c == 0:
                continue
            neighbour = padded[1 + d_r : 1 + d_r + rows, 1 + d_c : 1 + d_c + cols]
            index = padded_index[1 + d_r : 1 + d_r + rows, 1 + d_c : 1 + d_c + cols]
            with np.errstate(invalid="ignore"):
                drop = (dem - neighbour) / (math.hypot(d_r, d_c) * cell_size_m)
            better = np.nan_to_num(drop, nan=-np.inf) > best
            best = np.where(better, drop, best)
            receiver = np.where(better, index, receiver)
    return receiver.ravel()


def _catchments(
    labels: NDArray[np.int32],
    dem: NDArray[np.float64],
    transform: Affine,
    cell_size_m: float,
) -> tuple[NDArray[np.int32], Affine, pd.DataFrame]:
    """Label each coarse cell with the first element its D8 flow reaches."""
    factor = max(round(COARSE_SLOPE_M / cell_size_m), 1)
    coarse_dem = _block_mean(dem, factor)
    coarse_labels = _block_mode(labels, factor)
    coarse_transform = Affine(
        transform.a * factor, 0.0, transform.c, 0.0, transform.e * factor, transform.f
    )
    receiver = _d8_receivers(coarse_dem, cell_size_m * factor)

    flat_labels = coarse_labels.ravel()
    own = np.arange(flat_labels.size)
    pointer = np.where(flat_labels > OUTSIDE, own, receiver)
    # Pointer doubling: each cell takes its target's target until nothing
    # moves, about log2 of the longest flow path in passes.
    while True:
        doubled = pointer[pointer]
        if np.array_equal(doubled, pointer):
            break
        pointer = doubled
    catchment = flat_labels[pointer]

    on_element = flat_labels > OUTSIDE
    downstream = catchment[receiver]
    leaves = on_element & (downstream > OUTSIDE) & (downstream != flat_labels)
    pairs = pd.DataFrame({"upper": flat_labels[leaves], "lower": downstream[leaves]})
    drainage = pairs.groupby(["upper", "lower"]).size().rename("n_cells").reset_index()
    shape = coarse_labels.shape
    return catchment.reshape(shape).astype(np.int32), coarse_transform, drainage


def find_slope_elements(
    dem: ArrayLike,
    ground_group: ArrayLike,
    transform: Affine,
    *,
    categories: Mapping[str, ArrayLike] | None = None,
    core: ArrayLike | None = None,
) -> SlopeElements:
    """Find the slope elements on a DEM.

    Args:
        dem: Ground elevation in metres on a north-up grid of square cells,
            NaN for nodata and outside the LiDAR.
        ground_group: The ground group code of every cell, an index into
            :data:`GROUND_GROUPS`; see :func:`ground_group_codes` and
            :func:`rasterise_ground_map`.
        transform: The grid's affine transform, cell corner based.
        categories: Integer grids to take the majority of over each element,
            written as ``majority_<name>`` (for example a ground map row index
            for ``ground_id``, material and modification).
        core: Where given, a boolean grid marking a tile's core. Every
            element is kept, the halo's too, and ``in_core`` says whether its
            seed peak lies on the core, so the links, the catchments and the
            polygons are built on the whole tile and only the core's are
            written out (``build_slope_polygons`` in
            :mod:`landloss.hazard.landslide.slope_polygons` drops the rest
            after settling the shared ground).

    Returns:
        The elements and their links.

    Raises:
        ValueError: If the grids do not share a shape, or the transform is not
            north-up with square cells.
    """
    elevation = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    if groups.shape != elevation.shape:
        msg = f"The ground group grid is {groups.shape}, the DEM {elevation.shape}."
        raise ValueError(msg)
    core_grid = np.ones(elevation.shape, dtype=bool)
    if core is not None:
        core_grid = np.asarray(core, dtype=bool)
        if core_grid.shape != elevation.shape:
            msg = f"The core grid is {core_grid.shape}, the DEM {elevation.shape}."
            raise ValueError(msg)
    cell_size_m = _cell_size(transform)
    layers = terrain_layers(elevation, cell_size_m)

    free_faces, free_face_seeds, exceedance = _free_face_pass(
        elevation, groups, layers, cell_size_m
    )
    present = np.bincount(free_faces.ravel()) > 0
    free_faces = _relabel(free_faces, present)
    free_face_seeds = _relabel(free_face_seeds, present[: free_face_seeds.max() + 1])
    n_free_faces = int(free_faces.max())

    banks, bank_seeds = _bank_pass(free_faces > OUTSIDE, elevation, layers, groups)
    offset = np.where(banks > OUTSIDE, banks + n_free_faces, OUTSIDE)
    labels = np.where(free_faces > OUTSIDE, free_faces, offset).astype(np.int32)
    seeds_offset = np.where(bank_seeds > OUTSIDE, bank_seeds + n_free_faces, OUTSIDE)
    seed_grid = np.where(free_faces > OUTSIDE, free_face_seeds, seeds_offset)
    seed_grid = np.where(labels > OUTSIDE, seed_grid, OUTSIDE).astype(np.int32)

    n_labels = int(labels.max())
    measured, _ = _measure(labels, n_labels, elevation, groups, layers, cell_size_m)
    # A region under the smallest element's height is not an element, nor is
    # one gentler overall than the grow angle: ground under it is a bench or a
    # floor (the plan, phase 1), such as the two steep cells either side of a
    # gully's axis, which grow along the gully but measure across it. Nor is
    # one no transect crosses, with no crest on measured ground (a strip along
    # the grid's or the survey's edge): it cannot be measured.
    keep = np.zeros(n_labels + 1, dtype=bool)
    with np.errstate(invalid="ignore"):
        keep[1:] = (
            (measured["height_m"].to_numpy() >= MIN_WALL_HEIGHT_M)
            & (measured["length_m"].to_numpy() >= BETA_MIN_ELEMENT_LENGTH_M)
            & (measured["n_transects"].to_numpy() > 0)
            & ~(
                measured["overall_angle_deg"].to_numpy()
                < BETA_GROW_ANGLE_DEG - _ANGLE_SLACK_DEG
            )
        )

    # Each seed's priority as its own pass measured it: a free-face seed's 3 m
    # slope less its step test angle, a bank seed's less the grow angle.
    seed_exceedance = np.full(n_labels + 1, np.nan)
    seed_rows = np.full(n_labels + 1, -1, dtype=np.intp)
    seed_cols = np.full(n_labels + 1, -1, dtype=np.intp)
    if n_labels:
        bank_score = layers.slope_coarse_deg - bank_seed_slope_deg(groups)
        score = np.where(seed_grid > n_free_faces, bank_score, exceedance)
        # Rounded to a micro-degree, so cells that tie on even ground tie
        # exactly whatever the floating point of a tile's filters, and ties go
        # to the first cell in row order: the same cell on every tile.
        score = np.round(np.nan_to_num(score, nan=-np.inf), _SCORE_DECIMALS)
        rows, cols = np.nonzero(seed_grid > OUTSIDE)
        owner = seed_grid[rows, cols]
        order = np.lexsort((cols, rows, -score[rows, cols], owner))
        first = order[np.r_[True, owner[order][1:] != owner[order][:-1]]]
        seed_exceedance[owner[first]] = score[rows[first], cols[first]]
        seed_rows[owner[first]] = rows[first]
        seed_cols[owner[first]] = cols[first]
    in_core = np.zeros(n_labels + 1, dtype=bool)
    valid = seed_rows >= 0
    in_core[valid] = core_grid[seed_rows[valid], seed_cols[valid]]

    kept = np.nonzero(keep)[0]
    labels = _relabel(labels, keep)
    n_labels = int(kept.size)
    grown_in = np.where(kept <= n_free_faces, FREE_FACE_PASS, BANK_PASS)

    measured, roles = _measure(labels, n_labels, elevation, groups, layers, cell_size_m)
    elements = measured.drop(
        columns=["ground_group_code", "is_free_face", "length_m", "aspect_deg"]
    )
    elements.insert(0, "grown_in", grown_in)
    elements.insert(
        1, "element_type", np.where(measured["is_free_face"], FREE_FACE, BANK)
    )
    elements.insert(3, "area_m2", elements["n_cells"] * cell_size_m**2)

    inside = labels > OUTSIDE
    flat = labels[inside]
    slope = layers.slope_fine_deg[inside]
    by_label = pd.Series(slope).groupby(flat)
    index = elements.index
    elements["slope_mean_deg"] = by_label.mean().reindex(index).to_numpy()
    elements["slope_max_deg"] = by_label.max().reindex(index).to_numpy()
    aspect = _circular_mean_deg(labels, layers, n_labels)
    elements["length_m"] = _length_along_contour(labels, aspect, cell_size_m)
    elements["aspect_deg"] = aspect
    step = pd.Series(np.nan_to_num(layers.step_height_m[inside], nan=0.0))
    elements["step_peak_m"] = step.groupby(flat).max().reindex(index).to_numpy()
    elements["seed_exceedance_deg"] = seed_exceedance[kept]
    elements["seed_row"] = seed_rows[kept]
    elements["seed_col"] = seed_cols[kept]
    # The seed peak's cell centre in map units: the same on every tile that
    # holds the element, so tiles' elements can be matched across a seam.
    seeded = seed_rows[kept] >= 0
    elements["seed_x"] = np.where(
        seeded, transform.c + (seed_cols[kept] + 0.5) * transform.a, np.nan
    )
    elements["seed_y"] = np.where(
        seeded, transform.f + (seed_rows[kept] + 0.5) * transform.e, np.nan
    )
    elements["in_core"] = in_core[kept]
    # Ground with no 1 m slope next to an element (nodata, its rim, the edge
    # of the grid) means the survey's edge, not the ground, stopped it there.
    unmeasured = ndimage.binary_dilation(
        ~np.isfinite(layers.slope_fine_deg),
        structure=np.ones((3, 3), dtype=bool),
        border_value=1,
    )
    elements["touches_nodata"] = (
        np.bincount(flat, weights=unmeasured[inside], minlength=n_labels + 1)[1:] > 0
    )
    elements["ground_group"] = np.asarray(GROUND_GROUPS)[
        measured["ground_group_code"].to_numpy()
    ]
    elements["angle_excess_deg"] = (
        elements["overall_angle_deg"] - elements["threshold_angle_deg"]
    )
    elements["stack_dominant_cut"] = (
        elements["overall_angle_deg"] > STACK_DOMINANT_ANGLE_DEG
    ) & (elements["height_m"] > STACK_DOMINANT_HEIGHT_M)
    elements["hb1995_cut"] = (elements["overall_angle_deg"] > HB1995_CUT_ANGLE_DEG) & (
        elements["height_m"] > HB1995_CUT_HEIGHT_M
    )

    catchments, catchment_transform, drainage = _catchments(
        labels, elevation, transform, cell_size_m
    )
    own_catchment = np.bincount(catchments.ravel(), minlength=n_labels + 1)[1:]
    elements["own_catchment_area_m2"] = own_catchment * (
        catchment_transform.a * -catchment_transform.e
    )

    rows, cols = np.nonzero(inside)
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    elements["centroid_x"] = pd.Series(x).groupby(flat).mean().reindex(index).to_numpy()
    elements["centroid_y"] = pd.Series(y).groupby(flat).mean().reindex(index).to_numpy()
    for name, grid in (categories or {}).items():
        values = np.asarray(grid)
        if values.shape != elevation.shape:
            msg = f"The {name} grid is {values.shape}, the DEM {elevation.shape}."
            raise ValueError(msg)
        elements[f"majority_{name}"] = _majority(labels, values, n_labels)[1:]

    return SlopeElements(
        labels=labels,
        edge_roles=roles,
        elements=elements,
        stack_links=_stack_links(labels, elevation, roles, layers, cell_size_m),
        catchments=catchments,
        catchment_transform=catchment_transform,
        drainage_links=drainage,
        layers=layers,
    )


def rasterise_ground_map(
    ground_map: gpd.GeoDataFrame, transform: Affine, shape: tuple[int, int]
) -> tuple[NDArray[np.int8], NDArray[np.int32]]:
    """Burn the ground map onto a grid as ground groups and row positions.

    Args:
        ground_map: The ground map, with a ``material`` column, on the grid's
            coordinate reference system.
        transform: The grid's affine transform.
        shape: The grid's ``(rows, columns)``.

    Returns:
        ``(ground_group, row)``: the ground group code of every cell, off-map
        cells taking :data:`OFF_MAP_GROUND_GROUP`, and the position in
        ``ground_map`` of the piece each cell centre falls in, -1 off the map.
        The position reads ``material``, ``modification`` and ``ground_id``
        back for an element's majority.
    """
    position = np.full(shape, -1, dtype=np.int32)
    if len(ground_map):
        burned = features.rasterize(
            zip(ground_map.geometry, range(len(ground_map)), strict=True),
            out_shape=shape,
            transform=transform,
            fill=-1,
            dtype="int32",
        )
        position = burned.astype(np.int32)
    codes = (
        ground_group_codes(ground_map["material"].to_numpy())
        if len(ground_map)
        else np.array([], dtype=np.int8)
    )
    group = np.full(shape, GROUND_GROUPS.index(OFF_MAP_GROUND_GROUP), dtype=np.int8)
    on_map = position >= 0
    group[on_map] = codes[position[on_map]]
    return group, position
