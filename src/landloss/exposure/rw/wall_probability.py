"""The probability that each candidate wall line is a wall, and its condition.

A retaining wall inventory does not exist for the study area (**L-04**), so a
candidate line (:mod:`landloss.exposure.rw.lines`) carries a probability, not a
fact. This module puts two on each line:

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
it; the claim report extraction (**T-50**) is the calibration source, and
:func:`apply_count_bounds` is where its minimum and maximum walls per property
enter once it is held.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.exposure.rw.beta_population import BETA_POOR_SHARE

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

# What a cut face in rock keeps of its prior: a rock cut stands unsupported and
# is claimed for spalling or slides rather than wall failure (Oriental Bay and
# Evans Bay are the worked examples). Set against the wall counts in the claim
# report extraction (T-50) once it is held.
BETA_ROCK_CUT_FACTOR = 0.3

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

# The count bounds table (T-50): one row per claim, the fewest and most walls
# the claim report says the property has.
BOUNDS_COLUMNS = ("min_walls", "max_walls")


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


def apply_count_bounds(
    p_wall: np.ndarray, claim_ids: pd.Series, bounds: pd.DataFrame
) -> np.ndarray:
    """Return the probabilities scaled into each claim's count bounds.

    The claim report extraction (**T-50**) gives a minimum and a maximum number
    of walls per property. Inside each claim the probabilities are scaled by
    one factor so that their sum, the expected number of walls, is at least the
    minimum and at most the maximum; a claim already inside its bounds, or
    with no bounds, is unchanged. A claim whose lines all carry zero cannot be
    scaled up, so each of its lines takes an equal share of the minimum. No
    probability is scaled above 1, so a minimum above the number of lines is
    met as nearly as the lines allow.

    Args:
        p_wall: The probability per line, from :func:`line_wall_probability`.
        claim_ids: The claim of each line, aligned to ``p_wall``; null where
            the line belongs to no claim, which no bound reaches.
        bounds: One row per claim, indexed by claim id, carrying
            :data:`BOUNDS_COLUMNS`.

    Returns:
        The scaled probability per line.

    Raises:
        ValueError: If the inputs differ in length, a bound column is
            missing, or a minimum is above its maximum.
    """
    probability = np.asarray(p_wall, dtype=float).copy()
    if len(probability) != len(claim_ids):
        msg = (
            f"p_wall and claim_ids must match: got {len(probability)} and "
            f"{len(claim_ids)}"
        )
        raise ValueError(msg)
    _require(bounds, BOUNDS_COLUMNS, "bounds")
    if (bounds["min_walls"] > bounds["max_walls"]).any():
        msg = "bounds carry a minimum above its maximum"
        raise ValueError(msg)

    claims = claim_ids.to_numpy(dtype=object)
    for claim, row in bounds.iterrows():
        inside = claims == claim
        if not inside.any():
            continue
        expected = probability[inside].sum()
        count = int(inside.sum())
        low, high = float(row["min_walls"]), float(row["max_walls"])
        if expected < low:
            scaled = (
                np.full(count, low / count)
                if expected == 0.0
                else probability[inside] * (low / expected)
            )
        elif expected > high:
            scaled = probability[inside] * (high / expected)
        else:
            continue
        probability[inside] = np.minimum(scaled, 1.0)
    return probability


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
