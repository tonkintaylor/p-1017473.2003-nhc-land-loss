# Retaining wall exposure: status

**Status:** The wall candidates are rebuilt on the landslide model's
potential instability faces (pifs): wall units, their probability with the
claim report update, and a draw per exposure world, built and read by step 6,
ran over
the pilot on 2026-10-05. The candidate wall lines of 2026-10-02 were removed on
2026-10-08, with landslide steps 6 and 7. That rebuild was reviewed against the GNS literature review
(`temp/gns_review/`) on 2026-10-02: the literature gives each piece of
evidence on a wall its direction, not its size, so every probability is still
judgement until the claim report extraction (**T-50**) calibrates it. A second
part of the review, the same day, read how a wall fails with its ground (faces
plan, phase 3); see "Where it is now".

**Updated:** 2026-10-08

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
- [~] **Draw a type for every wall from its age, height and road frontage**,
  and give each type its own curve, in place of the condition axis
  (`.agents/plans/assigning-retaining-wall-types.md`). The seven type curves
  are set (the lead, 2026-10-06; two height classes from 2026-10-07), and the
  draw is built in step 6 but not yet run on the pilot. Nick
  Peters and John Leeves reviewed the shares on 2026-10-07, and the lead
  applied their changes on 2026-10-08 (**T-118**).
- [~] **Identify where walls are, as lines, with a probability on each**
  (`steps/s6_wall_population/`). No wall dataset exists (**L-04**), so the
  lines are inferred: GNS mapped walls [townsend_2020], SLIDE cut and fill
  edges and lines, terrain breaks, and section and road edges near buildings.
  Every source but the mapped walls and the terrain breaks is kept only along
  the stretches where the 1 m DEM steps at least 0.5 m across it (the lead,
  2026-10-02), bridging dips of up to 3 m and keeping stretches of at least
  3 m.
- [x] **Build the wall candidates from the potential instability faces (pifs)**
  of the landslide model, with the mapped walls, boundaries and SLIDE edges as
  evidence on each rather than as lines of their own (pips, pifs and sizs plan,
  `.agents/plans/building-pip-pif-siz-slope-polygons.md`; step 6 plan,
  phase 2e). A pif is a cluster of DEM points that drop at least 0.7 m at 1, 3
  and 5 cells in one of eight directions; a pif whose points are steeper than
  the ground stands unsupported at its height, or step 0.7 m (soil) or 3 m
  (rock) between close points, is a seed instability zone (siz), and the siz
  table ground step 3 writes, with the wall evidence ground step 4 adds, is the
  wall candidate list. The unwalled
  thresholds are `landslide-slope-thresholds.csv` and
  `landslide-seed-thresholds.csv`. Pifs only where the DEM is LiDAR
  [de_vilder_2024; nzgs_2025_recognition]. This replaces the free-face
  candidates of the earlier faces plan. Built 2026-10-05: every pif is tied to
  its property (LINZ property boundaries), and every GNS mapped wall with no
  pip within 2 m is a candidate of its own (`gns_only`, 979 of them over the
  pilot, 8.9 km of the 30.7 km mapped). Built the same day (then landslide step
  12, now exposure rw step 6 and ground step 4,
  `.agents/plans/placing-retaining-walls-on-pifs.md`): wall units (pifs and
  `gns_only` pieces of one property joined end to end, so one wall is not
  several), a prior from the height band, a rock cut and fill, a 0.95 floor
  on a unit GNS maps and 0.8 on a `gns_only` unit, and the claim and NZMM
  update below.
