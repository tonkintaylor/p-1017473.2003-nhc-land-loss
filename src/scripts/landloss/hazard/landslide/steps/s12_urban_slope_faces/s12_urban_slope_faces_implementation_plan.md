# Step 12 — Urban slope faces: implementation plan

**Status:** Phases 1 to 3 complete, phase 4 mostly built (the wall units,
their probability and the draws per world ran over the pilot on 2026-10-05;
the fragility per element is not started; stage D3 of
`.agents/plans/building-face-based-urban-slope-polygons.md`).

The step runs the pips, pifs and sizs pipeline
(`.agents/plans/building-pip-pif-siz-slope-polygons.md`) over a whole extent,
writes its layers, attaches the evidence for retaining wall candidates to the
siz table, and runs the checks that need only those layers. Steps 8 and 9
read its per-world zones in place of step 7's polygons (phase 5,
2026-10-06); steps 6 and 7 are removed once that has run over the pilot.

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
      `low_height` (`small` until 2026-10-07), because a 1 m grid cannot resolve a wall under about 0.5 m.
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
- [x] Wall units (`gen_urban_slope_wall_units.py`): one per candidate
      since 2026-10-07 (joined until then). A pif that straddles properties
      goes to the property holding most of its pips, or the rateable one with
      the next most where that is a road parcel.
- [x] Prior probability per wall unit from the height band, a rock cut over
      2.5 m and fill. The ground map's rock grade is not settled, so the prior
      moves when it is.
- [x] Read landslide step 13's cut and fill class into the prior
      (2026-10-06): fill and cut and fill take the fill factor, the rock
      factor applies only to a `cut` in rock over 2.5 m, natural takes
      `BETA_NATURAL_WALL_FACTOR`, uncertain and unknown are neutral; the
      ground map's fill no longer sets it. A unit takes the class of its
      longest pif, and the rw `wall_position` follows (fill on fill and cut
      and fill, else cut). The script stops if step 13 is missing or stale.
- [x] Wall height from step 13's pips (2026-10-06): a pif's `height_m` is
      the 80th percentile of its pips' drops to the foot of the face
      (`WALL_HEIGHT_QUANTILE`), not `max_delta_h_m` (kept for reference),
      which put only 29% of the pilot's walled units under 1.5 m against 54%
      in Anderson et al. [anderson_2015]. Rerun and recheck the height shape.
- [x] The GNS floor: a wall unit with a GNS mapped wall on it is at least 0.95,
      and a `gns_only` candidate is 0.8 (0.80 and 0.70 since 2026-10-07,
      interim).
- [x] Update from the property databases with the Poisson-binomial update in
      `exposure/rw/status.md`: an NZMM flag raises the expected minimum to 2
      walls on the property, applied modestly (`BETA_NZMM_UPDATE_WEIGHT`, 0.3
      of the full update) and flagged unreliable, as NZMM agrees with GNS no
      better than chance; the claim reports give a per-property count with a
      30% hold-out. The NZMM update was removed on 2026-10-07: the flag is
      +5 points.
- [x] Points-based wall probability (the lead, 2026-10-07,
      `.agents/plans/wall-probability-points.md`): the factor prior replaced
      by points on a logistic scale (20 points double the odds from
      `BETA_WALL_BASE_P`), from verticality (new on the siz table), height,
      length, building distance, setting, step 13 class, a cut in rock over
      2.0 m or in soil, the property's wall age shares and the NHC flag; the
      table is `src/landloss/io/assets/wall-probability-points.csv`. The
      wall age moved into `gen_hazard`, before the wall units.
