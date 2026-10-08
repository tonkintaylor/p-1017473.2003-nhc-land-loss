"""Shared names and rules for the urban failure polygons.

What belongs here: the wall states and zone kinds a polygon carries, the
column names the urban slope modules share, the headscarp band and colluvium
depth the polygon builder (:mod:`landloss.hazard.landslide.slope_polygons`)
reads, and the Kingsbury factors and topographic amplification landslide
step 8 scores a polygon's fragility from. The polygons themselves are step 12's
zones (``s12_urban_slope_faces``); the older candidate reconciliation of
landslide steps 6 and 7 was removed on 2026-10-08.

The rules are the starting points of plan section 7
(``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``),
fixed where that plan gave a range by section 7.6 of the build contract
(``.agents/plans/urban-slope-build-contract.md``). Each is to be researched
and justified in the report; the constants at the top of this module are
where a researched number replaces a starting point.
"""

import math
from collections.abc import Iterable

import numpy as np
import numpy.typing as npt
import pandas as pd

from landloss.domain.constants import (
    TOPOGRAPHIC_AMPLIFICATION_MAX,
)
from landloss.hazard.landslide import susceptibility

# The wall states a polygon can be in, and the three fixed geometries each
# state carries. A state geometry column is named ``<kind>_<state>`` and its
# depth ``depth_<kind>_<state>_m`` (depths for evacuated and inundated only).
WALL_STATES = ("no_wall", "fill_wall", "cut_wall")
GEOMETRY_KINDS = ("evacuated", "inundated", "imminent")
NO_WALL, FILL_WALL, CUT_WALL = WALL_STATES
EVACUATED, INUNDATED, IMMINENT = GEOMETRY_KINDS

# The wall positions a wall line carries, from ``landloss.exposure.rw.lines``.
CUT = "cut"
FILL = "fill"

# The headscarp band above the crest of a failure without a wall: half a metre,
# or a metre on slopes at or over HEADSCARP_STEEP_SLOPE_DEG. Plan section 7
# (T-44) on tension cracks 150 to 200 mm wide behind cut failures
# (sr1995-005-F19, F21), retreat by further small failures over months (F18)
# and crest cracking in the Port Hills (sr2015-016-F19, F20). Both widths are
# placeholders until T-44 is agreed with the project lead.
BETA_HEADSCARP_BAND_M = 0.5
BETA_HEADSCARP_BAND_STEEP_M = 1.0
HEADSCARP_STEEP_SLOPE_DEG = 30.0


# Depth of the ground that leaves a failure without a wall: the thin surface
# layer of colluvium, 1 to 2 m, that Kingsbury puts earthquake-induced
# surficial failures in [kingsbury_1995]. The middle of that range.
COLLUVIUM_DEPTH_M = 1.5


# Kingsbury's existing-landslide factor against the ground map's prior failure
# vocabulary (contract section 7.6).
PRIOR_FAILURE_LANDSLIDE_VALUES = {
    "none": susceptibility.LANDSLIDES_NONE,
    "relict": susceptibility.LANDSLIDES_OLD,
    "recent": susceptibility.LANDSLIDES_ACTIVE,
}

SLOPE_ID_COLUMN = "slope_id"
WALL_LINE_ID_COLUMN = "wall_line_id"
WALL_LINE_IDS_COLUMN = "wall_line_ids"
WALL_POSITION_COLUMN = "wall_position"
REP_POINT_COLUMN = "rep_point"
SCALE_COLUMN = "scale_m"
AREA_COLUMN = "area_m2"
SLOPE_COLUMN = "slope_degrees"
MATERIAL_COLUMN = "material"


