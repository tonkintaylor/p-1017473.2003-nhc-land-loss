# Plan: reworking the ground map so it has far fewer polygons

> **For agentic workers:** use `dispatching-subagent-tasks` or `executing-workflows`
> to carry this out task by task. Steps use checkboxes. Ground step 2 has its own
> method file and plan; both change in the same commit as the scripts
> (`adding-steps-scripts`).

**Date**: 2026-10-09 (reviewed and revised the same day) | **Status**: Draft,
awaiting the lead's sign-off on the numbers in Decisions D3 and D7

**Goal:** Cut the ground map over Upper Hutt from 1.65 M pieces and 574 MB, built in
64 minutes, to a map of large polygons that follows real cut, fill, material and
groundwater bodies, without changing what the map says about any of them beyond
what the lead has agreed to.

## Context

Ground step 2 (`src/scripts/landloss/ground/steps/s2_ground_map/gen_ground_map.py`)
took 64 minutes over Upper Hutt on 2026-10-08 and wrote 1,649,603 pieces. The
profile brief is `temp/ground-map-profiling-brief.md`. The 2026-10-09 profiling
run was cancelled while polygonising the residual (its log,
`temp/profile-ground-map/run-upper-hutt.log`, stops there), so the Upper Hutt
breakdown is still missing and Phase 0 gets one. The map on disk,
`temp/ground/ground-map-upper-hutt.geoparquet` (574,461,391 bytes, written
2026-10-08 22:27), is the whole 2026-10-08 build and is the baseline.

The pieces come from the planar partition of every source against every other
(`ground_map.build_ground_map`). Two of the sources are polygonised from rasters
cell by cell, with no tolerance:

1. **The 30 m cut-and-fill residual.** `polygonise_residual` thresholds the
   residual at +/-1 m (`RESIDUAL_MODIFICATION_THRESHOLD_M`) on its **1 m grid**
   and outlines every patch. That gave 981,472 polygons, each a 1 m staircase.
   The residual is the 1 m DEM minus a 30 m smoothed DEM, so a 1 m outline is far
   finer than anything the 30 m smoothing can support. Upper Hutt is 31.0 by
   32.7 km, about 1.0 billion cells. `ground_map.modification_from_residual`
   classes every cell to a string in a `dtype=object` array, a billion Python
   object references (about 8 GB) on top of the 4 GB float32 raster, before the
   script turns them into `uint8` codes. The full study area (59 by 54 km) is
   three times larger again and cannot be loaded at 1 m at all.
2. **The groundwater depth.** `polygonise_groundwater` merges only 4-connected
   cells with exactly the same float32 depth (15,426 polygons). The map only
   ever uses the depth as a class, through `gw_depth_class_from_depth`
   (saturated at a depth of 1 m or less, poorly drained at 3 m or less, well
   drained deeper; `susceptibility.GROUNDWATER_SATURATED_DEPTH_M` and
   `GROUNDWATER_POORLY_DRAINED_DEPTH_M`). The Kingsbury groundwater factor
   downstream, `susceptibility.groundwater_value`, uses the same two breaks
   (`GROUNDWATER_DEPTH_BREAKS_M`), so nothing downstream needs more than the
   class either.

The fill thickness is the mean of the positive 100 m residual over each fill
piece (`mean_positive_residual`), so it depends on the piece's shape and
changes when the pieces get larger.

Later steps read this map: ground step 3 burned the 574 MB map onto tiles and
needed the polygons clipped to the tile first to take three minutes, not more.

On the Porirua pilot (profile of 2026-10-09, 48.8 s in all) the partition took
8.9 s and the residual polygonising 5.6 s; the rest was mostly network reads.
That supports the two suspects, but the Upper Hutt breakdown is what matters.

## Decisions

