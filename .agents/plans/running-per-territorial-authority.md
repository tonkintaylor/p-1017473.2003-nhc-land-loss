# Plan: running the pipeline per territorial authority

## Context

Everything so far has run over the pilot box (`SMALL_WLG_PILOT`, 2.9 by 1.7
km, about 8,600 addresses). The study area is the four territorial
authorities, Wellington City, Lower Hutt, Upper Hutt and Porirua, from
`landloss.io.area_of_interest.get_study_areas()`. Wellington City alone holds
about ten times the pilot's properties. Three things stop the pipeline
running at that size today.

1. **Memory at 1 m.** Ground step 1 (`gen_multiscale_slope.py`) fetches the
   LINZ 1 m DEM over the whole extent and holds it, and its derivatives, as
   whole grids. Wellington City is a few hundred square kilometres, so one
   float grid at 1 m is over a gigabyte and the step holds several. Every step
   that reads the 1 m grids (ground steps 1 and 3 now, and the faces layer of
   `.agents/plans/building-face-based-urban-slope-polygons.md`) has the same
   limit, and each step's own plan names tiling as its next phase.
2. **Time.** The pilot run of 2 October 2026 took 67 minutes: 49 in the old
   landslide steps 6 and 7 (per-polygon zonal statistics, splitting and
   snapping; both since removed), about
   12 in one-off downloads of new LINZ layer versions, and under a minute for
   everything that varies by earthquake. At today's speed, Wellington City
   would have spent about eight hours in those two steps.
3. **Everything is rerun every time.** `gen_all.py` runs every module end to
   end, so a run of a new earthquake or a new rate setting repeats the hour of
   ground work that depends only on the DEM and the mapped layers. The ground
   module (`src/scripts/landloss/ground/`, run first by `gen_all.py`) now
   separates that work from the rest of the pipeline; the per-TA store and the
   skip-when-current rule in Phases 3 and 4 are what remain.

And one defect that matters more as the extent grows: **seven steps resolved
their own extent** (`resolve_extent` in what are now landslide steps 3 and 7
and ground step 1, shaking step 2, liquefaction step 2 and land value steps 1
and 4), and they did not agree. Ground step 1 snapped outward and the ground
map (now ground step 2) did not, which left 9,144 pilot candidates outside the
ground map.

## Decisions proposed

| Decision | Proposal | Why |
| --- | --- | --- |
| Unit of a run | One territorial authority at a time, or the pilot box | Matches how the data and the councils are organised, and how the lead expects to work next (2026-10-02) |
| Extent | One function, `landloss.io.area_of_interest.run_extent(name)`, returning the TA polygon, its bounding box and its tile grid; every step reads it | A configurable default is resolved in one place, so the steps cannot disagree |
| Tiling | 1 m grids processed in tiles of about 2 by 2 km with a margin at least as wide as the widest window any step uses (100 m today), each tile owning only its core | Bounded memory; the margin keeps every window and every face whole |
| Seams | A vector feature belongs to the tile its representative point falls in; features whose point falls in the margin are dropped from that tile | No duplicates and no gaps at seams |
| Coarse grids | The 10 m and coarser grids, the slope units and the large models run on the whole TA, with a margin | They fit in memory, and flow routing needs whole catchments |
| Static against per-realisation | Split the runner: the ground module (`gen_ground.py`, done) builds what depends only on the DEM and the mapped layers, once per TA; `gen_static.py` would add the other static steps (shaking, liquefaction, exposure steps 1 to 5); `gen_realisations.py` runs the exposure worlds and the earthquakes against it | The static part is the hour; the per-earthquake part is seconds |
| Where static layers live | The versioned store (`landloss.io.versioned_store.save_hazard`, `save_exposure`) under `DATA_VERSION`, per TA, so a colleague reads them rather than rebuilding; `temp/` for the pilot | Shared, versioned, and not rebuilt by accident |
| Reruns | Each static step skips itself when its output for the TA exists and its inputs have not changed, unless its `config.py` says to rebuild | A run of new earthquakes costs only the draws |
| Across TA boundaries | Ground, faces and walls are per TA; a landslide or runout crossing a TA boundary is kept by the TA its source lies in, and the loss tables are concatenated over TAs | Claims are unique across TAs, so the tables join cleanly |

## Phases

### Phase 0 — One extent

- [ ] `run_extent(name)` in `landloss.io.area_of_interest`: the pilot box or a
      TA, with its bounding box, its snapped grid origin for each cell size,
      and its tile grid.
- [ ] Every `resolve_extent` replaced by it, and the steps' outputs checked to
      share one extent over the pilot (the ground map covers every candidate).

