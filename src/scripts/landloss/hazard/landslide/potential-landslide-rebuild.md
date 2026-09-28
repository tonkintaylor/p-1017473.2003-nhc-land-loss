# Potential rebuild of the landslide hazard model

What a probabilistic, Wellington-specific earthquake-induced landslide model
would need if it were built from its own inputs rather than extended from the
supplied ESNZ grid or ported from Kingsbury (1995). Written 25 September 2026,
updated 29 September 2026.

This is an options document. The build-new against extend-ESNZ decision is still
open in `status.md`, and nothing here has been agreed.

**Data expected:** a dataset of about 600 **rainfall-induced** landslides is to be
supplied. It is not an earthquake inventory and cannot calibrate the shaking
term of any model below. What it can and cannot be used for is set out under
"Using the Nowicki Jessee (2018) model" and item 8.

## What the model has to produce

Three requirements, and each of them rules out methods that would otherwise be
reasonable.

1. **Two polygon sets per realisation: source and runout.** NHC settles loss of
   support and debris inundation differently, so a susceptibility surface is not
   an answer — the model has to emit discrete failures with a start and an end.
   That rules out susceptibility-only approaches, which is most of the
   literature.
2. **Probabilistic, not deterministic.** The question NHC is asking is about a
   portfolio, so the output has to be a distribution over realisations, not a
   single expected value. That rules out a single scenario run.
3. **Strong shaking in an urban environment.** The failures that matter are on
   modified slopes a few metres high behind houses, not the rock avalanches that
   dominate published inventories. Almost every calibration dataset available is
   rural.

## What the literature actually says

A 2026 review in the *Indian Geotechnical Journal* covers 247 co-seismic
landslide susceptibility papers published 1994–2023 and sorts them into four
families. Ours would have to borrow from three of them.

### Qualitative and semi-quantitative scoring

Expert weightings summed into a rating. **This is exactly what Kingsbury (1995)
is**, and what `s2_slope_failure_susceptibility` now reimplements. Cheap,
transparent, and calibrated to nothing — it produces a relative ranking and
cannot produce a rate, a probability or a polygon. Useful as a sanity check on
pattern, useless as a model.

### Physically based: Newmark and its descendants

A yield acceleration from an infinite-slope factor of safety, run against a
ground motion to give a sliding displacement, then displacement mapped to
probability of failure.

- **Bray & Macedo (2019)** for shallow crustal sources, **Bray, Macedo &
  Travasarou (2018)** for subduction. Do not use one regression for both.
- **Macedo, Bray, Abrahamson & Travasarou (2018)** is the performance-based
  probabilistic version: it integrates over the full intensity measure hazard
  rather than taking one scenario, which is the framing our requirement 2 asks
  for.
- **Jibson (2007)** is explicitly regional screening only.
- The weakness is that it needs `c′`, `φ′`, unit weight and failure depth per
  material — none of which is mapped over Wellington. Every regional application
  assigns them by geological unit, which is an expert weighting wearing a
  physics costume.

### Statistical: logistic regression on inventories

The dominant family, and the one that actually produces probabilities.

- **Nowicki Jessee et al. (2018)** is the global reference: logistic regression
  over 23 inventories, predictors being PGV, slope, lithology, land cover and a
  compound topographic index for wetness, producing a relative hazard per cell
  and an areal coverage estimate. No New Zealand event trained it. See "Using
  the Nowicki Jessee (2018) model".
- **Massey et al. (2018, 2020)** found the Kaikōura distribution was well
  explained by geology, slope, distance to surface fault traces, PGV, local
  slope relief and elevation.
- **Singeisen et al. (2023)** trained separate coastal and inland models for
  Kaikōura after finding an order of magnitude more landslides on coastal
  hillslopes — a warning that a single model over mixed terrain hides a lot.
- **Rosser et al. (2021) is a rainfall model, not a seismic one.** It is a
  national-scale New Zealand logistic regression for the GeoNet rainfall-induced
  landslide forecast tool, trained on 20 storm inventories, with 24-hour rainfall
  and soil moisture as the triggers. It belongs here for two reasons, not as a
  coseismic method. First, its pilot was **Wellington City: about 16,000
  landslides mapped over 11 storms between 1939 and 2016**, with anthropogenic
  modification among the candidate predictors — the only urban Wellington
  inventory in this list. Second, it rests on Massey et al. (2019), the SLIDE
  (Wellington) report on rainfall *and earthquake* induced landslide hazard
  models, which has not been read yet and may already contain a Wellington
  earthquake model.
- **Kritikos, Robinson & Davies (2015)** is the one aimed squarely at our
  problem: regional coseismic landslide hazard *without* a historical inventory.
  Wellington has no earthquake-induced landslide inventory, so this or a
  transfer-learning approach is the only statistical route.