- [x] **Read each pif's cut and fill class into the prior, before deciding
  whether there is a wall** (built 2026-10-06 in the wall units, then landslide
  step 12, now exposure rw step 6, from ground step 5's
  `urban-slope-pif-cut-fill.parquet`; the ground map's
  fill no longer sets the prior).
  - **How the class is read.** Each pif is cut, fill, cut and fill, uncertain
    or natural, from how its crest and the foot of its face sit against a
    robust surface fitted to the ground off the faces.
  - **Walls are less likely on a cut, particularly in rock.** A cut face in
    rock often stands unsupported; Wellington greywacke cuts stand at 55 to
    75° [nzgs_2025_torlesse]. So the rock reduction applies only to a `cut`
    in rock over 2.5 m; a cut in soil keeps its prior.
  - **Fill and cut and fill take the higher prior.** These are the front of a
    platform and its back, which is where walls hold fill and soil (Nick
    Peters, below; [monteith_2020]).
  - **Natural ground is lowered, the rest left alone.** A natural face is a
    bank, not an earthwork (`BETA_NATURAL_WALL_FACTOR`, 0.5); uncertain and
    unknown (and every `gns_only` unit) keep the prior from siz and height.
  - **Limits.** The class is local: it cannot see a large gully fill, which
    reads as the surface itself, so the SLIDE fill bodies and the ground map
    still carry fill.
  - **Over the pilot:** of the pifs of 10 pips or more, 37% in soil-like
    ground and 31% in weak rock are cut.
  - **A unit takes the class of its longest pif**, or where pifs tie, the
    tied class most of its pifs hold. Every weight is `BETA_` judgement until
    **T-50**.
- [~] **Lower the chance of a wall on a rock cut**, from the 1:50,000 geology
  and the SLIDE materials through the ground map; Wellington greywacke cuts
  commonly stand at 55 to 75° and many long-standing ones are unsupported
  [nzgs_2025_torlesse]. Three changes, the first two built on the wall units
  (2026-10-05 and 2026-10-06, on the unit's wall height): read "cut" from ground
  step 5's class on the pif rather than from the ground map's modification, which
  is fill on most of the pilot; apply it only to cuts taller than the
  soil cover over the rock (height band 4 and up, over 2.5 m), usually under 1 m and 0.5 to 3 m on
  typical slopes [nzgs_2025_torlesse; hancox_2013_slope_types]; and remap
  SLIDE's mixed fill classes in the ground map, which today make 71% of the
  pilot fill and leave the factor almost nothing to act on (ground step 2 plan,
  phase 2).
- [x] **Draw the walls per exposure world**, on their own stream, separate
  from the earthquakes, because whether a wall exists is not something the
  earthquake decides.
- [~] **Give every wall on sloping land the polygon of ground it holds up**, so
  the two fail together through the wall's fragility (landslide steps 4 to 6);
  walls on flat land fail by shaking in `vul/shaking/rw`.
- [x] **Date each wall from its dwelling**, the QV rating roll's building age
  decade, with exposure step 8's title age where that is missing or the lot is much
  older (below); built 2026-10-06 (`gen_wall_age.py`), not yet run.
- [x] **Raise the wall probabilities on a claimed property from the walls
  its claim report lists** (**T-50**), holding a share of claims out for the
  cross-validation (Wall datasets, below; the lead, 2026-10-02). Built
  2026-10-05 on the wall units (exposure rw step 6); the count bounds hook it
  replaces is removed. The SME suburb
  estimate, the manual mapping, the remote sensing pilot and the ICNZ database
  will not be obtained (decided 2026-10-01).
- [ ] **Settle a replaced wall against the $50,000 per dwelling sub-cap**, plus
  GST, in the loss module.

### Engineering review advice (Nick Peters)

Assumptions to shape the priors, not rules; several are now points in the
wall units' prior (`wall-probability-points.csv`, 2026-10-07), the rest not
yet built. Advice from the sense check of 2026-10-05 is added at the end. The
literature each one now rests on is in brackets (review of 2026-10-02). Nick
is a co-author of NZGS Units 7C.2 and 2, so where those units agree with him
they are not independent of his advice.

- [~] **Do not assume steep means walled.** Greywacke slopes often have an
  exposed rock cut, as at Oriental Bay and Evans Bay. Supported: greywacke
  cuts are commonly 55 to 75° and many long-standing ones are unsupported
  [nzgs_2025_torlesse].
- [~] **Most walls hold fill and soil, not rock**, at the front of a section or
  in stepped platforms. Built as points: fill and cut and fill +5, a cut in
  soil +10, a cut in rock over 2.0 m −20. Consistent with the thin cover
  over the rock [nzgs_2025_torlesse; hancox_2013_slope_types] and with cut-and-fill
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
- [~] **Read age as a proxy for wall type**: pre-1970 walls mostly gravity
  masonry, 1970s and 1980s crib, timber pole and block, later ones engineered.
  In Canterbury wall type tracked era, and stone masonry, the oldest,
  collapsed most (about 18% very poor against under 6% for block, gabion and
  timber pole) [anderson_2015].
- [~] **Expect walls in new subdivisions.** Suburb-scale cut and fill followed
  the earth-moving machinery of the 1950s [lyndsell_2019]. Built as age
  points, from −10 before 1970 to +10 from 2005.
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

From the sense check of 2026-10-05, tested where a figure exists in
`post_processing/sme_validations/sme_statements.md` (**T-67**):

- [x] **Make a very tall face unlikely to be walled in full**: points −20 at
  5 to 8 m and −60 at 8 m and over (**T-75**).
- [ ] **Expect walls built for rock in unmapped alluvium to fail**, as in
  Whitby and Porirua, where the maps show greywacke (**T-92**, **L-57**).
- [ ] **Expect a property with one wall to have several**; the units are
  drawn independently (**L-56**).
- [ ] **Treat rock near the active faults as weaker** (**T-89**).

### Wall age, for the wall type

Step 8 (`steps/s8_infer_rwt_age/`) estimates the age per claim property, from
the dates of its titles and survey plan. The wall probability does not read it
yet.

- [x] Bin dwelling age into four periods, each opened by a change in how walls
  were designed or regulated: before 1970, 1970 to June 1992, July 1992 to
  2004, and 2005 on (`src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`).
- [~] Infer each property's bin from the issue date of its title, with rules
  for an infilled, converted or reissued title, set against Christchurch's open
  valuation roll (`s8_infer_rwt_age`).
- [ ] Take the dwelling age from the QV rating roll's building age decade
  (`landloss.io.qv_rating_roll`, supplied 2026-10-02 as sensitive data), with
  exposure step 8's title age second (the lead, 2026-10-06; rules in
  `.agents/plans/assigning-retaining-wall-types.md`). Failing both, the
  suburb's bin shares.

