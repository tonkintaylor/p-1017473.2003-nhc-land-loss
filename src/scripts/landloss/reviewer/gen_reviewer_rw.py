"""Build the retaining wall reviewer page: one self-contained HTML file.

    uv run --frozen python src/scripts/landloss/reviewer/gen_reviewer_rw.py

The page walks a reviewer through the retaining wall chain, from the pips on the
DEM to the damage flags the loss module reads. Each step has its narrative, its
inputs and outputs, a map of example sites, pilot-wide summaries, key tables and
numbered assumption boxes. It is written to
``report/reviewer/rw/rw-reviewer<suffix>.html`` and needs no server: d3, Leaflet
and marked come from cdnjs, and everything else is inlined.

**The page shows what the steps wrote; it recomputes nothing.** Every map layer
is a cut-out of a current output around a site in ``rw/sites.toml``, so the maps
and counts are as fresh as the last run of each step. Only the narrative in
``rw/steps.toml`` and the register in ``rw/assumptions.toml`` can fall behind,
which is why each step's narrative carries the date it was checked and the page
flags a step whose data is newer.

**The wall work is moving, and the page is built to say so.** A missing output
leaves its step marked not built rather than stopping the build, and the
freshness panel lists every file's date and row count, together with the checks
that catch a downstream file left over from an earlier run.

**The page is internal.** It carries claim ids and claim report wall counts, so
``report/reviewer/`` is gitignored and the file must not leave T+T.
"""

import base64
import io
import json
import math
import re
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import rasterio
import shapely
from rasterio.transform import array_bounds
from rasterio.warp import (
    Resampling,
    calculate_default_transform,
    reproject,
    transform_bounds,
)
from rasterio.windows import from_bounds
from scipy.stats import norm

