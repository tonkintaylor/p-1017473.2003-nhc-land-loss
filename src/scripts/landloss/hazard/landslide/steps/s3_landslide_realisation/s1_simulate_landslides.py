"""Draw one realisation of the large landslides, placed one slope unit at a time.

A model grid gives each cell's expected large-landslide coverage: the Hancox
model 3 grid written by landslide step 2 on the committed settings, the Kritikos model 2
coverage written by landslide step 8, or the supplied ESNZ
probability grid when `COVERAGE_MODEL` selects it. It cannot say how much land a
claim covers, or whose land the debris lands on, because it holds no landslides.
This script draws a set of them, the **large** population of plan section 10:
the failures above the urban size range, placed in the slope units landslide step 1 cut.
The urban failures on the slopes beside buildings are drawn by landslide step 6
against their own fragilities, and the two are combined there.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s3_landslide_realisation/s1_simulate_landslides.py

What it runs over, and with what settings, comes from ``config.py`` beside it,
read at the bottom of this file and passed into :func:`main`. Change it there
rather than passing flags, so that what a run did can be read off the source.

The step reads only hazard outputs: the selected coverage, the slope units from landslide step 1
(``slope_units_path``), the 10 m DEM, slope and aspect from ground step 1 and its 100 m
topographic position, the ground step 2 ground map, and the supplied probability grid,
or the landslide step 2 Hancox or landslide step 8 Kritikos coverage, on the 10 m DEM grid so every per-cell product below is cell
aligned. It fetches nothing.

**No large landslide starts on flat land** (the project lead, 2026-10-02). The
probability is set to NaN on every working-grid cell whose centre lies on a
ground map piece with ``is_flatland`` true, the NLM flatland release, before
anything below reads it, so flat cells add no expected area and are never a
seed. A source seeded on a slope is not clipped where it runs onto flat land,
and its runout may well end there.

Nine stages, each of which is a stated assumption rather than a measurement.

1. **Expected failed area per unit.** The sum over the unit's cells of model
   coverage times cell area, times the model's source-area fraction (1 for
   Hancox and Kritikos coverage; :data:`BETA_SOURCE_AREA_FRACTION` for ESNZ), times one
   minus ``URBAN_AREA_SHARE`` (the share of the inventory's area the urban
   model draws instead).
2. **A count per unit**, a Poisson draw with mean the expected area over the
   mean size of the truncated law below. The unit decides where a failure
   starts, not how large it can be.
3. **A size per failure**, from the bounded power law between
   ``LARGE_MIN_SOURCE_AREA_M2`` and :data:`MAX_SOURCE_AREA_M2` with exponent
   :data:`SIZE_EXPONENT`, the published Kaikōura exponent [massey_2020], which
   holds above a cutoff near 500 m² and so over this range.
4. **A seed cell per failure**: a weighted choice over the unit's top
   :data:`SEED_CANDIDATE_CELLS` cells by model coverage times a crest lift from
   the 100 m topographic position, because earthquake sources favour crests.
5. **An ellipse for the source**, of the sampled area, long axis along the
   downhill azimuth at the seed with ``SOURCE_ASPECT_RATIO``, centred half a
   long axis downslope of the seed so the seed is its crest. It is not clipped
   to the unit: a failure larger than its unit crosses into the neighbours.
6. **Drop overlapping failures, keeping the largest.** Two landslides cannot
   occupy the same ground.
7. **Move the failure downhill**, by a distance that grows with the slope at
   the seed, between :data:`MIN_DISPLACEMENT_M` and :data:`MAX_DISPLACEMENT_M`.
   The translated ellipse is where the material ends up.
8. **Mint ``landslide_id``** by location, ``LS<7 digits>``, within the
   realisation.
9. **Write two polygons per landslide**: **evacuated land**, the source the
   material left, and **inundated land**, where it came to rest, in the land
   classes of :mod:`landloss.hazard.landslide.land_class`.

Leave ``EXTENT = "wlg-pilot"`` in ``config.py`` while the model is being
changed; steps 3 and 5 must have been run over the same extent.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray
import shapely
from rasterio import features
from rasterio.enums import Resampling

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.common.utils.terrain import azimuth_offsets, cell_size
from landloss.domain import constants
from landloss.hazard.landslide.geometry import landslide_volume_m3, mean_depth_m
from landloss.hazard.landslide.ground_map import flatland_cell_mask
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.io.source_material import get_eil_landslide_probability
from scripts.landloss.ground.steps.s1_terrain import (
    gen_multiscale_slope,
    gen_terrain_derivatives,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s1_slope_units.gen_slope_units import (
    slope_units_path,
)
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997.gen_hancox_1997_coverage import (
    coverage_path as hancox_coverage_path,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import config
from scripts.landloss.hazard.landslide.steps.s8_kritikos_2015.gen_kritikos_2015_hazard import (
    coverage_path as kritikos_coverage_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised -- Owhiro Bay, Pauatahanui -- which the
# default cp1252 Windows console cannot encode, so printing one raises. Ask for
# UTF-8 rather than stripping the macrons, because the names are worth getting
# right.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. This is a working layer, rebuildable from the source grid
# and the ground step 1 and landslide step 1 layers, so it has no business in a diff.
WORK_DIR = TEMP_DIR / "hazard" / "landslide"

# Separate names, so a pilot run cannot overwrite a full one.
OUT_STEM = "landslide-realisation"

# The stream this step draws from. One name per hazard, not per script, so every
# script in the module draws from the same sequence for a given realisation.
RNG_STREAM = "landslide"

# Carried on every polygon so a layer can be paired with the shaking and
# liquefaction layers of the same modelled earthquake.
REALISATION_ID_COLUMN = "realisation_id"

# The working grid: the 10 m DEM grid the slope units were cut on. The selected
# model grid is put onto it so the units, topographic position and coverage
# share cells.
RESOLUTION_M = 10
TOPOGRAPHIC_POSITION_LAYER = "topographic-position-100m"

# Which population these rows belong to, and the two columns that pair a large
# row with an urban one in the combined realisation landslide step 6 writes. The urban
# model's rows carry `urban` and a `slope_id`; a large row carries `large`, its
# `unit_id`, and a null `slope_id`.
POPULATION_COLUMN = "population"
LARGE_POPULATION = "large"
UNIT_ID_COLUMN = "unit_id"
SLOPE_ID_COLUMN = "slope_id"
LANDSLIDE_ID_COLUMN = "landslide_id"

# The size distribution above the urban range. A bounded power law: the
# probability density of a source area falls as area to the power
# -SIZE_EXPONENT, between the lower bound config.LARGE_MIN_SOURCE_AREA_M2 (the
# top of the urban range) and MAX_SOURCE_AREA_M2 (a whole hillside).
#
# The exponent is the published one. Massey et al. (2020) [massey_2020] fit 2.1
# to the Kaikōura greywacke source polygons above a cutoff near 500 m², and the
# range drawn here lies wholly above that cutoff, so the fit applies as read.
# Phase 1 of this step carried 1.19 instead, because its single law stretched
# two decades below the cutoff and the exponent was the only free parameter
# controlling total area; neither holds now. The exponent sets the shape of the
# sizes and nothing else: the count per unit is drawn to deliver an expected
# area, so the total area does not move with it.
#
# The upper bound is at least the largest Wellington earthquake landslide on
# record: Gold's slide on the Hutt Road in 1855, about 300,000 m³
# [brabhaharan_2018] (the project lead, 2026-10-02, raised from 3,000 m²). It
# is set at 35,000 m² of source, about what the volume-area law gives for
# 300,000 m³ (34,000 m²). The mean source area on these settings is about
# 2,500 m², and about 60% of the large-failure area is in failures above
# 3,000 m².
MAX_SOURCE_AREA_M2 = 35_000.0
SIZE_EXPONENT = 2.1

# The share of a failing cell's area that becomes source. The supplied grid
# gives the probability that a cell fails and says nothing about how much of
# it goes; the phase 1 calibration of this step solved that backwards from the
# areal coverage cross-check -- an expected source area of 258 m² per failing
# 1,024 m² cell, which delivered 0.99% coverage over the graded area against
# the order of 1% Nowicki Jessee et al. (2018) [nowicki_jessee_2018] give for
# strong shaking in steep terrain. 258 / 1,024 is this fraction, kept so the
# expected failed area per unit, and with it the coverage, is what that
# calibration delivered. A beta placeholder: the calibration against the
# Kaikōura inventory (phase 2 of the plan) sets it.
BETA_SOURCE_AREA_FRACTION = 0.252

LARGE_MODELS = ("esnz", "hancox_1997", "kritikos_2015")

# How many of a unit's highest-weight cells a failure's seed is chosen among.
# A single best cell would seed every failure in the unit at the same place; a
# choice over the whole unit would ignore the weighting.
SEED_CANDIDATE_CELLS = 10

# The topographic position, in metres above the 100 m neighbourhood mean, at
# which the crest lift reaches its full value. A cell 10 m or more above its
# surroundings is a crest or a spur; a cell below its surroundings gets no
# lift at all, and a cell the derivative has no value for is treated as level.
CREST_FULL_LIFT_M = 10.0

# How far the material travels, as a function of slope alone. A straight ramp:
# MIN_DISPLACEMENT_M at or below MIN_DISPLACEMENT_SLOPE_DEG, MAX_DISPLACEMENT_M
# at or above MAX_DISPLACEMENT_SLOPE_DEG, linear between them. This stands in
# for a Newmark displacement, which would take the yield acceleration and the
# shaking rather than the slope on its own; the range is the one asked for. The
# anchors say a 10 degree slope barely moves its debris and a 45 degree one
# moves it the full distance, which is the right direction and is not calibrated.
MIN_DISPLACEMENT_M = 1.0
MAX_DISPLACEMENT_M = 40.0
MIN_DISPLACEMENT_SLOPE_DEG = 10.0
MAX_DISPLACEMENT_SLOPE_DEG = 45.0

# How much material the failure involved, and how deep it lies over the polygon
# that carries it. Both come from the volume-area power law rather than from the
# simulation, which samples areas and nothing else. The vulnerability step needs
# the depth because what a repair costs depends on how much has to be moved and
# not only on the footprint.
VOLUME_COLUMN = "volume_m3"
DEPTH_COLUMN = "depth_m"

# Vertices per quarter of the source ellipse. 16 gives a 64 sided polygon,
# within a tenth of a percent of a true ellipse -- and the axes are corrected
# for even that, so each polygon carries the area that was sampled.
ELLIPSE_SEGMENTS = 16

# The columns of the written layer, in order.
OUTPUT_COLUMNS = [
    REALISATION_ID_COLUMN,
    LANDSLIDE_ID_COLUMN,
    POPULATION_COLUMN,
    UNIT_ID_COLUMN,
    SLOPE_ID_COLUMN,
    LAND_CLASS_COLUMN,
    "seed_easting",
    "seed_northing",
    "easting",
    "northing",
    "failure_probability",
    "source_area_m2",
    "semi_major_m",
    "semi_minor_m",
    "slope_degrees",
    "downhill_azimuth_degrees",
    "displacement_m",
    "runout_easting",
    "runout_northing",
    VOLUME_COLUMN,
    DEPTH_COLUMN,
    "geometry",
]

# The quantiles the distributions are described at. Deciles rather than a mean
# and a standard deviation, because none of these are symmetric -- a power law
# least of all -- and the shape is the thing worth looking at.
DECILES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

HECTARE_M2 = 10_000.0

# How much of a polygon set has to lie over itself before the run says so. Set
# just below the smallest share that rounds to a tenth of a per cent, so the
# line appears when there is really something to dissolve and not when there is
# only rounding.
MIN_REPORTED_OVERLAP_PERCENT = 0.05

RULE = "-" * 72


def realisation_path(*, extent, realisation_id):
    """Return the file a run writes one realisation to.

    A function rather than a constant because the name depends on the extent and
    on which realisation it is. ``fig_landslide_realisation.py`` calls this too,
    which is what keeps the figure drawing the realisation the simulation
    actually wrote.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_id: Which modelled earthquake this is.

    Returns:
        The output path, under ``temp/hazard/landslide/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.geoparquet"


