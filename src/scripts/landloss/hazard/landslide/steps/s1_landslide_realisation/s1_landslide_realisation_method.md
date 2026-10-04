# Step 1 — Landslide realisation: method

- The step turns a selected per-cell large-landslide model grid into the
  **large** population of landslides, one realisation per modelled earthquake:
  the failures above the urban size range, placed in the slope units step 5
  cuts, each with a polygon for the ground it left and a polygon for the ground
  it landed on. It is run by `s1_simulate_landslides.py`, and the figure it is
  checked against is produced by `fig_landslide_realisation.py` in the same
  folder, written to `report/hazard/landslide/landslide-realisation/fig/`. The
  small failures beside buildings are the urban population, drawn by landslide
  step 9 against their own fragilities, and step 9 combines the two.
- What a run does is set by `config.py` in the step folder — `EXTENT`,
  `REALISATION_IDS`, `COVERAGE_MODEL`, `LARGE_MIN_SOURCE_AREA_M2`, `URBAN_AREA_SHARE`,
  `SOURCE_ASPECT_RATIO` and `CREST_WEIGHT` — read in each script's
  `if __name__ == "__main__":` block and passed into `main()` as keyword
  arguments. Neither script takes command line arguments and neither `main()`
  carries a default. `EXTENT` is `"wlg-pilot"`, meaning runs go over
  `SMALL_WLG_PILOT` rather than the four territorial authorities (`"full"`), and steps 3 and 5 must have
  been run over the same extent.
- **The step reads only hazard outputs and fetches nothing.** `input_paths()`
  names them: the slope units from step 5 (`gen_slope_units.slope_units_path`)
  and, from step 3, the 10 m DEM, slope and downhill azimuth
  (`gen_multiscale_slope.dem_path`, `slope_path`, `aspect_path`) and the 100 m
  topographic position (`gen_terrain_derivatives.terrain_path`).
- `read_model_coverage()` reads the model selected by `COVERAGE_MODEL`.
  `"hancox_1997"`, the committed setting, reads the per-realisation source
  coverage written by step 10; `"esnz"` reads the supplied probability through
  `landloss.io.source_material.get_eil_landslide_probability` from the path in
  `EIL_PROBABILITY_SOURCE_PATH`.
- Each selected grid is used at its own scale, neither rescaled nor clipped.
  `check_probabilities()` refuses a grid holding any value outside [0, 1],
  because a grid in per cent and a grid carrying an undeclared nodata marker
  both look like ordinary numbers and would each produce a hundred times too
  many landslides.
- **The working grid is the 10 m DEM grid** the slope units were cut on.
  `align_probability()` puts the selected grid onto it nearest neighbour
  (`rio.reproject_match`); the Hancox grid is already aligned and the ESNZ
  grid's 32 m cells are repeated over the 10 m cells they contain.
  `unit_labels()` burns the units onto that grid, one
  label per unit; the probability, position, slope and aspect are then read
  cell for cell.
- **No large landslide starts on flat land** (the project lead, 2026-10-02).
  `flatland_mask()` burns the step 4 ground map pieces with `is_flatland` true
  (the NLM flatland release) onto the working grid by cell centre, and
  `mask_flatland()` sets the probability to NaN there before the expected area
  or the seeding reads it, so a flat cell adds nothing and is never a seed.
  `describe_flatland_mask()` prints the cells and the share of the grid's
  summed probability removed. A source seeded on a slope is not clipped where
  it runs onto flat land.
- **Expected failed area per unit** is computed by `expected_failed_area_m2()`:
  the sum over the unit's cells of model coverage times cell area, times the
  value from `coverage_source_area_fraction()`, times one minus
  `URBAN_AREA_SHARE`. Hancox's value is already source coverage and uses a
  fraction of 1. ESNZ uses `BETA_SOURCE_AREA_FRACTION` 0.252, the phase 1
  areal-coverage placeholder. The
  urban share, 0.25, is the share of the inventory's area the urban model
  draws instead, a placeholder until a research script measures it from
  `landloss.io.kaikoura`; every run prints it. A cell the grid does not reach
  contributes nothing, so a unit off the grid is never seeded.
