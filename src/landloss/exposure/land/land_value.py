"""Land value per address, anchored on the published rating valuations.

There is no public per-property land value for the study area that can simply be
redistributed, so the value has to be modelled. The model here is deliberately
the simplest one that is defensible: each territorial authority's published QV
average residential land value is spread across its addresses in proportion to a
landform multiplier, and a per-TA normalising constant pulls the modelled mean
back onto the published average.

The normalising constant is the point of the design. It means the engineering
judgement expressed in the landform factors moves value *between* properties and
never changes the total. A reviewer who disagrees with the factors is arguing
about the distribution within a territorial authority, not about whether
Wellington's land is worth what QV says it is worth -- and the aggregate the
client cares about is unaffected by that argument.

The anchors are the published district revaluations:

===============  ====  ==========  ============  ============  ============
Territorial      TA    Valued at   Rating units  Average CV    Average LV
authority        code
===============  ====  ==========  ============  ============  ============
Wellington City  047   2024-09-01  82,591        $1,086,000    $621,000
Lower Hutt City  046   2025-08-01  43,576        $775,000      $415,000
Porirua City     044   2025-09-01  21,481        $830,000      $420,000
Upper Hutt City  045   2025-06-01  18,474        $776,000      $438,000
===============  ====  ==========  ============  ============  ============

Those four dates are not the same, so each average is indexed onto the common
valuation date :data:`COMMON_VALUATION_DATE` before it is used. The index factors
live in the base rates asset alongside the averages, so the published figure and
the adjustment applied to it are both visible in the output rather than one being
silently folded into the other.

On top of the landform class sits a continuous terrain modifier, which is what
stops every address in a class being worth exactly the same thing. Its shape is
the other half of the design:

.. code-block:: text

    factor = landform_factor(class) * modifier
    modifier = clip(exp(beta_slope * z_slope + beta_tpi * z_tpi))

where the two terrain derivatives are standardised *within* each territorial
authority and landform class, and the modifier is then rescaled so that its mean
is exactly one inside each of those groups.

Standardising and rescaling within the group is the whole trick. Steep land is
already classed as hill, so a slope term that ran across the classes would be
paid for twice -- once by the class and again by the slope. Held to a mean of one
within the group, the class keeps all of the between-class signal and the
modifier does nothing but redistribute value inside it: the steeper half of a
suburb's hill addresses pays the gentler half, and the suburb's total is
untouched. The per-TA normalising constant then works exactly as it did before.

The modifier is optional. An address frame without the terrain columns is valued
on its landform class alone, which is what the first pass over a new extent does
before any DEM has been fetched.

A second modifier, for accessibility, multiplies the first and is built the same
way: centred, clipped and rescaled to a mean of one within the same groups. It
reads the straight-line gravity accessibility to the main centres and the
distance to the nearest railway station, which
:mod:`landloss.exposure.land.accessibility` measures, and it is what separates
Kelburn from Makara -- both hill, both steep -- where the terrain cannot. It is
optional in the same way as the terrain modifier.

Two approximations are worth stating plainly, because they bound what any
per-property figure from this module can be used for. The published averages are
*residential* averages applied to every address, and the LINZ address layer has
no residential flag to narrow them with. And lot size is measured only where the
frame carries the area of each address's property (SECTION_AREA_COLUMN); an
address without one falls back to a per-TA assumed lot, so its rate per square
metre is an order-of-magnitude figure rather than a valuation of the property.
"""

import math
from collections.abc import Collection, Sequence
from pathlib import Path

import geopandas as gpd
import pandas as pd

from landloss.domain import constants
from landloss.exposure.land.accessibility import (
    GRAVITY_COLUMN,
    STATION_DISTANCE_COLUMN,
)
from landloss.exposure.land.extent import (
    PROPERTY_ADDRESS_COUNT_COLUMN,
    PROPERTY_RATING_UNIT_COUNT_COLUMN,
    SECTION_AREA_COLUMN,
)
from landloss.exposure.land.landform import ELEVATED_FLAT, FLAT, HILL
from landloss.io import ASSETS_DIR

# The assets live under landloss.io rather than beside this module, because they
# are inputs that get read rather than code, and landloss.io is where the other
# packaged data files sit.
BASE_RATES_PATH = ASSETS_DIR / "land-value-base-rates.csv"
FACTORS_PATH = ASSETS_DIR / "land-value-factors.csv"

# The date every published average is indexed onto. The four councils revalue on
# their own cycles, so without a common date the TA totals are not comparable.
COMMON_VALUATION_DATE = "2025-09-01"

# The columns an address frame has to carry before it can be valued.
REQUIRED_ADDRESS_COLUMNS = ("territorial_authority", "landform_class")

