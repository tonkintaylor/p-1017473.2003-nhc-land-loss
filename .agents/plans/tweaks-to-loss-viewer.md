# Plan: tweaks to the loss viewer page

Written 2026-10-14. The changes `loss_viewer.html` needs to follow
`.agents/plans/tweaks-to-property-damage.md`.

The split agreed between Maxim Millen and Perrie Gilbert on 2026-10-14:

- Maxim Millen makes every Python change: the model, loss s1 and the CSV
  writer `gen_viewer_data.py`.
- Perrie Gilbert makes these changes, in the page's JavaScript and HTML only.

A page without these changes still reads the new CSV. Each item names the
CSV columns it reads. The Python behind items 1 to 7 is built and tested in the
working tree, not yet committed or rerun, so the CSV columns below exist only
after the rerun in `.agents/plans/tweaks-to-property-damage.md`. A CSV from
before the rerun lacks them, and the page should read them as 0 or hide them.

1. **Show imminent ground** (property damage section 2). Add
   `imminent_evacuated_m2`, `reinundated_m2` and `reinundated_m3` to the
   claim's damage split, beside evacuated and inundated (T-123). The CSV
   writes all three at 4 dp, and 0 where a claim has none. A claim only
   imminent ground reaches is now a row, with `evacuated_m2` and
   `inundated_m2` at 0 and an empty `cause`, so the page must not drop a row
   for having no damaged ground when the imminent switch (item 2) is on.
   `reinundated_m2` is the same footprint as the inundated ground, so it is
   shown, not added to the area.
2. **A switch for imminent ground** (T-127), like the liquefaction switch,
   off by default. Python does not settle imminent ground (the lead,
   2026-10-14), so the CSV's costs and cap leave it out. The switch adds it
   to the total in the page:
   - `imminent_evacuated_m2` is a separate quantity from `damaged_area_m2`.
     The page decides how it enters the total. It is ground not already
     evacuated by any failure, and it may include ground that is only
     inundated.
   - `reinundated_m3` is the spoil that buries the failure's inundated ground
     again, as a volume for repair. **How it is charged must follow the
     Natural Hazards Insurance Act 2023**: whether, and how far, re-inundation
     of ground already damaged in the same event is covered. Confirm that
     against the Act before the switch adds it to the repair.

   With the switch off, the page's settlement must equal s1's, so
   `check_viewer_against_the_model` still holds.
3. **A filter option**: "Has imminent land".
4. **Where new walls came from** (property damage sections 3 and 4). Show
   `new_wall_from_mapped_count` against `new_wall_count` in the claim panel,
   for example "2 new walls, 1 on a mapped wall line". A new wall is now
   built on its polygon's mapped wall (drawn or not) over the stretch alongside
   the failure's evacuated ground, else sized from the slip. A slip that only
   buried the claim gets no new wall, only its clearing (`spoil_m3`), so
   `new_wall_count`, `new_wall_face_m2` and `new_wall_rate_excl_gst` fall to 0
   there. Where the page says every slip no damaged wall holds gets a wall (the
   "one per slip" label on the new-walls row of the claim panel), say "per
   slip that scarred the claim". `new_wall_from_mapped_count` is absent from a
   CSV from before, so hide the split then.
5. **Wall-caused ground** (property damage section 5). Show
   `wall_landslide_m2` in the damage split as ground that came down with the
   claim's own wall. Add a tooltip on "Retaining wall only" saying that this
   ground counts as wall damage, not landslide.
6. **Insured wall length** (property damage section 1). Where the claim panel
   shows wall length, say it is the length supporting the claim's insured
   land, not the whole wall. The page does not read a wall length column
   today, so this is wording where one is added.
7. **Damaged wall length** (property damage section 6). Show
   `damaged_wall_length_m` beside the wall length in the claim panel, so a
   wall clipped by a neighbour's slip reads as partly replaced. Show it to
   2 dp: a clip can be a few centimetres, though the wall is replaced over at least 3 m.
   The CSV writes it at 4 dp: the sum of the claim's damaged pieces' damaged
   lengths, before the 1 m margins, or the whole piece length where the run
   has no damaged lengths. A wall only buried by another failure is no longer
   damaged, so `has_damaged_wall`, `damaged_wall_count`, `wall_value_excl_gst`
   and `replacement_face_m2` fall for those claims, and the page's text and
   tooltips must not say a buried wall is replaced.
8. **Escalation default in the page** (property damage section 7). Replace
   the `liqEsc` input's `value="1.42"` with a placeholder such as
   `__LIQ_ESCALATION__`, which `write_viewer()` fills from
   `LIQ_COST_ESCALATION` when it builds the page. Stop reading
   `RAW[0].liq_escalation`, keeping it only as a fallback for older CSVs.
9. **Work out the dropped columns** (section 7), keeping the old columns as a
   fallback for older CSVs:
   - `has_new_wall` from `new_wall_count > 0`;
   - `has_crossing` from `damaged_crossing_count > 0`;
   - `has_liquefaction` from `liq_state > 1`;
   - the run's ejecta part from `liq_sva`: the SVA part when it is 1, the
     no-SVA part when it is 0, in place of `liq_inundated_cost_excl_gst`;
   - `has_damaged_wall` from `damaged_wall_count > 0`, but only once the two
     claims where they differ are explained (section 7).

   The filter list offers some of these by name (`has_new_wall`,
   `has_liquefaction`), so derive them on load and the filters keep working.
10. **`liq_method` as a code** (section 7). Map `area` and `lookup` to the
    two sentences the page shows today, and show an unrecognised value as it
    is.
11. **Say how a replaced wall is sized** (property damage section 3 and 6).
    Where the page describes the walls it replaces, say that a replaced wall
    keeps its own height and type, and is replaced over its damaged length plus
    1 m at each end, at least 3 m, with the margin counted once per wall. The
    cap values the same metres but never more than the wall's length. A slip no
    longer enlarges the wall it came with, and `wall_enlarged_for_landslide` is
    gone from the settlement. Neither the CSV nor the page ever carried it, so
    nothing in the page needs removing for it. Walls replaced and the cap fall
    sharply in value on rerun: walls keep their own heights, and a wall a
    neighbour's slip only clipped is replaced over the clip.
