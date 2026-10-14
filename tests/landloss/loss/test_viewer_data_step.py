"""Tests for the loss viewer's data script (loss/ui/gen_viewer_data.py)."""

import inspect
import re

import pandas as pd
import pytest

from landloss.hazard.landslide.urban.realisation import FAILED_WITH_POLYGON
from scripts.landloss.loss.ui import gen_viewer_data
from scripts.landloss.loss.ui.gen_viewer_data import (
    AREA_METHOD,
    LOOKUP_METHOD,
    cause_label,
    landslide_by_origin,
    liquefaction_method,
    within_territorial_authority,
)

# A point inside Porirua City and one in central Wellington, in degrees.
IN_PORIRUA = (174.930, -41.084)
IN_WELLINGTON = (174.776, -41.288)


@pytest.mark.parametrize(
    ("flags", "label"),
    [
        ((True, False, False), "Liquefaction"),
        ((False, True, False), "Landslide"),
        ((False, False, True), "Retaining wall failure"),
        ((False, True, True), "Landslide and retaining wall failure"),
        ((True, True, True), "Liquefaction, landslide and retaining wall failure"),
        ((False, False, False), ""),
    ],
)
def test_the_cause_names_every_source_of_damage(flags, label) -> None:
    liquefaction, landslide, wall = flags
    assert (
        cause_label(liquefaction=liquefaction, landslide=landslide, wall=wall) == label
    )


def rows_at(*points) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "claim_id": [f"c{i}" for i in range(len(points))],
            "lon": [p[0] for p in points],
            "lat": [p[1] for p in points],
        }
    )


def test_an_authority_extent_keeps_only_its_own_claims() -> None:
    kept = within_territorial_authority(rows_at(IN_PORIRUA, IN_WELLINGTON), "porirua")
    assert kept["claim_id"].tolist() == ["c0"]


@pytest.mark.parametrize("extent", ["full", "wlg-pilot"])
def test_an_extent_that_is_not_one_authority_is_kept_whole(extent) -> None:
    rows = rows_at(IN_PORIRUA, IN_WELLINGTON)
    pd.testing.assert_frame_equal(within_territorial_authority(rows, extent), rows)


@pytest.mark.parametrize(
    ("settled_excl_gst", "method"),
    [([200.0, 0.0], LOOKUP_METHOD), ([1100.0, 0.0], AREA_METHOD)],
)
def test_the_method_is_whichever_cost_was_settled(
    tmp_path, monkeypatch, settled_excl_gst, method
) -> None:
    path = tmp_path / "liq.parquet"
    pd.DataFrame(
        {
            "claim_id": ["a", "b"],
            "cost_nzd": [200.0, 500.0],
            "area_cost_nzd": [1100.0, 0.0],
        }
    ).to_parquet(path)
    monkeypatch.setattr(
        gen_viewer_data.liq_land, "liq_land_damage_path", lambda *_, **__: path
    )
    claims = pd.DataFrame(
        {
            gen_viewer_data.LIQ_REPAIR_COLUMN: [
                v * gen_viewer_data.LIQ_COST_ESCALATION * 1.15 for v in settled_excl_gst
            ]
        },
        index=pd.Index(["a", "b"], name="claim_id"),
    )
    assert liquefaction_method(claims, 0, extent="porirua") == method


def test_the_version_names_the_commit_and_the_build_date() -> None:
    version = gen_viewer_data.viewer_version()
    assert re.fullmatch(
        r"v[0-9a-f]{6}, built \d{4}-\d{2}-\d{2}(, with uncommitted changes)?", version
    )


def test_the_written_page_carries_the_version_in_place_of_the_placeholder(
    tmp_path,
) -> None:
    page = gen_viewer_data.write_viewer(tmp_path, "v1a2b3c, built 2026-10-09")
    text = page.read_text(encoding="utf-8")
    assert gen_viewer_data.VERSION_PLACEHOLDER not in text
    assert '<span id="version">v1a2b3c, built 2026-10-09</span>' in text


def land_with(*polygons) -> pd.DataFrame:
    """Build a land table from (claim, pooled_union, [(ls, rw, area, wet)])."""
    rows = [
        {
            "claim_id": claim,
            "land_slide_total_insured_land_area": union,
            "landslide_ids": [f[0] for f in failures],
            "landslide_rw_ids": [f[1] for f in failures],
            "landslide_areas": [float(f[2]) for f in failures],
            "landslide_inundated_areas": [float(f[3]) for f in failures],
            "landslide_inundated_depths": [1.0 for _ in failures],
        }
        for claim, union, failures in polygons
    ]
    return pd.DataFrame(rows)


