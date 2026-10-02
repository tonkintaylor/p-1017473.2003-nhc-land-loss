# Landslide hazard: notes

The landslide `status.md` as it stood on 2026-10-02, kept whole when that file
was condensed for review, so that nothing it recorded is lost. `status.md` is
the current page and points into this one by section; where the two disagree,
`status.md` is current. This file is not kept up to date.

**Status:** A first cut of the extend-ESNZ route ran over the pilot and the
full extent and is now reworked onto slope units, not yet rerun; the Nowicki
Jessee (2018) model is rebuilt and checked; the portfolio of models is proposed
but not agreed, apart from the large/small split and the urban model's coupling
to the retaining walls. Phases 1 to 4 of the urban build (terrain derivatives,
ground map, slope units, candidates, failure polygons, fragility, the large and
urban draws) are built and were run end to end over the pilot on 2026-10-02.
The run fails far too much ground, and its delineation of the urban polygons is
not tied to a published method, so the polygons are to be rebuilt from faces
found once in the 1 m DEM (`.agents/plans/building-face-based-urban-slope-polygons.md`); the fragility anchoring has not been run.

**Updated:** 2026-10-02

## Approach

The route is not yet formally chosen — see `## Open decisions` — but the
cheapest of the three has now been built end to end, so that there is something
concrete to choose against rather than three descriptions. No progress marks
against the module as a whole until the decision is made; the step that exists
carries its own marked plan under `steps/`.

**The starting point.** ESNZ's probabilistic landslide model is in hand: a 32 m
grid carrying failure probability at discrete shaking levels. Three gaps in it
matter for this study.

- **No spatial correlation factor.** Cell probabilities are independent, so
  aggregating them across the portfolio misses the clustering that decides how
  many claims one event produces.
- **No smaller landslides.** Much of the loss here is expected from small
  failures on modified slopes; the register carries this as **I-08**.
- **No runout.** Loss of support and runout are settled differently, so a model
  without runout cannot answer the policy question.

**The three routes.** The first keeps the ESNZ model as the primary model; the
others replace or extend it.

- **Validate or recalibrate the ESNZ model** and keep it as the primary model.
  The cheapest route: check it against observed failures and the Greater
  Wellington zonation, and recalibrate the rate where it disagrees, rather than
  changing its structure. It leaves the three gaps above unclosed, so it only
  stands if they matter less than the calibration does.
- **Build a new model and compare it against ESNZ.** Drafted in full in
  `.agents/plans/estimating-eq-landslide-extent-wellington.md` — explicit source
  and runout polygons, Newmark displacement, an absolute rate calibrated against
  Nowicki Jessee (2018), and discrete failures sampled from a Kaikōura v3 size
  distribution. That plan has not been reviewed or agreed with the project team.
  ESNZ becomes the cross-comparison rather than an input.
- **Extend the ESNZ model.** Keep the 32 m probability grid as the base rate and
  add correlation, small failures and runout on top of it. Cheaper, and starts
  from a model that has already been through review, but inherits its 32 m
  resolution and its discrete shaking levels.

**The portfolio now proposed.** Rather than choose one route, build several
models split at a landslide size threshold. For large, green-field failures:
three from the literature (Nowicki Jessee 2018, Kritikos et al. 2015, Hancox et
al. 1997), possibly the GNS/ESNZ model, and a bespoke refit. For small failures
on modified slopes: one urban model. A strength-based model after Godt et al.
(2008) is proposed, and Marc et al. (2016) calibrates every large model's total
area. Set out in `potential-landslide-rebuild.md`; not yet agreed, apart from the large/small split, which is agreed (500 m² of
source area as the working threshold). The project lead now thinks 500 m² may be
too low (2026-10-01): three GNS reports put cut and fill failures at
10²–10⁵ m³, which spans it. The build places the boundary at 700 m² instead
(`LARGE_MIN_SOURCE_AREA_M2`, the top of the urban size range, decided in
section 3.9 of `.agents/plans/urban-slope-build-contract.md`), against the
agreed working 500 m²; that move is for the lead to confirm, under
`## Open decisions`. Extend-ESNZ becomes the GNS member of it.
Build plans for models 2 and 3, and for the calibration of every large model,
are in `.agents/plans/building-kritikos-2015-landslide-model.md` and
`.agents/plans/building-hancox-landslide-model-and-calibration.md`.

