"""Put a liquefaction land damage state and a cost on every insured property.

Samples the land damage state raster the hazard module wrote at each property,
looks the settled Canterbury cost up against that state, and writes one row per
property per realisation for the loss module to settle.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/steps/s2_liq_land_damage/gen_liq_land_damage.py

The state is sampled **once per property**, at its representative point, so a
property carries one state rather than a mixture. That matches the cost side:
the packaged rates are a cost per property, not a rate per square metre, so an
area never multiplies them.

Two limits ride on every row and are carried as columns rather than left to be
remembered. The costs are **2010/2011 dollars excluding GST**, while land values
are indexed to a different date, so `cost_year` travels with the money. And the
quantity is per property, so `rate_basis` says so.

The rates are **flat land only**. Nothing here masks the hill properties out,
because the liquefaction hazard grid covers flat land alone and a hill property
comes back with no state at all; if that ever changes, this step needs a mask.
A property off the grid is written with a null state named N/A, at **no cost**.
It is not given state 1, None, because that is surveyed flat land that showed no
damage and carries a Canterbury cost; land that cannot liquefy has no
liquefaction damage state at all. `on_liq_grid` records the same split as a
flag.

**Not every damaged property claims.** Each property on the grid draws whether
its owner makes a land claim, at the drop-out rate for its state in
``config.DROP_OUT_RATES`` -- placeholders awaiting tuning (T-64, Q-16). The
state the hazard put there is kept as `hazard_ld_state`; `ld_state`, the column
the loss module settles, is null for a property that drops out, and its cost is
zero, so the loss module reads it exactly as it reads land off the grid: no
liquefaction claim. `liq_claimed` records the draw.

**The draw is on** because the settled cost is fitted to claimant-only means
(T-65), which `COSTS_INCLUDE_NON_CLAIMANTS` records as False. Were it set True
the draw would go off, every property on the grid claiming at a cost diluted
with non-claimants' $0s (L-43).

**Each claim carries the ground it lost** (T-55): an evacuated area in m² and an
inundated area, drawn uniformly within its state's ranges in
``config.EVACUATED_AREA_M2`` and ``config.INUNDATED_SHARE`` -- judgement, to be
tuned with the repair rates (L-39, T-57). They are drawn from a stream of their
own, so switching the drop-out on does not move them, and are zero wherever
`ld_state` is null. Their sum less the overlap -- ``config.EVACUATED_OVERLAP_SHARE``
of the evacuated land, an assumption to be verified (L-44) -- capped at the
insured area, is `damaged_area_m2`, which the loss module values the land cover
cap over (T-56).

**The cost is priced two ways, and the loss module settles the second.**
`area_cost_nzd` prices each claim from its ground lost --
``config.REPAIR_RATES`` per m² of inundated and evacuated land plus a fixed
cost per claim, fitted by step 3 to the Canterbury claimant-only means (T-57,
T-65) -- with the fixed cost drawn per claim around its mean, at the spread
step 3 fits to the Canterbury quartiles, and the inundated rate raised by
``config.NO_SVA_INUNDATED_MULTIPLIER`` when ``config.NO_SVA`` is set (L-40).
Vul step 10 hands it to loss (since 2026-10-08). `cost_nzd`, the Canterbury
percentile lookup per state, is written beside it for reference only; its table
averages over non-claimants, so with the drop-out on it is no longer on the
settled cost's basis.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.common.utils.terrain import sample_at_points
from landloss.domain import constants
from landloss.domain.loss_contract import CLAIM_ID_COLUMN, LAND_ID_COLUMN
from landloss.exposure.land.extent import LAND_RATE_INCL_GST_COLUMN
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
from landloss.vul.liquefaction.costs import (
    COST_YEAR,
    COSTS_INCLUDE_NON_CLAIMANTS,
    RATE_BASIS,
    ld_cost_nzd,
    load_ld_costs,
)
from landloss.vul.liquefaction.damaged_area import (
    DAMAGED_AREA_COLUMN,
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    check_ranges,
    draw_damaged_areas,
    liquefied_area_m2,
)
from landloss.vul.liquefaction.drop_out import check_drop_out_rates, draw_claims
from landloss.vul.liquefaction.repair_rates import RepairRates, area_repair_cost_nzd
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "liq-land-damage"

CAUSE = str(constants.Cause.LIQUEFACTION)
# The state the loss module settles: the hazard's state where the property
# claims, null where it drops out or is off the grid.
STATE_COLUMN = "ld_state"
HAZARD_STATE_COLUMN = "hazard_ld_state"
ON_GRID_COLUMN = "on_liq_grid"
CLAIMED_COLUMN = "liq_claimed"
# The repair cost priced from the ground lost, beside the Canterbury lookup.
AREA_COST_COLUMN = "area_cost_nzd"
# Its own stream rather than the shared "vulnerability" one, so the claim draw
# is independent of the wall and crossing damage draws of the same event.
RNG_STREAM = "liquefaction_claims"
# And the areas their own, so the drop-out going on does not reshuffle them.
AREA_RNG_STREAM = "liquefaction_areas"
# And the spread of the per-claim cost its own, so refitting it moves no area.
COST_RNG_STREAM = "liquefaction_claim_costs"
# The state name a property off the liquefaction grid is written with. Its
# ld_state is null, so the loss module reads it as not liquefied.
OFF_GRID_STATE_NAME = "N/A"
RULE = "-" * 72


def liq_land_damage_path(realisation_id, *, extent):
    """Return the file a run writes one realisation's land damage to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.parquet"


