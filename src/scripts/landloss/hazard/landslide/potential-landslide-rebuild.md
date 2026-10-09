# Potential rebuild of the landslide hazard model

What a probabilistic, Wellington-specific earthquake-induced landslide model
would need if it were built from its own inputs rather than extended from the
supplied ESNZ grid or ported from Kingsbury (1995). Written 25 September 2026,
updated 29 September 2026.

This is an options document. The build-new against extend-ESNZ decision is still
open in `status.md`. The direction now proposed by the project lead is a
portfolio of several models split at a size threshold — see "A portfolio of
models: large and small landslides" — with extend-ESNZ as one member of it
(model 4) rather than the only route. Three of the large-landslide models come
from the literature: Nowicki Jessee (2018), Kritikos et al. (2015) and Hancox
et al. (1997). The threshold and the combination scheme are not yet agreed.

**Data collected:** the dataset of about 600 **rainfall-induced** landslides is
the NHC claim reports, now collected (the project lead, 2026-10-02); their
extraction is **T-50**. It is not an earthquake inventory and cannot calibrate the shaking
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
is**, and what `s7_slope_failure_susceptibility` now reimplements. Cheap,
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
  the energy of the pulse rather than its peak. The scenario's Sa(1.0 s)
  (`Sa_T1`) is available, and PGV is derived from it with a stated relation.
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

- **In the repo now:** ground step 1 (`ground/steps/s1_terrain`) builds DEM and slope at 10, 30 and
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
  `s7_slope_failure_susceptibility`.

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
  slopes. That is a better anchor than a literature table. **Compiled** in
  `src/landloss/io/assets/wellington-greywacke-strength.csv`, with depth to
  rock in `wellington-greywacke-depth-to-rock.csv` (see the assets README).
  Most of the values turn out to be design parameters for individual slopes,
  some back-analysed, rather than one regional ground model; the published
  anchors T+T reports quote are O'Riley et al. (2006) and Pender (1977).
  GNS's own drained shear tests on Wellington fill and buried colluvium
  (SR2019/40, SR2019/51) were added on 1 October 2026: fill φ′ about 38–46°
  with little cohesion, colluvium φ′ 24–28° with c′ 18–28 kPa.
  How they are assigned spatially is an open decision in `status.md`.
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
- **The ~600 rainfall-induced landslides of the NHC claim reports (collected)
  add to this**, with one
  caveat. Prior failure is a trigger-independent predictor — failed ground is
  weak ground whatever failed it — so a rainfall inventory is legitimate input
  here, where it would not be for the shaking term. The GNS Wellington City
  storm inventory behind Rosser et al. (2021), about 16,000 landslides, is the
  larger version of the same thing and is worth asking GNS for.
- **The NLM's own "Landslide" landform class is not a substitute** — 7 polygons,
  1.94 km², two building outlines on it. Measured and ruled out.
- **Hancox, Dellow & Perrin (1994)** reviewed the historical record of
  earthquake-induced slope failure for this region (GNS Client Report 353905,
  for Wellington Regional Council). It is not online and has to be requested
  from Greater Wellington or GNS. It is the one document that would tell us what
  Wellington has actually done in past earthquakes, and so the only local check
  on any model in the portfolio. Its successors are in `context/lit/landslide/`
  and are model 3 of the portfolio. Hancox, Perrin & Dellow (1997), GNS Client
  Report 43601B for the EQC Research Foundation, covers landsliding in 22 NZ
  earthquakes, including 1855 Wairarapa, "MM9 in Wellington; widespread
  landsliding in Wellington region". Hancox, Perrin & Dellow (2002), *BNZSEE*
  35(2), and Hancox (2010), *Australian Geomechanics* 45(3), summarise it. They
  give the NZ thresholds: landsliding from about M 5 and MM6, significant
  landsliding at M 6+ and MM7–8, and MM7 in the Wellington Region.

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

## A portfolio of models: large and small landslides

Rather than one model, build several, split by landslide size. Some are
alternatives to each other, one is a complement to all of them.

### The split

- **Large landslides are green-field failures.** They are natural-slope
  failures of the kind every coseismic inventory records. The models for them
  are trained on rural inventories and **do not consider cut, fill or
  retaining**. They still run over urban hillsides, because a large failure
  through a hill suburb starts in the natural slope beneath it. Land cover is
  scored as pre-development, as set out under "What we need to modify".
- **Small landslides are urban failures**: modified slopes, the few-metre cut
  behind a house, a sidling fill, a failed wall. There is no green-field
  inventory for them, and they are the population the current step's own
  plan already calls its largest technical risk (item 10).
- **Threshold: 500 m² of source area**, with 1,000 m² as the sensitivity case.
  The large/small split is agreed by the project lead (30 September 2026); the
  500 m² value is the working threshold. The reasons:
  1. It is where the large-model evidence stops. The GNS Kaikōura inventory is
     considered complete above 500 m² (Allstadt et al. 2018), and
     frequency–area distributions roll over below a few hundred square metres
     (Malamud et al. 2004). Below the threshold no green-field inventory
     constrains anything, so the urban model has to carry that range anyway.
  2. It is property scale. A Wellington residential section is of the order
     of 500–800 m², and the local expectation is that most earthquake
     landslides stay within one property (see "Cross-cutting choices").
  3. Rosser et al. (2021) note that New Zealand storm landslides are mostly
     under 1,000 m², which gives the urban model a local size reference either
     side of the threshold.

  The threshold is a judgement and should be recorded as one. The results
  should show how the loss moves between the two populations as it changes.
- **No double counting across the line.** Every large model's areal coverage
  includes failures below the threshold, and runout as well. Before adding the
  small model, remove the share of large-model area that comes from failures
  under the threshold. That share can be measured directly: the fraction of
  Kaikōura source and trail area in polygons of at least 500 m², from
  `landloss.io.kaikoura`. Runout is split off as under "What we need to
  modify".

### The models

Three models from the literature for large landslides, a possible fourth from
GNS, a bespoke refit, one urban model for small landslides, and a proposed
strength-based model after Godt et al. (2008). The papers are
in `context/lit/landslide/`.

