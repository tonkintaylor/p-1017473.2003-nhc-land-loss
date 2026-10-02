# Shaking vulnerability, retaining walls: status

**Status:** A damage state is drawn on every flat-land wall from the
published wall curve on PGV, per exposure world and earthquake. Built and tested
on synthetic inputs; not yet run on the pilot since the change.

**Updated:** 2026-10-02

## Approach

- Express the vulnerability of a wall as a **fragility curve giving the
  probability of failure at a given ground motion**, and draw a damage state
  against it. The probability is intrinsic to the curve -- nominally identical
  walls differ in capacity and respond variably to the same shaking -- so it is
  never replaced by a comparison of demand against capacity, however well the
  hazard is resolved.
- Carry **two damage states only, no damage and replace**. Very few damaged
  walls are repaired in practice, so a middle state would hold almost nothing.
- Keep the **initial condition separate from the damage state**. Condition
  describes the wall before the earthquake and is an input to the fragility; the
  damage state is the outcome.
- Index the curves on the wall classes the exposure module draws — size class
  and initial condition — so the two modules share one vocabulary.
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
- The fragility is the published wall curve for the wall's size class and
  initial condition in `retaining-wall-fragility.csv` (Koutsoupaki et al.
  2023, one `unnamed` class), a PGA curve converted at the ratio of shaking
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

## Validation

- The realised share written off against the fragility it was drawn from, which
  is what the run prints each time.
- Modelled wall damage against observed retaining wall damage in Canterbury and
  Kaikōura, once a comparable population is available.

## Literature review (2026-10-02)

Part C of the second review read the wall curves against the 2,991
Canterbury walls of Anderson et al. (2015) [anderson_2015]. The detail is in
`.agents/context/retaining-wall-fragility.md`, "Literature review: the curves against Canterbury". What it proposes, all for the lead:

- **The curves fail far too many walls.** At the study's 1.0 to 1.7 g the
  Koutsoupaki curves fail 30 to 93% of walls. In the Port Hills, at the same
  PGA, about 10% were Very Poor over the whole sequence. The curves also have
  the height trend backwards: Canterbury's Very Poor share rose from 7% under
  1.5 m to 23% over 3.5 m.
- **Anchor the medians on Canterbury:** about 3.1, 2.8, 2.5 and 2.0 g by
  height band, at β 0.6 (ours). Keep Koutsoupaki only for the
  modern-to-poor ratio.
- **"Replace" is Very Poor** (collapse, or failure of more than 5 m² of
  face). Average and Poor, about a third of walls, are "none", with Poor
  added as the high case.
- **Name the six classes after Anderson's wall types**, whose Very Poor
  shares run from 18% (stone masonry) to 0% (MSE).

## Open decisions

- **The wall classes the curves are defined for are still unnamed.** The
  review proposes Anderson's six types (above).
  Before that review: This is the
  same open decision the retaining wall exposure module carries, and it blocks
  indexing the fragility by wall type; until then every wall takes the one
  `unnamed` class's curve for its size and condition.
- ~~**Whether the Canterbury land damage rates already include retaining wall
  damage** (**T-27**).~~ Settled for walls: the project lead ruled on
  2026-10-02 that a wall replaced by shaking on flat land and the liquefaction
  land damage on the same claim are not a double count, so both are priced.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
