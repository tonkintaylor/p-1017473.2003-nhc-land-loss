# Ground: status

**Status:** The ground module holds the static per-extent work that every
other module reads: the terrain, the ground map, the instability zones, the
wall evidence on the slope faces and the cut and fill class of each pif. It was
the first half of the landslide hazard until 2026-10-08, when the lead moved it
out; it runs first in `gen_all.py`, before exposure, hazard and vul, because it
depends on no exposure world and no earthquake. All five steps have run over
the pilot; the module as a whole has not been rerun since the move.

**Updated:** 2026-10-09

For a reviewer: read this page, then each step's method file under `steps/`,
then the code. The landslide chain that reads it is in
`../hazard/landslide/status.md`.

## Approach

- Build every layer once per extent and keep it, so that the hazard, exposure
  and vulnerability work can be rerun without it (`gen_ground.py`, run by
  `gen_all.py`; the extent is in `config.py`). Outputs go under `temp/ground/`
  and figures and tables under `report/ground/`.
- [x] **Terrain (step 1).** A 1 m LiDAR DEM from LINZ, block-averaged to 3, 10,
  30, 50 and 100 m, with Horn's slope and the downhill aspect at 10 m and
  coarser (not 1 or 3 m since 2026-10-09: nothing read them), and the
  cut and fill residuals and the 100 m topographic position derived from them
  (`steps/s1_terrain/s1_terrain_method.md`).
- [x] **Ground map (step 2).** One non-probabilistic polygon map of material,
  modification, prior failure and groundwater depth, from the SLIDE, GNS,
  WCC and NLM layers by precedence, with the strength row by lookup
  (`steps/s2_ground_map/s2_ground_map_method.md`).
- [x] **Instability zones (step 3).** The pips, pifs and their pieces, the siz
  test on each piece, and the growth of the sizs into elements on the 1 m DEM,
  tiled over a large extent, skipping itself when its last run still holds
  (`steps/s3_instability_zones/s3_instability_zones_method.md`).
- [x] **Slope faces (step 4).** The evidence for a retaining wall read onto
  each pif (GNS and T+T mapped walls, cut and fill lines, buildings,
  property), the GNS-only wall candidates, and the siz table
  (`steps/s4_slope_faces/s4_slope_faces_method.md`).
- [x] **Pif cut and fill (step 5).** Each pif classed as cut, fill, cut and
  fill, uncertain or natural against a robust surface fitted to the ground off
  the faces, for the wall probability to read
  (`steps/s5_pif_cut_fill/s5_pif_cut_fill_method.md`).
- The wall units and draws that follow are exposure rw step 6 and the zones of
  each world's walls are landslide step 4; neither is ground.

## Where it is now

- **Steps 1 and 2 ran over the pilot on 2026-10-02**, as landslide steps 3 and
  4: the terrain derivatives and a ground map of 19,275 pieces. The ground map
  stopped short of the extent the other steps used and 71% of the pilot read as
  fill; the fix is phase 0 of the faces plan, and the two fill changes (SLIDE's mixed
  fill classes read as natural material with fill as the modification, and the
  GNS modelling set S52) are built and wait on a rerun. Step 1 now writes only
  the cut and fill residuals and the 100 m topographic position (2026-10-08).
- **Step 3** was split out of the old step 12 on 2026-10-08. The fall-line siz
  test (2 to 8 s on the pilots against 18 to 83 s) is built; on 2026-10-08 it
  gave the Wellington pilot 6,220 pif pieces and 4,790 sizs (353,740 pips). The Porirua pilot with 1 km tiles matched the
  whole grid's siz table. Since 2026-10-08 it searches only within 100 m of a
  building outline (the 2026-10-01 domain) and skips tiles with no land within
  reach. On the Wellington pilot that took the 6,220 pif pieces to 5,865 and
  the 4,790 sizs to 4,657, and the step ran in 44 s. Since 2026-10-09 only the
  pips within reach are joined into pifs (2% more pifs and sizs and 11% more
  element area on the Porirua pilot), each tile is searched only near its
  buildings, the ground map is cut to each tile before it is burned, and the
  tiles run in parallel and resume after a stop. A rural Upper Hutt tile fell
  from 6 to 12 min to a few seconds and an urban one from 6 min to 31 s. The
  Upper Hutt run stopped in step 3 on 2026-10-09 and has not been restarted.
  The found elements are now kept without their terrain layers, which
  landslide step 4 recomputes: about 3% of the old file size, same zones.
