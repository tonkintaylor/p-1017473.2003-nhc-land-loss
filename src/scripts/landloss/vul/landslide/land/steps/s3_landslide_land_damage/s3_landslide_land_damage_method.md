# Step 3 — Landslide land damage: method

- The step measures **how much of each property's insured land a landslide
  took, and from where**, per exposure world and modelled earthquake. It is
  run by `gen_landslide_land_damage.py`, and the arithmetic is in
  `landloss.vul.landslide.land.damaged_area`.
- The damage measure is **geometric, not a damage state**. A landslide either
  covers part of a property or it does not, and how much it covers is the whole
  question — unlike liquefaction, where the property carries a state.
- Properties come from `temp/exposure/insured-land[-pilot].geoparquet`
  (exposure step 5's `insured_land_path()`) and landslides from the combined
  realisation landslide step 6 writes,
  `temp/hazard/landslide/landslide-realisation-w<NNN>-r<NNN>[-pilot].geoparquet`,
  read through `combined_realisation_path(world_id, realisation_id, extent=...)`.
  The combined realisation holds the large model's polygons and the urban slope
  model's together, with a `population` column saying which; this step treats
  them alike, because a square metre of insured land does not care which model
  took it.
- The realisation is read per world as well as per earthquake because the
  urban failures depend on which walls the world drew.
- The step runs **per insured land polygon**: `main()` calls
  `damaged_area_per_property(insured, landslides, id_column=LAND_ID_COLUMN)`,
  so rows are keyed on `land_id`, the id minted in exposure step 5. `claim_id`
  (the LINZ property) is inserted after it, mapped from the insured land. Both
  column names come from `landloss.domain.loss_contract`.
- The land classes are the hazard module's,
  `landloss.hazard.landslide.land_class`, re-exported by `damaged_area`. The
  two kinds of ground stay apart all the way through, because the policy
  settles them differently: **evacuated** ground is what the failure removed,
  **inundated** ground is where the debris came to rest, which may have started
  on somebody else's property.
- The urban model also writes a third class, **imminent** ground left standing
  behind a headscarp. It is in `damaged_area.IGNORED_LAND_CLASSES` and measures
  nothing here: a polygon only imminent ground reaches is absent from the
  output, until the register decides how it is settled (**T-45**). The run
  prints how many such polygons the realisation carries.
- **Inundated area is measured on the union** of the landslides that reached a
  property, not summed across them. Evacuated polygons are pairwise disjoint by
  construction across both populations; inundated ones are not, because two
  failures either side of a gully both land in its floor, and ground buried
  twice is buried once.
- Each kind carries the **depth** of the material, area-weighted where more than
  one landslide reached the property. Depth is written onto the polygons by the
  hazard step, not computed here: the large model's from the volume–area power
  law in `landloss.hazard.landslide.geometry`, the urban model's from the fixed
  state geometry of its polygon.
- `check_within_insured_area()` asserts that neither kind of damaged ground
  exceeds the property's own insured area, and the run prints the result. The
  two together may legitimately exceed it, because evacuated and inundated
  ground can overlap each other. It is run with `id_column=LAND_ID_COLUMN`.
- The two kinds are also measured **together, on their union**, written as
  `landslide_area_m2` (`damaged_area.UNION_AREA_COLUMN`). Ground that is both
  evacuated and inundated counts once, so this is the loss contract's
  `land_slide_total_insured_land_area`, renamed at vul step 10. The check also
  flags a union larger than the insured area or smaller than the larger kind.
- `describe_landslides()` prints the realisation's polygons by population and
  land class; `describe_damage()` prints the union total beside the per-class
  totals, and the area the sum of the two would have counted twice (sum minus
  union).
- A land polygon no landslide reached is **absent from the output**, rather than
  present with zeros.
- **No cost is attached.** The T+T landslip remediation schedule is not
  packaged, so this step stops at area and depth and the pricing is left to the
  loss module.
- Output is `temp/vul/landslide-land-damage-w<NNN>-r<NNN>[-pilot].parquet`,
  built by `landslide_land_damage_path(world_id, realisation_id, extent=...)`,
  with columns `realisation_id`, `world_id`, `land_id`, `claim_id`,
  `evacuated_area_m2`, `inundated_area_m2`, `landslide_area_m2`,
  `evacuated_depth_m`, `inundated_depth_m`, `cause_evacuated` and
  `cause_inundated`. Outputs named on the realisation alone are from before
  the combined realisation existed and are stale.
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/landslide/land/test_landslide_land_damage_step.py`.

Potential future improvements: see `s3_landslide_land_damage_implementation_plan.md`.
