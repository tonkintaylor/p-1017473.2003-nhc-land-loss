"""Settle each claim: the repair cost, the cap, and what NHC pays.

    uv run --frozen python src/scripts/landloss/loss/steps/s1_settlement/s1_gen_settlement.py

Step 0 builds the cap. This step builds the **other half of the comparison** and
calls :func:`~landloss.loss.settlement.settle`, which pays
``min(repair cost, cap)`` less the excess.

How each repair cost is arrived at, and every one of them rests on an
assumption named here:

- **A damaged retaining wall** is replaced, priced at the beta flat rate on its
  face area with the site multiplier on top.
- **Damaged land on a claim with no wall** is repaired by building a wall
  that was never there, sized by how much ground went -- by area, and by
  volume where an inundated depth makes one available. It is a remediation
  cost, not an asset, so it reaches the repair cost and **never the cap**: a
  wall that did not exist has no undepreciated value to contribute.
- **Damaged land on a claim that has a wall costs no second wall.** The wall
  that is there is taken to be damaged and is replaced, and that replacement
  is the whole of the wall cost: one wall stands on the site, so the claim is
  charged for one wall (2026-09-29).
- **Professional fees are charged once per claim that involves a wall** --
  consent, design, engineering, health and safety, project management and
  survey, $5,100 excluding GST from the costing tool's own fee table. They are
  added before the site multiplier, so a difficult site costs more to design and
  consent as well as more to build. A wall is what gets designed and consented:
  clearing spoil on its own does not attract them, and neither does a Canterbury
  liquefaction cost, that being a settled amount rather than a works estimate.
- **Landslide spoil is cleared at a rate per cubic metre**, on top of whatever
  wall the ground needs. The volume still sets the earthworks rating as well,
  which is worth watching for a double count -- the rating is how hard the site
  is to build on, this is carting material away. The rate is the costing tool's
  own "Clear site: Load, cart and tip material", $150 per cubic metre excluding
  GST (**L-33**).
- **Liquefaction land damage** carries its own settled cost from the Canterbury
  database, which `vul` now sends through the contract. It is added on top,
  because it is a different mechanism from the ground a landslide took.
- **A damaged culvert or bridge** contributes its sub-cap limit to both sides,
  on the agreed reading that its real cost and value both exceed it. Adding the
  same figure to the repair cost and the cap settles it at the limit, whatever
  the true numbers are.

The three site ratings are **proxies off exposure layers**, not measurements:
driveway length for construction access, ground slope for constructability, and
the inundated volume for earthworks. See :mod:`landloss.loss.pricing`, where
every band is defined and marked as invented.

**The Canterbury costs are 2010/2011 dollars and are not inflated**, only
grossed up for GST. They are compared against land values and wall rates in
today's dollars, which understates their side of the comparison by however much
construction has risen since. Nothing in the repository supplies an index to
correct it with.

What it runs over comes from ``config.py`` beside it.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.gst import add_gst
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LIQ_LD_COST_COLUMN,
    REALISATION_ID_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
)
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    BETA_SIZE_CLASS_HEIGHT_M,
    SiteRatings,
    beta_wall_face_area_m2,
    beta_wall_rate_excl_gst_nzd_per_m2,
    beta_wall_repair_cost_incl_gst_nzd,
    classify_constructability,
    classify_construction_access,
    classify_inundation_earthworks,
    classify_landslide_wall_size,
    inundation_removal_cost_incl_gst_nzd,
    inundation_volume_m3,
    landslide_wall_length_m,
    professional_fees_incl_gst_nzd,
)
from landloss.loss.settlement import DamagedClaim, settle
from scripts.landloss.loss.steps.s0_land_cover_cap.s0_gen_land_cover_cap import (
    CAP_COLUMN,
    HAS_CROSSING_COLUMN,
    RW_UDV_COLUMN,
    land_cover_cap_path,
)
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "loss"
OUT_STEM = "settlement"
EXPOSURE_DIR = TEMP_DIR / "exposure"

RULE = "-" * 72

# The four tables this reads, in the order the contract lists them.
LOSS_TABLES = ("land", "rw", "culverts", "bridges")

# Exposure layers the site rating proxies come off. Read rather than imported
# through a path function, because they belong to steps this module does not
# otherwise depend on.
DRIVEWAYS_STEM = "driveways"
TERRAIN_STEM = "terrain-by-address"
ADDRESS_TO_CLAIM_STEM = "address-to-claim"
DRIVEWAY_LENGTH_COLUMN = "driveway_length_m"
SLOPE_COLUMN = "slope_deg"
ADDRESS_ID_COLUMN = "address_id"

# What the step writes beyond the claim key.
ACCESS_COLUMN = "construction_access"
EARTHWORKS_COLUMN = "earthworks_required"
CONSTRUCTABILITY_COLUMN = "constructability_reinstatement"
WALL_REPAIR_COLUMN = "wall_repair_cost_incl_gst_nzd"
LAND_REPAIR_COLUMN = "land_repair_cost_incl_gst_nzd"
LIQ_REPAIR_COLUMN = "liquefaction_repair_cost_incl_gst_nzd"
CROSSING_REPAIR_COLUMN = "crossing_repair_cost_incl_gst_nzd"
SPOIL_REPAIR_COLUMN = "spoil_removal_cost_incl_gst_nzd"
SPOIL_VOLUME_COLUMN = "inundated_volume_m3"
FEES_COLUMN = "professional_fees_incl_gst_nzd"
REPAIR_COST_COLUMN = "repair_cost_incl_gst_nzd"
SETTLEMENT_COLUMN = "settlement_incl_gst_nzd"
EXCESS_COLUMN = "excess_nzd"
CAPPED_COLUMN = "capped"
SYNTHETIC_WALL_COLUMN = "land_repaired_by_new_wall"
# The shape of the wall invented to reinstate landslide ground, written out so
# that the damaged area and the wall it buys can be read side by side. Whether
# they look reasonable together is the check nobody can do on a cost alone.
LANDSLIDE_REPAIR_AREA_COLUMN = "landslide_damaged_area_m2"
NEW_WALL_SIZE_COLUMN = "new_wall_size"
NEW_WALL_HEIGHT_COLUMN = "new_wall_height_m"
NEW_WALL_LENGTH_COLUMN = "new_wall_length_m"


def settlement_path(realisation_id: int, *, pilot: bool) -> Path:
    """Return the file a run writes one realisation's settlements to.

    Args:
        realisation_id: The modelled earthquake.
        pilot: Whether the run is over the small Wellington pilot box.

    Returns:
        The path, under ``temp/loss``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.parquet"


