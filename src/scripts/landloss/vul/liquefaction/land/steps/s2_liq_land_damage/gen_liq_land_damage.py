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
from landloss.vul.liquefaction.costs import (
    COST_YEAR,
    RATE_BASIS,
    ld_cost_nzd,
    load_ld_costs,
)
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
STATE_COLUMN = "ld_state"
ON_GRID_COLUMN = "on_liq_grid"
# The state name a property off the liquefaction grid is written with. Its
# ld_state is null, so the loss module reads it as not liquefied.
OFF_GRID_STATE_NAME = "N/A"
RULE = "-" * 72


def liq_land_damage_path(realisation_id, *, pilot):
    """Return the file a run writes one realisation's land damage to."""
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.parquet"


def describe_damage(damage, properties, percentile):
    """Print the states drawn and what they cost."""
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
        .groupby([STATE_COLUMN, "state_name"])
        .agg(properties=(CLAIM_ID_COLUMN, "size"), cost_nzd=("cost_nzd", "first"))
    )
    print(f"By land damage state, at the {percentile}th percentile of settled cost:")
    print(counts.to_string())
    total = damage["cost_nzd"].sum()
    print(f"  total repair cost {total:,.0f} NZD, {COST_YEAR} dollars excluding GST")


def main(*, pilot, realisation_ids, cost_percentile):
    """Write the liquefaction land damage per property, per realisation."""
    insured = gpd.read_parquet(insured_land_path(pilot=pilot))
    points = insured.geometry.representative_point()
    costs = load_ld_costs()
    names = costs["state_name"]

    for realisation_id in realisation_ids:
        raster = ld_state_path(realisation_id, pilot=pilot)
        print(f"Sampling {raster} at {len(insured):,} properties ...", flush=True)
        sampled = sample_at_points(raster, points).to_numpy()
        on_grid = ~np.isnan(sampled)
        # A property off the grid has no state and costs nothing, rather than
        # the Canterbury cost of state 1.
        cost = np.nan_to_num(
            ld_cost_nzd(sampled, percentile=cost_percentile, costs=costs)
        )
        states = pd.Series(sampled).astype("Int64")
        state_names = states.map(names).astype("string").fillna(OFF_GRID_STATE_NAME)
        damage = pd.DataFrame(
            {
                "realisation_id": realisation_id,
                LAND_ID_COLUMN: insured[LAND_ID_COLUMN].to_numpy(),
                CLAIM_ID_COLUMN: insured[CLAIM_ID_COLUMN].to_numpy(),
                "cause": CAUSE,
                STATE_COLUMN: states.array,
                ON_GRID_COLUMN: on_grid,
                "state_name": state_names.to_numpy(),
                "area_m2": insured["area_m2"].to_numpy(),
                LAND_RATE_INCL_GST_COLUMN: insured[
                    LAND_RATE_INCL_GST_COLUMN
                ].to_numpy(),
                "cost_nzd": cost,
                "rate_basis": RATE_BASIS,
                "cost_year": COST_YEAR,
                "cost_percentile": cost_percentile,
            }
        )
        describe_damage(damage, len(insured), cost_percentile)

        out_path = liq_land_damage_path(realisation_id, pilot=pilot)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        damage.to_parquet(out_path)
        print(f"Wrote {len(damage):,} rows to {out_path}")


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        realisation_ids=config.REALISATION_IDS,
        cost_percentile=config.COST_PERCENTILE,
    )
