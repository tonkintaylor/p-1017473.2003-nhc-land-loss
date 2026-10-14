# Retaining walls, landslide: status

**Status:** The three contract flags are written per wall per exposure world
and earthquake, from the urban wall outcome and the landslide polygons, with the
length of each flagged wall inside landslide ground (T-158, 2026-10-14). Not yet
run on the pilot.

**Updated:** 2026-10-14

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
- [x] A wall's own polygon sets neither its evacuated nor its inundated flag
  (the lead, 2026-10-13): the wall's line now sits at the toe and its evacuated
  polygon is cut there, so its own failure is the outcome route's. On the pilot
  (world 0, earthquake 0) the walls flagged evacuated fall from 424 to 190 and
  those flagged inundated from 798 to 137; the walls with any flag (one
  replacement each) stay at 1,121.

- [x] Measure the length of each flagged wall inside other polygons' evacuated
  and inundated ground, and write the damaged stretch (the lead, 2026-10-14):
  a wall damaged in shaking takes its whole line, one carrying only
  `is_inundated` is not damaged, and absorbed and superseded walls are measured
  like any other.

## Loss contract

What this module owes the retaining wall table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Supply `is_evacuated`.
- [x] Supply `is_inundated`.
- [x] Key every row on `rw_id`, carrying `claim_id` beside it.
- [x] Supply `is_damaged_by_shaking` for sloping walls, from the urban wall
  outcome; flat-land walls take theirs from vul/shaking/rw s9.
- [x] Supply the damaged stretch as `damaged_line`, with `evacuated_length_m`,
  `inundated_length_m` and `damaged_length_m`. Vul step 10 turns it into
  `rw_damaged_length` per claim's piece, outside `RW_COLUMNS`.

## Where it is now

- `steps/s11_wall_landslide_damage/` reads the world's wall population, the
  combined large and urban realisation of landslide step 6 and its urban wall
  outcome table, and writes
  `temp/vul/wall-landslide-damage-wNNN-rNNN[-pilot].parquet`, one row per wall,
  flat-land and sloping alike, with `slope_id`, `outcome` and the three flags
  (`landloss.vul.landslide.flags.wall_flags`), and the measured damage
  (`measure_wall_damage`: `evacuated_length_m`, `inundated_length_m`,
  `damaged_length_m` and the `damaged_line` geometry, so the file is now a
  geoparquet). It is tested end to end on synthetic inputs and has not been
  run on the pilot.
- Landslide step 6 supersedes failed urban polygons only, and only where they
  share more than `SHARED_GROUND_TOLERANCE_M2` of ground with a large slide
  (`supersede_by_large`, contract decision 35, built). A sloping wall whose
  polygon did not fail is not marked superseded; where a large slide reaches it,
  this step's line flag catches it.
- Vul step 10 writes the loss tables per exposure world and earthquake, and
  the loss module reads them the same way (**T-66**, done 2026-10-07).

## Next

1. Run the step over the pilot after exposure step 6 and landslide steps 5, 3
   and 6, then check the clipped walls against the slip's own new wall (6.4 in
   `.agents/plans/tweaks-to-property-damage.md`).
2. ~~In the loss calculation, a wall that crosses property boundaries counts
   as a wall on each property it enters by at least 1 m.~~ Superseded
   2026-10-14: a wall counts on each claim over its insured stretch, the line
   inside the claim's property and within 2 m of its insured land, shared
   equally on a boundary (exposure rw step 6's `insured_lengths_m`; vul
   step 10 splits on it).
3. ~~Pass the loss module which landslide polygons are retaining wall
   failures, and which polygons on one property are separate failures
   needing separate walls (**T-124**, 2026-10-07).~~ Done 2026-10-13: land
   step 3 lists each failure on a polygon with the wall it failed with, and
   loss step 1 holds each slip with its own wall.

A wall failed in shaking is replaced over its whole length, up to 50 m a
segment, with no partly failed state. This was accepted on 2026-10-07 as an
assumption justified by the size of the earthquake (**L-64**). A wall damaged
only by landslide ground is replaced over its damaged length (2026-10-14).

## Validation

Not yet defined.

## Open decisions

Not yet defined.

## Future improvements

- A wall partly evacuated or inundated by another polygon's landslide is
  replaced over its whole length (**T-158**). The line flag is set when more
  than 1 cm of the line lies inside the ground, and loss replaces any flagged
  wall in full. So a standing wall clipped by a neighbouring failure is
  priced as though it fell. In the Porirua run of 2026-10-11 (world 0,
  earthquake 0), wall `4eef7bbf-bfe3-40c4-91eb-a29515837562-RW01` is 46 m long
  and stood on its own polygon, SP0003419. It lies 3.96 m inside the evacuated
  ground of the neighbouring polygon SP0003334, where the two overlap by
  13 m², yet it was replaced in full at $225k
  (`temp/qgis/wall-neighbour-slide/wall_neighbour_slide.qgs`).
  **Fixed in code 2026-10-14, pending rerun** (section 6 of
  `.agents/plans/tweaks-to-property-damage.md`). A wall failed in shaking is
  damaged over its whole length. One damaged by landslide ground is damaged
  only over the stretch inside it, measured here and written as
  `evacuated_length_m`, `inundated_length_m`, `damaged_length_m` and
  `damaged_line`, merged first so overlapping failures count a stretch once,
  and an absorbed or superseded wall is measured like any other. Inundated
  ground alone no longer damages a wall: `is_inundated` stays on the wall, and
  loss stops costing it. Vul step 10 cuts the damaged line by each claim's
  insured stretch into `rw_damaged_length`, and loss replaces the wall over its
  damaged length plus 1 m at each end, at least 3 m, counted once per wall. The
  check for a double count against the slip's own new wall (6.4) is still to
  run after the rerun. Same-scale polygons that overlap make most of these
  clips, so making them tile removes the cause; the lengths only make what is
  left proportionate.
- Trimming and filling a walled polygon at its wall line leaves thin slivers
  (**T-159**). Hazard landslide step 4 (`wall_trim.py`, `zone_alignment.py`)
  leaves narrow spikes where the polygon's old outline meets the end of the
  wall line. In the Upper Hutt run of 2026-10-13 (world 0), 2,516 of the 16,872
  trimmed evacuated polygons hold more than 0.1 m² of ground narrower than
  0.5 m (36 hold more than 0.5 m²), against none of the 59,916 untrimmed ones.
  Example: SP0024301 on wall unit WU0017745, with a spike at about
  (1768590, 5441186). The fix belongs in the trim: clear anything narrower than
  about 0.5 m after the cut and fill, for example by a small negative then
  positive buffer, before the imminent zone is rebuilt.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
