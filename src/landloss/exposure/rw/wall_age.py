"""The age bin each property's retaining walls were built in, as shares.

A wall's type is drawn from the era it was built in
(``.agents/plans/assigning-retaining-wall-types.md``, Method 1), in the four
bins of :data:`landloss.exposure.rw.age.AGE_BINS`, whose breaks are explained in
``src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md``. Each property
gets a share per bin rather than one bin, because a decade or a rebuilt dwelling
does not settle which bin its walls are in; the wall draw picks the bin.

The evidence is read in order:

1. **Dwelling age first.** The QV rating roll's ``building_age_indicator``, the
   decade the main building was built (:func:`qv_age_shares`,
   :func:`property_qv_ages`).
2. **Property age second.** Exposure step 8's title and survey plan date
   (:mod:`landloss.exposure.rw.age`), only where it is the lot's own
   (:data:`LOT_DATE_BASES`): in place of the dwelling age where that
   is missing, and mixed half and half with it where the lot is
   :data:`BETA_LOT_OLDER_GAP_YEARS` or more older than the dwelling, since the
   original walls of a rebuilt section may have stayed. Where the dwelling is
   older than the lot (infill or a reissued title) the lot date is not used.
3. **Neither held:** the suburb's ``p_<bin>`` shares, and failing that the
   extent's (:func:`combine_wall_ages`).
"""

import numpy as np
import pandas as pd

from landloss.exposure.land.extent import SOURCE_ID_COLUMN
from landloss.exposure.rw.age import AGE_BASIS_COLUMN as LOT_BASIS_COLUMN
from landloss.exposure.rw.age import (
    AGE_BIN_COLUMN,
    AGE_BINS,
    DP,
    EST_YEAR_COLUMN,
)
from landloss.exposure.rw.age import TITLE as TITLE_DATED
from landloss.io.qv_rating_roll import linz_valuation_reference

# One share per bin, as the per-suburb table of exposure step 8 names them.
AGE_SHARE_COLUMNS = tuple(f"p_{age_bin}" for age_bin in AGE_BINS)
P_PRE_1970, P_1970_1991, P_1992_2004, P_2005_ON = AGE_SHARE_COLUMNS

# The decade midpoint the QV code stands for, which the lot-older test reads.
QV_YEAR_COLUMN = "qv_year"
PROPERTY_ID_COLUMN = "property_id"
VALUATION_REFERENCE_COLUMN = "valuation_reference"
BUILDING_AGE_COLUMN = "building_age_indicator"

# The rule that set each property's shares, in the order of the module
# docstring: the dwelling alone, the dwelling mixed with an older lot, the lot
# alone, the suburb and the extent.
AGE_BASIS_COLUMN = "age_basis"
AGE_BASES = ("qv", "qv_and_lot", "title", "suburb", "extent")
QV, QV_AND_LOT, TITLE, SUBURB, EXTENT = AGE_BASES

# The step 8 rules whose year is the lot's own title or plan date. Its
# neighbourhood rules (a neighbours' median, or Lot 1 of an infill plan set back
# to it) date the area, not the lot, so they go to the suburb instead.
LOT_DATE_BASES = (TITLE_DATED, DP)

# How much older than the dwelling a lot has to be before the walls are read as
# possibly the original ones, left when the house was rebuilt. Judgement with
# nothing fitted behind it; an open decision of the plan.
BETA_LOT_OLDER_GAP_YEARS = 20.0

# The QV code for a dwelling built before 1900, and the year it stands for.
_QV_PRE_CODE = "PRE"
_QV_PRE_YEAR = 1900.0

# The share of the lot's bin where the lot is much older than the dwelling.
_LOT_SHARE = 0.5

# How far from 1 a row of shares handed in may sum, for rounding in a table.
_SUM_TOLERANCE = 1e-6

