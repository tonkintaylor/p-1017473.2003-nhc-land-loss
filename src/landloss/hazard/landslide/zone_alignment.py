"""Align the zones of walled elements with their wall units' lines.

Landslide step 4 draws each element's evacuated, imminent and inundated zones
from the grid. Where an element is walled, its evacuated polygons are aligned
with the wall's line (:mod:`landloss.hazard.landslide.wall_trim`, the lead,
2026-10-13). This
module applies that to a scenario's zones frame, after the zones are built (and,
over tiles, stitched), so a wall unit's polygons are seen together whichever tile
built them.

**Which polygons.** The evacuated polygon of a built (not forced) element whose
pif is a member of a wall unit that is walled in the scenario. Not aligned:

- Line elements (``siz_id`` 0, the GNS-only and low-height units, which have no
  pips and so no fall) and forced polygons, which are drawn from the unit's line
  already.
- An element grown from a pif piece with no wall: it is in no unit, so it is
  not walled and its polygons stay as built.
- A unit with no pif in the siz table (no fall).

**Imminent and inundated zones** are otherwise left as built (the lead,
2026-10-13), with one exception: a polygon's imminent zone never overlaps its
own evacuated polygon. The imminent band is drawn with the zones, against the
evacuated outline as built; the alignment comes after it and can grow the
evacuated polygon into its own band, so each aligned polygon's new evacuated
ground is taken out of its imminent zone, and an imminent zone left with no area
is dropped (the lead, 2026-10-13). Inundated ground overlaps the evacuated on
purpose (the deposit), so it is not cut.

**Imminent ground touches its own landslide.** Every polygon's imminent zone,
aligned or not, keeps only the pieces that touch its own evacuated polygon; a
piece cut off from it (by the alignment, or left apart by the outline smoothing)
is deleted, and an imminent zone with no piece left is dropped
(:func:`imminent_touching`, the lead, 2026-10-13).

A polygon's volume is unchanged; its area is drawn again by the caller
(``drawn_areas``), so its depth follows the new area.
"""

from collections.abc import Mapping
from typing import Any

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
import shapely

from landloss.hazard.landslide.directions import STEP_XY
from landloss.hazard.landslide.slope_polygons import EVACUATED, IMMINENT
from landloss.hazard.landslide.urban.face_polygons import unit_of_pifs
from landloss.hazard.landslide.wall_trim import (
    WallTrimSettings,
    align_unit,
    mean_fall,
)

FloatArray = npt.NDArray[np.float64]

# What a walled polygon is marked with when its unit has no fall to align by.
HOW_NO_FALL = "no fall"

# The columns written on every zones row; "" and 0 where a polygon is not aligned.
TRIM_COLUMNS = ("wall_trim_how", "wall_trim_removed_m2", "wall_trim_filled_m2")

# An imminent zone with less area than this left, once its polygon's evacuated
# ground is taken out, is dropped (square metres).
MIN_IMMINENT_M2 = 1e-6

# How far a piece of imminent ground may lie from its own evacuated polygon and
# still touch it (metres): room for floating point, not a gap.
IMMINENT_TOUCH_M = 1e-3


def unit_falls(units: pd.DataFrame, directions: pd.Series) -> dict[Any, FloatArray]:
    """The fall of each wall unit: the mean fall of its first pif's pips.

    Args:
        units: The wall units, indexed by ``wall_unit_id``, with
            ``member_pif_ids``.
        directions: The siz table's ``pip_direction`` (one array of direction
            indices per pip), indexed by pif id.

    Returns:
        A unit vector (x, y) per unit that has a pif in ``directions``. A unit
        with no pif (a GNS-only unit) is left out.
    """
    falls: dict[Any, FloatArray] = {}
    for unit_id, members in units["member_pif_ids"].items():
        if members is None:
            continue
        for pif in members:
            steps = directions.get(int(pif))
            if steps is not None and len(steps):
                falls[unit_id] = mean_fall(steps, STEP_XY)
                break
    return falls