def input_paths(*, extent):
    """Return the landslide step 1 slope units, the ground step 2 ground map and the ground step 1 rasters."""
    return {
        "units": slope_units_path(extent=extent),
        "ground_map": ground_map_path(extent=extent),
        "dem": gen_multiscale_slope.dem_path(RESOLUTION_M, extent=extent),
        "slope": gen_multiscale_slope.slope_path(RESOLUTION_M, extent=extent),
        "aspect": gen_multiscale_slope.aspect_path(RESOLUTION_M, extent=extent),
        "topographic_position": gen_terrain_derivatives.terrain_path(
            TOPOGRAPHIC_POSITION_LAYER, extent=extent
        ),
    }


def resolve_extent(*, extent):
    """Return the bounding box and name of the extent to run over."""
    aoi = get_area_of_interest(extent)
    if aoi is not None:
        return aoi.bbox(constants.DEFAULT_CRS), aoi.name

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox = tuple(float(value) for value in study_areas.total_bounds)
    return bbox, "the four territorial authorities"


def read_grid(path):
    """Read one raster ground step 1 wrote, nodata as NaN, as a 2D array."""
    with rioxarray.open_rasterio(path, masked=True) as opened:
        grid = opened.squeeze("band", drop=True).load()
    grid.encoding.pop("_FillValue", None)
    return grid.rio.write_nodata(np.nan)


