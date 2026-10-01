# Retaining wall exposure: status

**Status:** An interim probability of a wall per property runs, partly on GNS
mapping, with a realisation drawn from it. The target is candidate wall lines
each carrying a probability; the real inference is not started.

**Updated:** 2026-10-01

## Approach

Intended, not implemented.

- Classify every wall on three axes: **six wall classes**, **three size
  subclasses** — small below 1 m, medium 1 to 2.5 m, large above 2.5 m — and
  **two initial state classes** (modern, poor). The axes match how the published
  fragility sets are parameterised — wall type, height and initial condition —
  so each cell can carry a curve from
  `.agents/context/retaining-wall-fragility.md`.
- Carry **two damage states only: no damage, and replace.** A wall either
  survives or is written off. Repair is not modelled because very few damaged
  walls are repaired in practice, so the third state would carry almost nothing.
  The initial state class is a separate axis and is not a damage state.
- Settle a replaced wall against the **$50,000 per dwelling** sub-cap, plus GST.
  The cap is per dwelling rather than per wall, so a property with several walls
  and one dwelling shares one cap.
- Size the three subclasses by what the costing can tell apart rather than by
  engineering interest. Above the cap the settlement stops depending on height,
  so a three metre and a six metre wall cost the same to settle and do not need
  separating.
- **Identify where walls are, as lines, and put a probability on each line**,
  from a model over the DEM, the geomorphology and geology, and road and dwelling
  locations. A wall is a located line, not a probability on a property, so a
  property with several walls has several lines. No retaining wall dataset exists
  for the study area, so the lines have to be inferred rather than looked up
  (**L-04**). The interim per-property probability is to be replaced by this.
- **Start candidate lines from the GNS mapped walls**, the edges of the GNS cut
  slopes and fill bodies, sharp breaks in slope, and section, road and driveway
  edges on sloping ground. Walls are usually on the edge of a section rather than
  the middle.
- **Read the 1:50,000 Wellington geology** to tell rock cuts from soil slopes.
  Steep greywacke does not mean walls, so it lowers a line's probability.
- **Set a wall's probability of failure from its condition and its size from its
  height**, and cost on size: initial condition changes the probability of
  failure only, not the cost.
- **Set the initial state from the age of the dwelling**, as the available proxy
  for whether a wall is modern or poor, read from a building construction age
  layer built outside this build; see "Wall condition from building age" below.
- **Constrain the wall count per property with the claim report extraction**
  (**T-50**) in a later phase. It arrives after the build starts, as a minimum
  and maximum number of walls per property, and raises the probabilities of the
  candidate lines inside that property. The SME suburb estimate, the manual
  mapping study, the remote sensing detection and the ICNZ database will not be
  obtained (decided 2026-10-01).
- **Draw the wall population per exposure realisation**, on its own stream,
  separate from the hazard realisations: a few exposure realisations against
  many hazard ones, because whether a wall exists is not something the
  earthquake decides.
- **Give every wall on sloping land a failure polygon** in the urban slope
  model, so the wall and the land it holds fail together through the wall's
  fragility; see `hazard/landslide/status.md`. Walls on flat land stand alone
  and fail by shaking in `vul/shaking/rw`.


### Engineering review advice (Nick Peters)

Advice from the T+T Wellington engineering review, to be built into the line
model. Much of it is general assumption rather than measured, and each item is
meant to shape a prior rather than be applied as a rule.

- [ ] **Do not assume steep means walled.** Properties on Wellington greywacke
  slopes often have an exposed rock cut face rather than a wall, and NHC claims
  there are for spalling or slides in the rock face. Oriental Bay and Evans Bay are
  steep with few walls. The 1:50,000 geology is how to tell.
- [ ] **Most walls hold fill and soil, not rock.** They stabilise fill at the front
  of a section or form stepped platforms onto shallower slopes. Not a blanket
  assumption.
- [ ] **Allow several walls per property**, most commonly two, three or four, of
  variable height and construction type. Do not treat a property with several
  walls as all small or all large.
- [ ] **Expect a cluster just under 1.5 m.** Many people build walls below 1.5 m
  because they believe they need no building consent, and some still do.
- [ ] **Read age as a proxy for condition and size.** Pre-1990 walls are more
  susceptible to deterioration and replacement and are more often cast in situ
  concrete gravity walls from the 1970s and 80s. Post-Building Act 1991 walls tend
  to be bigger, and more recent ones tend to be timber anchored.
- [ ] **Expect walls in new subdivisions.** Almost all have them.
- [ ] **Treat houses across gullies as possibly on thicker colluvium or fill**,
  with wetter soils at the base. Nick was not sure this is worth using.
- [~] **Scan the Wellington NHC claims reports** for retaining walls in the site
  description to estimate how many properties have them (Perrie's extraction,
  **T-50**, in progress).

### Wall condition from building age

Not in this build. A building construction age parquet, one row per building
keyed to the address spine, is to be built separately; the wall probability
script reads it when it exists and falls back to a proxy until then.

- Set the probability of a poor wall from the construction decade of the
  dwelling: pre-1990 walls, often cast in situ concrete gravity walls of the
  1970s and 80s, are more likely poor, and post-1991 Building Act walls more
  often modern. Height under 1.5 m, likely unconsented, and wall type where
  known raise it on top of age.
