"""Expand the National Liquefaction Model's two land damage grids into six states.

The study reports land damage on a six state scale -- None, Minor, Moderate,
Major, Severe, Very Severe -- and the National Liquefaction Model release in
hand carries two grids: P(at least Moderate) and P(at least Major). This step
turns the pair into one probability grid per state, over the study extent:

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/steps/s2_ld_probabilities/gen_liq_ld_probabilities.py

What it runs over comes from ``config.py`` beside it, read at the bottom of this
file and passed into :func:`main`. Change it there rather than passing flags, so
that what a run did can be read off the source.

Three things happen, and only the first of them is arithmetic nobody argues
with.

1. **Clip and reproject.** The NLM grids are national and arrive on their own
   grid; ``landloss.io.nlm`` reads them as delivered. They are clipped in their
   own projection first and reprojected afterwards, so a small extent stays
   cheap, and the Major grid is then matched cell for cell onto the Moderate
   one. Nearest neighbour throughout: these are probabilities attached to
   cells, and interpolating between two of them invents a third.
2. **Difference the exceedance pair into bands.** P(at least Moderate) is not
   the Moderate band, and reading it as one would count the Major mass twice.
   :func:`landloss.hazard.liquefaction.land_damage.exceedance_to_bands` does the
   subtraction and refuses a swapped pair.
3. **Subdivide the None and Major bands** into the four states the NLM does not
   supply. This is the beta shortcut: the shares have no evidence behind them
   and exist to give the chain a six state grid of the right shape. Everything
   carrying the ``beta_`` prefix -- the library function, the path helper here,
   and the ``beta-`` in every file name this step writes -- goes when the NLM
   supplies the full scale itself.

The output is six GeoTIFFs under ``temp/hazard/liquefaction/``, one per state,
on the extent's own grid. ``s3_ld_states/gen_liq_ld_states.py`` reads them and
draws a state per cell from them.

Needs the T: drive, which is where the NLM release tree lives.
"""

import geopandas as gpd
import numpy as np

# Imported for the side effect of registering the ``.rio`` accessor the clip and
# the reprojection below use; the name itself is never referenced.
import rioxarray  # noqa: F401
from pyproj import CRS
from rasterio.enums import Resampling
from rioxarray.exceptions import NoDataInBounds, OneDimensionalRaster