- **Step 4** reads T+T's 71 manually mapped walls beside the GNS mapped walls
  (2026-10-08). On 2026-10-08 the pilot had 4,790 sizs, 98 `low_height` and
  1,332 other pieces, and 859 GNS-only pieces (4,884 sizs and 91 `low_height`
  with the pairs test on 2026-10-07).
- **Step 5** reads the DEM a block of pifs at a time since 2026-10-09, so it
  fits over a territorial authority; over Porirua it gave the whole-grid
  classes exactly (69,643 pifs, 349 s, 2.5 GB). It classed 12,015 pifs on 2026-10-05 in 9.6 s: 2,198 cut, 1,472 cut
  and fill, 768 fill, 1,093 uncertain, 6,481 natural and 3 unknown. The class
  is a local reading against the platforms around a face, not a map of large
  earthworks. On the 6,220 pieces (2026-10-08, 8.7 s): 1,877 cut, 1,089 cut and
  fill, 515 fill, 1,014 uncertain, 1,725 natural and none unknown.
- **Run in one go (2026-10-08):** `gen_all.py` over the Wellington pilot ran
  the five steps in 86 s (6,220 pifs, 4,790 sizs; step 3 searched afresh as
  the DEM was rewritten). Every output matched the last run before the move
  (siz table, elements, GNS-only walls, pif cut and fill, and exposure rw step
  6's wall units and draws), and the whole pipeline ran on to the loss tables
  in 9.6 min.

## Next

1. Run `gen_ground.py` over the pilot and check each step reproduces its earlier
   counts (above).
2. Rerun the ground map over the common extent and review its area shares and
   the strength row chosen per grade
   (`steps/s2_ground_map/s2_ground_map_implementation_plan.md`, phase 2).
3. Write a DEM source mask and survey year beside the 1 m DEM, so faces are
   found only on LiDAR (`steps/s1_terrain/s1_terrain_implementation_plan.md`,
   phase 5).
4. Tile the full-extent terrain run, and run the instability zones over Porirua
   and then the other territorial authorities, with the tiles in parallel and
   the margin brought down from 750 m
   (`steps/s3_instability_zones/s3_instability_zones_implementation_plan.md`).
5. Split pifs on steepness as well, once the pieces of mixed steepness have been
   looked at.
6. Rebuild the claim layer, then rerun steps 4 and 5 over the pilot.

## Validation

- Empty and populated element polygon tables, and stitching with an empty tile
  (`tests/landloss/hazard/landslide/test_instability_zones.py`,
  `tests/landloss/hazard/landslide/test_tiled_faces.py`).
- Faces against the GNS mapped walls and the SLIDE breaks in slope
  (`steps/s4_slope_faces/table_slope_face_checks.py`): 63% of mapped wall
  length near a siz and 67% near any pif within 2 m.
- Cut and fill classes against the SLIDE cut slopes and fill bodies and by
  ground group (`steps/s5_pif_cut_fill/table_pif_cut_fill_checks.py`).
- The fall-line siz test against the pair test on both pilots
  (`hazard/landslide/research/siz_fall_line/siz_fall_line.md`).
- Tests are in `tests/landloss/hazard/landslide/` for the library functions the
  steps call (`test_ground_map.py`, `test_pif_cut_fill.py`).

## Open decisions

- **The Wellington Fault sheared zone** in the ground map is not built (**T-89**).
- **Whether the weathering grade is read from a landform proxy or from borehole
  depth-to-rock**, which decides the angle each rock face is tested at
  (`steps/s2_ground_map/s2_ground_map_implementation_plan.md`, phase 3).
- **The wall height setting**: the 70th percentile of near drops within 2 m puts
  63% of the pilot's walled units under 1.5 m, against 54% in Anderson et al.
  (`steps/s3_instability_zones/config.py`).
