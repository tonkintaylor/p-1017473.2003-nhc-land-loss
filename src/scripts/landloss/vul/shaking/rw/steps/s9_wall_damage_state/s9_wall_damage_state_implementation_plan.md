# Step 9 — Retaining wall damage state: implementation plan

**Status:** Phases 1, 1a and 2 complete. The step is restricted to flat-land
walls on the published wall curves, and `retaining-wall-fragility.csv` carries
the six `unnamed`-class rows read out of [koutsoupaki_2023]. Still open: naming
the wall classes, and the pilot rerun on the world-keyed population and the
PGV realisations.

## Phase 1 — A damage state on every wall (complete)

- [x] Read the wall population and the realisation's shaking field.
- [x] Sample the shaking at each wall's midpoint and carry it onto the output.
- [x] Draw no damage or replace against a failure probability.
- [x] Seed the draw from the realisation's vulnerability stream, so it
      reproduces and pairs with the hazards of the same modelled earthquake.
- [x] Report the split, the shaking range, and how many properties carry a
      wall to replace.

## Phase 1a — Ids and geometry for the loss contract (complete)

- [x] Carry `rw_id` and `claim_id` from the wall population, using the names in
      `landloss.domain.loss_contract`.
- [x] Keep the wall line as geometry, in the population's CRS, so the loss table
      has coordinates.
- [x] Write GeoParquet (`.geoparquet`) instead of plain parquet.

## Phase 2 — A real fragility, on PGV, for flat-land walls (complete)

Contract sections 3.11 and 7.12 of `.agents/plans/urban-slope-build-contract.md`.

- [x] Restrict the step to walls with `is_flatland` true. A sloping wall stands
      on an urban failure polygon's edge and is drawn with it by landslide
      step 9, so it is not drawn here.
- [x] Move the intensity measure from PGA to PGV: read shaking step 5's
      `pgv_path(r)` instead of step 4's PGA.
- [x] Index the curve on size class and initial condition through
      `landloss.vul.shaking.fragility.wall_failure_probability()`, which reads
      the wall curves through `landloss.hazard.landslide.urban.fragility`.
- [x] Convert a PGA-published curve at the wall's own PGV/PGA ratio (step 3's
      PGV over the unscaled TS1170.5 PGA at `RETURN_PERIOD_YR`, sampled at the
      midpoint) and record the site class, the ratio and the published PGA
      median on the output.
- [x] Key the output on the exposure world and the earthquake,
      `wall-damage-state-w<NNN>-r<NNN>[-pilot].geoparquet`, with a `world_id`
      column, and append the world to the seed so two worlds draw
      independently.
- [x] Exercise the step end to end on synthetic inputs in
      `tests/landloss/vul/shaking/test_wall_damage_state_step.py`.
- [x] Fill `retaining-wall-fragility.csv` (fragility phase of the urban slope
      build, contract section 8.1). Implementer H filled the six
      unnamed-class rows, one per size class and initial condition, from
      Tables A1 and A5 of [koutsoupaki_2023], so every unnamed-class wall
      now finds a curve. The step's tests still supply their own synthetic
      table.
- [ ] Name the wall classes the curves are defined for and replace the one
      `unnamed` class. This is still the open decision in the retaining wall
      exposure status file.
- [ ] Rerun the pilot once exposure rw step 6 writes the world-keyed population
      carrying `is_flatland`, and shaking step 5 the PGV realisations.

## Literature review (2026-10-02)

Part C of the second review read the wall curves against the Canterbury wall
population [anderson_2015]. The detail is in `.agents/context/retaining-wall-fragility.md`, "Literature review: the curves against Canterbury".
Proposals for the lead:

- [ ] Replace the Koutsoupaki medians in `retaining-wall-fragility.csv` with
      medians anchored on the Canterbury Very Poor share by height: about
      3.1 g under 1.5 m to 2.0 g over 3.5 m, at β 0.6 (ours). Keep the
      Koutsoupaki modern-to-poor ratio for condition. At 1.0 to 1.7 g the
      current curves fail 30 to 93% of walls, against about 10% observed.
      Flat-land walls are mostly in the lowest band.
- [ ] Keep two states. "Replace" is Anderson's Very Poor, with the Poor class
      added as the high case.
- [ ] Name the six classes after Anderson's wall types: gravity masonry,
      concrete block, timber pole, crib, gabion, and MSE or engineered
      concrete. Index the curves on them once the claim report extraction
      (**T-50**) gives Wellington's mix of types.

## Phase 3 — Once the shaking field varies within a site class

- [ ] Rerun when a ground motion model, rather than one factor per
      realisation, drives the spread in PGV. Today a realisation scales step
      3's grid by one factor, so the spatial variation across the walls is the
      site class pattern only.
- [ ] Decide whether walls on one property fail together. They are drawn
      independently, and two walls on the same ground are not independent.

## Potential future improvements

- Carry the failure probability forward as a probability rather than a draw, so
  the portfolio can be evaluated in expectation as well as by realisation.
- Hoist `WORLD_ID_COLUMN` into `landloss.domain.loss_contract` once the loss
  tables carry it, so every producer names it from one place.