| # | Decision | Choice | Why |
| --- | --- | --- | --- |
| D1 | Groundwater polygons | Class the depth first (saturated / poorly drained / well drained), then polygonise the class. The map carries `gw_depth_class` only; `gw_depth_m` is dropped and every reader of it moves to the class. | The map and the Kingsbury factor use only the class; the lead chose this over merging on 0.5 m rounding (2026-10-09). `gw_depth_m` **is** read downstream (Phase 1 lists the readers), so the readers change in the same work. The column is not kept with a representative depth per class, because that is invented data labelled as metres. |
| D2 | Residual patches | Class the residual on a 10 m grid, sieve the classed raster at a minimum patch area, polygonise, then simplify as a coverage | Removes the 1 m sawtooth and slivers at the source, before the partition multiplies them. 10 m is within what the 30 m smoothing supports, and reading the residual decimated to 10 m means the 1 m grid is never loaded, which bounds memory for the full extent. The minimum area and the tolerance are method choices for the lead, so the plan measures them. |
| D3 | Sieve area and simplify tolerance | Test 100, 900 and 2,500 m2 for the sieve (1, 9 and 25 cells at 10 m) against tolerances of 5 and 10 m, in metres, not cells; proposed start 900 m2 (one 30 m cell) and 10 m (one cell) | Needs the lead's number; do not commit a default until it is agreed. A 30 m tolerance would move boundaries across buildings, so it is not tested. |
| D4 | Fill thickness | Keep the mean positive 100 m residual per fill piece, computed from the raster by burning the piece ids once | The piece gets larger, so the mean covers more cells. The cells a piece gains sit near the 1 m threshold, so the thickness is expected to fall; Phase 3 measures the shift and reports it. |
| D5 | Unchanged-map reference | Keep the current Upper Hutt map as `temp/ground/ground-map-upper-hutt-baseline.geoparquet` and compare every variant against it | Every change here is a method change; the lead needs numbers, not assurances. |
| D6 | Branch | A branch off the current branch `add-project-context`, not off `develop`; nothing is committed until the lead has seen the numbers | `add-project-context` is 190 commits ahead of `develop` and holds the ground module's uncommitted work (steps 1, 3, 5 and `gen_ground.py`); branching off `develop` would lose it. The profile brief asks for a branch. |
| D7 | What a sieved patch becomes | One sieve over the three-class raster (natural, cut, fill): a patch below the minimum area takes the class of its largest neighbour | That is what `rasterio.features.sieve` does; it does not set the patch to natural. So a natural pocket inside a fill body becomes fill and a fill speckle inside a cut becomes cut. Sieving the cut and fill masks separately would instead turn every small patch natural. The lead can overturn this; the method file states whichever is built. |
| D8 | Simplification | `shapely.coverage_simplify`, never `shapely.simplify` per polygon | Cut and fill patches share boundaries. Simplifying each polygon on its own moves the two sides of a shared edge differently, so the partition gets gaps and overlaps along every one, which is the sliver problem this plan removes. Coverage simplification keeps shared edges. Available here: shapely 2.1.2 on GEOS 3.13.1. The same applies to the groundwater class polygons. |

## Phases

### Phase 0 -- The baseline

- [ ] Branch off `add-project-context` (D6). Rename the existing Upper Hutt map to
      `ground-map-upper-hutt-baseline.geoparquet` **before** anything runs, because
      the profile script overwrites `ground-map-upper-hutt.geoparquet`. Check it
      opens and has 1,649,603 pieces. The full Porirua map
      (`ground-map-porirua.geoparquet`, 144 MB, 2026-10-08 17:48) is the second
      baseline; rename it the same way.
- [ ] Run `temp/profile_ground_map.py` (already written; it times each phase and
      prints the residual polygon count, vertices and smallest area) over
      `porirua-pilot`, then `upper-hutt`.
- [ ] Record the total time, peak memory and the per-phase breakdown: reading the
      sources, polygonising groundwater, polygonising the residual, reading the
      rasters, `build_ground_map`, fill thickness, writing.

**Verification:** `$env:PYTHONPATH = "src"; uv run --frozen python temp/profile_ground_map.py`
prints a `PHASE` line per phase and a `RESIDUAL STATS` line.

