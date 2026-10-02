# Landslide hazard: status

**Status:** Two populations are built and ran over the pilot on 2026-10-02:
large failures placed in slope units on the supplied ESNZ grid, and urban
failures on slopes near buildings, coupled to the retaining walls. The urban
result fails far too much ground; its polygons are being rebuilt from faces
and its fragilities are placeholders until they are anchored. The portfolio
of large models is proposed, not agreed.

**Updated:** 2026-10-02

For a reviewer: read this page, then the plans it names, then each step's
method file under `steps/`, then the code. Detail that used to sit here (the
three routes, the historical accounts, the open questions about the supplied
grid) is in `landslide-notes.md` beside this file.

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

**Large failures**, above the urban size range (700 m² of source area as built):

- [x] Place large failures in the step 5 slope units on the supplied ESNZ 32 m
  probability grid, sized by the Kaikōura law [massey_2020], none starting on
  NLM flatland (step 1, the extend-ESNZ route).
- The route beyond that is not chosen, so it carries no mark: extend ESNZ,
  build a new model, or a portfolio of Nowicki Jessee (2018)
  [nowicki_jessee_2018], Kritikos et al. (2015) [kritikos_2015], Hancox et al.
  (1997) [hancox_1997], a strength-based model after Godt et al. (2008)
  [godt_2008] and a bespoke refit, each calibrated to the total area of Marc et
  al. (2016) [marc_2016] and the extent of Hancox. Options:
  `potential-landslide-rebuild.md`; build plans:
  `.agents/plans/building-kritikos-2015-landslide-model.md`,
  `.agents/plans/building-hancox-landslide-model-and-calibration.md`.
- [~] Rebuild the literature models and calibrations: Nowicki Jessee, Marc and
  the Hancox relationships are built and checked against their sources; none
  has been run over Wellington.
- [ ] Replace the runout, a rigid translation set by slope, with a reach angle
  by volume and failure style [de_vilder_2022].
- [ ] Add spatial correlation beyond one slope unit.

**Urban failures**, below the split, on sloping ground within 100 m of a
building (`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`):

- [x] Couple the urban model to the walls: sloping land fails in a large
  landslide, through its wall, or by localised failure; a polygon with a wall
  fails with the wall, and if any polygon on a wall fails the wall has failed.
  Walls are drawn per exposure world, failures per world and earthquake, each
  polygon on a lognormal fragility on PGV with a low, medium or high rate
  setting.
- [x] Build the terrain derivatives at 1 to 100 m (step 3), the ground map
  (step 4) and the slope units (step 5).
- [x] Delineate polygons from banded slope and aspect patches (steps 6 and 7);
  superseded, because no published method supports it.
- [>] Find faces, crest to toe, once from the 1 m DEM as a static layer, by
  geomorphons [jasiewicz_stepinski_2013] and the step test, and build one
  failure polygon per face: the wedge behind the crest [nzgs_mbie_2017], the
  runout below the toe [de_vilder_2022; hunter_fell_2003], the Kingsbury rating
  [kingsbury_1995], checked against the SLIDE breaks in slope [townsend_2020]
  (`.agents/plans/building-face-based-urban-slope-polygons.md`).
- [~] Attach a fragility per polygon (step 8); built, with placeholder medians,
  dispersion and rate factors until the anchoring
  (`.agents/plans/anchoring-and-calibrating-the-urban-fragilities.md`, a
  skeleton for the reviewer to develop).
- [x] Draw the urban failures per world and earthquake (step 9).
- [ ] Run per territorial authority, tiled, with the static layers built once
  (`.agents/plans/running-per-territorial-authority.md`).

**Demand and scenario.** The demand is the TS1170.5 2,500-year field as the
standard gives it, per site class (**T-26**, closed 2026-10-02). Where a model
needs a magnitude or a distance, every site is 25 km from an Mw 8.1 Hikurangi
interface event, the modal NSHM 2022 deaggregation for Wellington
(`BETA_SCENARIO_MW`, `BETA_SITE_DISTANCE_KM`); its source and caveats are in
`landslide-notes.md`, "Forward-use scenario".

## Where it is now

- **The whole chain ran over the pilot on 2026-10-02**, in 67 minutes, 49 of
  them in steps 6 and 7.
- **Step 1, large failures:** 7 failures, 0.95 ha, 0.14% coverage of the slope
  units. It rests on placeholders: `BETA_SOURCE_AREA_FRACTION` 0.252,
  `URBAN_AREA_SHARE` 0.25, an ellipse aspect ratio of 2, and sizes from 700 to
  3,000 m². The flat-land mask was added after the run.
