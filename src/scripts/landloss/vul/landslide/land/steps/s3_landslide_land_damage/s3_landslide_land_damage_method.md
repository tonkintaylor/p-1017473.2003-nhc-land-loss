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
  behind a headscarp. It is not in `AREA_COLUMNS`, so none of the damaged
  ground above includes it, and loss settles none of it. It is measured apart
  (**T-45**, 2026-10-14) by `imminent_ground_per_property`, joined on by
  `with_imminent_ground`, on each insured land polygon:
  - `imminent_evacuated_area_m2`: the imminent polygons' union on the polygon
    less the ground **any** failure evacuated on it, counted once. Ground only
    inundated is not subtracted, because buried ground can still be imminent
    for evacuation. It does not enter `landslide_area_m2` and sets no wall or
    crossing flag;
  - `reinundated_area_m2`: the union of the inundated ground of the failures
    that have an imminent polygon anywhere in the realisation, the same
    footprint as their inundated ground and only for those failures;
  - `reinundated_volume_m3`: summed over those failures, each one's
    re-inundated area on the polygon times its own inundated depth;
  - `reinundated_depth_m`: the volume over the area, 0 where the area is 0, so
    area times depth is always the volume.

  A polygon only imminent ground reaches has a row of its own, with no damaged
  ground. The inundated depth comes from the hazard realisation's `depth_m` on
  the inundated polygons. Nothing is calibrated to the claim reports, which
  show little imminent risk from earthquakes (the lead, 2026-10-14).
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
  `evacuated_depth_m`, `inundated_depth_m`, the four imminent columns above,
  `landslide_footprint_area_m2`, the failure lists below,
  `cause_evacuated` and `cause_inundated`.
  Outputs named on the realisation alone are from before the combined
  realisation existed and are stale.
- **Each failure apart** (**T-124**, 2026-10-13). The areas above pool every
  landslide that reached a polygon. Beside them, each polygon lists those
  landslides, one entry per failure in the same order in every list:
  `landslide_ids`; `landslide_rw_ids`, the retaining wall the failure took with
  it as the realisation names it (the whole wall), or missing; `landslide_areas`,
  the ground it took on the polygon, its own deposit over its own scar counted
  once; and `landslide_inundated_areas` and `landslide_inundated_depths`. Two
  failures that buried the same ground each count it, because each is held by
  its own wall; the pooled union does not. Built by `damaged_area_per_failure`
  and `failures_per_property`, carried into the loss contract by vul step 10,
  and read by loss step 1 to give each slip its own wall.
- Beside them are three lists in the same order, kept out of the five
  (`LANDSLIDE_FAILURE_COLUMNS`) so an older table still lists its failures:
  `landslide_evacuated_areas` (the failure's evacuated ground, which sizes a
  slip's wall), `landslide_imminent_areas` (the failure's own imminent ground
  less any ground evacuated on the polygon by any failure) and
  `landslide_reinundated_areas` (its inundated ground when it has imminent
  land, else 0). A failure only imminent ground reaches on the polygon is not
  listed, so the lists stay aligned; its imminent ground is in the scalar
  total only.
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/landslide/land/test_landslide_land_damage_step.py`.

Potential future improvements: see `s3_landslide_land_damage_implementation_plan.md`.
