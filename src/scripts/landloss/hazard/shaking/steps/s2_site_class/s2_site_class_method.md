# Step 2 — Site class: method

- The step writes a TS1170.5 site class per 100 m cell over the extent. It is
  run by `gen_site_class.py`, with the extent set in `config.py`.
- **Vs30** comes from the Foster et al. (2019) model, v18.12, read by
  `landloss.io.vs30.get_foster_2019_vs30` from
  `R:\DataLibrary\210.16_Vs30_NZ_Foster2019\v1_ref_Foster_v18.12`, windowed to
  the extent from `resolve_extent` in this step's `gen_site_class.py`, which
  the later shaking steps share.
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
  cell is Class I: after the fill, 55% are II, 28% III, 9% IV, 8% V and
  0.3% VI. The run prints
  these shares.
- The output is `temp/hazard/shaking/site-class-100m[-pilot].tif`, from
  `site_class_path()`, a raster of class numbers 1 to 6 (NaN offshore) named
  `site_class`.
- **Cells without a Vs30 value take the class of the nearest classed cell
  within 200 m**, centre to centre, by
  `landloss.hazard.shaking.site_class.fill_site_class_gaps`
  (`GAP_FILL_MAX_DISTANCE_M`). A tie between classes goes to the softer one.
  Foster's model has no value on some land cells along the harbour edge;
  over the pilot 73 of 522 cells have none and 25 are filled, which gives a
  class to all 17 retaining walls that sat on them. The fill also reaches up
  to 200 m offshore, where no asset is. The lead tried 300 m on 2026-10-06 and
  set it back to 200 m in favour of the ground map default below.
- **Cells still unclassed take a default Vs30 for their ground**, by
  `landloss.hazard.shaking.site_class.fill_site_class_from_ground_map`: the
  material covering most of the 100 m cell on landslide step 4's ground map
  (`ground_map_path()`; pieces of `unknown` material are left out of the
  count), its Vs30 from `BETA_GROUND_MAP_DEFAULT_VS30_M_S` in
  `landloss.domain.constants`, and the class of that Vs30 by the same Table
  3.3 bounds. The values are judgement, the fill value the lead's, and the
  lead confirmed the whole table on 2026-10-06 (every material, the five
  added ones and rock at 750 m/s in Class II included):

  | Material | Vs30 (m/s) | Class |
  | --- | --- | --- |
  | `fill_uncontrolled`, `reclamation` | 200 | VI |
  | `fill_engineered`, `alluvium` | 250 | V |
  | `colluvium`, `loess` | 300 | IV |
  | `rock_hw_cw`, `rock_crushed` | 450 | III |
  | `rock`, `rock_uw_mw` | 750 | II |
  | `unknown` | none | none |

  Each value is the inclusive top of its class. Cells the ground map does not
  reach (open sea), or whose only material is `unknown`, stay NaN. Over the
  pilot 8 cells are classed this way, all on uncontrolled fill on the
  reclaimed harbour edge, Class VI; they carry the 42 urban slope polygons
  that had no site class before.
- **Landslide step 4 has to have run first, over the same extent.** Step 2
  stops with a message naming `s4_ground_map/gen_ground_map.py` when the
  ground map is missing, and `gen_hazard.main` runs landslide steps 3 and 4
  before the shaking steps.
- Where each cell's class came from is written to
  `temp/hazard/shaking/site-class-source-100m[-pilot].tif`, from
  `source_path()`, as uint8 codes (`SITE_CLASS_SOURCES`): 0 none, 1 Foster
  Vs30, 2 nearest classed cell, 3 ground map default. Over the pilot: 449
  Foster, 25 nearest cell, 8 ground map, 40 none (sea). The run prints these
  counts, and the ground map cells by material.
- `read_site_class()` reads the output back for steps 3 and 4.
- The site class is mapped in the left panel of the figure produced by step 3's
  `fig_pgv.py`, written to `report/hazard/shaking/pgv/fig/`.

Potential future improvements: see `s2_site_class_implementation_plan.md`.
