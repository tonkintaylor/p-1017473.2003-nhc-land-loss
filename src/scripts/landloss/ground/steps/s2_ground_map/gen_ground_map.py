"""Ground step 2: reconcile every geology and earthworks source into one ground map.

    uv run --frozen python src/scripts/landloss/ground/steps/s2_ground_map/gen_ground_map.py

The run settings -- the extent, whether to reuse the cached layers, the
groundwater depth assumed off the NLM footprint, the groundwater simplification
tolerance, the residual threshold, the residual's classing cell, minimum patch
area and simplification tolerance, and the tile size the fill thickness is read
in -- come from ``config.py`` beside this script rather than from the command
line.

Needs ``TNT_KOORDINATES_API_KEY`` in ``.env`` for the T+T Koordinates layers
(SLIDE genesis, WCC earthworks, NLM geomorphology and groundwater depth); the
SLIDE materials and the 1:50,000 geology are public and need no key; the NLM
flatland is read from the release tree on T:. Ground step 1 has to have
written the cut-and-fill residual rasters first (``gen_terrain_derivatives.py``).

One non-probabilistic polygon map of the ground, read by everything downstream
that asks what the ground is made of: the slope candidates, the wall lines, the
slope units and the strength-based models. The sources are unioned into one
planar partition by :func:`landloss.hazard.landslide.ground_map.build_ground_map`
and each piece takes its attributes by precedence, finest source first:

- material: SLIDE interpreted materials, then the 1:50,000 geology, then the
  NLM ``l3_yp`` class, then ``unknown``;
- modification: SLIDE genesis cut slopes, fill bodies, landfills and dams, then
  the WCC cut and fill areas, then the SLIDE materials that name fill (its fill
  and mixed fill classes), then the thresholded 30 m residual, then
  ``natural``. The residual is read at a 10 m cell, thresholded, sieved so no
  patch is smaller than the minimum area and polygonised, and the polygons are
  simplified as a coverage; a patch below the minimum takes the class of its
  largest neighbour, which is not necessarily natural;
- prior failure: SLIDE genesis landslides and rockfall, then ``none``;
- groundwater class: the NLM median depth classed as saturated, poorly drained
  or well drained and polygonised over the flat land, then the class of the
  assumed default depth. The map carries the class only, not the depth.

Fill thickness is the mean of the positive 100 m residual over each fill piece,
read tile by tile so the 1 m grid is never held whole.
The Kingsbury geology value and the effective strength set follow from the
material by lookup. No probability anywhere.

Writes ``ground-map<extent_suffix>.geoparquet`` under temp/ground/, one row
per ``ground_id``.
"""

import math
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rioxarray
import shapely
import xarray as xr
from rasterio import windows
from rasterio.features import rasterize, shapes, sieve
from rasterio.transform import Affine
from rasterio.windows import Window
from shapely.geometry import box, shape

from landloss.common.utils import tiles
from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.hazard.landslide import ground_map
from landloss.hazard.landslide.ground_map import GroundSource
from landloss.io.area_of_interest import extent_suffix
from landloss.io.nlm import get_nlm_flatland
from landloss.io.readers import (
    get_gwd_median_depth,
    get_nlm_geomorphology,
    get_slide_genesis,
    get_slide_interpreted_materials,
    get_wcc_cut_areas,
    get_wcc_fill_areas,
    get_wellington_urban_geology,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    resolve_extent,
)
from scripts.landloss.ground.steps.s1_terrain.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.ground.steps.s2_ground_map import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. The map is a working layer, rebuildable from the sources.
WORK_DIR = TEMP_DIR / "ground"
OUT_STEM = "ground-map"

# The residual rasters ground step 1 writes, keyed by the base resolution they were
# taken against: the 30 m one classes cut and fill, the 100 m one gives the
# fill thickness.
MODIFICATION_RESIDUAL_M = 30
THICKNESS_RESIDUAL_M = 100

# How many rows of classing blocks :func:`read_residual` reads at a time: with a
# 10 m block and a 59 km wide raster, a strip is about 120 MB.
STRIP_BLOCK_ROWS = 50

