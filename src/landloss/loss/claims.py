"""Reading what upstream wrote onto the claims this module settles.

:mod:`landloss.loss.settlement` is arithmetic over arrays and knows nothing
about files. This module is the thin layer that fills those arrays from what
upstream writes, keeping the file and column names in one place instead of
spread across call sites.

**It also turns `vul`'s four tables into one row per claim.** The Act settles a
claim, not a polygon or a wall, so the areas and the structures have to be
brought onto `claim_id` before any of the arithmetic applies. Land polygons are
non-overlapping, so their damaged areas add; the market rate does not, and is
weighted by the damaged area it values.

**The damaged area is assembled from two causes.** `vul` gives each as an area:
landslide damage unioned over its evacuated and inundated footprints, and
liquefaction damage as its evacuated plus inundated land less their overlap,
no more than the polygon (**T-56**). The two are combined with a maximum rather
than a sum, so ground damaged by both causes is valued once. The combination is
not confirmed -- see `src/scripts/landloss/loss/status.md`.

**The dwelling count is the piece that has to come from here.** Both land
structure sub-caps and the excess are multiplied by the number of dwellings in
the residential building, and nothing in the `vul` contract carries one --
`vul` sends assets and their damage, not the property's occupancy. The count
comes instead from the module-level exposure step
``s3_dwellings_per_property``, which counts the address points standing inside
each claim property and writes one row per claim.

Two things about that count are worth carrying to the point of use, because
both bias a settlement and neither is visible in the number itself:

- **A dwelling is an address point, not a self-contained dwelling.** LINZ gives
  a unit of a block its own address, which is what makes the count work for
  flats, but it also gives one to a commercial tenancy and gives none to a
  minor dwelling that was never separately addressed. The count is a floor on a
  block and an over-count on a mixed-use building.
- **It scales three figures at once** -- the retaining wall sub-cap, the bridge
  and culvert sub-cap, and the excess. The first two raise a settlement and the
  third lowers it, so an error does not announce itself in the total; it has to
  be caught here.

The column names below are the contract with
:mod:`landloss.exposure.land.extent`, not an import from it: the four top-level
modules exchange data files rather than symbols, so the names are written out
in both places and a test holds them to each other. The four-table contract's
own names are a different case and *are* imported, from
:mod:`landloss.domain.loss_contract` -- `domain` is shared rather than one of
the four, and both `vul` and this module read the names from it.
"""

import numpy as np
import pandas as pd

from landloss.domain.loss_contract import (
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_DAMAGED_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LIQ_LD_AREA_COLUMN,
    MARKET_VALUE_COLUMN,
)

# The claim key, and the count written against it by the dwellings-per-property
# step. These must match what `landloss.exposure.land.extent` writes; see the
# module docstring for why they are not imported.
CLAIM_ID_COLUMN = "claim_id"
DWELLING_COUNT_COLUMN = "dwelling_count"

# How many identifiers an error message names before it stops. Enough to start
# looking with, short enough to read.
MAX_REPORTED_IDS = 5


def _report(values: pd.Index | pd.Series) -> str:
    """Return a short, stable list of identifiers for an error message.

    Args:
        values: The identifiers to name.

    Returns:
        Up to :data:`MAX_REPORTED_IDS` of them, sorted, with a count of the
        rest where there are more.
    """
    listed = sorted(pd.unique(pd.Series(values)))
    shown = ", ".join(repr(value) for value in listed[:MAX_REPORTED_IDS])
    if len(listed) > MAX_REPORTED_IDS:
        return f"{shown} and {len(listed) - MAX_REPORTED_IDS:,} more"
    return shown


