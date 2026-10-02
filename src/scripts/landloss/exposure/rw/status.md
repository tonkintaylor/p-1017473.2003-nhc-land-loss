# Retaining wall exposure: status

**Status:** Candidate wall lines, a probability on each and a wall population
per exposure world are built and ran over the pilot on 2026-10-02. A property
boundary, road frontage or SLIDE earthwork edge is now a candidate only where
the 1 m DEM steps across it, and the candidates are to be rebuilt from the
faces layer. Every probability is judgement until the claim report extraction
(**T-50**) calibrates it.

**Updated:** 2026-10-02

For a reviewer: read this page, then
`.agents/plans/building-face-based-urban-slope-polygons.md`, then the method
files under `steps/`, then the code. The fuller text this page held before it
was condensed is in `rw-notes.md` beside it.

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] **Carry two damage states, no damage and replace**, because very few
  damaged walls are repaired; condition (modern or poor) is a separate axis.
- [x] **Size walls small (below 1 m), medium (1 to 2.5 m) and large (above
  2.5 m)** of retained height, by what the costing can tell apart.
- [ ] **Name six wall classes**, so each class, size and condition can carry a
  published fragility curve (`.agents/context/retaining-wall-fragility.md`).
- [~] **Identify where walls are, as lines, with a probability on each**
  (`steps/s6_wall_population/`). No wall dataset exists (**L-04**), so the
  lines are inferred: GNS mapped walls [townsend_2020], SLIDE cut and fill
  edges and lines, terrain breaks, and section and road edges near buildings.
  Every source but the mapped walls and the terrain breaks is kept only along
  the stretches where the 1 m DEM steps at least 0.5 m across it (the lead,
  2026-10-02), bridging dips of up to 3 m and keeping stretches of at least
  3 m.
- [>] **Build the wall candidates from the step faces** of the static faces
  layer, with the mapped walls, boundaries and SLIDE edges as evidence on each
  rather than as lines of their own (faces plan, phase 2).
- [~] **Lower the chance of a wall on a rock cut**, from the 1:50,000 geology
  and the SLIDE materials through the ground map; steep greywacke often stands
  unsupported.
- [x] **Draw the walls per exposure world**, on their own stream, separate
  from the earthquakes, because whether a wall exists is not something the
  earthquake decides.
- [~] **Give every wall on sloping land the polygon of ground it holds up**, so
  the two fail together through the wall's fragility (landslide steps 7 to 9);
  walls on flat land fail by shaking in `vul/shaking/rw`.
- [~] **Set condition from the age of the dwelling** (step 8, below); not yet
  read onto the lines.
- [ ] **Constrain the wall count per property with the claim report
  extraction** (**T-50**), arriving later as a minimum and maximum per
  property; `apply_count_bounds` is written and not called. The SME suburb
  estimate, the manual mapping, the remote sensing pilot and the ICNZ database
  will not be obtained (decided 2026-10-01).
- [ ] **Settle a replaced wall against the $50,000 per dwelling sub-cap**, plus
  GST, in the loss module.

### Engineering review advice (Nick Peters)

Assumptions to shape the priors, not rules; most are not yet built in.

- [~] **Do not assume steep means walled.** Greywacke slopes often have an
  exposed rock cut, as at Oriental Bay and Evans Bay.
- [ ] **Most walls hold fill and soil, not rock**, at the front of a section or
  in stepped platforms.
- [x] **Allow several walls per property**, most commonly two to four, of
  varied height and construction.
- [ ] **Expect a cluster just under 1.5 m**, the height many believe needs no
  consent.
- [ ] **Read age as a proxy for condition and size**: pre-1990 walls more often
  cast in situ gravity walls prone to deterioration; post-1991 walls bigger,
  recent ones often timber anchored.
- [ ] **Expect walls in new subdivisions.**
- [ ] **Houses across gullies may sit on thicker colluvium or fill**; Nick was
  unsure this is worth using.
- [~] **Scan the Wellington NHC claims reports for walls** (**T-50**, in
  progress).

### Wall condition from building age

Step 8 (`steps/s8_infer_rwt_age/`) estimates the age per claim property, from
the dates of its titles and survey plan. The wall probability does not read it
yet.

