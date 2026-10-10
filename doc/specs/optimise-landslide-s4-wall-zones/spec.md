# Feature Specification: Optimise landslide step 4 (wall zones per world) over a territorial authority

**Branch**: `add-project-context` **Created**: 2026-10-09 **Status**: Draft

Landslide step 4 (`src/scripts/landloss/hazard/landslide/steps/s4_wall_zones/gen_wall_zones.py`)
builds the evacuated, imminent and inundated zones of every element for each
wall scenario (bare, walled, and one per exposure world). Over an extent ground
step 3 searched in tiles, it runs `tiled.zones_tile` on each tile in turn and
stitches the tiles' zones (`build_tiled`).

## Evidence (Upper Hutt, 2026-10-09)

1. Ground step 3 searched 101 of Upper Hutt's 121 tiles (3 km cores, 750 m
   margins) in 17 minutes on 4 workers, with each tile cut down to its
   buildings and kept on disk.
2. Landslide step 4 then ran the same 101 tiles one after another, in one
   process. In its first 21 minutes it built 13 tiles holding 7,154 of the
   118,487 elements the tiles hold between them (6%), which puts the whole
   step at about 5 to 6 hours.
3. The tiles hold 118,487 elements for the 54,903 that ground step 3 owns:
   each element in a 750 m margin is built again by every tile that reads it,
   2.2 times over on average.
4. A 90 s sample of the running step (py-spy) put the time in:
   `build_slope_polygons` 47%, `with_forced` and `polygon_geometries` 31%
   (16% smoothing cell outlines), `tile_inputs` 11% (7% burning the ground
   map), and `restore_elements` 8% (recomputing the terrain layers). Both
   polygon passes run once per scenario.
5. Ground step 3's tiling (`find_tiled`, `tiled.build_tile`, `run_tiles`,
   `keep_or_clear_tiles`) already does for its own pass what this spec asks
   of landslide step 4: worker processes, a tile kept on disk as it is done, a
   resume from the tiles not yet done, and a record that clears stale tiles.

## Scenarios (mandatory)

### Scenario 1 -- The tiles run in parallel (Priority: P1)

A run over a territorial authority builds landslide step 4's tiles on several
worker processes at once, as ground step 3 does, and stitches them into the
same zones and wall elements a one-process run writes.

**Why this priority**: the step is the longest in the pipeline over a
territorial authority, and its tiles are independent until the stitch.

**Independent test**: run the step over the Porirua pilot in 4 tiles on 1
worker and on 3, and compare the outputs.

**Acceptance criteria**:

1. **Given** the Porirua pilot built by ground step 3 in four 1.65 km tiles,
   **When** landslide step 4 runs on 1 worker and then on 3, **Then** the wall
   elements and every scenario's zones file are identical (attributes equal,
   geometries equal to 1e-6 m).
2. **Given** a run on several workers, **When** a tile finishes, **Then** a
   progress line names the tile, its element count, its own time and the time
   so far.

---

### Scenario 2 -- A stopped run resumes (Priority: P1)

A run that is killed partway, or fails on one tile, resumes from the tiles not
yet built and writes the same outputs as an unbroken run.

**Why this priority**: a multi-hour step lost to a closed console or a single
bad tile has to start again from the first tile today.

**Independent test**: kill a pilot run after some tiles, run it again, and
compare with an unbroken run.

**Acceptance criteria**:

1. **Given** a pilot run killed after 2 of 4 tiles, **When** the step runs
   again with nothing upstream changed, **Then** it builds only the other 2
   tiles and its outputs equal an unbroken run's.
2. **Given** kept tiles from a run whose inputs or settings differ (the found
   elements, the wall units or draws, the scenarios, the step's settings or
   its code), **When** the step runs, **Then** it clears those tiles and
   builds every tile again.

---

### Scenario 3 -- Less work per tile (Priority: P2)

Each tile does less repeated work: margins hold fewer elements built only to be
dropped, and work that does not depend on the scenario is done once per tile
rather than once per scenario.

**Why this priority**: parallel workers divide the time; less work per tile
cuts it, and also cuts memory per worker.

**Independent test**: profile one dense Upper Hutt tile before and after, and
compare the pilot outputs.

**Acceptance criteria**:

1. **Given** the dense Upper Hutt tile 2,4, **When** it is built before and
   after the change, **Then** its time falls and the pilot's outputs are
   unchanged, or every change is listed and agreed by the project lead.

---

### Edge Cases

