# Plan: tweaks to property damage

Written 2026-10-14 for review by the lead (Maxim Millen). **Sections 1, 2,
3, 4, 5, 6 and 8 are done (built and tested in the working tree, not yet
committed, not yet rerun); 7 is to build, and comes last, on the rerun's
CSV.** Eight changes to what vul hands loss, and to the loss viewer's CSV:

| # | Change | Where | Rerun from |
| --- | --- | --- | --- |
| 1 | A wall's length goes to each claim over the stretch within its property that supports its insured land (within 2 m) (**done**) | exposure rw s6, vul s10 | exposure rw s6 |
| 2 | Imminent land: imminent evacuated and re-inundated ground, carried apart for the page to add (**built, not yet rerun**) | vul landslide land s3, vul s10, loss `ui/gen_viewer_data.py` | vul landslide land s3 |
| 3 | A replaced wall keeps its own height and type; every wall built gets 1 m at each end and at least 3 m (**built, not yet rerun**) | loss s0 and s1 | loss s0 |
| 4 | A slip's new wall is the mapped wall (drawn or undrawn) where there is one, else sized from the slip (**built, not yet rerun**) | exposure rw s6, vul s10, loss s1 | exposure rw s6 |
| 5 | "Retaining wall only" claims stop reading as Combination (**done**) | loss `ui/gen_viewer_data.py` | the viewer only |
| 6 | A wall clipped by another polygon's landslide is replaced over its damaged length only (T-158) (**built, not yet rerun**) | vul landslide rw s11, vul s10, loss s0 and s1 | vul landslide rw s11 |
| 7 | The viewer CSV: per-run repeats and derivable columns dropped, after 2, 3, 4 and 6 | loss `ui/gen_viewer_data.py` | the viewer only |
| 8 | A slip-sized wall's length comes from the failure's evacuated insured ground only, not its deposit (**done and approved**) | vul landslide land s3, vul s10, loss s1 | vul landslide land s3 |

Changes the HTML viewer needs are not made here. They are listed in
`.agents/plans/tweaks-to-loss-viewer.md` for Perrie Gilbert to make in the
page's JavaScript and HTML.

## Who owns what

Agreed between Maxim Millen and Perrie Gilbert on 2026-10-14: **Maxim Millen
makes every Python change, including in the loss module. Perrie Gilbert works
only in the viewer's JavaScript and HTML.**

- **This plan, all Python:**
  - exposure rw s6, vul landslide land s3 and
    vul s10 (`gen_property_damage.py`, `landloss.vul.loss_input`);
  - loss s0 (`loss/steps/s0_land_cover_cap/s0_gen_land_cover_cap.py`), loss
    s1 (`loss/steps/s1_settlement/s1_gen_settlement.py`) and, where a change
    needs it, `src/landloss/loss/`;
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

**Done (2026-10-14).** Built and tested in the working tree, not yet
committed. Not yet rerun: the numbers below are from the run before it.

**Before.** rw s6 gave each drawn wall one claim, the property holding most
of its line, and insured it only if it touched **that** claim's insured land
buffered by `RW_COVERAGE_BUFFER_M` (2 m, `landloss.exposure.coverage`). vul s10
then split each insured wall onto every claim property it crossed by at least
1 m (`split_walls_by_property`), whether or not the piece supported that
claim's insured land. The primary claim took the whole length less the other
pieces.

Two faults followed:

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

**A stretch on a shared boundary is shared equally** (the lead, 2026-10-14):
where a wall lies on the boundary between two claims' parcels and both have
insured land within 2 m, each takes half of that length. The 1 m minimum
applies to the share.

The 2 m support distance is the one the coverage test already uses. Today it
is applied to the whole wall against one claim. Here it is applied to each
stretch against the claim whose parcel the stretch lies in. A stretch on a
neighbour's parcel belongs to the neighbour, or to nobody, even where it sits
beside this claim's land. WU0017745 would be insured on 3f496134 only, at the
part of its 7.6 m on that parcel within 2 m of 3f496134-…-L01. Its 32.1 m on
47934545 is more than 2 m from that claim's insured land, so it belongs to no
claim.

**Built.**

1. rw s6 cuts every candidate wall's line into **insured stretches**
   (`cut_walls_to_insured_stretches` in `landloss.exposure.coverage`): the
   line inside each claim's parcel, clipped to that claim's insured land
   buffered by 2 m (`insured_support_regions`). The parcels are the ones
   `gen_unit_properties` (`landloss.hazard.landslide.wall_units`) already uses
   for `property_lengths_m`. For each world's drawn walls rw s6 writes:
   - `insured_lengths_m` on each wall: a list of `{claim_id, length_m}` beside
     `property_lengths_m`, longest first;
   - one row per wall and claim to
     `temp/exposure/wall-insured-stretches-wNNN-<extent>.geoparquet`, carrying
     `wall_line_id`, `rw_id`, `claim_id`, `length_m` and the stretch line.
     vul needs the stretch line to place a damaged stretch (section 6), because
     every `rw` piece keeps the whole wall's line.
2. A wall is insured when any stretch is at least 1 m (the threshold the split
   already used). Its `rw_id` is minted on the claim with the longest stretch.
   This replaces the primary-claim test, and the claimless drop (I-05) for a
   wall that does support insured land; only 2 of the walls I-05 dropped in
   Upper Hutt support insured land. Road and back-of-section walls supporting
   no insured land stay uninsured, and stay in `drawn-walls-wNNN` with a null
   `rw_id`.
3. vul s10's split (`split_walls_by_property`) reads `insured_lengths_m`
   instead of `property_lengths_m`, and raises for a population without it.
   Each piece is one claim's stretch at its own length. Stretches under 1 m are
   dropped. No piece takes a remainder, so length that supports no claim's
   insured land is not priced.