def read_probability(bbox):
    """Read the supplied probability grid over the extent, in the study's projection."""
    return get_eil_landslide_probability(bbox=bbox, crs=constants.DEFAULT_CRS)


def coverage_source_area_fraction(coverage_model):
    """Return the conversion from a model grid to expected source coverage."""
    if coverage_model == "esnz":
        return BETA_SOURCE_AREA_FRACTION
    if coverage_model in ("hancox_1997", "kritikos_2015"):
        return 1.0
    msg = f"large model must be one of {LARGE_MODELS}, not {coverage_model!r}"
    raise ValueError(msg)


def read_model_coverage(*, coverage_model, bbox, extent, realisation_id, template):
    """Read one large model's grid and align it to the placement grid."""
    if coverage_model == "esnz":
        supplied = read_probability(bbox)
    elif coverage_model == "hancox_1997":
        supplied = read_grid(hancox_coverage_path(realisation_id, extent=extent))
    elif coverage_model == "kritikos_2015":
        supplied = read_grid(kritikos_coverage_path(realisation_id, extent=extent))
    else:
        coverage_source_area_fraction(coverage_model)
    return align_probability(supplied, template)


def check_probabilities(probability):
    """Check the grid holds probabilities, and hand back the ones it has.

    A grid in percent, or one carrying a nodata marker that was never declared,
    reads as a perfectly ordinary array of numbers and would produce a perfectly
    ordinary looking set of landslides -- a hundred times too many of them. It is
    refused here rather than corrected, because which of the two it is changes
    the answer and only the supplier knows.

    Args:
        probability: The probability grid.

    Returns:
        The finite values in the grid, flattened.

    Raises:
        ValueError: If the grid is empty over this extent, or any value falls
            outside [0, 1].
    """
    values = probability.to_numpy()
    finite = values[np.isfinite(values)]

    if finite.size == 0:
        msg = (
            "The probability grid has no data at all over this extent. Check "
            "that the extent and the grid cover the same ground."
        )
        raise ValueError(msg)

    if finite.min() < 0 or finite.max() > 1:
        msg = (
            f"The probability grid runs from {finite.min():g} to "
            f"{finite.max():g}, which is not a probability. If it is in per "
            "cent, or carries an undeclared nodata marker, confirm which with "
            "the supplier and convert it there rather than here."
        )
        raise ValueError(msg)

    return finite


def align_probability(probability, template):
    """Resample the probability grid onto the working grid, nearest neighbour.

    Nearest rather than bilinear: a probability is a property of the supplied
    cell, and smoothing it across cell edges would move chance onto ground the
    supplier gave none to. Each 10 m cell takes the value of the 32 m cell it
    falls in, so a unit's sum over its 10 m cells is the supplied grid's own
    sum over the same ground.

    Args:
        probability: The supplied grid, nodata as NaN.
        template: The 10 m DEM the slope units were cut on.

    Returns:
        The probability on ``template``'s cells, NaN where the grid has none.
    """
    aligned = probability.rio.reproject_match(template, resampling=Resampling.nearest)
    nodata = aligned.rio.nodata
    if nodata is not None and np.isfinite(nodata):
        aligned = aligned.where(aligned != nodata)
    return aligned.assign_coords(x=template["x"], y=template["y"])


def flatland_mask(ground_map, template):
    """Return True on the working-grid cells whose centre lies on flat land.

    Flat land is every ground map piece with ``is_flatland`` true, which the
    ground map takes from the NLM flatland release. A cell is flat where its
    centre falls in one, the default rasterisation rule.

    Args:
        ground_map: The ground step 2 ground map, carrying ``is_flatland``.
        template: The working grid, a ``(y, x)`` raster with a transform.

    Returns:
        A boolean array of the template's shape.
    """
    return flatland_cell_mask(ground_map, template)


def mask_flatland(probability, on_flatland):
    """Set the probability to NaN on flat land, so no large landslide starts there.

    Args:
        probability: The probability on the working grid.
        on_flatland: :func:`flatland_mask` on the same grid.

    Returns:
        The probability, NaN on every flat cell and unchanged elsewhere.
    """
    return probability.where(~on_flatland)


def describe_flatland_mask(probability, on_flatland):
    """Print how many cells, and how much of the grid's chance, the mask removes."""
    values = probability.to_numpy()
    carrying = np.isfinite(values)
    removed = carrying & on_flatland
    total = float(np.nansum(values))
    share = float(np.nansum(np.where(removed, values, 0.0))) / total if total else 0.0
    print(RULE)
    print("Flat land masked (no large landslide starts on NLM flatland):")
    print(
        f"  {int(removed.sum()):,} of {int(carrying.sum()):,} cells carrying a probability"
    )
    print(f"  {share:.1%} of the grid's summed probability removed")


