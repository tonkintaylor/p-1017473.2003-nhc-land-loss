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
- **The fit** is least squares on the mean cost of a claim per state,
  unweighted across states, all three parameters held non-negative. The mean
  inundated and evacuated area per state is taken over the claims step 2 wrote,
  pooled over `REALISATION_IDS`. Section sizes are therefore Wellington's, not
  Canterbury's.
- **States fitted**: Minor to Very severe (`FIT_STATES`). None loses no ground,
  so the fit could only price it at the fixed cost; it is left out.
- **The target is a mean estimated from percentiles.** The packaged table has
  the 15th, 50th and 85th percentiles per state, not the mean.
  `lognormal_mean` fits a lognormal through the 50th and 85th and returns its
  mean, which runs 1.25 to 2.4 times the median. The 15th is not used: it is $0
  for None, and it is where the non-claimants' $0s pull the table down. Means
  from the source would replace the estimate (**T-66**).
- **The basis is the target's**: 2010/2011 dollars excluding GST, averaged over
  damaged properties with non-claimants at $0 (**Q-17**). The rates are only
  consistent with the drop-out off, and are to be refitted when claimant-only
  costs arrive.
- **Output**: the three rates printed, and the fit by state written to
  `temp/vul/liq-repair-rate-calibration[-pilot].csv` -- claims, mean areas, the
  Canterbury mean, the modelled mean and their ratio. The run then says whether
  step 2's `REPAIR_RATES` still match the fit, within 1%; copying them across is
  a deliberate edit, so the rates a run used are in git.
- **The fit on 2026-10-02 is provisional**, not a result: against diluted
  costs with the drop-out off it reproduces the Canterbury means by
  construction, and the fixed cost is per damaged property rather than per
  claim. Over 1,767 pilot claims: $10.39 per m² inundated,
  $19.66 per m² evacuated, $995 per claim. Modelled over Canterbury means:
  Minor 0.83, Moderate 1.24, Major 0.98, Severe 0.91, Very severe 1.03. Moderate
  is the worst fitted: its 25% to 70% inundation gives it most of Major's
  inundated area at under two-thirds of Major's cost.

Potential future improvements: see `s3_repair_rate_calibration_implementation_plan.md`.