**Checkpoint:** the breakdown shows where the 64 minutes go. If a phase other
than the residual polygonising and `build_ground_map` dominates, revise Phase 2
before building anything.

### Phase 1 -- The groundwater class (D1)

- [ ] Test first, in `tests/landloss/hazard/landslide/test_ground_map.py`: a depth raster
      that straddles 1 m and 3 m polygonises into one polygon per class, with
      cells either side of a break in different classes, and a depth of exactly
      1.0 saturated and exactly 3.0 poorly drained, as the existing
      `gw_depth_class_from_depth` gives them (depth of 1 m or less is saturated,
      3 m or less poorly drained, deeper well drained).
- [ ] Fix the docstring of `gw_depth_class_from_depth` (`ground_map.py` line 578),
      which has the classes inverted ("saturated at or above").
- [ ] `polygonise_groundwater` classes the clipped depth with
      `ground_map.gw_depth_class_from_depth`, maps the classes to integer codes
      and polygonises the codes, as `polygonise_residual` does, then simplifies
      them as a coverage (D8).
- [ ] `build_ground_map` and the `GroundSource` for the NLM groundwater carry the
      class. Read `ground_map.py` at line 902, where the depth is filled by
      precedence with `default_gw_depth_m`, and lines 876 and 927-928, where the
      column and class are written. The default off the NLM footprint becomes the
      class of `DEFAULT_GROUNDWATER_DEPTH_M` (4 m gives well drained), derived in
      one place.
- [ ] Move every reader of `gw_depth_m` to `gw_depth_class` (found with
      `git grep -n gw_depth_m -- src tests` on 2026-10-09):
      - `src/landloss/hazard/landslide/urban/geometry.py:177`, the Kingsbury
        groundwater factor: add a class-to-factor helper beside
        `susceptibility.groundwater_value` (the breaks are the same) and call it.
      - `src/landloss/hazard/landslide/urban/face_polygons.py:73`, `:94`, `:152`:
        the ground column it carries, its off-map default (4.0, becomes
        `well_drained`) and the float cast. **This reader fails silently**: it
        casts to float and fills NaN with 4.0, so a missing depth turns saturated
        flat land into well drained with no error. It must not be left reading
        the old column.
      - `src/scripts/landloss/qgis/gen_qgis_e2e_build.py:451`: style a
        categorised `gw_depth_class` layer instead of binned depth.
      - `src/scripts/landloss/reviewer/gen_reviewer_landslide.py:226`.
      - `src/scripts/landloss/hazard/landslide/research/slope_elements/gen_ground_map_qgis_layers.py:152`
        is research and not maintained; leave it.
      - Tests: `test_ground_map.py` lines 425-428, 459, 522, 568, 575, 641-644,
        807-812, 915, 940; `urban/test_chain_end_to_end.py:304`,
        `urban/test_fragility.py:312`, `urban/test_geometry.py:51`, `:75`.
- [ ] Off the NLM footprint the assumed depth (`DEFAULT_GROUNDWATER_DEPTH_M`, 4 m)
      still gives well drained.

**Verification:** `uv run --frozen pytest tests/landloss/hazard/landslide/`
passes (the urban tests are in there), and the Porirua pilot's groundwater class
shares match the baseline's.

**Checkpoint:** the area share by `gw_depth_class` over Porirua is identical to
the baseline to the printed precision, and the groundwater polygon count has fallen.

### Phase 2 -- The residual: 10 m grid, sieve, polygonise, coverage simplify (D2, D3, D7, D8)

- [ ] Tests first: a synthetic classed raster with a one-cell speckle, a natural
      pocket inside a fill patch and a staircase edge gives, after the new
      function, no polygon below the minimum area, the pocket absorbed into the
      fill (D7), no vertex spacing finer than the tolerance, shared edges still
      shared (the union of the polygons has no gaps or overlaps), and a large
      patch keeps its area to within the stated tolerance.