# The columns of the output, in order (contract section 3.2).
COLUMNS = (
    "ground_id",
    "material",
    "material_source",
    "material_confidence",
    "modification",
    "modification_source",
    "modification_confidence",
    "is_flatland",
    "flatland_version",
    "gw_depth_class",
    "gw_source",
    "prior_failure",
    "prior_failure_source",
    "fill_thickness_m",
    "geology_value",
    "c_kpa",
    "phi_deg",
    "unit_weight_kn_m3",
    "strength_source",
    "area_m2",
    "geometry",
)

# The SLIDE genesis types whose mapping GNS completed, and so claim their
# attribute with high confidence; the dam polygons are the rest of the
# modification claimers and are low.
GENESIS_COMPLETE_TYPES = ("Cut slope", "Fill body", "Landfill")

# The codes the groundwater classes are polygonised with; 0 is left for the
# cells the grid does not cover.
GROUNDWATER_CODES = {
    name: code for code, name in enumerate(ground_map.GW_DEPTH_CLASSES, start=1)
}

RULE = "-" * 72


def ground_map_path(*, extent):
    """Return the file a run writes the ground map to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def residual_path(base_resolution_m, *, extent):
    """Return the cut-and-fill residual raster ground step 1 wrote against one base."""
    return terrain_path(f"cut-fill-residual-{base_resolution_m:g}m", extent=extent)


def read_residual(path, *, cell_m):
    """Read a cut-and-fill residual raster averaged up to a coarser cell.

    The residual is a 1 m grid, and a billion cells at that. It is read in
    strips of whole blocks and each strip is averaged into ``cell_m`` blocks
    before the next is read, so the 1 m grid is never in memory, only a strip
    of it and the result. The averaging is done here, not by GDAL's
    ``Resampling.average``, because the residual rasters carry no nodata tag
    (``terrain._as_derivative`` drops it), and GDAL's average of an untagged
    block touching one NaN is NaN.

    A block is the mean of the cells in it that hold a value, and is NaN only
    when none of them does, so a block half over the DEM's edge keeps the
    residual of the half that is there. Cells short of a whole block at the
    south and east edges, less than ``cell_m`` wide, are not read and are
    natural ground downstream.

    Args:
        path: The residual raster ground step 1 wrote, on a 1 m grid.
        cell_m: The side of the blocks to average to, in metres, a whole
            multiple of the raster's cell,
            ``config.RESIDUAL_CLASS_CELL_M``.

    Returns:
        The averaged residual as a float32 raster in the raster's system,
        NaN where no cell of a block held a value, on a grid of ``cell_m`` cells
        from the raster's north-west corner.

    Raises:
        ValueError: If the cell is not a whole multiple of the raster's cell.
    """
    with rasterio.open(path) as source:
        factor = cell_m / source.res[0]
        if not math.isclose(factor, round(factor)) or round(factor) < 1:
            msg = (
                f"The classing cell, {cell_m:g} m, is not a whole multiple of "
                f"the {source.res[0]:g} m cell of {path}"
            )
            raise ValueError(msg)
        factor = round(factor)
        rows, columns = source.height // factor, source.width // factor
        means = np.full((rows, columns), np.nan, dtype="float32")
        for first in range(0, rows, STRIP_BLOCK_ROWS):
            strip_rows = min(STRIP_BLOCK_ROWS, rows - first)
            strip = source.read(
                1,
                window=Window(0, first * factor, columns * factor, strip_rows * factor),
                masked=True,
            )
            strip = strip.astype("float32").filled(np.nan)
            blocks = strip.reshape(strip_rows, factor, columns, factor)
            held = np.isfinite(blocks)
            totals = np.where(held, blocks, 0.0).sum(axis=(1, 3), dtype="float64")
            counts = held.sum(axis=(1, 3))
            with np.errstate(invalid="ignore", divide="ignore"):
                means[first : first + strip_rows] = np.where(
                    counts > 0, totals / counts, np.nan
                )
        transform = source.transform @ Affine.scale(factor)
        crs = source.crs
    return xr.DataArray(
        means,
        dims=("y", "x"),
        coords={
            "y": transform.f + transform.e * (np.arange(rows) + 0.5),
            "x": transform.c + transform.a * (np.arange(columns) + 0.5),
        },
    ).rio.write_crs(crs)


def with_fields(frame, fields):
    """Give a polygon layer the fields this step reads, even when it is empty.

    An ArcGIS read with nothing in the extent comes back with a geometry and no
    fields, which is every SLIDE layer outside Wellington City (Porirua, the
    Hutt). Adding the fields empty lets each source build with no polygons.
    """
    missing = [field for field in fields if field not in frame.columns]
    return frame.assign(**dict.fromkeys(missing, pd.Series(dtype=object)))


def slide_confidence(confidence):
    """Normalise the SLIDE ``confidence`` field onto high, medium and low.

    The layer qualifies a few of its high entries -- "high (verified GE)",
    "high (post-2013 modified)" -- which are still high.
    """
    first_word = confidence.astype(str).str.split(" ").str[0].str.lower()
    unknown = set(first_word.unique()) - set(ground_map.CONFIDENCES)
    if unknown:
        msg = f"SLIDE confidence value(s) {sorted(unknown)} are not high, medium or low"
        raise ValueError(msg)
    return first_word


def slide_material_sources(materials):
    """Build one material source per SLIDE confidence level, highest first.

    A ``GroundSource`` carries one confidence, and the SLIDE polygons carry
    their own, so the layer is split by confidence into three sources in
    sequence. The polygons do not overlap one another, so the split changes
    nothing about which polygon a piece reads; it only lets each piece carry
    the confidence of the polygon it read.
    """
    frame = materials.assign(
        material=ground_map.material_from_slide(materials["Type"]),
        confidence=slide_confidence(materials["confidence"]),
    )
    return [
        GroundSource(
            "slide_materials",
            frame.loc[frame["confidence"] == level],
            "material",
            "material",
            level,
        )
        for level in ground_map.CONFIDENCES
    ]


def slide_modification_sources(materials):
    """Build one fill modification source per SLIDE confidence level, highest first.

    The SLIDE fill and mixed fill classes give the natural material as the
    material and record the fill here, as the modification, so the two are
    read separately. The frame is filtered to the fill types first, and split
    by confidence as :func:`slide_material_sources` is.
    """
    filled = materials.loc[materials["Type"].isin(ground_map.SLIDE_FILL_TYPES)]
    frame = filled.assign(
        modification=ground_map.modification_from_slide(filled["Type"]),
        confidence=slide_confidence(filled["confidence"]),
    )
    return [
        GroundSource(
            "slide_materials",
            frame.loc[frame["confidence"] == level],
            "modification",
            "modification",
            level,
        )
        for level in ground_map.CONFIDENCES
    ]


def genesis_sources(genesis):
    """Build the modification and prior failure sources from the SLIDE genesis.

    The frame is filtered to the claiming types before each source is built,
    so a no-claim type such as modified terrain never reaches a mapper.
    """
    complete = genesis.loc[genesis["Type"].isin(GENESIS_COMPLETE_TYPES)]
    dams = genesis.loc[
        genesis["Type"].isin(ground_map.GENESIS_MODIFICATION_TYPES)
        & ~genesis["Type"].isin(GENESIS_COMPLETE_TYPES)
    ]
    failures = genesis.loc[genesis["Type"].isin(ground_map.GENESIS_PRIOR_FAILURE_TYPES)]

    def modification(frame):
        return frame.assign(
            modification=ground_map.modification_from_genesis(frame["Type"])
        )

    return [
        GroundSource(
            "slide_genesis",
            modification(complete),
            "modification",
            "modification",
            "high",
        ),
        GroundSource(
            "slide_genesis", modification(dams), "modification", "modification", "low"
        ),
        GroundSource(
            "slide_genesis",
            failures.assign(
                prior_failure=ground_map.prior_failure_from_genesis(
                    failures["Type"], failures["Subtype"]
                )
            ),
            "prior_failure",
            "prior_failure",
            "low",
        ),
    ]


def wcc_sources(cut, fill):
    """Build the modification sources from the WCC cut and fill areas."""
    return [
        GroundSource(
            f"wcc_{kind}_areas",
            frame.assign(
                modification=ground_map.modification_from_wcc(
                    pd.Series(kind, index=frame.index)
                )
            ),
            "modification",
            "modification",
            "medium",
        )
        for kind, frame in (("cut", cut), ("fill", fill))
    ]


def polygonise(values, template, *, mask, column):
    """Turn runs of equal-valued cells into polygons carrying the value.

    Args:
        values: The array to polygonise, on ``template``'s grid.
        template: The raster the array sits on, for its transform and system.
        mask: Which cells to polygonise; the rest are left out.
        column: The column the value is written to.

    Returns:
        A GeoDataFrame of polygons, one per run of equal-valued 4-connected
        cells, in the template's system.
    """
    found = shapes(values, mask=mask, transform=template.rio.transform())
    geometries, cell_values = [], []
    for geometry, value in found:
        geometries.append(shape(geometry))
        cell_values.append(value)
    return gpd.GeoDataFrame(
        {column: cell_values}, geometry=geometries, crs=template.rio.crs
    )


def polygonise_groundwater(depth_path, extent, flatland, *, simplify_m):
    """Polygonise the NLM median groundwater depth, as a class, over the flat land.

    The grid is national and carries a value over flat land only, so it is
    clipped to the extent before loading and the polygons are cut back to the
    flatland. The depth is classed first (saturated, poorly drained, well
    drained) and the class codes are polygonised, so a polygon is a body of one
    class and not a run of equal depths. The class polygons are simplified as
    a coverage, which keeps the edge two classes share one edge.

    Args:
        depth_path: The grid, from :func:`landloss.io.readers.get_gwd_median_depth`.
        extent: The polygon being mapped.
        flatland: The NLM flatland polygons, in the study's system.
        simplify_m: The simplification tolerance in metres,
            ``config.GROUNDWATER_SIMPLIFY_M``.

    Returns:
        Polygons carrying ``gw_depth_class``, clipped to the flat land.
    """
    west, south, east, north = extent.bounds
    with rioxarray.open_rasterio(depth_path, masked=True) as opened:
        depth = (
            opened.squeeze(drop=True)
            .rio.clip_box(minx=west, miny=south, maxx=east, maxy=north)
            .load()
        )
    values = depth.to_numpy().astype("float32")
    classed = ground_map.gw_depth_class_from_depth(values)
    codes = np.zeros(classed.shape, dtype="uint8")
    for name, code in GROUNDWATER_CODES.items():
        codes[classed == name] = code
    polygons = polygonise(codes, depth, mask=codes > 0, column="code").to_crs(
        constants.DEFAULT_CRS
    )
    names = {code: name for name, code in GROUNDWATER_CODES.items()}
    polygons["gw_depth_class"] = polygons.pop("code").astype(int).map(names)
    if polygons.empty or flatland.empty:
        return polygons.iloc[0:0]
    polygons["geometry"] = shapely.coverage_simplify(
        polygons.geometry.to_numpy(), simplify_m
    )
    # keep_geom_type: where a class only touches the flat land the clip leaves
    # a line or a point, which is not ground.
    return gpd.clip(polygons, flatland, keep_geom_type=True).reset_index(drop=True)


def polygonise_residual(residual, *, threshold_m, min_patch_m2, simplify_m):
    """Polygonise the cut and fill the thresholded 30 m residual marks.

    The residual is classed to codes (natural, cut, fill) and sieved as one
    raster, so a patch smaller than ``min_patch_m2`` takes the class of its
    largest neighbour: a natural pocket inside a fill body becomes fill, and a
    fill speckle inside a cut becomes cut, rather than every small patch going
    natural. The minimum is a whole number of cells, the area over the cell's
    area rounded up, so no patch of the sieved raster is smaller than the area
    asked for. Cells with no residual are left out of the sieve and out of the
    polygons. The patches are then polygonised and simplified as a coverage,
    which moves the edge two patches share once, not once for each side.
    Simplifying cuts the corners of the cell staircase, so a polygon can come
    out a little under the minimum area and the total area moves a little: the
    minimum holds before simplification, and a ``simplify_m`` of zero keeps it.

    Args:
        residual: The 30 m cut-and-fill residual on the classing grid, from
            :func:`read_residual`.
        threshold_m: The magnitude beyond which the residual marks a cut or a
            fill, ``config.RESIDUAL_MODIFICATION_THRESHOLD_M``.
        min_patch_m2: The smallest patch kept, in square metres,
            ``config.RESIDUAL_MIN_PATCH_M2``.
        simplify_m: The simplification tolerance in metres,
            ``config.RESIDUAL_SIMPLIFY_M``; zero leaves the outlines as the
            cells give them.

    Returns:
        Polygons carrying ``modification`` as ``cut`` or ``fill``; natural and
        unknown cells are left out, because natural is the default anyway.
    """
    codes, nodata = ground_map.modification_codes_from_residual(
        residual.to_numpy(), threshold_m=threshold_m
    )
    transform = residual.rio.transform()
    # The epsilon keeps a minimum that is a whole number of cells from
    # rounding up on float noise.
    min_cells = math.ceil(min_patch_m2 / abs(transform.a * transform.e) - 1e-9)
    if min_cells > 1:
        codes = sieve(codes, min_cells, mask=~nodata)
    natural = ground_map.MODIFICATION_CODES[ground_map.NATURAL]
    polygons = polygonise(
        codes, residual, mask=(codes != natural) & ~nodata, column="code"
    )
    if simplify_m > 0 and not polygons.empty:
        polygons["geometry"] = shapely.coverage_simplify(
            polygons.geometry.to_numpy(), simplify_m
        )
    names = {code: name for name, code in ground_map.MODIFICATION_CODES.items()}
    polygons["modification"] = polygons["code"].astype(int).map(names)
    return polygons.drop(columns="code")


def mean_positive_residual(ground, residual_file, *, strip_cells):
    """Average the positive residual over each fill piece of the map.

    The fill thickness of a piece is the mean of the 100 m residual where it is
    positive -- ground standing above the 100 m surface -- over the cells
    inside the piece. Computed strip by strip: each strip's fill pieces, cut to
    the strip, are burned onto its cells by row number and the positive
    residual is summed per piece, and the sums and counts carry from strip to
    strip, so no polygon is clipped for good and the 1 m grid is never held
    whole. A cell is the piece's where its centre is inside it, so the means
    are those of a whole-grid burn. A strip is the full width of the raster,
    because the residual is written in one-row strips and a window narrower
    than that still has every row of it decoded in full: a strip reads each
    row once.

    Args:
        ground: The ground map, carrying ``modification``.
        residual_file: The 100 m cut-and-fill residual on the 1 m grid, on disk.
        strip_cells: The most cells a strip holds,
            ``config.THICKNESS_STRIP_CELLS``; a strip is as many whole rows as
            fit, and at least one.

    Returns:
        The mean positive residual per row, NaN where the piece is not fill
        or holds no positive cell.
    """
    fill = ground.loc[ground["modification"] == "fill"]
    thickness = pd.Series(np.nan, index=ground.index, dtype=float)
    if fill.empty:
        return thickness

    labels_of = pd.Series(np.arange(1, len(fill) + 1), index=fill.index)
    sums = np.zeros(len(fill) + 1)
    counts = np.zeros(len(fill) + 1)
    with rasterio.open(residual_file) as source:
        cell = abs(source.transform.a)
        strip_rows = max(1, strip_cells // source.width)
        for first in range(0, source.height, strip_rows):
            window = Window(
                0, first, source.width, min(strip_rows, source.height - first)
            )
            near = tiles.clip_to_window(
                fill, windows.bounds(window, source.transform), cell
            )
            if near.empty:
                continue
            labels = rasterize(
                zip(near.geometry, labels_of.loc[near.index], strict=True),
                out_shape=(window.height, window.width),
                transform=windows.transform(window, source.transform),
                fill=0,
                dtype="int32",
            )
            values = source.read(1, window=window, masked=True)
            values = values.astype("float32").filled(np.nan)
            positive = np.isfinite(values) & (values > 0)
            sums += np.bincount(
                labels[positive], weights=values[positive], minlength=len(fill) + 1
            )
            counts += np.bincount(labels[positive], minlength=len(fill) + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums[1:] / counts[1:]
    thickness.loc[fill.index] = np.where(counts[1:] > 0, means, np.nan)
    return thickness


def finish(ground, residual_100m_file, *, strip_cells):
    """Add the fill thickness, mint the ids, measure the area and order the columns.

    Args:
        ground: The attributed partition from ``build_ground_map``.
        residual_100m_file: The 100 m residual on the 1 m grid, on disk, for
            the thickness.
        strip_cells: The most cells a strip of the residual holds when the
            thickness is read.

    Returns:
        The ground map with every column of ``COLUMNS``, sorted by location.
    """
    ground = ground.copy()
    ground["fill_thickness_m"] = mean_positive_residual(
        ground, residual_100m_file, strip_cells=strip_cells
    )
    ground = sort_by_point(ground)
    ground.insert(0, "ground_id", mint_ids(constants.GROUND_ID_PREFIX, len(ground)))
    ground["area_m2"] = ground.area
    return ground[list(COLUMNS)]


def read_flatland(extent):
    """Read the NLM flatland polygons over the extent in the study's system."""
    flatland = get_nlm_flatland().to_crs(constants.DEFAULT_CRS)
    return flatland.loc[flatland.intersects(extent)].reset_index(drop=True)


