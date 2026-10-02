"""Tests for the Kingsbury (1995) slope failure susceptibility scheme."""

import numpy as np
import pandas as pd
import pytest

from landloss.domain import constants
from landloss.hazard.landslide.susceptibility import (
    GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    GROUNDWATER_POORLY_DRAINED,
    GROUNDWATER_SATURATED,
    GROUNDWATER_WELL_DRAINED,
    LANDSLIDES_ACTIVE,
    LANDSLIDES_NONE,
    LANDSLIDES_OLD,
    MAX_RATING,
    SIDLING_FILL_VALUE,
    ZONE_LABELS,
    ZONE_RANKS,
    cut_angle_value,
    geology_value_from_material,
    groundwater_value,
    slope_angle_value,
    slope_height_value,
    susceptibility_rating,
    susceptibility_zone,
)
from landloss.hazard.landslide.susceptibility import (
    GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED as GEOLOGY_HW_CW,
)


def rating_of(**factors):
    """Score one cell, taking scalars and handing back a scalar."""
    arrays = {name: np.array([value]) for name, value in factors.items()}
    return float(susceptibility_rating(**arrays)[0])


def zone_of(rating):
    return float(susceptibility_zone(np.array([rating]))[0])


# --- factor values against Table 4 --------------------------------------------


@pytest.mark.parametrize(
    ("slope", "expected"),
    [(0.0, 0.0), (19.9, 0.0), (20.0, 2.0), (34.9, 2.0), (35.0, 4.0), (45.0, 8.0)],
)
def test_slope_angle_classes_are_entered_at_their_lower_bound(slope, expected):
    """A slope of exactly 20 degrees is in the 20-35 class, not the one below."""
    assert slope_angle_value(np.array([slope]))[0] == expected


def test_the_steepest_slope_scores_the_maximum():
    """Precipitous ground is the top of the 1-10 scale."""
    assert slope_angle_value(np.array([75.0]))[0] == 10.0


@pytest.mark.parametrize(
    ("slope", "expected"),
    [(20.0, 0.0), (34.9, 0.0), (35.0, 4.0), (45.0, 8.0), (60.0, 10.0)],
)
def test_a_cut_under_35_degrees_is_not_a_class_in_the_scheme(slope, expected):
    """Table 4 defines cut classes only from 35 degrees up, so below it scores nil."""
    assert cut_angle_value(np.array([slope]))[0] == expected


def test_slope_height_is_not_scored_on_gentler_ground():
    """Note 3 excludes natural 35-45 degree slopes, coastal cliffs among them."""
    tall_but_not_steep = slope_height_value(np.array([30.0]), np.array([40.0]))

    assert tall_but_not_steep[0] == 0.0


def test_slope_height_is_scored_once_the_face_is_steep_enough():
    """The same 30 m of relief counts on a face steeper than 45 degrees."""
    assert slope_height_value(np.array([30.0]), np.array([50.0]))[0] == 10.0


def test_nodata_slope_stays_nodata():
    """A cell with no elevation must not come back scored as precipitous."""
    assert np.isnan(slope_angle_value(np.array([np.nan]))[0])
    assert np.isnan(cut_angle_value(np.array([np.nan]))[0])
    assert np.isnan(slope_height_value(np.array([np.nan]), np.array([np.nan]))[0])


# --- the published worked examples --------------------------------------------
#
# Kingsbury's Table 6 gives five typical cells with their weighted products and
# the band each falls in. Reproducing them verifies the values, the weightings
# and the bands together, and it is how the table was checked against OCR of the
# scanned booklet.
#
# Only the top three are reproduced here, and that is a statement about the
# source rather than about this code. The Very Low and Low rows reach their
# stated totals of 18 and 56 using factor values of 1 and 2, which are not
# classes Table 4 defines for the factors concerned; the Moderate, High and Very
# High rows decompose exactly into published classes. Since the low two cannot
# be written down in the scheme's own vocabulary, asserting them would only
# pin down a guess at how the source arrived at them.


