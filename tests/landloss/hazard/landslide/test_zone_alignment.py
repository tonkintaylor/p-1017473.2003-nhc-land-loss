"""Tests for aligning a walled element's zones with its wall unit's line."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely import LineString, box

from landloss.hazard.landslide.zone_alignment import (
    HOW_NO_FALL,
    TRIM_COLUMNS,
    align_zones,
    unit_falls,
    unit_walled,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones import config
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.zone_tiles import (
    align_walled_zones,
    wall_trim_settings,
)

CRS = "EPSG:2193"
SETTINGS = wall_trim_settings(config)
# Direction index 2 is one row down the grid: south.
SOUTH = np.array([0.0, -1.0])


def make_units():
    """One unit with a 10 m line along y = 0 on pif 7, one with no pif."""
    return gpd.GeoDataFrame(
        {"member_pif_ids": [np.array([7]), np.array([], dtype=np.int64)]},
        geometry=[LineString([(0, 0), (10, 0)]), LineString([(50, 0), (60, 0)])],
        index=pd.Index(["WU1", "WU2"], name="wall_unit_id"),
        crs=CRS,
    )


def make_elements():
    """Element 1 from the unit's pif, 2 from a pif in no unit, 3 a line element."""
    return pd.DataFrame(
        {"siz_id": [7, 9, 0], "wall_unit_id": [None, None, "WU2"]},
        index=pd.Index([1, 2, 3], name="label"),
    )


def make_zones(rows):
    """Zones of (polygon, zone, element, geometry) rows, with a volume of 40 m3."""
    polygon, zone, element, geometry = zip(*rows, strict=True)
    return gpd.GeoDataFrame(
        {
            "polygon": polygon,
            "zone": zone,
            "element": element,
            "forced": False,
            "volume_m3": 40.0,
        },
        geometry=list(geometry),
        crs=CRS,
    )


def area_of(zones, polygon, zone):
    rows = zones[(zones["polygon"] == polygon) & (zones["zone"] == zone)]
    return float(rows.geometry.area.sum())


def aligned(zones, *, flags=True):
    return align_zones(
        zones,
        elements=make_elements(),
        units=make_units(),
        flags=flags,
        falls={"WU1": SOUTH},
        settings=SETTINGS,
    )


def test_unit_falls_takes_the_mean_fall_of_the_first_pif():
    directions = pd.Series([np.array([2, 2, 2])], index=[7])
    falls = unit_falls(make_units(), directions)
    assert list(falls) == ["WU1"]
    np.testing.assert_allclose(falls["WU1"], SOUTH)


def test_unit_walled_reads_bounds_and_a_worlds_draw():
    units = make_units()
    assert unit_walled(units, flags=True).all()
    assert not unit_walled(units, flags=False).any()
    draw = unit_walled(units, flags=pd.Series({"WU2": True}))
    assert draw.to_dict() == {"WU1": False, "WU2": True}


def test_trim_takes_the_front_off_and_leaves_the_other_zones_as_built():
    band = box(0, 3, 10, 5).union(box(10, -2, 12, 3))
    zones = make_zones(
        [
            (1, "evacuated", 1, box(0, -2, 10, 3)),
            (1, "imminent", 1, band),
            (1, "inundated", 1, box(0, -8, 10, -2)),
        ]
    )
    out = aligned(zones)
    assert area_of(out, 1, "evacuated") == pytest.approx(30.0)
    assert area_of(out, 1, "imminent") == pytest.approx(band.area)
    assert area_of(out, 1, "inundated") == pytest.approx(60.0)
    assert len(out) == 3
    row = out[out["zone"] == "evacuated"].iloc[0]
    assert row["wall_trim_how"] == "line cuts"
    assert row["wall_trim_removed_m2"] == pytest.approx(20.0)


def test_fill_to_the_line_leaves_the_other_zones_as_built():
    notched = box(0, 0, 10, 4).difference(box(3, 0, 7, 1.5))
    zones = make_zones(
        [
            (1, "evacuated", 1, notched),
            (1, "imminent", 1, box(-1, 0, 0, 4)),
            (1, "inundated", 1, box(2, -3, 8, 1)),
        ]
    )
    out = aligned(zones)
    # The fill is held short of the notch's corners (oblique rays).
    assert area_of(out, 1, "evacuated") == pytest.approx(40.0, abs=1.5)
    assert area_of(out, 1, "inundated") == pytest.approx(24.0)
    assert area_of(out, 1, "imminent") == pytest.approx(4.0)
    assert out[out["zone"] == "evacuated"].iloc[0]["wall_trim_filled_m2"] > 4.5


