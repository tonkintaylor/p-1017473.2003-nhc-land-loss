"""Build the land cover cap on each claim, from the four tables vul hands over.

The Act settles the lesser of the repair cost and a **land cover cap** built out
of the value of what was damaged::

    land cover cap = market value of the damaged insured land
                   + min(retaining wall undepreciated value, its sub-cap)
                   + min(bridge and culvert undepreciated value, its sub-cap)

This step builds that cap on real data, per realisation:

    uv run --frozen python src/scripts/landloss/loss/steps/s0_land_cover_cap/s0_gen_land_cover_cap.py

**It stops short of a settlement, and that is not an omission.** A settlement is
``min(repair cost, cap)`` less the excess, and no repair cost exists yet: a
wall's needs the three site ratings, of which only earthworks can be derived
(**Q-10**), and damaged land has no Land SOW behind it at all. The cap is the
half of the comparison that *can* be built, and it is the half most of the
study's questions are about -- how often each constraint binds, and what the
sub-caps are worth.

The arithmetic is all in :mod:`landloss.loss.settlement` and
:mod:`landloss.loss.pricing`, and the aggregation onto ``claim_id`` is in
:mod:`landloss.loss.claims`. This script adds **no modelling**. What it runs
over comes from ``config.py`` beside it, and the policy it runs under is
:class:`~landloss.loss.policy.PolicySettings` as the Act stands.

**A damaged crossing contributes its sub-cap limit outright.** Nothing prices a
culvert or a bridge, and the agreed simplification is that both its replacement
cost and its undepreciated value exceed the limit in every case, so
``min(udv, limit)`` is the limit and the cap can be built without a price. Every
crossing `vul` sends is wholly inside insured land, so all of them qualify.

Every wall, by contrast, is priced -- at the beta flat rate, an average of four
timber pole rates standing in for a construction type nothing supplies.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    REALISATION_ID_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    beta_wall_face_area_m2,
    beta_wall_height_m,
    beta_wall_rate_excl_gst_nzd_per_m2,
    beta_wall_udv_incl_gst_nzd,
)
from landloss.loss.settlement import (
    area_cap_bound,
    damaged_land_value_nzd,
    land_cover_cap_nzd,
    structure_contribution_nzd,
    structure_sub_cap_bound,
)
from landloss.vul.loss_input import WORLD_ID_COLUMN
from scripts.landloss.loss.steps.s0_land_cover_cap import config
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "loss"
OUT_STEM = "land-cover-cap"

RULE = "-" * 72

# The four tables this reads, in the order the contract lists them.
LOSS_TABLES = ("land", "rw", "culverts", "bridges")

# What the step writes, beyond the claim key and what `land_by_claim` carries.
# Each is kept because none can be recovered from the cap afterwards: the two
# components say which side of the cap the money is on, and the two flags say
# which constraint was reached.
LAND_VALUE_COLUMN = "land_value_incl_gst_nzd"
RW_UDV_COLUMN = "retaining_wall_udv_incl_gst_nzd"
RW_CONTRIBUTION_COLUMN = "retaining_wall_contribution_incl_gst_nzd"
CROSSING_UDV_COLUMN = "bridge_culvert_udv_incl_gst_nzd"
CROSSING_CONTRIBUTION_COLUMN = "bridge_culvert_contribution_incl_gst_nzd"
CAP_COLUMN = "land_cover_cap_incl_gst_nzd"
AREA_CAP_BOUND_COLUMN = "area_cap_bound"
RW_SUB_CAP_BOUND_COLUMN = "retaining_wall_sub_cap_bound"
HAS_CROSSING_COLUMN = "has_damaged_crossing"


def land_cover_cap_path(world_id: int, realisation_id: int, *, extent: str) -> Path:
    """Return the file a run writes one world and realisation's caps to.

    Args:
        world_id: The exposure world, one draw of the wall population.
        realisation_id: The modelled earthquake.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The path, under ``temp/loss``.
    """
    suffix = extent_suffix(extent)
    stem = f"{OUT_STEM}-w{world_id:03d}-r{realisation_id:03d}"
    return WORK_DIR / f"{stem}{suffix}.parquet"


def wall_udv_by_claim(rw: pd.DataFrame, *, policy: PolicySettings) -> pd.Series:
    """Return each claim's damaged retaining wall undepreciated value.

    Undepreciated value, not repair cost: the cap is built from what the wall
    was worth, and only the repair side needs the site ratings nothing supplies.
    Walls are summed over the claim, because the sub-cap applies to a claim's
    walls together rather than to each wall on its own.

    Args:
        rw: The contract's retaining wall table.
        policy: The settings this scenario runs under.

    Returns:
        The value per claim, indexed by ``claim_id``. A claim with no damaged
        wall does not appear.
    """
    damaged = loss_claims.damaged_walls(rw)
    if damaged.empty:
        return pd.Series(dtype=float)
    face_area = beta_wall_face_area_m2(
        damaged[RW_SIZE_COLUMN].to_numpy(), damaged[RW_LENGTH_COLUMN].to_numpy()
    )
    walls = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: damaged[CLAIM_ID_COLUMN].to_numpy(),
            # The same per-wall rate the repair cost uses. A concrete wall
            # valued at the timber rate would understate the cap while the
            # repair understated nothing, which is a bias with no basis.
            "udv": beta_wall_udv_incl_gst_nzd(
                face_area,
                rate_excl_gst_nzd_per_m2=beta_wall_rate_excl_gst_nzd_per_m2(
                    damaged[RW_ID_COLUMN].to_numpy(),
                    beta_wall_height_m(damaged[RW_SIZE_COLUMN].to_numpy()),
                ),
                policy=policy,
            ),
        }
    )
    return walls.groupby(CLAIM_ID_COLUMN)["udv"].sum()


def claims_with_damaged_crossing(culverts: pd.DataFrame, bridges: pd.DataFrame) -> set:
    """Return the claims carrying a damaged culvert or bridge.

    Args:
        culverts: The contract's culvert table.
        bridges: The contract's bridge table.

    Returns:
        The claim ids, as a set.
    """
    found = set()
    for table in (culverts, bridges):
        damaged = loss_claims.damaged_crossings(table)
        if not damaged.empty:
            found |= set(damaged[CLAIM_ID_COLUMN])
    return found


def describe_land(caps):
    """Print how much damaged ground there is and what it is worth."""
    print(RULE)
    area_column = loss_claims.DAMAGED_AREA_COLUMN
    damaged = caps[caps[area_column] > 0]
    print(
        f"Land: {len(caps):,} claims, {len(damaged):,} with damaged ground, "
        f"{caps[area_column].sum():,.0f} m2 in total"
    )
    if damaged.empty:
        return
    print(
        f"  Valued at {caps[LAND_VALUE_COLUMN].sum():,.0f} NZD including GST, "
        f"median {damaged[LAND_VALUE_COLUMN].median():,.0f} NZD on a damaged claim"
    )
    bound = int(caps[AREA_CAP_BOUND_COLUMN].sum())
    print(
        f"  The area cap bound on {bound:,} claims, whose damage runs past it and "
        "is valued as though it stopped there"
    )


def describe_walls(caps, rw):
    """Print what the walls add to the cap, and what the sub-cap holds back."""
    print(RULE)
    damaged = loss_claims.damaged_walls(rw)
    with_wall = caps[caps[RW_UDV_COLUMN] > 0]
    print(
        f"Retaining walls: {len(damaged):,} damaged of {len(rw):,}, on "
        f"{len(with_wall):,} claims"
    )
    if with_wall.empty:
        return
    udv = caps[RW_UDV_COLUMN].sum()
    contributed = caps[RW_CONTRIBUTION_COLUMN].sum()
    bound = int(caps[RW_SUB_CAP_BOUND_COLUMN].sum())
    print(
        f"  {udv:,.0f} NZD of undepreciated value, of which {contributed:,.0f} NZD "
        "reaches the cap"
    )
    print(
        f"  The sub-cap bound on {bound:,} claims, holding back "
        f"{udv - contributed:,.0f} NZD"
    )


def describe_crossings(caps, culverts, bridges):
    """Print the damaged crossings and what they add to the cap."""
    print(RULE)
    damaged = len(loss_claims.damaged_crossings(culverts)) + len(
        loss_claims.damaged_crossings(bridges)
    )
    with_crossing = caps[caps[HAS_CROSSING_COLUMN]]
    print(
        f"Culverts and bridges: {len(culverts):,} culverts and {len(bridges):,} "
        f"bridges, {damaged:,} damaged, on {len(with_crossing):,} claims"
    )
    if with_crossing.empty:
        return
    print(
        f"  Each contributes its sub-cap limit outright, "
        f"{caps[CROSSING_CONTRIBUTION_COLUMN].sum():,.0f} NZD in all, on the "
        "agreed reading that replacement cost and undepreciated value both "
        "exceed it"
    )


def describe_caps(caps):
    """Print the caps themselves, and what is still missing from a settlement."""
    print(RULE)
    with_cap = caps[caps[CAP_COLUMN] > 0]
    print(
        f"Land cover cap: {caps[CAP_COLUMN].sum():,.0f} NZD over {len(with_cap):,} "
        "claims that have one"
    )
    if not with_cap.empty:
        print(f"  Median cap on those claims, {with_cap[CAP_COLUMN].median():,.0f} NZD")
    print(
        "Nothing here is settled. A settlement is min(repair cost, cap) less the "
        "excess, and no repair cost exists: a wall's needs the site ratings "
        "(Q-10), and damaged land has no Land SOW behind it."
    )


def main(*, extent, world_ids, realisation_ids):
    """Build and write the land cover cap per claim, per world and realisation.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: Which exposure worlds to cap.
        realisation_ids: Which modelled earthquakes to cap.
    """
    policy = PolicySettings()

    for world_id in world_ids:
        for realisation_id in realisation_ids:
            print(
                f"\nCapping world {world_id}, realisation {realisation_id} ...",
                flush=True,
            )
            tables = {
                name: gpd.read_parquet(
                    world_loss_input_path(name, world_id, realisation_id, extent=extent)
                )
                for name in LOSS_TABLES
            }

            caps = loss_claims.land_by_claim(tables["land"])
            caps[RW_UDV_COLUMN] = (
                wall_udv_by_claim(tables["rw"], policy=policy)
                .reindex(caps.index)
                .fillna(0)
            )

            # The dwelling count is validated against the same table it is read
            # from, so a claim missing one is refused here rather than quietly
            # halving its sub-cap.
            n_dwellings = loss_claims.dwelling_counts(
                caps.index.to_numpy(), caps.reset_index()
            )
            area = caps[loss_claims.DAMAGED_AREA_COLUMN].to_numpy()
            rate = caps[loss_claims.LAND_RATE_COLUMN].to_numpy()
            udv = caps[RW_UDV_COLUMN].to_numpy()
            limit = policy.retaining_wall_limit_nzd(n_dwellings)

            # A damaged crossing is given an undepreciated value of exactly its own
            # sub-cap limit, so `min(udv, limit)` returns the limit. That is the
            # agreed simplification: nothing prices a crossing, and both its
            # replacement cost and its value are taken to exceed the limit, so the
            # limit is what it contributes whatever the true figures are.
            with_crossing = claims_with_damaged_crossing(
                tables["culverts"], tables["bridges"]
            )
            caps[HAS_CROSSING_COLUMN] = caps.index.isin(with_crossing)
            crossing_limit = policy.bridge_culvert_limit_nzd(n_dwellings)
            crossing_udv = np.where(
                caps[HAS_CROSSING_COLUMN].to_numpy(), crossing_limit, 0
            )
            caps[CROSSING_UDV_COLUMN] = crossing_udv

            caps[LAND_VALUE_COLUMN] = damaged_land_value_nzd(area, rate, policy=policy)
            caps[AREA_CAP_BOUND_COLUMN] = area_cap_bound(area, policy=policy)
            caps[RW_CONTRIBUTION_COLUMN] = structure_contribution_nzd(udv, limit)
            caps[RW_SUB_CAP_BOUND_COLUMN] = structure_sub_cap_bound(udv, limit)
            caps[CROSSING_CONTRIBUTION_COLUMN] = structure_contribution_nzd(
                crossing_udv, crossing_limit
            )
            caps[CAP_COLUMN] = land_cover_cap_nzd(
                land_value_incl_gst_nzd=caps[LAND_VALUE_COLUMN].to_numpy(),
                retaining_wall_udv_incl_gst_nzd=udv,
                bridge_culvert_udv_incl_gst_nzd=crossing_udv,
                n_dwellings=n_dwellings,
                policy=policy,
            )

            describe_land(caps)
            describe_walls(caps, tables["rw"])
            describe_crossings(caps, tables["culverts"], tables["bridges"])
            describe_caps(caps)

            out = caps.reset_index()
            out.insert(0, REALISATION_ID_COLUMN, realisation_id)
            out.insert(1, WORLD_ID_COLUMN, world_id)
            out_path = land_cover_cap_path(world_id, realisation_id, extent=extent)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out.to_parquet(out_path)
            print(RULE)
            print(f"Wrote {len(out):,} claims to {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
