"""Tests for re-expressing an extent between projections.

Nothing here touches the network or the T: drive: pyproj carries the grids it
needs for a New Zealand transform with it.
"""

import pytest
from pyproj import Transformer
from pyproj.exceptions import CRSError

from landloss.common.utils.raster import bbox_in_crs

NZTM = "EPSG:2193"
WGS84 = "EPSG:4326"

# A Wellington box, in the study's own projection.
WELLINGTON_NZTM = (1_748_000.0, 5_425_000.0, 1_752_000.0, 5_429_000.0)

# The full country, where the edges bow far enough for the densification to
# matter. Stewart Island to North Cape, in NZTM.
NEW_ZEALAND_NZTM = (1_090_000.0, 4_750_000.0, 2_090_000.0, 6_200_000.0)


def test_a_box_comes_back_in_the_requested_projection():
    west, south, east, north = bbox_in_crs(WELLINGTON_NZTM, NZTM, WGS84)

    assert 174.0 < west < east < 176.0
    assert -42.0 < south < north < -41.0


def test_a_round_trip_still_covers_the_box_it_started_from():
    # Never smaller is the guarantee. A round trip therefore comes back a little
    # larger -- each leg takes the envelope of a bowed edge -- and never inside
    # the box it started from, which is what a clip depends on.
    in_wgs84 = bbox_in_crs(WELLINGTON_NZTM, NZTM, WGS84)
    west, south, east, north = bbox_in_crs(in_wgs84, WGS84, NZTM)

    assert west <= WELLINGTON_NZTM[0]
    assert south <= WELLINGTON_NZTM[1]
    assert east >= WELLINGTON_NZTM[2]
    assert north >= WELLINGTON_NZTM[3]
    assert west == pytest.approx(WELLINGTON_NZTM[0], abs=200.0)
    assert north == pytest.approx(WELLINGTON_NZTM[3], abs=200.0)


def test_the_same_projection_leaves_the_box_alone():
    assert bbox_in_crs(WELLINGTON_NZTM, NZTM, NZTM) == pytest.approx(WELLINGTON_NZTM)


def test_densifying_the_edges_never_loses_ground():
    # The failure this exists to prevent: transforming the four corners alone
    # returns a box inside the true extent, so the clip made with it drops a
    # strip along whichever edges bowed outwards.
    transformer = Transformer.from_crs(NZTM, WGS84, always_xy=True)
    barely_densified = transformer.transform_bounds(*NEW_ZEALAND_NZTM, densify_pts=2)
    densified = bbox_in_crs(NEW_ZEALAND_NZTM, NZTM, WGS84)

    assert densified[0] <= barely_densified[0]
    assert densified[1] <= barely_densified[1]
    assert densified[2] >= barely_densified[2]
    assert densified[3] >= barely_densified[3]
    assert densified != pytest.approx(barely_densified)


def test_an_unknown_projection_is_refused():
    # Rather than silently handing back the box it was given, which would clip
    # a raster against an extent expressed in the wrong units.
    with pytest.raises(CRSError):
        bbox_in_crs(WELLINGTON_NZTM, NZTM, "EPSG:999999")
