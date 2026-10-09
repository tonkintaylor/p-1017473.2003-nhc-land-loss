# Landslide step 8 — Kritikos (2015) relative hazard: method

- `gen_kritikos_2015_hazard.py` reads the 10 m DEM written by
  `ground/steps/s1_terrain/gen_multiscale_slope.py` and one PGV raster per shaking
  realisation from `s5_pgv_realisation/gen_pgv_realisations.py`. It reads the
  mapped faults with `landloss.io.active_faults.get_active_faults()` only when
  `FAULT_TERM` is `"mapped"`.
- `landloss.hazard.landslide.models.kritikos_2015.inputs` aggregates the DEM to
  the model's 60 m grid by block mean and takes the Horn slope there. Kritikos
  et al. (2015) [kritikos_2015] build every layer on one 60 m grid, and the
  memberships were fitted at that scale.
- Slope position is the topographic position index at `TPI_WINDOW_M`,
  standardised by `TPI_SD_M` or by the grid's own deviation, and classed after
  Jenness et al. (2013) [jenness_2013] into the paper's four classes: valley at
  −1 SD or below, ridge at +1 SD or above, flat within 0.5 SD on a slope of 5°
  or less, and midslope otherwise. The paper states no window; 600 m is a
  judgement, and the thresholds are marked `verify` in the module. The border
  half a window wide has no class, so no hazard.
- Distance to mapped faults is horizontal, from each cell to the nearest vertex
  of the AF250 traces (read from `NZAFD_AF250.geojson` through the local cache)
  densified to 30 m, searched out to 55 km, beyond which
  the membership is flat and the distance is `inf`. With `FAULT_TERM =
  "far_field"` every cell is set to `inf` and the fault database is not read,
  which holds the term at its far-field value.
- `landloss.hazard.shaking.pgv.mmi_from_pgv()` converts PGV, put on the 60 m
  cells by nearest neighbour, to Modified Mercalli intensity with the PGV-only
  relation of Worden et al. (2012), capped at MM X. The memberships are flat
  beyond MM IX, so the step prints how much of the area sits on that flat top.
- `model.run()` applies the average memberships of the paper's Figure 5,
  digitised to about 0.02 in `context/lit/landslide/kritikos_2015/figures/`,
  and combines them with the fuzzy gamma operator at `GAMMA`. Cells under 5°
  are flagged as gentle ground; the paper scores its success rate with and
  without them.
- `hazard_path()` names one float32 raster of the relative hazard H, 0 to 1,
  per shaking realisation under `temp/hazard/landslide/`, with
  `extent_suffix()` separating pilot and full-study outputs.
- H is a relative score, so it is turned into areal coverage by a transfer
  function fitted once, by `gen_kritikos_2015_transfer_function.py`, and
  committed as `landloss/io/assets/kritikos-2015-transfer-function.csv`.
  For each fitting event (`FIT_EVENTS`: Northridge and Wenchuan, the two the
  paper's memberships were derived from, so Kaikōura stays a test) the script
  builds H over the inventory's bounding box (`FIT_MARGIN_M` beyond it) with
  this config's `GAMMA`, `TPI_WINDOW_M` and `FAULT_TERM`, and an observed
  coverage grid from the inventory (`validations/kritikos_2015/event_inputs.py`).
  `evaluation.fit_transfer_function()` then sorts cells by H, cuts them into
  `FIT_N_BINS` bins of equal cumulative weight and takes each bin's mean H and
  mean coverage. Each event is fitted alone, and the committed curve pools the
  two with every cell of an event weighted 1/(its cell count), so that the
  16 million Wenchuan cells do not swamp the 1.7 million Northridge ones.
- Observed coverage is the share of a 60 m cell covered by landslide. Northridge
  is polygons (Harp & Jibson), burned at 10× supersampling and block-averaged.
  Wenchuan (Gorum et al. [gorum_2011]) is points with no areas in the GFDB, so
  the published total of 811 km² (a secondary-source figure, marked `verify`) is
  divided by the count and each landslide is spread as a disc of that mean area
  (13,490 m², more than one 60 m cell) by convolution, which conserves area.
  That area includes runout, so it overstates source area against Northridge's
  source polygons; the two events' coverages are not strictly the same quantity.
- `gen_kritikos_2015_hazard.py` applies the committed curve to H and writes the
  coverage as `kritikos_coverage_path()`, one float32 raster per realisation,
  which landslide step 3 reads with `COVERAGE_MODEL = "kritikos_2015"`. It refuses the run
  if the curve's recorded gamma, TPI window or fault term differ from
  `config.py`; rerun the fit script after changing any of them.
- The fitted events disagree. Where both exceed 0.01% coverage their curves
  differ by a factor of 1.3 to 70, Wenchuan being higher over H 0.4–0.75 and
  flat at about 4.5% above 0.74, Northridge steeper at the top (3.3% at 0.865).
  The pooled curve applied back to each event's own cells gives 1.05% for
  Northridge against 0.39% observed (2.7× over) and 0.61% for Wenchuan against
  1.29% observed (2.1× under). The fit also depends on the study area, which the
  paper does not define; only margin 0 has been fitted.
- The memberships, fuzzy gamma, inputs, success-rate AUC, weighted transfer fit
  and the fault reader are covered by
  `tests/landloss/hazard/landslide/models/test_kritikos_2015.py`; the step's
  fault-term switch, output names, curve check and run by
  `test_kritikos_2015_step.py`; and the coverage footprints and fit helpers by
  `test_kritikos_2015_fit.py`.

## Limitations

- **The fault term is distance to mapped faults, kept as the base case.** The
  lead decided to keep `FAULT_TERM = "mapped"` (2026-10-05) rather than hold the
  term at its far-field value. The scenario is mainly a Hikurangi interface
  rupture, which does not rupture a mapped crustal fault, so distance to mapped
  faults is a static property of the site, not distance to the rupture; at
  Kaikōura, density within 200 m of a ruptured fault was up to three times the
  background. Wellington is dense with mapped faults and the pilot sits on the
  flat top of the membership (every cell within 10 km), so the term does not
  rank cells there and may raise H evenly. The membership was fitted where
  mapped faults are sparse. With the GEM faults as stand-ins the term lowers
  Wenchuan's AUC (0.831 against 0.893 without it). The transfer function is
  fitted with the term on, so changing `FAULT_TERM` means refitting it.

Potential future improvements: see `s8_kritikos_2015_implementation_plan.md`.
