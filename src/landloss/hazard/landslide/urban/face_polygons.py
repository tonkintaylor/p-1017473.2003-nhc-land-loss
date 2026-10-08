"""Landslide step 12's zones of one world, as the polygons step 8 gives a fragility.

What belongs here: turning the evacuated, imminent and inundated zones that
landslide step 12 builds for one exposure world's wall draw
(``gen_urban_slope_wall_zones.py``, one row per polygon and zone) into one row
per polygon in the shape
:func:`landloss.hazard.landslide.urban.fragility.assign_fragility` reads, and
the check that those zones and the walls exposure rw step 6 drew for the same
world come from one draw. Used by landslide step 8
(``s8_urban_slope_fragility``).

The face polygons replaced step 7's polygons (removed 2026-10-08). Step 7 built
every wall state's geometry for each polygon and let step 8 pick one; step 12
has already built each world's zones with the walls that world drew (an
element is walled where its pif belongs to a walled wall unit), so a polygon
carries one geometry per kind, the world's. Its wall is the wall unit its
element's pif belongs to: ``wall_line_id`` is the unit's id (``WU...``), the
id exposure rw step 6 writes as a drawn wall's ``wall_line_id``, and
``wall_line_ids`` lists that one unit, so the fragility join and step 9's
wall groups read the unit as they read a wall line. A polygon whose pif is in
no unit has no wall to draw.

The Kingsbury rating is scored from the polygon's element and the ground map
piece under most of it: the slope is the element's overall angle, the height
the polygon's, and the modification, geology, prior failure and groundwater
the ground map's. An element off the ground map, or on a piece with no
geology, takes :data:`BETA_OFF_MAP_GROUND`.
"""

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.geometry import mean_depth_m
from landloss.hazard.landslide.slope_elements import FREE_FACE
from landloss.hazard.landslide.urban import geometry
from landloss.hazard.landslide.urban.fragility import continuous_rating, sloping_walls

# The columns of step 12's zones file this module reads (one row per polygon
# and zone, ``gen_urban_slope_faces.zone_polygons``).
POLYGON_COLUMN = "polygon"
ZONE_COLUMN = "zone"
ELEMENT_COLUMN = "element"
ELEMENT_TYPE_COLUMN = "element_type"
ZONE_COLUMNS = (
    POLYGON_COLUMN,
    ZONE_COLUMN,
    ELEMENT_COLUMN,
    ELEMENT_TYPE_COLUMN,
    "height_m",
    "area_m2",
    "depth_m",
    "volume_m3",
    "geometry",
)

# The columns of step 12's elements file it reads, indexed by element label.
ELEMENT_COLUMNS = ("siz_id", "majority_ground_row", "overall_angle_deg")

# The columns of step 12's wall units it reads, indexed by ``wall_unit_id``.
UNIT_COLUMNS = ("member_pif_ids", "is_fill")

# The columns of the step 4 ground map it reads, by position.
GROUND_COLUMNS = (
    "material",
    "modification",
    "geology_value",
    "prior_failure",
    "gw_depth_m",
)

# Whether the polygon's element carries a wall in this world's zones.
IS_WALLED_COLUMN = "is_walled"

# Every face polygon is cut from the 1 m grid, so the model's one scale is
# the cell.
FACE_SCALE_M = 1

# The ground an element off the step 4 ground map (or on a piece whose
# material is unknown) is scored on: natural, highly weathered rock (the
# ground map's value for Wellington greywacke), no prior failure, and the
# groundwater depth step 4 assumes off the NLM flat-land footprint, which puts
# hill country in the well drained class. Judgement until the ground map
# covers the whole extent.
BETA_OFF_MAP_GROUND = {
    "material": "rock",
    "modification": "natural",
    "geology_value": susceptibility.GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    "prior_failure": "none",
    "gw_depth_m": 4.0,
}