- [ ] Class to codes, not strings. Add `modification_codes_from_residual` in
      `ground_map.py` returning `uint8` (0 natural, 1 cut, 2 fill, with a nodata
      mask for NaN) from a module-level code table, and have the existing
      `modification_from_residual` map those codes to its names, so there is one
      truth and the object array is never built over a large grid.
- [ ] Read the 30 m residual decimated to 10 m, with `rasterio`'s
      `Resampling.average` on read (`out_shape`), so the 1 m grid is never loaded.
      Test: a 1 m synthetic residual read at 10 m gives the block means.
- [ ] A function in `gen_ground_map.py` beside `polygonise_residual`
      (per `placing-python-functions`, it stays in the script unless another step needs it)
      that sieves the codes with `rasterio.features.sieve` at a minimum patch
      size in cells (from the area and the cell size), with the nodata mask,
      polygonises, and simplifies with `shapely.coverage_simplify` (D8). The
      sieve area and tolerance arrive as arguments from `config.py`, with no
      defaults in `main()`.
- [ ] `config.py` gains `RESIDUAL_CLASS_CELL_M` (10), `RESIDUAL_MIN_PATCH_M2` and
      `RESIDUAL_SIMPLIFY_M`, with the reason for each value in the comment. Leave
      the last two at the values the lead agrees (D3). The script takes no
      command-line arguments. `src/scripts/landloss/ground/gen_ground.py:72` calls
      this step's `main()` with named arguments and gains the same three.
- [ ] State D7 in the method file: a sieved patch takes its largest neighbour's
      class, not natural.
- [ ] Run the sweep on `porirua` (the 144 MB baseline is on disk): sieve 100, 900,
      2,500 m2 against tolerances of 5 and 10 m. For each, record time, peak memory,
      piece count, file size, and the area shares by material, modification,
      modification source and groundwater class, beside the baseline. Then run
      the chosen variant only over Upper Hutt; six Upper Hutt runs would take most
      of a day.

**Verification:** a table of those numbers for each variant and the baseline, in
`temp/profile-ground-map/sweep.md`.

**Checkpoint:** the lead has chosen the sieve area and tolerance from that table.
The piece count over Upper Hutt is in the tens of thousands, not millions.

### Phase 3 -- The fill thickness (D4)

- [ ] Compare `fill_thickness_m` per fill piece between the baseline and the chosen
      variant. Aggregate by area: the area-weighted mean and the 5th and 95th
      percentile of the thickness over all fill, before and after. The thickness
      is expected to fall (D4); the size of the fall needs a sentence to the lead.
- [ ] If `mean_positive_residual` is now a large share of the time (the 1 m
      rasterisation of every fill piece), burn per window or per tile, as
      ground step 3 does through `landloss.common.utils.tiles`, so memory stays
      bounded for the full 59 by 54 km extent; the open item in
      `s2_ground_map_implementation_plan.md` lines 132-135 is the same problem.

**Verification:** the thickness comparison, plus `pytest` on `mean_positive_residual`
with a two-piece raster whose means are known by hand.

**Checkpoint:** the thickness distribution is reported to the lead and accepted.

### Phase 4 -- Land it

- [ ] Update `s2_ground_map_method.md` (the groundwater class, the 10 m grid, the
      sieve and D7, the coverage simplify, with the chosen numbers),
      `s2_ground_map_implementation_plan.md`, and `ground/status.md`. Weekly
      updates read the status file.
- [ ] Rebuild ground step 3 over Upper Hutt on the new map and note the time against
      the three minutes it took, since it was this step's size problem that started it.
- [ ] A changelog fragment `doc/whatsnew/mm.feature.<yymmddhhmm>.md`, since the map's
      pieces change for everyone reading it.
