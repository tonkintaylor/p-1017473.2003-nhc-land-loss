# Step 4 — Ground map: implementation plan

**Status:** Phase 1 complete. The step ran over `SMALL_WLG_PILOT` on
2026-10-02 as part of the whole chain and wrote 19,275 pieces. Two findings
from that run are open: the map stops short of the extent the other steps use,
which left 9,144 urban candidates without a material (fixed by phase 0 of
`.agents/plans/building-face-based-urban-slope-polygons.md`), and SLIDE's mixed
fill classes make 71% of the pilot fill (below).

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

- [x] Run `gen_ground_map.py` over the pilot. Made on 2026-10-02 in the
      whole-chain run: 19,275 pieces.
- [ ] Review the area shares the run prints, the strength row chosen per
      grade, and the two panels of `fig_ground_map.py`.
- [ ] Build the map over the same snapped extent as step 3 and the urban
      candidates, so every candidate has a material (faces plan, phase 0, and
      `.agents/plans/running-per-territorial-authority.md`, phase 0).
- [ ] SLIDE's mixed fill classes, 65% of the SLIDE area over the pilot, are
      mapped to `fill_uncontrolled`. Left as it is (the lead, 2026-10-02).
      **Reviewer: a mapping is invited**, for example the dominant natural
      material with fill recorded as the modification.
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