# The parameter names read out of the factors asset.
LANDFORM_FACTOR_PARAMETERS = {
    HILL: "landform_factor_hill",
    FLAT: "landform_factor_flat",
    ELEVATED_FLAT: "landform_factor_elevated_flat",
}
RATE_CLIP_MIN_PARAMETER = "rate_clip_min_multiple"
RATE_CLIP_MAX_PARAMETER = "rate_clip_max_multiple"

# Everything :func:`estimate_land_value` reads out of the factors asset, checked
# as a set before any of it is used. A parameter dropped or renamed in the asset
# is then named in one message, rather than surfacing as a bare KeyError out of
# the middle of a comprehension -- which is what a reviewer editing the CSV would
# otherwise get, and it does not say which of the two files is wrong.
VALUATION_PARAMETERS = (
    *LANDFORM_FACTOR_PARAMETERS.values(),
    RATE_CLIP_MIN_PARAMETER,
    RATE_CLIP_MAX_PARAMETER,
)

# The terrain derivatives the continuous modifier reads, sampled onto the
# addresses from the DEM by :mod:`landloss.common.utils.terrain`.
SLOPE_COLUMN = "slope_deg"
TOPOGRAPHIC_POSITION_COLUMN = "topographic_position_m"
TERRAIN_COLUMNS = (SLOPE_COLUMN, TOPOGRAPHIC_POSITION_COLUMN)

# The cohort the terrain signal is measured against. A 10 degree section is a
# gentle one among Wellington hill addresses and a remarkably steep one among
# Petone flat addresses, so "steep" only means anything relative to the group an
# address is already in.
TERRAIN_GROUP_COLUMNS = ("territorial_authority", "landform_class")

# The terrain parameters read out of the factors asset. All four are judgement,
# to be re-fitted against sale evidence; see the basis column of the asset.
BETA_SLOPE_PARAMETER = "beta_slope"
BETA_TOPOGRAPHIC_POSITION_PARAMETER = "beta_tpi"
TERRAIN_CLIP_MIN_PARAMETER = "terrain_modifier_clip_min"
TERRAIN_CLIP_MAX_PARAMETER = "terrain_modifier_clip_max"
TERRAIN_PARAMETERS = (
    BETA_SLOPE_PARAMETER,
    BETA_TOPOGRAPHIC_POSITION_PARAMETER,
    TERRAIN_CLIP_MIN_PARAMETER,
    TERRAIN_CLIP_MAX_PARAMETER,
)

# The accessibility attributes the second modifier reads, measured onto the
# addresses by :mod:`landloss.exposure.land.accessibility`.
ACCESSIBILITY_COLUMNS = (GRAVITY_COLUMN, STATION_DISTANCE_COLUMN)

# The accessibility parameters read out of the factors asset. All judgement, to
# be refitted against the District Valuation Roll; see the basis column.
ACCESSIBILITY_ELASTICITY_PARAMETER = "accessibility_elasticity"
RAIL_PREMIUM_PARAMETER = "rail_station_premium"
RAIL_DECAY_PARAMETER = "rail_station_decay_length_m"
ACCESSIBILITY_CLIP_MIN_PARAMETER = "accessibility_modifier_clip_min"
ACCESSIBILITY_CLIP_MAX_PARAMETER = "accessibility_modifier_clip_max"
# How strongly a section's value follows its size, read out of the factors asset
# only when the frame carries SECTION_AREA_COLUMN. Judgement; see its basis.
SECTION_AREA_ELASTICITY_PARAMETER = "section_area_elasticity"
SECTION_AREA_MIN_PARAMETER = "section_area_min_m2"
SIZE_PARAMETERS = (SECTION_AREA_ELASTICITY_PARAMETER, SECTION_AREA_MIN_PARAMETER)

# The whole property's land value. ``land_value_nzd`` is this over the property's
# rating units, which is what a published per-property land value is.
SITE_LAND_VALUE_COLUMN = "site_land_value_nzd"

# The lot size the rate per square metre is divided by, and where it came from:
# the measured area of the address's property, or the per-TA assumption when
# no measured area is available for it.
LOT_SIZE_COLUMN = "lot_size_m2"
LOT_SIZE_SOURCE_COLUMN = "lot_size_source"
MEASURED_LOT = "measured"
ASSUMED_LOT = "assumed"

ACCESSIBILITY_PARAMETERS = (
    ACCESSIBILITY_ELASTICITY_PARAMETER,
    RAIL_PREMIUM_PARAMETER,
    RAIL_DECAY_PARAMETER,
    ACCESSIBILITY_CLIP_MIN_PARAMETER,
    ACCESSIBILITY_CLIP_MAX_PARAMETER,
)


