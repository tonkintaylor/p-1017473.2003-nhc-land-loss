# Step 2 — Liquefaction land damage: implementation plan

**Status:** Phases 1, 1a, 1b and 1c complete. Costs are the packaged Canterbury
settlements; the drop-out draw is built but off, since those costs already
include non-claimants, and its rates are placeholders.

## Phase 1 — A priced state on every property (complete)

- [x] Read the insured land extent and the realised land damage state raster.
- [x] Sample one state per property at its representative point.
- [x] Read the packaged Canterbury cost rates, keeping the state named "None"
      from being parsed as a missing value.
- [x] Look a cost up per property at the run's percentile.
- [x] Carry `rate_basis`, `cost_year` and `cost_percentile` on every row, so a
      loss table cannot silently mix bases or vintages.
- [x] Report the properties the hazard grid does not reach, which over the
      pilot is the model covering flat land only.

## Phase 1a — land_id for the loss contract (complete)

- [x] Carry `land_id` from the insured land onto every row, after
      `realisation_id` and before `claim_id`, so step 10 can join the state to
      its land polygon.
- [x] Import the key names from `landloss.domain.loss_contract` rather than
      retyping them.
- [x] Leave the output without geometry; step 10 takes the coordinates from the
      insured land.

## Phase 1b — Off the grid is no damage (complete)

- [x] Write a property off the liquefaction grid as state 1, None, at no cost,
      rather than as a missing state, and record `on_liq_grid` beside it.
- [x] Carry the GST-inclusive land rate from the insured land rather than the
      exclusive one.

## Phase 1c — Not every damaged property claims (complete)

- [x] Draw per property whether it makes a land claim, at a drop-out rate per
      state, from a seeded stream of its own (`liquefaction_claims`).
- [x] Null `ld_state` and zero the cost for a property that drops out, keeping
      the hazard's state as `hazard_ld_state` and the draw as `liq_claimed`.
- [x] Hold the rates in `config.py` as `DROP_OUT_RATES`, flagged as
      placeholders, with Severe and Very severe at 0%.
- [x] Leave the draw off while the packaged costs include non-claimants at $0
      (**Q-17**), keyed on `COSTS_INCLUDE_NON_CLAIMANTS` in the costs module.
- [ ] Replace the costs with claimant-only rates from Virginie Lacrosse and set
      `COSTS_INCLUDE_NON_CLAIMANTS` False, which switches the draw on
      (**T-65**).
- [ ] Validate the rates against her counts of damaged properties and
      claimants per band, which give the drop-out directly, and tune them on
      her and John Leeves' feedback (**T-64**, **Q-16**). The existing diluted
      and the claimant-only rates check them only as means: drop-out = 1 −
      diluted mean ÷ claimant mean. Percentiles do not scale that way.
- [ ] Calibrate the T-57 repair rates against claimants only, to match.

## Phase 2 — Beyond the Canterbury lookup

- [ ] Index the 2011 costs to the study's valuation date, rather than leaving
      two vintages for the loss module to reconcile.
- [ ] Gross the rates up for GST at the loss boundary — they arrive excluding
      it and the Act compares on a GST-inclusive basis.
- [ ] Decide whether a property larger than the Canterbury median should cost
      more than the lookup says. The rates have no size term at all, which is
      right for the ILVR total and probably wrong for a large section.
- [ ] Separate states 5 and 6, which currently share one estimate.
- [ ] Sample more than one point per property once the hazard grid is finer
      than the properties, and decide how a mixture of states settles.

## Phase 3 — Lateral spreading

- [ ] Take the lateral spreading zones from the hazard module once they exist,
      and check whether the Canterbury rates need a separate lookup inside
      them. The Canterbury settlements include spreading damage, so applying a
      zone modifier to the hazard and then the same cost table may double count.

## Potential future improvements

- Distinguish the cost of land damage from the cost of the services under it.
  The settled figures bundle both.
- Carry the uncertainty rather than the percentile: the three columns are a
  distribution over properties and are currently used as three scenarios.
