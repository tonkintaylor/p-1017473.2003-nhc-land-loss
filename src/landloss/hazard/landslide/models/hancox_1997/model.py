"""Model 3: Hancox slope distribution with a Marc total landslide area.

Hancox et al. (1997) constrain where landsliding can occur by magnitude,
epicentral distance and Modified Mercalli intensity. Hancox (2010) gives the
share of earthquake-induced landslides in each slope class. Marc et al. (2016)
sets the event-wide area of landsliding.

This module apportions the Marc total to the modelled part of the Hancox area
affected, weights cells so the failed area follows Hancox's slope-class shares,
then caps each cell at complete coverage.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from landloss.hazard.landslide.calibration.constraints import (
    CalibrationReport,
    calibrate,
    extent_mask,
)
from landloss.hazard.landslide.models.hancox_1997 import relationships


@dataclass(frozen=True)
class HancoxResult:
    """The Hancox coverage and the totals used to build it."""

    coverage: np.ndarray
    event_total_area_km2: float
    eligible_area_km2: float
    study_target_area_km2: float
    report: CalibrationReport


def _broadcast_inputs(
    slope_deg: npt.ArrayLike,
    mm_intensity: npt.ArrayLike,
    site_distance_km: npt.ArrayLike,
    cell_area_km2: npt.ArrayLike,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Broadcast the four cell-wise inputs to one shape."""
    return tuple(
        np.asarray(value, dtype=float)
        for value in np.broadcast_arrays(
            slope_deg, mm_intensity, site_distance_km, cell_area_km2
        )
    )


def run(
    *,
    slope_deg: npt.ArrayLike,
    mm_intensity: npt.ArrayLike,
    site_distance_km: npt.ArrayLike,
    cell_area_km2: npt.ArrayLike,
    mw: float,
    event_total_area_km2: float,
    size_class: str = "small",
    mm_threshold: float = relationships.MM_THRESHOLD_WELLINGTON,
) -> HancoxResult:
    """Build Hancox model coverage on aligned cells.

    The event total is apportioned by the eligible modelled area divided by
    Hancox's mean area affected, capped at the whole event total. Within that
    area, each slope class receives failed area in proportion to
    :data:`relationships.SLOPE_SHARES`.

    Args:
        slope_deg: Slope angle per cell, in degrees.
        mm_intensity: Modified Mercalli intensity per cell.
        site_distance_km: Epicentral distance per cell, in km.
        cell_area_km2: Cell area in km², scalar or per cell.
        mw: Scenario moment magnitude.
        event_total_area_km2: Marc event-wide landslide area, in km².
        size_class: Hancox landslide size class used for the distance envelope.
        mm_threshold: Intensity below which coverage is zero.

    Returns:
        Coverage and its event, eligible-area and study-target totals.

    Raises:
        ValueError: If the event total is negative or a finite cell area is not
            positive.
    """
    if event_total_area_km2 < 0:
        msg = "event total area must not be negative"
        raise ValueError(msg)

    slope, mm, distance, area = _broadcast_inputs(
        slope_deg, mm_intensity, site_distance_km, cell_area_km2
    )
    finite_area = area[np.isfinite(area)]
    if np.any(finite_area <= 0):
        msg = "cell area must be positive"
        raise ValueError(msg)

    valid = (
        np.isfinite(slope) & np.isfinite(mm) & np.isfinite(distance) & np.isfinite(area)
    )
    keep = valid & extent_mask(
        distance,
        mw,
        mm,
        size_class=size_class,
        mm_threshold=mm_threshold,
    )
    eligible_area_km2 = float(area[keep].sum())
    area_affected_km2 = float(relationships.area_affected_km2(mw))
    study_fraction = min(eligible_area_km2 / area_affected_km2, 1.0)
    target_km2 = event_total_area_km2 * study_fraction

    relative = np.full(slope.shape, np.nan, dtype=float)
    relative[valid] = 0.0
    classes = relationships.slope_class(slope)
    for index, name in enumerate(relationships.SLOPE_CLASSES):
        in_class = keep & (classes == index)
        class_area_km2 = float(area[in_class].sum())
        if class_area_km2:
            relative[in_class] = relationships.SLOPE_SHARES[name] / class_area_km2

    coverage, report = calibrate(
        relative,
        area,
        keep,
        mw,
        target_km2,
    )
    return HancoxResult(
        coverage=coverage,
        event_total_area_km2=event_total_area_km2,
        eligible_area_km2=eligible_area_km2,
        study_target_area_km2=target_km2,
        report=report,
    )
