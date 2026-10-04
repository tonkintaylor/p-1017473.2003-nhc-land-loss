# Step 11 — Kritikos (2015) relative hazard: method

- `gen_kritikos_2015_hazard.py` reads the 10 m DEM written by
  `s3_multiscale_slope/gen_multiscale_slope.py` and one PGV raster per shaking
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
- The step writes H, not a coverage. The transfer function from H to areal
  coverage is fitted on Northridge and Wenchuan by
  `evaluation.fit_transfer_function()`, which needs the GFDB inventories
  (`landloss.io.gfdb`, now read from the local cache); step 1 does not yet read
  this model.
- The memberships, fuzzy gamma, inputs, success-rate AUC, transfer fit and the
  fault reader are covered by
  `tests/landloss/hazard/landslide/models/test_kritikos_2015.py`, and the step's
  fault-term switch, output names and run by
  `tests/landloss/hazard/landslide/test_kritikos_2015_step.py`.

Potential future improvements: see `s11_kritikos_2015_implementation_plan.md`.
