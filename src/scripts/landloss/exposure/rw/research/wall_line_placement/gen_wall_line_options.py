"""Redraw the pif wall units' lines along the toe of their pifs.

Research for the lead's question of 2026-10-12. A pif wall unit's line is its
pif's spine (ground step 3, ``instability_zones.gen_pif_spines``): the longest
path through the pips, which are the crest and upper face cells of a step. So
the line sits part way up the face, and inside the evacuated polygon rather
than near its downhill edge.

Option 9, the lead's method (2026-10-12), redraws it along the toe. The pif's
points are its pips and the cell each pip falls to at 1 m, which takes its
pip's fall. A toe point is a point with no pip of the pif within
``config.TOE_ANGLE_DEG`` of its fall and ``config.TOE_LOOK_M`` of it. Every
toe point moves ``config.OFFSET_M`` down its fall, and a line is fitted to the
moved points with the spine's bend count, no bend turning back more than
``config.MAX_BEND_DEG``. Each end is the moved toe point on the lowest ground
(1 m DEM) within ``config.END_SECTOR_DEG`` of the perpendicular to the
spine's end segment, on its downhill side, and ``config.END_REACH_M`` of the
spine's end (the nearest toe point where there is none). ``method`` is
``toe``, ``bend-dropped`` where a bend still turned back too far after the
fit and was dropped, ``breaks`` where the line breaks the wall line rules,
``translated`` where both ends come to the same toe point and the spine is
moved onto it instead, or ``no-toe`` where the pif has no toe point and keeps
its spine. GNS-only units have no pips and keep their line. Options 2 to 8,
compared earlier the same day, are recorded in ``wall_line_placement.md``.

It writes, under ``temp/qgis/wall-line-placement<suffix>/``, the current
lines and option 9's, each carrying what the wall points read off the line
(the boundary and road frontage shares, the primary property, the length)
and how far it moved, the toe points before and after the move, an outline
(concave hull) round each pif's points, the context layers for a QGIS
project (hillshade, pips, 1 m points, ground step 3 elements, the world 0
evacuated zones, property boundaries) and ``summary.csv``, with the time the
lines took.
"""

import math
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from matplotlib.colors import LightSource
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

