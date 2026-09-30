# Step 1 — PGA realisation: implementation plan

**Status:** Dropped — superseded by `s4_pga_realisation`, 2026-09-30. PGA now
comes per 100 m cell at each cell's own site class, from step 2's Foster Vs30
grid, rather than from the NLM's single site class 5 grid. It is a new step
rather than a change to this one because it reads step 2's output, and the
step number carries the run order. The scripts are removed; this plan and the
method file stay as the record of the site class 5 beta. Phase 2 is done by
steps 2 and 4, and Phase 3 is carried over to step 4.

## Phase 1 — A shaking field of the right shape (complete)

- [x] Read the NLM 2500-year PGA grid and clip it to the extent.
- [x] Scale it by one lognormal draw per realisation, against a 10% coefficient
      of variation, seeded from the project realisation stream.
- [x] Write one raster per realisation, named for the realisation.
- [x] Print the supplied field's range and the factor each realisation applied,
      so what changed between realisations is visible.

## Phase 2 — A field with spatial detail

- [ ] Replace the ~9,930 m national grid with a field over the study area at a
      resolution the exposure can actually resolve. The plan named 100 m. At the
      current cell size the whole pilot box is one cell, so no property differs
      from its neighbour.
- [ ] Take the site class from the Foster et al. (2019) V<sub>s</sub>30 model
      per point, rather than reading the single site class 5 field (**T-15**).
- [ ] Decide whether PGV is needed. Several retaining wall fragility curves are
      velocity-based, so dropping it constrains which curves can be used.

## Phase 3 — A defensible spread

- [ ] Replace the flat 10% coefficient of variation with the ground motion
      model's own sigma.
- [ ] Replace the single field-wide multiplier with a spatially correlated
      random field. The current choice is the fully correlated end of the range;
      real ground motion decorrelates over hundreds of metres to tens of
      kilometres, and the portfolio spread depends on which is used.

## Potential future improvements

- Carry Sa(T₁) alongside PGA, which the approach names and the beta does not
  produce.