**The urban model is coupled to the retaining wall exposure** (decided
2026-10-01). It works on candidate failure polygons: sloping ground within
100 m of a building and off the NLM flatland, delineated at several scales so
a small face can sit inside a larger one, and snapped to the candidate wall
lines, which alone are split at property boundaries. Each polygon carries a
fragility function of the demand rather than a probability. Land in
a polygon fails one of three ways: in a large-model landslide, which supersedes
it; through its retaining wall, whose fragility by size and condition decides;
or, with no wall, through a localised failure fragility. The wall population is
drawn per exposure realisation on its own stream, separate from the hazard
realisations, and the realised model per exposure world is written as a
GeoParquet for review before any earthquake is drawn. Walls on flat land stand
alone and fail by shaking in `vul/shaking/rw`. An urban failure rate setting,
low, medium or high, scales the fragilities and is reported with every result.
Topographic amplification is folded into each polygon's fragility. The geometry
rules and the rate anchoring are still open; see `## Open decisions`. The build
plan is `.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`
and the interface contract every step is built against is
`.agents/plans/urban-slope-build-contract.md`.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Extend step 3 to 1 m, write the aspect per scale, and derive face height,
  cut-and-fill residual, profile curvature, topographic position and
  vegetation height (`s3_multiscale_slope`).
- [x] Build the ground map, one planar partition carrying material,
  modification, prior failure, groundwater and a strength set per piece
  (`s4_ground_map`); QMAP and the NZGD boreholes are not read.
- [x] Cut slope units on the 10 m grid for the large models, after
  `r.slopeunits`, on the repository's own flow routing (`s5_slope_units`).
- [x] Delineate the urban failure candidates at 1, 3, 10 and 30 m by banded
  connected components within 100 m of a building (`s6_urban_slope_candidates`);
  superseded by the faces below.
- [x] Reconcile the candidates to the wall lines and fix each polygon's
  evacuated, inundated and imminent geometry per wall state
  (`s7_urban_slope_polygons`); superseded by the faces below.
- [x] Run the urban chain over the pilot end to end (the lead, 2026-10-02); what
  it showed is the context of `.agents/plans/building-face-based-urban-slope-polygons.md`.
- [>] Find faces, crest to toe, once from the 1 m DEM as a static layer, by
  geomorphons [jasiewicz_stepinski_2013] and the step test, and build one
  failure polygon per face: the wedge behind the crest [nzgs_mbie_2017], the
  runout below the toe [de_vilder_2022; hunter_fell_2003], the Kingsbury rating
  [kingsbury_1995]; checked against the SLIDE breaks in slope [townsend_2020].
  Replaces the banded patches, the splitting and snapping, and the wall
  grouping through shared polygons (`.agents/plans/building-face-based-urban-slope-polygons.md`).
- [~] Attach a fragility per polygon and wall state, anchored to the rate
  setting (`s8_urban_slope_fragility`, phase 3); the step and the anchoring
  validation (`validations/urban/`) are built, the anchoring is not run, so the
  localised medians and dispersion and the low and high rate factors are
  placeholders.
- [x] Rework step 1 onto the slope units with ellipse sources and draw the
  urban failures per world and earthquake (`s9_urban_slope_realisation`,
  phase 4).
- [ ] Run steps 8, 1 and 9 over the pilot after the exposure wall population,
  with the lead's review of the step 8 model file before any earthquake is
  drawn.

**Forward-use scenario, for the report.** Where a landslide model or its
calibration needs a magnitude or a source distance, every site in the study
area is taken to be **25 km from an Mw 8.1 event** (`BETA_SCENARIO_MW`,
`BETA_SITE_DISTANCE_KM`).

- **Source.** The modal magnitude and distance of the New Zealand National
  Seismic Hazard Model 2022 deaggregation of PGA for Wellington at
  Vs30 = 400 m/s, as provided by the project lead. Cite the NSHM 2022
  (Gerstenberger et al. 2022, GNS Science Report 2022/57).
- **The source is the Hikurangi subduction interface** (confirmed by the project
  lead). Marc et al. (2016) and the Hancox relationships are fitted on crustal
  earthquakes, so they calibrate the models on crustal events but do not set
  the Wellington total. The longer shaking of an interface rupture is a stated
  limitation of models 1–3; see the calibration plan's Risks.
- **Historical accounts for validation.** Two GNS compilations of contemporary
  and later accounts, recorded in `context/lit/landslide/SOURCES.md` (the PDFs
  are over 50 MB and are kept at `U:\MAMI\Literature`): Downes & Grapes (1999)
  on the 1855 Wairarapa earthquake and Grapes, Downes & Goh (2003) on the 1848
  Marlborough earthquakes. Both were swept
  by keyword for landslide passages and the surrounding accounts read; neither
  was read line by line, so an account that never says slip, slide or cliff
  could have been missed. Their use is set out under `## Validation`.

- **A figure for the report.** Gold's 1855 watercolour of a slip caused by the
  earthquake near Wellington, in `context/lit/landslide/gold_1855/` (GeoNet
  earthquake story 2178057, ref. B-103-016). Caption as given: *Landslip caused
  by earthquake near Wellington, New Zealand. January 1855.* It is an
  illustration only, with no place, scale or date beyond the month. To settle
  before it goes in: the holding library's reproduction terms, and whether it
  is the Wellington-Petone road painting Downes & Grapes (1999) list.
- **Still to record for the report:** the return period, and the NSHM version and
  tool the deaggregation was taken from.

