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
- It reads twelve files per world and earthquake (four of them for a slip's new
  wall, below), each through its own step's path function:
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
    `crossing_landslide_damage_path(w, r)`), keyed on `crossing_id`;
  - for a slip's new wall: the candidate stretches (exposure rw step 6,
    `candidate_stretches_path(extent=...)`), the wall probabilities
    (`wall_probability_path(extent=...)`), the urban slope model
    (hazard landslide step 5, `urban_slope_model_path(w, extent=...)`) and the
    combined realisation (hazard landslide step 6,
    `combined_realisation_path(w, r, extent=...)`).
- Every row carries its asset id and the `claim_id` of the LINZ property it
  belongs to, both minted in exposure and carried unchanged. Only insured
  assets reach this step: exposure rw step 6 insures a wall by the stretches
  that support a claim's insured land, and the crossing step filters crossings
  to the insured land.
- **Land**, one row per insured land polygon, spined on the insured land so a
  polygon no hazard reached still appears:
  - columns `land_id`, `claim_id`, `Liq_LD_state`, `total_insured_land_area`,
    `land_slide_total_insured_land_area`, `inundated_insured_area`,
    `inundated_mean_depth`, `evacuated_area`, `footprint_area`,
    `property_area`, `land_slide_footprint_area` and `suburb`. No land value:
    `loss` values the land from these (`landloss.loss.qv_land_value`);
  - `land_slide_total_insured_land_area` is the union of evacuated and
    inundated ground from vul step 3, not their sum;
  - landslide areas default to zero where no landslide reached the polygon,
    and `inundated_mean_depth` defaults to missing;
  - `Liq_LD_state` is null on land off the liquefaction grid, as written by
    vul step 2;
  - `dwelling_count` is carried as an extra column, pending Q-07;
  - the imminent and re-inundated ground from vul step 3 are extra columns too,
    outside `LAND_COLUMNS` and settled by nothing in loss: `imminent_evacuated_area`,
    `reinundated_insured_area`, `reinundated_mean_depth` and
    `reinundated_volume` (zero where no landslide reached the polygon), and the
    lists `landslide_imminent_areas` and `landslide_reinundated_areas` in the
    order of `landslide_ids`. A step 3 file from before them gives none of the
    columns. The viewer's CSV reads them. Written by `build_land_table`;
  - **a slip's new wall is the mapped wall where there is one** (section 4 of
    the property damage tweaks, 2026-10-14): where the land table lists the
    failures, `attach_mapped_walls()` (`landloss.vul.mapped_walls`) adds three
    lists in the order of `landslide_ids`, outside `LAND_COLUMNS`:
    `landslide_wall_heights`, `landslide_wall_lengths` and
    `landslide_wall_sources` (`mapped wall` or `slip`). For each failure no
    damaged wall holds (the piece of its wall on the claim is damaged, matched
    on `parent_rw_id`, the rule loss settles with) it takes the failure's
    `slope_id` from the realisation, the polygon's `wall_line_id` from the
    urban slope model (so a wall that was not drawn in the world is reached the
    same way, and a drawn wall insured on no claim too), that unit's
    `face_height_m` from `wall-probability`, and the unit's stretch on the
    failure's claim from `wall-candidate-stretches`. The length is that stretch
    line cut to the part within `RW_COVERAGE_BUFFER_M` (2 m) of the failure's
    evacuated ground on the claim (`evacuated_ground_per_failure()`, 4.4), the
    stretch shared between claims on a boundary as exposure shared it, and it is
    before the margin, which loss adds. **A failure is `slip`, with no height or
    length,** when it is a large-model landslide (no `slope_id`), its polygon's
    pif is in no wall unit, its unit has no stretch on the claim, it has no
    evacuated ground on the claim, or under 1 m of the stretch lies alongside
    it (4.3); and so is one a damaged wall holds, since loss builds nothing for
    it. Two failures on one unit and claim share one wall: the one with the most
    evacuated ground takes the union of their cut stretches and the other 0. A failure on two polygons of
    one claim is one failure, with its values on the first polygon and 0 length
    on the rest. A land table without the failure lists gets no lists, and loss
    sizes every new wall from the slip. The run prints how many entries have a
    mapped wall (`describe_mapped_walls()`).
