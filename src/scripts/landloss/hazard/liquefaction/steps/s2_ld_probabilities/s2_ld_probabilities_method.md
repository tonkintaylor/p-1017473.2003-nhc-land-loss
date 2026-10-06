# Step 2 — Land damage probabilities: method

- The step turns the National Liquefaction Model's two land damage exceedance
  grids into one probability grid per land damage state, over the study extent.
  It is run by `gen_liq_ld_probabilities.py`, whose module docstring states the
  three stages and which of them is a shortcut.
- What a run does is set by `config.py` in the step folder — `EXTENT` — read in
  the script's `if __name__ == "__main__":` block and passed into `main()` as a
  keyword argument. The script takes no command line arguments and `main()`
  carries no default, so a run can be accounted for from the tracked source
  alone. `EXTENT` is `"wlg-pilot"`, meaning runs go over `SMALL_WLG_PILOT`
  rather than the four territorial authorities. Step 3's `config.py` imports
  `EXTENT` from this one rather than repeating it.
- The inputs are the RP2500y, median groundwater grids read by
  `landloss.io.nlm.get_nlm_scenario_rp2500y_gwd_med_p_ld_moderate_fu` and
  `…_p_ld_major_fu`, at the release `CORE_NLM_VERSION` in
  `landloss.domain.constants` pins. Both are *exceedance* probabilities:
  P(at least Moderate) and P(at least Major).
- The grids are clipped in their own projection and reprojected to
  `DEFAULT_CRS` afterwards, in `clip_to_extent()`, so a small extent stays
  cheap. The extent is re-expressed by
  `landloss.common.utils.raster.bbox_in_crs`, which densifies the box's edges
  before taking their envelope — the same helper
  `landloss.io.source_material` uses. Resampling is nearest neighbour
  throughout: a cell carries the probability of damage at that cell, and
  averaging two of them invents a third.
- The Major grid is then matched onto the Moderate grid with
  `rio.reproject_match()`. The two are differenced cell by cell below and xarray
  aligns on coordinate values, so a grid half a cell out would difference to
  nothing at all rather than raising.
- The pair is differenced into the None, Moderate and Major bands by
  `exceedance_to_bands()` in `landloss.hazard.liquefaction.land_damage`, which
  does the subtraction itself rather than trusting a caller: reading
  P(at least Moderate) as the Moderate band would count the Major mass twice.
  It refuses a grid outside [0, 1] and a pair where Major exceeds Moderate,
  which is how a swapped pair presents.
- **The four states the release does not carry are manufactured here.** A
  tenth of the None band becomes Minor, and the Major band splits by exceedance:
  P(at least Severe) is two thirds of P(at least Major) and P(Very Severe) a
  fifth of it, so Major 1/3, Severe 7/15 and Very Severe 1/5
  (`BETA_NONE_SHARES`, `BETA_MAJOR_SHARES`). The ratios are read off the
  Canterbury exceedance curves of land damage rank against LSN (NLM groundwater,
  PL = 50), whose rank 3 and rank 4 curves match the NLM's Minor-to-Moderate and
  Moderate-to-Severe fragility curves (T-88, Maxim Millen, 2026-10-07). They are
  held constant at every LSN, where the curves show them drifting. They
  subdivide rather than add, so probability is conserved by construction and
  the function raises if the six do not sum to one. This is still a shortcut
  and is named as one — `beta_expand_ld_probabilities()`,
  `beta_probability_path()`, and a `beta-` opening every file name the step
  writes.
- The run prints the extent of the clipped grid, its cell size, how many cells it
  holds and how many of those carry a probability, then the two input means
  beside the six output means and their total — `describe_extent()` and
  `describe_expansion()`. The expansion is checkable by arithmetic from those
  lines alone, which is what they are there for.
- **A cell count well below the grid size is the expected state, not a gap.** The
  National Liquefaction Model covers flat land only, and the Wellington pilot box
  is mostly hill: over it, 239 of 522 cells carry a probability. Liquefaction is
  a flat land process, so the hills having no value is the model saying so rather
  than the clip having failed. Hill ground is the landslide module's concern.
- The six grids are written to `temp/hazard/liquefaction/` at the paths
  `beta_probability_path()` returns —
  `beta-ld-probability-<state>-pilot.tif` when `EXTENT` is `"wlg-pilot"`,
  with `extent_suffix(EXTENT)` for any other named extent and without a suffix
  for `"full"`, so a pilot run cannot overwrite a full one. `temp/` is
  gitignored and the directory comes from `TEMP_DIR` in
  `scripts.landloss.paths`. The projection is written back onto each grid
  before `landloss.common.utils.terrain.write_raster` is called, because that
  function refuses a grid without one.
- Cells the National Liquefaction Model knows nothing about arrive as NaN, and
  stay NaN through the differencing and the subdivision.
- **Lateral spreading** (T-47), when `LATERAL_SPREADING` in `config.py` is set,
  corrects P(at least Major) — states 4 to 6 together — after the match and
  before the differencing, in `correct_for_lateral_spreading()`. The arithmetic
  is `landloss.hazard.liquefaction.lateral_spreading`, a port of the NLM's
  `PiecewiseCorrection` from its `lateral-spread` branch:
  - the free faces step 1 wrote for the extent are buffered at 100 m and 200 m
    into near, middle and far zones, and the zones are written to
    `temp/hazard/liquefaction/ls-zones{-pilot,}.gpkg` for viewing;
  - near a free face P(at least Major) is tripled up to the knee at 0.075 and
    lifted by a fixed 0.15 above it; far from one it is divided by three, or
    lowered by a fixed 0.05. A baseline 20% becomes 35% near and 15% far, as on
    Ryan's figure. The middle band takes the midpoint of the two, where the NLM
    blends linearly in distance;
  - a cell is weighted by its share of each zone, burned at ten sub-cells a
    side and averaged, because the NLM grid is about 100 m a cell, as wide as
    the near zone;
  - P(at least Moderate) is left alone, as the NLM leaves it, and the corrected
    P(at least Major) is capped at it, so the lift moves probability from the
    Moderate band into Major and worse rather than breaking the exceedance pair.
  The run prints the mean P(at least Major) by zone before and after, and the
  number of cells the cap bound in.
- With `LATERAL_SPREADING` off, no correction is applied, as in the beta.
- The reusable arithmetic is covered without the network or the T: drive:
  `tests/landloss/hazard/liquefaction/test_land_damage.py` for the differencing
  and the subdivision, and `tests/landloss/common/utils/test_raster.py` for the
  extent transform. The clip, the match and the printing live in the script and
  are not covered.

Potential future improvements: see `s2_ld_probabilities_implementation_plan.md`.
