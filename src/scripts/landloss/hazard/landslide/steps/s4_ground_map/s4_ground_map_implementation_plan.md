# Step 4 — Ground map: implementation plan

**Status:** Phase 1 complete in code and tested on synthetic sources only. The
pilot run is this step's own to make (contract section 3) and has **not** been
made: it is blocked on landslide step 3's `gen_terrain_derivatives.py`, which
has not yet written `temp/hazard/landslide/terrain/` (the 30 m and 100 m
cut-and-fill residuals this step reads), and the step also reads three National
Liquefaction Model layers (`get_nlm_geomorphology`, `get_gwd_median_depth`,
`get_nlm_flatland`), which the build rules this phase was written under do not
allow a step script to fetch. The first phase 2 box below stays open until a
run over `SMALL_WLG_PILOT` has been made and its printed area shares reviewed.

## Background

The urban slope failure and retaining wall models need one non-probabilistic
statement of what the ground is made of, whether it has been cut or filled,
whether it has failed before, how wet it is and how strong it is, read by the
slope candidates (step 6), the wall lines (exposure rw step 6), the slope units
(step 5) and the strength-based models. Section 9 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md` sets
the sources and their precedence; sections 3.2, 7.3 and 9 of
`.agents/plans/urban-slope-build-contract.md` fix the columns, the vocabulary
and the function signatures this step is built against.

## Phase 1 — The reconciled map (complete)

- [x] The vocabulary, the source mappings and the precedence in
      `landloss.hazard.landslide.ground_map`: every mapper lists its source's
      classes and raises on a new one; the three genesis tuples partition the
      fifteen genesis types.
- [x] `build_ground_map()`: the union overlay of every source's boundaries
      and the flatland into one planar partition, attributed by
      representative-point lookup in precedence order, with the defaults
      written where no source reaches and water pieces dropped.
- [x] `strength_from_material()` reading `wellington-greywacke-strength.csv`
      through `ASSETS_DIR`, with the pick rule (all three values present,
      `check` false first, published first, file order) and the six picks on
      the committed CSV asserted in the tests.
- [x] `gen_ground_map.py`: reads the seven polygon sources, polygonises the
      NLM groundwater depth over the flat land and the thresholded 30 m
      residual, builds the map, takes the fill thickness as the mean positive
      100 m residual per fill piece, mints `ground_id` by location and writes
      `ground-map[-pilot].geoparquet`.
- [x] `fig_ground_map.py`: material and modification panels.
- [x] Tests on synthetic overlapping sources carrying every vocabulary value,
      the precedence order, the defaults, the water rule, the strength picks
      and the step chain end to end through `main()` on synthetic inputs in a
      temporary directory.

## Phase 2 — The pilot and the full extent

- [ ] Run `gen_ground_map.py` then `fig_ground_map.py` over the pilot once
      step 3's `gen_terrain_derivatives.py` has written
      `cut-fill-residual-30m-pilot.tif` and `cut-fill-residual-100m-pilot.tif`
      under `temp/hazard/landslide/terrain/`; review the area shares by
      material, modification, prior failure and source that the run prints,
      the strength row chosen per grade, and the two figure panels. Not yet
      made: the residual rasters are absent as of 2026-10-02 and the step's
      NLM inputs could not be fetched under this phase's build rules, so the
      step is exercised end to end only through `main()` on synthetic inputs
      in `tests/landloss/hazard/landslide/test_ground_map.py`.
- [ ] The full extent. The fill thickness burns every fill piece onto the 1 m
      residual grid at once, which the 59 by 54 km study area cannot carry in
      memory; tile the residual read by step 3's output tiles, or by a
      regular grid of the map's pieces, before a full run.
- [ ] Decide the material for the NLM classes that occur nationally but not in
      the Wellington extents (`Melange`, `Estuarine`, `Alluvial fan and
      plains`, `Glacial till`, the beach and marine terrace classes): the
      mapper raises on them today, which is right while none reaches the
      study area.

## Phase 3 — Sources not yet read

- [ ] QMAP [begg_2000] outside the 1:50,000 geology, for the parts of Upper
      Hutt and Porirua the urban map does not reach; no reader exists, so the
      material there is `unknown` today.
- [ ] Weathering grade from New Zealand Geotechnical Database boreholes
      interpolated into a depth-to-grade surface, which would let `rock`
      become `rock_uw_mw` or `rock_hw_cw`, and the depth-to-rock observations
      already compiled in `wellington-greywacke-depth-to-rock.csv`.
- [ ] The harbour reclamation extent, so `reclamation` is reached; no source
      names it today.
- [ ] The GNS fill and colluvium strengths (`sr2019-040-F01` to `F05`,
      `sr2019-051-F14`, `F15`) as a competing pick for the `FILL` and `COL`
      grades.

## Potential future improvements

- Carry the mapper's confidence per polygon rather than per source; the
  split of the SLIDE materials into three sources by confidence does this for
  the one layer that records a confidence, and a second such layer would need
  the same treatment.
- Fill thickness from boreholes or from the archived WCC earthworks plans
  where they give a depth, instead of the 100 m residual, which reads a
  natural spur as fill where no mapping says otherwise.
- A representative-point lookup attributes a sliver by one point; an area
  weighted rule would be more robust where a source boundary is drawn a few
  metres off another's.
