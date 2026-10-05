# Step 12 — Urban slope faces: implementation plan

**Status:** Phases 1 to 3 complete, phase 4 started (the parcel join and the
GNS-only candidates are built; stage D3 of
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
- [x] Every pif tied to a property (`property_of_pifs`), and every stretch of
      GNS mapped wall with no pip near it made a `gns_only` candidate
      (`gen_gns_only_candidates`).

## Phase 3 — Checks that need only these layers

- [x] `table_urban_slope_face_checks.py`: GNS wall recall, SLIDE break recall,
      the polygon area distribution, sizs by ground group and height band, and the
      count of polygons over the review area.
- [x] Results recorded in the method file.

## Phase 4 — The wall probability and the fragility of each zone

The wall placement runs per property, in this order, and is written out in full
in `.agents/plans/placing-retaining-walls-on-pifs.md` (read that first). The
weights are judgement until **T-50** (the claim report extraction); the last item
checks them against held-out claims.

- [x] Parcel join: each pif is tied to a property, with how cleanly it sits
      (`property_share`, `n_properties`).
- [x] GNS-only candidates: mapped wall with no pip near it, as lines.
- [ ] Wall units: join adjacent candidate pifs within a property (and the
      GNS-only pieces) into walls, so one wall is not counted as several pifs.
      Decide the rule for the 2,440 pifs that straddle properties (about a fifth,
      mostly a property against a road parcel): give the wall to the property
      holding most of its pips, or to the one whose building is nearer.
- [ ] Prior probability per wall unit from slope (height band), height and the
      ground map. Needs the ground map settled (fill and rock grade).
- [ ] The GNS floor: a wall unit with a GNS mapped wall on it is at least 0.95,
      and a `gns_only` candidate is 0.8.
- [ ] Update from the property databases, keeping the Poisson-binomial update
      already written in `exposure/rw/status.md`: an NZMM flag raises the
      expected minimum to about 2 walls on the property (modestly, as NZMM
      agrees with GNS no better than chance), and the claim reports give a
      per-property count with a 30% hold-out.
- [ ] Not taken from the five-round proposal: the 20% allocation rounds, because
      the per-property update is exact and has no order effect. They return only
      if a global wall target is set.
- [ ] Walls from the probability replace the two scenarios: each wall unit is
      walled by a draw, through `with_walls` with a Series.
- [ ] Cross-validation of the probabilities on the held-out claims.
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
- Road frontage as wall evidence (the property boundary itself is built).
- The age bin of the claim property as evidence (T-50).
