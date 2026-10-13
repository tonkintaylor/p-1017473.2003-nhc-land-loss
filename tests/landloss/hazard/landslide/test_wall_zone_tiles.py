"""Tests for how landslide step 4 keeps, resumes and stitches its tiles."""

import inspect
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
import shapely
from rasterio import windows
from rasterio.transform import Affine

from landloss.common.utils import tiles
from landloss.hazard.landslide.slope_polygons import SlopePolygons
from scripts.landloss.ground.steps.s3_instability_zones import tiled
from scripts.landloss.hazard.landslide.steps.s4_wall_zones import (
    gen_wall_zones,
    zone_tiles,
)

EXTENT = "porirua-pilot"
CRS = "EPSG:2193"


def make_tile(row, col):
    """A tile with empty windows: the step only reads its row and column."""
    window = windows.Window(0, 0, 1, 1)
    return tiles.Tile(row, col, window, window, (0.0, 0.0, 1.0, 1.0))


def make_found(*grid):
    """A TiledFound over the tiles at the given (row, col) places, in that order."""
    found_tiles = [tiled.FoundTile(make_tile(r, c), None) for r, c in grid]
    return tiled.TiledFound(Affine(1, 0, 0, 0, -1, 0), found_tiles, {})


def make_tile_zones(key, x):
    """One tile's zones for one scenario, a square polygon for one element."""
    zone = gpd.GeoDataFrame(
        {
            "element": [1],
            "element_key": [key],
            "forced": [False],
            "polygon": [1],
            "zone": ["evacuated"],
        },
        geometry=[shapely.box(x, 0, x + 1, 1)],
        crs=CRS,
    )
    element = gpd.GeoDataFrame(
        {"element_key": [key]}, geometry=[shapely.box(x, 0, x + 1, 1)], crs=CRS
    )
    return tiled.TileZones({"walled": zone}, element)


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_wall_zones, "WORK_DIR", tmp_path)
    return tmp_path


def keep(tile, value="zones"):
    zone_tiles.write_tile_zones(
        value, gen_wall_zones.tile_zones_path(tile, extent=EXTENT)
    )


def test_a_tile_from_the_same_record_is_kept(work_dir):
    record = {"settings": {"a": 1}}
    gen_wall_zones.keep_or_clear_tiles(extent=EXTENT, record=record, rebuild=False)
    keep(make_tile(0, 0))
    cleared = gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=False
    )
    assert cleared == 0
    assert gen_wall_zones.tile_zones_path(make_tile(0, 0), extent=EXTENT).exists()


def test_a_tile_from_a_different_record_is_cleared(work_dir):
    gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {"a": 1}}, rebuild=False
    )
    keep(make_tile(0, 0))
    keep(make_tile(0, 1))
    cleared = gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {"a": 2}}, rebuild=False
    )
    assert cleared == 2
    assert not gen_wall_zones.tile_zones_path(make_tile(0, 0), extent=EXTENT).exists()


def test_tiles_with_no_record_are_cleared(work_dir):
    keep(make_tile(0, 0))
    cleared = gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {"a": 1}}, rebuild=False
    )
    assert cleared == 1


def test_rebuild_clears_tiles_of_the_same_record(work_dir):
    record = {"settings": {"a": 1}}
    gen_wall_zones.keep_or_clear_tiles(extent=EXTENT, record=record, rebuild=False)
    keep(make_tile(0, 0))
    cleared = gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=True
    )
    assert cleared == 1


def test_the_kept_tiles_folder_is_named_for_the_extent(work_dir):
    folder = gen_wall_zones.tiles_dir(extent=EXTENT)
    assert folder.parent == work_dir
    assert "-porirua-pilot" in folder.name


def test_a_killed_write_leaves_no_file(work_dir):
    path = gen_wall_zones.tile_zones_path(make_tile(0, 0), extent=EXTENT)

    class Unpicklable:
        def __reduce__(self):
            raise RuntimeError

    with pytest.raises(RuntimeError):
        zone_tiles.write_tile_zones(Unpicklable(), path)
    assert not path.exists()
    assert not list(path.parent.glob("*.partial"))


def test_only_the_tiles_not_kept_are_to_build(work_dir):
    found = make_found((0, 0), (0, 1), (1, 0), (1, 1))
    keep(make_tile(0, 0))
    keep(make_tile(1, 0))
    todo = gen_wall_zones.tiles_to_build(found, extent=EXTENT)
    assert [(t.tile.row, t.tile.col) for t in todo] == [(0, 1), (1, 1)]