### Machine learning

Random forests, SVMs, neural networks. Consistently reported to out-perform
logistic regression on held-out data from the same event, and consistently
harder to transfer to a region with no inventory — which is our situation. Not
recommended here, for the reason that we would be training on Kaikōura and
predicting Wellington.

### The finding that most changes our current model

**Spatial clustering is real, geological, and kilometre-scale.** Rault et al.
(2019), analysing Northridge, Chi-Chi and Wenchuan, found coseismic landslides
cluster at ridge crests and slope toes in coherent patches of several tens of square kilometres, resolved at
about 7.8 km² macrocells. Crest clustering is specific to *seismic* triggering —
it does not appear in rainfall inventories. And the controls were **geological,
not seismic**: fault-zone rivers, stratigraphic alternations and bedding on
steep slopes, with ground motion parameters not exerting primary control.

Our current step samples every cell independently. `status.md` already calls
that the largest known error; this is the literature saying the correlation
length is kilometres and structural, not metres and random.

## The features, and how each could be constrained

Ordered roughly by how much they move the answer.

### 1. Ground motion — the trigger

The intensity measure the model is conditioned on.

- **In the repo now:** `landloss.io.nlm.get_nlm_scenario_pga_2500yr_site_class_5`
  gives a PGA grid for the 2500-year return period at site class 5, and
  `landloss.hazard.shaking.pga.beta_pga_realisation` already draws a realisation
  around it with `BETA_PGA_COV = 0.10`.
- **PGA is the wrong measure and we should say so.** Nowicki Jessee and Massey
  both use **PGV**, which correlates better with landsliding because it carries
  the energy of the pulse rather than its peak. Ask whether the NLM scenario
  tree can supply PGV as well; if not, a PGA-to-PGV conversion is a stated
  assumption.
- **Duration matters for a subduction scenario.** A Hikurangi M8.9 delivers its
  shaking over minutes. Arias intensity or significant duration captures that;
  PGA does not.
- **Site class.** The scenario is at one site class. Wellington's hill country is
  rock, its valleys soft sediment, and the landslide model only cares about the
  hills — so reading a grid conditioned on a single class needs checking against
  the site class actually under each slope.
- **Further afield:** NSHM 2022 for a full hazard curve rather than one return
  period, which is what a performance-based probabilistic treatment needs.

### 2. Slope angle and the scale it is measured at

The single strongest conditioning factor in every study in every family.

- **In the repo now:** `s3_multiscale_slope` builds DEM and slope at 10, 30 and
  100 m; `landloss.common.utils.terrain.slope_degrees` computes Horn slope at any
  resolution; `landloss.io.elevation` fetches LINZ 1 m tiles.
- **Constrain by choosing the support length deliberately and reporting the
  sensitivity.** A slope threshold is meaningless without the length it was
  measured over. The multiscale stack makes this a table rather than an
  assertion.
- **Fit the scale rather than assume it.** With the Kaikōura inventory in hand,
  the resolution at which slope best discriminates failed from unfailed ground
  can be *measured*, not chosen. That is a half-day exercise and it settles an
  argument.
- **A modified slope needs a finer scale than a natural one.** A 10 m-high cut
  face is invisible at 10 m and resolves at 1 m — already demonstrated in
  `s2_slope_failure_susceptibility`.

### 3. Anthropogenic modification — cut, fill and retaining

The literature that exists on this is thin, and it is the dominant mechanism for
*this* project. Christchurch 2011 recorded retaining wall and fill failure as a
distinct failure mode alongside rockfall; over 1,600 fill bodies are mapped in
central Wellington alone.

- **In the repo now:** `get_wcc_cut_areas` and `get_wcc_fill_areas` (453
  polygons, 6.3 km², Wellington City subdivision records only);
  `get_gns_slide_morphology` for the SLIDE linear features.
- **The SLIDE Genesis layer is the best source and has no reader yet.** Layer
  125309 on the T+T instance, and sub-layer 2 of the public WCC service, holds
  **2,987 cut slope polygons, 1,606 fill bodies and 1,058 modified terrain
  polygons** (679 of them subtype "residential", 29.2 km²), with a `DateOrigin`
  on each. That is an order of magnitude more than the WCC earthworks records.
  Write the reader.
- **Coverage is the binding constraint.** SLIDE reaches 38% of Wellington City
  and none of Porirua, Lower Hutt or Upper Hutt. Either chase equivalent records
  from those three councils, or detect cut and fill from LiDAR over the insured
  land extent — for which the multiscale slope stack is most of the input, since
  a cut face is steep at 1–2 m inside ground that is gentle at 20–30 m.
