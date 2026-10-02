# Step 4 — PGA realisation: implementation plan

**Status:** Phases 1 to 3 complete. Supersedes step 1, which read the NLM's
single site class 5 grid. The design is in
`.agents/plans/pga-on-site-class-grid.md`.

## Phase 1 — PGA per site class (complete)

- [x] Generate TS1170.5 PGA grids per site class and return period from Table
      3.2, and check that the 2500-year site class 5 grid equals the NLM's cell
      for cell.
- [x] Give each cell of step 2's site class grid the PGA of its class.

## Phase 2 — Realisations (complete)

- [x] Scale the field by one lognormal draw per realisation, against a 10%
      coefficient of variation, as step 1 did.
- [x] Write to the path step 1 wrote to, so the vulnerability steps read the new
      field through `pga_path` with only their import changed.

## Phase 3 — Gaps in the site class grid (complete)

- [x] Give cells without a Foster Vs30 value a site class, so the 17 of 761
      pilot retaining walls on them, 60 to 194 m from the nearest classed
      cell, read a PGA. Done in step 2 by a nearest-class fill within
      200 m.

## Phase 4 — A defensible spread

- [ ] Replace the flat 10% coefficient of variation with the ground motion
      model's own sigma.
- [ ] Replace the single field-wide multiplier with a spatially correlated
      random field. The current choice is the fully correlated end of the range;
      real ground motion decorrelates over hundreds of metres to tens of
      kilometres, and the portfolio spread depends on which is used.

## Potential future improvements

- ~~Carry the same realisation factor on PGV (step 3), so PGA and PGV move
  together within a realisation.~~ Done by step 5 (`s5_pgv_realisation`),
  which recomputes this step's factor from the same seed.
- Multiple site classes from the Vs30 sigma (clause 3.1.3.4).
- Use TS1170.5 Table 3.1 inside the settlement boundaries of Figure 3.2, instead
  of the 0.1 degree grid.
