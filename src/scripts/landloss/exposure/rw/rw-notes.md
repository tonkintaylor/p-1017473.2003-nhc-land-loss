# Retaining wall exposure: notes

The retaining wall `status.md` as it stood on 2026-10-02, kept whole when that
file was condensed for review, so that nothing it recorded is lost. `status.md`
is the current page; where the two disagree, `status.md` is current. This file
is not kept up to date.

Removed 2026-10-08: the candidate wall lines (`gen_wall_lines.py`,
`fig_wall_lines.py`, the line builders in `landloss.exposure.rw.lines`,
`wall-lines*.geoparquet`) and the per-line probability, along with landslide
steps 6 and 7 that they read and fed. The candidates are now the wall units
exposure rw step 6 builds on ground step 4's pifs (`gen_wall_units.py`;
landslide step 12 built them until 2026-10-08), and step 6 gives them a
probability and draws the population (`gen_wall_probability.py`, `gen_wall_population.py`). The
paragraphs below describing lines are the 2026-10-02 state, not the current
method.

**Status:** The candidate wall lines, a probability per line and a wall
population per exposure world are built and were run over the pilot on
2026-10-02; a property boundary is now a candidate only where the 1 m DEM steps
across it, and the candidates are to be rebuilt from the faces layer
(`.agents/plans/building-face-based-urban-slope-polygons.md`). Every probability is judgement until the claim report extraction
(**T-50**) calibrates it.

**Updated:** 2026-10-02

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [ ] Classify every wall on three axes: **six wall classes**, **three size
  subclasses** — small below 1 m, medium 1 to 2.5 m, large above 2.5 m — and
  **two initial state classes** (modern, poor). The axes match how the published
  fragility sets are parameterised — wall type, height and initial condition —
  so each cell can carry a curve from
  `.agents/context/retaining-wall-fragility.md`.
- [x] Carry **two damage states only: no damage, and replace.** A wall either
  survives or is written off. Repair is not modelled because very few damaged
  walls are repaired in practice, so the third state would carry almost nothing.
  The initial state class is a separate axis and is not a damage state.
- [ ] Settle a replaced wall against the **$50,000 per dwelling** sub-cap, plus GST.
  The cap is per dwelling rather than per wall, so a property with several walls
  and one dwelling shares one cap.
- [x] Size the three subclasses by what the costing can tell apart rather than by
  engineering interest. Above the cap the settlement stops depending on height,
  so a three metre and a six metre wall cost the same to settle and do not need
  separating.
- [~] **Identify where walls are, as lines, and put a probability on each line**,
  from a model over the DEM, the geomorphology and geology, and road and dwelling
  locations. A wall is a located line, not a probability on a property, so a
  property with several walls has several lines. No retaining wall dataset exists
  for the study area, so the lines have to be inferred rather than looked up
  (**L-04**). The lines exist (`gen_wall_lines.py`), and so does a probability
  per line from its source, rock cut, flat land and mapped wall
  (`gen_wall_probability.py`); the other inputs do not enter it yet.
- [x] **Start candidate lines from the GNS mapped walls**, the edges of the GNS cut
  slopes and fill bodies, sharp breaks in slope, and section and road edges on
  sloping ground near buildings. Walls are usually on the edge of a section
  rather than the middle. Driveway edges are not a source in this build. A
  section or road edge is a candidate only where the 1 m DEM steps at least
  0.5 m across it (the lead, 2026-10-02): over the pilot that keeps 1,574 of
  4,540 boundary lines.
- [>] **Build the wall candidates from the step faces** of the static faces
  layer, a wall being a face at least 0.5 m high, with the GNS mapped walls
  [townsend_2020], the property boundaries and the SLIDE edges as evidence on
  each rather than as lines of their own (`.agents/plans/building-face-based-urban-slope-polygons.md`, phase 2, where the
  references are listed).
- [~] **Read the 1:50,000 Wellington geology** to tell rock cuts from soil slopes.
  Steep greywacke does not mean walls, so it lowers a line's probability. Each
  line carries the ground map's material and an `is_rock_cut` flag, and a
  rock cut's probability is multiplied by `BETA_ROCK_CUT_FACTOR`.
- [~] **Set a wall's probability of failure from its condition and its size from its
  height**, and cost on size: initial condition changes the probability of
  failure only, not the cost. The size comes from the line's DEM face height,
  and the fragility by size and condition is in hazard landslide step 5 and
  `vul/shaking/rw` step 9.
- [ ] **Set the initial state from the age of the dwelling**, as the available proxy
  for whether a wall is modern or poor, read from a building construction age
  layer built outside this build; see "Wall condition from building age" below.
  The rule is in `poor_condition_probability`; no age is held.
