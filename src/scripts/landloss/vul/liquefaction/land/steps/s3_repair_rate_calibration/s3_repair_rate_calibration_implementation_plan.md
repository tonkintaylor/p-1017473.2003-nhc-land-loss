# Step 3 — Liquefaction repair rate calibration: implementation plan

**Status:** Phase 1 complete; Phase 2 in progress. Since 2026-10-08 the rates
are fitted to the Canterbury claimant-only means and quartiles (**T-65**) with
the drop-out on, and the loss module settles on them. They rest on a thin pilot
fit and are to be refitted and frozen before the full runs (Phase 3).

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

- [x] Settle on `area_cost_nzd` in place of the Canterbury lookup: vul step 10
      hands it to the loss module (2026-10-08).
- [x] Refit against the claimant-only Canterbury means, all six states weighted
      by claim count, with the drop-out on (**T-65**, 2026-10-08).
- [ ] Set the no-SVA multiplier on feedback (**Q-18**). It is 2.9 from public
      figures for now, which barely moves a near-zero inundated rate (**L-75**).
- [ ] Decide whether None should carry the fixed cost when it claims. It is now
      fitted and anchors the fixed cost, priced at $1,094 on average against a
      Canterbury mean of $922.
- [x] Fit the spread of the per-claim cost to the Canterbury claimant-only
      quartiles, as a calibration target, and report the modelled quartiles
      beside them (2026-10-08).
- [ ] Widen or skew the Severe and Very severe area ranges if their quartiles
      are to match: the per-claim spread cannot reach them (**L-39**).
- [ ] Revisit the Moderate inundation range alongside Maxim Millen's revision
      of the states (**T-54**): at 25% to 70% inundated it drives the inundated
      rate to near zero, since Canterbury paid Moderate barely more than Minor.

## Phase 3 — Before the full runs

From the review of 2026-10-08; the register carries the detail.

- [ ] Refit over several realisations and a larger extent, then freeze the
      rates so every region settles on the same ones (**L-70**, **I-26**).
- [ ] Revisit the Major, Severe and Very severe area ranges, under-priced at
      0.71 and 0.76 for Major and Very severe (**L-71**, **I-27**).
- [ ] Set the drop-out rates from the source's settlement likelihoods or
      Virginie Lacrosse's counts (**L-72**, **I-28**, **T-64**).

## Potential future improvements

- Price inundated land in the no-SVA case from a contractor rate for removing
  ejecta rather than a multiplier on the fitted rate (**L-75**, **I-25**).
- Fit against Canterbury section sizes rather than Wellington's, if the
  observed damage database can supply mean areas per state.