def _exposure(stem: str, *, pilot: bool, geo: bool) -> pd.DataFrame:
    """Read one exposure layer, geoparquet or plain."""
    suffix = "-pilot" if pilot else ""
    extension = "geoparquet" if geo else "parquet"
    path = EXPOSURE_DIR / f"{stem}{suffix}.{extension}"
    return gpd.read_parquet(path) if geo else pd.read_parquet(path)


def site_ratings_by_claim(land: pd.DataFrame, *, pilot: bool) -> pd.DataFrame:
    """Return the three site ratings for every claim, from the proxies.

    Construction access comes from the **longest** driveway on the claim and
    constructability from the **steepest** address on it, both taking the worst
    case where a claim has several. Earthworks comes from the inundated volume
    summed over the claim's polygons, which is the one rating with a basis in
    the contract rather than in a proxy.

    A claim with no driveway routed and no address matched rates easy on both
    proxies, which flatters it. Nothing distinguishes that from a genuinely
    easy site.

    Args:
        land: The contract's land table.
        pilot: Whether the run is over the small Wellington pilot box.

    Returns:
        A frame indexed by ``claim_id`` carrying the three ratings.
    """
    claim_ids = pd.Index(land[CLAIM_ID_COLUMN].unique(), name=CLAIM_ID_COLUMN)

    driveways = _exposure(DRIVEWAYS_STEM, pilot=pilot, geo=True)
    longest = driveways.groupby(CLAIM_ID_COLUMN)[DRIVEWAY_LENGTH_COLUMN].max()

    terrain = _exposure(TERRAIN_STEM, pilot=pilot, geo=True)
    to_claim = _exposure(ADDRESS_TO_CLAIM_STEM, pilot=pilot, geo=False)
    steepest = (
        terrain[[ADDRESS_ID_COLUMN, SLOPE_COLUMN]]
        .merge(to_claim, on=ADDRESS_ID_COLUMN)
        .groupby(CLAIM_ID_COLUMN)[SLOPE_COLUMN]
        .max()
    )

    volume = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)["volume"]
        .sum()
    )

    return pd.DataFrame(
        {
            ACCESS_COLUMN: classify_construction_access(
                longest.reindex(claim_ids).fillna(0.0).to_numpy()
            ),
            CONSTRUCTABILITY_COLUMN: classify_constructability(
                steepest.reindex(claim_ids).fillna(0.0).to_numpy()
            ),
            EARTHWORKS_COLUMN: classify_inundation_earthworks(
                volume.reindex(claim_ids).fillna(0.0).to_numpy()
            ),
        },
        index=claim_ids,
    )