from landloss.common.utils.raster import bbox_in_crs
from landloss.common.utils.terrain import cell_size, write_raster
from landloss.domain import constants
from landloss.hazard.liquefaction.land_damage import (
    LD_STATES,
    beta_expand_ld_probabilities,
)
from landloss.hazard.liquefaction.lateral_spreading import (
    ZONES,
    apply_lateral_spreading,
    far_weight_grid,
    lateral_spreading_zones,
    zone_grid,
)
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.io.nlm import (
    get_nlm_scenario_rp2500y_gwd_med_p_ld_major_fu,
    get_nlm_scenario_rp2500y_gwd_med_p_ld_moderate_fu,
)
from scripts.landloss.hazard.liquefaction.steps.s1_free_faces.gen_liq_free_faces import (
    free_faces_path,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities import config
from scripts.landloss.paths import TEMP_DIR

# temp/ is gitignored. These are working layers, rebuildable from the NLM
# release, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "hazard" / "liquefaction"

# Every file this step writes is named ``beta-``, because four of the six states
# in it were manufactured here rather than modelled. A file named this way is a
# file to delete when the NLM supplies the full scale.
OUT_PREFIX = "beta-ld-probability"

RULE = "-" * 72


def state_slug(state: str) -> str:
    """Return a state's name in the form a file name can carry.

    Args:
        state: One of :data:`landloss.hazard.liquefaction.land_damage.LD_STATES`.

    Returns:
        The name lowercased with its spaces hyphenated, e.g. ``very-severe``.
    """
    return state.lower().replace(" ", "-")


def beta_probability_path(state, *, extent):
    """Return the file a run writes one state's probability grid to.

    A function rather than six constants because the name depends on the extent,
    and the extent is an argument. ``gen_liq_ld_states.py`` calls this too, which
    is what keeps step 3 drawing from the grids this step actually wrote.

    The ``beta_`` in the name is deliberate and matches
    :func:`landloss.hazard.liquefaction.land_damage.beta_expand_ld_probabilities`:
    these grids hold four states the NLM does not model.

    Args:
        state: One of :data:`landloss.hazard.liquefaction.land_damage.LD_STATES`.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/hazard/liquefaction/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_PREFIX}-{state_slug(state)}{suffix}.tif"


def resolve_extent(study_areas, *, extent):
    """Choose the extent to run over, and say which one it is.

    Args:
        study_areas: The four territorial authorities.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        ``(bbox, name)``: the extent in the study's own projection, and a label
        for the run output.
    """
    aoi = get_area_of_interest(extent)
    if aoi is not None:
        return aoi.bbox(constants.DEFAULT_CRS), aoi.name

    west, south, east, north = (float(value) for value in study_areas.total_bounds)
    return (west, south, east, north), "the four territorial authorities"


def clip_to_extent(raster, bbox, label):
    """Clip a national grid to the study extent and return it in the study's projection.

    The clip is made in the raster's own projection and before any
    reprojection, so a small extent stays cheap -- the same order
    ``landloss.io.source_material.get_source_material_raster`` uses. The extent
    is re-expressed with :func:`landloss.common.utils.raster.bbox_in_crs` rather
    than by transforming its corners, because a rectangle's edges bow when they
    are reprojected and the envelope of four corners falls inside the true
    extent.

    Args:
        raster: The grid as the NLM delivered it, in its own projection.
        bbox: The extent (minx, miny, maxx, maxy) in
            :data:`landloss.domain.constants.DEFAULT_CRS`.
        label: What the grid is, for the error message if the two do not meet.

    Returns:
        The clipped grid, in :data:`landloss.domain.constants.DEFAULT_CRS`.

    Raises:
        ValueError: If the extent does not overlap the grid at all, which is
            nearly always a study extent and a release that were never meant to
            meet.
    """
    native = bbox_in_crs(bbox, constants.DEFAULT_CRS, raster.rio.crs)

    try:
        # allow_one_dimensional_raster, because a window one cell wide is a
        # degenerate read rather than a mistaken one, and rioxarray's refusal of
        # it is a RuntimeError that no caller thinks to catch.
        clipped = raster.rio.clip_box(*native, allow_one_dimensional_raster=True)
    except (NoDataInBounds, OneDimensionalRaster) as exc:
        bounds = tuple(float(value) for value in raster.rio.bounds())
        msg = (
            f"The study extent does not overlap the {label} grid, whose own "
            f"extent is {bounds} in {raster.rio.crs}. Check that the extent and "
            "the release are meant to cover the same ground."
        )
        raise ValueError(msg) from exc

    if CRS(clipped.rio.crs) == CRS(constants.DEFAULT_CRS):
        return clipped

    # Nearest neighbour rather than bilinear. A cell carries the probability of
    # damage at that cell, and averaging two of them across a cell boundary
    # produces a number neither of them said.
    return clipped.rio.reproject(constants.DEFAULT_CRS, resampling=Resampling.nearest)


def describe_extent(name, raster, resolution):
    """Print what is being run over, and what the clipped grid holds.

    The extent printed is the clipped grid's own, not the one that was asked
    for. They differ whenever the NLM release stops short of the study area, and
    it is the ground actually expanded that a result has to be quoted against.
    """
    west, south, east, north = (float(value) for value in raster.rio.bounds())
    finite = int(np.isfinite(raster.to_numpy()).sum())

    print(RULE)
    print(f"Extent: {name}, as far as the NLM release reaches")
    print(f"  {west:,.0f} - {east:,.0f} E, {south:,.0f} - {north:,.0f} N")
    print(f"  {(east - west) / 1000:,.1f} by {(north - south) / 1000:,.1f} km")
    print(
        f"Grid: {raster.shape[0]:,} by {raster.shape[1]:,} cells at "
        f"{resolution:g} m, in {raster.rio.crs}"
    )
    print(f"  {raster.size:,} cells, {finite:,} of them carrying a probability")


def describe_expansion(
    moderate_or_worse, nlm_major_or_worse, major_or_worse, probabilities
):
    """Print the two grids that went in beside the six that came out.

    Both are printed because the expansion is checkable by eye from them: the
    None and Minor means are half of one minus the Moderate exceedance each, the
    Moderate mean is the difference of the two exceedances, and Major, Severe
    and Very Severe are a quarter, a half and a quarter of the Major exceedance
    that was expanded -- the corrected one, when lateral spreading is applied.
    A reader who cannot make those add up is looking at a bug.
    """
    print(RULE)
    print("Mean exceedance probability, as the NLM release supplies it:")
    print(f"  P(at least Moderate)  {np.nanmean(moderate_or_worse.to_numpy()):.4f}")
    print(f"  P(at least Major)     {np.nanmean(nlm_major_or_worse.to_numpy()):.4f}")
    if major_or_worse is not nlm_major_or_worse:
        print(
            f"  P(at least Major)     {np.nanmean(major_or_worse.to_numpy()):.4f}"
            "  after lateral spreading, which is what is expanded"
        )

    print("Mean probability of each state, after differencing and subdividing:")
    total = 0.0
    for state in LD_STATES:
        mean = float(np.nanmean(probabilities[state].to_numpy()))
        total += mean
        print(f"  {state:<12} {mean:.4f}")
    print(f"  {'total':<12} {total:.4f}  (one, or the subdivision lost mass)")


def ls_zones_path(*, extent):
    """Return the file a run writes its lateral spreading zones to, for viewing."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"ls-zones{suffix}.gpkg"


def describe_lateral_spreading(grid, before, after, capped):
    """Print the mean P(at least Major) per zone, before and after the correction.

    A cell is counted in the zone its centre falls in, though the correction
    weights it by the share of it in each zone, so a near zone's mean is diluted
    by the part of its cells that lies further out. With the count of cells the
    cap at P(at least Moderate) bound in.
    """
    zone_values = grid.to_numpy()
    before_values = before.to_numpy()
    after_values = after.to_numpy()
    print(f"  {'zone':<8} {'cells':>10} {'P(>=Major) before':>18} {'after':>8}")
    for code, name in ZONES.items():
        in_zone = (zone_values == code) & np.isfinite(before_values)
        if not in_zone.any():
            print(f"  {name:<8} {0:>10,}")
            continue
        print(
            f"  {name:<8} {int(in_zone.sum()):>10,} "
            f"{float(before_values[in_zone].mean()):>18.4f} "
            f"{float(after_values[in_zone].mean()):>8.4f}"
        )
    print(f"  Capped at P(at least Moderate) in {int(capped.to_numpy().sum()):,} cells")


def correct_for_lateral_spreading(moderate_or_worse, major_or_worse, *, extent):
    """Correct P(at least Major) for lateral spreading, by zone.

    Reads the free faces step 1 wrote for this extent, buffers them into zones,
    writes the zones out for viewing, and applies
    :func:`landloss.hazard.liquefaction.lateral_spreading.apply_lateral_spreading`.

    Returns:
        The corrected P(at least Major).

    Raises:
        FileNotFoundError: If step 1 has not been run for this extent.
    """
    path = free_faces_path(extent)
    if not path.exists():
        msg = (
            f"No free faces at {path}. Run s1_free_faces with EXTENT = "
            f"{extent!r} first, or set LATERAL_SPREADING to False."
        )
        raise FileNotFoundError(msg)
    free_faces = gpd.read_file(path).to_crs(constants.DEFAULT_CRS)
    zones = lateral_spreading_zones(free_faces)
    zones_path = ls_zones_path(extent=extent)
    zones.to_file(zones_path, driver="GPKG")

    corrected, capped = apply_lateral_spreading(
        moderate_or_worse, major_or_worse, far_weight_grid(zones, major_or_worse)
    )
    grid = zone_grid(zones, major_or_worse)

    print(RULE)
    print(f"Lateral spreading, from {len(free_faces):,} free faces in {path.name}:")
    describe_lateral_spreading(grid, major_or_worse, corrected, capped)
    print(f"Wrote {zones_path}")
    return corrected


def main(*, extent, lateral_spreading):
    """Expand the NLM land damage grids into six state probabilities and write them out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        lateral_spreading: Whether to correct P(at least Major) for lateral
            spreading before the expansion.
    """
    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox, extent_name = resolve_extent(study_areas, extent=extent)

    print("Reading the NLM land damage exceedance grids ...", flush=True)
    moderate_or_worse = clip_to_extent(
        get_nlm_scenario_rp2500y_gwd_med_p_ld_moderate_fu(), bbox, "moderate"
    )
    major_or_worse = clip_to_extent(
        get_nlm_scenario_rp2500y_gwd_med_p_ld_major_fu(), bbox, "major"
    )

    # Matched onto the Moderate grid rather than clipped to the same box and
    # hoped over. The two are differenced cell by cell below, and xarray aligns
    # on coordinate values: a grid half a cell out would difference to nothing
    # at all rather than raising.
    major_or_worse = major_or_worse.rio.reproject_match(
        moderate_or_worse, resampling=Resampling.nearest
    )

    resolution = cell_size(moderate_or_worse)
    describe_extent(extent_name, moderate_or_worse, resolution)

    nlm_major_or_worse = major_or_worse
    if lateral_spreading:
        major_or_worse = correct_for_lateral_spreading(
            moderate_or_worse, major_or_worse, extent=extent
        )

    probabilities = beta_expand_ld_probabilities(moderate_or_worse, major_or_worse)
    describe_expansion(
        moderate_or_worse, nlm_major_or_worse, major_or_worse, probabilities
    )

    print(RULE)
    for state in LD_STATES:
        # The projection is written back explicitly rather than relied on to
        # survive the arithmetic, because write_raster refuses a grid without
        # one and a refusal here would come after the expensive part.
        grid = probabilities[state].rio.write_crs(constants.DEFAULT_CRS)
        path = write_raster(
            grid.rename(state_slug(state)), beta_probability_path(state, extent=extent)
        )
        print(f"Wrote {path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, lateral_spreading=config.LATERAL_SPREADING)
