"""One run of the urban slope and retaining wall chain, end to end, on a made-up world.

The world is built here by hand, so every outcome can be worked out on paper:

- two claims: claim 1 holds a face and the terrace above it, claim 2 the
  ground to the east, insured only on its lower flat land;
- landslide step 12's files for one exposure world: three failure polygons
  with their evacuated, imminent and inundated zones (the face of claim 1, a
  smaller polygon inside it, and a face on claim 2), the elements they grew
  from, and three wall units: a cut wall along the toe of claim 1's face, a
  fill wall along the crest of claim 2's face (on claim 2's property but far
  from its insured land, so uninsured), and a wall on claim 2's flat land
  with no polygon;
- a PGV grid, and one large-model landslide whose evacuated polygon covers
  claim 2's face.

The stages run in the order the step scripts run them, and each hand-over goes
through the file the step's own path function names, with every step's
``WORK_DIR`` pointed at ``tmp_path``: exposure rw step 6's wall probability on
its library function and its ``main`` (draw from step 12's draw, claim and
coverage filters, ``rw_id``, the drawn walls), landslide step 8 on its
script's ``read_step12_inputs``, ``read_polygons``, ``build_model`` and
``add_world_id`` (the zones of the world as polygons, checked against the drawn
walls), landslide step 9's ``main`` (draw, supersession, absorption, combined
realisation, wall outcomes), vul shaking rw step 9 on its script's helpers
(flat-land walls), vul landslide rw step 11's ``main`` (flags), vul landslide
land step 3's ``main`` (damaged area) and vul step 10's land and retaining
wall tables, written through ``world_loss_input_path``. The world and the
earthquake carry different ids, 1 and 2, so a swap of the two anywhere in the
chain shows in a file name or an id column. Step 12's files are built by hand
and checked against the columns step 8 and the wall probability read.

The draws are forced so the assertions are deterministic whatever the seed:
every wall unit is walled in the world and every unit is made a wall
(``p_wall`` set to 1 after the probability table is built), the wall medians
are far below the PGV for small and medium walls and far above it for large
ones, and the PGV is far above every localised median, so every polygon fails
and the large flat-land wall stands. The wall units are all on sloping ground
as step 12 builds them; the flat one is flagged ``is_flatland`` by hand so the
flat-land path of vul shaking rw step 9 stays covered.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
import xarray as xr
from shapely.geometry import LineString, box

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
from landloss.exposure.rw import population, wall_probability
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.hazard.landslide.urban import face_polygons, fragility, geometry
from landloss.hazard.landslide.urban import realisation as urban
from landloss.hazard.realisation import realisation_seed
from landloss.vul import loss_input
from landloss.vul.landslide.land import damaged_area
from landloss.vul.shaking import fragility as shaking_fragility
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    gen_insured_land,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_population,
    gen_wall_probability,
)
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import (
    s1_simulate_landslides,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_terrain_derivatives,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map import gen_ground_map
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    gen_urban_slope_fragility,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    gen_urban_slope_faces,
    gen_urban_slope_wall_units,
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

WALL_UNIT_HEIGHTS_M = {"toe": 2.0, "crest": 2.0, "flat": 3.0}
FACE_ANGLE_DEG = 45.0

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


# --- the synthetic inputs ------------------------------------------------------

# Step 12's polygons of the world: the step 12 polygon number, the element it
# grew from, that element's pif, whether the world walled it, and its
# evacuated, imminent and inundated zones (None where it has none). The nested
# polygon sits inside the face's evacuated ground and its pif is in no unit.
POLYGONS = {
    "face": (
        1,
        1,
        11,
        True,
        rect(0, 0, 30, 12),
        rect(0, 12, 30, 14),
        rect(0, -5, 30, 0),
    ),
    "nested": (2, 2, 12, False, rect(10, 4, 20, 9), rect(10, 9, 20, 10), None),
    "under_large": (
        3,
        3,
        13,
        True,
        rect(60, 0, 90, 12),
        rect(60, 12, 90, 14),
        rect(60, -5, 90, 0),
    ),
}

# Step 12's wall units: the id, the member pifs, whether on fill, the
# property, the source and the geometry.
UNITS = {
    "toe": ("WU0000001", [11], False, "P1", "pif", segment(0, 0, 30, 0)),
    "crest": ("WU0000002", [13], True, "P2", "pif", segment(60, 10, 90, 10)),
    "flat": ("WU0000003", [], False, "P2", "gns_only", segment(60, -15, 80, -15)),
}
CLAIM_OF_PROPERTY = {"P1": "CLM0000001", "P2": "CLM0000002"}

INSURED_LAND = {
    "L0000001": (CLAIM_1, rect(-5, -5, 40, 35)),
    "L0000002": (CLAIM_2, rect(50, -30, 100, -8)),
}

LARGE_EVACUATED = rect(55, -5, 95, 20)
LARGE_INUNDATED = rect(55, -12, 95, -5)


def make_zones():
    """Step 12's zones of the world, one row per polygon and zone."""
    rows = []
    for label, (polygon, element, _, walled, *zones) in POLYGONS.items():
        evacuated = zones[0]
        common = {
            "polygon": polygon,
            "element": element,
            "element_type": "free_face" if walled else "bank",
            "height_m": 10.0,
            "area_m2": evacuated.area,
            "depth_m": 1.0,
            "volume_m3": evacuated.area,
            "scenario": f"w{WORLD:03d}",
            "label": label,
        }
        for zone, shape in zip(geometry.GEOMETRY_KINDS, zones, strict=True):
            if shape is not None:
                rows.append({**common, "zone": zone, "geometry": shape})
    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=constants.DEFAULT_CRS)
    return frame.drop(columns="label")