def load_base_rates(path: Path = BASE_RATES_PATH) -> pd.DataFrame:
    """Read the published per-TA rating valuation anchors.

    Args:
        path: The CSV to read. Defaults to the packaged asset.

    Returns:
        A DataFrame with one row per territorial authority, with
        ``valuation_date`` parsed to a ``datetime.date`` and ``ta_code`` kept as
        a string so that its leading zero survives.

    Raises:
        ValueError: If any of the four study area territorial authorities is
            absent, naming the codes that are missing.
    """
    # ta_code is read as text on purpose: the Stats NZ codes are zero padded, and
    # reading "044" as an integer would turn it into 44 and stop it matching
    # STUDY_AREA_TA_CODES.
    base_rates = pd.read_csv(path, dtype={"ta_code": str})

    # An explicit format rather than inference, so that a malformed date in the
    # asset fails here instead of being quietly parsed as something else.
    base_rates["valuation_date"] = pd.to_datetime(
        base_rates["valuation_date"], format="%Y-%m-%d"
    ).dt.date

    missing = sorted(set(constants.STUDY_AREA_TA_CODES) - set(base_rates["ta_code"]))
    if missing:
        named = ", ".join(
            f"{code} ({constants.STUDY_AREA_TA_CODES[code]})" for code in missing
        )
        msg = (
            f"The base rates at {path} are missing the study area territorial "
            f"authority/authorities {named}."
        )
        raise ValueError(msg)

    return base_rates


def load_factors(path: Path = FACTORS_PATH) -> dict[str, float]:
    """Read the land value model parameters.

    The asset is a tall parameter/value/basis table rather than a wide one, so
    that the justification for each number sits on the same row as the number and
    cannot drift away from it.

    Args:
        path: The CSV to read. Defaults to the packaged asset.

    Returns:
        The parameters, keyed by the ``parameter`` column. The ``basis`` column
        is documentation for a human reader and is not returned.
    """
    factors = pd.read_csv(path)
    pairs = zip(factors["parameter"], factors["value"], strict=True)
    return {str(parameter): float(value) for parameter, value in pairs}


def index_base_rates(base_rates: pd.DataFrame) -> pd.DataFrame:
    """Bring every published average onto the common valuation date.

    The source column is left in place rather than overwritten, so that an output
    table shows both the figure the council published and the figure the model
    used, and the step between them stays auditable.

    Args:
        base_rates: The anchors as returned by :func:`load_base_rates`.

    Returns:
        A copy with an ``indexed_land_value_nzd`` column added, holding
        ``avg_land_value_nzd`` multiplied by ``index_to_2025_09``.
    """
    indexed = base_rates.copy()
    indexed["indexed_land_value_nzd"] = (
        indexed["avg_land_value_nzd"] * indexed["index_to_2025_09"]
    )
    return indexed


def solve_normalising_constant(
    factors: Sequence[float] | pd.Series,
    target_mean: float,
    weights: Sequence[float] | pd.Series | None = None,
) -> float:
    """Return the constant that puts the mean of ``constant * factors`` on target.

    This is the whole normalisation, in one line of arithmetic: because the mean
    is linear, scaling every factor by ``target_mean / mean(factors)`` makes the
    mean of the result exactly ``target_mean``. The constant therefore depends
    only on the *mix* of factors and not on how many addresses carry them --
    doubling the population leaves it unchanged.

    With ``weights`` the mean is a weighted one. Weighting each address by one
    over the addresses on its property makes it a mean over properties, which
    is what a published average per rating unit is.

    Args:
        factors: The landform multipliers, one per address.
        target_mean: The mean the scaled factors have to average out to, which
            here is a TA's indexed published average land value.
        weights: Optional weights, one per factor. Equal weights when omitted.

    Returns:
        The normalising constant.

    Raises:
        ValueError: If ``factors`` is empty, or if its mean is not positive.
            Neither has a normalisation, and both mean the factors asset or the
            landform classification is wrong rather than the data being unusual.
    """
    values = [float(factor) for factor in factors]

    if not values:
        msg = (
            "Cannot solve a normalising constant for an empty set of factors: "
            "there is nothing to spread the published average across."
        )
        raise ValueError(msg)

    shares = [1.0] * len(values) if weights is None else [float(w) for w in weights]
    mean_factor = sum(v * w for v, w in zip(values, shares, strict=True)) / sum(shares)
    if mean_factor <= 0:
        msg = (
            f"The mean landform factor is {mean_factor}, but it has to be "
            "positive to normalise against. Check the landform factors asset."
        )
        raise ValueError(msg)

    return target_mean / mean_factor


