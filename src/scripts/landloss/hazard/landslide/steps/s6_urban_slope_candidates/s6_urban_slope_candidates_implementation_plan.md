# Step 6 — Urban slope candidates: implementation plan

**Status:** Phase 1 complete; phase 2 not started. Phase 1 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`
(plan §8); the contract is sections 3.4, 7.5 and 10 of
`.agents/plans/urban-slope-build-contract.md`.

## Phase 1 — Delineate and attribute the candidates (complete)

- [x] The urban domain: building outlines buffered by
      `config.BUILDING_DISTANCE_M`, less the NLM flatland
      (`delineation.urban_domain`). No insured land mask.
- [x] Banded connected components at each scale in `config.SCALES_M`: slope
      bands and aspect octants, 4-connected labelling, patches under
      `config.MIN_PATCH_CELLS` merged into the neighbour sharing the most cell
      edges, patches longer than `config.MAX_PATCH_LENGTH_M` along the contour
      cut into equal pieces (`delineation.delineate_candidates`). Every band
      produces candidates.
- [x] Terrain attributes read onto each candidate as zonal statistics with a
      point read where no cell centre falls inside; distances to the nearest
      building, road centreline and property boundary; position above, below
      or beside the nearest building; the ground map copied from the polygon
      under the representative point (`gen_urban_slope_candidates.py`).
- [x] `candidate_id` minted by scale descending, then location
      (`landloss.common.utils.ids`).
- [x] Figure of the candidates per scale (`fig_urban_slope_candidates.py`).
- [x] Tests on a synthetic terrace-and-face and bank-with-face ground at 1 and
      3 m (`tests/landloss/hazard/landslide/urban/test_delineation.py`): the
      face is one patch nested inside the coarser bank, the gentlest band is a
      candidate class, small patches merge, a long strip splits, and the step
      writes the contract's columns end to end on synthetic inputs.

## Phase 2 — Run over the pilot and the study area

- [ ] Run over the pilot once landslide step 3's extension (the terrain
      derivatives under `temp/hazard/landslide/terrain/`) and step 4 (the
      ground map) have been run over it. Not run yet: the slope and aspect
      rasters exist over the pilot but the derivatives and the ground map do
      not, and the run reads the NLM flatland from T:, so it is the project
      lead's to launch.
- [ ] Check the pilot figure by eye: faces nested inside banks, patch edges on
      crests and toes, no grid rectangles.
- [ ] Run over the four territorial authorities at 1 m. The segmentation is
      whole-extent numpy on the 1 m grid (about 3,200 million cells for the
      59 by 54 km study area), which does not fit in memory.
- [x] Tile the delineation of a scale whose grid is over
      `config.MAX_UNTILED_CELLS` (`delineate_tiled()`, on
      `landloss.common.utils.tiles`), 2026-10-07. Checked identical to the
      whole-grid delineation, geometry and attributes, at 1 and 3 m on the
      Wellington and Porirua pilots with 800 m tiles.
- [ ] Run over Porirua (`EXTENT = "porirua"`), the first territorial
      authority; its whole-grid run ran out of memory at the 1 m
      delineation on 2026-10-07.

## Phase 3 — Refine the segmentation

- [ ] Replace `config.MAX_PATCH_LENGTH_M` (the mean GNS SLIDE wall segment
      length) with failure widths from the rainfall inventory when it is
      supplied.
- [ ] Recompute `slope_degrees` and `aspect_degrees` per piece after the
      contour split; the pieces now carry the whole patch's values.
- [ ] Decide what to do with a small patch that has no neighbour at all (an
      island in the cells outside the domain); it is kept as it is now.
- [ ] Try region growing (scikit-image superpixels) as the alternative of plan
      §8.2, and compare the patch edges against the mapped crests and toes.
- [ ] Add the 50 m scale if the 30 m banks turn out too small for the largest
      urban failures.

## Potential future improvements

- Read QMAP and the NZGD boreholes once step 4 reads them; the candidates copy
  whatever the ground map carries, so nothing changes here.
- Measure the building position along the aspect (uphill or downhill of the
  outline) rather than by elevation difference alone, which cannot tell a
  building beside a bank from one on a terrace at the same height.
- Carry the DEM survey vintage onto each candidate (limitation **L-12**), so
  a face found in an older survey can be weighed accordingly.