def test_only_walled_built_elements_of_a_unit_are_aligned():
    cut = box(0, -2, 10, 3)
    zones = make_zones(
        [
            (1, "evacuated", 1, cut),
            (2, "evacuated", 2, cut),
            (3, "evacuated", 3, cut),
            (4, "evacuated", 1, cut),
        ]
    )
    zones.loc[3, "forced"] = True
    out = aligned(zones)
    assert area_of(out, 1, "evacuated") == pytest.approx(30.0)
    # A pif in no unit, a line element and a forced polygon stay as built.
    for polygon in (2, 3, 4):
        assert area_of(out, polygon, "evacuated") == pytest.approx(50.0)
    assert set(TRIM_COLUMNS) <= set(out.columns)
    assert (out["wall_trim_how"] == "").sum() == 3


@pytest.mark.parametrize("flags", [False, pd.Series({"WU1": False})])
def test_a_bare_unit_is_left_as_built(flags):
    zones = make_zones([(1, "evacuated", 1, box(0, -2, 10, 3))])
    out = aligned(zones, flags=flags)
    assert area_of(out, 1, "evacuated") == pytest.approx(50.0)
    assert (out["wall_trim_how"] == "").all()


def test_a_unit_with_no_fall_is_left_as_built():
    zones = make_zones([(1, "evacuated", 1, box(0, -2, 10, 3))])
    out = align_zones(
        zones,
        elements=make_elements(),
        units=make_units(),
        flags=True,
        falls={},
        settings=SETTINGS,
    )
    assert area_of(out, 1, "evacuated") == pytest.approx(50.0)
    assert out["wall_trim_how"].iloc[0] == HOW_NO_FALL


def test_the_step_redraws_areas_and_depth_from_the_aligned_geometry():
    zones = make_zones([(1, "evacuated", 1, box(0, -2, 10, 3))])
    zones["area_m2"] = 50.0
    zones["depth_m"] = 0.8
    out = align_walled_zones(
        zones,
        elements=make_elements(),
        units=make_units(),
        flags=True,
        falls={"WU1": SOUTH},
        settings=SETTINGS,
    )
    assert out["area_m2"].iloc[0] == pytest.approx(30.0)
    assert out["depth_m"].iloc[0] == pytest.approx(40.0 / 30.0)


def test_the_step_passes_empty_zones_through():
    zones = make_zones([(1, "evacuated", 1, box(0, -2, 10, 3))]).iloc[:0]
    out = align_walled_zones(
        zones,
        elements=make_elements(),
        units=make_units(),
        flags=True,
        falls={"WU1": SOUTH},
        settings=SETTINGS,
    )
    assert out.empty


def test_the_imminent_zone_never_overlaps_its_own_aligned_evacuated_polygon():
    notched = box(0, 0, 10, 4).difference(box(3, 0, 7, 1.5))
    # The imminent band reaches into the notch the fill closes.
    band = box(3, 0.5, 7, 1.5).union(box(0, 4, 10, 6))
    zones = make_zones(
        [
            (1, "evacuated", 1, notched),
            (1, "imminent", 1, band),
            (2, "evacuated", 2, box(20, 0, 24, 4)),
            (2, "imminent", 2, box(21, 1, 23, 3)),
        ]
    )
    out = aligned(zones)
    evacuated = out[(out["polygon"] == 1) & (out["zone"] == "evacuated")].geometry.iloc[
        0
    ]
    imminent = out[(out["polygon"] == 1) & (out["zone"] == "imminent")].geometry.iloc[0]
    assert evacuated.intersection(imminent).area == pytest.approx(0.0, abs=1e-9)
    assert imminent.area == pytest.approx(band.difference(evacuated).area)
    assert imminent.area < band.area
    # Polygon 2 is not walled (its pif is in no unit): left as built, overlap and all.
    assert area_of(out, 2, "imminent") == pytest.approx(4.0)


def test_an_imminent_zone_the_evacuated_polygon_now_covers_is_dropped():
    notched = box(0, 0, 10, 4).difference(box(3, 0, 7, 1.5))
    zones = make_zones(
        [
            (1, "evacuated", 1, notched),
            (1, "imminent", 1, box(4, 0.5, 6, 1.5)),
        ]
    )
    out = aligned(zones)
    assert list(out["zone"]) == ["evacuated"]
