# Step 6 — Retaining wall population: method

- The step is two scripts. `gen_wall_probability.py` writes a **probability of a
  wall per insured property** and `gen_wall_population.py` draws a **realisation**
  from it, one line per wall. The probabilities are partly a **stand-in**: the
  slope-driven part is in `landloss.exposure.rw.beta_population`, which carries
  the `beta` prefix because it is deleted when the real inference arrives, and the
  combining numbers are in `landloss.exposure.rw.wall_probability`.
- Properties come from `temp/exposure/insured-land[-pilot].geoparquet`, the
  layer step 5 writes, read through its own `insured_land_path()`.
- Slope and downhill azimuth are derived from the LINZ elevation model over the
  properties' extent by `landloss.common.utils.terrain.slope_degrees` and
  `downhill_azimuth_degrees`, written to `temp/exposure/` and sampled at each
  property's representative point with `sample_at_points`, in `sample_terrain()`.
  A property outside the elevation model comes back NaN and has no probability.
- Three sources of evidence are attached by `attach_gns_evidence()` through
  `landloss.exposure.rw.wall_probability.attach_evidence`: GNS SLIDE mapped
  retaining walls (`get_gns_slide_morphology`, metres inside the property buffered
  by `RW_COVERAGE_BUFFER_M`), GNS SLIDE cut slopes and fill bodies
  (`get_slide_genesis`, share of the property's area) and the NLM landform class
  at the property's representative point (`get_nlm_geomorphology`). The run prints
  how many properties each source reaches in `describe_evidence`.
- **The evidence is one-sided.** GNS mapped only the walls visible from above and
  only in Wellington City, so a property with no mapped wall is not evidence of
  none. `wall_probability` applies the slope-driven prevalence, lifts it by the
  earthworks share, caps it on a plain landform, and sets it to at least
  `BETA_MAPPED_WALL_PROBABILITY` where a wall of `MIN_MAPPED_WALL_LENGTH_M` or
  more is mapped. Nothing lowers a probability because a wall is absent from the
  mapping.
- Retained height is a lognormal about a slope-driven median with log standard
  deviation `BETA_HEIGHT_LOG_SD`, cut at `BETA_DRAWN_HEIGHT_BOUNDS_M` when drawn.
  `size_class_probabilities` turns it into the probability of each size class
  given a wall, on the boundaries below, and `wall_probability_table` writes those
  beside `p_wall`, `p_poor` and `length_m` to
  `temp/exposure/wall-probability[-pilot].geoparquet` from
  `wall_probability_path()`, on the property's representative point.
- `gen_wall_population.py` reads that file and calls `draw_walls`, which draws
  whether each property has a wall, its height from the lognormal and its
  condition, and places a line for each. It reads no elevation model and no GNS
  layer, so realisations are cheap.
- **Slope is the base of the probability.** Prevalence ramps from zero below
  `BETA_MIN_SLOPE_DEG` to `BETA_MAX_PREVALENCE` above `BETA_MAX_SLOPE_DEG`, and
  median retained height ramps over the same range. Nothing here reads the
  Wellington City Council cut-and-fill models, road batters, section shape or the
  age of the subdivision, all of which the real model uses.
- **Initial condition is drawn, not derived.** The real model reads it off the
  age of the dwelling; no dwelling age is held, so `p_poor` is `BETA_POOR_SHARE`
  for every property, splitting the population evenly between modern and poor.
- Size classes are **small below 1 m, medium 1 to 2.5 m, large above 2.5 m** of
  retained height, by `classify_wall_size`. The boundaries are set by what the
  costing can tell apart: above the sub-cap the settlement stops depending on
  height.
- A wall is drawn as a straight line **along the contour**, perpendicular to the
  downhill azimuth and centred on the property's representative point, by
  `wall_lines`, on the representative point of the property and not on a mapped
  line. Its length is `BETA_LENGTH_SHARE` of the width of a square of
  the property's insured area. The orientation is right and the position is not,
  because nothing here knows where on a section a wall sits.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "exposure")`, so the walls of realisation 3 belong to the same modelled
  earthquake as its hazards, and a rerun reproduces.
- **Only walls on insured land are passed on.** After the draw,
  `landloss.exposure.coverage.keep_walls_on_insured_land` keeps a wall only if
  its line intersects its own claim's insured land polygon buffered by
  `RW_COVERAGE_BUFFER_M` (2 m), because a wall can support the insured land from
  just outside it. The test is against the step 5 polygons, not the
  representative points the slope was sampled at, and lying on another claim's
  land does not count. It runs after the draw, so the random stream is unchanged.
  `describe_coverage` prints the walls drawn, kept and dropped; under the beta
  each wall is centred inside its own polygon, so nearly all are kept.
- **Each kept wall gets an `rw_id`** of the form `<claim_id>-RW<nn>`, numbered
  from 01 within its claim, by `landloss.exposure.asset_ids.mint_asset_ids` with
  `RW_ID_SUFFIX`. It is minted after the coverage filter, on walls ordered by
  `sort_by_location` (claim, then the x and y of the line's representative
  point), so it is stable within a realisation and does not depend on row order.
- The output is `temp/exposure/beta-wall-population-rNNN[-pilot].geoparquet`
  from `wall_population_path()`, carrying `rw_id`, `claim_id`, `size_class`,
  `initial_condition`, `height_m`, `length_m` and the line.
- `gen_wall_probability.py` prints the expected number of walls, by size class,
  and `gen_wall_population.py` prints the walls drawn against the expected number
  and the counts by size class and initial condition, so a draw can be checked
  against the probabilities it came from. Both end by saying plainly that the
  result is not evidence about Wellington.

Potential future improvements: see `s6_wall_population_implementation_plan.md`.
