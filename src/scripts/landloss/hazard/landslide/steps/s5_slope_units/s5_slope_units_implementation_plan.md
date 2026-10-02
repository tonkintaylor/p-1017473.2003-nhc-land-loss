# Step 5 — Slope units: implementation plan

**Status:** Phase 1 built and tested on synthetic terrain, and the delineation
run over the pilot's 10 m rasters for the sensitivity table; the step script
itself awaits the step 4 ground map over the pilot. Phase 1 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`
(plan §10.1); the contract is sections 3.3 and 7.4 of
`.agents/plans/urban-slope-build-contract.md`.

## Background

A slope unit is one hillslope facet from a drainage line at the bottom to the
ridge at the top, with one broad aspect, of the order of 1 to 100 ha. Landslide
step 1 places each large failure in a unit, so the units decide where a
failure starts, not how large it can be. The delineation follows
`r.slopeunits` [alvioli_2016] without GRASS.

The plan named pysheds for the flow routing. The contract (section 12) decided
against it: pysheds needs numba, numba forces a numpy downgrade this project
does not tolerate, and the repository already carries priority-flood D8 routing
in `landloss.common.utils.hydrology`. The routing stage is therefore
`hydrology.route_grid`, and the labelling `scipy.ndimage`. If a `uv lock` with
pysheds is ever shown to keep `numpy>=2.1`, it can replace the routing stage
without changing any signature in `landloss.hazard.landslide.slope_units`.

## Phase 1 — Delineation on the 10 m grid (built; pilot run outstanding)

- [x] `hydrology.route_grid()`: priority flood, D8 receivers and accumulation
      of cell area in one call for a projected grid.
- [x] `slope_units.channel_cells()`, `channel_links()`, `link_catchments()`:
      the channel network at the threshold, one label per reach between
      junctions, every cell assigned to the link it drains to. A cell whose
      flow leaves the grid before reaching a channel takes the nearest
      catchment, so coastal and edge slopes are not left outside every unit.
- [x] `split_half_basins()`: left or right of the link by the cross product of
      the link's chord and the vector from the nearest link cell.
- [x] `units_to_polygons()`, `merge_similar_aspect()`,
      `split_by_aspect_variance()`, and `delineate_slope_units()` running them
      in order with the unit statistics read off the rasters.
- [x] `gen_slope_units.py`: the sensitivity over `CHANNEL_THRESHOLDS_TRIED_HA`,
      `flatland_share` from the step 4 ground map, `unit_id` minted by location,
      the contract's columns written through `slope_units_path()`.
- [x] `fig_slope_units.py`: units coloured by mean aspect over the extent.
- [x] Tests on a synthetic V-shaped valley: two half-basins of opposite aspect,
      the aspect merge, the large-unit split, no cell dropped, and the step's
      `main()` end to end on rasters and a ground map in `tmp_path`.
- [x] A grid on which no cell reaches the channel threshold (a small extent, or
      the 20 ha row of the sensitivity on a small one) is one basin on the left
      bank, so `delineate_slope_units()` returns one unit rather than an empty
      frame (contract 3.3: none is dropped). Tested on a 4 ha plane at 5 ha.
- [x] The circular mean and standard deviation of each unit's aspect are
      `landloss.common.utils.terrain.mean_azimuth_degrees` and
      `azimuth_sd_degrees` (contract section 7.1), so one definition serves
      every caller and the written `mean_aspect_degrees` is in [0, 360).
      `merge_similar_aspect()` keeps its area-weighted resultant vectors,
      which the terrain functions do not take, and reads their bearing through
      `_resultant_azimuth_degrees()`, which folds the 360.0 the modulus hands
      back west of north to 0.0 as the terrain functions do.
- [x] The per-link, per-unit stages (`split_half_basins()`, the unit
      statistics, `split_by_aspect_variance()`) group the cells by label once
      per pass with one stable sort (`_cells_by_label()`), and the split works
      in each unit's bounding window, so no stage scans the whole grid once
      per label.
- [x] Sensitivity over the pilot terrain. The step 4 ground map was not on
      disk, so `delineate_slope_units()` was run through
      `gen_slope_units.cut_units()` and `sensitivity_table()` over the 10 m
      DEM, slope and aspect step 3 wrote for the pilot (`SMALL_WLG_PILOT`,
      210 x 330 cells, 693 ha, no NaN in the DEM), with the committed
      `config.py` (tolerance 45 degrees, 1 to 50 ha), 5 s for the three
      thresholds. Every threshold covered the 693 ha in full with no NaN mean
      aspect:

      | `channel_threshold_ha` | `unit_count` | `median_area_ha` | `max_area_ha` |
      | --- | --- | --- | --- |
      | 1.0 | 75 | 2.94 | 48.76 |
      | 5.0 | 41 | 11.47 | 48.94 |
      | 20.0 | 25 | 30.01 | 49.99 |

      At 5 ha the median unit is 11 ha, inside the 1 to 100 ha range plan §1.4
      asks for; the maximum sits at `MAX_UNIT_AREA_HA` at every threshold, so
      the split is doing the work on the broad flanks of the pilot. The
      `flatland_share` and the figure await the ground map (next box).
- [ ] Run `gen_slope_units.py` and `fig_slope_units.py` over the pilot
      (`PILOT = True`) once step 4 has written `ground-map-pilot.geoparquet`,
      confirm the table above (the sensitivity reads no ground map, so it
      should not move), and look at the figure: units should run from drainage
      line to ridge with one hue each.

## Phase 2 — Full study area

- [ ] Run with `PILOT = False`. The full extent is about 32 million 10 m cells
      (the pilot is 69,300, and its three thresholds took 5 s), and the pure
      Python loops over every cell are the long jobs: the priority flood and
      the accumulation walk in `hydrology.route_grid()`, the catchment walk in
      `link_catchments()`, and the reach walk in `channel_links()` over the
      channel cells. The per-label stages are grouped by one sort per pass
      (`_cells_by_label()`), so they cost the unit's size, not the grid's; the
      pair search in `merge_similar_aspect()` rescans every adjacent pair per
      merge and would want a heap on thousands of units. Tile the routing by
      catchment, or route once and cache the receivers and accumulation under
      `temp/`, before this is run routinely; the sensitivity currently routes
      once per threshold tried.
- [ ] Check the unit sizes against the 1 to 100 ha range plan §1.4 asks for
      and tune `CHANNEL_THRESHOLD_HA`, `MIN_UNIT_AREA_HA` and
      `MAX_UNIT_AREA_HA` from the sensitivity table.

## Phase 3 — Refinements

- [ ] Smooth the half-basin boundary on a sinuous link: the side is decided
      against the link's straight chord, so a cell on the inside of a tight
      meander can land on the wrong bank. Deciding against the local link
      direction at the nearest link cell, smoothed over a few cells, would fix
      it.
- [ ] Decide whether a unit that is mostly flatland should be merged with its
      hill neighbour or kept, once step 1 has been reworked onto the units and
      the placement is visible.

## Potential future improvements

- The `r.slopeunits` optimisation of the threshold and the merge tolerance
  against a landslide inventory [alvioli_2016], once the rainfall inventory is
  supplied.
- A parameter-free delineation [alvioli_2020], which would remove the three
  tuned settings in `config.py`.
