# Step 1 — PGA realisation: method

**Retired 2026-09-30, superseded by `s4_pga_realisation`.** The scripts are
removed; the bullets below describe the step as it last ran.

- The step writes one peak ground acceleration field per realisation. It is run
  by `gen_pga_realisations.py`, and the spread it puts on the field is in
  `landloss.hazard.shaking.pga`.
- The grid is the National Liquefaction Model's **2500-year, site class 5** PGA
  field, read by `landloss.io.nlm.get_nlm_scenario_pga_2500yr_site_class_5` and
  used as delivered. No V<sub>s</sub>30 model and no per-point site class: every
  property in the study is treated as the same ground.
- It is clipped to the extent in its own projection before any reprojection, by
  `clip_to_extent` using `landloss.common.utils.raster.bbox_in_crs`.
- **The grid is national and about 9,930 m across a cell.** Over New Zealand it
  is 149 by 114 cells carrying PGA from 0.35 to 1.3 g, median 0.59. Over the
  four territorial authorities that is roughly 6 by 5 cells, and over the pilot
  box it is a **single cell**, because the pilot is 2.9 by 1.8 km and one cell is
  wider than that. Wellington's cell carries 1.0 g.
- The consequence is worth stating plainly: within the pilot every property
  reads the same PGA, and across the full study area only a handful of distinct
  values exist. Nothing downstream should expect shaking to vary from street to
  street.
- **A realisation is the grid scaled by one lognormal draw**, from
  `beta_pga_realisation`, against a 10% coefficient of variation. The multiplier
  has a mean of one, so a realisation is neither systematically stronger nor
  weaker than the supplied field, and the run prints the factor because it is
  the whole difference between one realisation and the next.
- **One multiplier covers the whole field**, not one per cell. Drawing per cell
  would destroy what spatial pattern the grid has and would average away across
  a portfolio; drawing once preserves the pattern and gives the widest spread a
  10% coefficient of variation can produce. Real ground motion is spatially
  correlated and lies between the two.
- Because the field is one cell over the pilot and the multiplier is shared,
  **every asset in a realisation reads an identical PGA**. Variation between
  assets has to come from the fragility draw rather than from the shaking.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "shaking")`, so realisation 3's shaking belongs to the same modelled
  earthquake as its liquefaction and landslides.
- The output is `temp/hazard/shaking/beta-pga-rNNN[-pilot].tif` from
  `pga_path()`, a raster of PGA in g named `pga_g`.
- **PGV is not produced.** It may be dropped from the study, so nothing
  downstream depends on it.

Potential future improvements: see `s1_pga_realisation_implementation_plan.md`.