- [x] Bin dwelling age into four periods, each opened by a change in how walls
  were designed or regulated: before 1970, 1970 to June 1992, July 1992 to
  2004, and 2005 on (`src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`).
- [~] Infer each property's bin from the issue date of its title, with rules
  for an infilled, converted or reissued title, set against Christchurch's open
  valuation roll (`s8_infer_rwt_age`).
- The District Valuation Roll's building age is the property-level source; QV
  supplied it for the four councils on 2026-10-02 as sensitive data
  (`landloss.io.qv_rating_roll`), and the open-data estimate stays in use for
  now (the lead, 2026-10-02). Failing a property-level age, an SA2 proxy from
  Stats NZ consents; detail in `rw-notes.md`.

## Loss contract

What this module owes the retaining wall table `loss` reads
(`.agents/plans/asset-pricing-approach.md`, section 1).

- [x] Give every wall an `rw_id`, `<claim_id>-RW<nn>`, after the coverage
  filter.
- [x] Pass on only the walls touching their claim's insured land buffered by
  2 m.
- [x] Carry `claim_id`, `size_class` and `length_m`, and the wall line.

## Where it is now

- **The pilot run of 2026-10-02**: 8,342 candidate lines, 2,921 walls drawn in
  world 0, 1,760 of them insured on 1,058 claims. Property boundaries were
  4,540 of the lines, 110 km. With the step test on the boundaries, road
  frontages and SLIDE earthwork edges, each trimmed to its stepped stretches,
  there are 8,832 candidates over 100 km, and the boundaries fall to 47.5 km
  in 4,494 shorter lines. Most sloping boundaries step somewhere along their
  length. This was rerun into a scratch folder only; the table is in the step 6
  method file.
- `gen_wall_lines.py`, `gen_wall_probability.py` and `gen_wall_population.py`
  are the three scripts of step 6; their method file says what each does.
  `p_wall` comes from the source, lowered on rock cuts, capped on flat land and
  raised where a wall is mapped; `p_poor` is raised under 1.5 m. Every number
  is `BETA_` judgement.
- Every wall a world drew, insured or not, is written to
  `drawn-walls-wNNN[-pilot].geoparquet` for the urban slope model; the insured
  ones, with their `rw_id`, to `wall-population-wNNN[-pilot].geoparquet`.
- Step 8 writes `rwt-age[-pilot].geoparquet`, an age bin per claim property,
  checked against Christchurch's open valuation roll
  (`validations/rwt_age_christchurch.md`).
- `beta_population` keeps two old height-range constants only until the loss
  module's pricing test stops reading them (**I-14**).

## Next

1. **Rerun the pilot chain from exposure step 6**, so `temp/` and every step
   downstream carry the step-tested wall lines; until then they hold the
   lines from before the step test.
2. Rebuild the wall candidates on the faces layer (faces plan, phase 2), then
   rerun the pilot and record the counts in the method file.
3. Name the six wall classes.
4. Read step 8's age bin onto the lines and set the condition probability from
   it.
5. Bring slope, height, position and subdivision age into `p_wall`, and wall
   type into `p_poor`.
6. Read the claim report extraction (**T-50**) when it lands, and constrain the
   count per property.
7. Record where the collected input datasets are held, so the inputs are
   reproducible.
8. Delete the two height-range constants once the loss owner has moved the
   pricing test (**I-14**).

## Validation

- Wall count and length per property against the claim report extraction
  (**T-50**), once it lands; the only independent measure of prevalence.
- The share of the GNS mapped walls with a detected step under them, which
  replaces the fixed 0.9 detection figure (faces plan, phase 4).
- The NZMM retaining wall flag per address (`landloss.io.nzmm_land_attributes`)
  against the addresses with a stepped candidate.
- The step 8 age rules against Christchurch's open valuation roll
  (`validations/table_rwt_age_christchurch.py`).

## Open decisions

- The six wall classes, which the fragility table waits on.
- Whether repair cost scales with wall length or height, and the fixed costs per
  job (**T-32**).
- What separates modern from poor, and the age that divides them.
- **T-11**, **T-20**: the council wall database and cut-and-fill models;
  **T-09**: the Auckland cut-and-fill tool.

## Future improvements

- Switch the condition's building age from step 8's open-data estimate to the
  QV rating roll's `building_age_indicator`. Low priority: the open-data
  approach is preferred for now.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