def unit_walled(units: pd.DataFrame, *, flags: bool | pd.Series) -> pd.Series:
    """A scenario's walled flag per wall unit.

    Args:
        units: The wall units, indexed by ``wall_unit_id``.
        flags: True for every unit walled, False for none, or a bool per unit
            indexed by ``wall_unit_id`` (a world's draw; a unit missing from it
            is not walled).

    Returns:
        A bool per unit, indexed like ``units``.
    """
    if isinstance(flags, pd.Series):
        return (
            flags.reindex(units.index)
            .astype("boolean")
            .fillna(value=False)
            .astype(bool)
        )
    return pd.Series(bool(flags), index=units.index)


def _elements_unit(elements: pd.DataFrame, units: pd.DataFrame) -> pd.Series:
    """The wall unit of each built element; NaN for a line element or no unit."""
    pif_unit = unit_of_pifs(units)
    element_unit = elements["siz_id"].astype(np.int64).map(pif_unit)
    if "wall_unit_id" in elements.columns:
        element_unit = element_unit.where(elements["wall_unit_id"].isna())
    return element_unit


def align_zones(
    zones: gpd.GeoDataFrame,
    *,
    elements: pd.DataFrame,
    units: gpd.GeoDataFrame,
    flags: bool | pd.Series,
    falls: Mapping[Any, FloatArray],
    settings: WallTrimSettings,
) -> gpd.GeoDataFrame:
    """Align the evacuated polygons of walled elements with their unit's line.

    See the module docstring for which polygons are aligned. Evacuated
    geometries change, and each aligned polygon's imminent zone loses what its
    evacuated polygon now holds (:func:`imminent_outside`). Areas and depths are
    not recomputed here: the caller sets them from the geometry
    (``drawn_areas``).

    Args:
        zones: One scenario's zones, a row per polygon and zone, with
            ``polygon``, ``zone``, ``element`` and ``forced``.
        elements: The scenario's elements, indexed by label, with ``siz_id``
            (and ``wall_unit_id`` where line elements are in it).
        units: The wall units, indexed by ``wall_unit_id``, with the wall's line
            as geometry and ``member_pif_ids``.
        flags: Whether each unit is walled in the scenario (:func:`unit_walled`).
        falls: Each unit's fall as a unit vector (:func:`unit_falls`).
        settings: The trim and fill settings.

    Returns:
        A copy of ``zones`` with the aligned geometries, and the columns
        :data:`TRIM_COLUMNS` (how each aligned polygon was trimmed, and the
        area removed and filled in square metres). A walled polygon whose unit has
        no fall is left as built and marked :data:`HOW_NO_FALL`.
    """
    zones = zones.reset_index(drop=True)
    zones["wall_trim_how"] = ""
    zones["wall_trim_removed_m2"] = 0.0
    zones["wall_trim_filled_m2"] = 0.0
    if zones.empty:
        return zones
    element_unit = _elements_unit(elements, units)
    walled = unit_walled(units, flags=flags)
    zone_unit = zones["element"].map(element_unit)
    unit_is_walled = zone_unit.map(walled).astype("boolean").fillna(value=False)
    candidate = (
        (zones["zone"] == EVACUATED)
        & ~zones["forced"].astype(bool)
        & unit_is_walled.astype(bool)
    ).to_numpy()
    if not candidate.any():
        return zones
    geometry = zones.geometry.to_numpy().copy()
    how = zones["wall_trim_how"].to_numpy(dtype=object).copy()
    removed = zones["wall_trim_removed_m2"].to_numpy().copy()
    filled = zones["wall_trim_filled_m2"].to_numpy().copy()
    rows = np.flatnonzero(candidate)
    by_unit = pd.Series(rows).groupby(zone_unit.to_numpy()[rows])
    for unit_id, unit_rows in by_unit:
        fall = falls.get(unit_id)
        if fall is None:
            how[unit_rows.to_numpy()] = HOW_NO_FALL
            continue
        line = units.geometry.loc[unit_id]
        positions = unit_rows.to_numpy()
        results = align_unit([geometry[i] for i in positions], line, fall, settings)
        for i, result in zip(positions, results, strict=True):
            geometry[i] = result.aligned
            how[i] = result.how
            removed[i] = result.area_removed_m2
            filled[i] = result.area_filled_m2
    zones[zones.geometry.name] = gpd.GeoSeries(
        geometry, crs=zones.crs, index=zones.index
    )
    zones["wall_trim_how"] = how
    zones["wall_trim_removed_m2"] = removed
    zones["wall_trim_filled_m2"] = filled
    changed = (how != "") & (how != HOW_NO_FALL)
    return imminent_outside(zones, polygons=zones.loc[changed, "polygon"])