def edge_line_ids(value: Iterable[object] | str | float | None) -> tuple[str, ...]:
    """Read one ``wall_line_ids`` cell as a tuple of ids.

    The cell is a list when built and a numpy array once read back from
    parquet; a missing cell is no line.

    Args:
        value: The cell.

    Returns:
        The ids in the cell's order, empty where there are none.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def amplification_factor(
    topographic_position_m: npt.NDArray[np.floating],
    slope_degrees: npt.NDArray[np.floating],
    *,
    max_factor: float = TOPOGRAPHIC_AMPLIFICATION_MAX,
) -> npt.NDArray[np.floating]:
    """Return the topographic amplification factor a fragility median is divided by.

    Contract section 7.6, a placeholder until it is replaced by a factor
    bracketed against sr2019-051-F35. Until then it is
    ``1 + (max_factor - 1) * max(clip(tpi / 10, 0, 1),
    clip((slope - 30) / 30, 0, 1))``, so a crest 10 m or more above its 100 m
    neighbourhood, or a face at 60 degrees, reaches the maximum. A NaN input
    contributes nothing, so a polygon with no position reads no
    amplification from it.

    Args:
        topographic_position_m: The 100 m topographic position, metres above
            the neighbourhood mean.
        slope_degrees: The polygon's slope.
        max_factor: The factor at a crest or a face over 60 degrees.

    Returns:
        The factor, 1.0 to ``max_factor``, the shape of the inputs.
    """
    tpi = np.nan_to_num(np.asarray(topographic_position_m, dtype=float), nan=0.0)
    slope = np.nan_to_num(np.asarray(slope_degrees, dtype=float), nan=0.0)
    crest = np.clip(tpi / 10.0, 0.0, 1.0)
    steep = np.clip((slope - 30.0) / 30.0, 0.0, 1.0)
    return 1.0 + (max_factor - 1.0) * np.maximum(crest, steep)


def kingsbury_factors(polygons: pd.DataFrame) -> dict[str, npt.NDArray[np.floating]]:
    """Score the six Kingsbury factors from a polygon's own attributes.

    Contract section 7.6, for :func:`susceptibility.susceptibility_rating`
    [kingsbury_1995]: slope from ``slope_angle_value(slope_degrees)``;
    modification ``cut_angle_value(slope_degrees)`` where ``modification`` is
    ``cut``, ``SIDLING_FILL_VALUE`` where ``fill``, else 0; height
    ``slope_height_value(face_height_10m, slope_degrees)``; geology the
    ground map's ``geology_value``; landslides from ``prior_failure``;
    groundwater ``groundwater_value(gw_depth_m)``.

    Args:
        polygons: Rows carrying ``slope_degrees``, ``modification``,
            ``face_height_10m``, ``geology_value``, ``prior_failure`` and
            ``gw_depth_m``.

    Returns:
        The six factor arrays, keyed by the rating function's argument names.

    Raises:
        ValueError: If a ``prior_failure`` value is not in the vocabulary.
    """
    slope = polygons[SLOPE_COLUMN].to_numpy(dtype=float)
    modification = polygons["modification"].to_numpy()
    modification_value = np.where(
        modification == CUT,
        susceptibility.cut_angle_value(slope),
        np.where(modification == FILL, susceptibility.SIDLING_FILL_VALUE, 0.0),
    )
    prior = polygons["prior_failure"]
    unknown = set(prior.dropna().unique()) - set(PRIOR_FAILURE_LANDSLIDE_VALUES)
    if unknown:
        msg = (
            f"No landslide class is assigned for prior_failure "
            f"{', '.join(repr(value) for value in sorted(unknown))}. Known: "
            f"{', '.join(repr(value) for value in PRIOR_FAILURE_LANDSLIDE_VALUES)}"
        )
        raise ValueError(msg)
    return {
        "slope": susceptibility.slope_angle_value(slope),
        "modification": modification_value,
        "height": susceptibility.slope_height_value(
            polygons["face_height_10m"].to_numpy(dtype=float), slope
        ),
        "geology": polygons["geology_value"].to_numpy(dtype=float),
        "landslides": prior.map(PRIOR_FAILURE_LANDSLIDE_VALUES).to_numpy(dtype=float),
        "groundwater": susceptibility.groundwater_value(
            polygons["gw_depth_m"].to_numpy(dtype=float)
        ),
    }


def kingsbury_score(
    polygons: pd.DataFrame,
) -> tuple[npt.NDArray[np.floating], pd.Series]:
    """The Kingsbury rating and zone of each polygon [kingsbury_1995].

    Args:
        polygons: Rows carrying what :func:`kingsbury_factors` reads.

    Returns:
        ``(rating, zone)``: the rating, and its zone, 1 (very low) to 5 (very
        high), as an ``Int64`` series on the polygons' index (NA where the
        rating is NaN).
    """
    rating = susceptibility.susceptibility_rating(**kingsbury_factors(polygons))
    zone = pd.Series(
        susceptibility.susceptibility_zone(rating), index=polygons.index
    ).astype("Int64")
    return rating, zone