def ratings_for(frame: pd.DataFrame, ratings: pd.DataFrame) -> SiteRatings:
    """Return the site ratings of each row's claim, aligned to the frame."""
    aligned = ratings.reindex(frame[CLAIM_ID_COLUMN].to_numpy())
    return SiteRatings(
        construction_access=aligned[ACCESS_COLUMN].to_numpy(),
        earthworks_required=aligned[EARTHWORKS_COLUMN].to_numpy(),
        constructability_reinstatement=aligned[CONSTRUCTABILITY_COLUMN].to_numpy(),
    )


def wall_repair_by_claim(
    rw: pd.DataFrame, ratings: pd.DataFrame, *, policy: PolicySettings
) -> pd.Series:
    """Return each claim's cost of replacing the retaining walls that failed.

    Args:
        rw: The contract's retaining wall table.
        ratings: The site ratings per claim.
        policy: The settings this scenario runs under.

    Returns:
        The cost per claim, indexed by ``claim_id``. A claim with no damaged
        wall does not appear.
    """
    damaged = loss_claims.damaged_walls(rw)
    if damaged.empty:
        return pd.Series(dtype=float)
    face_area = beta_wall_face_area_m2(
        damaged[RW_SIZE_COLUMN].to_numpy(), damaged[RW_LENGTH_COLUMN].to_numpy()
    )
    cost = beta_wall_repair_cost_incl_gst_nzd(
        face_area,
        ratings=ratings_for(damaged, ratings),
        # The same per-wall rate step 0 values the wall at. Pricing the repair
        # off one rate while the cap is built off another would put the two
        # sides of min(repair, cap) on different constructions.
        rate_excl_gst_nzd_per_m2=beta_wall_rate_excl_gst_nzd_per_m2(
            damaged[RW_ID_COLUMN].to_numpy()
        ),
        policy=policy,
    )
    return (
        pd.DataFrame(
            {CLAIM_ID_COLUMN: damaged[CLAIM_ID_COLUMN].to_numpy(), "cost": cost}
        )
        .groupby(CLAIM_ID_COLUMN)["cost"]
        .sum()
    )


