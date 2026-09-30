# PGA on the site class grid

**Status:** Implemented as
`src/scripts/landloss/hazard/shaking/steps/s4_pga_realisation/`, with step 1
retired. Progress is tracked in that step's implementation plan.

## Context

The shaking module now assigns a TS1170.5 site class per 100 m cell from the
Foster et al. (2019) Vs30 model (`steps/s2_site_class`), and PGV is built on
that grid (`steps/s3_pgv`). PGA still comes from step 1
(`steps/s1_pga_realisation`), which reads the NLM's single **site class 5**
2500-year grid at ~9,930 m cells:

- every property is treated as the same ground;
- the pilot box is one cell.

This plan puts PGA on the same site class grid as PGV. PGA and PGV then come
from one spectrum at one class per cell, and the per-cell spread of shaking is
visible to the vulnerability steps.

Two things make this cheap:

- **The source is already proven.** Rasterising TS1170.5:2025 Table 3.2's PGA
  column on its 0.1° grid and warping it to NZTM reproduces the NLM's
  `pga_2500yr_site_class_5.tif` exactly: every cell, the nodata footprint and
  the transform. This was checked while building
  `static_data_gen/gen_ts1170_sa_t1.py`. Generating PGA per site class and
  return period from the table therefore gives the NLM's numbers, from the same
  source and code path as Sa(1.0 s).
- **The downstream steps read PGA through a path function.** The retaining wall
  and culvert/bridge damage state steps (`vul/shaking/rw/steps/s9_…` and
  `vul/shaking/culverts_bridges/steps/s9_…`) read the field through
  `pga_path(realisation_id, pilot=…)` and sample it at points. A finer grid
  needs no change to how they sample.

## Approach

### 1. TS1170.5 PGA grids per site class and return period

