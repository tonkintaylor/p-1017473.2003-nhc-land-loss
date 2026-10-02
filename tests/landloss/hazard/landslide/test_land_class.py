"""Tests for the land class vocabulary the landslide polygons carry."""

from landloss.hazard.landslide import land_class
from landloss.vul.landslide.land import damaged_area


def test_the_three_classes():
    assert land_class.LAND_CLASSES == (
        "evacuated land",
        "inundated land",
        "imminent land",
    )
    assert land_class.LAND_CLASS_COLUMN == "land_class"


def test_the_classes_are_distinct():
    assert len(set(land_class.LAND_CLASSES)) == len(land_class.LAND_CLASSES)


def test_the_land_damage_step_reads_the_same_words():
    # vul re-points at this module in phase 4; until then the literals have to
    # agree, or a polygon written by hazard is not recognised by vul.
    assert damaged_area.EVACUATED == land_class.EVACUATED
    assert damaged_area.INUNDATED == land_class.INUNDATED
    assert damaged_area.LAND_CLASS_COLUMN == land_class.LAND_CLASS_COLUMN
    assert land_class.IMMINENT not in damaged_area.AREA_COLUMNS