def unit_labels(units, template):
    """Burn the slope units onto the working grid, one label per unit.

    Args:
        units: The slope units, in the grid's projection.
        template: The raster whose cells the labels are on.

    Returns:
        An integer array on ``template``'s shape: the unit's position in
        ``units`` plus one, or 0 where no unit covers the cell centre.
    """
    if units.empty:
        return np.zeros(template.shape, dtype=np.int32)
    return features.rasterize(
        zip(units.geometry, range(1, len(units) + 1), strict=True),
        out_shape=template.shape,
        transform=template.rio.transform(),
        fill=0,
        dtype="int32",
    )


def expected_failed_area_m2(
    probability,
    labels,
    unit_count,
    *,
    cell_area_m2,
    source_area_fraction,
    urban_area_share,
):
    """Sum the expected source area of the large population over each unit's cells.

    A cell with no probability contributes nothing, so a unit the supplied grid
    does not reach expects no failure and is never seeded.

    Args:
        probability: The probability on the working grid.
        labels: The unit label per cell, from :func:`unit_labels`.
        unit_count: How many units there are.
        cell_area_m2: The area of one working cell.
        source_area_fraction: The share of a failing cell's area that becomes
            source, :data:`BETA_SOURCE_AREA_FRACTION`.
        urban_area_share: The share of the failed area the urban model draws
            instead, taken off here.

    Returns:
        The expected failed area in square metres, one value per unit in
        label order.
    """
    chance = np.where(np.isfinite(probability), probability, 0.0).ravel()
    weight = chance * cell_area_m2 * source_area_fraction * (1.0 - urban_area_share)
    sums = np.bincount(labels.ravel(), weights=weight, minlength=unit_count + 1)
    return sums[1:]


def truncated_power_law_mean_m2(min_area_m2, max_area_m2, exponent):
    """Return the mean of the bounded power law with density proportional to area^-exponent.

    Args:
        min_area_m2: The lower bound.
        max_area_m2: The upper bound.
        exponent: The exponent of the density, :data:`SIZE_EXPONENT`.

    Returns:
        The mean source area in square metres.

    Raises:
        ValueError: If the bounds are not positive and increasing.
    """
    if not 0 < min_area_m2 < max_area_m2:
        msg = (
            f"the size bounds must be positive and increasing, got "
            f"[{min_area_m2:g}, {max_area_m2:g}]"
        )
        raise ValueError(msg)

    def moment(power):
        if np.isclose(power, 0.0):
            return np.log(max_area_m2 / min_area_m2)
        return (max_area_m2**power - min_area_m2**power) / power

    return moment(2.0 - exponent) / moment(1.0 - exponent)


def sample_areas(
    count, rng, *, min_area_m2, max_area_m2=MAX_SOURCE_AREA_M2, exponent=SIZE_EXPONENT
):
    """Draw source areas from the bounded power law.

    Drawn by inverting the cumulative distribution, so every draw costs one
    uniform variate and the limits are exact rather than approached by
    rejection.

    Args:
        count: How many areas to draw.
        rng: The random number generator.
        min_area_m2: The lower bound, ``config.LARGE_MIN_SOURCE_AREA_M2``.
        max_area_m2: The upper bound.
        exponent: The exponent of the density.

    Returns:
        Source areas in square metres, between the two bounds.
    """
    power = 1.0 - exponent
    low = min_area_m2**power
    high = max_area_m2**power
    uniform = rng.random(count)
    return (low + uniform * (high - low)) ** (1.0 / power)


def draw_counts(expected_area_m2, mean_area_m2, rng):
    """Draw how many failures each unit has, Poisson on its expected area.

    Args:
        expected_area_m2: The expected failed area per unit.
        mean_area_m2: The mean size of the law the sizes are drawn from.
        rng: The random number generator.

    Returns:
        An integer count per unit.
    """
    return rng.poisson(np.asarray(expected_area_m2, dtype=float) / mean_area_m2)


def seeding_weight(probability, topographic_position, *, crest_weight):
    """Weight each cell for seeding: its probability, lifted toward the crest.

    The lift is ``1 + crest_weight * clip(TPI / CREST_FULL_LIFT_M, 0, 1)``: a
    cell at or above a crest's position gets the full lift, one below its
    surroundings none. The derivative has no value within half a window of the
    extent edge, and a cell with none is treated as level rather than dropped.

    Args:
        probability: The probability on the working grid.
        topographic_position: The 100 m topographic position on the same grid.
        crest_weight: ``config.CREST_WEIGHT``.

    Returns:
        The weight per cell, 0 where the grid has no probability.
    """
    chance = np.where(np.isfinite(probability), probability, 0.0)
    position = np.where(np.isfinite(topographic_position), topographic_position, 0.0)
    lift = 1.0 + crest_weight * np.clip(position / CREST_FULL_LIFT_M, 0.0, 1.0)
    return chance * lift


def seed_cells(labels, weight, counts, rng, *, candidate_cells=SEED_CANDIDATE_CELLS):
    """Choose the seed cell of every failure, unit by unit.

    Within a unit the candidates are its highest-weight cells -- the top
    ``candidate_cells``, or as many as there are failures to seed when that is
    more -- and each failure's seed is a weighted choice among them, without
    replacement, so two failures in one unit do not start from the same cell.
    A unit with fewer candidates than failures reuses cells, and
    :func:`drop_overlapping` then keeps the larger of the pair.

    Args:
        labels: The unit label per cell, from :func:`unit_labels`.
        weight: The seeding weight per cell, from :func:`seeding_weight`.
        counts: The failure count per unit, from :func:`draw_counts`.
        rng: The random number generator.
        candidate_cells: How many of the top cells the choice is made over.

    Returns:
        ``(unit_index, rows, columns)``: the zero-based unit of every failure
        and the cell it is seeded at, failures in unit order.
    """
    flat_labels = labels.ravel()
    flat_weight = weight.ravel()
    order = np.argsort(flat_labels, kind="stable")
    starts = np.searchsorted(flat_labels[order], np.arange(1, counts.size + 2))

    unit_index, cells = [], []
    for unit, count in enumerate(counts):
        if count == 0:
            continue
        members = order[starts[unit] : starts[unit + 1]]
        member_weight = flat_weight[members]
        positive = member_weight > 0
        if not positive.any():
            continue
        members, member_weight = members[positive], member_weight[positive]

        top = max(candidate_cells, int(count))
        if members.size > top:
            best = np.argpartition(-member_weight, top - 1)[:top]
            members, member_weight = members[best], member_weight[best]

        chosen = rng.choice(
            members,
            size=int(count),
            replace=int(count) > members.size,
            p=member_weight / member_weight.sum(),
        )
        unit_index.append(np.full(chosen.size, unit))
        cells.append(chosen)

    if not cells:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty, empty
    flat = np.concatenate(cells)
    rows, columns = np.unravel_index(flat, labels.shape)
    return np.concatenate(unit_index), rows, columns


