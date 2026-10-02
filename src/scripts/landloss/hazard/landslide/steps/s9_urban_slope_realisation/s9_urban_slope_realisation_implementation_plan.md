# Step 9 — Urban slope realisation: implementation plan

**Status:** Phase 1 complete, and Phase 2's two integration items (the step 8
import and the shared fragility) and the review corrections (decisions 34
and 35) complete; the pilot run end to end (the open
Phase 2 item) and the Phase 3 checks remain. Phase 4
of `.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`;
the contract is sections 3.10, 5 and 7.11 of
`.agents/plans/urban-slope-build-contract.md`.

## Phase 1 — The draw, the resolution and the two outputs (complete)

- [x] Sample the earthquake's PGV at each polygon's representative point
      (`realisation.sample_pgv`).
- [x] Evaluate each row's lognormal fragility and draw one uniform per row on
      the `"urban"` stream seeded on the earthquake and the world
      (`realisation.draw_failures`).
- [x] Supersede every failed polygon whose evacuated polygon shares ground
      with a large-model evacuated polygon (`realisation.supersede_by_large`;
      failed polygons only since the review, see below).
- [x] Absorb nested failures largest first among the failed polygons that
      were not superseded, an absorbed polygon absorbing nothing, as step 1's
      `drop_overlapping` does (`realisation.resolve_overlaps`). Supersession
      runs first so every absorber is a survivor in the combined file; with
      absorption first, a polygon absorbed by an absorber that was then
      superseded, lying outside the large landslide, was counted nowhere.
- [x] Polygons that only touch along an edge or at a corner share no ground:
      neither absorbs nor supersedes on contact alone
      (`realisation.SHARED_GROUND_TOLERANCE_M2`).
- [x] Write the survivors' evacuated, inundated and imminent polygons beside
      the large-model rows as one combined realisation carrying both ids
      (`realisation.to_landslide_rows`, `realisation.combine_with_large`).
- [x] Write the wall outcome table spined on the world's sloping-land walls
      (`realisation.wall_outcomes`).
- [x] A figure of the draw by outcome over the extent, read from the two
      files the run wrote (`fig_urban_slope_realisation.py`).
- [x] Tests on synthetic model rows, a synthetic PGV grid and synthetic large
      polygons, running the step through `main()`.

## Review corrections (2026-10-02, contract decisions 34 and 35; complete)

- [x] One uniform per wall line (decision 34): `draw_failures` still draws one
      uniform per row in model order, then every row whose `wall_state` is
      not `no_wall` takes the uniform of the first row in model order on the
      same `wall_line_id`, so a wall on polygons at several scales fails or
      stands once, at the published rate, rather than at 1 − Π(1 − p_i).
      Rows without a wall keep their own uniform.
- [x] Only a failed polygon is superseded (decision 35): `realise()` runs
      `supersede_by_large` on the failed rows' evacuated geometry and maps the
      result onto every model row, `NONE` where the row did not fail; the
      wall outcome table reads a polygon that did not fail as `standing`
      whatever position it is handed. A wall a large slide reaches is left to
      vul step 11's line intersection.
- [x] Tests: two rows on one `wall_line_id` read one uniform and fail or stand
      together while rows without a wall keep their own; a polygon that did
      not fail under a large slide stands, and a failed one there is
      superseded with `taken_by` set.

## Review corrections (2026-10-02, second review; complete)

- [x] Every line of a wall split at a property boundary takes the polygon:
      the wall outcome table joins the population to the model on
      `wall_line_id` through the model's `wall_line_ids` (every edge line
      that drew a wall, step 8) rather than on `rw_id`, so no sloping line
      on a polygon's edge is left `standing` with `slope_id` null. The shared
      uniform of decision 34 groups rows by any line they share,
      transitively.
- [x] Every run prints the rate setting and factor of the model file
      (`describe_rate_setting()`), and refuses a file carrying more than one
      setting.
- [x] Tests: a wall split into two lines on one polygon edge gives both lines
      the polygon's outcome; rows sharing any line read one uniform; the run
      prints the rate setting; a mixed-setting file is refused.

## The wall fails with any of its polygons (2026-10-02; complete)

