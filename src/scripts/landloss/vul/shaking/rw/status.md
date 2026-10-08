# Shaking vulnerability, retaining walls: status

**Status:** A damage state is drawn on every flat-land wall from the
published wall curve on PGV, per exposure world and earthquake. Built and tested
on synthetic inputs; not yet run on the pilot since the change.

**Updated:** 2026-10-08

## Approach

- Express the vulnerability of a wall as a **fragility curve giving the
  probability of failure at a given ground motion**, and draw a damage state
  against it. The probability is intrinsic to the curve -- nominally identical
  walls differ in capacity and respond variably to the same shaking -- so it is
  never replaced by a comparison of demand against capacity, however well the
  hazard is resolved.
- Carry **two damage states only, no damage and replace**. Very few damaged
  walls are repaired in practice, so a middle state would hold almost nothing.
- Keep the **wall type separate from the damage state**. The type describes
  the wall before the earthquake and picks its fragility; the damage state is
  the outcome.
- Index the curves on the wall type the exposure module draws and the wall's
  height class (under 2 m, or 2 m and over),
  so the two modules share one vocabulary, and read "replace" at the
  moderate damage state, since moderate damage usually means replacement in
  a claim; a fill wall's curve is 15% weaker
  and a cut wall's 15% stronger (the lead, 2026-10-06;
  `.agents/plans/assigning-retaining-wall-types.md`).
- Draw **flat-land walls only**. A wall on sloping land fails with the urban
  failure polygon on whose edge it stands, drawn by landslide step 9; see
  `hazard/landslide/status.md`.
- Evaluate every curve on **PGV**, converting a curve published on PGA at the
  wall's own PGV/PGA ratio, so walls and urban slopes share one intensity
  measure.
- Emit **states, not costs**. A written-off wall is priced from its
  undepreciated value in the loss module, against the $50,000-per-dwelling
  sub-cap.

## Loss contract

What this module owes the retaining wall table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Carry `rw_id` through from the exposure module.
- [x] Carry `claim_id`, `rw_size` (`size_class`) and `rw_length` (`length_m`).
- [x] Supply `is_damaged_by_shaking`, from `damage_state` for flat-land walls;
  sloping walls take it from the urban wall outcome (vul/landslide/rw s11).
- [x] Carry coordinates. The wall line is written as the geometry.
- [x] Supply `is_evacuated` and `is_inundated`, from vul/landslide/rw s11.

## Where it is now

- `steps/s9_wall_damage_state/` reads the world's wall population, keeps the
  flat-land walls, samples shaking step 5's PGV at each line midpoint, and
  draws a state per wall on the vulnerability stream with the world appended,
  to `temp/vul/wall-damage-state-wNNN-rNNN[-pilot].geoparquet` with the curve,
  the site class and the PGV/PGA ratio recorded on every row.
- The fragility is the wall type curve for the wall's type and height class
  (under 2 m, or 2 m and over, from `height_m`; the lead, 2026-10-07, in place
  of the size class) in `retaining-wall-type-fragility.csv` (Koutsoupaki et al. 2023, moderate
  damage state), scaled by its fill or cut position, a PGA curve converted at
  the ratio of shaking
  step 3's PGV to the TS1170.5 PGA at the midpoint
  (`landloss.vul.shaking.fragility.wall_failure_probability`). The flat 70%,
  `BETA_FAILURE_PROBABILITY`, now serves the culverts and bridges only.
- `draw_damage_states()` takes probabilities rather than computing them, so the
  published curves replace the constant without the step changing.
- The step is tested end to end on synthetic inputs. The earlier pilot run, on
  the flat 70% and PGA, is superseded and the step has not been rerun.

## Next

1. Run the step over the pilot after exposure step 6 and shaking steps 2, 3
   and 5, and record the counts in the method file.
2. Rerun once the Vs30 model varies the site class, so the curves have something
   to discriminate on.
3. Decide whether walls on the same property fail independently. They are drawn
   that way, and two walls on one slope are not independent.
4. In the loss calculation, a wall that crosses property boundaries counts
   as a wall on each property it enters by at least 1 m, with the length of
   wall inside that property (2 m of wall in a property means that property
   has a wall 2 m long), not once on its primary property at its whole
   length (the lead, 2026-10-06). Exposure rw step 6's drawn walls and wall
   population carry `property_lengths_m` (each property's id and length,
   from landslide step 12's wall units, `BETA_MIN_WALL_LENGTH_IN_PROPERTY_M`)
   and `n_properties` for this; today each wall is one row on its primary
   property with `length_m` its whole simplified line. The loss module is
   not changed yet.
5. Read each wall's curve from its type, height class and fill or cut
   position (`wall_type_failure_probability`), once exposure draws the type
   (wall types plan, phase 3).

## Validation

- The realised share written off against the fragility it was drawn from, which
  is what the run prints each time.
- Modelled wall damage against observed retaining wall damage in Canterbury and
  Kaikōura, once a comparable population is available.

## Literature review (2026-10-02)

Part C of the second review read the wall curves against the 2,991
Canterbury walls of Anderson et al. (2015) [anderson_2015]. The detail is in
`.agents/context/retaining-wall-fragility.md`, "Literature review: the curves against Canterbury". What it proposes, all for the lead:

- **The Koutsoupaki curves are kept** (the lead, 2026-10-02). They
  overpredict against Christchurch: at the study's 1.0 to 1.7 g they fail 30
  to 93% of walls, where about 10% of Port Hills walls were Very Poor at the
  same PGA over the whole sequence. The report states this as a known
  conservatism.
- **"Replace" is Very Poor** in the comparison (collapse, or failure of more
  than 5 m² of face). Average and Poor, about a third of walls, are "none".
- **Name the six classes after Anderson's wall types**, whose Very Poor
  shares run from 18% (stone masonry) to 0% (MSE). Infer each wall's type
  from its age and the claim reports (the lead, 2026-10-02).

## Open decisions

- **The wall type shares by age and height.** Seven types, each with its own
  curve, stored as the PGA at which 15% and 50% of walls are replaced
  (`landloss.hazard.landslide.urban.wall_type_fragility`; the lead,
  2026-10-06, two height classes from 2026-10-07). Exposure step 6 now draws
  the type, but its shares are placeholders for Nick Peters to review; his
  advice at the sense check of 2026-10-05 bears on them (exposure rw status).
  The types were renamed after the NHC costing tool's wall rows on 2026-10-08
  (`retaining-wall-types.csv`), adding `reinforced_concrete`, mostly the old
  mass concrete walls, on the Fs 1.2 curve with the height effect switched
  (proposed, for the lead to confirm with the rest of the wall performance).
- ~~**Whether the Canterbury land damage rates already include retaining wall
  damage** (**T-27**).~~ Settled for walls: the project lead ruled on
  2026-10-02 that a wall replaced by shaking on flat land and the liquefaction
  land damage on the same claim are not a double count, so both are priced.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
