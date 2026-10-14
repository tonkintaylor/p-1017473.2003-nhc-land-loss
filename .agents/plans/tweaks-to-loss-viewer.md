# Plan: tweaks to the loss viewer page

Written 2026-10-14. The changes `loss_viewer.html` needs to follow
`.agents/plans/tweaks-to-property-damage.md`.

The split agreed between Maxim Millen and Perrie Gilbert on 2026-10-14:

- Maxim Millen makes every Python change: the model, loss s1 and the CSV
  writer `gen_viewer_data.py`.
- Perrie Gilbert makes these changes, in the page's JavaScript and HTML only.

A page without these changes still reads the new CSV. Each item names the
CSV columns it reads.

1. **Show imminent ground** (property damage section 2). Add
   `imminent_evacuated_m2`, `reinundated_m2` and `reinundated_m3` to the
   claim's damage split, beside evacuated and inundated (T-123).
2. **A switch for imminent ground** (T-127), like the liquefaction switch,
   off by default. Python does not settle imminent ground (the lead,
   2026-10-14), so the CSV's costs and cap leave it out. The switch adds it
   to the total in the page:
   - `imminent_evacuated_m2` is a separate quantity from `damaged_area_m2`.
     The page decides how it enters the total.
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
   for example "2 new walls, 1 on a mapped wall line".
5. **Wall-caused ground** (property damage section 5). Show
   `wall_landslide_m2` in the damage split as ground that came down with the
   claim's own wall. Add a tooltip on "Retaining wall only" saying that this
   ground counts as wall damage, not landslide.
6. **Insured wall length** (property damage section 1). Where the claim panel
   shows wall length, say it is the length supporting the claim's insured
   land, not the whole wall.
7. **Damaged wall length** (property damage section 6). Show
   `damaged_wall_length_m` beside the wall length in the claim panel, so a
   wall clipped by a neighbour's slip reads as partly replaced. Show it to
   2 dp: a clip can be a few centimetres, though the wall is replaced over at least 3 m.
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
