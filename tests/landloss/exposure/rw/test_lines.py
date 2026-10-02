"""Tests for the candidate wall lines.

A small synthetic neighbourhood, built by hand so every answer can be checked
on paper: four square claim properties in a two by two block with a road along
the south, rasters with constant or half-and-half values, a steep candidate
patch with a gentle neighbour on each side, two mapped walls near a candidate
edge, a cut/fill line, a cut slope and a fill body. The rasters are written to
tmp_path the way test_terrain.py writes its DEMs.
"""

import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import LineString, Point, box

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.exposure.rw import lines as wl
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_lines as script,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; see test_terrain.py.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, so that a raster written to
# tmp_path sits where a Wellington raster would sit rather than at the origin.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0

# The rasters run this far beyond the block on every side, so a boundary on
# the block's edge is still read rather than falling off the raster.
RASTER_MARGIN_M = 50.0
SIZE_M = 300

CRS = constants.DEFAULT_CRS
TOLERANCE_M = 3.0
ROAD_DISTANCE_M = 10.0
MIN_SLOPE_DEG = 5.0
MIN_HEIGHT_M = constants.MIN_WALL_HEIGHT_M

# Everything below y = 48 m (local) has a 0.4 m face: the mapped walls and the
# cut/fill line sit there, the rest of the lines sit above it.
LOW_FACE_BELOW_Y = 48.0
LOW_FACE_M = 0.4
HIGH_FACE_M = 2.0


def make_dem(elevation, resolution: float = 10.0):
    """Wrap an elevation array as a north-up DEM in NZTM."""
    elevation = np.asarray(elevation, dtype=float)
    rows, columns = elevation.shape

    # y descending, which is how a GeoTIFF stores a north-up raster; x ascending.
    eastings = ORIGIN_EASTING + resolution * (np.arange(columns) + 0.5)
    northings = ORIGIN_NORTHING + resolution * (np.arange(rows)[::-1] + 0.5)

    dem = xr.DataArray(
        elevation, dims=("y", "x"), coords={"y": northings, "x": eastings}
    )
    return dem.rio.write_crs(constants.DEFAULT_CRS)


def local(x, y):
    """Move a local coordinate in metres into NZTM."""
    return (ORIGIN_EASTING + x, ORIGIN_NORTHING + y)


def line(*points):
    """Build a line from local coordinates."""
    return LineString([local(x, y) for x, y in points])


def square(x0, y0, x1, y1):
    """Build a box from local coordinates."""
    return box(*local(x0, y0), *local(x1, y1))


def frame(geometries, **columns):
    return gpd.GeoDataFrame(columns, geometry=list(geometries), crs=CRS)


def write_grid(path, value_of, resolution: float = 1.0):
    """Write a raster whose value at each cell centre is value_of(x, y), local."""
    cells = int(SIZE_M / resolution)
    offsets = resolution * (np.arange(cells) + 0.5) - RASTER_MARGIN_M
    x, y = np.meshgrid(offsets, offsets[::-1])
    grid = make_dem(value_of(x, y), resolution).rename(path.stem)
    grid = grid.assign_coords(x=grid.x - RASTER_MARGIN_M, y=grid.y - RASTER_MARGIN_M)
    return write_raster(grid, path)


@pytest.fixture
def rasters(tmp_path):
    """The terrain rasters over the neighbourhood, written to tmp_path."""
    return {
        "face": write_grid(
            tmp_path / "face.tif",
            lambda x, y: np.where(y < LOW_FACE_BELOW_Y, LOW_FACE_M, HIGH_FACE_M),
        ),
        # Fill (positive) in the north half, cut (negative) in the south.
        "residual": write_grid(
            tmp_path / "residual.tif", lambda x, y: np.where(y >= 100.0, 1.0, -1.0)
        ),
        "slope_3m": write_grid(tmp_path / "slope-3m.tif", lambda x, y: 15.0 + 0 * x),
        # Sloping in the west half, flat in the east half.
        "slope_10m": write_grid(
            tmp_path / "slope-10m.tif", lambda x, y: np.where(x < 100.0, 15.0, 2.0)
        ),
        # Downhill to the south everywhere, so uphill is north.
        "aspect": write_grid(tmp_path / "aspect-3m.tif", lambda x, y: 180.0 + 0 * x),
    }