def test_the_moderate_example_reproduces():
    """Moderate to steep slopes and cuts, small old slides: Rs = 96, moderate."""
    rating = rating_of(
        slope=4.0,
        modification=8.0,
        height=4.0,
        geology=GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
        landslides=LANDSLIDES_OLD,
        groundwater=GROUNDWATER_SATURATED,
    )

    assert rating == 96.0
    assert zone_of(rating) == 3


def test_the_high_example_reproduces():
    """Steep slopes with steep, moderately high cuts: Rs = 138, high."""
    rating = rating_of(
        slope=8.0,
        modification=10.0,
        height=8.0,
        geology=GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
        landslides=LANDSLIDES_ACTIVE,
        groundwater=GROUNDWATER_SATURATED,
    )

    assert rating == 138.0
    assert zone_of(rating) == 4


def test_the_very_high_example_reaches_the_published_maximum():
    """Precipitous slopes with very high cuts: Rs = 150, the scheme's ceiling."""
    rating = rating_of(
        slope=10.0,
        modification=10.0,
        height=10.0,
        geology=GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
        landslides=LANDSLIDES_ACTIVE,
        groundwater=GROUNDWATER_SATURATED,
    )

    assert rating == MAX_RATING
    assert zone_of(rating) == 5


# --- bands and ranks ----------------------------------------------------------


@pytest.mark.parametrize(
    ("rating", "expected"),
    [(0.0, 1), (19.9, 1), (20.0, 2), (60.0, 3), (100.0, 4), (140.0, 5)],
)
def test_zone_bands_are_entered_at_their_lower_bound(rating, expected):
    """Table 5's bands are written 0-20, 20-60 and so on; the upper one wins."""
    assert zone_of(rating) == expected


def test_the_ranks_match_the_published_layer():
    """A rebuilt zone is only comparable with the source if the scales agree."""
    assert sorted(ZONE_RANKS) == sorted(constants.GWRC_SEVERITY_RANKS.values())


def test_every_rank_carries_a_label():
    """A figure legend reads these, so a missing one would print a bare number."""
    assert set(ZONE_LABELS) == set(ZONE_RANKS)


def test_a_sidling_fill_scores_the_maximum_modification():
    """The failure is on the contact the fill sits on, not on the face angle."""
    assert max(GEOLOGY_COLLUVIUM_OR_ALLUVIUM, 10.0) == SIDLING_FILL_VALUE


def test_nothing_can_exceed_the_published_maximum():
    """A rating above 150 would mean a weighting or a class value was mistyped."""
    everything_at_once = rating_of(
        slope=10.0,
        modification=SIDLING_FILL_VALUE,
        height=10.0,
        geology=GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
        landslides=LANDSLIDES_ACTIVE,
        groundwater=GROUNDWATER_SATURATED,
    )

    assert everything_at_once == MAX_RATING


def test_a_lesser_geology_class_lowers_the_rating():
    """Guards the geology weighting, which the step supplies as a constant."""
    colluvium = rating_of(
        slope=8.0,
        modification=0.0,
        height=0.0,
        geology=GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
        landslides=LANDSLIDES_NONE,
        groundwater=GROUNDWATER_SATURATED,
    )
    weathered_rock = rating_of(
        slope=8.0,
        modification=0.0,
        height=0.0,
        geology=GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
        landslides=LANDSLIDES_NONE,
        groundwater=GROUNDWATER_SATURATED,
    )

    assert colluvium - weathered_rock == 12.0


# --- groundwater, from depth to water ----------------------------------------


