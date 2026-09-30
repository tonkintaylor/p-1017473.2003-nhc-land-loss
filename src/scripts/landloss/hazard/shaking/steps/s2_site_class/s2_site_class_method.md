# Step 2 — Site class: method

- The step writes a TS1170.5 site class per 100 m cell over the extent. It is
  run by `gen_site_class.py`, with the extent set in `config.py`.
- **Vs30** comes from the Foster et al. (2019) model, v18.12, read by
  `landloss.io.vs30.get_foster_2019_vs30` from
  `R:\DataLibrary\210.16_Vs30_NZ_Foster2019\v1_ref_Foster_v18.12`, windowed to
  the extent from `resolve_extent` in step 1's `gen_pga_realisations.py`.
- **The output grid is the Vs30 model's own grid**: NZTM, 100 m cells on
  100 m-aligned bounds. Nothing is resampled.
- **Site class** is TS1170.5:2025 Table 3.3 on Vs30 alone, by
  `landloss.hazard.shaking.site_class.ts1170_site_class_from_vs30`: Vs30 above
  750 m/s is Class I; up to 750 is II, 450 is III, 300 is IV, 250 is V, and 200
  is VI, each bound inclusive. Vs30 at or below 150 m/s (Class VII) is returned
  as VI, the spectrum the TS floors VII at.
- **Limitation (L-38).** The profile criteria of Table 3.3 are not applied:
  soil depth over bedrock for Class I, underlying low-velocity layers for II and
  III, and soft-soil thicknesses for V and VI. Class VII takes the VI spectrum
  without the site-specific analysis the TS requires. The Vs30 sigma layer
  (`get_foster_2019_vs30_sigma`) is read by nothing yet, so each cell has one
  class from the Vs30 central estimate.
- Over the four territorial authorities Vs30 runs from 123 to 618 m/s, so no
  cell is Class I: 56% are II, 28% III, 9% IV, 7% V and 0.2% VI. The run prints
  these shares.
- The output is `temp/hazard/shaking/site-class-100m[-pilot].tif`, from
  `site_class_path()`, a raster of class numbers 1 to 6 (NaN offshore) named
  `site_class`.
- The site class is mapped in the left panel of the figure produced by step 3's
  `fig_pgv.py`, written to `report/hazard/shaking/pgv/fig/`.

Potential future improvements: see `s2_site_class_implementation_plan.md`.
