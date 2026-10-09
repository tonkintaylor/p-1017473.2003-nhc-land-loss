# Step 10 — Property damage: method

- The step writes the **four tables vul hands to loss**, per exposure world
  and modelled earthquake, as set out in section 1 of
  `.agents/plans/asset-pricing-approach.md`: land, retaining walls, culverts
  and bridges. It is run by `gen_property_damage.py` and adds no modelling of
  its own. Every number it writes was decided by the step it came from.
- The assembly is in `landloss.vul.loss_input`: `build_land_table()`,
  `build_rw_table()` and `build_crossing_tables()`. The contract column names
  come from `landloss.domain.loss_contract`, and each builder checks them with
  `check_contract_columns()` before returning.
- It reads eight files per world and earthquake, each through its own step's
  path function:
  - the insured land (exposure step 5, `insured_land_path(extent=...)`);
  - the world's wall population (exposure rw step 6,
    `wall_population_path(world_id, extent=...)`);
  - the liquefaction land damage (vul step 2, `liq_land_damage_path(r)`, per
    earthquake only) and the landslide land damage (vul step 3,
    `landslide_land_damage_path(w, r)`), both keyed on `land_id`;
  - the retaining wall damage states (`vul/shaking/rw` step 9,
    `wall_damage_state_path(w, r)`, flat-land walls only) and the wall
    landslide flags (`vul/landslide/rw` step 11,
    `wall_landslide_damage_path(w, r)`, every wall), keyed on `rw_id`;
  - the culvert and bridge damage states (`vul/shaking/culverts_bridges`
    step 9, `structure_damage_state_path(r)`, per earthquake only) and the
    crossing landslide flags (`vul/landslide/culverts_bridges` step 11,
    `crossing_landslide_damage_path(w, r)`), keyed on `crossing_id`.
- Every row carries its asset id and the `claim_id` of the LINZ property it
  belongs to, both minted in exposure and carried unchanged. Only insured
  assets reach this step: the exposure steps filter walls and crossings to the
  insured land.
- **Land**, one row per insured land polygon, spined on the insured land so a
  polygon no hazard reached still appears:
  - columns `land_id`, `claim_id`, `$/m2 market value` (the exposure land
    rate including GST, `land_rate_incl_gst_nzd_per_m2`; the exclusive rate
    stays in the exposure file), `Liq_LD_state`, `total_insured_land_area`,
    `land_slide_total_insured_land_area`, `inundated_insured_area`,
    `inundated_mean_depth` and `evacuated_area`;
  - `land_slide_total_insured_land_area` is the union of evacuated and
    inundated ground from vul step 3, not their sum;
  - landslide areas default to zero where no landslide reached the polygon,
    and `inundated_mean_depth` defaults to missing;
  - `Liq_LD_state` is null on land off the liquefaction grid, as written by
    vul step 2;
  - `dwelling_count` is carried as an extra column, pending Q-07.
- **Retaining walls**, one row per insured wall, **spined on the world's wall
  population** (`build_rw_table(walls, states, flags)`), so a wall on sloping
  ground, which the shaking step never sees, appears beside the flat-land walls
  it does: `rw_id`, `claim_id`, `rw_size`, `rw_length`,
  `is_damaged_by_shaking`, `is_evacuated` and `is_inundated`.
  `is_damaged_by_shaking` is true when the shaking step's damage state is
  replace **or** the wall landslide step's flag is set (a sloping wall whose
  urban polygon failed through it); a wall with no damage state row is not
  shaking damaged by that route. `is_evacuated` and `is_inundated` come from
  the wall landslide step, which already OR-ed the urban outcome with the
  geometry. The run prints how many walls carry a damage state and how many
  take their shaking flag from the urban outcome (`describe_walls()`).
- **Culverts and bridges** are split from the crossings by structure kind, the
  `crossing_id` becoming `culvert_id` or `bridge_id`:
  - culverts: `culvert_id`, `claim_id`, `is_inundated`, `is_damaged` (the
    shaking damage state is replace), plus `is_evacuated` as an extra column
    pending Q-09;
  - bridges: `bridge_id`, `claim_id`, `is_damaged_by_shaking`, `is_evacuated`
    and `is_inundated`.
- An asset with no landslide flags row stops the run rather than defaulting to
  undamaged (`_merge_flags()` in `landloss.vul.loss_input`); so does a wall
  damage state naming a wall not in the population.
- The geometry comes from the exposure layers (the insured land polygon, the
  wall line and the crossing geometry) and supplies the coordinates. Each table
  is written in EPSG:2193, reprojected if needed, and refused if it has no CRS
  (`in_default_crs()`).
- Each table carries `realisation_id` as its first column and `world_id` as
  its second (`loss_input.WORLD_ID_COLUMN`); neither is a contract column.
- The run prints, per world and earthquake:
  - land polygons, claims and dwellings, and the liquefaction states present;
  - the landslide union total against the evacuated plus inundated sum, to show
    what the union avoids double counting;
  - walls, culverts and bridges, with the count carrying each flag;
  - the **T-27** overlap: claims carrying both a liquefaction land damage state
    and a wall damaged by shaking, printed for information. Both are priced:
    the project lead ruled on 2026-10-02 that a retaining wall replaced by shaking on flat land and the liquefaction land damage on the same claim are not a double count.
- **Nothing is settled.** Caps, excesses, GST and pricing belong to the loss
  module, which this step does not touch.
- Output is `temp/vul/loss-input-<table>-w<NNN>-r<NNN>[-pilot].geoparquet`,
  one file per table (`land`, `rw`, `culverts`, `bridges`), from
  `world_loss_input_path(table, world_id, realisation_id, extent=...)`. The step
  writes through it and every vul caller and test uses it; `world_id` is
  positional with no default.
- The loss module reads the tables through `world_loss_input_path` too, per
  exposure world and earthquake, with its own `WORLD_IDS` setting (T-66). The
  old world-less `loss_input_path` is deleted.
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/test_property_damage_step.py`. It has not been run on
  the pilot since the rework, so no counts are recorded here; it needs
  the ground module, exposure steps 5, 6 and 7, landslide steps 1 to 6 and every vul step it
  reads run first.

Potential future improvements: see `s10_property_damage_implementation_plan.md`.