def _value_one_ta(
    site_raw: pd.Series,
    indexed_average: float,
    lower: pd.Series,
    upper: pd.Series,
    weight: pd.Series,
    units: pd.Series,
) -> pd.Series:
    """Value the sites of a single territorial authority.

    The published average is per rating unit, so the target is the average times
    the rating units the authority holds: the constant is solved so that the
    weighted total of site values equals ``indexed_average * sum(weight * units)``.
    Each property counts once through ``weight``, and a unit-titled block brings
    all of its rating units into the count, as the published figure does.

    Args:
        site_raw: Each address's raw site value -- its rate factor times its
            site area -- in arbitrary units.
        indexed_average: The TA's published average land value per rating unit,
            indexed onto the common valuation date.
        lower: The smallest site value each address may take.
        upper: The largest site value each address may take.
        weight: Each address's weight: one over the addresses on its property.
        units: The rating units on each address's property.

    Returns:
        The site value of each address, indexed as ``site_raw`` is. The weighted
        total per rating unit is the indexed published average, except in the
        one case noted below.
    """
    target_total = indexed_average * float((weight * units).sum())
    constant = solve_normalising_constant(
        site_raw, target_total / float(weight.sum()), weight
    )
    raw = constant * site_raw
    value = raw.clip(lower=lower, upper=upper)

    # Clipping takes value off the extremes, which drags the TA mean off the
    # published average -- and holding that mean is the entire justification for
    # the model. So the constant is solved a second time, this time across only
    # the sites the clip did not bind, carrying whatever the clipped sites gave
    # up or gained. The clipped sites stay pinned at their bounds, which is what
    # makes the total come out exactly right.
    binding = (raw < lower) | (raw > upper)
    free = ~binding
    free_total = float((weight * site_raw)[free].sum())

    if free_total > 0:
        residual = target_total - float((weight * value)[binding].sum())
        constant = residual / free_total

        # Re-applied once, not iterated to convergence. Two cases leave the mean
        # slightly off: the re-solve pushing a previously free site onto a bound,
        # and -- handled by the guard above -- every site binding, so there is
        # nobody free to carry the residual.
        value.loc[free] = (constant * site_raw[free]).clip(
            lower=lower[free], upper=upper[free]
        )

    return value


def _check_known(values: pd.Series, known: Collection, what: str) -> None:
    """Raise if a column holds a value the model has no parameter for.

    Args:
        values: The column to check.
        known: The keys, index or other container of the values that are known.
        what: What the values are, used in the error message.

    Raises:
        ValueError: If any value is absent from ``known``.
    """
    unknown = sorted(set(values) - set(known))
    if unknown:
        listed = ", ".join(repr(value) for value in unknown)
        expected = ", ".join(repr(value) for value in sorted(known))
        msg = (
            f"The addresses carry {what} value(s) the land value model has no "
            f"parameter for: {listed}. Known: {expected}."
        )
        raise ValueError(msg)


def _check_present(
    available: Collection[str], required: Sequence[str], what: str
) -> None:
    """Raise unless everything the model needs is there.

    Args:
        available: The names that are present.
        required: The names that have to be present.
        what: What the names are, used in the error message.

    Raises:
        ValueError: If any required name is absent, naming the ones that are.
    """
    missing = [name for name in required if name not in available]
    if missing:
        msg = (
            f"Missing {what}: {', '.join(missing)}. "
            f"The land value model needs all of: {', '.join(required)}."
        )
        raise ValueError(msg)


def _standardise_within_groups(
    values: pd.Series, groups: Sequence[pd.Series]
) -> pd.Series:
    """Express each value as standard deviations from its own group's mean.

    Three cases come back as zero rather than as NaN, and all three are ordinary
    rather than exceptional: a group with one member, a group whose values are
    all identical, and an address the DEM had no value for. Zero is the right
    answer for each -- it puts the address at the middle of its cohort, which is
    exactly what "nothing is known to distinguish it" should mean. NaN would
    instead poison the address's land value, and a single NaN land value is very
    hard to notice in a quarter of a million rows.

    Args:
        values: The quantity to standardise.
        groups: The keys splitting ``values`` into cohorts, indexed as ``values``
            is.

    Returns:
        The standardised values, indexed as ``values`` is.
    """
    grouped = values.groupby(list(groups), sort=False, dropna=False)
    centre = grouped.transform("mean")

    # ddof=0, because these are whole cohorts rather than samples drawn from
    # one, and because ddof=1 makes a one-address cohort divide by zero.
    spread = grouped.transform("std", ddof=0)

    # where() turns a zero or absent spread into NaN, so the division below has
    # nothing to divide by and the fillna picks the row up.
    return ((values - centre) / spread.where(spread > 0)).fillna(0.0)


