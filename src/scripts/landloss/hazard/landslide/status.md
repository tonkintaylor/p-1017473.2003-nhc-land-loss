# Landslide hazard: status

**Status:** Two populations are built and ran over the pilot on 2026-10-02:
large failures placed in slope units on the supplied ESNZ grid, and urban
failures on slopes near buildings, coupled to the retaining walls. The urban
result fails far too much ground; its polygons are being rebuilt from faces
and its fragilities are placeholders until they are anchored. The first part
of that rebuild, ground steps 1 and 2, landslide step 1 and the faces plan up to
the wall candidates, was
reviewed against the GNS literature review (`temp/gns_review/`) on 2026-10-02
and is ready to build once the lead settles the step test (Next, 1). The
second part, the failure polygons, landslide steps 5 and 6 and the anchoring skeleton,
was reviewed the same day, and so were the large failures; their proposals
wait on the lead (Next, 3 and 10). The portfolio of large models is proposed,
not agreed; its Hancox model 3 ran over the pilot on 2026-10-06 and placed no
large failure there, and from 2026-10-07 it passes its full area to landslide step 3
(`URBAN_AREA_SHARE` 0). The
slope elements and polygons library passed its toy-terrain
proof (stage D1) on 2026-10-02 and run over pilot examples (stage D2) on
2026-10-03; the pipeline step (stage D3, then step 12, now ground step 4) ran over the pilot on
2026-10-04, and its wall units, their probability and a draw per exposure
world on 2026-10-05 (now exposure rw step 6); the per-zone fragility is next.

**Updated:** 2026-10-09

For a reviewer: read this page, then the plans it names, then each step's
method file under `steps/`, then the code. Detail that used to sit here (the
three routes, the historical accounts, the open questions about the supplied
grid) is in `landslide-notes.md` beside this file.

**Where the steps are now (2026-10-08).** The static per-extent ground work left
this module for the new `ground` module, and the landslide steps were
renumbered in run order. The pipeline runs ground, exposure, hazard, then vul
(`gen_all.py`), and the hazard module runs once, after exposure. Landslide keeps
six steps run by `gen_hazard.py` and two alternative coverage models run by
hand:

- Landslide step 1, slope units; step 2, Hancox 1997 coverage; step 3, the
  large-model landslide realisations; step 4, the zones of each exposure world's
  walls (`s4_wall_zones`); step 5, the urban slope fragility; step 6, the urban
  slope realisations.
- Landslide step 7, slope failure susceptibility (the GWRC rebuild), and step 8,
  Kritikos 2015, are not run by `gen_hazard.py`.
- Ground step 1, terrain derivatives (was landslide step 3); ground step 2,
  ground map (was step 4); ground step 3, instability zones (was step 14);
  ground step 4, slope faces and the siz table (was the faces part of step 12);
  ground step 5, pif cut and fill (was step 13).
- Exposure rw step 6 now also builds the wall units and each world's wall draw
  (was the wall units part of step 12).

The dated entries below keep the step numbers of their day, with a pointer to
the new number where a reader would otherwise be lost. Old to new: step 1 is
landslide step 3; step 2 is landslide step 7; step 3 is ground step 1; step 4
is ground step 2; step 5 is landslide step 1; steps 6 and 7 were deleted; step
8 is landslide step 5; step 9 is landslide step 6; step 10 is landslide step 2;
step 11 is landslide step 8; step 12 is split into ground step 4, exposure rw
step 6 and landslide step 4; step 13 is ground step 5; step 14 is ground step 3.

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

**Large failures**, above the urban size range (700 m² of source area as built):

- [x] Place large failures in the landslide step 1 slope units on the supplied ESNZ 32 m
  probability grid, sized by the Kaikōura law [massey_2020], none starting on
  NLM flatland (landslide step 3, the extend-ESNZ route).
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

**Urban failures**, below the split, on the faces ground step 4 finds in the 1 m DEM
(the old 100 m building buffer went with the old step 6 on 2026-10-08) (`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`):

- [x] Couple the urban model to the walls: sloping land fails in a large
  landslide, through its wall, or by localised failure; a polygon with a wall
  fails with the wall, and if any polygon on a wall fails the wall has failed.
  Walls are drawn per exposure world, failures per world and earthquake, each
  polygon on a lognormal fragility on PGV with a low, medium or high rate
  setting.
- [x] Build the terrain derivatives at 1 to 100 m (ground step 1), the ground map
  (ground step 2) and the slope units (landslide step 1).