def ellipse_axes(area_m2, aspect_ratio):
    """Return the semi-axes of the source ellipse carrying an area.

    A :data:`ELLIPSE_SEGMENTS`-per-quarter polygon inscribed in an ellipse
    encloses slightly less than pi a b, and the axes are stretched to make up
    the difference, because area is the quantity the loss model reads and a
    polygon that does not carry the area that was sampled is a small lie that
    would have to be explained every time the two were compared.

    Args:
        area_m2: The area each polygon should enclose.
        aspect_ratio: The long axis over the short axis.

    Returns:
        ``(semi_major_m, semi_minor_m)``.
    """
    sides = 4 * ELLIPSE_SEGMENTS
    inscribed_ratio = 0.5 * sides * np.sin(2 * np.pi / sides) / np.pi
    semi_major = np.sqrt(np.asarray(area_m2, dtype=float) * aspect_ratio / np.pi)
    semi_major = semi_major / np.sqrt(inscribed_ratio)
    return semi_major, semi_major / aspect_ratio


def ellipses(eastings, northings, semi_major, semi_minor, azimuth_degrees):
    """Build one ellipse per centre, long axis along the azimuth.

    Args:
        eastings: The centre eastings.
        northings: The centre northings.
        semi_major: The semi-axis along the azimuth, per ellipse.
        semi_minor: The semi-axis across it, per ellipse.
        azimuth_degrees: The bearing of the long axis, clockwise from north.

    Returns:
        An array of polygons, one per centre.
    """
    eastings = np.atleast_1d(np.asarray(eastings, dtype=float))[:, None]
    northings = np.atleast_1d(np.asarray(northings, dtype=float))[:, None]
    semi_major = np.atleast_1d(np.asarray(semi_major, dtype=float))[:, None]
    semi_minor = np.atleast_1d(np.asarray(semi_minor, dtype=float))[:, None]
    radians = np.radians(np.atleast_1d(np.asarray(azimuth_degrees, dtype=float)))[
        :, None
    ]

    angles = np.linspace(0.0, 2 * np.pi, 4 * ELLIPSE_SEGMENTS, endpoint=False)[None, :]
    along = semi_major * np.cos(angles)
    across = semi_minor * np.sin(angles)
    east = eastings + along * np.sin(radians) + across * np.cos(radians)
    north = northings + along * np.cos(radians) - across * np.sin(radians)
    if eastings.size == 0:
        return np.empty(0, dtype=object)
    return shapely.polygons(np.stack([east, north], axis=-1))


def displacement_from_slope(slope_values):
    """Convert slope in degrees to how far the material travels, in metres.

    Args:
        slope_values: Slope at each failure, in degrees.

    Returns:
        Displacement in metres, between :data:`MIN_DISPLACEMENT_M` and
        :data:`MAX_DISPLACEMENT_M`. NaN slope carries through as NaN.
    """
    span = MAX_DISPLACEMENT_SLOPE_DEG - MIN_DISPLACEMENT_SLOPE_DEG
    fraction = np.clip((slope_values - MIN_DISPLACEMENT_SLOPE_DEG) / span, 0.0, 1.0)
    return MIN_DISPLACEMENT_M + fraction * (MAX_DISPLACEMENT_M - MIN_DISPLACEMENT_M)


