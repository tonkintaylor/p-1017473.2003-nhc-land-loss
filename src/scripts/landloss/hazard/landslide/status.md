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
not agreed; its Hancox model 3 and Wellington step are built but not run. The
slope elements and polygons library passed its toy-terrain
proof (stage D1) on 2026-10-02 and run over pilot examples (stage D2) on
2026-10-03; the pipeline step (stage D3, step 12) ran over the pilot on
2026-10-04, and the wall probability and per-zone fragility are next.

**Updated:** 2026-10-04

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
  Hancox model 3 are built and checked against their sources; Hancox has a
  Wellington forward step, and Kritikos has a step that writes its relative
  hazard, but none has been run over Wellington.
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
  static layer, each with its height and overall angle. **Built as step 12
  (stage D3, 2026-10-04)**, over the pilot. **Seeding revised
  2026-10-04** (the lead rejected the bank seeds): pips (cells that drop
  0.7 m per metre of distance at 1, 3 and 5 cells in one of eight directions,
  from the DEM alone), joined within 2 m into pifs, each tested over all
  pairs of its points into a siz (seed instability zone) with the two-band
  slope table (below 3.5 m: 35°, 45°, 53°; from 3.5 m: 32°, 40°, 48° for soil,
  weak and stronger rock) and a near step (0.7 m soil, 3 m rock). Fill is
  soil. The sizs are grown by the existing watershed growth, and the siz table
  is the input to the retaining wall workflow
  (`.agents/plans/building-pip-pif-siz-slope-polygons.md`). Build
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
  relationships, model 3 and the step 10 Wellington coverage run are built.
  Step 1 is configured to place that coverage directly. None has been run over
  Wellington. Step 10 already takes each realisation's MM threshold from the
  TS1170.5-derived PGV; its separate Marc amount uses the plan's central
  interface sensitivity rather than final NSHM source geometry.
