"""Build the landslide reviewer page: one self-contained HTML file.

    uv run --frozen python src/scripts/landloss/reviewer/gen_reviewer_landslide.py

The page walks a reviewer through both landslide populations: the large
failures (terrain, ground map, slope units, a coverage model and landslide
step 3's draw) and the urban failures (ground step 4's faces, landslide step
4's zones, a fragility per polygon and landslide step 6's draw), then the land
damage vul takes from them. It shares ``template.html`` and its helpers with the
retaining wall page (``gen_reviewer_rw.py``) and is written to
``report/reviewer/landslide/landslide-reviewer<suffix>.html``.

**The page shows what the steps wrote; it recomputes nothing.** Maps are
cut-outs of current outputs, rasters are coloured as saved, and the charts count
or sum rows and cells. The only curves drawn are lognormals from the fitted
medians and dispersions the calibration table already holds.

**Two scales of site.** The urban steps read at house-lot scale, so most sites
are squares of ``2 x SITE_HALF_WIDTH_M``. The large failures read at slope-unit
scale, so ``sites.toml`` also holds a whole-pilot site (``scale = "pilot"``),
which carries only the layers that make sense at that scale.

**The page is internal.** It carries insured land with claim ids, so
``report/reviewer/`` is gitignored and the file must not leave T+T.
"""

import base64
import io
import json
import tomllib
from datetime import UTC, datetime

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import shapely
from matplotlib import colors as mcolors
from rasterio.transform import array_bounds
from rasterio.warp import (
    Resampling,
    calculate_default_transform,
    reproject,
    transform_bounds,
)
from rasterio.windows import from_bounds

