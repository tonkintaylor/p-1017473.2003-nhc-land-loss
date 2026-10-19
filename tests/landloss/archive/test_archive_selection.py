import sqlite3
from contextlib import closing
from pathlib import Path, PurePath

import pytest

from scripts.landloss.archive.archive_results import (
    authority_of,
    left_out,
    plan_reports,
    plan_results,
)
from scripts.landloss.archive.archive_web_inputs import LAYER_FILE, TABLE_FILE, newest
from scripts.landloss.archive.copying import PlannedCopy, check_targets, damage

AUTHORITIES = ["wellington-city", "lower-hutt", "upper-hutt", "porirua"]


@pytest.mark.parametrize(
    ("name", "authority"),
    [
        ("settlement-w000-r000-lower-hutt.parquet", "lower-hutt"),
        ("dem-1m-upper-hutt.tif", "upper-hutt"),
        ("urban-slope-zones-w000-wellington-city.parquet", "wellington-city"),
        ("wall-population-w000-porirua.geoparquet", "porirua"),
        ("settlement-w000-r000-pilot.parquet", None),
        ("address-spine.geoparquet", None),
    ],
)
def test_a_file_is_an_authoritys_only_when_its_name_carries_it(name, authority) -> None:
    assert authority_of(name, AUTHORITIES) == authority


@pytest.mark.parametrize(
    "relative",
    [
        "ground/dem-1m-porirua.tif",
        "ground/slope-30m-porirua.tif",
        "hazard/landslide/aspect-10m-porirua.tif",
        "ground/terrain/cut-fill-residual-30m-porirua.tif",
        "hazard/landslide/terrain/face-height-5m-porirua.tif",
        "ground/urban-slope-found-porirua-tiles/tile-01-02.pkl",
        "hazard/landslide/urban-slope-zones-tiles-porirua/tile-00-03.pkl",
        "exposure/claim-valuation-links-porirua.parquet",
        "loss/qv-tier-factors/qv-tier-factors-by-property-porirua.geoparquet",
        "hazard/landslide/ground-map-porirua.geoparquet",
        "loss/settlement-w000-r000-porirua.parquet.partial",
        "reference/x-porirua.csv",
    ],
)
def test_dems_tiles_qv_records_and_stale_copies_are_left_out(relative) -> None:
    assert left_out(PurePath(relative)) is not None


@pytest.mark.parametrize(
    "relative",
    [
        "loss/settlement-w000-r000-porirua.parquet",
        "ground/urban-slope-found-porirua.pkl",
        "ground/ground-map-porirua.geoparquet",
        "hazard/landslide/slope-units-porirua.geoparquet",
        "exposure/land-value-by-address-porirua.geoparquet",
        "vul/loss-input-rw-w000-r000-porirua.geoparquet",
    ],
)
def test_results_are_archived(relative) -> None:
    assert left_out(PurePath(relative)) is None


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(path.name, encoding="utf-8")
    return path


def test_each_authority_comes_only_from_its_own_runs_folder(tmp_path) -> None:
    here, remote = tmp_path / "here", tmp_path / "remote"
    touch(here / "loss" / "settlement-w000-r000-wellington-city.parquet")
    touch(here / "loss" / "settlement-w000-r000-porirua.parquet")  # stale here
    touch(remote / "loss" / "settlement-w000-r000-wellington-city.parquet")  # stale
    touch(remote / "loss" / "settlement-w000-r000-porirua.parquet")
    plan, _ = plan_results(
        {"wellington-city": here, "porirua": remote},
        target_of=lambda relative: tmp_path / "t" / relative,
    )
    assert sorted((p.source.parent.parent.name, p.source.name) for p in plan) == [
        ("here", "settlement-w000-r000-wellington-city.parquet"),
        ("remote", "settlement-w000-r000-porirua.parquet"),
    ]


def test_results_land_under_their_module_on_the_target(tmp_path) -> None:
    root = tmp_path / "temp"
    touch(root / "hazard" / "landslide" / "slope-units-porirua.geoparquet")
    plan, skipped = plan_results(
        {"porirua": root}, target_of=lambda relative: Path("T:/v1") / relative
    )
    assert [p.target for p in plan] == [
        Path("T:/v1/hazard/landslide/slope-units-porirua.geoparquet")
    ]
    assert skipped == {}


def test_report_outputs_skip_the_pilot_and_go_under_report(tmp_path) -> None:
    touch(tmp_path / "loss" / "viewer" / "loss-viewer-w000-r000-porirua.csv")
    touch(tmp_path / "loss" / "viewer" / "loss-viewer-w000-r000-pilot.csv")
    plan = plan_reports(
        tmp_path,
        ["loss/viewer/loss-viewer-w000-r000-*.csv"],
        ["pilot"],
        target_of=lambda relative: Path("T:/v1") / relative,
    )
    assert [p.target for p in plan] == [
        Path("T:/v1/report/loss/viewer/loss-viewer-w000-r000-porirua.csv")
    ]


def test_only_the_newest_cached_version_of_each_layer_is_taken() -> None:
    paths = [Path(f"122657_{v}_{'a' * 32}.gpkg") for v in (447785, 448761, 448299)] + [
        Path(f"50318_436824_{'b' * 32}.gpkg"),
        Path(f"122657_448761_{'c' * 32}_{'d' * 16}.gpkg"),
    ]
    assert [(layer, v) for _, layer, v in newest(paths, LAYER_FILE)] == [
        (50318, 436824),
        (122657, 448761),
    ]
    tables = [Path("51567_448453.parquet"), Path("51567_448920.parquet")]
    assert [v for _, _, v in newest(tables, TABLE_FILE)] == [448920]


def test_a_target_with_other_contents_stops_the_copy(tmp_path) -> None:
    source = touch(tmp_path / "a" / "x.csv")
    same = tmp_path / "t" / "x.csv"
    touch(same)
    item = PlannedCopy(source, same, "g")
    assert check_targets([item]) == ([], [item])
    same.write_text("changed", encoding="utf-8")
    with pytest.raises(FileExistsError, match="never overwritten"):
        check_targets([item])


def test_a_file_cut_short_in_copying_is_damaged(tmp_path) -> None:
    import pandas as pd  # noqa: PLC0415 -- this test alone

    whole = tmp_path / "x.parquet"
    pd.DataFrame({"a": range(1000)}).to_parquet(whole)
    short = tmp_path / "short.parquet"
    short.write_bytes(whole.read_bytes()[:-100])
    assert damage(whole) is None
    assert damage(short) is not None


@pytest.mark.parametrize("relative", [False, True])
def test_geopackage_integrity_accepts_absolute_and_relative_paths(
    tmp_path, monkeypatch, relative
) -> None:
    whole = tmp_path / "whole #1.gpkg"
    with closing(sqlite3.connect(whole)) as db:
        db.execute("CREATE TABLE features (id INTEGER PRIMARY KEY)")
    monkeypatch.chdir(tmp_path)
    path = Path(whole.name) if relative else whole
    assert damage(path) is None


def test_corrupt_geopackage_is_damaged(tmp_path, monkeypatch) -> None:
    corrupt = tmp_path / "corrupt.gpkg"
    corrupt.write_bytes(b"not a SQLite database")
    monkeypatch.chdir(tmp_path)
    assert "DatabaseError" in damage(Path(corrupt.name))


def test_missing_geopackage_is_not_created(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    missing = Path("missing.gpkg")
    assert "OperationalError" in damage(missing)
    assert not missing.exists()
