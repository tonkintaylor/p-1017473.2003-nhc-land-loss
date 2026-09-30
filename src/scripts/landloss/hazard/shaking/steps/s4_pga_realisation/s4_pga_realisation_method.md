# Step 4 — PGA realisation: method

- The step writes one peak ground acceleration field per realisation, per
  100 m cell. It is run by `gen_pga_realisations.py`, with the extent,
  realisations and return period (default 2500 years) set in `config.py`.
- **The grid and site class come from step 2**: `read_site_class` in
  `s2_site_class/gen_site_class.py` reads the grid that step wrote, and raises
  if it has not been run over the same extent.
- **PGA per cell** is the TS1170.5 PGA of that cell's site class, read by
  `landloss.io.ts1170.get_ts1170_pga` and put on the site class grid by
  `landloss.hazard.shaking.site_class.demand_on_site_class_grid` (nearest
  neighbour, then a per-cell pick).
- The PGA grids come from TS1170.5:2025 Table 3.2's PGA column through
  `static_data_gen/gen_ts1170_grids.py`. They are ~9,930 m a cell, so **within
  one demand cell PGA changes only where the site class does**. At 2500 years
  and site class 5 the grid equals the NLM's `pga_2500yr_site_class_5.tif` cell
  for cell.
- **PGA falls on softer ground at 2500 years.** At the Wellington grid point the
  table gives 1.77 g for Class II, 1.68 III, 1.27 IV and 1.00 V. This is the
  TS1170.5 non-linear site response, and it is the opposite of Sa(1.0 s) and PGV
  in step 3.
- Over the four territorial authorities the supplied field runs from 0.93 to
  2.02 g. It carries 1.56 to 2.02 g on Class II cells, which are 55% of the
  area, and 0.93 to 1.08 g on Class V. The run prints the range per class.
- **Cells step 2 filled carry the PGA of the class they were given**: Foster's
  Vs30 has no value along parts of the harbour edge, and step 2 fills those
  cells from the nearest classed cell within 200 m. Over the pilot every
  retaining wall now reads a PGA. Cells further than 200 m from a classed
  cell carry none.
- **A realisation is the field scaled by one lognormal draw**, from
  `landloss.hazard.shaking.pga.beta_pga_realisation`, against a 10% coefficient
  of variation. The multiplier has a mean of one, and **one multiplier covers
  the whole field**, so every property moves together within a realisation.
  The run prints the factor.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "shaking")`, so realisation 3's shaking belongs to the same modelled
  earthquake as its liquefaction and landslides.
- The output is `temp/hazard/shaking/beta-pga-rNNN[-pilot].tif` from
  `pga_path()`, a raster of PGA in g named `pga_g`. It is read by the retaining
  wall and culvert/bridge damage state steps (`vul/shaking/*/steps/s9_*`).
- `src/scripts/landloss/hazard/gen_hazard.py` runs steps 2, 3 and 4 in order.

Potential future improvements: see `s4_pga_realisation_implementation_plan.md`.
