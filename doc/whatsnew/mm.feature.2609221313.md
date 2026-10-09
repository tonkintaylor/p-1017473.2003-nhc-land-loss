The liquefaction hazard now runs end to end in this repository, in two steps
under `src/scripts/landloss/hazard/liquefaction/steps/`.

`s2_ld_probabilities/gen_liq_ld_probabilities.py` reads the National
Liquefaction Model's RP2500y, median groundwater land damage grids, clips them
to the study extent and expands the pair into one probability grid per land
damage state. The grids are exceedance probabilities, so the pair is differenced
into bands before the None and Major bands are subdivided into the four states
the release does not carry. That subdivision is the beta shortcut and is named
as one — `beta_expand_ld_probabilities`, `beta_probability_path`, and a `beta-`
opening every file name the step writes — so that what goes when the model emits
land damage categories 1–6 is visible without reading the code.

`s3_ld_states/gen_liq_ld_states.py` draws one state per cell from those grids
and writes a raster of `ld_state` per realisation, with the generator coming
from `realisation_seed(BASE_SEED, realisation_id, "liquefaction")` rather than
from a seed of its own, so that a realisation means the same modelled earthquake
here as in every other hazard layer. The run prints the realised share of each
state beside the mean probability it was drawn from, and `fig_ld_states.py` maps
the realisation with those same two numbers beside it.

`landloss.common.utils.raster.bbox_in_crs` re-expresses a bounding box in
another projection, densifying its edges first so that a clip made with it does
not lose the strip of ground a bowed edge leaves outside the envelope of four
transformed corners. It was `landloss.io.source_material._bbox_in_crs`, which
now calls it: the new liquefaction step goes to grids that module does not read,
and needed the same conversion.