def build_failures(
    probability,
    slope,
    aspect,
    topographic_position,
    units,
    rng,
    *,
    min_source_area_m2,
    source_area_fraction,
    urban_area_share,
    source_aspect_ratio,
    crest_weight,
):
    """Draw the failures of every unit: how many, how big, where, and where they end.

    The terrain at the seed decides the ellipse's direction and the runout. A
    seed whose cell has no downhill azimuth or no slope -- level ground, or a
    hole at the extent edge -- takes its unit's circular mean aspect and mean
    slope instead, so a unit the grid expects failures in always places them.

    Args:
        probability: The probability on the working grid.
        slope: The 10 m slope in degrees, on the same grid.
        aspect: The 10 m downhill azimuth in degrees, on the same grid.
        topographic_position: The 100 m topographic position, on the same grid.
        units: The slope units, carrying ``unit_id``, ``mean_slope_degrees``
            and ``mean_aspect_degrees``.
        rng: The random number generator.
        min_source_area_m2: The lower bound of the size law.
        source_area_fraction: The share of the model value that is expected
            source coverage.
        urban_area_share: The share of the failed area the urban model draws.
        source_aspect_ratio: The long axis over the short axis of a source.
        crest_weight: How much the topographic position lifts the seeding.

    Returns:
        ``(failures, per_unit)``: a GeoDataFrame of failures whose geometry is
        the source ellipse, and a DataFrame on the units' index carrying each
        unit's ``expected_area_m2`` and drawn ``count``.
    """
    template = probability
    labels = unit_labels(units, template)
    cell_area_m2 = cell_size(template) ** 2

    expected = expected_failed_area_m2(
        probability.to_numpy(),
        labels,
        len(units),
        cell_area_m2=cell_area_m2,
        source_area_fraction=source_area_fraction,
        urban_area_share=urban_area_share,
    )
    mean_area_m2 = truncated_power_law_mean_m2(
        min_source_area_m2, MAX_SOURCE_AREA_M2, SIZE_EXPONENT
    )
    counts = draw_counts(expected, mean_area_m2, rng)
    per_unit = pd.DataFrame(
        {"expected_area_m2": expected, "count": counts}, index=units.index
    )

    weight = seeding_weight(
        probability.to_numpy(),
        topographic_position.to_numpy(),
        crest_weight=crest_weight,
    )
    unit_index, rows, columns = seed_cells(labels, weight, counts, rng)

    seed_eastings = template["x"].to_numpy()[columns]
    seed_northings = template["y"].to_numpy()[rows]
    probabilities = probability.to_numpy()[rows, columns]

    slope_values = slope.to_numpy()[rows, columns]
    azimuth_values = aspect.to_numpy()[rows, columns]
    unit_slope = units["mean_slope_degrees"].to_numpy()[unit_index]
    unit_aspect = units["mean_aspect_degrees"].to_numpy()[unit_index]
    slope_values = np.where(np.isfinite(slope_values), slope_values, unit_slope)
    azimuth_values = np.where(np.isfinite(azimuth_values), azimuth_values, unit_aspect)

    areas = sample_areas(rows.size, rng, min_area_m2=min_source_area_m2)
    semi_major, semi_minor = ellipse_axes(areas, source_aspect_ratio)

    # The seed is the crest of the source: the ellipse is centred half a long
    # axis downslope of it, so its uphill tip is the seed cell.
    centre_east, centre_north = azimuth_offsets(azimuth_values, semi_major)
    eastings = seed_eastings + centre_east
    northings = seed_northings + centre_north

    displacement = displacement_from_slope(slope_values)
    east_offset, north_offset = azimuth_offsets(azimuth_values, displacement)

    failures = gpd.GeoDataFrame(
        {
            UNIT_ID_COLUMN: units[UNIT_ID_COLUMN].to_numpy()[unit_index],
            "seed_easting": seed_eastings,
            "seed_northing": seed_northings,
            "easting": eastings,
            "northing": northings,
            "failure_probability": probabilities,
            "source_area_m2": areas,
            "semi_major_m": semi_major,
            "semi_minor_m": semi_minor,
            "slope_degrees": slope_values,
            "downhill_azimuth_degrees": azimuth_values,
            "displacement_m": displacement,
            "runout_easting": eastings + east_offset,
            "runout_northing": northings + north_offset,
        },
        geometry=ellipses(eastings, northings, semi_major, semi_minor, azimuth_values),
        crs=template.rio.crs,
    )
    return failures, per_unit


def drop_overlapping(failures):
    """Drop every failure whose source overlaps a larger one, keeping the larger.

    The overlap rule is applied to the **source** areas and nowhere else, and
    that is a decision rather than an oversight. Two landslides cannot start
    from the same ground, so overlapping sources are not a thing that happens.
    Two landslides can perfectly well finish on the same ground -- a pair either
    side of a gully both run into its floor -- so overlapping runouts are left
    alone. A failure dropped here takes its runout with it, because
    :func:`to_polygons` only ever sees the survivors.

    Worked largest first, so a failure survives only if nothing bigger than
    itself survived and reached it. A failure that has already been dropped
    cannot drop anything else -- otherwise one large landslide would clear a
    hole far wider than itself, through a chain of failures none of which
    happened.

    Args:
        failures: The sampled failures, indexed from zero, whose geometry is the
            source ellipse.

    Returns:
        The failures that survive, in their original order.
    """
    if failures.empty:
        return failures

    geometries = failures.geometry.to_numpy()
    areas = failures["source_area_m2"].to_numpy()
    tree = shapely.STRtree(geometries)

    # Stable, so that two failures of exactly the same area resolve the same way
    # on every run rather than however the sort happened to order them.
    order = np.argsort(-areas, kind="stable")
    dropped = np.zeros(areas.size, dtype=bool)

    for index in order:
        if dropped[index]:
            continue
        for other in tree.query(geometries[index], predicate="intersects"):
            if other != index:
                dropped[other] = True

    return failures[~dropped]


def mint_landslide_ids(failures):
    """Number the surviving failures by location and give each its ``landslide_id``.

    Args:
        failures: The survivors of :func:`drop_overlapping`.

    Returns:
        The failures sorted by their source's representative point, with
        ``landslide_id`` (``LS<7 digits>``) inserted first and a fresh index.
    """
    ordered = sort_by_point(failures)
    ids = mint_ids(constants.LARGE_LANDSLIDE_ID_PREFIX, len(ordered))
    ordered.insert(0, LANDSLIDE_ID_COLUMN, ids.to_numpy())
    return ordered


def to_polygons(failures):
    """Expand each failure into its evacuated and its inundated polygon.

    Only the survivors of :func:`drop_overlapping` reach here, which is how a
    dropped failure loses its runout as well as its source: a landslide that did
    not happen cannot have buried anything. So no two evacuated polygons in the
    result overlap, and inundated ones may.

    Args:
        failures: The surviving failures, carrying ``landslide_id``, whose
            geometry is the source ellipse.

    Returns:
        Two rows per failure, told apart by :data:`LAND_CLASS_COLUMN`.
    """
    evacuated = failures.assign(**{LAND_CLASS_COLUMN: EVACUATED})

    # The same ellipse at the runout centre: the source translated downhill.
    # Rebuilt from its centre, axes and azimuth rather than moved, because an
    # ellipse is defined by those and rebuilding cannot drift from the source
    # polygon the way a separate translation could. The debris keeps the
    # source's shape and area, so the material that left is the material that
    # lands and the two depths come out identical.
    inundated = gpd.GeoDataFrame(
        failures.drop(columns=[failures.geometry.name]).assign(
            **{LAND_CLASS_COLUMN: INUNDATED}
        ),
        geometry=ellipses(
            failures["runout_easting"],
            failures["runout_northing"],
            failures["semi_major_m"],
            failures["semi_minor_m"],
            failures["downhill_azimuth_degrees"],
        ),
        crs=failures.crs,
    )

    both = pd.concat([evacuated, inundated], ignore_index=True)

    # Volume is conserved through the runout -- the material that left the
    # source is the material that lands -- so it is computed once from the
    # source area and then spread over whichever footprint the row carries.
    both[VOLUME_COLUMN] = landslide_volume_m3(both["source_area_m2"].to_numpy())
    both[DEPTH_COLUMN] = mean_depth_m(
        both[VOLUME_COLUMN].to_numpy(), both.geometry.area.to_numpy()
    )
    both[POPULATION_COLUMN] = LARGE_POPULATION
    both[SLOPE_ID_COLUMN] = pd.Series(pd.NA, index=both.index, dtype="string")
    return both.sort_values([LANDSLIDE_ID_COLUMN, LAND_CLASS_COLUMN]).reset_index(
        drop=True
    )


