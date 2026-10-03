# Landslide hazard: status

**Status:** Two populations are built and ran over the pilot on 2026-10-02:
large failures placed in slope units on the supplied ESNZ grid, and urban
failures on slopes near buildings, coupled to the retaining walls. The urban
result fails far too much ground; its polygons are being rebuilt from faces
and its fragilities are placeholders until they are anchored. The first part
of that rebuild, steps 3 to 5 and the faces plan up to the wall candidates, was
reviewed against the GNS literature review (`temp/gns_review/`) on 2026-10-02
and is ready to build once the lead settles the step test (Next, 1). The
second part, the failure polygons, steps 8 and 9 and the anchoring skeleton,
was reviewed the same day, and so were the large failures; their proposals
wait on the lead (Next, 3 and 10). The portfolio of large models is proposed,
not agreed. The slope elements and polygons library passed its toy-terrain
proof (stage D1) on 2026-10-02; real pilot examples (stage D2) are next.

**Updated:** 2026-10-03

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
  [godt_2008] and a bespoke refit. **Each keeps its own published
  calibration** (the lead, 2026-10-02): scaling every model to one Kaikōura
  or Marc total would make them agree whatever their structure, and the
  portfolio would then measure no model uncertainty. Kaikōura, Marc et al.
  (2016) [marc_2016] and the Hancox extent are tests reported beside each
  model. A model is calibrated only where its method leaves a gap, from its
  own source: Kritikos's relative hazard is turned to coverage on its own
  training events (Northridge, Wenchuan), and Hancox takes its amount from
  Marc. The table is in the rebuild note, "How they combine". Options:
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
- [~] Find slope elements, crest to toe, once from the 1 m LiDAR DEM as a
  static layer, grown from seeds strongest first (revised 2026-10-02 in place
  of geomorphons), each with its height and overall angle. An element is a
  free-face, and a wall candidate, where it is steeper
  than its ground stands unsupported at that height, from one lookup of eight
  fixed height bands by three ground groups: NZGS Unit 7C.2 Figure 35 for
  rock, 35° for soil and fill [nzgs_2025_torlesse]; a bank otherwise. Build
  one polygon per element: a trial wedge on the real profile behind the
  crest [nzgs_mbie_2017], running to the top of the slope above an excavated
  toe [kingsbury_1995], the runout below the toe [de_vilder_2022;
  hunter_fell_2003], the Kingsbury rating [kingsbury_1995], checked against
  the SLIDE breaks in slope [townsend_2020] and the Wellington slope profiles
  [hancox_2013_slope_types]
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
  (exposure rw status). The ground map's two fill changes are built: SLIDE's
  mixed fill classes read their natural material with fill as the
  modification, and fill reads the GNS modelling set S52 (step 4 plan,
  phase 2); step 4 needs a rerun to see the fill share fall from 71%. One
  consequence is left for the rebuild: `evacuated_depth_m` in
  `landloss.hazard.landslide.urban.geometry` reads the fill thickness only
  where the material is a fill material, so a mixed fill piece, now rock,
  colluvium or alluvium with fill as its modification, takes the colluvium
  depth there. That code belongs to steps 6 to 9, which phase 3 of the faces
  plan replaces, and a test pins the behaviour, so it was not changed; the
  face polygons should read the modification, not the material.
- **Literature models:** Nowicki Jessee (2018) is rebuilt and reproduces the
  USGS at Loma Prieta (`validations/nowicki_2018/`); Marc et al. (2016)
  reproduces the paper's fit (`validations/calibration/`); the Hancox
  relationships and the calibration interface are built. None has been run over
  Wellington.