- [ ] **Constrain the wall count per property with the claim report extraction**
  (**T-50**) in a later phase. It arrives after the build starts, as a minimum
  and maximum number of walls per property, and raises the probabilities of the
  candidate lines inside that property. The SME suburb estimate, the manual
  mapping study, the remote sensing detection and the ICNZ database will not be
  obtained (decided 2026-10-01). The scaling once written for this was
  removed on 2026-10-05: the claim counts now update the wall units'
  probabilities in exposure rw step 6(`gen_wall_units.py`).

- [x] **Draw the wall population per exposure realisation**, on its own stream,
  separate from the hazard realisations: a few exposure realisations against
  many hazard ones, because whether a wall exists is not something the
  earthquake decides.
- [~] **Give every wall on sloping land a failure polygon** in the urban slope
  model, so the wall and the land it holds fail together through the wall's
  fragility; see `hazard/landslide/status.md`. Landslide steps 7 to 9 fix the
  polygons, put a fragility on each and draw them with the walls on their
  edges; none has been run over the pilot. Walls on flat land stand alone and
  fail by shaking in `vul/shaking/rw`.


### Engineering review advice (Nick Peters)

Advice from the T+T Wellington engineering review, to be built into the line
model. Much of it is general assumption rather than measured, and each item is
meant to shape a prior rather than be applied as a rule.

- [~] **Do not assume steep means walled.** Properties on Wellington greywacke
  slopes often have an exposed rock cut face rather than a wall, and NHC claims
  there are for spalling or slides in the rock face. Oriental Bay and Evans Bay are
  steep with few walls. The 1:50,000 geology is how to tell.
- [ ] **Most walls hold fill and soil, not rock.** They stabilise fill at the front
  of a section or form stepped platforms onto shallower slopes. Not a blanket
  assumption.
- [x] **Allow several walls per property**, most commonly two, three or four, of
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

Step 8 (`steps/s8_infer_rwt_age/`) estimates the age per claim property, from
the dates of its titles and survey plan. The wall probability does not read it
yet. The QV rating roll's building age could replace the estimate later; see
"Future improvements".

- [x] Bin dwelling age into four periods, each opened by a change in how walls
  were designed or regulated: before 1970, 1970 to June 1992, July 1992 to
  2004, and 2005 on. The reasoning is in
  `src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`.
- [~] Infer each property's bin from the issue date of its title (LINZ NZ
  Property Titles List), with rules for an infilled, converted or reissued
  title, set against Christchurch's open valuation roll (step 8,
  `s8_infer_rwt_age`). The per-suburb shares go in the report as a table.
- Set the probability of a poor wall from the construction decade of the
  dwelling: pre-1990 walls, often cast in situ concrete gravity walls of the
  1970s and 80s, are more likely poor, and post-1991 Building Act walls more
  often modern. Height under 1.5 m, likely unconsented, and wall type where
  known raise it on top of age.
- Where no age is held, use a suburb or SA2 proxy, so no line is left without
  a condition probability.
- The property-level source is the District Valuation Roll building age code,
  a decade per rating unit under the Rating Valuations Rules 2008. LINZ
  publishes it openly for five councils only, none in the study area. QV
  supplied it for all four councils on 2026-10-02, as sensitive data
  (`landloss.io.qv_rating_roll`), but the open-data estimate stays in use for
  now (the lead, 2026-10-02).
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

**The candidate wall lines existed (removed 2026-10-08).** `steps/s6_wall_population/gen_wall_lines.py`
writes `temp/exposure/wall-lines[-pilot].geoparquet`, one line per place a wall
could stand and no probability, through `landloss.exposure.rw.lines`: the GNS
SLIDE mapped walls snapped onto the urban slope candidate edges, the SLIDE
cut/fill lines, the edges of the genesis cut slopes and fill bodies, terrain
breaks at the toe of steep 1 m candidates, and property boundaries and road
frontages on sloping ground within 100 m of a building; coincident lines
collapsed by source precedence, split at claim property boundaries, and each
carrying its face height and size class from the 5 m local relief, fill or cut
position from the cut-and-fill residual, the ground map's material and flat
land, and its claim (the uphill owner for a fill wall on a boundary, the
downhill owner for a cut wall). Mapped walls under 0.5 m are kept and classed
small. `fig_wall_lines.py` draws the lines by source. It was exercised end to
end on synthetic inputs only; it read landslide steps 3, 4 and 6 (now ground
steps 1 and 2; step 6 was removed).