@pytest.fixture
def properties():
    """Four square claim properties: A SW, B SE, C NW, D NE."""
    return frame(
        [
            square(0, 0, 100, 100),
            square(100, 0, 200, 100),
            square(0, 100, 100, 200),
            square(100, 100, 200, 200),
        ],
        claim_id=["A", "B", "C", "D"],
    )


@pytest.fixture
def roads():
    """One road centreline 8 m south of the block."""
    return frame([line((-20, -8), (220, -8))])


@pytest.fixture
def buildings():
    """One building in each property."""
    return frame(
        [
            square(40, 40, 60, 60),
            square(140, 40, 160, 60),
            square(40, 140, 60, 160),
            square(140, 140, 160, 160),
        ]
    )


@pytest.fixture
def candidates():
    """A steep 1 m patch in A between two gentle ones, and a patch in B."""
    return frame(
        [
            square(20, 60, 80, 70),  # the steep face
            square(20, 50, 80, 60),  # the gentle ground below it: the toe
            square(20, 70, 80, 80),  # the gentle ground above it: the crest
            square(120, 20, 160, 40),  # the patch the mapped walls are near
        ],
        scale_m=[1, 1, 1, 1],
        slope_band=["60+", "0-10", "10-20", "20-30"],
        face_height_5m=[3.0, 0.2, 0.3, 1.0],
        aspect_degrees=[180.0, 180.0, 180.0, 180.0],
    )


@pytest.fixture
def morphology():
    """Two mapped walls 2 m and 5 m north of the edge at y = 40, and a cut/fill line."""
    return frame(
        [
            line((125, 42), (155, 42)),
            line((125, 45), (155, 45)),
            line((10, 30), (90, 30)),
        ],
        Type=[wl.MAPPED_WALL_TYPE, wl.MAPPED_WALL_TYPE, wl.CUT_FILL_LINE_TYPE],
    )


@pytest.fixture
def genesis():
    """A cut slope and a fill body in D."""
    return frame(
        [square(110, 110, 190, 150), square(110, 160, 190, 190)],
        Type=["Cut slope", "Fill body"],
    )


@pytest.fixture
def ground_map():
    """Rock cut in the south half, colluvial fill on flat land in the north half."""
    margin = RASTER_MARGIN_M
    return frame(
        [
            square(-margin, -margin, 200 + margin, 100),
            square(-margin, 100, 200 + margin, 200 + margin),
        ],
        ground_id=["GM0000001", "GM0000002"],
        material=["rock", "colluvium"],
        modification=["cut", "fill"],
        is_flatland=[False, True],
    )


def build(rasters, **layers):
    return wl.build_wall_lines(
        **layers,
        face_height_path=rasters["face"],
        residual_path=rasters["residual"],
        slope_3m_path=rasters["slope_3m"],
        slope_10m_path=rasters["slope_10m"],
        aspect_path=rasters["aspect"],
        snap_tolerance_m=TOLERANCE_M,
        road_distance_m=ROAD_DISTANCE_M,
        min_slope_deg=MIN_SLOPE_DEG,
        min_wall_height_m=MIN_HEIGHT_M,
    )


# -- the sources ---------------------------------------------------------------


def test_mapped_walls_and_cut_fill_lines_are_read_by_type(morphology):
    walls = wl.mapped_wall_lines(morphology)
    cut_fill = wl.slide_cut_fill_lines(morphology)
    assert len(walls) == 2
    assert set(walls["source"]) == {"gns_mapped_wall"}
    assert len(cut_fill) == 1
    assert set(cut_fill["source"]) == {"slide_cut_fill_line"}


def test_source_functions_refuse_a_frame_without_type(morphology):
    with pytest.raises(ValueError, match="Type"):
        wl.mapped_wall_lines(morphology.drop(columns="Type"))