# The decade each bin's QV decades end before. A decade cannot split at July
# 1992, so the 1990s count in 1992_2004 (plan, Method 1.1); the 2000s are split
# half and half at 2005, as the bin note says when no consent counts are held.
_FIRST_1970_1991_DECADE = 1970
_FIRST_1992_2004_DECADE = 1990
_SPLIT_DECADE = 2000
_FIRST_2005_ON_DECADE = 2010
_DECADE_MIDPOINT = 5.0


def _decade_shares(decade: float) -> tuple[float, float, float, float]:
    """Return the share per bin of a dwelling built in one decade."""
    if decade < _FIRST_1970_1991_DECADE:
        return (1.0, 0.0, 0.0, 0.0)
    if decade < _FIRST_1992_2004_DECADE:
        return (0.0, 1.0, 0.0, 0.0)
    if decade < _SPLIT_DECADE:
        return (0.0, 0.0, 1.0, 0.0)
    if decade < _FIRST_2005_ON_DECADE:
        return (0.0, 0.0, 0.5, 0.5)
    return (0.0, 0.0, 0.0, 1.0)


def qv_age_shares(building_age_indicator: pd.Series) -> pd.DataFrame:
    """Return the share per age bin of each QV rating unit's dwelling.

    The roll codes the decade the main building was built in three characters,
    ``"196"`` for the 1960s, and ``"PRE"`` for before 1900. ``"XXX"``,
    ``"AAA"``, ``"MIX"``, a blank and anything else are read as not known. The
    1990s count in ``1992_2004`` and the 2000s go half to ``1992_2004`` and
    half to ``2005_on`` (``.agents/plans/assigning-retaining-wall-types.md``,
    Method 1.1; ``src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md``).

    Args:
        building_age_indicator: The roll's ``building_age_indicator``, as text.

    Returns:
        On the same index, :data:`AGE_SHARE_COLUMNS` and :data:`QV_YEAR_COLUMN`,
        the decade's midpoint (1900 for ``"PRE"``); every column NaN where the
        code is not a known age.
    """
    codes = building_age_indicator.astype("string").str.strip().str.upper()
    is_decade = codes.str.fullmatch(r"\d{3}").fillna(value=False).astype(bool)
    is_pre = (codes == _QV_PRE_CODE).fillna(value=False).astype(bool)

    shares = np.full((len(codes), len(AGE_SHARE_COLUMNS)), np.nan)
    years = np.full(len(codes), np.nan)
    decades = codes[is_decade].astype(int).to_numpy() * 10
    if len(decades):
        shares[is_decade.to_numpy()] = [_decade_shares(d) for d in decades]
    years[is_decade.to_numpy()] = decades + _DECADE_MIDPOINT
    shares[is_pre.to_numpy()] = _decade_shares(_QV_PRE_YEAR)
    years[is_pre.to_numpy()] = _QV_PRE_YEAR

    out = pd.DataFrame(
        shares, index=building_age_indicator.index, columns=AGE_SHARE_COLUMNS
    )
    out[QV_YEAR_COLUMN] = years
    return out