def dwelling_counts(
    claim_ids: np.ndarray | pd.Series,
    dwellings_per_property: pd.DataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    count_column: str = DWELLING_COUNT_COLUMN,
) -> np.ndarray:
    """Return the dwelling count for each claim, in the order asked for.

    The result is what :class:`~landloss.loss.settlement.DamagedClaim` takes as
    ``n_dwellings``, aligned to the claims the caller is settling.

    A claim with no row in the property table is **refused rather than
    defaulted to one**. Defaulting would halve the cap on a pair of flats and
    halve the excess with it, which changes a settlement without changing
    anything visible about it; the same reasoning
    :func:`~landloss.loss.settlement.settle` applies to a count below one.

    Args:
        claim_ids: The claims to settle, in the order their other arrays are in.
        dwellings_per_property: One row per claim property, as
            ``s3_dwellings_per_property`` writes it.
        id_column: The claim identifier both are keyed on.
        count_column: The dwelling count column.

    Returns:
        The counts as a float array, one per entry in ``claim_ids``.

    Raises:
        ValueError: If the table lacks either column, carries a claim twice, or
            is missing a claim that was asked for; or if any count is below one
            or not finite.
    """
    for column in (id_column, count_column):
        if column not in dwellings_per_property.columns:
            msg = f"the property table carries no {column!r} column"
            raise ValueError(msg)

    counts = dwellings_per_property.set_index(id_column)[count_column]
    if counts.index.has_duplicates:
        duplicated = counts.index[counts.index.duplicated()]
        msg = (
            "the property table carries a claim more than once, so the count "
            f"to use is ambiguous: {_report(duplicated)}"
        )
        raise ValueError(msg)

    asked = pd.Series(np.asarray(claim_ids))
    found = asked.map(counts)
    if found.isna().any():
        msg = (
            "no dwelling count for "
            f"{_report(asked[found.isna()])}. A claim with no count is refused "
            "rather than settled as one dwelling, because that would halve the "
            "sub-caps without halving what is claimed against them."
        )
        raise ValueError(msg)

    values = found.to_numpy(dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values < 1):
        below = asked[(~np.isfinite(values)) | (values < 1)]
        msg = (
            f"dwelling count below one, or not finite, for {_report(below)}. "
            "Cover exists only where there is a residential building, so this "
            "is a missing count rather than a property with no dwellings."
        )
        raise ValueError(msg)
    return values


# What `land_by_claim` writes. The rate carries `_incl_gst_` because that is the
# basis the Act compares on and the basis `settle` expects; `vul` sends it as
# `$/m2 market value`, which says nothing about GST.
DAMAGED_AREA_COLUMN = "damaged_area_m2"
LAND_RATE_COLUMN = "land_rate_incl_gst_nzd_per_m2"

# Every damage flag either crossing table might carry. Which ones are present
# differs between culverts and bridges (**Q-09**), so they are looked for rather
# than required.
CROSSING_FLAG_COLUMNS = (
    IS_DAMAGED_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
)


def damaged_area_m2(land: pd.DataFrame) -> np.ndarray:
    """Return each land polygon's damaged insured area, over both causes.

    Both causes arrive as areas from `vul`. Landslide damage is unioned over
    the evacuated and inundated footprints. Liquefaction damage is the
    evacuated plus the inundated land less their overlap, capped at the
    polygon's insured area (**T-56**), and zero where the polygon has no state
    -- off the grid, undamaged, or not claimed.

    The two are combined with a **maximum, not a sum**: a polygon both
    liquefied and buried is one piece of damaged ground, and adding the two
    would value some of it twice. The maximum is exact where one cause reaches
    all of the ground the other did. Where the two lie on different parts of
    the polygon it undercounts, by at most the smaller of the two areas.

    Args:
        land: The contract's land table, one row per insured land polygon.

    Returns:
        The damaged area of each row, in the order given.

    Raises:
        ValueError: If a column the calculation needs is missing.
    """
    needed = (LIQ_LD_AREA_COLUMN, LANDSLIDE_AREA_COLUMN)
    missing = [column for column in needed if column not in land.columns]
    if missing:
        msg = f"the land table carries no {missing} column(s)"
        raise ValueError(msg)

    liquefied = np.nan_to_num(land[LIQ_LD_AREA_COLUMN].to_numpy(dtype=float))
    slipped = np.nan_to_num(land[LANDSLIDE_AREA_COLUMN].to_numpy(dtype=float))
    return np.maximum(liquefied, slipped)


