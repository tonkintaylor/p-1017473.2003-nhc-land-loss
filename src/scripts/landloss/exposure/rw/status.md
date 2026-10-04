# Retaining wall exposure: status

**Status:** Candidate wall lines, a probability on each and a wall population
per exposure world are built and ran over the pilot on 2026-10-02. A property
boundary, road frontage or SLIDE earthwork edge is now a candidate only where
the 1 m DEM steps across it, and the candidates are to be rebuilt from the
landslide model's potential instability faces (pifs). That rebuild was reviewed against the GNS literature review
(`temp/gns_review/`) on 2026-10-02: the literature gives each piece of
evidence on a wall its direction, not its size, so every probability is still
judgement until the claim report extraction (**T-50**) calibrates it. A second
part of the review, the same day, read how a wall fails with its ground (faces
plan, phase 3); see "Where it is now".

**Updated:** 2026-10-04

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
- [>] **Build the wall candidates from the potential instability faces (pifs)**
  of the landslide model, with the mapped walls, boundaries and SLIDE edges as
  evidence on each rather than as lines of their own (pips, pifs and sizs plan,
  `.agents/plans/building-pip-pif-siz-slope-polygons.md`; step 6 plan,
  phase 2e). A pif is a cluster of DEM points that drop at least 0.7 m at 1, 3
  and 5 cells in one of eight directions; a pif whose points are steeper than
  the ground stands unsupported at its height, or step 0.7 m (soil) or 3 m
  (rock) between close points, is a seed instability zone (siz), and the siz
  table the landslide model writes is the wall candidate list. The unwalled
  thresholds are `landslide-slope-thresholds.csv` and
  `landslide-seed-thresholds.csv`. Pifs only where the DEM is LiDAR
  [de_vilder_2024; nzgs_2025_recognition]. This replaces the free-face
  candidates of the earlier faces plan.
- [~] **Lower the chance of a wall on a rock cut**, from the 1:50,000 geology
  and the SLIDE materials through the ground map; Wellington greywacke cuts
  commonly stand at 55 to 75° and many long-standing ones are unsupported
  [nzgs_2025_torlesse]. Two changes: apply it only to cuts taller than the
  soil cover over the rock (height band 4 and up, over 2.5 m), usually under 1 m and 0.5 to 3 m on
  typical slopes [nzgs_2025_torlesse; hancox_2013_slope_types]; and remap
  SLIDE's mixed fill classes in the ground map, which today make 71% of the
  pilot fill and leave the factor almost nothing to act on (landslide step 4
  plan, phase 2).
- [x] **Draw the walls per exposure world**, on their own stream, separate
  from the earthquakes, because whether a wall exists is not something the
  earthquake decides.
- [~] **Give every wall on sloping land the polygon of ground it holds up**, so
  the two fail together through the wall's fragility (landslide steps 7 to 9);
  walls on flat land fail by shaking in `vul/shaking/rw`.
- [~] **Set condition from the age of the dwelling** (step 8, below); not yet
  read onto the lines.
- [ ] **Raise the wall probabilities on a claimed property from the walls
  its claim report lists** (**T-50**), holding a share of claims out for the
  cross-validation (Wall datasets, below; the lead, 2026-10-02). This replaces
  `apply_count_bounds`, which is written and not called. The SME suburb
  estimate, the manual mapping, the remote sensing pilot and the ICNZ database
  will not be obtained (decided 2026-10-01).
- [ ] **Settle a replaced wall against the $50,000 per dwelling sub-cap**, plus
  GST, in the loss module.

### Engineering review advice (Nick Peters)

Assumptions to shape the priors, not rules; most are not yet built in. The
literature each one now rests on is in brackets (review of 2026-10-02). Nick
is a co-author of NZGS Units 7C.2 and 2, so where those units agree with him
they are not independent of his advice.

- [~] **Do not assume steep means walled.** Greywacke slopes often have an
  exposed rock cut, as at Oriental Bay and Evans Bay. Supported: greywacke
  cuts are commonly 55 to 75° and many long-standing ones are unsupported
  [nzgs_2025_torlesse].
