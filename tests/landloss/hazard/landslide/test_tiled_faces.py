"""Tests for how ground step 3's tiles agree on which pifs are whose."""

import geopandas as gpd
import pandas as pd
import pytest
import shapely
from rasterio import windows
from rasterio.transform import Affine

from landloss.common.utils import tiles
from landloss.domain import constants
from scripts.landloss.ground.steps.s3_instability_zones import tiled


def pifs(parents, pips):
    """A siz table of pifs, each a MultiPoint of its pips."""
    return gpd.GeoDataFrame(
        {"parent_pif_id": parents},
        geometry=[shapely.MultiPoint(points) for points in pips],
        index=pd.RangeIndex(1, len(parents) + 1, name="pif_id"),
        crs=constants.DEFAULT_CRS,
    )


def test_a_pif_seen_from_two_tiles_has_one_key():
    # The same pips, read off two tiles whose arithmetic differs in the last
    # place, and listed in another order.
    one = pifs([1], [[(100.5, 200.5), (101.5, 200.5), (102.5, 201.5)]])
    other = pifs([7], [[(102.5 + 1e-9, 201.5), (100.5, 200.5 - 1e-9), (101.5, 200.5)]])
    assert tiled.pip_keys(one).iloc[0] == tiled.pip_keys(other).iloc[0]


def test_a_cut_short_pif_does_not_match_the_whole_one():
    whole = pifs([1], [[(100.5, 200.5), (101.5, 200.5), (102.5, 201.5)]])
    cut = pifs([1], [[(100.5, 200.5), (101.5, 200.5)]])
    assert tiled.pip_keys(whole).iloc[0] != tiled.pip_keys(cut).iloc[0]


def test_a_parent_belongs_by_the_centre_of_all_its_pieces():
    # Parent 1's two pieces straddle x = 1000; their pips' centre is at 1001,
    # so the tile east of 1000 owns both, and the west tile owns neither.
    table = pifs(
        [1, 1, 2],
        [
            [(996.5, 50.5), (998.5, 50.5)],
            [(1003.5, 50.5), (1005.5, 50.5)],
            [(900.5, 50.5), (902.5, 50.5)],
        ],
    )
    west = (0.0, 0.0, 1000.0, 100.0)
    east = (1000.0, 0.0, 2000.0, 100.0)
    assert tiled.owned_parents(table, west) == {2}
    assert tiled.owned_parents(table, east) == {1}


@pytest.mark.parametrize("include_empty_tile", [False, True])
def test_a_pif_two_tiles_both_claim_is_kept_once(include_empty_tile):
    # A parent longer than the margin: each tile's cut of it centres in that
    # tile's own core, so both claim the piece they share.
    shared = [(100.5, 50.5), (101.5, 50.5)]
    records = []
    for col, (parent_pips, core) in enumerate(
        [
            ([shared, [(90.5, 50.5)]], (0.0, 0.0, 101.0, 100.0)),
            ([shared, [(110.5, 50.5)]], (101.0, 0.0, 200.0, 100.0)),
        ]
    ):
        table = pifs([1, 1], parent_pips)
        elements = gpd.GeoDataFrame(
            {"siz_id": [1], "seed_row": [49], "seed_col": [100]},
            geometry=[shapely.box(100, 50, 102, 51)],
            index=pd.Index([1], name="label"),
            crs=constants.DEFAULT_CRS,
        )
        window = windows.Window(0, 0, 200, 100)
        records.append(
            {
                "tile": tiles.Tile(0, col, window, window, core),
                "path": None,
                "table": table,
                "elements": elements,
                "owned": tiled.owned_parents(table, core),
            }
        )
    assert records[0]["owned"] == records[1]["owned"] == {1}

    if include_empty_tile:
        records.append(
            {
                "tile": tiles.Tile(0, 2, window, window, core),
                "path": None,
                "table": pifs([], []),
                "elements": elements.iloc[:0].copy(),
                "owned": set(),
            }
        )

    found, table, elements = tiled.globalise_found(records, Affine(1, 0, 0, 0, -1, 100))

    assert table.index.is_unique
    assert len(table) == 3
    assert elements.index.is_unique
    assert len(elements) == 1
    assert sum(1 in found_tile.owned_pifs for found_tile in found.tiles) == 1