def fake_builder(built, fail_on=None):
    """A stand-in for build_zone_tile that keeps a tile as the real one does."""

    def build(found_tile, *, path):
        tile = found_tile.tile
        if (tile.row, tile.col) == fail_on:
            msg = "tile failed"
            raise RuntimeError(msg)
        zone_tiles.write_tile_zones(make_tile_zones(("grown", 1), 0), path)
        built.append((tile.row, tile.col))
        return {"tile": tile, "n_elements": 1, "seconds": 0.0}

    return build


def run(found, builder, monkeypatch):
    monkeypatch.setattr(zone_tiles, "build_zone_tile", builder)
    monkeypatch.setattr(zone_tiles, "start_worker", lambda *args: None)
    todo = gen_wall_zones.tiles_to_build(found, extent=EXTENT)
    gen_wall_zones.run_tiles(
        todo,
        workers=1,
        start_args=(),
        tile_kwargs=[
            {"path": gen_wall_zones.tile_zones_path(t.tile, extent=EXTENT)}
            for t in todo
        ],
    )


def test_a_failed_tile_leaves_the_others_kept_and_a_rerun_builds_only_it(
    work_dir, monkeypatch
):
    found = make_found((0, 0), (0, 1), (1, 0), (1, 1))
    first = []
    with pytest.raises(RuntimeError, match="tile failed"):
        run(found, fake_builder(first, fail_on=(0, 1)), monkeypatch)
    assert first == [(0, 0)]
    second = []
    run(found, fake_builder(second), monkeypatch)
    assert second == [(0, 1), (1, 0), (1, 1)]
    assert gen_wall_zones.tiles_to_build(found, extent=EXTENT) == []


def test_the_progress_line_names_the_tile_its_elements_and_times():
    summary = {"tile": make_tile(2, 3), "n_elements": 1234, "seconds": 41.6}
    line = gen_wall_zones.describe_tile(summary, number=2, total=4, elapsed=90.2)
    assert "[2/4]" in line
    assert "tile 2,3" in line
    assert "1,234 elements" in line
    assert "42 s" in line
    assert "90 s in all" in line


def test_the_kept_tiles_are_read_in_tile_order_whatever_order_they_finished(
    work_dir,
):
    found = make_found((0, 0), (0, 1), (1, 0))
    keys = {(0, 0): ("grown", 1), (0, 1): ("grown", 2), (1, 0): ("grown", 3)}
    for place in [(1, 0), (0, 0), (0, 1)]:
        keep(make_tile(*place), make_tile_zones(keys[place], place[1] + 10 * place[0]))
    read = gen_wall_zones.read_kept_tiles(found, extent=EXTENT)
    assert [z.elements["element_key"].iloc[0] for z in read] == [
        keys[(0, 0)],
        keys[(0, 1)],
        keys[(1, 0)],
    ]


def test_the_stitch_does_not_depend_on_the_order_the_tiles_were_kept(work_dir):
    found = make_found((0, 0), (0, 1), (1, 0))
    keys = {(0, 0): ("grown", 1), (0, 1): ("grown", 2), (1, 0): ("grown", 3)}
    labels = {key: number for number, key in enumerate(keys.values(), 1)}

    def stitched(order):
        for place in order:
            keep(
                make_tile(*place),
                make_tile_zones(keys[place], place[1] + 10 * place[0]),
            )
        read = gen_wall_zones.read_kept_tiles(found, extent=EXTENT)
        return tiled.stitch_zones(read, labels, "walled")

    one = stitched([(0, 0), (0, 1), (1, 0)])
    other = stitched([(1, 0), (0, 1), (0, 0)])
    pd.testing.assert_frame_equal(one, other)
    assert one["polygon"].tolist() == [1, 2, 3]
    assert one["element"].tolist() == [1, 2, 3]


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def files(tmp_path, found="f", units="u", draws="d"):
    if not (tmp_path / "ground.parquet").exists():
        write(tmp_path / "ground.parquet", "g")
    return {
        "hashed": {
            "found": write(tmp_path / "found.pkl", found),
            "units": write(tmp_path / "units.parquet", units),
            "draws": write(tmp_path / "draws.parquet", draws),
        },
        # Stamped by size and time, so written once.
        "stamped": {"ground_map": tmp_path / "ground.parquet"},
    }


def record(tmp_path, settings=None, code=(), **content):
    return gen_wall_zones.built_from(
        **files(tmp_path, **content),
        settings={"scenarios": ["walled", "bare"], "world_ids": [0]}
        if settings is None
        else settings,
        code=code,
    )


