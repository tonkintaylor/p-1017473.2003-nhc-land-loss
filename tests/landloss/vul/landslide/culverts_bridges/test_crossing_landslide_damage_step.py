"""The crossing landslide damage step end to end on synthetic inputs, with no disk.

The step reads the crossing population of an earthquake and the combined
landslide realisation of a world and that earthquake. Here both are small
hand-built frames written where the step looks for them (each producing step's
work directory pointed at ``tmp_path``), so the test is of what the step
writes -- the file, its columns and the two flags per crossing -- and not of
the data it normally reads.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from landloss.domain import constants
from landloss.hazard.landslide.land_class import EVACUATED, IMMINENT, INUNDATED
from landloss.hazard.landslide.urban.realisation import COMBINED_COLUMNS
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population import (
    gen_crossing_population,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.vul.landslide.culverts_bridges.steps.s11_crossing_landslide_damage import (  # noqa: E501
    gen_crossing_landslide_damage as step,
)

CRS = constants.DEFAULT_CRS

# crossing_id, claim_id, asset, geometry: one under each kind of ground, one
# under imminent ground only, one clear of everything.
CROSSINGS = [
    ("C01-X01", "C01", "culvert", Point(0, 0)),
    ("C01-X02", "C01", "bridge", Point(100, 0)),
    ("C02-X01", "C02", "culvert", Point(200, 15)),
    ("C03-X01", "C03", "bridge", Point(500, 500)),
]


def crossing_population():
    return gpd.GeoDataFrame(
        {
            "crossing_id": [row[0] for row in CROSSINGS],
            "claim_id": [row[1] for row in CROSSINGS],
            "asset": [row[2] for row in CROSSINGS],
        },
        geometry=[row[3] for row in CROSSINGS],
        crs=CRS,
    )


def combined_realisation(world_id=0, realisation_id=0):
    rows = [
        (
            "LS0000001",
            "large",
            None,
            "SU0000001",
            EVACUATED,
            1.5,
            Point(0, 0).buffer(10),
        ),
        (
            "LS0000001",
            "large",
            None,
            "SU0000001",
            INUNDATED,
            1.5,
            Point(100, 0).buffer(10),
        ),
        (
            "SP0000001",
            "urban",
            "SP0000001",
            None,
            EVACUATED,
            1.0,
            Point(200, 0).buffer(5),
        ),
        (
            "SP0000001",
            "urban",
            "SP0000001",
            None,
            INUNDATED,
            0.5,
            Point(200, -15).buffer(5),
        ),
        (
            "SP0000001",
            "urban",
            "SP0000001",
            None,
            IMMINENT,
            np.nan,
            Point(200, 15).buffer(5),
        ),
    ]
    frame = gpd.GeoDataFrame(
        {
            "realisation_id": realisation_id,
            "world_id": world_id,
            "landslide_id": [row[0] for row in rows],
            "population": [row[1] for row in rows],
            "slope_id": [row[2] for row in rows],
            "unit_id": [row[3] for row in rows],
            "land_class": [row[4] for row in rows],
            "depth_m": [row[5] for row in rows],
            "volume_m3": [row[5] * row[6].area for row in rows],
            "source_area_m2": [row[6].area for row in rows],
            "wall_state": [None, None, "no_wall", "no_wall", "no_wall"],
            "rw_id": None,
            "pgv_m_s": [np.nan, np.nan, 0.4, 0.4, 0.4],
            "p_fail": [np.nan, np.nan, 0.3, 0.3, 0.3],
            "uniform": [np.nan, np.nan, 0.1, 0.1, 0.1],
        },
        geometry=[row[6] for row in rows],
        crs=CRS,
    )
    assert list(frame.columns) == list(COMBINED_COLUMNS)
    return frame


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    """Every input the step reads, written where it looks for it."""
    monkeypatch.setattr(gen_crossing_population, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(gen_urban_slope_realisation, "WORK_DIR", tmp_path / "hazard")
    monkeypatch.setattr(step, "WORK_DIR", tmp_path / "vul")

    crossings_path = gen_crossing_population.crossing_population_path(
        0, extent="wlg-pilot"
    )
    crossings_path.parent.mkdir(parents=True)
    crossing_population().to_parquet(crossings_path)

    for world_id in (0, 1):
        slides = combined_realisation(world_id, 0)
        if world_id == 1:
            # The second world's urban model failed nothing: large rows only.
            slides = slides.iloc[:2]
        path = gen_urban_slope_realisation.combined_realisation_path(
            world_id, 0, extent="wlg-pilot"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        slides.to_parquet(path)
    return crossing_population()


def read_flags(world_id, realisation_id):
    return pd.read_parquet(
        step.crossing_landslide_damage_path(
            world_id, realisation_id, extent="wlg-pilot"
        )
    )


# --- path function --------------------------------------------------------------


def test_the_path_names_the_world_the_realisation_and_the_extent():
    assert (
        step.crossing_landslide_damage_path(0, 3, extent="wlg-pilot").name
        == "crossing-landslide-damage-w000-r003-pilot.parquet"
    )
    assert (
        step.crossing_landslide_damage_path(12, 1, extent="full").name
        == "crossing-landslide-damage-w012-r001.parquet"
    )
    assert (
        step.crossing_landslide_damage_path(0, 0, extent="wlg-pilot").parent
        == step.WORK_DIR
    )


# --- end to end ------------------------------------------------------------------


def test_the_output_carries_the_columns_and_flags_every_crossing(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    flags = read_flags(0, 0)

    assert list(flags.columns) == [
        "realisation_id",
        "world_id",
        "crossing_id",
        "claim_id",
        "is_evacuated",
        "is_inundated",
    ]
    assert flags["crossing_id"].tolist() == [row[0] for row in CROSSINGS]
    assert flags["claim_id"].tolist() == [row[1] for row in CROSSINGS]
    assert (flags["realisation_id"] == 0).all()
    assert (flags["world_id"] == 0).all()
    assert flags["is_evacuated"].tolist() == [True, False, False, False]
    assert flags["is_inundated"].tolist() == [False, True, False, False]
    assert flags["is_evacuated"].dtype == bool
    assert flags["is_inundated"].dtype == bool


def test_each_world_is_flagged_against_its_own_realisation(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0, 1], realisation_ids=[0])
    quiet = read_flags(1, 0)
    assert (quiet["world_id"] == 1).all()
    assert quiet["is_evacuated"].tolist() == [True, False, False, False]
    assert quiet["is_inundated"].tolist() == [False, True, False, False]


def test_a_crossing_population_without_ids_stops_the_run(synthetic_run):
    stale = synthetic_run.drop(columns="crossing_id")
    stale.to_parquet(
        gen_crossing_population.crossing_population_path(0, extent="wlg-pilot")
    )
    with pytest.raises(ValueError, match="crossing_id"):
        step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])


def test_no_crossings_writes_an_empty_file_with_the_full_columns(synthetic_run):
    empty = synthetic_run.iloc[:0]
    empty.to_parquet(
        gen_crossing_population.crossing_population_path(0, extent="wlg-pilot")
    )
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    flags = read_flags(0, 0)
    assert flags.empty
    assert list(flags.columns) == [
        "realisation_id",
        "world_id",
        "crossing_id",
        "claim_id",
        "is_evacuated",
        "is_inundated",
    ]
