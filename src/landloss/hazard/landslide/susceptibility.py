"""The Kingsbury (1995) earthquake-induced slope failure susceptibility scheme.

Greater Wellington's slope failure susceptibility zonation scores six factors,
each on a 1 to 10 scale, weights them, and sums the products into a
susceptibility rating that bands into five zones::

    Rs = 4*F_slope + 4*F_modification + 2*F_height + 2*F_geology
         + 2*F_landslides + 1*F_groundwater

The values and the weightings are Table 4 of Kingsbury (1995), and the bands are
its Table 5. All four map sheets covering this study area -- Wellington
(WRC/PP-T-95/06), Porirua and SH58 (/07), Hutt Valley (/08) and SH2 Upper Hutt
to Featherston (/10) -- carry the identical table, so this is one scheme applied
region wide rather than four.

This module holds the scoring only. Where each factor's input comes from, and
which of them this study can actually supply, belongs to the step that runs it:
``src/scripts/landloss/hazard/landslide/steps/s2_slope_failure_susceptibility/``.

The published layer built from this scheme is CC BY-ND, which is why the scheme
is reimplemented here rather than the layer being derived from. A method is not
a dataset; see ``.agents/plans/rebuilding-gwrc-slope-failure-susceptibility.md``.

Two things the scheme does that are easy to miss:

- **Slope height is only scored on slopes steeper than 45 degrees.** Kingsbury's
  note 3 is explicit that it is not appropriate for natural slopes of 35 to 45
  degrees, naming coastal cliffs and the Wellington Fault scarp. So the factor is
  masked, not merely valued at zero.
- **The zone ranks match the published layer's own ``SEVERITY`` classes**, 1 low
  through 5 high, so a rating scored here bands onto the same 1 to 5 scale as
  ``landloss.domain.constants.GWRC_SEVERITY_RANKS``. That is what makes a
  rebuilt zone directly comparable with the source layer's.
"""

import numpy as np
import numpy.typing as npt
import pandas as pd

# Table 4 weightings. Slope angle and slope modification carry 4 each, so
# between them they are 80 of the 150 points available -- which is why the
# booklets say those two "were used primarily to define the boundaries of the
# hazard zones on the maps".
SLOPE_ANGLE_WEIGHT = 4
SLOPE_MODIFICATION_WEIGHT = 4
SLOPE_HEIGHT_WEIGHT = 2
GEOLOGY_WEIGHT = 2
LANDSLIDE_WEIGHT = 2
GROUNDWATER_WEIGHT = 1

# The highest rating the scheme can produce, stated in Kingsbury's note 2 to
# Table 6. Worth keeping as a named check rather than a comment: the worked
# examples in that table sum to 96, 138 and 150 for the moderate, high and very
# high cells, and reproducing them is how this implementation was verified
# against OCR of the source. The table's two lowest cells reach their stated 18
# and 56 using factor values of 1 and 2, which Table 4 does not define for the
# factors concerned, so they cannot be written down in the scheme's own
# vocabulary and are not reproduced.
MAX_RATING = 150

# Slope angle classes, in degrees. A class is entered at its lower bound, so 20
# degrees scores 2 rather than 0.
SLOPE_ANGLE_BREAKS_DEGREES = (20.0, 35.0, 45.0, 60.0)
SLOPE_ANGLE_VALUES = (0.0, 2.0, 4.0, 8.0, 10.0)

# Cut slope angle classes. Table 4 defines these only from 35 degrees upwards --
# a cut flatter than that is not a class in the source at all. Scoring it zero
# is this implementation's reading of that silence, and it is the reading that
# matters least: a cut under 35 degrees is not what the scheme is about.
CUT_ANGLE_BREAKS_DEGREES = (35.0, 45.0, 60.0)
CUT_ANGLE_VALUES = (0.0, 4.0, 8.0, 10.0)

# A sidling fill scores the maximum whatever its angle, because the failure is on
# the contact the fill was placed on rather than on the face of it.
SIDLING_FILL_VALUE = 10.0

