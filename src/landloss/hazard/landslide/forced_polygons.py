"""The minimum polygon of a wall with no element of its own, drawn from its line.

The lead (2026-10-07): "force all walls to have that minimum polygon even if it
overlaps." A GNS-only or low-height wall candidate gets an element by burning
its line into the cells no other element holds
(:func:`landloss.hazard.landslide.instability_zones.add_line_elements`); where
every cell its line touches is already another element's (a short GNS leftover
2 m from a pif, inside that siz's element), or its line is off the DEM, the
label grid, one label a cell, cannot hold it. Such a candidate's polygon is
drawn here as geometry from its line, so it may overlap other polygons:

- **Evacuated:** the width behind the crest the floor gives every polygon,
  ``max(0.5 H, 1 m)``
  (:func:`landloss.hazard.landslide.slope_polygons.min_evacuated_width_m`),
  on the uphill side of the whole line (:func:`uphill_side`), with ``H`` the
  candidate's height and never under
  :data:`~landloss.domain.constants.MIN_WALL_HEIGHT_M`, as a line element
  takes it. Where the DEM cannot say which side is uphill (off the DEM, or
  level), the band is centred on the line and ``side_unknown`` is set.
- **Depth and volume:** as a line element's
  (:func:`landloss.hazard.landslide.slope_polygons.element_depth_m` with a
  run of 0): walled, the wall's planar slip, ``0.5 H w`` per metre, a mean
  depth of ``0.5 H``; bare, the bank rule, the same slip no deeper than the
  fill thickness on fill, or the cover depth.
- **Imminent:** behind the evacuated band, to where a line from the toe at
  :data:`~landloss.hazard.landslide.slope_polygons.BETA_REPOSE_ANGLE_DEG`
  meets level ground (``H / tan(35)`` behind the line), never narrower than
  the T-45 band of a face this steep (a metre), as the polygon builder gives
  a line element on level ground behind it.
- **Inundated:** in front of the line, to where a line from the crest at the
  cut relation's travel angle for a step
  (:func:`~landloss.hazard.landslide.slope_polygons.reach_ratio` at 90
  degrees, the ground below not read) meets level ground, ``H / (H/L)``,
  as the builder traces
  a line element's runout down a level fall line, with the seismic distance
  of its Kingsbury zone added and held to the builder's caps
  (:func:`~landloss.hazard.landslide.slope_polygons.inundated_length_m`);
  where that strip would carry the volume too deep, it spreads back over the
  evacuated band as the builder's does
  (:func:`~landloss.hazard.landslide.slope_polygons.deposit_overlap_m2`).
- Where the side is unknown, neither the imminent nor the inundated zone is
  drawn.

Step 9's absorb rule handles the overlaps: a failed polygon sharing ground
with a larger failed one is absorbed into it, so the land a forced polygon
shares is counted once in the dissolved totals.
"""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import ArrayLike
from rasterio.transform import Affine

from landloss.domain.constants import MIN_WALL_HEIGHT_M
from landloss.hazard.landslide.slope_elements import BANK, FREE_FACE
from landloss.hazard.landslide.slope_polygons import (
    BETA_REPOSE_ANGLE_DEG,
    EVACUATED,
    IMMINENT,
    INUNDATED,
    _area_depth_m,
    deposit_overlap_m2,
    element_depth_m,
    headscarp_band_width_m,
    inundated_length_m,
    kingsbury_of_polygons,
    min_evacuated_width_m,
    reach_ratio,
    seismic_runout_m,
)

# What a forced polygon's element was grown in.
FORCED = "forced"

# How far either side of the line, in metres, the DEM is read to find the
# uphill side, and the least mean difference, in metres, that decides it.
SIDE_OFFSET_M = 1.5
SIDE_MIN_RISE_M = 0.1


def _dem_at(dem: np.ndarray, transform: Affine, xy: np.ndarray) -> np.ndarray:
    """The DEM at each point, NaN off the grid or on no data."""
    # North-up square cells: the cell a point falls in, by its offset from
    # the grid's corner.
    cols = np.floor((xy[:, 0] - transform.c) / transform.a).astype(np.int64)
    rows = np.floor((xy[:, 1] - transform.f) / transform.e).astype(np.int64)
    height, width = dem.shape
    inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    out = np.full(len(xy), np.nan)
    out[inside] = dem[rows[inside], cols[inside]]
    return out


