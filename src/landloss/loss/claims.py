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
    RW_DAMAGED_LENGTH_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    crossing_clearing_cost_incl_gst_nzd,
    crossing_replacement_cost_incl_gst_nzd,
    margin_rule_length_m,
)
from landloss.loss.qv_land_value import DAMAGED_LAND_RATE_COLUMN

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
# basis the Act compares on and the basis `settle` expects. It is averaged from
# the per-row rate `landloss.loss.qv_land_value.damaged_land_rates` adds.
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
        land: The contract's land table, one row per insured land polygon,
            with the rate its damaged land is valued at added by
            :func:`~landloss.loss.qv_land_value.damaged_land_rates`.

    Returns:
        A frame indexed by ``claim_id``, carrying
        :data:`DAMAGED_AREA_COLUMN`, :data:`LAND_RATE_COLUMN` and
        :data:`DWELLING_COUNT_COLUMN`.

    Raises:
        ValueError: If a column the calculation needs is missing, or if a
            claim's polygons disagree about the dwelling count.
    """
    for column in (CLAIM_ID_COLUMN, DAMAGED_LAND_RATE_COLUMN, DWELLING_COUNT_COLUMN):
        if column not in land.columns:
            msg = f"the land table carries no {column!r} column"
            raise ValueError(msg)

    rows = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
            DAMAGED_AREA_COLUMN: damaged_area_m2(land),
            DAMAGED_LAND_RATE_COLUMN: land[DAMAGED_LAND_RATE_COLUMN].to_numpy(
                dtype=float
            ),
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

    rows["_valued"] = rows[DAMAGED_AREA_COLUMN] * rows[DAMAGED_LAND_RATE_COLUMN]
    grouped = rows.groupby(CLAIM_ID_COLUMN)
    claims = grouped.agg(
        **{
            DAMAGED_AREA_COLUMN: (DAMAGED_AREA_COLUMN, "sum"),
            DWELLING_COUNT_COLUMN: (DWELLING_COUNT_COLUMN, "first"),
            "_valued": ("_valued", "sum"),
            "_mean_rate": (DAMAGED_LAND_RATE_COLUMN, "mean"),
        }
    )
    area = claims[DAMAGED_AREA_COLUMN]
    claims[LAND_RATE_COLUMN] = np.where(
        area > 0, claims["_valued"] / area.where(area > 0), claims["_mean_rate"]
    )
    return claims[[DAMAGED_AREA_COLUMN, LAND_RATE_COLUMN, DWELLING_COUNT_COLUMN]]


def damaged_walls(rw: pd.DataFrame) -> pd.DataFrame:
    """Return the retaining walls a settlement has to replace.

    A wall is damaged when it failed in shaking or sits on evacuated ground,
    and since a damaged wall is replaced rather than repaired, **either flag
    being true is one replacement, not one per flag**. **Inundated ground does
    not damage a wall** (the lead, 2026-10-14): a wall only buried by another
    failure's deposit is not replaced, because the deposit is cleared as land.
    ``is_inundated`` stays on the table for information. An undamaged wall
    contributes nothing to the cap, so it is dropped here rather than priced at
    zero.

    Args:
        rw: The contract's retaining wall table, one row per insured wall.

    Returns:
        The rows with ``is_damaged_by_shaking`` or ``is_evacuated`` set.

    Raises:
        ValueError: If a flag column is missing.
    """
    flags = (IS_DAMAGED_BY_SHAKING_COLUMN, IS_EVACUATED_COLUMN)
    missing = [column for column in flags if column not in rw.columns]
    if missing:
        msg = f"the retaining wall table carries no {missing} column(s)"
        raise ValueError(msg)
    damaged = np.zeros(len(rw), dtype=bool)
    for flag in flags:
        damaged |= rw[flag].to_numpy(dtype=bool)
    return rw.loc[damaged]


# The wall a row of the retaining wall table is a piece of, written by `vul`
# after the contract columns. A name written out here, as the claim key is, and
# held to ``landloss.vul.loss_input.PARENT_RW_ID_COLUMN`` by a test.
PARENT_RW_ID_COLUMN = "parent_rw_id"
DAMAGED_LENGTH_COLUMN = "damaged_length_m"
REPLACED_LENGTH_COLUMN = "replaced_length_m"
VALUED_LENGTH_COLUMN = "valued_length_m"


def wall_lengths_by_piece(walls: pd.DataFrame) -> pd.DataFrame:
    """Return the length each damaged wall piece is replaced and valued over.

    **Worked per wall, not per piece** (2026-10-14). The pieces are grouped on
    their parent wall, so a wall shared by two claims gets the margin once, and
    one damaged at two separate places still gets one margin, not one per
    stretch. For a wall whose pieces are damaged over ``D`` metres in all:

    - **replaced length** = :func:`~landloss.loss.pricing.margin_rule_length_m`
      of ``D``, which is what the repair prices;
    - **valued length** = the same, but no longer than the wall itself -- the
      sum of its pieces' ``rw_length`` -- because the cap never counts more
      wall than the property had. A wall that failed whole is valued over its
      length and replaced over its length plus the margin.

    Each is shared over the pieces in proportion to their damaged length, so
    the pieces add back to the wall's. A piece's damaged length is its
    ``rw_damaged_length`` where the table carries one, else its whole
    ``rw_length``: a table written before the column settles at the whole
    length. A piece damaged by shaking is damaged over its whole ``rw_length``.
    A wall with no damaged length at all is replaced over none.

    Args:
        walls: Damaged rows of the contract's retaining wall table
            (:func:`damaged_walls`), with ``parent_rw_id`` where walls are split
            across claims; without it each row is its own wall.

    Returns:
        A frame on ``walls``' index with ``damaged_length_m``,
        ``replaced_length_m`` and ``valued_length_m``, one row per piece.

    Raises:
        ValueError: If ``parent_rw_id`` is present but missing on any piece.
    """
    length = walls[RW_LENGTH_COLUMN].to_numpy(dtype=float)
    damaged = (
        walls[RW_DAMAGED_LENGTH_COLUMN].fillna(0.0).to_numpy(dtype=float)
        if RW_DAMAGED_LENGTH_COLUMN in walls.columns
        else length
    )
    if IS_DAMAGED_BY_SHAKING_COLUMN in walls.columns:
        # A wall that fails in shaking is damaged over its whole length.
        shaken = walls[IS_DAMAGED_BY_SHAKING_COLUMN].astype(bool).to_numpy()
        damaged = np.where(shaken, length, damaged)
    damaged = np.minimum(damaged, length)
    parent = walls[RW_ID_COLUMN].astype(object)
    if PARENT_RW_ID_COLUMN in walls.columns:
        # vul step 10 gives every piece its wall, so a gap is a broken table,
        # not an old one (the lead, 2026-10-14).
        missing = walls[PARENT_RW_ID_COLUMN].isna()
        if missing.any():
            msg = (
                f"{int(missing.sum())} wall pieces have no {PARENT_RW_ID_COLUMN}, "
                f"for example {walls.loc[missing, RW_ID_COLUMN].iloc[0]}: rerun "
                "vul step 10"
            )
            raise ValueError(msg)
        parent = walls[PARENT_RW_ID_COLUMN].astype(object)
    grouped = pd.DataFrame(
        {"parent": parent.to_numpy(dtype=object), "length": length, "damaged": damaged}
    ).groupby("parent")
    wall_length = grouped["length"].transform("sum").to_numpy()
    wall_damaged = grouped["damaged"].transform("sum").to_numpy()

    has_damage = wall_damaged > 0
    share = np.divide(
        damaged, wall_damaged, out=np.zeros_like(damaged), where=has_damage
    )
    replaced = np.where(has_damage, margin_rule_length_m(wall_damaged), 0.0)
    valued = np.minimum(replaced, wall_length)
    return pd.DataFrame(
        {
            DAMAGED_LENGTH_COLUMN: damaged,
            REPLACED_LENGTH_COLUMN: replaced * share,
            VALUED_LENGTH_COLUMN: valued * share,
        },
        index=walls.index,
    )


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


# The flags that mean a crossing is broken and must be replaced: liquefaction
# under it, carried as the culvert's `is_damaged` and the bridge's
# `is_damaged_by_shaking`, or a landslide taking the ground it stands on. A
# crossing only inundated is buried but whole, and is cleared instead.
CROSSING_REPLACEMENT_FLAGS = (
    IS_DAMAGED_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
)

# What `crossing_costs_by_claim` writes.
CROSSING_REPAIR_COLUMN = "crossing_repair_cost_incl_gst_nzd"
CROSSING_UDV_COLUMN = "bridge_culvert_udv_incl_gst_nzd"
CROSSINGS_REPLACED_COLUMN = "crossings_replaced"
CROSSINGS_CLEARED_COLUMN = "crossings_cleared"


def crossing_costs_by_claim(
    culverts: pd.DataFrame, bridges: pd.DataFrame, *, policy: PolicySettings
) -> pd.DataFrame:
    """Return what each claim's damaged culverts and bridges cost and are worth.

    Each crossing is priced on its own and the claim's are summed:

    - **replaced** where any of :data:`CROSSING_REPLACEMENT_FLAGS` is set, at
      :func:`~landloss.loss.pricing.crossing_replacement_cost_incl_gst_nzd`.
      A replacement takes the place of a clearing, so a crossing broken and
      buried is charged the replacement alone;
    - **cleared** where it is only inundated, at
      :func:`~landloss.loss.pricing.crossing_clearing_cost_incl_gst_nzd`.

    Culverts and bridges are priced alike. A damaged crossing's undepreciated
    value is its replacement cost whichever remedy it needs: the structure is
    worth what it costs to build, whether or not it was broken. The sub-cap
    then limits what that adds to the cap, in
    :func:`~landloss.loss.settlement.land_cover_cap_nzd`.

    Args:
        culverts: The contract's culvert table.
        bridges: The contract's bridge table.
        policy: The settings this scenario runs under, which carry the GST rate.

    Returns:
        Indexed by claim, for claims with a damaged crossing:
        :data:`CROSSING_REPAIR_COLUMN`, :data:`CROSSING_UDV_COLUMN`,
        :data:`CROSSINGS_REPLACED_COLUMN` and :data:`CROSSINGS_CLEARED_COLUMN`.
    """
    frames = []
    for table in (culverts, bridges):
        damaged = damaged_crossings(table)
        if damaged.empty:
            continue
        replaced = np.zeros(len(damaged), dtype=bool)
        for flag in CROSSING_REPLACEMENT_FLAGS:
            if flag in damaged.columns:
                replaced |= damaged[flag].to_numpy(dtype=bool)
        frames.append(
            pd.DataFrame(
                {
                    CLAIM_ID_COLUMN: damaged[CLAIM_ID_COLUMN].to_numpy(),
                    "replaced": replaced,
                }
            )
        )
    columns = [
        CROSSING_REPAIR_COLUMN,
        CROSSING_UDV_COLUMN,
        CROSSINGS_REPLACED_COLUMN,
        CROSSINGS_CLEARED_COLUMN,
    ]
    if not frames:
        return pd.DataFrame(columns=columns, index=pd.Index([], name=CLAIM_ID_COLUMN))
    crossings = pd.concat(frames, ignore_index=True)
    replacement = float(crossing_replacement_cost_incl_gst_nzd(policy=policy))
    clearing = crossing_clearing_cost_incl_gst_nzd(policy=policy)
    crossings[CROSSING_REPAIR_COLUMN] = np.where(
        crossings["replaced"], replacement, clearing
    )
    crossings[CROSSING_UDV_COLUMN] = replacement
    crossings[CROSSINGS_REPLACED_COLUMN] = crossings["replaced"].astype(int)
    crossings[CROSSINGS_CLEARED_COLUMN] = (~crossings["replaced"]).astype(int)
    return crossings.groupby(CLAIM_ID_COLUMN)[columns].sum()
