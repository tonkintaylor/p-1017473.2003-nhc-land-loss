"""The probability that each candidate wall is a wall, and its condition.

A retaining wall inventory does not exist for the study area (**L-04**), so a
candidate carries a probability, not a fact. The candidates are the wall units
landslide step 12 builds on the potential instability faces
(:mod:`landloss.hazard.landslide.wall_units`), which carry their own
``p_wall``: :func:`gen_unit_probability_table` puts the condition on each unit
and the claim it belongs to (:func:`claim_of_properties`), in the shape the
population draw reads. The earlier candidate lines
(:mod:`landloss.exposure.rw.lines`) and the two probabilities this module puts
on each line are kept for the urban slope chain test:

- ``p_wall``: the probability that the line is a wall, from the source the line
  came from, lowered where the face is a cut in rock, capped on the flat land,
  and lifted where GNS Science mapped a wall along it;
- ``p_poor``: the probability that the wall, if it exists, is in the poor
  initial condition, from the dwelling age where held and otherwise from the
  height, because a wall under
  :data:`~landloss.domain.constants.UNCONSENTED_WALL_HEIGHT_M` is often built
  without consent.

Each probability carries a *basis*, the last rule that set it, so a map of
``p_wall_basis`` shows where the mapping reaches and where the prior is all
there is. :mod:`landloss.exposure.rw.population` draws a world from the table
this module writes; keeping the two apart means the evidence is read once and
any number of worlds are drawn from it cheaply.

**The mapping is one-sided.** The GNS SLIDE retaining walls are visible from
above and Wellington City only [townsend_2020], so a mapped wall raises a
line's probability to at least :data:`BETA_MAPPED_WALL_PROBABILITY` and the
absence of one changes nothing. Every number that combines the evidence
carries a ``beta`` name because it is engineering judgement with no fit behind
it; the claim report extraction (**T-50**) is the calibration source. The walls
a claim report lists raise the wall units' probabilities in landslide step 12
(:func:`landloss.hazard.landslide.wall_units.gen_wall_unit_probability`), not
here.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.domain.loss_contract import CLAIM_ID_COLUMN
from landloss.exposure.land.extent import SOURCE_ID_COLUMN
from landloss.exposure.rw.beta_population import (
    BETA_POOR_SHARE,
    SIZE_CLASSES,
    classify_wall_size,
)
from landloss.exposure.rw.lines import CUT, FILL
from landloss.exposure.rw.population import REQUIRED_COLUMNS, WALL_LINE_ID_COLUMN

# The probability of a wall along a line with one mapped on it. Not 1, because
# the mapping is from imagery and a line can be a road batter or the
# neighbour's wall. The one place the mapped-wall floor is typed. Replaced by
# the share of real walls the GNS mapping captures, from the claims with walls
# at addresses inside the SLIDE footprint.
BETA_MAPPED_WALL_PROBABILITY = 0.9

# The prior probability that a line is a wall, by the source it came from, in
# the precedence order of landloss.exposure.rw.lines.SOURCES. A mapped wall is
# the floor above; a cut/fill line marks an earthwork edge that is usually
# retained; a genesis edge is coarser; a terrain break is a face the DEM sees,
# which may be a bank or a cutting; a boundary is a place a wall often is and
# usually is not. Judgement until the count bounds (T-50) replace them.
BETA_SOURCE_PROBABILITY = {
    "gns_mapped_wall": BETA_MAPPED_WALL_PROBABILITY,
    "slide_cut_fill_line": 0.6,
    "slide_cut_edge": 0.5,
    "slide_fill_edge": 0.5,
    "terrain_break": 0.4,
    "road_frontage": 0.25,
    "property_boundary": 0.15,
}

# What a cut face in rock keeps of its prior, set once in
# landloss.domain.constants and shared with the wall units.
BETA_ROCK_CUT_FACTOR = constants.BETA_ROCK_CUT_FACTOR

# The most a line on the NLM flat land can carry: a wall there is a garden edge
# at most. Set against the wall counts in the claim report extraction (T-50)
# once it is held.
BETA_FLATLAND_MAX_PROBABILITY = 0.1

# The probability of poor condition for a wall under UNCONSENTED_WALL_HEIGHT_M,
# which is often built without consent and to no standard. Set with the age
# shares below once the building construction age source is held.
BETA_UNCONSENTED_POOR_SHARE = 0.7

# The probability of poor condition by the dwelling's construction decade,
# either side of the 1991 Building Act: pre-1990 walls are often cast in situ
# concrete gravity walls of the 1970s and 80s, post-1991 ones more often
# anchored timber. Applied only where a dwelling age is held. Set from the
# building construction age source (the District Valuation Roll building age)
# once it is held.
BETA_PRE_1990_POOR_SHARE = 0.7
BETA_POST_1990_POOR_SHARE = 0.3
BUILDING_ACT_DECADE = 1990

# The basis strings: the last rule that set each probability.
WALL_BASES = ("source_prior", "rock_cut", "flatland_cap", "mapped")
SOURCE_PRIOR, ROCK_CUT, FLATLAND_CAP, MAPPED = WALL_BASES
POOR_BASES = ("default", "height", "age")
DEFAULT, HEIGHT, AGE = POOR_BASES

PROBABILITY_COLUMNS = ("p_wall", "p_wall_basis", "p_poor", "p_poor_basis")

# The line columns the two probabilities read. dwelling_age_decade is read
# where present and treated as unheld where the column is absent.
WALL_INPUT_COLUMNS = ("source", "is_mapped_wall", "is_rock_cut", "is_flatland")
HEIGHT_COLUMN = "face_height_m"
AGE_COLUMN = "dwelling_age_decade"

# The wall unit columns the unit table reads (landslide step 12).
UNIT_COLUMNS = (
    "property_id",
    "p_wall",
    "p_wall_basis",
    "height_m",
    "length_m",
    "is_fill",
    "unit_source",
    "ground_material",
)


def _require(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    """Refuse a frame missing any of the columns.

    Args:
        frame: The frame to check.
        columns: The columns it has to carry.
        name: What to call the frame in the message.

    Raises:
        ValueError: If a column is missing.
    """
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        msg = f"{name} is missing {missing}"
        raise ValueError(msg)


def line_wall_probability(lines: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return the probability that each line is a wall, and what set it.

    Applied in this order: the prior of the line's source
    (:data:`BETA_SOURCE_PROBABILITY`); multiplied by :data:`BETA_ROCK_CUT_FACTOR`
    where ``is_rock_cut``; capped at :data:`BETA_FLATLAND_MAX_PROBABILITY` where
    ``is_flatland``; raised to at least :data:`BETA_MAPPED_WALL_PROBABILITY`
    where ``is_mapped_wall``, because a wall seen from above outranks a prior
    guessed from the source. The basis is the last rule that changed the value,
    so a mapped wall whose prior already sat at the floor keeps the basis of
    the rule that put it there.

    Args:
        lines: One row per candidate line carrying :data:`WALL_INPUT_COLUMNS`.

    Returns:
        The probability per line, and the basis per line, one of
        :data:`WALL_BASES`, both aligned to ``lines``.

    Raises:
        ValueError: If a column is missing, or a source is not one of
            :data:`BETA_SOURCE_PROBABILITY`.
    """
    _require(lines, WALL_INPUT_COLUMNS, "lines")
    source = lines["source"].to_numpy()
    unknown = sorted(set(source) - set(BETA_SOURCE_PROBABILITY))
    if unknown:
        msg = f"lines carry sources with no prior: {unknown}"
        raise ValueError(msg)

    probability = np.array(
        [BETA_SOURCE_PROBABILITY[name] for name in source], dtype=float
    )
    basis = np.full(len(lines), SOURCE_PRIOR, dtype=object)

    rock_cut = lines["is_rock_cut"].to_numpy(dtype=bool)
    lowered = probability * BETA_ROCK_CUT_FACTOR
    changed = rock_cut & (lowered != probability)
    probability = np.where(rock_cut, lowered, probability)
    basis[changed] = ROCK_CUT

    flat = lines["is_flatland"].to_numpy(dtype=bool)
    capped = np.minimum(probability, BETA_FLATLAND_MAX_PROBABILITY)
    changed = flat & (capped != probability)
    probability = np.where(flat, capped, probability)
    basis[changed] = FLATLAND_CAP

    mapped = lines["is_mapped_wall"].to_numpy(dtype=bool)
    lifted = np.maximum(probability, BETA_MAPPED_WALL_PROBABILITY)
    changed = mapped & (lifted != probability)
    probability = np.where(mapped, lifted, probability)
    basis[changed] = MAPPED

    return probability, basis