def property_qv_ages(roll: pd.DataFrame, boundaries: pd.DataFrame) -> pd.DataFrame:
    """Return the QV dwelling age shares of each LINZ property.

    The roll is joined to the boundaries on the valuation reference
    (:func:`landloss.io.qv_rating_roll.linz_valuation_reference`). Where several
    rating units fall on one property, the oldest dwelling stands for it, as
    the earliest title does in exposure step 8, because its walls are the
    oldest that may still stand. Every property is kept, not only residential
    ones, since a wall can stand on any.

    Args:
        roll: Units from :func:`landloss.io.qv_rating_roll.get_qv_rating_roll`,
            carrying its valuation number parts and ``building_age_indicator``.
        boundaries: The LINZ property boundaries, carrying ``source_id`` and
            ``valuation_reference``.

    Returns:
        Indexed by ``property_id`` (the ``source_id`` as a string), the
        :data:`AGE_SHARE_COLUMNS` and :data:`QV_YEAR_COLUMN` of each property
        with a known dwelling age.
    """
    units = qv_age_shares(roll[BUILDING_AGE_COLUMN])
    units[VALUATION_REFERENCE_COLUMN] = linz_valuation_reference(roll)
    # pandas joins a missing key to every other missing key, so a property with
    # no valuation reference would take the age of any unit without one.
    units = units[
        units[QV_YEAR_COLUMN].notna() & units[VALUATION_REFERENCE_COLUMN].notna()
    ]

    properties = pd.DataFrame(
        {
            PROPERTY_ID_COLUMN: boundaries[SOURCE_ID_COLUMN].astype(str).to_numpy(),
            VALUATION_REFERENCE_COLUMN: boundaries[
                VALUATION_REFERENCE_COLUMN
            ].to_numpy(),
        }
    )
    properties = properties[properties[VALUATION_REFERENCE_COLUMN].notna()]
    joined = properties.merge(units, on=VALUATION_REFERENCE_COLUMN, how="inner")
    oldest = joined.sort_values(QV_YEAR_COLUMN, kind="stable").drop_duplicates(
        PROPERTY_ID_COLUMN
    )
    return oldest.set_index(PROPERTY_ID_COLUMN).sort_index()[
        [*AGE_SHARE_COLUMNS, QV_YEAR_COLUMN]
    ]


def own_lot_dates(lot_ages: pd.DataFrame) -> pd.DataFrame:
    """Return the lots exposure step 8 dated by their own title or plan.

    A year step 8 took from the neighbours (its rules 3 and 4) is left out,
    because it is not the lot's date and would stand in for the suburb's
    shares under the name of a title.

    Args:
        lot_ages: Step 8's ``est_year``, ``age_bin`` and ``age_basis`` per
            property.

    Returns:
        The ``est_year`` and ``age_bin`` of the rows with a bin and a basis in
        :data:`LOT_DATE_BASES`, on their index.
    """
    own_date = lot_ages[LOT_BASIS_COLUMN].astype(object).isin(LOT_DATE_BASES)
    has_bin = lot_ages[AGE_BIN_COLUMN].notna()
    own = own_date & has_bin
    return lot_ages.loc[own, [EST_YEAR_COLUMN, AGE_BIN_COLUMN]]


def _one_hot(age_bins: pd.Series) -> pd.DataFrame:
    """Return a share of 1 in each row's own bin.

    Raises:
        ValueError: If a bin is not one of :data:`AGE_BINS`.
    """
    labels = age_bins.astype(object)
    unknown = sorted(set(labels.dropna()) - set(AGE_BINS))
    if unknown:
        msg = f"title age bins {unknown} are not among {AGE_BINS}"
        raise ValueError(msg)
    return pd.DataFrame(
        {
            column: (labels == age_bin).astype(float)
            for column, age_bin in zip(AGE_SHARE_COLUMNS, AGE_BINS, strict=True)
        },
        index=age_bins.index,
    )


def _normalised_default(default: pd.Series) -> pd.Series:
    """Return the extent's shares, checked and rescaled to sum to 1.

    Raises:
        ValueError: If the shares are not one per bin, are negative or do not
            sum to 1.
    """
    if set(default.index) != set(AGE_SHARE_COLUMNS):
        msg = (
            f"the default shares must be over {AGE_SHARE_COLUMNS}, "
            f"not {list(default.index)}"
        )
        raise ValueError(msg)
    shares = default.reindex(list(AGE_SHARE_COLUMNS)).astype(float)
    if (shares < 0).any() or abs(shares.sum() - 1.0) > _SUM_TOLERANCE:
        msg = (
            "the default shares must be non-negative and sum to 1, "
            f"not {shares.to_dict()}"
        )
        raise ValueError(msg)
    return shares / shares.sum()


