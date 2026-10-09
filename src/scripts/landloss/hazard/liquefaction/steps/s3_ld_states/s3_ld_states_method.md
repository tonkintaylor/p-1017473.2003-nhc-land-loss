# Step 3 — Land damage states: method

- The step turns the six probability grids step 2 wrote into a raster of
  `ld_state` values 1 to 6, one raster per realisation. It is run by
  `gen_liq_ld_states.py`, and the figure it is checked against is produced by
  `fig_ld_states.py` in the same folder, written to
  `report/hazard/liquefaction/ld-states/fig/`.
- What a run does is set by `config.py` in the step folder — `EXTENT` and
  `REALISATION_IDS` — read in each script's `if __name__ == "__main__":` block
  and passed into `main()` as keyword arguments. Neither script takes command
  line arguments and neither `main()` carries a default. `EXTENT` is imported
  from step 2's `config.py` rather than repeated, because this step reads the
  rasters step 2 wrote and a second copy of the setting could only ever send it
  looking for a file that is not there. `REALISATION_IDS` is `[0]`: one
  realisation for the beta.
- The inputs are read by `read_probabilities()`, which asks step 2's
  `beta_probability_path()` where each grid went rather than rebuilding the
  name. It refuses a set of six that are not all the same shape, which is what
  the folder looks like after two runs over different extents.
- The generator comes from
  `landloss.hazard.realisation.realisation_seed(BASE_SEED, realisation_id,
  "liquefaction")`, not from a seed of the script's own. A realisation is one
  modelled earthquake, and the same id has to mean the same event in every
  hazard layer for a claim's causes to be summable. `STREAM` is `"liquefaction"`
  — one stream name per hazard, so the hazard's steps belong to the same draw.
- **Each cell is drawn independently.** `draw_ld_states()` in
  `landloss.hazard.liquefaction.land_damage` takes one uniform variate per cell
  and compares it against the cumulative probability across the states in the
  severity order of `LD_STATES`, so a cell's state is the first band its draw
  falls inside. Liquefaction is spatially correlated and nothing here reproduces
  that: the share of each state comes out right, the size of the patches does
  not. The salt-and-pepper texture this produces is visible in the map panel of
  `fig_ld_states.py`.
- A cell whose probabilities are missing comes back as NaN rather than as state
  1, because "nothing known here" is not "no damage".
- The run prints, per realisation, how many cells carried a state and then the
  realised share of each state beside the mean probability it was drawn from —
  `describe_draw()`. The gap to expect between the two columns is the sampling
  noise of the cell count printed above them; a state adrift by much more than
  that means a band boundary is in the wrong place.
- The states are written to `temp/hazard/liquefaction/` at the path
  `ld_state_path()` returns — `ld-state-r000-pilot.tif` for realisation 0 with
  `EXTENT = "wlg-pilot"`, and without the suffix for `"full"`, so a pilot run cannot overwrite
  a full one. The realisation id is in the file name rather than in a folder, so
  a directory listing shows which events have been drawn. `temp/` is gitignored
  and the directory comes from `TEMP_DIR` in `scripts.landloss.paths`.
- The raster carries the name `ld_state`, the field name the beta build contract
  uses, and its projection is written back explicitly before
  `landloss.common.utils.terrain.write_raster` is called.
- Unlike step 2's grids, nothing here is named `beta`. Drawing a state from a set
  of probabilities is correct whatever supplies them, and a raster of `ld_state`
  is what the full version of the hazard emits too. Only the probabilities
  behind it are manufactured, which step 2's `beta-` file names say.
- `fig_ld_states.py` draws two panels per realisation: the states over the
  extent on a basemap, using `landloss.common.utils.plot.style_basemap_ax` and a
  six-colour sequence from pale to dark so severity reads without the legend;
  and the realised share of each state beside the mean probability it came from,
  on a log axis, where a pair of bars that is not level is the draw putting a
  band boundary in the wrong place. It asks
  `ld_state_path()` and `read_probabilities()` for its inputs, so it cannot draw
  a different realisation from the one last written.
- The reusable pieces are covered without the network or the T: drive:
  `tests/landloss/hazard/liquefaction/test_land_damage.py` for the draw and
  `tests/landloss/hazard/test_realisation.py` for the seeding. The reading,
  the printing and the plotting live in the scripts and are not covered.

Potential future improvements: see `s3_ld_states_implementation_plan.md`.
