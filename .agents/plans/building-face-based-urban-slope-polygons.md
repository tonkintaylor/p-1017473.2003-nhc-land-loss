# Plan: face-based urban slope polygons and retaining wall candidates

## Context

The first pilot run of the urban slope chain (2 October 2026) built and ran end
to end, and showed that the way it finds ground that can fail does not stand
up. This plan replaces it. It is the plan a reviewer should read alongside
`src/scripts/landloss/hazard/landslide/status.md` and
`src/scripts/landloss/exposure/rw/status.md`; the build it changes is
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`.

What the pilot showed, each checked against the files the run wrote:

1. **The urban polygons are not tied to a published method.** Landslide step 6
   cuts the ground near buildings into patches of one slope band (0-10, 10-20,
   20-30, 30-45, 45-60, 60+ degrees) and one of eight aspect directions, at 1,
   3, 10 and 30 m, merges patches under nine cells and cuts any patch wider
   than 25 m across the slope into strips. The bands, the octants and the 25 m
   (the mean GNS wall segment length) were this build's own choices. Patch edges
   fall where the slope crosses a band edge, not at the crest or the toe of a
   face, so the polygons do not follow the contours.
2. **Step 7 splits and snaps every polygon to every candidate wall line.** The
   snapping moved neighbouring polygons' vertices independently, so 54,804
   pairs of 1 m polygons overlap by 16 ha in total, and the splitting cut the
   polygons at property boundaries, against the decision that only walls are
   split at boundaries.
3. **Walls were grouped through shared polygons.** One group chained 737 walls
   and 11,555 polygons under one draw, because any walls bounding the same
   polygon were treated as one wall.
4. **Most candidate walls were property boundaries with no step.** Every
   boundary on ground of 5 degrees or more was a candidate: 4,540 of 8,342
   lines. The step test now required (decided 2026-10-02, built) keeps 1,574.
5. **Steps 6 and 7 take 49 of the run's 67 minutes**, almost all of it in
   per-polygon Python loops: zonal statistics read one polygon at a time onto
   59,132 patches, and shapely splits and buffers one polygon at a time.

## The idea

**A face is the unit.** A face is a piece of ground between a crest (a convex
break in slope above it) and a toe (a concave break below it): a retaining
wall, a cut face, the batter of a fill, or a steep natural bank. Faces are
found once, from the 1 m DEM alone, and stored as a static layer. Both the
retaining wall candidates and the urban failure polygons are built from that
layer, so a wall and the ground it holds up come from the same object and
nothing has to be reconciled afterwards.

- A **wall candidate** is a face that is a sharp step: its toe-to-crest height
  is at least `MIN_WALL_HEIGHT_M` and it is steep enough to need retaining.
  The GNS mapped walls, the property boundaries and road frontages, and the
  SLIDE cut and fill edges become **evidence** on that face (they raise or
  lower its probability of being a wall), not sources of lines of their own.
- A **failure polygon** is a face plus the ground that goes with it when it
  fails: a wedge behind the crest, and a runout zone below the toe. It is not
  split by property boundaries or by anything else.
- One wall is one face, so the wall group of step 9 is the face, and the
  grouping problem disappears.

This keeps the agreed design: land on a slope fails in a large landslide,
through its wall, or by localised failure; a polygon with a wall fails with
the wall; fragilities are lognormal on PGV; the rate setting stands; the step
8 and step 9 machinery is kept.

## References relied on

Keys are in `doc/references.bib`.

| Key | Used for |
| --- | --- |
| `jasiewicz_stepinski_2013` | Geomorphons: classifying each DEM cell as flat, peak, ridge, shoulder, spur, slope, hollow, footslope, valley or pit. Shoulder is the crest and footslope the toe of a face. To be added to the bib |
| `townsend_2020` | GNS SLIDE: the manually mapped breaks in slope (top and bottom), cut slopes and fill bodies for Wellington City, used to test the detector and as evidence |
| `kingsbury_1995` | Section 4.4.2: a steep component controls the stability of the whole slope it sits on; a steep facet is expanded to the slope it occupies, with a runout allowance. The Kingsbury factors also stay as the localised fragility's rating |
| `nzgs_mbie_2017` | Module 6, earthquake resistant retaining wall design: the active wedge behind a retained height, the width of ground that goes with a failed wall |
| `de_vilder_2022` | Reach angle against volume by failure style (dry debris avalanche, fill flow slide): the runout below the toe |
| `hunter_fell_2003` | Travel distance of failures in constructed (cut and fill) and natural soil slopes, the primary behind de Vilder's fill relation |
| `monteith_2020`, `lyndsell_2019` | The Priscilla and Orchy Crescent fills: failure on the fill and rock contact, scarp up to 15 m, fill and colluvium strengths, as the check on the fill wedge |
| `massey_2020` | Volume from area, for the depth of the larger faces |
| `alvioli_2016` | Slope units, kept for the large models only |

## Phases

### Phase 0 — Prerequisites

- [ ] **One extent for every step.** Landslide step 3 snaps its extent outward
      and step 4 uses the pilot box, so 9,144 pilot candidates fell outside
      the ground map and took no material. Every step reads its extent from one
      function, because a configurable default is resolved in one place:
      `run_extent(name)`, phase 0 of
      `.agents/plans/running-per-territorial-authority.md`, which this phase
      shares.
- [ ] **Vectorised zonal statistics.** One helper in
      `landloss.common.utils.terrain` that rasterises the polygons once to a
      label grid and reduces each raster by `np.bincount` (mean, max, min,
      count), replacing the per-polygon reads. Step 1 already sums per slope
      unit this way. Expected to take step 6's attribute reading from about
      25 minutes to seconds over the pilot.

### Phase 1 — The static faces layer

A new script, `hazard/landslide/static_data_gen/gen_faces.py`, with the
library in `landloss.hazard.landslide.faces`.

- [ ] **Step height raster.** At every 1 m cell, the rise across 3 m against
      the rise across 9 m along the downhill direction, `(3 x short - long) /
      2`: the estimator already used for property boundaries
      (`landloss.exposure.rw.lines.step_height_m`), here as a raster. Zero on
      an even hillside; the height of a step at the cell.
- [ ] **Geomorphons** on the 1 m and 3 m DEMs, with a lookup distance tried at
      10, 20 and 50 m, written as class rasters. Implemented in numpy in
      `terrain` (eight line-of-sight directions), checked against
      WhiteboxTools' `Geomorphons` on a test tile so no dependency is added.
- [ ] **Faces.** Connected cells between a shoulder and a footslope, with the
      crest line traced along the shoulder cells and the toe line along the
      footslope cells; each face carries its height (crest minus toe
      elevation), its mean and maximum slope, its length along the contour,
      its aspect, and its peak step height. A face is a **step** where the
      step height reaches `MIN_WALL_HEIGHT_M` over a horizontal run of a metre
      or two, and a **bank** otherwise. Steps can sit inside banks (a wall in
      a slope); that is the only nesting left.
- [ ] No slope cut-off: a gentle face is still a face, with a low rating.
- [ ] Written per territorial authority to the versioned store
      (`landloss.io.versioned_store.save_hazard`), tiled with an overlap margin
      so the 1 m grid fits in memory, with a reader. It reads only the LINZ
      DEM, so it is rerun only when the DEM changes, not with the pipeline.
- [ ] Figures: the faces over the hillshade and contours, and the QGIS
      project's layers, for the lead's review before phase 2.

### Phase 2 — Retaining wall candidates from the faces

Exposure step 6 (`gen_wall_lines.py`) is rewritten on the faces layer.

- [ ] A wall candidate is a step face; its line is the face's centreline, its
      retained height the face height, its position `fill` where the face
      holds up a platform above it and `cut` where it holds up a slope.
- [ ] Evidence attached to each candidate: a GNS mapped wall within the snap
      tolerance; a property boundary or road frontage along it; a SLIDE cut or
      fill edge along it; the ground map's material (rock lowers it); its
      distance to a building.
- [ ] A GNS mapped wall with no step under it stays a candidate, classed
      small, because the 1 m grid cannot resolve a wall under about half a
      metre (I-03).
- [ ] The wall line is split at property boundaries for the loss table
      (several `rw_id` on one wall); the face is not.
- [ ] `gen_wall_probability.py` puts a probability on each candidate from the
      evidence, replacing the per-source priors.

### Phase 3 — Failure polygons from the faces

Landslide steps 6 and 7 are replaced by one step on the faces layer.

- [ ] One failure polygon per face, carrying the face's id; no splitting and
      no snapping.
- [ ] Evacuated ground: the face, plus behind the crest a wedge of width
      `H x tan(45 - phi'/2)` from the ground map's friction angle
      (`nzgs_mbie_2017`), checked against the Priscilla and Orchy geometry
      (`monteith_2020`); for a bank with no wall, the headscarp band of T-44.
- [ ] Inundated ground: below the toe by the reach angle for the face's
      failure style (`de_vilder_2022`, `hunter_fell_2003`), clipped at the next
      building or road.
- [ ] Imminent ground: the T-45 band behind the evacuated crest.
- [ ] The Kingsbury rating per face from its own slope, height, material,
      modification and groundwater (`kingsbury_1995`), as now.
- [ ] Step 8 and step 9 read the face polygons; step 9 groups by face, so one
      wall is one draw.

### Phase 4 — Checks

- [ ] Detection against the GNS mapped walls: the share with a step face
      within 2 m (recall), which replaces the fixed 0.9 detection figure.
- [ ] Faces against the SLIDE breaks in slope and cut slopes and fill bodies
      in Wellington City: precision and recall of crests and toes.
- [ ] Face counts, heights and lengths by suburb, and against the 10^2 to
      10^4 m3 Wellington cut failures (`hancox_2013_slope_types`).
- [ ] The pilot rerun end to end, timed per step.

## What it removes

Landslide step 6 (`s6_urban_slope_candidates`) and step 7
(`s7_urban_slope_polygons`) as they stand: the slope bands, the octants, the
four scales, the 25 m strips, the splitting and snapping to wall lines, and
the terrain-break and boundary line sources in `landloss.exposure.rw.lines`.
Their figures and tests go with them. Steps 3, 4, 5, 8 and 9 stay, with step 9
grouping by face.

## Speed

The static part of the run (steps 3 to 7 and the exposure steps) is
independent of the exposure world and the earthquake, and today `gen_all.py`
reruns it every time. The faces layer is computed once per territorial
authority and read thereafter; with the vectorised zonal statistics and no
per-polygon splitting, the expectation is that the pilot's 49 minutes in steps
6 and 7 falls to a few minutes, and a run of many earthquakes costs about half
a minute each over the pilot. To be measured in phase 4.

## Open decisions

- The geomorphon lookup distance, and whether the 3 m DEM or the 1 m one
  gives the cleaner crests and toes.
- The steepness and run that make a face a step rather than a bank.
- Whether the faces layer lives in the shared versioned store or a local
  cache.
- How far the evacuated wedge reaches behind a cut face with no wall: the T-44
  band, or the earth pressure wedge on the face height.

Written 2026-10-02. Not yet reviewed.