def test_the_record_is_the_same_for_the_same_inputs(tmp_path):
    assert record(tmp_path) == record(tmp_path)


@pytest.mark.parametrize(
    "change",
    [{"found": "other"}, {"units": "other"}, {"draws": "other"}],
)
def test_the_record_changes_with_the_found_elements_units_or_draws(tmp_path, change):
    before = record(tmp_path)
    assert record(tmp_path, **change) != before


@pytest.mark.parametrize(
    "settings",
    [
        {"scenarios": ["walled", "bare", "w001"], "world_ids": [0, 1]},
        {"scenarios": ["walled", "bare"], "world_ids": [1]},
    ],
)
def test_the_record_changes_with_the_scenarios_and_worlds(tmp_path, settings):
    assert record(tmp_path, settings=settings) != record(tmp_path)


def one():
    return 1


def two():
    return 2


def test_the_record_changes_with_the_code_that_builds_a_tile(tmp_path):
    assert record(tmp_path, code=(one,)) != record(tmp_path, code=(two,))
    assert record(tmp_path, code=(one,)) == record(tmp_path, code=(one,))


def test_the_code_of_a_tile_is_all_of_what_builds_it():
    names = {item.__name__.rsplit(".", 1)[-1] for item in gen_wall_zones.TILE_CODE}
    assert {"zone_tiles", "tiled", "slope_polygons", "slope_elements"} <= names


def two_polygons():
    """A built result of two polygons, each one evacuated and one imminent cell."""
    cells = pd.DataFrame(
        {
            "polygon": [1, 1, 2, 2],
            "zone": ["evacuated", "imminent", "evacuated", "imminent"],
            "row": [0, 1, 5, 6],
            "col": [0, 0, 5, 5],
            "depth_m": [1.0, None, 2.0, None],
        }
    )
    polygons = pd.DataFrame(
        {
            "element": [10, 20],
            "volume_m3": [1.0, 2.0],
            "area_m2": [1.0, 1.0],
            "imminent_area_m2": [1.0, 1.0],
            "inundated_area_m2": [0.0, 0.0],
            "depth_m": [1.0, 2.0],
        },
        index=pd.RangeIndex(1, 3, name="polygon"),
    )
    empty = pd.DataFrame()
    return SlopePolygons(
        polygons=polygons,
        cells=cells,
        element_links=empty,
        retrogression_links=empty,
        overlaps=empty,
        shape=(10, 10),
        transform=Affine(1.0, 0.0, 0.0, 0.0, -1.0, 10.0),
    )


@pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning")
def test_skipped_elements_are_not_drawn_and_the_others_are_drawn_as_before():
    result = two_polygons()
    every = zone_tiles.zone_polygons(result, scenario="bare")
    kept = zone_tiles.zone_polygons(result, scenario="bare", skip={20})
    expected = every[every["element"] != 20].reset_index(drop=True)
    assert set(kept["element"]) == {10}
    pd.testing.assert_frame_equal(
        pd.DataFrame(kept.drop(columns="geometry")),
        pd.DataFrame(expected.drop(columns="geometry")),
    )
    assert kept.geometry.geom_equals(expected.geometry).all()


@pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning")
def test_with_forced_skips_the_same_elements():
    result = two_polygons()
    forced = gpd.GeoDataFrame({"wall_unit_id": []}, geometry=[], crs=CRS)
    skipped = zone_tiles.with_forced(
        result,
        "bare",
        forced,
        pd.Series(dtype=bool),
        pd.Series(dtype=bool),
        pd.Series(dtype=float),
        None,
        skip={20},
    )
    assert set(skipped["polygon"]) == {1}


@pytest.mark.filterwarnings("ignore:Use `@` matmul:PendingDeprecationWarning")
def test_outlines_kept_between_scenarios_change_no_zone():
    result = two_polygons()
    outlines = {}
    first = zone_tiles.zone_polygons(result, scenario="bare", outlines=outlines)
    again = zone_tiles.zone_polygons(result, scenario="walled", outlines=outlines)
    assert outlines
    assert first.geometry.geom_equals_exact(again.geometry, 0).all()
    assert (again["scenario"] == "walled").all()


def test_a_tiles_scenarios_share_one_dict_and_the_builder_is_put_back(monkeypatch):
    seen = []

    def builder(*args, **kwargs):
        seen.append(kwargs.get("shared"))

    monkeypatch.setattr(tiled, "build_slope_polygons", builder)
    with zone_tiles.sharing_between_scenarios():
        tiled.build_slope_polygons(0)
    # The swapped-in builder is gone, and the next tile gets a dict of its own.
    assert tiled.build_slope_polygons is builder
    with zone_tiles.sharing_between_scenarios():
        tiled.build_slope_polygons(1)
        tiled.build_slope_polygons(2)
    assert seen[1] is seen[2]
    assert seen[1] is not seen[0]