- **Literature review of the first part, 2026-10-02.** Steps 3 to 5 and the
  faces plan's phases 0 to 2 were read against the 991 findings of
  `temp/gns_review/`, and the plans edited in place with citations: the faces
  plan, the step 3 and step 4 plans, and exposure rw step 6. What it changed:
  - the step test now has a published basis, NZGS Figure 35 for rock
    [nzgs_2025_torlesse], checked against the page image; the faces carry an
    overall angle crest to toe, the quantity every Wellington cut criterion is
    written in [grant_taylor_1964; kingsbury_1995; hancox_brabhaharan_1995];
  - three ground map changes are proposed before the faces read it: the mixed
    fills to their natural material with fill as the modification, the fill
    strength from the GNS analysis set rather than one densifying sample
    [monteith_2020; lyndsell_2019], and the sheared zone west of the
    Wellington Fault as crushed rock [grant_taylor_1964];
  - faces only on LiDAR, with a source mask from step 3 [de_vilder_2024;
    nzgs_2025_recognition].

  Step 5, the slope units, feeds only the large failures and the review found
  nothing that moves it. Findings from the first review batch, the SR reports,
  had no independent check, so their numbers are read off the page before
  adoption.
- **Literature review of the urban polygons, fragility and draw, 2026-10-02**
  (part A of `temp/handoff-remaining-review.md`). Read: faces plan phase 3,
  steps 8 and 9, the anchoring skeleton, and A-03, A-07, A-08, A-10, A-14 and
  A-15. Edited in place: the faces plan (phase 3 rewritten, new phase 4
  checks), the anchoring skeleton (the reviewer's answers), and the step 8 and
  9 plans. Every number it relies on from a first-batch report was checked
  against the page, including both de Vilder et al. reach-angle fits against
  the figure images. What it proposes, all for the lead:
  - **long faces cut into segments** of about 1,000 m³ along the contour,
    because Wellington cut failures are 10² to 10⁴ m³ and none takes a whole
    road cut [hancox_2013_slope_types; hancox_brabhaharan_1995], so a long
    wall no longer fails whole;
  - **the evacuated wedge by face type**: a wall's on the retained ground's
    φ′ (0.45 H for fill) [nzgs_mbie_2017; monteith_2020]; a fill bank's at
    0.45 H with 0.25 H (our reading of the Priscilla RS2 plot) and 0.65 H
    (the buried colluvium) as cases; a cut bank with no wall keeps T-44;
  - **runout by reach angle from the crest** (A-08 replaced): the dry debris
    avalanche line for cuts and natural banks, the fill flow slide line for
    every fill, because Wellington fills fail after the shaking as water
    enters the cracks [de_vilder_2022; brown_larkin_2005; monteith_2020];
  - **imminent ground to a 35° repose line from the toe** (A-10 revised,
    T-45), the GNS planning screen [de_vilder_2024];
  - **amplification by face height and ridge or terrace setting**, 1.0 for
    most house-lot faces, in place of the placeholder that gives every 60°
    wall 1.5 [brabhaharan_2018];
  - **the anchoring**: anchors as shares of face area; A16, A19 and A21 read
    their sources too strongly; the 2013 Cook Strait earthquakes, 0.21 to
    0.26 g in Wellington with two small failures on modified ground
    [holden_2013; van_dissen_2013], become the low-demand anchor; the rate
    setting brackets antecedent wetness, up to two MM units
    [dellow_hancox_2006], with one factor set for fill and one for the rest;
    significant landsliding starts at MM8, not MM7 [dowrick_2008].

  A-07, the circular footprint, is retired for the urban population.
- **Literature review of the large failures, 2026-10-02** (part B of the
  handoff). Read: step 1 and its placeholders, the rebuild note's portfolio,
  the Kritikos and Hancox plans, and A-01, A-02, A-04, A-05, A-06, A-09, A-11
  and A-12. Edited in place: the step 1 plan ("Literature review of the
  placeholders"), the rebuild note ("What the literature review says about
  the route"), and the risks of the Kritikos and Hancox plans. Proposals, all
  for the lead:
  - **size exponent 1.88**, the reviewed Kaikōura fit above 500 m²
    [massey_2018]; the 2.1 built is cited to Massey et al. (2020), which is
    not held, so it cannot be checked;
  - **the cap is raised from 3,000 m² to 35,000 m²**, about the source area
    of Gold's 1855 slide on the Hutt Road [brabhaharan_2018] (decided by the
    lead on 2026-10-02 and built);
  - **define the urban population by ground, not size**: keep the large
    model's lower bound where Kaikōura is complete, let urban face failures
    run past the split, and set `URBAN_AREA_SHARE` to about 0.05, the share of
    Kaikōura area below 500 m² (3 to 5%, our digitising), not 0.25;
  - **`BETA_SOURCE_AREA_FRACTION` of about 0.4 to 1.0, not 0.252**, if the
    ESNZ grid keeps the Kaikōura model's definition (a cell fails where its
    centroid lies in a source), which makes its mean probability the
    coverage. The loss from step 1 would rise by up to four times;
  - **ESNZ as one member, not the base**: GNS's own assessment is that its
    EIL model under-estimates Wellington [lin_2025];
  - **Kaikōura is a low case for the amount**, so it is reported as a test
    with Murchison and Inangahua beside it, season stated
    [dellow_hancox_2006], and no model is scaled to it (the lead's decision
    above);
  - **fault-distance clustering and Kritikos's fault term apply only to a
    crustal rupture**, not the Hikurangi interface scenario [massey_2018].

  Two documents would settle the biggest of these, the EIL tool reports
  SR2018/08 and SR2023/04, added to the most-wanted list with Massey et al.
  (2020).