def test_genesis_edges_are_the_polygon_boundaries(genesis):
    edges = wl.genesis_edge_lines(genesis)
    assert edges["source"].tolist() == ["slide_cut_edge", "slide_fill_edge"]
    assert edges.geometry.iloc[0].length == pytest.approx(2 * (80 + 40))
    assert edges.geometry.iloc[1].length == pytest.approx(2 * (80 + 30))


def test_terrain_break_is_the_toe_of_the_steep_patch_only(candidates):
    breaks = wl.terrain_break_lines(
        candidates,
        steep_deg=wl.TERRAIN_BREAK_STEEP_DEG,
        gentle_deg=wl.TERRAIN_BREAK_GENTLE_DEG,
        min_face_height_m=MIN_HEIGHT_M,
    )
    assert len(breaks) == 1
    assert breaks["source"].iloc[0] == "terrain_break"
    toe = breaks.geometry.iloc[0]
    assert toe.length == pytest.approx(60.0)
    assert {round(y - ORIGIN_NORTHING, 6) for _, y in toe.coords} == {60.0}


def test_terrain_break_needs_the_face_height(candidates):
    short = candidates.assign(face_height_5m=[0.3, 0.2, 0.3, 1.0])
    breaks = wl.terrain_break_lines(
        short, steep_deg=45.0, gentle_deg=20.0, min_face_height_m=MIN_HEIGHT_M
    )
    assert breaks.empty


def test_band_bounds_refuse_an_unreadable_label():
    with pytest.raises(ValueError, match="slope band label"):
        wl.terrain_break_lines(
            frame(
                [square(0, 0, 1, 1)],
                slope_band=["steep"],
                face_height_5m=[1.0],
                aspect_degrees=[0.0],
            ),
            steep_deg=45.0,
            gentle_deg=20.0,
            min_face_height_m=0.5,
        )


@ignore_affine_matmul
def test_boundary_lines_split_road_frontage_from_boundary_on_sloping_ground(
    properties, roads, rasters
):
    boundaries = wl.boundary_lines(
        properties,
        roads,
        road_distance_m=ROAD_DISTANCE_M,
        slope_path=rasters["slope_10m"],
        min_slope_deg=MIN_SLOPE_DEG,
    )
    midpoints = boundaries.geometry.interpolate(0.5, normalized=True)
    # The east half reads 2 degrees on the 10 m slope, so nothing is kept there.
    assert (midpoints.x - ORIGIN_EASTING < 100.0).all()
    frontages = boundaries[boundaries["source"] == "road_frontage"]
    others = boundaries[boundaries["source"] == "property_boundary"]
    assert len(frontages) == 1
    assert frontages.geometry.iloc[0].interpolate(0.5, normalized=True).y == (
        pytest.approx(ORIGIN_NORTHING)
    )
    assert not others.empty
    assert (others.geometry.interpolate(0.5, normalized=True).y > ORIGIN_NORTHING).all()


# -- the snap, the collapse and the split ------------------------------------


def test_mapped_wall_snaps_onto_an_edge_2m_away_and_not_one_5m_away(
    morphology, candidates
):
    walls = wl.mapped_wall_lines(morphology)
    snapped = wl.snap_to_candidate_edges(walls, candidates, tolerance_m=TOLERANCE_M)
    near = snapped.geometry.iloc[0]
    far = snapped.geometry.iloc[1]
    assert {round(y - ORIGIN_NORTHING, 6) for _, y in near.coords} == {40.0}
    assert far.equals(walls.geometry.iloc[1])
    assert snapped["source"].tolist() == walls["source"].tolist()


