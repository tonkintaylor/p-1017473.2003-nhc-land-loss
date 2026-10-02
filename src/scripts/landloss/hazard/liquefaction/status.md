# Liquefaction hazard: status

**Status:** Prototype under way; the NLM output in hand is still on draft
demands.

**Updated:** 2026-10-02

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

Prototype:

- [x] Get land damage (LD) probabilities for the 2500-year event using the
  TS1170.5 demands.
- [x] Rebuild the waterways layer from the readers on the NLM lateral spreading
  branch (**T-46**), keeping its minimum pond area filter and its filter on
  centre lines named as rivers, so it matches the NLM's own layer. Since the
  call the NLM layer has gained the water bodies of at least 5 ha and the coast
  as free faces, and the rebuild follows it: `steps/s1_free_faces/`. One
  departure: the Waiwhetū Stream is added by ID, provisionally, pending Maxim
  Millen (**Q-19**, under **T-48**).
- [x] Buffer the waterways at **100 m and 200 m** to obtain the lateral spreading
  (LS) zones (**T-47**), as buffer polygons rather than a distance grid, since
  buffering lines is quick where the NLM's grid route took a day for the lower
  Waikato. Agreed 2026-09-25.
- [~] Modify the probabilities of LD states **4 to 6** by LS zone, reading the
  shift off Ryan's figure against the baseline probability: up inside the
  100 m buffer (a baseline 20% becomes about 35%), down outside it (20% becomes
  about 15%). Applied when the state probability layers are built, before the
  realisation is drawn. Owner Perrie Gilbert (**T-47**). Built, as the NLM's
  piecewise correction on P(at least Major); not yet run against the NLM grids.
- [~] Generate realisations of LD from the modified probabilities. Drawn, but
  not yet from probabilities the lateral spreading correction has touched.

Beyond the prototype:

- [ ] Switch the National Liquefaction Model (NLM) output to LD categories 1–6.
- [ ] Refine the LS buffer zones.

## Beta build

A first end-to-end run is being assembled that produces the right data
structures rather than the right numbers; see
`.agents/plans/beta-build.md` for the whole chain.

The liquefaction beta replaces the lateral spreading work entirely with two
steps, and still ends at the structure the full version produces:

- [x] `gen_liq_ld_probabilities` — read the current NLM 2500-year probability
      layer, which carries Moderate and Major only, and expand it to all six
      land damage states by subdividing those masses.
- [x] `gen_liq_ld_states` — draw a state per cell and write one raster of
      `ld_state` per realisation. One realisation for the beta.

No river buffers, no LS zone modifier. Output is a raster of `ld_state` values
1 to 6, which is what the full version emits too.

## Where it is now

- The NLM output in hand is built on **draft** TS1170.5, not the published
  version, so every probability downstream of it is provisional.
- Some progress on the buffers and the probabilities, in the NLM work rather
  than in this repository.
- This repository holds the named river against other watercourse split in
  `landloss.hazard.liquefaction.waterways`, with a map and a table over it, and
  beside it the NLM's free-face layer, rebuilt (`get_free_faces`).
  `steps/s1_free_faces/` writes it per extent, defaulting to a new lower Hutt
  pilot box (`LOWER_HUTT_PILOT`), since the small pilot box holds almost no
  waterways.
- The beta chain runs end to end in this repository, over the Wellington pilot
  box. `steps/s2_ld_probabilities/` reads the two NLM exceedance grids and
  expands them into six state probability rasters; `steps/s3_ld_states/` draws a
  state per cell from them, writes one raster of `ld_state` per realisation and
  maps it. Both write to `temp/hazard/liquefaction/`.
- Everything that manufactures the four states the NLM does not supply is named
  `beta`, down to the `beta-` opening the probability file names, so that what
  goes when the model emits categories 1–6 is visible without reading the code.

## Next

1. Run step 2 with the lateral spreading correction over the pilot box, then
   the study area, and check the per-zone shift it prints against Ryan's figure
   (**T-47**). Step 1 has to be run for the same extent first; `gen_hazard.py`
   does both.
2. Run the two beta steps over the four territorial authorities rather than the
   pilot box, once the extent is worth the runtime.

## Validation

- The realised share of each land damage state against the mean probability it
  was drawn from, printed by `gen_liq_ld_states.py` and drawn beside the map by
  `fig_ld_states.py`. It checks the draw, not the probabilities.

## Open decisions

- **The river layer.** Every published option has oddities, and the choice sets
  the lateral spreading zones. Decided 2026-09-25: rebuild the NLM's own layer,
  filters as they are (**T-46**). Still open: whether further centre lines not
  named as rivers should be added by ID, as was done around Bottle Lake
  (**T-48**, unassigned). The Waiwhetū Stream is in, provisionally (**Q-19**).
- **How the land damage states are revised.** Maxim Millen is revising the
  liquefaction land damage states (**T-54**, 2026-09-30); the LS modifier
  applies to whatever states that produces.
- **T-26** — TS1170.5 or NSHM (2022) demands. The approach above assumes
  TS1170.5.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