- **Literature review of the walls, 2026-10-02** (part C). The Koutsoupaki
  wall curves fail 30 to 93% of walls at the study's shaking, against about
  10% in Canterbury at the same PGA [anderson_2015], which is part of why 88%
  of sloping walls were replaced in the pilot. The lead decided on
  2026-10-02 to keep the curves and state that they overpredict against
  Christchurch; the detail is in the exposure rw status and
  `.agents/context/retaining-wall-fragility.md`.
- The anchoring skeleton and the per-territorial-authority plan are written
  and not reviewed.
- **The slope elements and polygons library is built and proven on toy
  terrain (faces plan, stage D1).** `landloss.hazard.landslide.slope_elements`
  and `landloss.hazard.landslide.slope_polygons` pass all 17 toy grids
  (the plan's 12 cases plus an added case 13), noise-free, at noise seed 7,
  and over 30 noise seeds (510 of 510), and 197 regression tests pass.
  Findings, the `BETA_` values changed on the evidence, and the points left
  for the lead are in
  `research/slope_elements/toy_slope_elements.md`. Not yet built: the wall
  candidates (phase 2), stage D2 on real pilot examples, and the pipeline
  step itself (`gen_slope_elements.py`, stage D3).

## Next

1. **Settled 2026-10-02:** the lead confirmed the step test as written (faces
   plan, phase 1: the eight height bands and the 24-entry angle lookup, the
   soil-like 35° included) and accepted the three ground map changes (step 4
   plan, phase 2).
2. **Rebuild the first part**, in this order, each on the pilot:
   1. one extent for every step and the vectorised zonal statistics (faces
      plan, phase 0);
   2. step 3's DEM source mask and survey year (step 3 plan, phase 5), then
      rerun step 3, which also rewrites the vegetation height with the
      building mask;
   3. the ground map changes the lead accepts (the two fill changes built
      2026-10-02; the Wellington Fault sheared zone not yet), then rerun
      step 4 over the common extent and review its area shares and strength
      picks;
   4. the slope elements layer (faces plan, phase 1), proven on toy terrain
      (done, stage D1) and next on pilot examples with figures for the report
      (stage D2), for the lead's review;
   5. the wall candidates and their probability on the faces (faces plan,
      phase 2; exposure rw step 6, phase 2e), and the phase 4 checks that need
      only the walls: GNS mapped wall recall and the height shape against
      Anderson et al. [anderson_2015].

   Step 5 needs a rerun only for the common extent.
3. **The lead decides the phase 3 proposals** (faces plan, phase 3, and its
   open decisions): the segment volume, the fill bank width, the failure
   style per face, the repose angle and the amplification rule. Then build
   the face-based polygons, rerun the pilot and record the counts and
   timings.
4. Develop and run the anchoring on the face polygons, after the lead decides
   the reviewer's answers in the anchoring skeleton and the anchor table is
   edited to match.
5. Run per territorial authority (per-TA plan).
6. Ask the supplier what an ESNZ cell's probability is a probability of, and
   what shaking it is conditioned on, and in particular whether it keeps the
   Kaikōura model's centroid definition (step 1 plan, "Literature review of
   the placeholders"). Download GNS SR2018/08 and SR2023/04, the forecast
   tool reports, which may answer it first.
7. Choose the large-model route. Run Nowicki Jessee over Wellington as the
   USGS runs it, with its Kaikōura test reported, and build model 3 with
   Marc's scenario total as its amount (Hancox plan, phase 6).
8. Replace the large-model runout rule with the de Vilder et al. (2022) reach
   angles; the urban rule is in the faces plan, phase 3.
9. Add imminent-risk land to each large landslide (**T-45**), with the same
   repose-line rule proposed for the urban faces.
10. Measure step 1's placeholders from the Kaikōura inventory (step 1 plan,
    phase 3), after the lead decides the review's proposals for the exponent,
    the cap, the urban share and the source fraction.

