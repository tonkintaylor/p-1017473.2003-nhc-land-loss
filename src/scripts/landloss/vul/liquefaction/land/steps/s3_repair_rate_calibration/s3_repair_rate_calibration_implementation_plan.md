# Step 3 — Liquefaction repair rate calibration: implementation plan

**Status:** Phase 1 complete as machinery. The rates are **provisional**: fitted
to the current, diluted Canterbury costs with the drop-out off, they only
re-express the Canterbury means per m², and are not validated. They ride beside
the lookup in step 2 and nothing settles on them. They become a result when
refitted against claimant-only costs (**T-65**).

## Phase 1 — Rates that reproduce Canterbury (complete)

- [x] Estimate the Canterbury mean per state from the 50th and 85th
      percentiles, through a lognormal.
- [x] Fit a rate per m² of inundated land, one of evacuated land and a fixed
      cost per claim, non-negative, to the mean per state from Minor to Very
      severe.
- [x] Report the fit by state and whether step 2's configured rates match it.
- [x] Price every claim from its ground lost in step 2, as `area_cost_nzd`,
      with the no-SVA flag raising the inundated rate.

## Phase 2 — Using and refitting them

- [ ] Decide whether `area_cost_nzd` replaces the Canterbury lookup as the
      repair cost the loss module settles on. Its total is about 1.8 times the
      lookup's at the 50th percentile, because it reproduces means.
- [ ] Refit against claimant-only Canterbury costs, preferably means rather
      than percentiles, with the drop-out on (**T-65**).
- [ ] Set the no-SVA multiplier on feedback (**Q-18**).
- [ ] Decide whether None should carry the fixed cost when it claims. With the
      drop-out off every None property claims and is priced at $995 against a
      Canterbury mean of about $670.
- [ ] Revisit the Moderate inundation range if Moderate stays the worst fitted
      state (1.24), alongside Maxim Millen's revision of the states (**T-54**).

## Potential future improvements

- Weight the fit by the number of claims per state, if the total rather than
  each state's mean is what has to match.
- Fit against Canterbury section sizes rather than Wellington's, if the
  observed damage database can supply mean areas per state.