def land_repair_by_claim(
    land: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    walled: pd.Index,
    policy: PolicySettings,
) -> pd.DataFrame:
    """Return the cost of holding land a landslide took, by claim.

    **A wall is invented only where the property had none.** Where one was
    already there it is taken to be damaged and is replaced, and that
    replacement is the whole of the wall cost -- there is one wall on the
    site, so the claim is charged for one wall. Pricing a replacement and an
    invented wall on the same claim charged twice for the same structure, once
    at $74,302 against a slip of 1.4 square metres.

    The area held is the landslide total, which `vul` has already unioned over
    the evacuated and inundated footprints -- so a claim whose slip evacuated
    ground outside the boundary, leaving no insured evacuated area, still gets
    a wall for what was inundated inside it.

    The invented wall is sized on the ground alone. It needs no floor at the
    existing wall's size, because a property with a wall does not reach this
    path at all.

    Args:
        land: The contract's land table.
        ratings: The site ratings per claim.
        walled: The claims whose retaining wall is being replaced. They are
            charged for that wall and no other.
        policy: The settings this scenario runs under.

    Returns:
        A frame indexed by ``claim_id`` with the cost and whether a wall was
        invented for it.
    """
    per_claim = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "area": land[LANDSLIDE_AREA_COLUMN].fillna(0.0).to_numpy(),
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)[["area", "volume"]]
        .sum()
    )

    per_claim["damaged"] = per_claim["area"].clip(lower=0.0)
    # One wall per property. A claim whose own wall is being replaced does not
    # also get one invented for it.
    needs_wall = (per_claim["damaged"] > 0) & ~per_claim.index.isin(walled)
    out = pd.DataFrame(
        {
            LAND_REPAIR_COLUMN: 0.0,
            SYNTHETIC_WALL_COLUMN: needs_wall,
            LANDSLIDE_REPAIR_AREA_COLUMN: per_claim["damaged"],
            NEW_WALL_SIZE_COLUMN: "",
            NEW_WALL_HEIGHT_COLUMN: 0.0,
            NEW_WALL_LENGTH_COLUMN: 0.0,
        },
        index=per_claim.index,
    )
    if not needs_wall.any():
        return out

    building = per_claim.loc[needs_wall]
    size = classify_landslide_wall_size(
        building["damaged"].to_numpy(), building["volume"].to_numpy()
    )
    length = landslide_wall_length_m(building["damaged"].to_numpy())
    out.loc[needs_wall, NEW_WALL_SIZE_COLUMN] = size
    out.loc[needs_wall, NEW_WALL_HEIGHT_COLUMN] = [
        BETA_SIZE_CLASS_HEIGHT_M[value] for value in size
    ]
    out.loc[needs_wall, NEW_WALL_LENGTH_COLUMN] = length
    face_area = beta_wall_face_area_m2(size, length)
    aligned = ratings.reindex(building.index)
    out.loc[needs_wall, LAND_REPAIR_COLUMN] = beta_wall_repair_cost_incl_gst_nzd(
        face_area,
        ratings=SiteRatings(
            construction_access=aligned[ACCESS_COLUMN].to_numpy(),
            earthworks_required=aligned[EARTHWORKS_COLUMN].to_numpy(),
            constructability_reinstatement=aligned[CONSTRUCTABILITY_COLUMN].to_numpy(),
        ),
        policy=policy,
    )
    return out


def spoil_by_claim(land: pd.DataFrame) -> pd.Series:
    """Return the volume of landslide spoil on each claim.

    Args:
        land: The contract's land table.

    Returns:
        The volume per claim, indexed by ``claim_id``.
    """
    return (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)["volume"]
        .sum()
    )


def liquefaction_repair_by_claim(land: pd.DataFrame) -> pd.Series:
    """Return each claim's Canterbury settled cost, on the Act's GST basis.

    The contract carries the cost excluding GST, in 2010/2011 dollars. It is
    grossed up here and **not inflated**, because nothing in the repository
    supplies an index; see the module docstring.

    Args:
        land: The contract's land table.

    Returns:
        The cost per claim, indexed by ``claim_id``.
    """
    costs = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "cost": land[LIQ_LD_COST_COLUMN].fillna(0.0).to_numpy(),
            }
        )
        .groupby(CLAIM_ID_COLUMN)["cost"]
        .sum()
    )
    return add_gst(costs)


