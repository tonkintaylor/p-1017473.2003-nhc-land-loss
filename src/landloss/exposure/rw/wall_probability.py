"""The probability that each candidate wall is a wall.

A retaining wall inventory does not exist for the study area (**L-04**), so a
candidate carries a probability, not a fact. The candidates are the wall units
landslide step 12 builds on the potential instability faces
(:mod:`landloss.hazard.landslide.wall_units`), which carry their own
``p_wall``: :func:`gen_unit_probability_table` puts on each unit the claim it
belongs to (:func:`claim_of_properties`), in the shape the population draw
reads. The earlier candidate lines (:mod:`landloss.exposure.rw.lines`) and the
``p_wall`` this module puts on each line are kept for the urban slope chain
test: the probability that the line is a wall, from the source the line came
from, lowered where the face is a cut in rock, capped on the flat land, and
lifted where GNS Science mapped a wall along it. A wall's type, which carries
what used to be its condition, is drawn per world in exposure step 6
(:mod:`landloss.exposure.rw.wall_type`).

The probability carries a *basis*, the last rule that set it, so a map of
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
from landloss.exposure.rw.beta_population import SIZE_CLASSES, classify_wall_size
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

# The basis strings: the last rule that set the probability.
WALL_BASES = ("source_prior", "rock_cut", "flatland_cap", "mapped")
SOURCE_PRIOR, ROCK_CUT, FLATLAND_CAP, MAPPED = WALL_BASES

PROBABILITY_COLUMNS = ("p_wall", "p_wall_basis")

# The line columns the probability reads.
WALL_INPUT_COLUMNS = ("source", "is_mapped_wall", "is_rock_cut", "is_flatland")
HEIGHT_COLUMN = "face_height_m"

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


def wall_probability_table(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the candidate lines with the wall probability and its basis.

    Args:
        lines: The candidate wall lines ``gen_wall_lines.py`` wrote, carrying
            :data:`WALL_INPUT_COLUMNS` and ``face_height_m``.

    Returns:
        A copy on the same rows and geometry carrying the inputs and
        :data:`PROBABILITY_COLUMNS`.

    Raises:
        ValueError: If a required column is missing.
    """
    _require(lines, (*WALL_INPUT_COLUMNS, HEIGHT_COLUMN), "lines")
    table = lines.copy()
    p_wall, wall_basis = line_wall_probability(table)
    table["p_wall"] = p_wall
    table["p_wall_basis"] = wall_basis
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
    it is. A unit's id is its ``wall_line_id``, so a drawn wall names the unit
    it came from.

    Args:
        units: The wall unit table ``gen_urban_slope_wall_units.py`` writes,
            indexed by ``wall_unit_id``, carrying :data:`UNIT_COLUMNS`.
        claim_ids: From :func:`claim_of_properties`.

    Returns:
        One row per unit, in unit order, on a fresh index, carrying
        :data:`~landloss.exposure.rw.population.REQUIRED_COLUMNS`,
        ``p_wall_basis``, ``property_id`` (the unit's primary property, the
        one its wall is drawn on), the unit's geometry and, where the units
        carry them, ``property_lengths_m`` and ``n_properties`` (its length in
        every property it enters by at least 1 m) and ``length_original_m``.

    Raises:
        ValueError: If a unit column is missing.
    """
    _require(units, UNIT_COLUMNS, "units")
    height = units["height_m"].to_numpy(dtype=float)
    # A unit with no height is a GNS-only piece the DEM shows no step at (GNS
    # walls with no pip near them show a step of only 0.4 to 0.5 m), so it is
    # small, not the "large" classify_wall_size gives a NaN.
    size_class = np.where(np.isnan(height), SIZE_CLASSES[0], classify_wall_size(height))
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
            "size_class": size_class,
            HEIGHT_COLUMN: height,
            "length_m": units["length_m"].to_numpy(dtype=float),
            # is_fill is landslide step 13's class fill or cut and fill; every
            # other class (cut, natural, uncertain, unknown) is read as a cut.
            "wall_position": np.where(units["is_fill"].to_numpy(dtype=bool), FILL, CUT),
            # The wall units are faces of sloping ground; walls on the flat
            # land are not candidates yet.
            "is_flatland": np.zeros(len(units), dtype=bool),
            "source": units["unit_source"].to_numpy(dtype=object),
            "material": units["ground_material"].to_numpy(dtype=object),
        },
        geometry=units.geometry.to_numpy(),
        crs=units.crs,
    )
    for column in ("property_lengths_m", "n_properties", "length_original_m"):
        if column in units.columns:
            table[column] = units[column].to_numpy()
    _require(table, REQUIRED_COLUMNS, "the unit table")
    return table