def rw_with(*walls, damaged=True) -> pd.DataFrame:
    """Build a wall table from (claim, rw_id, parent_rw_id)."""
    return pd.DataFrame(
        {
            "claim_id": [w[0] for w in walls],
            "rw_id": [w[1] for w in walls],
            "parent_rw_id": [w[2] for w in walls],
            "rw_height": 2.0,
            "rw_length": 10.0,
            "is_damaged_by_shaking": False,
            "is_evacuated": damaged,
            "is_inundated": False,
        }
    )


def origin_of(land, rw, claim="C1"):
    return landslide_by_origin(land, rw).loc[claim]


def test_ground_that_came_with_the_claims_own_wall_is_wall_ground() -> None:
    land = land_with(("C1", 100.0, [("S1", "W1", 100, 0)]))
    got = origin_of(land, rw_with(("C1", "W1", "W1")))
    assert got["wall_landslide_m2"] == 100
    assert got["other_landslide_m2"] == 0


def test_a_neighbours_slip_is_other_ground() -> None:
    land = land_with(("C1", 140.0, [("S1", "W1", 100, 0), ("S2", "W9", 40, 0)]))
    got = origin_of(land, rw_with(("C1", "W1", "W1")))
    assert got["wall_landslide_m2"] == 100
    assert got["other_landslide_m2"] == 40


def test_a_slope_only_slip_is_other_ground() -> None:
    land = land_with(("C1", 60.0, [("S3", None, 60, 0)]))
    got = origin_of(land, rw_with(("C1", "W1", "W1")))
    assert got["wall_landslide_m2"] == 0
    assert got["other_landslide_m2"] == 60


def test_a_split_walls_piece_holds_the_slip_of_its_whole_wall() -> None:
    land = land_with(("B", 50.0, [("S1", "W1", 50, 0)]))
    got = origin_of(land, rw_with(("B", "W1-P2", "W1")), claim="B")
    assert got["wall_landslide_m2"] == 50


def test_an_undamaged_piece_holds_nothing() -> None:
    land = land_with(("C1", 50.0, [("S1", "W1", 50, 0)]))
    got = origin_of(land, rw_with(("C1", "W1", "W1"), damaged=False))
    assert got["wall_landslide_m2"] == 0
    assert got["other_landslide_m2"] == 50


def test_a_slip_with_a_wall_on_another_claim_is_other_ground() -> None:
    land = land_with(("C1", 50.0, [("S1", "W1", 50, 0)]))
    got = origin_of(land, rw_with(("C1", "W2", "W2"), ("C2", "W1", "W1")))
    assert got["wall_landslide_m2"] == 0
    assert got["other_landslide_m2"] == 50


def test_failures_on_two_polygons_add_and_one_failure_counts_once() -> None:
    two = land_with(
        ("C1", 100.0, [("S1", "W1", 100, 0)]), ("C1", 50.0, [("S2", "W1", 50, 0)])
    )
    got = origin_of(two, rw_with(("C1", "W1", "W1")))
    assert got["wall_landslide_m2"] == 150
    spanning = land_with(
        ("C1", 25.0, [("S1", "W1", 25, 0)]), ("C1", 15.0, [("S1", "W1", 15, 0)])
    )
    assert origin_of(spanning, rw_with(("C1", "W1", "W1")))["wall_landslide_m2"] == 40


def test_wall_ground_is_capped_at_the_pooled_ground() -> None:
    land = land_with(("C1", 60.0, [("S1", "W1", 60, 0), ("S2", "W1", 60, 0)]))
    got = origin_of(land, rw_with(("C1", "W1", "W1")))
    assert got["wall_landslide_m2"] == 60


def test_a_land_table_without_the_lists_raises() -> None:
    land = pd.DataFrame(
        {"claim_id": ["C1"], "land_slide_total_insured_land_area": [10.0]}
    )
    with pytest.raises(ValueError, match="rerun vul step 10"):
        landslide_by_origin(land, rw_with(("C1", "W1", "W1")))


def test_with_no_damaged_wall_all_ground_is_other() -> None:
    land = land_with(("C1", 50.0, [("S1", "W1", 50, 0)]))
    got = origin_of(land, rw_with(("C1", "W1", "W1"), damaged=False))
    assert got["wall_landslide_m2"] == 0
    assert got["other_landslide_m2"] == 50


