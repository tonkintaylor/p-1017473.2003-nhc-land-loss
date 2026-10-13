"""Tests for the ground a face polygon's element is scored on."""

import numpy as np
import pandas as pd
import pytest

from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import face_polygons


def ground_map(**columns):
    base = {
        "material": ["colluvium", "rock"],
        "modification": ["natural", "natural"],
        "geology_value": [susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM, np.nan],
        "prior_failure": ["none", "none"],
        "gw_depth_class": ["saturated", "poorly_drained"],
    }
    return pd.DataFrame({**base, **columns})


def elements(rows):
    return pd.DataFrame({"majority_ground_row": rows}, index=range(10, 10 + len(rows)))


def test_the_off_map_ground_is_well_drained():
    assert face_polygons.BETA_OFF_MAP_GROUND["gw_depth_class"] == "well_drained"
    assert "gw_depth_m" not in face_polygons.BETA_OFF_MAP_GROUND
    assert "gw_depth_m" not in face_polygons.GROUND_COLUMNS


def test_an_element_reads_the_class_of_its_ground_map_piece():
    ground = face_polygons.ground_of_elements(elements([0, 1]), ground_map())

    assert ground["gw_depth_class"].tolist() == ["saturated", "poorly_drained"]


def test_an_element_off_the_map_takes_the_well_drained_default():
    ground = face_polygons.ground_of_elements(elements([-1, 0]), ground_map())

    assert ground["gw_depth_class"].tolist() == ["well_drained", "saturated"]
    assert ground["geology_value"].dtype == float


def test_a_piece_of_unknown_material_keeps_its_own_groundwater_class():
    # The second piece has no geology, so it takes the off-map geology, but
    # the groundwater class it carries is its own and not the default.
    ground = face_polygons.ground_of_elements(elements([1]), ground_map())

    assert (
        ground["geology_value"].iloc[0]
        == face_polygons.BETA_OFF_MAP_GROUND["geology_value"]
    )
    assert ground["gw_depth_class"].iloc[0] == "poorly_drained"


def test_a_missing_class_on_a_ground_map_piece_is_refused():
    with pytest.raises(ValueError, match="gw_depth_class"):
        face_polygons.ground_of_elements(
            elements([0, 1]), ground_map(gw_depth_class=["saturated", None])
        )


def test_a_class_outside_the_vocabulary_is_refused():
    with pytest.raises(ValueError, match="boggy"):
        face_polygons.ground_of_elements(
            elements([0, 1]), ground_map(gw_depth_class=["saturated", "boggy"])
        )


def test_an_empty_ground_map_gives_every_element_the_default():
    empty = ground_map().iloc[0:0]

    ground = face_polygons.ground_of_elements(elements([0, 1]), empty)

    assert ground["gw_depth_class"].tolist() == ["well_drained", "well_drained"]


def test_ground_of_elements_refuses_a_ground_map_with_only_the_old_depth_column():
    old = ground_map().drop(columns="gw_depth_class").assign(gw_depth_m=[0.5, 2.0])

    with pytest.raises(ValueError, match="Rebuild the ground map"):
        face_polygons.ground_of_elements(elements([0, 1]), old)


def test_a_ground_map_with_the_old_depth_column_is_refused():
    old = ground_map().drop(columns="gw_depth_class").assign(gw_depth_m=[0.5, 2.0])

    with pytest.raises(ValueError, match="gw_depth_class"):
        face_polygons.face_polygons(
            pd.DataFrame(columns=face_polygons.ZONE_COLUMNS),
            pd.DataFrame(columns=face_polygons.ELEMENT_COLUMNS),
            pd.DataFrame(columns=face_polygons.UNIT_COLUMNS),
            old,
        )