- A tile with no element of its own but elements in its margin.
- A tile ground step 3 skipped (no building): it has no found elements and is
  not built here either.
- A wall unit owned by no searched tile: already counted and printed
  (`tiled.units_on_no_tile`); NHC does not insure such walls.
- A worker that runs out of memory: the run stops, and the tiles already
  built are kept for the resume.
- The step over an extent searched whole (every pilot): unchanged.

## Requirements (mandatory)

### Functional Requirements

- **FR-001**: The step MUST build the tiles of a tiled extent in worker
  processes, at most `TILE_WORKERS` at once, read from the step's
  `config.py`.
- **FR-002**: Each worker MUST read the layers every tile reads (the ground
  map, the coastline, the building outlines, the wall units and draws) once,
  not once per tile.
- **FR-003**: Each tile's zones MUST be written to disk when built and dropped
  from memory, so that a worker holds one tile at a time.
- **FR-004**: The stitch MUST read the kept tiles in tile order, so that the
  outputs do not depend on which worker finished first.
- **FR-005**: A run MUST skip every tile already kept by a run with the same
  record, and MUST clear the kept tiles when the record differs or
  `REBUILD` is set. The record MUST cover the found elements, the wall units
  and draws, the scenarios, the step's settings and the source of the code
  that builds a tile.
- **FR-006**: A kept tile MUST be written to a temporary file and renamed, so
  that a killed run leaves no half-written tile.
- **FR-007**: The outputs MUST equal a one-process run's (Scenario 1).
- **FR-008**: The step SHOULD build only the margin elements that can change
  an owned element's zones, rather than every element in the 750 m margin.
  This is the open item in phase 3 of
  `s4_wall_zones_implementation_plan.md` ("Find what in
  `build_slope_polygons` reads beyond a tile").
- **FR-009**: The step SHOULD compute once per tile what every scenario shares
  (for example the elements' cell outlines before the walls are applied),
  where the profile shows it is shared.
- **FR-010**: [NEEDS CLARIFICATION: is a change to the zones from FR-008 or
  FR-009 acceptable if it is small, or must the zones stay exactly as they
  are? The pilot comparison gives the size of any change.]

### Key Entities (if data is involved)

- **Kept tile zones**: one tile's zones for every scenario and its elements,
  with local ids and their keys, as `tiled.TileZones` holds them now.
- **Step record**: what a run was built from, kept beside the tiles to decide
  whether they can be reused.

## Success Criteria (mandatory)

- **SC-001**: Over the Porirua pilot in 4 tiles, the outputs on 3 workers are
  identical to those on 1 (attributes equal, geometries to 1e-6 m).
- **SC-002**: A pilot run killed after 2 of 4 tiles and run again builds only
  the remaining tiles and writes outputs identical to SC-001's.
- **SC-003**: Over Upper Hutt on a 64 GB, 20-thread machine with 4 workers,
  the step finishes in under 90 minutes with FR-001 to FR-007, and under 45
  minutes with FR-008 and FR-009.
- **SC-004**: The peak memory of one worker over Upper Hutt is measured and
  written in the step's method file, with the worker count it supports.
- **SC-005**: The unit tests and `uv run --frozen prek -a` pass, and the
  step's method file and plan, and `hazard/landslide/status.md`, describe what
  was built.

## Assumptions

- Ground step 3's tiling is the pattern to follow (worker initialiser, tile
  record, resume, clearing by record); this spec does not restate it.
- The scenario list stays as it is (bare, walled, one per world in
  `WORLD_IDS`); more worlds scale the per-scenario work.
- The ground map stays as it is; its size is being profiled separately
  (`temp/ground-map-profiling-brief.md`), and a smaller map would speed up
  `tile_inputs` here too.
- The cut-down tile windows and the stored found elements of ground step 3
  are unchanged.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Each worker holds its own copy of the ground map (about 4.6 GB over Upper Hutt) | Memory caps the worker count | Measure per worker (SC-004); clip the map to each tile's window in the worker |
| Workers finish out of order | Ids or the "first tile claims it" rules change | Stitch in tile order from the kept tiles (FR-004) |
| A kept tile from an older run is reused | Wrong zones, silently | The record and clearing rule (FR-005) |
| FR-008 drops a margin element an owned zone needed | Zones change at tile seams | Compare with the pilot whole-grid and one-tile runs before accepting (FR-010) |
| Worker processes on Windows import the step's module afresh | A function defined in a script run from the console cannot be pickled | Keep the worker function in an importable module, as ground step 3 does in `tiled.py` |