- [ ] Rebuild or check every reader of the map. A rebuild changes its row count
      and ids (`ground_id` is minted by location). The readers, from
      `git grep -n "ground_map_path\|ground-map" -- src tests` on 2026-10-09:
      - **Must be rebuilt:** ground step 3 (`gen_instability_zones.py`), which
        stores `majority_ground_row`, a row number into the map, in its elements;
        ground step 4 (`gen_slope_faces.py`); landslide steps 1 (`gen_slope_units.py`),
        2 (`gen_hancox_1997_coverage.py`), 3 (`s1_simulate_landslides.py`),
        4 (`gen_wall_zones.py`) and 5 (`gen_urban_slope_fragility.py`); shaking
        step 2 (`gen_site_class.py`).
      - **Regenerate:** `fig_ground_map.py`, the exposure rw and landslide QGIS
        validations (`gen_rw_qgis_project.py`, `gen_landslide_qgis_project.py`),
        the e2e QGIS build and the reviewer page.
      - Research scripts under `hazard/landslide/research/slope_elements/` are
        not maintained.
- [ ] `uv run --frozen prek -a` until it passes cleanly, and `uv run --frozen pytest`.

**Verification:** `uv run --frozen prek -a` and `uv run --frozen pytest` both pass.

**Checkpoint:** the lead has seen the numbers and agrees to the commit.

## File inventory

| Phase | Files | Change |
| --- | --- | --- |
| 0 | `temp/profile_ground_map.py`, `temp/profile-ground-map/*` | Done / new, gitignored |
| 1 | `s2_ground_map/gen_ground_map.py`, `src/landloss/hazard/landslide/ground_map.py`, `src/landloss/hazard/landslide/susceptibility.py`, `src/landloss/hazard/landslide/urban/geometry.py`, `src/landloss/hazard/landslide/urban/face_polygons.py`, `src/scripts/landloss/qgis/gen_qgis_e2e_build.py`, `src/scripts/landloss/reviewer/gen_reviewer_landslide.py`, `tests/landloss/hazard/landslide/test_ground_map.py`, `tests/landloss/hazard/landslide/urban/test_chain_end_to_end.py`, `.../urban/test_fragility.py`, `.../urban/test_geometry.py` | Modified |
| 2 | `s2_ground_map/gen_ground_map.py`, `s2_ground_map/config.py`, `src/scripts/landloss/ground/gen_ground.py`, `src/landloss/hazard/landslide/ground_map.py`, `tests/.../test_ground_map.py` | Modified |
| 3 | `s2_ground_map/gen_ground_map.py`, `tests/.../test_ground_map.py` | Modified |
| 4 | `s2_ground_map_method.md`, `s2_ground_map_implementation_plan.md`, `ground/status.md`, `doc/whatsnew/mm.feature.*.md`, the readers listed in Phase 4 | Modified / new |

New files in the repo: 1 (the changelog fragment). Deleted: none.

## Risks

| Risk | Mitigation |
| --- | --- |
| Sieving removes real small cut or fill bodies, such as a retaining-wall cut | The sweep reports the area lost; the minimum is the lead's call (D3). The wall units come from other sources. |
| A sieved patch takes a neighbour's class rather than natural (D7) | Stated in the method; the test asserts it; the lead can overturn it before the numbers are run. |
| Simplifying shifts a boundary across a building | Tolerance is in metres, at most one 10 m cell; the sweep reports the area moved. |
| Per-polygon simplification breaks shared edges and makes slivers | `shapely.coverage_simplify` only (D8); the Phase 2 test checks the union has no gaps or overlaps. |
| The 10 m classing grid loses genuine 1 m detail | The residual is against a 30 m surface, so 10 m is within what it supports; the sweep reports the modification shares against the 1 m baseline. |
| Fill thickness falls | Expected (D4); Phase 3 measures and reports. |
| A reader of `gw_depth_m` is left behind and fails silently | Phase 1 lists every reader from the grep and moves each to the class; the face polygon builder's NaN-to-4.0 fill is the one to watch. |
| A different piece count changes the ground ids and row numbers other steps hold | Phase 4 lists the consumers and rebuilds them; ground step 3's `majority_ground_row` is a row number, not an id. |
| The 58% cut or fill share for a rural, hilly authority is a method question, not a speed one | Report it with the numbers (brief); do not change `RESIDUAL_MODIFICATION_THRESHOLD_M` here. |
