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
- [x] Map each sloping wall's outcome from landslide step 6 onto the flags,
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
  combined large and urban realisation of landslide step 6 and its urban wall
  outcome table, and writes
  `temp/vul/wall-landslide-damage-wNNN-rNNN[-pilot].parquet`, one row per wall,
  flat-land and sloping alike, with `slope_id`, `outcome` and the three flags
  (`landloss.vul.landslide.flags.wall_flags`). It is tested end to end on
  synthetic inputs and has not been run on the pilot.
- Landslide step 6 supersedes failed urban polygons only, and only where they
  share more than `SHARED_GROUND_TOLERANCE_M2` of ground with a large slide
  (`supersede_by_large`, contract decision 35, built). A sloping wall whose
  polygon did not fail is not marked superseded; where a large slide reaches it,
  this step's line flag catches it.
- Vul step 10 writes the loss tables per exposure world and earthquake, and
  the loss module reads them the same way (**T-66**, done 2026-10-07).

## Next

1. Run the step over the pilot after exposure step 6 and landslide steps 5, 3
   and 6.
2. In the loss calculation, a wall that crosses property boundaries counts
   as a wall on each property it enters by at least 1 m, with the length of
   wall inside that property (2 m of wall in a property means that property
   has a wall 2 m long), not once on its primary property at its whole
   length (the lead, 2026-10-06). Exposure rw step 6's drawn walls and wall
   population carry `property_lengths_m` (each property's id and length,
   from exposure rw step 6's wall units, `BETA_MIN_WALL_LENGTH_IN_PROPERTY_M`)
   and `n_properties` for this; today each wall is one row on its primary
   property with `length_m` its whole simplified line. The loss module is
   not changed yet.

## Validation

Not yet defined.

## Open decisions

Not yet defined.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
