"""Tests for combining the authorities' viewer CSVs into the region's."""

import pandas as pd
import pytest

from scripts.landloss.loss.ui.gen_viewer_region import (
    TA_COLUMN,
    combine_viewer_rows,
)


def rows(claims, *, version="vabc123, built 2026-10-12", method="area"):
    return pd.DataFrame(
        {
            "claim_id": claims,
            "settlement": [1.0] * len(claims),
            "liq_method": method,
            "built_with": version,
        }
    )


def test_the_authorities_are_stacked_and_labelled():
    combined = combine_viewer_rows(
        {"Porirua City": rows(["a", "b"]), "Wellington City": rows(["c"])}
    )
    assert combined["claim_id"].tolist() == ["a", "b", "c"]
    assert combined[TA_COLUMN].tolist() == [
        "Porirua City",
        "Porirua City",
        "Wellington City",
    ]
    assert list(combined.columns[:2]) == ["claim_id", TA_COLUMN]


def test_a_build_date_may_differ_but_not_the_commit():
    combine_viewer_rows(
        {
            "A": rows(["a"], version="vabc123, built 2026-10-11"),
            "B": rows(["b"], version="vabc123, built 2026-10-12"),
        }
    )
    with pytest.raises(ValueError, match="built_with"):
        combine_viewer_rows(
            {
                "A": rows(["a"], version="vabc123, built 2026-10-12"),
                "B": rows(["b"], version="vdef456, built 2026-10-12"),
            }
        )


def test_different_liquefaction_methods_are_refused():
    with pytest.raises(ValueError, match="liq_method"):
        combine_viewer_rows(
            {"A": rows(["a"], method="area"), "B": rows(["b"], method="lookup")}
        )


def test_a_claim_in_two_authorities_is_refused():
    with pytest.raises(ValueError, match="more than one authority"):
        combine_viewer_rows({"A": rows(["a", "b"]), "B": rows(["b"])})


def test_different_columns_are_refused():
    with pytest.raises(ValueError, match="different columns"):
        combine_viewer_rows(
            {"A": rows(["a"]), "B": rows(["b"]).drop(columns="settlement")}
        )


def test_nothing_to_combine_is_refused():
    with pytest.raises(ValueError, match="no viewer CSVs"):
        combine_viewer_rows({})