- [x] If any polygon on a wall fails, fail every polygon on that wall
      (`_fail_with_the_wall`, on the groups `_wall_groups` builds), the
      project lead's rule; tested in
      `test_if_any_polygon_on_a_wall_fails_every_polygon_on_it_fails` and
      `test_a_wall_none_of_whose_polygons_fail_stands_for_all_of_them`.

## Phase 2 — Integration with the steps built alongside

- [x] Replace the stand-in `urban_slope_model_path` in
      `gen_urban_slope_realisation.py` with the import from
      `s8_urban_slope_fragility/gen_urban_slope_fragility.py` once that script
      exists; the stand-in spells the contract path exactly.
- [x] Point `draw_failures` at `urban.fragility.lognormal_failure_probability`
      in place of the module's own evaluation of the same curve.
- [ ] Run the pilot end to end once step 1 writes `population`, `unit_id` and
      string `landslide_id` rows (contract section 3.9) and step 8 writes the
      model file.

## Literature review (2026-10-02)

Part A of the second review read this step against `temp/gns_review/`. The
draw, supersession and absorption stand. What changes, all proposals for the
lead, follows from the face polygons (faces plan, phase 3):

- [ ] **Group by face segment.** One wall is one face; a long face is cut
      into segments of about `BETA_FACE_SEGMENT_VOLUME_M3` along the contour,
      so a wall's draw is per segment, not per wall line. The "wall fails with
      any of its polygons" rule then fails one segment of a long wall, not the
      whole of it, which matches walls that collapsed in part in Canterbury
      (`anderson2015-F24`). The shared-uniform and transitive-line grouping
      reduce to the face segment id.
- [ ] **The geometry is read, not computed here.** The inundated polygon is
      the reach-angle runout from the crest, clipped at the next building or
      road, and the imminent polygon the band to a 35° repose line from the
      toe, both written by the faces step [de_vilder_2022; de_vilder_2024].
      No change to `to_landslide_rows`.
- [ ] **Absorption and the inundated strip.** Under the face rules an
      inundated strip routinely runs past the evacuated ground of the polygon
      that absorbs it, so the open question below ("an inundated strip of an
      absorbed failure ... is lost with it") matters more than before. The
      proposal is to keep the absorbed polygon's inundated ground where it
      falls outside the absorber's.

## Phase 3 — Checks

- [ ] Over the pilot: the realised share of polygons failing against the
      fragility they were drawn from, per rate setting (plan Verification).
- [ ] The share of urban failures confined to one property, against the local
      expectation under "Local failures versus global failures" in
      `.agents/context/land-damage-mechanisms.md`, and the failed polygon sizes
      against the Wellington cut-failure record, about 10² to 10⁴ m³
      [hancox_2013_slope_types] (`sr2013-058-F12`). Multi-property failures
      are expected on gully fills and colluvium (`brown2005-F29`,
      `sr2013-058-F06`).
- [ ] The evacuated share of face area by Kingsbury zone, after absorption,
      against the anchors read as shares of area (anchoring plan, question 1).
- [ ] A table for the report of the realised failure rate of banks against
      walls, by wall state, wall type, height band, condition and Kingsbury
      zone, with an unsupported cut of the same height beside each wall
      class (the lead, 2026-10-02; what to set it against is in
      `landslide-notes.md`, "Failure rates of banks against walls, for the
      report").

## Potential future improvements

- Absorption and supersession are tested on the evacuated geometry only; an
  inundated strip of an absorbed failure that reaches past its absorber's is
  lost with it. Whether that ground should still count is open.
- A wall whose line sits on polygons at several scales takes the highest-ranked
  outcome among them (superseded, failed with polygon, absorbed, standing); a
  rule by scale, keeping the finest polygon's outcome, is the alternative.
- The run writes no per-polygon outcome, so the figure colours absorbed
  and superseded polygons only where a wall records them; a per-polygon
  table from the run would colour the unwalled ones too.
- Polygons off the PGV grid are not drawn (`p_fail` NaN) and are counted by the
  run, apart from those with no fragility median (2026-10-02); a nearest-cell
  fallback would draw them.