from landloss.domain import constants
from landloss.exposure.rw import wall_type
from landloss.hazard.landslide import (
    instability_zones,
    slope_elements,
    slope_polygons,
    wall_units,
)
from landloss.hazard.landslide.urban import fragility, geometry, wall_type_fragility
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    drawn_walls_path,
    wall_population_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    wall_draws_path,
    wall_units_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    aspect_path,
    dem_path,
    slope_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    elements_path,
)
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import (
    gns_only_path,
    siz_table_path,
)
from scripts.landloss.ground.steps.s5_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
    pif_cut_fill_pips_path,
)
from scripts.landloss.hazard.landslide.steps.s1_slope_units.gen_slope_units import (
    slope_units_path,
)
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997.gen_hancox_1997_coverage import (
    coverage_path as hancox_coverage_path,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import (
    config as s1_config,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import (
    s1_simulate_landslides,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation.s1_simulate_landslides import (
    realisation_path as large_realisation_path,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.gen_wall_zones import (
    wall_elements_path,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
    urban_wall_outcome_path,
)
from scripts.landloss.hazard.landslide.steps.s8_kritikos_2015.gen_kritikos_2015_hazard import (
    coverage_path as kritikos_coverage_path,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR
from scripts.landloss.reviewer import config
from scripts.landloss.reviewer import gen_reviewer_rw as rw
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage.gen_landslide_land_damage import (
    landslide_land_damage_path,
)

HERE = rw.HERE
CONTENT_DIR = HERE / "landslide"
OUT_DIR = REPORT_DIR / "reviewer" / "landslide"

FIT_TABLE = "report/hazard/landslide/urban-fragility/tab/urban-area-calibration-fit.csv"

# Where a `{NAME}` in the content files is looked up, in this order. The
# landslide constants are spread over the library and landslide step 3's own modules, so
# one module is not enough; a name in none of them raises.
CONSTANT_SOURCES = [
    constants,
    s1_config,
    s1_simulate_landslides,
    instability_zones,
    slope_elements,
    slope_polygons,
    geometry,
    fragility,
    wall_type,
    wall_units,
    wall_type_fragility,
]

# Downstream outputs must be no older than the outputs they were built from.
STALENESS_PAIRS = [
    ("slope_10m", "slope_units"),
    ("ground_map", "slope_units"),
    ("pgv_realisation", "hancox_coverage"),
    ("ground_map", "hancox_coverage"),
    ("hancox_coverage", "large_realisation"),
    ("slope_units", "large_realisation"),
    ("ground_map", "sizs"),
    ("elements", "zones_world"),
    ("wall_draws", "zones_world"),
    ("zones_world", "urban_model"),
    ("drawn_walls", "urban_model"),
    ("urban_model", "realisation"),
    ("large_realisation", "realisation"),
    ("pgv_realisation", "realisation"),
    ("realisation", "land_damage"),
]

# How each raster is coloured: matplotlib colour map, range, and whether a zero
# is drawn clear (a coverage of 0 is "nothing fails here", not a colour).
RASTER_STYLE = {
    "slope_10m": {"cmap": "YlOrBr", "vmin": 0.0, "vmax": 50.0, "clear_zero": False},
    "tpi_100m": {"cmap": "RdBu_r", "vmin": -15.0, "vmax": 15.0, "clear_zero": False},
    "hancox_coverage": {
        "cmap": "YlOrRd",
        "vmin": 0.0,
        "vmax": 0.05,
        "clear_zero": True,
    },
    "kritikos_coverage": {
        "cmap": "YlOrRd",
        "vmin": 0.0,
        "vmax": 0.05,
        "clear_zero": True,
    },
}
COVERAGE_NOTE = (
    "clear = 0; 0.05 and above at the top colour; same scale for both models"
)
LEGEND_STOPS = 6

# Only these layers are carried for the whole-pilot site: the rest are house-lot
# scale and would make the page too large to open.
PILOT_LAYERS = {
    "slope_10m",
    "tpi_100m",
    "hancox_coverage",
    "kritikos_coverage",
    "ground_material",
    "flatland",
    "slope_units",
    "large_realisation",
    "urban_model_theta",
    "failures",
}
# Simplification for the whole-pilot site's polygons, in metres.
PILOT_SIMPLIFY_M = 2.0
# At pilot scale a polygon is a few pixels, so it carries only what colours it
# and names it; the house-lot sites carry the full column lists.
PILOT_COLUMNS = {
    "large_realisation": ["landslide_id", "land_class", "source_area_m2"],
    "urban_model_theta": ["slope_id", "wall_state", "theta"],
    "failures": ["slope_id", "population", "land_class", "wall_state"],
}

GROUND_COLUMNS = [
    "material",
    "modification",
    "is_flatland",
    "prior_failure",
    "gw_depth_m",
]
UNIT_COLUMNS = [
    "unit_id",
    "area_m2",
    "mean_slope_degrees",
    "relief_m",
    "flatland_share",
]
LARGE_COLUMNS = [
    "landslide_id",
    "land_class",
    "unit_id",
    "source_area_m2",
    "slope_degrees",
    "displacement_m",
    "depth_m",
]
MODEL_COLUMNS = [
    "slope_id",
    "wall_state",
    "fragility_basis",
    "wall_type",
    "size_class",
    "kingsbury_zone",
    "continuous_rating",
    "theta_base",
    "amp_factor",
    "rate_factor",
    "theta",
    "beta",
    "material",
    "modification",
    "area_m2",
]
FAILURE_COLUMNS = [
    "landslide_id",
    "population",
    "land_class",
    "slope_id",
    "wall_state",
    "pgv_m_s",
    "p_fail",
    "uniform",
    "depth_m",
]


def fill_constants(text):
    """Replace each ``{NAME}`` with today's value, from the first module holding it."""

    def value(match):
        name = match[1]
        for module in CONSTANT_SOURCES:
            if hasattr(module, name):
                return f"{getattr(module, name):g}"
        msg = (
            f"{{{name}}} names no constant in {[m.__name__ for m in CONSTANT_SOURCES]}"
        )
        raise AttributeError(msg)

    return rw.CONSTANT_PLACEHOLDER.sub(value, text)


def read_content(name):
    """A content file from ``landslide/``, parsed, with its constants filled in."""
    text = (CONTENT_DIR / name).read_text(encoding="utf-8")
    return tomllib.loads(fill_constants(text))


def layer_files(*, extent, world_id, realisation_id):
    """Every output the page reads, by the key the content files name it by."""
    w, r = world_id, realisation_id
    return {
        "dem_1m": dem_path(1, extent=extent),
        "dem_10m": dem_path(10, extent=extent),
        "slope_10m": slope_path(10, extent=extent),
        "aspect_10m": aspect_path(10, extent=extent),
        "tpi_100m": terrain_path("topographic-position-100m", extent=extent),
        "ground_map": ground_map_path(extent=extent),
        "slope_units": slope_units_path(extent=extent),
        "pgv_realisation": pgv_path(r, extent=extent),
        "hancox_coverage": hancox_coverage_path(r, extent=extent),
        "kritikos_coverage": kritikos_coverage_path(r, extent=extent),
        "large_realisation": large_realisation_path(extent=extent, realisation_id=r),
        "sizs": siz_table_path(extent=extent),
        "elements": elements_path(extent=extent),
        "gns_only": gns_only_path(extent=extent),
        "pif_cut_fill": pif_cut_fill_path(extent=extent),
        "pif_cut_fill_pips": pif_cut_fill_pips_path(extent=extent),
        "wall_units": wall_units_path(extent=extent),
        "wall_draws": wall_draws_path(extent=extent),
        "wall_elements": wall_elements_path(extent=extent),
        "zones_world": zones_path(f"w{w:03d}", extent=extent),
        "zones_walled": zones_path("walled", extent=extent),
        "zones_bare": zones_path("bare", extent=extent),
        "drawn_walls": drawn_walls_path(w, extent=extent),
        "wall_population": wall_population_path(w, extent=extent),
        "urban_model": urban_slope_model_path(w, extent=extent),
        "realisation": combined_realisation_path(w, r, extent=extent),
        "wall_outcome": urban_wall_outcome_path(w, r, extent=extent),
        "insured_land": insured_land_path(extent=extent),
        "land_damage": landslide_land_damage_path(w, r, extent=extent),
    }


# ---- rasters -----------------------------------------------------------------


def raster_legend(key):
    """The colour ramp of one raster layer, for the page's map key."""
    style = RASTER_STYLE[key]
    cmap = mpl.colormaps[style["cmap"]]
    return {
        "colors": [mcolors.to_hex(cmap(v)) for v in np.linspace(0, 1, LEGEND_STOPS)],
        "vmin": style["vmin"],
        "vmax": style["vmax"],
        "note": COVERAGE_NOTE if style["clear_zero"] else None,
    }


def raster_overlay(path, box, key):
    """A raster cut to a box, coloured and warped to web mercator for Leaflet.

    Warped with nearest neighbour, so each cell keeps the value the step wrote,
    and drawn pixelated on the page so a 10 m cell reads as one.
    """
    if not path.exists():
        return None
    style = RASTER_STYLE[key]
    with rasterio.open(path) as src:
        window = from_bounds(*box, transform=src.transform)
        data = src.read(1, window=window, masked=True, boundless=True)
        values = data.filled(np.nan).astype(float)
        transform = src.window_transform(window)
        crs = src.crs
    height, width = values.shape
    if height == 0 or width == 0:
        return None
    dst_transform, dst_width, dst_height = calculate_default_transform(
        crs, rw.WEB_MERCATOR, width, height, *box
    )
    warped = np.full((dst_height, dst_width), np.nan)
    reproject(
        values,
        warped,
        src_transform=transform,
        src_crs=crs,
        dst_transform=dst_transform,
        dst_crs=rw.WEB_MERCATOR,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    scaled = (warped - style["vmin"]) / (style["vmax"] - style["vmin"])
    rgba = mpl.colormaps[style["cmap"]](np.clip(np.nan_to_num(scaled), 0, 1))
    clear = ~np.isfinite(warped)
    if style["clear_zero"]:
        clear |= warped <= 0
    rgba[clear, 3] = 0.0
    west, south, east, north = transform_bounds(
        rw.WEB_MERCATOR,
        rw.WGS84,
        *array_bounds(dst_height, dst_width, dst_transform),
    )
    buffer = io.BytesIO()
    plt.imsave(buffer, rgba, format="png")
    png = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"png": png, "bounds": [[south, west], [north, east]]}


def raster_sum(path, *, cell_area=True):
    """The sum of a raster's cells (times cell area if asked) and its mean."""
    if not path.exists():
        return None, None
    with rasterio.open(path) as src:
        values = src.read(1, masked=True).astype(float).filled(np.nan)
        area = abs(src.res[0] * src.res[1])
    total = np.nansum(values) * (area if cell_area else 1.0)
    return float(total), float(np.nanmean(values))


# ---- vector layers -----------------------------------------------------------


def clipped(frame, box):
    """The rows of a polygon layer cut to the box, so big polygons stay small."""
    near = rw.around(frame, box)
    if near.empty:
        return near
    return gpd.clip(near, shapely.box(*box))


def pilot_ground(ground):
    """The ground map dissolved by material and the flatland, for the whole pilot."""
    material = (
        ground[["material", "geometry"]]
        .dissolve(by="material", as_index=False)
        .explode(index_parts=False)
    )
    material["geometry"] = material.geometry.simplify(PILOT_SIMPLIFY_M)
    flat = ground[ground["is_flatland"].fillna(value=False).astype(bool)]
    flat = flat[["geometry"]].dissolve().explode(index_parts=False)
    flat["geometry"] = flat.geometry.simplify(PILOT_SIMPLIFY_M)
    return material, flat


def simplified(frame):
    """A copy with every geometry simplified for the whole-pilot site."""
    frame = frame.copy()
    frame["geometry"] = frame.geometry.simplify(PILOT_SIMPLIFY_M)
    return frame


def site_layers(site, box, frames, files, pilot_cache):
    """Every map layer cut to one site, keyed as ``steps.toml`` names them."""
    layers = {}
    is_pilot = site.get("scale") == "pilot"
    for key in RASTER_STYLE:
        overlay = raster_overlay(files[key], box, key)
        if overlay is not None:
            layers[key] = overlay
    ground = frames["ground_map"]
    if ground is not None:
        if is_pilot:
            material, flat = pilot_cache["ground"]
            layers["ground_material"] = rw.to_geojson(material, ["material"])
            layers["flatland"] = rw.to_geojson(flat, [])
        else:
            near = clipped(ground, box)
            layers["ground_material"] = rw.to_geojson(near, GROUND_COLUMNS)
            flat = near[near["is_flatland"].fillna(value=False).astype(bool)]
            layers["flatland"] = rw.to_geojson(flat, [])
    if frames["slope_units"] is not None:
        units = (
            frames["slope_units"] if is_pilot else clipped(frames["slope_units"], box)
        )
        layers["slope_units"] = rw.to_geojson(units, UNIT_COLUMNS)
    vectors = [
        ("large_realisation", "large_realisation", LARGE_COLUMNS),
        ("urban_model_theta", "urban_model", MODEL_COLUMNS),
        ("failures", "realisation", FAILURE_COLUMNS),
    ]
    for layer, key, columns in vectors:
        frame = frames[key]
        if frame is None:
            continue
        if is_pilot:
            if layer == "failures":
                # Evacuated ground only: the runout and imminent rows would
                # double the page for a few pixels each.
                frame = frame[frame["land_class"] == "evacuated land"]
            frame, columns = simplified(frame), PILOT_COLUMNS[layer]
        else:
            frame = rw.around(frame, box)
        layers[layer] = rw.to_geojson(frame, columns)
    if not is_pilot:
        # The face, zone and pip layers are the retaining wall page's own cuts.
        layers.update(rw.site_layers(box, rw_frames(frames), walls=None))
    return layers


def rw_frames(frames):
    """The frames the retaining wall page's site cutter reads, None where absent."""
    keys = [
        "sizs",
        "pif_cut_fill",
        "pif_cut_fill_pips",
        "gns_only",
        "elements",
        "insured_land",
        "zones_world",
        "zones_walled",
        "zones_bare",
        "realisation",
        "wall_elements",
        "wall_units",
        "wall_draws",
    ]
    return {key: frames.get(key) for key in keys}


def pilot_site(files):
    """The whole-pilot site's centre and half width, from the 10 m DEM's extent."""
    with rasterio.open(files["dem_10m"]) as src:
        left, bottom, right, top = src.bounds
    return {
        "x": (left + right) / 2,
        "y": (bottom + top) / 2,
        "half_width_m": max(right - left, top - bottom) / 2,
    }


# ---- charts ------------------------------------------------------------------


def table_chart(title, frame):
    """A small table chart from a frame."""
    return {
        "kind": "table",
        "title": title,
        "rows": json.loads(frame.to_json(orient="records", double_precision=3)),
    }


def failed_share(model, failed_ids, by):
    """Polygons, failures and the failed share by one model column."""
    table = model.assign(failed=model["slope_id"].isin(failed_ids))
    grouped = table.groupby(by).agg(
        polygons=("slope_id", "size"), failed=("failed", "sum")
    )
    grouped["failed_share"] = (grouped["failed"] / grouped["polygons"]).round(3)
    return grouped.reset_index()


def localised_curves():
    """The unwalled curve as in code and as fitted, at three ratings.

    Read from the calibration table, which holds each candidate's medians at
    rating 0 and 150 and its dispersion; the median at rating R is the
    log-linear interpolation landslide step 5 uses. Before amplification and rate.
    """
    path = REPO_ROOT / FIT_TABLE
    if not path.exists():
        return None
    fits = pd.read_csv(path).set_index("curve")
    labels = {
        "committed": "in code (placeholder)",
        "adopted": "adopted fit (not ported)",
    }
    curves = []
    for name, band in labels.items():
        if name not in fits.index:
            continue
        row = fits.loc[name]
        theta0, theta150 = (
            row["theta_at_zero_rating_m_s"],
            row["theta_at_max_rating_m_s"],
        )
        for rating in (0, 75, 150):
            theta = theta0 * (theta150 / theta0) ** (rating / 150)
            curves.append(
                {
                    "label": f"rating {rating}, {band}",
                    "wall_type": f"rating {rating}",
                    "band": band,
                    "theta": float(theta),
                    "beta": float(row["beta"]),
                }
            )
    return {
        "kind": "curves",
        "title": "Unwalled polygon fragility, P(fail | PGV)",
        "note": "Kingsbury rating 0, 75 and 150, before amplification and the rate "
        "factor. Solid: what landslide step 5 uses; dashed: the adopted fit (LS-A32).",
        "x_max": 4.0,
        "x_label": "PGV (m/s)",
        "unit": "m/s",
        "curves": curves,
    }


def pilot_summaries(frames, files):
    """The pilot-wide charts the steps name, keyed as in ``steps.toml``."""
    charts = {}
    ground = frames["ground_map"]
    if ground is not None:
        area = ground.geometry.area
        by_material = (
            area.groupby(ground["material"].fillna("(none)")).sum() / 1e4
        ).round()
        charts["material_shares"] = {
            "kind": "bar",
            "title": "Ground map area by material (ha)",
            "data": [
                [m, int(a)] for m, a in by_material.sort_values(ascending=False).items()
            ],
        }
    flat_share = None
    if ground is not None:
        flat = ground["is_flatland"].fillna(value=False).astype(bool)
        flat_share = ground.geometry.area[flat].sum() / ground.geometry.area.sum()
    hancox_m2, hancox_mean = raster_sum(files["hancox_coverage"])
    kritikos_m2, kritikos_mean = raster_sum(files["kritikos_coverage"])
    tiles = []
    if hancox_m2 is not None:
        tiles += [
            ["Hancox expected failed area (m²)", f"{hancox_m2:,.0f}"],
            ["Hancox mean coverage", f"{hancox_mean:.4%}"],
        ]
    if kritikos_m2 is not None:
        tiles += [
            ["Kritikos expected area, flatland not masked (m²)", f"{kritikos_m2:,.0f}"],
            ["Kritikos mean coverage", f"{kritikos_mean:.3%}"],
        ]
    if flat_share is not None:
        tiles.append(["NLM flatland share of the pilot", f"{flat_share:.0%}"])
    if tiles:
        charts["coverage_tiles"] = {"kind": "tiles", "data": tiles}
    large = frames["large_realisation"]
    if large is not None:
        evacuated = large[large["land_class"] == "evacuated land"]
        charts["large_tiles"] = {
            "kind": "tiles",
            "data": [
                ["large failures drawn", f"{large['landslide_id'].nunique():,}"],
                ["evacuated area (m²)", f"{evacuated.geometry.area.sum():,.0f}"],
                ["coverage model", str(s1_config.COVERAGE_MODEL)],
            ],
        }
    sizs = frames["sizs"]
    if sizs is not None:
        seeds = sizs[sizs["is_siz"].fillna(value=False).astype(bool)]
        label = (
            seeds["ground_group"].astype(str) + " · " + seeds["height_band"].astype(str)
        )
        charts["sizs_by_group_band"] = {
            "kind": "bar",
            "title": "Siz pieces by ground group and height band",
            "data": sorted(rw.counts(label)),
        }
    zone_rows = []
    for key in ["zones_world", "zones_walled", "zones_bare"]:
        zones = frames[key]
        if zones is None:
            continue
        # Measured from each row's geometry: the zones table's area_m2 carries
        # the polygon's evacuated area on all three of its zone rows.
        area = zones.geometry.area.groupby(zones["zone"]).sum() / 1e4
        zone_rows.append({"scenario": key.removeprefix("zones_"), **area.round(1)})
    if zone_rows:
        charts["zone_areas"] = table_chart(
            "Zone area by scenario (ha, rows summed)", pd.DataFrame(zone_rows)
        )
    rule_rows = []
    for key in ["zones_world", "zones_walled", "zones_bare"]:
        zones = frames[key]
        if zones is None:
            continue
        evacuated = zones[zones["zone"] == "evacuated"]
        grouped = evacuated.groupby(["element_type", "width_rule"]).agg(
            polygons=("zone", "size"),
            share_floored=("width_floored", "mean"),
            width_m=("width_behind_crest_m", "median"),
            depth_m=("depth_m", "median"),
            volume_m3=("volume_m3", "median"),
            runout_m=("runout_m", "median"),
            imminent_width_m=("imminent_width_m", "median"),
        )
        grouped.insert(0, "scenario", key.removeprefix("zones_"))
        rule_rows.append(grouped.reset_index())
    if rule_rows:
        charts["zone_rules"] = table_chart(
            "Evacuated rules on the pilot: medians per polygon",
            pd.concat(rule_rows).round(2),
        )
    units, drawn = frames["wall_units"], frames["drawn_walls"]
    charts.update(rw.wall_model_charts(units, drawn))
    if units is not None and drawn is not None:
        charts["wall_tiles"] = {
            "kind": "tiles",
            "data": [
                ["wall units", f"{len(units):,}"],
                ["expected walls (sum p_wall)", f"{units['p_wall'].sum():,.0f}"],
                ["drawn walls (this world)", f"{len(drawn):,}"],
                ["median points", f"{units['wall_points'].median():+.0f}"],
            ],
        }
    curves = localised_curves()
    if curves is not None:
        charts["localised_curves"] = curves
    model = frames["urban_model"]
    if model is not None:
        by_state = model.groupby("wall_state").agg(
            polygons=("slope_id", "size"),
            median_theta_m_s=("theta", "median"),
            median_beta=("beta", "median"),
            median_amp_factor=("amp_factor", "median"),
        )
        charts["theta_by_wall_state"] = table_chart(
            "Landslide step 5 medians by wall state", by_state.round(3).reset_index()
        )
    realisation = frames["realisation"]
    if model is not None and realisation is not None:
        urban = realisation[realisation["population"] == "urban"]
        evacuated = urban[urban["land_class"] == "evacuated land"]
        failed_ids = set(evacuated["slope_id"])
        large_rows = realisation[realisation["population"] != "urban"]
        inundated = urban[urban["land_class"] == "inundated land"]
        charts["realisation_tiles"] = {
            "kind": "tiles",
            "data": [
                ["urban polygons (landslide step 5)", f"{len(model):,}"],
                ["failed", f"{len(failed_ids):,}"],
                ["failed share", f"{len(failed_ids) / len(model):.0%}"],
                ["evacuated (ha)", f"{evacuated.geometry.area.sum() / 1e4:,.1f}"],
                [
                    "inundated, rows summed (ha)",
                    f"{inundated.geometry.area.sum() / 1e4:,.1f}",
                ],
                ["large failure rows", f"{len(large_rows):,}"],
            ],
        }
        charts["failed_by_wall_state"] = table_chart(
            "Failed share by wall state", failed_share(model, failed_ids, "wall_state")
        )
        charts["failed_by_kingsbury_zone"] = table_chart(
            "Failed share by Kingsbury zone",
            failed_share(model, failed_ids, "kingsbury_zone"),
        )
    land = frames["land_damage"]
    if land is not None:
        tiles = [["land parcels in table", f"{len(land):,}"]]
        for column, label in [
            ("evacuated_area_m2", "evacuated (ha)"),
            ("inundated_area_m2", "inundated (ha)"),
        ]:
            if column in land.columns:
                tiles.append([label, f"{land[column].sum() / 1e4:,.2f}"])
        charts["land_damage_tiles"] = {"kind": "tiles", "data": tiles}
    return charts


# ---- checks ------------------------------------------------------------------


def staleness_checks(files):
    """Pairs whose downstream file is older than the file it is built from."""
    checks = []
    for upstream, downstream in STALENESS_PAIRS:
        up, down = files[upstream], files[downstream]
        if not (up.exists() and down.exists()):
            continue
        ok = down.stat().st_mtime >= up.stat().st_mtime
        checks.append(
            {
                "ok": ok,
                "text": f"{down.name} is "
                + ("newer than" if ok else "OLDER than")
                + f" {up.name}",
            }
        )
    return checks


def row_checks(frames):
    """Row counts that must agree between steps if they come from one run."""
    checks = []
    model, realisation = frames["urban_model"], frames["realisation"]
    if model is not None and realisation is not None:
        urban = realisation[realisation["population"] == "urban"]
        unknown = set(urban["slope_id"]) - set(model["slope_id"])
        checks.append(
            {
                "ok": not unknown,
                "text": f"landslide step 6 urban polygons not in the landslide step 5 model: {len(unknown):,}",
            }
        )
    large = frames["large_realisation"]
    if large is not None and realisation is not None:
        in_combined = int((realisation["population"] != "urban").sum())
        checks.append(
            {
                "ok": in_combined == len(large),
                "text": f"landslide step 3 rows: {len(large):,}; large rows in the "
                f"combined realisation: {in_combined:,}",
            }
        )
    return checks


# ---- page --------------------------------------------------------------------


def main(*, extent, world_id, realisation_id, site_half_width_m):
    """Read the current outputs and write the landslide reviewer page."""
    content = read_content("steps.toml")
    assumptions = read_content("assumptions.toml")["assumptions"]
    sites = read_content("sites.toml")["sites"]

    files = layer_files(extent=extent, world_id=world_id, realisation_id=realisation_id)
    frames = {
        key: rw.read_output(path) if path.suffix != ".tif" else None
        for key, path in files.items()
    }
    print(
        f"read {sum(f is not None for f in frames.values())} tables of "
        f"{sum(p.suffix != '.tif' for p in files.values())}"
    )

    used = {key for step in content["steps"] for key in step.get("layers", [])}
    pilot_cache = {}
    if frames["ground_map"] is not None:
        pilot_cache["ground"] = pilot_ground(frames["ground_map"])

    site_payload = []
    for site in sites:
        if site.get("scale") == "pilot":
            site = {**site, **pilot_site(files)}
        half = site.get("half_width_m", site_half_width_m)
        box = rw.site_box(site, half)
        layers = site_layers(site, box, frames, files, pilot_cache)
        keep = used & PILOT_LAYERS if site.get("scale") == "pilot" else used
        layers = {k: v for k, v in layers.items() if k in keep}
        dem = files["dem_10m"] if site.get("scale") == "pilot" else files["dem_1m"]
        centre = gpd.GeoSeries(
            gpd.points_from_xy([site["x"]], [site["y"]]), crs=rw.NZTM
        ).to_crs(rw.WGS84)
        site_payload.append(
            {
                **site,
                "centre": [centre.y.iloc[0], centre.x.iloc[0]],
                "layers": layers,
                "hillshade": rw.hillshade_overlay(dem, box),
            }
        )
        print(f"site {site['id']}: {len(layers)} layers")

    steps = content["steps"]
    rw.step_freshness(steps, files)
    for step in steps:
        step["table_data"] = [rw.read_table(path) for path in step.get("tables", [])]

    payload = {
        "title": content["title"],
        "short": content["short"],
        "overview": content["overview"],
        "flow": content["flow"],
        "inputs": content["inputs"],
        "steps": steps,
        "assumptions": assumptions,
        "sites": site_payload,
        "chains": {},
        "sections": {},
        "charts": pilot_summaries(frames, files),
        "raster_legends": {key: raster_legend(key) for key in RASTER_STYLE},
        "files": {key: rw.file_record(path) for key, path in files.items()},
        "checks": row_checks(frames) + staleness_checks(files),
        "build": {
            "extent": extent,
            "world_id": world_id,
            "realisation_id": realisation_id,
            "built": rw.stamp(datetime.now(tz=UTC).astimezone()),
            **rw.git_stamp(),
        },
    }
    out_path = OUT_DIR / f"landslide-reviewer{extent_suffix(extent)}.html"
    rw.write_page(payload, out_path)
    print(
        f"wrote {rw.repo_relative(out_path)} ({out_path.stat().st_size / 1e6:.1f} MB)"
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        site_half_width_m=config.SITE_HALF_WIDTH_M,
    )