def describe_extent(name, extent):
    """Print the extent being mapped, so a mistaken study area is obvious at once."""
    minx, miny, maxx, maxy = extent.bounds
    print(RULE)
    print(f"Extent    : {name}")
    print(f"  NZTM    : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size    : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")


def describe_shares(ground, column, label):
    """Print the area share of the map in each value of a column."""
    shares = ground.groupby(column)["area_m2"].sum() / ground["area_m2"].sum()
    print(RULE)
    print(f"{label}, by area:")
    for value, share in shares.sort_values(ascending=False).items():
        print(f"  {value!s:<24} {share:>6.1%}")


def describe_strength(ground):
    """Print the strength row chosen per grade."""
    print(RULE)
    print("Strength row per grade:")
    chosen = ground.dropna(subset=["strength_source"]).drop_duplicates(
        "strength_source"
    )
    for _, row in chosen.iterrows():
        grade = ground_map.MATERIAL_STRENGTH_GRADE[row["material"]]
        print(
            f"  {grade:<5} {row['strength_source']:<5} c' {row['c_kpa']:>6.1f} kPa, "
            f"phi' {row['phi_deg']:>5.1f} deg, "
            f"unit weight {row['unit_weight_kn_m3']:>5.1f} kN/m3"
        )
    if chosen.empty:
        print("  none: no piece carries a known material")


