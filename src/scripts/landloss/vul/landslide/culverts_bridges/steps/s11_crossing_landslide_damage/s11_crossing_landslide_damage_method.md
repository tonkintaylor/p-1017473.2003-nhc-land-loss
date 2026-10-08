# Step 11 — Crossing landslide damage: method

- The step records **whether a landslide reached each culvert or bridge, and
  from where**, per exposure world and modelled earthquake. It is run by
  `gen_crossing_landslide_damage.py`, and the test is
  `landloss.vul.landslide.flags.landslide_flags()`.
- The damage measure is **a flag, not an area**. A structure is settled on
  whether a landslide reached it at all, unlike land, where the quantity is how
  much ground was taken.
- Crossings come from exposure step 7's
  `temp/exposure/crossing-population-r<NNN>[-pilot].geoparquet`, read through
  `crossing_population_path(realisation_id, extent=...)`. The crossing
  population is drawn per earthquake, not per world: which structure sits at a
  crossing does not depend on which walls exist, so one population is read
  per earthquake and flagged against every world's landslides.
- Landslides come from the combined realisation landslide step 6 writes,
  `temp/hazard/landslide/landslide-realisation-w<NNN>-r<NNN>[-pilot].geoparquet`,
  read through `combined_realisation_path(world_id, realisation_id, extent=...)`:
  the large model's polygons and the urban slope model's together, treated
  alike here.
- Only insured crossings arrive here: exposure step 7 keeps a crossing only
  where it lies wholly inside its claim's insured land.
- A crossing whose geometry **intersects an evacuated polygon** is
  `is_evacuated`; one that **intersects an inundated polygon** is
  `is_inundated`. A crossing touching both kinds of ground carries both flags.
  The land classes are `landloss.hazard.landslide.land_class`'s; the urban
  model's `imminent land` sets no flag.
- `is_evacuated` is computed for **culverts as well as bridges**. The contract
  in `.agents/plans/asset-pricing-approach.md` section 1 asks for it on bridges
  only; culverts carry it as an extra column, pending **Q-09**.
- Rows are keyed on `crossing_id`, the id minted in exposure step 7, and carry
  `claim_id`. The split into `culvert_id` and `bridge_id` by structure kind
  happens at vul step 10, not here. Column names come from
  `landloss.domain.loss_contract`.
- **Every crossing is written**, one row each, with both flags False where no
  landslide reached it. The run prints how many carry each flag and how many
  carry both (`describe_damage()`).
- An empty crossing population, as over the pilot box, writes an empty file
  with the same columns and boolean flags, and the run prints "no crossings
  over this extent".
- A crossing population written before `crossing_id` existed is refused with a
  message to rerun exposure steps 5 and 7.
- Output is `temp/vul/crossing-landslide-damage-w<NNN>-r<NNN>[-pilot].parquet`,
  built by `crossing_landslide_damage_path(world_id, realisation_id, extent=...)`,
  with columns `realisation_id`, `world_id`, `crossing_id`, `claim_id`,
  `is_evacuated` and `is_inundated`.
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/landslide/culverts_bridges/test_crossing_landslide_damage_step.py`.

Potential future improvements: see `s11_crossing_landslide_damage_implementation_plan.md`.
