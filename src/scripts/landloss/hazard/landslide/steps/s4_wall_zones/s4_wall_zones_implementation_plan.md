# Landslide step 4 — Wall zones: implementation plan

**Status:** Phases 1 and 2 complete; phase 3 partly done.

The step builds the zones of each exposure world's walls. It was the zones part
of the old landslide step 12 (`s12_urban_slope_faces`), split out by the lead on
2026-10-08 with the search (ground step 3), the wall evidence (ground step 4) and
the wall units (exposure rw step 6). It runs after exposure, because it reads
the wall draws. Landslide steps 5 and 6 read its per-world zones. The plan for
the wall placement as a whole is `.agents/plans/placing-retaining-walls-on-pifs.md`.

## Phase 1 — The zones (complete)

- [x] Evacuated, imminent and inundated polygons written for two scenarios:
      every siz walled, and none walled (`walled`, `bare`), kept as bounds and
      for the figures.
- [x] Walls from the probability replace the two scenarios: each wall unit is
      walled by a draw per exposure world, and the zones of each draw are built
      through `with_walls` with a Series (`gen_wall_zones.py`).
- [x] Every wall has a polygon (the lead, 2026-10-06): every element a siz pif
      grows is kept even where the keep rule would drop it, and every polygon's
      width behind its crest is at least `BETA_MIN_EVACUATED_WIDTH_H` (0.5) of
      its height and `BETA_MIN_EVACUATED_WIDTH_M` (1 m), walled or not.
- [x] GNS-only units and the units of `low_height` pifs given an element on
      their line (`add_line_elements`), and a polygon drawn as geometry for a
      unit whose line finds no free cell (`forced_polygons`, 2026-10-07).
- [x] Zones drawn smoothed, and the runout from Hunter and Fell's travel angle
      with the seismic distance of the Kingsbury zone (2026-10-07 and
      2026-10-08).
- [x] `fig_wall_zones.py` draws the walled and bare zones, or a world's, side by
      side at the pilot sites (`FIG_ZONE_SCENARIOS`).

## Phase 2 — Replace the old polygons (complete)

- [x] The fragility and the realisation (now landslide steps 5 and 6) read the
      polygons from this step (2026-10-06): the fragility reads each world's
      zones (`urban-slope-zones-wNNN`) through
      `landloss.hazard.landslide.urban.face_polygons`, a polygon's wall is its
      element's wall unit, and it stops where the zones and exposure rw step 6's
      drawn walls are not one draw; the realisation reads the fragility's model
      unchanged.
- [x] The old steps 6 and 7, their figures and their tests are removed
      (2026-10-08), with the old candidate method: exposure rw step 6's
      candidate wall lines (`gen_wall_lines.py`, `fig_wall_lines.py`, the line
      builders and the per-line probability) and the terrain layers only those
      read (face heights, profile curvature, 20 m topographic position and
      vegetation height, with the DSM fetch).
- [x] Split out of the old step 12, with its own config and figure
      (2026-10-08); run by `gen_hazard.py` in one pass after exposure.

## Phase 3 — Per territorial authority and the open checks

- [x] The wall zones run tile by tile over a 1 m DEM larger than
      `config.MAX_UNTILED_CELLS` (`build_tiled`, `tiled.py`), 2026-10-07:
      3 km cores, 750 m margins, aligned to the 3 m catchment blocks; line and
      forced elements owned by their wall unit's line. Checked on the Porirua
      pilot with 1 km tiles against the whole grid: the zones' areas within
      0.2% (evacuated within 0.01%), but about a third of the bare and 3% of
      the walled zone rows differ in shape (median 14 m²). The differences are
      not at the seams and not from the drainage graph; their source in
      `build_slope_polygons` is not yet found.
- [ ] Find what in `build_slope_polygons` reads beyond a tile, and make the
      tiled zones identical to the whole grid's.
- [ ] Run over Porirua, then the other three territorial authorities; a
      process pool over the tiles.
- [ ] Run the tiles in parallel, keep each on disk and resume after a stop,
      and cut the repeated work per tile: the spec is
      `doc/specs/optimise-landslide-s4-wall-zones/spec.md` (2026-10-09; over
      Upper Hutt the one-process tile pass was heading for 5 to 6 hours).
- [ ] Rerun the pilots with the fall-line siz test and the zones built from
      the new elements, and record the counts in the method file.
- [ ] A fragility per element, and the share of urban ground in a polygon that
      fails in a realisation, against the order of 1% the literature gives (the
      check the first pilot missed by a factor of about 40).

## Potential future improvements

- A `low_height` pif piece grows no element; its line element gives it the
  minimum polygon, and seeding growth on the wall's own threshold is the
  alternative.
- Pass the building outlines (`building_mask()`, ground step 3) as the barrier
  grid of `build_slope_polygons`, so debris stops at the house below (the lead,
  2026-10-07; landslide status, Next). Roads are not barriers.
- Settle the deposit depth limits, `BETA_MAX_DEPOSIT_DEPTH_H` (one height) and
  `BETA_MAX_DEPOSIT_DEPTH_SOURCE` (twice the source depth), both proposals:
  under them most pilot failures spread back over part of their scar and a
  quarter over all of it.