**Marc et al. (2016) rebuilt and checked.**
`landloss.hazard.landslide.calibration.marc_2016` reproduces the paper's fit on
its own 26 events (steepness scale 11.7° against 11.6°, sensitivity within 10%);
see `validations/calibration/marc_2016_table_s1_findings.md`.

**Hancox relationships and the calibration interface built.**
`landloss.hazard.landslide.models.hancox_1997.relationships` holds the area
affected, maximum distances, intensity thresholds and slope-class shares; the
digitised Figure 19 points refit to the published regression.
`landloss.hazard.landslide.calibration` applies the extent mask and the scaling
to a target total. Neither has been run on an event yet; Kaikōura is next.
How Marc is used for the Hikurangi interface is open; the options are in the
calibration plan.

**Model 1 of the portfolio: Nowicki Jessee (2018), rebuilt.**

- [x] Rebuild the model and its input layers from the raw public sources, in
  `landloss.hazard.landslide.models.nowicki_2018`; the portfolio itself is set
  out in `potential-landslide-rebuild.md`.
- [x] Check it against the USGS `groundfailure` run at Loma Prieta, in
  `validations/nowicki_2018/`: the equations reproduce the USGS output, and the
  rebuilt inputs give total landslide area within 1% of it
  (`nowicki_2018_loma_prieta_findings.md`).
- [ ] Run it over Wellington, with PGV from the scenario's Sa(1.0 s) at site
  class 2; the reader for Sa(1.0 s) at site classes 1-7 is in
  `landloss.io.nlm`.
- The source datasets reach T: through the `get_` scripts in `static_data_gen/`,
  which have to be run before anything above can read them.

## Beta build

A first end-to-end run is being assembled that produces the right data
structures rather than the right numbers; see
`.agents/plans/beta-build.md` for the whole chain.

Landslide is the module the beta needs least from: `steps/s1_landslide_realisation/`
already emits the structure the chain expects — **polygons of evacuated ground
and polygons of inundated ground**, one set per realisation. The two types may
overlap each other.

One caveat on the structure, because the chain downstream would double count
without it. `drop_overlapping()` enforces non-overlap among the **evacuated**
polygons only. The inundated polygons are those same circles translated
different distances in different directions, so two of them can and do land on
top of one another — most obviously where two failures on opposite sides of a
gully both run into its floor. Ground buried by two landslides is buried once,
so anything summing inundated area has to dissolve first. The run output prints
both the summed and the dissolved area for each type, so the gap is visible
every run.

This is a **conflict with the stated beta contract**, which says polygons of the
same type may not overlap. Evacuated ground meets it; inundated ground does not.
It has to be settled before the intersect downstream is written, and the depth
attribute makes it sharper: where two landslides bury the same ground, it is not
obvious whether the depth there is the deeper of the two or the sum.

Each polygon also still needs a **depth**, approximated from the **total
evacuated area of the landslide it belongs to** — a bigger failure is a deeper
one. Depth belongs to the landslide rather than to the piece of it inside any
one claim, so it is attached here and carried through the intersect. Dissolving
the inundated polygons to satisfy the contract would discard the
`landslide_id` that depth hangs off, which is why the two questions are one
question.

The step now draws one realisation per id in `config.REALISATION_IDS`, seeded
from the project-wide `BASE_SEED` through
`landloss.hazard.realisation.realisation_seed`, and writes
`landslide-realisation-rNNN[-pilot].geoparquet` with `realisation_id` on every
polygon. A landslide layer and a liquefaction layer carrying the same
`realisation_id` are the same modelled earthquake, so a property's causes can be
summed.

## Where it is now

`steps/s1_landslide_realisation/` holds the large model of the extend-ESNZ
route, reworked onto the slope units in phase 4 of the urban build. It
resamples the supplied 32 m probability grid onto step 3's 10 m DEM grid, sums
the expected failed area per step 5 slope unit net of a 25% urban share, draws
a Poisson count per unit and a size per failure from the Kaikōura power law
(exponent 2.1) truncated to 700–3,000 m², seeds each at a crest-weighted
high-probability cell, places an ellipse along the downhill azimuth that
crosses unit boundaries when larger than its unit, drops the smaller of any
overlapping pair, and moves each one downhill by a distance that grows with the
slope — emitting the source polygon as `evacuated land` and the displaced
polygon as `inundated land`, with `population` `large`, its `unit_id` and an
`LS` id. No large landslide starts on NLM flatland: the probability is masked
there from the step 4 ground map (the lead, 2026-10-02), not yet rerun. The slope and
downhill direction it uses are in `landloss.common.utils.terrain`, and the reader
for the grid is `landloss.io.source_material`; both are library code with tests,
because they will outlive whatever the model turns into. Its method and its
phased plan are in the step folder.

The version before the rework, sampling every 32 m cell independently with
circular footprints, was run against the real grid over both the pilot box and
the full study area. The pattern was right -- the hills either side of the Hutt
Valley and around Porirua are dense and the valley floors are clear -- and the
figure under `report/hazard/landslide/landslide-realisation/fig/` is how that
was checked. Its areal coverage calibration is restated in the rework as the
placeholder `BETA_SOURCE_AREA_FRACTION` (0.252), recorded with the size law in
`steps/s1_landslide_realisation/s1_landslide_realisation_implementation_plan.md`.
The reworked step is tested end to end on a synthetic three-unit plane and has
not been run; the questions it raises are under `## Open decisions`.

