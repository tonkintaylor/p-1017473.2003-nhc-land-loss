"""A slip's new wall on the mapped wall: the join vul makes for loss (section 4)."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from landloss.domain import constants
from landloss.domain.loss_contract import LANDSLIDE_WALL_COLUMNS
from landloss.vul.mapped_walls import (
    alongside_length,
    attach_mapped_walls,
    held_failure_keys,
)
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    attach_failures_to_walls,
)

CRS = constants.DEFAULT_CRS


def stretches(rows):
    """Candidate stretches from ``(unit, claim, line)`` rows, lengths at the line's."""
    return gpd.GeoDataFrame(
        {
            "wall_line_id": [unit for unit, _, _ in rows],
            "claim_id": [claim for _, claim, _ in rows],
            "length_m": [line.length for _, _, line in rows],
        },
        geometry=[line for _, _, line in rows],
        crs=CRS,
    )


def walls_table(rows):
    """A wall table of ``(claim, parent, shaking, evacuated)`` rows."""
    return pd.DataFrame(
        {
            "rw_id": [f"{parent}-P{k}" for k, (_, parent, _, _) in enumerate(rows)],
            "claim_id": [claim for claim, *_ in rows],
            "parent_rw_id": [parent for _, parent, _, _ in rows],
            "is_damaged_by_shaking": [shaken for *_, shaken, _ in rows],
            "is_evacuated": [evacuated for *_, evacuated in rows],
        }
    )


def land_table(claims_and_failures):
    """A land table of ``(claim, [(failure, wall)])`` rows, one polygon each."""
    return pd.DataFrame(
        {
            "land_id": [
                f"{claim}-L{k}" for k, (claim, _) in enumerate(claims_and_failures)
            ],
            "claim_id": [claim for claim, _ in claims_and_failures],
            "landslide_ids": [
                [f for f, _ in failures] for _, failures in claims_and_failures
            ],
            "landslide_rw_ids": [
                [w for _, w in failures] for _, failures in claims_and_failures
            ],
        }
    )


def run(land, rw, *, ground, lines, heights=None, slopes=None):
    """``attach_mapped_walls`` with every failure on slope ``S<id>`` of unit ``U``."""
    failures = [f for ids in land["landslide_ids"] for f in ids]
    return attach_mapped_walls(
        land,
        rw,
        slope_ids=pd.Series(
            {f: f"S-{f}" for f in failures} if slopes is None else slopes
        ),
        wall_line_of_slope=pd.Series({f"S-{f}": "U" for f in failures}),
        height_of_wall_line=pd.Series({"U": 1.5} if heights is None else heights),
        candidate_stretches=stretches(lines),
        evacuated_ground=ground,
    )


UNIT = LineString([(0, 0), (20, 0)])


def test_a_failure_takes_the_stretch_within_two_metres_of_its_evacuated_ground():
    land = land_table([("C1", [("F1", None)])])
    # The ground spans x 5 to 9, so the stretch within 2 m runs 3 to 11.
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 3)},
        lines=[("U", "C1", UNIT)],
    )

    assert out["landslide_wall_sources"][0] == ["mapped wall"]
    assert out["landslide_wall_lengths"][0] == pytest.approx([8.0])
    assert out["landslide_wall_heights"][0] == pytest.approx([1.5])


@pytest.mark.parametrize("height", [np.nan, 0.0, -1.0])
def test_a_wall_with_no_usable_height_falls_back_to_the_slip(height):
    land = land_table([("C1", [("F1", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 3)},
        lines=[("U", "C1", UNIT)],
        heights={"U": height},
    )

    assert out["landslide_wall_sources"][0] == ["slip"]


def test_the_lists_are_added_in_the_order_of_the_landslide_ids():
    land = land_table([("C1", [("F1", None), ("F2", None), ("F3", None)])])
    out = run(
        land,
        walls_table([]),
        ground={
            ("C1", "F1"): box(5, 0, 9, 3),
            ("C1", "F3"): box(0, 8, 1, 9),
        },
        lines=[("U", "C1", UNIT)],
    )

    for column in LANDSLIDE_WALL_COLUMNS:
        assert len(out[column][0]) == 3
    # F2 has no evacuated ground on the claim, F3's is 8 m from the stretch.
    assert out["landslide_wall_sources"][0] == ["mapped wall", "slip", "slip"]
    assert out["landslide_wall_heights"][0][1:] == [None, None]
    assert out["landslide_wall_lengths"][0][1:] == [None, None]


def test_under_a_metre_alongside_is_a_slip():
    land = land_table([("C1", [("F1", None)])])
    # Ground starting at x 21 reaches within 2 m of the stretch from x 19.06.
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(21, 0.5, 24, 4)},
        lines=[("U", "C1", UNIT)],
    )

    assert out["landslide_wall_sources"][0] == ["slip"]