- **Fill behaves differently from cut and must stay separate.** A cut face loses
  support from below; a sidling fill slides on the contact it was placed on.
  Dynamic modelling of two Wellington anthropogenic fill slopes exists in the
  literature and is worth reading for parameter values.
- **Retaining walls remain a known dead end.** `data-sources.md` records that no
  private wall dataset exists. SLIDE's morphology lines include some walls; test
  what fraction.

### 4. Material and strength

- **In the repo now:** `get_slide_interpreted_materials` — 14 near-surface
  material classes at nominally 1:500, over 111 km²; `get_nlm_geomorphology` for
  the regional fallback; `get_nz_land_cover` for LCDB v6.0.
- **Weathering grade is not mapped anywhere for Wellington.** The option of
  building a surface from NZ Geotechnical Database borehole logs is recorded in
  `status.md`. Depth to highly-or-less weathered rock is 2.1–4.4 m on one
  Wellington hillside road, from T+T's own Hornsey Road investigation.
- **Constrain strength by back-analysis rather than by assignment.** T+T's
  Wellington ground models already carry `c′`, `φ′` and unit weight for residual
  soil, CW–HW greywacke and MW–SW greywacke, derived by back-analysing standing
  slopes. That is a better anchor than a literature table.
- **Slope height/angle precedent is a real T+T asset.** A regional database of
  slope height against angle for Wellington greywacke exists internally, built
  from ~600 km of WCC roading, 500+ EQC landslip assessments and large trial
  cuttings. If it survives, it constrains the stable envelope directly.

### 5. Structure and defects

The mechanism literature is emphatic that Wellington greywacke fails on
defects — persistent joints, bedding, sheared and crushed zones — not through
intact rock. Massey et al. (2022) tie Kaikōura rock slope failure mechanisms to
structure, and the clustering work found fault-zone and bedding control
dominating ground motion.

- **Distance to mapped fault traces** was a significant predictor in the
  Kaikōura models. The NZ Active Faults Database and the Porirua Fault Trace
  Study (LiDAR-remapped Ohariu/Pukerua/Moonshine) are both obtainable.
- **Aspect against bedding dip** is the physically right variable and is not
  mappable at regional scale here. Expect to carry it as an unmodelled source of
  variance, and say so.
- **A crushed-and-shattered proxy** from fault proximity is the practical
  substitute, and is already the reading behind Kingsbury's third geology class.

### 6. Topographic amplification and site response

Coseismic failures favour convex ridge crests and spurs, close to the reverse of
the rainfall pattern (Meunier, Hovius & Haines 2008), and crest clustering is
seismic-specific.

- **In the repo now:** `terrain.topographic_position` and `terrain.local_relief`
  give ridge/gully position and relief at any window.
- **Apply an amplification factor to the demand**, not to the susceptibility:
  ~1.3× on moderately steep slopes and ~1.5× above 60°, from Rathje & Bray
  (2001) and Ashford & Sitar (2002). Recent work quantifying amplification for
  the Gorkha earthquake is worth reading before fixing the numbers.
- **Constrain the factor against the Kaikōura inventory**: fit landslide density
  against topographic position at several window widths and see whether the
  published factors reproduce the observed crest bias.

### 7. Hydrology

- **In the repo now:** `get_gwd_median_depth` — NLM median groundwater depth,
  flat land only, about 20% of the study area, and silent over the hill country
  that matters.
- **Wetness proxies are what the literature actually uses.** Nowicki Jessee uses
  a compound topographic index, `ln(A / tan α)`, fitted at ~1 km. It is
  computable from the DEM we already fetch, but its coefficient only applies
  at that scale.
- **Antecedent conditions couple the hazards.** Wet ground lowers the yield
  acceleration, and shaking raises rainfall-triggered susceptibility for seasons
  afterwards. Out of scope per `project-scope.md`, but it belongs in the
  limitations.

### 8. Prior failure

Ground that has failed fails again, and Kingsbury puts existing landslides and
the ground beside them straight into the high zone.

- **SLIDE Genesis carries 494 relict landslides, 88 recent ones and 26
  rockfalls**, with source-area and debris-trail subtypes. Over the SLIDE
  footprint that is a usable inventory.
- **The expected ~600 rainfall-induced landslides add to this**, with one
  caveat. Prior failure is a trigger-independent predictor — failed ground is
  weak ground whatever failed it — so a rainfall inventory is legitimate input
  here, where it would not be for the shaking term. The GNS Wellington City
  storm inventory behind Rosser et al. (2021), about 16,000 landslides, is the
  larger version of the same thing and is worth asking GNS for.