def imminent_outside(
    zones: gpd.GeoDataFrame, *, polygons: pd.Series
) -> gpd.GeoDataFrame:
    """The zones with each named polygon's imminent zone kept off its evacuated one.

    The imminent band is drawn against the evacuated outline as built; once the
    evacuated polygon is aligned it can reach into its own band. Each named
    polygon's evacuated geometry is taken out of its imminent geometry, and an
    imminent zone left with under :data:`MIN_IMMINENT_M2` is dropped.

    Args:
        zones: One scenario's zones, a row per polygon and zone.
        polygons: The ``polygon`` ids whose evacuated geometry was aligned.

    Returns:
        The zones, with those polygons' imminent geometries cut.
    """
    if polygons.empty:
        return zones
    evacuated = zones[zones["zone"] == EVACUATED].drop_duplicates("polygon")
    evacuated_of = pd.Series(evacuated.geometry.to_numpy(), index=evacuated["polygon"])
    rows = np.flatnonzero(
        ((zones["zone"] == IMMINENT) & zones["polygon"].isin(set(polygons))).to_numpy()
    )
    if not len(rows):
        return zones
    geometry = zones.geometry.to_numpy().copy()
    owners = evacuated_of.reindex(zones["polygon"].to_numpy()[rows]).to_numpy()
    geometry[rows] = shapely.difference(geometry[rows], owners)
    zones[zones.geometry.name] = gpd.GeoSeries(
        geometry, crs=zones.crs, index=zones.index
    )
    gone = rows[shapely.area(geometry[rows]) < MIN_IMMINENT_M2]
    return zones.drop(index=zones.index[gone]).reset_index(drop=True)


def imminent_touching(zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The zones with each imminent zone cut to the pieces touching its own landslide.

    Imminent ground is the ground left standing behind a failure, so it must
    touch that failure's evacuated polygon (the lead, 2026-10-13). Each
    imminent zone is split into its pieces; a piece further than
    :data:`IMMINENT_TOUCH_M` from its own polygon's evacuated geometry is
    deleted, and an imminent zone with no piece left is dropped. Every
    polygon's imminent zone is checked, not only the aligned ones'.

    Args:
        zones: One scenario's zones, a row per polygon and zone.

    Returns:
        The zones, with the imminent geometries cut and the emptied imminent
        rows dropped.
    """
    rows = np.flatnonzero((zones["zone"] == IMMINENT).to_numpy())
    if not len(rows):
        return zones
    evacuated = zones[zones["zone"] == EVACUATED].drop_duplicates("polygon")
    evacuated_of = pd.Series(evacuated.geometry.to_numpy(), index=evacuated["polygon"])
    geometry = zones.geometry.to_numpy().copy()
    pieces = gpd.GeoSeries(geometry[rows], index=rows).explode(index_parts=False)
    owners = evacuated_of.reindex(zones["polygon"].to_numpy()[pieces.index]).to_numpy()
    touching = shapely.dwithin(pieces.to_numpy(), owners, IMMINENT_TOUCH_M)
    if touching.all():
        return zones
    kept = pieces[touching]
    cut = np.setdiff1d(pieces.index[~touching], kept.index)
    trimmed = np.unique(pieces.index[~touching])
    trimmed = trimmed[np.isin(trimmed, kept.index)]
    for row in trimmed:
        geometry[row] = shapely.union_all(kept.loc[[row]].to_numpy())
    zones[zones.geometry.name] = gpd.GeoSeries(
        geometry, crs=zones.crs, index=zones.index
    )
    return zones.drop(index=zones.index[cut]).reset_index(drop=True)
