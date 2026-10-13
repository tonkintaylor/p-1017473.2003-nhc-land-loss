# Plan: tweaks to property damage

Written 2026-10-14 for review by the lead (Maxim Millen). **Draft: nothing is
built.** Six changes to what vul hands loss, and to the loss viewer's CSV:

| # | Change | Where | Rerun from |
| --- | --- | --- | --- |
| 1 | A wall's length goes to each claim over the stretch within its property that supports its insured land (within 2 m) | exposure rw s6, vul s10 | exposure rw s6 |
| 2 | Imminent land: imminent evacuated and re-inundated ground | vul landslide land s3, vul s10, loss s1 | vul landslide land s3 |
| 3 | Walls sized by height and type, not by size class | vul s10 (sizing), loss s1 (pricing) | vul s10 |
| 4 | A slip's new wall is the undrawn wall where there is one | hazard landslide s5 and s6, exposure rw s6, vul s10 | exposure rw s6 |
| 5 | "Retaining wall only" claims stop reading as Combination | loss `ui/gen_viewer_data.py` | the viewer only |
| 6 | A wall clipped by another polygon's landslide is replaced over its damaged length only (T-158) | vul landslide rw s11, vul s10, loss s0 and s1 | vul landslide rw s11 |

Changes the HTML viewer needs are not made here. They are listed in
`.agents/plans/tweaks-to-loss-viewer.md` for Perrie Gilbert to make in the
page's JavaScript and HTML.

## Who owns what

Agreed between Maxim Millen and Perrie Gilbert on 2026-10-14: **Maxim Millen
makes every Python change, including in the loss module. Perrie Gilbert works
only in the viewer's JavaScript and HTML.**

- **This plan, all Python:**
  - exposure rw s6, hazard landslide s5 and s6, vul landslide land s3 and
    vul s10 (`gen_property_damage.py`, `landloss.vul.loss_input`);
  - loss s1 (`loss/steps/s1_settlement/s1_gen_settlement.py`) and, where a
    change needs it, `src/landloss/loss/`;
  - the viewer's CSV (`loss/ui/gen_viewer_data.py`).
- **Perrie Gilbert, JavaScript and HTML only:** `loss/ui/loss_viewer.html`,
  from the list in `.agents/plans/tweaks-to-loss-viewer.md`. This plan does not
  edit the page.
- The viewer CSV is built from s1's settlement, and
  `check_viewer_against_the_model` checks it against s1. So a change that moves
  a cost lands in s1 and the CSV together, and the check must pass before the
  CSV is written.
- New data still goes to loss as **extra columns**, outside `LAND_COLUMNS`
  and `RW_COLUMNS`, the way the T-124 failure lists were added. Each loss
  function keeps its fallback for a table without them, so an older run's
  tables still settle.

## 1. Insured wall length by the land it supports

**Today.** rw s6 gives each drawn wall one claim, the property holding most
of its line, and insures it only if it touches **that** claim's insured land
buffered by `RW_COVERAGE_BUFFER_M` (2 m, `landloss.exposure.coverage`). vul s10
then splits each insured wall onto every claim property it crosses by at least
1 m (`split_walls_by_property`), whether or not the piece supports that
claim's insured land. The primary claim takes the whole length less the other
pieces.

Two faults follow:

- **A wall supporting a neighbour's insured land is insured on neither.**
  Upper Hutt world 0 example: WU0017745 is 39.7 m long, with 32.1 m on
  property 47934545 and 7.6 m on 3f496134. It is given to 47934545, whose
  insured land is 15.65 m away, so it is dropped. It touches
  3f496134-…-L01 (0 m). Over world 0, earthquake 0, this leaves 88 damaged
  walls (1,553 m) uninsured in Upper Hutt and 113 (2,435 m) in Porirua. For
  scale, 2,077 and 2,828 insured walls are damaged. Damage here is judged with
  vul's own rule, because vul only scores insured walls.
