# Optimising landslide step 4 (wall zones) over a territorial authority

**Spec:** `doc/specs/optimise-landslide-s4-wall-zones/spec.md` (2026-10-09)
**Status:** Planned, not started. Decision 1 taken 2026-10-09 (move); Decision 2 open.

Over Upper Hutt, landslide step 4 builds 101 tiles one after another and is
heading for 5 to 6 hours. Ground step 3 ran the same tiles in 17 minutes on 4
workers. The plan follows the spec's order: parallel and resume first (P1),
then measure, then cut the work per tile (P2). The one per-tile cut that cannot
change the outputs (drawing only owned elements) is taken in Phase A with the
parallel run, since it is the largest certain saving and is gated by the same
pilot comparison.

## Findings that shape the plan

1. `zones_tile`, `TileZones`, `stitch_*`, `label_keys`, `line_keys` and
   `units_on_no_tile` live in ground step 3's `tiled.py`, not in step 4. Ground
   step 3 hashes the whole `tiled` module source into `SEARCH_CODE`, so any edit
   to that file, even to the zones half, makes its record stale and re-runs its
   17 minute Upper Hutt search. On 2026-10-09 the kept Upper Hutt tiles'
   `code_sha256` equals the working tree's, so they are valid now and the first
   edit to `tiled.py` invalidates them, whatever that edit is.
2. `zones_tile` draws the zones of every polygon in the tile (`with_forced`,
   `polygon_geometries`, the smoothing) and then keeps only
   `frame["element"].isin(owned)`. About 55% of that 31% of the time (the margin
   share of the 2.2x repeat) is spent on rows that are dropped. Filtering to owned
   elements first leaves the outputs unchanged.
3. The plan records an unexplained difference between tiled and whole-grid zones
   (about a third of bare zone rows differ in shape). Phase C compares against the
   current tiled output, not the whole grid, so it is not confused with that bug.
4. Tile sizes are very uneven (8 to 3,290 owned elements on Upper Hutt; tile 4,4
   the largest), so the parallel run gets less than a full 4x on 4 workers: the
   last dense tiles leave workers idle. More workers help until memory caps them.

## Expected speed-up (Upper Hutt, from the 2026-10-09 run and py-spy sample)

| Stage | Expected | Wall time |
| --- | --- | --- |
| Today, one process | 118,487 element builds at 7,154 per 21 min | about 5.8 h |
| Phase A, 4 workers | about 4x, less for uneven tiles | about 90 min |
| Phase A, owned-only drawing | a further 1.2x (17% of tile time, output identical) | about 75 min |
| Phase C, map clipped per worker and margin trimmed | a further 1.2 to 1.4x | 50 to 60 min |
| 6 to 8 workers, if memory allows | | under 45 min |

The 8% in `restore_elements` and the per-scenario `build_slope_polygons` passes
stay unless FR-009 finds scenario-independent work. The ground map (11% in
`tile_inputs`, 4.6 GB per worker) is the largest lever left after this plan and
is profiled separately (`temp/ground-map-profiling-brief.md`).

## Phase 0: Keep the one-process baseline

- [ ] Let the Upper Hutt run of 2026-10-09 (`temp/logs/run-upper-hutt-20261009-124430.log`)
      finish; it has no resume, so a kill loses every tile built. Its wall
      elements and zones files are the one-process baseline the parallel run is
      compared against over a territorial authority, beside the pilot gates.
- [ ] Record its total step 4 time from the log in `s4_wall_zones_method.md`.

## Phase A: Parallel, kept tiles, resume and owned-only drawing (Scenarios 1 and 2, FR-001 to FR-007; first item of FR-009)

- [ ] Create `s4_wall_zones/tiled.py`, an importable worker module (Windows
      workers must pickle the function): `start_worker` and `end_worker` read the
      ground map, coastline, building outlines, wall units, draws, `lineless`
      units and scenario flags once per process (FR-002); `build_zones_tile` runs
      `zones_tile`, writes the `TileZones` to a `.partial` file and renames it
      (FR-006), then writes a done-marker last; a kept-tile path helper and reader.
- [ ] Move the zones half (`zones_tile`, `TileZones`, `line_keys`,
      `units_on_no_tile`, `label_keys`, `stitch_zones`, `stitch_elements` and
      their helpers) out of ground step 3's `tiled.py` into it (Decision 1).
      Ground step 3's `tiled.py` keeps only the search half. This stales ground
      step 3's Upper Hutt record once (17 minutes on 4 workers); every later edit
      to the zones half stales only step 4's own tiles.
- [ ] Draw only owned elements: in `zones_tile`, filter `result.polygons` to
      owned elements before `polygon_geometries` and `with_forced`; keep polygon
      numbering and `first = polygons.index.max() + 1`. The pilot output must be
      identical, checked by the same gate as the worker count.