def test_collapse_keeps_the_highest_precedence_line_and_marks_mapped():
    lines = frame(
        [
            line((0, 10), (50, 10)),  # a property boundary
            line((0, 11), (50, 11)),  # a mapped wall 1 m from it
            line((0, 50), (50, 50)),  # a terrain break
            line((0, 52), (50, 52)),  # a property boundary 2 m from it
            line((100, 10), (150, 10)),  # a lone cut edge
        ],
        source=[
            "property_boundary",
            "gns_mapped_wall",
            "terrain_break",
            "property_boundary",
            "slide_cut_edge",
        ],
    )
    collapsed = wl.collapse_coincident(lines, tolerance_m=TOLERANCE_M)
    assert collapsed["source"].tolist() == [
        "gns_mapped_wall",
        "slide_cut_edge",
        "terrain_break",
    ]
    assert collapsed["is_mapped_wall"].tolist() == [True, False, False]
    assert collapsed.index.tolist() == [0, 1, 2]


def test_collapse_does_not_merge_a_long_line_into_a_short_one():
    lines = frame(
        [line((0, 0), (10, 0)), line((0, 1), (100, 1))],
        source=["gns_mapped_wall", "property_boundary"],
    )
    collapsed = wl.collapse_coincident(lines, tolerance_m=TOLERANCE_M)
    assert len(collapsed) == 2


def test_collapse_refuses_an_unknown_source():
    lines = frame([line((0, 0), (1, 0))], source=["driveway_edge"])
    with pytest.raises(ValueError, match="driveway_edge"):
        wl.collapse_coincident(lines, tolerance_m=TOLERANCE_M)


def test_line_crossing_a_boundary_splits_in_two(properties):
    lines = frame(
        [
            line((50, 50), (150, 50)),  # crosses x = 100 between A and B
            line((100, 20), (100, 80)),  # lies along that boundary
            line((10, 20), (40, 20)),  # inside A
        ],
        source=["terrain_break", "property_boundary", "slide_cut_edge"],
    )
    split = wl.split_at_boundaries(lines, properties)
    assert len(split) == 4
    assert split["source"].tolist() == [
        "terrain_break",
        "terrain_break",
        "property_boundary",
        "slide_cut_edge",
    ]
    pieces = split.geometry.iloc[:2]
    assert pieces.length.tolist() == pytest.approx([50.0, 50.0])
    assert split.geometry.iloc[2].equals(lines.geometry.iloc[1])


# -- the attributes -----------------------------------------------------------


@ignore_affine_matmul
def test_face_height_is_the_median_along_the_line(rasters):
    # 20 m at 0.4 m then 10 m at 2.0 m: 21 samples, median in the low strip.
    lines = gpd.GeoSeries([line((10, 28), (10, 58)), line((10, 60), (10, 70))], crs=CRS)
    face = wl.face_height_m(lines, rasters["face"], spacing_m=1.0)
    assert face.tolist() == pytest.approx([LOW_FACE_M, HIGH_FACE_M])


@ignore_affine_matmul
def test_face_height_of_a_short_line_is_read_at_its_midpoint(rasters):
    lines = gpd.GeoSeries([line((10, 47.9), (10, 48.4))], index=[7], crs=CRS)
    face = wl.face_height_m(lines, rasters["face"], spacing_m=1.0)
    assert face.index.tolist() == [7]
    assert face.iloc[0] == pytest.approx(HIGH_FACE_M)


@ignore_affine_matmul
def test_wall_position_reads_the_residual_uphill(rasters):
    # Downhill is south, so the probe 3 m north of y = 98 reads the fill half.
    lines = gpd.GeoSeries([line((20, 98), (80, 98)), line((20, 50), (80, 50))], crs=CRS)
    aspect = pd.Series([180.0, 180.0])
    position = wl.wall_position(lines, aspect, rasters["residual"], probe_m=3.0)
    assert position.tolist() == ["fill", "cut"]


def test_claim_rule_on_a_boundary_line_for_a_fill_and_a_cut_wall(properties):
    along = line((20, 100), (80, 100))  # the boundary between A (south) and C (north)
    inside = line((10, 20), (40, 20))  # inside A
    road_edge = line((20, 0), (80, 0))  # the frontage of A, road reserve south of it
    lines = frame([along, along, inside, road_edge], source=["property_boundary"] * 4)
    aspect = pd.Series([180.0] * 4)
    claims = wl.assign_claim(
        lines,
        properties,
        wall_position=pd.Series(["fill", "cut", "cut", "cut"]),
        aspect_degrees=aspect,
        tolerance_m=TOLERANCE_M,
    )
    # Uphill is north: the fill wall belongs to C, the cut wall to A.
    assert claims.tolist()[:3] == ["C", "A", "A"]
    assert claims.iloc[3] is None