- **The NLM's own "Landslide" landform class is not a substitute** — 7 polygons,
  1.94 km², two building outlines on it. Measured and ruled out.
- **Hancox, Dellow & Perrin (1994)** reviewed the historical record of
  earthquake-induced slope failure for this region and has not been located. It
  is the one document that would tell us what Wellington has actually done in
  past earthquakes.

### 9. Land cover and vegetation

Kingsbury explicitly excluded vegetation as unimportant in this region. Nowicki
Jessee includes land cover as a predictor and finds it significant globally,
with a spread of 1.4 in the logit between artificial surfaces (0.30) and
needleleaved forest (1.71) — see "Using the Nowicki Jessee (2018) model" for
what that does to the urban answer.

- **In the repo now:** `get_nz_land_cover`, LCDB v6.0 with six time steps.
- **Constrain the disagreement empirically** against Kaikōura rather than
  picking a side: fit landslide density by LCDB class and see whether it carries
  signal once slope is controlled for. In an urban catchment most of the study
  area is built-up anyway, so the prize is small.

### 10. How big each failure is

Converting a probability surface into polygons needs a size distribution, and
this is currently the weakest link in the existing step.

- **In the repo now:** `landloss.io.kaikoura` reads 31,623 source-area polygons
  and 26,559 debris trails (CC BY 4.0, cite GNS Science 2024);
  `landloss.hazard.landslide.geometry` holds `ALPHA = 0.074` and `GAMMA = 1.46`
  for volume from area.
- **Fit the distribution rather than calibrating one parameter to total area.**
  The current exponent of 1.19 was solved backwards to make areal coverage come
  out right, against published values of 2.1–2.5. Malamud et al. (2004) and the
  frequency-area literature say an inverse gamma or double Pareto with a
  rollover is the right shape, and a single power law stretched two decades
  below the cutoff cannot carry both a published slope and the right total area.
  The Kaikōura polygons make this a fit, not a guess.
- **Filter Kaikōura to greywacke** — around 70% of its landslides were in Pahau
  terrane greywacke, the same Torlesse rock.
- **Two populations, not one.** Kaikōura is natural rural slopes; our losses are
  expected on small engineered cuts and fills. Fit the modified-slope population
  separately, conditioned on the SLIDE cut and fill polygons, and state the
  split. This is the plan's own largest technical risk.

### 11. Where the debris goes

- **In the repo now:** the Kaikōura debris trails, paired with their source
  areas, which is exactly what a reach-angle relationship is fitted from.
- **Fit reach angle (H/L) against volume** from those pairs, conditioned on
  volume, rather than taking a literature range.
- **Route rather than translate.** The current step moves a circle downhill
  rigidly. Regional options run from a steepest-descent random walk — the
  `runoutSIM` approach, where the chance of moving to a neighbouring cell is
  driven by slope — through Flow-R style empirical spreading, to full
  Voellmy-rheology runout, which is far beyond what a portfolio model needs.
- **A random walk gives probabilistic runout for free**, which suits
  requirement 2: the output is a probability of inundation per cell rather than
  one deposit polygon.
- **Urban runout is short and obstructed.** Debris from a 3 m cut behind a house
  stops at the house. Nothing in the rural inventories captures that.

### 12. Spatial correlation between failures

- **This is the structural change the literature most clearly demands**, and the
  one the current model most clearly lacks.
- **Constrain the correlation length from Kaikōura directly.** The source
  polygons give an observed point pattern; a pair-correlation or semivariogram
  of landslide density against separation distance gives a length scale to
  simulate with.
- **Implement it as a correlated random field** over the probability surface —
  draw a spatially correlated Gaussian field at the fitted length scale and
  threshold it, rather than drawing each cell independently. That fixes the
  spread of the loss distribution, which is the quantity NHC is actually asking
  about.
- **Expect kilometres, not metres.** The published analysis resolved clustering
  at about 7.8 km² macrocells.

## Using the Nowicki Jessee (2018) model

The most promising statistical route, because it is the only model in this list
that is fitted to earthquake inventories, conditioned on ground motion, and
produces a quantity — areal coverage — that converts directly into a landslide
area budget. It is also what the current step's 1% coverage cross-check already
leans on informally.

The paper is in the repository at
`context/lit/landslide/nowicki_jessee_2018/nowicki-jessee-2018-global-seismic-landslide-model.pdf`.
Everything below is read from it; section, table and equation numbers are the
paper's.

### What it is

