# Step 0 — Land cover cap: implementation plan

## Phase 1 — The cap on real data (complete)

- [x] Aggregate vul's four tables onto `claim_id`, which was item 5 of the loss
      module's Next list: `landloss.loss.claims.land_by_claim()` and
      `damaged_walls()`.
- [x] Build the damaged area from both causes, with the liquefaction state read
      as damaging the whole insured area and the two causes combined with a
      maximum.
- [x] Value the damaged land with the Act's area cap applied, and record whether
      it bound.
- [x] Price each damaged wall's undepreciated value at the beta flat rate, sum
      over the claim, and record whether the sub-cap bound.
- [x] Assemble the cap with `land_cover_cap_nzd()` and write one row per claim.
- [x] Run the module through `scripts.landloss.pipeline.run_steps`, so a
      settlement step can join it without the runner changing shape.

## Phase 2 — What the cap is still missing

- [ ] Price culverts and bridges, which contribute nothing today. Until then a
      claim whose only damaged structure is a crossing caps on its land alone.
- [ ] Replace the beta flat wall rate with a real mapping from size class and
      condition onto a construction type. The rates span a factor of 21, so this
      moves the wall half of the cap more than anything else.
- [x] Value liquefied land over the damaged area `vul` sends,
      `Liq_LD_damaged_area`, rather than the whole insured area (**T-56**).
- [ ] Confirm the overlap assumption inside that area -- 30% of the evacuated
      land lying under the inundated (**L-44**) -- and that the maximum is the
      right combination where both causes reach one polygon.

## Phase 3 — The settlement

- [ ] A repair cost for a wall, which needs the three site ratings (**Q-10**).
      Only `earthworks_required` can be derived today, from inundation volume.
- [ ] A repair cost for damaged land, which needs the Land SOW. The Canterbury
      liquefaction rates exist but are 2010/11 dollars excluding GST and reach
      no settlement yet.
- [ ] Settle with `settle()` once both exist, and report the share of claims
      binding on each constraint, which is the module's stated validation.

## Notes

- **Steps number from 0 within their own module, and the numbers are unique
  across it.** The `sN_` prefix on a script is the order to run the module in:
  someone new should be able to follow the prefixes from `s0_` upwards and have
  run `loss`. No two runnable scripts in the module may share a number, so the
  next step to land here is `s1_`, whether or not it sits in this step's
  directory. Scripts that are not part of the run, such as the `fig_` figures
  elsewhere in the repo, carry no prefix and no number.
- The other modules do not follow this yet, so the rule starts here. Exposure
  begins at 1 and vul at 2; vul repeats step numbers (two 9s, two 11s); and
  exposure has two `s1_` scripts —
  `exposure/steps/s1_address_spine/s1_build_address_spine.py` and
  `exposure/land/steps/s2_land_value/s1_build_terrain_attributes.py` — so its
  prefixes do not give a run order. A cross-module reference such as "vul step
  10" in these documents names the step as it is called today, not as it would
  be under this rule.
- The sub-cap bound on no claims in the pilot run. That is worth watching rather
  than assuming: a sub-cap that never binds is doing no work, and the module's
  validation list calls it out for exactly that reason.
