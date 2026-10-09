"""Tests for how ground step 3 keeps a tiled run's tiles for a resume."""

from scripts.landloss.ground.steps.s3_instability_zones import (
    gen_instability_zones,
    tiled,
)

EXTENT = "porirua-pilot"


def done_tile(folder):
    """A tile left by an earlier run: its found elements and its record."""
    folder.mkdir(parents=True, exist_ok=True)
    found = folder / "tile-00-00.pkl"
    tiled.write_tile_found("found", found)
    tiled.write_tile_found(None, tiled.tile_record_path(found))
    return found


def test_a_tile_from_the_same_search_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_instability_zones, "WORK_DIR", tmp_path)
    record = {"settings": {"a": 1}}
    gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=False
    )
    found = done_tile(gen_instability_zones.tiles_dir(extent=EXTENT))
    cleared = gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=False
    )
    assert cleared == 0
    assert tiled.read_tile_record(found) is None


def test_a_tile_from_another_search_is_cleared(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_instability_zones, "WORK_DIR", tmp_path)
    gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {"a": 1}}, rebuild=False
    )
    found = done_tile(gen_instability_zones.tiles_dir(extent=EXTENT))
    cleared = gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {"a": 2}}, rebuild=False
    )
    assert cleared == 2
    assert not found.exists()
    assert not tiled.tile_record_path(found).exists()


def test_tiles_with_no_record_of_their_search_are_cleared(tmp_path, monkeypatch):
    # Tiles left by a run before the folder held its record.
    monkeypatch.setattr(gen_instability_zones, "WORK_DIR", tmp_path)
    found = done_tile(gen_instability_zones.tiles_dir(extent=EXTENT))
    cleared = gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record={"settings": {"a": 1}}, rebuild=False
    )
    assert cleared == 2
    assert not found.exists()


def test_rebuild_clears_the_tiles(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_instability_zones, "WORK_DIR", tmp_path)
    record = {"settings": {"a": 1}}
    gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=False
    )
    done_tile(gen_instability_zones.tiles_dir(extent=EXTENT))
    cleared = gen_instability_zones.keep_or_clear_tiles(
        extent=EXTENT, record=record, rebuild=True
    )
    assert cleared == 2


def test_a_killed_write_leaves_no_file(tmp_path):
    path = tmp_path / "tile-00-00.pkl"

    class Unpicklable:
        def __reduce__(self):
            raise RuntimeError

    try:
        tiled.write_tile_found(Unpicklable(), path)
    except RuntimeError:
        pass
    assert not path.exists()