1. **Large, literature — USGS / Nowicki Jessee (2018).** The landslide model
   the USGS runs in its Ground Failure product: a global logistic regression
   giving areal coverage. **Rebuilt** as
   `landloss.hazard.landslide.models.nowicki_2018` and checked against the USGS
   at Loma Prieta. See "Using the Nowicki Jessee (2018) model" and "The USGS
   software". Paper: `nowicki_jessee_2018/`.
2. **Large, literature — Kritikos, Robinson & Davies (2015).** A University of
   Canterbury model, built for regions with no landslide inventory; the paper
   names the Southern Alps as the case it is for. Fuzzy logic: memberships for
   shaking intensity (MMI, from scenario isoseismals), slope and other
   topographic factors, distance to active faults and distance to streams, fitted
   on Northridge and Wenchuan and tested blind on Chi-Chi. It needs only a DEM, an
   active fault map and isoseismals, all of which exist for Wellington; Allstadt
   et al. (2018) could not run it globally only for want of a global fault map.
   Its output is a relative probability, not coverage, so it needs a map from
   relative hazard to coverage, taken from its own training events ("How they
   combine"). Paper: `kritikos_2015/` (summary; the PDF is held
   outside git). **Build plan:**
   `.agents/plans/building-kritikos-2015-landslide-model.md`.
