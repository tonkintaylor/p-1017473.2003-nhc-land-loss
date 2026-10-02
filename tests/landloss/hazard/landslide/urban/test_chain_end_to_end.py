"""One run of the urban slope and retaining wall chain, end to end, on a made-up world.

The world is built here by hand, so every outcome can be worked out on paper:

- a planar hillside falling south: flat land below ``y = 0``, a 45 degree face
  from 0 to 10 m, a terrace from 10 to 30 m and a 30 degree slope above it;
- two claims: claim 1 holds the face and the terrace, claim 2 the ground to the
  east, insured only on its lower flat land;
- three failure candidates at two scales: the face of claim 1 at 10 m, a 1 m
  patch nested inside it, and a second 10 m face on claim 2;
- three candidate wall lines: a cut wall along the toe of claim 1's face, a fill
  wall along the crest of claim 2's face (on claim 2's property but far from its
  insured land, so uninsured), and a wall on claim 2's flat land;
- a PGV grid, and one large-model landslide whose evacuated polygon covers
  claim 2's face.

The stages run in the order the step scripts run them, and each hand-over goes
through the file the step's own path function names, with every step's
``WORK_DIR`` pointed at ``tmp_path``: landslide step 7 on its script's helpers
(reconcile, relief, mint, nest, score, state geometries, column order),
exposure rw step 6's ``main`` (draw, claim and coverage filters, ``rw_id``, the
drawn walls), landslide step 8 on its script's ``build_model`` and
``add_world_id``, landslide step 9's ``main`` (draw, supersession, absorption,
combined realisation, wall outcomes), vul shaking rw step 9 on its script's
helpers (flat-land walls), vul landslide rw step 11's ``main`` (flags), vul
landslide land step 3's ``main`` (damaged area) and vul step 10's land and
retaining wall tables, written through ``world_loss_input_path``. The world and
the earthquake carry different ids, 1 and 2, so a swap of the two anywhere in
the chain shows in a file name or an id column. The candidates and the wall
lines are built by hand and checked against the columns steps 6 and the
exposure wall lines step write.

The draws are forced so the assertions are deterministic whatever the seed:
every line is made a wall (``p_wall`` set to 1 after the probability table is
built), the wall medians are far below the PGV for small and medium walls and
far above it for large ones, and the PGV is far above every localised median,
so every polygon fails and the large flat-land wall stands.
"""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
import xarray as xr
from shapely.geometry import LineString, box

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.common.utils.terrain import sample_at_points, write_raster
from landloss.domain import constants
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LAND_COLUMNS,
    LAND_ID_COLUMN,
    RW_COLUMNS,
    RW_ID_COLUMN,
)
from landloss.exposure.land.extent import (
    AREA_COLUMN,
    DWELLING_COUNT_COLUMN,
    LAND_RATE_INCL_GST_COLUMN,
)
from landloss.exposure.rw import lines as wall_lines
from landloss.exposure.rw import population, wall_probability
from landloss.exposure.rw.beta_population import classify_wall_size
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.hazard.landslide.urban import fragility, geometry
from landloss.hazard.landslide.urban import realisation as urban
from landloss.hazard.landslide.urban.delineation import SNAP_TOLERANCE_M
from landloss.hazard.realisation import realisation_seed
from landloss.vul import loss_input
from landloss.vul.landslide.land import damaged_area
from landloss.vul.shaking import fragility as shaking_fragility
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    gen_insured_land,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_lines,
    gen_wall_population,
    gen_wall_probability,
)
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import (
    s1_simulate_landslides,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates import (
    gen_urban_slope_candidates,
)
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons import (
    gen_urban_slope_polygons,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    gen_urban_slope_fragility,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class import gen_site_class
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import (
    gen_pgv_realisations,
)
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import (
    gen_landslide_land_damage,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import (
    gen_wall_landslide_damage,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import (
    gen_wall_damage_state,
)
from scripts.landloss.vul.steps.s10_property_damage import gen_property_damage

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM; every coordinate below is metres
# east and north of it.
X0 = 1_748_000.0
Y0 = 5_425_000.0

# The rasters cover x from -30 to 120 m and y from -50 to 60 m.
GRID_X_MIN = -30.0
GRID_Y_MAX = 60.0
GRID_WIDTH_M = 150.0
GRID_HEIGHT_M = 110.0
DEM_CELL_M = 1.0
SHAKING_CELL_M = 10.0

# Different ids, so a world and an earthquake swapped anywhere in the chain
# shows: every file name carries -w001-r002 and every id column 1 and 2.
WORLD = 1
EARTHQUAKE = 2
IDS_SUFFIX = f"-w{WORLD:03d}-r{EARTHQUAKE:03d}-pilot"
RATE_SETTING = "medium"

# Every face slopes down to the south.
SOUTH = 180.0

# The earthquake's PGV everywhere, m/s: far above every localised median (3 m/s
# at most before amplification) and every small or medium wall median, far
# below the large wall median.
PGV_M_S = 100.0
# Step 3's PGV at the return period over the unscaled PGA: the ratio a PGA wall
# median is converted at.
RATIO_M_S_PER_G = 1.2
SITE_CLASS = 3
# The wall table medians, in g on PGA: one that fails at any PGV, one that
# never does.
ALWAYS_FAILS_G = 1e-5
NEVER_FAILS_G = 1e4
WALL_BETA = 0.6

TOE_WALL_HEIGHT_M = 2.0
CREST_WALL_HEIGHT_M = 2.0
FLAT_WALL_HEIGHT_M = 3.0

# The two claims, their insured land and their property polygons.
CLAIM_1 = "CLM0000001"
CLAIM_2 = "CLM0000002"

# The columns landslide step 1 writes, which the large rows below carry.
LARGE_COLUMNS = s1_simulate_landslides.OUTPUT_COLUMNS


def at(x, y):
    return (X0 + x, Y0 + y)


def rect(x_min, y_min, x_max, y_max):
    return box(X0 + x_min, Y0 + y_min, X0 + x_max, Y0 + y_max)


def segment(x_from, y_from, x_to, y_to):
    return LineString([at(x_from, y_from), at(x_to, y_to)])


def make_grid(values, resolution):
    """Wrap an array as a north-up raster over the world, y descending."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    eastings = X0 + GRID_X_MIN + resolution * (np.arange(columns) + 0.5)
    northings = Y0 + GRID_Y_MAX - resolution * (np.arange(rows) + 0.5)
    grid = xr.DataArray(values, dims=("y", "x"), coords={"y": northings, "x": eastings})
    return grid.rio.write_crs(constants.DEFAULT_CRS)


def constant_grid(value, resolution):
    shape = (round(GRID_HEIGHT_M / resolution), round(GRID_WIDTH_M / resolution))
    return make_grid(np.full(shape, value, dtype=float), resolution)


def hillside_dem():
    """Flat land, a 45 degree face, a terrace, then a 30 degree hillside."""
    rows = round(GRID_HEIGHT_M / DEM_CELL_M)
    columns = round(GRID_WIDTH_M / DEM_CELL_M)
    y = GRID_Y_MAX - DEM_CELL_M * (np.arange(rows) + 0.5)
    elevation = np.select(
        [y < 0.0, y < 10.0, y < 30.0],
        [np.zeros_like(y), y, np.full_like(y, 10.0)],
        default=10.0 + (y - 30.0) * math.tan(math.radians(30.0)),
    )
    return make_grid(np.tile(elevation[:, None], (1, columns)), DEM_CELL_M)


# --- the synthetic inputs ------------------------------------------------------

# The candidate columns of contract section 3.4, one value for all three.
CANDIDATE_DEFAULTS = {
    "slope_band": "45-60",
    "aspect_octant": 4,
    "slope_degrees": 45.0,
    "aspect_degrees": SOUTH,
    "slope_1m": 45.0,
    "slope_3m": 44.0,
    "slope_10m": 40.0,
    "slope_30m": 30.0,
    "face_height_5m": 5.0,
    "face_height_10m": 10.0,
    "cut_fill_residual_30m": 0.2,
    "cut_fill_residual_100m": 0.5,
    "profile_curvature": -0.01,
    "topographic_position_20m": 1.0,
    "topographic_position_100m": 2.0,
    "vegetation_height_m": 1.0,
    "building_distance_m": 8.0,
    "building_position": "below",
    "road_distance_m": 40.0,
    "boundary_distance_m": 5.0,
    "ground_id": "GM0000001",
    "material": "colluvium",
    "modification": "natural",
    "prior_failure": "none",
    "gw_depth_class": "well_drained",
    "gw_depth_m": 4.0,
    "fill_thickness_m": np.nan,
    "geology_value": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "relief_m": 10.0,
}

# Each candidate's label, delineation scale and face.
CANDIDATES = {
    "face": (10, rect(0, 0, 30, 10)),
    "nested": (1, rect(10, 4, 20, 9)),
    "under_large": (10, rect(60, 0, 90, 10)),
}

# Each line's label, then its source, mapped flag, claim, face height, position,
# flat-land flag, slope and geometry.
LINES = {
    "toe": (
        "terrain_break",
        False,
        CLAIM_1,
        TOE_WALL_HEIGHT_M,
        "cut",
        False,
        45.0,
        segment(0, 0, 30, 0),
    ),
    "crest": (
        "gns_mapped_wall",
        True,
        CLAIM_2,
        CREST_WALL_HEIGHT_M,
        "fill",
        False,
        45.0,
        segment(60, 10, 90, 10),
    ),
    "flat": (
        "property_boundary",
        False,
        CLAIM_2,
        FLAT_WALL_HEIGHT_M,
        "cut",
        True,
        2.0,
        segment(60, -15, 80, -15),
    ),
}

INSURED_LAND = {
    "L0000001": (CLAIM_1, rect(-5, -5, 40, 35)),
    "L0000002": (CLAIM_2, rect(50, -30, 100, -8)),
}

LARGE_EVACUATED = rect(55, -5, 95, 20)
LARGE_INUNDATED = rect(55, -12, 95, -5)


def make_candidates():
    """Step 6's candidates, minted by scale descending then location."""
    labels = list(CANDIDATES)
    rows = {
        column: [value] * len(labels) for column, value in CANDIDATE_DEFAULTS.items()
    }
    frame = gpd.GeoDataFrame(
        {
            "label": labels,
            "scale_m": np.array([CANDIDATES[k][0] for k in labels], dtype=np.int64),
            **rows,
        },
        geometry=[CANDIDATES[k][1] for k in labels],
        crs=constants.DEFAULT_CRS,
    )
    frame["area_m2"] = frame.geometry.area
    frame["contour_length_m"] = (
        frame.geometry.bounds["maxx"] - frame.geometry.bounds["minx"]
    )
    frame = sort_by_point(frame, by=("scale_m",), ascending=(False,))
    frame["candidate_id"] = mint_ids(constants.CANDIDATE_ID_PREFIX, len(frame))
    ids = dict(zip(frame["label"], frame["candidate_id"], strict=True))
    return frame[list(gen_urban_slope_candidates.OUTPUT_COLUMNS)], ids


def make_wall_lines():
    """Exposure rw step 6's candidate wall lines (contract section 3.5)."""
    labels = list(LINES)
    values = [LINES[k] for k in labels]
    heights = np.array([v[3] for v in values], dtype=float)
    geometries = [v[7] for v in values]
    frame = gpd.GeoDataFrame(
        {
            "label": labels,
            "source": [v[0] for v in values],
            "is_mapped_wall": np.array([v[1] for v in values], dtype=bool),
            "claim_id": [v[2] for v in values],
            "face_height_m": heights,
            "size_class": classify_wall_size(heights),
            "wall_position": [v[4] for v in values],
            "is_flatland": np.array([v[5] for v in values], dtype=bool),
            "ground_id": "GM0000001",
            "material": "colluvium",
            "modification": "natural",
            "is_rock_cut": False,
            "slope_degrees": [v[6] for v in values],
            "aspect_degrees": SOUTH,
            "dwelling_age_decade": pd.array([pd.NA] * len(labels), dtype="Int64"),
            "length_m": [g.length for g in geometries],
        },
        geometry=geometries,
        crs=constants.DEFAULT_CRS,
    )
    frame = gen_wall_lines.mint_wall_line_ids(frame[["label", *wall_lines.COLUMNS]])
    ids = dict(zip(frame.pop("label"), frame["wall_line_id"], strict=True))
    return frame, ids


def make_insured_land():
    """Exposure land step 5's insured land, one polygon per claim."""
    land_ids = list(INSURED_LAND)
    geometries = [INSURED_LAND[k][1] for k in land_ids]
    return gpd.GeoDataFrame(
        {
            LAND_ID_COLUMN: land_ids,
            CLAIM_ID_COLUMN: [INSURED_LAND[k][0] for k in land_ids],
            LAND_RATE_INCL_GST_COLUMN: [500.0, 400.0],
            AREA_COLUMN: [g.area for g in geometries],
            DWELLING_COUNT_COLUMN: np.array([1, 1], dtype=np.int64),
        },
        geometry=geometries,
        crs=constants.DEFAULT_CRS,
    )


def make_barriers():
    """A house on claim 1's terrace and a road well below the flat land."""
    building = rect(5, 15, 25, 25)
    road = segment(-30, -40, 120, -40).buffer(5.0)
    return gpd.GeoSeries([building, road], crs=constants.DEFAULT_CRS)


def make_wall_table(path):
    """A wall fragility table in the packaged CSV's form, medians forced."""
    rows = []
    for size_class in ("small", "medium", "large"):
        theta = NEVER_FAILS_G if size_class == "large" else ALWAYS_FAILS_G
        for condition in ("modern", "poor"):
            rows.append(
                {
                    "wall_class": fragility.UNNAMED_WALL_CLASS,
                    "size_class": size_class,
                    "initial_condition": condition,
                    "im": fragility.PGA_IM,
                    "theta": theta,
                    "beta": WALL_BETA,
                    "published_height_m": 3.0,
                    "damage_state": "extensive",
                    "source": f"synthetic_{size_class}",
                    "basis": "forced for the chain test",
                }
            )
    pd.DataFrame(rows, columns=list(fragility.WALL_TABLE_COLUMNS)).to_csv(
        path, index=False
    )
    return fragility.load_retaining_wall_fragility(path)


def make_large_rows():
    """Landslide step 1's large-model realisation: one evacuated and inundated pair."""
    base = {
        column: [np.nan, np.nan] for column in LARGE_COLUMNS if column != "geometry"
    }
    base.update(
        {
            "realisation_id": np.array([EARTHQUAKE, EARTHQUAKE], dtype=np.int64),
            "landslide_id": ["LS0000001", "LS0000001"],
            "population": [urban.LARGE, urban.LARGE],
            "unit_id": ["SU0000001", "SU0000001"],
            "slope_id": [None, None],
            LAND_CLASS_COLUMN: [EVACUATED, INUNDATED],
            "source_area_m2": [LARGE_EVACUATED.area] * 2,
            "volume_m3": [2.0 * LARGE_EVACUATED.area] * 2,
            "depth_m": [2.0, 1.0],
        }
    )
    frame = gpd.GeoDataFrame(
        base, geometry=[LARGE_EVACUATED, LARGE_INUNDATED], crs=constants.DEFAULT_CRS
    )
    return frame[list(LARGE_COLUMNS)]


# --- the stages, as the step scripts run them ------------------------------------

# Every step module whose path functions the chain writes or reads through, and
# the folder under the chain's root its WORK_DIR is pointed at.
WORK_DIRS = (
    (gen_urban_slope_candidates, "landslide"),
    (gen_urban_slope_polygons, "landslide"),
    (s1_simulate_landslides, "landslide"),
    (gen_urban_slope_fragility, "landslide"),
    (gen_urban_slope_realisation, "landslide"),
    (gen_site_class, "shaking"),
    (gen_pgv_realisations, "shaking"),
    (gen_wall_lines, "exposure"),
    (gen_wall_probability, "exposure"),
    (gen_wall_population, "exposure"),
    (gen_insured_land, "exposure"),
    (gen_wall_damage_state, "vul"),
    (gen_wall_landslide_damage, "vul"),
    (gen_landslide_land_damage, "vul"),
    (gen_property_damage, "vul"),
)


def write(frame, path):
    """Write a stage's output where its path function says and read it back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(frame, gpd.GeoDataFrame):
        frame.to_parquet(path)
        return gpd.read_parquet(path)
    frame.to_parquet(path, index=False)
    return pd.read_parquet(path)


def build_polygons(candidates, lines, *, dem_path, barriers):
    """Landslide step 7, on its script's helpers in the order ``main`` runs them."""
    step = gen_urban_slope_polygons
    polygons = geometry.reconcile_candidates(
        candidates, lines, tolerance_m=SNAP_TOLERANCE_M
    )
    polygons[geometry.RELIEF_COLUMN] = step.recompute_relief(polygons, dem_path)
    polygons = step.mint_slope_ids(polygons)
    polygons[geometry.PARENT_SLOPE_ID_COLUMN] = geometry.nest_parents(polygons)
    polygons = step.score_ground(polygons)
    polygons = geometry.attach_state_geometries(
        polygons, lines, barriers=barriers, tolerance_m=SNAP_TOLERANCE_M
    )
    return step.order_columns(polygons, candidates.columns)


def flat_wall_states(walls, *, pgv_rp, pga, wall_table):
    """Vul shaking rw step 9, on its script's helpers, for one world and earthquake."""
    step = gen_wall_damage_state
    flat = step.flat_land_walls(walls)
    points = step.midpoints(flat)
    return step.build_states(
        flat,
        world_id=WORLD,
        realisation_id=EARTHQUAKE,
        pgv_m_s=sample_at_points(
            gen_pgv_realisations.pgv_path(EARTHQUAKE, pilot=True), points
        ),
        site_class=step.sample_site_class(points, pilot=True),
        pgv_pga_ratio=fragility.pgv_pga_ratio_m_s_per_g(pgv_rp, pga, points),
        table=wall_table,
    )


def loss_tables(insured, walls, liquefaction):
    """Vul step 10's land and retaining wall tables, through the path functions."""
    land = loss_input.build_land_table(
        insured,
        liquefaction,
        pd.read_parquet(
            gen_landslide_land_damage.landslide_land_damage_path(
                WORLD, EARTHQUAKE, pilot=True
            )
        ),
    )
    rw = loss_input.build_rw_table(
        walls,
        pd.read_parquet(
            gen_wall_damage_state.wall_damage_state_path(WORLD, EARTHQUAKE, pilot=True),
            columns=[RW_ID_COLUMN, shaking_fragility.DAMAGE_STATE_COLUMN],
        ),
        pd.read_parquet(
            gen_wall_landslide_damage.wall_landslide_damage_path(
                WORLD, EARTHQUAKE, pilot=True
            )
        ),
    )
    written = {}
    for name, table in (("land", land), ("rw", rw)):
        table = gen_property_damage.in_default_crs(table, name)
        table.insert(0, urban.REALISATION_ID_COLUMN, EARTHQUAKE)
        table.insert(1, urban.WORLD_ID_COLUMN, WORLD)
        written[name] = write(
            table,
            gen_property_damage.world_loss_input_path(
                name, WORLD, EARTHQUAKE, pilot=True
            ),
        )
    return written


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Run every stage once and keep what each one wrote and read."""
    root = tmp_path_factory.mktemp("chain")
    with pytest.MonkeyPatch.context() as patch:
        for module, folder in WORK_DIRS:
            patch.setattr(module, "WORK_DIR", root / folder)
        yield run_chain(root)


def run_chain(root):
    """The stages, in run order, each reading what the one before it wrote."""
    pilot = True
    dem_path = write_raster(hillside_dem(), root / "dem-1m.tif")
    pgv_path = gen_pgv_realisations.pgv_path(EARTHQUAKE, pilot=pilot)
    pgv_path.parent.mkdir(parents=True, exist_ok=True)
    write_raster(constant_grid(PGV_M_S, SHAKING_CELL_M), pgv_path)
    write_raster(
        constant_grid(SITE_CLASS, SHAKING_CELL_M),
        gen_site_class.site_class_path(pilot=pilot),
    )
    pgv_rp = constant_grid(RATIO_M_S_PER_G, SHAKING_CELL_M)
    pga = constant_grid(1.0, SHAKING_CELL_M)
    wall_table = make_wall_table(root / "retaining-wall-fragility.csv")

    candidates, candidate_ids = make_candidates()
    candidates = write(
        candidates, gen_urban_slope_candidates.urban_slope_candidates_path(pilot=pilot)
    )
    lines, line_ids = make_wall_lines()
    lines = write(lines, gen_wall_lines.wall_lines_path(pilot=pilot))
    insured = write(
        make_insured_land(), gen_insured_land.insured_land_path(pilot=pilot)
    )
    large = write(
        make_large_rows(),
        s1_simulate_landslides.realisation_path(pilot=pilot, realisation_id=EARTHQUAKE),
    )

    # Landslide step 7.
    polygons = build_polygons(
        candidates, lines, dem_path=dem_path, barriers=make_barriers()
    )
    polygons = write(
        polygons, gen_urban_slope_polygons.urban_slope_polygons_path(pilot=pilot)
    )
    slope_ids = dict(
        zip(
            polygons[geometry.CANDIDATE_ID_COLUMN],
            polygons[geometry.SLOPE_ID_COLUMN],
            strict=True,
        )
    )
    slope_of = {label: slope_ids[candidate_ids[label]] for label in CANDIDATES}

    # Exposure rw step 6. Every line is made a wall so the draw is certain.
    probabilities = wall_probability.wall_probability_table(lines)
    probabilities = write(
        probabilities, gen_wall_probability.wall_probability_path(pilot=pilot)
    )
    forced = probabilities.copy()
    forced["p_wall"] = 1.0
    write(forced, gen_wall_probability.wall_probability_path(pilot=pilot))
    gen_wall_population.main(pilot=pilot, world_ids=[WORLD])
    walls = gpd.read_parquet(
        gen_wall_population.wall_population_path(WORLD, pilot=pilot)
    )
    drawn = gpd.read_parquet(gen_wall_population.drawn_walls_path(WORLD, pilot=pilot))

    # Landslide step 8, on the forced wall table rather than the packaged one.
    model = gen_urban_slope_fragility.build_model(
        polygons,
        drawn,
        wall_table=wall_table,
        rate_setting=RATE_SETTING,
        pgv=pgv_rp,
        pga=pga,
        pilot=pilot,
    )
    model = gen_urban_slope_fragility.add_world_id(model, WORLD)
    model = write(
        model, gen_urban_slope_fragility.urban_slope_model_path(WORLD, pilot=pilot)
    )

    # Landslide step 9: the run itself, then its draw again on the same inputs
    # for the assertions on each row.
    step9 = gen_urban_slope_realisation
    step9.main(pilot=pilot, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])
    combined = gpd.read_parquet(
        step9.combined_realisation_path(WORLD, EARTHQUAKE, pilot=pilot)
    )
    outcomes = pd.read_parquet(
        step9.urban_wall_outcome_path(WORLD, EARTHQUAKE, pilot=pilot)
    )
    read_model, _, pgv, read_large = step9.read_inputs(WORLD, EARTHQUAKE, pilot=pilot)
    rng = realisation_seed(
        constants.BASE_SEED, EARTHQUAKE, urban.URBAN_STREAM, world_id=WORLD
    )
    realised = step9.realise(read_model, pgv, read_large, rng)

    # Vul shaking rw step 9, flat-land walls only.
    states = write(
        flat_wall_states(walls, pgv_rp=pgv_rp, pga=pga, wall_table=wall_table),
        gen_wall_damage_state.wall_damage_state_path(WORLD, EARTHQUAKE, pilot=pilot),
    )

    # Vul landslide rw step 11 and vul landslide land step 3.
    gen_wall_landslide_damage.main(
        pilot=pilot, world_ids=[WORLD], realisation_ids=[EARTHQUAKE]
    )
    flags = pd.read_parquet(
        gen_wall_landslide_damage.wall_landslide_damage_path(
            WORLD, EARTHQUAKE, pilot=pilot
        )
    )
    gen_landslide_land_damage.main(
        pilot=pilot, world_ids=[WORLD], realisation_ids=[EARTHQUAKE]
    )
    damaged = pd.read_parquet(
        gen_landslide_land_damage.landslide_land_damage_path(
            WORLD, EARTHQUAKE, pilot=pilot
        )
    )

    # Vul step 10. No liquefaction reaches this world.
    liquefaction = pd.DataFrame(
        {
            LAND_ID_COLUMN: pd.Series([], dtype=object),
            "ld_state": pd.Series([], dtype=object),
            "cost_nzd": pd.Series([], dtype=float),
            "damaged_area_m2": pd.Series([], dtype=float),
        }
    )
    tables = loss_tables(insured, walls, liquefaction)

    return {
        "root": root,
        "candidates": candidates,
        "lines": lines,
        "insured": insured,
        "large": large,
        "polygons": polygons,
        "probabilities": probabilities,
        "walls": walls,
        "drawn": drawn,
        "model": model,
        "draws": realised.draws,
        "absorbed_by": realised.absorbed_by,
        "superseded_by": realised.superseded_by,
        "survivors": realised.survivors,
        "combined": combined,
        "outcomes": outcomes,
        "states": states,
        "flags": flags,
        "damaged": damaged,
        "land": tables["land"],
        "rw": tables["rw"],
        "line_ids": line_ids,
        "slope_of": slope_of,
    }


# --- the hand-built inputs are what the steps write ---------------------------------


def test_the_hand_built_inputs_carry_the_columns_their_steps_write(chain):
    assert list(chain["candidates"].columns) == list(
        gen_urban_slope_candidates.OUTPUT_COLUMNS
    )
    assert list(chain["lines"].columns) == [
        gen_wall_lines.WALL_LINE_ID_COLUMN,
        *wall_lines.COLUMNS,
    ]


# --- every output names its world and earthquake ------------------------------------

# frame: (the file name it was written to, whether it carries realisation_id)
OUTPUT_NAMES = {
    "walls": (f"wall-population-w{WORLD:03d}-pilot.geoparquet", False),
    "drawn": (f"drawn-walls-w{WORLD:03d}-pilot.geoparquet", False),
    "model": (f"urban-slope-model-w{WORLD:03d}-pilot.geoparquet", False),
    "combined": (f"landslide-realisation{IDS_SUFFIX}.geoparquet", True),
    "outcomes": (f"urban-wall-outcome{IDS_SUFFIX}.parquet", True),
    "states": (f"wall-damage-state{IDS_SUFFIX}.geoparquet", True),
    "flags": (f"wall-landslide-damage{IDS_SUFFIX}.parquet", True),
    "damaged": (f"landslide-land-damage{IDS_SUFFIX}.parquet", True),
    "land": (f"loss-input-land{IDS_SUFFIX}.geoparquet", True),
    "rw": (f"loss-input-rw{IDS_SUFFIX}.geoparquet", True),
}


@pytest.mark.parametrize("frame_name", list(OUTPUT_NAMES))
def test_every_output_is_named_and_stamped_with_the_world_and_earthquake(
    chain, frame_name
):
    file_name, has_realisation = OUTPUT_NAMES[frame_name]
    assert any(chain["root"].rglob(file_name)), f"no {file_name} was written"
    frame = chain[frame_name]
    assert not frame.empty
    assert (frame[urban.WORLD_ID_COLUMN] == WORLD).all()
    if has_realisation:
        assert (frame[urban.REALISATION_ID_COLUMN] == EARTHQUAKE).all()


# --- every column a stage reads is in the previous stage's output ---------------

# stage: (the frame it reads, the columns it reads from it), the columns taken
# from the reading module's own constants where it names them.
READS = {
    "landslide step 7 reads the candidates": (
        "candidates",
        (
            geometry.CANDIDATE_ID_COLUMN,
            geometry.SCALE_COLUMN,
            geometry.ASPECT_COLUMN,
            geometry.SLOPE_COLUMN,
            geometry.RELIEF_COLUMN,
            geometry.MATERIAL_COLUMN,
            geometry.FILL_THICKNESS_COLUMN,
            "modification",
            "face_height_10m",
            "geology_value",
            "prior_failure",
            "gw_depth_m",
            "topographic_position_100m",
            "geometry",
        ),
    ),
    "landslide step 7 reads the wall lines": (
        "lines",
        (
            geometry.WALL_LINE_ID_COLUMN,
            *geometry.LINE_COLUMNS.values(),
            geometry.IS_FLATLAND_COLUMN,
            "geometry",
        ),
    ),
    "the wall probability reads the wall lines": (
        "lines",
        (*wall_probability.WALL_INPUT_COLUMNS, wall_probability.HEIGHT_COLUMN),
    ),
    "the wall draw reads the probabilities": (
        "probabilities",
        population.REQUIRED_COLUMNS,
    ),
    "landslide step 8 reads the polygons": (
        "polygons",
        (
            geometry.SLOPE_ID_COLUMN,
            geometry.WALL_LINE_ID_COLUMN,
            geometry.WALL_LINE_IDS_COLUMN,
            geometry.WALL_POSITION_COLUMN,
            geometry.REP_POINT_COLUMN,
            "continuous_rating",
            "amp_factor",
            "kingsbury_rating",
            "kingsbury_zone",
            geometry.SCALE_COLUMN,
            geometry.AREA_COLUMN,
            geometry.SLOPE_COLUMN,
            geometry.MATERIAL_COLUMN,
            "modification",
            "face_height_10m",
            *geometry.STATE_DEPTH_COLUMNS,
            *geometry.STATE_GEOMETRY_COLUMNS,
            "geometry",
        ),
    ),
    "landslide step 8 reads the drawn walls": (
        "drawn",
        (
            RW_ID_COLUMN,
            geometry.WALL_LINE_ID_COLUMN,
            "size_class",
            "initial_condition",
            fragility.IS_FLATLAND_COLUMN,
        ),
    ),
    "landslide step 9 reads the model": (
        "model",
        (
            urban.SLOPE_ID_COLUMN,
            urban.WALL_LINE_ID_COLUMN,
            urban.WALL_LINE_IDS_COLUMN,
            urban.RW_ID_COLUMN,
            urban.WALL_STATE_COLUMN,
            urban.THETA_COLUMN,
            urban.BETA_COLUMN,
            urban.REP_POINT_COLUMN,
            urban.EVACUATED_GEOMETRY_COLUMN,
            urban.INUNDATED_GEOMETRY_COLUMN,
            urban.IMMINENT_GEOMETRY_COLUMN,
            urban.DEPTH_EVACUATED_COLUMN,
            urban.DEPTH_INUNDATED_COLUMN,
        ),
    ),
    "landslide step 9 reads the wall population": (
        "walls",
        (
            urban.RW_ID_COLUMN,
            urban.WALL_LINE_ID_COLUMN,
            urban.CLAIM_ID_COLUMN,
            urban.IS_FLATLAND_COLUMN,
        ),
    ),
    "landslide step 9 reads the large realisation": (
        "large",
        (
            urban.LANDSLIDE_ID_COLUMN,
            urban.POPULATION_COLUMN,
            LAND_CLASS_COLUMN,
            "geometry",
        ),
    ),
    "vul shaking rw step 9 reads the wall population": (
        "walls",
        (
            RW_ID_COLUMN,
            shaking_fragility.SIZE_CLASS_COLUMN,
            shaking_fragility.INITIAL_CONDITION_COLUMN,
            "is_flatland",
            "geometry",
        ),
    ),
    "vul landslide rw step 11 reads the wall population": (
        "walls",
        (RW_ID_COLUMN, CLAIM_ID_COLUMN, "geometry"),
    ),
    "vul landslide rw step 11 reads the combined realisation": (
        "combined",
        (LAND_CLASS_COLUMN, "geometry"),
    ),
    "vul landslide rw step 11 reads the wall outcomes": (
        "outcomes",
        (RW_ID_COLUMN, urban.SLOPE_ID_COLUMN, urban.OUTCOME_COLUMN),
    ),
    "vul landslide land step 3 reads the combined realisation": (
        "combined",
        (LAND_CLASS_COLUMN, damaged_area.DEPTH_COLUMN, "geometry"),
    ),
    "vul step 10 reads the wall population": (
        "walls",
        (
            RW_ID_COLUMN,
            CLAIM_ID_COLUMN,
            loss_input.SIZE_CLASS_COLUMN,
            loss_input.LENGTH_COLUMN,
            "geometry",
        ),
    ),
    "vul step 10 reads the wall damage states": (
        "states",
        (RW_ID_COLUMN, shaking_fragility.DAMAGE_STATE_COLUMN),
    ),
    "vul step 10 reads the wall flags": (
        "flags",
        (
            RW_ID_COLUMN,
            IS_DAMAGED_BY_SHAKING_COLUMN,
            IS_EVACUATED_COLUMN,
            IS_INUNDATED_COLUMN,
        ),
    ),
    "vul step 10 reads the land damage": (
        "damaged",
        (
            LAND_ID_COLUMN,
            *damaged_area.AREA_COLUMNS.values(),
            damaged_area.UNION_AREA_COLUMN,
            damaged_area.DEPTH_COLUMNS[INUNDATED],
        ),
    ),
}


@pytest.mark.parametrize("stage", list(READS))
def test_every_column_a_stage_reads_is_in_the_previous_stage_output(chain, stage):
    frame_name, columns = READS[stage]
    missing = [c for c in columns if c not in chain[frame_name].columns]
    assert not missing, f"{stage}: {frame_name} carries no {missing}"


# --- the outcomes ------------------------------------------------------------------


def model_row(chain, label):
    model = chain["model"]
    position = np.flatnonzero(
        model[urban.SLOPE_ID_COLUMN].to_numpy() == chain["slope_of"][label]
    )
    assert position.size == 1
    return int(position[0])


def urban_landslide_ids(chain):
    combined = chain["combined"]
    is_urban = combined[urban.POPULATION_COLUMN] == urban.URBAN
    return set(combined.loc[is_urban, urban.LANDSLIDE_ID_COLUMN])


def wall_rw_id(chain, label):
    walls = chain["walls"]
    hit = walls[walls[urban.WALL_LINE_ID_COLUMN] == chain["line_ids"][label]]
    assert len(hit) == 1
    return hit[RW_ID_COLUMN].iloc[0]


def test_every_polygon_fails_under_the_forced_shaking(chain):
    assert chain["draws"][urban.FAILED_COLUMN].all()
    assert (chain["draws"][urban.P_FAIL_COLUMN] > 0.999).all()


def test_the_nested_pair_resolves_largest_first(chain):
    polygons = chain["polygons"].set_index(geometry.SLOPE_ID_COLUMN)
    face = chain["slope_of"]["face"]
    nested = chain["slope_of"]["nested"]
    assert polygons.loc[nested, geometry.PARENT_SLOPE_ID_COLUMN] == face

    face_row, nested_row = model_row(chain, "face"), model_row(chain, "nested")
    assert chain["absorbed_by"][nested_row] == face_row
    assert chain["absorbed_by"][face_row] == urban.NONE
    assert chain["survivors"][face_row]
    assert not chain["survivors"][nested_row]
    assert face in urban_landslide_ids(chain)
    assert nested not in urban_landslide_ids(chain)


def test_an_urban_failure_under_the_large_polygon_is_superseded_and_counted_once(
    chain,
):
    row = model_row(chain, "under_large")
    assert chain["draws"][urban.FAILED_COLUMN].iloc[row]
    assert chain["superseded_by"][row] == 0
    assert chain["slope_of"]["under_large"] not in urban_landslide_ids(chain)

    # Its evacuated ground is in the combined realisation exactly once, in the
    # large polygon.
    evacuated = chain["model"][urban.EVACUATED_GEOMETRY_COLUMN].iloc[row]
    combined = chain["combined"]
    evacuated_rows = combined[combined[LAND_CLASS_COLUMN] == EVACUATED]
    shared = shapely.area(
        shapely.intersection(evacuated_rows.geometry.to_numpy(), evacuated)
    )
    sharing = evacuated_rows[shared > urban.SHARED_GROUND_TOLERANCE_M2]
    assert len(sharing) == 1
    assert sharing[urban.POPULATION_COLUMN].iloc[0] == urban.LARGE


def test_the_wall_on_the_failed_polygon_is_flagged(chain):
    rw_id = wall_rw_id(chain, "toe")
    outcomes = chain["outcomes"].set_index(RW_ID_COLUMN)
    assert outcomes.loc[rw_id, urban.OUTCOME_COLUMN] == urban.FAILED_WITH_POLYGON
    assert outcomes.loc[rw_id, urban.SLOPE_ID_COLUMN] == chain["slope_of"]["face"]

    flags = chain["flags"].set_index(RW_ID_COLUMN)
    assert flags.loc[rw_id, IS_DAMAGED_BY_SHAKING_COLUMN]
    rw = chain["rw"].set_index(RW_ID_COLUMN)
    assert rw.loc[rw_id, IS_DAMAGED_BY_SHAKING_COLUMN]


def test_the_uninsured_walls_polygon_takes_the_wall_fragility_and_writes_no_loss_row(
    chain,
):
    crest = chain["line_ids"]["crest"]
    drawn = chain["drawn"].set_index(urban.WALL_LINE_ID_COLUMN)
    assert pd.isna(drawn.loc[crest, RW_ID_COLUMN])

    row = chain["model"].iloc[model_row(chain, "under_large")]
    assert row[urban.WALL_LINE_ID_COLUMN] == crest
    assert pd.isna(row[RW_ID_COLUMN])
    assert row[urban.WALL_STATE_COLUMN] == geometry.FILL_WALL
    assert row["fragility_basis"] == fragility.WALL_BASIS
    assert row["fragility_source"] == "synthetic_medium"
    assert row["theta"] == pytest.approx(
        ALWAYS_FAILS_G * RATIO_M_S_PER_G / row["amp_factor"]
    )

    assert crest not in set(chain["walls"][urban.WALL_LINE_ID_COLUMN])
    assert crest not in set(chain["outcomes"][urban.WALL_LINE_ID_COLUMN])
    crest_line = chain["lines"].set_index("wall_line_id").geometry[crest]
    assert not chain["rw"].geometry.geom_equals(crest_line).any()


def test_the_flat_land_wall_has_no_slope_id(chain):
    flat = chain["line_ids"]["flat"]
    rw_id = wall_rw_id(chain, "flat")
    flags = chain["flags"].set_index(RW_ID_COLUMN)
    assert pd.isna(flags.loc[rw_id, urban.SLOPE_ID_COLUMN])
    assert pd.isna(flags.loc[rw_id, urban.OUTCOME_COLUMN])
    assert rw_id not in set(chain["outcomes"][RW_ID_COLUMN])
    assert flat not in set(chain["model"][urban.WALL_LINE_ID_COLUMN].dropna())

    states = chain["states"].set_index(RW_ID_COLUMN)
    assert states.loc[rw_id, shaking_fragility.DAMAGE_STATE_COLUMN] == (
        shaking_fragility.NO_DAMAGE
    )
    rw = chain["rw"].set_index(RW_ID_COLUMN)
    assert not rw.loc[rw_id, IS_DAMAGED_BY_SHAKING_COLUMN]


def test_the_retaining_wall_table_carries_every_insured_wall_once(chain):
    rw = chain["rw"]
    walls = chain["walls"]
    # Vul step 10 writes the ids in front of the contract's columns.
    assert list(rw.columns) == [
        urban.REALISATION_ID_COLUMN,
        urban.WORLD_ID_COLUMN,
        *RW_COLUMNS,
        "geometry",
    ]
    assert not rw[RW_ID_COLUMN].duplicated().any()
    assert sorted(rw[RW_ID_COLUMN]) == sorted(walls[RW_ID_COLUMN])
    insured_lines = {chain["line_ids"][label] for label in ("toe", "flat")}
    assert set(walls[urban.WALL_LINE_ID_COLUMN]) == insured_lines


def test_evacuated_polygons_in_the_combined_realisation_never_overlap(chain):
    combined = chain["combined"]
    evacuated = combined[combined[LAND_CLASS_COLUMN] == EVACUATED].geometry.to_numpy()
    assert len(evacuated) == 2
    for i in range(len(evacuated)):
        for j in range(i + 1, len(evacuated)):
            shared = shapely.area(shapely.intersection(evacuated[i], evacuated[j]))
            assert shared <= urban.SHARED_GROUND_TOLERANCE_M2


def test_the_land_table_measures_the_surviving_failures_on_the_insured_land(chain):
    land = chain["land"].set_index(LAND_ID_COLUMN)
    assert list(chain["land"].columns[2 : 2 + len(LAND_COLUMNS)]) == list(LAND_COLUMNS)

    face_row = model_row(chain, "face")
    face_evacuated = chain["model"][urban.EVACUATED_GEOMETRY_COLUMN].iloc[face_row]
    claim_1_land = INSURED_LAND["L0000001"][1]
    assert land.loc["L0000001", "evacuated_area"] == pytest.approx(
        face_evacuated.intersection(claim_1_land).area
    )
    # Only the large slide's inundated ground reaches claim 2's insured land.
    claim_2_land = INSURED_LAND["L0000002"][1]
    assert land.loc["L0000002", "evacuated_area"] == 0.0
    assert land.loc["L0000002", "inundated_insured_area"] == pytest.approx(
        LARGE_INUNDATED.intersection(claim_2_land).area
    )