- **Length is priced on claims it does not support.** A piece on a property
  whose insured land it does not reach is still kept and priced, and the
  primary piece always takes the remainder.

**The rule (the lead, 2026-10-14).** A stretch of wall belongs to a claim
when it is **both**:

- **within the claim's property**, its LINZ parcel; and
- **supporting the claim's insured land**: within `RW_COVERAGE_BUFFER_M`
  (2 m) of it.

The 2 m support distance is the one the coverage test already uses. Today it
is applied to the whole wall against one claim. Here it is applied to each
stretch against the claim whose parcel the stretch lies in. A stretch on a
neighbour's parcel belongs to the neighbour, or to nobody, even where it sits
beside this claim's land. WU0017745 would be insured on 3f496134 only, at the
part of its 7.6 m on that parcel within 2 m of 3f496134-…-L01. Its 32.1 m on
47934545 is more than 2 m from that claim's insured land, so it belongs to no
claim.

**Change.**

1. rw s6 cuts every drawn wall's line into **insured stretches**: the line
   inside each claim's parcel, clipped to that claim's insured land buffered
   by 2 m. The parcels are the ones `gen_unit_properties`
   (`landloss.hazard.landslide.wall_units`) already uses for
   `property_lengths_m`. rw s6 writes:
   - `insured_lengths_m` on each wall: a list of `{claim_id, length_m}` beside
     `property_lengths_m`;
   - one row per wall and claim to
     `temp/exposure/wall-insured-stretches-wNNN-<extent>.geoparquet`, carrying
     `wall_line_id`, `rw_id`, `claim_id`, `length_m` and the stretch line.
     vul needs the stretch line to place a damaged stretch (section 6), because
     every piece today keeps the whole wall's line.
2. A wall is insured when any stretch is at least 1 m (the threshold the split
   already uses). Its `rw_id` is minted on the claim with the longest stretch.
   This replaces the primary-claim test, and the claimless drop (I-05) for a
   wall that does support insured land. Only 2 such Upper Hutt walls exist.
   Road and back-of-section walls supporting no insured land stay uninsured
   and stay in `drawn-walls-wNNN`.
3. vul s10's split reads `insured_lengths_m` instead of `property_lengths_m`.
   Each piece is one claim's stretch at its own length. Stretches under 1 m are
   dropped, as pieces under 1 m are now. A primary piece no longer takes the
   remainder, so length that supports no claim's insured land is not priced.