- [ ] **Most walls hold fill and soil, not rock**, at the front of a section or
  in stepped platforms. Consistent with the thin cover over the rock
  [nzgs_2025_torlesse; hancox_2013_slope_types] and with cut-and-fill
  platforms that houses straddle [monteith_2020]; the SLIDE reports call walls
  "a typical Wellington construction method" for cuts and fills but give no
  counts [lyndsell_2019; monteith_2020].
- [x] **Allow several walls per property**, most commonly two to four, of
  varied height and construction. A cut-and-fill platform carries two, at
  its back and its front [monteith_2020].
- [ ] **Expect a cluster just under 1.5 m**, the height many believe needs no
  consent. The Building Act 2004 exempts a wall retaining not more than 1.5 m
  with no surcharge [nz_parliament_2004]; in Canterbury 54% of 2,991 walls
  retained under 1.5 m [anderson_2015], though their classes cannot show a
  cluster within that.
- [ ] **Read age as a proxy for condition and size**: pre-1990 walls more often
  cast in situ gravity walls prone to deterioration; post-1991 walls bigger,
  recent ones often timber anchored. In Canterbury wall type tracked era, and
  stone masonry, the oldest, collapsed most (about 18% very poor against
  under 6% for block, gabion and timber pole) [anderson_2015].
- [ ] **Expect walls in new subdivisions.** Suburb-scale cut and fill followed
  the earth-moving machinery of the 1950s [lyndsell_2019].
- [ ] **Houses across gullies may sit on thicker colluvium or fill**; Nick was
  unsure this is worth using. Supported but hard to map: colluvium is 5 to
  10 m in old gullies that may not show at the surface [nzgs_2025_torlesse],
  and gully fills are mostly too small for the geological map [begg_2000].
- [~] **Scan the Wellington NHC claims reports for walls** (**T-50**, in
  progress).
- [x] **Compare the wall datasets property by property**: GNS mapped walls,
  the NHC NZMM flag and the claim reports (`validations/rw_dataset_comparison.md`,
  2026-10-02). GNS and NZMM agree no better than chance (kappa 0.03), and
  neither separates claims listing a wall from those listing none. The NZMM
  flag sits on claimed properties four to six times as often as on others;
  ask NHC how it is populated before using it.

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

## Wall datasets: access and use

Three datasets record walls. All three are incomplete, each in its own way.
They are compared property by property in
`validations/rw_dataset_comparison.md` (2026-10-02). They agree no better than
chance (kappa 0.03 between GNS and NZMM), so none of them can be the truth.

| Dataset | Access | What it locates | Covers | What it misses |
|---|---|---|---|---|
| GNS SLIDE mapped walls [townsend_2020] | `get_gns_slide_morphology`, `Type == MAPPED_WALL_TYPE`; Koordinates 125308 (T+T instance), CC BY 4.0 | A line: 11,288 segments, 280 km | Urban Wellington City | Walls not visible from above; flags 21% of properties |
| NHC NZMM land attributes | `get_nzmm_land_attributes`, `has_retaining_wall`; on T: under `SENSITIVE/`, put on LINZ polygons via `qv_rating_roll.linz_valuation_reference`; sensitive, aggregates only | A property, Y/N | Four councils | Flags 3% of properties; how it is filled is not documented |
| Claim reports | `extract_claim_reports.py` output (`reports.csv`, `walls.csv` per claims list), held on U: (`validations/config.py`); private, aggregates only | A property: count, construction, length and height per wall; no position | 1,551 claimed properties, mostly hill land | Walls that do not matter to the claim |

How each can be used:

- [x] **GNS is the only one that locates a wall**, so it is the only one that
  is evidence on a candidate line. It is already used as a floor on `p_wall`.
- [ ] **NZMM and the claims locate a property, not a wall.** At most they can
  say how many walls a property has. They cannot say which candidate line
  is the wall.