def test_assign_claim_needs_the_claim_column(properties):
    lines = frame([line((10, 20), (40, 20))], source=["terrain_break"])
    with pytest.raises(ValueError, match="claim_id"):
        wl.assign_claim(
            lines,
            properties.drop(columns="claim_id"),
            wall_position=pd.Series(["cut"]),
            aspect_degrees=pd.Series([180.0]),
            tolerance_m=TOLERANCE_M,
        )


def test_geographic_frames_are_refused(properties):
    lines = frame([line((10, 20), (40, 20))], source=["terrain_break"])
    with pytest.raises(ValueError, match="geographic"):
        wl.split_at_boundaries(
            lines.to_crs("EPSG:4326"), properties.to_crs("EPSG:4326")
        )
    with pytest.raises(ValueError, match="Reproject"):
        wl.split_at_boundaries(lines, properties.to_crs("EPSG:4326"))


# -- the whole chain -----------------------------------------------------------


@ignore_affine_matmul
def test_build_wall_lines_carries_the_contract_columns(
    rasters, morphology, genesis, properties, roads, buildings, candidates, ground_map
):
    built = build(
        rasters,
        morphology=morphology,
        genesis=genesis,
        properties=properties,
        roads=roads,
        buildings=buildings,
        candidates=candidates,
        ground_map=ground_map,
    )
    assert built.columns.tolist() == list(wl.COLUMNS)
    assert built.index.tolist() == list(range(len(built)))
    assert built.crs == CRS
    assert built["is_mapped_wall"].dtype == bool
    assert built["is_flatland"].dtype == bool
    assert built["is_rock_cut"].dtype == bool
    assert str(built["dwelling_age_decade"].dtype) == "Int64"
    assert built["dwelling_age_decade"].isna().all()
    assert set(built["wall_position"]) <= set(wl.WALL_POSITIONS)
    assert set(built["size_class"]) <= {"small", "medium", "large"}
    assert set(built["source"]) <= set(wl.SOURCES)
    assert (built["length_m"].to_numpy() == built.geometry.length.to_numpy()).all()
    assert (built.geometry.geom_type == "LineString").all()


@ignore_affine_matmul
def test_a_short_face_is_dropped_unless_a_wall_is_mapped(
    rasters, morphology, genesis, properties, roads, buildings, candidates, ground_map
):
    built = build(
        rasters,
        morphology=morphology,
        genesis=genesis,
        properties=properties,
        roads=roads,
        buildings=buildings,
        candidates=candidates,
        ground_map=ground_map,
    )
    short = built[built["face_height_m"] < MIN_HEIGHT_M]
    # The two mapped walls sit in the 0.4 m strip and are the only short lines kept.
    assert len(short) == 2
    assert short["is_mapped_wall"].all()
    assert set(short["source"]) == {"gns_mapped_wall"}
    assert set(short["size_class"]) == {"small"}
    # The cut/fill line sits in the same strip and is not mapped, so it is gone.
    assert "slide_cut_fill_line" not in set(built["source"])
    # The road frontages lie on y = 0, inside the strip, so none survives.
    assert "road_frontage" not in set(built["source"])