def make_elements():
    """Step 12's elements, indexed by label, all on the one ground map piece."""
    values = list(POLYGONS.values())
    return pd.DataFrame(
        {
            "siz_id": [v[2] for v in values],
            "majority_ground_row": 0,
            "overall_angle_deg": FACE_ANGLE_DEG,
        },
        index=pd.Index([v[1] for v in values], name="label"),
    )


def make_ground_map():
    """The step 4 ground map: one colluvium piece over the whole world."""
    return gpd.GeoDataFrame(
        {
            "ground_id": ["GM0000001"],
            "material": ["colluvium"],
            "modification": ["natural"],
            "geology_value": [susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM],
            "prior_failure": ["none"],
            "gw_depth_m": [4.0],
        },
        geometry=[rect(GRID_X_MIN, GRID_Y_MAX - GRID_HEIGHT_M, 120, GRID_Y_MAX)],
        crs=constants.DEFAULT_CRS,
    )


def make_units():
    """Step 12's wall units, indexed by ``wall_unit_id``."""
    labels = list(UNITS)
    values = [UNITS[k] for k in labels]
    geometries = [v[5] for v in values]
    return gpd.GeoDataFrame(
        {
            "member_pif_ids": [v[1] for v in values],
            "is_fill": np.array([v[2] for v in values], dtype=bool),
            "property_id": pd.array([v[3] for v in values], dtype="string"),
            "unit_source": [v[4] for v in values],
            "p_wall": 0.5,
            "p_wall_basis": "prior",
            "height_m": [WALL_UNIT_HEIGHTS_M[k] for k in labels],
            "length_m": [g.length for g in geometries],
            "ground_material": "colluvium",
        },
        geometry=geometries,
        index=pd.Index([v[0] for v in values], name="wall_unit_id"),
        crs=constants.DEFAULT_CRS,
    )


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
    (gen_urban_slope_faces, "landslide"),
    (gen_urban_slope_wall_units, "landslide"),
    (gen_ground_map, "landslide"),
    (s1_simulate_landslides, "landslide"),
    (gen_urban_slope_fragility, "landslide"),
    (gen_urban_slope_realisation, "landslide"),
    (gen_site_class, "shaking"),
    (gen_pgv_realisations, "shaking"),
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
            gen_pgv_realisations.pgv_path(EARTHQUAKE, extent="wlg-pilot"), points
        ),
        site_class=step.sample_site_class(points, extent="wlg-pilot"),
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
                WORLD, EARTHQUAKE, extent="wlg-pilot"
            )
        ),
    )
    rw = loss_input.build_rw_table(
        walls,
        pd.read_parquet(
            gen_wall_damage_state.wall_damage_state_path(
                WORLD, EARTHQUAKE, extent="wlg-pilot"
            ),
            columns=[RW_ID_COLUMN, shaking_fragility.DAMAGE_STATE_COLUMN],
        ),
        pd.read_parquet(
            gen_wall_landslide_damage.wall_landslide_damage_path(
                WORLD, EARTHQUAKE, extent="wlg-pilot"
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
                name, WORLD, EARTHQUAKE, extent="wlg-pilot"
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
        patch.setattr(
            gen_terrain_derivatives, "TERRAIN_DIR", root / "landslide" / "terrain"
        )
        yield run_chain(root)


def run_chain(root):
    """The stages, in run order, each reading what the one before it wrote."""
    extent = "wlg-pilot"
    pgv_path = gen_pgv_realisations.pgv_path(EARTHQUAKE, extent=extent)
    pgv_path.parent.mkdir(parents=True, exist_ok=True)
    write_raster(constant_grid(PGV_M_S, SHAKING_CELL_M), pgv_path)
    write_raster(
        constant_grid(SITE_CLASS, SHAKING_CELL_M),
        gen_site_class.site_class_path(extent=extent),
    )
    tpi_path = gen_terrain_derivatives.terrain_path(
        "topographic-position-100m", extent=extent
    )
    tpi_path.parent.mkdir(parents=True, exist_ok=True)
    write_raster(constant_grid(0.0, SHAKING_CELL_M), tpi_path)
    pgv_rp = constant_grid(RATIO_M_S_PER_G, SHAKING_CELL_M)
    pga = constant_grid(1.0, SHAKING_CELL_M)
    wall_table = make_wall_table(root / "retaining-wall-fragility.csv")

    insured = write(
        make_insured_land(), gen_insured_land.insured_land_path(extent=extent)
    )
    large = write(
        make_large_rows(),
        s1_simulate_landslides.realisation_path(
            extent=extent, realisation_id=EARTHQUAKE
        ),
    )

    # Landslide step 12: the elements, the ground map, the wall units, the
    # world's draw (every unit walled) and the world's zones.
    write(make_ground_map(), gen_ground_map.ground_map_path(extent=extent))
    elements = make_elements()
    path = gen_urban_slope_faces.elements_path(extent=extent)
    path.parent.mkdir(parents=True, exist_ok=True)
    elements.to_parquet(path)
    units = make_units()
    units.to_parquet(gen_urban_slope_wall_units.wall_units_path(extent=extent))
    write(
        pd.DataFrame(
            {
                "world_id": np.int64(WORLD),
                "wall_unit_id": units.index.to_numpy(dtype=object),
                "walled": True,
            }
        ),
        gen_urban_slope_wall_units.wall_draws_path(extent=extent),
    )
    zones = write(
        make_zones(),
        gen_urban_slope_faces.zones_path(f"w{WORLD:03d}", extent=extent),
    )
    unit_ids = {label: UNITS[label][0] for label in UNITS}

    # Exposure rw step 6. Every unit is made a wall so the draw is certain,
    # and the flat one is put on flat land by hand.
    claim_ids = pd.Series(CLAIM_OF_PROPERTY, name=CLAIM_ID_COLUMN)
    claim_ids.index.name = "property_id"
    probabilities = wall_probability.gen_unit_probability_table(units, claim_ids)
    probabilities = write(
        probabilities, gen_wall_probability.wall_probability_path(extent=extent)
    )
    forced = probabilities.copy()
    forced["p_wall"] = 1.0
    forced["is_flatland"] = forced["wall_line_id"] == unit_ids["flat"]
    write(forced, gen_wall_probability.wall_probability_path(extent=extent))
    gen_wall_population.main(extent=extent, world_ids=[WORLD])
    walls = gpd.read_parquet(
        gen_wall_population.wall_population_path(WORLD, extent=extent)
    )
    drawn = gpd.read_parquet(gen_wall_population.drawn_walls_path(WORLD, extent=extent))

    # Landslide step 8, on the forced wall table rather than the packaged one.
    step8 = gen_urban_slope_fragility
    read_elements, read_units, ground_map = step8.read_step12_inputs(extent=extent)
    polygons = step8.read_polygons(
        WORLD,
        extent=extent,
        elements=read_elements,
        units=read_units,
        ground_map=ground_map,
    )
    slope_of = dict(
        zip(
            polygons[face_polygons.POLYGON_COLUMN],
            polygons[geometry.SLOPE_ID_COLUMN],
            strict=True,
        )
    )
    slope_of = {label: slope_of[POLYGONS[label][0]] for label in POLYGONS}
    model = step8.build_model(
        polygons,
        drawn,
        wall_table=wall_table,
        rate_setting=RATE_SETTING,
        pgv=pgv_rp,
        pga=pga,
        extent=extent,
    )
    model = step8.add_world_id(model, WORLD)
    model = write(model, step8.urban_slope_model_path(WORLD, extent=extent))

    # Landslide step 9: the run itself, then its draw again on the same inputs
    # for the assertions on each row.
    step9 = gen_urban_slope_realisation
    step9.main(extent=extent, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])
    combined = gpd.read_parquet(
        step9.combined_realisation_path(WORLD, EARTHQUAKE, extent=extent)
    )
    outcomes = pd.read_parquet(
        step9.urban_wall_outcome_path(WORLD, EARTHQUAKE, extent=extent)
    )
    read_model, _, pgv, read_large = step9.read_inputs(WORLD, EARTHQUAKE, extent=extent)
    rng = realisation_seed(
        constants.BASE_SEED, EARTHQUAKE, urban.URBAN_STREAM, world_id=WORLD
    )
    realised = step9.realise(read_model, pgv, read_large, rng)

    # Vul shaking rw step 9, flat-land walls only.
    states = write(
        flat_wall_states(walls, pgv_rp=pgv_rp, pga=pga, wall_table=wall_table),
        gen_wall_damage_state.wall_damage_state_path(WORLD, EARTHQUAKE, extent=extent),
    )

    # Vul landslide rw step 11 and vul landslide land step 3.
    gen_wall_landslide_damage.main(
        extent=extent, world_ids=[WORLD], realisation_ids=[EARTHQUAKE]
    )
    flags = pd.read_parquet(
        gen_wall_landslide_damage.wall_landslide_damage_path(
            WORLD, EARTHQUAKE, extent=extent
        )
    )
    gen_landslide_land_damage.main(
        extent=extent, world_ids=[WORLD], realisation_ids=[EARTHQUAKE]
    )
    damaged = pd.read_parquet(
        gen_landslide_land_damage.landslide_land_damage_path(
            WORLD, EARTHQUAKE, extent=extent
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
        "zones": zones,
        "elements": elements,
        "units": units,
        "ground_map": ground_map,
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
        "unit_ids": unit_ids,
        "slope_of": slope_of,
    }


# --- the hand-built inputs are what the steps write ---------------------------------


def test_the_hand_built_inputs_carry_the_columns_their_steps_write(chain):
    zones = chain["zones"]
    assert set(face_polygons.ZONE_COLUMNS) <= set(zones.columns)
    assert set(zones["zone"]) == set(geometry.GEOMETRY_KINDS)
    assert set(face_polygons.ELEMENT_COLUMNS) <= set(chain["elements"].columns)
    assert set(wall_probability.UNIT_COLUMNS) <= set(chain["units"].columns)
    assert chain["units"].index.name == "wall_unit_id"


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
    "landslide step 8 reads the zones": ("zones", face_polygons.ZONE_COLUMNS),
    "landslide step 8 reads the elements": (
        "elements",
        face_polygons.ELEMENT_COLUMNS,
    ),
    "landslide step 8 reads the wall units": ("units", face_polygons.UNIT_COLUMNS),
    "landslide step 8 reads the ground map": (
        "ground_map",
        face_polygons.GROUND_COLUMNS,
    ),
    "landslide step 8's polygons carry what the fragility reads": (
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
            "depth_evacuated_m",
            "depth_inundated_m",
            *geometry.GEOMETRY_KINDS,
            "geometry",
        ),
    ),
    "the wall probability reads the wall units": (
        "units",
        wall_probability.UNIT_COLUMNS,
    ),
    "the wall draw reads the probabilities": (
        "probabilities",
        population.REQUIRED_COLUMNS,
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
    hit = walls[walls[urban.WALL_LINE_ID_COLUMN] == chain["unit_ids"][label]]
    assert len(hit) == 1
    return hit[RW_ID_COLUMN].iloc[0]


def test_every_polygon_fails_under_the_forced_shaking(chain):
    assert chain["draws"][urban.FAILED_COLUMN].all()
    assert (chain["draws"][urban.P_FAIL_COLUMN] > 0.999).all()


def test_the_nested_pair_resolves_largest_first(chain):
    face = chain["slope_of"]["face"]
    nested = chain["slope_of"]["nested"]
    model = chain["model"]
    assert model[urban.WALL_STATE_COLUMN].iloc[model_row(chain, "nested")] == (
        geometry.NO_WALL
    )

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
    crest = chain["unit_ids"]["crest"]
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
    crest_line = chain["units"].geometry[crest]
    assert not chain["rw"].geometry.geom_equals(crest_line).any()


def test_the_flat_land_wall_has_no_slope_id(chain):
    flat = chain["unit_ids"]["flat"]
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
    insured_lines = {chain["unit_ids"][label] for label in ("toe", "flat")}
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