def terrain_modifier(
    addresses: gpd.GeoDataFrame, factors: dict[str, float]
) -> pd.Series:
    """Spread value within a landform class according to the terrain.

    The modifier multiplies the landform factor, and is built so that it can
    only move value between the addresses of a cohort and never into or out of
    it:

    1. slope and topographic position are standardised within each
       :data:`TERRAIN_GROUP_COLUMNS` group, so that "steep" means steep for this
       territorial authority and this landform class rather than steep in
       general;
    2. the two are combined as ``exp(beta_slope * z_slope + beta_tpi * z_tpi)``,
       which is a multiplicative effect on value and so cannot go negative;
    3. the result is clipped, so that one freak address cannot be handed several
       times its neighbour's value on the strength of a terrain derivative;
    4. it is rescaled so that its mean within each group is exactly one.

    Step 4 is what keeps the landform factors meaning what they say. Without it
    a cohort of unusually steep addresses would be scaled down as a whole, which
    is the between-class signal the landform class already carries, counted a
    second time.

    Args:
        addresses: Address points carrying :data:`TERRAIN_COLUMNS` and
            :data:`TERRAIN_GROUP_COLUMNS`.
        factors: The model parameters, carrying :data:`TERRAIN_PARAMETERS`.

    Returns:
        The multiplier for each address, indexed as ``addresses`` is, with a
        mean of exactly one within each group. Never NaN.

    Raises:
        ValueError: If a required column or parameter is absent, naming what is
            missing.
    """
    _check_present(
        addresses.columns,
        (*TERRAIN_COLUMNS, *TERRAIN_GROUP_COLUMNS),
        "address frame column(s)",
    )
    _check_present(factors, TERRAIN_PARAMETERS, "land value factor(s)")

    if addresses.empty:
        # A grouped transform over no rows has nothing to group by, and a pilot
        # extent really can come back with no addresses in it.
        return pd.Series(1.0, index=addresses.index, dtype=float)

    groups = [addresses[column] for column in TERRAIN_GROUP_COLUMNS]
    z_slope = _standardise_within_groups(addresses[SLOPE_COLUMN].astype(float), groups)
    z_position = _standardise_within_groups(
        addresses[TOPOGRAPHIC_POSITION_COLUMN].astype(float), groups
    )

    exponent = (
        factors[BETA_SLOPE_PARAMETER] * z_slope
        + factors[BETA_TOPOGRAPHIC_POSITION_PARAMETER] * z_position
    )

    # math.exp through map rather than numpy, so that this module keeps to the
    # dependencies it already has; the cost is invisible next to the spatial
    # work upstream.
    modifier = exponent.map(math.exp).clip(
        lower=factors[TERRAIN_CLIP_MIN_PARAMETER],
        upper=factors[TERRAIN_CLIP_MAX_PARAMETER],
    )

    return _rescale_within_groups(modifier, groups)


def _rescale_within_groups(
    modifier: pd.Series, groups: Sequence[pd.Series]
) -> pd.Series:
    """Rescale a modifier so that its mean within every group is exactly one.

    Done last in each modifier, so the mean is exactly one whatever the clip did.
    The guard covers a clip band configured at or below zero, which would be a
    broken asset rather than unusual data, but not one worth a NaN.
    """
    group_mean = modifier.groupby(list(groups), sort=False, dropna=False).transform(
        "mean"
    )
    return (modifier / group_mean.where(group_mean > 0)).fillna(1.0)