def test_a_unit_with_no_stretch_on_the_claim_is_a_slip():
    land = land_table([("C1", [("F1", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 3)},
        lines=[("U", "C2", UNIT)],
    )

    assert out["landslide_wall_sources"][0] == ["slip"]


def test_a_large_model_landslide_or_a_polygon_on_no_unit_is_a_slip():
    land = land_table([("C1", [("L1", None), ("F2", None)])])
    out = attach_mapped_walls(
        land,
        walls_table([]),
        slope_ids=pd.Series({"L1": None, "F2": "S2"}, dtype=object),
        wall_line_of_slope=pd.Series({"S2": None}, dtype=object),
        height_of_wall_line=pd.Series({"U": 1.5}),
        candidate_stretches=stretches([("U", "C1", UNIT)]),
        evacuated_ground={("C1", "L1"): box(5, 0, 9, 3), ("C1", "F2"): box(5, 0, 9, 3)},
    )

    assert out["landslide_wall_sources"][0] == ["slip", "slip"]


def test_a_failure_a_damaged_wall_holds_is_a_slip_whatever_unit_it_stands_on():
    land = land_table([("C1", [("F1", "W1"), ("F2", "W2")])])
    # W1 is damaged on this claim; W2 is not damaged, so does not hold F2.
    rw = walls_table([("C1", "W1", False, True), ("C1", "W2", False, False)])
    out = run(
        land,
        rw,
        ground={("C1", "F1"): box(5, 0, 9, 3), ("C1", "F2"): box(5, 0, 9, 3)},
        lines=[("U", "C1", UNIT)],
    )

    assert out["landslide_wall_sources"][0] == ["slip", "mapped wall"]


def test_two_failures_on_one_unit_and_claim_share_the_union_on_the_first():
    land = land_table([("C1", [("F1", None), ("F2", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 3), ("C1", "F2"): box(8, 0, 12, 3)},
        lines=[("U", "C1", UNIT)],
    )

    # 3 to 11 and 6 to 14 m: the union is 3 to 14 m, counted once.
    assert out["landslide_wall_lengths"][0] == pytest.approx([11.0, 0.0])
    assert out["landslide_wall_sources"][0] == ["mapped wall", "mapped wall"]


def test_the_shared_wall_goes_to_the_failure_with_the_most_evacuated_ground():
    land = land_table([("C1", [("F1", None), ("F2", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 7, 3), ("C1", "F2"): box(8, 0, 12, 3)},
        lines=[("U", "C1", UNIT)],
    )

    # 3 to 14 m, counted once, on the larger ground.
    assert out["landslide_wall_lengths"][0] == pytest.approx([0.0, 11.0])


def test_a_failure_with_no_evacuated_area_builds_no_mapped_wall():
    land = land_table([("C1", [("F1", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 0)},
        lines=[("U", "C1", UNIT)],
    )

    assert out["landslide_wall_sources"][0] == ["slip"]


def test_two_failures_on_different_claims_each_take_their_own_stretch():
    land = land_table([("C1", [("F1", None)]), ("C2", [("F1", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 3), ("C2", "F1"): box(5, 0, 9, 3)},
        lines=[("U", "C1", UNIT), ("U", "C2", LineString([(0, 0), (6, 0)]))],
    )

    # C1's stretch, and C2's within 2 m of its ground (3 to 6 m, with C1's own
    # stretch lying along the same 3 to 6 m, so the shared part is halved).
    assert out["landslide_wall_lengths"][0] == pytest.approx([6.5])
    assert out["landslide_wall_lengths"][1] == pytest.approx([1.5])


def test_a_failure_on_two_polygons_of_one_claim_is_built_once():
    land = land_table([("C1", [("F1", None)]), ("C1", [("F1", None)])])
    out = run(
        land,
        walls_table([]),
        ground={("C1", "F1"): box(5, 0, 9, 3)},
        lines=[("U", "C1", UNIT)],
    )

    assert out["landslide_wall_lengths"].tolist() == [[8.0], [0.0]]
    assert out["landslide_wall_sources"].tolist() == [["mapped wall"], ["mapped wall"]]


def test_a_land_table_without_the_failure_lists_is_returned_as_it_is():
    land = pd.DataFrame({"land_id": ["L1"], "claim_id": ["C1"]})

    out = attach_mapped_walls(
        land,
        walls_table([]),
        slope_ids=pd.Series(dtype=object),
        wall_line_of_slope=pd.Series(dtype=object),
        height_of_wall_line=pd.Series(dtype=float),
        candidate_stretches=stretches([("U", "C1", UNIT)]),
        evacuated_ground={},
    )

    assert list(out.columns) == ["land_id", "claim_id"]


def test_a_stretch_on_a_shared_boundary_is_shared_between_the_claims():
    near = box(5, 0, 9, 3)

    both = stretches([("U", "C1", UNIT), ("U", "C2", UNIT)])
    assert alongside_length(both, "C1", near) == pytest.approx(4.0)
    assert alongside_length(both, "C2", near) == pytest.approx(4.0)
    alone = stretches([("U", "C1", UNIT)])
    assert alongside_length(alone, "C1", near) == pytest.approx(8.0)
    assert alongside_length(alone, "C2", near) == 0.0


def test_the_held_rule_agrees_with_the_one_loss_settles_with():
    rw = walls_table(
        [
            ("C1", "W1", False, True),
            ("C1", "W2", True, False),
            ("C1", "W3", False, False),
            ("C2", "W1", False, False),
        ]
    )
    failures = pd.DataFrame(
        {
            "claim_id": ["C1", "C1", "C1", "C2", "C1"],
            "landslide_id": ["F1", "F2", "F3", "F4", "F5"],
            "rw_id": ["W1", "W2", "W3", "W1", None],
            "attributed": True,
        }
    )
    damaged = rw[rw["is_damaged_by_shaking"] | rw["is_evacuated"]].assign(
        rw_height=1.0, rw_length=5.0
    )

    by_loss = attach_failures_to_walls(failures, damaged) >= 0
    held = held_failure_keys(rw)
    by_vul = np.array(
        [
            (c, w) in held
            for c, w in zip(failures["claim_id"], failures["rw_id"], strict=True)
        ]
    )

    assert by_vul.tolist() == by_loss.tolist() == [True, True, False, False, False]
