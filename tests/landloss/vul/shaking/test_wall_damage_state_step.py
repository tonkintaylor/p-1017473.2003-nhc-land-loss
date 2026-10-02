"""The wall damage state step end to end on synthetic inputs, with no network.

The step reads one world's wall population, the step 2 site class grid, step
3's PGV grid, step 5's PGV realisation and the TS1170.5 PGA grids. Here every
one of them is a small hand-built layer written where the step looks for it
(each producing step's work directory pointed at ``tmp_path``), the TS1170.5
reader is faked with a coarse grid per site class, and the wall table is a
synthetic six-row one, so the test is of what the step writes -- the file, its
columns, the conversion and the draw -- and not of the data it normally reads.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scipy.stats import norm
from shapely.geometry import LineString

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.landslide.urban import fragility as urban_fragility
from landloss.hazard.realisation import realisation_seed
from landloss.vul.shaking.fragility import (
    DAMAGE_STATES,
    NO_DAMAGE,
    PGA_IM,
    draw_damage_states,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import gen_wall_population
from scripts.landloss.hazard.shaking.steps.s2_site_class import gen_site_class
from scripts.landloss.hazard.shaking.steps.s3_pgv import gen_pgv
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import (
    gen_pgv_realisations,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import (
    gen_wall_damage_state as step,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# A 400 by 300 m box of 100 m cells on a round NZTM coordinate.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0
CELL_M = 100.0
RETURN_PERIOD_YR = 2500

SITE_CLASS = np.array(
    [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 1.0, 2.0], [3.0, 4.0, 5.0, np.nan]]
)
STEP3_PGV = np.array(
    [[0.5, 0.6, 0.7, 0.8], [0.9, 1.0, 0.5, 0.6], [0.7, 0.8, 0.9, np.nan]]
)
# A realisation of PGV: step 3's grid scaled by one factor, as step 5 writes.
FACTORS = {0: 1.1, 1: 0.9}


def pga_for_class(site_class: int) -> float:
    """The constant unscaled PGA the fake TS1170.5 grid carries per class."""
    return 0.5 + 0.1 * site_class


def make_grid(values, resolution=CELL_M, origin=(ORIGIN_EASTING, ORIGIN_NORTHING)):
    """Wrap an array as a north-up raster in NZTM with its top left at origin."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    left, top = origin
    eastings = left + resolution * (np.arange(columns) + 0.5)
    northings = top - resolution * (np.arange(rows) + 0.5)
    grid = xr.DataArray(values, dims=("y", "x"), coords={"y": northings, "x": eastings})
    return grid.rio.write_crs(constants.DEFAULT_CRS)


def cell_centre(row, column):
    return (
        ORIGIN_EASTING + CELL_M * (column + 0.5),
        ORIGIN_NORTHING - CELL_M * (row + 0.5),
    )


def wall_at(row, column, length_m=20.0):
    """A horizontal wall line whose midpoint is the centre of the cell."""
    x, y = cell_centre(row, column)
    return LineString([(x - length_m / 2, y), (x + length_m / 2, y)])


# rw_id, cell, size class, condition, flat land. The sloping walls must not be
# drawn; the last flat wall lies outside every grid.
WALLS = [
    ("C01-RW01", (0, 0), "small", "modern", True),
    ("C01-RW02", (0, 1), "medium", "poor", True),
    ("C02-RW01", (1, 1), "small", "poor", False),
    ("C02-RW02", (1, 2), "large", "modern", True),
    ("C03-RW01", (2, 0), "small", "poor", True),
    ("C03-RW02", (2, 2), "medium", "modern", False),
    ("C04-RW01", (5, 5), "large", "poor", True),
]


def wall_population():
    rows = [
        {
            "rw_id": rw_id,
            "claim_id": rw_id.split("-")[0],
            "wall_line_id": f"WL{i + 1:07d}",
            "world_id": 0,
            "size_class": size_class,
            "initial_condition": initial_condition,
            "height_m": 1.5,
            "length_m": 20.0,
            "wall_position": "fill",
            "is_flatland": is_flatland,
            "source": "property_boundary",
            "material": "alluvium",
            "geometry": wall_at(*cell),
        }
        for i, (rw_id, cell, size_class, initial_condition, is_flatland) in enumerate(
            WALLS
        )
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=constants.DEFAULT_CRS)


