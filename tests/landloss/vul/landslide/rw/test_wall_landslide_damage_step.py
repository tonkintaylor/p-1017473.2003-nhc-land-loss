"""The wall landslide damage step end to end on synthetic inputs, with no disk.

The step reads one world's wall population, the combined landslide realisation
of a world and earthquake and the urban wall outcome table of the same pair.
Here each is a small hand-built frame written where the step looks for it (each
producing step's work directory pointed at ``tmp_path``), so the test is of what
the step writes -- the file, its columns and the three flags per wall -- and
not of the data it normally reads.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from landloss.domain import constants
from landloss.hazard.landslide.land_class import EVACUATED, IMMINENT, INUNDATED
from landloss.hazard.landslide.urban.realisation import (
    ABSORBED,
    COMBINED_COLUMNS,
    FAILED_WITH_POLYGON,
    OUTCOME_COLUMNS,
    STANDING,
    SUPERSEDED,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import gen_wall_population
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import (
    gen_wall_landslide_damage as step,
)

CRS = constants.DEFAULT_CRS

# A large-model landslide and the urban failures, laid out so that each wall
# below meets exactly the ground its row says.
LARGE_EVACUATED = Point(0, 0).buffer(10)
LARGE_INUNDATED = Point(100, 0).buffer(10)
URBAN_FACE = Point(200, 0).buffer(5)
URBAN_RUNOUT = Point(200, -15).buffer(5)
URBAN_IMMINENT = Point(200, 15).buffer(5)

# rw_id, flat land, geometry, outcome row (slope_id, outcome) or None.
WALLS = [
    # Flat land, clear of everything: no outcome row, every flag False.
    ("C01-RW01", True, LineString([(40, 50), (60, 50)]), None),
    # Flat land, crossing the large landslide's inundated ground.
    ("C01-RW02", True, LineString([(90, 0), (110, 0)]), None),
    # Sloping, failed with its polygon, clear of every polygon.
    (
        "C02-RW01",
        False,
        LineString([(300, 50), (320, 50)]),
        ("SP0000001", FAILED_WITH_POLYGON),
    ),
    # Sloping, absorbed by a larger urban failure, clear of every polygon.
    ("C02-RW02", False, LineString([(300, 80), (320, 80)]), ("SP0000002", ABSORBED)),
    # Sloping, its polygon not delineated (null slope_id), standing, but its
    # line crosses the urban failure's evacuated ground.
    ("C03-RW01", False, LineString([(190, 0), (210, 0)]), (None, STANDING)),
    # Sloping, superseded by the large landslide, and crossing its evacuated
    # ground as well: evacuated by both routes, counted once.
    ("C03-RW02", False, LineString([(-10, 0), (10, 0)]), ("SP0000004", SUPERSEDED)),
    # Sloping, standing, under the urban failure's imminent ground only.
    ("C04-RW01", False, LineString([(190, 15), (210, 15)]), ("SP0000005", STANDING)),
]


def wall_population(world_id=0):
    rows = [
        {
            "rw_id": rw_id,
            "claim_id": rw_id.split("-")[0],
            "wall_line_id": f"WL{i + 1:07d}",
            "world_id": world_id,
            "size_class": "small",
            "initial_condition": "modern",
            "height_m": 1.0,
            "length_m": 20.0,
            "wall_position": "fill",
            "is_flatland": is_flatland,
            "source": "property_boundary",
            "material": "colluvium",
            "geometry": geometry,
        }
        for i, (rw_id, is_flatland, geometry, _) in enumerate(WALLS)
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)


def combined_realisation(world_id=0, realisation_id=0):
    """Two large rows and the three state rows of one urban failure."""
    rows = [
        ("LS0000001", "large", None, "SU0000001", EVACUATED, 1.5, LARGE_EVACUATED),
        ("LS0000001", "large", None, "SU0000001", INUNDATED, 1.5, LARGE_INUNDATED),
        ("SP0000003", "urban", "SP0000003", None, EVACUATED, 1.0, URBAN_FACE),
        ("SP0000003", "urban", "SP0000003", None, INUNDATED, 0.5, URBAN_RUNOUT),
        ("SP0000003", "urban", "SP0000003", None, IMMINENT, np.nan, URBAN_IMMINENT),
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


def wall_outcomes(world_id=0, realisation_id=0):
    """One row per sloping wall, as landslide step 9 writes it."""
    rows = [
        (rw_id, f"WL{i + 1:07d}", rw_id.split("-")[0], slope_id, outcome)
        for i, (rw_id, is_flatland, _, row) in enumerate(WALLS)
        if not is_flatland
        for slope_id, outcome in [row]
    ]
    table = pd.DataFrame(
        {
            "rw_id": [row[0] for row in rows],
            "wall_line_id": [row[1] for row in rows],
            "claim_id": [row[2] for row in rows],
            "slope_id": [row[3] for row in rows],
            "outcome": [row[4] for row in rows],
            "taken_by": ["SP0000009" if row[4] == ABSORBED else None for row in rows],
        }
    )
    table["taken_by"] = table["taken_by"].where(table["outcome"] == ABSORBED, None)
    table.loc[table["outcome"] == SUPERSEDED, "taken_by"] = "LS0000001"
    assert list(table.columns) == list(OUTCOME_COLUMNS)
    table.insert(0, "world_id", world_id)
    table.insert(1, "realisation_id", realisation_id)
    return table


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    """Every input the step reads, written where it looks for it."""
    monkeypatch.setattr(gen_wall_population, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(gen_urban_slope_realisation, "WORK_DIR", tmp_path / "hazard")
    monkeypatch.setattr(step, "WORK_DIR", tmp_path / "vul")

    walls_path = gen_wall_population.wall_population_path(0, extent="wlg-pilot")
    walls_path.parent.mkdir(parents=True)
    wall_population().to_parquet(walls_path)

    for realisation_id in (0, 1):
        slides = combined_realisation(0, realisation_id)
        if realisation_id == 1:
            # The second earthquake fails nothing in the urban model and the
            # large landslide sits elsewhere, so every wall is clear.
            slides = slides.iloc[:2].copy()
            slides["geometry"] = [Point(900, 900).buffer(5), Point(950, 900).buffer(5)]
        path = gen_urban_slope_realisation.combined_realisation_path(
            0, realisation_id, extent="wlg-pilot"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        slides.to_parquet(path)

        outcomes = wall_outcomes(0, realisation_id)
        if realisation_id == 1:
            outcomes["outcome"] = STANDING
            outcomes["taken_by"] = None
        outcomes.to_parquet(
            gen_urban_slope_realisation.urban_wall_outcome_path(
                0, realisation_id, extent="wlg-pilot"
            )
        )
    return wall_population()


def read_flags(world_id, realisation_id):
    return pd.read_parquet(
        step.wall_landslide_damage_path(world_id, realisation_id, extent="wlg-pilot")
    )


# --- path function --------------------------------------------------------------


def test_the_path_names_the_world_the_realisation_and_the_extent():
    assert (
        step.wall_landslide_damage_path(0, 3, extent="wlg-pilot").name
        == "wall-landslide-damage-w000-r003-pilot.parquet"
    )
    assert (
        step.wall_landslide_damage_path(12, 1, extent="full").name
        == "wall-landslide-damage-w012-r001.parquet"
    )
    assert (
        step.wall_landslide_damage_path(0, 0, extent="wlg-pilot").parent
        == step.WORK_DIR
    )


# --- end to end ------------------------------------------------------------------


def test_the_output_carries_the_contract_columns_for_every_wall(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    flags = read_flags(0, 0)

    assert list(flags.columns) == [
        "realisation_id",
        "world_id",
        "rw_id",
        "claim_id",
        "slope_id",
        "outcome",
        "is_damaged_by_shaking",
        "is_evacuated",
        "is_inundated",
    ]
    # One row per wall in the population, flat land and sloping alike, in
    # population order.
    assert flags["rw_id"].tolist() == [rw_id for rw_id, _, _, _ in WALLS]
    assert flags["claim_id"].tolist() == [rw_id.split("-")[0] for rw_id, *_ in WALLS]
    assert (flags["realisation_id"] == 0).all()
    assert (flags["world_id"] == 0).all()
    for column in ("is_damaged_by_shaking", "is_evacuated", "is_inundated"):
        assert flags[column].dtype == bool


def test_each_wall_takes_the_flags_of_section_5_2(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    flags = read_flags(0, 0).set_index("rw_id")

    expected = {
        # Per wall, the shaking, evacuated and inundated flags in that order.
        "C01-RW01": (False, False, False),
        "C01-RW02": (False, False, True),
        "C02-RW01": (True, False, False),
        "C02-RW02": (False, True, False),
        "C03-RW01": (False, True, False),
        "C03-RW02": (False, True, False),
        "C04-RW01": (False, False, False),
    }
    for rw_id, (shaking, evacuated, inundated) in expected.items():
        row = flags.loc[rw_id]
        assert bool(row["is_damaged_by_shaking"]) is shaking, rw_id
        assert bool(row["is_evacuated"]) is evacuated, rw_id
        assert bool(row["is_inundated"]) is inundated, rw_id


def test_slope_id_and_outcome_are_carried_and_null_for_flat_land_walls(
    synthetic_run,
):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    flags = read_flags(0, 0).set_index("rw_id")

    for rw_id, is_flatland, _, row in WALLS:
        if is_flatland:
            assert pd.isna(flags.loc[rw_id, "slope_id"])
            assert pd.isna(flags.loc[rw_id, "outcome"])
            continue
        slope_id, outcome = row
        assert flags.loc[rw_id, "outcome"] == outcome
        if slope_id is None:
            assert pd.isna(flags.loc[rw_id, "slope_id"])
        else:
            assert flags.loc[rw_id, "slope_id"] == slope_id


def test_each_realisation_is_flagged_against_its_own_landslides(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0, 1])

    quiet = read_flags(0, 1)
    assert (quiet["realisation_id"] == 1).all()
    assert len(quiet) == len(WALLS)
    for column in ("is_damaged_by_shaking", "is_evacuated", "is_inundated"):
        assert not quiet[column].any()
    assert (quiet.loc[quiet["outcome"].notna(), "outcome"] == STANDING).all()

    busy = read_flags(0, 0)
    assert busy["is_evacuated"].sum() == 3


def test_a_run_reproduces_exactly(synthetic_run):
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    first = read_flags(0, 0)
    step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
    second = read_flags(0, 0)
    pd.testing.assert_frame_equal(first, second)


def test_an_outcome_naming_a_wall_outside_the_population_stops_the_run(
    synthetic_run,
):
    outcomes = wall_outcomes(0, 0)
    outcomes.loc[0, "rw_id"] = "Z-RW99"
    outcomes.to_parquet(
        gen_urban_slope_realisation.urban_wall_outcome_path(0, 0, extent="wlg-pilot")
    )
    with pytest.raises(ValueError, match="not in the population"):
        step.main(extent="wlg-pilot", world_ids=[0], realisation_ids=[0])