- [x] Delineate polygons from banded slope and aspect patches (the old steps 6 and 7);
  superseded, because no published method supports it, and removed
  2026-10-08.
- [~] Find slope elements, crest to toe, once from the 1 m LiDAR DEM as a
  static layer, each with its height and overall angle. **Built as the old step 12, now
  ground step 3 (stage D3, 2026-10-04)**, over the pilot. **Seeding revised
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
- [x] **Class every pif as cut, fill, cut and fill, uncertain or natural
  ground (now ground step 5, 2026-10-05)**, before the wall probability reads the pifs.
  Each pip is walked down its fall direction to the foot of its face. The
  crest and the foot are then compared against a robust quadratic fitted only
  to the ground off the faces (`landloss.hazard.landslide.pif_cut_fill`).
  - The class says whether a face is cut back into the slope or stands proud
    of it, against the platforms around it.
  - A large fill is invisible, because the surface is today's ground.
  - Faces within the fit's own scatter are `uncertain`.
  - The method was chosen over a 30 m rolling mean and a plain quadratic in
    `research/cut_fill/pif_cut_fill.md`.
- [x] **Place the retaining walls on the pifs (ground step 4 and exposure rw step 6, 2026-10-05)**: make
  each wall candidate (a siz or `low_height` pif piece, or a GNS-only piece)
  its own wall unit (the lead, 2026-10-07; joined until then), put a
  points-based prior (the lead, 2026-10-07: verticality, height, length,
  building distance, setting, ground step 5 class, rock or soil cut, wall age, the
  NHC flag; `.agents/plans/wall-probability-points.md`) and the GNS floor on
  each (0.95, GNS-only 0.70), update on the claim reports per property
  (pilot 2026-10-07, after the review: base 0.458 solved for 3,357 expected
  walls, 40% above the interim 2,398), and draw each unit walled
  per exposure world, so the hazard and the exposure share one draw
  (`.agents/plans/placing-retaining-walls-on-pifs.md`). The every-siz-walled
  and none-walled runs stay as bounds; `gen_exposure.main` runs the wall units and draws, and
  `gen_hazard.main` the zones of each world's walls (landslide step 4).
- [~] Attach a fragility per polygon (landslide step 5), on landslide step 4's zones of each
  world's wall draw (2026-10-06); built, with placeholder medians,
  dispersion and rate factors until the anchoring
  (`.agents/plans/anchoring-and-calibrating-the-urban-fragilities.md`, a
  skeleton for the reviewer to develop).
- [x] Draw the urban failures per world and earthquake (landslide step 6).
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
  them in the old steps 6 and 7 (removed 2026-10-08).
- **Landslide step 3, large failures (then step 1):** 7 failures, 0.95 ha, 0.14% coverage of the slope
  units. It rests on placeholders: `BETA_SOURCE_AREA_FRACTION` 0.252,
  `URBAN_AREA_SHARE` 0.25, an ellipse aspect ratio of 2, and sizes from 700 to
  3,000 m². The flat-land mask was added after the run.
- **Ground steps 1 and 2 and landslide step 1 (then steps 3 to 5):** terrain derivatives, a ground map of 19,275 pieces and 41
  slope units over the pilot. The ground map stops short of the extent the
  other steps use, which left 9,144 candidates without a material; the fix is
  phase 0 of the faces plan.
- **The old steps 6 and 7:** 59,132 candidates and 89,808 polygons, superseded and
  removed 2026-10-08.
- **Landslide steps 5 and 6 (then steps 8 and 9):** 44% of polygons failed and 36% of the urban domain was
  evacuated, against the order of 1% the literature gives. Causes: placeholder
  medians below the demand, walls grouped through shared polygons, and the
  delineation. The wall rule and the landslide step 6 counts by cause were added after
  the run; grouping by face waits on the faces.
- **Changed since the run, and needing a rerun of the pilot from ground step 1:**
  ground step 1 now writes only the two cut-and-fill residuals and the 100 m
  topographic position; the face heights, profile curvature, 20 m topographic
  position and vegetation height went with the old steps 6 and 7 on 2026-10-08. The
  ground map's two fill changes are built: SLIDE's
  mixed fill classes read their natural material with fill as the
  modification, and fill reads the GNS modelling set S52 (ground step 2 plan,
  phase 2); ground step 2 needs a rerun to see the fill share fall from 71%. The old
  `evacuated_depth_m` in `landloss.hazard.landslide.urban.geometry`, which read
  the fill thickness only where the material is a fill material, was removed
  with the old steps 6 and 7 on 2026-10-08; the face polygons should read the
  modification, not the material.