- Extend `src/scripts/landloss/hazard/shaking/static_data_gen/gen_ts1170_sa_t1.py`
  into `gen_ts1170_grids.py`. Keep the rasterise-and-warp code as it is and
  write two measures:
  - Sa(1.0 s), as now, to `v1/sa_t1/`;
  - PGA straight from the table's `pga_g` column, to `v1/pga/`, as
    `pga_{rp}yr_site_class_{sc}.tif`.

  That is 42 more grids. As before, they go to the local cache mirror and to
  `%USERPROFILE%\Downloads\my\`, for copying to
  `R:\DataLibrary\210.14_seismic_demands_NZ_TS1170_5\v1\pga\`.
- In `landloss.io.ts1170`:
  - add `TS1170_PGA_DIR`, `ts1170_pga_fname(rp, sc)` and
    `get_ts1170_pga(rp, sc)`;
  - make the file-name validation shared between the two measures;
  - add tests mirroring the Sa(1.0 s) ones.
- Check: the 2500-year, site class 5 PGA grid equals the NLM's grid cell for
  cell.

### 2. A shared "demand on the site class grid" helper

`s3_pgv/gen_pgv.py` has `sa_t1_by_site_class`: read each class's grid and
`reproject_match` it to the site class grid by nearest neighbour. PGA needs the
same thing, so move it into the library:

- add `landloss.hazard.shaking.site_class.demand_on_site_class_grid(read_grid,
  site_class, *, return_period_yr)`;
- it returns the per-cell selection: it reads each class's grid with
  `read_grid(return_period_yr, c)`, matches it to the grid, and applies
  `select_by_site_class`;
- `gen_pgv.py` switches to it;
- add a unit test with two small per-class grids.

### 3. The PGA step on the site class grid

This goes in **a new step, `steps/s4_pga_realisation/`**, rather than a change
to s1. Step numbers carry the run order and s1 would now depend on step 2's
output. s1 is also imported by the vulnerability steps, so it cannot be
renumbered (`.agents/skills/adding-steps-scripts/SKILL.md`).

- `config.py`: `PILOT`, `REALISATION_IDS`, `RETURN_PERIOD_YR = 2500`.
- `gen_pga_realisations.py`, with `main(*, pilot, realisation_ids,
  return_period_yr)`:
  1. read the site class grid through `s2_site_class.gen_site_class.site_class_path`,
     raising if step 2 has not been run over the extent (as `gen_pgv.read_site_class`
     does);
  2. build the per-cell PGA with `demand_on_site_class_grid(get_ts1170_pga, …)`;
  3. per realisation, scale it with the existing
     `landloss.hazard.shaking.pga.beta_pga_realisation`, seeded by
     `realisation_seed(BASE_SEED, rid, "shaking")`, unchanged;
  4. write to `pga_path(realisation_id, pilot=…)`, keeping the name
     `temp/hazard/shaking/beta-pga-rNNN[-pilot].tif` and `pga_g`.
- Move `resolve_extent` and `pga_path` so that nothing imports them from s1:
  - `resolve_extent` goes to `s2_site_class/gen_site_class.py`, the first step
    that reads the extent now. s2 and s3 import it from there.
  - `pga_path` goes to s4.
- Switch the two vulnerability `s9_…` scripts to import `pga_path` from s4.
- Retire s1:
  - mark its plan `Dropped — superseded by s4_pga_realisation`, with the
    reason;
  - delete its script and config;
  - keep its plan and method files, so the record of the site class 5 beta
    stays readable.

### 4. Tidy-ups the change makes possible

- Remove `constants.BETA_SITE_CLASS`. Nothing reads it any more, and its
  comment says it goes once Foster supplies the class per location.
- Leave `landloss.io.nlm.get_nlm_scenario_pga_2500yr*` in place. They are
  tested readers of the NLM release and the check in stage 1 uses them.
- Update the docstring of `landloss.hazard.shaking.pga`. It describes the input
  as "a single assumed site class rather than a per-point Vs30", and that stops
  being true.

### 5. Docs

- s4 gets a plan and a method file per the steps skill.
- The s1 plan gets its `Dropped` note, and this plan gets a status line.
- Changelog fragment:
  - `doc/whatsnew/mm.feature.<yymmddhhmm>.md` for the PGA change;
  - `mm.removal.<…>.md` for dropping `BETA_SITE_CLASS` and s1.
- `status.md` is untouched, because it carries only what the project lead
  supplies. Offer wording instead.

## Things to expect in the results

- **PGA falls on softer ground at 2500 years.** At the Wellington grid point
  the table gives PGA of 1.74, 1.77, 1.68, 1.27, 1.00 and 0.97 g for Classes I
  to VI, which is non-linear site response. Sa(1.0 s) rises the other way. So
  on the soft valley floors the new PGA is **lower** than the stiff hillsides',
  and lower than site class 2 anywhere. This is the TS1170.5 behaviour, not a
  bug, and it is worth saying in the method file because it reverses the
  intuition that soft ground shakes harder.
- The old field was site class 5 everywhere. Most of the study area is Class
  II, which carries a higher PGA than V (1.77 against 1.00 g at the Wellington
  point), so **PGA rises over most of the study area**, and so will PGA-driven
  damage.

## Verification

- Run `uv run --frozen pytest`, then `uv run --frozen prek run --files <all
  touched files>` until clean. Use `--files` rather than `-a` so that new
  untracked files are checked. Then `ruff check --select FIX`.
- Grid check: `get_ts1170_pga(2500, 5)` equals the NLM `pga_2500yr_site_class_5`
  grid cell for cell.
- Step check on the pilot, run s2 then s4:
  - each class's cells carry the table value (Class II 1.77, III 1.68, IV 1.27,
    V 1.00 g at the Wellington point) times the realisation factor;
  - the output is on the site class grid.
- Downstream check: run the two vulnerability `s9_…` steps on the pilot and
  confirm they read the new field. The printed PGA ranges should now span
  several values rather than one.

## Potential future improvements

- Carry the same realisation factor on PGV (s3), so PGA and PGV move together
  within a realisation.
- The ground motion model's own sigma and a spatially correlated field, in place
  of the flat 10% multiplier. This is s1's Phase 3, carried over to s4.
- Multiple site classes from the Vs30 sigma (clause 3.1.3.4).