def wall_table():
    """Six unnamed-class rows: the small ones on PGA, the rest PGV-native."""
    rows = []
    for size_class, theta, im in (
        ("small", 0.5, PGA_IM),
        ("medium", 0.8, "pgv_m_s"),
        ("large", 1.0, "pgv_m_s"),
    ):
        for initial_condition, shift in (("modern", 1.0), ("poor", 0.7)):
            rows.append(
                {
                    "wall_class": "unnamed",
                    "size_class": size_class,
                    "initial_condition": initial_condition,
                    "im": im,
                    "theta": theta * shift,
                    "beta": 0.5,
                    "published_height_m": 2.0,
                    "damage_state": "collapse",
                    "source": f"test_{size_class}_{initial_condition}",
                    "basis": "synthetic",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    """Every input the step reads, written where it looks for it."""
    monkeypatch.setattr(gen_site_class, "WORK_DIR", tmp_path / "shaking")
    monkeypatch.setattr(gen_pgv, "WORK_DIR", tmp_path / "shaking")
    monkeypatch.setattr(gen_pgv_realisations, "WORK_DIR", tmp_path / "shaking")
    monkeypatch.setattr(gen_wall_population, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(step, "WORK_DIR", tmp_path / "vul")

    write_raster(
        make_grid(SITE_CLASS).astype("float32").rename("site_class"),
        gen_site_class.site_class_path(pilot=True),
    )
    write_raster(
        make_grid(STEP3_PGV).astype("float32").rename("pgv_m_s"),
        gen_pgv.output_path("pgv", return_period_yr=RETURN_PERIOD_YR, pilot=True),
    )
    for realisation_id, factor in FACTORS.items():
        write_raster(
            make_grid(STEP3_PGV * factor).astype("float32").rename("pgv_m_s"),
            gen_pgv_realisations.pgv_path(realisation_id, pilot=True),
        )

    population = wall_population()
    path = gen_wall_population.wall_population_path(0, pilot=True)
    path.parent.mkdir(parents=True)
    population.to_parquet(path)

    def fake_ts1170_pga(return_period_yr, site_class):
        assert return_period_yr == RETURN_PERIOD_YR
        # Two 1,000 m cells each way, covering the box with margin.
        coarse = np.full((2, 2), pga_for_class(site_class))
        return make_grid(coarse, 1000.0, (ORIGIN_EASTING - 300, ORIGIN_NORTHING + 300))

    monkeypatch.setattr(step, "get_ts1170_pga", fake_ts1170_pga)
    monkeypatch.setattr(urban_fragility, "load_retaining_wall_fragility", wall_table)
    return population


def read_states(world_id, realisation_id):
    return gpd.read_parquet(
        step.wall_damage_state_path(world_id, realisation_id, pilot=True)
    )


# --- path function --------------------------------------------------------------


def test_the_path_names_the_world_the_realisation_and_the_extent():
    assert (
        step.wall_damage_state_path(0, 3, pilot=True).name
        == "wall-damage-state-w000-r003-pilot.geoparquet"
    )
    assert (
        step.wall_damage_state_path(12, 1, pilot=False).name
        == "wall-damage-state-w012-r001.geoparquet"
    )
    assert step.wall_damage_state_path(0, 0, pilot=True).parent == step.WORK_DIR


# --- end to end ------------------------------------------------------------------


@ignore_affine_matmul
def test_the_output_carries_the_contract_columns_for_flat_land_walls_only(
    synthetic_run,
):
    step.main(
        pilot=True,
        world_ids=[0],
        realisation_ids=[0],
        return_period_yr=RETURN_PERIOD_YR,
    )
    states = read_states(0, 0)

    assert list(states.columns) == [
        "realisation_id",
        "world_id",
        "rw_id",
        "claim_id",
        "asset",
        "size_class",
        "initial_condition",
        "height_m",
        "length_m",
        "is_flatland",
        "pgv_m_s",
        "site_class",
        "theta_base_pga_g",
        "pgv_pga_ratio_m_s_per_g",
        "theta",
        "beta",
        "fragility_source",
        "failure_probability",
        "damage_state",
        "geometry",
    ]
    flat = [rw_id for rw_id, _, _, _, is_flat in WALLS if is_flat]
    assert list(states["rw_id"]) == flat
    assert states["is_flatland"].all()
    assert (states["asset"] == step.ASSET).all()
    assert (states["realisation_id"] == 0).all()
    assert (states["world_id"] == 0).all()
    assert states["site_class"].dtype == pd.Int64Dtype()
    assert set(states["damage_state"]) <= set(DAMAGE_STATES)
    assert states.crs == synthetic_run.crs
    assert states.geometry.geom_type.eq("LineString").all()
    assert list(states["claim_id"]) == [rw_id.split("-")[0] for rw_id in flat]


@ignore_affine_matmul
def test_pgv_and_the_site_class_are_sampled_at_the_midpoint(synthetic_run):
    step.main(
        pilot=True,
        world_ids=[0],
        realisation_ids=[1],
        return_period_yr=RETURN_PERIOD_YR,
    )
    states = read_states(0, 1).set_index("rw_id")

    for rw_id, (row, column), _, _, is_flat in WALLS:
        if not is_flat or row >= SITE_CLASS.shape[0]:
            continue
        assert states.loc[rw_id, "pgv_m_s"] == pytest.approx(
            STEP3_PGV[row, column] * FACTORS[1], rel=1e-6
        )
        assert states.loc[rw_id, "site_class"] == int(SITE_CLASS[row, column])


@ignore_affine_matmul
def test_a_pga_curve_is_converted_at_the_walls_own_ratio(synthetic_run):
    step.main(
        pilot=True,
        world_ids=[0],
        realisation_ids=[0],
        return_period_yr=RETURN_PERIOD_YR,
    )
    states = read_states(0, 0).set_index("rw_id")

    # C01-RW01: small, modern, 0.5 g published, in cell (0, 0) of class 1.
    ratio = STEP3_PGV[0, 0] / pga_for_class(1)
    wall = states.loc["C01-RW01"]
    assert wall["theta_base_pga_g"] == 0.5
    assert wall["pgv_pga_ratio_m_s_per_g"] == pytest.approx(ratio, rel=1e-6)
    assert wall["theta"] == pytest.approx(0.5 * ratio, rel=1e-6)
    assert wall["fragility_source"] == "test_small_modern"
    expected = norm.cdf(np.log(wall["pgv_m_s"] / wall["theta"]) / 0.5)
    assert wall["failure_probability"] == pytest.approx(expected, rel=1e-6)

    # C01-RW02: medium, poor, PGV-native 0.56 m/s: no conversion recorded.
    wall = states.loc["C01-RW02"]
    assert np.isnan(wall["theta_base_pga_g"])
    assert np.isnan(wall["pgv_pga_ratio_m_s_per_g"])
    assert wall["theta"] == pytest.approx(0.56)
    assert wall["beta"] == 0.5


@ignore_affine_matmul
def test_a_wall_outside_the_grids_draws_no_damage(synthetic_run):
    step.main(
        pilot=True,
        world_ids=[0],
        realisation_ids=[0],
        return_period_yr=RETURN_PERIOD_YR,
    )
    states = read_states(0, 0).set_index("rw_id")

    wall = states.loc["C04-RW01"]
    assert np.isnan(wall["pgv_m_s"])
    assert pd.isna(wall["site_class"])
    assert np.isnan(wall["failure_probability"])
    assert wall["damage_state"] == NO_DAMAGE


@ignore_affine_matmul
def test_the_draw_is_on_the_vulnerability_stream_keyed_on_both_ids(synthetic_run):
    step.main(
        pilot=True,
        world_ids=[0],
        realisation_ids=[0, 1],
        return_period_yr=RETURN_PERIOD_YR,
    )
    for realisation_id in (0, 1):
        states = read_states(0, realisation_id)
        rng = realisation_seed(
            constants.BASE_SEED, realisation_id, step.RNG_STREAM, world_id=0
        )
        expected = draw_damage_states(states["failure_probability"].to_numpy(), rng)
        assert list(states["damage_state"]) == list(expected)


@ignore_affine_matmul
def test_a_run_reproduces_exactly(synthetic_run):
    kwargs = {
        "pilot": True,
        "world_ids": [0],
        "realisation_ids": [0],
        "return_period_yr": RETURN_PERIOD_YR,
    }
    step.main(**kwargs)
    first = read_states(0, 0)
    step.main(**kwargs)
    second = read_states(0, 0)
    pd.testing.assert_frame_equal(first, second)


@ignore_affine_matmul
def test_a_world_with_no_flat_land_walls_writes_an_empty_file(
    synthetic_run, monkeypatch
):
    sloping = synthetic_run.assign(is_flatland=False)
    sloping.to_parquet(gen_wall_population.wall_population_path(0, pilot=True))

    step.main(
        pilot=True,
        world_ids=[0],
        realisation_ids=[0],
        return_period_yr=RETURN_PERIOD_YR,
    )
    states = read_states(0, 0)
    assert states.empty
    assert "damage_state" in states.columns