### Phase 1 — A tiling utility

- [x] `landloss.common.utils.tiles`: the tile grid with margins
      (`tile_grid`), a reader that returns one tile of a raster with its
      margin (`read_window`), and the representative-point ownership rule for
      vectors (`owned_by`), 2026-10-07. No core writer yet: the first step
      tiled (the old landslide step 6) wrote vectors, not rasters.
- [x] Tests: the cores cover every cell once, a window reads what a whole
      read holds there, a feature on a seam has exactly one owner
      (`tests/landloss/common/utils/test_tiles.py`); step 6 tiled gives the
      candidates it gave whole (`test_tiled_candidates.py`, and on both
      pilots at 1 and 3 m), before that step was removed.

### Phase 2 — The 1 m steps, tiled

Measured on the Porirua pilot on 2026-10-07 (peak memory per step, scaled
by area, under the step numbers of the time): only the old landslide step 6's
delineation (about 85 GB over Porirua) and the old step 12's faces (95 GB) and
wall zones (77 GB) outgrow a 64 GB machine; ground step 1 (then landslide step
3) peaked at 33 GB over Porirua, and ground step 5 (then step 13) and the wall
units scale to about 28 GB. The old step 12 is now ground step 4 (faces), exposure
rw step 6 (wall units) and landslide step 4 (wall zones).

- [ ] Ground step 1 fetches and writes the 1 m DEM and derivatives per
      tile; the coarser grids are built from the tiles. Not needed for
      Porirua (33 GB); likely needed for Wellington City and the Hutt. Lighter
      since 2026-10-08: the derivatives step no longer writes the face heights,
      curvature, 20 m position or vegetation height, nor fetches the 1 m DSM.
- [x] ~~The old landslide step 6's delineation per tile~~: tiled on 2026-10-07,
      then that step was removed on 2026-10-08 with the rest of the old
      candidate method (old steps 6 and 7 and the exposure wall lines), which
      nothing downstream read.
- [x] The faces and wall zones per tile (the old step 12; now
      `ground/steps/s3_instability_zones/tiled.py`, used by ground step 4 and
      landslide step 4); the zones are close but not yet identical to the whole
      grid's (see `s4_slope_faces_implementation_plan.md`, phase 6).
- [ ] ~~Vectorised zonal statistics~~: no longer needed; the per-polygon zonal
      statistics belonged to the old steps 6 and 7.

### Phase 3 — The split runner

Started 2026-10-08 from the step that needs it most: ground step 3
(`s3_instability_zones`) holds the 1 m search that was step 12's, and skips
itself when its record of settings, inputs and code still holds; the static
ground work moved into its own module, `ground` (`gen_ground.py`: steps 1 to 5,
run first by `gen_all.py`, in the order ground, exposure, hazard, vul); and
`config.START_FROM` in `gen_all.py` starts a run at a named module and step
(`{"module": "ground", "step": "s4"}`).

- [x] The ground module: terrain, ground map, instability zones, slope faces
      and the pif cut and fill, run once per extent.
- [ ] `gen_static.py`: the static steps outside ground, namely shaking steps 2
      and 3, liquefaction step 2, and exposure steps 1 to 5, per TA, skipping
      what exists. Ground's own steps skip only where they say so (ground step
      3 does today).
- [ ] `gen_realisations.py`: the exposure worlds and wall draws, the
      earthquakes, the landslide draws (landslide steps 3 to 6), and vul, per
      TA.
- [ ] `gen_all.py` calls the ground module, `gen_static.py` and
      `gen_realisations.py`, so the one-command run still works.

### Phase 4 — The versioned store

- [ ] Static layers (the ground module's `temp/ground/` outputs first) saved and read through `versioned_store` per TA, with the
      pilot staying in `temp/`.
- [ ] A short record in each step's method file of where its output lives.

### Phase 5 — Run and measure

- [ ] The pilot rerun tiled, checked equal to the untiled pilot.
- [ ] Wellington City run end to end, timed per step, with peak memory.
- [ ] Lower Hutt, Upper Hutt and Porirua. Porirua runs as the `porirua`
      extent, its bounding box, before Phase 0's outline clip.

## Risks

- The LINZ DEM is a merge of survey years (**L-12**); a tile seam on a survey
  boundary is a second seam.
- The GNS SLIDE layers cover Wellington City only, so the other three TAs run
  on the ground map's coarser sources and the faces alone.
- A run per TA multiplies the outputs to keep in step; the versioned store and
  one extent function are what keep them consistent.

Written 2026-10-02. Not yet reviewed.
