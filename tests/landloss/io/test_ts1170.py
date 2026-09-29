"""Tests for reading TS1170.5:2025 Table 3.2.

The CSV is written to ``tmp_path`` by each test, and ``ts1170_table_3_2_path``
-- the one place that would reach R: -- is replaced. Nothing touches the
network drive.
"""

import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr

from landloss.io import ts1170

NUMERALS = ["I", "II", "III", "IV", "V", "VI"]
HEADER = ["location", "latitude", "longitude", "apoe", "M", "D"] + [
    f"{numeral}-{suffix}"
    for numeral in NUMERALS
    for suffix in ["PGA", "Sas", "Tc", "Td"]
]


def write_table(path):
    """Write two rows in the delivered layout, BOM and padded APoE included."""
    rows = [
        ["-41.3~174.8", -41.3, 174.8, " 1/2500", 7.9, "4.0"]
        + [v for i in range(6) for v in (1.0 + i, 2.0 + i, 0.3 + i, 2.5 + i)],
        ["-34.3~172.9", -34.3, 172.9, " 1/25", 6.2, "n/a"]
        + [v for i in range(6) for v in (0.1, 0.2, 0.4, 1.6)],
    ]
    pd.DataFrame(rows, columns=HEADER).to_csv(path, index=False, encoding="utf-8-sig")
    return path


@pytest.fixture
def table(tmp_path, monkeypatch):
    """Stand a written CSV in for the one on R:, and read it."""
    path = write_table(tmp_path / "table.csv")
    monkeypatch.setattr(ts1170, "ts1170_table_3_2_path", lambda **_: path)
    return ts1170.get_ts1170_table_3_2()


def test_one_row_per_grid_point_apoe_and_site_class(table) -> None:
    """Two delivered rows stack into twelve, one per site class each."""
    assert len(table) == 12
    assert sorted(table["site_class"].unique()) == [1, 2, 3, 4, 5, 6]
    assert list(table.columns) == [
        "latitude",
        "longitude",
        "apoe",
        "return_period_yr",
        "magnitude",
        "fault_distance_km",
        "site_class",
        "pga_g",
        "sa_s_g",
        "tc_s",
        "td_s",
    ]


def test_site_class_parameters_come_from_their_own_columns(table) -> None:
    """Site Class IV's row carries the IV- columns, not another class's."""
    row = table[(table["latitude"] == -41.3) & (table["site_class"] == 4)]

    assert row[["pga_g", "sa_s_g", "tc_s", "td_s"]].iloc[0].tolist() == [
        pytest.approx(4.0),
        pytest.approx(5.0),
        pytest.approx(3.3),
        pytest.approx(5.5),
    ]


def test_apoe_is_stripped_and_return_period_parsed(table) -> None:
    """The delivered APoE carries a leading space; the return period does not."""
    assert set(table["apoe"]) == {"1/2500", "1/25"}
    assert set(table["return_period_yr"]) == {2500, 25}


def test_fault_distance_na_is_missing(table) -> None:
    """``n/a`` fault distances read as missing rather than as text."""
    distances = table.groupby("latitude")["fault_distance_km"].first()

    assert distances[-41.3] == "4.0"
    assert pd.isna(distances[-34.3])


def test_sa_t1_fname_follows_the_nlm_pattern() -> None:
    """The grids are named as the NLM names its seismic-standard grids."""
    assert ts1170.ts1170_sa_t1_fname(2500, 4) == "sa_t1_2500yr_site_class_4.tif"


@pytest.mark.parametrize(("return_period_yr", "site_class"), [(2000, 4), (2500, 7)])
def test_sa_t1_fname_refuses_what_the_table_does_not_carry(
    return_period_yr, site_class
) -> None:
    """No 1/2000 APoE, and no Site Class VII."""
    with pytest.raises(ValueError, match="is not one of"):
        ts1170.ts1170_sa_t1_fname(return_period_yr, site_class)


# rioxarray builds a raster's transform with affine's deprecated `*` operator
# when writing it; the warning is theirs, not this reader's.
@pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning")
def test_get_sa_t1_reads_the_named_grid(tmp_path, monkeypatch) -> None:
    """The grid for the asked return period and site class is read, in g."""
    grid = xr.DataArray(
        np.array([[1.5, np.nan], [2.0, 2.5]], dtype="float32"),
        dims=("y", "x"),
        coords={"y": [1.0, 0.0], "x": [0.0, 1.0]},
    ).rio.write_crs("EPSG:2193")
    path = tmp_path / "sa_t1_2500yr_site_class_4.tif"
    grid.rio.write_nodata(np.nan).rio.to_raster(path)
    asked = []
    monkeypatch.setattr(
        ts1170.tdrive_sync,
        "get_cached",
        lambda p, **_: asked.append(p) or path,
    )

    result = ts1170.get_ts1170_sa_t1(2500, 4)

    assert asked == [ts1170.TS1170_SA_T1_DIR / "sa_t1_2500yr_site_class_4.tif"]
    assert result.rio.crs.to_epsg() == 2193
    assert float(result[0, 0]) == pytest.approx(1.5)
    assert np.isnan(float(result[0, 1]))