- **A logistic regression** (equation 8, coefficients in Table 3):

  `t = a + b·ln(PGV) + c·Slope + d·Lithology + e·LandCover + f·CTI + g·ln(PGV)·Slope`,
  `P = 1 / (1 + e^−t)`

  | Term | Coefficient | Input as fitted |
  | --- | --- | --- |
  | Intercept `a` | −6.30 | — |
  | ln(PGV) `b` | 1.65 | ShakeMap PGV in cm/s, ~1 km |
  | Slope `c` | 0.06 per degree | slope from GMTED2010 median elevation, 7.5 arc-sec (~250 m) |
  | CTI `f` | 0.03 | compound topographic index, 30 arc-sec (~1 km) |
  | ln(PGV) × Slope `g` | 0.01 | the interaction; the authors read it as a proxy for topographic amplification |
  | Lithology `d` | one per GLiM class | GLiM top-level classes, gridded at 250 m |
  | Land cover `e` | one per GlobCover class | GlobCover 2009, 300 m |

  The lithology and land cover classes that matter for Wellington:

  | Class | Coefficient |
  | --- | --- |
  | GLiM siliciclastic sedimentary | −1.92 |
  | GLiM metamorphics | −1.87 |
  | GLiM mixed sedimentary | −1.36 |
  | GLiM unconsolidated sediments | −3.22 |
  | GlobCover closed to open herbaceous vegetation (grassland) | 1.03 |
  | GlobCover closed to open shrubland | 0.79 |
  | GlobCover closed to open broadleaved evergreen forest | 0.68 |
  | GlobCover closed needleleaved evergreen forest (plantation pine) | 1.71 |
  | GlobCover artificial surfaces and associated areas | 0.30 |

  Classes absent from Table 3 are the reference categories. The complete table,
  with standard errors and confidence intervals, is in the paper.
- **P is a relative hazard, not a probability.** The model was fitted to a
  sample balanced 1:1 between landslide and non-landslide points (section
  2.1.1), which inflates P. The paper says so and supplies a correction.
- **The correction gives areal coverage** (section 5.5.3, equation 9): the
  fraction of a cell expected to be covered by landslides,

  `LP = exp(−7.592 + 5.237·P − 3.042·P² + 4.035·P³)`,

  fitted to the complete polygon inventories only. It runs from 0.05% at P = 0
  to **26% at P = 1**, so no cell can be more than about a quarter covered. This
  coverage figure is the number we would use; P on its own is not.
- **Training data** (Table 1): 23 inventories with a quality score of 2.0 or
  more, out of 36. **All four New Zealand events in the table — Cook Strait
  2013, Lake Grassmere 2013, Eketahuna 2014 and Wilberforce 2015 — scored 0.5
  to 0.6 and were used for testing only. Kaikōura 2016 is not in the database.**
  No New Zealand event trained the model.
- **Subduction and duration are its weak point.** Magnitude was tested as a
  proxy for duration and dropped (section 4.1). In the leave-one-event-out
  cross validation Tohoku, the only great subduction event, performed worst,
  and the authors conclude a magnitude term "may be needed … to accurately
  model larger events and account for duration of shaking" (section 5.5.2). A
  Hikurangi scenario is exactly that case.
- **Uncertainty is coefficient uncertainty only.** The prediction interval
  (section 3.4, equation 7) propagates the regression's standard errors, and
  the authors state it ignores input uncertainty, ShakeMap uncertainty
  included, and so underestimates the true spread.
- **It has already been run on Kaikōura, and it overpredicted.** Allstadt,
  Jibson et al. (2018) applied three global models, this one included, to
  Kaikōura. Their abstract reports **significant overprediction of landslides
  by all three**. The Nowicki Jessee paper adds that the result depended
  strongly on the ShakeMap version, and found the right area of highest hazard
  only once a finite rupture replaced the point source. This is the one New
  Zealand test of the model, it points the wrong way for an unadjusted
  application, and it is the first thing to read before we repeat the test.
- The USGS runs the model in its Ground Failure product with slopes below 5°
  excluded, probabilities below 0.002 dropped, and adjusted coefficients for
  unconsolidated sediments and mixed sedimentary rocks — a precedent for
  modifying the published coefficients.

### What the numbers look like for Wellington

Coverage `LP` for siliciclastic sedimentary rock with CTI = 5, from equations 8
and 9:

| PGV (cm/s) | Slope | Grassland | Artificial surfaces | Plantation pine |
| --- | --- | --- | --- | --- |
| 20 | 15° | 0.2% | 0.1% | 0.5% |
| 20 | 30° | 1.2% | 0.5% | 3.3% |
| 50 | 15° | 1.9% | 0.7% | 4.8% |
| 50 | 30° | 10.6% | 5.3% | 15.8% |
| 100 | 15° | 8.7% | 3.9% | 14.1% |
| 100 | 30° | 19.8% | 15.4% | 22.4% |

Three things follow.

