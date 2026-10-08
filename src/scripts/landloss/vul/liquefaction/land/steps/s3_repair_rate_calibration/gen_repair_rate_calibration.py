"""Fit the liquefied land repair rates to the Canterbury cost per state.

Pools the claims step 2 wrote, takes the mean evacuated and inundated area of a
claim in each land damage state, and fits a rate per m² of each and a fixed
cost per claim so the modelled mean cost per state comes as close as it can to
the Canterbury claimant-only mean (T-57, T-65). Then fits the spread of the
per-claim cost between claims so the modelled quartiles per state come as close
as they can to Canterbury's; the spread has a mean of one, so it leaves the
means alone. Writes the fit, state by state, and says whether the rates step 2
is configured with still match it.

The Canterbury figures are a **calibration target only** (Maxim Millen,
2026-10-08): they set the model's parameters and are compared with its output,
and nothing in the model draws from them.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/steps/s3_repair_rate_calibration/gen_repair_rate_calibration.py

The fit is run on demand, not as part of the pipeline: it reads step 2's areas,
and step 2 reads the rates it produces from its own ``config.py``. Refit after
changing the area ranges, the overlap, the drop-out rates or the cost table.

The target is the claimant-only mean and quartiles per state
(:func:`landloss.vul.liquefaction.costs.load_claimant_costs`), each state
weighted by its claim count when ``WEIGHT_BY_CLAIMS`` is set. The mean estimated
from the percentile table by
:func:`landloss.vul.liquefaction.repair_rates.lognormal_mean` is printed beside
it for comparison.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import pandas as pd

from landloss.io.area_of_interest import extent_suffix
from landloss.vul.liquefaction.costs import (
    CLAIMS_COLUMN,
    COST_YEAR,
    COSTS_INCLUDE_NON_CLAIMANTS,
    MEAN_COST_COLUMN,
    PERCENTILE_COLUMNS,
    QUARTILE_COLUMNS,
    load_claimant_costs,
    load_ld_costs,
)
from landloss.vul.liquefaction.damaged_area import (
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
)
from landloss.vul.liquefaction.repair_rates import (
    RepairRates,
    fit_per_claim_sigma,
    fit_repair_rates,
    lognormal_mean,
    modelled_quartiles,
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


def calibration_path(*, extent):
    """Return the file the state-by-state fit is written to."""
    return TEMP_DIR / "vul" / f"{OUT_STEM}{extent_suffix(extent)}.csv"


def percentile_means(costs):
    """Return the mean per state estimated from the percentile table.

    Kept for comparison only: that table averages over non-claimants at $0.
    """
    p50, p85 = PERCENTILE_COLUMNS[50], PERCENTILE_COLUMNS[85]
    return pd.Series(
        {
            state: lognormal_mean(costs.loc[state, p50], costs.loc[state, p85])
            for state in costs.index
        },
        name="percentile_table_mean_nzd",
    )


def is_stale(fitted, configured):
    """Return whether the configured rates differ from the fit."""
    pairs = zip(
        (
            fitted.inundated_nzd_per_m2,
            fitted.evacuated_nzd_per_m2,
            fitted.per_claim_nzd,
            fitted.per_claim_sigma,
        ),
        (
            configured.inundated_nzd_per_m2,
            configured.evacuated_nzd_per_m2,
            configured.per_claim_nzd,
            configured.per_claim_sigma,
        ),
        strict=True,
    )
    return any(abs(c - f) > STALE_TOLERANCE * max(abs(f), 1.0) for f, c in pairs)


def main(*, extent, realisation_ids, fit_states, weight_by_claims):
    """Fit the repair rates and write the fit state by state."""
    if COSTS_INCLUDE_NON_CLAIMANTS:
        print(
            "WARNING: COSTS_INCLUDE_NON_CLAIMANTS is set, so step 2 draws no "
            "drop-out; fitting claimant-only means against every damaged "
            "property mixes two bases."
        )
    damage = pd.concat(
        pd.read_parquet(liq_land_damage_path(realisation_id, extent=extent))
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

    canterbury = load_claimant_costs()
    quartile_columns = {q: f"canterbury_p{q}_nzd" for q in QUARTILE_COLUMNS}
    table = (
        by_state.join(canterbury["state_name"])
        .join(canterbury[CLAIMS_COLUMN].rename("canterbury_claims"))
        .join(canterbury[MEAN_COST_COLUMN].rename("canterbury_mean_nzd"))
        .join(
            canterbury[list(QUARTILE_COLUMNS.values())].rename(
                columns={QUARTILE_COLUMNS[q]: c for q, c in quartile_columns.items()}
            )
        )
        .join(percentile_means(load_ld_costs()))
    )
    fit = table.loc[fit_states]
    weights = fit["canterbury_claims"].to_dict() if weight_by_claims else None
    means_fit = fit_repair_rates(
        fit["mean_inundated_m2"].to_dict(),
        fit["mean_evacuated_m2"].to_dict(),
        fit["canterbury_mean_nzd"].to_dict(),
        weights=weights,
    )
    # The cost of each claim's ground lost, on the Canterbury basis: volunteers
    # in, so no no-SVA multiplier.
    area_cost = (
        claims[INUNDATED_AREA_COLUMN] * means_fit.inundated_nzd_per_m2
        + claims[EVACUATED_AREA_COLUMN] * means_fit.evacuated_nzd_per_m2
    ).groupby(claims[STATE_COLUMN].astype(int))
    area_cost = {int(state): group.to_numpy() for state, group in area_cost}
    sigma = fit_per_claim_sigma(
        {state: area_cost[state] for state in fit_states},
        means_fit.per_claim_nzd,
        {
            state: fit.loc[state, list(quartile_columns.values())].to_numpy(float)
            for state in fit_states
        },
        weights=weights,
    )
    rates = RepairRates(
        means_fit.inundated_nzd_per_m2,
        means_fit.evacuated_nzd_per_m2,
        means_fit.per_claim_nzd,
        sigma,
    )
    table["modelled_mean_nzd"] = (
        table["mean_inundated_m2"] * rates.inundated_nzd_per_m2
        + table["mean_evacuated_m2"] * rates.evacuated_nzd_per_m2
        + rates.per_claim_nzd
    )
    table["modelled_over_canterbury"] = (
        table["modelled_mean_nzd"] / table["canterbury_mean_nzd"]
    )
    quartiles = pd.DataFrame(
        {
            state: modelled_quartiles(costs, rates.per_claim_nzd, sigma)
            for state, costs in area_cost.items()
        },
        index=[f"modelled_p{q}_nzd" for q in QUARTILE_COLUMNS],
    ).T
    table = table.join(quartiles)
    table["in_fit"] = table.index.isin(fit_states)

    print(RULE)
    print(
        f"Fitted over {int(fit['claims'].sum()):,} modelled claims in states "
        f"{fit_states} to the Canterbury claimant-only means"
        + (", weighted by claim count" if weight_by_claims else "")
        + f", {COST_YEAR} dollars excluding GST:"
    )
    print(f"  inundated  {rates.inundated_nzd_per_m2:10,.2f} NZD per m2")
    print(f"  evacuated  {rates.evacuated_nzd_per_m2:10,.2f} NZD per m2")
    print(f"  per claim  {rates.per_claim_nzd:10,.0f} NZD on average")
    print(
        f"  spread     {rates.per_claim_sigma:10,.2f} sigma of the per-claim "
        "cost, fitted to the Canterbury quartiles"
    )
    print(RULE)
    print(table.round(2).to_string())
    print(RULE)
    print("Cost of a claim by state, modelled against Canterbury (NZD):")
    shown = {}
    for q, column in quartile_columns.items():
        shown[f"p{q}"] = table[f"modelled_p{q}_nzd"].round(0).astype(int)
        shown[f"Canterbury p{q}"] = table[column]
    shown["mean"] = table["modelled_mean_nzd"].round(0).astype(int)
    shown["Canterbury mean"] = table["canterbury_mean_nzd"]
    print(pd.DataFrame(shown).set_index(table["state_name"]).to_string())

    configured = RepairRates(**s2_config.REPAIR_RATES)
    print(RULE)
    if is_stale(rates, configured):
        print(
            "Step 2's REPAIR_RATES differ from this fit. Copy the four values "
            "above into its config.py if the fit is to be used."
        )
    else:
        print("Step 2's REPAIR_RATES match this fit.")

    out_path = calibration_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path)
    print(f"Wrote the fit by state to {out_path}")
    return rates


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        fit_states=config.FIT_STATES,
        weight_by_claims=config.WEIGHT_BY_CLAIMS,
    )