@ignore_affine_matmul
def test_build_wall_lines_attributes_each_line_from_its_ground(
    rasters, morphology, genesis, properties, roads, buildings, candidates, ground_map
):
    built = build(
        rasters,
        morphology=morphology,
        genesis=genesis,
        properties=properties,
        roads=roads,
        buildings=buildings,
        candidates=candidates,
        ground_map=ground_map,
    )
    south = built[
        built.geometry.interpolate(0.5, normalized=True).y < ORIGIN_NORTHING + 100
    ]
    north = built[
        built.geometry.interpolate(0.5, normalized=True).y > ORIGIN_NORTHING + 100
    ]
    assert not south.empty
    assert not north.empty
    assert (south["material"] == "rock").all()
    assert south["is_rock_cut"].all()
    assert (~south["is_flatland"]).all()
    assert (south["wall_position"] == "cut").all()
    assert (north["material"] == "colluvium").all()
    assert (~north["is_rock_cut"]).all()
    assert north["is_flatland"].all()
    assert (north["wall_position"] == "fill").all()
    # The genesis edges in D are split at nothing and belong to D.
    assert set(built.loc[built["source"] == "slide_cut_edge", "claim_id"]) == {"D"}
    assert (built["slope_degrees"] == 15.0).all()
    assert (built["aspect_degrees"] == 180.0).all()
    # A mapped wall in B keeps B; the terrain break in A keeps A.
    assert set(built.loc[built["is_mapped_wall"], "claim_id"]) == {"B"}
    assert set(built.loc[built["source"] == "terrain_break", "claim_id"]) == {"A"}


@ignore_affine_matmul
def test_wall_lines_file_carries_the_contract_columns_with_minted_ids(
    tmp_path,
    rasters,
    morphology,
    genesis,
    properties,
    roads,
    buildings,
    candidates,
    ground_map,
):
    built = build(
        rasters,
        morphology=morphology,
        genesis=genesis,
        properties=properties,
        roads=roads,
        buildings=buildings,
        candidates=candidates,
        ground_map=ground_map,
    )
    # The tail of gen_wall_lines.py: sort by location, mint, write.
    ordered = sort_by_point(built)
    ordered.insert(
        0,
        "wall_line_id",
        mint_ids(constants.WALL_LINE_ID_PREFIX, len(ordered)).to_numpy(),
    )
    out_path = tmp_path / "wall-lines-pilot.geoparquet"
    ordered.to_parquet(out_path)

    read = gpd.read_parquet(out_path)
    assert read.columns.tolist() == ["wall_line_id", *wl.COLUMNS]
    assert read["wall_line_id"].is_unique
    assert all(re.fullmatch(r"WL\d{7}", value) for value in read["wall_line_id"])
    assert read["wall_line_id"].iloc[0] == "WL0000001"
    assert str(read["dwelling_age_decade"].dtype) == "Int64"
    assert read.crs == CRS


@ignore_affine_matmul
def test_build_wall_lines_on_no_sources_is_empty_with_the_columns(
    rasters, properties, roads, buildings, candidates, ground_map
):
    built = build(
        rasters,
        morphology=frame([], Type=[]),
        genesis=frame([], Type=[]),
        properties=properties.iloc[0:0],
        roads=roads,
        buildings=buildings,
        candidates=candidates.iloc[0:0],
        ground_map=ground_map,
    )
    assert built.empty
    assert built.columns.tolist() == list(wl.COLUMNS)


# -- the script ----------------------------------------------------------------


@pytest.fixture
def redirected_script(
    tmp_path,
    monkeypatch,
    rasters,
    morphology,
    genesis,
    properties,
    roads,
    buildings,
    candidates,
    ground_map,
):
    """Point every read of gen_wall_lines.py at the synthetic inputs.

    The extent is left to the test, because what the script keeps depends on
    it.
    """
    boundaries = properties.assign(source="Rating unit", source_id=[1, 2, 3, 4]).drop(
        columns="claim_id"
    )
    # The claim id build_claim_properties mints is the source id.
    candidates.to_parquet(tmp_path / "candidates.geoparquet")
    ground_map.to_parquet(tmp_path / "ground-map.geoparquet")

    monkeypatch.setattr(script, "WORK_DIR", tmp_path / "exposure")
    monkeypatch.setattr(script, "get_gns_slide_morphology", lambda **_: morphology)
    monkeypatch.setattr(script, "get_slide_genesis", lambda **_: genesis)
    monkeypatch.setattr(script, "get_nz_property_boundaries", lambda **_: boundaries)
    monkeypatch.setattr(script, "get_nz_building_outlines", lambda **_: buildings)
    monkeypatch.setattr(script, "get_nz_address_roads", lambda **_: roads)
    monkeypatch.setattr(
        script,
        "urban_slope_candidates_path",
        lambda *, pilot: tmp_path / "candidates.geoparquet",
    )
    monkeypatch.setattr(
        script, "ground_map_path", lambda *, pilot: tmp_path / "ground-map.geoparquet"
    )
    monkeypatch.setattr(
        script,
        "terrain_path",
        lambda layer, *, pilot: {
            "face-height-5m": rasters["face"],
            "cut-fill-residual-30m": rasters["residual"],
        }[layer],
    )
    monkeypatch.setattr(
        script,
        "slope_path",
        lambda resolution_m, *, pilot: {
            3: rasters["slope_3m"],
            10: rasters["slope_10m"],
        }[resolution_m],
    )
    monkeypatch.setattr(
        script, "aspect_path", lambda resolution_m, *, pilot: rasters["aspect"]
    )
    return script