def describe_damage(damage, properties, percentile, *, apply_drop_out):
    """Print the states drawn, how many claim, and what they cost."""
    known = damage[ON_GRID_COLUMN]
    print(RULE)
    print(f"Properties: {properties:,}")
    print(f"  {int(known.sum()):,} sampled a liquefaction land damage state")
    print(
        f"  {properties - int(known.sum()):,} sit off the hazard grid, which "
        f"covers flat land only, and are written as state {OFF_GRID_STATE_NAME} "
        "at no cost"
    )
    if not known.any():
        return
    print(RULE)
    counts = (
        damage.loc[known]
        .groupby([HAZARD_STATE_COLUMN, "state_name"])
        .agg(
            properties=(CLAIM_ID_COLUMN, "size"),
            claimed=(CLAIMED_COLUMN, "sum"),
            total_cost_nzd=("cost_nzd", "sum"),
            total_area_cost_nzd=(AREA_COST_COLUMN, "sum"),
        )
    )
    claims = (
        "claims drawn at the placeholder drop-out rates"
        if apply_drop_out
        else "every property claiming"
    )
    print(
        f"By land damage state, {claims}, "
        f"at the {percentile}th percentile of settled cost:"
    )
    print(counts.round(0).astype("int64").to_string())
    claims = damage.loc[damage[CLAIMED_COLUMN]]
    if not claims.empty:
        print(RULE)
        print("Ground lost per claim, by land damage state (mean m2):")
        areas = claims.groupby([STATE_COLUMN, "state_name"])[
            [
                EVACUATED_AREA_COLUMN,
                INUNDATED_AREA_COLUMN,
                DAMAGED_AREA_COLUMN,
                "area_m2",
            ]
        ].mean()
        print(areas.round(1).to_string())
    total = damage["cost_nzd"].sum()
    area_total = damage[AREA_COST_COLUMN].sum()
    print(
        f"  total repair cost {total:,.0f} NZD by the Canterbury lookup, "
        f"{area_total:,.0f} NZD from the ground lost; {COST_YEAR} dollars "
        "excluding GST"
    )