def describe_extent(name, probability):
    """Print what is being run over, and the working grid."""
    west, south, east, north = (float(v) for v in probability.rio.bounds())
    print(RULE)
    print(f"Extent: {name}")
    print(f"  {west:,.0f} - {east:,.0f} E, {south:,.0f} - {north:,.0f} N")
    print(f"  {(east - west) / 1000:,.1f} by {(north - south) / 1000:,.1f} km")
    print(
        f"Working grid: {probability.shape[0]:,} by {probability.shape[1]:,} "
        f"cells at {cell_size(probability):g} m, in {probability.rio.crs}"
    )


def describe_probabilities(finite, resolution, cells):
    """Print the probability distribution on the working grid."""
    print(RULE)
    print(f"Cells carrying a probability: {finite.size:,} of {cells:,}")
    print(
        f"  min {finite.min():.2e}, median {np.median(finite):.2e}, "
        f"mean {finite.mean():.2e}, max {finite.max():.2e}"
    )
    print(
        f"  the grid's own expected failed area, before the fraction and the "
        f"urban share: {finite.sum() * resolution**2 / HECTARE_M2:,.1f} ha"
    )


def describe_settings(
    *,
    min_source_area_m2,
    source_area_fraction,
    urban_area_share,
    source_aspect_ratio,
    crest_weight,
):
    """Print the placement settings the run used, and the size law they imply."""
    mean_area_m2 = truncated_power_law_mean_m2(
        min_source_area_m2, MAX_SOURCE_AREA_M2, SIZE_EXPONENT
    )
    print(RULE)
    print("Placement settings:")
    print(
        f"  size law: area^-{SIZE_EXPONENT:g} on [{min_source_area_m2:,.0f}, "
        f"{MAX_SOURCE_AREA_M2:,.0f}] m2, mean {mean_area_m2:,.0f} m2"
    )
    print(f"  source area fraction of a failing cell: {source_area_fraction:g}")
    print(f"  urban area share taken off: {urban_area_share:g}")
    print(f"  source aspect ratio: {source_aspect_ratio:g}")
    print(f"  crest weight: {crest_weight:g}")


def describe_units(units, per_unit):
    """Print the units and what the grid expects in them."""
    expected = per_unit["expected_area_m2"]
    counts = per_unit["count"]
    unit_area = float(units["area_m2"].sum())
    coverage = 100 * expected.sum() / unit_area if unit_area > 0 else 0.0
    print(RULE)
    print(
        f"Slope units: {len(units):,}, {int((expected > 0).sum()):,} expecting a failure"
    )
    print(
        f"  expected failed area: {expected.sum() / HECTARE_M2:,.2f} ha over "
        f"{unit_area / HECTARE_M2:,.1f} ha of units ({coverage:.2f}% coverage)"
    )
    print(
        f"  failures drawn: {int(counts.sum()):,} in {int((counts > 0).sum()):,} "
        f"units, at most {int(counts.max()) if len(counts) else 0:,} in one unit"
    )


def describe_distribution(values, label, units):
    """Print the deciles of a distribution, the shape being the arguable part."""
    values = pd.Series(np.asarray(values, dtype=float)).dropna()
    if values.empty:
        print(f"{label}: nothing to describe.")
        return

    quantiles = values.quantile(DECILES)
    print(f"{label} ({units}):")
    print(
        "  " + "  ".join(f"{int(q * 100):>3}%={v:,.1f}" for q, v in quantiles.items())
    )
    print(f"  mean {values.mean():,.1f}, total {values.sum():,.0f}")


def describe_result(polygons):
    """Print the ground the two polygon sets cover, which is what the loss model reads.

    The two are measured differently on purpose, and the asymmetry is the point.
    :func:`drop_overlapping` has already made the evacuated polygons pairwise
    disjoint, so their summed area *is* the ground they cover. Nothing
    guarantees the same of the inundated polygons: they are those same ellipses
    moved different distances in different directions, so two failures either
    side of a gully both land in its floor. Ground buried by two landslides is
    buried once, and anything summing inundated area without dissolving first
    counts it twice.
    """
    print(RULE)
    for land_class in (EVACUATED, INUNDATED):
        subset = polygons[polygons[LAND_CLASS_COLUMN] == land_class]
        if subset.empty:
            print(f"{land_class}: none.")
            continue

        summed = subset.geometry.area.sum()
        if land_class == EVACUATED:
            print(
                f"{land_class}: {len(subset):,} polygons, "
                f"{summed / HECTARE_M2:,.2f} ha, none of it overlapping"
            )
            continue

        distinct = subset.geometry.union_all().area
        print(
            f"{land_class}: {len(subset):,} polygons, "
            f"{summed / HECTARE_M2:,.2f} ha summed, "
            f"{distinct / HECTARE_M2:,.2f} ha of distinct ground"
        )

        # Said in words as well as in two numbers, because the difference is a
        # trap rather than a detail. Tested against a threshold rather than
        # against zero: dissolving 64 sided polygons leaves floating point dust
        # behind, and a line reporting "0.0% overlap" on every run would teach
        # everyone to ignore the line.
        share = 100 * (summed - distinct) / summed
        if share >= MIN_REPORTED_OVERLAP_PERCENT:
            print(
                f"  {share:.1f}% of that is runout polygons lying over one "
                "another -- dissolve before summing"
            )

    # Reported because the depth is what the vulnerability step multiplies, and
    # it comes from a power law whose coefficient is still a placeholder. Seeing
    # the numbers each run is the cheapest guard against that going unnoticed.
    source = polygons[polygons[LAND_CLASS_COLUMN] == EVACUATED]
    if not source.empty:
        describe_distribution(source[VOLUME_COLUMN], "landslide volume", "m3")
        describe_distribution(source[DEPTH_COLUMN], "mean depth", "m")