## Validation

- Total failed area, urban plus large, against Marc et al. (2016) and Nowicki
  Jessee et al. (2018) at the demand.
- Large-model density against the Greater Wellington `SEVERITY` zonation, as a
  rank correlation (`validations/fig_landslide_vulnerability_model_gwrc.py`).
- Sizes and reach angles against the Kaikōura inventory (`landloss.io.kaikoura`).
- Faces against the GNS mapped walls and the SLIDE breaks in slope, face
  heights and angles against the Wellington slope profiles
  [hancox_2013_slope_types], and tall step faces against NZGS Figure 36 and
  Grant-Taylor's envelope [nzgs_2025_torlesse; grant_taylor_1964] (faces
  plan, phase 4).
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
  built (`LARGE_MIN_SOURCE_AREA_M2`). The review proposes keeping it as the
  large model's lower bound only, with the urban population defined by
  ground and free to run past it (step 1 plan).
- **The largest credible single failure**: the cap was raised to 35,000 m²
  (the lead, 2026-10-02), about Gold's slide.
- **How much spatial correlation** to add.
- **Which runout relation** replaces the translation. For the urban faces the
  review proposes the de Vilder et al. reach angles from the crest, dry for
  cuts and natural banks and the flow-slide line for every fill (faces plan,
  phase 3); for the large failures it is part B of the review.
- **Depth where two runouts overlap**: the deeper or the sum.
- **The face detection and geometry rules**: the faces plan's open decisions,
  and the headscarp band (**T-44**). The step test is proposed from NZGS
  Figure 35 [nzgs_2025_torlesse]; which Figure 35 row each rock class reads
  waits on a weathering grade the ground map does not yet carry.
- **Converting the PGA wall curves to PGV** at each site's ratio, as built.
- **SLIDE's mixed fill classes.** "Mixed fill/rock", "Mixed fill/colluvium"
  and "Mixed fill/colluvium/rock", 65% of the SLIDE area over the pilot, are
  mapped to uncontrolled fill (`landloss.hazard.landslide.ground_map`), which
  makes 71% of the pilot fill and puts Kingsbury's geology factor at its top.
  **Accepted by the lead on 2026-10-02 and built in code the same day, not yet
  rerun** (step 4 plan, phase 2): the natural material as the material and fill as the
  modification, colluvium ahead of rock where both are named, because
  Wellington fills fail on the buried colluvium at their base
  [brown_larkin_2005; lyndsell_2019; monteith_2020]. It also gives the wall
  chain's rock-cut factor rock to act on.
- **The fill strength.** Every fill reads φ′ 45.7° from one Orchy Crescent
  sample's first shear stage, a maximum on a densifying sample
  [lyndsell_2019]; the GNS analysis set, φ′ 42° and c′ 2 kPa
  [monteith_2020], is accepted (2026-10-02) and built as an explicit pick,
  with Brown and Larkin's 32° and 5 kPa [brown_larkin_2005] as the low case.
  It sets the width of the fill wedge.
- **How strength is assigned spatially** for the strength-based model, and
  whether to build a weathering surface from the NZGD.
- **The pilot box is mostly flat suburb**; whether to move it onto hill country.
- **T-22**, **T-15**, and **T-11**, **T-20**, **T-50** for the wall and earthwork
  data.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
