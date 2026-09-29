# Landslide hazard: status

**Status:** A first cut of the extend-ESNZ route is running; the route is still
not formally chosen.

**Updated:** 2026-09-24

## Approach

The route is not yet formally chosen — see `## Open decisions

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


could this report help: Hancox G T, Dellow G D and Perrin N D (1994).
Earthquake induced slope failure hazard study,
Wellington Region: Review of historical records of
earthquake induced slope failures. Institute of
Geological and Nuclear Sciences Limited Contract
Report prepared for Works Consultancy Services
Limited for Wellington Regional Council.