# Step 3 — Land damage states: implementation plan

**Status:** Phase 1 complete and runnable. Phase 2 is the one that changes the
answer rather than the shape of it, and none of it has been started.

This step is the end of the liquefaction chain: a raster of `ld_state` per
realisation, which is the structure `.agents/plans/beta-build.md` has exposure
sampling one value per address from. The full version of the hazard emits the
same structure, so nothing downstream has to change when steps 1 and 2 are
replaced.

## Phase 1 — One drawn state per cell, per realisation (complete)

- [x] Read the six probability grids step 2 wrote, and refuse a set that is not
      all on one grid.
- [x] Take the generator from `landloss.hazard.realisation.realisation_seed`
      with the project seed, the realisation id and the stream name
      `liquefaction`, rather than seeding the script.
- [x] Draw one state per cell by comparing a uniform variate against the
      cumulative probability in severity order — `draw_ld_states` in
      `landloss.hazard.liquefaction.land_damage`.
- [x] Leave a cell with missing probabilities as NaN rather than as state 1.
- [x] Write one GeoTIFF per realisation, with the realisation id in the file
      name.
- [x] Print the realised share of each state beside the mean probability it was
      drawn from, which is the check that the band boundaries are in the right
      place.
- [x] Draw the realisation as a map, with the shares beside it —
      `fig_ld_states.py`.
- [x] Cover the draw with tests that need neither the network nor the T: drive:
      `tests/landloss/hazard/liquefaction/test_land_damage.py` and
      `tests/landloss/hazard/test_realisation.py`.

## Phase 2 — Spatial correlation

- [ ] Correlate the draw between neighbouring cells, so a realisation produces
      patches of damage rather than salt and pepper. Neighbouring cells sit on
      the same deposit at the same depth to groundwater, and independent
      sampling reproduces the share of each state while getting the size of the
      patches wrong. That is the shape of the loss distribution, which is the
      question NHC is asking.
- [ ] Decide what the correlation length should be, and from what. The
      Canterbury mapped land damage is the only dataset in reach that could
      support a figure.

## Phase 3 — More than one realisation

- [ ] Run enough realisations to carry a distribution rather than a number.
      `REALISATION_IDS` already takes a list, so this is a question of how many
      and what to do with them downstream, not of the script.
- [ ] Decide whether every realisation's raster is kept, or only the sampled
      states per address. At study area extent the rasters are the larger of the
      two by a long way.

## Phase 4 — Validation against observation

- [ ] Compare a realisation's state shares over Christchurch against the mapped
      land damage there. Nothing in this step is checked against observation
      today; the run output checks only that the draw matches the probabilities
      it was given, which it would do even if the probabilities were wrong.

## Potential future improvements

- Sample the state per address inside this step rather than leaving the raster
  for exposure to sample, if the address spine turns out to be the only consumer.
- Write the realisations as one multi-band raster rather than one file each,
  which would make an ensemble cheaper to read back.