- **Steps 3 to 5:** terrain derivatives, a ground map of 19,275 pieces and 41
  slope units over the pilot. The ground map stops short of the extent the
  other steps use, which left 9,144 candidates without a material; the fix is
  phase 0 of the faces plan.
- **Steps 6 and 7:** 59,132 candidates and 89,808 polygons, superseded.
- **Steps 8 and 9:** 44% of polygons failed and 36% of the urban domain was
  evacuated, against the order of 1% the literature gives. Causes: placeholder
  medians below the demand, walls grouped through shared polygons, and the
  delineation. The wall rule and the step 9 counts by cause were added after
  the run; grouping by face waits on the faces.
- **Changed since the run, and needing a rerun of the pilot from step 3:**
  vegetation height masks the building outlines, so roofs no longer read as
  canopy in the step 6 candidates, and the wall lines are step-tested
  (exposure rw status).
- **Literature models:** Nowicki Jessee (2018) is rebuilt and reproduces the
  USGS at Loma Prieta (`validations/nowicki_2018/`); Marc et al. (2016)
  reproduces the paper's fit (`validations/calibration/`); the Hancox
  relationships and the calibration interface are built. None has been run over
  Wellington.
- The faces plan, the anchoring skeleton and the per-territorial-authority plan
  are written and not reviewed.

## Next

1. Build the faces layer and the face-based polygons (faces plan, phases 0 to
   3), then rerun the pilot and record the counts and timings.
2. Develop and run the anchoring (anchoring skeleton), on the face polygons.
3. Run per territorial authority (per-TA plan).
4. Ask the supplier what an ESNZ cell's probability is a probability of, and
   what shaking it is conditioned on.
5. Choose the large-model route, and run Nowicki Jessee over Wellington and the
   calibration on Kaikōura.
6. Replace the runout rule with the de Vilder et al. (2022) reach angles.
7. Add imminent-risk land to each landslide (**T-45**), with the regression
   rules of **T-44**.
8. Measure step 1's placeholders from the Kaikōura inventory (step 1 plan,
   phase 3).

## Validation

- Total failed area, urban plus large, against Marc et al. (2016) and Nowicki
  Jessee et al. (2018) at the demand.
- Large-model density against the Greater Wellington `SEVERITY` zonation, as a
  rank correlation (`validations/fig_landslide_vulnerability_model_gwrc.py`).
- Sizes and reach angles against the Kaikōura inventory (`landloss.io.kaikoura`).
- Faces against the GNS mapped walls and the SLIDE breaks in slope (faces plan,
  phase 4).
- The share of failures confined to one property, against the expectation in
  `.agents/context/land-damage-mechanisms.md`.
- The 1855 and 1848 historical accounts, as qualitative rank-order checks only;
  the method is in `landslide-notes.md`, "Validation".

## Open decisions

Each is set out in `landslide-notes.md` under "Open decisions" unless named
otherwise.

- **What an ESNZ cell's probability means**, and what shaking it is
  conditioned on; only the supplier can say, and it moves the answer most.
- **L-08** restricts the ESNZ model to cross-comparison; it needs revisiting if
  the extend route is chosen.
- **The large-model route**: extend ESNZ, build new, or the portfolio.
- **The large/small split**: 500 m² agreed as the working threshold, 700 m² as
  built (`LARGE_MIN_SOURCE_AREA_M2`).
- **The largest credible single failure**, the 3,000 m² cap.
- **How much spatial correlation** to add.
- **Which runout relation** replaces the translation, and whether a fill in an
  earthquake takes the dry or the flow-slide relation.
- **Depth where two runouts overlap**: the deeper or the sum.
- **The face detection and geometry rules**: the faces plan's open decisions,
  and the headscarp band (**T-44**).
- **Converting the PGA wall curves to PGV** at each site's ratio, as built.
- **SLIDE's mixed fill classes.** "Mixed fill/rock", "Mixed fill/colluvium"
  and "Mixed fill/colluvium/rock", 65% of the SLIDE area over the pilot, are
  mapped to uncontrolled fill (`landloss.hazard.landslide.ground_map`), which
  makes 71% of the pilot fill and puts Kingsbury's geology factor at its top.
  Left as it is (the lead, 2026-10-02). **The reviewer is invited to propose a
  mapping**, for example the dominant natural material with fill recorded as
  the modification.
- **How strength is assigned spatially** for the strength-based model, and
  whether to build a weathering surface from the NZGD.
- **The pilot box is mostly flat suburb**; whether to move it onto hill country.
- **T-22**, **T-15**, and **T-11**, **T-20**, **T-50** for the wall and earthwork
  data.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
