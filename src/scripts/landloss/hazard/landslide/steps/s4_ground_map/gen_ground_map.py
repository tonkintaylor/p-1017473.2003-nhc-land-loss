"""Reconcile every geology and earthworks source into one ground map.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s4_ground_map/gen_ground_map.py

The run settings -- the pilot box or the full study area, whether to reuse the
cached layers, the groundwater depth assumed off the NLM footprint and the
residual threshold -- come from ``config.py`` beside this script rather than
from the command line.

Needs ``TNT_KOORDINATES_API_KEY`` in ``.env`` for the T+T Koordinates layers
(SLIDE genesis, WCC earthworks, NLM geomorphology and groundwater depth); the
SLIDE materials and the 1:50,000 geology are public and need no key; the NLM
flatland is read from the release tree on T:. Landslide step 3 has to have
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
  ``natural``;
- prior failure: SLIDE genesis landslides and rockfall, then ``none``;
- groundwater depth: the NLM median depth polygonised over the flat land, then
  the assumed default.

Fill thickness is the mean of the positive 100 m residual over each fill piece.
The Kingsbury geology value and the effective strength set follow from the
material by lookup. No probability anywhere.

Writes ``ground-map[-pilot].geoparquet`` under temp/hazard/landslide/, one row
per ``ground_id``.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray
from rasterio.features import rasterize, shapes
from shapely.geometry import box, shape

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.hazard.landslide import ground_map
from landloss.hazard.landslide.ground_map import GroundSource
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
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    resolve_extent,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. The map is a working layer, rebuildable from the sources.
WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "ground-map"

# The residual rasters step 3 writes, keyed by the base resolution they were
# taken against: the 30 m one classes cut and fill, the 100 m one gives the
# fill thickness.
MODIFICATION_RESIDUAL_M = 30
THICKNESS_RESIDUAL_M = 100

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
    "gw_depth_m",
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

# The codes the thresholded residual is polygonised with.
RESIDUAL_CODES = {"cut": 1, "fill": 2}

RULE = "-" * 72


def ground_map_path(*, pilot):
    """Return the file a run writes the ground map to."""
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def residual_path(base_resolution_m, *, pilot):
    """Return the cut-and-fill residual raster step 3 wrote against one base."""
    return terrain_path(f"cut-fill-residual-{base_resolution_m:g}m", pilot=pilot)


def read_raster(path):
    """Read a single-band raster into memory with nodata as NaN."""
    with rioxarray.open_rasterio(path, masked=True) as opened:
        return opened.squeeze(drop=True).load()


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


def polygonise_groundwater(depth_path, extent, flatland):
    """Polygonise the NLM median groundwater depth over the flat land.

    The grid is national and carries a value over flat land only, so it is
    clipped to the extent before loading and the polygons are cut back to the
    flatland. A polygon per run of equal-valued cells fragments the flat land
    only, which the urban domain excludes.

    Args:
        depth_path: The grid, from :func:`landloss.io.readers.get_gwd_median_depth`.
        extent: The polygon being mapped.
        flatland: The NLM flatland polygons, in the study's system.

    Returns:
        Polygons carrying ``gw_depth_m``, clipped to the flat land.
    """
    west, south, east, north = extent.bounds
    with rioxarray.open_rasterio(depth_path, masked=True) as opened:
        depth = (
            opened.squeeze(drop=True)
            .rio.clip_box(minx=west, miny=south, maxx=east, maxy=north)
            .load()
        )
    values = depth.to_numpy().astype("float32")
    polygons = polygonise(
        values, depth, mask=np.isfinite(values), column="gw_depth_m"
    ).to_crs(constants.DEFAULT_CRS)
    if polygons.empty or flatland.empty:
        return polygons.iloc[0:0]
    return gpd.clip(polygons, flatland).reset_index(drop=True)


def polygonise_residual(residual, *, threshold_m):
    """Polygonise the cut and fill the thresholded 30 m residual marks.

    Args:
        residual: The 30 m cut-and-fill residual on the 1 m grid.
        threshold_m: The magnitude beyond which the residual marks a cut or a
            fill, ``config.RESIDUAL_MODIFICATION_THRESHOLD_M``.

    Returns:
        Polygons carrying ``modification`` as ``cut`` or ``fill``; natural and
        unknown cells are left out, because natural is the default anyway.
    """
    classed = ground_map.modification_from_residual(
        residual.to_numpy(), threshold_m=threshold_m
    )
    codes = np.zeros(classed.shape, dtype="uint8")
    for name, code in RESIDUAL_CODES.items():
        codes[classed == name] = code
    polygons = polygonise(codes, residual, mask=codes > 0, column="code")
    names = {code: name for name, code in RESIDUAL_CODES.items()}
    polygons["modification"] = polygons["code"].astype(int).map(names)
    return polygons.drop(columns="code")


def mean_positive_residual(ground, residual):
    """Average the positive residual over each fill piece of the map.

    The fill thickness of a piece is the mean of the 100 m residual where it is
    positive -- ground standing above the 100 m surface -- over the cells
    inside the piece. Computed by burning each fill piece's row number onto
    the raster's grid and summing per label, so no polygon is clipped.

    Args:
        ground: The ground map, carrying ``modification``.
        residual: The 100 m cut-and-fill residual on the 1 m grid.

    Returns:
        The mean positive residual per row, NaN where the piece is not fill
        or holds no positive cell.
    """
    fill = ground.loc[ground["modification"] == "fill"]
    thickness = pd.Series(np.nan, index=ground.index, dtype=float)
    if fill.empty:
        return thickness

    labels = rasterize(
        zip(fill.geometry, range(1, len(fill) + 1), strict=True),
        out_shape=residual.shape,
        transform=residual.rio.transform(),
        fill=0,
        dtype="int32",
    )
    values = residual.to_numpy()
    positive = np.isfinite(values) & (values > 0)
    sums = np.bincount(
        labels[positive], weights=values[positive], minlength=len(fill) + 1
    )
    counts = np.bincount(labels[positive], minlength=len(fill) + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums[1:] / counts[1:]
    thickness.loc[fill.index] = np.where(counts[1:] > 0, means, np.nan)
    return thickness


def finish(ground, residual_100m):
    """Add the fill thickness, mint the ids, measure the area and order the columns.

    Args:
        ground: The attributed partition from ``build_ground_map``.
        residual_100m: The 100 m residual on the 1 m grid, for the thickness.

    Returns:
        The ground map with every column of ``COLUMNS``, sorted by location.
    """
    ground = ground.copy()
    ground["fill_thickness_m"] = mean_positive_residual(ground, residual_100m)
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
    *, pilot, use_cached_layers, default_gw_depth_m, residual_modification_threshold_m
):
    """Build the ground map over the extent and write it out.

    Args:
        pilot: Whether to run over ``SMALL_WLG_PILOT`` rather than the four
            territorial authorities.
        use_cached_layers: Whether to reuse the cached polygon layers.
        default_gw_depth_m: The depth to groundwater assumed off the NLM
            footprint, in metres.
        residual_modification_threshold_m: The magnitude of 30 m residual
            beyond which the ground is cut or fill where no mapping reaches.
    """
    bbox, extent_name = resolve_extent(pilot=pilot)
    extent = box(*bbox)
    describe_extent(extent_name, extent)

    print("\nReading the polygon sources ...", flush=True)
    materials = get_slide_interpreted_materials(bbox=bbox, use_cache=use_cached_layers)
    geology = get_wellington_urban_geology(bbox=bbox, use_cache=use_cached_layers)
    landforms = get_nlm_geomorphology(bbox=bbox, use_cache=use_cached_layers)
    genesis = get_slide_genesis(bbox=bbox, use_cache=use_cached_layers)
    cut = get_wcc_cut_areas(bbox=bbox, use_cache=use_cached_layers)
    fill = get_wcc_fill_areas(bbox=bbox, use_cache=use_cached_layers)
    flatland = read_flatland(extent)
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

    print("\nPolygonising the groundwater depth and the 30 m residual ...", flush=True)
    groundwater = polygonise_groundwater(get_gwd_median_depth(), extent, flatland)
    residual_30m = read_raster(residual_path(MODIFICATION_RESIDUAL_M, pilot=pilot))
    residual = polygonise_residual(
        residual_30m, threshold_m=residual_modification_threshold_m
    )
    print(f"  {'groundwater depth':<20} {len(groundwater):>6,} polygons")
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
            ground_map.NLM_GWD_SOURCE, groundwater, "gw_depth_m", "gw_depth_m", "medium"
        ),
    ]

    print("\nBuilding the planar partition and attributing it ...", flush=True)
    ground = ground_map.build_ground_map(
        extent,
        sources,
        flatland=flatland,
        default_gw_depth_m=default_gw_depth_m,
        crs=constants.DEFAULT_CRS,
    )
    residual_100m = read_raster(residual_path(THICKNESS_RESIDUAL_M, pilot=pilot))
    ground = finish(ground, residual_100m)

    out_path = ground_map_path(pilot=pilot)
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
        pilot=config.PILOT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        default_gw_depth_m=config.DEFAULT_GROUNDWATER_DEPTH_M,
        residual_modification_threshold_m=config.RESIDUAL_MODIFICATION_THRESHOLD_M,
    )