- [ ] Replace the interim base and GNS floor (solved for 60% of the
      factor prior's expected walls) with a calibration on the held-out
      claims and the share of properties with a wall.
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
      step 13, the wall units and the wall zones, and step 12's `WORLD_IDS` is
      read from exposure rw step 6's config.
- [x] Every wall on a siz has a polygon (the lead, 2026-10-06): a pif needs
      at least `BETA_MIN_PIF_PIPS` (3) pips, so smaller clusters are neither
      sizs nor wall candidates; every element a siz pif grows is kept even
      where the keep rule (3 m long, 0.5 m high, the grow angle, a transect)
      would drop it, with `kept_by_rule` False, its height raised to 0.5 m
      and, with no transect, a run of 0; and every polygon's width behind its
      crest is at least `BETA_MIN_EVACUATED_WIDTH_H` (0.5) of its height and
      `BETA_MIN_EVACUATED_WIDTH_M` (1 m), walled or not.
- [x] Pifs mostly inside a LINZ building outline are dropped before the siz
      test (2026-10-06).
- [x] No saw-tooth walls (2026-10-06): each unit is one line of at most
      `WALL_MAX_BENDS` bends and no section under `WALL_MIN_SEGMENT_M`, and
      `length_m` is its length.
- [x] GNS-only units given an element and polygon on
      their line; the boundary and road frontage factors and the tall face
      taper on the prior (all 2026-10-06).
- [x] The pif pieces are the pifs (2026-10-06): the siz table, step 13 and
      the wall members use the 20 m pieces the growth uses, with
      `parent_pif_id`; the units of `low_height` pifs get line elements, so every
      wall has a polygon but where its line lies on other elements or its
      polygon falls in the DEM margin.
- [x] Pifs cut by the wall rules (one implementation,
      `landloss.hazard.landslide.bend_split`) with a 50 m cap in place of the
      20 m split, and the wall height from each pip's near drop (3 m) on the
      siz table in place of step 13's walk to the foot (2026-10-06).
- [x] The rules hold on every output (2026-10-06): no pif under 3 m
      (`BETA_MIN_PIF_LENGTH_M`), each piece's line the stretch it was cut
      on, each unit one line of 3 to 50 m with at most 3 bends (walls over
      50 m after the boundary cut are cut into equal pieces,
      `WALL_MAX_LENGTH_M`), asserted in `find_instability_zones` and
      `gen_wall_units`; wall height the 70th percentile of the near drops
      within 2 m (the lead, 2026-10-06).
- [x] A 185° total turning cap on every pif piece and wall
      (`MAX_TOTAL_TURN_DEG`), and the 50 m cap cut at the line's bends, then
      (walls only) property boundaries, then evenly (2026-10-06).
- [x] Independent candidates (the lead, 2026-10-07): every siz piece, every
      `low_height` piece (renamed from `small`) and every GNS-only piece,
      itself cut by the shared line rules, is its own wall unit; the joins
      (GNS feature, end to end, GNS-only merge) and the re-cutting of joined
      walls are removed.
- [x] A wall on a property boundary (2026-10-06): units carry their length in every property they enter by 1 m
      (`property_lengths_m`), count as a wall on each in the claim update
      (keeping the highest), and are drawn once on their primary property.
      The loss side's use of the lengths is a vul rw Next item.
- [ ] Wall units on the flat land: every unit is a face of sloping ground.
- [ ] A fragility per element, and the share of urban ground in a polygon that
      fails in a realisation, against the order of 1% the literature gives (the
      check the first pilot missed by a factor of about 40).

## Phase 5 — Replace steps 6 and 7

- [x] Steps 8 and 9 read the polygons from this step (2026-10-06): step 8
      reads each world's zones (`urban-slope-zones-wNNN`) through
      `landloss.hazard.landslide.urban.face_polygons`, a polygon's wall is its
      element's wall unit, and it stops where the zones and exposure rw step
      6's drawn walls are not one draw; step 9 reads step 8's model unchanged.
      `gen_hazard.main_urban` no longer runs step 7. Not yet run over the
      pilot.
- [x] The two bounds stay for the figures: `fig_urban_slope_wall_zones.py`
      draws the walled and bare zones side by side at the pilot sites
      (`FIG_ZONE_SCENARIOS`).
- [ ] Steps 6 and 7, their figures and their tests are removed (step 6's
      candidates still feed exposure rw step 6's wall lines; step 7 is out
      of the pipeline but its scripts and library remain).
- [ ] The old seeding code (`find_slope_elements`) is removed with
      `fig_toy_slope_elements.py` refactored off it.

## Phase 6 — Per territorial authority

- [x] The faces and the wall zones run tile by tile over a 1 m DEM larger
      than `config.MAX_UNTILED_CELLS` (`tiled.py`), 2026-10-07: 3 km cores,
      750 m margins, aligned to the 3 m catchment blocks; pifs owned by their
      parent's pip centre, ids matched across tiles by pip cells and wall
      unit. Checked on the Porirua pilot with 1 km tiles against the whole
      grid: the siz table identical, 3,584 of 3,603 elements identical (19
      differ by 1 to 4 cells), the zones' areas within 0.2% (evacuated within
      0.01%), but about a third of the bare and 3% of the walled zone rows
      differ in shape (median 14 m2). The differences are not at the seams
      and not from the drainage graph; their source in
      `build_slope_polygons` is not yet found.
- [ ] Find what in `build_slope_polygons` reads beyond a tile, and make the
      tiled zones identical to the whole grid's.
- [ ] Run over Porirua, then the other three territorial authorities; a
      process pool over the tiles.

## Potential future improvements

- Walled units under 1.5 m are 73% against 54% in Anderson et al. at the
  60th percentile within 2 m (18% at the 80th within 3 m): a setting
  between the two would meet it.

- A `low_height` pif piece grows no element; its line element gives it the
  minimum polygon, and seeding growth on the wall's own threshold is the
  alternative.
- The age bin of the claim property as evidence (T-50).
- Pass the building outlines (`building_mask()`) as the barrier grid of
  `build_slope_polygons`, so debris stops at the house below (the lead,
  2026-10-07; landslide status, Next 15). Roads are not barriers.
- Settle the deposit depth limits, `BETA_MAX_DEPOSIT_DEPTH_H` (one height)
  and `BETA_MAX_DEPOSIT_DEPTH_SOURCE` (twice the source depth), both
  proposals: under them most pilot failures spread back over part of their
  scar and a quarter over all of it.