def main(
    *,
    extent,
    realisation_ids,
    cost_percentile,
    drop_out_rates,
    evacuated_area_m2,
    inundated_share,
    evacuated_overlap_share,
    repair_rates,
    no_sva,
    no_sva_inundated_multiplier,
):
    """Write the liquefaction land damage per property, per realisation."""
    check_drop_out_rates(drop_out_rates)
    check_ranges(evacuated_area_m2, name="evacuated area")
    check_ranges(inundated_share, name="inundated share", upper=1.0)
    rates = RepairRates(**repair_rates)
    inundated_multiplier = no_sva_inundated_multiplier if no_sva else 1.0
    if no_sva:
        print(
            "No SVA: the inundated repair rate is raised by "
            f"{no_sva_inundated_multiplier:g} for clearing without volunteers."
        )
    apply_drop_out = not COSTS_INCLUDE_NON_CLAIMANTS
    if not apply_drop_out:
        print(
            "Drop-out off: the packaged costs already average over non-claimants "
            "at $0, so drawing claims against them would count it twice (T-65)."
        )
    insured = gpd.read_parquet(insured_land_path(extent=extent))
    points = insured.geometry.representative_point()
    costs = load_ld_costs()
    names = costs["state_name"]

    for realisation_id in realisation_ids:
        raster = ld_state_path(realisation_id, extent=extent)
        print(f"Sampling {raster} at {len(insured):,} properties ...", flush=True)
        sampled = sample_at_points(raster, points).to_numpy()
        on_grid = ~np.isnan(sampled)
        if apply_drop_out:
            rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
            claimed = draw_claims(sampled, drop_out_rates, rng)
        else:
            claimed = on_grid
        # A property off the grid, or one that does not claim, has no state to
        # settle and costs nothing -- not the Canterbury cost of state 1.
        cost = np.where(
            claimed,
            np.nan_to_num(
                ld_cost_nzd(sampled, percentile=cost_percentile, costs=costs)
            ),
            0.0,
        )
        evacuated, inundated = draw_damaged_areas(
            sampled,
            insured["area_m2"].to_numpy(),
            evacuated_area_m2,
            inundated_share,
            realisation_seed(constants.BASE_SEED, realisation_id, AREA_RNG_STREAM),
        )
        evacuated = np.where(claimed, evacuated, 0.0)
        inundated = np.where(claimed, inundated, 0.0)
        damaged = liquefied_area_m2(
            evacuated,
            inundated,
            insured["area_m2"].to_numpy(),
            evacuated_overlap_share,
        )
        area_cost = area_repair_cost_nzd(
            evacuated,
            inundated,
            claimed,
            rates,
            inundated_multiplier=inundated_multiplier,
            rng=realisation_seed(constants.BASE_SEED, realisation_id, COST_RNG_STREAM),
        )
        hazard_states = pd.Series(sampled).astype("Int64")
        states = hazard_states.where(claimed)
        state_names = (
            hazard_states.map(names).astype("string").fillna(OFF_GRID_STATE_NAME)
        )
        damage = pd.DataFrame(
            {
                "realisation_id": realisation_id,
                LAND_ID_COLUMN: insured[LAND_ID_COLUMN].to_numpy(),
                CLAIM_ID_COLUMN: insured[CLAIM_ID_COLUMN].to_numpy(),
                "cause": CAUSE,
                STATE_COLUMN: states.array,
                HAZARD_STATE_COLUMN: hazard_states.array,
                ON_GRID_COLUMN: on_grid,
                CLAIMED_COLUMN: claimed,
                "state_name": state_names.to_numpy(),
                "area_m2": insured["area_m2"].to_numpy(),
                EVACUATED_AREA_COLUMN: evacuated,
                INUNDATED_AREA_COLUMN: inundated,
                DAMAGED_AREA_COLUMN: damaged,
                LAND_RATE_INCL_GST_COLUMN: insured[
                    LAND_RATE_INCL_GST_COLUMN
                ].to_numpy(),
                "cost_nzd": cost,
                AREA_COST_COLUMN: area_cost,
                "rate_basis": RATE_BASIS,
                "cost_year": COST_YEAR,
                "cost_percentile": cost_percentile,
            }
        )
        describe_damage(
            damage, len(insured), cost_percentile, apply_drop_out=apply_drop_out
        )

        out_path = liq_land_damage_path(realisation_id, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        damage.to_parquet(out_path)
        print(f"Wrote {len(damage):,} rows to {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        cost_percentile=config.COST_PERCENTILE,
        drop_out_rates=config.DROP_OUT_RATES,
        evacuated_area_m2=config.EVACUATED_AREA_M2,
        inundated_share=config.INUNDATED_SHARE,
        evacuated_overlap_share=config.EVACUATED_OVERLAP_SHARE,
        repair_rates=config.REPAIR_RATES,
        no_sva=config.NO_SVA,
        no_sva_inundated_multiplier=config.NO_SVA_INUNDATED_MULTIPLIER,
    )
