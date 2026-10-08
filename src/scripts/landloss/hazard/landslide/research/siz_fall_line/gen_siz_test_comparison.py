"""Compare ground step 3's old siz test with the per-piece fall-line test on the pilots.

    uv run --frozen python src/scripts/landloss/hazard/landslide/research/siz_fall_line/gen_siz_test_comparison.py

Until 2026-10-08 ground step 3 (then landslide step 12) decided whether a pif is a siz by comparing every pair
of its points up to 30 m apart (``instability_zones.PAIRS_TEST``) on the whole
pif, and every piece :func:`split_pifs` cut from it took that verdict. Now each
piece is tested on its own pips with the fall-line test
(``FALL_LINE_TEST``), which reads each pip's drop down its true downhill line
to the toe of its face. This script finds the pips, pifs and pieces over each
pilot as ground step 3 does and puts each piece to three tests:

- ``old``: the pair test on the whole pif, inherited by the piece;
- ``d8``: the fall-line test on the piece, each pip falling along the nearest
  of the eight directions;
- ``new``: the fall-line test on the piece along the true downhill direction,
  what ground step 3 now runs.

It writes, per extent, under ``temp/hazard/landslide/research/siz-fall-line/``:

- ``siz-test-pips{suffix}.geoparquet``: one point per pip on a piece, with the
  piece and its verdict under each test, and ``agreement`` between ``old`` and
  ``new`` (``both``, ``old_only``, ``new_only`` or ``neither``);
- ``siz-test-pieces{suffix}.geoparquet``: one row per piece, its pips as a
  MultiPoint, with its parent, verdicts and both tests' angles and drop;

and the summary ``report/hazard/landslide/siz-fall-line/tab/siz-test-comparison.csv``.
Run landslide steps 3 and 4 over each extent first. Findings are in
``siz_fall_line.md`` beside this script.
"""

import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.hazard.landslide import instability_zones as zones
from landloss.hazard.landslide.slope_elements import terrain_layers
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_building_outlines
from scripts.landloss.ground.steps.s3_instability_zones import config as faces_config
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    CRS,
    building_mask,
    get_inputs,
)
from scripts.landloss.paths import REPORT_DIR, TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The pilots compared, and whether to reuse their cached LINZ layers.
EXTENTS = ("wlg-pilot", "porirua-pilot")
USE_CACHED_LAYERS = True

OUT_DIR = TEMP_DIR / "hazard" / "landslide" / "research" / "siz-fall-line"
TABLE_PATH = (
    REPORT_DIR
    / "hazard"
    / "landslide"
    / "siz-fall-line"
    / "tab"
    / "siz-test-comparison.csv"
)

VARIANTS = ("old", "d8", "new")
STAT_COLUMNS = (
    "max_angle_below_deg",
    "max_angle_above_deg",
    "max_delta_h_m",
    "threshold_angle_deg",
    "near_step_pass",
    "far_angle_pass",
    "is_siz",
)


def find_pieces(extent):
    """The grids, pips, whole pifs and their pieces, as ground step 3 finds them."""
    dem, transform, bbox, _, group, _ = get_inputs(
        extent=extent, use_cached_layers=USE_CACHED_LAYERS
    )
    buildings = get_nz_building_outlines(
        bbox=bbox, crs=CRS, use_cache=USE_CACHED_LAYERS
    )
    cell_size_m = abs(transform.a)
    pips = zones.find_pips(dem, cell_size_m)
    whole, _ = zones.cluster_pifs(pips.mask, cell_size_m)
    whole, _, _ = zones.exclude_pifs(
        whole, building_mask(buildings, transform, dem.shape)
    )
    whole, _ = zones.drop_short_pifs(
        whole, cell_size_m, min_length_m=zones.BETA_MIN_PIF_LENGTH_M
    )
    pieces, parent, _ = zones.split_pifs(
        whole,
        cell_size_m,
        max_span_m=zones.MAX_PIF_SPAN_M,
        max_bends=faces_config.WALL_MAX_BENDS,
        stray_tolerance_m=faces_config.WALL_STRAY_TOLERANCE_M,
        min_segment_m=faces_config.WALL_MIN_SEGMENT_M,
        max_turn_deg=faces_config.MAX_TOTAL_TURN_DEG,
    )
    return dem, group, transform, pips, whole, pieces, parent