- **Retaining walls**, one row per insured wall, **spined on the world's wall
  population** (`build_rw_table(walls, states, flags)`), so a wall on sloping
  ground, which the shaking step never sees, appears beside the flat-land walls
  it does: `rw_id`, `claim_id`, `rw_size`, `rw_type`, `rw_height`, `rw_length`,
  `is_damaged_by_shaking`, `is_evacuated` and `is_inundated`.
  `is_damaged_by_shaking` is true when the shaking step's damage state is
  replace **or** the wall landslide step's flag is set (a sloping wall whose
  urban polygon failed through it); a wall with no damage state row is not
  shaking damaged by that route. `is_evacuated` and `is_inundated` come from
  the wall landslide step, which already OR-ed the urban outcome with the
  geometry. The run prints how many walls carry a damage state and how many
  take their shaking flag from the urban outcome (`describe_walls()`).
- **A wall is split onto each claim whose insured land it supports**
  (`split_walls_by_property`, 2026-10-12, RW-A31; on insured stretches since
  2026-10-14): one row per claim in the wall's `insured_lengths_m` (exposure rw
  step 6; a population without the column raises, telling the user to rerun that step),
  `<rw_id>-P<n>`, each on that claim at the length of its stretch, and each
  carrying the whole wall's type, height and damage, since the wall stands or
  fails as one. Stretches under 1 m are dropped, no piece takes a remainder, and
  the length that supports no claim's insured land is not priced. A wall with
  no stretch gives no row; a piece on a claim with no insured land is dropped.
  A wall with one stretch keeps its own id. `parent_rw_id` is written after
  the contract columns to tie the pieces back to the wall. Each piece keeps the
  whole wall's line. **Each piece also carries `rw_damaged_length`**, an extra
  column outside `RW_COLUMNS` (T-158, 2026-10-14), written when the run is given
  the world's `wall-insured-stretches-w<NNN>-<extent>.geoparquet` (exposure rw
  step 6; `build_rw_table(..., stretches=...)`): a piece damaged by shaking takes
  its whole `rw_length`; one damaged by landslide ground takes the wall's
  `damaged_line` (the line inside evacuated ground, from vul landslide rw
  step 11) cut by the claim's own insured stretch, so a wall damaged only on a
  neighbour's stretch leaves this claim's piece undamaged (0, and it loses
  `is_evacuated` and `is_inundated`); every other piece takes 0, and a piece only
  inundated keeps `is_inundated`. A damaged part lying in k claims' stretches (a
  wall on a shared boundary) gives each 1/k of its length, by
  `landloss.exposure.coverage.shared_lengths()`, the rule that shared the
  stretch, so a piece's damaged length never exceeds its `rw_length`. A piece
  damaged by landslide ground with `MIN_DAMAGED_PIECE_LENGTH_M` (0.1 m) or less
  of damage is undamaged with 0 and no flags (6.3, the lead's judgement), so a
  few millimetres of overlap cannot buy the 3 m minimum wall in loss; a piece
  damaged by shaking is not tested. The stretches and the flags' `damaged_line`
  are required together: stretches with flags written before step 11 measured
  damage raise, naming step 11. The run prints the damaged pieces and their
  damaged length (`describe_walls()`). The run prints the walls that give no
  piece. Over Lower Hutt
  world 0 before 2026-10-14 (the primary took the remainder), 7,772 walls became
  10,590 rows and the claims with a damaged wall rose from 4,961 to 6,244; the
  stretch rule has not been run on real data.
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
  `tests/landloss/vul/test_property_damage_step.py`, and the new-wall join by
  `tests/landloss/vul/test_mapped_walls.py`. It has not been run on
  the pilot since the rework, so no counts are recorded here; it needs
  the ground module, exposure steps 5, 6 and 7, landslide steps 1 to 6 and every vul step it
  reads run first.

Potential future improvements: see `s10_property_damage_implementation_plan.md`.