1. **The "urban" class halves the answer.** At 50 cm/s on 30° slopes,
   artificial surfaces give half the coverage of grassland. The model says towns
   landslide less, because its training inventories are rural and towns sit on
   flatter, drier ground. That is the opposite of what the cut and fill
   literature leads us to expect for Wellington's hill suburbs.
2. **The greywacke crosswalk barely matters.** Siliciclastic sedimentary
   (−1.92) and metamorphic (−1.87) differ by 0.05 in the logit, so whichever
   class Torlesse greywacke is mapped to, the answer is the same. Only mixed
   sedimentary (−1.36) would move it noticeably.
3. **Slope is measured at ~250 m.** A 30° slope at 250 m is steep country. Our
   hill suburbs will mostly read 10–25° at that scale even where individual cut
   faces are near vertical.

### Three ways to use it, in increasing order of commitment

1. **As an independent check on total landslide area (do this regardless).**
   Run it at its native ~250 m over the study area for the scenario PGV and sum
   `LP × cell area`. This replaces the "order of 1%" figure in
   `s1_landslide_realisation_method.md` with a number computed for
   Wellington's actual slopes and shaking.
2. **As the coarse "how much" layer, downscaled for "where".** Treat each
   ~250 m cell's `LP × cell area` as a landslide area budget, and allocate that
   budget to fine cells inside it by a fine-scale susceptibility (1–10 m slope,
   SLIDE cut and fill, prior failure). The size distribution (item 10) turns
   the area into a number of polygons, the correlated random field (item 12)
   decides which cells fire together, and runout (item 11) follows unchanged.
   This keeps the model's calibration at the scale it was fitted at and puts
   our local data where it is strongest. **This is the recommended route.**
3. **As a template refitted to New Zealand.** Keep equation 8 and refit the
   coefficients on the Kaikōura inventory (filtered to greywacke), adding NZ
   predictors: distance to fault, local relief, modified ground. Given that no
   New Zealand event trained the published model, there is a real case for
   this. The costs are that it is one event, rural, and a different shaking
   style from a Hikurangi scenario — exactly the transfer problem the global
   model was built to avoid. If done, fit on a balanced sample as the paper
   did and refit equation 9 against the complete Kaikōura polygons, or the
   coverage conversion will not match the new coefficients.

### What we still need

1. **A PGV grid for the scenario.** The NLM scenario tree supplies PGA only
   (item 1). Ask whether PGV can be supplied; failing that, a PGA-to-PGV
   conversion is a stated assumption. It becomes the largest single input
   uncertainty, because ln(PGV) carries the biggest coefficient and the
   interaction term as well.
2. **Slope at the model's own resolution.** The multiscale stack
   (`s3_multiscale_slope`) stops at 100 m. It needs a ~250 m level computed the
   way the paper did — slope of the *median* elevation in each 7.5 arc-second
   cell, not a mean of fine slopes, which would come out much steeper.
3. **CTI at ~1 km**, computed from a DEM coarsened to 30 arc-seconds. Computed
   from the 1 m DEM it would have a different distribution and the 0.03
   coefficient would not apply.
4. **A lithology crosswalk** from the GNS geological map units to GLiM
   classes. Low stakes for greywacke (see above); it matters for the Tertiary
   and Quaternary cover sequences and the valley sediments.
5. **A land cover crosswalk** from LCDB v6.0 (`get_nz_land_cover`) to
   GlobCover 2009 classes. Higher stakes: the coefficients run from 0.30
   (artificial) to 1.71 (needleleaved forest).
6. **The Kaikōura PGV field** (the USGS ShakeMap for the 2016 event is public)
   and **Allstadt, Jibson et al. (2018)**, so the model can be run over the
   Kaikōura inventory already in `landloss.io.kaikoura` and scored against a
   published run. That is the one test of whether it transfers to New Zealand
   greywacke.

### What we need to modify

1. **Urban land cover.** Applied as published, the artificial-surfaces
   coefficient suppresses coverage in exactly the places our losses sit, and
   the model has no term for cut, fill or retaining. The fix is the
   two-population split in item 10: use the model for the natural-slope
   population, with urban cells scored as their pre-development cover
   (grassland or shrubland), and carry the modified-slope population
   separately, conditioned on SLIDE cut and fill. State the substitution.
2. **Resolution.** Every coefficient is tied to ~250 m slope and ~1 km CTI.
   Never apply them to fine inputs; downscale the output instead (route 2).
3. **Duration.** For the Hikurangi scenario the model has no duration term and
   underperformed on Tohoku. Either carry this as a stated limitation, or add a
   magnitude or significant-duration adjustment fitted to the subduction events
   in the wider inventory set, and say which.