- Where no age is held, use a suburb or SA2 proxy, so no line is left without
  a condition probability.
- The property-level source is the District Valuation Roll building age code,
  a decade per rating unit under the Rating Valuations Rules 2008. LINZ
  publishes it openly for five councils only, none in the study area, so for
  Wellington it is licensed from QV or CoreLogic, or obtained through NHC,
  which as an insurer likely holds construction decade for its portfolio.
- The proxy, failing a property-level source: each SA2's share of stock
  consented since 1990 from Stats NZ building consents, adjusted to the
  regional decade split in Housing in Aotearoa New Zealand: 2025. GHS-OBAT
  (satellite epochs, all pre-1980 stock in one class) and the RiskScape
  inventory's construction eras at meshblock, held by GNS, are the coarser
  alternatives.


## Beta build

A first end-to-end run is being assembled that produces the right data
structures rather than the right numbers; see
`.agents/plans/beta-build.md` for the whole chain.

The retaining wall exposure the chain expects is **lines**, one per wall, keyed
to `claim_id` and carrying `size_class` and `initial_condition`. That is the
structure the beta has to emit however the population is produced.

## Loss contract

What this module owes the retaining wall table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Give every wall an `rw_id`, `<claim_id>-RW<nn>`, minted in step 6 after
  the coverage filter.
- [x] Pass on only the walls that intersect their claim's insured land buffered
  by 2 m (`keep_walls_on_insured_land`).
- [x] Carry `claim_id`, `size_class` (the contract's `rw_size`) and `length_m`
  (`rw_length`).
- [x] Carry coordinates, as the wall line.

## Where it is now

**This is the interim shape.** It puts a probability on each property, which
cannot say where a wall is or give a property more than one. The plan
(`steps/s6_wall_population/s6_wall_population_implementation_plan.md`, phase 2)
replaces it with candidate wall lines, each with a probability.

`steps/s6_wall_population/` is two scripts. `gen_wall_probability.py` writes a
**probability of a wall per insured property**, with the retained height as a
lognormal, the probability of each size class and of poor condition.
`gen_wall_population.py` then **draws a realisation** from it: at most one wall per
insured property, each placed as a line along the contour. Only walls
intersecting their claim's insured land buffered by 2 m are written, each with an
`rw_id`.

The probability starts from slope alone, which is a **stand-in**, and is then
adjusted by three GNS Science and NLM layers read through `landloss.io.readers`:

- the retaining walls GNS SLIDE mapped (`get_gns_slide_morphology`) raise a
  probability where a wall is mapped;
- the SLIDE cut slopes and fill bodies (`get_slide_genesis`) lift it;
- the NLM landform class (`get_nlm_geomorphology`) caps it on plains.

The GNS mapping is Wellington City only and shows only walls visible from above,
so it never lowers a probability. Over the pilot box 1,024 of 4,295 properties
(24%) have a mapped wall, and the run expects 1,409 walls (33%) against 15.9% from
slope alone. That says the slope-only prevalence was too low on the mapped
suburbs, not that 33% is right. The library is
`landloss.exposure.rw.wall_probability`, with the slope-driven part in
`landloss.exposure.rw.beta_population`, whose public names carry `beta` because
they are deleted when the real inference lands.

It is not evidence about Wellington. It exists so the vulnerability work has
lines with a size class and an initial condition to read.

The size thresholds are settled: small below 1 m, medium 1 to 2.5 m, large above
2.5 m.

- Some of the other input datasets have been collected. They are held outside
  the repository, so nothing here reads them yet.
- The manual mapping and the remote sensing detection started with Sophia are
  not being pursued, and neither feeds the model. The claim report extraction
  (**T-50**) is in progress and is not yet readable from here.

## Next

1. Build the candidate wall lines, starting from the GNS mapped walls and the
   edges of cut slopes and fill bodies, and put a probability on each line, using
   the 1:50,000 geology to lower it on steep greywacke.
2. Name the six wall classes, so a published fragility curve can attach to
   each cell of the class, size and condition grid.
3. Bring the collected input datasets into the repository, or record where they
   are held and how they are read, so the inputs are reproducible.
4. Read the claim report extraction (**T-50**) when it lands, in a later phase,
   and constrain the wall count per property to the minimum and maximum it
   gives.
5. Read the building construction age parquet when it is built, outside this
   build, and set the condition probability from it.
6. Train the predictive model and write a wall population per property.

## Validation

- Predicted wall count and length per property against the claim report
  extraction (**T-50**), once it lands, by suburb where the sample allows. That
  extraction is the only independent measure of prevalence the study will have,
  so it is the primary check rather than one of several.
- The share of real walls the GNS mapping captures, from the claims with walls
  at addresses inside the SLIDE footprint, replacing the fixed 0.9.

## Open decisions

- The six wall classes are not yet named. They should map onto the wall types
  that carry published fragility curves, or the classification will not be able
  to attach one.
- Whether repair cost scales with wall length or wall height, and what the fixed
  per-job costs are (**T-32**).
- What separates "modern" from "poor", and the dwelling age that divides them.
- The building age source for Wellington: DVR building age licensed from QV or
  CoreLogic, NHC's own property attributes, or the SA2 consents proxy.
- **T-11**, **T-20** — the Wellington City Council retaining wall database and
  the council cut-and-fill models.
- **T-09** — reuse of the Auckland Council cut-and-fill slope tool.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