def extent_of(x0, y0, x1, y1):
    """Build a resolve_extent stand-in returning a local box as the extent."""
    return lambda *, pilot: ((*local(x0, y0), *local(x1, y1)), "test")


@ignore_affine_matmul
def test_gen_wall_lines_main_writes_the_file(tmp_path, monkeypatch, redirected_script):
    """Run the step's main() over the whole block, every read redirected."""
    monkeypatch.setattr(script, "resolve_extent", extent_of(0, 0, 200, 200))

    script.main(pilot=True, use_cached_layers=True, road_distance_m=ROAD_DISTANCE_M)

    out_path = script.wall_lines_path(pilot=True)
    assert out_path == tmp_path / "exposure" / "wall-lines-pilot.geoparquet"
    written = gpd.read_parquet(out_path)
    assert written.columns.tolist() == ["wall_line_id", *wl.COLUMNS]
    assert written["wall_line_id"].iloc[0] == "WL0000001"
    assert not written.empty
    # The mapped walls in B have a 0.4 m face and survive on the exemption.
    assert (written["source"] == "gns_mapped_wall").sum() == 2


@ignore_affine_matmul
def test_gen_wall_lines_main_drops_the_lines_in_the_margin(
    monkeypatch, redirected_script
):
    """An extent over the west half alone keeps no line whose midpoint is east.

    The mapped walls in B pass the face-height rule on the exemption, so only
    the extent clip can remove them; before it they were written with every
    raster attribute NaN.
    """
    monkeypatch.setattr(script, "resolve_extent", extent_of(0, 0, 100, 200))

    script.main(pilot=True, use_cached_layers=True, road_distance_m=ROAD_DISTANCE_M)

    written = gpd.read_parquet(script.wall_lines_path(pilot=True))
    assert not written.empty
    midpoints = written.geometry.interpolate(0.5, normalized=True)
    assert (midpoints.x - ORIGIN_EASTING <= 100.0).all()
    assert (written["source"] != "gns_mapped_wall").all()
    assert written["wall_line_id"].iloc[0] == "WL0000001"


def test_drop_off_extent_keeps_by_midpoint_and_reindexes():
    lines = frame(
        [
            line((-10, 50), (30, 50)),  # midpoint at x = 10: inside
            line((-60, 50), (-20, 50)),  # midpoint at x = -40: in the margin
            line((50, 190), (50, 230)),  # midpoint at y = 210: in the margin
        ],
        source=["a", "b", "c"],
    )
    kept = script.drop_off_extent(lines, (*local(0, 0), *local(200, 200)))
    assert kept["source"].tolist() == ["a"]
    assert kept.index.tolist() == [0]
    assert script.drop_off_extent(lines.iloc[0:0], (*local(0, 0), *local(1, 1))).empty


def test_midpoint_helper_is_half_way():
    middle = wl._midpoints(gpd.GeoSeries([line((0, 0), (10, 0))], crs=CRS))  # noqa: SLF001
    assert middle.iloc[0].equals(Point(local(5, 0)))