def uphill_side(line: shapely.LineString, dem: ArrayLike, transform: Affine) -> int:
    """Which side of a line the ground rises on: 1 left, -1 right, 0 unknown.

    The DEM is read :data:`SIDE_OFFSET_M` either side of the line, square to
    it, at points every metre along it; the side whose ground stands higher
    by :data:`SIDE_MIN_RISE_M` or more on the mean is uphill. Off the DEM, or
    on level ground, the side is unknown.
    """
    z = np.asarray(dem, dtype=float)
    points = shapely.get_coordinates(shapely.segmentize(line, 1.0))
    if len(points) < 2:
        return 0
    step = np.gradient(points, axis=0)
    norm = np.hypot(step[:, 0], step[:, 1])
    norm[norm == 0] = np.nan
    left = np.column_stack([-step[:, 1], step[:, 0]]) / norm[:, None]
    rise = _dem_at(z, transform, points + SIDE_OFFSET_M * left) - _dem_at(
        z, transform, points - SIDE_OFFSET_M * left
    )
    if not np.isfinite(rise).any():
        return 0
    mean = float(np.nanmean(rise))
    if abs(mean) < SIDE_MIN_RISE_M:
        return 0
    return 1 if mean > 0 else -1


def _band(line: shapely.LineString, near_m: float, far_m: float, side: int) -> object:
    """The band between ``near_m`` and ``far_m`` from a line, on one side."""
    far = shapely.buffer(line, side * far_m, single_sided=True)
    if near_m <= 0:
        return far
    return shapely.difference(
        far, shapely.buffer(line, side * near_m, single_sided=True)
    )


def gen_forced_elements(
    lines: gpd.GeoSeries,
    height_m: pd.Series,
    *,
    dem: ArrayLike,
    transform: Affine,
    first_label: int,
) -> gpd.GeoDataFrame:
    """One forced element per wall line: its evacuated band and side.

    Args:
        lines: The wall lines, indexed by ``wall_unit_id``.
        height_m: Each line's wall height, indexed like ``lines``.
        dem: The DEM the elements were found on.
        transform: Its affine transform.
        first_label: The element label of the first forced element (the
            labels follow on from the grown and line elements).

    Returns:
        One row per line, indexed by element ``label``, with ``wall_unit_id``,
        ``grown_in`` (:data:`FORCED`), ``siz_id`` (0), ``height_m``,
        ``overall_angle_deg`` (90, a step), ``run_m`` (0), ``width_m``,
        ``length_m``, ``side`` (1 left of the line, -1 right, 0 unknown),
        ``side_unknown`` and the evacuated band as geometry.
    """
    heights = np.fmax(
        height_m.reindex(lines.index).to_numpy(dtype=float), MIN_WALL_HEIGHT_M
    )
    width = min_evacuated_width_m(heights)
    geometry, sides = [], []
    for line, w in zip(lines.to_numpy(), width, strict=True):
        side = uphill_side(line, dem, transform)
        sides.append(side)
        geometry.append(
            shapely.buffer(line, w / 2.0, cap_style="flat")
            if side == 0
            else _band(line, 0.0, w, side)
        )
    sides = np.array(sides, dtype=np.int64)
    return gpd.GeoDataFrame(
        {
            "wall_unit_id": lines.index.to_numpy(dtype=object),
            "grown_in": FORCED,
            "siz_id": np.zeros(len(lines), dtype=np.int64),
            "height_m": heights,
            "overall_angle_deg": 90.0,
            "run_m": 0.0,
            "width_m": width,
            "length_m": shapely.length(lines.to_numpy()),
            "side": sides,
            "side_unknown": sides == 0,
            "line": lines.to_numpy(),
        },
        geometry=geometry,
        crs=lines.crs,
        index=pd.RangeIndex(first_label, first_label + len(lines), name="label"),
    )