def main(
    *,
    extent,
    realisation_ids,
    coverage_model,
    large_min_source_area_m2,
    urban_area_share,
    source_aspect_ratio,
    crest_weight,
):
    """Draw a realisation of large landslides per id and write each one out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to draw.
        coverage_model: Which large-landslide coverage grid to place.
        large_min_source_area_m2: The smallest source the large population
            draws; the top of the urban range.
        urban_area_share: The share of the failed area the urban model draws,
            taken off the expected area here.
        source_aspect_ratio: The long axis over the short axis of a source.
        crest_weight: How much the 100 m topographic position lifts a cell's
            seeding weight.
    """
    bbox, extent_name = resolve_extent(extent=extent)
    paths = input_paths(extent=extent)
    print(RULE)
    print(f"Extent    : {extent_name}")
    for name, path in paths.items():
        print(f"  {name:<21}: {path}")

    units = gpd.read_parquet(paths["units"])
    ground_map = gpd.read_parquet(paths["ground_map"])
    dem = read_grid(paths["dem"])
    slope = read_grid(paths["slope"])
    aspect = read_grid(paths["aspect"])
    topographic_position = read_grid(paths["topographic_position"])

    source_area_fraction = coverage_source_area_fraction(coverage_model)
    on_flatland = flatland_mask(ground_map, dem)
    describe_extent(extent_name, dem)
    describe_settings(
        min_source_area_m2=large_min_source_area_m2,
        source_area_fraction=source_area_fraction,
        urban_area_share=urban_area_share,
        source_aspect_ratio=source_aspect_ratio,
        crest_weight=crest_weight,
    )

    for realisation_id in realisation_ids:
        print(
            f"Reading {coverage_model} large-landslide coverage for "
            f"realisation {realisation_id} ...",
            flush=True,
        )
        probability = read_model_coverage(
            coverage_model=coverage_model,
            bbox=bbox,
            extent=extent,
            realisation_id=realisation_id,
            template=dem,
        )
        finite = check_probabilities(probability)
        describe_flatland_mask(probability, on_flatland)
        probability = mask_flatland(probability, on_flatland)
        describe_probabilities(finite, cell_size(probability), probability.size)
        draw_realisation(
            probability,
            slope,
            aspect,
            topographic_position,
            units,
            extent=extent,
            realisation_id=realisation_id,
            large_min_source_area_m2=large_min_source_area_m2,
            source_area_fraction=source_area_fraction,
            urban_area_share=urban_area_share,
            source_aspect_ratio=source_aspect_ratio,
            crest_weight=crest_weight,
        )


def draw_realisation(
    probability,
    slope,
    aspect,
    topographic_position,
    units,
    *,
    extent,
    realisation_id,
    large_min_source_area_m2,
    source_area_fraction,
    urban_area_share,
    source_aspect_ratio,
    crest_weight,
):
    """Draw one modelled earthquake's large landslides and write them out.

    The generator comes from the project seed and the realisation id rather than
    from a seed of this step's own, so the landslides of realisation 3 belong to
    the same earthquake as the shaking and liquefaction of realisation 3.

    Args:
        probability: The per-cell probability of slope failure, on the working grid.
        slope: Slope in degrees, on the same grid.
        aspect: Downhill azimuth in degrees, on the same grid.
        topographic_position: The 100 m topographic position, on the same grid.
        units: The slope units.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_id: Which modelled earthquake this is.
        large_min_source_area_m2: The lower bound of the size law.
        source_area_fraction: The share of the model value that is source area.
        urban_area_share: The share of the failed area the urban model draws.
        source_aspect_ratio: The long axis over the short axis of a source.
        crest_weight: How much the topographic position lifts the seeding.
    """
    out_path = realisation_path(extent=extent, realisation_id=realisation_id)
    print(RULE)
    print(f"Realisation {realisation_id}")

    rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
    failures, per_unit = build_failures(
        probability,
        slope,
        aspect,
        topographic_position,
        units,
        rng,
        min_source_area_m2=large_min_source_area_m2,
        source_area_fraction=source_area_fraction,
        urban_area_share=urban_area_share,
        source_aspect_ratio=source_aspect_ratio,
        crest_weight=crest_weight,
    )
    describe_units(units, per_unit)

    survivors = drop_overlapping(failures)
    print(
        f"  {len(failures) - len(survivors):,} dropped for overlapping a larger "
        f"failure, leaving {len(survivors):,}"
    )

    polygons = to_polygons(mint_landslide_ids(survivors))
    polygons[REALISATION_ID_COLUMN] = realisation_id
    polygons = polygons[OUTPUT_COLUMNS]

    # No failures is a result, and it is written as one: an empty layer with the
    # full schema, so every step reading this realisation finds a file and
    # reports nothing damaged rather than stopping on a missing input.
    if failures.empty:
        print("\nNothing failed in this realisation; writing an empty layer.")
    else:
        print(RULE)
        describe_distribution(survivors["source_area_m2"], "Source area", "m2")
        describe_distribution(survivors["slope_degrees"], "Slope", "degrees")
        describe_distribution(survivors["displacement_m"], "Displacement", "m")
        describe_result(polygons)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    polygons.to_parquet(out_path)
    print(f"Wrote {len(polygons):,} polygons to {out_path}")
    print(
        f"Seed {constants.BASE_SEED}, realisation {realisation_id}, stream "
        f"{RNG_STREAM!r}; the same three reproduce it exactly."
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        coverage_model=config.COVERAGE_MODEL,
        large_min_source_area_m2=config.LARGE_MIN_SOURCE_AREA_M2,
        urban_area_share=config.URBAN_AREA_SHARE,
        source_aspect_ratio=config.SOURCE_ASPECT_RATIO,
        crest_weight=config.CREST_WEIGHT,
    )
