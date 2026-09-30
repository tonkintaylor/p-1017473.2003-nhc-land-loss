# Retaining wall exposure: status

**Status:** A probability of a wall per property runs, partly on GNS mapping,
with a realisation drawn from it; the real inference is not started.

**Updated:** 2026-09-30

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
- **Predict where walls are and how big they are** from a model over the DEM,
  geomorphology, and road and dwelling locations. No retaining wall dataset
  exists for the study area, so the population has to be inferred rather than
  looked up (**L-04**).
- **Set the initial state from the age of the dwelling**, as the available proxy
  for whether a wall is modern or poor.
- **Train the model on four sources** — the ICNZ database, a manual mapping
  study, estimates from T+T Wellington SMEs, and automated detection from remote
  sensing. Each covers a different part of the population and none covers it
  alone.
- Treat the **remote sensing detection as a pilot** rather than a primary
  source. Dense vegetation obscures walls in exactly the suburbs of interest and
  the detection rate is itself unknown (**L-05**).


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
- The manual mapping and the remote sensing detection have both been started
  with Sophia. That work also sits outside the repository and cannot be re-run
  from here.

## Next

1. Place walls on the GNS-mapped lines where one is mapped, rather than on a
   synthetic line, and rerun over the four territorial authorities.
2. Name the six wall classes, so a published fragility curve can attach to
   each cell of the class, size and condition grid.
3. Bring the collected input datasets into the repository, or record where they
   are held and how they are read, so the inputs are reproducible.
4. Bring the manual mapping and the remote sensing pilot into the repository on
   the same basis.
5. Obtain the ICNZ database.
6. Attach a dwelling age attribute to the address spine, which the initial state
   class reads.
7. Train the predictive model and write a wall population per property.

## Validation

- Predicted wall prevalence by suburb against the SME suburb-by-suburb estimate
  (**T-19**). That estimate is the only independent measure of prevalence the
  study will have, so it is the primary check rather than one of several.
- Predicted locations against the manual mapping study, held out of training
  rather than trained on.
- Detection rate of the remote sensing pilot against the same manual mapping, so
  that the unknown detection rate behind **L-05** is measured rather than
  assumed.
- Size distribution against the ICNZ database.

## Open decisions

- The six wall classes are not yet named. They should map onto the wall types
  that carry published fragility curves, or the classification will not be able
  to attach one.
- Whether repair cost scales with wall length or wall height, and what the fixed
  per-job costs are (**T-32**).
- What separates "modern" from "poor", and the dwelling age that divides them.
- Access to the ICNZ database, which is not covered by a register task.
- **T-19** — the SME estimate of wall prevalence by suburb.
- **T-11**, **T-20** — the Wellington City Council retaining wall database and
  the council cut-and-fill models.
- **T-09**, **T-10** — reuse of the Auckland Council cut-and-fill slope tool,
  and how remote sensing can support the detection.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
