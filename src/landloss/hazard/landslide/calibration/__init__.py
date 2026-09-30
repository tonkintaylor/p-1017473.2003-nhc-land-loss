"""Calibration of the large-landslide models against independent constraints.

Every large-landslide model in the portfolio (models 1, 2, 5 and 7 of
``src/scripts/landloss/hazard/landslide/potential-landslide-rebuild.md``) is
checked two ways: its **amount** of landsliding against Marc et al. (2016)
(:mod:`.marc_2016`), and its **extent** against the Hancox et al. (1997) New
Zealand relationships
(:mod:`landloss.hazard.landslide.models.hancox_1997.relationships`). The
operations that apply them are in :mod:`.constraints`. See
``.agents/plans/building-hancox-landslide-model-and-calibration.md``.
"""

from landloss.hazard.landslide.calibration.constraints import (
    CalibrationReport,
    TransferFunction,
    calibrate,
    extent_mask,
    fit_transfer_function,
    scale_to_total,
)

__all__ = [
    "CalibrationReport",
    "TransferFunction",
    "calibrate",
    "extent_mask",
    "fit_transfer_function",
    "scale_to_total",
]