def gen_forced_zones(
    forced: gpd.GeoDataFrame,
    walled: pd.Series,
    *,
    is_fill: pd.Series,
    fill_thickness_m: pd.Series,
    ground: pd.DataFrame | None,
    first_polygon: int,
    scenario: str,
) -> gpd.GeoDataFrame:
    """The zones of the forced elements, in the shape of the zones file.

    Args:
        forced: From :func:`gen_forced_elements`.
        walled: Whether each forced element carries a wall, indexed like
            ``forced``.
        is_fill: Whether each is on fill, indexed like ``forced``.
        fill_thickness_m: The fill thickness, NaN where unknown.
        ground: The ground under each, indexed like ``forced``, for its
            Kingsbury zone and so its seismic distance
            (:func:`~landloss.hazard.landslide.slope_polygons.kingsbury_of_polygons`);
            None scores none.
        first_polygon: The polygon number of the first forced polygon (they
            follow on from the scenario's built polygons).
        scenario: The scenario name written on every row.

    Returns:
        One row per forced polygon and zone (evacuated always; imminent and
        inundated where the side is known), with ``polygon``, ``zone``,
        ``element``, ``segment``, ``element_type``, ``is_fill``, ``style``,
        ``width_rule``, ``width_behind_crest_m``, ``width_floored``,
        ``width_realised_m``, ``is_stack``, ``base_height_m``, ``height_m``,
        ``length_m``, ``area_m2``, ``depth_m``, ``volume_m3``,
        ``source_angle_deg``, ``downslope_angle_deg`` (NaN), ``reach_hl``,
        ``kingsbury_rating``, ``kingsbury_zone``, ``seismic_runout_m``,
        ``imminent_width_m``, ``runout_m``, ``imminent_area_m2``,
        ``inundated_area_m2``, ``forced``, ``side_unknown``, ``scenario`` and
        the zone's geometry.
    """
    if forced.empty:
        return gpd.GeoDataFrame(geometry=[], crs=forced.crs)
    flags = walled.reindex(forced.index, fill_value=False).to_numpy(dtype=bool)
    fill = is_fill.reindex(forced.index, fill_value=False).to_numpy(dtype=bool)
    thickness = fill_thickness_m.reindex(forced.index).to_numpy(dtype=float)
    element_type = np.where(flags, FREE_FACE, BANK)
    height = forced["height_m"].to_numpy(dtype=float)
    width = forced["width_m"].to_numpy(dtype=float)
    area = forced.geometry.area.to_numpy()
    depth = element_depth_m(
        element_type,
        height,
        is_fill=fill,
        fill_thickness_m=thickness,
        width_m=width,
        run_m=np.zeros(len(forced)),
    )
    depth = np.where(np.isnan(depth), _area_depth_m(area), depth)
    volume = depth * area
    reach, style = reach_ratio(
        forced["overall_angle_deg"].to_numpy(dtype=float),
        np.full(len(forced), np.nan),
    )
    rating, kingsbury_zone = kingsbury_of_polygons(
        ground,
        forced.index.to_numpy(),
        slope_deg=forced["overall_angle_deg"].to_numpy(dtype=float),
        height_m=height,
        index=forced.index,
    )
    seismic = seismic_runout_m(kingsbury_zone)
    runout = inundated_length_m(
        height / reach,
        height_m=height,
        volume_m3=volume,
        toe_length_m=forced["length_m"].to_numpy(dtype=float),
        downslope_angle_deg=np.full(len(forced), np.nan),
        seismic_m=seismic,
    )
    band = headscarp_band_width_m(np.full(len(forced), 90.0))
    behind = np.fmax(
        height / math.tan(math.radians(BETA_REPOSE_ANGLE_DEG)), width + band
    )

    rows = []
    for k, (label, element) in enumerate(forced.iterrows()):
        common = {
            "polygon": first_polygon + k,
            "element": int(label),
            "segment": 1,
            "element_type": element_type[k],
            "is_fill": bool(fill[k]),
            "style": style[k],
            "width_rule": FORCED,
            "width_behind_crest_m": width[k],
            "width_floored": True,
            "width_realised_m": width[k],
            "is_stack": False,
            "base_height_m": height[k],
            "height_m": height[k],
            "length_m": float(element["length_m"]),
            "area_m2": area[k],
            "depth_m": depth[k],
            "volume_m3": volume[k],
            "source_angle_deg": float(element["overall_angle_deg"]),
            "downslope_angle_deg": np.nan,
            "reach_hl": reach[k],
            "kingsbury_rating": rating[k],
            "kingsbury_zone": kingsbury_zone.iloc[k],
            "seismic_runout_m": seismic[k],
            "imminent_width_m": behind[k] - width[k],
            "runout_m": runout[k],
            "forced": True,
            "side_unknown": bool(element["side_unknown"]),
            "scenario": scenario,
        }
        zones = [(EVACUATED, element.geometry)]
        side = int(element["side"])
        if side != 0:
            line = element["line"]
            zones.append((IMMINENT, _band(line, width[k], behind[k], side)))
            front = _band(line, 0.0, runout[k], -side)
            back = min(
                float(
                    deposit_overlap_m2(
                        volume[k],
                        height_m=height[k],
                        depth_m=depth[k],
                        strip_area_m2=shapely.area(front),
                    )
                )
                / float(element["length_m"]),
                width[k],
            )
            if back > 0:
                front = shapely.union(front, _band(line, 0.0, back, side))
            zones.append((INUNDATED, front))
        areas = {zone: shapely.area(geometry) for zone, geometry in zones}
        for zone, geometry in zones:
            rows.append(
                {
                    **common,
                    "imminent_area_m2": areas.get(IMMINENT, 0.0),
                    "inundated_area_m2": areas.get(INUNDATED, 0.0),
                    "zone": zone,
                    "geometry": geometry,
                }
            )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=forced.crs)