# Slope height classes, in metres, scored only where the slope is steeper than
# SLOPE_HEIGHT_MIN_SLOPE_DEGREES.
SLOPE_HEIGHT_BREAKS_M = (5.0, 10.0, 20.0)
SLOPE_HEIGHT_VALUES = (0.0, 4.0, 8.0, 10.0)
SLOPE_HEIGHT_MIN_SLOPE_DEGREES = 45.0

# Geology classes. Named rather than left as bare numbers because the step
# supplies one of them as a constant, and a constant chosen from a named class
# can be argued with.
GEOLOGY_UNWEATHERED_TO_MODERATELY_WEATHERED = 0.0
GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED = 4.0
GEOLOGY_CRUSHED_AND_SHATTERED_GREYWACKE = 8.0
GEOLOGY_COLLUVIUM_OR_ALLUVIUM = 10.0

# Existing landslide classes.
LANDSLIDES_NONE = 0.0
LANDSLIDES_OLD = 5.0
LANDSLIDES_ACTIVE = 10.0

# Groundwater classes.
GROUNDWATER_WELL_DRAINED = 0.0
GROUNDWATER_POORLY_DRAINED = 5.0
GROUNDWATER_SATURATED = 10.0

# Depth to groundwater, in metres below ground, at which each class is entered.
# Kingsbury names his three classes and never says what depth they are, so these
# are this study's reading of them against the failure the scheme is about.
#
# The booklets put earthquake-induced surficial failures in "a variable but
# generally thin (1 to 2 metre) surface layer of colluvium", failing "at the
# bedrock interface". So a water table inside that layer is the saturated case;
# one just below it is the poorly drained case, because prolonged rain lifts it
# into the failing material -- which is the condition the source says the factor
# was generalised to reflect; and one well below it drains.
GROUNDWATER_SATURATED_DEPTH_M = 1.0
GROUNDWATER_POORLY_DRAINED_DEPTH_M = 3.0

# Ordered deepest first, because the classes fall as depth rises.
GROUNDWATER_DEPTH_BREAKS_M = (
    GROUNDWATER_SATURATED_DEPTH_M,
    GROUNDWATER_POORLY_DRAINED_DEPTH_M,
)
GROUNDWATER_DEPTH_VALUES = (
    GROUNDWATER_SATURATED,
    GROUNDWATER_POORLY_DRAINED,
    GROUNDWATER_WELL_DRAINED,
)

# Kingsbury's geology classes against the National Liquefaction Model's ``l3_yp``
# material class, which is the finest of the model's three nested
# classifications that this study has a use for. The coarser ``l2_geomorphology``
# was read first and is not enough: it rolls talus in with landslide debris, and
# it has no class at all for open water, so a harbour scores as alluvium.
#
# The outcome is still close to binary -- basement rock against everything
# unconsolidated -- and saying so is more honest than dressing it up. That is a
# limit of the source, not of the field chosen: Kingsbury's four classes turn on
# weathering grade and shearing, and the model maps neither, so his unweathered
# and his crushed-and-shattered classes are never reached however finely the
# landform is read.
#
# Water is mapped to NaN rather than to a value. Open water is not ground that
# can fail, and scoring it would put a susceptibility on a harbour.
#
# The fill classes here are the model's own mapped fill, a regional geological
# unit. They are not the Wellington City earthworks fill that the slope
# modification factor reads, which is a different dataset at a different scale,
# and the two are scored by different factors.
NLM_MATERIAL_GEOLOGY_VALUES: dict[str, float] = {
    # Basement rock. In this region that is Torlesse greywacke, which the model
    # labels "sandstone" or "greywacke" in ``main_rock`` -- two lithology names
    # for the same basement, not a difference the scheme scores.
    "Sedimentary": GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    "Metamorphic": GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    "Igneous": GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    # Material moved downslope, which is Kingsbury's colluvium in everything but
    # the name.
    "Talus": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "Colluvium": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "Loess": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    # Water-laid deposits.
    "River channel": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "Floodplain": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "Foreshore": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "Swamp": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    # Placed ground.
    "Uncompacted fill": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "Compacted fill": GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    # Not land.
    "Water body": float("nan"),
}