4. The contract does not change: still one `rw` row per piece, with
   `rw_length` (now the piece's insured length), `claim_id` and
   `parent_rw_id`. Step 0's wall value and s1's replacement both take the
   piece length, as before. Section 6 adds the damaged length beside it.

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
  less ground already evacuated by any failure (the lead, 2026-10-14). Ground
  only inundated is **not** subtracted: buried ground can still be imminent
  for evacuation, so it counts as imminent evacuated as well as re-inundated.
- **Re-inundated:** the failure's inundated ground, inundated again. It is
  the same footprint as the inundated area, so it is read off the failure's
  inundated ground on each land polygon, and only for a failure that has
  imminent land.

**Decided (the lead, 2026-10-14):**

- **2.1. Imminent evacuated ground is a separate quantity.** It is not added
  to the damaged area valued in the cap, and it does not size a slip's wall.
  It goes to the page on its own, and the page's JavaScript can add it to the
  total.
- **2.2. Re-inundation is a volume, for repair.** The re-inundated spoil is
  carried as a volume (area by depth) in the CSV. It is not priced in Python.
  How the page charges it must follow the Natural Hazards Insurance Act 2023,
  and that note is in `.agents/plans/tweaks-to-loss-viewer.md`.
- **2.3. No calibration.** The claim reports show earthquake claims carry
  almost no imminent risk (`vul/static_data_gen/claim_reports_status.md`),
  while the model gives most failures imminent land. The lead is content with
  the model's imminent land as it stands.

**Change.**

1. vul landslide land s3 measures both on each insured land polygon:
   - `imminent_evacuated_area_m2`: imminent ground less any ground already
     evacuated on the polygon by any failure, counted once. Inundated ground
     is not subtracted;
   - `reinundated_area_m2`, `reinundated_depth_m` and
     `reinundated_volume_m3`. The area is the union over failures, the volume
     is summed over failures at each one's own depth, and the depth is the
     volume divided by the area (the lead, 2026-10-14), so area by depth is
     always the volume, and is 0 where the area is 0.

   It also adds per-failure lists in the same order as the T-124 lists:
   `landslide_imminent_areas` and `landslide_reinundated_areas`.
2. vul s10 carries them on the land table as extra columns
   (`imminent_evacuated_area`, `reinundated_insured_area`,
   `reinundated_mean_depth`, `reinundated_volume` and the two lists), outside
   `LAND_COLUMNS`.
3. Imminent ground still sets no wall or crossing flag. A wall standing in
   imminent ground is not damaged.
4. **Loss s1 does not change.** It does not settle imminent ground, so no
   cost, cap or new wall moves. `PolicySettings.include_imminent_damage` stays
   unused in Python. The switch T-127 asks for is the page's.
5. The viewer CSV gains `imminent_evacuated_m2`, `reinundated_m2` and
   `reinundated_m3` per claim, read in `damaged_land()` the way
   `evacuated_m2` and `inundated_m2` are now. `settled_in_python` leaves them
   out, as the page does with its switch off, so the model check still holds.

**Built (2026-10-14).** In the working tree, not yet committed, not yet rerun.

1. `imminent_ground_per_property` and `with_imminent_ground` in
   `landloss.vul.landslide.land.damaged_area`, called from
   `gen_landslide_land_damage.py`, write `imminent_evacuated_area_m2`,
   `reinundated_area_m2`, `reinundated_depth_m` and `reinundated_volume_m3` on
   each polygon. Imminent evacuated ground is the imminent union less the union
   of ground evacuated by any failure, with inundated ground left in. The
   re-inundated area is the union of inundated ground of failures that have an
   imminent polygon, and the volume sums each failure's union area by its own
   first finite inundated depth. A polygon only imminent ground reaches gets a
   row of its own with no damaged ground.
2. `damaged_area_per_failure` adds `imminent_area_m2` and `reinundated_area_m2`,
   and `failures_per_property` writes `landslide_imminent_areas` and
   `landslide_reinundated_areas` in the order of `landslide_ids`. Their contract
   names are `LANDSLIDE_IMMINENT_AREAS_COLUMN` and
   `LANDSLIDE_REINUNDATED_AREAS_COLUMN` (`IMMINENT_LAND_LIST_COLUMNS`), kept out
   of `LANDSLIDE_FAILURE_COLUMNS`.
3. `loss_input.build_land_table` carries them (`IMMINENT_LAND_SOURCES`) as
   `imminent_evacuated_area`, `reinundated_insured_area`,
   `reinundated_mean_depth`, `reinundated_volume` and the two lists, only where
   s3 wrote them. The contract names are in `landloss.domain.loss_contract`
   (`IMMINENT_LAND_COLUMNS`). `LAND_COLUMNS` does not change.
4. `gen_viewer_data.py` (`imminent_by_claim`, `damaged_land`) writes
   `imminent_evacuated_m2`, `reinundated_m2` and `reinundated_m3` per claim at 4
   dp, zeros for a land table from before. A claim only imminent ground reaches
   is kept, with no damaged ground and an empty `cause`.
   `settled_in_python` does not read them.
5. Loss s0, s1, pricing and claims are untouched, and
   `include_imminent_damage` is still unused in Python.

**Deviations from the plan:**

- `IGNORED_LAND_CLASSES` is removed from `damaged_area`, with the step's "polygons
  measure nothing" print, because imminent ground is now measured.
- A failure that only imminent ground reaches on a polygon is not in
  `landslide_ids`, so its imminent ground is in the scalar total but not in the
  per-failure lists, which keeps them aligned.
- `damaged_area_per_failure` and `imminent_ground_per_property` require
  `landslide_id`, and raise without it.
- The step test that asserted an imminent-only polygon is absent from s3's
  output now asserts it is present with zero damaged ground and 400 m² imminent
  evacuated. It is not a case the lead approved by eye.

## 3. Walls sized from their own height, with one margin rule

**Today, in loss s1.**

- A damaged wall is replaced at its own `rw_type` (T-122 rule), `rw_height`
  and `rw_length`, but `replacement_wall_shape` enlarges it where it holds a
  slip: the taller of its own height and the slip's size-class height
  (`beta_wall_height_m`: 0.75, 1.75 or 2.75 m), and the longer of its own
  length and the slip's width (`landslide_wall_length_m`). In Upper Hutt
  world 0, earthquake 0, 1,895 of 2,807 damaged pieces are made taller this
  way and 1,637 longer.
- A slip held by no damaged wall gets a new wall sized by the slip's size
  class (`classify_landslide_wall_size` from its area and volume),
  `beta_wall_height_m` and `landslide_wall_length_m` (width plus
  `LANDSLIDE_WALL_MARGIN_M` = 2 m at each end, at least
  `MIN_LANDSLIDE_WALL_LENGTH_M` = 5 m), priced as timber pole.

**Decided (the lead, 2026-10-14):**

- **3.1. A replaced wall keeps its own height and type, and takes its
  length from the margin rule (3.2):** its damaged length plus 1 m at each
  end, at least 3 m. The margin rule replaces the slip as what sizes it, so
  `replacement_wall_shape`'s size-class height and slip-width length go. A
  replacement can be narrower than its slip. That is accepted: walls sit
  where the ground needs them, so most are wide enough.
- **3.2. One margin rule for every wall that is built.** 1 m is added at
  each end and the wall is at least 3 m long:

  replaced length = max(damaged length + 2 × 1 m, 3 m)

  It applies to a wall that failed over its whole length (its damaged length
  is its length), to a wall damaged over part of its length (section 6), and
  to a slip's new wall (section 4). `LANDSLIDE_WALL_MARGIN_M` becomes 1.0 and
  `MIN_LANDSLIDE_WALL_LENGTH_M` becomes 3.0 in `landloss.loss.pricing`, so
  the slip-sized fallback in section 4 takes the same numbers (the lead
  confirmed the fallback's change, 2026-10-14). Both stay marked as invented.
- **3.3. `wall_enlarged_for_landslide` is dropped** from the settlement.
  Only s1 reads it.
- **3.4. The margin is added once per wall** (the lead, 2026-10-14), to the
  sum of its damaged lengths. A wall damaged at two separate places, such as
  clipped by a failure at each end, still gets one 2 m margin, not one per
  damaged stretch.

**Change.**

1. Loss s1 sizes each damaged wall per wall, not per piece, so a wall shared
   by two claims gets the margin once. It groups the `rw` pieces on
   `parent_rw_id`, applies 3.2 to the sum of their damaged lengths
   (`rw_damaged_length`, section 6, or `rw_length` for a whole-length
   failure), and shares the replaced length out over the pieces in
   proportion to their damaged length.
2. Each piece is priced at its own `rw_height` and `rw_type` through
   `replacement_rate_excl_gst_nzd_per_m2` and `wall_face_area_m2`, as now.
   The replacement size class is the wall's own `rw_size`.
3. Loss s0 values the wall for the cap (its undepreciated value, up to the
   retaining wall sub-cap) over the damaged length plus the margin, but no
   longer than the wall itself (the lead, 2026-10-14):

   valued length = min(max(damaged length + 2 × 1 m, 3 m), wall length)

   It is worked per wall like step 1, where the wall length is the sum of its
   pieces' `rw_length` (its insured length, section 1), and shared over the
   pieces the same way. So the cap and the repair price the same metres,
   except that the cap never counts more wall than the property had: a wall
   that failed whole is valued over its length and replaced over its
   length + 2 m.
4. `attach_failures_to_walls` stays. It still decides which slips are held
   by a damaged wall (T-124) and types the viewer's claims (section 5).

**Built (2026-10-14).** In the working tree, not yet committed, not yet rerun.

1. `margin_rule_length_m` in `landloss.loss.pricing` is the one margin rule,
   `max(damaged + 2 × LANDSLIDE_WALL_MARGIN_M, MIN_LANDSLIDE_WALL_LENGTH_M)`,
   with the constants now 1.0 and 3.0, both still marked invented.
   `landslide_wall_length_m` calls it, so the slip fallback takes the same
   numbers.
2. `wall_lengths_by_piece` in `landloss.loss.claims` groups the pieces on
   `parent_rw_id` and returns each piece's `damaged_length_m`,
   `replaced_length_m` and `valued_length_m`: the margin is added once per wall
   to the sum of its damaged lengths, the valued length is capped at the sum of
   the pieces' `rw_length`, and both are shared over the pieces in proportion to
   their damaged length. A table without `rw_damaged_length`
   (`RW_DAMAGED_LENGTH_COLUMN`, an extra column outside `RW_COLUMNS`) uses
   `rw_length`. Pieces with no parent are each their own wall.
3. Loss s1 prices each piece at its own `rw_height` and `rw_type` over its
   replaced length (`wall_repair_by_claim`), and `replacement_wall_shape` keeps
   its own `rw_size`. The size-class height, the slip-width length and
   `wall_enlarged_for_landslide` are gone. Loss s0 values the wall over
   `valued_length_m` (`wall_udv_by_claim`). `attach_failures_to_walls` is
   unchanged.
4. `gen_calc_walkthrough.py` and the research script
   `table_clipped_wall_double_count.py` follow the new signatures.
   `loss_viewer.html` and the viewer CSV never read
   `wall_enlarged_for_landslide`, so no viewer change follows.

**Deviations from the plan:**

- `wall_lengths_by_piece` lives in `landloss.loss.claims`, not in a step,
  because s0 cannot import s1 and sections 4 and 6 reuse it.
- `replacement_wall_shape` and `wall_repair_by_claim` lost their `failures`
  argument, because nothing in them reads a slip now.
- A wall whose summed damaged length is 0 is replaced and valued over 0 m, not
  the 3 m minimum.
- A piece's damaged length is clipped to its `rw_length`.
- Old tests of slip enlargement and the enlarged flag were replaced, as 3.1 and
  3.3 remove that behaviour. None was a case the lead approved by eye.

**Measured (world 0, earthquake 0, wall face × rate before GST and on-costs,
with an earlier version of 3.2 that added 1 m in total):**

| Rule | Upper Hutt | Porirua |
| --- | --- | --- |
| Today | $65.8M | $88.2M |
| Own height, today's length | $48.8M | $64.9M |
| Today's height, own length + 1 m | $55.1M | $72.6M |
| Own height, own length + 1 m | $41.3M (−37%) | $53.8M (−39%) |

Most of the drop is height. Damaged walls' own heights are DEM face heights,
5th to 95th percentile 1.1 to 1.9 m, median 1.4 m. Today's size-class
enlargement lifts most of them to 1.75 or 2.75 m. Measure again with 3.2 as
decided once it is built.

## 4. A slip's new wall is the mapped wall where there is one

**Today.** A polygon whose wall unit was not drawn in this world takes the
no-wall fragility. All 59,233 `no_wall` polygons in Upper Hutt world 0 have
empty `wall_line_ids`, but 42,101 of them still carry their own unit as the
singular `wall_line_id` on `urban-slope-model-wNNN`
(`drawn_edge_walls` in `landloss.hazard.landslide.urban.fragility` keeps it).
So 3,710 of the 4,300 Upper Hutt slips that get a new wall can already reach
their undrawn unit through `landslide_id` → `slope_id` → `wall_line_id`, and
5,791 of 6,493 in Porirua. `wall-probability-<extent>` holds every
candidate's line, `face_height_m` and `length_m`, drawn or not. rw s6
already cuts every candidate into insured stretches (section 1), because the
cut depends on the line and the parcels and not on the world, but it writes
only the drawn walls' stretches. So when an unwalled polygon fails, loss
invents a wall from the slip's area, when the wall the ground needs has
already been mapped.

**Decided (the lead, 2026-10-14):**

- **4.1. The undrawn wall's type is not used.** Every new wall is priced as
  timber pole, as now, on the pile its height calls for. Only the height and
  length come from the line.
- **4.2. No hazard change and no per-world undrawn-walls file.** The link
  from a failure to its wall is the one the slope model already carries.
  vul s10 makes the join and hands the result to loss on the land table.
- **4.3. Fall back to today's slip-sized wall** where the failure has no
  mapped wall it can use: its polygon's pif is in no wall unit, it is a
  large-model landslide (no `slope_id`; 69 in Upper Hutt, 9 in Porirua), or
  its unit has no insured stretch on the failure's claim, so neither a drawn
  nor an undrawn wall there supports the claim's insured land.
- **4.4. Height from the mapped wall, length from the failure** (the lead,
  2026-10-14). The new wall is built only over the part of the claim's
  stretch alongside the failure's **evacuated** ground, not the whole
  stretch, plus 3.2's margin. This matches section 6 (a clipped wall is
  rebuilt over its damaged length) and section 8 (a slip-sized wall spans the
  scar, not the deposit). "Alongside" is the stretch line within
  `RW_COVERAGE_BUFFER_M` (2 m) of the failure's evacuated ground on the claim.
  Where that is under 1 m, the failure falls back to the slip-sized wall
  (4.3).

**Change.**

1. rw s6 writes the stretches it already cuts for every candidate, once per
   extent, to `wall-candidate-stretches-<extent>.geoparquet`
   (`wall_line_id`, `claim_id`, `length_m`, the stretch line). The per-world
   `wall-insured-stretches-wNNN` stays as it is for section 6.
2. vul s10, for each failure held by no damaged wall, reads its `slope_id`
   from the realisation, the polygon's `wall_line_id` from
   `urban-slope-model-wNNN`, then that unit's `face_height_m` from
   `wall-probability-<extent>` and its stretch on the failure's claim from
   `wall-candidate-stretches-<extent>`. A drawn wall that is insured on no
   claim is reached the same way, since the polygon's `wall_line_id` is that
   drawn line. It then cuts that stretch line to the part within 2 m of the
   failure's evacuated ground on the claim (4.4).
3. It hands loss per-failure lists on the land table, extra columns in the
   order of `landslide_ids`: `landslide_wall_heights`,
   `landslide_wall_lengths` (the length alongside the evacuated ground,
   before the margin) and `landslide_wall_sources` (`mapped wall` or `slip`).
   A `slip` failure carries no height or length, and loss sizes it as today.
4. Loss s1 sizes a `mapped wall` at its height and its length through 3.2,
   priced as timber pole. A `slip` failure, or a table without the lists, is
   sized from the slip as today, with 3.2's numbers.
5. Still one wall per failure (T-124). Two failures on one unit and one
   claim share it once: vul s10 gives them the union of their cut stretches,
   on the first failure, and 0 on the other.
6. `gen_viewer_data.py` adds `new_wall_from_mapped_count`, so the page can
   say how many new walls stand on a mapped line.
7. **A failure with no evacuated ground on the claim gets no new wall** (the
   lead, 2026-10-14; see section 8). Loss s1 builds new walls only for
   failures no damaged wall holds **and** whose `evacuated` area on the claim
   is more than 0. A failure that only buried the claim still costs its land
   repair (clearing the deposit), but no wall. A land table without the
   evacuated list measures each failure's whole ground as its evacuated
   ground (section 8's fallback), so an older table still builds a wall for
   it.

**Built (2026-10-14).** In the working tree, not yet committed, not yet rerun.

1. rw s6 (`gen_wall_population.py`, `candidate_stretches_path`) writes
   `temp/exposure/wall-candidate-stretches[-pilot].geoparquet` once per extent,
   with `wall_line_id`, `claim_id`, `length_m` and the stretch line, the output
   of `cut_walls_to_insured_stretches` over every candidate before the
   per-world filter.
2. `landloss.vul.mapped_walls` (new) holds `attach_mapped_walls`, called from
   `gen_property_damage.py`. It reads each failure's `slope_id`, the polygon's
   `wall_line_id` from the slope model, `face_height_m` from
   `wall-probability`, and the stretch from the candidate stretches.
   `alongside_length` cuts the stretch to within `RW_COVERAGE_BUFFER_M` of the
   failure's evacuated ground, which `evacuated_ground_per_failure` in
   `damaged_area` re-derives per claim and failure because s3 keeps only areas.
   `held_failure_keys` is the held-by-a-damaged-wall rule of
   `attach_failures_to_walls`, kept in vul because loss imports vul, and a test
   holds the two together.
3. The land table gains `landslide_wall_heights`, `landslide_wall_lengths`
   (before the margin) and `landslide_wall_sources` (`MAPPED_WALL` or
   `SLIP_WALL`), in the order of `landslide_ids`, outside `LAND_COLUMNS`. A
   failure falls back to `slip` on any case 4.3 names, and also where the
   mapped wall's height is not finite and above 0, or a damaged wall holds it.
4. Loss s1 (`land_repair_by_claim`, `landslide_failures`) builds a `mapped wall`
   at its height over `margin_rule_length_m` of its length, priced as timber
   pole on the pile its height calls for, with its size class from
   `classify_wall_size(height)`. A `slip` failure or an older table is sized
   from the slip. It builds a new wall only where no damaged wall holds the
   failure and its evacuated ground is more than 0, so a buried-only failure
   keeps its clearing (`spoil_by_claim`) and gets no wall. An older table
   without the evacuated list uses the whole ground, and a pooled older table
   the claim's `evacuated_area`.
5. Two failures on one unit and claim share one wall: the one with the most
   evacuated ground takes the union of the cut stretches and the other carries
   `mapped wall` with length 0, which loss reads as built on that wall. A
   failure whose evacuated ground has no area gets no mapped wall (loss builds
   none for it either). s1's `describe_failures` counts a failure that shares
   a wall on its own, not as a new wall.
6. `NEW_WALL_FROM_MAPPED_COLUMN` (`new_wall_from_mapped_count`) is carried onto
   the settlement and written by `viewer_rows` beside `new_wall_count`, as 0
   where a settlement written before the column exists lacks it.
   `settled_in_python` does not read it.

**Deviations from the plan:**

- The second failure of a shared wall is `mapped wall` with length 0, not
  `slip`, because loss could not otherwise tell it from a mapped wall.
- A failure on two polygons of one claim puts its mapped values on the first
  polygon's entry, and later entries carry the same height and source with
  length 0. Loss merges them by claim and `landslide_id`.
- vul s10 now reads the combined realisation again, and raises if
  `wall-candidate-stretches` is missing.
- s1 imports `classify_wall_size` from `landloss.exposure.rw.beta_population`
  to label the new wall's class.
- The section 8 test of a buried-only claim's minimum length is now a test of
  no wall and a kept clearing, as section 8 said it would be.

**Measured (world 0, earthquake 0, mapped failures only, before 3.2):** each
unit's whole line, plus 1 m, costs more than today's slip-sized wall: $73.8M
against $66.6M in Upper Hutt, and $121.1M against $97.1M in Porirua. Whole
lines run 3.2 to 36 m (5th to 95th percentile), median 14 m, against a median
of 11 m from slip area. That measured the whole line; under 4.4 only the
part alongside the evacuated ground is built, so measure again after the
rerun.

## 5. "Retaining wall only" claims read as Combination

**Done (2026-10-14).** Built and tested in the working tree, not yet
committed.

**Before.** `damaged_land()` in `loss/ui/gen_viewer_data.py` set
`has_landslide` for any claim with evacuated or inundated landslide ground.
A wall that failed with its polygon (`failed_with_polygon`) usually brings
that polygon's ground down on the same claim. So the claim carried both the
wall flag and the landslide flag, and the page typed it Combination. The
docstring recorded the gap: "whether a given landslide came from that wall or
from the slope is not yet passed down (T-124)". T-124 is now done. The land
table lists each failure with the wall it came with (`landslide_rw_ids`), and
the rw table ties each piece to its wall (`parent_rw_id`).

In world 0, earthquake 0, every bit of landslide ground on **985** Upper Hutt
claims and **1,509** Porirua claims came down with the claim's own damaged
wall. That is 138,398 of 359,286 m² and 189,718 of 472,564 m². Those claims
read as Combination today and would read as retaining wall only, before
liquefaction, crossings and the territorial authority filter are applied.

**Built, in `gen_viewer_data.py` only.**

1. `landslide_by_origin` splits each claim's landslide ground by failure.
   A failure is the claim's own wall's when one of the claim's damaged walls
   holds it, by `attach_failures_to_walls` from loss s1: the rule settlement
   uses to decide which slips get a new wall, which matches the failure's
   `landslide_rw_id` to `parent_rw_id` on the claim's damaged `rw` rows.
   `by_landslide` keeps a claim only if it has ground from a failure none of
   its own damaged walls holds. Ground from a neighbour's wall, or from a
   slope with no wall, still counts as landslide.
2. `cause` and `has_landslide` follow, so the page types the claim correctly
   with no HTML change.
3. A new column, `wall_landslide_m2`, holds the ground that came down with the
   claim's own walls, so the split stays visible. It is capped at the claim's
   pooled landslide ground, because two failures that buried the same ground
   each count it, so it is not additive with `evacuated_m2` or
   `inundated_m2`.
4. A land table without the T-124 lists, or a wall table without
   `parent_rw_id`, raises and names vul s10 to rerun (the lead, 2026-10-14).
   There is no fallback to the old rule.

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
  evacuated ground.** Its damaged length is measured, not assumed to be the
  whole wall.
- **Inundated ground does not damage a wall** (the lead, 2026-10-14). A wall
  that did not fail and is only buried by another failure's deposit has no
  cost: the deposit is cleared as land, and the wall is not replaced. So a
  wall carrying only `is_inundated` is not damaged.
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

   It writes `evacuated_length_m`, `inundated_length_m` (for information
   only), `damaged_length_m` (the evacuated length alone) and the damaged
   stretch line, `damaged_line` (the line inside evacuated ground). A wall
   damaged by shaking gets its whole line as `damaged_line`. A wall carrying
   only `is_inundated` gets an empty `damaged_line` and 0.

   **`is_inundated` stays on the wall, for information** (the lead,
   2026-10-14). It is in the shared contract for land, walls and crossings,
   crossings still price it, and the reviewer page, the QGIS build and the
   exec report maps show it. Loss stops costing it instead:
   `damaged_walls` in `landloss.loss.claims` counts a wall as damaged only
   when `is_damaged_by_shaking` or `is_evacuated` is set, not, as now, any of
   the three flags. `RW_COLUMNS` does not change.
2. vul s10 cuts each wall's `damaged_line` by the claim's insured stretch
   from `wall-insured-stretches-wNNN` (section 1). It writes the length as
   `rw_damaged_length` on each `rw` piece, an extra column outside
   `RW_COLUMNS`. A shaking-damaged piece takes its whole `rw_length`. An
   undamaged piece takes 0. A wall damaged only on a neighbour's stretch
   leaves this claim's piece undamaged, so it no longer carries the flags
   either. A landslide-damaged piece whose own damaged length is 0.1 m or
   less is also left undamaged, with 0 and no flags (6.3).

   **A damaged stretch on a shared boundary is shared the same way as the
   insured stretch** (section 1, and the warning in
   `cut_walls_to_insured_stretches`): the stretch lines of two claims on one
   boundary both hold that part of the wall, so a damaged part lying in k
   claims' stretches gives each 1/k of its length. Without this, a damaged
   boundary stretch is counted on both claims and a piece's damaged length
   can exceed its `rw_length`. The cut reuses `_shared_lengths` in
   `landloss.exposure.coverage` (made public) rather than a second rule, and
   a piece's `rw_damaged_length` never exceeds its `rw_length`.
3. Loss s1 replaces a landslide-damaged wall over its damaged length with
   section 3.2's margin, worked per wall over its pieces (section 3, step 1).
   A shaking-damaged piece's damaged length is its `rw_length`. A table
   without `rw_damaged_length` falls back to the whole length.
4. Loss s0 values a damaged wall for the cap over its damaged length plus
   the margin, no longer than the wall (section 3, step 3).
5. The viewer's `wall_value_excl_gst` and `replacement_face_m2` follow s0 and
   s1 without any change to how `gen_viewer_data.py` computes them. Its one
   change is a new column, `damaged_wall_length_m` per claim, for the page to
   show.

The Porirua wall would be replaced over 3.96 + 2 × 1 = 5.96 m, not 46 m (3.2).

**Decided (the lead, 2026-10-14):**

- **6.1. The margin is section 3.2's.** A landslide-damaged wall is
  replaced over its damaged length plus 1 m at each end, and at least 3 m,
  the same rule as a wall that failed whole and a slip's new wall. This
  replaces the earlier 6.1 (no margin, no minimum).
- **6.2. `absorbed` and `superseded` walls are measured.** These are walls
  taken by a larger urban failure, or by a large-model landslide. They set
  `is_evacuated` through their outcome, not their geometry, but their damaged
  length is still measured from the absorbing failure's ground, like any
  other landslide-damaged wall. The absorbing failure is another polygon, so
  step 1's "every failure other than its own polygon" already includes it.
- **6.3. A piece needs more than 0.1 m of damage.** The wall is flagged when
  more than 1 cm of its whole line is inside the ground, but split onto
  claims (step 2) one claim's share can be a few millimetres, and with the
  3 m minimum (3.2) that sliver would buy 3 m of wall. So a
  landslide-damaged piece counts as damaged only when its own damaged length
  is more than 0.1 m, a new constant `MIN_DAMAGED_PIECE_LENGTH_M` in vul.
  The test is applied in vul s10 before loss works the margin per wall, so a
  wall whose pieces all fall under it is not replaced. The wall flag's 1 cm
  tolerance (`WALL_INSIDE_TOLERANCE_M`) is unchanged. A shaking-damaged
  piece is not tested.

**Built (2026-10-14).** In the working tree, not yet committed, not yet rerun.
6.4 below is not built, as planned.

1. `measure_wall_damage` in `landloss.vul.landslide.flags`, called at the end of
   `wall_flags`, measures each flagged wall not damaged by shaking against the
   merged evacuated and inundated ground of every polygon but its own, with
   `WALL_INSIDE_TOLERANCE_M`. The step writes `evacuated_length_m`,
   `inundated_length_m`, `damaged_length_m` and `damaged_line`
   (`WALL_DAMAGE_COLUMNS`), now as a geoparquet with `damaged_line` as geometry.
   A shaking-damaged wall gets its whole line, an inundated-only wall an empty
   line and 0. Absorbed and superseded walls are measured like any other, so
   one whose absorbing ground covers no more than 0.1 m of its line is cleared
   as undamaged by vul s10's sliver rule. s11's `describe_damage` prints how
   many outcome-flagged walls that leaves, to read against the walls replaced
   before the change.
2. `damaged_walls` in `landloss.loss.claims` counts a wall as damaged only when
   `is_damaged_by_shaking` or `is_evacuated` is set. `is_inundated` stays on
   the wall.
3. vul s10 (`build_rw_table(stretches=...)`, `damaged_piece_lengths`) cuts
   `damaged_line` by the claim's stretch from `wall-insured-stretches-wNNN` and
   writes `rw_damaged_length` on each piece. `shared_lengths` in
   `landloss.exposure.coverage` is now public, and gives each of k claims 1/k of
   a damaged part on a shared boundary. A piece never exceeds its `rw_length`.
   A shaking piece takes its whole `rw_length`. A landslide-damaged piece with
   `MIN_DAMAGED_PIECE_LENGTH_M` (0.1 m) or less is undamaged and loses both
   flags.
4. Loss s0 and s1 take the damaged length through `wall_lengths_by_piece`
   (section 3), which forces the whole `rw_length` for a shaking-damaged piece.
5. `damaged_wall_length_by_claim` in `gen_viewer_data.py` writes
   `damaged_wall_length_m` per claim at 4 dp, the whole piece length where
   `rw_damaged_length` is absent. `wall_value_excl_gst` and
   `replacement_face_m2` follow s0 and s1 unchanged.

**Deviations from the plan:**

- A flat-land wall damaged only by the shaking step's state is unknown to s11,
  so s10 gives it its whole `rw_length` from its own shaking flag.
- A piece losing its flags under 6.3 loses `is_inundated` too; a piece of an
  inundated-only wall keeps it.
- The damaged part is placed on a claim's stretch with a 1 mm buffer
  (`DAMAGED_STRETCH_TOLERANCE_M`), because the stretch and the damaged line are
  float-rounded cuts of one line. Damage of exactly 0.1 m may land either side
  of the 6.3 test.
- `build_rw_table` without stretches writes no `rw_damaged_length`, so loss
  falls back to the whole length. The step always passes them and raises if
  `wall-insured-stretches` is missing.
- Tests that kept an inundated-only wall as damaged were changed to the lead's
  rule. None was a case approved by eye.

**Check after the rerun (the lead, 2026-10-14: done retrospectively):**

- **6.4. Double count against the slip's own new wall.** The slip that clips
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
  structure, the clipped stretch should hold the slip, at its own height
  and its replaced length (3.1 and 3.2). If they are different
  structures, both stay.

  s1 is built first with both kept, as written above. The check is run on the
  single rerun after 2, 3, 4 and 6 are built, and the counts and examples go
  to the lead then. If they show the same structure, s1 is changed so the
  clipped stretch holds the slip, and loss is rerun. Until then, the rerun's
  wall costs may count such claims twice; say so wherever its numbers are
  quoted.

## 7. The viewer CSV: drop repeats

**Today.** Some columns of the CSV written by `gen_viewer_data.py` are the
same on every row, or can be worked out from other columns. The Porirua CSV
(world 0, earthquake 0) is 17,750 claims and 5.04 MB. Values keep the
precision `viewer_rows()` and `main()` write them at now (areas to 4 dp,
dollars and rates to 6 dp). They are not rounded further (the lead,
2026-10-14).

**Build this section last, and update it first (the lead, 2026-10-14).**
Sections 2, 4, 5 and 6 add columns, now built in `gen_viewer_data.py`
(`imminent_evacuated_m2`, `reinundated_m2`, `reinundated_m3`,
`new_wall_from_mapped_count`, `wall_landslide_m2`, `damaged_wall_length_m`),
and section 1's stretches, with section 6's rule that inundated ground alone
does not damage a wall, may remove the `has_damaged_wall` mismatch below. Section 3
removes no CSV column (`wall_enlarged_for_landslide` was never in it). So once
2, 3, 4 and 6 are rerun, recount the columns, recheck the tables below on the new CSV and
measure its size, then build.

**Decided (the lead, 2026-10-14):** make every change in this section, with
`has_damaged_wall` dropped only once the check below is cleared.

The 38 columns of the CSV before this plan are each read by
`loss_viewer.html`. Four are the same on
every row, and the page reads them from the first row only (`RAW[0]`):

| Column | What it is | Change |
| --- | --- | --- |
| `liq_escalation` | the liquefaction cost escalation, 1.42, a loss constant (`LIQ_COST_ESCALATION`) that the page opens its control on | **Drop it from the CSV.** The page's control default is written into the page when `write_viewer()` builds it, from `LIQ_COST_ESCALATION`, the way `__VIEWER_VERSION__` is now. The CSV's liquefaction cost is in 2010/11 dollars before escalation, so the escalation describes the page's control, not the run. |
| `liq_sva` | whether the run priced ejecta clearing with the Student Volunteer Army | **Keep.** It describes how the run priced `liq_cost_excl_gst`, and one page reads CSVs from several runs and extents, so it cannot live in the page. |
| `liq_method` | how the run priced liquefaction, as a 67-character sentence on every row | **Keep, as a short code** (`area` or `lookup`). The page maps the code to its sentence. |
| `built_with` | the version the CSV was built with | **Keep.** The page warns when a CSV is older than the page, which needs this. |

Five can be worked out from other columns, and are dropped:

| Column | Same as | Check on Porirua |
| --- | --- | --- |
| `has_new_wall` | `new_wall_count > 0` | equal on every claim |
| `has_crossing` | `damaged_crossing_count > 0` | equal on every claim |
| `has_liquefaction` | `liq_state > 1` (worse than None) | equal on every claim |
| `liq_inundated_cost_excl_gst` | the SVA or no-SVA part, whichever `liq_sva` says | equal on every claim |
| `has_damaged_wall` | `damaged_wall_count > 0` | differs on 2 claims |

The two `has_damaged_wall` claims carry a damaged wall row but no repair cost
and no wall value: e099fb18… and f9112736…. Find out why before dropping the
column, on the CSV rebuilt after section 1. A damaged wall that costs nothing
is likely a zero-length piece, which section 1's stretches would remove. If
the two still differ, bring them to the lead and keep the column until it is
settled.

The page already falls back for an older CSV that lacks a column. Reading
the dropped columns from the others is page work, listed in
`.agents/plans/tweaks-to-loss-viewer.md`. `settled_in_python` reads
`has_damaged_wall` and `has_new_wall` too, so it works them out from the
counts the same way, and `check_viewer_against_the_model` still runs on the
CSV's rows as now. The CSV's size with the drops alone is not yet measured.

## 8. A slip-sized wall's length from its evacuated ground only

**Done and approved (the lead, 2026-10-14).** Built in the working tree, not
yet committed.

**Before.** `landslide_wall_length_m` took `A` as the failure's whole insured
ground on the claim: its evacuated and inundated pieces, unioned. A slip
whose deposit spread over the claim got a wall as wide as the deposit.

**Decided.** `A` is the failure's **evacuated** insured ground on the claim
alone. The wall goes across the scar; the deposit is cleared, not retained.

**Built.**

1. vul landslide land s3 (`damaged_area_per_failure`) measures each
   failure's evacuated ground on the polygon, and `failures_per_property`
   writes it as `landslide_evacuated_areas`, in the order of
   `landslide_ids`. The contract names it
   `LANDSLIDE_EVACUATED_AREAS_COLUMN`, kept out of
   `LANDSLIDE_FAILURE_COLUMNS` so an older land table still lists its
   failures.
2. vul s10 (`build_land_table`) carries the list to loss where s3 wrote it.
3. Loss s1 (`landslide_failures`) carries an `evacuated` area per failure,
   summed over a claim's polygons like `area`. `landslide_wall_length_m`
   takes it, for both a slip's new wall and the slip-width enlargement in
   `replacement_wall_shape`. The size class (height) still comes from the
   whole ground and the volume.
4. Fallbacks: a table with no evacuated list measures the wall off the whole
   ground, as before; pooled ground of an older table uses the claim's
   `evacuated_area`.

**Consequence, now decided.** As built, a claim that was only buried by a
slip from next door has zero evacuated ground, so its new wall is the
shortest one, `MIN_LANDSLIDE_WALL_LENGTH_M`, rather than one as wide as the
deposit. Before section 8 it got a wall as wide as the deposit: s1 gives
every failure no damaged wall holds a new wall, whatever its ground. **The
lead decided (2026-10-14) that it gets no wall at all**: inundated ground
alone needs no wall, only clearing. This is built with section 4 (step 7
there), and the section 8 test of a buried-only claim's minimum length is now
a test of no wall.

Section 4's slip-sized fallback and 3.2's margin numbers apply on top of
this, and are built.

## Reruns

| After | Rerun |
| --- | --- |
| 1 (built, not yet rerun) | exposure rw s6 onwards: all of hazard, because hazard s5 joins the drawn walls by `rw_id`, then vul and loss. For each of Lower Hutt, Upper Hutt and Porirua: `run_extent.ps1 -Module exposure -Step "rw s6, wall population"`, then loss, then the viewer. |
| 2 alone (built, not yet rerun) | vul landslide land s3 onwards: s3, vul s10, loss s1 and the viewer. Section 2 itself moves no s1 number, but rerunning s3 also writes section 8's evacuated lists, which do move s1's slip-wall lengths. So s1 must be rerun before the viewer, or `check_viewer_against_the_model` compares against a stale settlement. |
| 3 alone (built, not yet rerun) | loss s0 onwards, then the viewer |
| 4 alone (built, not yet rerun) | exposure rw s6 for `wall-candidate-stretches-<extent>`, then vul s10, loss and the viewer. Hazard need not be rerun: the link is the slope model's existing `wall_line_id`. |
| 6 alone (built, not yet rerun) | vul landslide rw s11 onwards, then loss and the viewer. It needs section 1's insured stretches, so in practice it comes with 1. |
| 5 (built) or 7 alone | `gen_viewer_data.py`. Section 5 needs a vul s10 land table with the T-124 lists and a wall table with `parent_rw_id`, and raises without them. |
| 8 (built, not yet rerun) | vul landslide land s3 onwards (s3, then vul s10, then loss and the viewer). Until s3 is rerun, loss uses the whole ground as before. |

Sections 1, 2, 3, 4, 6 and 8 are built but not yet rerun (5 needs only the
viewer). One rerun from exposure rw s6 covers every row above: exposure rw s6
(it writes `wall-candidate-stretches`, which vul s10 now requires, and the
insured stretches s11 needs), then hazard, vul landslide rw s11 and land s3,
vul s10, loss s0 and s1, and the viewer. Then the 6.4 check, then build
section 7 on that run's CSV.

## Tests

- Section 1 (written, `test_coverage.py`, `test_population.py`,
  `test_loss_input.py`): a stretch counts for a claim only when it is on the
  claim's parcel and within 2 m of its insured land; WU0017745 reproduced
  synthetically (insured on 3f496134 at its supporting stretch, nothing on
  47934545); a wall on a shared boundary is split equally; a wall supporting
  nothing stays uninsured; each vul s10 piece is its claim's insured stretch,
  length that supports no claim is dropped, and `RW_COLUMNS` is unchanged.
- vul rw s11 and s10 (written, `test_flags.py`, `test_wall_landslide_damage_step.py`,
  `test_loss_input.py`, `test_property_damage_step.py`): a wall clipped 4 m by a neighbour's evacuated ground
  gets `rw_damaged_length` 4 m on the piece that holds the clipped stretch and
  0 elsewhere. A shaking failure takes the whole length, even when it is also
  clipped. A wall inside only another failure's inundated ground keeps
  `is_inundated`, is not damaged, and costs nothing (loss `damaged_walls`
  skips it). A line along a failure's edge is not damaged.
  Overlapping failures
  count a stretch once. A damaged stretch on a shared boundary gives each
  claim half, and no piece's damaged length exceeds its `rw_length`. A piece
  whose own damaged length is 0.1 m or less is undamaged, and a wall whose
  pieces are all that short is not replaced.
- loss s0 and s1 (written, `test_claims.py`, `test_land_cover_cap_step.py`,
  `test_settlement_step.py`, `test_pricing.py`): a clipped wall is replaced over max(damaged length + 2 m,
  3 m) and valued over the same, capped at the wall's length, both worked per
  wall and shared over its pieces; a wall that failed whole is valued over its
  length and replaced over its length + 2 m;
  a slip no longer enlarges the wall it came with. A table without
  `rw_damaged_length` settles at the whole length.
- vul land s3 (written, `test_damaged_area.py`,
  `test_landslide_land_damage_step.py`, `test_loss_input.py`): imminent evacuated excludes ground already evacuated by any
  failure but keeps ground that is only inundated; re-inundated equals the
  failure's inundated ground, its volume is each failure's area by its own
  depth, its depth is the volume over the area; a failure with no imminent
  polygon gives zero.
- viewer CSV (written, `test_viewer_data_step.py`): imminent and re-inundated ground are carried, and the model
  check still passes because `settled_in_python` leaves them out.
- vul s10 (written, `test_mapped_walls.py`, `test_property_damage_step.py`,
  `test_damaged_area.py`; exposure rw s6's candidate stretches in
  `test_population.py`): a failure held by no damaged wall takes its polygon's mapped
  wall's height, and the length of its stretch on the failure's claim within
  2 m of the failure's evacuated ground; under 1 m alongside, or no stretch,
  is `slip`; a large-model failure is `slip`; two failures on one unit and
  claim share one wall; the per-failure lists stay aligned with
  `landslide_ids`.
- loss s1 (written, `test_settlement_step.py`): a `mapped wall` is priced as timber pole at its height and
  max(length alongside + 2 m, 3 m); a `slip` failure, or a table without the
  lists, is sized from the slip with the 1 m and 3 m numbers; a failure with
  no evacuated ground on the claim gets no new wall but keeps its land
  repair.
- Section 5 (written, `test_viewer_data_step.py`): a claim whose only ground
  came with its own wall is typed retaining wall only; one with a neighbour's
  slip as well is Combination; a land table without the T-124 lists, or a
  wall table without `parent_rw_id`, raises.
- viewer CSV (to write with section 7): the dropped columns are gone, `settled_in_python` works them
  out from the counts, and the model check still passes.
- Section 8 (written, `test_damaged_area.py`, `test_loss_input.py`,
  `test_settlement_step.py`): each failure's evacuated area is measured and listed;
  vul s10 carries it; a new wall's length and a replacement's slip-width
  follow the evacuated ground; a buried-only claim gets the minimum length
  (changed to no wall and a kept clearing with section 4, step 7); a table without the list
  measures off the whole ground.

## Status files to update when built

- `src/scripts/landloss/exposure/rw/status.md`
- `src/scripts/landloss/vul/landslide/land/status.md` (T-45 measured)
- `src/scripts/landloss/vul/landslide/rw/status.md` (T-158 fixed), and the
  s11 method file
- the s10 method file
- `src/scripts/landloss/loss/status.md` (s1's new-wall sizing; imminent
  ground reaches the viewer CSV but s1 does not settle it)
- register: a task for each section (Maxim Millen). Note on T-127 and T-122
  that their Python side is Maxim Millen's under the 2026-10-14 split, and
  their page side is Perrie Gilbert's.