def combine_wall_ages(
    qv: pd.DataFrame,
    titles: pd.DataFrame,
    fallback: pd.DataFrame,
    default: pd.Series,
    *,
    lot_older_gap_years: float = BETA_LOT_OLDER_GAP_YEARS,
) -> pd.DataFrame:
    """Combine the dwelling, lot, suburb and extent ages of each property.

    The rules (``.agents/plans/assigning-retaining-wall-types.md``, Method 1):

    - the dwelling and the lot both dated, the lot at least
      ``lot_older_gap_years`` older: half the dwelling's shares and half the
      lot's bin (``qv_and_lot``);
    - otherwise a dated dwelling: its shares (``qv``), so a dwelling older than
      its lot ignores the lot;
    - a dated lot alone: its bin (``title``);
    - neither: the suburb's shares (``suburb``), and with no suburb the
      extent's (``extent``).

    Args:
        qv: Output of :func:`property_qv_ages`, indexed by ``property_id``.
        titles: Indexed by ``property_id``, the lot's ``est_year`` and
            ``age_bin`` from exposure step 8, for the properties it dated.
        fallback: Indexed by ``property_id``, the suburb's
            :data:`AGE_SHARE_COLUMNS`; a row with any share missing is read as
            no suburb.
        default: The extent's share per bin, indexed by
            :data:`AGE_SHARE_COLUMNS`, summing to 1.
        lot_older_gap_years: How much older than the dwelling a lot has to be
            for its bin to be mixed in.

    Returns:
        Indexed by every ``property_id`` in ``qv``, ``titles`` or ``fallback``,
        the :data:`AGE_SHARE_COLUMNS`, each row summing to 1, and
        :data:`AGE_BASIS_COLUMN`, one of :data:`AGE_BASES`.

    Raises:
        ValueError: If a title bin is not one of
            :data:`~landloss.exposure.rw.age.AGE_BINS`, or the default shares
            are not a share per bin summing to 1.
    """
    columns = list(AGE_SHARE_COLUMNS)
    default = _normalised_default(default)
    index = (
        qv.index.union(titles.index).union(fallback.index).rename(PROPERTY_ID_COLUMN)
    )

    dwelling = qv.reindex(index)
    lot = titles.reindex(index)
    suburb = fallback.reindex(index)[columns].astype(float)
    lot_shares = _one_hot(lot[AGE_BIN_COLUMN])

    has_qv = dwelling[columns].notna().all(axis=1)
    has_lot = lot[AGE_BIN_COLUMN].notna()
    has_suburb = suburb.notna().all(axis=1)
    lot_older = (
        has_qv
        & has_lot
        & (
            lot[EST_YEAR_COLUMN].astype(float)
            <= dwelling[QV_YEAR_COLUMN].astype(float) - lot_older_gap_years
        )
    )

    shares = pd.DataFrame(
        np.tile(default.to_numpy(), (len(index), 1)), index=index, columns=columns
    )
    basis = pd.Series(EXTENT, index=index, dtype=object)

    by_suburb = ~has_qv & ~has_lot & has_suburb
    shares.loc[by_suburb] = (
        suburb[by_suburb].div(suburb[by_suburb].sum(axis=1), axis=0).to_numpy()
    )
    basis[by_suburb] = SUBURB

    by_lot = ~has_qv & has_lot
    shares.loc[by_lot] = lot_shares[by_lot].to_numpy()
    basis[by_lot] = TITLE

    shares.loc[has_qv] = dwelling.loc[has_qv, columns].to_numpy()
    basis[has_qv] = QV

    shares.loc[lot_older] = (1.0 - _LOT_SHARE) * dwelling.loc[
        lot_older, columns
    ].to_numpy() + _LOT_SHARE * lot_shares[lot_older].to_numpy()
    basis[lot_older] = QV_AND_LOT

    shares[AGE_BASIS_COLUMN] = basis
    return shares
