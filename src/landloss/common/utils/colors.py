"""The colour maps shared between this study's figures and its QGIS projects.

A colour map defined in the script that draws a figure is fine right up until a
second thing draws the same quantity. Then there are two of them, they agree
today, and one of them is edited a month later -- so a reader comparing a QGIS
layer against the figure in the report has to work out which legend they are
looking at before they can look at the map.

Everything here is a quantity this study renders in more than one place. A
colour chosen for a single figure stays in that figure's script, where it is
easier to find and cheaper to change; see the `keep plotting logic in scripts`
convention in `.agents/skills/adding-steps-scripts/SKILL.md`. Ported from the
National Liquefaction Model's ``nlm_colors``, which serves the same purpose
there.

Two conventions, both of which the QGIS builder depends on.

Colours are ``#rrggbb``, or ``#rrggbbaa`` where a band is deliberately
see-through. A categorical map is ``{value: (colour, label)}`` and is ordered as
the legend should read, which is not always the sort order of the values.
"""

# The two kinds of ground a landslide leaves behind, as
# ``src/scripts/landloss/hazard/landslide/steps/s1_landslide_realisation/``
# writes them into the ``land_class`` column. Red for the ground that goes,
# orange for the ground it lands on: they have to be told apart at a glance,
# because the whole reason the model keeps them separate is that NHC settles
# loss of support and runout differently.
EVACUATED_LAND = "evacuated land"
INUNDATED_LAND = "inundated land"

LAND_CLASS_COLOURS: dict[str, tuple[str, str]] = {
    EVACUATED_LAND: ("#a50026", "Evacuated land (source)"),
    INUNDATED_LAND: ("#f46d43", "Inundated land (runout)"),
}

# The six land damage states, keyed by the state codes in
# ``gen_observed_damage_db.DAMAGE_STATES``. A green to red ramp; states 1, 3, 4
# and 6 keep the National Liquefaction Model's own colours so a panel from this
# study reads against one from that one, and 2 and 5 fill the ramp in between.
#
# These are damage *states* -- a severity scale from none observed to very
# severe -- and not the NHC land damage *categories*, which are payout types.
# The two are different things and the labels here say which.
#
# Mirrors ``STATE_COLOURS`` in
# ``src/scripts/landloss/vul/liquefaction/land/report/fig_land_damage_maps.py``,
# which predates this module. Point that script here next time it is touched,
# rather than leaving two copies to drift.
LAND_DAMAGE_STATE_COLOURS: dict[int, tuple[str, str]] = {
    1: ("#3AB04A", "1 None observed"),
    2: ("#A6D96A", "2 Minor"),
    3: ("#FEE900", "3 Moderate"),
    4: ("#F8951D", "4 Major"),
    5: ("#D7301F", "5 Severe"),
    6: ("#9D1C1F", "6 Very severe"),
}

# Greater Wellington's earthquake-induced slope failure zonation, keyed by the
# integer rank in ``landloss.domain.constants.GWRC_SEVERITY_RANKS``. Green
# through yellow to red, one colour per class. Discrete rather than a continuous
# ramp: these are five ordinal classes off a 1995 map, and a colour bar would
# imply a precision the source does not have.
GWRC_SEVERITY_COLOURS: dict[int, tuple[str, str]] = {
    1: ("#1a9850", "1 Low"),
    2: ("#a6d96a", "2"),
    3: ("#fee08b", "3 Moderate"),
    4: ("#f46d43", "4"),
    5: ("#a50026", "5 High"),
}

# Probability of earthquake-induced slope failure per cell, as the supplied ESNZ
# grid carries it. Bands rather than a continuous ramp, because the useful
# question of this grid is "which order of magnitude", and the values are very
# unevenly distributed -- a median near 0.02 against a maximum near 0.98, so a
# linear ramp shows almost the whole country in one colour.
#
# Keyed by (lower, upper). An upper bound equal to the lower bound marks an
# open-ended band: leading means "everything below", trailing "everything
# above". That is the convention the QGIS discrete-ramp writer reads.
EIL_PROBABILITY_COLOURS: dict[tuple[float, float], str] = {
    (0.0, 0.005): "#ffffcc",
    (0.005, 0.01): "#ffeda0",
    (0.01, 0.025): "#fed976",
    (0.025, 0.05): "#feb24c",
    (0.05, 0.1): "#fd8d3c",
    (0.1, 0.2): "#fc4e2a",
    (0.2, 0.4): "#e31a1c",
    (0.4, 0.4): "#800026",
}

# Slope in degrees, on the bands this study keeps talking in: flat ground, the
# 10 degrees below which displaced material barely moves, and the 45 above which
# the displacement model saturates.
SLOPE_DEGREE_COLOURS: dict[tuple[float, float], str] = {
    (0.0, 5.0): "#f7f7f7",
    (5.0, 10.0): "#d9f0d3",
    (10.0, 20.0): "#a6dba0",
    (20.0, 30.0): "#fee08b",
    (30.0, 45.0): "#f46d43",
    (45.0, 45.0): "#7f0000",
}