def describe_ratings(claims):
    """Print how the proxies rated the population."""
    print(RULE)
    print("Site ratings, all three proxied and none measured:")
    for column, label in (
        (ACCESS_COLUMN, "construction access (driveway length)"),
        (CONSTRUCTABILITY_COLUMN, "constructability (ground slope)"),
        (EARTHWORKS_COLUMN, "earthworks (inundated volume)"),
    ):
        counts = claims[column].value_counts().reindex(["E", "M", "D"]).fillna(0)
        spread = ", ".join(f"{int(n):,} {r}" for r, n in counts.items())
        print(f"  {label}: {spread}")


def describe_repair(claims):
    """Print where the repair cost comes from."""
    print(RULE)
    invented = int(claims[SYNTHETIC_WALL_COLUMN].sum())
    print(f"Repair cost: {claims[REPAIR_COST_COLUMN].sum():,.0f} NZD including GST")
    for column, label in (
        (WALL_REPAIR_COLUMN, "replacing damaged retaining walls"),
        (LAND_REPAIR_COLUMN, "new walls to reinstate landslide ground"),
        (SPOIL_REPAIR_COLUMN, "clearing landslide spoil off the ground"),
        (FEES_COLUMN, "consent, design, engineering, H&S, PM and survey"),
        (LIQ_REPAIR_COLUMN, "Canterbury liquefaction land costs"),
        (CROSSING_REPAIR_COLUMN, "culverts and bridges at their sub-cap"),
    ):
        total = claims[column].sum()
        reached = int((claims[column] > 0).sum())
        print(f"  {total:>16,.0f} NZD  {label} ({reached:,} claims)")
    # One wall per property, so these two never overlap. Printed rather than
    # asserted, because the day they do overlap is the day to look.
    replaced = int(
        (
            (claims[WALL_REPAIR_COLUMN] > 0)
            & (claims[LANDSLIDE_REPAIR_AREA_COLUMN] > 0)
        ).sum()
    )
    both = int(
        ((claims[WALL_REPAIR_COLUMN] > 0) & (claims[LAND_REPAIR_COLUMN] > 0)).sum()
    )
    print(
        f"  A wall was invented on {invented:,} claims that had none. On "
        f"{replaced:,} more the landslide ground came with a wall already "
        f"there, which is replaced instead -- {both:,} are charged for both"
    )


def describe_settlement(claims, policy):
    """Print what is paid, and which constraint bound."""
    print(RULE)
    paid = claims[claims[SETTLEMENT_COLUMN] > 0]
    print(
        f"Settlement: {claims[SETTLEMENT_COLUMN].sum():,.0f} NZD over "
        f"{len(paid):,} claims that are paid anything"
    )
    # `capped` is true of almost every claim with no damaged land, by
    # construction: there the cap is the wall's undepreciated value and the
    # repair cost is that same value times one plus the site multiplier, so the
    # cap is below it whenever the multiplier is above zero. Reporting the total
    # alone would read as a finding when it is an artefact, so the two are split.
    capped = claims[CAPPED_COLUMN]
    with_land = capped & (claims[loss_claims.DAMAGED_AREA_COLUMN] > 0)
    print(
        f"  {int(capped.sum()):,} claims settle at the land cover cap, but only "
        f"{int(with_land.sum()):,} of them have damaged land. On the rest the cap "
        "is the wall's value and the repair cost is that value plus the site "
        "multiplier, so capping is arithmetic rather than a result."
    )
    damaged = claims[REPAIR_COST_COLUMN] > 0
    zeroed = int((damaged & (claims[SETTLEMENT_COLUMN] == 0)).sum())
    print(
        f"  {zeroed:,} claims have damage but pay nothing, the excess of "
        f"{policy.excess_rate:.0%} of what was payable, floored at "
        f"{policy.excess_min_nzd:,.0f} and capped at "
        f"{policy.excess_max_nzd:,.0f} NZD, having taken all of it"
    )


