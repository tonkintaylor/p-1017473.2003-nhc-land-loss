"""Tests for the loss viewer's data script (loss/ui/gen_viewer_data.py)."""

import pandas as pd
import pytest

from scripts.landloss.loss.ui import gen_viewer_data
from scripts.landloss.loss.ui.gen_viewer_data import (
    AREA_METHOD,
    LOOKUP_METHOD,
    cause_label,
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
        {gen_viewer_data.LIQ_REPAIR_COLUMN: [v * 1.15 for v in settled_excl_gst]},
        index=pd.Index(["a", "b"], name="claim_id"),
    )
    assert liquefaction_method(claims, 0, extent="porirua") == method