- **Literature models:** Nowicki Jessee (2018) is rebuilt and reproduces the
  USGS at Loma Prieta (`validations/nowicki_2018/`); Marc et al. (2016)
  reproduces the paper's fit (`validations/calibration/`); the Hancox
  relationships, model 3 and the landslide step 2 Wellington coverage run are built.
  Landslide step 3 is configured to place that coverage directly. None has been run over
  Wellington. Landslide step 2 already takes each realisation's MM threshold from the
  TS1170.5-derived PGV; its separate Marc amount uses the plan's central
  interface sensitivity rather than final NSHM source geometry.
- **Kritikos model 2** (`.agents/plans/building-kritikos-2015-landslide-model.md`)
  is built end to end: landslide step 8 (then step 11) has run over `wlg-pilot` with the real AF250
  traces and writes H and a coverage raster per realisation, and landslide step 3 reads
  it with `COVERAGE_MODEL = "kritikos_2015"`. The paper's
  average memberships are digitised from Figure 5 to about 0.02
  (`context/lit/landslide/kritikos_2015/figures/`); the fuzzy gamma model, the
  60 m inputs, the AF250 fault reader, the success-rate AUC and the monotone
  transfer-function fit are in `landloss.hazard.landslide.models.kritikos_2015`
  and `landloss.io.active_faults`. The digitisation reproduces the paper's Wenchuan AUC (0.831 against
  0.839) and brackets its Northridge value (0.867 to 0.927 by study area
  against 0.904) with Copernicus 30 m and GEM faults as stand-ins
  (`validations/kritikos_2015/`); Chi-Chi cannot be reproduced, as the GFDB
  lacks its landslides. The transfer function is fitted on Northridge and
  Wenchuan (`gen_kritikos_2015_transfer_function.py`, committed as an io
  asset), each event alone and pooled. The two events disagree by 1.3× to 70×
  in coverage at the same H, and the pooled curve is 2.7× over Northridge's
  observed coverage and 2.1× under Wenchuan's, so the curve is a judgement
  between them, not a measurement. Wenchuan's coverage rests on a secondary-source
  total area (811 km², runout included), marked `verify`. Over `wlg-pilot`
  every cell is at the flat top of the MM and fault memberships and mean
  coverage is 1.47%. The TPI
  window and class thresholds are judgements, though the AUC does not depend on
  the window. The fault term lowers Wenchuan's AUC with the GEM faults, which
  bears on the `FAULT_TERM` choice, which the lead has settled as `"mapped"`
  (2026-10-05); the limitation is in the landslide step 8 method file.
- **Literature review of the first part, 2026-10-02.** Ground steps 1 and 2, landslide step 1 and the
  faces plan's phases 0 to 2 (then steps 3 to 5) were read against the 991 findings of
  `temp/gns_review/`, and the plans edited in place with citations: the faces
  plan, the ground step 1 and ground step 2 plans, and exposure rw step 6. What it changed:
  - the step test now has a published basis, NZGS Figure 35 for rock
    [nzgs_2025_torlesse], checked against the page image; the faces carry an
    overall angle crest to toe, the quantity every Wellington cut criterion is
    written in [grant_taylor_1964; kingsbury_1995; hancox_brabhaharan_1995];
  - three ground map changes are proposed before the faces read it: the mixed
    fills to their natural material with fill as the modification, the fill
    strength from the GNS analysis set rather than one densifying sample
    [monteith_2020; lyndsell_2019], and the sheared zone west of the
    Wellington Fault as crushed rock [grant_taylor_1964];
  - faces only on LiDAR, with a source mask from ground step 1 [de_vilder_2024;
    nzgs_2025_recognition].

  Landslide step 1, the slope units, feeds only the large failures and the review found
  nothing that moves it. Findings from the first review batch, the SR reports,
  had no independent check, so their numbers are read off the page before
  adoption.