## Wall datasets: access and use

Three datasets record walls. All three are incomplete, each in its own way.
They are compared property by property in
`validations/rw_dataset_comparison.md` (2026-10-02). They agree no better than
chance (kappa 0.03 between GNS and NZMM), so none of them can be the truth.

| Dataset | Access | What it locates | Covers | What it misses |
|---|---|---|---|---|
| GNS SLIDE mapped walls [townsend_2020] | `get_gns_slide_morphology`, `Type == MAPPED_WALL_TYPE`; Koordinates 125308 (T+T instance), CC BY 4.0 | A line: 11,288 segments, 280 km | Urban Wellington City | Walls not visible from above; flags 21% of properties |
| T+T manually mapped walls | `get_tt_manual_walls`; Koordinates 125317 (T+T instance), T+T project data licence (NHC use only) | A line: 71 walls, 1.1 km | Wellington pilot only | Walls not visible from above; 4 of the 17 in the pilot DEM box duplicate a GNS wall |
| NHC NZMM land attributes | `get_nzmm_land_attributes`, `has_retaining_wall`; on T: under `SENSITIVE/`, put on LINZ polygons via `qv_rating_roll.linz_valuation_reference`; sensitive, aggregates only | A property, Y/N | Four councils | Flags 3% of properties; how it is filled is not documented |
| Claim reports | `extract_claim_reports.py` output (`reports.csv`, `walls.csv` per claims list), held on U: (`validations/config.py`); private, aggregates only | A property: count, construction, length and height per wall; no position | 1,551 claimed properties, mostly hill land, before the seven lists added 2026-10-06 (Tower, FMG, MAS, Ando, Chubb, QBE, loss adjusters) | Walls that do not matter to the claim |

How each can be used:

- [x] **GNS and T+T's manual walls are the only ones that locate a wall**, so
  they are the only evidence on a candidate line. The manual walls join the GNS
  walls in ground step 4, less any within 2 m of a GNS wall, and are
  used exactly as GNS walls are: evidence on a pif, the floor on `p_wall`, and
  `gns_only` candidates of their own (2026-10-08).
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
- [~] **Hold them out and cross-validate at the end**, once the face-based
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
  - Built 2026-10-05 as tables (exposure rw step 6,
    `table_wall_unit_checks.py`); nothing is calibrated on them.