Two of the three gaps are closed only nominally. There are small failures now,
drawn by the urban model, but on placeholder fragilities; there is runout, but
it is a rigid translation along one bearing. Spatial correlation exists only
within a slope unit.

The folder also holds `validations/fig_landslide_vulnerability_model_gwrc.py`,
which draws the Greater Wellington zonation the result gets checked against.

The Nowicki Jessee (2018) model is rebuilt as library code in
`landloss.hazard.landslide.models.nowicki_2018`, with its source datasets
fetched to T: by `static_data_gen/` and checked against the USGS in
`validations/nowicki_2018/`. It has not yet been run over Wellington.

**Phases 1 to 4 of the urban build** are in the repository, each step with its
method and plan under `steps/`, every library function tested on synthetic
inputs, and only the step 3 DEM, slope and aspect run over the pilot:

- `steps/s3_multiscale_slope/` builds the DEM, slope and aspect at 1, 3, 10,
  30, 50 and 100 m from one 1 m LINZ fetch, and `gen_terrain_derivatives.py`
  writes face height, cut-and-fill residual, profile curvature, topographic
  position and vegetation height (from a new LINZ 1 m surface model reader,
  `landloss.io.readers.get_dsm`). `gen_multiscale_slope.py` is run over the
  pilot (the DEM, slope and aspect at all six cell sizes are in
  `temp/hazard/landslide/`); `gen_terrain_derivatives.py` and the two figure
  scripts are not yet run over the pilot.
- `steps/s4_ground_map/` writes `ground-map[-pilot].geoparquet` from the SLIDE
  materials, the 1:50,000 geology, the NLM `l3_yp`, the SLIDE genesis, the WCC
  earthworks, the thresholded residual and the NLM groundwater over the flat
  land, by precedence in `landloss.hazard.landslide.ground_map`; the strength
  set per material is one row of `wellington-greywacke-strength.csv` per
  grade, chosen by a rule the tests pin. Material is `unknown` outside the
  three material sources because QMAP has no reader.
- `steps/s5_slope_units/` writes `slope-units[-pilot].geoparquet`, half-basins
  of each channel link merged by aspect and split over 50 ha
  (`landloss.hazard.landslide.slope_units`, on `hydrology.route_grid`; pysheds
  is not used), with the unit count's sensitivity to the channel threshold
  printed.
- `steps/s6_urban_slope_candidates/` writes
  `urban-slope-candidates[-pilot].geoparquet`, the banded connected components
  at each scale with the terrain, distance and ground map attributes on each
  (`landloss.hazard.landslide.urban.delineation`).
- `steps/s7_urban_slope_polygons/` writes
  `urban-slope-polygons[-pilot].geoparquet`: candidates snapped and split to
  the exposure wall lines, `slope_id`, the wall on each edge, the nesting
  parent, the Kingsbury rating and zone, the amplification factor and the
  fixed state geometries and depths (`landloss.hazard.landslide.urban.geometry`,
  one named function per rule with its source cited).
- `steps/s8_urban_slope_fragility/` writes
  `urban-slope-model-wNNN[-pilot].geoparquet` per exposure world, a lognormal
  on PGV per polygon: the Koutsoupaki et al. (2023) wall curve by size and
  condition, converted from PGA at the polygon's own PGV/PGA ratio, where a
  wall was drawn on its edge, insured or not (it reads every wall the world
  drew, flat-land walls left out), and the localised median from the continuous
  Kingsbury rating where none was, divided by the amplification factor and
  multiplied by the rate factor (`landloss.hazard.landslide.urban.fragility`),
  with a medians table by zone and wall state and a map for the lead's review.
- `validations/urban/` draws the low, medium and high curves per zone against
  `urban-fragility-anchors.csv` and fits the localised constants and a
  dispersion; it reads the TS1170.5 grids and has not been run.
