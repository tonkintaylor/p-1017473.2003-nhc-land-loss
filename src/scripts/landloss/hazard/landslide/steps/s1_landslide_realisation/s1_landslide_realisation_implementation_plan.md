# Step 1 — Landslide realisation: implementation plan

**Status:** Phase 2, placement in slope units, is built and tested end to end
on a synthetic three-unit plane; it has not been run over the pilot. Phase 1 is the cell-by-cell realisation it replaced, kept here because
its calibration still carries into phase 2. Phases 3 to 6 are open.

This step is the **large** population of the landslide model: the failures
above the urban size range, placed in the slope units step 5 cuts (plan
section 10 of `.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`,
contract section 3.9 of `.agents/plans/urban-slope-build-contract.md`). The
small failures beside buildings are the urban population, landslide steps 6 to
9, and step 9 combines the two realisations. The supplied 32 m probability grid
stays the base rate: the three things it does not carry — where a failure
starts, how big it is, where the debris goes — are added on top of it. The
alternative, a model built from the ground up, is drafted in
`.agents/plans/estimating-eq-landslide-extent-wellington.md`, and choosing
between them is still open.

## Phase 1 — A cell-by-cell realisation, every assumption stated (complete, superseded)

Replaced by phase 2. Kept because its areal-coverage calibration is the one
number phase 2 inherits, and because the reader of a realisation written before
2 October 2026 needs to know what produced it.

- [x] Read the supplied probability grid through
      `landloss.io.source_material.get_eil_landslide_probability`, with the path
      as a constant and the raster's projection read off the file.
- [x] Refuse a grid holding anything outside [0, 1].
- [x] Sample each cell independently against its own probability.
- [x] Draw a source area per failure from a bounded power law between 3 m² and
      3000 m², with the exponent solved backwards from areal coverage: 1.19
      gave a mean source area of 258 m², 0.99% coverage over the graded area,
      against the order of 1% in Nowicki Jessee et al. (2018)
      [nowicki_jessee_2018].
- [x] Place each failure as an area-exact circle at its cell centre, drop every
      failure overlapping a larger surviving one, displace it downhill by a
      distance ramping from 1 m to 40 m with slope, and emit the source and the
      displaced circle as `evacuated land` and `inundated land`.
