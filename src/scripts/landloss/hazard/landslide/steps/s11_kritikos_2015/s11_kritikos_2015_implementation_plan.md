# Step 11 — Kritikos (2015) relative hazard: implementation plan

**Status:** The library, the forward step and their unit tests are built. The
coverage conversion and the checks against the paper and Kaikōura wait on the
lead, because they read `R:`.

The plan for the model as a whole is
`.agents/plans/building-kritikos-2015-landslide-model.md`.

## Phase 1 — Build model 2 (complete)

- [x] Digitise the average membership curves of the paper's Figure 5 into
      `landloss.hazard.landslide.models.kritikos_2015.memberships`.
- [x] Combine the four memberships with the fuzzy gamma operator, γ = 0.9.
- [x] Build the 60 m slope, the TPI slope position and the distance to mapped
      active faults.
- [x] Convert each shaking realisation's PGV to MM with
      `landloss.hazard.shaking.pgv.mmi_from_pgv()`.
- [x] Write one 60 m relative hazard raster per shaking realisation.

## Phase 2 — Check the digitisation and the fault reader (the lead, needs `R:`)

- [x] Confirm the AF250 data folder layout; the reader now names
      `NZAFD_AF250.geojson` and reads it through the cache. Confirmed on the real
      file, and step 11 ran over `wlg-pilot` with it.
- [x] Reproduce the paper's success-rate AUCs, Northridge 0.904, Wenchuan 0.839,
      within about 0.02, with `evaluation.success_rate_auc()`
      (`validations/kritikos_2015/`, findings beside it): Wenchuan 0.831,
      Northridge 0.867 to 0.927 by study area. Chi-Chi (0.921) is not
      reproducible from the GFDB, which lacks its landslides.
- [ ] Score Kaikōura, with and without the greywacke MM shift.

## Phase 3 — Convert H to coverage

- [ ] Fit `evaluation.fit_transfer_function()` on Northridge and Wenchuan.
- [ ] Add the fitted curve to this step so it writes a coverage raster, and add
      `kritikos_2015` to step 1's `LARGE_MODELS` and `read_model_coverage()`.
- [ ] Report Kaikōura's total through the curve, against Marc et al. (2016) and
      the Hancox extent, without rescaling.

## Phase 4 — Run Wellington

- [ ] Run over `wlg-pilot` and read the printed saturation: the share of cells
      at MM 9 or above and within 10 km of a mapped fault.
- [ ] Run the sensitivities in `config.py`: `TPI_WINDOW_M` of 300 and 1200,
      `GAMMA` of 0.8, and `FAULT_TERM = "far_field"`.
- [ ] Fix `TPI_SD_M` to the full-study value, then run the four territorial
      authorities.