from landloss.domain import constants
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_age import (
    wall_age_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    drawn_walls_path,
    wall_population_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_probability import (
    wall_probability_path,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
    urban_wall_outcome_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    elements_path,
    gns_only_path,
    siz_table_path,
    wall_elements_path,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_wall_units import (
    wall_draws_path,
    wall_property_records_path,
    wall_units_path,
)
from scripts.landloss.hazard.landslide.steps.s13_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
    pif_cut_fill_pips_path,
)
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR
from scripts.landloss.reviewer import config
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage.gen_landslide_land_damage import (
    landslide_land_damage_path,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage.gen_wall_landslide_damage import (
    wall_landslide_damage_path,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state.gen_wall_damage_state import (
    wall_damage_state_path,
)
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

HERE = Path(__file__).resolve().parent
CONTENT_DIR = HERE / "rw"
TEMPLATE_PATH = HERE / "template.html"
OUT_DIR = REPORT_DIR / "reviewer" / "rw"

NZTM = "EPSG:2193"
WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"

# About 10 cm in degrees: fine enough for 1 m features, and it keeps the page
# small.
COORDINATE_PRECISION_DEG = 1e-6

# A constant named in braces in the content files, {BETA_WALL_BASE_P}.
CONSTANT_PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")

# Each table on the page is cut at this many rows; the CSV itself is linked.
MAX_TABLE_ROWS = 60

# Downstream outputs must be no older than the outputs they were built from.
# A pair that fails means the downstream step has not been rerun since.
STALENESS_PAIRS = [
    ("sizs", "pif_cut_fill"),
    ("pif_cut_fill", "wall_units"),
    ("wall_units", "wall_draws"),
    ("wall_draws", "zones_world"),
    ("wall_units", "wall_probability"),
    ("wall_probability", "drawn_walls"),
    ("wall_probability", "wall_population"),
    ("drawn_walls", "urban_model"),
    ("zones_world", "urban_model"),
    ("urban_model", "realisation"),
    ("realisation", "wall_outcome"),
    ("wall_population", "wall_landslide_damage"),
    ("wall_outcome", "wall_landslide_damage"),
    ("wall_landslide_damage", "loss_input_rw"),
    ("realisation", "land_damage"),
]

# The columns each map layer carries into the page. Everything else is dropped
# to keep the file small, and so nothing reaches the page unchosen.
UNIT_COLUMNS = [
    "wall_unit_id",
    "unit_source",
    "cut_fill_class",
    "is_siz",
    "gns_wall",
    "height_m",
    "length_m",
    "n_pifs",
    "p_prior",
    "p_prior_basis",
    "p_floor",
    "p_floor_basis",
    "p_claims",
    "p_wall",
    "p_wall_basis",
    "is_rock_cut",
    "is_fill",
    "is_natural",
    "is_property_boundary",
    "is_road_frontage",
    "held_out",
    "claim_walls",
    "nzmm_wall",
    "in_exposure",
    "property_id",
]
PIF_COLUMNS = [
    "pif_id",
    "parent_pif_id",
    "candidate_class",
    "is_siz",
    "is_wall_candidate",
    "n_pips",
    "near_drop_p80_m",
    "max_delta_h_m",
    "verticality",
    "gns_wall",
    "height_band",
    "ground_group",
]
ELEMENT_COLUMNS = [
    "element_type",
    "height_m",
    "area_m2",
    "overall_angle_deg",
    "ground_group",
]
WALL_COLUMNS = [
    "rw_id",
    "wall_line_id",
    "claim_id",
    "size_class",
    "wall_type",
    "age_bin",
    "height_m",
    "length_m",
    "wall_position",
    "is_flatland",
]
ZONE_COLUMNS = [
    "zone",
    "element_type",
    "style",
    "width_rule",
    "height_m",
    "depth_m",
    "area_m2",
    "forced",
]
SLIDE_COLUMNS = [
    "landslide_id",
    "population",
    "land_class",
    "wall_state",
    "rw_id",
    "p_fail",
    "uniform",
    "depth_m",
]
FLAG_COLUMNS = ["is_damaged_by_shaking", "is_evacuated", "is_inundated"]


def layer_files(*, extent, world_id, realisation_id):
    """Every output the page reads, by the key the content files name it by."""
    w, r = world_id, realisation_id
    return {
        "dem_1m": dem_path(1, extent=extent),
        "sizs": siz_table_path(extent=extent),
        "elements": elements_path(extent=extent),
        "gns_only": gns_only_path(extent=extent),
        "pif_cut_fill": pif_cut_fill_path(extent=extent),
        "pif_cut_fill_pips": pif_cut_fill_pips_path(extent=extent),
        "wall_units": wall_units_path(extent=extent),
        "wall_draws": wall_draws_path(extent=extent),
        "property_records": wall_property_records_path(extent=extent),
        "wall_elements": wall_elements_path(extent=extent),
        "zones_world": zones_path(f"w{w:03d}", extent=extent),
        "zones_walled": zones_path("walled", extent=extent),
        "zones_bare": zones_path("bare", extent=extent),
        "wall_probability": wall_probability_path(extent=extent),
        "wall_age": wall_age_path(extent=extent),
        "insured_land": insured_land_path(extent=extent),
        "drawn_walls": drawn_walls_path(w, extent=extent),
        "wall_population": wall_population_path(w, extent=extent),
        "urban_model": urban_slope_model_path(w, extent=extent),
        "realisation": combined_realisation_path(w, r, extent=extent),
        "wall_outcome": urban_wall_outcome_path(w, r, extent=extent),
        "wall_damage_state": wall_damage_state_path(w, r, extent=extent),
        "wall_landslide_damage": wall_landslide_damage_path(w, r, extent=extent),
        "loss_input_rw": world_loss_input_path("rw", w, r, extent=extent),
        "land_damage": landslide_land_damage_path(w, r, extent=extent),
    }


def fill_constants(text):
    """Replace each ``{NAME}`` with today's value of that constant.

    The wall constants change from one day to the next, so the content files
    name them rather than quote them. A name that is not in
    :mod:`landloss.domain.constants` raises ``AttributeError``, which is the
    point: a renamed constant must not leave a stale number on the page.
    """
    return CONSTANT_PLACEHOLDER.sub(lambda m: f"{getattr(constants, m[1]):g}", text)


def read_content(name):
    """A content file from ``rw/``, parsed, with its constants filled in."""
    text = (CONTENT_DIR / name).read_text(encoding="utf-8")
    return tomllib.loads(fill_constants(text))


def repo_relative(path):
    """The path as the reviewer would type it from the repository root."""
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def modified_at(path):
    """When a file was last written, in local time."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).astimezone()


def stamp(moment):
    """A date and time as the page prints it."""
    return moment.strftime("%Y-%m-%d %H:%M")


def file_record(path):
    """When a file was written, how big it is and, for a table, how many rows."""
    record = {"path": repo_relative(path), "exists": path.exists()}
    if not record["exists"]:
        return record
    stat = path.stat()
    record["modified"] = stamp(modified_at(path))
    record["size_mb"] = round(stat.st_size / 1e6, 2)
    if path.suffix == ".parquet" or path.name.endswith(".geoparquet"):
        record["rows"] = pq.read_metadata(path).num_rows
    return record


def read_output(path):
    """One output as a frame with its index as columns, or None if not built.

    A step that has not been run is something the page reports, so a missing
    file is not an error here.
    """
    if not path.exists():
        return None
    schema = pq.read_schema(path)
    is_geo = b"geo" in (schema.metadata or {})
    frame = gpd.read_parquet(path) if is_geo else pd.read_parquet(path)
    named_index = [name for name in frame.index.names if name is not None]
    return frame.reset_index() if named_index else frame


def records(frame, columns=None):
    """Rows of a frame as JSON-ready dicts, NaN as null."""
    if columns is not None:
        frame = frame[[c for c in columns if c in frame.columns]]
    return json.loads(pd.DataFrame(frame).to_json(orient="records"))


def counts(series):
    """A bar chart's data: each value of ``series`` and how often it occurs."""
    tally = series.fillna("(none)").astype(str).value_counts()
    return [[label, int(n)] for label, n in tally.items()]


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


def row_checks(frames, *, world_id):
    """Row counts that must agree between steps if they come from one run."""
    checks = []
    draws, drawn = frames["wall_draws"], frames["drawn_walls"]
    if draws is not None and drawn is not None:
        walled = int(draws.loc[draws["world_id"] == world_id, "walled"].sum())
        checks.append(
            {
                "ok": walled == len(drawn),
                "text": f"walled units in world {world_id}: {walled:,}; "
                f"drawn walls: {len(drawn):,}",
            }
        )
    population = frames["wall_population"]
    for key, label in [
        ("wall_outcome", "landslide step 9 outcomes"),
        ("wall_landslide_damage", "vul landslide rw flags"),
        ("loss_input_rw", "loss input rw rows"),
    ]:
        other = frames[key]
        if population is None or other is None:
            continue
        missing = int((~population["rw_id"].isin(other["rw_id"])).sum())
        checks.append(
            {
                "ok": missing == 0 and len(other) == len(population),
                "text": f"insured walls: {len(population):,}; {label}: "
                f"{len(other):,}; walls with no row: {missing:,}",
            }
        )
    return checks


def lognormal_beta(p15, p50):
    """The dispersion of a lognormal curve from its 15th and 50th percentiles."""
    return math.log(p50 / p15) / norm.ppf(0.85)


def fragility_curves():
    """The wall type curves as median and dispersion, for plotting only."""
    path = REPO_ROOT / "src" / "landloss" / "io" / "assets"
    table = pd.read_csv(path / "retaining-wall-type-fragility.csv")
    return [
        {
            "label": f"{row.wall_type} {row.size_class}",
            "wall_type": row.wall_type,
            "size_class": row.size_class,
            "theta": float(row.p50),
            "beta": lognormal_beta(float(row.p15), float(row.p50)),
        }
        for row in table.itertuples()
    ]


def pilot_summaries(frames):
    """The pilot-wide charts the steps name, keyed as in ``steps.toml``."""
    charts = {}
    sizs, units = frames["sizs"], frames["wall_units"]
    if sizs is not None:
        classes = counts(sizs["candidate_class"])
        if frames["gns_only"] is not None:
            classes.append(["gns_only (no pips)", len(frames["gns_only"])])
        charts["candidate_classes"] = {
            "kind": "bar",
            "title": "Pif pieces by candidate class",
            "data": classes,
        }
        charts["height_bands"] = {
            "kind": "bar",
            "title": "Pif pieces by height band",
            "data": sorted(counts(sizs["height_band"])),
        }
    if frames["pif_cut_fill"] is not None:
        charts["cut_fill_classes"] = {
            "kind": "bar",
            "title": "Pif pieces by cut/fill class",
            "data": counts(frames["pif_cut_fill"]["cut_fill_class"]),
        }
    if units is not None:
        charts["p_wall_basis"] = {
            "kind": "bar",
            "title": "Units by the stage that set p_wall",
            "data": counts(units["p_wall_basis"]),
        }
        edges = np.linspace(0.0, 1.0, 21)
        hist, _ = np.histogram(units["p_wall"].dropna(), bins=edges)
        charts["p_wall_hist"] = {
            "kind": "bar",
            "title": "Units by p_wall",
            "data": [
                [f"{lo:.2f}", int(n)] for lo, n in zip(edges[:-1], hist, strict=False)
            ],
        }
        charts["expected_walls"] = {
            "kind": "tiles",
            "data": [
                ["wall units", f"{len(units):,}"],
                ["expected walls (sum p_wall)", f"{units['p_wall'].sum():,.0f}"],
                ["units in exposure", f"{int(units['in_exposure'].sum()):,}"],
            ],
        }
    drawn, population = frames["drawn_walls"], frames["wall_population"]
    if drawn is not None and population is not None:
        charts["population_tiles"] = {
            "kind": "tiles",
            "data": [
                ["drawn walls (world)", f"{len(drawn):,}"],
                ["insured walls", f"{len(population):,}"],
                ["claims with a wall", f"{population['claim_id'].nunique():,}"],
            ],
        }
        for column in ["size_class", "wall_type", "age_bin", "wall_position"]:
            charts[column] = {
                "kind": "bar",
                "title": f"Insured walls by {column}",
                "data": counts(population[column]),
            }
    zone_rows = []
    for key in ["zones_world", "zones_walled", "zones_bare"]:
        zones = frames[key]
        if zones is None:
            continue
        area = zones.groupby("zone")["area_m2"].sum() / 1e4
        zone_rows.append({"scenario": key.removeprefix("zones_"), **area.round(1)})
    if zone_rows:
        charts["zone_areas"] = {
            "kind": "table",
            "title": "Zone area by scenario (ha)",
            "rows": json.loads(pd.DataFrame(zone_rows).to_json(orient="records")),
        }
    charts["fragility_curves"] = {
        "kind": "curves",
        "title": "Wall fragility, P(replace | PGA)",
        "note": "Lognormal through the table's p15 and p50, for display.",
        "curves": fragility_curves(),
    }
    if frames["wall_outcome"] is not None:
        charts["outcomes"] = {
            "kind": "bar",
            "title": "Insured walls by realisation outcome",
            "data": counts(frames["wall_outcome"]["outcome"]),
        }
    loss_rw = frames["loss_input_rw"]
    if loss_rw is not None:
        flagged = loss_rw[FLAG_COLUMNS].fillna(value=False).astype(bool)
        charts["flag_counts"] = {
            "kind": "bar",
            "title": "Loss input walls by flag",
            "data": [[c, int(flagged[c].sum())] for c in FLAG_COLUMNS]
            + [["any flag (replaced)", int(flagged.any(axis=1).sum())]],
        }
    land = frames["land_damage"]
    if land is not None:
        charts["land_damage_tiles"] = {
            "kind": "tiles",
            "data": [
                ["land parcels in table", f"{len(land):,}"],
                ["evacuated (ha)", f"{land['evacuated_area_m2'].sum() / 1e4:,.2f}"],
                ["inundated (ha)", f"{land['inundated_area_m2'].sum() / 1e4:,.2f}"],
            ],
        }
    return charts


def to_geojson(frame, columns):
    """A clipped layer as GeoJSON in WGS84, carrying only ``columns``."""
    keep = [c for c in columns if c in frame.columns]
    layer = gpd.GeoDataFrame(frame[keep], geometry=frame.geometry, crs=frame.crs)
    layer = layer.to_crs(WGS84)
    layer.geometry = shapely.set_precision(
        layer.geometry.array, COORDINATE_PRECISION_DEG
    )
    return json.loads(layer.to_json(drop_id=True))


def around(frame, box):
    """The rows of a layer whose geometry touches the box."""
    xmin, ymin, xmax, ymax = box
    return frame.cx[xmin:xmax, ymin:ymax]


def site_box(site, half_width_m):
    """The square cut out around a site, in NZTM."""
    x, y = site["x"], site["y"]
    return (x - half_width_m, y - half_width_m, x + half_width_m, y + half_width_m)


def joined_walls(frames):
    """Drawn walls with their insured status, outcome and damage flags."""
    walls = frames["drawn_walls"]
    if walls is None:
        return None
    walls = walls.copy()
    population = frames["wall_population"]
    walls["insured"] = (
        walls["rw_id"].isin(population["rw_id"]) if population is not None else False
    )
    if frames["wall_outcome"] is not None:
        outcome = frames["wall_outcome"].set_index("rw_id")
        walls["outcome"] = walls["rw_id"].map(outcome["outcome"])
        walls["taken_by"] = walls["rw_id"].map(outcome["taken_by"])
    if frames["loss_input_rw"] is not None:
        flags = frames["loss_input_rw"].set_index("rw_id")[FLAG_COLUMNS]
        for column in FLAG_COLUMNS:
            walls[column] = walls["rw_id"].map(flags[column])
    return walls


def site_layers(box, frames, walls):
    """Every map layer cut to one site, keyed as ``steps.toml`` names them."""
    layers = {}
    classes = None
    if frames["pif_cut_fill"] is not None:
        classes = frames["pif_cut_fill"].set_index("pif_id")["cut_fill_class"]
    sizs = frames["sizs"]
    if sizs is not None:
        pifs = around(sizs, box)
        spine = pifs["spine"]
        if not isinstance(spine, gpd.GeoSeries):
            spine = gpd.GeoSeries(shapely.from_wkb(spine), crs=sizs.crs)
        pifs = gpd.GeoDataFrame(pifs.drop(columns="geometry"), geometry=spine.values)
        pifs = pifs.set_crs(sizs.crs)
        if classes is not None:
            pifs["cut_fill_class"] = pifs["pif_id"].map(classes)
        layers["pifs"] = to_geojson(pifs, [*PIF_COLUMNS, "cut_fill_class"])
    pips = frames["pif_cut_fill_pips"]
    if pips is not None:
        xmin, ymin, xmax, ymax = box
        inside = pips["x"].between(xmin, xmax) & pips["y"].between(ymin, ymax)
        near = pips[inside].copy()
        if classes is not None:
            near["cut_fill_class"] = near["pif_id"].map(classes)
        points = gpd.GeoDataFrame(
            near, geometry=gpd.points_from_xy(near["x"], near["y"]), crs=NZTM
        )
        layers["pips"] = to_geojson(points, ["pif_id", "cut_fill_class"])
        has_foot = near["foot_x"].notna()
        feet = near[has_foot]
        ticks = shapely.linestrings(
            np.stack(
                [feet[["x", "foot_x"]].to_numpy(), feet[["y", "foot_y"]].to_numpy()],
                axis=-1,
            )
        )
        layers["pip_feet"] = to_geojson(
            gpd.GeoDataFrame(feet, geometry=ticks, crs=NZTM),
            ["cut_fill_class"],
        )
    simple = [
        ("gns_only", "gns_only", ["candidate_class", "length_m"]),
        ("elements", "elements", ELEMENT_COLUMNS),
        ("insured_land", "insured_land", ["land_id", "claim_id", "area_m2"]),
        ("zones_world", "zones_world", ZONE_COLUMNS),
        ("zones_walled", "zones_walled", ZONE_COLUMNS),
        ("zones_bare", "zones_bare", ZONE_COLUMNS),
        ("slides", "realisation", SLIDE_COLUMNS),
    ]
    for layer, key, columns in simple:
        if frames[key] is not None:
            layers[layer] = to_geojson(around(frames[key], box), columns)
    if frames["wall_elements"] is not None:
        elements = frames["wall_elements"]
        forced = elements[elements["forced"].fillna(value=False).astype(bool)]
        layers["forced"] = to_geojson(around(forced, box), ["wall_unit_id", "width_m"])
    units = frames["wall_units"]
    if units is not None:
        near_units = around(units, box).copy()
        draws = frames["wall_draws"]
        if draws is not None:
            walled = draws.set_index("wall_unit_id")["walled"]
            near_units["walled"] = near_units["wall_unit_id"].map(walled)
        layers["units"] = to_geojson(near_units, [*UNIT_COLUMNS, "walled"])
    if walls is not None:
        layers["walls"] = to_geojson(
            around(walls, box),
            [*WALL_COLUMNS, "insured", "outcome", "taken_by", *FLAG_COLUMNS],
        )
    return layers


def unit_chains(unit_ids, frames, walls):
    """One wall's whole story, from its unit to its damage flags, by unit id."""
    units = frames["wall_units"]
    if units is None:
        return {}
    chosen = units[units["wall_unit_id"].isin(unit_ids)]
    chains = {
        row["wall_unit_id"]: {"unit": row}
        for row in records(chosen, [*UNIT_COLUMNS, "member_pif_ids"])
    }
    if frames["wall_draws"] is not None:
        draws = frames["wall_draws"].set_index("wall_unit_id")["walled"]
        for unit_id, chain in chains.items():
            chain["walled"] = bool(draws.get(unit_id, default=False))
    if walls is not None:
        mine = walls[walls["wall_line_id"].isin(unit_ids)]
        wall_columns = [*WALL_COLUMNS, "insured", "outcome", "taken_by", *FLAG_COLUMNS]
        for row in records(mine, wall_columns):
            chains[row["wall_line_id"]]["wall"] = row
    return chains


def hillshade(dem, cell_m, azimuth_deg=315.0, altitude_deg=45.0):
    """A 0 to 1 hillshade of a DEM array, NaN where the DEM has no data."""
    dy, dx = np.gradient(dem, cell_m)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    azimuth, altitude = np.radians(azimuth_deg), np.radians(altitude_deg)
    shade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(
        slope
    ) * np.cos(azimuth - aspect)
    return np.clip(shade, 0.0, 1.0)


def hillshade_overlay(path, box):
    """A site's hillshade as a PNG for Leaflet, warped to web mercator.

    Leaflet lays an image on an axis-aligned box in latitude and longitude, which
    an NZTM grid is not: over a 120 m site the corners would sit metres off the
    1 m faces. Warping to web mercator first makes the image's box exact.
    """
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        window = from_bounds(*box, transform=src.transform)
        dem = src.read(1, window=window, masked=True, boundless=True).filled(np.nan)
        transform = src.window_transform(window)
        crs = src.crs
        cell_m = src.res[0]
    shade = hillshade(dem.astype(float), cell_m)
    height, width = shade.shape
    dst_transform, dst_width, dst_height = calculate_default_transform(
        crs, WEB_MERCATOR, width, height, *box
    )
    warped = np.full((dst_height, dst_width), np.nan)
    reproject(
        shade,
        warped,
        src_transform=transform,
        src_crs=crs,
        dst_transform=dst_transform,
        dst_crs=WEB_MERCATOR,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    west, south, east, north = transform_bounds(
        WEB_MERCATOR, WGS84, *array_bounds(dst_height, dst_width, dst_transform)
    )
    buffer = io.BytesIO()
    plt.imsave(buffer, warped, cmap="gray", vmin=0.0, vmax=1.0, format="png")
    png = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"png": png, "bounds": [[south, west], [north, east]]}


def read_table(relative_path):
    """A CSV for the page: its columns, its first rows and when it was written."""
    path = REPO_ROOT / relative_path
    if not path.exists():
        return {"path": relative_path, "exists": False}
    table = pd.read_csv(path)
    return {
        "path": relative_path,
        "exists": True,
        "modified": file_record(path)["modified"],
        "n_rows": len(table),
        "columns": [str(c) for c in table.columns],
        "rows": json.loads(
            table.head(MAX_TABLE_ROWS).to_json(orient="values", double_precision=4)
        ),
    }


def git_stamp():
    """The commit the page was built from, and whether the tree was clean."""

    def git(*args):
        result = subprocess.run(
            ["git", *args],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
    }


def step_freshness(steps, files):
    """For each step, its newest output's date and whether it postdates the text."""
    for step in steps:
        dates = [
            modified_at(files[key]) for key in step["outputs"] if files[key].exists()
        ]
        step["built"] = bool(dates)
        if dates:
            newest = max(dates)
            step["data_modified"] = stamp(newest)
            step["narrative_stale"] = newest.date().isoformat() > step["checked"]


def write_page(payload, out_path):
    """Inline the payload into the template and write the page."""
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    # A "</" inside the JSON would close the script element it sits in.
    data = data.replace("</", "<\\/")
    page = TEMPLATE_PATH.read_text(encoding="utf-8").replace("__REVIEWER_DATA__", data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")


def main(*, extent, world_id, realisation_id, site_half_width_m):
    """Read the current outputs and write the retaining wall reviewer page."""
    content = read_content("steps.toml")
    assumptions = read_content("assumptions.toml")["assumptions"]
    sites = read_content("sites.toml")["sites"]

    files = layer_files(extent=extent, world_id=world_id, realisation_id=realisation_id)
    frames = {
        key: read_output(path) if path.suffix != ".tif" else None
        for key, path in files.items()
    }
    walls = joined_walls(frames)
    print(
        f"read {sum(f is not None for f in frames.values())} of {len(frames)} outputs"
    )

    site_payload = []
    unit_ids = set()
    for site in sites:
        box = site_box(site, site_half_width_m)
        layers = site_layers(box, frames, walls)
        unit_ids.update(
            feature["properties"]["wall_unit_id"]
            for feature in layers.get("units", {}).get("features", [])
        )
        centre = gpd.GeoSeries(
            gpd.points_from_xy([site["x"]], [site["y"]]), crs=NZTM
        ).to_crs(WGS84)
        site_payload.append(
            {
                **site,
                "centre": [centre.y.iloc[0], centre.x.iloc[0]],
                "layers": layers,
                "hillshade": hillshade_overlay(files["dem_1m"], box),
            }
        )
        print(f"site {site['id']}: {len(layers)} layers")

    steps = content["steps"]
    step_freshness(steps, files)
    for step in steps:
        step["table_data"] = [read_table(path) for path in step.get("tables", [])]

    payload = {
        "title": content["title"],
        "short": content["short"],
        "overview": content["overview"],
        "flow": content["flow"],
        "inputs": content["inputs"],
        "steps": steps,
        "assumptions": assumptions,
        "sites": site_payload,
        "chains": unit_chains(unit_ids, frames, walls),
        "charts": pilot_summaries(frames),
        "files": {key: file_record(path) for key, path in files.items()},
        "checks": row_checks(frames, world_id=world_id) + staleness_checks(files),
        "build": {
            "extent": extent,
            "world_id": world_id,
            "realisation_id": realisation_id,
            "built": stamp(datetime.now(tz=UTC).astimezone()),
            **git_stamp(),
        },
    }
    out_path = OUT_DIR / f"rw-reviewer{extent_suffix(extent)}.html"
    write_page(payload, out_path)
    print(f"wrote {repo_relative(out_path)} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        site_half_width_m=config.SITE_HALF_WIDTH_M,
    )