- **Literature review of the urban polygons, fragility and draw, 2026-10-02**
  (part A of `temp/handoff-remaining-review.md`). Read: faces plan phase 3,
  landslide steps 5 and 6, the anchoring skeleton, and A-03, A-07, A-08, A-10, A-14 and
  A-15. Edited in place: the faces plan (phase 3 rewritten, new phase 4
  checks), the anchoring skeleton (the reviewer's answers), and the landslide step 5 and
  6 plans. Every number it relies on from a first-batch report was checked
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
    avalanche line for every face, fill included (the lead, 2026-10-07, in
    place of the fill flow slide line the review proposed), one length per
    polygon held to 3 H past the toe and to 0.3 m deposit depth, never under
    a one-cell strip at the toe, spreading back over its own scar where the
    strip would be deeper than H or twice the source depth [de_vilder_2022];
  - **imminent ground to a 35° repose line from the toe** (A-10 revised,
    T-45), the GNS planning screen [de_vilder_2024], one width per polygon
    held to where that line meets level ground;
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
  handoff). Read: landslide step 3 and its placeholders, the rebuild note's portfolio,
  the Kritikos and Hancox plans, and A-01, A-02, A-04, A-05, A-06, A-09, A-11
  and A-12. Edited in place: the landslide step 3 plan ("Literature review of the
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
    run past the split; `URBAN_AREA_SHARE` is set to 0 (decided by the lead
    on 2026-10-07: Hancox does not count the urban model's cut, fill and wall
    failures, and the 700 m² bound keeps the two apart);
  - **`BETA_SOURCE_AREA_FRACTION` of about 0.4 to 1.0, not 0.252**, if the
    ESNZ grid keeps the Kaikōura model's definition (a cell fails where its
    centroid lies in a source), which makes its mean probability the
    coverage. The loss from landslide step 3 would rise by up to four times;
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
  ground step 2 is rerun, which inflates the fill results. GNS holds no wall height,
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
- **Landslide step 4 (2026-10-09)** rebuilds ground step 3's found elements
  from a compact store, recomputing their terrain layers from the DEM, and
  reads back each tile's window cut down to its buildings; on the tiled
  Porirua pilot its wall elements and zones were unchanged. It prints how
  many wall units with no element lie on no searched tile.