# Table 5 zone bands, and the ranks they map to. The ranks are the published
# layer's own SEVERITY classes, so a rebuilt zone and a source zone are the same
# number for the same severity.
ZONE_BREAKS = (20.0, 60.0, 100.0, 140.0)
ZONE_RANKS = (1, 2, 3, 4, 5)

# What a rank means, for labelling a figure or a table without retyping it.
ZONE_LABELS = {
    1: "Very low",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Very high",
}


def _classify(
    values: npt.NDArray[np.floating],
    breaks: tuple[float, ...],
    scores: tuple[float, ...],
) -> npt.NDArray[np.floating]:
    """Score values into classes, keeping nodata as nodata.

    ``np.digitize`` sorts NaN above every break and would hand back the top
    score for it, so a cell with no elevation would come out as precipitous.
    The NaN is put back afterwards rather than the input being filled, because
    a missing factor has to stay missing until the caller decides what to do
    about it.

    Args:
        values: The quantity being classified.
        breaks: The lower bound of every class after the first, ascending. A
            value equal to a break falls in the class above it.
        scores: One score per class, so one longer than ``breaks``.

    Returns:
        The score for each value, NaN where the value was NaN.

    Raises:
        ValueError: If there is not exactly one more score than break.
    """
    if len(scores) != len(breaks) + 1:
        msg = (
            f"{len(breaks)} breaks define {len(breaks) + 1} classes, but "
            f"{len(scores)} scores were given."
        )
        raise ValueError(msg)

    values = np.asarray(values, dtype=float)
    classified = np.asarray(scores, dtype=float)[np.digitize(values, breaks)]
    return np.where(np.isnan(values), np.nan, classified)