def run_damaged_land(tmp_path, monkeypatch, *, land, rw, outcomes) -> pd.DataFrame:
    """Run damaged_land over small parquet files written to tmp_path."""
    module = gen_viewer_data
    paths = {}
    for name, frame in (("land", land), ("rw", rw)):
        paths[name] = tmp_path / f"{name}.parquet"
        frame.to_parquet(paths[name])
    liq = tmp_path / "liq.parquet"
    pd.DataFrame(
        {
            "claim_id": ["x"],
            "ld_state": [1],
            "evacuated_area_m2": [0.0],
            "inundated_area_m2": [0.0],
        }
    ).to_parquet(liq)
    slid = tmp_path / "slid.parquet"
    pooled = land.groupby("claim_id")["land_slide_total_insured_land_area"].sum()
    pd.DataFrame(
        {
            "claim_id": pooled.index,
            "evacuated_area_m2": pooled.to_numpy(),
            "inundated_area_m2": 0.0,
        }
    ).to_parquet(slid)
    walls = tmp_path / "walls.parquet"
    pd.DataFrame(
        {"claim_id": outcomes, "outcome": [FAILED_WITH_POLYGON] * len(outcomes)}
    ).to_parquet(walls)
    monkeypatch.setattr(module.liq_land, "liq_land_damage_path", lambda *_, **__: liq)
    monkeypatch.setattr(
        module.landslide_land, "landslide_land_damage_path", lambda *_, **__: slid
    )
    monkeypatch.setattr(
        module.wall_landslide, "wall_landslide_damage_path", lambda *_, **__: walls
    )
    monkeypatch.setattr(
        module, "world_loss_input_path", lambda table, *_, **__: paths[table]
    )
    return module.damaged_land(0, 0, extent="full")


def test_ground_with_its_own_wall_types_the_claim_retaining_wall_only(
    tmp_path, monkeypatch
) -> None:
    land = land_with(("C1", 100.0, [("S1", "W1", 100, 0)]))
    got = run_damaged_land(
        tmp_path,
        monkeypatch,
        land=land,
        rw=rw_with(("C1", "W1", "W1")),
        outcomes=["C1"],
    ).loc["C1"]
    assert got["cause"] == "Retaining wall failure"
    assert got["has_landslide"] == 0
    assert got["wall_landslide_m2"] == 100
    assert got["evacuated_m2"] == 100


def test_a_neighbours_slip_as_well_types_the_claim_combination(
    tmp_path, monkeypatch
) -> None:
    land = land_with(("C1", 140.0, [("S1", "W1", 100, 0), ("S2", "W9", 40, 0)]))
    got = run_damaged_land(
        tmp_path,
        monkeypatch,
        land=land,
        rw=rw_with(("C1", "W1", "W1")),
        outcomes=["C1"],
    ).loc["C1"]
    assert got["cause"] == "Landslide and retaining wall failure"
    assert got["has_landslide"] == 1


def test_a_slope_only_slip_stays_landslide(tmp_path, monkeypatch) -> None:
    land = land_with(("C1", 60.0, [("S3", None, 60, 0)]))
    got = run_damaged_land(
        tmp_path,
        monkeypatch,
        land=land,
        rw=rw_with(("C1", "W1", "W1"), damaged=False),
        outcomes=[],
    ).loc["C1"]
    assert got["cause"] == "Landslide"
    assert got["has_landslide"] == 1
    assert got["wall_landslide_m2"] == 0


def test_damaged_land_raises_without_the_lists(tmp_path, monkeypatch) -> None:
    land = pd.DataFrame(
        {"claim_id": ["C1"], "land_slide_total_insured_land_area": [100.0]}
    )
    with pytest.raises(ValueError, match="rerun vul step 10"):
        run_damaged_land(
            tmp_path,
            monkeypatch,
            land=land,
            rw=rw_with(("C1", "W1", "W1")),
            outcomes=["C1"],
        )


def test_damaged_land_raises_without_the_parent_wall_id(tmp_path, monkeypatch) -> None:
    land = land_with(("C1", 100.0, [("S1", "W1", 100, 0)]))
    rw = rw_with(("C1", "W1", "W1")).drop(columns="parent_rw_id")
    with pytest.raises(ValueError, match="parent_rw_id"):
        run_damaged_land(tmp_path, monkeypatch, land=land, rw=rw, outcomes=["C1"])


def test_a_claim_with_only_a_piece_of_the_failed_wall_stays_in_the_table(
    tmp_path, monkeypatch
) -> None:
    land = land_with(("B", 50.0, [("S1", "W1", 50, 0)]))
    got = run_damaged_land(
        tmp_path,
        monkeypatch,
        land=land,
        rw=rw_with(("B", "W1-P2", "W1")),
        outcomes=["A"],
    ).loc["B"]
    assert got["evacuated_m2"] == 50
    assert got["cause"] == "Retaining wall failure"
    assert got["has_landslide"] == 0


def test_the_settlement_arithmetic_reads_none_of_the_typing() -> None:
    source = inspect.getsource(gen_viewer_data.settled_in_python)
    for name in ("cause", "has_landslide", "wall_landslide_m2"):
        assert f'"{name}"' not in source