- [x] **Let a claim report raise each wall's probability, not set a
  minimum count** (the lead, 2026-10-02). On a claimed property whose report
  lists n walls, each candidate line's `p_wall` is updated on the evidence
  that at least n of the property's lines are walls:
  P(line is a wall | at least n walls) = p × P(at least n − 1 of the other
  lines) / P(at least n of all lines), each from the Poisson-binomial of
  the lines' priors. Every line rises or stays, never falls, and the
  expected count rises towards n without being forced to it. A report listing
  no walls changes nothing, because it is not evidence of no wall. Built
  2026-10-05 on the wall units (exposure rw step 6), with NZMM true read as at
  least 2 walls, applied at 0.3 of its update and flagged unreliable.
  - It replaced the count bounds hook, removed on 2026-10-05, whose maximum
    lowered probabilities and whose scaling ignored the priors' shape.
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

- **The wall units moved into step 6 (2026-10-08).** The wall units, their
  probability and the draw per world, built in landslide step 12 until now, are
  built by `gen_wall_units.py` in this step, after `gen_wall_age.py`, and write
  to `temp/exposure/`. The pifs, the wall evidence and the cut and fill class
  they read are ground steps 3 to 5, which `gen_all.py` runs before exposure;
  the zones of each world's walls are landslide step 4. Pilot figures below
  dated before this are from the old step 12 and have not been rerun.
- **The wall type curves (2026-10-06).** Seven types, on the moderate damage
  state since moderate damage usually means replacement in a claim, each
  stored as the PGA at which 15% and 50% of walls are replaced
  (`src/landloss/io/assets/retaining-wall-type-fragility.csv`, read by
  `landloss.hazard.landslide.urban.wall_type_fragility`), with fill walls
  15% weaker and cut walls 15% stronger. Set beside the published curves and
  the Canterbury shares in `src/scripts/landloss/vul/research/fig_rw_type_fragility.md`.
  Nothing in the model reads them yet.
- **The pilot run of 2026-10-05 on the wall units** (then landslide step 12; the
  method is now in the exposure rw step 6 method file): 7,248 units, 3,458 expected walls (3,336 before the claim and NZMM
  update), 6,821 units on a claim. 67% of the GNS mapped wall length is within
  2 m of a pif, 97% with the `gns_only` units. The claim layer reaches 70
  claimed properties in the pilot, 21 held out; most hold-out values are under
  the suppression limit. In world 0, 3,466 walls are drawn and 2,019 insured.
  29% of the drawn units are under 1.5 m, against 54% in Canterbury
  [anderson_2015]. These counts predate the review fixes later that day
  (ground step 4 and exposure rw step 6 plans); rerun ground step 4 and then
  exposure rw step 6.
- **The wall height and the class prior (2026-10-06, not yet rerun).** A
  unit's `height_m`, which sets its size class and type band, is now the 80th
  percentile of its pifs' face drops from ground step 5, not the largest
  pip drop, which put too few walls under 1.5 m; it also sets the prior's
  height band. Its `p_wall` prior reads ground step 5's cut and fill class, and `wall_position` is fill on fill and cut
  and fill, else cut.
- `gen_wall_units.py` builds the wall units and draws them per world;
  `gen_wall_probability.py` reads the wall units, ties each to its claim
  (`claim_of_properties`); `gen_wall_population.py` takes which units are walls
  from that draw for the world (`draw_wall_population(walled=...)`) and draws each wall's
  age bin and type (2026-10-06, wall types plan).
- **The pilot run of 2026-10-02** (the candidate lines, removed 2026-10-08): 8,342 candidate lines, 2,921 walls drawn in
  world 0, 1,760 of them insured on 1,058 claims. Property boundaries were
  4,540 of the lines, 110 km. With the step test on the boundaries, road
  frontages and SLIDE earthwork edges, each trimmed to its stepped stretches,
  there are 8,832 candidates over 100 km, and the boundaries fall to 47.5 km
  in 4,494 shorter lines. Most sloping boundaries step somewhere along their
  length. This was rerun into a scratch folder only; the table is in the step 6
  method file.
