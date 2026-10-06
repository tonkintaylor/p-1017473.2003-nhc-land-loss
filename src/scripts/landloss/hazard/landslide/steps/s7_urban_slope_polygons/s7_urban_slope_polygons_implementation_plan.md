# Step 7 — Urban slope polygons: implementation plan

**Superseded in the pipeline (2026-10-06).** Landslide steps 8 and 9 read
step 12's zones of each world's wall draw instead of these polygons, and
`gen_hazard.main_urban` no longer runs this step: its polygons are reconciled
to the exposure wall lines, which no longer carry the walls exposure rw step 6
draws. The scripts stay until step 12's plan, phase 5, removes them.

**Status:** Phase 1 complete in code and tested on synthetic candidates and
lines; the pilot run is the project lead's to launch once steps 3 and 6 and
the exposure wall lines have been run.

## Background

Step 6 delineates failure candidates from the terrain alone, and exposure
retaining wall step 6 draws the candidate wall lines. The urban model needs
one set of failure polygons whose edges are the wall lines, each carrying the
fixed geometry of every state it can be in, so that a realisation only picks
up what this step has already computed. Sections 1.2 and 7 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md` set
the objects and the geometry rules; sections 3.6, 4 and 7.6 of
`.agents/plans/urban-slope-build-contract.md` fix the columns, the ids and
the function signatures this step is built against.

## Phase 1 — The polygons and their fixed geometries (complete)

- [x] The reconciliation rules in `landloss.hazard.landslide.urban.geometry`:
      `snap_edges_to_lines()` (vertices within the tolerance projected onto
      the lines, then `shapely.snap` and `make_valid`, with a guard against a
      small patch collapsing onto a line), `split_by_lines()` (pieces under
      `MIN_PIECE_AREA_M2` merged back), `wall_line_on_edge()` and
      `nest_parents()`, chained by `reconcile_candidates()`.
- [x] The fixed geometry rules, one named function each with its source in
      the docstring: `crest_line()` and `toe_line()`, `offset_strip()`,
      `headscarp_band_m()`, `evacuated_no_wall()`, `imminent_no_wall()`,
      `fill_wedge()`, `imminent_fill_wall()`, `dry_reach_angle()`,
      `runout_length_m()`, `spread_runout_m()`, `inundated_polygon()`,
      `evacuated_depth_m()`, `fill_wall_depth_m()`, assembled per polygon by
      `state_geometries()` and per frame by `attach_state_geometries()`.
- [x] The Kingsbury factors from the polygon's own attributes
      (`kingsbury_factors()`) and the topographic amplification factor
      (`amplification_factor()`).
- [x] `gen_urban_slope_polygons.py`: reads the candidates, the wall lines, the
      1 m DEM, the building outlines and the roads; reconciles; recomputes
      the relief on the reconciled geometry; mints `slope_id` by scale and
      location; nests; scores; fixes the state geometries; writes
      `urban-slope-polygons[-pilot].geoparquet` and prints the counts
      contract section 3.6 asks for.
- [x] `fig_urban_slope_polygons.py`: the finest-scale polygons by wall edge
      with the wall edges over them, and a close-up of the no-wall state's
      three geometries.
- [x] Tests in `tests/landloss/hazard/landslide/urban/test_geometry.py` on
      planar synthetic cases: a straddling candidate is split, an edge
      within the tolerance becomes the wall line, the no-wall and fill-wall
      extents, the runout and its truncation by a barrier, the headscarp
      band, nesting parents, ids stable under row order, and the library
      chain end to end writing a file with the contract's columns.

## Review corrections (2026-10-02; complete)

- [x] Record every wall line on a polygon's edge (`wall_line_ids`, longest
      shared edge first) beside the one sharing the longest edge
      (`wall_line_id`): the wall lines are split at property boundaries and
      the polygons are not, so one wall along an edge is often several
      lines, and step 8 and step 9 now give the polygon's wall state and
      outcome to every one of them.
- [x] Record only sloping-land lines on an edge (`sloping_lines()`); the
      snap and the split still read every line. A flat-land line sharing the
      longest edge no longer shadows a sloping line on the same polygon.
- [x] Prefix the placeholder geometry numbers `BETA_`
      (`BETA_HEADSCARP_BAND_M`, `BETA_HEADSCARP_BAND_STEEP_M`,
      `BETA_FILL_WEDGE_HEIGHT_MULTIPLE`, `BETA_MIN_RUNOUT_M`), each comment
      naming what sets it; `amplification_factor()`'s docstring names
      phase 3 as what replaces it.
- [x] Tests: a wall split at x = 12 on a 20 m square records both lines; a
      line crossing the edge or ending against it is not on it; a flat-land
      line on the toe leaves the polygon the shorter sloping line; lines
      without `is_flatland` are refused.

## Phase 2 — The pilot

- [ ] Run the pilot once step 3 (`dem-1m-pilot.tif`), step 6 (the
      candidates) and the exposure wall lines exist. Review the counts the
      run prints and the figure, including the count of polygons with no
      downhill direction.
- [ ] Decide the three rules this build chose where the contract's rule gave
      no usable answer, all documented in the function docstrings:
      - the crest and toe are the boundary segments facing uphill and
        downhill (`crest_line()`), not the vertices above and below the
        centroid, because on a raster patch's staircase outline at a diagonal
        aspect the vertex rule takes the side vertices and sweeps wing-shaped
        strips off them;
      - the inundated strip is at least long enough to spread the evacuated
        ground at its own depth (`spread_runout_m()`), because the reach
        angle rule measures L from the crest and gives no run past the toe on
        a face gentler than about 40 degrees, where a 1 m strip would carry
        the whole volume at an implausible depth;
      - a polygon with no downhill direction (a level patch step 6 kept, NaN
        aspect) takes a band around its whole edge for the imminent and
        inundated geometries (`no_direction_states()`), the inundated band
        not cut at barriers, and a wall on its edge copies that state
        because neither a wedge nor a run can be placed without a direction.
- [ ] Decide whether the full-extent 1 m run can be carried in memory. The
      reconciliation and the state geometries are per-polygon loops over
      shapely, so the run time scales with the polygon count; tiling by the
      candidates' extent is the next phase if the full extent is too slow.

## Phase 3 — The researched rules

- [ ] Replace each starting point of plan section 7 with the researched
      rule: the headscarp band against the claim report extraction when it
      lands, the fill wedge multiple against the Wellington fill evidence,
      the reach angles against the inventory [de_vilder_2022], and the
      amplification factor bracketed against `sr2019-051-F35`.
- [x] A minimum shared edge for `wall_line_on_edge()`: a line crossing a
      boundary transversally meets the buffered boundary over about twice
      the tolerance, and the contract's longest-intersection rule counted
      it. Only the part of the intersection running within
      `EDGE_ALIGNMENT_MAX_DEG` of the boundary counts now.
- [ ] Simplify a raster patch's staircase outline before the crest and toe
      are read, so a diagonal face reads one crest rather than a run of
      half-cell risers.
- [ ] A fill-wall relief that includes the retained height, so the fill flow
      slide runs from the top of the wedge rather than the top of the face.

## Potential future improvements

- Split polygons at property boundaries as well as wall lines, which plan
  section 1.2 decided against for now, so that a failure confined to one
  property reads as one row.
- Read the crest and toe off the DEM rather than the geometry, which would
  put the headscarp band on the true break in slope on an irregular face.
- Carry a multi-part inundated geometry where a barrier splits the strip,
  rather than the largest part.
- Give a level patch the circular mean aspect of its edge neighbours in step
  6, so that no polygon reaches this step without a direction and the band
  rule of `no_direction_states()` is no longer needed; or cut that band at
  barriers.