def _require(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        msg = f"{name} carry no {missing}."
        raise ValueError(msg)


def unit_of_pifs(units: pd.DataFrame) -> pd.Series:
    """Map each pif to the wall unit it is a member of.

    Args:
        units: Step 12's wall units, indexed by ``wall_unit_id``, carrying
            ``member_pif_ids``.

    Returns:
        The ``wall_unit_id`` per pif, indexed by pif id (int64).

    Raises:
        ValueError: If a pif is a member of two units.
    """
    members = pd.DataFrame(
        {
            "pif": units["member_pif_ids"].to_numpy(),
            "wall_unit_id": units.index.to_numpy(dtype=object),
        }
    ).explode("pif")
    members = members.dropna(subset=["pif"])
    pif = members["pif"].astype(np.int64)
    repeated = pif.duplicated()
    if repeated.any():
        msg = f"pifs in two wall units: {pif[repeated].unique()[:5].tolist()}"
        raise ValueError(msg)
    return pd.Series(members["wall_unit_id"].to_numpy(dtype=object), index=pif.values)


def ground_of_elements(
    elements: pd.DataFrame, ground_map: pd.DataFrame
) -> pd.DataFrame:
    """The ground map columns under each element, off-map defaults filled in."""
    rows = elements["majority_ground_row"].to_numpy(dtype=np.int64)
    safe = np.maximum(rows, 0)
    out = {}
    for column, default in BETA_OFF_MAP_GROUND.items():
        values = (
            ground_map[column].to_numpy()[safe]
            if len(ground_map)
            else np.full(len(rows), default, dtype=object)
        )
        on_map = (rows >= 0) if len(ground_map) else np.zeros(len(rows), dtype=bool)
        values = pd.Series(values, index=elements.index, dtype=object)
        # A piece whose material is unknown carries no geology, and takes the
        # off-map ground's.
        out[column] = values.where(on_map & values.notna().to_numpy(), default)
    ground = pd.DataFrame(out, index=elements.index)
    for column in ("geology_value", "gw_depth_m"):
        ground[column] = ground[column].astype(float)
    return ground


def _zone_geometry(zones: gpd.GeoDataFrame, zone: str) -> gpd.GeoSeries:
    rows = zones[zones[ZONE_COLUMN] == zone]
    return gpd.GeoSeries(
        rows.geometry.to_numpy(),
        index=rows[POLYGON_COLUMN].to_numpy(dtype=np.int64),
        crs=zones.crs,
    )


def face_polygons(
    zones: gpd.GeoDataFrame,
    elements: pd.DataFrame,
    units: pd.DataFrame,
    ground_map: pd.DataFrame,
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> gpd.GeoDataFrame:
    """One row per polygon of one world's zones, as the fragility reads it.

    Step 12 grows its elements on a DEM read wider than the extent, so a face
    at the edge grows whole, but the shaking grids stop at the extent. A
    polygon whose representative point lies outside ``bbox`` has no demand to
    read and is left out, before the slope ids are minted.

    Args:
        zones: Step 12's zones of one world (or one scenario), one row per
            polygon and zone, carrying :data:`ZONE_COLUMNS`.
        elements: Step 12's elements, indexed by element label, carrying
            :data:`ELEMENT_COLUMNS`.
        units: Step 12's wall units, indexed by ``wall_unit_id``, carrying
            :data:`UNIT_COLUMNS`.
        ground_map: The step 4 ground map, carrying :data:`GROUND_COLUMNS`,
            in the row order the elements' ``majority_ground_row`` reads.
        bbox: The extent the model runs over, (minx, miny, maxx, maxy) in the
            zones' CRS; None keeps every polygon (the full extent, whose DEM
            stops at the study area).

    Returns:
        One row per polygon inside ``bbox``, sorted by location, with a
        ``slope_id`` minted in that order, the step 12 ``polygon`` and ``element``,
        ``wall_line_id`` (the element's wall unit: its pif's, or, for an
        element built on a GNS-only unit's line, the ``wall_unit_id`` it
        carries; None where it has none), ``wall_line_ids`` (that unit, or
        empty), ``wall_position`` (``fill`` or ``cut`` from the unit's
        ``is_fill``), ``is_walled``, the
        Kingsbury columns, ``scale_m``, ``area_m2``, ``slope_degrees``,
        ``material``, ``modification``, ``face_height_10m`` (the polygon's
        height), ``rep_point``, the ``evacuated``, ``inundated`` and
        ``imminent`` geometries (None where the polygon has no such zone),
        ``depth_evacuated_m``, ``depth_inundated_m`` (the evacuated volume
        over the inundated area) and the evacuated geometry as ``geometry``.
        ``amp_factor`` is added by :func:`with_amplification`.

    Raises:
        ValueError: If an input misses a column, a polygon has no evacuated
            zone, or a pif is a member of two units.
    """
    _require(zones, ZONE_COLUMNS, "The zones")
    _require(elements, ELEMENT_COLUMNS, "The elements")
    _require(units, UNIT_COLUMNS, "The wall units")
    _require(ground_map, GROUND_COLUMNS, "The ground map")

    evacuated_rows = zones[zones[ZONE_COLUMN] == geometry.EVACUATED].set_index(
        POLYGON_COLUMN
    )
    polygons = evacuated_rows.index.to_numpy(dtype=np.int64)
    if len(np.unique(zones[POLYGON_COLUMN])) != len(polygons):
        msg = "Every polygon in the zones needs an evacuated zone."
        raise ValueError(msg)

    element = evacuated_rows[ELEMENT_COLUMN].to_numpy(dtype=np.int64)
    by_element = elements.reindex(element)
    ground = ground_of_elements(
        by_element.assign(
            majority_ground_row=by_element["majority_ground_row"].fillna(-1)
        ),
        ground_map,
    )
    unit = (
        by_element["siz_id"].map(unit_of_pifs(units)).to_numpy(dtype=object)
        if len(units)
        else np.full(len(polygons), None, dtype=object)
    )
    if "wall_unit_id" in by_element.columns:
        # An element on a GNS-only unit's line is that unit's.
        line_unit = by_element["wall_unit_id"].to_numpy(dtype=object)
        unit = np.where(pd.notna(line_unit), line_unit, unit)
    unit = np.array([None if pd.isna(u) else str(u) for u in unit], dtype=object)
    has_unit = unit != None  # noqa: E711
    fill = (
        pd.Series(units["is_fill"].to_numpy(dtype=bool), index=units.index)
        .reindex(unit[has_unit])
        .to_numpy(dtype=bool)
    )
    position = np.full(len(polygons), None, dtype=object)
    position[has_unit] = np.where(fill, geometry.FILL, geometry.CUT)

    evacuated = gpd.GeoSeries(
        evacuated_rows.geometry.to_numpy(), index=polygons, crs=zones.crs
    )
    inundated = _zone_geometry(zones, geometry.INUNDATED).reindex(polygons)
    imminent = _zone_geometry(zones, geometry.IMMINENT).reindex(polygons)
    volume = evacuated_rows["volume_m3"].to_numpy(dtype=float)
    inundated_area = np.where(
        inundated.isna().to_numpy(), 0.0, inundated.area.fillna(0.0).to_numpy()
    )

    frame = gpd.GeoDataFrame(
        {
            POLYGON_COLUMN: polygons,
            ELEMENT_COLUMN: element,
            geometry.WALL_LINE_ID_COLUMN: unit,
            geometry.WALL_LINE_IDS_COLUMN: pd.Series(
                [[u] if u is not None else [] for u in unit], dtype=object
            ).to_numpy(),
            geometry.WALL_POSITION_COLUMN: position,
            IS_WALLED_COLUMN: (
                evacuated_rows[ELEMENT_TYPE_COLUMN].to_numpy() == FREE_FACE
            ),
            geometry.SCALE_COLUMN: np.full(len(polygons), FACE_SCALE_M, dtype=np.int64),
            geometry.AREA_COLUMN: evacuated_rows["area_m2"].to_numpy(dtype=float),
            geometry.SLOPE_COLUMN: by_element["overall_angle_deg"].to_numpy(
                dtype=float
            ),
            "face_height_10m": evacuated_rows["height_m"].to_numpy(dtype=float),
            **{column: ground[column].to_numpy() for column in GROUND_COLUMNS},
            "depth_evacuated_m": evacuated_rows["depth_m"].to_numpy(dtype=float),
            "depth_inundated_m": np.where(
                inundated_area > 0.0,
                mean_depth_m(volume, np.where(inundated_area > 0, inundated_area, 1.0)),
                np.nan,
            ),
            geometry.EVACUATED: evacuated.to_numpy(),
            geometry.INUNDATED: inundated.to_numpy(),
            geometry.IMMINENT: imminent.to_numpy(),
        },
        geometry=evacuated.to_numpy(),
        crs=zones.crs,
    )
    for column in (geometry.EVACUATED, geometry.INUNDATED, geometry.IMMINENT):
        frame[column] = gpd.GeoSeries(frame[column], crs=zones.crs)
    # Object columns, so a polygon with no unit reads None rather than NaN.
    for column, values in (
        (geometry.WALL_LINE_ID_COLUMN, unit),
        (geometry.WALL_POSITION_COLUMN, position),
    ):
        frame[column] = pd.Series(values, index=frame.index, dtype=object)
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        point = frame.geometry.representative_point()
        inside = (
            (point.x >= minx)
            & (point.x <= maxx)
            & (point.y >= miny)
            & (point.y <= maxy)
        )
        frame = frame.loc[inside.to_numpy(dtype=bool)]
    frame = _score(frame)
    frame = sort_by_point(frame)
    frame.insert(
        0,
        geometry.SLOPE_ID_COLUMN,
        mint_ids(constants.SLOPE_ID_PREFIX, len(frame)).to_numpy(),
    )
    frame[geometry.REP_POINT_COLUMN] = gpd.GeoSeries(
        frame.geometry.representative_point(), crs=zones.crs
    )
    return frame


def _score(polygons: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add the Kingsbury rating and zone and the continuous rating."""
    factors = geometry.kingsbury_factors(polygons)
    polygons["kingsbury_rating"], polygons["kingsbury_zone"] = geometry.kingsbury_score(
        polygons
    )
    polygons["continuous_rating"] = continuous_rating(
        slope_degrees=polygons[geometry.SLOPE_COLUMN].to_numpy(dtype=float),
        modification=factors["modification"],
        height=factors["height"],
        geology=factors["geology"],
        landslides=factors["landslides"],
        groundwater=factors["groundwater"],
    )
    return polygons


def with_amplification(
    polygons: gpd.GeoDataFrame, topographic_position_m: npt.ArrayLike
) -> gpd.GeoDataFrame:
    """Add the topographic position and the amplification factor.

    The placeholder factor of
    :func:`landloss.hazard.landslide.urban.geometry.amplification_factor`, on
    the 100 m topographic position at each polygon's representative point
    and the element's slope.

    Args:
        polygons: From :func:`face_polygons`.
        topographic_position_m: The 100 m topographic position at each
            ``rep_point``, in row order; NaN reads no amplification from it.

    Returns:
        A copy with ``topographic_position_100m`` and ``amp_factor``.
    """
    out = polygons.copy()
    out["topographic_position_100m"] = np.asarray(topographic_position_m, dtype=float)
    out["amp_factor"] = geometry.amplification_factor(
        out["topographic_position_100m"].to_numpy(dtype=float),
        out[geometry.SLOPE_COLUMN].to_numpy(dtype=float),
    )
    return out


def check_zones_match_walls(polygons: pd.DataFrame, walls: pd.DataFrame) -> None:
    """Refuse zones and drawn walls that do not come from one wall draw.

    Step 12 builds a world's zones from its wall unit draw and exposure rw
    step 6 writes the walls of the same draw, so a polygon is walled in the
    zones exactly where its unit is among the world's drawn sloping-land
    walls. Where the two disagree, one file is stale (a rerun of step 12's
    wall units, or of rw step 6, without the other) or names other ids (the
    old wall line ids), and the fragility would give walled ground a
    localised median or bare ground a wall curve without an error.

    Args:
        polygons: From :func:`face_polygons`.
        walls: The world's drawn walls (``drawn_walls_path``), carrying
            ``wall_line_id`` and ``is_flatland``.

    Raises:
        ValueError: If a walled polygon's unit is not a drawn wall, a polygon
            whose unit is a drawn wall is not walled, or a walled polygon
            has no unit.
    """
    drawn = set(sloping_walls(walls)[geometry.WALL_LINE_ID_COLUMN].astype(str))
    unit = polygons[geometry.WALL_LINE_ID_COLUMN].to_numpy(dtype=object)
    walled = polygons[IS_WALLED_COLUMN].to_numpy(dtype=bool)
    missing = pd.isna(unit)
    in_drawn = np.array([str(u) in drawn for u in unit], dtype=bool) & ~missing
    no_unit = walled & missing
    walled_not_drawn = walled & ~in_drawn & ~no_unit
    drawn_not_walled = ~walled & in_drawn
    problems = []
    for mask, what in (
        (walled_not_drawn, "walled in the zones but their unit is not a drawn wall"),
        (drawn_not_walled, "bare in the zones but their unit is a drawn wall"),
        (no_unit, "walled in the zones but in no wall unit"),
    ):
        if mask.any():
            examples = sorted({str(u) for u in unit[mask]})[:3]
            problems.append(f"{int(mask.sum()):,} polygons {what} (units {examples})")
    if problems:
        msg = (
            "the zones and the drawn walls are not one wall draw: "
            + "; ".join(problems)
            + ". Rerun step 12's gen_urban_slope_wall_zones.py and exposure rw "
            "step 6's gen_wall_population.py for this world, after the same "
            "gen_urban_slope_wall_units.py run."
        )
        raise ValueError(msg)
