r"""Landslide depth from area, via the published volume-area relationship.

A landslide's area is what the simulation samples; its **depth** is what decides
how much material has to be moved, and so what the repair costs. The two are
related by the volume-area power law that landslide inventories are routinely
fitted with:

.. math::

    V = \\alpha A^{\\gamma}

so the mean depth over the footprint is

.. math::

    d = V / A = \\alpha A^{\\gamma - 1}

With :math:`\\gamma` near 1.45 the exponent on area is about 0.45, which is the
substance of the relationship: a landslide ten times the area is roughly three
times as deep, not ten times. Depth grows, but far more slowly than area.

:data:`GAMMA` follows Massey et al. (2020) for the Kaikōura inventory, who report
γ ≈ 1.46–1.47 for rotational, translational and compound slides in Pahau terrane
greywacke -- the same Torlesse rock as the Wellington hills.
:data:`ALPHA` is **not** from that study; it is the widely used Guzzetti et al.
(2009) coefficient for a γ of the same order, adopted here so the beta has a
defensible number rather than an invented one. Refitting α to the Kaikōura
greywacke subset is the obvious improvement.

Volume is conserved through the runout: the material that left the source is the
material that lands. So a caller computes the volume once from the **evacuated**
area and divides it by whichever footprint it wants the depth over. In the beta
the runout circle is rebuilt at the source radius, so the two areas are equal
and the two depths come out identical; that is a property of the beta's
geometry, not a bug.
"""

import numpy as np

# Massey et al. (2020), Kaikoura landslide volumes:
# https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2019JF005163
GAMMA = 1.46

# Guzzetti et al. (2009). Adopted as a placeholder because Massey's alpha is not
# to hand; it sets the absolute scale of every depth this module returns, so it
# is the first number to replace when the Kaikoura fit is available.
ALPHA = 0.074


def landslide_volume_m3(
    area_m2: np.ndarray | float,
    *,
    alpha: float = ALPHA,
    gamma: float = GAMMA,
) -> np.ndarray | float:
    """Return the volume of a landslide from its source area.

    Args:
        area_m2: The evacuated (source) area, in square metres.
        alpha: The coefficient of the volume-area power law.
        gamma: The exponent of the volume-area power law.

    Returns:
        Volume in cubic metres, the same shape as ``area_m2``.

    Raises:
        ValueError: If any area is negative.
    """
    areas = np.asarray(area_m2, dtype=float)
    if np.any(areas < 0):
        msg = "area_m2 must not be negative"
        raise ValueError(msg)
    return alpha * areas**gamma


def mean_depth_m(
    volume_m3: np.ndarray | float,
    footprint_m2: np.ndarray | float,
) -> np.ndarray | float:
    """Return the mean depth of a volume spread over a footprint.

    Args:
        volume_m3: The volume of material, from :func:`landslide_volume_m3`.
        footprint_m2: The area it is spread over -- the evacuated area for the
            depth of ground removed, the inundated area for the depth of debris.

    Returns:
        Mean depth in metres. A footprint of zero gives NaN rather than an
        infinity, because a landslide covering no ground has no depth to report.

    Raises:
        ValueError: If any footprint is negative.
    """
    footprints = np.asarray(footprint_m2, dtype=float)
    if np.any(footprints < 0):
        msg = "footprint_m2 must not be negative"
        raise ValueError(msg)
    volumes = np.asarray(volume_m3, dtype=float)
    return np.divide(
        volumes,
        footprints,
        out=np.full(np.broadcast(volumes, footprints).shape, np.nan),
        where=footprints > 0,
    )
