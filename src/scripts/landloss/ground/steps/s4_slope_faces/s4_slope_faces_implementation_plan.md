# Ground step 4 — Slope faces: implementation plan

**Status:** Phases 1 to 3 complete; phase 4 not started.

The step reads the evidence for retaining wall candidates onto the pifs of
ground step 3's grid table, makes the GNS-only candidates, and writes the siz
table. It was the wall evidence part of the old landslide step 12
(`s12_urban_slope_faces`), which also ran the search, built the wall units and
built the zones. The lead split that step on 2026-10-08: the search is ground
step 3 (`s3_instability_zones_implementation_plan.md`), the wall units and
draws are exposure rw step 6 (`s6_wall_population_implementation_plan.md`) and
the zones of each world's walls are landslide step 4
(`s4_wall_zones_implementation_plan.md`). The plan for the wall placement as a
whole is `.agents/plans/placing-retaining-walls-on-pifs.md`.

## Phase 1 — Wall candidates (complete)

- [x] `gen_slope_faces.py`: the grid table of ground step 3, the ground map of
      ground step 2 and the LINZ layers in; the siz table out, as GeoParquet,
      one row per pif, for the retaining wall workflow.
- [x] `landloss.hazard.landslide.wall_candidates`: evidence per pif from the GNS
      mapped walls, the GNS cut/fill lines, the SLIDE cut and fill bodies, the
      ground map and the building outlines.
- [x] A GNS mapped wall with no siz within reach stays a candidate, classed
      `low_height` (`small` until 2026-10-07), because a 1 m grid cannot
      resolve a wall under about 0.5 m.
- [x] Evidence columns written onto the siz table.
- [x] Parcel join: every pif tied to a property (`property_of_pifs`), with how
      cleanly it sits (`property_share`, `n_properties`); a pif that straddles
      properties goes to the property holding most of its pips, or the
      rateable one with the next most where that is a road parcel.
- [x] GNS-only candidates (`gen_gns_only_candidates`): mapped wall with no pip
      near it, as lines, cut by the shared line rules (the lead, 2026-10-07),
      indexed by `gns_only_id`.
- [x] The rateable property of a GNS-only piece by the pif's rule, and one
      stacked title rule (`stack_representatives`) for pifs, records and
      claims (review fixes, 2026-10-05).

## Phase 2 — Checks that need only these layers (complete)

- [x] `table_slope_face_checks.py`: GNS wall recall, SLIDE break recall,
      the polygon area distribution, sizs by ground group and height band, and
      the count of polygons over the review area.
- [x] Results recorded in the method file.

## Phase 3 — More wall records (the lead, 2026-10-08) (complete)

- [x] Read T+T's manually mapped walls (Koordinates 125317) beside the GNS
      mapped walls, dropping any within 2 m of a GNS wall, and use the rest
      as GNS walls are (`gen_mapped_walls`).
- [x] Move the search out to ground step 3 and the wall units and zones out to
      exposure rw step 6 and landslide step 4; run from `gen_ground.py`.

## Phase 4 — Rerun with the new inputs

- [ ] Rebuild the claim layer
      (`exposure/rw/validations/gen_rw_dataset_properties.py`, reads T:), then
      rerun this step, ground step 5 and exposure rw step 6 over the pilot.
- [ ] Rerun the pilots and Porirua through ground steps 3 and 4 with the
      fall-line siz test, and recount the candidates in the method file.

## Potential future improvements

- A `low_height` pif piece grows no element; its line element (landslide step 4)
  gives it the minimum polygon, and seeding growth on the wall's own threshold
  is the alternative.
