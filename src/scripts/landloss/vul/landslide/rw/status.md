# Retaining walls, landslide: status

**Status:** The three contract flags are written per wall per exposure world
and earthquake, from the urban wall outcome and the landslide polygons. Not yet
run on the pilot.

**Updated:** 2026-10-02

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Flag each insured wall whose line runs inside the realisation's evacuated
  or inundated polygons for more than `WALL_INSIDE_TOLERANCE_M` (0.01 m), and
  flag the two kinds of ground separately because the policy settles them
  differently. A line that only touches a polygon's edge is not flagged.
- [x] Map each sloping wall's outcome from landslide step 9 onto the flags,
  failed with its polygon as damaged by shaking and absorbed or superseded as
  evacuated, OR-ed with the line flags, because the wall fails with the
  polygon on whose edge it stands.

## Loss contract

What this module owes the retaining wall table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Supply `is_evacuated`.
- [x] Supply `is_inundated`.
- [x] Key every row on `rw_id`, carrying `claim_id` beside it.
- [x] Supply `is_damaged_by_shaking` for sloping walls, from the urban wall
  outcome; flat-land walls take theirs from vul/shaking/rw s9.

## Where it is now

- `steps/s11_wall_landslide_damage/` reads the world's wall population, the
  combined large and urban realisation of landslide step 9 and its urban wall
  outcome table, and writes
  `temp/vul/wall-landslide-damage-wNNN-rNNN[-pilot].parquet`, one row per wall,
  flat-land and sloping alike, with `slope_id`, `outcome` and the three flags
  (`landloss.vul.landslide.flags.wall_flags`). It is tested end to end on
  synthetic inputs and has not been run on the pilot.
- Landslide step 9 supersedes failed urban polygons only, and only where they
  share more than `SHARED_GROUND_TOLERANCE_M2` of ground with a large slide
  (`supersede_by_large`, contract decision 35, built). A sloping wall whose
  polygon did not fail is not marked superseded; where a large slide reaches it,
  this step's line flag catches it.
- Vul step 10 writes the loss tables per exposure world and earthquake, and
  keeps the deprecated `loss_input_path` resolving world 0 (contract section
  3.15, decision 37, built), so the loss module's reads work and read world 0.
  Moving the loss module's calls onto worlds is the loss owner's, register task
  **T-65**.

## Next

1. Run the step over the pilot after exposure step 6 and landslide steps 8, 1
   and 9.

## Validation

Not yet defined.

## Open decisions

Not yet defined.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