def land_by_claim(land: pd.DataFrame) -> pd.DataFrame:
    """Return one row per claim: damaged area, market rate and dwelling count.

    The polygons of a claim are non-overlapping, so their damaged areas add.
    The rate does not: it is averaged, **weighted by the damaged area it
    values**, so the claim's value is what valuing each polygon separately and
    adding would have given. Where a claim has no damaged ground at all there
    is nothing to weight by, and the plain mean stands in -- it multiplies by a
    zero area either way.

    One polygon per claim today, in which case both reduce to that polygon's
    own rate.

    Args:
        land: The contract's land table, one row per insured land polygon.

    Returns:
        A frame indexed by ``claim_id``, carrying
        :data:`DAMAGED_AREA_COLUMN`, :data:`LAND_RATE_COLUMN` and
        :data:`DWELLING_COUNT_COLUMN`.

    Raises:
        ValueError: If a column the calculation needs is missing, or if a
            claim's polygons disagree about the dwelling count.
    """
    for column in (CLAIM_ID_COLUMN, MARKET_VALUE_COLUMN, DWELLING_COUNT_COLUMN):
        if column not in land.columns:
            msg = f"the land table carries no {column!r} column"
            raise ValueError(msg)

    rows = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
            DAMAGED_AREA_COLUMN: damaged_area_m2(land),
            MARKET_VALUE_COLUMN: land[MARKET_VALUE_COLUMN].to_numpy(dtype=float),
            DWELLING_COUNT_COLUMN: land[DWELLING_COUNT_COLUMN].to_numpy(),
        }
    )

    counts = rows.groupby(CLAIM_ID_COLUMN)[DWELLING_COUNT_COLUMN].nunique()
    if (counts > 1).any():
        msg = (
            "a claim's land polygons disagree about the dwelling count, so the "
            f"count to settle on is ambiguous: {_report(counts.index[counts > 1])}"
        )
        raise ValueError(msg)

    rows["_valued"] = rows[DAMAGED_AREA_COLUMN] * rows[MARKET_VALUE_COLUMN]
    grouped = rows.groupby(CLAIM_ID_COLUMN)
    claims = grouped.agg(
        **{
            DAMAGED_AREA_COLUMN: (DAMAGED_AREA_COLUMN, "sum"),
            DWELLING_COUNT_COLUMN: (DWELLING_COUNT_COLUMN, "first"),
            "_valued": ("_valued", "sum"),
            "_mean_rate": (MARKET_VALUE_COLUMN, "mean"),
        }
    )
    area = claims[DAMAGED_AREA_COLUMN]
    claims[LAND_RATE_COLUMN] = np.where(
        area > 0, claims["_valued"] / area.where(area > 0), claims["_mean_rate"]
    )
    return claims[[DAMAGED_AREA_COLUMN, LAND_RATE_COLUMN, DWELLING_COUNT_COLUMN]]


def damaged_walls(rw: pd.DataFrame) -> pd.DataFrame:
    """Return the retaining walls a settlement has to replace.

    A wall carries a flag per cause -- shaking, evacuation and inundation --
    and since a damaged wall is replaced rather than repaired, **any flag being
    true is one replacement, not one per flag**. An undamaged wall contributes
    nothing to the cap, so it is dropped here rather than priced at zero.

    Args:
        rw: The contract's retaining wall table, one row per insured wall.

    Returns:
        The rows carrying at least one damage flag.

    Raises:
        ValueError: If a flag column is missing.
    """
    flags = (IS_DAMAGED_BY_SHAKING_COLUMN, IS_EVACUATED_COLUMN, IS_INUNDATED_COLUMN)
    missing = [column for column in flags if column not in rw.columns]
    if missing:
        msg = f"the retaining wall table carries no {missing} column(s)"
        raise ValueError(msg)
    damaged = np.zeros(len(rw), dtype=bool)
    for flag in flags:
        damaged |= rw[flag].to_numpy(dtype=bool)
    return rw.loc[damaged]


def damaged_crossings(crossings: pd.DataFrame) -> pd.DataFrame:
    """Return the culverts or bridges a settlement has to replace.

    The two tables describe damage asymmetrically -- a culvert carries a
    generic ``is_damaged`` and no ``is_evacuated``, a bridge carries
    ``is_damaged_by_shaking`` and does -- and whether that is deliberate is
    **Q-09**. Rather than assume, this keeps a row where **any flag the table
    actually carries** is true, so neither table has to be special-cased and a
    flag appearing later is picked up without a change here.

    Args:
        crossings: The contract's culvert or bridge table.

    Returns:
        The rows carrying at least one damage flag. An empty table in, an empty
        table out.

    Raises:
        ValueError: If the table carries no damage flag at all.
    """
    flags = [column for column in CROSSING_FLAG_COLUMNS if column in crossings.columns]
    if not flags:
        msg = (
            "the crossing table carries none of the damage flags "
            f"{list(CROSSING_FLAG_COLUMNS)}, so nothing says what is damaged"
        )
        raise ValueError(msg)
    if crossings.empty:
        return crossings
    damaged = np.zeros(len(crossings), dtype=bool)
    for flag in flags:
        damaged |= crossings[flag].to_numpy(dtype=bool)
    return crossings.loc[damaged]
