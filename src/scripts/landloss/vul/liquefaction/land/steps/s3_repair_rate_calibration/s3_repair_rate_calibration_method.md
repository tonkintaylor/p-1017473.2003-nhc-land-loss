# Step 3 — Liquefaction repair rate calibration: method

- The step works out what liquefied land costs to repair **from the ground it
  lost**, so the model can price a claim the way a claim report does rather
  than by a lookup per state (**T-57**). It is run by
  `gen_repair_rate_calibration.py`, **on demand rather than in the pipeline**:
  step 2 reads the rates from its own `config.py`, so copying them across is a
  deliberate edit and the rates a run used are in git.
- **Three parameters**: a rate per m² of ejecta paid for, a rate per m² of
  evacuated land (repairing cracked and spread ground), and a fixed cost per
  claim. Ejecta is kept apart from the rest, rather than one rate per state, so
  the Student Volunteer Army can be put on clearing it (**L-40**).
  `landloss.vul.liquefaction.repair_rates` holds the fit.
- **The Student Volunteer Army as an allowance** (Perrie Gilbert, 2026-10-12):
  volunteers cleared the first `VOLUNTEER_CLEARED_M2` (250 m², judgement) of
  every site's ejecta for nothing, so a Moderate site, given about 240 m² of
  it, cost Canterbury no more than a Minor one with none -- which is what its
  medians show. The ejecta rate is fitted to the ejecta beyond the allowance,
  what claims paid for. Without volunteers (`NO_SVA`, or the loss viewer's
  switch) all of a site's ejecta is paid at the same rate. The medians fit
  about as well from 200 m² to 300 m².
  - The fixed cost is there because Minor has 1 m² evacuated and nothing
    inundated (**L-39**), so no rate per m² can price it. It stands for what
    any claim costs whatever its area: assessment, getting a crew to site,
    small reinstatement.
- **The None state costs nothing** (Perrie Gilbert, 2026-10-12): there is no
  damage to repair, so not even the fixed cost is charged, and None is not
  fitted against. Step 2 charges only claims in a worse state.
- **Back-calculated on a standard section** (2026-10-12): a section of
  `SECTION_M2`, 500 m², loses the middle of each state's evacuated range and of
  its inundated share (step 2's `EVACUATED_AREA_M2` and `INUNDATED_SHARE`), and
  the three rates are fitted by least squares so that section costs the
  Canterbury **median** in each state, Minor to Very severe (`FIT_STATES`),
  each weighted by its Canterbury claim count (`WEIGHT_BY_CLAIMS`), all three
  held non-negative. This replaced fitting the means over the pilot's own
  modelled claims.
- **The target is the claimant-only quartiles** per state
  (`costs_liq_ld_claimant_costs_2011.csv`, **T-65**, from Virginie Lacrosse):
  Canterbury, flat land, liquefaction only, 2010/2011 dollars excluding GST,
  before the excess. **A calibration target only** (Maxim Millen,
  2026-10-08): it sets the parameters and is compared with the output, and
  nothing in the model draws from it.
- **The spread of the per-claim cost** is fitted second, to the lower and
  upper quartiles, **holding the median**: each claim's fixed cost is
  multiplied by a lognormal draw with a mean of one, and for each candidate
  sigma the fixed cost's mean is set so its median stays at the back-calculated
  value (`fit_per_claim_sigma_holding_median`). The rates carry that mean as
  `per_claim_nzd`. Step 2 draws the multiplier from a stream of its own
  (`liquefaction_claim_costs`).
- **Checked against a real run** (`COMPARE_EXTENT`, Lower Hutt): each claim
  step 2 drew there is priced from its own ground at the rates, and its
  quartiles per state compared with Canterbury's, both multiplied by
  `LIQ_COST_ESCALATION` (1.42) to today's dollars, written to
  `temp/vul/liq-repair-rate-comparison<suffix>.csv`.
- **The loss module settles on these rates**: vul step 10 hands loss step 2's
  `area_cost_nzd`. Step 2 also writes the clearing-ejecta part of it,
  `inundated_cost_nzd`, which the loss viewer's Student Volunteer Army switch
  reprices without a rerun.
- **The fit on 2026-10-12**: $3.39 per m² of ejecta beyond the 250 m²
  volunteers clear, $18.57 per m² evacuated, and a per-claim cost of $794 at
  the median ($1,207 on average) with a spread of 0.92. Over Lower Hutt's
  claims, modelled median over Canterbury's: Minor 1.09, Moderate 1.25, Major
  1.09, Severe 1.28, Very severe 0.76 -- Lower Hutt's sections are larger than
  500 m², so more of their ejecta lies beyond the allowance. Without volunteers
  a Moderate section's ejecta costs about $800 more, Major to Very severe about
  $850 more, in 2010/2011 dollars. Either ejecta clearing cost little because volunteers did it
  (**L-40**), or Moderate's inundated share is too high. Major, Severe and Very
  severe share one inundated range (30% to 100%), so inundation does not tell
  them apart; their difference is evacuated ground.
- **Figures** (`fig_repair_rate_calibration.py`, over `COMPARE_EXTENT`): the
  ground lost per state, how the three rates build the section's median per
  state, the quartiles on real claims with and without the spread, the spread
  fit, and a rate curve each for inundated and evacuated land with the no-SVA
  rate beside the inundated one.

Potential future improvements: see `s3_repair_rate_calibration_implementation_plan.md`.