- [ ] In `gen_wall_zones.py`, add `keep_or_clear_tiles` and `run_tiles` after
      ground step 3's: folder
      `temp/hazard/landslide/urban-slope-zones{suffix}-tiles/` with a
      `built-from.json`; one worker runs inline, more use `ProcessPoolExecutor`
      with `as_completed`; a failure cancels pending tiles and keeps finished ones.
- [ ] The record (FR-005): the `urban-slope-found.pkl` stat and its tile records,
      the wall units and draws file stats, `WORLD_IDS` and scenario names, the
      step's settings, and a sha256 of the source of the code that builds a tile
      (`zones_tile`, `slope_polygons`, `forced_polygons`, `wall_units`,
      `with_forced`, `zone_polygons`). `TILE_WORKERS` is not in it.
- [ ] `config.py`: add `TILE_WORKERS` and `REBUILD`; pass them through
      `main(...)` and the call in `hazard/gen_hazard.py`.
- [ ] Stitch in tile order from the kept tiles (FR-004), then the existing
      `label_keys`, `stitch_elements`, `stitch_zones`.
- [ ] Progress line per finished tile: number, owned and total elements, own
      seconds, time so far.
- [ ] Unit tests: equal record reuses tiles; changed settings, draws or code hash
      clears them; `REBUILD` clears them; a leftover `.partial` is ignored; the
      stitch is the same for a shuffled completion order.
- [ ] Gate on the Porirua pilot in four 1.65 km tiles, as a comparison script with
      a findings doc and no CLI arguments: 1 worker against 3 (attributes equal,
      geometries to 1e-6 m; SC-001), the owned-only build against the kept
      pre-change output (identical), and a run killed after 2 of 4 tiles then
      rerun against an unbroken run (SC-002).

## Phase B: Measure before cutting (SC-003, SC-004)

- [ ] Rerun ground step 3 over Upper Hutt (its record is stale after the move),
      then run step 4 on 4 workers; record wall time and peak memory per worker
      (target under 90 minutes) and compare the outputs with the Phase 0 baseline.
- [ ] Try 6 and 8 workers if the 4-worker peak leaves room on 64 GB; record the
      largest count that fits and its wall time.
- [ ] Decide whether to shrink the per-worker ground map (about 4.6 GB).
      `fill_by_element`, `ground_rows` and `ground_of_elements` index the whole map
      by row position, so a lighter map must keep only the columns they need or
      remap rows.
- [ ] Write the peak memory and the supported worker count into
      `s4_wall_zones_method.md`.

## Phase C: Less work per tile (Scenario 3, FR-008 to FR-010)

- [ ] Burn or pre-clip the ground map once per worker (the 7% in `tile_inputs`).
- [ ] Re-profile tile 2,4 with py-spy. Take the rest of FR-009 (shared per-tile
      work) only where the profile shows it is scenario-independent; scenarios
      differ only by wall flags, but `_contest` and `_claims` couple neighbouring
      elements.
- [ ] FR-008, the open phase 3 item in `s4_wall_zones_implementation_plan.md`:
      on the pilot, keep only margin elements within R metres of an owned one for
      several R, compare owned zones with the full-margin build, and choose R from
      the observed influence range. Needs Decision 2 first.
- [ ] Anything not identical goes to the lead as a list with its size (FR-010).
- [ ] Target: under 45 minutes over Upper Hutt (SC-003).

## Housekeeping

- [ ] Update `s4_wall_zones_method.md`; tick phase 3 in
      `s4_wall_zones_implementation_plan.md`; update `hazard/landslide/status.md`.
- [ ] Changelog fragments in `doc/whatsnew/`, one new file per entry.
- [ ] `uv run --frozen prek -a` and `uv run --frozen pytest`.
- [ ] Say plainly which checks need the user's Upper Hutt run: the 20-thread,
      64 GB timing cannot be run from here.

## Decisions for the lead

1. **Taken (2026-10-09): move the zones half into step 4's `tiled.py`.** The
   move itself saves no time; it is taken because Phase C edits `zones_tile`
   repeatedly (the margin radii of FR-008 alone are several runs), and while the
   zones half stays in ground step 3's file every such edit re-runs the 17 minute
   search. Moved, the cost is one rerun. Rejected: a step 4 wrapper importing
   ground step 3's `zones_tile` (avoids the rerun now, not later); hand-editing
   `code_sha256` in ground step 3's `built-from.json` after the move (the found
   elements do not depend on the zones half, so it would be correct, but the
   record has to stay trustworthy).
2. FR-010: decide a tolerance for zone changes up front, or see the pilot
   differences first. Phase A and the first items of Phase C are arranged so
   only the FR-008 margin trimming can change anything.
