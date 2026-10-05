# Step 1 — Landslide realisation: implementation plan

**Status:** Phase 2, placement in slope units, is built and tested end to end
on a synthetic three-unit plane and now accepts the Hancox step 10 coverage, the
Kritikos step 11 coverage or
the supplied ESNZ grid; the Hancox route has not been run over the pilot. Phase 1 is the cell-by-cell realisation it replaced, kept here because
its calibration still carries into phase 2. Phases 3 to 6 are open.

This step is the **large** population of the landslide model: the failures
above the urban size range, placed in the slope units step 5 cuts (plan
section 10 of `.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`,
contract section 3.9 of `.agents/plans/urban-slope-build-contract.md`). The
small failures beside buildings are the urban population, landslide steps 6 to
9, and step 9 combines the two realisations. `COVERAGE_MODEL` selects the
Hancox step 10 coverage, the Kritikos step 11 coverage or the supplied 32 m ESNZ probability grid; the three
things neither carries — where a failure starts, how big it is, where the
debris goes — are added on top.

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
- [x] Read the grid selected by `COVERAGE_MODEL` and put it on the 10 m DEM
      grid nearest neighbour (`read_model_coverage`, `align_probability`), so
      units, position and model coverage share cells.
- [x] Expected failed area per unit: Σ (model value × cell area) over the
      unit's cells, times the model's source-area fraction, times
      (1 − `URBAN_AREA_SHARE`) (`expected_failed_area_m2`). Hancox is already
      source coverage and uses 1; ESNZ retains
      `BETA_SOURCE_AREA_FRACTION`.
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
      through `main()` with the input paths and model coverage reader replaced.
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
  unit expecting 1,306 m² of large failure draws one failure on average. The cap
  was raised to 35,000 m² on 2026-10-02, which puts the mean at about
  2,500 m² and roughly halves the count per unit for the same expected area.

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

## Literature review of the placeholders (2026-10-02)

Part B of the second review (`temp/handoff-remaining-review.md`) read this
step against `temp/gns_review/` (finding ids in backticks,
`out/findings.csv`). Every item below is a **proposal for the lead**. Numbers
that are ours (a conversion, a reading, a judgement) say so. Each first-batch
finding used here was checked against its page on 2026-10-02.

- [ ] **The size exponent: 1.88, not 2.1.** The Kaikōura source areas follow a
      power law with exponent 1.88 above x_min = 500 m², fitted by the Clauset
      et al. method, and roll over at 50 to 100 m² [massey_2018]
      (`massey2018-F10`, checked against the text). The 2.1 in
      `SIZE_EXPONENT` is cited to Massey et al. (2020) [massey_2020], which is
      neither held in `context/lit/` nor in the review set, so it cannot be
      checked here. Use 1.88 unless the 2020 paper is obtained and shows 2.1
      for a greywacke subset. Murchison and Inangahua fit 2.62 and 2.71, but
      above 10,000 m² (`massey2018-F11`). They are the evidence for a
      steeper tail, not for the range drawn here. An exponent below 2 puts
      most of the area in the largest failures, so the cap (next item)
      matters more than it does at 2.1.