3. **Large, literature — Hancox, Perrin & Dellow (1997, 2002; Hancox 2010).** The
   New Zealand empirical relationships from 22 historical earthquakes. Not a
   susceptibility map in itself, but the only New Zealand-derived constraints on
   where and how much, and so used two ways:
   - **As a model:** the area affected by landsliding from magnitude,
     log10 A = 0.96 M − 3.7 (A in km²), the maximum distance from the source for
     each landslide size class, and the intensity thresholds (landsliding from
     MM6; **MM7 in the Wellington Region**, attributed to the better performance
     of greywacke). Landslides are distributed within that envelope by slope,
     using Hancox (2010) Table 2's share of historical failures by slope class.
   - **As a test of the others**, not a calibration of them ("How they
     combine"). The relationship constrains the **extent** of landsliding,
     not its **amount**. A is the area within which landslides occurred — about 20,000
     km² for 1855 Wairarapa — not the area that slid, which is a small fraction
     of it. So it cannot calibrate total coverage on its own. It can calibrate
     the footprint: coverage outside the area affected, or beyond the maximum
     distance for the magnitude, should be close to zero. That is exactly the
     error Allstadt et al. found in model 1, whose hazard did not decay quickly
     enough away from the rupture. For the amount, it needs pairing with an
     event where both are known. At Kaikōura, about 20 km² slid (Allstadt et al.)
     within an affected area of the order of 10,000 km². A ratio of that kind,
     applied to A(M), gives an independent New Zealand estimate of total area to
     set beside Marc et al. (2016).

   Papers: `hancox_1997/` (with a searchable markdown version of the scanned
   report), `hancox_2002/`, `hancox_2010/`. **Build plan, including model 3's
   amount from Marc et al. (2016) and the Hancox and Marc tests reported for
   every large model:** `.agents/plans/building-hancox-landslide-model-and-calibration.md`.
4. **Large, possible — GNS / ESNZ.** The supplied ESNZ grid is already
   confirmed to be the GNS slope failure model held in PRUE (`status.md`, L-08).
   Its 32 m cells match the national GNS grid in Rosser et al. (2021), which is
   consistent with it coming from the same GNS framework. The GNS reports behind
   it should settle the open questions in `status.md`: what a cell's
   probability is a probability of, and what shaking it is conditioned on. To
   obtain and read:
   - Massey et al. (2019), **SR2019/37**, SLIDE (Wellington): rainfall induced
     and earthquake induced landslide hazard models. The most likely source of
     the ESNZ grid's method.
   - SLIDE (Wellington): geomorphological characterisation of the Wellington
     urban area, **SR2019/28**.
   - Massey et al., SLIDE (Wellington): vulnerability of dwellings to
     landslides, **SR2018/27**. Not a hazard model, but directly relevant to
     the vulnerability module.

   The GNS model is fitted on Wellington data, so it may not be purely
   green-field. Check whether it already carries modified ground before placing
   it on the large side of the line.
5. **Large, bespoke — recalibrated with new inputs.** Model 1's structure
   refitted on New Zealand data (route 3 below), using modern and local inputs
   at their proper resolution. That means the 1 m LiDAR slope stack, a geology
   split with real strength contrast, distance to rupture, and the
   the ground step 1 (`ground/steps/s1_terrain`) terrain metrics. It is calibrated to the ~20 km²
   Kaikōura total, with its footprint checked against model 3's envelope. The
   training data would be the GNS Kaikōura inventory, plus selected events from
   the USGS Ground Failure Database (Schmitt et al. 2017, below; read by
   `landloss.io.gfdb`) — for example
   greywacke-like terrain, or the subduction events needed for Hikurangi.
6. **Small — urban-scale bespoke model.** Failures below the threshold on
   modified and natural ground inside the insured land extent. Its inputs:
   - SLIDE cut and fill (item 3), prior failure (item 8) and fine-scale slope
     (item 2).
   - Susceptibility informed by the ~600 rainfall-induced landslides of the
     NHC claim reports (collected)
     and, if it can be obtained, the GNS Wellington City storm inventory of
     about 16,000 — for trigger-independent predictors only (see "What the
     rainfall inventory can and cannot do here").
   - Placement, sizing and runout through the existing
     `s3_landslide_realisation` machinery, with its size distribution capped
     at the threshold.

7. **Large, proposed — strength-based coverage after Godt et al. (2008).**
   Godt's model with its displacement step removed, so that coverage comes
   straight from strength against shaking. It is the one model in the portfolio
   where geology enters as strength, so greywacke is represented by its `c′`
   and `φ′`, not by a class coefficient. Paper: `godt_2008/`.
   - **Godt et al. as published.** An infinite-slope factor of safety `FS` for
     a constant 2.4 m slide thickness, with no groundwater, and cohesion and
     friction assigned by geological unit from a modified Nadim et al. (2006)
     susceptibility ranking. The critical acceleration is
     `ac = (FS − 1) g sin α`. It is compared with PGA through Jibson's (2007)
     displacement regression, and a displacement of more than 5 cm counts as
     failure. This is evaluated for each of a set of slope quantiles
     (1st to 99th) within each ~1 km cell, computed from 90 m SRTM (Verdin et
     al. 2007), so a cell's coverage is the share of its slope distribution
     that fails.
   - **The modification.** Drop the displacement estimate. A part of the slope
     distribution fails where the shaking exceeds its critical acceleration,
     `PGA > ac`, and coverage is the share of the cell's slope distribution
     for which that holds. The strength parameters stay central, which is the
     point of the model: `c′`, `φ′` and unit weight by material, from T+T's
     back-analysed Wellington values for residual soil, CW–HW and MW–SW
     greywacke (item 4), and slide thickness by material or weathering depth
     rather than a flat 2.4 m.
   - **With our data.** Take the slope distribution inside each model cell from
     the 1–10 m LiDAR stack (ground step 1, `ground/steps/s1_terrain`) rather than seven quantiles
     of 90 m slope, and the material from the SLIDE interpreted materials and
     the GNS geological map. At 1 m the distribution includes cut faces, so
     the same construction could reach towards the small modified-slope
     population (model 6) as well.
   - **What the modification costs.** Without a displacement model, `PGA > ac`
     is a pseudo-static criterion. It takes no account of how long the demand
     stays above `ac`, which is what Newmark displacement measures, so a brief
     high-frequency peak counts as failure. That makes it prone to overpredict,
     the same weakness Allstadt et al. found in the published model. Carry the
     demand as an effective fraction of PGA, set from published practice
     (0.65 PGA for a whole slope; "What the literature review says about the
     route", item 6), not fitted to Marc or Kaikōura, which are its tests
     ("How they combine").
   - **A reference to check against.** The published model is `godt_2008` in
     the USGS `groundfailure` package, and its Loma Prieta test data include a
     `godt_2008.grd` target. So the unmodified model can be rebuilt and checked
     the way model 1 was, before the modification is made.

Other published models considered, and not in the portfolio:

- **Nowicki et al. (2014).** The predecessor of model 1, superseded by it.

Used as a test of every model, and as model 3's amount, rather than as a model:

- **Marc et al. (2016)**, for the amount of landsliding. A seismologically
  derived expression for the total area and total volume of landslides an
  earthquake triggers. It is built from scaling relationships between landslide
  spatial density, ground acceleration, fault length, source (asperity) depth,
  and seismic moment, with a landscape steepness term and a near-constant
  threshold acceleration. It gives one number per earthquake and no spatial
  pattern. Paper: `marc_2016/`.
  - **Performance.** Tested on 40 shallow continental earthquakes, it predicts
    total volume to within a factor of 2 for 63% of them (R² = 0.76), and total
    area to within a factor of 2 for 11 of 17 (R² = 0.73). Low landscape
    steepness causes systematic overprediction, and the area prediction is also
    sensitive to the size-frequency distribution and possibly to shaking
    duration.
  - **Use** (revised by the lead, 2026-10-02, "How they combine"). It sets the
    amount for model 3 only, whose own method has none. For every other model
    its total for the scenario is reported beside that model's own total as a
    test, and no model is scaled to it. Kaikōura
    post-dates the paper, so it is also an out-of-sample test of Marc itself:
    run the expression for Kaikōura and compare it with the ~20 km² observed.
  - **Limit.** The calibration set is shallow continental earthquakes. The two
    subduction events it shows, Tohoku and Pisco, are plotted only for
    reference and are not part of the fit. It suits a Wellington Fault
    scenario; for a Hikurangi interface scenario it has to be used with that
    caution stated.

### The forward-use scenario

The study works at a return period, not a scenario earthquake. Where a model or
a calibration needs a magnitude or a source distance, every site in the study
area is taken to be **25 km from an Mw 8.1 event** (`BETA_SCENARIO_MW`,
`BETA_SITE_DISTANCE_KM`). That is the modal event in the NSHM deaggregation of
Wellington PGA at Vs30 = 400 m/s, per the project lead; `status.md` records it
with its source for the report.

- **Calibration does not need it.** Calibration runs on real events (Kaikōura,
  GFDB events) with their real geometry.
- **Forward use needs it only for magnitude- and distance-dependent terms.** Under
  it, Hancox's area affected (about 11,900 km² at Mw 8.1, an equivalent radius
  of about 62 km) contains every site, and every landslide size class is possible
  at 25 km. So the extent constraint shapes the models on real events but does
  not clip the Wellington answer.
- **It describes weaker shaking than the study's.** Marc's own shaking term gives
  about 0.17 g at 25 km from an Mw 8.1, and typical ground-motion models give a
  PGA of the order of 0.2–0.4 g, against the study's 2500-year TS1170.5 PGA of
  about 1 g. So shaking-dependent terms read the study's own shaking, not the
  scenario. The model 3 plan sets out how the Wellington amount is then fixed.

### How they combine

**The purpose of the portfolio (the project lead, 2026-10-02).** Each large
model is a valid, independent estimate, made with **its own published
calibration**. The spread between them is the epistemic uncertainty in the
large-landslide loss. If every model were scaled to the same Kaikōura total
(or the same Marc total), they would all give much the same answer whatever
their structure, and the portfolio would measure nothing. So:

- **No model is rescaled to a common target.** Kaikōura, Marc et al. (2016)
  and the Hancox extent are **tests** reported beside each model's result,
  not targets each model is forced onto.
- **A model is calibrated only where its own method leaves a gap**, and then
  from its own source, never from the shared test events. The one exception
  is model 5, the bespoke refit, which is fitted on New Zealand data by
  definition, and so is the one model that cannot be tested on Kaikōura.
- **Models 1–5 and 7 are alternatives** for the large population, carried as
  weighted branches of a logic tree.
- **Model 6 complements whichever large model is used.** The loss per
  realisation is the large-model loss plus the model 6 loss, and landslide step 6
  removes the overlap.
- The same PGV realisations and spatial correlation (item 12) drive every
  model in a realisation, so the populations are shaken by the same
  earthquake.

**Each model's own calibration, and how it becomes polygons.** Every model's
output is an expected landslide area per cell (a coverage). The shared
realisation machinery of landslide step 3 turns it into polygons in the same
way for all of them. It sums coverage × cell area over each slope unit, less
the urban share, draws a Poisson count for the unit with mean that area over
the mean size, draws each size from the bounded power law (700 to 35,000 m²),
and stamps an ellipse at a crest-weighted seed, with runout below it. No model
emits polygons itself, and no model's cells are failures in themselves.

| Model | What it outputs | Where its amount comes from (its own calibration) | Tests reported beside it |
| --- | --- | --- | --- |
| 4. ESNZ grid (landslide step 3) | A probability per 32 m cell, already conditioned on one shaking level (the file's, read from its name as 2 g) | The file itself: triggering and amount are in it. The only open step is what a probability means: if a cell fails where its centroid lies in a source, as in GNS's Kaikōura model (`massey2018-F29`), the probability is the coverage and the source fraction is 1. It is an interpretation for the supplier to confirm, not a calibration | Kaikōura, Marc, Hancox extent |
| 1. Nowicki Jessee (2018) | A probability per ~250 m cell, turned to coverage by the paper's equation 9 | The published global fit (23 inventories), as the USGS runs it in its Ground Failure product: slopes below 5° excluded, probabilities below 0.002 dropped, the adjusted coefficients for unconsolidated sediments and mixed sedimentary rock. No rescaling. Allstadt et al. found it overpredicted Kaikōura; that is reported as its test result, not removed | Kaikōura, Marc, Hancox extent |
| 2. Kritikos et al. (2015) | A relative hazard H, 0 to 1, per 60 m cell, from the published average memberships and γ = 0.9; fully specified by the paper | H is relative ("an order-of-magnitude estimate only"), so it needs a map from H to coverage, which the paper does not give. Take that map from **its own training events**, the Northridge and Wenchuan inventories (binned observed coverage against H on each event), not from Kaikōura | Kaikōura, Marc, Hancox extent |
| 3. Hancox et al. (1997) | Coverage spread over the slope classes of Hancox (2010) Table 2, inside the MM threshold and the extent | **Marc et al. (2016)** (the lead, 2026-10-02): Marc's total for the scenario earthquake, apportioned over the Hancox area affected, and the study area takes its share. Under the Hikurangi interface scenario Marc depends almost wholly on the interface depth (model 3 plan), so it uses the real depth (option A of that plan) | Kaikōura |
| 7. Godt et al. (2008) | Coverage per cell from the share of the slope distribution whose critical acceleration is exceeded | The published model as the USGS runs it (strengths by unit, 2.4 m thickness, Jibson's displacement, 5 cm threshold) as the base. The strength-only variant takes its demand from published practice, 0.65 PGA for a whole slope (`brabhaharan2018-F07`, `sr2019-051-F34`), not from a fit | Kaikōura, Marc, Hancox extent |
| 5. Bespoke refit | Model 1's structure, refitted | Fitted on New Zealand data (Kaikōura, GFDB events) by design | Marc and Hancox only, since Kaikōura trained it |

### What the literature review says about the route (2026-10-02)

Part B of the second review (`temp/handoff-remaining-review.md`) read the
route choice against `temp/gns_review/` (finding ids in backticks). The
review set holds none of the papers behind models 1, 2 and 7: Nowicki Jessee,
Kritikos and Godt are in `context/lit/landslide/` but were not part of it. So
it cannot rank those three against each other. It does bear on the ESNZ
model, on the calibrations and on the scenario. Every point is a **proposal
for the lead**.

1. **The ESNZ grid (model 4) under-reads Wellington, by GNS's own account.**
   - GNS's expert assessment is that the EIL model, not trained for this
     area, under-estimates landslide hazard in the Wellington region
     (`sr2025-001-F05`, checked against the page).
   - Its 2,475-year map is mostly Very low or Low over the hills of the four
     councils, with scattered Moderate (`sr2025-001-F08`, checked against the
     map), where the slope-angle map reads Very high (`F09`).
   - The model is Massey, Lukovic and Dellow (2022) (`sr2025-001-F20`), and
     the report reproduces none of its inputs.
   - The Kaikōura model it grew from counts a 32 m cell as failed where its
     centroid lies in a source area (`massey2018-F29`). Read that way, a
     cell's probability is already a coverage. This bears directly on landslide
     step 3's `BETA_SOURCE_AREA_FRACTION` (landslide step 3 plan, "Literature review of the
     placeholders").

   **Proposal:** keep ESNZ as one member of the portfolio, not as the base,
   and put the centroid question to the supplier with the two already open.
2. **Kaikōura is a low case for the amount.**
   - Its roughly 10,000 landslides are two to six times fewer than
     magnitude-only relations predict for Mw 7.8 (`massey2018-F06`).
   - It produced fewer landslides over 10,000 m² than Murchison, which the
     authors put down to offshore rupture, topography and moment spread over
     more than 20 faults (`F07`, `F08`).
   - It struck in November; winter earthquakes in New Zealand affect 2 to 2.5
     times the area of summer ones [dellow_hancox_2006] (`dellow2006-F05`,
     our digitising).

   **So Kaikōura is a test, not a target** ("How they combine", the lead's
   decision of 2026-10-02): a model that reads below it is not wrong on that
   account. Report Murchison (1929, wet, `dellow2006-F22`, `F24`) and
   Inangahua (1968, `sr2015-016-F12`) beside it as the high cases.
3. **The Hancox extent is a minimum.** The June 1942 landsliding was
   reported over about 6,500 km², against the 3,700 km² the 1997 national
   study used for that event, so the affected-area relationships are likely
   minima [downes_2001] (`downes2001-F21`, `F22`). Under the scenario it
   clips nothing in the study area anyway (the model 3 plan), so this changes
   the Kaikōura test, not the Wellington answer.
4. **Subduction events landslide less than their magnitude suggests.** The
   2001 Peru, 2010 Maule and 2011 Tohoku earthquakes caused little
   landsliding, two of them in dry seasons (`brabhaharan2018-F36`). The 2009
   Mw 7.6 Dusky Sound interface event, 30 km deep, caused small shallow
   landsliding over about 5,600 km², less than the Mw 7.2 2003 Fiordland
   event's 10,000 km² [brabhaharan_2018] (`sr2015-016-F22`, checked against
   the page). This supports the model 3 plan's use of the study's own
   shaking rather than a magnitude-driven total, because the low counts
   follow the shaking at the surface, not the magnitude. Nothing in the set
   quantifies the effect of the longer duration of interface shaking
   (RQ-18 found no such evidence), so duration stays a stated limitation.
5. **The shaking threshold.** "Significant landsliding likely in susceptible
   areas" first appears at MM8 in the revised New Zealand MM scale
   [dowrick_2008] (`dowrick2008-F05`), one level above the MM7 that model 3
   takes for the Wellington Region from Hancox et al. (1997). The 2013 Cook
   Strait and Lake Grassmere earthquakes were judged threshold events for
   Wellington (`sr2013-042-F07`, `vandissen2013-F05`). At the study's demand
   (MMI 10 and above everywhere at 2,475 years, about 0.8 g or more,
   `sr2025-001-F13`) the threshold does not bind, so it changes the Kaikōura
   calibration of model 3, not the forward run.
6. **Model 7, the strength-based model, has two published anchors in the
   set.**
   - Greywacke rock mass should be taken as brittle, reaching residual
     strength after millimetres to centimetres of displacement, and Newmark
     is crude for it [nzgs_2025_torlesse] (`nzgs2025-u7c2-F37`). That
     supports dropping Godt's 5 cm displacement step, the modification
     already proposed, for rock.
   - Its demand need not be a free fraction of PGA. Wellington practice uses
     0.65 PGA for a whole-slope mechanism [brabhaharan_2018; monteith_2020]
     (`brabhaharan2018-F07`, Table 7.8; `sr2019-051-F34`), with PGA times the
     crest amplification for the upper quartile of a slope. Use that as the
     fraction, from practice rather than from a fit.
   - Pender's lower-bound rock-mass envelope for Wellington greywacke,
     `τ = 1.7 MPa (σn / 10 MPa)^0.5`, applies to slopes 15 to 180 m high
     (`nzgs2025-u7c2-F23`). It is the strength input for the larger slopes
     model 7 covers.

What it does not settle: which of models 1, 2, 5 and 7 should carry most
weight. That needs the Kaikōura runs each build plan already sets out, and
the review set adds no evidence for one over another.

### The USGS software

- **The software is the USGS `groundfailure` package**
  (<https://code.usgs.gov/ghsc/esi/groundfailure/groundfailure>). It is
  released into the public domain, with a CC0 waiver worldwide, so there is no
  licence barrier to running or modifying it. Cite it as Allstadt, Thompson,
  Hearne & Biegel (2018), groundfailure v1.0, USGS Software Release,
  <https://doi.org/10.5066/P91G4NS4>. The methodology paper is Allstadt et al.
  (2021) in *Earthquake Spectra*.
- **Tag 1.0 is the reviewed release of 11 May 2018.** The latest tag at the
  time of writing is **1.3.2 (12 August 2026)**. Use the latest, not 1.0.
- **Model 1 is in it** as `jessee_2018`, with Table 3's coefficients and
  equation 9, unchanged from the paper, plus operational additions:
  - The **unconsolidated sediment coefficient is raised from −3.21 to −1.36**,
    "to better reflect that this unit is not actually strong". It is set equal
    to mixed sedimentary.
  - Cells below 2° slope or below 2 %g PGA are masked.
  - PGV is clipped at 211 cm/s and CTI at 19.
  - Probability is capped at 0.256.
  - Uncertainty is propagated from the ShakeMap PGV standard deviation plus a
    model standard-deviation raster.

  **Godt et al. (2008), the physically based alternative, is in it** as
  `godt_2008`. So are the
  liquefaction models of Zhu et al. (2015, 2017), which the liquefaction work
  may want as a cross-check.
- **It can be rerun, but not straight out of the box for Wellington.** The
  code is in the repository. The global input rasters are not, apart from
  small extracts for Northridge and Loma Prieta used by the notebooks and
  tests. The Nowicki Jessee model expects `global_grad.tif`,
  `GLIM_replace.tif`, `globcover_replace.tif`, `global_cti_fil.grd` and
  `jessee_standard_deviation.tif`. The two `_replace` files are **coefficient
  rasters**: GLiM and GlobCover already recoded to their Table 3
  coefficients, not the raw maps. It also expects its shaking input as a
  ShakeMap `grid.xml`, not a GeoTIFF.
- **Two ways to run model 1:**
  1. **Run `groundfailure` itself.** Obtain the global rasters — ask the USGS,
     or rebuild them from GMTED2010, GLiM, GlobCover 2009 and HYDRO1k — and
     write our scenario PGV and PGA, with their standard deviations, into
     ShakeMap grid format. This is faithful to the operational product, at
     the cost of a conda environment and a format conversion.
  2. **Reimplement the equation in `src/landloss`**, with Wellington inputs
     built to the model's specification, and use `groundfailure` as the
     reference implementation. Check that our code reproduces its output on
     the bundled Northridge extract before trusting it on Wellington.

  **Decided: option 2, a complete rebuild, then a check.** The project lead
  prefers to control the whole pipeline. So every input layer is rebuilt from
  its public source by our own code, the equation is implemented in
  `src/landloss`, and `groundfailure` serves only as the reference to check
  against. It keeps model 1 inside our own realisation loop and lets models 1
  and 5 share one implementation.
- **The check is ready-made.** `groundfailure`'s test data for the 1989 Loma
  Prieta earthquake (`tests/data/loma_prieta/`) holds the USGS's own prepared
  inputs for this model — `global_grad.tif`, `GLIM_replace.tif`,
  `globcover_replace.tif`, `global_cti_fil.grd`,
  `jessee_standard_deviation.tif` — plus the ShakeMap (`grid.xml`,
  `uncertainty.xml`) and the expected output (`targets/jessee_2018.grd`,
  `jessee_2018_std.grd`). The check runs in two stages:
  1. Rebuild each layer from its raw source over the Loma Prieta extent and
     compare it with the USGS raster. This tests the layer build.
  2. Run our equation on the USGS rasters and compare with the target. This
     tests the implementation.

  Only once both agree does the same pipeline run over Wellington.
- **Built and checked (29 September 2026).** The rebuild is
  `landloss.hazard.landslide.models.nowicki_2018`, fed by the `get_` scripts in
  `static_data_gen/` and the readers in `landloss.io.global_datasets`. At Loma
  Prieta the equations reproduce the USGS output on its own inputs. The fully
  rebuilt inputs give total landslide area within 1% of it (−0.6%) and a
  cell-by-cell correlation of 0.81. Slope is computed on a grid registered as
  the USGS's is, after resampling the DEM onto it, which is what closes most of
  the slope bias. See
  `validations/nowicki_2018/nowicki_2018_loma_prieta_findings.md`. The
  Wellington run is not yet made. PGV comes from the scenario's Sa(1.0 s) at
  site class 2, read through `landloss.io.nlm.get_nlm_scenario_sa_t1_2500yr`.
- **Every layer can be downloaded by script** (checked 29 September 2026):

  | Layer | Source | Access |
  | --- | --- | --- |
  | Slope | GMTED2010 7.5 arc-second **median** tile `50S150E_20101117_gmted_med075.tif` (covers 50–30°S, 150–180°E), from the USGS EROS `edcintl.cr.usgs.gov` GMTED tiles | Direct HTTP, 277 MB, no login |
  | Lithology | GLiM full vector, `LiMW_GIS 2015.gdb.zip`, from the Dropbox link on the University of Hamburg GLiM page (also sold by CCGM as the Lithological Map of the World) | Direct, 1.1 GB, no login. The 0.5° PANGAEA version (CC BY 3.0) is too coarse. Licence of the vector not stated; check before redistributing |
  | Land cover | GlobCover 2009 v2.3, `Globcover2009_V2.3_Global_.zip`, ESA `due.esrin.esa.int` | Direct HTTP, 381 MB, no login |
  | CTI | HYDRO1k itself sits behind an EarthExplorer login. Instead, **recompute CTI** as `ln(A / tan β)` from the GMTED2010 30 arc-second tile, which stands in for the GTOPO30 elevation data HYDRO1k was built from. The USGS HDMA CTI for Australasia on ScienceBase is a later alternative | Our own computation |
  | Model standard deviation | USGS only; not needed for the mean. The code falls back to a constant 0.03 without it | — |

  Two things to watch. The Hamburg file is the 2015 CCGM edition of GLiM,
  while the paper used v1.0 (2012), so the top-level classes should be checked
  against Table 3 on the Loma Prieta extent. A recomputed CTI will differ
  somewhat from HYDRO1k's, which was hydrologically conditioned, so its
  distribution should be checked against `global_cti_fil.grd` in the same
  test data.

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
- **It has already been run on Kaikōura, and it overpredicted.** See the next
  section.
- The USGS runs the model in its Ground Failure product with slopes below 5°
  excluded, probabilities below 0.002 dropped, and adjusted coefficients for
  unconsolidated sediments and mixed sedimentary rocks — a precedent for
  modifying the published coefficients.

### What Allstadt et al. (2018) found on Kaikōura

Allstadt, Jibson et al. (2018) ran three global models against the GNS
Kaikōura inventory: this one (cited there as Jessee 2017, the thesis version of
the same model, run through equation 9 to areal coverage), Nowicki et al.
(2014) and Godt et al. (2008). The paper is in the repository at
`context/lit/landslide/allstadt_2018/allstadt-2018-kaikoura-near-real-time-landslide-models.pdf`.

- **There is an observed total to calibrate against.** Summed over cells with
  ShakeMap PGA ≥ 0.1 g, the inventory's landslide area — source and debris
  trail together — is **about 20 km²** (their aggregate hazard `H_agg`). The
  inventory is considered complete above 500 m².
- **All three models "dramatically overpredicted"** that total. Once the
  multi-fault rupture was in the ShakeMap, the observed `H_agg` was not inside
  any model's ±1σ ground-motion range. On a cell-by-cell plot of predicted
  against observed coverage, every model was steeper than 1:1 and predicted
  non-zero hazard where none was observed.
- **The pattern was roughly right; the decay was wrong.** The models found the
  worst-affected areas once a rupture plane replaced the point source, but
  hazard stayed elevated tens of kilometres from any actual landslide. Most
  Kaikōura landslides were within 2.5 km of a fault that ruptured (Massey et
  al. 2018), and nothing in the model represents distance to rupture.
- **The overprediction is not blamed on the shaking.** The ShakeMap bias
  correction for PGA was only −0.03 magnitude units. The authors suggest
  instead that Wenchuan contributes most of the training polygons and may
  dominate the fit, and that peak ground motion misses the frequency and
  duration that control triggering. They suggest Arias intensity.
- **Greywacke over-predicted where it mattered most.** The highest peaks of the
  Seaward Kaikōura Range were predicted high hazard, were shaken above 1 g
  nearby, and produced almost no landslides. The authors conclude "there is some
  change in susceptibility that the model inputs are not currently able to
  capture". At the same time many of the largest landslides were in Tertiary
  sediment in the gentler country seaward of the range, and 44 large ones,
  including the eight largest, sat on surface ruptures.
- **The coverage includes runout.** The training inventories merged source and
  debris trail, so equation 9 predicts the fraction of a cell touched by any
  part of a landslide, not the fraction that is source.
- **Ground-motion uncertainty was propagated, and it matters.** Varying the
  shaking by ±1σ left the spatial pattern stable but moved `H_agg`
  substantially, which the authors present as a distribution rather than a
  single value. That is the same wrapping our requirement 2 needs.
- **Slope breaks, ridge noses, terrace edges and coastal cliffs** concentrated
  failures in the field, consistent with topographic amplification (item 6).

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
2. **This model is nearly blind to how greywacke is classed — which is a
   weakness of the model, not a reason to deprioritise the crosswalk.**
   Siliciclastic sedimentary (−1.92) and metamorphic (−1.87) differ by only 0.05
   in the logit, because GLiM's top-level classes lump all greywacke together.
   Other models see a large effect. Massey et al. (2018, 2020) found geology
   among the strongest Kaikōura predictors. Allstadt et al. found the model
   overpredicted the greywacke peaks and underplayed the Tertiary cover. Kingsbury
   (1995) splits greywacke by crushing. Newmark approaches depend on greywacke
   `c′` and `φ′` directly, and Godt et al. (2008) assigns them by lithology and
   age. **Mapping Wellington's geology onto classes that carry a real strength
   difference stays high priority.** That means greywacke by weathering and
   crushing, Tertiary sediments, and the valley deposits.
3. **Slope is measured at ~250 m.** A 30° slope at 250 m is steep country. Our
   hill suburbs will mostly read 10–25° at that scale even where individual cut
   faces are near vertical.

### Three ways to use it, in increasing order of commitment

1. **As an independent check on total landslide area (do this regardless).**
   Run it at its native ~250 m over the study area for the scenario PGV and sum
   `LP × cell area`. This replaces the "order of 1%" figure in
   `s3_landslide_realisation_method.md` with a number computed for
   Wellington's actual slopes and shaking. Treat the result as an upper bound:
   the model overpredicted Kaikōura, and its coverage includes runout, so it
   should be compared with our source plus runout area, not source alone.
2. **As the coarse "how much" layer, downscaled for "where".** Treat each
   ~250 m cell's `LP × cell area` as a landslide area budget, and allocate that
   budget to fine cells inside it by a fine-scale natural-slope susceptibility
   (1–10 m slope, geology, prior failure). Under the portfolio split this is
   model 1 on the large side of the threshold, so cut and fill belong to
   model 6 and not to this allocation. The size distribution (item 10),
   truncated at the threshold, turns the area into a number of polygons. The
   correlated random field (item 12) decides which cells fire together, and
   runout (item 11) follows unchanged. This keeps the model's calibration at
   the scale it was fitted at and puts our local data where it is strongest.
   **This is the recommended route.**
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

1. **A PGV grid for the scenario — resolved: derive it from Sa(1.0 s).** The
   scenario supplies `Sa_T1`, and PGV correlates closely with long-period
   spectral acceleration. Record the Sa-to-PGV relation used and its scatter,
   and carry that scatter into the PGV realisations. ln(PGV) carries the
   biggest coefficient and the interaction term as well, so the conversion is
   still the most influential single input assumption.
2. **Slope at the model's own resolution.** The multiscale stack
   (ground step 1, `ground/steps/s1_terrain`) stops at 100 m. It needs a ~250 m level computed the
   way the paper did — slope of the *median* elevation in each 7.5 arc-second
   cell, not a mean of fine slopes, which would come out much steeper.
3. **CTI at ~1 km**, computed from a DEM coarsened to 30 arc-seconds. Computed
   from the 1 m DEM it would have a different distribution and the 0.03
   coefficient would not apply.
4. **A geology classification with real strength contrast — high
   priority.** First, a crosswalk from the GNS geological map units to GLiM
   classes, so the published model can be run at all. Second, and more
   important, a finer split that GLiM cannot express: greywacke by weathering
   and crushing (item 4, item 5), Tertiary sediments, and the valley deposits.
   That split feeds the fine-scale allocation in route 2 and any refit in
   route 3. The published model is insensitive to the greywacke class, but that
   is the model's limitation (see "What the numbers look like"), not evidence
   that geology does not matter.
5. **A land cover crosswalk** from LCDB v6.0 (`get_nz_land_cover`) to
   GlobCover 2009 classes. Higher stakes: the coefficients run from 0.30
   (artificial) to 1.71 (needleleaved forest).
6. **The Kaikōura PGV field** (USGS ShakeMap version 16, the final one with
   the Bradley et al. 2017 rupture), so the model can be run over the Kaikōura
   inventory already in `landloss.io.kaikoura`. Allstadt et al. (2018) give the
   target: about 20 km² of source plus debris trail above 0.1 g. Reproducing
   their overprediction first confirms our implementation. The ratio between
   our run and 20 km² is then a first New Zealand correction factor, and the
   residuals by geological unit show whether greywacke needs its own treatment.

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
4. **Lithology coefficients**, following the USGS precedent. Allstadt et al.
   already show the greywacke peaks over-predicted. Under the lead's decision
   (item 5) the coefficients the USGS itself changed are used and no others,
   and the greywacke over-prediction is reported, not fitted away.
5. **Overall level: withdrawn (the lead, 2026-10-02).** The model
   overpredicted Kaikōura across the board, and the first plan was to scale
   `LP` to the 20 km² Kaikōura total. Under "How they combine" model 1 keeps
   its published calibration instead, run with the USGS Ground Failure
   product's own operational settings (slopes below 5° excluded,
   probabilities below 0.002 dropped, the adjusted coefficients for
   unconsolidated sediments and mixed sedimentary rock). The Kaikōura
   overprediction is reported as its test result. The same holds for item 4:
   adopt the USGS's own coefficient changes, not new ones fitted on
   Kaikōura.
6. **Source against runout.** Equation 9 coverage includes debris trails. In
   route 2 either split the budget into source and runout using the Kaikōura
   source to trail area ratio, or let our runout step (item 11) generate the
   trail and allocate only the source share.
7. **Distance to rupture.** Hazard in the model does not decay with distance
   from the fault, whereas Kaikōura landslides were concentrated within 2.5 km
   of ruptured traces. For a Wellington Fault scenario the rupture trace is
   known, so a distance-to-rupture term fitted on Kaikōura is a feasible
   addition (item 5).
8. **Spatial correlation.** Like every cell-by-cell model, it gives an expected
   coverage per cell and says nothing about which cells fail together. Our step
   has to add that (item 12) whichever route is taken.
9. **Probabilistic wrapping.** The model is conditional on one PGV field and
   its own intervals cover coefficient error only. Run it inside PGV
   realisations — the PGV analogue of `beta_pga_realisation` — so that ground
   motion uncertainty reaches the loss distribution.
10. **Topographic amplification is already in it.** The ln(PGV) × Slope term is
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
  Supporting information alongside it:
  `nowicki-jessee-2018-supporting-information.pdf` (Figures S1–S4, Tables
  S1–S2; Figures S4I–L are the blind tests on the four New Zealand events) and
  `nowicki-jessee-2018-table-s3-model-selection.xls` (all model combinations
  tested, ranked by AIC). Operational implementation notes are from the USGS
  Ground Failure background page, <https://earthquake.usgs.gov/data/ground-failure/background.php>.
- Allstadt, K.E., Jibson, R.W., Thompson, E.M., Massey, C.I., Wald, D.J.,
  Godt, J.W. & Rengers, F.K. (2018). Improving near-real-time coseismic
  landslide models: lessons learned from the 2016 Kaikōura, New Zealand,
  earthquake. *BSSA* 108(3B), 1649–1664. <https://doi.org/10.1785/0120170297>
  The Kaikōura run of the global models, including this one.
  **In the repository** (tracked, not temp) —
  `context/lit/landslide/allstadt_2018/allstadt-2018-kaikoura-near-real-time-landslide-models.pdf`.
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
  *JGR Earth Surface* 120, 711–729. <https://doi.org/10.1002/2014JF003224>
  Model 2. **In the repository** —
  `context/lit/landslide/kritikos_2015/kritikos-2015-regional-coseismic-landslide-hazard-without-inventories.pdf`.
- Hancox, G.T., Perrin, N.D. & Dellow, G.D. (1997). Earthquake-induced
  landsliding in New Zealand and implications for MM intensity and seismic
  hazard assessment. GNS Client Report 43601B, for the EQC Research Foundation.
  Model 3. **In the repository** — `context/lit/landslide/hancox_1997/`, the scan
  with a searchable markdown version beside it.
- Hancox, G.T., Perrin, N.D. & Dellow, G.D. (2002). Recent studies of
  historical earthquake-induced landsliding, ground damage, and MM intensity
  in New Zealand. *BNZSEE* 35(2). **In the repository** —
  `context/lit/landslide/hancox_2002/`.
- Hancox, G.T. (2010). Earthquake-induced landsliding in New Zealand and
  potential for landslides during earthquakes in Adelaide, South Australia.
  *Australian Geomechanics* 45(3), 51–64. **In the repository** —
  `context/lit/landslide/hancox_2010/`.
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
- **Potential data source:** Schmitt, R.G., Tanyaş, H., Nowicki Jessee, M.A.,
  Zhu, J., Biegel, K.M., Allstadt, K.E., Jibson, R.W., Thompson, E.M., van
  Westen, C.J., Sato, H.P., Wald, D.J., Godt, J.W., Gorum, T., Xu, C.,
  Rathje, E.M. & Knudsen, K.L. (2017). An open repository of
  earthquake-triggered ground-failure inventories. USGS Data Series 1064.
  <https://doi.org/10.5066/F7H70DB4>, ScienceBase community
  <https://www.sciencebase.gov/catalog/item/583f4114e4b04fc80e3c4a1a>. Original
  inventory files and an integrated database with uniform attributes,
  including the inventories Nowicki Jessee et al. trained on. The training and
  test source for model 5, and the inventories to test models 2 and 7 on.
  **Held** as the integrated database, version 4 (February 2022: 84
  inventories, 467,045 ground-failure polygons and 115,402 points), on the
  cross-project data library on R:, and read by `landloss.io.gfdb`
  (`get_gfdb_ground_failure_polygons` and its siblings). New Zealand events are
  in it as events only, with no ground failures mapped. For New Zealand the
  GNS Kaikōura inventory (`landloss.io.kaikoura`) remains the source.
- **Software:** Allstadt, K.E., Thompson, E.M., Hearne, M. & Biegel, K. (2018).
  groundfailure v1.0. USGS Software Release. <https://doi.org/10.5066/P91G4NS4>,
  code at <https://code.usgs.gov/ghsc/esi/groundfailure/groundfailure>
  (public domain / CC0; latest tag 1.3.2, 12 August 2026). Methodology in
  Allstadt, K.E., Thompson, E.M., Jibson, R.W., et al. (2021), The USGS ground
  failure product: near-real-time estimates of earthquake-triggered landslides
  and liquefaction, *Earthquake Spectra* 38, 5–36,
  <https://doi.org/10.1177/87552930211032685>. **Not in temp** — clone the
  repository when needed; the 2021 paper was not attempted.
- Godt, J.W., Sener, B., Verdin, K.L., Wald, D.J., Earle, P.S., Harp, E.L. &
  Jibson, R.W. (2008). Rapid assessment of earthquake-induced landsliding.
  *Proceedings of the First World Landslide Forum*, Tokyo, 392–395. Model 7.
  **In the repository** —
  `context/lit/landslide/godt_2008/godt-2008-rapid-assessment-eq-induced-landsliding.pdf`,
  the copy the USGS PAGER references page links.
- Nowicki, M.A., Wald, D.J., Hamburger, M.W., Hearne, M. & Thompson, E.M.
  (2014). Development of a globally applicable model for near real-time
  prediction of seismically induced landslides. *Engineering Geology* 173,
  54–65. The predecessor of model 1. **Not in temp** — download not attempted.
- Marc, O., Hovius, N., Meunier, P., Gorum, T. & Uchida, T. (2016). A
  seismologically consistent expression for the total area and volume of
  earthquake-triggered landsliding. *JGR Earth Surface* 121(4), 640–663.
  <https://doi.org/10.1002/2015JF003732> Calibration of total area for the
  large models. **In the repository** —
  `context/lit/landslide/marc_2016/marc-2016-total-area-volume-eq-triggered-landsliding.pdf`,
  the author's accepted version from the GFZ repository.
- GNS Science Report SR2019/28, SLIDE (Wellington): geomorphological
  characterisation of the Wellington urban area; and Massey, C.I., Thomas,
  K-L., King, A.B., Singeisen, C., Taig, T. & Horspool, N.A., SLIDE
  (Wellington): vulnerability of dwellings to landslides, GNS Science Report
  SR2018/27. Both listed on the GNS online shop. **Not in temp** — to obtain
  with SR2019/37 for model 4.
- Regional and method context also from the
  `seismic-landslide-hazard-wellington` skill in this repository, and the method
  extraction in
  `.agents/plans/rebuilding-gwrc-slope-failure-susceptibility.md`.
