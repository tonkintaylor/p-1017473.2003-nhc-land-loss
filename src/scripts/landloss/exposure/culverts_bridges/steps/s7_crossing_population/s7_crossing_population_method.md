# Step 7 — Culvert and bridge crossings: method

- The step finds where an insured accessway crosses a watercourse and puts a
  culvert or a bridge there. It is run by `gen_crossing_population.py`, and the
  detection and the draw are both in
  `landloss.exposure.culverts_bridges.crossings`.
- The exposure is the **crossing**, not the structure. A culvert or a bridge
  exists to carry the accessway over water, so where an accessway crosses
  nothing there is nothing to find.
- Accessways come from `temp/exposure/driveways[-pilot].geoparquet`, the
  corridors step 5 generates and writes out beside the insured land extent, read
  through its own `driveway_path()`.
- **Both river layers are read**: the LINZ river name lines
  (`get_nz_river_name_lines`) and the river name polygons
  (`get_nz_river_name_polygons`, added by this step). A narrow stream exists only
  as a centreline while a river wide enough to need a bridge has an areal extent,
  so the lines alone would miss exactly the crossings most likely to carry a
  bridge. Each crossing records which layer found it, in
  `watercourse_source` (`lines`, `polygons` or `both`), so what the second
  layer earns is visible per run.
- **Any watercourse counts**, not only the named rivers
  `classify_waterways` separates out for lateral spreading, because most
  accessway crossings are of small streams.
- A crossing is the **part of the accessway lying on the water**, from
  `detect_crossings`, rather than the whole corridor.
- **One physical crossing is one row.** A named river polygon usually has its
  centreline running through it, so one accessway over it is found on both
  layers. `detect_crossings` merges the crossings of the same `claim_id` that
  intersect one another (`_merge_shared_crossings` in
  `landloss.exposure.culverts_bridges.crossings`), unioning their geometries
  into one row whose `watercourse_source` is `both`. The merge happens before
  the coverage filter and before the ids are minted, so each physical crossing
  gets one `crossing_id` and becomes one culvert or bridge row at vul step 10.
  Crossings of different claims are never merged, even where they touch.
- **Only crossings wholly inside their own claim's insured land are kept.**
  The insured land is read from step 5 through its `insured_land_path()`, and
  `keep_crossings_within_insured_land` in `landloss.exposure.coverage` keeps a
  crossing only if its geometry is covered by (`covered_by`) the insured land
  polygon of the same `claim_id`; touching the boundary counts as inside. The
  polygon is grown by `CROSSING_COVERAGE_TOLERANCE_M` (1 mm) before the test,
  because a crossing is cut from the same corridor the insured land is built
  from, so its ends sit on the insured boundary and the overlay rounds them a
  hair either side of it; an exact test drops most such crossings. A
  crossing partly outside, typically on the road reserve because the driveways
  are not clipped to the property, is dropped. The run prints detected, kept
  and dropped counts from `describe_coverage`.
- Each kept crossing gets a **`crossing_id`** of the form
  `<claim_id>-XNN`, from `mint_asset_ids` with `CROSSING_ID_SUFFIX` in
  `landloss.exposure.asset_ids`, numbered within the claim after
  `sort_by_location` orders the crossings by claim and then by the x and y of
  their representative point. It is minted **before the structure draw**, so it
  is independent of the random number generator and a crossing keeps the same
  id in every realisation. It is renamed to `culvert_id` or `bridge_id` by
  structure at vul step 10.
- The structure is **drawn, not observed**: a culvert at
  `CULVERT_PROBABILITY`, a bridge otherwise. The two are exhaustive, because
  something has to carry the accessway over the water. Both figures are
  engineering judgement fitted to nothing.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "exposure")`, the same stream the wall population uses, so the crossings of
  realisation 3 belong to the same modelled earthquake as its hazards.
- The output is
  `temp/exposure/crossing-population-rNNN[-pilot].geoparquet` from
  `crossing_population_path()`, carrying `crossing_id`, `claim_id`, the
  crossing geometry, `watercourse_source` and `structure`, in that order.
- Because the draw now runs over the filtered and sorted crossings rather than
  every detected one, outputs written before the coverage filter was added are
  stale and must be regenerated.
- **Over the pilot box the population is empty.** Neither river layer returns a
  feature there: the nearest named watercourse is about 2.8 km away, while the
  same readers return 9,233 lines and 37 polygons over the four territorial
  authorities. Central Wellington's streams are piped and are not named
  watercourses in the LINZ data. The run says so in its own output rather than
  leaving a zero to be read as a failure.
- Both layers carry **named** watercourses only, so the unnamed streams most
  small accessway crossings sit on are not counted. The run ends by saying the
  count is a floor rather than an estimate.

Potential future improvements see `s7_crossing_population_implementation_plan.md`.
