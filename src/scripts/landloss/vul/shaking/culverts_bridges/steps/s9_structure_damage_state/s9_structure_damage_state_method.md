# Step 9 — Culvert and bridge damage state: method

- The step decides **which culverts and bridges the shaking wrote off**, one
  damage state per structure per realisation. It is run by
  `gen_structure_damage_state.py`, and the fragility is in
  `landloss.vul.shaking.fragility` — the same one the retaining walls use.
- Structures come from
  `temp/exposure/crossing-population-r<nnn>[-pilot].geoparquet`, the population
  step 7 draws, read through its own `crossing_population_path()`.
- **Two damage states only, no damage and replace**, for the same reason as the
  walls: a failed crossing is rebuilt rather than patched.
- A damage state is a **draw against a probability of failure**, never a
  threshold on ground motion. The fragility returns that probability because
  that is what a fragility curve is, and it stays a probability however well the
  shaking field is resolved.
- **The beta's fragility is one flat number**, `BETA_FAILURE_PROBABILITY = 0.7`,
  and it does not yet distinguish a culvert from a bridge. The kind of structure
  is carried on every row as the asset, because the two are priced differently
  in the loss module even though they share the $25,000 sub-cap.
- PGA is sampled from the realisation's field at each structure's
  `geometry.representative_point()`, a point guaranteed to lie on the
  structure, and carried onto the output so the input is in place when the
  fragility starts using it. A midpoint along the line is not used because a
  crossing kept by step 7's coverage filter can be a polygon or a geometry
  collection, on which interpolating along a line is not defined.
- Every row carries the structure's `crossing_id` and `claim_id` unchanged from
  step 7 (names from `landloss.domain.loss_contract`), and the structure's own
  geometry in EPSG 2193, which supplies the coordinates the loss contract asks
  for. `crossing_id` is split into `culvert_id` and `bridge_id` by the asset
  kind at vul step 10.
- **The Wellington pilot legitimately produces no rows.** The crossing
  population follows named watercourses and the nearest is some kilometres from
  the pilot box, so the population itself is empty. The run says so in words
  rather than printing an empty table, because an empty output here is a
  coverage fact and not a failure.
- **No cost is attached.** The loss module prices a written-off structure from
  its undepreciated value, so what this step writes is the state.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "vulnerability")`, the same stream the walls draw from.
- Output is `temp/vul/structure-damage-state-r<nnn>[-pilot].geoparquet`, with
  columns `realisation_id`, `crossing_id`, `claim_id`, `asset`, `pga_g`,
  `failure_probability`, `damage_state` and `geometry` (`OUT_COLUMNS` in
  `gen_structure_damage_state.py`). An empty population writes an empty
  GeoDataFrame with the same columns and the population's CRS.
- Outputs written before `crossing_id` and the geometry were carried are stale;
  exposure steps 5 and 7 and then this step must be re-run.

Potential future improvements see
`s9_structure_damage_state_implementation_plan.md`.