from landloss.hazard.landslide.bend_split import rule_breaks
from landloss.hazard.landslide.instability_zones import DIRECTIONS
from landloss.hazard.landslide.wall_units import (
    gen_unit_boundary_flags,
    gen_unit_properties,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_property_boundaries
from scripts.landloss.exposure.rw.research.wall_line_placement import config
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    read_sizs,
    wall_draws_path,
    wall_units_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import dem_path
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    CRS,
    dem_bbox,
    elements_path,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.gen_wall_zones import (
    world_scenario,
    zones_path,
)
from scripts.landloss.paths import TEMP_DIR

# A step along each of the eight fall directions as (x, y) in cells: a step
# down the grid's rows is a step south.
STEP_XY = np.array([(dc, -dr) for dr, dc in DIRECTIONS], dtype=float)
CURRENT = "current"
TOE_FIT = "opt9"
HALF_CELL_M = 0.5
SEARCH_MARGIN_M = 1e-6
# Two ends closer than this are the same toe point. An absolute distance:
# NZTM coordinates are in the millions, so a relative tolerance is metres.
SAME_POINT_M = 1e-6
# The fit's penalty on a bend turning back past config.MAX_BEND_DEG, in metres
# of residual per degree over: large beside the toe points' distances, so the
# fit gives the limit first. A bend still over by more than BEND_TOL_DEG after
# the fit is dropped.
BEND_PENALTY_M_PER_DEG = 1.0
BEND_TOL_DEG = 0.5


def main(*, extent, use_cached_layers):
    """Draw the toe lines over the extent and write them with the context.

    Args:
        extent: The build extent.
        use_cached_layers: Whether to reuse the cached LINZ layers.
    """
    directory = out_dir(extent=extent)
    directory.mkdir(parents=True, exist_ok=True)
    sizs = read_sizs(extent=extent)
    sizs["spine"] = gpd.GeoSeries(sizs["spine"], crs=sizs.crs)
    units = gpd.read_parquet(wall_units_path(extent=extent))
    if "wall_unit_id" in units.columns:
        units = units.set_index("wall_unit_id")
    draws = pd.read_parquet(wall_draws_path(extent=extent))
    w0 = draws[draws["world_id"] == 0].set_index("wall_unit_id")["walled"]
    units["walled_w0"] = w0.reindex(units.index).fillna(False).astype(bool)
    pif_of = {
        unit_id: int(ids[0])
        for unit_id, ids in units["member_pif_ids"].items()
        if len(ids)
    }
    units["pif_id"] = pd.Series(pif_of, dtype="Int64")
    units["candidate_class"] = units["pif_id"].map(sizs["candidate_class"]).fillna(
        "gns_only"
    )
    elements = gpd.read_parquet(elements_path(extent=extent))
    element_of = elements.set_index("siz_id").geometry
    element_of = element_of[~element_of.index.duplicated()]
    units["element"] = units["pif_id"].map(element_of)
    print(units["candidate_class"].value_counts().to_string())

    properties = get_nz_property_boundaries(
        bbox=dem_bbox(extent=extent), crs=CRS, use_cache=use_cached_layers
    )
    members = pif_members(units, sizs)
    with rasterio.open(dem_path(1, extent=extent)) as src:
        ground = (src.read(1, masked=True).filled(np.nan).astype(float), src.transform)

    current = units.loc[list(members), ["geometry"]].copy()
    current["method"] = "spine"
    baseline = measure(current, units, properties, units.geometry)
    baseline.to_file(directory / f"lines-{CURRENT}.gpkg", driver="GPKG")
    rows = [summarise(CURRENT, baseline, 0.0, baseline)]
    lines, seconds = draw_lines(units, members, ground)
    measured = measure(lines, units, properties, units.geometry)
    measured.to_file(directory / f"lines-{TOE_FIT}.gpkg", driver="GPKG")
    rows.append(summarise(TOE_FIT, measured, seconds, baseline))
    write_toe_points(directory / f"toe-points-{TOE_FIT}", members)
    print(f"{TOE_FIT}: {len(lines):,} lines in {seconds:.1f} s")

    summary = pd.DataFrame(rows)
    summary.to_csv(directory / "summary.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(summary.round(3).to_string(index=False))
    write_pif_hulls(directory / "pif-hulls.gpkg", sizs, units["pif_id"])
    write_context(directory, extent=extent, sizs=sizs, properties=properties)
    print(f"Written to {directory}")


def out_dir(*, extent):
    """Where the layers and the summary are written."""
    return TEMP_DIR / "qgis" / f"wall-line-placement{extent_suffix(extent)}"


def pif_members(units, sizs):
    """Each pif unit's pips and their fall as unit vectors, keyed by unit id."""
    pif_units = units[units["unit_source"] == "pif"]
    members = {}
    for unit_id, ids in pif_units["member_pif_ids"].items():
        row = sizs.loc[int(ids[0])]
        step = STEP_XY[np.asarray(row["pip_direction"], dtype=int)]
        members[unit_id] = (
            shapely.get_coordinates(row.geometry),
            step / np.hypot(*step.T)[:, None],
        )
    return members


def draw_lines(units, members, ground):
    """The toe line for every pif unit, the method that drew it and the time.

    ``ground`` is the 1 m DEM as ``(heights, transform)``.
    """
    started = time.perf_counter()
    lines, methods = {}, {}
    for unit_id, (pips, fall) in members.items():
        xy, toe_fall = toe_points(pips, fall)
        moved = xy + config.OFFSET_M * toe_fall
        lines[unit_id], methods[unit_id] = toe_fit(
            units.geometry[unit_id], moved, ground_at(moved, ground), fall
        )
    seconds = time.perf_counter() - started
    frame = gpd.GeoDataFrame(
        {"method": pd.Series(methods)},
        geometry=gpd.GeoSeries(lines, crs=units.crs),
    )
    return frame, seconds


def toe_points(pips, fall):
    """The pif's points with no pip of the pif in their own downhill direction.

    The points are the pips and the cell each falls to at 1 m, which takes
    its pip's fall. A pip blocks a point when it lies within
    ``config.TOE_LOOK_M`` of it and within ``config.TOE_ANGLE_DEG`` of its
    fall. Only the point and pip pairs a KD-tree finds within the look
    distance are tested, so the cost grows with the pips near each point
    rather than with the square of the pif's pips; the search reaches
    ``SEARCH_MARGIN_M`` further so a pip at exactly the look distance (common
    on the 1 m grid) is still tested.

    Returns:
        ``(xy, fall)``: each toe point and its fall as a unit vector.
    """
    step = STEP_XY[np.argmax(fall @ (STEP_XY / np.hypot(*STEP_XY.T)[:, None]).T, axis=1)]
    points = np.vstack([pips, pips + step])
    point_fall = np.vstack([fall, fall])
    pairs = cKDTree(points).sparse_distance_matrix(
        cKDTree(pips), config.TOE_LOOK_M + SEARCH_MARGIN_M, output_type="ndarray"
    )
    near, pip = pairs["i"], pairs["j"]
    rel = pips[pip] - points[near]
    gap = np.hypot(rel[:, 0], rel[:, 1])
    along = (rel * point_fall[near]).sum(axis=1)
    hit = (
        (gap > 1e-6)
        & (gap <= config.TOE_LOOK_M)
        & (along >= gap * math.cos(math.radians(config.TOE_ANGLE_DEG)))
    )
    blocked = np.zeros(len(points), dtype=bool)
    blocked[near[hit]] = True
    _, first = np.unique(points[~blocked], axis=0, return_index=True)
    return points[~blocked][first], point_fall[~blocked][first]


def ground_at(xy, ground):
    """The DEM height of the cell each point lies in (NaN off the DEM)."""
    heights, transform = ground
    cols, rows = ~transform * (xy[:, 0], xy[:, 1])
    rows = np.floor(rows).astype(int)
    cols = np.floor(cols).astype(int)
    inside = (rows >= 0) & (rows < heights.shape[0]) & (cols >= 0) & (cols < heights.shape[1])
    z = np.full(len(xy), np.nan)
    z[inside] = heights[rows[inside], cols[inside]]
    return z


def toe_fit(line, toe, toe_z, fall):
    """The line through the moved toe points, between the lowest toe points off the spine's ends.

    Each end is :func:`toe_end` of the spine's end, and the inner vertices
    are seeded at the spine's and fitted by :func:`fit_inner_vertices`. A pif
    with no toe point (its pips face each other within the look distance)
    keeps its spine; where both ends come to the same toe point the spine is
    moved, unchanged, so its nearest point lies on that toe point (the lead,
    2026-10-12).
    """
    if not len(toe):
        return line, "no-toe"
    xy = shapely.get_coordinates(line)
    down = fall.mean(axis=0)
    start = toe_end(xy[0], xy[1], toe, toe_z, down)
    end = toe_end(xy[-1], xy[-2], toe, toe_z, down)
    if np.hypot(*(start - end)) < SAME_POINT_M:
        nearest = shapely.get_coordinates(
            line.interpolate(line.project(shapely.Point(start)))
        )[0]
        return shapely.LineString(xy + (start - nearest)), "translated"
    inner = xy[1:-1]
    vertices = fit_inner_vertices(start, end, inner, toe)
    method = "toe"
    # A bend the fit could not bring within the limit is dropped and the
    # line refitted, the sharpest first, until none turns back too far.
    while len(vertices) > 2 and turns_deg(vertices).max() > config.MAX_BEND_DEG + BEND_TOL_DEG:
        inner = np.delete(inner, int(np.argmax(turns_deg(vertices))), axis=0)
        vertices = fit_inner_vertices(start, end, inner, toe)
        method = "bend-dropped"
    fitted = shapely.LineString(vertices)
    return fitted, "breaks" if breaks(fitted) else method


def toe_end(spine_end, next_vertex, toe, toe_z, down):
    """The moved toe point on the lowest ground off one end of the spine.

    It looks along the perpendicular to the spine's end segment on the
    downhill side (the side the pif's mean fall ``down`` points to), within
    ``config.END_SECTOR_DEG`` either side of it and ``config.END_REACH_M`` of
    the end, and takes the toe point on the lowest ground there; the toe
    point nearest the end where there is none.
    """
    run = next_vertex - spine_end
    normal = np.array([-run[1], run[0]]) / max(np.hypot(*run), 1e-12)
    if normal @ down < 0:
        normal = -normal
    rel = toe - spine_end
    gap = np.hypot(*rel.T)
    seen = (
        (gap <= config.END_REACH_M)
        & (rel @ normal >= gap * math.cos(math.radians(config.END_SECTOR_DEG)))
        & ~np.isnan(toe_z)
    )
    if not seen.any():
        return toe[np.argmin(gap)]
    return toe[seen][np.argmin(toe_z[seen])]


def turns_deg(vertices):
    """How far the line turns at each inner vertex, in degrees (0 straight on)."""
    heading = np.arctan2(*np.diff(vertices, axis=0)[:, ::-1].T)
    return np.degrees(np.abs((np.diff(heading) + math.pi) % (2 * math.pi) - math.pi))


def fit_inner_vertices(start, end, seed, toe):
    """The line from ``start`` to ``end`` whose inner vertices best fit the toe.

    Each inner vertex stays within ``config.MAX_REACH_M`` of its seed: a
    vertex whose segments no toe point is nearest to has no pull on it and
    would otherwise wander off. A bend turning back more than
    ``config.MAX_BEND_DEG`` is penalised by ``BEND_PENALTY_M_PER_DEG`` per
    degree over, as a residual beside the toe points' distances.
    """
    if len(seed) == 0:
        return np.vstack([start, end])

    def gaps(flat):
        vertices = np.vstack([start, flat.reshape(-1, 2), end])
        over = np.maximum(turns_deg(vertices) - config.MAX_BEND_DEG, 0.0)
        return np.concatenate([toe_gaps(toe, vertices), BEND_PENALTY_M_PER_DEG * over])

    fitted = least_squares(
        gaps,
        seed.ravel(),
        loss="soft_l1",
        f_scale=config.FIT_LOSS_SCALE_M,
        bounds=(seed.ravel() - config.MAX_REACH_M, seed.ravel() + config.MAX_REACH_M),
    )
    return np.vstack([start, fitted.x.reshape(-1, 2), end])


def toe_gaps(points, vertices):
    """Each point's distance to the line through ``vertices``."""
    start, end = vertices[:-1], vertices[1:]
    run = end - start
    t = ((points[:, None, :] - start[None]) * run[None]).sum(axis=2) / np.maximum(
        (run**2).sum(axis=1), 1e-12
    )
    nearest = start[None] + np.clip(t, 0.0, 1.0)[..., None] * run[None]
    return np.hypot(*(points[:, None, :] - nearest).transpose(2, 0, 1)).min(axis=1)


def breaks(line):
    """The wall line rules a line breaks (ground step 3's)."""
    return rule_breaks(
        line,
        max_bends=config.WALL_MAX_BENDS,
        min_length_m=config.WALL_MIN_SEGMENT_M,
        max_length_m=config.WALL_MAX_LENGTH_M,
        max_turn_deg=config.MAX_TOTAL_TURN_DEG,
    )


def measure(lines, units, properties, current):
    """What the wall points read off each line, and how far it moved."""
    out = lines.copy()
    out.index.name = "wall_unit_id"
    out["length_m"] = out.length
    out["candidate_class"] = units["candidate_class"].reindex(out.index)
    out["height_m"] = units["height_m"].reindex(out.index)
    out["walled_w0"] = units["walled_w0"].reindex(out.index)
    flags = gen_unit_boundary_flags(out, properties)
    owners = gen_unit_properties(out, properties)
    out = out.join(flags).join(owners[["property_id", "n_properties"]])
    samples = [
        shapely.line_interpolate_point(g, np.linspace(0, 1, 11), normalized=True)
        for g in out.geometry
    ]
    old = current.reindex(out.index)
    out["shift_m"] = [
        float(np.median(shapely.distance(p, o))) for p, o in zip(samples, old, strict=True)
    ]
    element = units["element"].reindex(out.index)
    has = element.notna().to_numpy()
    share = np.full(len(out), np.nan)
    share[has] = shapely.length(
        shapely.intersection(out.geometry.to_numpy()[has], element.to_numpy()[has])
    ) / np.maximum(out.length.to_numpy()[has], 1e-9)
    out["in_element_share"] = share
    return out


def summarise(name, lines, seconds, baseline):
    """One summary row for a set of lines, with the extremes beside the medians."""
    moved = lines["method"].value_counts()
    same_owner = lines["property_id"].fillna("") == baseline["property_id"].reindex(
        lines.index
    ).fillna("")
    ratio = lines["length_m"] / baseline["length_m"].reindex(lines.index)
    return {
        "variant": name,
        "n_lines": len(lines),
        "seconds": round(seconds, 1),
        "methods": "; ".join(f"{k} {v}" for k, v in moved.items()),
        "shift_m_median": lines["shift_m"].median(),
        "shift_m_p90": lines["shift_m"].quantile(0.9),
        "shift_m_max": lines["shift_m"].max(),
        "length_ratio_median": ratio.median(),
        "length_ratio_max": ratio.max(),
        "in_element_share_median": lines["in_element_share"].median(),
        "on_road_frontage": lines["on_road_frontage"].mean(),
        "on_property_boundary": lines["on_property_boundary"].mean(),
        "primary_property_changed": 1.0 - same_owner.mean(),
        "under_5m": (lines["length_m"] < 5.0).mean(),
    }


def write_toe_points(stem, members):
    """The toe points, as found and moved down their fall, as layers."""
    rows = []
    for unit_id, (xy, fall) in members.items():
        toe, toe_fall = toe_points(xy, fall)
        moved = toe + config.OFFSET_M * toe_fall
        rows.append(
            pd.DataFrame(
                {
                    "wall_unit_id": unit_id,
                    "x": toe[:, 0],
                    "y": toe[:, 1],
                    "xm": moved[:, 0],
                    "ym": moved[:, 1],
                }
            )
        )
    toes = pd.concat(rows, ignore_index=True)
    for suffix, (x, y) in {"": ("x", "y"), "-moved": ("xm", "ym")}.items():
        gpd.GeoDataFrame(
            toes[["wall_unit_id"]], geometry=gpd.points_from_xy(toes[x], toes[y]), crs=CRS
        ).to_file(f"{stem}{suffix}.gpkg", driver="GPKG")


def write_pif_hulls(path, sizs, unit_pif):
    """An outline round each pif's points (pips and 1 m points) as a layer.

    Each pif piece split by ground step 3 gets its own outline, carrying its
    parent pif, the wall unit drawn from it, if any, and a colour index that
    differs from every outline it touches, for a QGIS style to tell
    neighbouring pifs apart.
    """
    pifs = sizs[sizs["candidate_class"].isin(["siz", "low_height"])]
    hulls = []
    for row in pifs.itertuples():
        xy = shapely.get_coordinates(row.geometry)
        step = STEP_XY[np.asarray(row.pip_direction, dtype=int)]
        points = shapely.multipoints(np.vstack([xy, xy + step]))
        hulls.append(
            shapely.concave_hull(points, ratio=config.HULL_RATIO).buffer(HALF_CELL_M)
        )
    unit_of = pd.Series(unit_pif.dropna().index, index=unit_pif.dropna().astype(int))
    out = gpd.GeoDataFrame(
        {
            "pif_id": pifs.index,
            "parent_pif_id": pifs["parent_pif_id"].to_numpy(),
            "wall_unit_id": pifs.index.map(unit_of),
            "candidate_class": pifs["candidate_class"].to_numpy(),
            "n_pips": pifs["n_pips"].to_numpy(),
            "colour": colour_touching(np.asarray(hulls)),
        },
        geometry=hulls,
        crs=CRS,
    )
    out.to_file(path, driver="GPKG")
    print(f"Pif outlines written: {len(out):,}")


def colour_touching(polygons):
    """A colour index per polygon, the lowest one no polygon it touches has."""
    left, right = shapely.STRtree(polygons).query(polygons, predicate="intersects")
    touching = [[] for _ in polygons]
    for i, j in zip(left, right, strict=True):
        if i != j:
            touching[i].append(j)
    colour = np.full(len(polygons), -1)
    for i, others in enumerate(touching):
        taken = set(colour[others])
        colour[i] = next(c for c in range(len(polygons)) if c not in taken)
    return colour


def write_context(directory, *, extent, sizs, properties):
    """The layers a QGIS project of the comparison needs beside the lines."""
    with rasterio.open(dem_path(1, extent=extent)) as src:
        z = src.read(1, masked=True).filled(np.nan).astype(float)
        profile = src.profile
    shade = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(z, nan=np.nanmin(z)), vert_exag=2, dx=1.0, dy=1.0
    )
    profile.update(dtype="uint8", nodata=0, count=1, compress="deflate")
    with rasterio.open(directory / "hillshade.tif", "w", **profile) as dst:
        dst.write(np.where(np.isnan(z), 0, 1 + shade * 254).astype("uint8"), 1)

    pip_rows = []
    for pif_id, row in sizs[sizs["candidate_class"].isin(["siz", "low_height"])].iterrows():
        xy = shapely.get_coordinates(row.geometry)
        step = STEP_XY[np.asarray(row["pip_direction"], dtype=int)]
        pip_rows.append(
            pd.DataFrame(
                {
                    "pif_id": pif_id,
                    "x": xy[:, 0],
                    "y": xy[:, 1],
                    "x1": xy[:, 0] + step[:, 0],
                    "y1": xy[:, 1] + step[:, 1],
                }
            )
        )
    pips = pd.concat(pip_rows, ignore_index=True)
    for name, (x, y) in {"pips": ("x", "y"), "points-1m": ("x1", "y1")}.items():
        gpd.GeoDataFrame(
            pips[["pif_id"]], geometry=gpd.points_from_xy(pips[x], pips[y]), crs=CRS
        ).to_file(directory / f"{name}.gpkg", driver="GPKG")

    elements = gpd.read_parquet(elements_path(extent=extent))
    elements[["siz_id", "grown_in", "height_m", "run_m", "geometry"]].to_file(
        directory / "elements.gpkg", driver="GPKG"
    )
    zones = gpd.read_parquet(zones_path(world_scenario(0), extent=extent))
    zones = zones[zones["zone"] == "evacuated"]
    zones[["polygon", "element", "forced", "height_m", "geometry"]].to_file(
        directory / "evacuated-w000.gpkg", driver="GPKG"
    )
    gpd.GeoDataFrame(
        geometry=shapely.boundary(properties.geometry.to_numpy()), crs=properties.crs
    ).to_file(directory / "property-boundaries.gpkg", driver="GPKG")
    print(f"Context written: {len(pips):,} pips")


if __name__ == "__main__":
    main(extent=config.EXTENT, use_cached_layers=config.USE_CACHED_LAYERS)
