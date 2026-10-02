# Step 10 — Property damage: implementation plan

**Status:** Phases 1, 1a, 1b and 1c complete, with the pilot run open. The step
writes the four contract tables per world and earthquake; what the join
exposed is not yet fully resolved.

The step is numbered `s10` because step numbers run across the `vul` module
rather than across one `steps/` folder, and it sits at module level rather than
under a hazard because it is the only step that reads all of them.

## Phase 1 — One row per property (complete, superseded by Phase 1a)

- [x] Read the four vulnerability outputs and the insured land extent through
      their own steps' path functions, so the join cannot drift from what the
      steps actually wrote.
- [x] Spine the join on the insured land, so an undamaged property is present
      with zeros rather than absent.
- [x] Default a quantity to zero and a state to missing, which are different
      statements and should not be collapsed.
- [x] Count structures per property as a total and a number to replace.
- [x] Carry `dwelling_count`, `cost_year`, `rate_basis` and `cost_percentile`
      through, so the basis of every number stays with it.
- [x] Report causes per property, and size the T-27 double count.

## Phase 1a — Four contract tables (complete)

- [x] Replace the one-row-per-property join with the four tables of section 1
      of `.agents/plans/asset-pricing-approach.md`: land, retaining walls,
      culverts and bridges, assembled by `landloss.vul.loss_input`.
- [x] Key every row on its asset id and `claim_id`, both minted in exposure.
- [x] Read the wall and crossing landslide flags from the two new step 11
      landslide steps.
- [x] Split the crossings into culverts and bridges by structure kind.
- [x] Write each table as GeoParquet in EPSG:2193 with a `realisation_id`,
      through `loss_input_path()` (renamed `world_loss_input_path()` in
      Phase 1c).
- [x] Carry `dwelling_count` on land (Q-07) and `is_evacuated` on culverts
      (Q-09) as extra columns.
- [x] Keep the T-27 overlap print, now per claim.

## Phase 1b — Exposure worlds and the wall population spine (complete)

Contract `.agents/plans/urban-slope-build-contract.md` sections 3.15 and 7.14.

- [x] Read the world's wall population and spine the retaining wall table on
      it (`build_rw_table(walls, states, flags)`), so a sloping wall the
      shaking step never sees appears beside the flat-land walls it does.
- [x] Set `is_damaged_by_shaking` from either route: the shaking step's
      replace state, or the wall landslide step's flag from the urban slope
      outcome.
- [x] Read the landslide land damage, both wall files and the crossing flags
      per world and earthquake; the liquefaction and structure files stay per
      earthquake.
- [x] Loop over `WORLD_IDS` as well as `REALISATION_IDS`, name every output
      `loss-input-<table>-w<NNN>-r<NNN>[-pilot].geoparquet`, and insert
      `world_id` after `realisation_id` on every table; `vul/config.py`,
      `gen_vul.py`, `scripts/landloss/config.py` and `gen_all.py` carry
      `WORLD_IDS` and run the modules hazard, exposure, hazard urban, vul.
- [x] Run the step end to end on synthetic inputs in
      `tests/landloss/vul/test_property_damage_step.py`.
- [ ] Run on the pilot once exposure steps 5 to 7, landslide steps 1 to 9 and
      the vul steps it reads are run for world 0, and record the counts in the
      method document.

## Phase 1c — Keep the loss module's reads working (complete)

Contract `.agents/plans/urban-slope-build-contract.md` section 3.15, decision 37.
The loss module, owned elsewhere and not edited here, calls
`loss_input_path(name, realisation_id, pilot=pilot)` five times; against the
world signature of Phase 1b each call raised `TypeError`.

- [x] Rename the writer to `world_loss_input_path(table, world_id,
      realisation_id, *, pilot)` and move every vul caller and test to it.
- [x] Keep `loss_input_path(table, realisation_id, *, pilot)`, deprecated,
      returning the world 0 path, with a docstring naming the five loss callers.
- [x] Confirm, by reading without editing, that the five loss calls use the
      three-argument form the kept function takes.
- [x] Pin in `tests/landloss/vul/test_property_damage_step.py` that
      `loss_input_path(t, r, pilot=p)` equals
      `world_loss_input_path(t, 0, r, pilot=p)` and reads the file the step
      writes for world 0.
- [ ] Delete `loss_input_path()` once the loss owner moves the five calls to
      `world_loss_input_path()` with a `WORLD_IDS` setting.

## Phase 2 — Resolve what the join exposed

- [x] **T-27, retaining walls**: the project lead ruled on 2026-10-02 that a retaining wall replaced by shaking on flat land and the liquefaction land damage on the same claim are not a double count, so both are priced and the
      overlap print is information only.
- [ ] **T-27, culverts and bridges**: confirm whether the Canterbury land damage
      rates already include culvert and bridge damage.
- [ ] Decide how two causes on one property combine. They are currently written
      side by side and summed nowhere, which is correct while the landslide side
      is unpriced and will not be once it is.
- [x] Decide whether evacuated and inundated ground on one property are added or
      taken on their union. Resolved: the union, computed in vul step 3 and
      written as `land_slide_total_insured_land_area`.
- [ ] Hand `height_m` to the loss module once the loss owner has re-confirmed
      the set heights it prices at against the DEM face heights the wall
      population now carries (**I-14**, contract section 3.7).

## Phase 3 — More than one world and realisation

- [ ] Run the chain over enough worlds and realisations to have a distribution
      rather than a point, and write one set of files per pair as now.
- [ ] Add a summary across pairs, so the portfolio can be read as an
      exceedance curve rather than a single scenario, with the world and the
      earthquake variance read apart.

## Potential future improvements

- Emit one row per dwelling rather than one per property, if that turns out to
  be the shape the settlement wants. Today only the representative identifier of
  a block reaches this table, with its dwelling count beside it.
- Carry the cause of each quantity as its own column rather than folding it into
  the column name, once there is more than one hazard per asset class.
- Carry `slope_id` and the urban outcome on the retaining wall table, so the
  loss report can attribute a wall replacement to the polygon that took it.