def poor_condition_probability(
    height_m: np.ndarray, dwelling_age_decade: pd.Series
) -> tuple[np.ndarray, np.ndarray]:
    """Return the probability that each wall is in poor condition, and why.

    :data:`~landloss.exposure.rw.beta_population.BETA_POOR_SHARE` by default;
    :data:`BETA_UNCONSENTED_POOR_SHARE` where the height is under
    :data:`~landloss.domain.constants.UNCONSENTED_WALL_HEIGHT_M`; and where a
    dwelling age is held it overrides both, :data:`BETA_PRE_1990_POOR_SHARE`
    for a decade before :data:`BUILDING_ACT_DECADE` and
    :data:`BETA_POST_1990_POOR_SHARE` from it on. A NaN height takes the
    default.

    Args:
        height_m: The face height of each wall, in metres.
        dwelling_age_decade: The construction decade of the dwelling on each
            line's property, nullable; null where no age is held.

    Returns:
        The probability per wall, and the basis per wall, one of
        :data:`POOR_BASES`, both aligned to ``height_m``.

    Raises:
        ValueError: If the two inputs differ in length.
    """
    heights = np.asarray(height_m, dtype=float)
    if len(heights) != len(dwelling_age_decade):
        msg = (
            f"height_m and dwelling_age_decade must match: got {len(heights)} "
            f"and {len(dwelling_age_decade)}"
        )
        raise ValueError(msg)

    probability = np.full(len(heights), BETA_POOR_SHARE, dtype=float)
    basis = np.full(len(heights), DEFAULT, dtype=object)

    unconsented = heights < constants.UNCONSENTED_WALL_HEIGHT_M
    probability[unconsented] = BETA_UNCONSENTED_POOR_SHARE
    basis[unconsented] = HEIGHT

    held = dwelling_age_decade.notna().to_numpy(dtype=bool)
    decade = dwelling_age_decade.to_numpy(dtype=float, na_value=np.nan)
    pre_act = held & (decade < BUILDING_ACT_DECADE)
    probability[pre_act] = BETA_PRE_1990_POOR_SHARE
    probability[held & ~pre_act] = BETA_POST_1990_POOR_SHARE
    basis[held] = AGE

    return probability, basis