def accessibility_modifier(
    addresses: gpd.GeoDataFrame, factors: dict[str, float]
) -> pd.Series:
    """Spread value within a landform class according to accessibility.

    Built like :func:`terrain_modifier`, so that it too can only move value
    between the addresses of a cohort:

    1. each address's raw accessibility is
       ``gravity ** elasticity * (1 + premium * exp(-station_distance / L))``,
       so the gravity term acts as an elasticity -- value proportional to a power
       of accessibility -- and the station term as a premium that fades over a
       walking distance;
    2. its logarithm is centred on the mean within each
       :data:`TERRAIN_GROUP_COLUMNS` group, so that "accessible" means accessible
       for this territorial authority and this landform class;
    3. the result is exponentiated and clipped, so that the CBD fringe cannot
       run away from the rest of its cohort and a remote address cannot collapse;
    4. it is rescaled so that its mean within each group is exactly one.

    Centring in logs rather than dividing by the arithmetic mean matters in step
    2. Gravity is heavily skewed -- a handful of CBD-fringe addresses carry many
    times the accessibility of the rest -- and against an arithmetic mean nearly
    every address would sit below one before the clip ever saw it.

    The group is the same as the terrain modifier's, and for the same reason.
    Flat land in Wellington City is mostly the CBD and the eastern suburbs, so a
    gravity term running across the classes would pay the flat class again for
    location its landform factor, read off market bands, already carries.

    An address with no gravity value sits at the middle of its cohort, and one
    with no station distance -- the extent had no stations in reach -- takes no
    station premium.

    Args:
        addresses: Address points carrying :data:`ACCESSIBILITY_COLUMNS` and
            :data:`TERRAIN_GROUP_COLUMNS`.
        factors: The model parameters, carrying :data:`ACCESSIBILITY_PARAMETERS`.

    Returns:
        The multiplier for each address, indexed as ``addresses`` is, with a
        mean of exactly one within each group. Never NaN.

    Raises:
        ValueError: If a required column or parameter is absent, naming what is
            missing.
    """
    _check_present(
        addresses.columns,
        (*ACCESSIBILITY_COLUMNS, *TERRAIN_GROUP_COLUMNS),
        "address frame column(s)",
    )
    _check_present(factors, ACCESSIBILITY_PARAMETERS, "land value factor(s)")

    if addresses.empty:
        return pd.Series(1.0, index=addresses.index, dtype=float)

    gravity = addresses[GRAVITY_COLUMN].astype(float)
    station_distance = addresses[STATION_DISTANCE_COLUMN].astype(float)

    # A non-positive gravity has no logarithm. It cannot come out of the gravity
    # formula, so it is treated like a missing one rather than raised on.
    log_gravity = gravity.where(gravity > 0).map(math.log)
    station = (
        (-station_distance / factors[RAIL_DECAY_PARAMETER])
        .map(math.exp)
        .fillna(0.0)
        .mul(factors[RAIL_PREMIUM_PARAMETER])
        .add(1.0)
        .map(math.log)
    )
    log_raw = factors[ACCESSIBILITY_ELASTICITY_PARAMETER] * log_gravity + station

    groups = [addresses[column] for column in TERRAIN_GROUP_COLUMNS]
    centre = log_raw.groupby(groups, sort=False, dropna=False).transform("mean")
    centred = (log_raw - centre).fillna(0.0)

    modifier = centred.map(math.exp).clip(
        lower=factors[ACCESSIBILITY_CLIP_MIN_PARAMETER],
        upper=factors[ACCESSIBILITY_CLIP_MAX_PARAMETER],
    )
    return _rescale_within_groups(modifier, groups)


def property_weight(addresses: pd.DataFrame) -> pd.Series:
    """Return each address's weight: one over the addresses on its property.

    Everything an address carries from its property -- the area, the rating
    units, the site value -- is the property's, so a property LINZ has put
    thirty addresses on would otherwise count thirty times. Weighting by one
    over the addresses on it counts it once. An address without the count, or
    the whole frame without the column, weighs one.

    Args:
        addresses: Address points, optionally carrying
            :data:`PROPERTY_ADDRESS_COUNT_COLUMN`.

    Returns:
        The weight of each address, indexed as ``addresses`` is.
    """
    if PROPERTY_ADDRESS_COUNT_COLUMN not in addresses.columns:
        return pd.Series(1.0, index=addresses.index, dtype=float)
    count = addresses[PROPERTY_ADDRESS_COUNT_COLUMN].astype(float)
    return (1.0 / count.where(count > 0)).fillna(1.0)


def _rating_units(addresses: pd.DataFrame) -> pd.Series:
    """Return the rating units on each address's property, one where unknown."""
    if PROPERTY_RATING_UNIT_COUNT_COLUMN not in addresses.columns:
        return pd.Series(1.0, index=addresses.index, dtype=float)
    units = addresses[PROPERTY_RATING_UNIT_COUNT_COLUMN].astype(float)
    return units.where(units > 0).fillna(1.0)


def ta_mean_land_value(valued: pd.DataFrame) -> pd.Series:
    """Return each TA's modelled mean land value per rating unit.

    Total site value over total rating units, each property counted once. It is
    the mean :func:`estimate_land_value` holds on the published average, so the
    run and the validation compare against the same thing.

    Args:
        valued: Addresses as :func:`estimate_land_value` returns them.

    Returns:
        The mean per territorial authority.
    """
    weight = property_weight(valued)
    site = (
        valued[SITE_LAND_VALUE_COLUMN]
        if SITE_LAND_VALUE_COLUMN in valued
        else (valued["land_value_nzd"])
    )
    ta = valued["territorial_authority"]
    total_value = (site * weight).groupby(ta).sum()
    total_units = (_rating_units(valued) * weight).groupby(ta).sum()
    return total_value / total_units