def test_the_code_of_a_tile_includes_the_modules_its_values_come_from():
    names = {item.__name__ for item in gen_wall_zones.TILE_CODE}
    assert {
        "landloss.hazard.landslide.geometry",
        "landloss.hazard.landslide.susceptibility",
        "landloss.hazard.landslide.ground_map",
        "landloss.hazard.landslide.pif_cut_fill",
        "landloss.hazard.landslide.wall_candidates",
        "landloss.hazard.landslide.urban.fragility",
        "landloss.domain.constants",
        "scripts.landloss.ground.steps.s3_instability_zones.grid",
    } <= names


def test_the_settings_of_a_tile_include_the_fill_modification():
    settings = gen_wall_zones.tile_settings(
        extent=EXTENT, scenarios=["walled"], world_ids=[0]
    )
    assert "fill_modification" in settings
    assert settings["extent"] == EXTENT
    assert settings["world_ids"] == [0]


def test_a_half_written_record_clears_the_tiles(work_dir):
    record = {"settings": {"a": 1}}
    gen_wall_zones.keep_or_clear_tiles(extent=EXTENT, record=record, rebuild=False)
    keep(make_tile(0, 0))
    stamp = gen_wall_zones.tiles_dir(extent=EXTENT) / "built-from.json"
    stamp.write_text("", encoding="utf-8")
    cleared = gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=False
    )
    assert cleared == 1
    assert not list(stamp.parent.glob("*.partial"))


def test_the_record_is_written_through_a_temporary_file(work_dir, monkeypatch):
    replaced = []
    real = gen_wall_zones.os.replace
    monkeypatch.setattr(
        gen_wall_zones.os, "replace", lambda a, b: (replaced.append(b), real(a, b))
    )
    gen_wall_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {}}, rebuild=False
    )
    assert [path.name for path in replaced] == ["built-from.json"]


@pytest.mark.parametrize(
    ("rebuild", "use_cached_layers", "expected"),
    [(False, True, False), (True, True, True), (False, False, True)],
)
def test_layers_fetched_again_force_a_rebuild(rebuild, use_cached_layers, expected):
    assert (
        gen_wall_zones.rebuild_wanted(
            rebuild=rebuild, use_cached_layers=use_cached_layers
        )
        is expected
    )


def test_a_tile_is_built_by_the_module_level_builder_the_sharing_swaps():
    # The sharing swaps tiled.build_slope_polygons by name; if zones_tile stops
    # calling it that way the scenarios silently stop sharing.
    assert "build_slope_polygons(" in inspect.getsource(tiled.zones_tile)
    assert "build_slope_polygons" in vars(tiled)


def test_the_sharing_puts_the_builder_back_when_a_tile_fails(monkeypatch):
    def builder(*args, **kwargs):
        return None

    monkeypatch.setattr(tiled, "build_slope_polygons", builder)
    with pytest.raises(RuntimeError), zone_tiles.sharing_between_scenarios():
        raise RuntimeError
    assert tiled.build_slope_polygons is builder


def test_line_elements_are_keyed_by_their_wall_unit_id_as_minted():
    elements = pd.DataFrame(
        {"wall_unit_id": [None, "WU0000219", "WU0000007"]}, index=[1, 2, 3]
    )
    found = SimpleNamespace(elements=elements)

    keys = tiled.line_keys(found, first_new_label=2)

    assert keys == {2: (tiled.LINE, "WU0000219"), 3: (tiled.LINE, "WU0000007")}


def test_line_and_forced_elements_follow_the_grown_ones_in_wall_unit_order():
    grown = (tiled.GROWN, 5)
    keys = [
        (tiled.FORCED, "WU0000003"),
        (tiled.LINE, "WU0000219"),
        grown,
        (tiled.LINE, "WU0000007"),
    ]
    tile = SimpleNamespace(elements=pd.DataFrame({"element_key": keys}))

    labels = tiled.label_keys(SimpleNamespace(labels={grown: 1}), [tile])

    assert labels == {
        grown: 1,
        (tiled.LINE, "WU0000007"): 2,
        (tiled.LINE, "WU0000219"): 3,
        (tiled.FORCED, "WU0000003"): 4,
    }