def wall_probability_table(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the candidate lines with the two probabilities and their bases.

    Args:
        lines: The candidate wall lines ``gen_wall_lines.py`` wrote, carrying
            :data:`WALL_INPUT_COLUMNS` and ``face_height_m``;
            ``dwelling_age_decade`` is read where present and treated as unheld
            where absent.

    Returns:
        A copy on the same rows and geometry carrying the inputs and
        :data:`PROBABILITY_COLUMNS`.

    Raises:
        ValueError: If a required column is missing.
    """
    _require(lines, (*WALL_INPUT_COLUMNS, HEIGHT_COLUMN), "lines")
    table = lines.copy()
    p_wall, wall_basis = line_wall_probability(table)
    if AGE_COLUMN in table.columns:
        age = table[AGE_COLUMN]
    else:
        age = pd.Series(
            pd.array([pd.NA] * len(table), dtype="Int64"), index=table.index
        )
    p_poor, poor_basis = poor_condition_probability(
        table[HEIGHT_COLUMN].to_numpy(dtype=float), age
    )
    table["p_wall"] = p_wall
    table["p_wall_basis"] = wall_basis
    table["p_poor"] = p_poor
    table["p_poor_basis"] = poor_basis
    return table


def claim_of_properties(
    boundaries: gpd.GeoDataFrame, claims: gpd.GeoDataFrame
) -> pd.Series:
    """Return the claim each LINZ property boundary belongs to.

    :func:`~landloss.exposure.land.extent.build_claim_properties` dissolves the
    boundaries with identical geometry (stacked unit titles) into one claim,
    named after the lowest ``source_id``. This maps every claimable
    boundary's ``source_id`` to the claim whose polygon has exactly its
    geometry, so a wall unit on any title of a stack belongs to the stack's
    claim. Road and hydro parcels are not claimable and have no entry.

    Args:
        boundaries: The LINZ NZ Property Boundaries, carrying ``source_id``.
        claims: The output of ``build_claim_properties(boundaries)``.

    Returns:
        The ``claim_id`` per boundary, indexed by ``source_id`` as a string.
    """
    claim_of_footprint = pd.Series(
        claims[CLAIM_ID_COLUMN].to_numpy(),
        index=claims.geometry.to_wkb().to_numpy(),
    )
    claim_ids = pd.Series(
        claim_of_footprint.reindex(boundaries.geometry.to_wkb().to_numpy()).to_numpy(),
        index=pd.Index(
            boundaries[SOURCE_ID_COLUMN].astype(str).to_numpy(), name="property_id"
        ),
        name=CLAIM_ID_COLUMN,
    )
    claim_ids = claim_ids[claim_ids.notna()]
    return claim_ids[~claim_ids.index.duplicated()]


def gen_unit_probability_table(
    units: gpd.GeoDataFrame, claim_ids: pd.Series
) -> gpd.GeoDataFrame:
    """Return the wall units in the shape the population draw reads.

    One row per wall unit from landslide step 12, carrying its ``p_wall`` as
    it is and the condition probability from its height
    (:func:`poor_condition_probability`; no dwelling age is held). A unit's id
    is its ``wall_line_id``, so a drawn wall names the unit it came from.

    Args:
        units: The wall unit table ``gen_urban_slope_wall_units.py`` writes,
            indexed by ``wall_unit_id``, carrying :data:`UNIT_COLUMNS`.
        claim_ids: From :func:`claim_of_properties`.

    Returns:
        One row per unit, in unit order, on a fresh index, carrying
        :data:`~landloss.exposure.rw.population.REQUIRED_COLUMNS`,
        ``p_wall_basis``, ``p_poor_basis``, ``property_id``, a null
        ``dwelling_age_decade`` and the unit's geometry.

    Raises:
        ValueError: If a unit column is missing.
    """
    _require(units, UNIT_COLUMNS, "units")
    height = units["height_m"].to_numpy(dtype=float)
    # A unit with no height is a GNS-only piece the DEM shows no step at (GNS
    # walls with no pip near them show a step of only 0.4 to 0.5 m), so it is
    # small, not the "large" classify_wall_size gives a NaN.
    size_class = np.where(np.isnan(height), SIZE_CLASSES[0], classify_wall_size(height))
    age = pd.Series(pd.array([pd.NA] * len(units), dtype="Int64"), index=units.index)
    p_poor, poor_basis = poor_condition_probability(height, age)
    property_id = units["property_id"].astype("string")
    claim = property_id.map(claim_ids)
    table = gpd.GeoDataFrame(
        {
            WALL_LINE_ID_COLUMN: units.index.to_numpy(dtype=object),
            CLAIM_ID_COLUMN: claim.astype(object).where(claim.notna(), None).to_numpy(),
            "property_id": property_id.astype(object)
            .where(property_id.notna(), None)
            .to_numpy(),
            "p_wall": units["p_wall"].to_numpy(dtype=float),
            "p_wall_basis": units["p_wall_basis"].to_numpy(dtype=object),
            "p_poor": p_poor,
            "p_poor_basis": poor_basis,
            "size_class": size_class,
            HEIGHT_COLUMN: height,
            "length_m": units["length_m"].to_numpy(dtype=float),
            # Landslide step 13's cut and fill class replaces this once it is
            # settled; until then a unit not on fill is read as a cut.
            "wall_position": np.where(units["is_fill"].to_numpy(dtype=bool), FILL, CUT),
            # The wall units are faces of sloping ground; walls on the flat
            # land are not candidates yet.
            "is_flatland": np.zeros(len(units), dtype=bool),
            "source": units["unit_source"].to_numpy(dtype=object),
            "material": units["ground_material"].to_numpy(dtype=object),
            AGE_COLUMN: age.to_numpy(),
        },
        geometry=units.geometry.to_numpy(),
        crs=units.crs,
    )
    _require(table, REQUIRED_COLUMNS, "the unit table")
    return table