def section_size_factor(
    area_per_rating_unit_m2: pd.Series,
    assumed_lot_size_m2: pd.Series,
    elasticity: float,
    min_area_m2: float,
) -> pd.Series:
    """Scale the rate per square metre by the size of the section.

    ``(max(area per rating unit, min_area) / assumed_lot) ** (elasticity - 1)``.
    With the elasticity below one, a section's value grows more slowly than its
    area, so its rate falls as it gets bigger: twice the assumed lot is worth
    about 1.41 times as much at 0.5, and its rate is about 0.71 times.

    The area is per rating unit, so a unit-titled block is sized as the sections
    its flats would each have, and its land is the sum of theirs rather than one
    oversized garden; a freehold property is sized on its whole area, however
    many addresses stand on it. The floor stops a block of many small units, or
    a slip of a section, extrapolating the curve far below any section a value
    was ever set from.

    Args:
        area_per_rating_unit_m2: Each address's property area over its rating
            units, in m2.
        assumed_lot_size_m2: The per-TA lot size the factor is relative to.
        elasticity: How value scales with area.
        min_area_m2: The smallest area the factor is evaluated at.

    Returns:
        The rate multiplier for each address, indexed as the area is. One where
        the area is missing or not positive.
    """
    area = area_per_rating_unit_m2.astype(float)
    ratio = area.clip(lower=min_area_m2) / assumed_lot_size_m2.astype(float)
    return ratio.where(area > 0).pow(elasticity - 1.0).fillna(1.0)


def estimate_land_value(
    addresses: gpd.GeoDataFrame,
    base_rates: pd.DataFrame | None = None,
    factors: dict[str, float] | None = None,
) -> gpd.GeoDataFrame:
    """Put a modelled land rate per square metre, and a land value, on every address.

    The rate is what is modelled; the value follows from it. For each
    territorial authority in turn:

    1. the published average land value per rating unit is indexed onto
       :data:`COMMON_VALUATION_DATE`;
    2. each address is given a rate factor: the landform multiplier for its
       class, times its terrain modifier if the frame carries
       :data:`TERRAIN_COLUMNS`, its accessibility modifier if it carries
       :data:`ACCESSIBILITY_COLUMNS`, and :func:`section_size_factor` if it
       carries :data:`SECTION_AREA_COLUMN`;
    3. the site value is that factor times the site area -- the measured
       property, or the assumed lot where there is none -- and a constant is
       solved so that total site value over total rating units is the indexed
       published average, counting each property once;
    4. each site is clipped to the configured multiples of the average per
       rating unit, the floor applying only to a property of one rating unit,
       because a flat's share of its block's land is legitimately small;
    5. the constant is solved once more across the sites the clip did not
       bind, so that the TA mean still lands on the published average.

    Step 5 is what makes the model arguable-with in a useful way. The factors
    are judgement, and judgement moves value from one property to another -- but
    never changes what the territorial authority is worth in total, which stays
    exactly what the council published. Without a measured area every address is
    one rating unit on its assumed lot, which is the model before areas were
    measured.

    Args:
        addresses: Address points carrying :data:`REQUIRED_ADDRESS_COLUMNS`, as
            produced by :func:`landloss.exposure.land.landform.classify_landform`.
            :data:`TERRAIN_COLUMNS` and :data:`ACCESSIBILITY_COLUMNS` turn on
            the two location modifiers. :data:`SECTION_AREA_COLUMN`, with
            :data:`PROPERTY_ADDRESS_COUNT_COLUMN` and
            :data:`PROPERTY_RATING_UNIT_COUNT_COLUMN`, measures each site. Every
            combination is a supported answer, and all of them hold the TA mean.
        base_rates: The published anchors. Defaults to the packaged asset.
        factors: The model parameters. Defaults to the packaged asset.

    Returns:
        A new GeoDataFrame, re-indexed from zero, with
        ``land_rate_nzd_per_m2``; :data:`SITE_LAND_VALUE_COLUMN`, the whole
        property's land; ``land_value_nzd``, that over its rating units, which is
        what a published per-property land value is; ``assumed_lot_size_m2``;
        :data:`LOT_SIZE_COLUMN`, the site area the rate is per; and
        :data:`LOT_SIZE_SOURCE_COLUMN`. The caller's frame is left untouched.

    Raises:
        ValueError: If a required column or a required factor is absent, if an
            address carries a territorial authority the base rates say nothing
            about, or if it carries a landform class the factors say nothing
            about. None of the four is silently dropped, because an address that
            vanishes between the exposure model and the loss model is an
            expensive thing to notice late.
    """
    _check_present(
        addresses.columns, REQUIRED_ADDRESS_COLUMNS, "address frame column(s)"
    )

    if base_rates is None:
        base_rates = load_base_rates()
    if factors is None:
        factors = load_factors()

    _check_present(factors, VALUATION_PARAMETERS, "land value factor(s)")

    rates = index_base_rates(base_rates).set_index("ta_name")
    factor_by_class = {
        landform: factors[parameter]
        for landform, parameter in LANDFORM_FACTOR_PARAMETERS.items()
    }

    # A copy, so that nothing written below can reach back into the caller's
    # frame. Re-indexed for the same reason classify_landform re-indexes: the
    # per-TA assignment below addresses rows by label, which needs unique labels.
    valued = addresses.copy().reset_index(drop=True)

    _check_known(valued["territorial_authority"], rates.index, "territorial authority")
    _check_known(valued["landform_class"], factor_by_class, "landform class")

    factor = valued["landform_class"].map(factor_by_class).astype(float)

    # The terrain columns are optional, and their absence is not an error: an
    # extent can be valued on landform alone before any DEM has been fetched for
    # it. Because the modifier averages one within every group, switching it on
    # leaves each TA's total exactly where it was and only redistributes inside.
    if all(column in valued.columns for column in TERRAIN_COLUMNS):
        factor = factor * terrain_modifier(valued, factors)

    # The accessibility columns are optional in the same way, and for the same
    # reason leave each TA's total where it was.
    if all(column in valued.columns for column in ACCESSIBILITY_COLUMNS):
        factor = factor * accessibility_modifier(valued, factors)

    assumed_lot = valued["territorial_authority"].map(rates["median_lot_size_m2"])
    assumed_lot = assumed_lot.astype(float)

    # The site is optional too. Without a measured area, an address is one rating
    # unit on the assumed lot; with one, it is its property, with its rating units.
    area = pd.Series(float("nan"), index=valued.index, dtype=float)
    if SECTION_AREA_COLUMN in valued.columns:
        _check_present(factors, SIZE_PARAMETERS, "land value factor(s)")
        area = valued[SECTION_AREA_COLUMN].astype(float)
    measured = area > 0
    site_area = area.where(measured, assumed_lot)
    units = _rating_units(valued).where(measured, 1.0)

    if SECTION_AREA_COLUMN in valued.columns:
        factor = factor * section_size_factor(
            site_area / units,
            assumed_lot,
            factors[SECTION_AREA_ELASTICITY_PARAMETER],
            factors[SECTION_AREA_MIN_PARAMETER],
        )

    weight = property_weight(valued)
    site_value = pd.Series(float("nan"), index=valued.index, dtype=float)

    clip_min = factors[RATE_CLIP_MIN_PARAMETER]
    clip_max = factors[RATE_CLIP_MAX_PARAMETER]

    # Grouped rather than vectorised because each TA has its own anchor, its own
    # normalising constant and its own clip bounds; there is no shared scale.
    grouped = valued.groupby("territorial_authority", sort=False)
    for ta_name, rows in grouped.groups.items():
        indexed_average = float(rates.loc[ta_name, "indexed_land_value_nzd"])
        single = units.loc[rows] == 1
        site_value.loc[rows] = _value_one_ta(
            factor.loc[rows] * site_area.loc[rows],
            indexed_average,
            lower=(clip_min * indexed_average * single).astype(float),
            upper=clip_max * indexed_average * units.loc[rows],
            weight=weight.loc[rows],
            units=units.loc[rows],
        )

    valued["land_rate_nzd_per_m2"] = site_value / site_area
    valued[SITE_LAND_VALUE_COLUMN] = site_value
    valued["land_value_nzd"] = site_value / units
    valued["assumed_lot_size_m2"] = assumed_lot
    valued[LOT_SIZE_COLUMN] = site_area
    valued[LOT_SIZE_SOURCE_COLUMN] = measured.map(
        {True: MEASURED_LOT, False: ASSUMED_LOT}
    )

    return valued