- **Step 12, urban slope faces (stage D3, 2026-10-04; since 2026-10-08 split into
  ground step 4, exposure rw step 6 and landslide step 4).**
  `ground/steps/s4_slope_faces/gen_slope_faces.py` (then
  `steps/s12_urban_slope_faces/`) runs the pipeline over
  an extent and writes the siz table and the elements to `temp/ground/`;
  `s4_wall_zones/gen_wall_zones.py` writes the evacuated,
  imminent and inundated zones for the two wall scenarios to
  `temp/hazard/landslide/`. It also reads the evidence for a wall onto every
  pif (`landloss.hazard.landslide.wall_candidates`): a mapped GNS wall, cut/fill
  line, SLIDE cut or fill body, ground material, nearest building. Over the
  pilot, 8,223 pifs are sizs and a further 197 carry a GNS wall and are
  candidates of class `low_height`; the whole run takes about 40 s. Against the GNS
  mapping, 63% of mapped wall length has a siz pip within 2 m (67% a pip of any
  pif) and 59% of sharp breaks in slope within 3 m. The checks are in
  `table_slope_face_checks.py`. Every pif is also tied to its LINZ
  property (2026-10-05; 2,440 straddle two or more properties, 832 are on road
  parcels), and the 979 stretches of GNS mapped wall with no pip near them
  (8.9 km of 30.7 km) are written as `gns_only` line candidates. The wall
  placement (2026-10-05; step 12 method file, now ground step 4 and exposure rw step 6) made 7,248 wall
  units with 3,458 expected walls (3,336 before the claim and NZMM update);
  97% of the mapped wall length is within 2 m of a unit member. In world 0,
  47% of the sizs are walled and the evacuated area is 631,176 m², between
  the all-walled 640,878 m² and the bare 612,654 m². Since 2026-10-06 landslide
  steps 5 and 6 (then 8 and 9) read each world's zones in place of the old step 7's polygons, which the
  pipeline no longer builds: a polygon's wall is its element's wall unit, the
  wall exposure rw step 6 exposes, and landslide step 5 stops if the zones and the
  drawn walls are not one draw. Not yet run over the pilot; the fragility is
  still the old placeholder, not the per-element one. These counts
  predate the review fixes of 2026-10-05 (spine, corner rule, GNS-only and
  stacked title property, NZMM weight); ground step 4 must be rerun.
  - **Every wall on a siz has a polygon (the lead, 2026-10-06).** A pif needs
    at least three pips (`BETA_MIN_PIF_PIPS`); every element a siz grows is
    kept even where the element keep rule would drop it; the width behind
    every polygon's crest is at least half its height and 1 m
    (`BETA_MIN_EVACUATED_WIDTH_H`, `BETA_MIN_EVACUATED_WIDTH_M`), walled or
    not. Rerun over the pilot through landslide step 6 (then step 9):
    6,892 pifs (was 12,015), 4,953 sizs (8,223), 8,729 elements (9,204;
    164 kept only by the siz rule), 5,002 wall units (7,333), 2,609
    expected walls, evacuated 681,973 m² walled, 666,087 m² bare and
    679,143 m² in world 0 (640,878, 612,654 and 632,018 m² before). The
    floor sets every polygon's width on the pilot, so the walled and bare
    widths are now the same. 185 of world 0's 1,570 insured sloping walls
    have no polygon in landslide step 6 (573 of 2,004 before): 175 GNS-only, 4 on
    `low_height` pifs and 6 at the DEM margin landslide step 5 leaves out.
  - **Buildings, wall lines and boundaries (the lead, 2026-10-06).** Pifs
    with most of their pips in a LINZ building outline are dropped (334 on
    the pilot); each wall unit is one line of at most 3 bends and no
    section under 3 m (`WALL_MAX_BENDS`, `WALL_MIN_SEGMENT_M`), whose length
    is the exposure's; and units carry their length in every property they enter by 1 m, which each counts the
    unit as a wall in the claim update. Pilot: 6,558 pifs, 4,676 sizs, 8,425
    elements, 3,961 units (1,908 expected walls), 668,912 m² evacuated in
    world 0, and 48 of 1,141 insured sloping walls with no polygon (42
    GNS-only).
  - **Long walls, GNS-only polygons, setting and tall faces (the lead,
    2026-10-06).** A GNS-only unit gets an element and the minimum polygon on its line
    (`add_line_elements`, in `gen_wall_zones.py`, which now also
    builds the walled and bare bounds); the prior takes 2.0 on a road
    frontage and 1.5 on a property boundary, and tapers from 5 m to 0.1 at
    8 m of face. Pilot: 4,647 units, 2,639 expected walls (2,752 without the
    taper), 99% of pif spine points within 2 m of a wall line, 15 of 1,668
    insured walls with no polygon, 32% of walled units under 1.5 m.
  - **Pif pieces and low-height pifs (the lead, 2026-10-06).** The siz table,
    ground step 5 and the wall units use the 20 m pif pieces the growth uses
    (`parent_pif_id` kept; each piece takes its whole pif's siz test), and
    the units of `low_height` pifs get a line element as the GNS-only ones do.
    Pilot: 10,379 pieces of 6,558 pifs, 6,713 units (417 with more than one
    line, up to 5; the longest 161 m), 3,347 expected walls, 11 of 1,945
    insured walls with no polygon (10 in the DEM margin, 1 GNS-only line
    wholly on other elements), 24% of walled units under 1.5 m.
  - **Pifs cut by the wall rules, near drop height (the lead,
    2026-10-06).** The pifs are cut along their spines by the walls' bends
    rule (one implementation, `bend_split`) with a 50 m cap in place of the
    20 m split, and a wall's height is the 80th percentile of its pips' near
    drops (the lowest cell within 3 m below), read in ground step 4, not ground step
    5's walk to the foot. Pilot: 7,762 pieces, 5,540 units (241 with more
    than one line), 3,462 expected walls, 9 units over 5 m (2,013 before),
    23 of 1,963 insured walls with no polygon (22 in the DEM margin), 18% of
    walled units under 1.5 m against 54%; elements over 50 m long rose from
    16 to 55.
  - **The rules on every output (the lead, 2026-10-06).** No pif under 3 m
    (`BETA_MIN_PIF_LENGTH_M`); each pif piece's line is the stretch it was
    cut on; every wall unit is one line of 3 to 50 m with at most 3 bends
    (walls still over 50 m after the boundary cut are cut into equal
    pieces), asserted in the library. Wall height the 70th percentile of the
    near drops within 2 m (0.6 had given 72% under 1.5 m). Pilot: 6,163 pieces and 4,834 units, none
    breaking a rule, none multi-line, longest 50 m; 3,272 expected walls;
    73% of walled units under 1.5 m (70% pif, 97% GNS-only) against 54%;
    23 of 1,830 insured walls with no polygon (22 in the DEM margin).
  - **Turning cap and the 50 m cap order (the lead, 2026-10-06).** No pif
    piece or wall turns more than 185° in all (`MAX_TOTAL_TURN_DEG`); a line
    over 50 m is cut at its own bends, then (walls only) at property
    boundaries, then evenly. Pilot: 6,220 pieces (387 cut at bends, 72
    evenly), 4,848 units (540 cut at bends, 75 at boundaries, 61 evenly),
    no rule broken, 3,272 expected walls, 21 of 1,775 insured walls with no
    polygon, 72% of walled units under 1.5 m.
  - **Independent candidates (the lead, 2026-10-07).** Every siz pif piece,
    every `low_height` pif piece (renamed from `small`) and every GNS-only
    piece, itself cut by the shared line rules, is its own wall unit with
    one line, probability and draw; the joins are gone. Pilot: 5,832 units
    (4,884 siz, 80.8 km; 91 low-height, 1.0 km; 857 GNS-only, 10.5 km), no
    rule broken, 3,997 expected walls, world 0 drawing 3,991 (2,130 insured,
    24 with no polygon: 21 in the DEM margin, 3 GNS-only lines on other
    elements), 663,401 m² evacuated, 63% of walled units under 1.5 m (55%
    without the GNS-only units).
  - **Every wall has its minimum polygon (the lead, 2026-10-07).** A unit
    whose line finds no free cell gets the band `max(0.5 H, 1 m)` behind its
    line drawn as geometry, overlapping if it must (`forced_polygons`): 5 on
    the pilot (1 with the uphill side unknown, 4 overlapping). No candidate
    is left without a polygon; the 21 insured walls with none in landslide step 6 lie
    outside the shaking extent.
  - **Contained runout and imminent ground (the lead, 2026-10-07).** The fill
    flow slide line ran 724 of the pilot's polygons more than 20 m (to 266 m),
    as single-cell lines down the fall line, and a few imminent bands up to
    73 m uphill. Every polygon now runs out dry, takes one runout length and
    one imminent width (the median of its rays, capped) and sweeps it along
    its whole toe or crest (`slope_polygons`): the longest runout is 20 m
    (2.2 H at the 99th percentile), the longest imminent band 25 m, and
    every polygon leaves at least a one-cell strip below its toe and spreads
    back over its own scar where that strip would be deeper than its height
    or twice its source depth: no deposit is deeper than twice its source,
    and the inundated depth is 5.7 m at the 90th percentile.
  - **Runout by Hunter and Fell's travel angles (the lead, 2026-10-07).**
    The dry reach angle (H/L 0.86 to 1.0) met the ground at the toe of
    every face flatter than about 42°, so 97% of the pilot's polygons ran
    out only the 1 m strip and 69% of the inundated area lay back over its
    own scar, even on steep slopes. Ground below the toe at 20° or steeper
    now takes their unconfined natural slope relation on that angle, which
    runs on down the slope; flatter ground takes their cut relation on the
    face's angle [hunter_fell_2003]. World 0: 1,367 of 6,110 polygons on
    steep ground (median runout 6.0 m), 77% still at the 1 m strip (faces
    onto level ground), 13% at the 3 H cap, the longest 36 m; inundated
    ground below the toe 284,081 m² (125,000 before), 43% of the inundated
    area on the scar. Landslide step 6 world 0: 210,173 m² of inundated land
    dissolved.
  - **Fill bank depth, runout caps and the DEM's face angle (the lead,
    2026-10-08).** A fill bank takes the slip plane from its toe, no deeper
    than its fill (median 0.18 m on the pilot, none deeper than its height;
    before, 56% were); the runout cap is 2, 3 or 4 H by the ground below the
    toe (under 20°, 20° to 35°, steeper); the cut relation reads the face
    with the 1 m DEM's cell of run taken off (median 68°) and lays its run
    out from the face. World 0: 5,848 polygons, 60% at the 1 m strip, 13% at
    the cap; 35% of the inundated area on the scar (43% before), 74
    polygons over their whole scar (966); 175,995 m² of inundated land
    dissolved in landslide step 6.
  - **Seismic distance by Kingsbury zone (the lead, 2026-10-08).** Added to
    the travel run in place of the 1 m strip, then capped: 0.5 m very low
    and low, 1 m moderate, 2 m high, 3 m very high, for a Mw 7.5, 0.7 g
    earthquake. The zone is now scored in landslide step 4 before the runout (it
    agrees with landslide step 5's on 99.9% of the pilot's polygons). World 0: median
    runout 1.9 m (90th percentile 4.5 m), 18% of polygons at their height
    cap (57% of those under 1 m high; 34% of those on 20° to 35° ground), 20%
    of the inundated area on the scar; 185,012 m² of inundated land
    dissolved in landslide step 6.
  - **Smoothed zone outlines (the lead, 2026-10-08).** Every zone is drawn
    through the midpoints between cell centres and rounded, not along the
    cell edges, and its area is the drawn area: evacuated −0.5%, inundated
    −1.6%, imminent −12.5% on the pilot. Landslide step 6 world 0 dissolves 303,203 m²
    evacuated, 53,620 m² imminent and 183,300 m² inundated land. The
    imminent zone now takes the evacuated outline as its inner edge, which
    closes the gaps between them (+0.4% against its cells on the world 0
    cells); the pilot has not been rerun with it.
  - **Specks dropped (the lead, 2026-10-08).** A piece of a polygon's
    inundated strip of under three cells, apart from the rest of it, is
    dropped and its volume spreads back over the scar. The same goes for the
    evacuated ground, before its area and volume are read: 275 pieces in 203
    of world 0's 5,766 polygons, 224 m². The pilot has not been rerun with
    either.