- **Kritikos model 2** (`.agents/plans/building-kritikos-2015-landslide-model.md`)
  has its library and forward step built and unit tested; step 11 has run over
  `wlg-pilot` with the real AF250 traces. The paper's
  average memberships are digitised from Figure 5 to about 0.02
  (`context/lit/landslide/kritikos_2015/figures/`); the fuzzy gamma model, the
  60 m inputs, the AF250 fault reader, the success-rate AUC and the monotone
  transfer-function fit are in `landloss.hazard.landslide.models.kritikos_2015`
  and `landloss.io.active_faults`. Step 11 writes the relative hazard H per
  realisation; it stops there, because the hazard-to-coverage transfer function
  still has to be fitted on Northridge and Wenchuan from the GFDB, and step 1
  does not yet read it. The digitisation reproduces the paper's Wenchuan AUC (0.831 against
  0.839) and brackets its Northridge value (0.867 to 0.927 by study area
  against 0.904) with Copernicus 30 m and GEM faults as stand-ins
  (`validations/kritikos_2015/`); Chi-Chi cannot be reproduced, as the GFDB
  lacks its landslides. The TPI
  window and class thresholds are judgements, though the AUC does not depend on
  the window. The fault term lowers Wenchuan's AUC with the GEM faults, which
  bears on the lead's `FAULT_TERM` decision. The fault term lowers Wenchuan's AUC with the GEM faults, which
  bears on the lead's `FAULT_TERM` decision.
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
  and `landloss.hazard.landslide.slope_polygons` pass all 19 toy grids
  (the plan's 12 cases plus three added in D1: case 13's soil-like batters,
  case 14's two gully heads on a ridge bent so they face 60 degrees apart,
  under `BETA_FACING_APART_DEG` where case 6's face 180 degrees apart, and
  case 15's undulating hills, a negative control), noise-free, at noise
  seed 7, and over 30 noise seeds (570 of 570), and 209 regression tests
  pass. Findings, the `BETA_` values changed on the evidence, and the points
  left for the lead are in
  `research/slope_elements/toy_slope_elements.md`. Not yet built: the wall
  candidates (phase 2) and the pipeline step itself
  (`gen_slope_elements.py`, stage D3).
- **The library has been run over the whole small Wellington pilot, with
  twelve example sites (stage D2, 2026-10-03, rerun 2026-10-04).** 10,750
  elements and 12,466 polygons in 31 s, with 22% of the pilot's land
  evacuated. 83% of GNS mapped wall cells have an element within 2 m, and
  87% of sharp breaks in slope have a crest or toe within 3 m. No `BETA_`
  value changed, and the grow tolerance is settled at 3° (the pilot is the
  same at 2° to 5°). The sea is masked with the LINZ coastline polygons
  (`get_nz_coastline_polygons`), which removed the polygons the DEM's flat
  sea gave seawalls; the lead confirmed that run-out over flat ground fans
  out. The sites also show very large polygons on weak-rock and fill
  hillsides. The ground map still reads about 74% of the pilot as fill until
  step 4 is rerun, which inflates the fill results. GNS holds no wall height,
  so wall heights are the DEM's. Figures are in
  `report/hazard/landslide/slope-elements/fig/`; findings and the points for
  the lead are in `research/slope_elements/pilot_example_slope_elements.md`.
- **The slope elements' seed thresholds are two packaged CSVs (2026-10-04),**
  `landslide-slope-thresholds.csv` (the angle each ground group stands at, by
  height band) and `landslide-seed-thresholds.csv` (per ground group, the
  minimum step height for a free-face seed and the minimum slope for a bank
  seed) in `src/landloss/io/assets/`, read by `slope_elements.py` instead of
  being written in it. The shipped values are the numbers the lead confirmed on
  2026-10-02 and the 18.4° bank slope, so the results do not move;
  `assets/README.md` says what each column means. Raising `bank_min_slope_deg`
  for a group is the lever for pilot 5's rock hillside reading as one bank. The
  other `BETA_` settings are still constants.
- **Pips, pifs and sizs replace the free-face and bank seeding (2026-10-04).**
  `landloss.hazard.landslide.instability_zones` finds them, grows the sizs with
  the existing watershed growth and hands the elements to the unchanged polygon
  builder; `with_walls` switches an element between a wall wedge and a
  headscarp band, so the pilot is drawn twice, with every siz walled and with
  none (`research/slope_elements/fig_pilot_example_instability_zones.py`). Over
  the whole pilot: 353,740 pips, 12,015 pifs, 8,223 sizs (every one of the 7,709
  pips, pifs, sizs and 9,204 elements in 24.5 s, plus
  about 7 s for each scenario's polygons (the old pipeline took 27 to 40 s in
  all, so about the same speed). A pif is a chain of pips 2 m apart, so a whole
  hillside was one pif, grown as one element, and up to 4,694 m² (28 evacuated
  polygons over 2,000 m² in the walled run); the segments cut along the
  element's mean aspect did not split curved or branching elements. Every pif
  spanning more than 20 m is now cut in two at the middle of its span along its
  principal axis, and each half again (`split_pifs`, `MAX_PIF_SPAN_M`), before
  growth; each piece seeds its own element and the watershed meets the pieces
  along the ground between. The siz table is still one row per pif. Over the
  pilot that gives 9,204 elements and 9,204 walled (9,354 unwalled) evacuated
  polygons, median 56 m², largest 551 m² (461 unwalled), none over 1,000 m²,
  and the same total area; the old pipeline had 7,093, largest 2,142 m².
  Site 05's right hand hillside now gives about eight polygons of 50 to 300 m²
  and a few fragments. Splitting at 40 m or 30 m left the largest at 1,207 m² and
  709 m²; the asperities of the faces plan were not needed. The old seeding
  code stays for the toy figures (`fig_toy_slope_elements.py`), is marked
  deprecated and is to be retired; the shared slope table is now the two-band
  one, so the old pilot and toy figure scripts read it too.
- **Step 12, urban slope faces (stage D3, 2026-10-04).**
  `steps/s12_urban_slope_faces/gen_urban_slope_faces.py` runs the pipeline over
  an extent and writes the siz table, the elements and the evacuated,
  imminent and inundated zones for the two wall scenarios to
  `temp/hazard/landslide/`. It also reads the evidence for a wall onto every
  pif (`landloss.hazard.landslide.wall_candidates`): a mapped GNS wall, cut/fill
  line, SLIDE cut or fill body, ground material, nearest building. Over the
  pilot, 8,223 pifs are sizs and a further 197 carry a GNS wall and are
  candidates of class `small`; the whole run takes about 40 s. Against the GNS
  mapping, 63% of mapped wall length has a siz pip within 2 m (67% a pip of any
  pif) and 59% of sharp breaks in slope within 3 m. The checks are in
  `table_urban_slope_face_checks.py`. No probability is yet put on a candidate,
  no fragility on a zone, and steps 6 and 7 are still what steps 8 and 9 read.

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
      (done, stage D1), run over pilot examples (done, stage D2) and built as
      step 12 (done, stage D3); next, the lead reviews the 20 m pif split and
      the old seeding and bank code is retired (step 12 plan, phase 5);
   5. the wall probability on the candidates (step 12 plan, phase 4; exposure
      rw step 6, phase 2e), and then the phase 4 checks that need the
      walls: the height shape against Anderson et al. [anderson_2015].

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
7. Choose the large-model route. Run Hancox model 3 over the pilot and review
   its total and slope distribution, then run Nowicki Jessee over Wellington
   as the USGS runs it, with both models' Kaikōura tests reported.
   Kritikos model 2 waits on the lead running its phases 5 and 6 (score
   Kaikōura, fit the transfer function); phase 4, reproducing the paper's AUCs,
   is done.
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
- Hancox slope-class shares, MM and extent masks, Marc apportionment and the
  step 1 handoff in `tests/landloss/hazard/landslide/`.
- Kritikos memberships, fuzzy gamma, inputs, AUC and transfer fit in
  `tests/landloss/hazard/landslide/models/test_kritikos_2015.py`; the paper's
  AUCs are reproduced on Northridge and Wenchuan
  (`validations/kritikos_2015/kritikos_2015_findings.md`), not on Chi-Chi.
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
  and the headscarp band (**T-44**). Stage D2 leaves one for the lead: whether
  the large weak-rock hillside polygons are acceptable
  (`research/slope_elements/pilot_example_slope_elements.md`). The step test is proposed from NZGS
  Figure 35 [nzgs_2025_torlesse]; which Figure 35 row each rock class reads
  waits on a weathering grade the ground map does not yet carry.
- **Siz test choices not yet confirmed by the lead:** the 30 m cap on the pair
  distance, the 1.41 scaling of the 0.7 m drop on diagonals, and the support
  points (the cells 1, 3 and 5 cells below each pip) that give a vertical wall a
  height; and that every soil pif is a siz, because a pip already stands
  steeper than the soil angle.
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
