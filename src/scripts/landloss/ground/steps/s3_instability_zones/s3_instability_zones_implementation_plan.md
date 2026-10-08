# Ground step 3 — Instability zones: implementation plan

**Status:** Phases 1 and 2 complete; phase 3 not started. The step is part of the
ground module (`gen_ground.py`) since 2026-10-08.

The grid work of the urban slope chain (pips, pifs, pieces, the siz test,
the growth into elements) was the first and slowest part of the old landslide
step 12. It depends only on the 1 m DEM, the ground map and the LINZ building
outlines and coastline, so the lead (2026-10-08) asked for it to be its own
static step, built once per extent, so that everything after it can be rerun
without it. It then moved into the new ground module with the other static
per-extent work.

## Phase 1 — Split the grid work out of the old step 12 (complete)

- [x] `gen_instability_zones.py` runs `find_instability_zones` (whole, or
      tiled over a large extent) and `grid_table`, and writes the found
      elements, the element polygons and the siz table's grid columns.
- [x] Ground step 4's `gen_slope_faces.py` reads
      `urban-slope-grid-sizs{suffix}.parquet` and only reads the wall evidence
      onto it.
- [x] A record of what each run was built from; a rerun with the same
      settings, DEM, ground map and search code skips itself. `REBUILD`
      forces a search.
- [x] `gen_hazard.py` ran it before the faces; `gen_ground.py` now runs it
      (ground step 3), before ground step 4.

## Phase 2 — Own the grid helpers (complete)

- [x] Move the grid helpers it borrowed from the faces script (`get_dem`,
      `get_inputs`, `grid_table`, `find_tiled`, `element_polygons`,
      `building_mask`, the found pickle's paths, `CRS` and `WORK_DIR`) and
      `tiled.py` into this step. Moved 2026-10-08 with the ground module; the
      pif and wall line rules in `config.py` moved with them.

## Phase 3 — A faster siz test and a lighter tiled search

- [x] The fall-line siz test (`instability_zones.FALL_LINE_TEST`, the lead,
      2026-10-08): each pip's drop down its true downhill line to the toe of
      its face, by the pair test's step and angle rules. 2 to 8 s on the pilots
      against 18 to 83 s.
- [x] The siz test made on each piece after the split, not on the whole pif;
      `piece_table` and the whole-pif pass removed. Compared on both pilots
      (`research/siz_fall_line/`): soil sizs unchanged, weak rock about 10%
      fewer.
- [x] Checked tile by tile on the Porirua pilot with 1 km tiles against the
      whole grid (2026-10-07): the siz table identical, 3,584 of 3,603 elements
      identical (19 differ by 1 to 4 cells).
- [ ] Split the pifs on steepness as well (a new piece where a run of passing
      pips meets a run of failing ones), once the pieces of mixed steepness
      have been looked at in the comparison's QGIS projects.
- [ ] Rerun the pilots and Porirua through ground steps 3 and 4 with the new
      siz test, and record the counts in the method file.
- [ ] Own pieces rather than parent pifs in the tiles, now that each piece is
      tested on its own, and bring `TILE_MARGIN_M` down from 750 m towards
      100 m.
- [ ] Run the tiles in parallel (about 8 at once on a 14-core machine, each
      about 4 to 5 GB).
- [ ] Run over Porirua, then the other three territorial authorities.
- [ ] The old seeding code (`find_slope_elements`) is removed with
      `fig_toy_slope_elements.py` refactored off it.

## Potential future improvements

- Store the outputs in the versioned store per territorial authority
  (`.agents/plans/running-per-territorial-authority.md`, phase 4) so a
  colleague reads them rather than rebuilding.
- Record the LINZ building outline and coastline layer versions in the run
  record, so a refreshed layer also makes the last run stale.