def main(
    *,
    extent,
    use_cached_layers,
    default_gw_depth_m,
    groundwater_simplify_m,
    residual_modification_threshold_m,
    residual_class_cell_m,
    residual_min_patch_m2,
    residual_simplify_m,
    thickness_strip_cells,
):
    """Build the ground map over the extent and write it out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        use_cached_layers: Whether to reuse the cached polygon layers.
        default_gw_depth_m: The depth to groundwater assumed off the NLM
            footprint, in metres; the map carries its class.
        groundwater_simplify_m: The tolerance, in metres, the groundwater class
            polygons are simplified to as a coverage.
        residual_modification_threshold_m: The magnitude of 30 m residual
            beyond which the ground is cut or fill where no mapping reaches.
        residual_class_cell_m: The cell, in metres, the 30 m residual is
            averaged to and classed on.
        residual_min_patch_m2: The smallest cut or fill patch the residual
            keeps, in square metres; a smaller one takes its largest
            neighbour's class.
        residual_simplify_m: The tolerance, in metres, the residual patches
            are simplified to as a coverage.
        thickness_strip_cells: The most cells a strip of the 100 m residual
            holds when the fill thickness is read.
    """
    bbox, extent_name = resolve_extent(extent=extent)
    area = box(*bbox)
    describe_extent(extent_name, area)

    print("\nReading the polygon sources ...", flush=True)
    materials = with_fields(
        get_slide_interpreted_materials(bbox=bbox, use_cache=use_cached_layers),
        ["Type", "confidence"],
    )
    geology = get_wellington_urban_geology(bbox=bbox, use_cache=use_cached_layers)
    landforms = get_nlm_geomorphology(bbox=bbox, use_cache=use_cached_layers)
    genesis = with_fields(
        get_slide_genesis(bbox=bbox, use_cache=use_cached_layers),
        ["Type", "Subtype"],
    )
    cut = get_wcc_cut_areas(bbox=bbox, use_cache=use_cached_layers)
    fill = get_wcc_fill_areas(bbox=bbox, use_cache=use_cached_layers)
    flatland = read_flatland(area)
    for name, frame in (
        ("SLIDE materials", materials),
        ("1:50,000 geology", geology),
        ("NLM geomorphology", landforms),
        ("SLIDE genesis", genesis),
        ("WCC cut areas", cut),
        ("WCC fill areas", fill),
        ("NLM flatland", flatland),
    ):
        print(f"  {name:<20} {len(frame):>6,} polygons")

    print("\nPolygonising the groundwater class and the 30 m residual ...", flush=True)
    groundwater = polygonise_groundwater(
        get_gwd_median_depth(), area, flatland, simplify_m=groundwater_simplify_m
    )
    residual_30m = read_residual(
        residual_path(MODIFICATION_RESIDUAL_M, extent=extent),
        cell_m=residual_class_cell_m,
    )
    residual = polygonise_residual(
        residual_30m,
        threshold_m=residual_modification_threshold_m,
        min_patch_m2=residual_min_patch_m2,
        simplify_m=residual_simplify_m,
    )
    print(f"  {'groundwater class':<20} {len(groundwater):>6,} polygons")
    print(f"  {'residual cut/fill':<20} {len(residual):>6,} polygons")

    sources = [
        *slide_material_sources(materials),
        GroundSource(
            "geology_1_50k",
            geology.assign(
                material=ground_map.material_from_geology(geology["unit_code"])
            ),
            "material",
            "material",
            "medium",
        ),
        GroundSource(
            "nlm_geomorphology",
            landforms.assign(material=ground_map.material_from_nlm(landforms["l3_yp"])),
            "material",
            "material",
            "low",
        ),
        *genesis_sources(genesis),
        *wcc_sources(cut, fill),
        *slide_modification_sources(materials),
        GroundSource("residual_30m", residual, "modification", "modification", "low"),
        GroundSource(
            ground_map.NLM_GWD_SOURCE,
            groundwater,
            "gw_depth_class",
            "gw_depth_class",
            "medium",
        ),
    ]

    print("\nBuilding the planar partition and attributing it ...", flush=True)
    ground = ground_map.build_ground_map(
        area,
        sources,
        flatland=flatland,
        default_gw_depth_m=default_gw_depth_m,
        crs=constants.DEFAULT_CRS,
    )
    ground = finish(
        ground,
        residual_path(THICKNESS_RESIDUAL_M, extent=extent),
        strip_cells=thickness_strip_cells,
    )

    out_path = ground_map_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ground.to_parquet(out_path)

    print(RULE)
    print(f"{len(ground):,} pieces over {ground['area_m2'].sum() / 1e6:.2f} km2")
    describe_shares(ground, "material", "Material")
    describe_shares(ground, "material_source", "Material source")
    describe_shares(ground, "modification", "Modification")
    describe_shares(ground, "modification_source", "Modification source")
    describe_shares(ground, "prior_failure", "Prior failure")
    describe_shares(ground, "prior_failure_source", "Prior failure source")
    describe_shares(ground, "gw_depth_class", "Groundwater depth class")
    describe_shares(ground, "gw_source", "Groundwater source")
    describe_shares(ground, "is_flatland", "On NLM flatland")
    describe_strength(ground)
    print(RULE)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        default_gw_depth_m=config.DEFAULT_GROUNDWATER_DEPTH_M,
        groundwater_simplify_m=config.GROUNDWATER_SIMPLIFY_M,
        residual_modification_threshold_m=config.RESIDUAL_MODIFICATION_THRESHOLD_M,
        residual_class_cell_m=config.RESIDUAL_CLASS_CELL_M,
        residual_min_patch_m2=config.RESIDUAL_MIN_PATCH_M2,
        residual_simplify_m=config.RESIDUAL_SIMPLIFY_M,
        thickness_strip_cells=config.THICKNESS_STRIP_CELLS,
    )