- **Step 13, pif cut and fill (2026-10-05; now ground step 5).**
  `ground/steps/s5_pif_cut_fill/gen_pif_cut_fill.py` classes every pif of ground step 4.
  It writes `urban-slope-pif-cut-fill.parquet`, one row per pif joining the siz
  table on `pif_id`, and the pips with their feet.
  - **Pilot classes (all 12,015 pifs):** 2,198 cut, 1,472 cut and fill, 768
    fill, 1,093 uncertain, 6,481 natural and 3 with too little ground to fit.
  - **Speed:** 9.6 s, against about 45 s for the research code.
  - **Against the SLIDE mapping** (`table_pif_cut_fill_checks.py`, pifs of 10
    pips or more):
    - SLIDE cut slopes read as cut 33% of the time and uncertain 39%, against
      34% and 19% on unmapped ground.
    - SLIDE fill bodies read as fill only 6% of the time.
    - The class is a local reading, not a map of the large earthworks; the
      SLIDE and WCC polygons stay the source for those.
  - **By ground:** weak rock pifs are 31% cut against 37% in soil-like
    ground.
  - **For the wall probability (2026-10-06):** exposure rw step 6's wall units read
    each unit's class into the prior (fill and cut and fill raised, a cut in
    rock over 2.5 m and natural ground lowered, uncertain and unknown
    neutral) in place of the ground map's fill, and each pif's wall height
    as the 80th percentile of its pips' drops to the foot of the face, which
    also sets the prior's height band (the siz table's band is unchanged). Not
    yet rerun over the pilot. `gen_ground.main` runs ground step 5 between ground step 4's faces and
    exposure rw step 6's wall units.