def assess_variants(dem, group, transform, pips, whole, pieces, parent):
    """Each piece's verdict and statistics under the three variants, and timings."""
    seconds = {}
    start = time.perf_counter()
    on_whole = zones.assess_pifs(
        dem, pips, whole, group, transform, test=zones.PAIRS_TEST
    )
    seconds["old"] = time.perf_counter() - start
    start = time.perf_counter()
    d8 = zones.assess_pifs(
        dem, pips, pieces, group, transform, test=zones.FALL_LINE_TEST
    )
    seconds["d8"] = time.perf_counter() - start
    start = time.perf_counter()
    layers = terrain_layers(dem, abs(transform.a))
    new = zones.assess_pifs(
        dem,
        pips,
        pieces,
        group,
        transform,
        test=zones.FALL_LINE_TEST,
        downhill=(layers.downhill_row, layers.downhill_col),
    )
    seconds["new"] = time.perf_counter() - start
    parents = parent[new.index.to_numpy()]
    old = on_whole.reindex(parents).set_axis(new.index)
    table = new.drop(columns=list(STAT_COLUMNS))
    table.insert(0, "parent_pif_id", parents.astype(np.int64))
    for name, frame in (("old", old), ("d8", d8), ("new", new)):
        table = table.join(frame[list(STAT_COLUMNS)].add_prefix(f"{name}_"))
    table["agreement"] = agreement(table["old_is_siz"], table["new_is_siz"])
    return table, seconds


def agreement(old, new):
    """Name each piece's pair of verdicts."""
    old, new = old.astype(bool), new.astype(bool)
    return pd.Series(
        np.select(
            [old & new, old & ~new, ~old & new],
            ["both", "old_only", "new_only"],
            default="neither",
        ),
        index=old.index,
    )


def pip_points(pips, pieces, transform, table):
    """One point per pip on a piece, carrying its piece's verdicts."""
    rows, cols = np.nonzero(pips.mask & (pieces > 0))
    piece = pieces[rows, cols].astype(np.int64)
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    verdicts = table.loc[
        piece, ["parent_pif_id", *(f"{v}_is_siz" for v in VARIANTS), "agreement"]
    ].reset_index(drop=True)
    return gpd.GeoDataFrame(
        {"pif_id": piece}
        | {column: verdicts[column].to_numpy() for column in verdicts},
        geometry=gpd.points_from_xy(x, y),
        crs=CRS,
    )


def piece_frame(points, table):
    """One row per piece, its pips as a MultiPoint, with every variant's columns."""
    grouped = points.groupby("pif_id").geometry.apply(
        lambda g: shapely.MultiPoint(list(g))
    )
    return gpd.GeoDataFrame(table, geometry=grouped.reindex(table.index), crs=CRS)


def summary_rows(extent, table, points, seconds, n_whole):
    """The comparison of one extent, one row per measure."""
    flags = {v: table[f"{v}_is_siz"].astype(bool) for v in VARIANTS}
    by_pip = points["agreement"].value_counts()
    rows = {"whole_pifs": n_whole, "pieces": len(table), "pips": len(points)}
    for v in VARIANTS:
        rows[f"siz_pieces_{v}"] = int(flags[v].sum())
        rows[f"seconds_{v}"] = round(seconds[v], 1)
    for v in ("d8", "new"):
        rows[f"siz_old_not_{v}"] = int((flags["old"] & ~flags[v]).sum())
        rows[f"siz_{v}_not_old"] = int((~flags["old"] & flags[v]).sum())
    rows["siz_d8_not_new"] = int((flags["d8"] & ~flags["new"]).sum())
    rows["siz_new_not_d8"] = int((~flags["d8"] & flags["new"]).sum())
    rows["pips_old_only"] = int(by_pip.get("old_only", 0))
    rows["pips_new_only"] = int(by_pip.get("new_only", 0))
    for column in ("max_angle_below_deg", "max_angle_above_deg", "max_delta_h_m"):
        diff = table[f"new_{column}"] - table[f"d8_{column}"]
        rows[f"new_minus_d8_{column}_median"] = round(float(diff.median()), 3)
        rows[f"new_minus_d8_{column}_p95"] = round(float(diff.quantile(0.95)), 3)
    for ground_group, part in table.groupby("ground_group"):
        for v in VARIANTS:
            rows[f"siz_pieces_{v}_{ground_group}"] = int(part[f"{v}_is_siz"].sum())
    return pd.DataFrame(
        {"extent": extent, "measure": list(rows), "value": list(rows.values())}
    )


def main(*, extents):
    """Compare the variants over each extent and write the layers and table."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for extent in extents:
        print(f"\n=== {extent}", flush=True)
        dem, group, transform, pips, whole, pieces, parent = find_pieces(extent)
        table, seconds = assess_variants(
            dem, group, transform, pips, whole, pieces, parent
        )
        points = pip_points(pips, pieces, transform, table)
        suffix = extent_suffix(extent)
        points.to_parquet(OUT_DIR / f"siz-test-pips{suffix}.geoparquet")
        piece_frame(points, table).to_parquet(
            OUT_DIR / f"siz-test-pieces{suffix}.geoparquet"
        )
        summary = summary_rows(extent, table, points, seconds, int(whole.max()))
        print(summary.drop(columns="extent").to_string(index=False))
        summaries.append(summary)
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(summaries).to_csv(TABLE_PATH, index=False)
    print(f"\nWrote {TABLE_PATH} and the layers under {OUT_DIR}")


if __name__ == "__main__":
    main(extents=EXTENTS)