def slope_angle_value(
    slope_degrees: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Score the natural slope angle factor, F_slope.

    Args:
        slope_degrees: Ground slope in degrees.

    Returns:
        The factor value, 0 to 10, NaN where the slope is NaN.
    """
    return _classify(slope_degrees, SLOPE_ANGLE_BREAKS_DEGREES, SLOPE_ANGLE_VALUES)


def cut_angle_value(
    slope_degrees: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Score the face angle of a cut slope, the modification factor F_modification.

    This is the same measurement as :func:`slope_angle_value` reads, on the same
    ground, but a different scale: modification is scored on how steep the *cut*
    stands, and the scheme has no class for a cut under 35 degrees.

    Args:
        slope_degrees: The angle of the cut face in degrees.

    Returns:
        The factor value, 0 to 10, NaN where the slope is NaN.
    """
    return _classify(slope_degrees, CUT_ANGLE_BREAKS_DEGREES, CUT_ANGLE_VALUES)


def slope_height_value(
    height_m: npt.NDArray[np.floating],
    slope_degrees: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Score the slope height factor, F_height, where the scheme applies it.

    Kingsbury's note 3 restricts this factor to slopes steeper than
    :data:`SLOPE_HEIGHT_MIN_SLOPE_DEGREES`, "cuts mainly", and says it is not
    appropriate for natural 35 to 45 degree slopes such as coastal cliffs or the
    Wellington Fault scarp. Ground below that angle scores zero here regardless
    of how much relief it carries.

    Args:
        height_m: The height of the steep face, in metres.
        slope_degrees: The angle of that face, in degrees, used to decide
            whether the factor applies at all.

    Returns:
        The factor value, 0 to 10, NaN where either input is NaN.
    """
    scored = _classify(height_m, SLOPE_HEIGHT_BREAKS_M, SLOPE_HEIGHT_VALUES)

    slope_degrees = np.asarray(slope_degrees, dtype=float)
    applies = slope_degrees >= SLOPE_HEIGHT_MIN_SLOPE_DEGREES
    scored = np.where(applies, scored, 0.0)
    return np.where(np.isnan(slope_degrees), np.nan, scored)


def groundwater_value(
    depth_m: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Score the groundwater factor, F_groundwater, from depth to water.

    The scheme names three drainage conditions and never says what depth each
    one is; the thresholds are this study's, and the reasoning behind them is
    with :data:`GROUNDWATER_SATURATED_DEPTH_M`.

    Shallow water scores high, so the classes fall as depth rises -- the reverse
    of every other factor here, which is the one thing worth checking twice when
    reading this.

    Args:
        depth_m: Depth to groundwater in metres below ground. A caller holding a
            grid that covers only part of its extent fills the gap before
            calling rather than passing NaN: ground the model does not cover is
            not ground with an unknown water table.

    Returns:
        The factor value, 0 (well drained) to 10 (saturated), NaN where the
        depth is NaN.
    """
    return _classify(depth_m, GROUNDWATER_DEPTH_BREAKS_M, GROUNDWATER_DEPTH_VALUES)


def geology_value_from_material(materials: pd.Series) -> pd.Series:
    """Score the geology factor, F_geology, from NLM material classes.

    Args:
        materials: The ``l3_yp`` column of the National Liquefaction Model's
            geomorphology polygons. This is the field to read, not the coarser
            ``l2_geomorphology`` and not ``main_rock``: the reasons are with
            :data:`NLM_MATERIAL_GEOLOGY_VALUES`.

    Returns:
        The factor value for each polygon, on the caller's own index. NaN where
        the polygon is open water, which is deliberately left unscored.

    Raises:
        ValueError: If a material is not one this study has decided a class for,
            which means the upstream model has gained a class and somebody has
            to make the decision rather than have it defaulted.
    """
    unknown = set(materials.dropna().unique()) - set(NLM_MATERIAL_GEOLOGY_VALUES)
    if unknown:
        known = ", ".join(repr(name) for name in sorted(NLM_MATERIAL_GEOLOGY_VALUES))
        msg = (
            f"No geology class is assigned for the material(s) "
            f"{', '.join(repr(name) for name in sorted(unknown))}. Known: {known}"
        )
        raise ValueError(msg)

    return materials.map(NLM_MATERIAL_GEOLOGY_VALUES)


def susceptibility_rating(
    *,
    slope: npt.NDArray[np.floating],
    modification: npt.NDArray[np.floating],
    height: npt.NDArray[np.floating],
    geology: npt.NDArray[np.floating],
    landslides: npt.NDArray[np.floating],
    groundwater: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Sum the weighted factor values into a susceptibility rating, Rs.

    Every argument is a factor *value* on the 0 to 10 scale, not a measurement:
    the weighting is applied here so that no caller can apply it twice.

    Six arguments because the scheme has six factors, and grouping them into a
    container would only move the same six names somewhere else while hiding
    which of them a given call left out.

    Args:
        slope: F_slope, from :func:`slope_angle_value`.
        modification: F_modification, from :func:`cut_angle_value` or
            :data:`SIDLING_FILL_VALUE`.
        height: F_height, from :func:`slope_height_value`.
        geology: F_geology, one of the ``GEOLOGY_`` classes.
        landslides: F_landslides, one of the ``LANDSLIDES_`` classes.
        groundwater: F_groundwater, one of the ``GROUNDWATER_`` classes.

    Returns:
        The rating, 0 to :data:`MAX_RATING`.
    """
    return (
        SLOPE_ANGLE_WEIGHT * np.asarray(slope, dtype=float)
        + SLOPE_MODIFICATION_WEIGHT * np.asarray(modification, dtype=float)
        + SLOPE_HEIGHT_WEIGHT * np.asarray(height, dtype=float)
        + GEOLOGY_WEIGHT * np.asarray(geology, dtype=float)
        + LANDSLIDE_WEIGHT * np.asarray(landslides, dtype=float)
        + GROUNDWATER_WEIGHT * np.asarray(groundwater, dtype=float)
    )


def susceptibility_zone(
    rating: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Band a susceptibility rating into the five published zones.

    Args:
        rating: The susceptibility rating, from :func:`susceptibility_rating`.

    Returns:
        The zone rank, 1 (very low) to 5 (very high), on the same scale as
        ``landloss.domain.constants.GWRC_SEVERITY_RANKS``. NaN where the rating
        is NaN, which is why the result is floating rather than integer.
    """
    ranks = tuple(float(rank) for rank in ZONE_RANKS)
    return _classify(rating, ZONE_BREAKS, ranks)