- `steps/s9_urban_slope_realisation/` draws each polygon per world and
  earthquake on the urban stream, one uniform per wall line, and if any
  polygon on a wall fails the wall has failed and every polygon on it fails
  (the lead's rule, 2026-10-02); it prints the rate setting, supersedes the
  failed polygons that share ground with a large-model evacuated polygon, then
  absorbs nested failures among the rest largest first, and writes the
  survivors' evacuated, inundated and imminent land beside the large rows as
  `landslide-realisation-wNNN-rNNN[-pilot].geoparquet`, with
  `urban-wall-outcome-wNNN-rNNN[-pilot].parquet` naming each sloping-land
  wall's outcome (`landloss.hazard.landslide.urban.realisation`).
- `gen_hazard.py` runs in two passes: `main()` for shaking, liquefaction and
  landslide steps 3 to 6 then 1, and `main_urban()` for steps 7 to 9 after the
  exposure module.

Steps 3 to 6 hold whole grids in memory, so the full extent at 1 m needs
tiling before they can run, and each of their plans names that as its phase 2.
The likely route is to run per territorial authority (lead, 2026-10-02);
step 7's phase 2 decides whether its polygon count fits in memory. Step 1's
full-extent run is its phase 6. Steps 8 and 9 work on the model's vector rows,
hold no grid and have no tiling phase.

## Next

1. Choose between building a new model and extending ESNZ, reviewing the
   drafted plan with the project team as part of that. The first cut is intended
   to inform that decision, not to pre-empt it.
2. Confirm with the supplier what shaking level the grid is conditioned on, and
   whether its probabilities are conditional on that shaking or already carry a
   rate. Nothing in the code depends on the answer, and nothing can be written up
   without it.
3. Fit the size distribution to an inventory, and replace the displacement ramp
   with a Newmark displacement. Both are placeholders and both move the answer.
4. Add spatial correlation, which is the largest remaining error and the one that
   most affects the shape of the loss distribution rather than its average.
5. Run the vul land damage step on the combined realisation over the pilot.
   The intersection with insured land per claim, keeping loss of support and
   runout separate, is built in `vul/landslide/land` step 3.

The phased build for the new-model route is in
`.agents/plans/estimating-eq-landslide-extent-wellington.md`, not here.
6. Run the Nowicki Jessee model over Wellington, with PGV from the scenario's
   Sa(1.0 s) at site class 2 (`PGV (mm/s) = 750 * Sa(1.0 s) [g]`, the shaking
   module's agreed relation).
7. After the beta, take the site class from the Foster et al. (2019) Vs30 model
   rather than the fixed site class 2 (**T-15**).
8. Add imminent-risk land to each landslide (**T-45**), as agreed on
   2026-09-25: a new circle centred on the same place, about the same size; the
   part of it upslope of the evacuated polygon is the additional evacuated land
   behind a regressed headscarp; imminent inundation is re-inundation of the
   same area, so its areas can be read off even where it runs outside the
   property. The chance of imminent land depends on slope. Its extent is really
   geology-dependent, but geology is not in the model, so for now it is derived
   from the diameter -- a decision to revisit. Maxim Millen expects to take this
   on (2026-09-30), and it may be deferred. **T-44** sets the regression rules
   to agree with John Leeves.
9. Replace the runout rule, which moves every failure by a distance set by slope
   alone (decided 2026-10-01). Runout is to depend on volume and failure style:
   de Vilder, Brideau & Massey (2022), *Empirical and physics-based runout
   models*, GNS Science Report 2019/38, gives reach angle (H/L) against volume
   with exceedance lines. There, dry earthquake failures stop short (median H/L
   about 0.86 at 1,000 m³), while fill and wet flow slides travel about twice as
   far.
10. Build the faces layer and the face-based polygons (`.agents/plans/building-face-based-urban-slope-polygons.md`, phases 0 to
    3), then rerun the pilot and record the counts and timings in the method
    files.
11. Run the anchoring (`validations/urban/fig_urban_fragility_anchors.py`) on
    the TS1170.5 site class I grids, set the localised constants, the
    localised dispersion and the low and high rate factors from it, and write
    its findings file; then the lead reviews the step 8 model file.
12. Measure `URBAN_AREA_SHARE`, `SOURCE_ASPECT_RATIO` and
    `BETA_SOURCE_AREA_FRACTION` from the Kaikōura inventory (step 1's plan,
    phase 3).
13. The plan's checks over the pilot: the share of urban failures confined to
    one property, against the expectation under "Local failures versus global failures" in
    `.agents/context/land-damage-mechanisms.md`, and the failed polygon sizes
    against the Wellington cut-failure record.

## Validation

- Failure probability and total areal coverage against the ESNZ 32 m grid at
  matching shaking levels. This is the comparison the build-new route exists to
  support, and on the extend route it is the check that the base rate survived
  the extensions.
- Simulated landslide density against the GWRC `SEVERITY` 1–5 zonation, as a
  rank correlation rather than an absolute one — the layer is a susceptibility
  zonation, not a rate. A script under `validations/`.
- Total areal coverage against the Nowicki Jessee (2018) estimate for the same
  shaking.
- Simulated size distribution and reach angles against the Kaikōura inventory.
- **Historical accounts of 1855 and 1848** (Downes & Grapes 1999; Grapes et al.
  2003). Qualitative rank-order and presence/absence checks, never calibration.
  Neither report has a slip inventory, map, count or area, and neither gives an
  MM value in its text (the 1848 report has an isoseismal figure whose OCR is
  unreadable; read it from the original).
  - *1855 (Mw 8.1-8.2, Wairarapa Fault, January, little antecedent rain
    reported).* The closer match in size to the Mw 8.1 scenario.
    - **Positive control:** the Rimutaka Range and Palliser Bay coast. Iorns
      (1913) has slips "hundreds of feet long and many chains across" burying
      the Muka Muka rocks; McKay (1901) describes slips from at least 2,600 ft
      down to river bottoms near 500 ft, "thousands of acres" in all, larger on
      the western slope. Both are late and exaggerate, but agree with each other
      and with contemporary reports of the Rimutaka road.
    - **Positive control:** the Rimutaka Road and the Hutt/Petone road. The
      *Spectator* of 3 Feb 1855 has one slip of any size on the Petone road,
      "several considerable landslips" in the lower Hutt gorges and seven miles
      of landslips and crevices beyond Kaitoke. Fox puts the road damage at
      about £2,000. A modelled failure density on the road corridors and a
      length of road blocked can be set against these. A later account has a
      3-acre slide into the harbour burying part of the Hutt road.
    - **Eastern harbour hills:** several heavy landslips were visible from
      Wellington; the Wainuiomata and Orongorongo slopes are described as split
      with fronts fallen. Several of these authors also confuse 1848 and 1855.
    - **Negative or low checks:** Wellington town and the western suburbs
      (fissures and chimneys, no slips reported), the Hutt Valley floor
      (fissures and sand cones, not slips), Porirua (uplift and settlement of
      the road only), the Kaitoke to Hodder's road ("all right"), and eastern
      Palliser Bay ("not affected to any great extent"). Damage was worst on low
      ground and least on rock sites, the ordering the site class term should
      reproduce.
    - **Far field:** cliff collapses at Wanganui and Rangitikei, and slips near
      Cape Campbell and Flaxbourne. Useful only if the model extends that far.
  - *1848 (Mw at least 7.4, Awatere Fault, about 100 km of rupture, and two
    severe Wellington aftershocks on 17 and 19 October).* A smaller event
    with heavy antecedent rain.
    - **Rain plus shaking:** about 10 inches fell in the week before the
      mainshock, more than three times the previous month. Colenso in November
      found "streams of stones" descended from the hill summits at Palliser Bay,
      mudstone cliffs east of the bay still falling, and blamed both the
      shocks and the rain. This is the one account that can test whether the
      models respond to wet antecedent conditions; they have no such term, so
      it can only be a stated limitation.
    - **Wellington:** fissures on loose gravelly ground and at cliff and terrace
      edges, none deep or wide; rocks rolling into the sea from the Heads round
      to Cape Terawhiti; and a Gold painting of gullies from the old Porirua
      Road, read by the editors as landslide scars in the Ngaio Gorge. Shaking
      was "comparatively light" near rock at Karori Road and Kaiwharawhara.
    - **Near the rupture:** rockfalls and slips at Cloudy Bay, Queen Charlotte
      Sound and the lower Awatere, and slips on the White Bluff seaward face.
      A source-adjacent check for a crustal event, not a Wellington one.
    - **Several accounts placed here belong to 1855.** The editors flag Heaphy's
      Orongorongo slips and McDowell's Wainuiomata ones as probable confusions.
      Do not count them for 1848.
  - **How to use them.**
    1. Run the calibrated models for a crustal Mw 8.2 and an Mw 7.5 scenario
       with their own shaking fields, not the Hikurangi Mw 8.1 at 25 km
       scenario, which is a different source. Expect the Rimutaka, Palliser Bay
       and eastern harbour slopes to rank highest, the Hutt and Petone road
       corridors high, and the Wellington west, Porirua and the Hutt floor low.
    2. Compare road-corridor failure counts and blocked lengths with the
       *Spectator* passage for the Petone, Hutt gorge and Rimutaka roads.
    3. Rank against Hancox (1997) and the Marc (2016) total for the same events
       rather than against these reports for total area, which they cannot give.
  - **Limits.** Evidence clusters on travelled corridors and settlement; a silent
    hillside is weak evidence of no slips. Many accounts are reminiscences
    decades later with exaggerated sizes, near-duplicates echo one another, and
    1848 and 1855 are confused. The forest cover of the 1850s is not that of
    today, and neither event is an interface rupture, so neither says anything
    about the longer shaking that limits models 1-3.
- Proportion of landslides confined to a single property. Local expectation in
  `.agents/context/land-damage-mechanisms.md` is that most are, with
  multi-property failures concentrated in gullies; if the model does not
  reproduce that it is wrong regardless of how well it matches the literature.
- The rebuilt Nowicki Jessee model against the USGS `groundfailure` run at Loma
  Prieta, equations and input layers separately:
  `validations/nowicki_2018/nowicki_2018_loma_prieta_findings.md`.

## Open decisions

Everything here is a decision somebody has to make, not a task somebody has to
do. The tasks and limitations that follow from them live in the register; these
stay here because they are choices about what the model *means*, and the step
cannot be signed off while they are open.

### About the supplied grid

- **What a cell's probability is a probability of.** The grid gives a number per
  32 m cell. Either it means *this cell contains a failure somewhere in it*, and
  the size of that failure is ours to choose; or it means *this whole 1,024 m²
  cell fails*, and the size is already decided. The model takes the first
  reading. The second would need a mean source area of about 1,028 m² against
  the 259 m² now used, would put landslides over 3.9% of the graded area against
  the order of 1% the literature gives, and would raise the loss about fourfold.
  Only the supplier can settle it, and nothing else on this list moves the answer
  as much.
- **What shaking level the grid is conditioned on.** Read from the file name
  (`EILProb_PGA2g.tif`) and unconfirmed, as is whether the probabilities are
  conditional on that shaking or already carry a rate per year. The step runs
  either way; no result can be written up until this is known.
- **L-08 against using ESNZ as the primary model.** The ESNZ model is confirmed
  to be the same GNS slope failure model held in PRUE that **L-08** restricts to
  cross-comparison only. The team may still adopt it as the primary model, so
  that register entry needs revisiting if the extend route is chosen.
- **Build new against extend ESNZ.** Undecided, and the decision the rest of the
  module waits on. The extend route now exists in runnable form, which changes
  what the comparison costs but not what it is.

### About the landslides the model draws

- **The footprint is an ellipse, not a grown source.** A real source area is
  elongated down the slope; the reworked step 1 places an ellipse of the
  sampled area along the downhill azimuth, at an aspect ratio of 2 that is a
  placeholder for the Kaikōura ratio. It does not follow a gully or stop at a
  ridge. The decision is whether that is close enough, or whether to grow the
  source across the slope facet, the fuller answer that phase 4 of the step's
  plan carries.
- **The total area is set by a placeholder, not by the size law.** The rework
  moved to two populations: above 700 m² step 1 draws the published Kaikōura
  exponent of 2.1 [massey_2020], and below it the urban model draws. Because the
  count is Poisson on the expected area, the exponent no longer moves the total;
  `BETA_SOURCE_AREA_FRACTION` (0.252) does, restating the earlier calibration
  that needed an exponent of 1.19 from 3 m². The decision is what sets that
  fraction: the supplier's reading of a cell's probability, or a fit to the
  Kaikōura inventory.
- **The 3,000 m² upper bound.** With the count drawn on the expected area the
  cap no longer moves the total, but it still sets the largest single failure
  and so how many properties one landslide can reach. Both bounds were given as
  a range to model rather than derived from anything. The decision is what the
  largest credible single failure in Wellington actually is.
- **Failures are sampled independently between slope units, so the model has
  little clustering.** Real
  failures share a hillside, a geology and a shaking level. Independent sampling
  gets the average right and the spread wrong — too few very bad events and too
  few very quiet ones — and the portfolio question NHC is asking is a question
  about the spread. The decision is how much correlation structure to buy, given
  the grid supplies none.

### About what happens after a failure

- **Runout is a rigid translation, so debris neither spreads nor follows a
  gully.** The displaced polygon is the source circle moved downhill, keeping its
  area and shape. The decision is whether the loss model needs debris that
  widens, thins and routes down the steepest path, or whether a translated
  footprint is close enough for a settlement question.
- **Displacement depends on slope alone, not on the size of the failure.** A
  3 m² slip and a 3,000 m² one on the same hillside travel the same distance,
  which no inventory supports. Decided 2026-10-01 that it changes (`## Next`,
  item 9); still open is which relation replaces it, and whether earthquake
  failures of fill take the dry or the flow-slide relation, which turns on how
  wet the fill is assumed to be.
- **Inundated polygons may overlap one another; evacuated ones may not.** The
  beta contract says polygons of the same type may not overlap, and runout does
  not meet it — two failures either side of a gully both land in its floor.
  Dissolving them would discard the `landslide_id` that depth hangs off, so the
  decision is whether depth at doubly-buried ground is the deeper of the two or
  the sum. It has to be settled before the per-property intersect is written.

### About how the model is exercised

- **The pilot box is flat suburb and does not test the model.** Over it the
  failures have a median slope of 3°; over the full study area the median is 28°.
  The pilot exercises the code and nothing else, so the step should be judged on
  the full extent. The decision is whether to keep the current pilot for speed or
  move it onto hill country where it would also be a check on the model.
- **T-22** — explicit extent against per-property classification. The drafted
  plan takes the explicit route, and the decision closes when the plan is agreed.
- **T-15** — the site class. Carried as a parameter rather than blocking on it.
- **T-11**, **T-20**, **T-50** — retaining wall, cut-and-fill and claim report
  data. The Kaikōura inventory is natural slopes and the losses here are
  expected on modified ones, so a second population conditioned on this data
  is the plan's own largest technical risk. The SME suburb estimate (**T-19**)
  will not be obtained; the claim report extraction is the calibration source
  for the urban population. The raw source area and debris trail polygons are
  now readable, via `landloss.io.kaikoura` — the fit itself is still to do.

### About the urban model

- **The urban polygons are being rebuilt from faces.** The pilot run of
  2026-10-02 failed 44% of the polygons and evacuated 36% of the urban domain,
  against the order of 1% the literature gives. Three causes: placeholder
  fragility medians below the demand, walls grouped through shared polygons
  (one group of 737 walls under one draw), and a delineation of slope bands,
  aspect octants and 25 m strips that no published method supports. The
  replacement, and the references it rests on, are in `.agents/plans/building-face-based-urban-slope-polygons.md`.
- **Where the large/small split sits.** The agreed working threshold is 500 m²
  of source area; the build places it at 700 m² (`LARGE_MIN_SOURCE_AREA_M2`,
  the top of the urban size range, contract section 3.9), so step 1 draws
  sources from 700 m² up and the urban model covers everything below. The
  lead already thinks 500 m² may be too low. The decision is whether 700 m²
  stands, or the split moves to 500 m² or elsewhere.
- **The fixed geometry rules.** Each polygon carries fixed evacuated, inundated
  and imminent-risk polygons keyed by its wall state, so a realisation only
  decides whether it fails. The headscarp band (**T-44**), the fill wedge
  behind a failed wall, the runout length and the depth are to be researched
  and justified in the report.
- **Anchoring the rate setting.** What fixes the low, medium and high
  fragilities: Kingsbury's slope failure opportunity table, the Hancox (1997)
  intensity thresholds and the Port Hills 2011 cut, fill and wall failures are
  the candidates. They are in `urban-fragility-anchors.csv`, each class word
  read as a fraction failing by implementer judgement for the lead to review.
  The anchoring has not been run, so whether they agree with the 0.6
  dispersion placed is not yet known; its run sets that and its findings file
  records it.
- **The intensity measure per fragility.** PGV for the ground, as the landslide
  literature uses, against PGA for the published wall curves; each row names
  its own. As built every curve is evaluated on PGV, a PGA wall curve converted
  at the site's ratio of the step 3 PGV to the TS1170.5 PGA, for the lead to
  confirm.
- **Whether a failure drawn larger than its slope unit grows across the
  neighbouring units.** The units themselves are built (step 5); step 1 now
  places an ellipse that crosses unit boundaries, with region growing along
  the facet as a later phase of step 1.
- **Two step 9 rules the build chose where the contract was silent**
  (`s9_urban_slope_realisation_implementation_plan.md`): a wall on polygons at
  several scales takes one outcome by rank (superseded, failed, absorbed,
  standing), and where several large-model polygons reach an urban one the one
  sharing the most ground takes it. Both for the project lead to confirm. That
  a wall fails with any of its polygons is decided (lead, 2026-10-02).
- **Two step 7 rules the build chose where the contract's gave no usable
  answer** (`s7_urban_slope_polygons_implementation_plan.md`, phase 2): the
  crest and toe are the boundary segments facing uphill and downhill rather
  than the vertices above and below the centroid, and the inundated strip is
  at least long enough to spread the evacuated ground at its own depth, with a
  1 m floor, because the reach-angle rule measured from the crest gives no run
  past the toe on faces gentler than about 40 degrees. Both for the project
  lead to confirm.

### About the strength-based model

- **How greywacke strength is assigned spatially.** The strength values are
  compiled in `src/landloss/io/assets/wellington-greywacke-strength.csv` (c′,
  φ′, unit weight and Su by weathering grade, from published sources and T+T
  Wellington projects, plus GNS's own lab tests on Wellington fill and buried
  colluvium from SR2019/40 and SR2019/51), with depth-to-rock observations in
  `wellington-greywacke-depth-to-rock.csv`. Weathering grade is not mapped, so
  it is still to be decided how a cell gets a material, a strength and a
  failure depth. This is the input that model 7 cannot run without.

### An option not yet taken: build a weathering surface from the NZGD

Kingsbury's geology factor turns on the weathering grade of the greywacke, and
**no published layer maps that for Wellington**. The step currently assigns one
value to all bedrock hill country, which is defensible but flat.

The grade is recorded, though — borehole by borehole, logged to the NZ
Geotechnical Society field guidelines, in the **New Zealand Geotechnical
Database**. There are thousands of Wellington holes; the Semmens et al. (2011)
subsoil class work used 1,025 and the layer built from it cites 2,422. Depth to
highly-or-less weathered bedrock is a real, logged quantity: T+T's own Hornsey
Road work found it at 2.1 to 4.4 m along one hillside road.

So the option is to pull the logs, take depth to a given weathering grade as the
value, and interpolate it into a surface — the same shape of exercise as several
scripts in this repo already do. What makes it a decision rather than a task:

- The NZGD is not open. Access needs registration through MBIE, and the terms on
  redistributing anything derived need checking before the work starts.
- Point-to-surface interpolation over hill country is a modelling choice in its
  own right, and boreholes cluster where people build rather than where slopes
  fail.
- The prize is capped. The factor is weighted 2, so it spans 20 of 150 points,
  and the gap between the two classes that would realistically be in play is 8
  points. It would have to change a lot of cells to move a zone boundary.

Worth doing if the weathering distinction turns out to matter to the loss
answer; not worth doing speculatively.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
