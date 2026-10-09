# Step 3 — PGV: implementation plan

**Status:** Phases 1 and 2 complete.

The design is in `.agents/plans/pgv-from-vs30-site-class.md`. The site class
comes from step 2.

## Phase 1 — Sa(1.0 s) per cell (complete)

- [x] Pick, per cell of step 2's site class grid, the TS1170.5 Sa(1.0 s) grid
      for that cell's class, at the configured return period.

## Phase 2 — PGV (complete)

- [x] Convert Sa(1.0 s) to PGV in m/s and write both, over the pilot and the
      four territorial authorities.
- [x] Map site class and PGV side by side.

## Potential future improvements

- Replace the ~9,930 m demand grid with one fine enough that PGV varies with
  more than the site class, for example by interpolating the Table 3.2
  parameters rather than taking the nearest grid point.
- Use TS1170.5 Table 3.1, by location name, inside the urban and rural
  settlement boundaries of Figure 3.2, where the TS says it applies instead of
  the 0.1 degree grid.
- Cite the source of the 750 mm/s per g relation in
  `landloss.hazard.shaking.pgv`.
- ~~Carry a spread on PGV per realisation, as step 1 does on PGA, once PGA and
  PGV share a site class grid, so the two move together within a realisation.~~
  Done by step 5 (`s5_pgv_realisation`), which scales this step's PGV grid by
  step 4's realisation factor.
