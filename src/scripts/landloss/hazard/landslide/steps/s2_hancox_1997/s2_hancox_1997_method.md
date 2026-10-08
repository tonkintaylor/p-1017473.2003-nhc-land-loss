# Landslide step 2 — Hancox (1997) coverage: method

- `gen_hancox_1997_coverage.py` reads the 10 m slope raster written by
  `ground/steps/s1_terrain/gen_multiscale_slope.py` and one PGV raster per shaking
  realisation from `s5_pgv_realisation/gen_pgv_realisations.py`, and rasterises
  the NLM flatland pieces in the ground step 2 ground map with
  `landloss.hazard.landslide.ground_map.flatland_cell_mask()`; it fetches no
  data.
- `landloss.hazard.shaking.pgv.mmi_from_pgv()` converts PGV to instrumental
  Modified Mercalli intensity with the PGV-only Worden et al. (2012) relation,
  without magnitude or distance residual terms and capped at MM X. That PGV is
  the TS1170.5 return-period demand for the realisation, so the model's
  shaking-dependent threshold is driven by the study demand.
- `landloss.hazard.landslide.models.hancox_1997.model.run()` sets coverage to
  zero below Hancox et al.'s MM7 Wellington threshold and beyond the maximum
  epicentral distance for the configured magnitude and size class.
- The same model function weights eligible 10 m cells by Hancox (2010) Table
  2's slope-class shares divided by each class's share of eligible ground, so
  the failed area follows the observed slope distribution; NLM flatland is
  excluded before those areas and the study's share of the Marc total are
  calculated.
- `marc_event_total_area_km2()` evaluates Marc et al. (2016) for the settings
  in `config.py`; the committed run uses the plan's central interface
  sensitivity of Mw 8.1, mean asperity depth 22.5 km, reverse faulting, every
  asperity onshore, modal slope 22 degrees and `A_topo = 1`. These source
  settings determine only Marc's event-wide amount; they do not replace or
  modify the TS1170.5-derived PGV used for the Hancox threshold.
- Model 3 apportions that event total by the eligible modelled area divided by
  Hancox's mean area affected and scales the slope-weighted grid to that amount
  with `landloss.hazard.landslide.calibration.calibrate()`.
- `coverage_path()` names one float32 coverage raster per shaking realisation
  under `temp/hazard/landslide/`, with `extent_suffix()` separating pilot and
  full-study outputs.
- `scripts.landloss.hazard.gen_hazard.main()` runs this step before landslide step 3;
  landslide step 3 reads the coverage selected by its `COVERAGE_MODEL` setting and uses
  Hancox coverage directly as expected source-area coverage.
- The model equations, the PGV-to-MMI conversion, Marc total, output names and
  pipeline handoff are covered by
  `tests/landloss/hazard/landslide/models/test_hancox_1997_model.py`,
  `tests/landloss/hazard/landslide/test_hancox_1997_step.py`,
  `tests/landloss/hazard/landslide/test_large_placement.py` and
  `tests/landloss/hazard/shaking/test_pgv.py`.

Potential future improvements: see `s2_hancox_1997_implementation_plan.md`.
