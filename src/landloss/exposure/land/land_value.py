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
no residential flag to narrow them with. And lot size is a per-TA median rather
than a measured parcel area, so the rate per square metre is an order-of-
magnitude figure for comparing cohorts, not a valuation of any one property.
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
    factors: Sequence[float] | pd.Series, target_mean: float
) -> float:
    """Return the constant that puts the mean of ``constant * factors`` on target.

    This is the whole normalisation, in one line of arithmetic: because the mean
    is linear, scaling every factor by ``target_mean / mean(factors)`` makes the
    mean of the result exactly ``target_mean``. The constant therefore depends
    only on the *mix* of factors and not on how many addresses carry them --
    doubling the population leaves it unchanged.

    Args:
        factors: The landform multipliers, one per address.
        target_mean: The mean the scaled factors have to average out to, which
            here is a TA's indexed published average land value.

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

    mean_factor = sum(values) / len(values)
    if mean_factor <= 0:
        msg = (
            f"The mean landform factor is {mean_factor}, but it has to be "
            "positive to normalise against. Check the landform factors asset."
        )
        raise ValueError(msg)

    return target_mean / mean_factor


def _value_one_ta(
    factor: pd.Series, indexed_average: float, lower: float, upper: float
) -> pd.Series:
    """Value the addresses of a single territorial authority.

    Args:
        factor: The landform multiplier for each address in the TA.
        indexed_average: The TA's published average land value, indexed onto the
            common valuation date.
        lower: The smallest land value an address may take.
        upper: The largest land value an address may take.

    Returns:
        The land value of each address, indexed as ``factor`` is. The mean is the
        indexed published average, except in the one case noted below.
    """
    constant = solve_normalising_constant(factor, indexed_average)
    raw = constant * factor
    value = raw.clip(lower=lower, upper=upper)

    # Clipping takes value off the extremes, which drags the TA mean off the
    # published average -- and holding that mean is the entire justification for
    # the model. So the constant is solved a second time, this time across only
    # the addresses the clip did not bind, carrying whatever the clipped
    # addresses gave up or gained. The clipped addresses stay pinned at their
    # bounds, which is what makes the total come out exactly right.
    binding = (raw < lower) | (raw > upper)
    free = ~binding
    free_factor_total = float(factor[free].sum())

    if free_factor_total > 0:
        residual = indexed_average * len(factor) - float(value[binding].sum())
        constant = residual / free_factor_total

        # Re-applied once, not iterated to convergence. Two cases leave the mean
        # slightly off: the re-solve pushing a previously free address onto a
        # bound, and -- handled by the guard above -- every address binding, so
        # there is nobody free to carry the residual. Both need a clip band
        # narrower than the spread of the factors themselves, which means the
        # clip multiples and the factors disagree and one of them is wrong. With
        # the values the study actually runs, nothing binds at all.
        value.loc[free] = (constant * factor[free]).clip(lower=lower, upper=upper)

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


def estimate_land_value(
    addresses: gpd.GeoDataFrame,
    base_rates: pd.DataFrame | None = None,
    factors: dict[str, float] | None = None,
) -> gpd.GeoDataFrame:
    """Put a modelled land value on every address.

    For each territorial authority in turn:

    1. the published average land value is indexed onto
       :data:`COMMON_VALUATION_DATE`;
    2. each address is given the landform multiplier for its class, multiplied
       by its terrain modifier if the frame carries :data:`TERRAIN_COLUMNS` and
       by its accessibility modifier if it carries
       :data:`ACCESSIBILITY_COLUMNS`;
    3. a normalising constant is solved so that the scaled multipliers average to
       the indexed published figure;
    4. the resulting values are clipped to the configured multiples of that
       figure, so that no single address is modelled at an absurd value;
    5. the constant is solved once more across the addresses the clip did not
       bind, so that the TA mean still lands on the published average.

    Step 5 is what makes the model arguable-with in a useful way. The landform
    factors are judgement, and judgement moves value from one property to another
    -- but never changes what the territorial authority is worth in total, which
    stays exactly what the council published.

    Args:
        addresses: Address points carrying :data:`REQUIRED_ADDRESS_COLUMNS`, as
            produced by :func:`landloss.exposure.land.landform.classify_landform`.
            Carrying :data:`TERRAIN_COLUMNS` as well turns on the continuous
            terrain modifier described in :func:`terrain_modifier`, and
            :data:`ACCESSIBILITY_COLUMNS` the one described in
            :func:`accessibility_modifier`; without them an address is valued
            on its landform class alone. Every combination is a supported
            answer, and all of them hold the TA mean.
        base_rates: The published anchors. Defaults to the packaged asset.
        factors: The model parameters. Defaults to the packaged asset.

    Returns:
        A new GeoDataFrame, re-indexed from zero, with ``land_value_nzd``,
        ``land_rate_nzd_per_m2`` and ``assumed_lot_size_m2`` added. The caller's
        frame is left untouched.

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

    land_value = pd.Series(float("nan"), index=valued.index, dtype=float)

    clip_min = factors[RATE_CLIP_MIN_PARAMETER]
    clip_max = factors[RATE_CLIP_MAX_PARAMETER]

    # Grouped rather than vectorised because each TA has its own anchor, its own
    # normalising constant and its own clip bounds; there is no shared scale.
    grouped = valued.groupby("territorial_authority", sort=False)
    for ta_name, rows in grouped.groups.items():
        indexed_average = float(rates.loc[ta_name, "indexed_land_value_nzd"])
        land_value.loc[rows] = _value_one_ta(
            factor.loc[rows],
            indexed_average,
            lower=clip_min * indexed_average,
            upper=clip_max * indexed_average,
        )

    lot_size = valued["territorial_authority"].map(rates["median_lot_size_m2"])
    lot_size = lot_size.astype(float)

    valued["land_value_nzd"] = land_value
    valued["land_rate_nzd_per_m2"] = land_value / lot_size
    valued["assumed_lot_size_m2"] = lot_size

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
