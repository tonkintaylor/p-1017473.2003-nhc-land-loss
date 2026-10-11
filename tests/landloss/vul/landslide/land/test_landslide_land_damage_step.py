"""The landslide land damage step end to end on synthetic inputs, with no disk.

The step reads the insured land extent and the combined landslide realisation
of a world and earthquake. Here both are small hand-built frames written where
the step looks for them (each producing step's work directory pointed at
``tmp_path``), so the test is of what the step writes -- the file, its columns
and the areas per land polygon -- and not of the data it normally reads.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from landloss.domain import constants
from landloss.hazard.landslide.land_class import EVACUATED, IMMINENT, INUNDATED
from landloss.hazard.landslide.urban.realisation import COMBINED_COLUMNS
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    gen_insured_land,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import (
    gen_landslide_land_damage as step,
)

CRS = constants.DEFAULT_CRS

# Three 20 by 20 m land polygons in a row, 100 m apart.
LAND = [
    ("C01-L01", "C01", box(0, 0, 20, 20)),
    ("C02-L01", "C02", box(100, 0, 120, 20)),
    ("C03-L01", "C03", box(200, 0, 220, 20)),
]


def insured_land():
    return gpd.GeoDataFrame(
        {
            "land_id": [land_id for land_id, _, _ in LAND],
            "claim_id": [claim_id for _, claim_id, _ in LAND],
            "area_m2": [geometry.area for _, _, geometry in LAND],
            "dwelling_count": 1,
        },
        geometry=[geometry for _, _, geometry in LAND],
        crs=CRS,
    )


def footprints():
    """A 5 by 5 m building in the south west corner of each polygon."""
    return gpd.GeoDataFrame(
        {"claim_id": [claim_id for _, claim_id, _ in LAND]},
        geometry=[
            box(geometry.bounds[0], 0, geometry.bounds[0] + 5, 5)
            for _, _, geometry in LAND
        ],
        crs=CRS,
    )


def combined_realisation(world_id=0, realisation_id=0):
    """A large landslide over the first polygon and an urban failure over it
    and the second; the third sees imminent ground only.
    """
    rows = [
        # The large landslide evacuates the west half of the first polygon.
        ("LS0000001", "large", None, "SU0000001", EVACUATED, 2.0, box(-10, 0, 10, 20)),
        # Its runout buries the east half of the same polygon ...
        ("LS0000001", "large", None, "SU0000001", INUNDATED, 2.0, box(10, 0, 30, 20)),
        # ... and the urban failure's runout buries the same east half again,
        # which must count once, plus the south half of the second polygon.
        ("SP0000001", "urban", "SP0000001", None, INUNDATED, 0.5, box(10, 0, 30, 20)),
        ("SP0000002", "urban", "SP0000002", None, EVACUATED, 1.0, box(100, 0, 120, 10)),
        ("SP0000002", "urban", "SP0000002", None, INUNDATED, 0.5, box(100, 0, 120, 10)),
        # Imminent ground over the whole third polygon measures nothing.
        (
            "SP0000003",
            "urban",
            "SP0000003",
            None,
            IMMINENT,
            np.nan,
            box(200, 0, 220, 20),
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
            "wall_state": [None, None, "no_wall", "fill_wall", "fill_wall", "no_wall"],
            "rw_id": [None, None, None, "C02-RW01", "C02-RW01", None],
            "pgv_m_s": [np.nan, np.nan, 0.4, 0.4, 0.4, 0.4],
            "p_fail": [np.nan, np.nan, 0.3, 0.3, 0.3, 0.3],
            "uniform": [np.nan, np.nan, 0.1, 0.1, 0.1, 0.1],
        },
        geometry=[row[6] for row in rows],
        crs=CRS,
    )
    assert list(frame.columns) == list(COMBINED_COLUMNS)
    return frame


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    """Every input the step reads, written where it looks for it."""
    monkeypatch.setattr(gen_insured_land, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(gen_urban_slope_realisation, "WORK_DIR", tmp_path / "hazard")
    monkeypatch.setattr(step, "WORK_DIR", tmp_path / "vul")

    land_path = gen_insured_land.insured_land_path(extent="wlg-pilot")
    land_path.parent.mkdir(parents=True)
    insured_land().to_parquet(land_path)
    footprints().to_parquet(gen_insured_land.footprints_path(extent="wlg-pilot"))

    for world_id in (0, 1):
        slides = combined_realisation(world_id, 0)
        if world_id == 1:
            # The second world drew no wall at the second polygon, so its
            # urban failures lie elsewhere: only the large landslide reaches
            # any insured land.
            slides = slides.iloc[:2]
        path = gen_urban_slope_realisation.combined_realisation_path(
            world_id, 0, extent="wlg-pilot"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        slides.to_parquet(path)
    return insured_land()


def read_damage(world_id, realisation_id):
    return pd.read_parquet(
        step.landslide_land_damage_path(world_id, realisation_id, extent="wlg-pilot")
    )


# --- path function --------------------------------------------------------------


def test_the_path_names_the_world_the_realisation_and_the_extent():
    assert (
        step.landslide_land_damage_path(0, 3, extent="wlg-pilot").name
        == "landslide-land-damage-w000-r003-pilot.parquet"
    )
    assert (
        step.landslide_land_damage_path(12, 1, extent="full").name
        == "landslide-land-damage-w012-r001.parquet"
    )
    assert (
        step.landslide_land_damage_path(0, 0, extent="wlg-pilot").parent
        == step.WORK_DIR
    )


# --- end to end ------------------------------------------------------------------


def test_the_output_carries_the_columns_with_the_world_after_the_realisation(
    synthetic_run,
):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    damaged = read_damage(0, 0)

    assert list(damaged.columns) == [
        "realisation_id",
        "world_id",
        "land_id",
        "claim_id",
        "evacuated_area_m2",
        "inundated_area_m2",
        "landslide_area_m2",
        "evacuated_depth_m",
        "inundated_depth_m",
        "landslide_footprint_area_m2",
        "cause_evacuated",
        "cause_inundated",
    ]
    assert (damaged["realisation_id"] == 0).all()
    assert (damaged["world_id"] == 0).all()
    assert damaged["cause_evacuated"].iloc[0] == str(
        constants.Cause.LANDSLIDE_EVACUATED
    )
    assert damaged["cause_inundated"].iloc[0] == str(
        constants.Cause.LANDSLIDE_INUNDATED
    )


def test_both_populations_are_measured_and_imminent_ground_is_not(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    damaged = read_damage(0, 0).set_index("land_id")

    # The third polygon, under imminent ground only, is absent.
    assert damaged.index.tolist() == ["C01-L01", "C02-L01"]
    assert damaged["claim_id"].tolist() == ["C01", "C02"]

    first = damaged.loc["C01-L01"]
    assert first["evacuated_area_m2"] == pytest.approx(200.0)
    # The east half is buried by the large runout and the urban one: once.
    assert first["inundated_area_m2"] == pytest.approx(200.0)
    assert first["landslide_area_m2"] == pytest.approx(400.0)
    # The building in the corner is all under the evacuated ground.
    assert first["landslide_footprint_area_m2"] == pytest.approx(25.0)
    assert first["evacuated_depth_m"] == pytest.approx(2.0)
    # Two landslides of equal footprint on the same ground: the mean depth.
    assert first["inundated_depth_m"] == pytest.approx(1.25)

    second = damaged.loc["C02-L01"]
    assert second["evacuated_area_m2"] == pytest.approx(200.0)
    assert second["inundated_area_m2"] == pytest.approx(200.0)
    # Evacuated and inundated on the same ground: the union counts it once.
    assert second["landslide_area_m2"] == pytest.approx(200.0)


def test_each_world_is_measured_against_its_own_realisation(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0, 1], realisation_ids=[0])

    quiet = read_damage(1, 0)
    assert (quiet["world_id"] == 1).all()
    assert quiet["land_id"].tolist() == ["C01-L01"]
    assert quiet["inundated_depth_m"].iloc[0] == pytest.approx(2.0)


def test_a_run_reproduces_exactly(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    first = read_damage(0, 0)
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    second = read_damage(0, 0)
    pd.testing.assert_frame_equal(first, second)
