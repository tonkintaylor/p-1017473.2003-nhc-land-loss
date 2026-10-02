# Step 8 — Urban slope fragility: implementation plan

**Status:** Phase 1 complete in code and tested on synthetic polygons, walls
and grids; the pilot run and the anchoring are the project lead's to launch
once steps 7, exposure step 6 and shaking steps 2 and 3 have been run.

## Background

Step 7 fixes the failure polygons and the geometry of every state each can be
in; exposure retaining wall step 6 draws, per exposure world, which candidate
lines carry a wall. This step joins the two for one world and gives every
polygon the fragility step 9 draws against: a lognormal on PGV whose median
comes from the published wall curve where the polygon has a wall and from the
polygon's continuous Kingsbury rating where it has none, adjusted for
topographic amplification and the run's rate setting. Section 4 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md` sets
the rows; sections 3.8, 6 and 7.7 of `.agents/plans/urban-slope-build-contract.md`
fix the columns, the conversion and the function signatures this step is
built against.

## Phase 1 — The model file per world (complete)

- [x] The fragility functions in `landloss.hazard.landslide.urban.fragility`:
      the two readers (`load_retaining_wall_fragility()`,
      `load_urban_fragility_anchors()`), `lognormal_failure_probability()`,
      `interpolated_slope_value()` and `continuous_rating()`,
      `localised_theta_base_m_s()`, `rate_factor()`,
      `pgv_pga_ratio_m_s_per_g()`, `pga_to_pgv_theta()`, `wall_curve()`,
      `polygon_theta()`, `wall_state()`, `sloping_walls()` (flat-land walls
      never join a polygon; vul shaking rw step 9 draws them) and
      `assign_fragility()`.
- [x] `retaining-wall-fragility.csv` filled with the six rows read out of
      [koutsoupaki_2023] (Fs = 1.5 for `modern`, Fs = 1.1 for `poor`; the
      3 m wall for `small` and `medium`, the 6 m wall for `large`; Ux DS3 =
      10% of H on PGA), each row's choice recorded in `basis` and the reading
      in `src/landloss/io/assets/README.md`.
- [x] `urban-fragility-anchors.csv` filled with the anchors of plan section 6
      (Kingsbury Tables 1 and 7, the Wellington low-demand record, the Port
      Hills, the forecasts for cuts and fills), the class-word-to-fraction
      reading marked as judgement in `set_by`.
- [x] `gen_urban_slope_fragility.py`: reads the polygons, the world's drawn
      walls, the wall table, the site class grid and step 3's PGV and
      the unscaled TS1170.5 PGA on it; samples the site class and the PGV/PGA
      ratio at each representative point; writes
      `urban-slope-model-wNNN[-pilot].geoparquet` sorted by `slope_id` and
      prints the counts contract section 3.8 asks for.
- [x] Join the polygons to exposure step 6's drawn walls
      (`drawn_walls_path`) rather than the insured population, and decide a
      polygon has a wall by a `wall_line_id` match rather than a non-null
      `rw_id` in `assign_fragility()`, so an uninsured wall gives its polygon
      the wall-derived fragility with `rw_id` null (decision 36 of the build
      contract).
- [x] Read every wall line on a polygon's edge (step 7's `wall_line_ids`)
      rather than the one sharing the longest edge: a polygon has a wall when
      any of them drew one (`drawn_edge_walls()`), takes the first such
      wall's curve and its own `wall_position`, and carries every edge line
      that drew a wall as `wall_line_ids` in the model file, so step 9 can
      fail each of those walls with it. A wall split at a property boundary
      no longer leaves its other lines without a polygon.
- [x] Take `RETURN_PERIOD_YR` from shaking step 3's `config.py`, so the
      return period of the PGV grid the ratio reads is set in one place.
- [x] `table_urban_slope_model.py`: the medians by Kingsbury zone, wall state
      and basis, the table the project lead reviews.
- [x] `fig_urban_slope_model.py`: the finest-scale polygons coloured by
      median, and the cumulative distribution of the median per wall state
      against the study's PGV range.
- [x] Tests in `tests/landloss/hazard/landslide/urban/test_fragility.py`: the
      contract's unit checks, the packaged tables read and validated, and the
      three scripts end to end on synthetic inputs in a temporary directory.

## Phase 2 — The pilot and the anchoring

- [ ] Run the pilot once step 7 (`urban-slope-polygons-pilot.geoparquet`),
      exposure step 6 (`drawn-walls-w000-pilot.geoparquet`) and shaking
      steps 2 and 3 exist. Review the printed counts, the table and the
      figure.
- [ ] Run `hazard/landslide/validations/urban/fig_urban_fragility_anchors.py`,
      which fits the localised median's two constants and a dispersion to the
      anchor table at the rock-site PGV/PGA ratio and prints them; paste the
      fitted `LOCALISED_THETA_AT_ZERO_RATING_M_S` and
      `LOCALISED_THETA_AT_MAX_RATING_M_S` into
      `landloss.hazard.landslide.urban.fragility`, and, if the fitted
      dispersion is accepted, `LOCALISED_FRAGILITY_BETA` into
      `landloss.domain.constants`. Write
      `urban_fragility_anchors_findings.md` beside the validation scripts
      from that first run.
- [ ] Set the `low` and `high` entries of `URBAN_RATE_FACTORS` from the
      spread between the anchors read generously and conservatively (plan
      section 6); the committed 1.5 and 1/1.5 are placeholders.
- [ ] Confirm the wall-curve reading with the project lead: DS3 (`extensive`,
      Ux = 10% of H) as "replace", the 3 m and 6 m walls for the three size
      classes, and Fs = 1.1 as the poor condition.

## Phase 3 — The researched rules

- [ ] Name the six wall classes and give the table a row per class, size and
      condition; `wall_class` is `unnamed` until then and
      `assign_fragility()` looks every wall up under that one class.
- [ ] Bracket the amplification factor step 7 computes against
      `sr2019-051-F35`, so the division recorded here is the researched one.
- [ ] A dwelling-age source for the wall population, which would move the
      share of poor walls and so the share of polygons on the lower curve.

## Potential future improvements

- Read the PGV/PGA ratio per site class from the TS1170.5 spectrum shape
  rather than from the two grids, if a per-class scalar is ever wanted for
  the report; the grids are the products the shaking steps already use.
- Carry a fitted dispersion per zone rather than one `beta` for every
  localised row, if the anchors turn out to want different spreads.
- A PGV-native wall curve set (Cosentini and Bozzoni 2022 screened PGV as the
  optimal measure for gravity walls) would remove the conversion for the
  classes it covers.