- **The count per unit** is a Poisson draw, `draw_counts()`, with mean the
  unit's expected area over the mean of the size law,
  `truncated_power_law_mean_m2()` — about 2,500 m² on the committed settings. The
  unit decides where a failure starts, not how large it can be.
- **Size** is drawn per failure by `sample_areas()` from a bounded power law
  between `LARGE_MIN_SOURCE_AREA_M2` (700 m², the top of the urban range) and
  `MAX_SOURCE_AREA_M2` (35,000 m², about the source area of Gold's 1855 slide
  on the Hutt Road, about 300,000 m³ [brabhaharan_2018], by the volume-area
  law; the project lead's choice on 2026-10-02), with exponent `SIZE_EXPONENT` of 2.1, the
  Kaikōura greywacke fit of [massey_2020], which holds above a cutoff near
  500 m² and so over the whole range drawn. The exponent sets the shape of the
  sizes and, through the mean, the count; the total area is the expected area
  and does not move with it.
- **Seeding.** `seeding_weight()` weights every cell by its probability times
  `1 + CREST_WEIGHT × clip(TPI_100m / CREST_FULL_LIFT_M, 0, 1)`: a cell
  standing `CREST_FULL_LIFT_M` (10 m) or more above its 100 m neighbourhood
  gets the full lift, a cell below its surroundings none, and a cell the
  derivative has no value for (within half a window of the extent edge) is
  treated as level. `seed_cells()` then chooses each failure's seed by a
  weighted draw, without replacement, among the unit's top
  `SEED_CANDIDATE_CELLS` (10) cells by weight — or as many as there are
  failures when that is more. A unit with fewer positive-weight cells than
  failures reuses cells, and `drop_overlapping()` keeps the larger of the pair.
- **Shape** is an ellipse built by `ellipses()` from the axes `ellipse_axes()`
  gives: the sampled area at `SOURCE_ASPECT_RATIO` (2.0, long over short,
  placeholder for the Kaikōura ratio), the long axis along the downhill azimuth
  at the seed cell, and the centre half a long axis downslope of the seed so the
  seed is the ellipse's crest. The axes are stretched for the 64-sided polygon
  so it carries exactly the area sampled, because area is what the loss model
  reads. The ellipse is not clipped to its unit: a failure larger than its unit
  crosses into the neighbours, which is "grown along the facet" in its simplest
  form. A seed whose cell has no slope or no azimuth takes its unit's
  `mean_slope_degrees` and `mean_aspect_degrees` instead (`build_failures()`),
  so a unit the grid expects failures in always places them.
- **Overlaps are resolved on the source areas only**, by `drop_overlapping()`,
  largest first and stable on ties; a failure already dropped drops nothing
  else, so one large landslide cannot clear a hole wider than itself through
  failures that did not happen. A dropped failure takes its runout with it,
  because `to_polygons()` only ever sees the survivors. No two evacuated
  polygons overlap; inundated polygons may.
- **Displacement** is a function of slope alone, `displacement_from_slope()`:
  a straight ramp from `MIN_DISPLACEMENT_M` (1 m) at or below 10° to
  `MAX_DISPLACEMENT_M` (40 m) at or above 45°, read at the seed cell. It stands
  in for a Newmark displacement. The "How far" panel of the figure plots the
  assumption beside the landslides it produced.
- **Identifiers.** `mint_landslide_ids()` sorts the survivors by their source's
  representative point (`landloss.common.utils.ids.sort_by_point`, x then y)
  and numbers them `LS0000001` upward (`mint_ids` with
  `constants.LARGE_LANDSLIDE_ID_PREFIX`), within the realisation. An id is
  stable as long as the inputs and settings are; a changed extent renumbers.
- **The two polygons** are built by `to_polygons()`: the source ellipse,
  labelled `evacuated land`, and the same ellipse rebuilt at the runout centre,
  labelled `inundated land`, two rows sharing a `landslide_id` and told apart
  by `land_class`. The class names come from
  `landloss.hazard.landslide.land_class`, the one vocabulary every landslide
  layer uses. Volume comes from the volume-area law in
  `landloss.hazard.landslide.geometry.landslide_volume_m3`, conserved through
  the runout, and `depth_m` is that volume over each polygon's own area.
- Every row carries `realisation_id`, `population` (always `large`), the
  `unit_id` the failure was seeded in and a null `slope_id`, the columns step 9
  pairs a large row with an urban one on. The full column order is
  `OUTPUT_COLUMNS` in `s1_simulate_landslides.py`; the phase 1 `radius_m` is
  replaced by `semi_major_m` and `semi_minor_m`, and `seed_easting` and
  `seed_northing` record the seed cell beside the ellipse centre.
- Each run draws one realisation per id in `config.REALISATION_IDS`, from
  `landloss.hazard.realisation.realisation_seed` with the project-wide
  `BASE_SEED`, the realisation id and the stream `"landslide"`, so the
  landslides of realisation 3 belong to the same earthquake as the shaking and
  liquefaction of realisation 3. The step holds no seed of its own.
- The realisation is written by `draw_realisation()` to the path
  `realisation_path()` returns,
  `temp/hazard/landslide/landslide-realisation-rNNN<extent_suffix>.geoparquet`
  (`-pilot` for `"wlg-pilot"`, nothing for `"full"`), so a run over one extent
  cannot overwrite another. `fig_landslide_realisation.py` calls
  `realisation_path()` and `input_paths()` with the same `config.EXTENT` rather
  than rebuilding the names.
- A run where nothing failed prints that and **writes an empty layer** with
  the full schema, so the vulnerability steps reading the realisation find a
  file and report nothing damaged.
- Every run prints the extent and working grid, the probability deciles, the
  placement settings and the size law they imply, the unit count and expected
  coverage, the counts drawn and dropped, the source area, slope and
  displacement deciles, the summed and dissolved areas by land class, and the
  volume and depth deciles (`describe_*()` functions).
- The figure, `fig_landslide_realisation.py`, draws four panels: every
  landslide over the slope unit outlines; a close-up around the largest failure
  with the seed cell and an arrow from source to runout; the source areas as a
  complementary cumulative distribution with the lower bound marked; and
  displacement against slope.
- Every function above is covered without the network or the T: drive by
  `tests/landloss/hazard/landslide/test_large_placement.py`, on a synthetic
  three-unit plane with a crest row and an unmapped margin, and the step is
  run end to end through `main()` with `input_paths()` and `read_probability()`
  replaced, asserting the contract's columns, the id format, the size bounds,
  the non-overlap of sources, and that the same realisation id reproduces.

## Known weaknesses

- The source is an ellipse stamped on the terrain, not a region grown along
  the steepest-descent lines, so it does not follow a gully or stop at a ridge.
- Runout is a rigid translation of the source: the debris keeps the source's
  shape and area and does not spread, thin or follow a gully, and the distance
  depends on the slope at the seed and not on the size of the failure.
- The counts of neighbouring units are drawn independently, so clustering
  exists within a unit but not between units.
- `URBAN_AREA_SHARE`, `SOURCE_ASPECT_RATIO` and `BETA_SOURCE_AREA_FRACTION`
  are placeholders, and the total area follows the last of them directly.
- Two inundated polygons can overlap; `describe_result()` prints the summed
  and the dissolved inundated area for that reason, and anything summing
  inundated area has to dissolve first.

Potential future improvements: see `s1_landslide_realisation_implementation_plan.md`.