- [ ] **Do not fit `p_wall` to any of them.** Each is a lower bound, biased
  in its own way: GNS to walls visible from above, the claims to walls that
  mattered to a claim on hill land, and NZMM to something not yet known (it
  sits on claimed properties four to six times as often as on others). Fit
  to any of them and the model inherits its gaps. Even taken together they
  find a wall on only 51% of the claimed properties where an engineer listed
  one.
- [ ] **Hold them out and cross-validate at the end**, once the face-based
  candidates and `p_wall` are settled (Validation, below). The checks are
  one-sided, because a dataset with no wall is not evidence of no wall:
  - **Claims, per property:** the modelled expected walls (the sum of
    `p_wall` on the property's lines) against the walls the report lists. The
    model should reach the listed count on most claimed properties. Score
    P(at least one wall) on the properties whose report lists a wall. Also
    score lists-a-wall against lists-none, as a weak contrast only.
  - **GNS, per line:** the share of mapped walls that a candidate line finds
    (the recall already planned in the faces plan, phase 4).
  - **All three, per stratum** (NZMM slope class, council, age bin): the
    modelled share of properties with a wall should not fall below the share
    any dataset, or their union, records. A stratum where it does is one where
    the model has too few walls.
  - **NZMM:** only after NHC says how the flag is filled.
- [ ] **Let a claim report raise each wall's probability, not set a
  minimum count** (the lead, 2026-10-02). On a claimed property whose report
  lists n walls, each candidate line's `p_wall` is updated on the evidence
  that at least n of the property's lines are walls:
  P(line is a wall | at least n walls) = p × P(at least n − 1 of the other
  lines) / P(at least n of all lines), each from the Poisson-binomial of
  the lines' priors. Every line rises or stays, never falls, and the
  expected count rises towards n without being forced to it. A report listing
  no walls changes nothing, because it is not evidence of no wall. This is
  proposed; how to meet it is not settled.
  - It replaces `apply_count_bounds`, whose maximum lowers probabilities and
    whose scaling ignores the priors' shape. Remove it with the change.
  - A random, seeded share of claims (say 30%) is held out and never
    updated, so the cross-validation scores the model on claims it did not
    see.
  - If a property has fewer candidate lines than listed walls, every line goes
    to 1 and the shortfall is reported as candidates missing, not hidden.

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
- **Literature review of how a wall fails with its ground, 2026-10-02**
  (part A of `temp/handoff-remaining-review.md`; detail in the faces plan,
  phase 3, and the landslide status). What it proposes for walls, all for the
  lead:
  - a long face is cut into segments of about 1,000 m³, so a long wall fails
    by segment, not whole; Canterbury walls often collapsed only in part
    [anderson_2015] (`anderson2015-F24`);
  - the ground behind a failed wall is the active wedge on the retained
    ground's φ′, 0.45 H for fill [nzgs_mbie_2017; monteith_2020];
  - a failed fill wall's debris runs out on the fill flow slide line, about
    twice as far as a cut wall's [de_vilder_2022];
  - about a third of Canterbury walls fell in the Average or Poor performance
    classes, which the two damage states cannot hold (`anderson2015-F09`);
    part C below proposes reading them as "none".
- **Literature review of wall performance and condition, 2026-10-02** (part C
  of the handoff). The detail is in `.agents/context/retaining-wall-fragility.md`, "Literature review: the curves against Canterbury" and in
  the "Literature review" section of `assets/choice-of-rwt-bin-ages.md`.
  Proposals, all for the lead:
  - **the wall curves are kept** (the lead, 2026-10-02): the Koutsoupaki
    curves fail 30 to 93% of walls at the study's 1.0 to 1.7 g, against about
    10% Very Poor over the whole Canterbury sequence at the same PGA
    [anderson_2015], and the report says they overpredict against
    Christchurch;
  - **the six classes**, named after Anderson's wall types, with each wall's
    type **inferred from its age bin and the claim reports** (**T-50**) (the
    lead, 2026-10-02), and the type setting the condition;
  - **"replace" is Very Poor** in the comparison;
  - **condition from age**: keep the four bins, with `pre_1970` as the
    gravity masonry era that Anderson found performed worst. Read 1960 and
    the mid-1970s into the fill's engineered or uncontrolled class, not into
    `p_poor`. The oldest Wellington fills performed well, so a fill's age
    alone should not raise its failure rate (`sr2013-058-F26`);
  - **one naming fix**: `wall_probability` splits `p_poor` at 1990, where
    the bins and the Building Act split at 1992, so the constants should be
    renamed to follow the bins.

## Next

1. **Rerun the pilot chain from exposure step 6**, so `temp/` and every step
   downstream carry the step-tested wall lines; until then they hold the
   lines from before the step test. Skip this if the faces rebuild (2) is
   starting now: it replaces those lines.
2. Rebuild the wall candidates on the sizs (the siz table written by landslide
   stage D3; step 6 plan, phase 2e), after the lead reviews the large
   evacuated polygons (landslide status, Next 2); then rerun the pilot and record the counts, the GNS mapped wall recall and
   the drawn height shape against Anderson et al. [anderson_2015] in the
   method file.
3. Name the six wall classes.
4. Read step 8's age bin onto the lines and set the condition probability from
   it.
5. Bring slope, height, position and subdivision age into `p_wall`, and wall
   type into `p_poor`.
6. Once `p_wall` is settled, raise it on the claimed properties that are not
   held out, using the walls their reports list, in place of
   `apply_count_bounds`. Then cross-validate on the held-out claims, GNS and
   the strata (Wall datasets, above; `validations/`).
7. Record where the collected input datasets are held, so the inputs are
   reproducible.
8. Delete the two height-range constants once the loss owner has moved the
   pricing test (**I-14**).

## Validation

- Wall count and length per property against the claim report extraction
  (**T-50**), the only on-site record; one-sided, as a lower bound (Wall
  datasets, above).
- The share of the GNS mapped walls with a detected step under them, which
  replaces the fixed 0.9 detection figure (faces plan, phase 4).
- Drawn wall heights against Anderson et al.'s Canterbury shares, 54% under
  1.5 m, 26% 1.5 to 2.5 m, 20% over 2.5 m [anderson_2015], as a shape check:
  their sample leans to road walls and walls over 1.5 m.
- The modelled share of properties with a wall, per NZMM slope class,
  council and age bin, against the share each dataset and their union records
  (`validations/rw_dataset_comparison.md`). The NZMM flag only once NHC says
  how it is filled.
- The step 8 age rules against Christchurch's open valuation roll
  (`validations/table_rwt_age_christchurch.py`).

## Open decisions

- The share of claims held out from the claim report update, and whether the
  held-out claims get the update in the loss run once the check is done.
- Ask NHC how the NZMM `RetainingWallInd` is filled. It flags 3% of
  properties, and claimed properties far more often than others.

- The six wall classes, which the fragility table waits on; the review
  proposes Anderson's types.
- Whether repair cost scales with wall length or height, and the fixed costs per
  job (**T-32**).
- What separates modern from poor, and the age that divides them. The step 8
  bins open at 1970, July 1992 and 2005; the literature also marks the
  mid-1970s, when NZ earthfill standards arrived [monteith_2020], and 1960,
  before which cuts and non-engineered fills are a warning sign
  [nzgs_2025_recognition]. Neither is a bin edge today.
- The rock-cut factor from height band 4 (over 2.5 m), the cut height taken
  to be through the soil cover, within the published 0.5 to 3 m.
- **T-11**, **T-20**: the council wall database and cut-and-fill models;
  **T-09**: the Auckland cut-and-fill tool.

## Future improvements

- Switch the condition's building age from step 8's open-data estimate to the
  QV rating roll's `building_age_indicator`. Low priority: the open-data
  approach is preferred for now.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
