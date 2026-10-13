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
   `imminent_evacuated_m2` and `reinundated_m2` to the claim's damage split,
   beside evacuated and inundated (T-123).
2. **A switch for imminent ground** (T-127), like the liquefaction switch. It
   does nothing until s1 settles imminent ground and the CSV carries its cost
   and area apart from the rest. The page then needs those columns, so that
   unticking takes them out of the repair and the cap.
3. **A filter option**: "Has imminent land".
4. **Where new walls came from** (property damage sections 3 and 4). Show
   `new_wall_from_undrawn_count` against `new_wall_count` in the claim panel,
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
   wall clipped by a neighbour's slip reads as partly replaced.