def summarise_by_suburb(valued: gpd.GeoDataFrame) -> pd.DataFrame:
    """Reduce valued addresses to the cohort table the Phase 1 tool consumes.

    One row per territorial authority, suburb and landform class. Medians rather
    than means, because within a cohort the interest is in the typical property
    and a handful of clipped extremes should not move the number.

    Args:
        valued: Addresses as returned by :func:`estimate_land_value`, also
            carrying ``suburb_locality``.

    Returns:
        A tidy DataFrame with ``territorial_authority``, ``suburb_locality``,
        ``landform_class``, ``address_count``, ``median_land_value_nzd`` and
        ``median_land_rate_nzd_per_m2``. The geometry is dropped: this is a table
        to read, not a layer to map.
    """
    cohorts = ["territorial_authority", "suburb_locality", "landform_class"]

    # Dropped to a plain DataFrame first, because the geometry has no meaning
    # once rows are pooled into a cohort and carrying it would imply otherwise.
    attributes = pd.DataFrame(
        valued.drop(columns=valued.geometry.name, errors="ignore")
    )

    # dropna=False so that an address with no suburb recorded is reported as its
    # own cohort rather than disappearing out of the totals.
    return (
        attributes.groupby(cohorts, dropna=False, sort=True)
        .agg(
            address_count=("land_value_nzd", "size"),
            median_land_value_nzd=("land_value_nzd", "median"),
            median_land_rate_nzd_per_m2=("land_rate_nzd_per_m2", "median"),
        )
        .reset_index()
    )
