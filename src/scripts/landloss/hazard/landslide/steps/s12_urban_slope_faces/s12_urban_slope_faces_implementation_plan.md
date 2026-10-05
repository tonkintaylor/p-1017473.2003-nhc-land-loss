# Step 12 — Urban slope faces: implementation plan

**Status:** Phases 1 to 3 complete, phase 4 mostly built (the wall units,
their probability and the draws per world ran over the pilot on 2026-10-05;
the fragility per element is not started; stage D3 of
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
- [x] Pif spines, end falls and the rateable property written on the siz
      table, and the GNS-only file indexed by `gns_only_id`.
- [x] Wall units: join adjacent candidate pifs within a property (and the
      GNS-only pieces) into walls, so one wall is not counted as several pifs
      (`gen_urban_slope_wall_units.py`). A pif that straddles properties goes
      to the property holding most of its pips, or the rateable one with the
      next most where that is a road parcel.
- [x] Prior probability per wall unit from the height band, a rock cut over
      2.5 m and fill (ground map material or a SLIDE fill body). The ground map
      is not settled (fill and rock grade), so the prior moves when it is.
- [ ] Read landslide step 13's cut and fill class into the prior (lower on a
      cut, lower again on a cut in rock), as the "cut" of the rock cut rule
      and as the rw `wall_position`, once step 13 is settled.
- [x] The GNS floor: a wall unit with a GNS mapped wall on it is at least 0.95,
      and a `gns_only` candidate is 0.8.
- [x] Update from the property databases with the Poisson-binomial update in
      `exposure/rw/status.md`: an NZMM flag raises the expected minimum to 2
      walls on the property, applied modestly (`BETA_NZMM_UPDATE_WEIGHT`, 0.3
      of the full update) and flagged unreliable, as NZMM agrees with GNS no
      better than chance; the claim reports give a per-property count with a
      30% hold-out.
- [x] Review fixes (2026-10-05): the spine is the geodesic diameter of the
      pif (a spanning tree's longest path folded back on thick faces); a
      corner needs the falls to turn, so stacked terraces stay apart; a
      GNS-only piece takes its property by the pif's rateable rule; one
      stacked title rule (`stack_representatives`) for pifs, records and
      claims; step 8 stops on drawn walls that name no polygon line; the
      zones read the found elements the faces script keeps. The pilot numbers
      in the method file predate them; rerun the step.
- Dropped: the 20% allocation rounds of the five-round proposal, because the
  per-property update is exact and has no order effect. They return only if a
  global wall target is set.
- [x] Walls from the probability replace the two scenarios: each wall unit is
      walled by a draw per exposure world, and the zones of each draw are
      built through `with_walls` with a Series
      (`gen_urban_slope_wall_zones.py`). The two scenarios stay as bounds.
- [~] Cross-validation of the probabilities on the held-out claims, GNS and
      the strata (`table_urban_slope_wall_checks.py`): the tables are written;
      nothing is calibrated until **T-50**, and on the pilot most claim values
      fall under the suppression limit.
- [x] Run step 12 from an orchestrator: `gen_hazard.main` runs the faces,
      wall units and wall zones, and step 12's `WORLD_IDS` is read from
      exposure rw step 6's config.
- [ ] A rule for a wall on a property boundary, which is one unit on each
      side (count it on both, or tie the two units to one draw).
- [ ] Wall units on the flat land: every unit is a face of sloping ground.
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
