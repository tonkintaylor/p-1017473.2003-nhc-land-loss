# Step 14 — Instability zones: method

- The step finds the pips, the pifs and their pieces, tests each piece for a
  siz and grows the sizs into elements, once per extent, with
  `landloss.hazard.landslide.instability_zones.find_instability_zones`, run by
  `gen_instability_zones.py` with the settings in `config.py` beside it and,
  for the rules shared with the walls (the pif cutting rules and the wall
  height read off each pif), step 12's `config.py`. The method of the search
  itself is described in step 12's method file
  (`s12_urban_slope_faces_method.md`, the pips, pieces and siz test bullets).
- It reads the 1 m DEM of step 3 with the sea masked, the ground map of step 4
  rasterised to ground groups, and the LINZ building outlines (pifs mostly on
  them are dropped), through step 12's `get_dem`, `get_inputs` and
  `building_mask`.
- An extent whose 1 m DEM holds more than `config.MAX_UNTILED_CELLS` cells is
  searched tile by tile (step 12's `tiled.py`, through `find_tiled`), with
  cores of `config.TILE_CORE_M` and margins of `config.TILE_MARGIN_M`; every
  pilot is searched whole (`search_whole()`).
- It writes the found elements to step 12's `found_path` (with one pickle per
  tile on a tiled run), the element polygons to `elements_path`, and the siz
  table's grid columns (pips, angles, drop, near drop, verticality, spine and
  end falls; step 12's `grid_table`) to `grid_sizs_path`, all under
  `temp/hazard/landslide/`. Step 12's faces script reads the wall evidence
  onto that table; its wall zones read the found elements.
- Each run writes a record of what it was built from
  (`urban-slope-instability-zones{suffix}.json`, `built_from()`): the
  settings, the size and modification time of the 1 m DEM and the ground map,
  and a hash of the source of the search code (`SEARCH_CODE`). A rerun whose
  record matches and whose outputs all exist is skipped (`is_current()`);
  `config.REBUILD` forces a search. A refreshed LINZ layer does not make a run
  stale.
- `gen_hazard.py` runs the step after the slope units and before step 12's
  faces.

Potential future improvements: see `s14_instability_zones_implementation_plan.md`.