@pytest.mark.parametrize(
    ("depth_m", "expected"),
    [
        (0.0, GROUNDWATER_SATURATED),
        (0.9, GROUNDWATER_SATURATED),
        (1.0, GROUNDWATER_POORLY_DRAINED),
        (2.9, GROUNDWATER_POORLY_DRAINED),
        (3.0, GROUNDWATER_WELL_DRAINED),
        (4.0, GROUNDWATER_WELL_DRAINED),
        (16.0, GROUNDWATER_WELL_DRAINED),
    ],
)
def test_groundwater_class_falls_as_the_water_table_deepens(depth_m, expected):
    """This factor runs the opposite way to every other one, so it is worth pinning."""
    assert groundwater_value(np.array([depth_m]))[0] == expected


def test_the_assumed_off_footprint_depth_is_well_drained():
    """A hillside outside the NLM's flat-land grid has to score as draining."""
    assumed = 4.0

    assert groundwater_value(np.array([assumed]))[0] == GROUNDWATER_WELL_DRAINED


def test_unknown_groundwater_depth_stays_unknown():
    """A caller filling the gap is a decision; NaN passing through is not."""
    assert np.isnan(groundwater_value(np.array([np.nan]))[0])


# --- geology, from NLM material classes ---------------------------------------
#
# The classes below are every value of l3_yp present over the four territorial
# authorities, read off the layer. If the model gains another the lookup raises
# rather than defaulting, which is what the last test guards.

STUDY_AREA_MATERIALS = (
    "Sedimentary",
    "River channel",
    "Foreshore",
    "Floodplain",
    "Uncompacted fill",
    "Water body",
    "Metamorphic",
    "Igneous",
    "Talus",
    "Loess",
    "Colluvium",
    "Compacted fill",
)

BASEMENT_MATERIALS = ("Sedimentary", "Metamorphic", "Igneous")


def test_every_material_in_the_study_area_has_a_geology_class():
    """A missing one would stop a full run part way through, not degrade it."""
    scored = geology_value_from_material(pd.Series(STUDY_AREA_MATERIALS))

    # Water is the one deliberate NaN; everything else has to carry a value.
    assert scored.drop(index=STUDY_AREA_MATERIALS.index("Water body")).notna().all()


def test_basement_rock_scores_below_unconsolidated_ground():
    """The split between rock and loose material is the whole of this factor."""
    scored = geology_value_from_material(pd.Series(STUDY_AREA_MATERIALS))
    by_material = dict(zip(STUDY_AREA_MATERIALS, scored, strict=True))

    for material in BASEMENT_MATERIALS:
        assert by_material[material] == GEOLOGY_HW_CW

    loose = set(STUDY_AREA_MATERIALS) - set(BASEMENT_MATERIALS) - {"Water body"}
    for material in loose:
        assert by_material[material] == GEOLOGY_COLLUVIUM_OR_ALLUVIUM


def test_open_water_is_left_unscored():
    """A harbour is not ground that can fail, so it gets no susceptibility."""
    scored = geology_value_from_material(pd.Series(["Water body"]))

    assert np.isnan(scored.iloc[0])


def test_talus_is_read_as_colluvium():
    """The coarser l2 field rolls talus in with landslide debris; l3 does not."""
    scored = geology_value_from_material(pd.Series(["Talus"]))

    assert scored.iloc[0] == GEOLOGY_COLLUVIUM_OR_ALLUVIUM


def test_an_unmapped_material_is_refused():
    """A new class upstream is a decision for somebody, not a silent default."""
    with pytest.raises(ValueError, match="No geology class is assigned"):
        geology_value_from_material(pd.Series(["Volcanic cone"]))


def test_hill_country_can_still_reach_the_lowest_zone():
    """Gentle, well drained bedrock has to be able to score very low.

    With geology and groundwater held constant this was impossible: the two
    together put every cell above the 20 point band before any terrain was read.
    """
    rating = rating_of(
        slope=0.0,
        modification=0.0,
        height=0.0,
        geology=GEOLOGY_HW_CW,
        landslides=LANDSLIDES_NONE,
        groundwater=GROUNDWATER_WELL_DRAINED,
    )

    assert zone_of(rating) == 1
