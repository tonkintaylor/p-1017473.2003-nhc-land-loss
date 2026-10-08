# Ground step 5 — Pif cut and fill: method

- **Inputs.** The pifs come from ground step 4's siz table (`siz_table_path`), and the
  DEM from ground step 3's `get_dem()`: ground step 1's 1 m DEM with every cell
  off the LINZ land polygons set to no data, the same grid the pips were found
  on. The step is run by `gen_pif_cut_fill.py` ("s5, pif cut and fill" in
  `gen_ground.py`), after ground step 4. Each pip's
  fall direction is re-read with `instability_zones.find_pips`, and the step
  stops if any pip of the table is not a pip of this DEM (ground step 3 is then stale).
- **The method** is `landloss.hazard.landslide.pif_cut_fill.gen_pif_cut_fill`.
  Every threshold is a named constant at the top of that module, judgement and
  untuned.
  - `face_feet` walks each pip down its own fall direction, a cell at a time.
    It stops at the first step flatter than `FOOT_SLOPE_DEG` (20°), at no data,
    or after `FOOT_MAX_M` (15 m). The cell it stops on is the foot of the face.
  - `face_mask` takes every cell the walks passed over, for every pif, grown by
    `FACE_BUFFER_M` (1 m), as the ground the fits skip.
  - `fit_quadratic` fits each pif's anchor surface. It uses every cell closer
    than `FIT_RADIUS_M` (20 m) to any of the pif's pips or feet that is off the
    face mask, with a quadratic in coordinates centred on those points.
    - The fit is reweighted by Tukey's bisquare up to `ROBUST_ITERATIONS` (10)
      times, stopping once no coefficient moves by more than 1 mm.
    - Its scale is 1.4826 times the median absolute deviation of the fitted
      cells' residuals.
    - A pif with fewer than `MIN_FIT_CELLS` (30) such cells has no surface, and
      its class is `unknown`.
  - `classify` uses the medians over the pif's pips of the DEM minus the
    surface, at the crest and at the foot.
    - The *excess drop* is the crest residual minus the foot residual.
    - The *position* is their sum over the excess drop: -1 means all of the
      excess is below the surface, +1 all of it above.
    - The class is `natural` up to `EXCESS_DROP_M` (1 m), then `uncertain` up
      to `SCALE_K` (2) times the scale.
    - Beyond that it is `fill` above `POSITION_SPLIT` (one third), `cut` below
      minus one third, and `cut_and_fill` between.
- **Outputs.** `gen_pif_cut_fill.py` writes two tables under
  `temp/ground/`, with `extent_suffix(extent)` on the name.
  - `urban-slope-pif-cut-fill.parquet` has one row per pif, indexed by
    `pif_id`: `n_pips`, `face_drop_m`, the surface (`surface_a` to `surface_f`,
    `surface_centre_x`, `surface_centre_y`, `surface_radius_m`), its
    `surface_scale_m`, `crest_residual_m`, `foot_residual_m`, `excess_drop_m`,
    `uncertain_below_m`, `position` and `cut_fill_class`.
  - `urban-slope-pif-cut-fill-pips.parquet` has one row per pip: its pif, the
    pip and its foot (x, y, z) and the surface at both.
  - The pif table joins the siz table on `pif_id`. The wall probability (exposure rw step 6)
    reads the class from it.
- **Speed.** Over the `wlg-pilot` extent (5 October 2026), the 12,015 pifs and
  353,740 pips take 9.6 s, the pip directions included. The research version
  took about 45 s for the anchor fit alone.
  - The window distances come from one Euclidean distance transform per pif,
    not a KD-tree.
  - The fit solves the 6 by 6 normal equations, not an SVD.
  - The reweighting stops early once the fit settles.
  - The medians use a partition directly.
  - The walk carries only the pips still moving.
  - With the early stop off, the classes are identical to the research run; with
    it on, one pif changes, one that sits 2 mm from a class boundary.
- **Pilot result.** Over all 12,015 pifs: 2,198 cut, 1,472 cut and fill, 768
  fill, 1,093 uncertain, 6,481 natural and 3 unknown. Of the 3,341 pifs of at
  least 10 pips: 1,160 cut, 662 cut and fill, 268 fill, 696 uncertain and 555
  natural.
- **Checks.** `table_pif_cut_fill_checks.py` writes three tables to
  `report/ground/pif-cut-fill/tab/`. The shares below are for pifs of
  at least 10 pips (`config.CHECK_MIN_PIPS`).
  - `class-counts.csv`: the counts above.
  - `class-vs-slide.csv`: pifs on SLIDE cut slopes are 33% cut and 39%
    uncertain, against 34% and 19% on unmapped ground. Pifs on SLIDE fill
    bodies are only 6% fill. The surface is today's ground, so a large fill is
    the local surface, and the class measures how a face sits against the
    platforms around it.
  - `class-by-ground-group.csv`: soil-like ground is 37% cut and 23% cut and
    fill. Weak rock is 31% cut, 14% cut and fill and 24% uncertain.
- **The research behind it**, its comparison with a 30 m rolling mean and a
  plain quadratic, the literature and the cross-section figure are in
  `hazard/landslide/research/cut_fill/pif_cut_fill.md` and
  `hazard/landslide/research/cut_fill/fig_pif_cross_sections.py`.
  The unit tests are in `tests/landloss/hazard/landslide/test_pif_cut_fill.py`.

Potential future improvements: see `s5_pif_cut_fill_implementation_plan.md`.
