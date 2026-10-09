**Slope elements and polygons revised after the stage D1 review.**

`landloss.hazard.landslide.slope_elements`:

- Elements are measured between their breaks in slope, not between their end cells'
  centres. A wall falling across one interval between cell centres reads vertical, so a
  0.6 m wall is a free-face on every ground group at any bearing.
- Nodata and the grid's edge are ends, not crests or toes, and elements carry
  `touches_nodata`.
- A watershed bug that let barrier cells take ground from seeds is fixed.
- Free-face seeds grow within their own ground group, and only into cells over their own
  ground's limit.
- `BETA_FREE_FACE_GROW_TOL_DEG` is now 3 degrees (was 5).
- Two new judgement values: `BETA_STEP_MARGIN_DEG` and `BETA_MIN_ELEMENT_LENGTH_M`.
- Regions gentler than the grow angle are dropped.
- `core` now marks elements `in_core` instead of dropping them, and each element carries
  `seed_x` and `seed_y`.

`landloss.hazard.landslide.slope_polygons`:

- A free-face's volume is cut by a straight slip plane from its toe to the back of its
  width (`planar_depth_m`), and evacuated cells carry `depth_m`.
- A polygon keeps its own width even where it reaches into the element above, as a
  `within_width` overlap. This replaces the first build's ray cut-off.
- Each polygon carries `width_realised_m`.
- A stack also runs out from its free-face's own crest.
- Halo polygons are dropped only after the shared ground is settled.

`landloss.hazard.landslide.synthetic_terrain` adds `rotate_toy_case` and the case 13
soil batters. Findings are in
`src/scripts/landloss/hazard/landslide/research/slope_elements/toy_slope_elements.md`.
