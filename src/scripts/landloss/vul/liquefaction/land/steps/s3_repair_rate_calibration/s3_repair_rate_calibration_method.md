# Step 3 — Liquefaction repair rate calibration: method

- The step fits what liquefied land costs to repair **from the ground it
  lost**, so the model can price a claim the way a claim report does rather
  than by a lookup per state (**T-57**). It is run by
  `gen_repair_rate_calibration.py`, **on demand rather than in the pipeline**:
  it reads step 2's areas, and step 2 reads the rates it produces from its own
  `config.py`, so a pipeline run that refitted them would be circular.
- **Three parameters**: a rate per m² of inundated land (clearing ejecta), a
  rate per m² of evacuated land (repairing cracked and spread ground), and a
  fixed cost per claim. `landloss.vul.liquefaction.repair_rates` holds the fit.
  - The fixed cost is there because Minor has 1 m² evacuated and nothing
    inundated (**L-39**), so no rate per m² can price it. Without it, Minor
    claims are priced at about $16 against a Canterbury mean of about $1,200.
    It stands for what any claim costs whatever its area: assessment, getting
    a crew to site, small reinstatement.
- **The fit** is least squares on the mean cost of a claim per state, each
  state weighted by its Canterbury claim count (`WEIGHT_BY_CLAIMS`), all three
  parameters held non-negative. The mean inundated and evacuated area per state
  is taken over the claims step 2 wrote, with the drop-out on, pooled over
  `REALISATION_IDS`. Section sizes are therefore Wellington's, not
  Canterbury's.
- **States fitted**: all six (`FIT_STATES`). None loses no ground, so its
  claims cost the fixed cost alone, which anchors it.
- **The target is the claimant-only mean and quartiles** per state
  (`costs_liq_ld_claimant_costs_2011.csv`, **T-65**): Canterbury, flat land,
  liquefaction only, no retaining wall, culvert or bridge claims, 2010/2011
  dollars excluding GST, before the excess. **A calibration target only**
  (Maxim Millen, 2026-10-08): it sets the parameters and is compared with the
  output, and nothing in the model draws from it. The mean replaced, on
  2026-10-08, a mean estimated by `lognormal_mean` from the 50th and 85th
  percentiles of a table averaging over non-claimants at $0; that estimate is
  still written beside it for comparison.
- **The spread of the per-claim cost** is fitted second. Canterbury's claims
  are right-skewed in every state, and None claims, which lose no ground, still
  run from $468 to $1,027 between the quartiles, so a single fixed cost put a
  floor of about $1,100 under every claim and left None and Minor with no
  spread at all. Each claim's fixed cost is now multiplied by a lognormal draw
  with a mean of one; its sigma is fitted, with the three rates held, to
  minimise the claim-weighted squared log miss of the modelled lower quartile,
  median and upper quartile per state. A mean of one leaves the means where the
  rates put them. The modelled quartiles integrate the draw over a fixed grid
  of normal quantiles, so the fit is deterministic. Step 2 draws the multiplier
  from a stream of its own (`liquefaction_claim_costs`).
- **The loss module settles on these rates** since 2026-10-08: vul step 10
  hands loss step 2's `area_cost_nzd`, not the percentile lookup.
- **Output**: the three rates and the spread printed, with the modelled
  quartiles and mean per state beside Canterbury's, and the fit by state written
  to `temp/vul/liq-repair-rate-calibration<suffix>.csv` -- claims, mean areas,
  the Canterbury claim count, mean and quartiles, the percentile table's mean,
  the modelled mean, their ratio and the modelled quartiles. The run then says whether step 2's `REPAIR_RATES` still
  match the fit, within 1%; copying them across is a deliberate edit, so the
  rates a run used are in git.
- **The fit on 2026-10-08**, over the pilot's 644 claims: $1.28 per m²
  inundated, $27.47 per m² evacuated, $1,094 per claim on average with a
  spread of 1.01. Modelled mean over Canterbury: None 1.19, Minor 0.87,
  Moderate 1.01, Major 0.71, Severe 1.14, Very severe 0.76. The quartiles of
  None, Minor and Moderate, 86% of Canterbury's claims, land within about 30%
  (Moderate: $566 / $912 / $1,586 against $497 / $819 / $1,549). Severe and
  Very severe stay too narrow: their cost is mostly area, drawn uniformly from
  tight ranges (**L-39**), so Severe's lower quartile is about twice
  Canterbury's and Very severe's upper quartile about 60% of it. The inundated
  rate is near zero however the states are
  weighted (0.09 unweighted, 0.52 by root claim count), because Canterbury
  paid Moderate ($1,351) barely more than Minor ($1,291) while Moderate is
  given 25% to 70% of its insured land inundated (**L-39**). Either ejecta
  clearing cost little because volunteers did it (**L-40**), or the inundated
  shares are too high; the under-priced Major and Very severe point at the
  area ranges.

Potential future improvements: see `s3_repair_rate_calibration_implementation_plan.md`.
