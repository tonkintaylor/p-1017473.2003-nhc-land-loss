# Step 2 — Land damage probabilities: implementation plan

**Status:** Phase 1 complete and runnable. Phase 2 deletes most of it, and that
is the plan rather than a regret.

This step exists because the National Liquefaction Model release in hand carries
two land damage grids and the study reports six states. Everything here that
manufactures the missing four is marked `beta` — in
`beta_expand_ld_probabilities`, in `beta_probability_path`, and in the `beta-`
that opens every file name the step writes — so that what has to go is visible
without reading the code. The whole chain it feeds is described in
`.agents/plans/beta-build.md`.

## Phase 1 — Six state probabilities over the study extent (complete)

- [x] Read the RP2500y, median groundwater exceedance grids through
      `landloss.io.nlm`, at the release `CORE_NLM_VERSION` pins.
- [x] Clip in the grids' own projection before reprojecting, with the extent
      re-expressed by `landloss.common.utils.raster.bbox_in_crs` so that a
      bowed edge does not lose a strip of ground.
- [x] Match the Major grid onto the Moderate grid cell for cell, so the
      differencing cannot silently align to nothing.
- [x] Difference the exceedance pair into bands, and refuse a swapped pair —
      `exceedance_to_bands` in `landloss.hazard.liquefaction.land_damage`.
- [x] Subdivide the None and Major bands into the four states the release does
      not carry, conserving probability by construction.
- [x] Write one GeoTIFF per state under `temp/hazard/liquefaction/`.
- [x] Print the two input means beside the six output means, so the expansion
      can be checked by arithmetic from the run output alone.
- [x] Cover the reusable pieces with tests that need neither the network nor the
      T: drive — `tests/landloss/hazard/liquefaction/test_land_damage.py` for
      the differencing and the subdivision,
      `tests/landloss/common/utils/test_raster.py` for the extent transform.

## Phase 2 — Delete the subdivision

- [ ] Read the six state probabilities from the National Liquefaction Model
      directly, once it emits land damage categories 1–6 rather than Moderate
      and Major. This is the "Beyond the prototype" item in the hazard's
      `status.md`.
- [ ] Remove `beta_expand_ld_probabilities`, `beta_probability_path` and the
      `beta-` file name prefix, leaving `exceedance_to_bands` and the clip in
      place — differencing an exceedance pair stays correct whatever supplies
      the bands.
- [ ] Check the six grids the model supplies sum to one per cell, which the
      subdivision guarantees by construction and a modelled set does not.

## Phase 3 — Lateral spreading

- [ ] Modify the probabilities inside the lateral spreading zones, which the
      beta skips entirely. The zones come from buffering the rivers; the river
      layer is the open decision in the hazard's `status.md`.
- [ ] Decide whether the modifier acts on the exceedance grids before the
      differencing or on the band probabilities after it. The two are not the
      same and the choice has to be stated in the method file.

## Phase 4 — Demands the released model is not yet built on

- [ ] Re-run against a release built on published TS1170.5 rather than the draft
      the current one uses. Every probability downstream of this step is
      provisional until then, and nothing in the code says so — only the
      hazard's `status.md` does.
- [ ] Carry more than one return period, if the loss model ends up needing a
      curve rather than the 2500-year scenario.

## Potential future improvements

- Subdivision shares with evidence behind them, if the model is still short of
  the full scale when the report is written. The Canterbury observed damage in
  `vul/liquefaction/land` is the only source that could support them.
- A validation figure over Christchurch, where mapped land damage exists to
  compare the expanded states against. Nothing checks the expansion against
  observation today; the run output checks only its arithmetic.
