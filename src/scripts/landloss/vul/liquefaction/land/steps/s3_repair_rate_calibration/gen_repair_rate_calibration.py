"""Back-calculate the liquefied land repair rates from the Canterbury medians.

Takes a standard section of ``SECTION_M2`` (500 m²) and the ground it loses in
each land damage state -- the middle of step 2's evacuated range and of its
inundated share -- and fits a rate per m² of each and a fixed cost per claim so
that section costs the Canterbury claimant-only **median** in each state
(Perrie Gilbert, 2026-10-12). Then fits the spread of the per-claim cost so the
quartiles either side of that median come as close as they can to Canterbury's,
holding the median where the rates put it. The None state is left out: it
costs nothing, there being no damage to repair.

Then checks the rates against a real run: each claim in ``COMPARE_EXTENT``,
priced from the ground step 2 drew for it, against Canterbury's quartiles per
state, both brought to today's dollars by ``LIQ_COST_ESCALATION``.

The Canterbury figures are a **calibration target only** (Maxim Millen,
2026-10-08): they set the model's parameters and are compared with its output,
and nothing in the model draws from them.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/steps/s3_repair_rate_calibration/gen_repair_rate_calibration.py

Run on demand, not as part of the pipeline: step 2 reads the rates from its own
``config.py``, so copy them there when this says they are stale. Refit after
changing the area ranges, the section size or the cost table.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import numpy as np
import pandas as pd

from landloss.io.area_of_interest import extent_suffix
from landloss.loss.pricing import LIQ_COST_ESCALATION
from landloss.vul.liquefaction.costs import (
    CLAIMS_COLUMN,
    COST_YEAR,
    QUARTILE_COLUMNS,
    load_claimant_costs,
)
from landloss.vul.liquefaction.damaged_area import (
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
)
from landloss.vul.liquefaction.repair_rates import (
    NO_DAMAGE_STATE,
    RepairRates,
    fit_per_claim_sigma_holding_median,
    fit_repair_rates,
    inundated_cost_nzd,
    modelled_quartiles,
    section_ground,
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

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "liq-repair-rate-calibration"
COMPARE_STEM = "liq-repair-rate-comparison"
# How far a configured rate may sit from the fit before it is called stale.
STALE_TOLERANCE = 0.01
RULE = "-" * 72


def calibration_path(*, extent):
    """Return the file the fit, state by state, is written to."""
    return WORK_DIR / f"{OUT_STEM}{extent_suffix(extent)}.csv"


def comparison_path(*, extent):
    """Return the file the comparison with a real run is written to."""
    return WORK_DIR / f"{COMPARE_STEM}{extent_suffix(extent)}.csv"


def is_stale(fitted, configured):
    """Return whether the configured rates differ from the fit."""
    pairs = zip(
        (
            fitted.inundated_nzd_per_m2,
            fitted.evacuated_nzd_per_m2,
            fitted.per_claim_nzd,
            fitted.per_claim_sigma,
            fitted.volunteer_cleared_m2,
        ),
        (
            configured.inundated_nzd_per_m2,
            configured.evacuated_nzd_per_m2,
            configured.per_claim_nzd,
            configured.per_claim_sigma,
            configured.volunteer_cleared_m2,
        ),
        strict=True,
    )
    return any(abs(c - f) > STALE_TOLERANCE * max(abs(f), 1.0) for f, c in pairs)


def back_calculate(*, section_m2, volunteer_cleared_m2, fit_states, weight_by_claims):
    """Fit the rates to the Canterbury medians on a standard section.

    Returns:
        The rates, and a table per state of the section's ground, the targets
        and what the section costs at the fitted rates.
    """
    if NO_DAMAGE_STATE in fit_states:
        msg = "the None state costs nothing and is not fitted against"
        raise ValueError(msg)
    inundated, evacuated = section_ground(
        s2_config.EVACUATED_AREA_M2, s2_config.INUNDATED_SHARE, section_m2
    )
    canterbury = load_claimant_costs()
    quartiles = {q: canterbury[column] for q, column in QUARTILE_COLUMNS.items()}
    weights = (
        canterbury.loc[fit_states, CLAIMS_COLUMN].to_dict()
        if weight_by_claims
        else None
    )
    median_fit = fit_repair_rates(
        {s: inundated[s] for s in fit_states},
        {s: evacuated[s] for s in fit_states},
        quartiles[50].loc[fit_states].to_dict(),
        weights=weights,
        volunteer_cleared_m2=volunteer_cleared_m2,
    )
    area_cost = {
        s: float(inundated_cost_nzd(inundated[s], median_fit))
        + evacuated[s] * median_fit.evacuated_nzd_per_m2
        for s in fit_states
    }
    sigma = fit_per_claim_sigma_holding_median(
        area_cost,
        median_fit.per_claim_nzd,
        {
            s: np.array([quartiles[q].loc[s] for q in QUARTILE_COLUMNS], dtype=float)
            for s in fit_states
        },
        weights=weights,
    )
    # The per-claim draw has a mean of one, so the fixed cost the rates carry is
    # the mean that puts its median at the back-calculated value.
    rates = RepairRates(
        median_fit.inundated_nzd_per_m2,
        median_fit.evacuated_nzd_per_m2,
        median_fit.per_claim_nzd * float(np.exp(sigma**2 / 2)),
        sigma,
        volunteer_cleared_m2=median_fit.volunteer_cleared_m2,
    )
    table = pd.DataFrame(
        {
            "state_name": canterbury["state_name"],
            "canterbury_claims": canterbury[CLAIMS_COLUMN],
            "section_inundated_m2": pd.Series(inundated),
            "section_evacuated_m2": pd.Series(evacuated),
        }
    ).loc[fit_states]
    section = pd.Series(area_cost)
    for q in QUARTILE_COLUMNS:
        table[f"canterbury_p{q}_nzd"] = quartiles[q].loc[fit_states]
        table[f"section_p{q}_nzd"] = pd.Series(
            {
                s: modelled_quartiles(
                    np.array([section[s]]), rates.per_claim_nzd, sigma
                )[list(QUARTILE_COLUMNS).index(q)]
                for s in fit_states
            }
        )
    return rates, table


def compare_with_run(rates, *, extent, realisation_ids):
    """Price a real run's claims at the rates, against Canterbury's quartiles.

    Both sides are brought to today's dollars by :data:`LIQ_COST_ESCALATION`.

    Returns:
        One row per state: the claims, and the modelled and Canterbury
        quartiles in today's dollars.
    """
    damage = pd.concat(
        pd.read_parquet(liq_land_damage_path(r, extent=extent)) for r in realisation_ids
    )
    claims = damage.loc[
        damage[CLAIMED_COLUMN] & (damage[STATE_COLUMN] != NO_DAMAGE_STATE)
    ]
    area_cost = (
        inundated_cost_nzd(claims[INUNDATED_AREA_COLUMN], rates)
        + claims[EVACUATED_AREA_COLUMN] * rates.evacuated_nzd_per_m2
    )
    canterbury = load_claimant_costs()
    rows = {}
    for state, costs in area_cost.groupby(claims[STATE_COLUMN].astype(int)):
        modelled = modelled_quartiles(
            costs.to_numpy(), rates.per_claim_nzd, rates.per_claim_sigma
        )
        row = {"state_name": canterbury.loc[state, "state_name"], "claims": len(costs)}
        for i, (q, column) in enumerate(QUARTILE_COLUMNS.items()):
            row[f"modelled_p{q}_nzd"] = modelled[i] * LIQ_COST_ESCALATION
            row[f"canterbury_p{q}_nzd"] = (
                canterbury.loc[state, column] * LIQ_COST_ESCALATION
            )
        rows[state] = row
    table = pd.DataFrame.from_dict(rows, orient="index")
    table["modelled_over_canterbury_p50"] = (
        table["modelled_p50_nzd"] / table["canterbury_p50_nzd"]
    )
    return table


def main(
    *,
    section_m2,
    volunteer_cleared_m2,
    fit_states,
    weight_by_claims,
    compare_extent,
    compare_realisation_ids,
):
    """Back-calculate the rates, compare them with a run, and write both."""
    rates, table = back_calculate(
        section_m2=section_m2,
        volunteer_cleared_m2=volunteer_cleared_m2,
        fit_states=fit_states,
        weight_by_claims=weight_by_claims,
    )
    print(RULE)
    print(
        f"Back-calculated on a {section_m2:,.0f} m2 section to the Canterbury "
        f"claimant-only medians, states {fit_states}"
        + (", weighted by claim count" if weight_by_claims else "")
        + f", {COST_YEAR} dollars excluding GST:"
    )
    print(
        f"  inundated  {rates.inundated_nzd_per_m2:10,.2f} NZD per m2 paid for, "
        f"beyond the first {rates.volunteer_cleared_m2:,.0f} m2 volunteers clear"
    )
    print(f"  evacuated  {rates.evacuated_nzd_per_m2:10,.2f} NZD per m2")
    median = rates.per_claim_nzd * np.exp(-(rates.per_claim_sigma**2) / 2)
    print(
        f"  per claim  {rates.per_claim_nzd:10,.0f} NZD on average "
        f"({median:,.0f} at the median)"
    )
    print(
        f"  spread     {rates.per_claim_sigma:10,.2f} sigma, fitted to the "
        "Canterbury quartiles holding the median"
    )
    print("  None costs nothing.")
    print(RULE)
    print("The section by state against Canterbury (2010/2011 NZD):")
    print(table.round(1).to_string())

    configured = RepairRates(**s2_config.REPAIR_RATES)
    print(RULE)
    if is_stale(rates, configured):
        print(
            "Step 2's REPAIR_RATES differ from this fit. Copy the four values "
            "above into its config.py if the fit is to be used."
        )
    else:
        print("Step 2's REPAIR_RATES match this fit.")
    out_path = calibration_path(extent=compare_extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path)
    print(f"Wrote the fit by state to {out_path}")

    print(RULE)
    if not liq_land_damage_path(
        compare_realisation_ids[0], extent=compare_extent
    ).exists():
        print(f"No step 2 run for {compare_extent} to compare with; run it first.")
        return rates
    compared = compare_with_run(
        rates, extent=compare_extent, realisation_ids=compare_realisation_ids
    )
    print(
        f"{compare_extent}: each claim priced from its own ground at these "
        f"rates, against Canterbury, both x{LIQ_COST_ESCALATION} to today's "
        "dollars excluding GST:"
    )
    print(compared.round(2).to_string())
    compare_out = comparison_path(extent=compare_extent)
    compared.to_csv(compare_out)
    print(f"Wrote the comparison to {compare_out}")
    return rates


if __name__ == "__main__":
    main(
        section_m2=config.SECTION_M2,
        volunteer_cleared_m2=config.VOLUNTEER_CLEARED_M2,
        fit_states=config.FIT_STATES,
        weight_by_claims=config.WEIGHT_BY_CLAIMS,
        compare_extent=config.COMPARE_EXTENT,
        compare_realisation_ids=config.COMPARE_REALISATION_IDS,
    )
