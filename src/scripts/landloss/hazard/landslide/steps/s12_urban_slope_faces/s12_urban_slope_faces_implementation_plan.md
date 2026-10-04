# Step 12 — Urban slope faces: implementation plan

**Status:** Phases 1 to 3 complete, phase 4 next (stage D3 of
`.agents/plans/building-face-based-urban-slope-polygons.md`).

The step runs the pips, pifs and sizs pipeline
(`.agents/plans/building-pip-pif-siz-slope-polygons.md`) over a whole extent,
writes its layers, attaches the evidence for retaining wall candidates to the
siz table, and runs the checks that need only those layers. It replaces steps 6
and 7 once steps 8 and 9 read its polygons (phase 5).

## Phase 1 — The pipeline over an extent

- [x] `gen_urban_slope_faces.py`: DEM (step 3), ground map (step 4) and the LINZ
      coastline in; pips, pifs, sizs and elements out.
- [x] Siz table written as GeoParquet, one row per pif, for the retaining wall
      workflow.
- [x] Elements written as polygons with their siz and its angles.
- [x] Evacuated, imminent and inundated polygons written for two scenarios:
      every siz walled, and none walled.
- [x] Counts and timings printed and recorded in the method file.

## Phase 2 — Wall candidates

- [x] `landloss.hazard.landslide.wall_candidates`: evidence per pif from the GNS
      mapped walls, the GNS cut/fill lines, the SLIDE cut and fill bodies, the
      ground map and the building outlines.
- [x] A GNS mapped wall with no siz within reach stays a candidate, classed
      small, because a 1 m grid cannot resolve a wall under about 0.5 m.
- [x] Evidence columns written onto the siz table.

## Phase 3 — Checks that need only these layers

- [x] `table_urban_slope_face_checks.py`: GNS wall recall, SLIDE break recall,
      the polygon area distribution, sizs by ground group and height band, and the
      count of polygons over the review area.
- [x] Results recorded in the method file.

## Phase 4 — The wall probability and the fragility of each zone

- [ ] A probability on each wall candidate from its evidence. Every weight is
      judgement until **T-50** (the claim report extraction).
- [ ] Walls from the probability replace the two scenarios: each siz is walled
      by a draw, through `with_walls` with a Series.
- [ ] A fragility per element, and the share of urban ground in a polygon that
      fails in a realisation, against the order of 1% the literature gives (the
      check the first pilot missed by a factor of about 40).

## Phase 5 — Replace steps 6 and 7

- [ ] Steps 8 and 9 read the polygons from this step.
- [ ] Steps 6 and 7, their figures and their tests are removed.
- [ ] The old seeding code (`find_slope_elements`) is removed with
      `fig_toy_slope_elements.py` refactored off it.

## Phase 6 — Per territorial authority

- [ ] Run over the four territorial authorities in tiles
      (`find_instability_zones` takes a `core`), in a process pool.

## Potential future improvements

- Cut the siz table's pifs at the same 20 m span as the growth, so a long pif
  is not one wall candidate.
- Property boundary and road frontage as wall evidence (needs the address
  spine's boundaries read onto the pifs).
- The age bin of the claim property as evidence (T-50).