## Next

1. **Settled 2026-10-02:** the lead confirmed the step test as written (faces
   plan, phase 1: the eight height bands and the 24-entry angle lookup, the
   soil-like 35° included) and accepted the three ground map changes (ground step 2
   plan, phase 2).
2. **Rebuild the first part**, in this order, each on the pilot:
   1. one extent for every step and the vectorised zonal statistics (faces
      plan, phase 0);
   2. ground step 1's DEM source mask and survey year (ground step 1 plan, phase 5), then
      rerun ground step 1 (the vegetation height it once rewrote with the
      building mask was removed 2026-10-08);
   3. the ground map changes the lead accepts (the two fill changes built
      2026-10-02; the Wellington Fault sheared zone not yet, **T-89**), then rerun
      ground step 2 over the common extent and review its area shares and strength
      picks;
   4. the slope elements layer (faces plan, phase 1), proven on toy terrain
      (done, stage D1), run over pilot examples (done, stage D2) and built as
      ground steps 3 and 4 (done, stage D3, then step 12); next, the lead reviews the 20 m pif split and
      the old seeding and bank code is retired (ground step 3 plan, phase 3);
   5. the wall probability on the candidates (exposure rw step 6 plan, phases 2e
      and 2f; built 2026-10-05 with its checks, the height shape
      against Anderson et al. [anderson_2015] included), and reading ground
      step 5's cut and fill class and face drops into the prior and the wall
      height (2026-10-06); next, the pilot rerun (Next, 11).

   Landslide step 1 needs a rerun only for the common extent.
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
   Kaikōura model's centroid definition (landslide step 3 plan, "Literature review of
   the placeholders"). Download GNS SR2018/08 and SR2023/04, the forecast
   tool reports, which may answer it first.