def check_cap_against_step_0(claims, realisation_id, *, pilot):
    """Compare this step's cap with step 0's, which built it independently."""
    path = land_cover_cap_path(realisation_id, pilot=pilot)
    if not path.exists():
        print(f"  Step 0's caps are not on disk at {path}; cap not cross-checked")
        return
    theirs = pd.read_parquet(path).set_index(CLAIM_ID_COLUMN)[CAP_COLUMN]
    ours = claims["land_cover_cap_incl_gst_nzd"]
    gap = (ours - theirs.reindex(ours.index)).abs().max()
    print(f"  Cap agrees with step 0 to {gap:,.6f} NZD at worst")


def main(*, pilot, realisation_ids):
    """Settle every claim and write the result, per realisation.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        realisation_ids: Which modelled earthquakes to settle.
    """
    policy = PolicySettings()

    for realisation_id in realisation_ids:
        print(f"\nSettling realisation {realisation_id} ...", flush=True)
        tables = {
            name: gpd.read_parquet(loss_input_path(name, realisation_id, pilot=pilot))
            for name in LOSS_TABLES
        }
        land, rw = tables["land"], tables["rw"]

        claims = loss_claims.land_by_claim(land)
        ratings = site_ratings_by_claim(land, pilot=pilot)
        claims = claims.join(ratings)

        # The size and length of each claim's damaged wall. Not a deduction
        # from the land any more -- only the floor the new wall is built to,
        # because ground that already needed a wall of that size still does.
        # The claims whose own wall is being replaced. They are charged for
        # that wall and never for one invented beside it.
        walled = pd.Index(loss_claims.damaged_walls(rw)[CLAIM_ID_COLUMN].unique())

        claims[WALL_REPAIR_COLUMN] = (
            wall_repair_by_claim(rw, ratings, policy=policy)
            .reindex(claims.index)
            .fillna(0.0)
        )
        land_repair = land_repair_by_claim(
            land,
            ratings,
            walled=walled,
            policy=policy,
        ).reindex(claims.index)
        claims[LAND_REPAIR_COLUMN] = land_repair[LAND_REPAIR_COLUMN].fillna(0.0)
        claims[SYNTHETIC_WALL_COLUMN] = (
            land_repair[SYNTHETIC_WALL_COLUMN].fillna(value=False).astype(bool)
        )
        claims[LANDSLIDE_REPAIR_AREA_COLUMN] = land_repair[
            LANDSLIDE_REPAIR_AREA_COLUMN
        ].fillna(0.0)
        claims[NEW_WALL_SIZE_COLUMN] = land_repair[NEW_WALL_SIZE_COLUMN].fillna("")
        claims[NEW_WALL_HEIGHT_COLUMN] = land_repair[NEW_WALL_HEIGHT_COLUMN].fillna(0.0)
        claims[NEW_WALL_LENGTH_COLUMN] = land_repair[NEW_WALL_LENGTH_COLUMN].fillna(0.0)
        claims[LIQ_REPAIR_COLUMN] = (
            liquefaction_repair_by_claim(land).reindex(claims.index).fillna(0.0)
        )
        # Clearing the spoil is now its own line as well as setting the
        # earthworks rating, so a claim with buried ground and no wall is no
        # longer charged nothing for it.
        claims[SPOIL_VOLUME_COLUMN] = (
            spoil_by_claim(land).reindex(claims.index).fillna(0.0)
        )
        claims[SPOIL_REPAIR_COLUMN] = inundation_removal_cost_incl_gst_nzd(
            claims[SPOIL_VOLUME_COLUMN].to_numpy(), policy=policy
        )

        n_dwellings = loss_claims.dwelling_counts(
            claims.index.to_numpy(), claims.reset_index()
        )

        # A damaged crossing is settled at its sub-cap limit by adding that
        # figure to both sides: it contributes the limit to the cap, and the
        # same amount to the repair cost so the comparison does not reduce it.
        caps = pd.read_parquet(land_cover_cap_path(realisation_id, pilot=pilot))
        has_crossing = (
            caps.set_index(CLAIM_ID_COLUMN)[HAS_CROSSING_COLUMN]
            .reindex(claims.index)
            .fillna(value=False)
            .to_numpy()
        )
        crossing_limit = policy.bridge_culvert_limit_nzd(n_dwellings)
        claims[CROSSING_REPAIR_COLUMN] = np.where(has_crossing, crossing_limit, 0.0)

        # Professional fees are charged once on a claim that **involves a
        # wall**, whether one that failed or one invented to reinstate ground.
        # A wall is the thing that gets designed, consented and supervised.
        # Clearing spoil on its own does not: no consent, no producer statement,
        # no survey. Nor does a Canterbury liquefaction cost, which is what NHC
        # settled rather than a works estimate, so it already stands for
        # everything that claim cost.
        works = (claims[WALL_REPAIR_COLUMN] > 0) | (claims[LAND_REPAIR_COLUMN] > 0)
        claims[FEES_COLUMN] = np.where(
            works,
            professional_fees_incl_gst_nzd(
                ratings=ratings_for(claims.reset_index(), ratings), policy=policy
            ),
            0.0,
        )

        claims[REPAIR_COST_COLUMN] = (
            claims[WALL_REPAIR_COLUMN]
            + claims[LAND_REPAIR_COLUMN]
            + claims[SPOIL_REPAIR_COLUMN]
            + claims[FEES_COLUMN]
            + claims[LIQ_REPAIR_COLUMN]
            + claims[CROSSING_REPAIR_COLUMN]
        )

        # The invented wall is a remediation cost and never an asset, so the
        # undepreciated value handed to the cap is the real walls' alone, taken
        # from what step 0 priced.
        rw_udv = (
            caps.set_index(CLAIM_ID_COLUMN)[RW_UDV_COLUMN]
            .reindex(claims.index)
            .fillna(0.0)
            .to_numpy()
        )
        claims[RW_UDV_COLUMN] = rw_udv

        settlement = settle(
            DamagedClaim(
                damaged_area_m2=claims[loss_claims.DAMAGED_AREA_COLUMN].to_numpy(),
                land_rate_incl_gst_nzd_per_m2=claims[
                    loss_claims.LAND_RATE_COLUMN
                ].to_numpy(),
                repair_cost_incl_gst_nzd=claims[REPAIR_COST_COLUMN].to_numpy(),
                n_dwellings=n_dwellings,
                retaining_wall_udv_incl_gst_nzd=rw_udv,
                bridge_culvert_udv_incl_gst_nzd=np.where(
                    has_crossing, crossing_limit, 0.0
                ),
            ),
            policy=policy,
        )
        claims["land_cover_cap_incl_gst_nzd"] = settlement.land_cover_cap_nzd
        claims[EXCESS_COLUMN] = settlement.excess_nzd
        claims[SETTLEMENT_COLUMN] = settlement.settlement_nzd
        claims[CAPPED_COLUMN] = settlement.capped

        describe_ratings(claims)
        describe_repair(claims)
        describe_settlement(claims, policy)
        check_cap_against_step_0(claims, realisation_id, pilot=pilot)

        out = claims.reset_index()
        out.insert(0, REALISATION_ID_COLUMN, realisation_id)
        out_path = settlement_path(realisation_id, pilot=pilot)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path)
        print(RULE)
        print(f"Wrote {len(out):,} claims to {out_path}")


if __name__ == "__main__":
    main(pilot=config.PILOT, realisation_ids=config.REALISATION_IDS)