4. **Lithology coefficients**, following the USGS precedent, if the Kaikōura
   test shows the greywacke class systematically over- or under-predicts.
5. **Spatial correlation.** Like every cell-by-cell model, it gives an expected
   coverage per cell and says nothing about which cells fail together. Our step
   has to add that (item 12) whichever route is taken.
6. **Probabilistic wrapping.** The model is conditional on one PGV field and
   its own intervals cover coefficient error only. Run it inside PGV
   realisations — the PGV analogue of `beta_pga_realisation` — so that ground
   motion uncertainty reaches the loss distribution.
7. **Topographic amplification is already in it.** The ln(PGV) × Slope term is
   the model's proxy for amplification, so applying the item 6 factor on top
   would count it twice. Pick one.

### What the rainfall inventory can and cannot do here

- **Cannot** fit or check the PGV term, the interaction term, or CTI. Rainfall
  and seismic failures sit in different places on the hillslope — rainfall in
  hollows and gullies, seismic toward crests (Meunier, Hovius & Haines 2008;
  Rault et al. 2019) — and CTI is exactly the variable that encodes that
  difference.
- **Can** inform the trigger-independent part of the fine-scale allocation in
  route 2: which modified slopes, materials and previously failed ground are
  weak. If its polygons are within the study area, it is also the only local
  evidence on the size of failures on small urban slopes, which is the
  modified-slope population the global model does not cover. Use it for size
  with care: rainfall failures are shallow and saturated, and their sizes are a
  plausible but unproven stand-in for seismic ones.

## Cross-cutting choices that have to be made once

1. **Mapping unit: grid cells or slope units.** Slope units — watersheds
   bounded by ridge and valley lines — are reported to perform slightly better
   and to be far more interpretable, because a landslide occupies a slope facet
   rather than a square. Reported gains are modest (one comparison: 83.2% against
   80.9% training accuracy) and several studies find the choice changes little.
   Slope units would also make "grow the source across the facet" natural, which
   is what the current circular footprint fails to do.
2. **Calibrate on Kaikōura, predict Wellington.** Every statistical route means
   training somewhere else. That is a transferability problem, and it argues for
   logistic regression with interpretable coefficients over a machine learning
   model whose fit cannot be inspected.
3. **What the probability is a probability of.** The same question that is
   already open about the supplied grid: per cell, per slope unit, per event, and
   conditional on what shaking. Settle it before anything is fitted.
4. **Validation with no local inventory.** The GWRC layer is a pattern check
   only and may be displayed but not derived from. Realistic checks are: areal
   coverage against Nowicki Jessee for the same shaking; size distribution and
   reach angles against Kaikōura; and the local expectation that most Wellington
   earthquake landslides are confined to a single property, with multi-property
   failures concentrated in gullies.

## What it would take

The honest summary is that items 1, 2, 10, 11 and 12 are all constrainable from
data already in this repository, and that they are the five that move the loss
answer most. Item 3 needs one reader written and a coverage decision. Items 4, 5
and 8 are where Wellington is genuinely data-poor, and where the model will have
to carry stated assumptions rather than measurements.

Nothing here argues that a rebuild is the right call. It argues that if one is
made, the Kaikōura inventory plus the SLIDE mapping plus the multiscale terrain
stack is enough to fit a defensible model, and that the two things that would
most improve the *current* model — a fitted size distribution and spatial
correlation — are worth doing either way.

## Sources

Each entry says where its PDF is: tracked in the repository under
`context/lit/landslide/`, parked in `temp/reference/landslide/` (gitignored;
provenance in `SOURCES.md` there), or "not in temp", meaning it was not
obtained, with the reason.

- Mapping co-seismic landslide susceptibility: an overview of current and
  emerging methods, *Indian Geotechnical Journal* (2026) — the 247-paper review.
  **Not in temp** — download not attempted.
- Nowicki Jessee, M.A., Hamburger, M.W., Allstadt, K., Wald, D.J., Robeson,
  S.M., Tanyaş, H., Hearne, M. & Thompson, E.M. (2018). A global empirical
  model for near-real-time assessment of seismically induced landslides. *JGR
  Earth Surface* 123, 1835–1859.
  <https://doi.org/10.1029/2017JF004494>
  **In the repository** (tracked, not temp) —
  `context/lit/landslide/nowicki_jessee_2018/nowicki-jessee-2018-global-seismic-landslide-model.pdf`.
  The supporting information (Tables S1–S3) is not included. Operational implementation notes are from the USGS Ground Failure background
  page, <https://earthquake.usgs.gov/data/ground-failure/background.php>.