- `gen_wall_age.py`, `gen_wall_units.py`, `gen_wall_probability.py` and
  `gen_wall_population.py` (run in that order by `gen_exposure`) are the scripts
  of step 6; their method file says
  what each does. The candidate lines and their `p_wall` were removed on
  2026-10-08. Every number is `BETA_` judgement.
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
- **Wall lines and properties from the wall units (2026-10-06).** A drawn
  wall's line is its unit's simplified line (at most 3 bends, no section
  under 3 m) and `length_m` is that line's length; a unit can cross property
  boundaries and is drawn once on its primary property, carrying
  `property_lengths_m` and `n_properties` for the loss side to count it on
  each property it enters by 1 m (vul rw status files, Next). Pilot world 0:
  1,940 walls drawn, 1,141 insured.

## Next

1. Review the pilot rerun of 2026-10-08 (`gen_all.py` over `wlg-pilot`, world
   0, earthquake 0, with the claim layer rebuilt that morning and the renamed
   wall types): 3,340 walls drawn on 5,747 candidates, 1,886 kept on insured
   land; 1,410 of them fail with their polygon and 1,718 carry a damage flag.
2. Rerun ground steps 4 and 5 and then exposure rw step 6 over the pilot, for the
   new wall height and class prior, and recheck the size classes and the
   share under 1.5 m against Anderson et al. [anderson_2015] (54%).
3. Landslide step 5's edge join is repaired: landslide steps 5 and 6 read
   landslide step 4's zones, which carry the wall unit ids, and the old step 7
   lines are removed (2026-10-08).
4. Add walls on the flat land: every wall unit is a face of sloping ground.
5. Tie a wall on a property boundary, which is one unit on each side, so one
   draw serves both, or count it on both.
6. Done 2026-10-08: the type shares (`beta-retaining-wall-type-shares.csv`)
   follow the 2026-10-07 review by Nick Peters and John Leeves (**T-118**).
   On 2026-10-08 the lead renamed `engineered` to
   `reinforced_concrete_post_1992` and `reinforced_concrete` to
   `reinforced_concrete_pre_1992` (**T-119**), and moved four wall type curves
   (wall types plan). The frontage multipliers
   are still to be reviewed (wall types plan, phase 4).
7. Bring subdivision age into `p_wall`.
8. Calibrate the wall units' weights on the held-out claims, GNS and the
   strata once **T-50** is complete (Wall datasets, above).
9. Record where the collected input datasets are held, so the inputs are
    reproducible.
10. Delete the two height-range constants once the loss owner has moved the
    pricing test (**I-14**).
11. Possibly correlate the wall draw between nearby units, so a wall makes its
    neighbours likelier while each unit keeps its `p_wall`: a Gaussian copula
    whose correlation reaches zero at a set range (spherical or Wendland),
    factored once per cluster of nearby units, so milliseconds per world. The
    claim update's assumption of independent units on a property is accepted
    (the lead, 2026-10-06). It changes every world's draw.
12. Add a background population of low walls, since the count is probably
    much too low; wall numbers were raised by about 40% in the meantime
    (**T-121**, 2026-10-07).
13. Compare the drawn type mix with the claim reports' (about 2,000 reports:
    53% timber, 16% concrete, 15% masonry or block, 6% crib) (**T-120**).

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
- Exposure step 8's age rules against Christchurch's open valuation roll
  (`validations/table_rwt_age_christchurch.py`).

## Open decisions

- The share of claims held out from the claim report update, and whether the
  held-out claims get the update in the loss run once the check is done.
- Ask NHC how the NZMM `RetainingWallInd` is filled. It flags 3% of
  properties, and claimed properties far more often than others.

- The road frontage multipliers: placeholders in the wall types plan, for
  Nick Peters to review. The type shares were settled on 2026-10-08
  (**T-118**).
- Whether repair cost scales with wall length or height, and the fixed costs per
  job (**T-32**).
- The rock-cut factor from height band 4 (over 2.5 m), the cut height taken
  to be through the soil cover, within the published 0.5 to 3 m.
- **T-11**, **T-20**: the council wall database and cut-and-fill models;
  **T-09**: the Auckland cut-and-fill tool.

## Future improvements

- The held improvements to the wall type draw: one draw per property, geology
  as a multiplier, large and frontage walls dated from the lot, and a
  retained-material shift (wall types plan, "Future improvements").

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