- [x] Fetch the LINZ DEM at the grid's cell size for the slope and the downhill
      direction (dropped in phase 2: the step reads step 3's rasters).

## Phase 1a — An empty realisation is still written (complete)

- [x] Write an empty layer with the full schema when nothing fails, so the
      vulnerability steps do not stop on a missing file.

## Phase 2 — Placement in slope units, the large population (built; pilot run open)

- [x] Read the slope units (`slope_units_path`) and the 10 m DEM, slope and
      aspect and the 100 m topographic position from step 3; fetch nothing.
      `USE_CACHED_DEM` is gone from `config.py`.
- [x] Resample the probability grid onto the 10 m DEM grid, nearest neighbour
      (`align_probability`), so units, position and probability share cells.
- [x] Expected failed area per unit: Σ (p × cell area) over the unit's cells,
      times `BETA_SOURCE_AREA_FRACTION`, times (1 − `URBAN_AREA_SHARE`)
      (`expected_failed_area_m2`).
- [x] A Poisson count per unit, mean the expected area over the mean of the
      size law (`draw_counts`, `truncated_power_law_mean_m2`).
- [x] Sizes from the power law truncated to
      [`LARGE_MIN_SOURCE_AREA_M2`, `MAX_SOURCE_AREA_M2`] (`sample_areas`).
- [x] Seed each failure by a weighted choice over the unit's top ten cells by
      `p × (1 + CREST_WEIGHT × clip(TPI_100m / 10, 0, 1))` (`seeding_weight`,
      `seed_cells`).
- [x] An ellipse source of the sampled area, long axis along the downhill
      azimuth at `SOURCE_ASPECT_RATIO`, centred half a long axis downslope of
      the seed, not clipped to its unit (`ellipse_axes`, `ellipses`,
      `build_failures`).
- [x] Runout as phase 1: the ellipse translated by `displacement_from_slope`.
      `drop_overlapping` kept.
- [x] `landslide_id` as `LS<7 digits>` minted by location within the
      realisation (`mint_landslide_ids`, on `landloss.common.utils.ids`);
      `population`, `unit_id` and a null `slope_id` on every row; the land
      classes imported from `landloss.hazard.landslide.land_class`.
- [x] `fig_landslide_realisation.py` re-pointed: unit outlines under the map,
      the seed cell and the ellipse in the close-up, the lower bound on the
      size panel.
- [x] `tests/landloss/hazard/landslide/test_large_placement.py`: every
      function above on a synthetic three-unit plane, and the step end to end
      through `main()` with the input paths and the probability reader
      replaced.
- [ ] Run over the pilot after steps 3 to 5 (step 3's
      `topographic-position-100m` and step 5's
      `slope-units-pilot.geoparquet` must exist first), and review the
      printed counts and the figure.

The numbers the contract asks this plan to record:

- `SIZE_EXPONENT` is **2.1**, the published Kaikōura fit [massey_2020], not
  re-solved. The contract said to re-solve it to hold coverage at
  0.99% × (1 − `URBAN_AREA_SHARE`), but under a Poisson count whose mean is
  the expected area over the mean size, the total area is the expected area
  whatever the exponent: the exponent sets the shape of the sizes and the
  count, not the coverage. The published value applies as read because the
  range drawn, 700 to 3000 m², lies wholly above the fit's cutoff near 500 m².
- The coverage is carried instead by `BETA_SOURCE_AREA_FRACTION = 0.252`, the
  share of a failing cell's area that becomes source, which is the phase 1
  calibration restated: 258 m² of expected source per failing 1,024 m² cell.
  The expected failed area is therefore 0.252 × 0.75 = 0.189 of Σ p × cell
  area, which over the full grid (mean probability about 0.039, from 0.99% /
  0.252) is 0.74% = 0.99% × (1 − 0.25). A beta placeholder until phase 3
  calibrates it.
- The mean of the truncated law on [700, 3000] m² at 2.1 is **1,306 m²**, so a
  unit expecting 1,306 m² of large failure draws one failure on average.

- [x] Mask the probability to off-flatland ground before the expected area
      and the seeding read it, so no large landslide starts on NLM flatland
      (`flatland_mask`, `mask_flatland`; the project lead, 2026-10-02). Tested
      in `test_large_placement.py`; not yet rerun over the pilot.

## Phase 3 — Fit the size law and the placeholders to the Kaikōura inventory

- [ ] Measure `URBAN_AREA_SHARE` from the Kaikōura v3 source polygons
      (`landloss.io.kaikoura`): the share of the inventory's area inside the
      urban size range, below `LARGE_MIN_SOURCE_AREA_M2`. A research script;
      the value is a placeholder of 0.25.
- [ ] Measure `SOURCE_ASPECT_RATIO` from the same polygons: downslope length
      over across-slope width. Placeholder 2.0.
- [ ] Fit the exponent and the upper bound above `LARGE_MIN_SOURCE_AREA_M2`
      to the greywacke subset, rather than borrowing Massey's 2.1, and check
      the realised sizes against the inventory on the size panel of the figure.
- [ ] Calibrate `BETA_SOURCE_AREA_FRACTION` against the inventory's areal
      coverage rather than the Nowicki Jessee order of magnitude, and decide
      whether the supplied grid's probability is conditional on shaking or
      already carries a rate (open question below).
- [ ] Commit the fitted parameters as a packaged asset, following
      `landloss/io/one_offs/gen_study_extent.py`, so the 31k-polygon inventory
      is not needed day to day.
- [ ] Report the sensitivity of the loss to `LARGE_MIN_SOURCE_AREA_M2`, the
      boundary of the urban range, as plan section 10.3 asks.

## Phase 4 — Growth along the facet, and a runout that is more than a translation

- [ ] Grow each source along the steepest-descent lines from its seed to its
      sampled area — region growing on the 10 m DEM, elongated downslope at
      the aspect ratio — instead of stamping an ellipse. The ellipse is the
      simplest form of "grown along the facet"; it crosses unit boundaries
      when larger than its unit, which is the behaviour wanted, but it does
      not follow a gully or stop at a ridge.
- [ ] Derive a yield acceleration per cell from an infinite-slope factor of
      safety with the ground map's strength parameters, and compute a Newmark
      displacement from it and the shaking — Bray & Macedo (2019) for the
      crustal faults, Bray, Macedo & Travasarou (2018) for Hikurangi — in
      place of the slope ramp `displacement_from_slope` applies.
- [ ] Make displacement depend on the size of the failure as well as the
      slope; a 700 m² source and a 3000 m² one on the same hillside currently
      travel the same distance.
- [ ] Sample a reach angle conditioned on volume from the Kaikōura
      debris-trail polygons, route the debris down the steepest-descent path
      and widen it with volume, keeping the source and the trail as separate
      polygon sets so nothing downstream changes.
- [ ] Check reach angles against the inventory.

## Phase 5 — Spatial correlation, and many realisations

- [x] Seed from `realisation_seed(BASE_SEED, realisation_id, "landslide")`,
      draw one earthquake per id in `config.REALISATION_IDS`, carry
      `realisation_id` on every polygon and write
      `landslide-realisation-rNNN[-pilot].geoparquet` per id.
- [x] Clustering within a unit: the Poisson count per unit and the seeding at
      the unit's highest-weight cells put several failures on one hillside
      where the grid is high, which the phase 1 independent cell sampling
      could not.
- [ ] Correlate the counts between neighbouring units, so one event produces
      bad hillsides rather than a scatter of bad units. The unit draws are
      independent.
- [ ] Run N realisations and carry a distribution of affected area per
      property per cause.
- [ ] Check the proportion of landslides confined to a single property
      against `.agents/context/land-damage-mechanisms.md`: most confined to
      one property, multi-property failures concentrated in gullies.

## Phase 6 — The full extent

- [ ] Run over the four territorial authorities. The working grid is the 10 m
      DEM grid, about 5,900 by 5,400 cells over the full extent; the step
      holds the probability, slope, aspect, position, label and weight arrays
      at once, about 1.5 GB in float64, which fits a workstation but has not
      been run. If it does not, tile by slope unit: every per-cell product is
      summed within a unit, so units can be processed in blocks and only the
      ellipses need the whole extent.
- [ ] Judge the model on the full extent, not the pilot: the pilot is largely
      flat suburb and exercises the code, not the model.

## Open questions

- **What the supplied probability means.** The *rate* is now read as the
  expected failed area per unit, and the phase 1 calibration — 258 m² of
  source per failing 1,024 m² cell — is the only thing tying it to an areal
  coverage. The reading that a failing 32 m cell fails whole is rejected: it
  would put coverage at 3.9%, four times the literature. If the supplier
  confirms the whole-cell reading anyway, `BETA_SOURCE_AREA_FRACTION` becomes
  1.0 and the loss rises by about four times.
- **What shaking level the grid is conditioned on.** Taken from the file name
  (`EILProb_PGA2g.tif`) and unconfirmed. The step runs either way; the report
  cannot describe the result without it.
- **Whether the grid's probabilities are conditional on shaking, or already
  include a rate.** Changes what a realisation is a realisation *of*.
- **Why the grid puts any failure probability on flat ground.** Over the full
  study area the phase 1 failures had a median slope of 28°; the pilot box's
  had 3°, with probabilities of 0.3% to 7.6% across Newtown, Kilbirnie and
  Rongotai. The step now masks the NLM flatland, so no large failure starts
  there (2026-10-02); flat ground the NLM release does not cover can still
  carry probability. Worth asking whether the grid covers mechanisms other
  than slope failure, or is smoothed across the hill margin.
- **Whether to keep the ESNZ grid as the base rate at all.** The module-level
  decision in `status.md`; register entry **L-08** restricts the GNS/PRUE
  model, confirmed to be the same model, to cross-comparison.

## Potential future improvements

- Grow sources along steepest descent rather than stamping ellipses (phase 4).
- A Newmark displacement and a volume-conditioned runout (phase 4).
- Correlated counts between neighbouring units (phase 5).
- Every placeholder — `URBAN_AREA_SHARE`, `SOURCE_ASPECT_RATIO`,
  `BETA_SOURCE_AREA_FRACTION`, the exponent and bounds — measured from the
  Kaikōura inventory (phase 3).
- Tiling by unit for the full extent, if the whole-extent arrays do not fit
  (phase 6).