- Allstadt, K.E., Jibson, R.W., Thompson, E.M., Massey, C.I., Wald, D.J.,
  Godt, J.W. & Rengers, F.K. (2018). Improving near-real-time coseismic
  landslide models: lessons learned from the 2016 Kaikōura, New Zealand,
  earthquake. *BSSA* 108(3B), 1649–1664.
  <https://pubs.geoscienceworld.org/ssa/bssa/article/108/3B/1649/529880/Improving-Near-Real-Time-Coseismic-Landslide>
  The Kaikōura run of the global models; only the abstract has been read.
  **Not in temp** — GeoScienceWorld refuses scripted downloads; save by hand.
- Rosser, B., Massey, C., Lukovic, B., Dellow, S. & Hill, M. (2021).
  Development of a rainfall-induced landslide forecast tool for New Zealand. In
  *Understanding and Reducing Landslide Disaster Risk*, Springer, 273–277.
  **Rainfall-triggered, not seismic.**
  <https://doi.org/10.1007/978-3-030-60311-3_32>
  **In temp** — `rosser-2021-rainfall-induced-landslide-forecast-tool-nz.pdf`.
- Massey, C., et al. (2019). SLIDE (Wellington): rainfall induced and earthquake
  induced landslide hazard models. GNS Science Report SR2019/37. **Not in temp**
  — not located online; request from GNS. Possibly the most directly relevant
  document on this list.
- Massey, C., et al. (2018, 2020) on the Kaikōura landslide distribution and
  volumes; Massey et al. (2022) on rock slope failure mechanisms. **Not in
  temp.**
- Singeisen, C., et al. (2023). Coastal earthquake-induced landslide
  susceptibility during the 2016 Kaikōura earthquake. *NHESS* 23, 2987.
  <https://nhess.copernicus.org/articles/23/2987/2023/>
  **In temp** — `singeisen-2023-coastal-eq-landslide-susceptibility-kaikoura.pdf`.
- Kritikos, T., Robinson, T.R. & Davies, T.R.H. (2015). Regional coseismic
  landslide hazard assessment without historical landslide inventories.
  *JGR Earth Surface*.
  <https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/2014JF003224>
  **Not in temp** — Wiley refuses scripted downloads; save by hand.
- Rault, C., Robert, A., Marc, O., Hovius, N. & Meunier, P. (2019). Seismic and
  geologic controls on spatial clustering of landslides in three large
  earthquakes. *Earth Surface Dynamics* 7, 829.
  <https://esurf.copernicus.org/articles/7/829/2019/>
  **In temp** — `rault-2019-spatial-clustering-landslides-three-earthquakes.pdf`.
- Meunier, P., Hovius, N. & Haines, J.A. (2008) on topographic site effects and
  the location of earthquake-induced landslides. **Not in temp.**
- Bray, J.D. & Macedo, J. (2019). Procedure for estimating shear-induced seismic
  slope displacement for shallow crustal earthquakes. *JGGE* 145(12). **Not in
  temp** — download not attempted.
- Macedo, J., Bray, J., Abrahamson, N. & Travasarou, T. (2018).
  Performance-based probabilistic seismic slope displacement procedure.
  *Earthquake Spectra* 34(2), 673. **Not in temp** — download not attempted.
- Malamud, B.D., Turcotte, D.L., Guzzetti, F. & Reichenbach, P. (2004).
  Landslide inventories and their statistical properties. *ESPL*. **Not in
  temp.**
- Tanyaş, H., et al. (2019). Factors controlling landslide frequency–area
  distributions. *ESPL*. <https://onlinelibrary.wiley.com/doi/full/10.1002/esp.4543>
  **Not in temp.**
- Goetz, J. (2026). runoutSIM v1.0: an R package for regionally simulating
  landslide runout and connectivity using random walks. *GMD* 19, 5709.
  <https://gmd.copernicus.org/articles/19/5709/2026/>
  **In temp** — `goetz-2026-runoutsim-random-walk-runout.pdf`.
- Geomechanical characterisation and dynamic numerical modelling of two
  anthropogenic fill slopes. *Engineering Geology*.
  <https://www.sciencedirect.com/science/article/abs/pii/S0013795220318779>
  **Not in temp** — download not attempted.
- Landslides caused by the 22 February 2011 Christchurch earthquake. *BNZSEE*.
  <https://bulletin.nzsee.org.nz/index.php/bnzsee/article/view/219>
  **Not in temp.**
- Comparison of slope units and grid cells as mapping units. *Earth Science
  Informatics* (2018).
  <https://link.springer.com/article/10.1007/s12145-018-0335-9>
  **Not in temp** — download not attempted.
- Regional and method context also from the
  `seismic-landslide-hazard-wellington` skill in this repository, and the method
  extraction in
  `.agents/plans/rebuilding-gwrc-slope-failure-susceptibility.md`.
