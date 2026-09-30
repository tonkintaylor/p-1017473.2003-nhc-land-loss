# Step 3 — PGV: method

- The step writes Sa(1.0 s) and peak ground velocity (PGV) per 100 m cell over
  the extent. It is run by `gen_pgv.py`, with the extent and return period set
  in `config.py` (default: 2500 years).
- **The site class and the grid come from step 2**: `read_site_class` reads the
  grid `s2_site_class/gen_site_class.py` wrote, found through
  `site_class_path()`, and raises if step 2 has not been run over the same
  extent.
- **Sa(1.0 s)** per cell is the TS1170.5 Sa(1.0 s) grid of that cell's class,
  read by `landloss.io.ts1170.get_ts1170_sa_t1` for each class, put on the site
  class grid by nearest neighbour (`rio.reproject_match`), and picked per cell by
  `landloss.hazard.shaking.site_class.select_by_site_class`. Those grids come
  from Table 3.2 through `static_data_gen/gen_ts1170_sa_t1.py` and are ~9,930 m
  a cell, so **within one demand cell Sa(1.0 s) changes only where the site
  class does**.
- **PGV** is `landloss.hazard.shaking.pgv.pgv_m_s_from_sa_1s`: PGV (mm/s) =
  750 × Sa(1.0 s) (g), written in m/s.
- The outputs are under `temp/hazard/shaking/`, named by `output_path()`:
  `sa-t1-{rp}yr-100m[-pilot].tif` (g, named `sa_t1_g`) and
  `pgv-{rp}yr-100m[-pilot].tif` (m/s, named `pgv_m_s`).
- Over the four territorial authorities at 2500 years, Sa(1.0 s) runs from 1.28
  to 2.81 g and PGV from 0.96 to 2.11 m/s, median 1.22. The run prints these
  ranges.
- Site class and PGV are mapped side by side in the figure produced by
  `fig_pgv.py`, written to `report/hazard/shaking/pgv/fig/`.

Potential future improvements: see `s3_pgv_implementation_plan.md`.