- [x] **The cap: raised from 3,000 m² to 35,000 m²** (the lead, 2026-10-02:
      about Gold's slide; built as `MAX_SOURCE_AREA_M2`). The review had
      proposed about 30,000 m². The record is far above 3,000 m²:
  - Kaikōura sources reach about 550,000 m² (`massey2018-F09`);
  - in 1855 the one sizeable slip on the Wellington-Petone road was about
    1.2 ha [grapes_downes_1997] (`grapes1997-F01`), and Gold's slide on the
    Hutt Road was about 300,000 m³ [brabhaharan_2018] (`brabhaharan2018-F10`);
  - the largest Wellington landslide of the last 140 years is about
    250,000 m³ on the Wellington Fault scarp at Te Marua, from rain
    [hancox_2013_slope_types] (`sr2013-058-F23`, checked against the page);
  - coseismic cut failures in New Zealand run to 10⁵ m³ and occasionally
    10⁶ m³ (`brabhaharan2018-F01`).

  Gold's 300,000 m³ is about 34,000 m² by inverting the volume-area relation
  (**ours**, A-06). The proposed cap, 30,000 m², is a judgement at that order
  for hillsides near houses. The 1855 Rimutaka slips, median about 3.6 ha
  (`grapes1997-F19`, our digitising), belong to the ranges rather than the
  suburbs. **A check that the pair works:** with 1.88 between 700 and
  30,000 m², the mean source area is about 3,000 m² (ours), inside the 2,100
  to 3,700 m² digitised from Kaikōura (`massey2018-F14`). The law as built
  gives about 1,300 m². At a fixed expected area the count falls by about
  half, and about two thirds of the large-failure area moves into failures
  above 3,000 m² (ours).
- [ ] **The split and the urban share.** The lead thinks 500 m² may be too low
      (A-01, 1 October), and the evidence agrees that modified-slope failures
      cross it. New Zealand coseismic cut failures are generally 10³ to
      10⁵ m³ (`brabhaharan2018-F01`, `sr2015-016-F06`), about 680 to
      16,000 m² (ours). Hunter and Fell's cut failures run to 52,000 m³ and
      their fills to 10,500 m³ [hunter_fell_2003] (`hunter2003-F39`). The
      proposal is to stop treating the split as a size at all on the urban
      side:
  - the large population starts at `LARGE_MIN_SOURCE_AREA_M2`, kept at
    500 to 700 m², because that is where the Kaikōura inventory is complete
    and fitted (`massey2018-F10`);
  - the urban population is defined by ground, a face (faces plan, phase 3),
    and its segments run to their own volumes, so an urban failure can exceed
    the split;
  - where the two overlap, step 9's supersession already decides.

  On that reading `URBAN_AREA_SHARE` is the share of a green-field
  inventory's area below the split. At Kaikōura, sources under 500 m² are
  about 53 to 66% of the count but only 3 to 5% of the area
  (`massey2018-F13`, our digitising of Figure 2a). **The placeholder 0.25 is
  five times the published shape. Proposal: 0.05, until the research script
  measures it below 700 m² from `landloss.io.kaikoura`.**
- [ ] **`BETA_SOURCE_AREA_FRACTION`: what the grid's probability is.** The
      Kaikōura model GNS published counts a 32 m cell as a landslide where its
      **centroid** falls inside a source area, debris trails excluded and
      sources under 50 m² removed (`massey2018-F29`, checked against the
      text). Under that definition a cell's probability is the chance that a
      point at its centre is in a source, whose expectation over many cells is
      the source-area fraction. So the fraction is about 1, and the coverage
      is the mean probability. The open question below rejects the
      whole-cell reading because it gives 3.9% coverage on the pilot. The
      review does not support rejecting it on that ground:
  - the "order of 1%" target comes from Kaikōura, where most landslides lay
    at 0.4 to 1.0 g (`massey2018-F05`), and the grid is read at the file
    name's 2 g;
  - GNS's own assessment is that its EIL model under-estimates landslide
    hazard in the Wellington region (`sr2025-001-F05`, checked against the
    page);
  - its 2,475-year map is mostly Very low or Low over the four councils' hills
    (`sr2025-001-F08`, checked against the map).

  Two things still argue for something below 1. First, the paper's
  cell-based coverage (1.4%, `massey2018-F04`) is about 2.5 times its
  polygon-based coverage (0.56%, `F03`), unreconciled. Second, few
  high-probability cells held landslides: 26 of the 228 cells above 50%
  (`F30`). **Proposal: a range of about 0.4 to 1.0 in place of 0.252, with
  the supplier asked whether the ESNZ grid (Massey, Lukovic and Dellow 2022,
  `sr2025-001-F20`) keeps the 2018 centroid definition.** If it does, the
  loss from this step rises by up to four times.
- [ ] **Coverage cross-check (A-05):** the order of 1% stands as a check, not a
      target, with the observed range written beside it:
  - Kaikōura, 0.56% of the 3,600 km² main area by polygons and 1.4% by cells;
    greywacke 0.6% (`massey2018-F02`, `F03`, `F04`);
  - Inangahua, at least about 0.6% of the main area (`sr2015-016-F12`,
    ours);
  - the worst-hit southern Rimutaka Range in 1855, about 5 to 7% of the land
    (`grapes1997-F19`, our digitising), the extreme near a rupture.

  Wet ground raises both density and extent: winter earthquakes affect 2 to
  2.5 times the area of summer ones [dellow_hancox_2006] (`dellow2006-F05`,
  our digitising).
- [ ] **Shape:** keep `SOURCE_ASPECT_RATIO` 2.0 until it is measured. The one
      direct observation is two to one: 1855 slips at Green's Stream were about
      20 m long and 10 m wide (`grapes1997-F20`). Flows are elongate
      [nzgs_2025_recognition] (`nzgs2025-u2-F05`).
- [ ] **Volume from area (A-06):** the relation holds for shallow disrupted
      failures. Most Northridge failures were 1 to 5 m thick
      (`brabhaharan2018-F30`), which it matches (1.3 m at 500 m², 3.7 m at
      5,000 m², ours). It under-reads deep-seated ones: the Cook Strait
      rotational slump was about 100,000 m³ against about 30,000 m³ from its
      plan area (`sr2013-042-F18`, ours, dimensions read as width, depth and
      length). It also under-reads fills up to 18 m thick (`brown2005-F05`).
      Keep it for the large population, and note that it under-reads where a
      failure reactivates a deep slide.
- [ ] **Runout (A-08):** replace the slope ramp with the dry debris avalanche
      reach angle from the crest [de_vilder_2022] (`sr2019-038-F03`, checked
      against Figure 2.3), below 100,000 m³, and the rock avalanche line above
      it (`F06`). This is the same construction as the urban faces (faces plan,
      phase 3), so one function serves both. Phase 4's "check reach angles
      against the inventory" stays.
- [ ] **Clustering (A-09):** Kaikōura landslide density within 200 m of a
      ruptured fault is up to three times the background, decaying over 2.5 to
      3 km (`massey2018-F21`), and seven of the eight largest landslides were
      crossed by rupture (`F18`). Small and large failures cluster in
      different places (`F23`). This is a property of a crustal rupture: under
      the Hikurangi interface scenario no fault ruptures at the surface in the
      study area, so it does not apply. **Proposal:** correlate through the
      shaking realisation in the interface scenario, and add a rupture
      distance term only if a Wellington Fault scenario is run.
      Preconditioning by an earlier earthquake also clusters failures
      (`F24`).

## Open questions

- **What the supplied probability means.** The *rate* is now read as the
  expected failed area per unit, and the phase 1 calibration — 258 m² of
  source per failing 1,024 m² cell — is the only thing tying it to an areal
  coverage. The reading that a failing 32 m cell fails whole was rejected
  because it would put coverage at 3.9%, four times the literature. The
  2026-10-02 review questions that rejection: GNS's published Kaikōura model
  defines its probability by a cell's centroid falling in a source, which
  makes the mean probability the coverage, and the 1% target was observed at
  lower shaking than the grid is read at (see "Literature review of the
  placeholders", `BETA_SOURCE_AREA_FRACTION`). If the supplier confirms that
  definition, the fraction is about 0.4 to 1.0 and the loss rises by up to
  about four times.
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