4. The contract does not change: still one `rw` row per piece, with
   `rw_length` (now the piece's insured length), `claim_id` and
   `parent_rw_id`. Step 0's wall value and s1's replacement both take the
   piece length, as now. Section 6 adds the damaged length beside it.

The geometry is all in rw s6 already (the line, the parcels and the insured
land), which is why the stretches are cut there.

## 2. Imminent land: imminent evacuated and re-inundated

**Today.** Hazard landslide s6 writes an `imminent land` polygon for most
failures: 26,094 against 27,400 evacuated in Upper Hutt world 0,
earthquake 0. vul landslide land s3 ignores it
(`IGNORED_LAND_CLASSES = (IMMINENT,)` in `landloss.vul.landslide.land.damaged_area`).
So the land table, the loss settlement and the viewer have no imminent
ground. `PolicySettings.include_imminent_damage` already exists in loss. T-127
asks for imminent ground to be carried through loss with a switch to leave it
out.

**The two kinds of imminent ground, as agreed 2026-09-25 (T-45):**

- **Imminent evacuated:** the imminent polygon's ground upslope of the
  evacuated polygon, behind a regressed headscarp. It is the imminent polygon
  less the failure's evacuated ground.
- **Re-inundated:** the failure's inundated ground, inundated again. It is
  the same footprint as the inundated area, so it is read off the failure's
  inundated ground on each land polygon, and only for a failure that has
  imminent land.

**Change.**

1. vul landslide land s3 measures both on each insured land polygon:
   - `imminent_evacuated_area_m2`: imminent ground less any ground already
     evacuated or inundated on the polygon by any failure, counted once;
   - `reinundated_area_m2` and `reinundated_depth_m`.

   It also adds per-failure lists in the same order as the T-124 lists:
   `landslide_imminent_areas` and `landslide_reinundated_areas`.
2. vul s10 carries them on the land table as extra columns
   (`imminent_evacuated_area`, `reinundated_insured_area`,
   `reinundated_mean_depth` and the two lists), outside `LAND_COLUMNS`.
3. Imminent ground still sets no wall or crossing flag. A wall standing in
   imminent ground is not damaged.
4. Loss s1 settles them under `include_imminent_damage` (T-127), as the
   lead decides in 2.1 and 2.2. It writes the imminent area and cost as their
   own settlement columns, so the page's switch can take them out.
5. The viewer CSV gains `imminent_evacuated_m2` and `reinundated_m2` per
   claim, read in `damaged_land()` the way `evacuated_m2` and `inundated_m2`
   are now. Once s1 settles imminent ground, the CSV also gains its cost and
   area, and `settled_in_python` follows, so the model check still holds.

**Decisions for the lead:**

- 2.1. Does imminent evacuated ground add to the damaged area valued in the
  cap, to the ground the slip's wall is sized on, or both?
- 2.2. Is re-inundated spoil charged again at its own depth, or is
  re-inundation an area only?
- 2.3. The claim reports show earthquake claims carry almost no imminent risk
  (`vul/static_data_gen/claim_reports_status.md`), while the model gives most
  failures imminent land. Calibrate before it is switched on in reported
  numbers?

## 3. Walls sized by height and type

This section reads "using the wall type and wall height" as follows (confirm,
**decision 3.1**). Wherever a wall's size is known in metres, size and price
it from its height and type, not from the three-band size class.

**Today, in loss s1.**

- A damaged wall is replaced at its own `rw_type` (T-122 rule) and
  `rw_height`. But a slip it holds can enlarge it only through the slip's
  size class: `beta_wall_height_m(slip_size)`.
- A slip held by no damaged wall gets a new wall. It is sized by the slip's
  size class (`classify_landslide_wall_size` from its area and volume), with
  `beta_wall_height_m` for height and `beta_wall_face_area_m2` for face, and
  priced as timber pole.

**Change.**

1. vul s10 works out each failure's **required wall** and hands it to loss on
   the land table as per-failure lists (`landslide_wall_heights`,
   `landslide_wall_lengths`, `landslide_wall_types`, `landslide_wall_sources`).
   The values are:
   - the failure's own wall where it came with one (the replacement, as now);
   - else the undrawn wall (section 4);
   - else a height from the failed polygon's own face. That is the slope
     model's `face_height_10m`, carried onto the realisation row by
     `slope_id`, rather than a size class.
2. Loss s1 prices each required wall from its height and
   type through `replacement_rate_excl_gst_nzd_per_m2` and
   `wall_face_area_m2`, in place of the size-class path. Where the lists are
   missing, it falls back to the size class, as now.
3. The viewer's `new_wall_face_m2` and `new_wall_rate_excl_gst` follow s1
   unchanged. `gen_viewer_data.py` adds `new_wall_from_undrawn_count`, so the
   page can say how many new walls came from a mapped line.

## 4. A slip's new wall is the undrawn wall where there is one

**Today.** A polygon whose wall unit was not drawn in this world takes the
no-wall fragility and loses its unit: all 59,233 `no_wall` polygons in Upper
Hutt world 0 have empty `wall_line_ids`. Exposure draws a type for every
candidate but writes it only for drawn walls. `wall-probability-<extent>`
holds every candidate's line, `face_height_m`, `length_m` and
`property_lengths_m`. So when an unwalled polygon fails, loss invents a wall
from the slip's area, when the wall the ground needs has already been
mapped.

**Change.**

1. Hazard landslide s5 writes `candidate_wall_line_id` on every polygon
   whose element belongs to a wall unit, drawn or not, from the same
   member-pif mapping s4 uses (`gen_element_walls`). Hazard s6 carries it on
   each failure. The fragility, the trim and the outcome are unchanged.
2. rw s6 writes `undrawn-walls-wNNN-<extent>.geoparquet` per world: every
   candidate not drawn, with the `wall_type` and `age_bin` the type draw
   already gave it, `height_m` (`face_height_m`), `length_m`, the line, and
   `insured_lengths_m` (section 1). A wall that was drawn but is insured on no
   claim is in `drawn-walls-wNNN` and is treated the same way.
3. vul s10 sizes a slip held by no damaged wall from its candidate wall,
   where it has one:
   - height: the line's `height_m`;
   - type: the line's drawn type, through the T-122 replacement rule;
   - length: the line's insured length on this claim, extended to the slip's
     width (`landslide_wall_length_m`) where the slip is wider, as a
     replacement is now.

   `landslide_wall_sources` records `undrawn wall`, `uninsured wall` or
   `slip`.
4. Still one wall per failure (T-124). Two failures on one candidate wall and
   one claim share it once, at the longer length.

**Decision 4.1.** Use the undrawn wall's own drawn type through T-122, or
price every new wall as timber pole as now and take only the height and
length from the line?

## 5. "Retaining wall only" claims read as Combination

**Today.** `damaged_land()` in `loss/ui/gen_viewer_data.py` sets
`has_landslide` for any claim with evacuated or inundated landslide ground.
A wall that failed with its polygon (`failed_with_polygon`) usually brings
that polygon's ground down on the same claim. So the claim carries both the
wall flag and the landslide flag, and the page types it Combination. The
docstring records the gap: "whether a given landslide came from that wall or
from the slope is not yet passed down (T-124)". T-124 is now done. The land
table lists each failure with the wall it came with (`landslide_rw_ids`), and
the rw table ties each piece to its wall (`parent_rw_id`).

In world 0, earthquake 0, every bit of landslide ground on **985** Upper Hutt
claims and **1,509** Porirua claims came down with the claim's own damaged
wall. That is 138,398 of 359,286 m² and 189,718 of 472,564 m². Those claims
read as Combination today and would read as retaining wall only, before
liquefaction, crossings and the territorial authority filter are applied.

**Change, in `gen_viewer_data.py` only.**

1. `by_landslide` keeps a claim only if it has landslide ground from a
   failure whose `landslide_rw_id` is **not** one of the claim's own damaged
   walls (`parent_rw_id` on its damaged `rw` rows). Ground from a
   neighbour's wall, or from a slope with no wall, still counts as landslide.
2. `cause` and `has_landslide` follow, so the page types the claim correctly
   with no HTML change.
3. A new column, `wall_landslide_m2`, holds the ground that came down with the
   claim's own walls, so the split stays visible.
4. A land table without the T-124 lists falls back to today's rule.

`has_landslide` keeps its name and type, so a page built before this change
still reads the CSV.

## 6. A wall clipped by another landslide: replace the damaged length only

This is **T-158**. It was parked because its fix needed loss. Under the
2026-10-14 split it is ours.

**Today.** vul landslide rw s11 (`landloss.vul.landslide.flags.wall_flags`)
sets `is_evacuated` or `is_inundated` on a wall when more than 1 cm of its line
lies inside another polygon's evacuated or inundated ground. Loss then
replaces every flagged wall over its whole length.

Example: Porirua, 2026-10-11, world 0, earthquake 0. Wall
`4eef7bbf-bfe3-40c4-91eb-a29515837562-RW01` is 46 m long and stood on its own
polygon, SP0003419. 3.96 m of it lies inside the evacuated ground of its
neighbour SP0003334, and it was replaced in full at $225k.

**The rule (the lead, 2026-10-14):**

- **A wall that fails in shaking is damaged over its whole length.** That
  covers a flat-land wall whose shaking damage state is replace, and a
  sloping wall whose own polygon failed through it (`failed_with_polygon`).
  Both reach loss as `is_damaged_by_shaking`.
- **A wall damaged by landslide ground is damaged only over the length inside
  that ground.** Its damaged length is measured, not assumed to be the whole
  wall.
- **Shaking wins:** a wall with both is damaged over its whole length.
- Each claim then takes the damaged length that falls on **its own insured
  stretch** (section 1): within its property and within 2 m of its insured
  land.

**Change.**

1. vul landslide rw s11 measures, for every wall carrying `is_evacuated` or
   `is_inundated` and not `is_damaged_by_shaking`:
   - the stretch of its line inside the evacuated ground and inside the
     inundated ground of every failure other than its own polygon;
   - each kind of ground merged first, so overlapping failures count a stretch
     once;
   - the same inside tolerance as the flag (`WALL_INSIDE_TOLERANCE_M`), so a
     line running along a failure's edge is not damaged.

   It writes `evacuated_length_m`, `inundated_length_m`,
   `damaged_length_m` (the union of the two) and the damaged stretch
   line, `damaged_line`. A wall damaged by shaking gets its whole line as
   `damaged_line`.
2. vul s10 cuts each wall's `damaged_line` by the claim's insured stretch
   from `wall-insured-stretches-wNNN` (section 1). It writes the length as
   `rw_damaged_length` on each `rw` piece, an extra column outside
   `RW_COLUMNS`. A shaking-damaged piece takes its whole `rw_length`. An
   undamaged piece takes 0. A wall damaged only on a neighbour's stretch
   leaves this claim's piece undamaged, so it no longer carries the flags
   either.
3. Loss s1 replaces a landslide-damaged piece over `rw_damaged_length`, which
   already carries the margin (6.1), never more than the piece's `rw_length`. A
   shaking-damaged piece is replaced over its `rw_length`, as now. A table
   without `rw_damaged_length` falls back to the whole length.
4. Loss s0 values a damaged piece for the cap over the same damaged length,
   so the cap and the repair price the same stretch of wall.
5. The viewer's `wall_value_excl_gst` and `replacement_face_m2` follow s0 and
   s1 with no change to `gen_viewer_data.py`. The CSV gains
   `damaged_wall_length_m` per claim for the page to show.

The Porirua wall would be replaced over 3.96 m plus the margin, not 46 m.

**Decided (the lead, 2026-10-14):**

- **6.2. `absorbed` and `superseded` walls are measured.** These are walls
  taken by a larger urban failure, or by a large-model landslide. They set
  `is_evacuated` through their outcome, not their geometry, but their damaged
  length is still measured from the absorbing failure's ground, like any
  other landslide-damaged wall. The absorbing failure is another polygon, so
  step 1's "every failure other than its own polygon" already includes it.

**Open:**

- **6.1. The margin.** A partly damaged wall is not rebuilt over exactly the
  damaged metres:
  - the new section is tied into sound wall at each end;
  - below a certain length a job is not worth mobilising for.

  Loss already has both numbers for a slip's new wall:
  `LANDSLIDE_WALL_MARGIN_M = 2.0` added at each end, and
  `MIN_LANDSLIDE_WALL_LENGTH_M = 5.0` as the floor (`landloss.loss.pricing`,
  lines 310 and 311). Its docstring calls both invented. The proposal is to
  reuse them, so there is one pair of numbers to revise:

  replaced length = min(wall length, max(damaged length + 2 × 2 m, 5 m))

  The Porirua wall would then be replaced over 3.96 + 4 = 7.96 m, not 46 m.
  The margin is applied to the whole wall, not to each claim's piece, or two
  claims sharing a damaged stretch would each add 4 m. So vul extends
  `damaged_line` 2 m along the wall at each end, and to 5 m if shorter, never
  past the wall's ends, **before** splitting it onto claims (step 2). The
  extension falls on whichever claim's stretch it reaches. The constants are
  imported from `landloss.loss.pricing`, not copied. Choose:
  - (a) reuse 2 m and 5 m as above (recommended);
  - (b) separate figures for a partly damaged existing wall;
  - (c) no margin: the damaged length only.

**Checks before settling the numbers:**

- **6.3. Double count against the slip's own new wall.** The slip that clips
  a wall usually also gets a new wall of its own on the claim. Under T-124 a
  slip whose wall is not one of the claim's own is held by a new wall. So one
  claim may be charged twice for the same ground: once to rebuild the clipped
  stretch, and once for a new wall to hold the slip.

  Check it on the Porirua example (`4eef7bbf…-RW01`, clipped by SP0003334)
  and on a sample of claims carrying both a clipped piece and a new wall,
  using the QGIS project `temp/qgis/wall-neighbour-slide/wall_neighbour_slide.qgs`.
  For each, record:
  - whether the new wall and the clipped stretch stand on the same line;
  - the two lengths;
  - the cost of each.

  Report how many claims carry both, and the money involved, in each of Lower
  Hutt, Upper Hutt and Porirua for world 0, earthquake 0. If they are the same
  structure, the clipped stretch should hold the slip, sized against it as a
  replacement is today (`replacement_wall_shape`). If they are different
  structures, both stay. Bring the counts and the examples to the lead before
  s1's pricing is built.

## Reruns

| After | Rerun |
| --- | --- |
| 1 or 4 | exposure rw s6 onwards: all of hazard, because hazard s5 joins the drawn walls by `rw_id`, then vul and loss. For each of Lower Hutt, Upper Hutt and Porirua: `run_extent.ps1 -Module exposure -Step "rw s6, wall population"`, then loss, then the viewer. |
| 2 or 3 alone | vul landslide land s3 onwards, then loss and the viewer |
| 6 alone | vul landslide rw s11 onwards, then loss and the viewer. It needs section 1's insured stretches, so in practice it comes with 1. |
| 5 alone | `gen_viewer_data.py` |

Build 1, 4 and 6 together so the pipeline is rerun once.

## Tests

- rw s6: a stretch counts for a claim only when it is on the claim's parcel
  and within 2 m of its insured land. WU0017745 is the case to reproduce
  synthetically: insured on 3f496134 at its supporting stretch, nothing on
  47934545. A wall supporting nothing stays uninsured.
- vul s10: each piece is its claim's insured stretch, length that supports no
  claim is dropped, and `RW_COLUMNS` is unchanged.
- vul rw s11 and s10: a wall clipped 4 m by a neighbour's evacuated ground
  gets `rw_damaged_length` 4 m on the piece that holds the clipped stretch and
  0 elsewhere. A shaking failure takes the whole length, even when it is also
  clipped. A line along a failure's edge is not damaged. Overlapping failures
  count a stretch once.
- loss s0 and s1: a clipped piece is valued and replaced over its damaged
  length plus the margin, never more than the piece. A table without
  `rw_damaged_length` settles as today.
- vul land s3: imminent evacuated excludes ground already evacuated or
  inundated, re-inundated equals the failure's inundated ground, and a failure
  with no imminent polygon gives zero.
- vul s10: the required wall comes from the failure's own wall, then the
  candidate wall, then the polygon's face, and the per-failure lists stay
  aligned with `landslide_ids`.
- viewer: a claim whose only ground came with its own wall is typed
  retaining wall only; one with a neighbour's slip as well is Combination.

## Status files to update when built

- `src/scripts/landloss/exposure/rw/status.md`
- `src/scripts/landloss/vul/landslide/land/status.md` (T-45 measured)
- `src/scripts/landloss/vul/landslide/rw/status.md` (T-158 fixed), and the
  s11 method file
- the s10 method file
- `src/scripts/landloss/loss/status.md` (s1's new-wall sizing and imminent
  ground)
- register: a task for each section (Maxim Millen). Note on T-127 and T-122
  that their Python side is Maxim Millen's under the 2026-10-14 split, and
  their page side is Perrie Gilbert's.
