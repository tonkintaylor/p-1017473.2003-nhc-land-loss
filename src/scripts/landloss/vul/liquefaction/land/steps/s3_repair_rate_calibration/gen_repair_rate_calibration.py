"""Fit the liquefied land repair rates to the Canterbury cost per state.

Pools the claims step 2 wrote, takes the mean evacuated and inundated area of a
claim in each land damage state, and fits a rate per m² of each and a fixed
cost per claim so the modelled mean cost per state comes as close as it can to
the Canterbury mean (T-57). Writes the fit, state by state, and says whether the
rates step 2 is configured with still match it.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/steps/s3_repair_rate_calibration/gen_repair_rate_calibration.py

The fit is run on demand, not as part of the pipeline: it reads step 2's areas,
and step 2 reads the rates it produces from its own ``config.py``. Refit after
changing the area ranges, the overlap, or the cost table -- in particular when
claimant-only Canterbury costs replace the current ones (T-65), at which point
the drop-out comes on and the rates change basis with it.

The Canterbury means are estimated from the 50th and 85th percentiles by
:func:`landloss.vul.liquefaction.repair_rates.lognormal_mean`; the method file
says why.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import pandas as pd

from landloss.vul.liquefaction.costs import (
    COST_YEAR,
    COSTS_INCLUDE_NON_CLAIMANTS,
    PERCENTILE_COLUMNS,
    load_ld_costs,
)
from landloss.vul.liquefaction.damaged_area import (
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
)
from landloss.vul.liquefaction.repair_rates import (
    RepairRates,
    fit_repair_rates,
    lognormal_mean,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    config as s2_config,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage.gen_liq_land_damage import (
    CLAIMED_COLUMN,
    STATE_COLUMN,
    liq_land_damage_path,
)
from scripts.landloss.vul.liquefaction.land.steps.s3_repair_rate_calibration import (
    config,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_STEM = "liq-repair-rate-calibration"
# How far step 2's configured rates may sit from the fit before the run says so.
STALE_TOLERANCE = 0.01
RULE = "-" * 72


def calibration_path(*, pilot):
    """Return the file the state-by-state fit is written to."""
    suffix = "-pilot" if pilot else ""
    return TEMP_DIR / "vul" / f"{OUT_STEM}{suffix}.csv"


def canterbury_means(costs):
    """Return the estimated mean Canterbury cost per state."""
    p50, p85 = PERCENTILE_COLUMNS[50], PERCENTILE_COLUMNS[85]
    return pd.Series(
        {
            state: lognormal_mean(costs.loc[state, p50], costs.loc[state, p85])
            for state in costs.index
        },
        name="canterbury_mean_nzd",
    )


def is_stale(fitted, configured):
    """Return whether the configured rates differ from the fit."""
    pairs = zip(
        (
            fitted.inundated_nzd_per_m2,
            fitted.evacuated_nzd_per_m2,
            fitted.per_claim_nzd,
        ),
        (
            configured.inundated_nzd_per_m2,
            configured.evacuated_nzd_per_m2,
            configured.per_claim_nzd,
        ),
        strict=True,
    )
    return any(abs(c - f) > STALE_TOLERANCE * max(abs(f), 1.0) for f, c in pairs)


def main(*, pilot, realisation_ids, fit_states):
    """Fit the repair rates and write the fit state by state."""
    if not COSTS_INCLUDE_NON_CLAIMANTS:
        print(
            "The packaged costs are claimant-only: fitting against them gives "
            "rates for claims, to pair with the drop-out on."
        )
    damage = pd.concat(
        pd.read_parquet(liq_land_damage_path(realisation_id, pilot=pilot))
        for realisation_id in realisation_ids
    )
    claims = damage.loc[damage[CLAIMED_COLUMN]]
    by_state = claims.groupby(STATE_COLUMN).agg(
        claims=(CLAIMED_COLUMN, "size"),
        mean_inundated_m2=(INUNDATED_AREA_COLUMN, "mean"),
        mean_evacuated_m2=(EVACUATED_AREA_COLUMN, "mean"),
    )
    by_state.index = by_state.index.astype(int)
    missing = sorted(set(fit_states) - set(by_state.index))
    if missing:
        msg = f"no claims in states {missing} to fit against; pool more realisations"
        raise ValueError(msg)

    costs = load_ld_costs()
    table = by_state.join(costs["state_name"]).join(canterbury_means(costs))
    fit = table.loc[fit_states]
    rates = fit_repair_rates(
        fit["mean_inundated_m2"].to_dict(),
        fit["mean_evacuated_m2"].to_dict(),
        fit["canterbury_mean_nzd"].to_dict(),
    )
    table["modelled_mean_nzd"] = (
        table["mean_inundated_m2"] * rates.inundated_nzd_per_m2
        + table["mean_evacuated_m2"] * rates.evacuated_nzd_per_m2
        + rates.per_claim_nzd
    )
    table["modelled_over_canterbury"] = (
        table["modelled_mean_nzd"] / table["canterbury_mean_nzd"]
    )
    table["in_fit"] = table.index.isin(fit_states)

    print(RULE)
    print(
        f"Fitted over {int(fit['claims'].sum()):,} claims in states {fit_states}, "
        f"{COST_YEAR} dollars excluding GST:"
    )
    print(f"  inundated  {rates.inundated_nzd_per_m2:10,.2f} NZD per m2")
    print(f"  evacuated  {rates.evacuated_nzd_per_m2:10,.2f} NZD per m2")
    print(f"  per claim  {rates.per_claim_nzd:10,.0f} NZD")
    print(RULE)
    print(table.round(2).to_string())

    configured = RepairRates(**s2_config.REPAIR_RATES)
    print(RULE)
    if is_stale(rates, configured):
        print(
            "Step 2's REPAIR_RATES differ from this fit. Copy the three values "
            "above into its config.py if the fit is to be used."
        )
    else:
        print("Step 2's REPAIR_RATES match this fit.")

    out_path = calibration_path(pilot=pilot)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path)
    print(f"Wrote the fit by state to {out_path}")
    return rates


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        realisation_ids=config.REALISATION_IDS,
        fit_states=config.FIT_STATES,
    )
