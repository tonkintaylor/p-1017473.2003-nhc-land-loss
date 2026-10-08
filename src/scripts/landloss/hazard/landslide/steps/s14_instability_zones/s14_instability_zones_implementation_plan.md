# Step 14 — Instability zones: implementation plan

**Status:** Phase 1 complete; phase 2 not started.

The grid work of the urban slope chain (pips, pifs, pieces, the siz test,
the growth into elements) was step 12's first and slowest part. It depends
only on the 1 m DEM, the ground map and the LINZ building outlines and
coastline, so the lead (2026-10-08) asked for it to be its own static step,
built once per extent, so that everything after it can be rerun without it.

## Phase 1 — Split the grid work out of step 12 (complete)

- [x] `gen_instability_zones.py` runs `find_instability_zones` (whole, or
      tiled over a large extent) and step 12's `grid_table`, and writes the
      found elements, the element polygons and the siz table's grid columns.
- [x] Step 12's faces script reads `urban-slope-grid-sizs{suffix}.parquet`
      and only reads the wall evidence onto it.
- [x] A record of what each run was built from; a rerun with the same
      settings, DEM, ground map and search code skips itself. `REBUILD`
      forces a search.
- [x] `gen_hazard.py` runs it before step 12's faces.

## Phase 2 — Faster and lighter over a territorial authority

- [ ] Own pieces rather than parent pifs in the tiles, now that each piece is
      tested on its own (step 12 plan, phase 5b), and bring
      `TILE_MARGIN_M` down from 750 m towards 100 m.
- [ ] Run the tiles in parallel (about 8 at once on a 14-core machine, each
      about 4 to 5 GB).
- [ ] Move the grid helpers it borrows from step 12's faces script
      (`get_dem`, `get_inputs`, `grid_table`, `find_tiled`, `element_polygons`,
      the found pickle's paths) into this step, once step 12's own edits have
      settled.

## Potential future improvements

- Store the outputs in the versioned store per territorial authority
  (`.agents/plans/running-per-territorial-authority.md`, phase 4) so a
  colleague reads them rather than rebuilding.
- Record the LINZ building outline and coastline layer versions in the run
  record, so a refreshed layer also makes the last run stale.