**The probability per line and the draw per world existed** (the per-line
probability was removed 2026-10-08; the draw now runs on the wall units of
`gen_wall_units.py`).
`gen_wall_probability.py` reads only the lines and writes
`temp/exposure/wall-probability[-pilot].geoparquet`, putting on each line
`p_wall`, from its source's prior, lowered on a rock cut, capped on flat land
and raised where GNS mapped a wall, and `p_poor`, raised under 1.5 m where a
wall is likely unconsented, each with the rule that set it
(`landloss.exposure.rw.wall_probability`). `gen_wall_population.py` draws one
population per exposure world on `EXPOSURE_BASE_SEED` and the world id
(`landloss.exposure.rw.population`), two uniforms per line, wall or not and
poor or not, so a property can have several walls. Claimless lines are dropped
(**I-05**), the 2 m insured-land filter applied, and each kept wall gets an
`rw_id` and carries `wall_line_id` and `world_id`, to
`temp/exposure/wall-population-wNNN[-pilot].geoparquet`. Every wall the
world drew, before the claim and coverage filters, is also written to
`temp/exposure/drawn-walls-wNNN[-pilot].geoparquet` with `rw_id` null where
the wall is not insured; landslide step 5 reads it, so road and
back-of-section walls shape the urban slope model. `gen_exposure.py`
runs the three scripts in order over `WORLD_IDS`.

**The age of every property's walls is estimated.** Step 8's
`gen_rwt_age.py` writes `temp/exposure/rwt-age[-pilot].geoparquet`, one row
per claim property with a dwelling, carrying a year, one of the four age bins
and the rule that set it (`landloss.exposure.rw.age`), from the issue date of
its titles and the date of the survey plan its lot is on.
`table_rwt_age_by_suburb.py` writes the per-suburb shares for the report. The
rules were set against Christchurch's open valuation roll
(`validations/table_rwt_age_christchurch.py`, findings in
`validations/rwt_age_christchurch.md`).

Every number is `BETA_` judgement, not evidence about Wellington. The step 8
age is not yet read onto the lines, so the age rule never fires. (The count
bounds hook was removed on 2026-10-05; the claim counts update the wall units
in exposure rw step 6.) Both scripts are exercised end to end on
synthetic inputs only; neither has been run over the pilot. The interim
per-property probability and the slope-driven stand-in are deleted;
`landloss.exposure.rw.beta_population` keeps the size and condition classes,
and its two old height-range constants only until the loss module's pricing
test stops reading them (**I-14**).

The size thresholds are settled: small below 1 m, medium 1 to 2.5 m, large above
2.5 m.

- Some of the other input datasets have been collected. They are held outside
  the repository, so nothing here reads them yet.
- The manual mapping and the remote sensing detection started with Sophia are
  not being pursued, and neither feeds the model. The claim report extraction
  (**T-50**) is in progress and is not yet readable from here.

## Next

1. Rebuild the wall candidates on the faces layer (`.agents/plans/building-face-based-urban-slope-polygons.md`, phase 2), then
   rerun the pilot and record the counts in the method file. Done: the wall
   units of `gen_wall_units.py` (landslide step 12 until 2026-10-08) are the
   candidates (the lines were removed
   2026-10-08).
2. Name the six wall classes, so a published fragility curve can attach to
   each cell of the class, size and condition grid.
3. Bring the collected input datasets into the repository, or record where they
   are held and how they are read, so the inputs are reproducible.
4. Read the claim report extraction (**T-50**) when it lands, in a later phase,
   and raise the wall units' probabilities per property on the walls it lists
   (built 2026-10-05 in `gen_wall_units.py`, then landslide step 12, on the
   claim layer held now).
5. Read exposure step 8's age bin per property onto the lines, in place of the empty
   `dwelling_age_decade`, and set the condition probability from the four bins.
6. Train the predictive model, bringing slope, height, wall position and
   subdivision age into `p_wall` and wall type into `p_poor`.
7. Delete `BETA_MIN_HEIGHT_M` and `BETA_MAX_HEIGHT_M` once the loss owner has
   re-confirmed the set heights against the 0.5–1.0, 1.0–2.5 and 2.5+ m ranges
   and moved the pricing test onto `MIN_WALL_HEIGHT_M` (**I-14**).

## Validation

- Predicted wall count and length per property against the claim report
  extraction (**T-50**), once it lands, by suburb where the sample allows. That
  extraction is the only independent measure of prevalence the study will have,
  so it is the primary check rather than one of several.
- The share of real walls the GNS mapping captures, from the claims with walls
  at addresses inside the SLIDE footprint, replacing the fixed 0.9.
- The step 8 age rules against Christchurch's open valuation roll, scored per
  property and per suburb (`validations/table_rwt_age_christchurch.py`).

## Open decisions

- The six wall classes are not yet named. They should map onto the wall types
  that carry published fragility curves, or the classification will not be able
  to attach one.
- Whether repair cost scales with wall length or wall height, and what the fixed
  per-job costs are (**T-32**).
- What separates "modern" from "poor", and the dwelling age that divides them.
- **T-11**, **T-20** — the Wellington City Council retaining wall database and
  the council cut-and-fill models.
- **T-09** — reuse of the Auckland Council cut-and-fill slope tool.

## Future improvements

- Switch the wall condition's building age from step 8's open-data estimate to
  the QV rating roll's `building_age_indicator`, which is filled on every
  residential dwelling. Low priority: the open-data approach is preferred for
  now.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
