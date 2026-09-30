# Landslide hazard: status

**Status:** A first cut of the extend-ESNZ route is running, and the Nowicki
Jessee (2018) model is rebuilt and checked; the portfolio of models is proposed
but not agreed.

**Updated:** 2026-09-29

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
source area as the working threshold). Extend-ESNZ becomes the GNS member of it.
Build plans for models 2 and 3, and for the calibration of every large model,
are in `.agents/plans/building-kritikos-2015-landslide-model.md` and
`.agents/plans/building-hancox-landslide-model-and-calibration.md`.

**Forward-use scenario, for the report.** Where a landslide model or its
calibration needs a magnitude or a source distance, every site in the study
area is taken to be **25 km from an Mw 8.1 event** (`BETA_SCENARIO_MW`,
`BETA_SITE_DISTANCE_KM`).

- **Source.** The modal magnitude and distance of the New Zealand National
  Seismic Hazard Model 2022 deaggregation of PGA for Wellington at
  Vs30 = 400 m/s, as provided by the project lead. Cite the NSHM 2022
  (Gerstenberger et al. 2022, GNS Science Report 2022/57).
- **Still to record for the report:** the return period, the NSHM version and
  tool the deaggregation was taken from, and which source the mode is (the
  Hikurangi interface or a crustal fault). Marc et al. (2016) is calibrated on
  crustal earthquakes only, so the last of these decides whether it applies.

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

`steps/s1_landslide_realisation/` holds a runnable first cut of the extend-ESNZ
route. It reads the supplied 32 m probability grid, samples every cell
independently, gives each failure a size from a bounded power law and a circular
footprint, drops the smaller of any overlapping pair, and moves each one downhill
by a distance that grows with the slope — emitting the source polygon as
`evacuated land` and the displaced polygon as `inundated land`. The slope and
downhill direction it uses are in `landloss.common.utils.terrain`, and the reader
for the grid is `landloss.io.source_material`; both are library code with tests,
because they will outlive whatever the model turns into. Its method and its
phased plan are in the step folder.

It has been run against the real grid over both the pilot box and the full
study area. The pattern is right -- the hills either side of the Hutt Valley and
around Porirua are dense and the valley floors are clear -- and the figure under
`report/hazard/landslide/landslide-realisation/fig/` is how that was checked.
The current run figures, and the calibration of the size distribution behind
them, are in `steps/s1_landslide_realisation/s1_landslide_realisation_method.md`;
the questions they raise are under `## Open decisions`.

Two of the three gaps are closed only nominally. There are small failures now,
but their size distribution is fitted to nothing; there is runout, but it is a
rigid translation along one bearing. Spatial correlation is not addressed at all.

The folder also holds `validations/fig_landslide_vulnerability_model_gwrc.py`,
which draws the Greater Wellington zonation the result gets checked against.

The Nowicki Jessee (2018) model is rebuilt as library code in
`landloss.hazard.landslide.models.nowicki_2018`, with its source datasets
fetched to T: by `static_data_gen/` and checked against the USGS in
`validations/nowicki_2018/`. It has not yet been run over Wellington.

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
5. Intersect the result with insured land per claim, keeping loss of support and
   runout separate because `vul` needs them per cause.

The phased build for the new-model route is in
`.agents/plans/estimating-eq-landslide-extent-wellington.md`, not here.
6. Run the Nowicki Jessee model over Wellington, with PGV from the scenario's
   Sa(1.0 s) at site class 2 (`PGV (mm/s) = 750 * Sa(1.0 s) [g]`, the shaking
   module's agreed relation).
7. After the beta, take the site class from the Foster et al. (2019) Vs30 model
   rather than the fixed site class 2 (**T-15**).

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

- **The footprint is a circle, and it should not be.** A real source area is
  elongated down the slope; the model places a circle of the right area at the
  cell centre. Area is right, shape is wrong, and the error shows up wherever the
  answer depends on how a failure is oriented against a property boundary rather
  than on how much ground it covers — which is most of the per-property work.
  The decision is what replaces it: an ellipse oriented downslope is cheap and
  closes most of the gap; growing the source across the slope facet is the fuller
  answer and needs the terrain work that phase 4 carries.
- **The size-frequency distribution is calibrated to area, not fitted to an
  inventory.** This is a separate thing from the footprint. The exponent controls
  how many small failures there are against large ones, and it has been solved
  backwards to make the total area match the literature, giving 1.19 — far
  shallower than the 2.1 to 2.5 that published inventories report. Those fits
  hold only above about 500 m² and real inventories roll over below that, so one
  power law stretched from 3 m² cannot carry both a published slope and the right
  total area. The decision is whether to accept a distribution that gets the area
  right and the proportions wrong, or to move to two populations — small
  modified-slope failures and natural-slope landslides fitted separately.
- **The 3,000 m² upper bound is now a calibration parameter.** With a shallow
  exponent most of the area sits in the largest failures, so the cap decides the
  answer: holding the exponent, a 1,000 m² cap gives 0.44% areal coverage, 3,000
  gives 0.98% and 10,000 gives 2.42%. Both bounds were given as a range to model
  rather than derived from anything. The decision is what the largest credible
  single failure in Wellington actually is.
- **Failures are sampled independently, so the model has no clustering.** Real
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
  which no inventory supports. The decision is whether to make it a function of
  volume as well, which arrives with the Newmark work in phase 3.
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
- **T-11**, **T-19**, **T-20** — retaining wall and cut-and-fill data. The
  Kaikōura inventory is natural slopes and the losses here are expected on
  modified ones, so a second population conditioned on this data is the plan's
  own largest technical risk. The raw source area and debris trail polygons are
  now readable, via `landloss.io.kaikoura` — the fit itself is still to do.

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