7. Choose the large-model route. Run Hancox model 3 over the pilot and review
   its total and slope distribution, then run Nowicki Jessee over Wellington
   as the USGS runs it, with both models' Kaikōura tests reported.
   Kritikos model 2 waits on the lead scoring Kaikōura (phase 5) and
   running it through the curve (phase 6, test do not scale), and on the
   choice between the pooled curve and a per-event bracket; phase 4,
   reproducing the paper's AUCs, and the fit and wiring are done.
8. Replace the large-model runout rule with the de Vilder et al. (2022) reach
   angles; the urban rule is in the faces plan, phase 3.
9. Add imminent-risk land to each large landslide (**T-45**), with the same
   repose-line rule proposed for the urban faces.
10. Measure landslide step 3's placeholders from the Kaikōura inventory (landslide step 3 plan,
    phase 3), after the lead decides the review's proposals for the exponent,
    the cap, the urban share and the source fraction.
11. Recheck the height shape against Anderson et al. [anderson_2015]: the
    pilot rerun of 2026-10-06 (the faces, pif cut and fill, wall units, zones
    and checks, through landslide steps 5 and 6) puts 31% of the walled units under
    1.5 m, against 54%.
12. Run `gen_all.py` over the pilot, so landslide steps 5 and 6 run on landslide step 4's
    zones, review their counts, (the old steps 6 and 7 were removed 2026-10-08;
    landslide step 4 plan, phase 2).
13. Add walls on the flat land, where no wall unit is today. (A wall on a
    property boundary is one unit counted on each property it enters,
    2026-10-06; the loss side's use of it is a vul rw Next item.)
14. **Evaluate the wall curves in PGA in landslide step 6** (a potential future step,
    the lead, 2026-10-06; landslide step 6 plan, "Potential future improvements"): the
    wall curves are published in PGA [koutsoupaki_2023] and landslide step 5 converts
    their medians to PGV with the TS1170.5 PGV/PGA ratio. That is exact
    while shaking steps 4 and 5 scale PGA and PGV by one draw, but landslide step 6
    could sample the realised PGA field at the walled polygons and evaluate
    the curves in PGA directly, removing the ratio and the site class from
    the wall median.
15. **Stop urban runout at building outlines** (the lead, 2026-10-07, not
    yet built): pass the LINZ building outlines ground step 3 already rasterises
    (`building_mask()`) as the `barriers` grid of `build_slope_polygons`, so
    a small failure's debris stops at the house below it. Urban model only:
    a large landslide destroys the building, so its runout is not stopped.
    Roads are not barriers (a road is level ground, where the reach line
    already ends the runout).

## Validation

- Total failed area, urban plus large, against Marc et al. (2016) and Nowicki
  Jessee et al. (2018) at the demand.
- Hancox slope-class shares, MM and extent masks, Marc apportionment and the
  landslide step 3 handoff in `tests/landloss/hazard/landslide/`.
- Kritikos memberships, fuzzy gamma, inputs, AUC and transfer fit in
  `tests/landloss/hazard/landslide/models/test_kritikos_2015.py`; the coverage
  footprints in `test_kritikos_2015_fit.py`; the paper's
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
  ground and free to run past it (landslide step 3 plan).
- **The largest credible single failure**: the cap was raised to 35,000 m²
  (the lead, 2026-10-02), about Gold's slide.
- **How much spatial correlation** to add.
- **The urban failure rate, with a low and a high estimate** (**T-76**). A
  first pass failed about 80% of the pifs judged unstable; John Leeves
  expects far fewer land failures than wall failures (sense check,
  2026-10-05). Whether NHC wants the range or one estimate is **Q-20**.
- **Which runout relation** replaces the translation. For the urban faces the
  lead set Hunter and Fell's travel angles from the crest (2026-10-07, in
  place of the de Vilder et al. dry reach angle set earlier that day); the
  20° switch to the downslope relation, the 80° cap on the cut angle and
  the 1.5 H window the downslope angle is read over are proposals. For the
  large failures it is part B of the review.
- **The deposit depth limits.** A deposit deeper than its strip allows
  spreads back over its own scar (the lead, 2026-10-07) until it is no
  deeper than one height or twice its source depth, both proposals: 3,138
  of the pilot's 5,850 polygons spread back, 72 over their whole scar
  (5,841 and 1,510 of 6,203 before the travel angles and the fill bank
  slip plane).
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
  rerun** (ground step 2 plan, phase 2): the natural material as the material and fill as the
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
`steps/`; the ground steps' are under `src/scripts/landloss/ground/steps/`, and the
wall units' under `src/scripts/landloss/exposure/rw/steps/s6_wall_population/`.
