# Urban slope failure and retaining wall build: interface contract

> **Historical (2026-10-02).** This is the contract the first build was made
> against, with "As built" notes added as it went. It is kept as the record of
> that build, not as a description of the code. **The current truth is each
> step's method file** under `src/scripts/landloss/*/steps/`, and the status
> files above them. The urban polygons and wall candidates it specifies are
> being replaced: see `.agents/plans/building-face-based-urban-slope-polygons.md`.
> A reviewer does not need to read this file to review the code.

The single document every implementer of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md` (the
plan) builds against. Section numbers in the plan are cited as "plan §n". Where
the plan left a detail open this contract decides it, marks the decision
**[decided here]**, and keeps it simple. Nothing here is code; every signature
is the one the implementer writes.

Conventions that apply throughout, from `AGENTS.md`, `.agents/context/code-structure.md`
and the `adding-steps-scripts` skill:

- Every step lives in `s<n>_<topic>/` with `__init__.py`, `config.py`,
  `s<n>_<topic>_implementation_plan.md` and `s<n>_<topic>_method.md`. Step
  numbers continue per submodule, as the repository already does (hazard
  shaking s1–s4 and landslide s1 coexist): shaking adds s5, landslide adds
  s4–s9, exposure rw stays on s6, and vul as section 3 lists. Scripts take no
  CLI arguments; `main()` holds no defaults and returns nothing. Every `gen_`
  script exposes one path function per output, and every figure script calls
  it.
- Paths out of the repo come from `scripts.landloss.paths` (`TEMP_DIR`,
  `REPORT_DIR`); packaged assets from `landloss.io.ASSETS_DIR`.
- Every GeoParquet is written by `GeoDataFrame.to_parquet` in `EPSG:2193`
  (`landloss.domain.constants.DEFAULT_CRS`), with the primary geometry column
  named `geometry`. Extra geometry columns are ordinary GeoParquet geometry
  columns (`GeoDataFrame.set_geometry` is only ever called on `geometry`).
- File name parts: `[-pilot]` is appended when `config.PILOT` is true;
  `-w<NNN>` is `f"-w{world_id:03d}"`; `-r<NNN>` is `f"-r{realisation_id:03d}"`.
  When both appear, `w` comes before `r`: `...-w000-r003[-pilot]...`.
- Every run prints the ids it ran for, the rate setting where it applies, and
  the counts the plan's Verification section lists.
- Tests under `tests/landloss/` mirror the library path. Test folders carry **no**
  `__init__.py` (none of the existing ones do). Synthetic rasters are built as
  `tests/landloss/common/utils/test_terrain.py` builds them: an `xr.DataArray`
  with dims `("y", "x")`, `y` descending, `x` ascending, half-cell-centred
  coordinates in NZTM, then `.rio.write_crs(constants.DEFAULT_CRS)`. Copy its
  `make_dem()` helper into the new test module rather than importing it across
  test files.
- Each implementer writes their own changelog fragment
  `doc/whatsnew/<initials>.feature.<yymmddhhmm>.md`, where `<initials>` are the
  committing developer's from `git config user.name` (one of `mm|pg`, the
  `issue_pattern` in `pyproject.toml`), never appending to another's.

## 1. Constants added to `src/landloss/domain/constants.py`

Added in phase 0, in one block after `BASE_SEED`. Reused existing constants are
listed after the table. **[decided here]**: the four id prefixes beyond `WL`
and `SP` live in the same block, so every minted prefix is in one place.

| Name | Value | One-line comment |
| --- | --- | --- |
| `EXPOSURE_BASE_SEED` | `2003` | The seed every exposure world's draws derive from; separate from `BASE_SEED` because whether a wall exists is not something the earthquake decides. |
| `URBAN_BUILDING_DISTANCE_M` | `100.0` | The urban slope model runs within this distance of a LINZ building outline, off the NLM flatland. |
| `URBAN_SCALES_M` | `(1, 3, 10, 30)` | The cell sizes the urban failure candidates are delineated at; nesting across them is kept. |
| `MIN_WALL_HEIGHT_M` | `0.5` | A candidate wall line with a DEM face lower than this is not modelled. |
| `UNCONSENTED_WALL_HEIGHT_M` | `1.5` | Walls under this height are often built without consent and are more likely in poor condition. |
| `URBAN_RATE_FACTORS` | `{"low": 1.5, "medium": 1.0, "high": 1.0 / 1.5}` | Multiplier on every urban fragility median by `config.URBAN_RATE`. Medium is 1.0 by definition; **low and high are placeholders to be set by the anchoring (plan §6)**. A *low* failure rate is a *higher* median, so low > 1. |
| `TOPOGRAPHIC_AMPLIFICATION_MAX` | `1.5` | The largest factor a crest, spur or face over 60 degrees divides a fragility median by. |
| `LOCALISED_FRAGILITY_BETA` | `0.6` | Dispersion of the localised (no wall) fragility until the anchoring sets it. |
| `WALL_LINE_ID_PREFIX` | `"WL"` | Candidate wall line ids, `WL<7 digits>`. |
| `SLOPE_ID_PREFIX` | `"SP"` | Urban failure polygon ids, `SP<7 digits>`. |
| `CANDIDATE_ID_PREFIX` | `"UC"` | Urban failure candidate ids, `UC<7 digits>`. |
| `GROUND_ID_PREFIX` | `"GM"` | Ground map polygon ids, `GM<7 digits>`. |
| `UNIT_ID_PREFIX` | `"SU"` | Slope unit ids, `SU<7 digits>`. |
| `LARGE_LANDSLIDE_ID_PREFIX` | `"LS"` | Large-model landslide ids, `LS<7 digits>`, per realisation. |

Reused, not redefined:

- `landloss.exposure.rw.beta_population.SMALL_MAX_HEIGHT_M` (1.0),
  `MEDIUM_MAX_HEIGHT_M` (2.5), `SIZE_CLASSES`, `INITIAL_CONDITIONS`,
  `BETA_POOR_SHARE`, `classify_wall_size()` and `describe_population()`.
- `landloss.exposure.coverage.RW_COVERAGE_BUFFER_M` (2.0) and
  `keep_walls_on_insured_land()`.
- `landloss.domain.constants.BASE_SEED`, `DEFAULT_CRS`, `FLATLAND_NLM_VERSION`,
  `NZ_BUILDING_OUTLINES_LAYER_ID` and the rest of the layer ids.
- `landloss.hazard.landslide.susceptibility` factor values, breaks and
  `susceptibility_rating()` / `susceptibility_zone()`.

## 2. The seeding change

`src/landloss/hazard/realisation.py`, phase 0. Exact signature:

```python
def realisation_seed(
    base_seed: int,
    realisation_id: int,
    stream: str,
    *,
    world_id: int | None = None,
) -> np.random.Generator:
```

- Entropy is `[base_seed, realisation_id, stream_entropy(stream)]` exactly as
  now, and `world_id` is **appended** when it is not `None`:
  `[base_seed, realisation_id, stream_entropy(stream), world_id]`. Every
  existing call passes no `world_id`, so every existing draw is unchanged.
- `world_id` below zero raises `ValueError` with the same wording pattern as
  the `realisation_id` check.
- **The exposure world draw**:
  `realisation_seed(EXPOSURE_BASE_SEED, world_id, "exposure")` — the world id
  *is* the realisation id, no `world_id` keyword.
- **The urban draw**:
  `realisation_seed(BASE_SEED, realisation_id, "urban", world_id=world_id)`.
- The module docstring gains a paragraph on worlds versus earthquakes (plan §2).
- Tests added to `tests/landloss/hazard/test_realisation.py`: a call without
  `world_id` matches the pre-change draws (assert against the existing
  `draws()` helper); two world ids give different draws for the same
  earthquake and stream; the same `(base, r, stream, w)` reproduces; a
  negative `world_id` is refused.

## 3. Steps in run order

Config keys are given per step. `PILOT` is always
`# Whether to run over the small Wellington pilot box` and is `True` in the
committed file. `WORLD_IDS = [0]` and `REALISATION_IDS = [0]` where present.
Every path function returns a `Path`. The pilot extent is `SMALL_WLG_PILOT`;
the full extent is the bounding box of `get_study_areas()`, exactly as
`gen_multiscale_slope.resolve_extent` does.

**[decided here]**: implementers are required to make the **pilot** run. A
full-extent 1 m run is the project lead's to launch; where a step cannot carry
the full extent in memory the implementation plan of that step says so and
names tiling as its next phase.

### 3.0 Shaking step 5 — `hazard/shaking/steps/s5_pgv_realisation/` (phase 0)

Scripts: `gen_pgv_realisations.py`.

`config.py`: `PILOT`, `REALISATION_IDS`, `RETURN_PERIOD_YR = 2500`.

Method: reads the step 3 PGV grid
(`s3_pgv.gen_pgv.output_path("pgv", return_period_yr=..., pilot=...)`) and
scales it by the **same** lognormal factor step 4 applied to PGA. Step 4 does
not write its factor, so **[decided here]** step 5 recomputes it from the same
seed: `beta_scale_factor(realisation_seed(BASE_SEED, realisation_id, "shaking"))`
from `landloss.hazard.shaking.pga`, which is the first and only draw
`beta_pga_realisation` makes on that generator. Phase 0 adds a test to
`tests/landloss/hazard/shaking/test_pga.py` asserting that
`beta_pga_realisation(pga, rng)[1]` equals `beta_scale_factor(rng_copy)` for a
generator seeded the same way, so the two steps cannot drift.

Path function and output:

- `pgv_path(realisation_id, *, pilot)` →
  `temp/hazard/shaking/pgv-r<NNN>[-pilot].tif`, float32, band name `pgv_m_s`,
  on the step 2 site class 100 m grid, NaN where step 3 had none.

Prints: the realisation id, the factor, median and max PGV.

### 3.1 Landslide step 3, extended — `hazard/landslide/steps/s3_multiscale_slope/`

Scripts: `gen_multiscale_slope.py` (exists, extended),
`gen_terrain_derivatives.py` (new), `fig_terrain_derivatives.py` (new; the
derivatives over the pilot, to
`report/hazard/landslide/terrain-derivatives/fig/`), `fig_multiscale_slope.py`
(new; slope and aspect per scale, to
`report/hazard/landslide/multiscale-slope/fig/`).

`config.py`:

| Key | Value | Read by |
| --- | --- | --- |
| `PILOT` | `True` | both |
| `RESOLUTIONS_M` | `(1, 3, 10, 30, 50, 100)` | `gen_multiscale_slope.py` |
| `USE_CACHED_DEM` | `True` | `gen_multiscale_slope.py` only (`gen_terrain_derivatives.py` reads the DEMs step 3 wrote and fetches only the DSM) |
| `USE_CACHED_DSM` | `True` | `gen_terrain_derivatives.py` |
| `FACE_HEIGHT_WINDOWS_M` | `(5.0, 10.0)` | `gen_terrain_derivatives.py` |
| `RESIDUAL_BASE_RESOLUTIONS_M` | `(30, 100)` | `gen_terrain_derivatives.py` |
| `TOPOGRAPHIC_POSITION_WINDOWS_M` | `{20.0: 3, 100.0: 10}` (window m → DEM resolution it is computed on) | `gen_terrain_derivatives.py` |
| `CURVATURE_RESOLUTION_M` | `3` | `gen_terrain_derivatives.py` |

**[decided here]**: 100 m stays in `RESOLUTIONS_M` because the cut-and-fill
residual reads the 100 m surface and the step wrote it already. The least
common multiple is 300 m, as now.

`gen_multiscale_slope.py` changes: per resolution it also writes the aspect,
computed by `landloss.common.utils.terrain.downhill_azimuth_degrees` (degrees
clockwise from grid north, pointing downslope; this is the study's aspect, and
**[decided here]** no new `aspect_degrees` function is added). The 1 m DEM is
fetched at 1 m (`get_dem(..., resolution=1)`); the existing block-mean chain
builds every coarser grid from it.

Path functions (keep `output_path(kind, resolution_m, *, pilot)`; add one
wrapper per output kind so callers never spell the kind):

- `dem_path(resolution_m, *, pilot)` → `temp/hazard/landslide/dem-<n>m[-pilot].tif`
- `slope_path(resolution_m, *, pilot)` → `temp/hazard/landslide/slope-<n>m[-pilot].tif`
  (band `slope_degrees`)
- `aspect_path(resolution_m, *, pilot)` → `temp/hazard/landslide/aspect-<n>m[-pilot].tif`
  (band `downhill_azimuth_degrees`)

`gen_terrain_derivatives.py` reads the 1, 3, 10, 30 and 100 m DEMs the script
above wrote and the LINZ 1 m DSM, and writes under
`temp/hazard/landslide/terrain/`. Path function
`terrain_path(layer, *, pilot)` keyed on `TERRAIN_LAYERS`, a dict of layer key
→ band name, with these keys and files:

| Key | File | Grid | Band | Method |
| --- | --- | --- | --- | --- |
| `face-height-5m` | `face-height-5m[-pilot].tif` | 1 m | `local_relief_m` | `terrain.local_relief(dem_1m, 1, 5)` |
| `face-height-10m` | `face-height-10m[-pilot].tif` | 1 m | `local_relief_m` | `terrain.local_relief(dem_1m, 1, 10)` |
| `cut-fill-residual-30m` | `cut-fill-residual-30m[-pilot].tif` | 1 m | `cut_fill_residual_m` | `terrain.cut_fill_residual(dem_1m, dem_30m)`; negative = cut, positive = fill |
| `cut-fill-residual-100m` | `cut-fill-residual-100m[-pilot].tif` | 1 m | `cut_fill_residual_m` | `terrain.cut_fill_residual(dem_1m, dem_100m)` |
| `profile-curvature` | `profile-curvature-3m[-pilot].tif` | 3 m | `profile_curvature_per_m` | `terrain.profile_curvature(dem_3m, 3)` |
| `topographic-position-20m` | `topographic-position-20m[-pilot].tif` | 3 m | `topographic_position_m` | `terrain.topographic_position(dem_3m, 3, 20)` |
| `topographic-position-100m` | `topographic-position-100m[-pilot].tif` | 10 m | `topographic_position_m` | `terrain.topographic_position(dem_10m, 10, 100)` |
| `vegetation-height` | `vegetation-height[-pilot].tif` | 1 m | `vegetation_height_m` | `terrain.vegetation_height(dsm_1m, dem_1m)`; NaN where no DSM |

**[decided here]**: curvature on the 3 m DEM, not 1 m, because 1 m LiDAR
curvature is survey noise; the two topographic position windows are computed
on the 3 m and 10 m DEMs respectively, so a 100 m window is 11 cells, not 101.
The DSM comes from a new reader `landloss.io.readers.get_dsm(bbox, resolution,
crs, *, use_cache)` mirroring `get_dem`'s signature and caching (via
`linz_stac_utils` where it offers a DSM product, otherwise by the `/dsm_1m/`
collections the STAC walk in `landloss.io.elevation` already notes), cached
under `koopcache_dir("dsm")`, with its own `Licence:` and `Source:` docstring
sections (section 7.15).
Where no DSM survey covers a cell the vegetation height is NaN, and the method
file says so.

As built (phase 1, accepted): `gen_terrain_derivatives.py` carries
`TERRAIN_FILE_STEMS` beside `TERRAIN_LAYERS`, so the curvature file name
carries `CURVATURE_RESOLUTION_M` and a run on another cell size cannot
overwrite it; the derivatives are written float32; each carries a NaN border
half its window wide inside the extent, because the DEMs on disk are trimmed
before the windows run, so a downstream reader of
`topographic-position-100m` near the extent edge NaN-fills (step 1's seeding
weight); `profile_curvature` returns 0.0, not NaN, where the gradient is
exactly zero. `tests/landloss/hazard/landslide/test_multiscale_slope_step.py`
exercises both scripts end to end on synthetic DEMs with `fetch_dem` and
`get_dsm` faked (A's test footprint, section 11).

Prints: per layer the grid, NaN count and deciles.

### 3.2 Landslide step 4 — `hazard/landslide/steps/s4_ground_map/` (new)

Scripts: `gen_ground_map.py`, `fig_ground_map.py` (material and modification
over the pilot, to `report/hazard/landslide/ground-map/fig/`).

`config.py`: `PILOT`, `USE_CACHED_LAYERS = True`,
`DEFAULT_GROUNDWATER_DEPTH_M = 4.0` (the same value step 2 assumes off the NLM
footprint), `RESIDUAL_MODIFICATION_THRESHOLD_M = 1.0` (a 30 m residual beyond
this magnitude marks cut or fill where no mapping reaches).

Inputs: `get_wellington_urban_geology`, `get_slide_interpreted_materials`,
`get_slide_genesis` (filtered to the claiming `Type` values of section 9.2
before each `GroundSource` is built), `get_wcc_cut_areas`, `get_wcc_fill_areas`,
`get_nlm_geomorphology`, `get_nlm_flatland` (reprojected to `DEFAULT_CRS`),
`get_gwd_median_depth`, the 30 m and 100 m residual rasters from step 3, and
`wellington-greywacke-strength.csv` read with `pd.read_csv` from
`ground_map.STRENGTH_TABLE_PATH`. **[decided here]**: QMAP is not read in
this build (no reader exists); off every source the material is `unknown`.
NZGD boreholes are a later phase, as the plan says.

The two rasters become polygon sources before `build_ground_map` sees them:
the script polygonises the GWD median depth raster (`get_gwd_median_depth`
returns a `Path`) clipped to the flatland with `rasterio.features.shapes`,
one polygon per run of equal-valued cells carrying `gw_depth_m`, and
polygonises the thresholded 30 m residual the same way (section 9.2). The GWD
cells fragment the flatland only, which the urban domain excludes.

Method: `landloss.hazard.landslide.ground_map.build_ground_map()` (section 7.3)
unions every source's boundaries into one planar partition and gives each
piece its attributes by precedence (section 9). No probability anywhere.

As built (phase 1, accepted):

- `fill_thickness_m` is computed in the script
  (`gen_ground_map.mean_positive_residual`: the fill pieces burned onto the
  1 m 100 m-residual grid, mean of the positive cells per piece), not as a
  polygonised `GroundSource`, because polygonising a continuous 1 m residual
  would fragment the partition. `build_ground_map` still accepts a
  `fill_thickness_m` source and applies the fill-only rule; the script passes
  none and fills the column in `finish()`.
- A `GroundSource` carries one confidence, so the SLIDE materials layer becomes
  three sources named `slide_materials` (high, medium, low, in that order;
  `gen_ground_map.slide_material_sources`), with the layer's qualified entries
  `high (verified GE)` and `high (post-2013 modified)` folded onto `high`
  (`slide_confidence`). The genesis layer likewise becomes three sources
  (`genesis_sources`): cut slope, fill body and landfill (modification, high);
  dam (modification, low); landslides and rockfall (prior failure, low).
- Where no source reaches, `material_source`, `modification_source` and
  `prior_failure_source` are `assumed` and `material_confidence` and
  `modification_confidence` are `low`.
- A source value of water does not fill the material; the lookup continues to
  the next source. A SLIDE pond over 1:50,000 rock is `rock`; a piece that saw
  water and no ground source beneath is dropped.
- `modification_from_residual` returns `natural` between the thresholds and
  `unknown` where the residual is NaN; the script polygonises only the cut and
  fill cells, so `unknown` modification is never written by this build.
- `gw_depth_class_from_depth` uses `<=` at the breaks (section 9.1: saturated
  at depth <= 1 m, poorly drained <= 3 m), whereas
  `susceptibility.groundwater_value` puts a depth on a break in the class
  above; the breaks themselves are imported from `susceptibility`.
- Vocabulary constants beyond section 7.3's list, all additive: `WATER`,
  `NATURAL`, `NO_PRIOR_FAILURE`, `NLM_GWD_SOURCE`, `ATTRIBUTES`,
  `GENESIS_TYPES`, `SLIDE_MATERIALS`, `GEOLOGY_MATERIALS`, `NLM_MATERIALS`,
  `GENESIS_MODIFICATIONS`, `ROCKFALL_SUBTYPES`, `WCC_MODIFICATIONS`,
  `STRENGTH_VALUE_COLUMNS`, `ROCK_MATERIALS` (the rock subset of section 9.1,
  which `exposure.rw.lines` imports).
- `material_from_nlm` lists exactly the thirteen classes of section 9.2; the
  national layer's other classes (Melange, Estuarine, Alluvial fan and plains,
  Glacial till, Tuff, Lacustrine and playa, Beach, Marine terraces and plains)
  occur nowhere over the four territorial authorities, so the mapper raises on
  them as section 7.3 says.

Path function and output:

- `ground_map_path(*, pilot)` →
  `temp/hazard/landslide/ground-map[-pilot].geoparquet`, one row per `ground_id`.

| Column | dtype | Meaning |
| --- | --- | --- |
| `ground_id` | str | `GM<7 digits>`, minted by location (section 4) |
| `material` | str | Section 9 vocabulary |
| `material_source` | str | Source name that supplied it (section 9) |
| `material_confidence` | str | `high`, `medium`, `low` |
| `modification` | str | `cut`, `fill`, `natural`, `unknown` |
| `modification_source` | str | as above |
| `modification_confidence` | str | as above |
| `is_flatland` | bool | Inside an NLM flatland polygon |
| `flatland_version` | str | `FLATLAND_NLM_VERSION` |
| `gw_depth_m` | float64 | NLM median depth from the polygonised GWD source; `DEFAULT_GROUNDWATER_DEPTH_M` off the footprint |
| `gw_depth_class` | str | `saturated`, `poorly_drained`, `well_drained`; derived from `gw_depth_m` by `gw_depth_class_from_depth` |
| `gw_source` | str | `nlm_gwd` or `assumed` |
| `prior_failure` | str | `relict`, `recent`, `none` |
| `prior_failure_source` | str | as above |
| `fill_thickness_m` | float64 | From the 100 m residual where positive and modification is fill; NaN otherwise |
| `geology_value` | float64 | Kingsbury F_geology, 0–10, from `material` (section 9); NaN for `unknown` |
| `c_kpa` | float64 | The chosen strength row's `c_eff_kpa` (renamed); NaN for `unknown` |
| `phi_deg` | float64 | The chosen row's `phi_eff_deg` (renamed); NaN for `unknown` |
| `unit_weight_kn_m3` | float64 | The chosen row's `unit_weight_kn_m3`; NaN for `unknown` |
| `strength_source` | str, nullable | The `record_id` of the strength table row used; null for `unknown` |
| `area_m2` | float64 | Polygon area |
| `geometry` | Polygon | EPSG:2193 |

The strength row for a grade is the one `strength_from_material` picks
(section 7.3): among the rows of that `grade` carrying **all three** of
`c_eff_kpa`, `phi_eff_deg` and `unit_weight_kn_m3`, the first with `check`
false before true, then `source_type == "published"` before the rest, then
file order. **[decided here]**: the unit weight is required because the
Kingsbury and strength readers downstream take the three together, and a row
missing one is not a set. A grade named in `STRENGTH_GRADE_PICKS` reads the
row it names instead: `FILL` reads `S52` (the lead, 2026-10-02; step 4 plan,
phase 2). On the CSV as committed this picks `S30` (RS), `S17` (HW), `S10`
(MW), `S20` (CW, the only CW row with a unit weight, `check` true), `S08`
(COL) and `S52` (FILL); the test asserts them so a CSV edit that moves a pick
is seen.

Prints: area share by material, by modification, by prior failure, and by
source for each attribute; the strength row chosen per grade.

### 3.3 Landslide step 5 — `hazard/landslide/steps/s5_slope_units/` (new)

Scripts: `gen_slope_units.py`, `fig_slope_units.py` (units coloured by aspect
over the pilot, to `report/hazard/landslide/slope-units/fig/`).

`config.py`: `PILOT`, `CHANNEL_THRESHOLD_HA = 5.0`,
`CHANNEL_THRESHOLDS_TRIED_HA = (1.0, 5.0, 20.0)` (the sensitivity the run
reports: unit count and median area at each), `ASPECT_MERGE_TOLERANCE_DEG = 45.0`,
`MIN_UNIT_AREA_HA = 1.0`, `MAX_UNIT_AREA_HA = 50.0`.

Inputs: the 10 m DEM, slope and aspect from step 3 (`dem_path(10, pilot=...)`,
`slope_path(10, pilot=...)`, `aspect_path(10, pilot=...)`); the ground map's
`is_flatland`.

Method: `landloss.hazard.landslide.slope_units.delineate_slope_units()`
(section 7.4). **[decided here]**: built on the repository's own
`landloss.common.utils.hydrology` (priority flood, D8 receivers, accumulation),
not on pysheds; see section 12. **[decided here]**: units are delineated over
the whole extent and none is dropped; each carries `flatland_share`, and step 1
places failures only where the coverage raster carries a value.

As built (phase 1, accepted): routing is `hydrology.route_grid(dem, *, dx_m,
dy_m) -> FlowRouting` (a NamedTuple of `filled`, `order`, `receiver`,
`upstream_area_m2`), the one addition to `hydrology.py`; a cell whose flow
leaves the grid before reaching a channel (edge and coastal slopes) takes the
nearest catchment by distance transform, so no cell is outside every unit;
`split_by_aspect_variance` falls back to a positional (x, y) k-means when the
aspect k-means is degenerate (a uniform-aspect unit, or a smaller cluster
under 5% of the cells), without which such a unit could never be split;
`delineate_slope_units` alternates split and merge up to three passes,
because absorbing a sub-minimum fragment can push a unit back over the
maximum; `merge_similar_aspect` returns `basin_id`, `side`, `area_m2`,
`mean_aspect_degrees` and `geometry` only, and a merged unit takes the
`basin_id` and `side` of the larger of the pair; `delineate_slope_units`
re-reads every statistic off the rasters afterwards, with its own private
circular mean and standard deviation (replacing them with
`terrain.mean_azimuth_degrees` and `azimuth_sd_degrees` is an open box in the
step's plan).

Path function and output:

- `slope_units_path(*, pilot)` →
  `temp/hazard/landslide/slope-units[-pilot].geoparquet`, one row per `unit_id`.

| Column | dtype | Meaning |
| --- | --- | --- |
| `unit_id` | str | `SU<7 digits>`, minted by location |
| `basin_id` | int64 | The channel-link sub-basin the unit was cut from |
| `side` | str | `left` or `right` of the channel, looking downstream |
| `area_m2` | float64 | |
| `mean_slope_degrees` | float64 | Mean 10 m slope |
| `mean_aspect_degrees` | float64 | Circular mean of the 10 m downhill azimuth |
| `aspect_sd_degrees` | float64 | Circular standard deviation |
| `min_elevation_m` | float64 | |
| `max_elevation_m` | float64 | |
| `relief_m` | float64 | max minus min |
| `flatland_share` | float64 | Share of the unit on NLM flatland, 0–1 |
| `channel_threshold_ha` | float64 | The threshold the run used |
| `geometry` | Polygon | EPSG:2193 |

Prints: unit count, area deciles, the sensitivity table across the thresholds
tried.

### 3.4 Landslide step 6 — `hazard/landslide/steps/s6_urban_slope_candidates/` (new)

Scripts: `gen_urban_slope_candidates.py`, `fig_urban_slope_candidates.py`
(candidates per scale over the pilot, to
`report/hazard/landslide/urban-slope-candidates/fig/`).

`config.py`: `PILOT`, `USE_CACHED_LAYERS = True`, `SCALES_M = URBAN_SCALES_M`
(imported from constants, not retyped), `BUILDING_DISTANCE_M = URBAN_BUILDING_DISTANCE_M`
(same), `MIN_PATCH_CELLS = 9` (the single definition of the minimum patch;
passed as `delineate_candidates(min_patch_cells=config.MIN_PATCH_CELLS)`),
`MAX_PATCH_LENGTH_M = 25.0` (**[decided here]**: the mean GNS SLIDE wall
segment length, 280 km / 11,288; replaced by failure widths from the rainfall
inventory when supplied). No `ROAD_HALF_WIDTH_M`: `road_distance_m` is the
distance to the centreline, and the buffered road is step 7's barrier.

Inputs: slope and aspect rasters at 1, 3, 10 and 30 m, the 1 m DEM
(`dem_path(1, pilot=...)`, for `relief_m` and `building_position`), every
terrain derivative, the ground map, `get_nz_building_outlines`,
`get_nz_address_roads`, `get_nz_property_boundaries`, `get_nlm_flatland`.
Walls are not read.

Method: `landloss.hazard.landslide.urban.delineation` (section 7.5). The
domain is the union of building outlines buffered by `BUILDING_DISTANCE_M`
minus the NLM flatland. At each scale the slope is banded and the aspect
binned into octants; same-band same-octant 4-connected cells form patches;
patches under `MIN_PATCH_CELLS` are merged into the neighbour sharing the
longest edge; patches longer than `MAX_PATCH_LENGTH_M` along the contour are
split; terrain and ground attributes are read onto each patch. Every band,
the gentlest included, produces candidates.

As built (phase 1, accepted): `label_patches` classes cells as
`band * (ASPECT_OCTANTS + 1) + octant + 1`, not `band * ASPECT_OCTANTS +
octant`, because with the literal formula a level cell in band 0 (octant -1)
collides with the outside class; the behaviour of section 10 is unchanged. The
pieces of a contour-split patch carry the whole patch's `slope_degrees` and
`aspect_degrees`. A small patch with no neighbour at all (an island) is kept.
The script's `read_zonal` falls back to `terrain.sample_at_points` at the
representative point where `zonal_statistic` is NaN (a 1 m patch holds no
cell centre of a 10 or 30 m raster). `delineation.contour_length_m(geometry,
aspect_degrees)` is public so step 7 recomputes it rather than restating it,
and the module carries `NO_CLASS`, `OUTSIDE`, `FOUR_CONNECTED` and
`CANDIDATE_COLUMNS` as named values.

Path function and output:

- `urban_slope_candidates_path(*, pilot)` →
  `temp/hazard/landslide/urban-slope-candidates[-pilot].geoparquet`, one row
  per `candidate_id`, nested rows across scales allowed.

| Column | dtype | Meaning |
| --- | --- | --- |
| `candidate_id` | str | `UC<7 digits>`, minted by (scale descending, then location) |
| `scale_m` | int64 | The delineation scale |
| `slope_band` | str | `0-10`, `10-20`, `20-30`, `30-45`, `45-60`, `60+` |
| `aspect_octant` | int64 | 0 (N) to 7 (NW), clockwise |
| `slope_degrees` | float64 | Mean slope at `scale_m` |
| `aspect_degrees` | float64 | Circular mean downhill azimuth at `scale_m` |
| `slope_1m`, `slope_3m`, `slope_10m`, `slope_30m` | float64 | Mean slope at each scale |
| `face_height_5m`, `face_height_10m` | float64 | Max local relief in the patch, each window |
| `cut_fill_residual_30m`, `cut_fill_residual_100m` | float64 | Mean residual |
| `profile_curvature` | float64 | Mean, 1/m |
| `topographic_position_20m`, `topographic_position_100m` | float64 | Mean, m |
| `vegetation_height_m` | float64 | Mean; NaN where no DSM |
| `building_distance_m` | float64 | Distance to the nearest building outline |
| `building_position` | str | `above`, `below`, `beside`: the patch centroid's elevation against the nearest outline's centroid, `beside` within ±1 m |
| `road_distance_m` | float64 | Distance to the nearest road centreline |
| `boundary_distance_m` | float64 | Distance to the nearest property boundary |
| `ground_id` | str | Ground map polygon at the representative point |
| `material`, `modification`, `prior_failure`, `gw_depth_class` | str | Copied from that polygon |
| `gw_depth_m`, `fill_thickness_m`, `geology_value` | float64 | Copied from that polygon |
| `relief_m` | float64 | Max minus min 1 m elevation inside the patch |
| `area_m2` | float64 | |
| `contour_length_m` | float64 | Length of the patch across the slope (perpendicular to `aspect_degrees`) |
| `geometry` | Polygon | EPSG:2193 |

Prints: candidate count and area by scale and band, nesting depth
distribution.

### 3.5 Exposure rw step 6 — `gen_wall_lines.py` (new, in `exposure/rw/steps/s6_wall_population/`)

Scripts: `gen_wall_lines.py`, `fig_wall_lines.py` (lines by source over the
pilot, to `report/exposure/rw/wall-lines/fig/`).

`config.py` of the step gains `USE_CACHED_LAYERS = True` (exists) and
`USE_CACHED_DEM` stays (unused by this script once it reads step 3's rasters
rather than fetching; keep for `gen_wall_probability.py` until phase 2 removes
it). It also gains `ROAD_FRONTAGE_DISTANCE_M = 5.0`.

Inputs: the terrain derivatives, the 3 m slope and aspect and the 10 m slope
from step 3 (`slope_path(3, pilot=...)`, `aspect_path(3, pilot=...)`,
`slope_path(10, pilot=...)`), the ground map, `get_gns_slide_morphology`
(mapped walls and cut/fill lines), `get_slide_genesis` (cut slope and fill body
edges), the claim properties
`build_claim_properties(get_nz_property_boundaries(...))`
(`landloss.exposure.land.extent`, one polygon per claim carrying `claim_id`;
used both for splitting and for the claim), `get_nz_building_outlines`,
`get_nz_address_roads`, the slope candidates. The step 5 insured land is
**not** read here; `gen_wall_population.py` applies it as the coverage filter.

Method: `landloss.exposure.rw.lines.build_wall_lines()` (section 7.8), in this
order: build candidate lines from the sources in plan §1.1 (**[decided here]**
driveway edges are not a source in this build; step 5 does not write the
driveway corridors separately); snap the GNS mapped walls to the nearest
candidate polygon edge within `SNAP_TOLERANCE_M`; collapse coincident lines
from several sources into one, keeping the highest-precedence source; split
every line at property boundaries; read the face height; read the ground map;
mark fill or cut wall and flat land; drop lines whose face is under
`MIN_WALL_HEIGHT_M` **except GNS mapped walls, which are kept and classed
small** (**[decided here]**: the 1 m grid cannot resolve a sub-metre wall,
I-03, and a mapped wall is evidence one exists); mint `wall_line_id`.

Path function and output:

- `wall_lines_path(*, pilot)` →
  `temp/exposure/wall-lines[-pilot].geoparquet`, one row per `wall_line_id`,
  no probability.

| Column | dtype | Meaning |
| --- | --- | --- |
| `wall_line_id` | str | `WL<7 digits>`, minted by location |
| `source` | str | Highest-precedence source: `gns_mapped_wall`, `slide_cut_fill_line`, `slide_cut_edge`, `slide_fill_edge`, `terrain_break`, `road_frontage`, `property_boundary` |
| `is_mapped_wall` | bool | A GNS mapped wall lies within `SNAP_TOLERANCE_M` along the line |
| `claim_id` | str, nullable | The claim whose property polygon (`build_claim_properties`) the line belongs to (rule below); null on road reserve or outside every claim property |
| `face_height_m` | float64 | Median of `face-height-5m` sampled every 1 m along the line |
| `size_class` | str | `classify_wall_size(face_height_m)` |
| `wall_position` | str | `fill` or `cut` (rule below) |
| `is_flatland` | bool | Ground map at the midpoint |
| `ground_id` | str | Ground map polygon at the midpoint |
| `material`, `modification` | str | Copied from that polygon |
| `is_rock_cut` | bool | `material` is a rock class and `modification == "cut"` |
| `slope_degrees` | float64 | 3 m slope at the midpoint |
| `aspect_degrees` | float64 | 3 m downhill azimuth at the midpoint |
| `dwelling_age_decade` | Int64, nullable | Null in this build (no age source held) |
| `length_m` | float64 | |
| `geometry` | LineString | EPSG:2193 |

Rules **[decided here]**:

- `claim_id`: the claim whose property polygon (`build_claim_properties`, not
  the step 5 insured extent, which is a building buffer plus driveways and
  would leave a wall elsewhere on the property claim-less) contains the line's
  midpoint. A line lying along a boundary (within `SNAP_TOLERANCE_M` of it for
  more than half its length) takes the claim on the **uphill** side for a fill
  wall and the **downhill** side for a cut wall, because the fill-platform owner
  built the fill wall and the one who cut into the hill built the cut wall.
  The rule therefore runs after `wall_position()` and reads `wall_position`
  and `aspect_degrees` (section 7.8).
- `wall_position`: `fill` when `cut-fill-residual-30m` sampled 3 m uphill of the
  midpoint (along `aspect_degrees` reversed) is ≥ 0, else `cut`.
- Terrain breaks come from the 1 m candidates: the shared edge between a patch
  in a band at or above 45 degrees and a lower neighbour in a band below 20
  degrees (the toe of a steep face), where the steep patch's `face_height_5m`
  is at least `MIN_WALL_HEIGHT_M`.
- Road frontages are property boundary segments within `ROAD_FRONTAGE_DISTANCE_M`
  of a road centreline; other boundary segments are `property_boundary`. Both
  are kept only where the **10 m** slope (`slope_path(10, ...)`) at the midpoint
  is at least `MIN_SLOPING_GROUND_DEG` (5 degrees); `slope_degrees` on the
  output is the **3 m** slope, so the script passes both rasters.

As built (phase 1, accepted):

- `buildings` limits the property-boundary and road-frontage lines to within
  `URBAN_BUILDING_DISTANCE_M` of a building outline (the candidates' urban
  domain), so a rural boundary draws no line; the other sources are not
  filtered by it.
- `assign_claim` reads the uphill or downhill property `2 x tolerance_m` from
  the midpoint along the azimuth, because a line may lie up to `tolerance_m`
  from the boundary on either side and a probe at `tolerance_m` could land on
  the boundary itself.
- `terrain_break_lines` takes the lower neighbour as the shared edge whose
  midpoint lies downhill of the steep patch's representative point along the
  candidate's `aspect_degrees`; the crest edge is excluded, and a steep patch
  with NaN aspect keeps every qualifying edge. `build_wall_lines` uses the
  finest scale present in the candidates frame.
- `wall_position`: a line whose aspect is NaN reads the residual at its
  midpoint; a residual that reads NaN gives `cut`.
- Off the ground map (midpoint in no polygon) `material` and `modification`
  are `unknown`, `ground_id` is None and `is_flatland` False; the ground map
  partitions the extent, so this is off the extent only.
- Property boundary pieces are the noded, line-merged union of the claim
  property boundaries, so a piece runs between junctions and may turn a lot
  corner; `snap_to_candidate_edges` snaps vertex by vertex onto the nearest
  candidate boundary within tolerance. Both are listed in the step's plan as
  improvements (a split at sharp angles; a whole-line snap).
- `CUT_FILL_LINE_TYPE = "Cut/fill line"`, from the GNS morphology `Type`
  values the WCC earthworks research script recorded.

Prints: line count and length by source, by size class, by position, share
with a claim, share on flat land.

### 3.6 Landslide step 7 — `hazard/landslide/steps/s7_urban_slope_polygons/` (new)

Scripts: `gen_urban_slope_polygons.py`, `fig_urban_slope_polygons.py`
(polygons with their wall edges and one state's fixed geometry over the pilot,
to `report/hazard/landslide/urban-slope-polygons/fig/`).

`config.py`: `PILOT`, `USE_CACHED_LAYERS = True`, `ROAD_HALF_WIDTH_M = 5.0`
(runout barrier width).

Inputs: the candidates, the wall lines, the 1 m DEM, building outlines and
roads (runout barriers), the ground map (already on the candidates).

Method: `landloss.hazard.landslide.urban.geometry` (section 7.6). Snap
candidate edges within `SNAP_TOLERANCE_M` onto wall lines; split a candidate
that straddles a line; mint `slope_id`; record the wall line on each
polygon's edge; compute the Kingsbury rating and the amplification factor;
compute the fixed geometry and depth for each wall state the polygon can be in.

Path function and output:

- `urban_slope_polygons_path(*, pilot)` →
  `temp/hazard/landslide/urban-slope-polygons[-pilot].geoparquet`, one row per
  `slope_id`.

Columns: every candidate column (section 3.4, recomputed on the reconciled
geometry where it depends on geometry: `area_m2`, `relief_m`,
`contour_length_m`), `candidate_id` carried, plus:

| Column | dtype | Meaning |
| --- | --- | --- |
| `slope_id` | str | `SP<7 digits>`, minted by (scale descending, then location) |
| `piece` | int64 | Which piece of its candidate this is after `split_by_lines` (section 7.6), 0 where the candidate was not split |
| `wall_line_id` | str, nullable | The wall line on the polygon's edge; where several, the one sharing the longest edge |
| `wall_edge_length_m` | float64 | Length of that shared edge; 0 where none |
| `wall_position` | str, nullable | Copied from the line |
| `wall_face_height_m` | float64 | Copied from the line; NaN where none |
| `parent_slope_id` | str, nullable | The smallest coarser-scale polygon covering at least 90% of this one |
| `kingsbury_rating` | float64 | `susceptibility_rating()` on the polygon's own attributes (rule in section 7.6) |
| `kingsbury_zone` | Int64, nullable | `susceptibility_zone()`; null on `unknown` material, whose `geology_value` is NaN |
| `continuous_rating` | float64 | The rating with the slope factor interpolated (section 7.7) |
| `amp_factor` | float64 | 1.0 to `TOPOGRAPHIC_AMPLIFICATION_MAX` |
| `rep_point` | Point | `geometry.representative_point()`, where PGV is sampled |
| `depth_evacuated_no_wall_m`, `depth_inundated_no_wall_m` | float64 | Section 7.6 depth rules |
| `depth_evacuated_fill_wall_m`, `depth_inundated_fill_wall_m` | float64 | NaN where the state is impossible |
| `depth_evacuated_cut_wall_m`, `depth_inundated_cut_wall_m` | float64 | NaN where the state is impossible |
| `evacuated_no_wall`, `inundated_no_wall`, `imminent_no_wall` | Polygon | The fixed geometry for the no-wall state |
| `evacuated_fill_wall`, `inundated_fill_wall`, `imminent_fill_wall` | Polygon or None | Filled only when `wall_position == "fill"` |
| `evacuated_cut_wall`, `inundated_cut_wall`, `imminent_cut_wall` | Polygon or None | Filled only when `wall_position == "cut"` |
| `geometry` | Polygon | The failure polygon (the face), EPSG:2193 |

**[decided here]**: the nine state geometry columns are named exactly as
above, `<kind>_<state>` with kinds `evacuated`, `inundated`, `imminent` and
states `no_wall`, `fill_wall`, `cut_wall`. A polygon with no wall line has only
its `no_wall` columns filled; a polygon with a wall line has `no_wall` and the
one state matching the line's position, so no row ever carries three states.

As built (phase 1, accepted; the two rules marked **lead** are for the project
lead to confirm, listed under the step's plan phase 2):

- **lead** The crest and toe are the boundary segments whose outward normal
  faces uphill (crest) or downhill (toe), merged with `linemerge`, not the
  vertex rule section 7.6 gave: on the staircase outline of a raster patch at
  a diagonal aspect the vertex rule includes the side vertices and
  `offset_strip` sweeps wing-shaped strips off them. On an axis-aligned face
  the two rules agree. `crest_line` and `toe_line` return `LineString |
  MultiLineString` (multi-part on a concave face) and `offset_strip` accepts
  both.
- **lead** The inundated strip length is `max(runout_length_m(...),
  spread_runout_m(...))`, where `spread_runout_m` = evacuated area / toe
  length (the debris spread at its evacuated depth, the rule step 1's runout
  already uses), and `inundated_polygon` never sweeps less than
  `MIN_RUNOUT_M = 1.0` m. Section 7.6's `runout_length_m` measures L from the
  crest, so on a face gentler than about 40 degrees the run past the toe is
  zero, the strip would be empty and the conserved volume gave inundated
  depths of 9 m and more.
- `snap_edges_to_lines` first projects each vertex within the tolerance onto
  the nearest point of the nearest line, then `shapely.snap` and `make_valid`
  (shapely's snap moves vertices only onto a line's own vertices); a snap that
  would lose more than `MAX_SNAP_AREA_LOSS = 0.5` of the candidate's area is
  not applied; the largest polygonal part is kept after `make_valid`.
- Two orchestrators beyond section 7.6's list:
  `reconcile_candidates(candidates, lines, *, tolerance_m)` (snap, split,
  `wall_line_on_edge`, copy `wall_position` and `face_height_m` as
  `wall_face_height_m`, recompute `area_m2` and `contour_length_m`) and
  `attach_state_geometries(polygons, lines, *, barriers, tolerance_m)`
  (`state_geometries` per row plus `rep_point`). `wall_line_on_edge` returns
  a DataFrame on `polygons.index` with `wall_line_id` and
  `wall_edge_length_m`.
- `contour_length_m` is recomputed with `delineation.contour_length_m`, so
  `geometry.py` imports `delineation`. A fill wall's wedge height is floored at
  `MIN_WALL_HEIGHT_M` (a mapped wall kept small can carry a face height near
  0). The fill-wall runout uses the face's `relief_m` as section 7.6 states,
  not relief plus the retained height (the step's plan phase 3).
- `continuous_rating` is imported from `urban.fragility`, where the architect
  wrote `interpolated_slope_value` and `continuous_rating` at the phase 1
  integration so step 7 can import (section 7.7); H fills the rest of the
  module in phase 3.

Prints: polygon count by scale, share with a wall edge, zone distribution,
area deciles, `amp_factor` deciles, counts of empty or invalid state
geometries (must be zero).

### 3.7 Exposure rw step 6 — `gen_wall_probability.py` (reworked to lines) and `gen_wall_population.py` (reworked)

`config.py` after phase 2:

| Key | Value | Read by |
| --- | --- | --- |
| `PILOT` | `True` | all |
| `WORLD_IDS` | `[0]` | `gen_wall_population.py` (replaces `REALISATION_IDS`) |
| `USE_CACHED_LAYERS` | `True` | `gen_wall_lines.py` only (`gen_wall_probability.py` reads `wall_lines_path` and fetches nothing) |
| `ROAD_FRONTAGE_DISTANCE_M` | `5.0` | `gen_wall_lines.py` |

`USE_CACHED_DEM` is removed in phase 2 (nothing fetches a DEM any more).
`exposure/config.py` and `gen_exposure.py` gain `WORLD_IDS` in the same phase
and run `gen_wall_lines`, `gen_wall_probability` and `gen_wall_population` in
that order (section 11, G).

**`gen_wall_probability.py`**: reads `wall_lines_path`; the dwelling age
parquet when it exists (not in this build: `dwelling_age_decade` stays null);
the count bounds when present (later phase; not read). Writes one row per
line with the probabilities from `landloss.exposure.rw.wall_probability`
(section 7.9).

- `wall_probability_path(*, pilot)` →
  `temp/exposure/wall-probability[-pilot].geoparquet` (name unchanged, content
  changed): every wall line column, plus

| Column | dtype | Meaning |
| --- | --- | --- |
| `p_wall` | float64 | Probability the line is a wall |
| `p_wall_basis` | str | `mapped`, `source_prior`, `rock_cut`, `flatland_cap`: the last rule that set it |
| `p_poor` | float64 | Probability of poor condition given a wall |
| `p_poor_basis` | str | `height`, `age`, `default` |

**`gen_wall_population.py`**: reads the probabilities and the step 5 insured
land. Per world: `rng = realisation_seed(EXPOSURE_BASE_SEED, world_id, "exposure")`;
`landloss.exposure.rw.population.draw_wall_population(probabilities, rng)`;
drop lines with no `claim_id` (council and road-reserve walls are out of scope,
I-05); `keep_walls_on_insured_land`; `sort_by_location`; mint `rw_id` with
`mint_asset_ids(..., RW_ID_SUFFIX)`.

- `wall_population_path(world_id, *, pilot)` →
  `temp/exposure/wall-population-w<NNN>[-pilot].geoparquet` (`OUT_STEM`
  changes from `beta-wall-population` to `wall-population`).

| Column | dtype | Meaning |
| --- | --- | --- |
| `rw_id` | str | `<claim_id>-RW<nn>`, as now |
| `claim_id` | str | |
| `wall_line_id` | str | The line that drew the wall |
| `world_id` | int64 | |
| `size_class` | str | From the line |
| `initial_condition` | str | `modern` or `poor`, drawn |
| `height_m` | float64 | `face_height_m` of the line |
| `length_m` | float64 | |
| `wall_position` | str | `fill` or `cut` |
| `is_flatland` | bool | |
| `source` | str | |
| `material` | str | |
| `geometry` | LineString | The line geometry, EPSG:2193 |

**[decided here]**: `height_m` is the DEM face height, from `MIN_WALL_HEIGHT_M`
upward and unbounded above (a 15 m fill batter is `large`), so the realised
ranges behind `.agents/plans/asset-pricing-approach.md` §1.1 (0.4–1.0,
1.0–2.5, 2.5–3.0 m, from the deleted `beta_wall_height_m`) become 0.5–1.0,
1.0–2.5 and 2.5+ m. The set heights `loss` prices at (0.75, 1.75, 2.75 m)
stand until the loss owner re-confirms them against the new ranges, logged
under I-14; `height_m` stays on this file for that review and is not handed
to `loss` in this build (section 3.15, contract columns unchanged).

Prints: world id and stream; lines drawn over lines offered; expected count;
`describe_population()`; the coverage filter counts; share on flat land;
`height_m` deciles by size class.

As built (phases 2 to 4, accepted, G):

- (Superseded 2026-10-05: the wall unit claim update in landslide step 12
  replaces this and `apply_count_bounds` is removed;
  `.agents/plans/placing-retaining-walls-on-pifs.md`.)
  `apply_count_bounds(p_wall, claim_ids, bounds)` is built in
  `wall_probability.py`, beside the probability it scales, not in
  `population.py` (section 7.10 amended); it is tested and not called, because
  no bounds file is held. `BOUNDS_COLUMNS = ("min_walls", "max_walls")` names
  the table it will read.
- `p_wall` reads source, rock cut, flat land and mapped wall only, and `p_poor`
  height and age only, as section 7.9 specifies; the plan §3.2 inputs not
  built (slope, height, position and subdivision age into `p_wall`, wall type
  into `p_poor`) are open boxes in the step's plan.
- `gen_exposure.main` runs the three scripts after the insured land and
  dwellings steps; `exposure/config.py` carries `WORLD_IDS = [0]`.
- Neither script has been run over the pilot: `gen_wall_lines.py` reads
  landslide steps 3, 4 and 6 and `gen_wall_population.py` step 5's insured
  land. Both run end to end on synthetic inputs in the tests.

Review correction (2026-10-02, decision 36; built, G): the
claim filter and `keep_walls_on_insured_land` decide what is insured, not
whether a wall stands. A road retaining wall above or below a property, or a
wall at the back of a section more than `RW_COVERAGE_BUFFER_M` from the insured
land, still holds the slope in world `w`. So `gen_wall_population.py` also
writes every wall the world drew, before either filter:

- `drawn_walls_path(world_id, *, pilot)` →
  `temp/exposure/drawn-walls-w<NNN>[-pilot].geoparquet`, one row per line that
  drew a wall in world `w`, in line order; `wall_line_id` is unique in it.
  Columns: those of the population table above, in the same order, with
  `rw_id` and `claim_id` **nullable**. `rw_id` is the minted id joined back on
  `wall_line_id` where the wall survived both filters, and null for a
  claimless council or road-reserve wall and for one off its claim's insured
  land.

It is written in the same world loop after `rw_id` is minted, so the draw and
the stream are unchanged and `wall_population_path(w)` stays the insured
subset that vul and loss read. Landslide step 8 reads the drawn walls
(section 3.8); nothing else does. Prints: the count drawn, and how many carry
an `rw_id`.

As built (decision 36, G): as specified. The join back is
`landloss.exposure.rw.population.attach_rw_ids(drawn, population)`, which
raises `ValueError` where a `wall_line_id` repeats in the drawn walls or the
population names a line that drew no wall; the script adds `DRAWN_STEM`,
`insert_world_id` and `describe_drawn_walls`. These names are beyond the list
above; the contract's names, columns and signatures are kept. Not run over the
pilot.

### 3.8 Landslide step 8 — `hazard/landslide/steps/s8_urban_slope_fragility/` (new)

Scripts: `gen_urban_slope_fragility.py`, `fig_urban_slope_model.py` (medians
on the map over the pilot, to `report/hazard/landslide/urban-slope-model/fig/`),
`table_urban_slope_model.py` (medians by zone and wall state, to
`report/hazard/landslide/urban-slope-model/tab/urban-slope-model-medians-w<NNN>[-pilot].csv`;
the table the project lead reviews).

`config.py`: `PILOT`, `WORLD_IDS`, `URBAN_RATE = "medium"`,
`RETURN_PERIOD_YR = 2500`.

Inputs: the polygons, the drawn walls for world `w` (`drawn_walls_path(w)`,
section 3.7, decision 36), `retaining-wall-fragility.csv`, the step 2 site class grid
(`s2_site_class.gen_site_class.read_site_class(pilot=...)`), step 3's PGV grid
(`s3_pgv.gen_pgv.output_path("pgv", return_period_yr=RETURN_PERIOD_YR, pilot=...)`),
the unscaled TS1170.5 PGA on the same grid, which the step builds as step 4
does (`demand_on_site_class_grid(get_ts1170_pga, site_class, return_period_yr=RETURN_PERIOD_YR)`),
and `config.URBAN_RATE`. **[decided here]**: step 8 does not read
`urban-fragility-anchors.csv`; the localised median function's parameters are
constants in `urban/fragility.py` set by the anchoring, and the anchor CSV is
the record the validation figure draws them against.

Method: `landloss.hazard.landslide.urban.fragility.assign_fragility()`
(section 7.7). The step samples `site_class` at `rep_point` with
`terrain.sample_at_points(site_class_path(pilot=...), rep_point)` and the
PGV/PGA ratio with `pgv_pga_ratio_m_s_per_g(pgv, pga, rep_point)`, and passes
both Series in.

- `urban_slope_model_path(world_id, *, pilot)` →
  `temp/hazard/landslide/urban-slope-model-w<NNN>[-pilot].geoparquet`, one row
  per `slope_id`, **written sorted by `slope_id` with a fresh index**
  (`assign_fragility` returns it so); step 9 relies on that order.

| Column | dtype | Meaning |
| --- | --- | --- |
| `slope_id` | str | |
| `world_id` | int64 | |
| `wall_line_id` | str, nullable | |
| `rw_id` | str, nullable | The insured wall drawn on the edge in world `w`; null when the line drew none, has none, or drew a wall that is not insured (decision 36) |
| `wall_state` | str | `no_wall`, `fill_wall`, `cut_wall` |
| `wall_class` | str, nullable | `unnamed` until the six classes are named |
| `size_class`, `initial_condition` | str, nullable | From the drawn wall |
| `im` | str | `pgv_m_s` |
| `theta_base` | float64 | Median before adjustment, m/s |
| `theta_base_pga_g` | float64 | The published PGA median before conversion; NaN for localised or PGV-native curves |
| `site_class` | Int64 | TS1170.5 class at `rep_point`; null off the grid |
| `pgv_pga_ratio_m_s_per_g` | float64 | The ratio used for the conversion; NaN where none |
| `amp_factor` | float64 | |
| `rate_setting` | str | `config.URBAN_RATE` |
| `rate_factor` | float64 | `URBAN_RATE_FACTORS[rate_setting]` |
| `theta` | float64 | `theta_base / amp_factor * rate_factor` |
| `beta` | float64 | |
| `fragility_basis` | str | `wall` or `localised` |
| `fragility_source` | str | The CSV `source` of the wall row, or `localised:<continuous_rating:.0f>` |
| `kingsbury_rating`, `kingsbury_zone`, `continuous_rating` | as step 7 | |
| `scale_m`, `area_m2`, `slope_degrees`, `material`, `modification`, `face_height_10m` | as step 7 | For review |
| `depth_evacuated_m`, `depth_inundated_m` | float64 | The state's depths |
| `rep_point` | Point | |
| `evacuated`, `inundated`, `imminent` | Polygon | The state's fixed geometry |
| `geometry` | Polygon | The face |

Prints: world id, rate setting and factor, counts by wall state and basis,
median `theta` by zone and state, the `amp_factor` and ratio ranges.

As built (phases 2 to 4, accepted, H):

- Script names as above (`fig_urban_slope_model.py`,
  `table_urban_slope_model.py`). The table carries `zone_label`,
  `fragility_basis`, `median_theta_base_m_s`, `median_amp_factor` and
  `median_beta` beside the medians, so the three parts of each adjusted median
  can be reviewed side by side.
- `retaining-wall-fragility.csv` holds six `unnamed` rows from
  [koutsoupaki_2023] (Fs = 1.5 modern, Fs = 1.1 poor; 3 m wall for small and
  medium, 6 m for large; DS3, `Ux = 10% H` after [prakash_1995], on PGA), and
  `urban-fragility-anchors.csv` is filled; the class-word fractions are
  implementer judgement for the lead's review. The paper is kept in
  `context/lit/landslide/koutsoupaki_2023/`.
- Not run over the pilot: the step reads step 7, exposure step 6 and shaking
  steps 2 and 3. It runs end to end on synthetic inputs in the tests.

Review correction (2026-10-02, decision 36; built, H): step 8
joins the polygons to `drawn_walls_path(w)` (section 3.7) in place of
`wall_population_path(w)`, with flat-land walls excluded, so a polygon whose
edge line drew a sloping wall that is not insured still takes the wall state,
the wall curve and the wall's evacuated, inundated and imminent geometry.
`assign_fragility` first keeps the walls a polygon may take with
`fragility.sloping_walls(walls)`, which drops every row whose
`fragility.IS_FLATLAND_COLUMN` (`is_flatland`) is true and every row with a
null `wall_line_id` (section 7.7); it then decides that a polygon has a wall
from its `wall_line_id` matching one of those rows, not from `rw_id`, which is
null on such a row. The script prints how many drawn walls are insured and
how many flat-land walls it skips. A flat-land wall on a polygon's edge leaves
the polygon `no_wall` whether or not it is insured, as section 5.1 has it; an
uninsured flat-land wall is drawn by no step, because vul shaking rw step 9
reads only the insured population. Step 9's wall outcome table is unchanged: it spines on
the insured population, so a polygon carrying an uninsured wall gives no wall
a row, while its ground is still modelled with the wall.

### 3.9 Landslide step 1, reworked — `hazard/landslide/steps/s1_landslide_realisation/`

Scripts: `s1_simulate_landslides.py` (name kept), `fig_landslide_realisation.py`
(exists, re-pointed).

`config.py`: `PILOT`, `REALISATION_IDS` (`USE_CACHED_DEM` is removed: the
step reads step 3's rasters and fetches nothing),
`LARGE_MIN_SOURCE_AREA_M2 = 700.0` (**[decided here]**: the top of the urban
size range, plan §10.3), `URBAN_AREA_SHARE = 0.25` (**[decided here]**:
placeholder for the share of the calibration inventory's area inside the urban
range; a research script measures it from `landloss.io.kaikoura` later; printed
by every run), `SOURCE_ASPECT_RATIO = 2.0` (**[decided here]**: downslope
length to across-slope width of a source ellipse, placeholder for the Kaikōura
ratio), `CREST_WEIGHT = 0.5` (how much `topographic-position-100m` lifts a
cell's seeding weight).

Inputs: the EIL probability grid as now (32 m), the slope units
(`slope_units_path`), and from step 3 `dem_path(10)`, `slope_path(10)`,
`aspect_path(10)` and `terrain_path("topographic-position-100m")` (10 m grid).
**[decided here]**: the working grid is the 10 m DEM grid: the probability is
resampled onto it with `rio.reproject_match(dem_10m, resampling=Resampling.nearest)`,
so the units (cut on that grid), `TPI_100m` and `p` share cells and every
per-cell product below is cell-aligned.

Method: per slope unit, expected failed area = Σ (cell probability × cell
area) × `BETA_SOURCE_AREA_FRACTION` × (1 − `URBAN_AREA_SHARE`) over the unit's
10 m cells (the fraction as built, below); the count is a Poisson
draw with mean expected area / mean size of the power law truncated to
`[LARGE_MIN_SOURCE_AREA_M2, MAX_SOURCE_AREA_M2]`; sizes are drawn from that
truncated law (`sample_areas` with the new lower bound); each failure is seeded
at the unit cell maximising `p × (1 + CREST_WEIGHT × clip(TPI_100m / 10, 0, 1))`
with a weighted random choice over the top ten such cells; **[decided here]**
the source is an ellipse of the sampled area, long axis along the downhill
azimuth with `SOURCE_ASPECT_RATIO`, centred half a long axis downslope of the
seed (this is "grown along the facet" in the simplest form; it crosses unit
boundaries when larger than its unit, and region growing along steepest
descent is phase 4 of that step's plan); runout as now (`displacement_from_slope`,
the ellipse translated). `drop_overlapping` stays. Areal coverage is held at
0.99% × (1 − `URBAN_AREA_SHARE`) above the new lower bound by
`BETA_SOURCE_AREA_FRACTION`, not by re-solving `SIZE_EXPONENT` (as built,
below), and the implementation plan records the numbers.

- `realisation_path(*, pilot, realisation_id)` unchanged →
  `temp/hazard/landslide/landslide-realisation-r<NNN>[-pilot].geoparquet`.

Columns as now plus `population` (str, always `large`), `unit_id` (str),
`slope_id` (str, always null), `landslide_id` **becomes str** `LS<7 digits>`,
minted by location within the realisation (section 4). `land_class` stays
`evacuated land` / `inundated land`, now imported from
`landloss.hazard.landslide.land_class` (section 7.13) instead of the script's
own literals; `depth_m` and `volume_m3` as now.

As built (phases 2 to 4, accepted, J1):

- **`SIZE_EXPONENT` is not re-solved; it stays 2.1** [massey_2020]. Under the
  Poisson count above, the realised total area equals the expected area
  whatever the exponent, so the exponent cannot carry coverage. A script
  constant `BETA_SOURCE_AREA_FRACTION = 0.252` does instead, multiplied into
  the expected area: the phase 1 calibration restated (258 m² of source per
  failing 1,024 m² cell), giving 0.74% = 0.99% × 0.75 over the full grid.
  Without it the formula would deliver about 2.9%, the whole-cell reading
  phase 1 rejected. The truncated mean on [700, 3000] m² is 1,306 m².
- Columns: `radius_m` is replaced by `semi_major_m` and `semi_minor_m`, and
  `seed_easting` and `seed_northing` are added beside `easting` and
  `northing` (the ellipse centre). Step 9 carries every extra large-row column.
- Script constants `SEED_CANDIDATE_CELLS = 10` and `CREST_FULL_LIFT_M = 10.0`
  name the "top ten" and the "/ 10" above.
- A seed cell with NaN slope or aspect takes its unit's `mean_slope_degrees`
  and `mean_aspect_degrees`, so a unit the grid expects failures in always
  places them.
- Not run: the step reads step 3 and step 5 outputs. It runs end to end on a
  synthetic three-unit plane in
  `tests/landloss/hazard/landslide/test_large_placement.py`.

### 3.10 Landslide step 9 — `hazard/landslide/steps/s9_urban_slope_realisation/` (new)

Scripts: `gen_urban_slope_realisation.py`, `fig_urban_slope_realisation.py`
(failed, absorbed and superseded polygons over the pilot, to
`report/hazard/landslide/urban-slope-realisation/fig/`). The figure reads the
two files the run wrote, through `combined_realisation_path` and
`urban_wall_outcome_path`, and draws nothing again; step 8's model file
supplies only the faces behind the map and the evacuated polygons of the
walls' polygons the outcome table names, and the figure stops if a `slope_id`
the run wrote is missing from it.

`config.py`: `PILOT`, `WORLD_IDS`, `REALISATION_IDS`.

Inputs: the model for `w`, `wall_population_path(w)` (the spine of the wall
outcome table), `pgv_path(r)`, `realisation_path(r)`.

Method: `landloss.hazard.landslide.urban.realisation` (section 7.11), plan
§5.1 steps 1 to 6. `rng = realisation_seed(BASE_SEED, realisation_id, "urban", world_id=world_id)`.
Rows stay in model-file order (sorted by `slope_id`, section 3.8), so each
polygon's uniform is tied to its id.

Path functions and outputs:

- `combined_realisation_path(world_id, realisation_id, *, pilot)` →
  `temp/hazard/landslide/landslide-realisation-w<NNN>-r<NNN>[-pilot].geoparquet`.
- `urban_wall_outcome_path(world_id, realisation_id, *, pilot)` →
  `temp/hazard/landslide/urban-wall-outcome-w<NNN>-r<NNN>[-pilot].parquet`.

Combined realisation columns (large rows keep every step 1 column; urban rows
carry null in step 1's simulation columns):

| Column | dtype | Meaning |
| --- | --- | --- |
| `realisation_id` | int64 | |
| `world_id` | int64 | |
| `landslide_id` | str | `LS<7>` for large rows; **the `slope_id`** for urban rows |
| `population` | str | `large` or `urban` |
| `slope_id` | str, nullable | Null on large rows |
| `unit_id` | str, nullable | Null on urban rows |
| `land_class` | str | `evacuated land`, `inundated land`, or `imminent land` (urban rows only) |
| `depth_m` | float64 | NaN on `imminent land` |
| `volume_m3` | float64 | Urban: `depth_evacuated_m × evacuated area` |
| `source_area_m2` | float64 | Urban: the evacuated polygon's area |
| `wall_state` | str, nullable | Urban rows |
| `rw_id` | str, nullable | Urban rows whose wall is insured; null on large rows, on `no_wall` rows and on a row whose wall is not insured (decision 36) |
| `pgv_m_s` | float64 | Sampled at `rep_point`; NaN on large rows |
| `p_fail` | float64 | Evaluated fragility; NaN on large rows |
| `uniform` | float64 | The draw; NaN on large rows |
| `geometry` | Polygon | EPSG:2193 |

**[decided here]**: a third land class `imminent land` is written. The
vocabulary lives in hazard, `landloss.hazard.landslide.land_class`
(`EVACUATED`, `INUNDATED`, `IMMINENT`; section 7.13), so no hazard module
imports `landloss.vul`; `damaged_area.IMMINENT` equals it, and the land step
ignores the class until T-45 is decided, because its `AREA_COLUMNS` filter
already excludes it. Evacuated polygons never overlap across both
populations; inundated and imminent may.

Wall outcome table, one row per wall in world `w` on sloping land
(`is_flatland` false), spined on `wall_population_path(w)` and left-joined to
the model on `rw_id` by `wall_outcomes` (section 7.11), so `claim_id` and
`wall_line_id` come from the population and a wall whose line's polygon was
not delineated still has a row; section 5 for the vocabulary:

| Column | dtype | Meaning |
| --- | --- | --- |
| `world_id` | int64 | |
| `realisation_id` | int64 | |
| `rw_id` | str | |
| `wall_line_id` | str | |
| `claim_id` | str | |
| `slope_id` | str, nullable | The polygon the wall belongs to; null when the line's polygon was not delineated (should be rare; counted and printed) |
| `outcome` | str | `standing`, `failed_with_polygon`, `absorbed`, `superseded`; `standing` where `slope_id` is null |
| `taken_by` | str, nullable | The `landslide_id` of the polygon that absorbed or superseded it; null otherwise |

Prints: world and earthquake ids, polygons by wall state, failed, absorbed,
superseded, summed and dissolved areas by `land_class` and population, the
wall outcome counts.

As built (phases 2 to 4, accepted, J2):

- `draw_failures` evaluates the curve through
  `urban.fragility.lognormal_failure_probability`. The stand-in
  `urban_slope_model_path` the step carried while step 8 was unbuilt was
  replaced at the integration by the import from `gen_urban_slope_fragility`.
- **A wall on polygons at several scales takes one outcome by rank**:
  `superseded` > `failed_with_polygon` > `absorbed` > `standing`, ties to
  model order; the winning row supplies `slope_id` and `taken_by`. For the
  lead to confirm; recorded in the step's method and plan.
- **Where several large evacuated polygons reach one urban polygon**,
  `supersede_by_large` returns the one sharing the most ground, ties to the
  earlier large row.
- `combine_with_large` sorts by `landslide_id` then `land_class`, so within
  one urban failure the rows run evacuated, imminent, inundated.
- Absorption and supersession are tested on evacuated geometry only, as above;
  an absorbed failure's inundated strip reaching past its absorber's is lost
  with it (an improvement in the step's plan). A polygon whose representative
  point is off the PGV grid has `p_fail` NaN and is not drawn; the run prints
  the count.
- Not run over the pilot.

Review corrections (2026-10-02; built, J, and recorded in the step's method
and plan):

- **One uniform per wall line (decision 34).** A wall line sits on the edges
  of polygons at several scales, and each of them takes the same wall curve
  from `assign_fragility`. With a uniform each, the wall would fail through
  some polygon with probability 1 − Π(1 − p_i) rather than the published p
  (p = 0.3 on four scales gives about 0.76), and the published curve
  [koutsoupaki_2023] is applied as given, not re-anchored as the localised
  curve is (plan §1.2). So `draw_failures` still draws one uniform per model
  row in model order, then every row whose `wall_state` is not `no_wall` takes
  the uniform of the first row in model order carrying the same
  `wall_line_id` (a common random number). Rows without a wall keep their own
  uniform, so their draws are unchanged. The wall's polygons then fail
  together where their curves agree, and `resolve_overlaps` absorbs the
  smaller into the largest. The key is `wall_line_id`, not `rw_id`, because an
  uninsured wall (decision 36) has no `rw_id` and is still one wall. As built,
  a walled row with a null `wall_line_id` also keeps its own uniform.
- **Only a failed polygon is superseded (decision 35).** `supersede_by_large`
  runs on the failed rows' evacuated geometry and its result is mapped onto
  every model row, `NONE` where the row did not fail, as `absorbed_by` is. A
  polygon that did not fail is `standing` whatever a large slide does around
  it; a wall the large slide actually reaches is flagged `is_evacuated` by vul
  step 11's line test (a positive length inside, `WALL_INSIDE_TOLERANCE_M`) with the combined realisation's `evacuated land`
  (section 5.2, row 3). So a wall is replaced only where its line is reached,
  not where a large slide grazes its polygon's headscarp band, and a coarse
  30 m polygon touching a large slide no longer writes off every wall on its
  edge. This is plan §5.1 step 4 as written ("an urban failure"). As built, the
  step resolves in this order: draw, supersede the failed rows, then absorb
  among the failed rows no large slide superseded, so every absorber is a
  survivor; `_polygon_outcomes` masks both absorption and supersession with
  `failed`, so a row that did not fail reads `standing` even if a caller hands
  it a position.

### 3.11 Vul shaking rw step 9 — `vul/shaking/rw/steps/s9_wall_damage_state/` (restricted, PGV)

`config.py`: `PILOT`, `WORLD_IDS`, `REALISATION_IDS`, `RETURN_PERIOD_YR = 2500`
(the TS1170.5 demand the PGV/PGA ratio is taken at; the same value as step 3's).

Inputs: `wall_population_path(w)`, `pgv_path(r)` (shaking step 5), the step 2
site class grid (`s2_site_class.gen_site_class.read_site_class(pilot=...)`),
step 3's PGV grid (`s3_pgv.gen_pgv.output_path("pgv", return_period_yr=RETURN_PERIOD_YR, pilot=...)`),
the unscaled PGA built as step 8 does
(`demand_on_site_class_grid(get_ts1170_pga, site_class, return_period_yr=RETURN_PERIOD_YR)`),
and the wall fragility table.

Method: **flat-land walls only** (`is_flatland` true). PGV sampled at the line
midpoint as now; `site_class` sampled there too
(`terrain.sample_at_points(site_class_path(pilot=...), midpoints)`), and the
ratio by `pgv_pga_ratio_m_s_per_g(pgv, pga, midpoints)` (section 7.7), so the
flat-land conversion is recorded exactly as the model file records it
(section 6). Failure probability from
`landloss.vul.shaking.fragility.wall_failure_probability()` (section 7.12), the
PGV-converted wall curve by class, size and condition. Draw on
`realisation_seed(BASE_SEED, realisation_id, "vulnerability", world_id=world_id)`
— the unchanged stream with the world appended (as built, below), so the
crossings' draws are unaffected; the draw order is population order.

- `wall_damage_state_path(world_id, realisation_id, *, pilot)` →
  `temp/vul/wall-damage-state-w<NNN>-r<NNN>[-pilot].geoparquet`.

Columns: `realisation_id`, `world_id`, `rw_id`, `claim_id`, `asset`
(`retaining wall`), `size_class`, `initial_condition`, `height_m`, `length_m`,
`is_flatland` (always true), `pgv_m_s`, `site_class` (Int64, null off the
grid), `theta_base_pga_g` (float64, NaN for PGV-native rows),
`pgv_pga_ratio_m_s_per_g` (float64, NaN where no conversion), `theta`, `beta`,
`fragility_source`, `failure_probability`, `damage_state`, `geometry`.

As built (phases 2 to 4, accepted, K1):

- **The draw carries the world**:
  `realisation_seed(BASE_SEED, realisation_id, "vulnerability", world_id=world_id)`.
  Accepted over the text as first written: the stream is unchanged, the
  crossings' own call is untouched, and without the world the walls and the
  crossings of one earthquake would read the same generator.
- `wall_failure_probability` computes
  `theta = theta_base / WALL_AMP_FACTOR * WALL_RATE_FACTOR` inline (both 1.0)
  rather than through `polygon_theta`, and evaluates the lognormal only where
  PGV, `theta` and `beta` are finite: a wall off the PGV grid, or on a PGA
  curve with no ratio at its midpoint, carries NaN and draws no damage; the
  run prints the count. `draw_damage_states` checks the range on finite values
  only, so an all-NaN array no longer trips warnings-as-errors.
- `PGA_IM` and `PGV_IM` in `landloss.vul.shaking.fragility` are
  `urban_fragility.PGA_IM` and `urban_fragility.IM`, re-pointed at the
  integration once section 7.7's module defined them; the test conftest that
  stood in for the unbuilt urban fragility functions was deleted then too.
- `WORLD_ID_COLUMN = "world_id"` is a literal in the step script;
  `loss_contract.py` is not changed, as this contract does not require it.
- `wall_curve` is called once per distinct `(size_class, initial_condition)`
  pair, with the same result.
- Not run over the pilot.

### 3.12 Vul landslide rw step 11 — `vul/landslide/rw/steps/s11_wall_landslide_damage/` (extended)

`config.py`: `PILOT`, `WORLD_IDS`, `REALISATION_IDS`.

Inputs: `wall_population_path(w)`, `combined_realisation_path(w, r)`,
`urban_wall_outcome_path(w, r)`.

Method: `landloss.vul.landslide.flags.wall_flags()` (section 7.13): the
outcome mapping of section 5.2 OR-ed with the geometric intersections
`landslide_flags()` finds against the combined realisation.

- `wall_landslide_damage_path(world_id, realisation_id, *, pilot)` →
  `temp/vul/wall-landslide-damage-w<NNN>-r<NNN>[-pilot].parquet`, one row per
  wall in the population.

| Column | dtype | Meaning |
| --- | --- | --- |
| `realisation_id`, `world_id` | int64 | |
| `rw_id`, `claim_id` | str | |
| `slope_id` | str, nullable | Null for flat-land walls |
| `outcome` | str, nullable | Null for flat-land walls |
| `is_damaged_by_shaking` | bool | `outcome == "failed_with_polygon"`; false for flat-land walls (their shaking flag is step 9's) |
| `is_evacuated` | bool | Section 5.2 |
| `is_inundated` | bool | Section 5.2 |

As built (phases 2 to 4, accepted, K2): as specified. The output writes
`is_damaged_by_shaking` false for flat-land walls; their shaking flag is set
in `build_rw_table` from step 9's state (section 5.2, row 5). Not run over the
pilot.

### 3.13 Vul landslide land step 3 — `vul/landslide/land/steps/s3_landslide_land_damage/` (file names)

`config.py`: `PILOT`, `WORLD_IDS`, `REALISATION_IDS`. Reads
`combined_realisation_path(w, r)`. Method unchanged. Output
`landslide_land_damage_path(world_id, realisation_id, *, pilot)` →
`temp/vul/landslide-land-damage-w<NNN>-r<NNN>[-pilot].parquet`, with a
`world_id` column inserted after `realisation_id`.

As built (phases 2 to 4, accepted, K2): as specified, with `world_id` after
`realisation_id`; `imminent land` is unmeasured. Not run over the pilot.

### 3.14 Vul landslide culverts and bridges step 11 — `vul/landslide/culverts_bridges/steps/s11_crossing_landslide_damage/` (file names)

`config.py`: `PILOT`, `WORLD_IDS`, `REALISATION_IDS`. Reads
`crossing_population_path(realisation_id, pilot=...)` (**[decided here]**: the
crossing population stays keyed on `r` in this build; moving it to worlds is a
later item) and `combined_realisation_path(w, r)`. Output
`crossing_landslide_damage_path(world_id, realisation_id, *, pilot)` →
`temp/vul/crossing-landslide-damage-w<NNN>-r<NNN>[-pilot].parquet`, with
`world_id` after `realisation_id`.

As built (phases 2 to 4, accepted, K2): as specified. The loop is
realisation-outer, world-inner, reading the crossing population once per
earthquake; only the print order differs. Not run over the pilot.

### 3.15 Vul step 10 — `vul/steps/s10_property_damage/` (file names and ids)

`config.py`: `PILOT`, `WORLD_IDS`, `REALISATION_IDS`; `vul/config.py` and
`gen_vul.py` gain `WORLD_IDS` and pass `world_ids` to every landslide and rw
step. Reads, per `(w, r)`: `insured_land_path(pilot)`,
`liq_land_damage_path(r)` (unchanged), `landslide_land_damage_path(w, r)`,
`wall_population_path(w)`, `wall_damage_state_path(w, r)`,
`wall_landslide_damage_path(w, r)`, `structure_damage_state_path(r)`
(unchanged), `crossing_landslide_damage_path(w, r)`.

`build_rw_table(walls, states, flags)` (section 7.14) spines the rw table on
the **population**, so every insured wall appears whether or not it is on flat
land. Output `loss_input_path(table, world_id, realisation_id, *, pilot)` →
`temp/vul/loss-input-<table>-w<NNN>-r<NNN>[-pilot].geoparquet`; each table
gets `world_id` inserted after `realisation_id`. Contract columns unchanged.

As built (phases 2 to 4, accepted, K2): as specified; `gen_vul.py`,
`vul/config.py`, `gen_all.py` and `scripts/landloss/config.py` carry
`WORLD_IDS`. Not run over the pilot.

Review correction (2026-10-02, decision 37; built, K): the
loss module, owned elsewhere and not edited in this build, calls
`loss_input_path(name, realisation_id, pilot=pilot)` in
`loss/steps/s0_land_cover_cap/s0_gen_land_cover_cap.py`,
`loss/steps/s1_settlement/s1_gen_settlement.py`,
`loss/ui/gen_calc_walkthrough.py` (twice) and
`loss/ui/gen_viewer_data.py`. Against the signature above each call
raises `TypeError`, with the realisation id landing in `world_id`, and no loss
test calls the path function. Until the loss owner loops over worlds, step 10
carries two path functions in place of the one above:

- `world_loss_input_path(table, world_id, realisation_id, *, pilot)` → the file
  name above. Step 10 writes through it, and every vul caller and test uses
  it; `world_id` is positional with no default, so no vul code can fall back
  on a world silently.
- `loss_input_path(table, realisation_id, *, pilot)`, the old signature,
  deprecated: returns `world_loss_input_path(table, 0, realisation_id,
  pilot=pilot)`. Its docstring says it serves the loss module only and reads
  world 0; nothing in vul calls it; a test pins that it resolves world 0 and
  matches the file step 10 writes for world 0.

The loss module therefore reads world 0 of each earthquake, which is every
world this build runs (`WORLD_IDS = [0]`). For the loss owner: move the five
calls to `world_loss_input_path(name, world_id, realisation_id, pilot=pilot)`
with a `WORLD_IDS` setting, after which the deprecated function is deleted.
The reviewer's form, `world_id` as a keyword with no default on
`loss_input_path` itself, was not taken, because the loss calls pass no
`world_id` and would still raise.

As built (decision 37, K): as specified. The deprecated function says so in
its docstring and raises no runtime `DeprecationWarning`; the step's plan
carries an open box for deleting it, and the request to the loss owner is
register task **T-66**. Not run over the pilot.

### 3.16 Validation — `hazard/landslide/validations/urban/` (new)

Files: `__init__.py`, `fig_urban_fragility_anchors.py`,
`table_urban_fragility_anchors.py`, `urban_fragility_anchors_findings.md`
(written after the first run, as the other validation folders carry a
findings file).

Inputs: `load_urban_fragility_anchors()`, the functions in `urban/fragility.py`,
the Kingsbury scenario PGAs (rows of the anchor table), and for the rock-site
ratio the TS1170.5 site class I grids `get_ts1170_sa_t1(rp, 1)` and
`get_ts1170_pga(rp, 1)` with `rp = s3_pgv.config.RETURN_PERIOD_YR`.

Outputs: `report/hazard/landslide/urban-fragility/fig/urban-fragility-anchors.png`
(one panel per zone: the low, medium and high curves on PGV against the anchor
points, with the PGA anchors converted at the rock-site ratio, **[decided here]**
the median of `pgv_m_s_from_sa_1s(sa_t1) / pga` over the site class I grid
cells inside `SMALL_WLG_PILOT`) and
`report/hazard/landslide/urban-fragility/tab/urban-fragility-anchors.csv`
(the class-word-to-fraction table: `class_word`, `fail_fraction`, `set_by`,
`basis`). No `config.py`: validations read the assets, not a run.

As built (phases 2 to 4, accepted, H): both scripts and their tests exist.
`urban_fragility_anchors_findings.md` is not written: it follows the first
run, which reads the TS1170.5 grids through the versioned-store cache and is
the project lead's to launch. The localised constants, `LOCALISED_FRAGILITY_BETA`
and the `low` and `high` rate factors stay placeholders until then. No fit of
the packaged anchors has been recorded: whether they agree with the 0.6
dispersion placed is for that run and its findings file to say.

## 4. Identifiers

| Id | Format | Minted by | Sort key before numbering |
| --- | --- | --- | --- |
| `ground_id` | `GM<7 digits>` | `gen_ground_map.py` | representative point x, then y |
| `unit_id` | `SU<7 digits>` | `gen_slope_units.py` | x, then y |
| `candidate_id` | `UC<7 digits>` | `gen_urban_slope_candidates.py` | `scale_m` descending, then x, then y |
| `wall_line_id` | `WL<7 digits>` | `gen_wall_lines.py` | x, then y |
| `slope_id` | `SP<7 digits>` | `gen_urban_slope_polygons.py` | `scale_m` descending, then x, then y |
| `rw_id` | `<claim_id>-RW<nn>` | `gen_wall_population.py` | `sort_by_location` (claim, x, y), as now; carries `wall_line_id` |
| `landslide_id` (large) | `LS<7 digits>` | `s1_simulate_landslides.py`, per realisation | x, then y of the source |
| `landslide_id` (urban) | the `slope_id` | `gen_urban_slope_realisation.py` | — |

Numbering starts at 1, `f"{prefix}{n:07d}"`. x and y are the geometry's
`representative_point()`, the sort is `kind="mergesort"` (stable) so ties keep
incoming order, and the incoming order is itself deterministic (raster
polygonisation order, or the source layer's order). An id is stable as long as
the inputs and parameters are; a changed extent renumbers, and the method
file says so.

**[decided here]**: a new module `landloss.common.utils.ids` holds the
claim-free minting so that hazard code does not import `landloss.exposure`.
Phase 0 writes it in full, with its tests, because B, C, D, E, F and J all
mint with it (section 11):

```python
def sort_by_point(
    frame: gpd.GeoDataFrame,
    *,
    by: Sequence[str] = (),
    ascending: Sequence[bool] | bool = True,
) -> gpd.GeoDataFrame
    # Sort by the columns in `by` (each ascending or descending per `ascending`,
    # one flag per column or one for all), then representative point x, then y
    # (both ascending); stable; fresh index.
def mint_ids(prefix: str, count: int, *, width: int = 7) -> pd.Series
    # f"{prefix}{n:0{width}d}" for n in 1..count.
```

D and F call `sort_by_point(frame, by=("scale_m",), ascending=(False,))`; the
others call it with no `by`. `landloss.exposure.asset_ids` is unchanged.

## 5. The wall outcome table and the contract flags

### 5.1 Outcomes

`landloss.hazard.landslide.urban.realisation.OUTCOMES = ("standing", "failed_with_polygon", "absorbed", "superseded")`.
Schema in section 3.10. Flat-land walls never appear. A sloping wall whose
line's polygon was not delineated has nothing to fail and is `standing` with
`slope_id` null. A wall whose polygon
survived is `standing`; whose polygon failed through the wall and survived
nesting and supersession is `failed_with_polygon`; whose polygon failed but
was absorbed by a larger failed urban polygon sharing ground with it is
`absorbed`; whose polygon failed and whose evacuated geometry shares ground
with a large-model evacuated polygon is `superseded`. Two polygons **share
ground** where their intersection has an area above
`realisation.SHARED_GROUND_TOLERANCE_M2` (0.01 m², a numerical tolerance, not
a parameter); polygons that only touch along an edge or at a corner do not, so
neither absorbs nor supersedes the other. Supersession is tested on the failed
polygon's **evacuated** geometry for the state it is in, as plan §5.1 step 4
says, and is resolved first; absorption is then resolved among the failed
polygons no large slide superseded. A polygon that did not fail is never
superseded (decision 35): a wall a large slide reaches is flagged by the line
intersection of section 5.2, row 3. A wall on polygons at several scales takes
one outcome by `realisation.OUTCOME_RANK`
(`{superseded: 0, failed_with_polygon: 1, absorbed: 2, standing: 3}`, lowest
wins, ties to model order), so `superseded` outranks `absorbed`. Section 7.11
states the same rules.

### 5.2 Flag mapping

`landloss.vul.landslide.flags.OUTCOME_FLAGS`, applied by step 11 and OR-ed with
the geometric intersections:

| Outcome / condition | `is_damaged_by_shaking` | `is_evacuated` | `is_inundated` |
| --- | --- | --- | --- |
| `failed_with_polygon` | True | | |
| `absorbed` or `superseded` | | True | |
| a positive length of the line runs inside any `evacuated land` polygon (either population), above `WALL_INSIDE_TOLERANCE_M` = 0.01 m | | True | |
| a positive length of the line runs inside any `inundated land` polygon, above the same tolerance | | | True |
| flat-land wall with `damage_state == "replace"` in step 9 | True (set in `build_rw_table`) | | |
| `standing` and no intersection | False | False | False |

Any flag true means one replacement in `loss`; the mapping only attributes
the cause, which plan §5.2 records as proposed, so the mapping lives in one
dict and nowhere else.

## 6. Fragility rows

Every fragility is a lognormal CDF on PGV in m/s:
`P(fail | PGV) = Phi(ln(PGV / theta) / beta)`. The row columns, in this order,
on the model file (section 3.8) and repeated on the step 9 output where
noted:

| Column | Meaning |
| --- | --- |
| `im` | Always `pgv_m_s` |
| `theta_base` | The published or localised median in m/s before adjustment |
| `theta_base_pga_g` | The published median in g when the curve was PGA-based, else NaN |
| `site_class` | The TS1170.5 site class at the representative point |
| `pgv_pga_ratio_m_s_per_g` | PGV (m/s) / PGA (g) at the representative point (step 8) or line midpoint (vul step 9): step 3's PGV grid over the unscaled TS1170.5 PGA grid at `RETURN_PERIOD_YR`, both on the step 2 site class grid, sampled by `urban.fragility.pgv_pga_ratio_m_s_per_g` (section 7.7); realisation-free, because steps 4 and 5 scale PGA and PGV by one factor; NaN when no conversion was made |
| `amp_factor` | Topographic amplification, 1.0 to `TOPOGRAPHIC_AMPLIFICATION_MAX` |
| `rate_setting` | `config.URBAN_RATE` (`low`, `medium`, `high`), written so the file records the setting plan §4.4 asks for |
| `rate_factor` | `URBAN_RATE_FACTORS[rate_setting]` |
| `theta` | `theta_base / amp_factor * rate_factor` |
| `beta` | Dispersion: the wall row's, or `LOCALISED_FRAGILITY_BETA` |
| `fragility_basis` | `wall` or `localised` |
| `fragility_source` | The wall table's `source` (a `doc/references.bib` key), or `localised:<continuous_rating:.0f>` |

Conversion: `theta_base = theta_base_pga_g × pgv_pga_ratio_m_s_per_g`. The
rate factor is applied to wall-derived medians too, so the setting scales
every urban fragility as plan §4.4 says; flat-land walls in `vul/shaking/rw`
take `rate_factor = 1.0` and `amp_factor = 1.0`.

## 7. Library modules and public functions

All arrays are `numpy.typing.NDArray[np.floating]` unless stated; all frames
are in a projected CRS and functions raise `ValueError` on a geographic one, as
`landloss.exposure.coverage._check_frames` does. Each module has one purpose;
a function not listed is private.

### 7.1 `landloss.common.utils.terrain` (additions)

```python
def cut_fill_residual(dem: xr.DataArray, base: xr.DataArray) -> xr.DataArray
```
`dem` minus `base` resampled bilinearly onto `dem`'s grid
(`base.rio.reproject_match(dem, resampling=Resampling.bilinear)`). Negative
where the ground was cut below the smoothed surface, positive where filled.
Name `cut_fill_residual_m`. Raises if either carries no CRS.

```python
def profile_curvature(dem: xr.DataArray, resolution: float) -> xr.DataArray
```
Zevenbergen and Thorne (1987) profile curvature on the 3×3 window, in 1/m,
ArcGIS sign convention: negative on convex (crest) ground, positive on
concave; 0.0 where the gradient is exactly zero. One-cell NaN border. Name
`profile_curvature_per_m`. Cited as `[zevenbergen_thorne_1987]`.

```python
def vegetation_height(dsm: xr.DataArray, dem: xr.DataArray) -> xr.DataArray
```
`dsm` reprojected to `dem`'s grid (bilinear) minus `dem`, clipped at 0, NaN
where either is NaN. Name `vegetation_height_m`.

```python
def mean_azimuth_degrees(azimuth_degrees: np.ndarray) -> float
def azimuth_sd_degrees(azimuth_degrees: np.ndarray) -> float
```
Circular mean and circular standard deviation in degrees, NaN-skipping; NaN
when nothing finite.

```python
def zonal_statistic(
    raster_path: Path | str,
    polygons: gpd.GeoSeries,
    *,
    statistic: Literal["mean", "max", "min", "median"] = "mean",
) -> pd.Series
```
One value per polygon, on `polygons.index`, by masking the raster with each
polygon (`rasterio.mask` or `rasterio.features.geometry_mask`); NaN where no
cell centre falls inside. Used by steps 5, 6 and 7 to read rasters onto
patches. `mean` of an azimuth raster is **not** circular; callers of aspect use
`zonal_azimuth_mean(raster_path, polygons) -> pd.Series`, provided alongside.

Tests: `tests/landloss/common/utils/test_terrain.py` extended: residual of a
plane against its own block mean is zero; curvature sign on a ridge and a
gully; vegetation height on a DSM one metre above a DEM; circular mean of
350 and 10 degrees is 0.

### 7.2 `landloss.common.utils.ids` (new, phase 0)

Section 4 specifies it fully; phase 0 writes the module and
`tests/landloss/common/utils/test_ids.py` (a descending `by` column sorts
descending; ties keep incoming order; `mint_ids("UC", 3)` is `UC0000001`
to `UC0000003`), so every implementer imports it and none edits it.

### 7.3 `landloss.hazard.landslide.ground_map` (new)

Vocabulary constants (section 9): `MATERIALS`, `MODIFICATIONS`,
`PRIOR_FAILURES`, `GW_DEPTH_CLASSES`, `CONFIDENCES = ("high", "medium", "low")`,
`UNKNOWN = "unknown"`, `ASSUMED = "assumed"`,
`MATERIAL_GEOLOGY_VALUES: dict[str, float]`,
`MATERIAL_STRENGTH_GRADE: dict[str, str]`,
`STRENGTH_TABLE_PATH = ASSETS_DIR / "wellington-greywacke-strength.csv"`,
`GENESIS_MODIFICATION_TYPES`, `GENESIS_PRIOR_FAILURE_TYPES` and
`GENESIS_NO_CLAIM_TYPES` (the three partition the fifteen genesis `Type`
values of section 9.2; a test asserts it), and `ROCK_MATERIALS` (the four rock
materials of section 9.1; `exposure.rw.lines.is_rock_cut` reads it). The
further constants section 3.2 lists as built are additive.

```python
@dataclass(frozen=True)
class GroundSource:
    name: str                 # e.g. "slide_materials"; written to the *_source column
    frame: gpd.GeoDataFrame   # polygons carrying `column`
    column: str               # already in the vocabulary (or units) of `attribute`
    attribute: str            # "material" | "modification" | "prior_failure" | "gw_depth_m" | "fill_thickness_m"
    confidence: str           # one of CONFIDENCES

def material_from_slide(types: pd.Series) -> pd.Series
def material_from_geology(unit_codes: pd.Series) -> pd.Series
def material_from_nlm(l3_yp: pd.Series) -> pd.Series
def modification_from_genesis(types: pd.Series) -> pd.Series
def modification_from_wcc(kind: pd.Series) -> pd.Series
def modification_from_residual(residual_m: np.ndarray, *, threshold_m: float) -> np.ndarray
def prior_failure_from_genesis(types: pd.Series, subtypes: pd.Series) -> pd.Series
def gw_depth_class_from_depth(depth_m: np.ndarray) -> np.ndarray
def kingsbury_geology_value(materials: pd.Series) -> pd.Series
def strength_from_material(materials: pd.Series, strength_table: pd.DataFrame) -> pd.DataFrame
def build_ground_map(
    extent: shapely.Polygon,
    sources: Sequence[GroundSource],
    *,
    flatland: gpd.GeoDataFrame,
    default_gw_depth_m: float,
    crs: str = DEFAULT_CRS,
) -> gpd.GeoDataFrame
```

Each `*_from_*` maps a source's own classes to the vocabulary and raises
`ValueError` naming any class it has no rule for, as
`susceptibility.geology_value_from_material` does; the two genesis mappers
have rules only for their claiming types (`GENESIS_MODIFICATION_TYPES`,
`GENESIS_PRIOR_FAILURE_TYPES`), and the script filters the genesis frame to
those before building each `GroundSource`, so an unlisted or no-claim type
reaching a mapper raises. `build_ground_map` takes
the sources **in precedence order** (first wins per attribute), builds the
planar partition of `extent` by the union of every source's boundaries and
the flatland polygons, fills each piece's attributes from the first source
whose polygon contains the piece's representative point, writes `unknown`,
`natural`, `none` and NaN defaults where no source reaches, and returns
the frame with every column of section 3.2 except `ground_id` and `area_m2`
(the script mints and measures). The source column is `<attribute>_source`,
except that `gw_depth_m`'s is `gw_source`; `<attribute>_confidence` is written
for `material` and `modification` only (the two section 3.2 carries). From
`gw_depth_m` it derives `gw_depth_class` with `gw_depth_class_from_depth`,
and where no `gw_depth_m` source reaches it writes `default_gw_depth_m`
(the script passes `config.DEFAULT_GROUNDWATER_DEPTH_M`) with `gw_source =
ASSUMED`. It writes `flatland_version` from `constants.FLATLAND_NLM_VERSION`
and the strength columns by `strength_from_material` on the finished
`material` column.

`strength_from_material` picks one row per grade `MATERIAL_STRENGTH_GRADE[material]`
from `strength_table` (the CSV as read, columns `record_id`, `grade`,
`source_type`, `check`, `c_eff_kpa`, `phi_eff_deg`, `unit_weight_kn_m3`, ...):
among the rows of that `grade` whose `c_eff_kpa`, `phi_eff_deg` and
`unit_weight_kn_m3` are all non-null, the first ordered by `check` false
before true, `source_type == "published"` before the rest, then file order;
it raises `ValueError` naming the grade when no row carries all three. It
returns, on `materials.index`, the columns **renamed** `record_id` →
`strength_source`, `c_eff_kpa` → `c_kpa`, `phi_eff_deg` → `phi_deg`, and
`unit_weight_kn_m3` as is; NaN and null for `unknown`.

Tests in `tests/landloss/hazard/landslide/test_ground_map.py`: precedence on
two overlapping synthetic sources (finer wins inside, coarser outside);
defaults off every source, including `assumed` groundwater at the default
depth; every mapper refuses an unknown class; the three genesis tuples
partition the fifteen types; the strength picks on the committed CSV are the
six rows section 3.2 names, and a grade with no complete row raises.

### 7.4 `landloss.hazard.landslide.slope_units` (new)

```python
def channel_cells(accumulation_m2: np.ndarray, *, threshold_m2: float) -> np.ndarray  # bool
def channel_links(channels: np.ndarray, receiver: np.ndarray) -> np.ndarray  # int labels, 0 off-channel
def link_catchments(receiver: np.ndarray, order: np.ndarray, links: np.ndarray) -> np.ndarray  # int per cell
def split_half_basins(catchments: np.ndarray, links: np.ndarray, receiver: np.ndarray, aspect_degrees: np.ndarray) -> np.ndarray
def units_to_polygons(labels: np.ndarray, transform: Affine, crs: str) -> gpd.GeoDataFrame
def merge_similar_aspect(units: gpd.GeoDataFrame, *, tolerance_deg: float, min_area_m2: float, max_area_m2: float) -> gpd.GeoDataFrame
def split_by_aspect_variance(units: gpd.GeoDataFrame, aspect: xr.DataArray, *, max_area_m2: float) -> gpd.GeoDataFrame
def delineate_slope_units(
    dem: xr.DataArray,
    slope: xr.DataArray,
    aspect: xr.DataArray,
    *,
    channel_threshold_ha: float,
    aspect_tolerance_deg: float,
    min_area_ha: float,
    max_area_ha: float,
) -> gpd.GeoDataFrame
```

`Affine` is `from rasterio.transform import Affine`, as
`landloss.hazard.landslide.models.nowicki_2018.inputs` imports it; the
`affine` package is not a declared dependency (section 12).

`delineate_slope_units` runs `hydrology.route_grid` (priority flood, D8
receivers, accumulation with cell area as weight, in one call; the addition to
`hydrology.py`), then the stages above in order (as built: alternating the
split and merge up to three passes, section 3.3), and
returns the columns of section 3.3 except `unit_id` and `flatland_share`,
with `mean_slope_degrees` the mean of `slope` (the step 3 10 m slope raster)
over the unit's cells.
`channel_links` labels each channel reach between junctions; `link_catchments`
assigns every cell to the link it drains to; `split_half_basins` puts each
cell on the left or right of its link by the sign of the cross product of the
link's downstream direction and the vector from the link to the cell;
`merge_similar_aspect` merges adjacent units whose circular mean aspects
differ by less than the tolerance while the merged area stays under
`max_area_m2`, and absorbs units under `min_area_m2` into the most similar
neighbour; `split_by_aspect_variance` splits any unit over `max_area_m2` by
k-means (k = 2) on aspect unit vectors until none is over.

Tests in `tests/landloss/hazard/landslide/test_slope_units.py`: a synthetic
V-shaped valley yields two half-basins of opposite aspect; a unit over the
maximum is split; small units are absorbed.

### 7.5 `landloss.hazard.landslide.urban.delineation` (new)

Raster segmentation only.

```python
SLOPE_BANDS_DEG = (10.0, 20.0, 30.0, 45.0, 60.0)
SLOPE_BAND_LABELS = ("0-10", "10-20", "20-30", "30-45", "45-60", "60+")
ASPECT_OCTANTS = 8
SNAP_TOLERANCE_M = 3.0          # shared by gen_wall_lines.py and step 7
# No MIN_PATCH_CELLS here: config.MIN_PATCH_CELLS (section 3.4) is the one
# definition, passed in as `min_patch_cells`. `Affine` as in section 7.4.

def urban_domain(buildings: gpd.GeoDataFrame, flatland: gpd.GeoDataFrame, *, building_distance_m: float) -> shapely.Geometry
def slope_band(slope_degrees: np.ndarray) -> np.ndarray          # int, -1 for NaN
def aspect_octant(azimuth_degrees: np.ndarray) -> np.ndarray      # int 0..7, -1 for NaN
def label_patches(band: np.ndarray, octant: np.ndarray) -> np.ndarray  # int labels, 0 = outside
def merge_small_patches(labels: np.ndarray, *, min_cells: int) -> np.ndarray
def patches_to_polygons(labels: np.ndarray, transform: Affine, crs: str) -> gpd.GeoDataFrame  # columns: label, geometry
def split_long_patches(patches: gpd.GeoDataFrame, aspect_degrees: np.ndarray, *, max_length_m: float) -> gpd.GeoDataFrame
def delineate_candidates(
    slope: xr.DataArray,
    aspect: xr.DataArray,
    domain: shapely.Geometry,
    *,
    scale_m: int,
    min_patch_cells: int,
    max_length_m: float,
) -> gpd.GeoDataFrame
```

`label_patches` uses `scipy.ndimage.label` on
`band * (ASPECT_OCTANTS + 1) + octant + 1` (section 3.4 says why) with
4-connectivity, one class at a time; `merge_small_patches` merges each
patch under `min_cells` into the neighbouring patch sharing the most cell
edges, repeated until none remains (an island with no neighbour is kept);
`split_long_patches` cuts a patch whose
extent perpendicular to its mean aspect exceeds `max_length_m` into equal
pieces along lines parallel to the aspect. `delineate_candidates` returns
`scale_m`, `slope_band`, `aspect_octant`, `slope_degrees`, `aspect_degrees`,
`area_m2`, `contour_length_m`, `geometry`, clipped to `domain`. The script adds
the other attributes with `zonal_statistic`. One public function beyond the
list: `contour_length_m(geometry, aspect_degrees) -> ndarray`, the extent
perpendicular to the aspect, which step 7 recomputes on the reconciled
geometry.

Tests in `tests/landloss/hazard/landslide/urban/test_delineation.py`: a
synthetic terrace-and-face DEM (two flats joined by a face steep enough that
Horn's kernel reads its shoulders in `60+` too: as built a 12 m face at 76
degrees over three cells, because a 60-degree face of any height is never one
patch at 1 m) gives three patches at 1 m, with the face in the `60+` band; a
20-degree bank with a 2 m face in it shows the fine face nested inside the
coarser bank at 3 m; small patches merge; a long strip splits.

### 7.6 `landloss.hazard.landslide.urban.geometry` (new)

The geometry of a failure polygon: reconciling its edges to wall lines, and
the fixed state geometries. Each rule is a named function whose docstring
cites its source by `doc/references.bib` key or GNS finding id (plan §7).

```python
WALL_STATES = ("no_wall", "fill_wall", "cut_wall")
GEOMETRY_KINDS = ("evacuated", "inundated", "imminent")
HEADSCARP_BAND_M = 0.5
HEADSCARP_BAND_STEEP_M = 1.0
HEADSCARP_STEEP_SLOPE_DEG = 30.0
FILL_WEDGE_HEIGHT_MULTIPLE = 1.0
DRY_REACH_ANGLE_HL = ((100.0, 0.9), (10_000.0, 0.8))   # (volume m3, H/L), log-linear between
FILL_REACH_ANGLE_HL = 0.38
COLLUVIUM_DEPTH_M = 1.5
LARGE_POLYGON_AREA_M2 = 500.0

def snap_edges_to_lines(polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, tolerance_m: float) -> gpd.GeoDataFrame
def split_by_lines(polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame
def wall_line_on_edge(polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, tolerance_m: float) -> pd.DataFrame
def nest_parents(polygons: gpd.GeoDataFrame, *, min_cover: float = 0.9) -> pd.Series
def crest_line(face: shapely.Polygon, aspect_degrees: float) -> shapely.LineString
def toe_line(face: shapely.Polygon, aspect_degrees: float) -> shapely.LineString
def offset_strip(line: shapely.LineString, azimuth_degrees: float, width_m: float) -> shapely.Polygon
def headscarp_band_m(slope_degrees: float) -> float
def evacuated_no_wall(face: shapely.Polygon, aspect_degrees: float, slope_degrees: float) -> shapely.Polygon
def imminent_no_wall(face: shapely.Polygon, aspect_degrees: float, slope_degrees: float) -> shapely.Polygon
def fill_wedge(wall_line: shapely.LineString, aspect_degrees: float, height_m: float, *, multiple: float = FILL_WEDGE_HEIGHT_MULTIPLE) -> shapely.Polygon
def imminent_fill_wall(wall_line: shapely.LineString, aspect_degrees: float, height_m: float) -> shapely.Polygon
def dry_reach_angle(volume_m3: float) -> float
def runout_length_m(relief_m: float, reach_angle_hl: float, face_length_m: float) -> float
def inundated_polygon(toe: shapely.LineString, aspect_degrees: float, runout_m: float, *, barriers: gpd.GeoSeries) -> shapely.Polygon
def evacuated_depth_m(area_m2: float, material: str, fill_thickness_m: float) -> float
def fill_wall_depth_m(height_m: float) -> float
def state_geometries(
    face: shapely.Polygon,
    *,
    aspect_degrees: float,
    slope_degrees: float,
    relief_m: float,
    material: str,
    fill_thickness_m: float,
    wall_line: shapely.LineString | None,
    wall_position: str | None,
    wall_height_m: float | None,
    barriers: gpd.GeoSeries,
) -> dict[str, shapely.Polygon | float | None]
def amplification_factor(topographic_position_m: np.ndarray, slope_degrees: np.ndarray, *, max_factor: float = TOPOGRAPHIC_AMPLIFICATION_MAX) -> np.ndarray
def kingsbury_factors(polygons: pd.DataFrame) -> dict[str, np.ndarray]

# As built (phase 1, section 3.6):
MIN_RUNOUT_M = 1.0
MAX_SNAP_AREA_LOSS = 0.5
def spread_runout_m(evacuated_area_m2: float, toe_length_m: float) -> float
def reconcile_candidates(candidates: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, tolerance_m: float) -> gpd.GeoDataFrame
def attach_state_geometries(polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, barriers: gpd.GeoSeries, tolerance_m: float) -> gpd.GeoDataFrame
```

Rules **[decided here]** where plan §7 gives a range (two of them, the crest
and toe rule and the runout length, were changed by the build; section 3.6
records what runs and marks them for the lead):

- `snap_edges_to_lines`: `shapely.snap(polygon, lines_union, tolerance_m)` then
  `make_valid`; `split_by_lines`: `shapely.ops.split` by each intersecting
  line, pieces under 1 m² dropped and merged into their neighbour; both keep
  `candidate_id` and add `piece` (int).
- `wall_line_on_edge`: for each polygon the lines whose intersection with
  `polygon.boundary.buffer(tolerance_m)` is longest; returns `slope index`,
  `wall_line_id`, `wall_edge_length_m`.
- `crest_line` and `toe_line` are geometric, not from the DEM: as built, the
  boundary segments whose outward normal faces uphill (`aspect + 180`) form
  the crest and those facing downhill the toe, merged with `linemerge`
  (section 3.6 says why the vertex rule was dropped).
- `evacuated_no_wall` = face ∪ `offset_strip(crest, aspect + 180, band)`;
  `imminent_no_wall` = the next strip of the same width behind.
- `fill_wedge` = `offset_strip(wall_line, aspect + 180, multiple × height_m)`;
  `imminent_fill_wall` = the strip of one further `height_m` behind the wedge.
  Cut wall states equal the no-wall states.
- Inundated: `runout_length_m = max(relief_m / reach_angle_hl − face_length_m, 0)`
  with `face_length_m` the face's extent along the aspect; as built the strip
  length is the larger of that and `spread_runout_m` (evacuated area over toe
  length) and never under `MIN_RUNOUT_M` (section 3.6); the strip from the
  toe downhill is cut at the first building outline or road (road centreline
  buffered by `ROAD_HALF_WIDTH_M`) it meets. Fill wall uses
  `FILL_REACH_ANGLE_HL`; the other states `dry_reach_angle(volume)` with
  `volume = evacuated area × evacuated depth`.
- `evacuated_depth_m`: `COLLUVIUM_DEPTH_M`; `max(that, fill_thickness_m)` on
  fill materials where known; for `area_m2 > LARGE_POLYGON_AREA_M2` the larger
  of that and `geometry.mean_depth_m(landslide_volume_m3(area), area)`.
  `fill_wall_depth_m = height_m / 2` (the wedge tapers from `height_m` to 0).
  Inundated depth = volume / inundated area (volume conserved).
- `amplification_factor = 1 + (max_factor − 1) × max(clip(tpi_100m / 10, 0, 1), clip((slope − 30) / 30, 0, 1))`:
  a crest 10 m or more above its 100 m neighbourhood, or a face at 60 degrees,
  reaches the maximum. Placeholder until phase 3 brackets it against
  `sr2019-051-F35`.
- `kingsbury_factors` returns the six factor arrays for
  `susceptibility.susceptibility_rating`: slope from `slope_angle_value(slope_degrees)`;
  modification `cut_angle_value(slope_degrees)` where `modification == "cut"`,
  `SIDLING_FILL_VALUE` where `fill`, else 0; height
  `slope_height_value(face_height_10m, slope_degrees)`; geology `geology_value`;
  landslides `LANDSLIDES_NONE / OLD / ACTIVE` for `none / relict / recent`;
  groundwater `groundwater_value(gw_depth_m)`.

Tests in `tests/landloss/hazard/landslide/urban/test_geometry.py`: a candidate
straddling a line splits into two pieces sharing the line; the fill wedge on a
planar slope has area `length × height`; runout on a planar slope reaches
`relief / HL` from the crest; a barrier truncates it; the headscarp band is
1 m above 30 degrees.

### 7.7 `landloss.hazard.landslide.urban.fragility` (new)

```python
IM = "pgv_m_s"
FRAGILITY_BASES = ("wall", "localised")
UNNAMED_WALL_CLASS = "unnamed"
RETAINING_WALL_FRAGILITY_PATH = ASSETS_DIR / "retaining-wall-fragility.csv"
URBAN_FRAGILITY_ANCHORS_PATH = ASSETS_DIR / "urban-fragility-anchors.csv"
LOCALISED_THETA_AT_ZERO_RATING_M_S = 3.0     # placeholder; set by the anchoring
LOCALISED_THETA_AT_MAX_RATING_M_S = 0.6      # placeholder; set by the anchoring

def load_retaining_wall_fragility(path: Path = RETAINING_WALL_FRAGILITY_PATH) -> pd.DataFrame
def load_urban_fragility_anchors(path: Path = URBAN_FRAGILITY_ANCHORS_PATH) -> pd.DataFrame
def lognormal_failure_probability(im: np.ndarray, theta: np.ndarray, beta: np.ndarray) -> np.ndarray
def interpolated_slope_value(slope_degrees: np.ndarray) -> np.ndarray
def continuous_rating(
    *,
    slope_degrees: np.ndarray,
    modification: np.ndarray,
    height: np.ndarray,
    geology: np.ndarray,
    landslides: np.ndarray,
    groundwater: np.ndarray,
) -> np.ndarray
def localised_theta_base_m_s(rating: np.ndarray) -> np.ndarray
def rate_factor(setting: str) -> float
def pgv_pga_ratio_m_s_per_g(pgv: xr.DataArray, pga: xr.DataArray, points: gpd.GeoSeries) -> pd.Series
def pga_to_pgv_theta(theta_pga_g: np.ndarray, ratio_m_s_per_g: np.ndarray) -> np.ndarray
def wall_curve(table: pd.DataFrame, *, wall_class: str, size_class: str, initial_condition: str) -> pd.Series
def polygon_theta(theta_base: np.ndarray, amp_factor: np.ndarray, rate_factor: float) -> np.ndarray
IS_FLATLAND_COLUMN = "is_flatland"         # decision 36: the drawn wall column sloping_walls reads

def sloping_walls(walls: pd.DataFrame) -> pd.DataFrame   # decision 36
def assign_fragility(
    polygons: gpd.GeoDataFrame,
    walls: gpd.GeoDataFrame,
    wall_table: pd.DataFrame,
    *,
    rate_setting: str,
    site_class: pd.Series,
    pgv_pga_ratio: pd.Series,
) -> gpd.GeoDataFrame
```

- `interpolated_slope_value` and `continuous_rating` exist already: the
  architect wrote them at the phase 1 integration, with
  `tests/landloss/hazard/landslide/urban/test_fragility.py` started, because
  step 7 imports `continuous_rating` (section 3.6). H extends both files and
  owns them as section 11 says.
- `lognormal_failure_probability` uses `scipy.stats.norm.cdf`; `im <= 0` gives
  0; `beta <= 0` raises.
- `interpolated_slope_value`: `np.interp` through the points
  `(0, 0), (20, 2), (35, 4), (45, 8), (60, 10)`, flat at 10 above 60, so the
  probability rises continuously with steepness; `continuous_rating` is
  `susceptibility_rating` with that in place of the stepped slope factor.
- `localised_theta_base_m_s(rating) = THETA_0 × (THETA_MAX / THETA_0) ** (rating / MAX_RATING)`,
  a log-linear decrease from 3.0 m/s at rating 0 to 0.6 m/s at 150. Gentle
  ground gets a very high median rather than being dropped. **Placeholder**:
  phase 3 fits the two constants and, if the anchors want it, a `beta`, to
  the anchor table, and the validation figure shows the fit.
- `rate_factor` raises `ValueError` naming the valid settings.
- `pgv_pga_ratio_m_s_per_g` divides `pgv` by `pga` cell by cell (both on the
  step 2 site class grid; raises unless shape, transform and CRS match) and
  samples the ratio at `points` in the cell each point falls in (the
  grid's inverse transform, as built: `.sel(method="nearest")` would return an
  edge cell off the grid), returning a Series on
  `points.index`, NaN off the grid or where either grid is NaN. Table 3.2 is
  not read: it is one row per grid point, APoE and site class with no Sa(1.0 s)
  column, so a scalar per site class is undefined; the grids are the products
  steps 3 and 4 already use, and the ratio is the same whichever realisation
  factor scaled them.
- `wall_curve` raises if the triple is missing or duplicated in the table.
- `sloping_walls(walls)` keeps the rows of the drawn walls with
  `IS_FLATLAND_COLUMN` false and a non-null `wall_line_id`: a flat-land wall
  is drawn by vul shaking rw step 9 only, and a null line would match every
  polygon without one.
- `assign_fragility` takes the world's drawn walls (`drawn_walls_path(w)`,
  section 3.7, decision 36), keeps `sloping_walls(walls)`, and joins each
  polygon's `wall_line_id` to them on `wall_line_id` (at most one wall per
  line per world); a polygon has a wall where that join matches, and `rw_id`
  is carried from the wall, null on one that is not insured, sets `wall_state`,
  picks the state's geometry and depth columns from the polygon file, computes
  the row columns of section 6 (`site_class` and `pgv_pga_ratio` are Series on
  `polygons.index`, sampled by the step at `rep_point`), and returns the
  section 3.8 frame minus `world_id`, **sorted by `slope_id` with a fresh
  index**.

Tests in `tests/landloss/hazard/landslide/urban/test_fragility.py`: the
lognormal at `im == theta` is 0.5; conversion of a 0.5 g median at ratio 1.2
is 0.6 m/s; `rate_factor("medium") == 1.0`; an unknown setting is refused;
`interpolated_slope_value` equals the stepped value at every break; a polygon
with a wall takes the wall curve and one without takes the localised one.

As built (phases 2 to 4, accepted, H): additive names beyond the list,
documented in the assets README: `wall_state()`, `anchor_points()`,
`fit_localised_fragility()` and `LocalisedFit` (the fit the validation runs),
`PGA_IM`, `WALL_INTENSITY_MEASURES`, `WALL_TABLE_COLUMNS`, `ANCHOR_COLUMNS`,
`MODEL_COLUMNS` and the column names. `LOCALISED_THETA_AT_ZERO_RATING_M_S` and
`LOCALISED_THETA_AT_MAX_RATING_M_S` keep the names above (no `beta_` prefix)
and say in their comment that they are placeholders. `pgv_pga_ratio_m_s_per_g`
reads the cell each point falls in (amended above). A
`DataArray.to_numpy(dtype=float)` call, which raises `TypeError`, was fixed in
it; the reader signatures take `path: Path = <packaged>`; the wall join skips a
null `wall_line_id`.

As built (decision 36, H): `assign_fragility` reads the drawn walls, and
`sloping_walls()` and `IS_FLATLAND_COLUMN` are added, as above; `_wall_rows`
reads the same match. Tests: an uninsured wall gives its polygon the wall
curve with `rw_id` null, a flat-land wall on an edge leaves the polygon
`no_wall`, drawn walls without `is_flatland` are refused, and the step test
writes `drawn_walls_path` with one uninsured wall.

### 7.8 `landloss.exposure.rw.lines` (new)

```python
SOURCES = ("gns_mapped_wall", "slide_cut_fill_line", "slide_cut_edge", "slide_fill_edge", "terrain_break", "road_frontage", "property_boundary")  # precedence order
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"   # copied from wall_probability; G deletes the original in phase 2 (section 7.9)
CUT_FILL_LINE_TYPE = "<set from the layer's Type values by the implementer>"
TERRAIN_BREAK_STEEP_DEG = 45.0
TERRAIN_BREAK_GENTLE_DEG = 20.0
MIN_SLOPING_GROUND_DEG = 5.0
FACE_SAMPLE_SPACING_M = 1.0
POSITION_PROBE_DISTANCE_M = 3.0

def mapped_wall_lines(morphology: gpd.GeoDataFrame) -> gpd.GeoDataFrame
def slide_cut_fill_lines(morphology: gpd.GeoDataFrame) -> gpd.GeoDataFrame
def genesis_edge_lines(genesis: gpd.GeoDataFrame) -> gpd.GeoDataFrame
def terrain_break_lines(candidates: gpd.GeoDataFrame, *, steep_deg: float, gentle_deg: float, min_face_height_m: float) -> gpd.GeoDataFrame
def boundary_lines(
    properties: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    *,
    road_distance_m: float,
    slope_path: Path,
    min_slope_deg: float,
) -> gpd.GeoDataFrame
def snap_to_candidate_edges(lines: gpd.GeoDataFrame, candidates: gpd.GeoDataFrame, *, tolerance_m: float) -> gpd.GeoDataFrame
def collapse_coincident(lines: gpd.GeoDataFrame, *, tolerance_m: float) -> gpd.GeoDataFrame
def split_at_boundaries(lines: gpd.GeoDataFrame, properties: gpd.GeoDataFrame) -> gpd.GeoDataFrame
def face_height_m(lines: gpd.GeoSeries, face_height_path: Path, *, spacing_m: float) -> pd.Series
def wall_position(lines: gpd.GeoSeries, aspect_degrees: pd.Series, residual_path: Path, *, probe_m: float) -> pd.Series
def assign_claim(
    lines: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    *,
    wall_position: pd.Series,
    aspect_degrees: pd.Series,
    tolerance_m: float,
) -> pd.Series
def build_wall_lines(
    *,
    morphology: gpd.GeoDataFrame,
    genesis: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    candidates: gpd.GeoDataFrame,
    ground_map: gpd.GeoDataFrame,
    face_height_path: Path,
    residual_path: Path,
    slope_3m_path: Path,
    slope_10m_path: Path,
    aspect_path: Path,
    snap_tolerance_m: float,
    road_distance_m: float,
    min_slope_deg: float,
    min_wall_height_m: float,
) -> gpd.GeoDataFrame
```

Every source function returns `source` and `geometry` (LineString, multi-parts
exploded). `boundary_lines` keeps only segments whose midpoint reads at least
`min_slope_deg` on `slope_path` (the 10 m slope; `MIN_SLOPING_GROUND_DEG`);
`build_wall_lines` then keeps only those within `URBAN_BUILDING_DISTANCE_M` of
a `buildings` outline (section 3.5). `ROCK_MATERIALS` is imported from
`landloss.hazard.landslide.ground_map` (exposure may depend on hazard), not
restated here.
`collapse_coincident` keeps, among lines within `tolerance_m` of
one another over most of their length, the one with the earliest `source` in
`SOURCES`, and sets `is_mapped_wall` where any collapsed member was a mapped
wall. `properties` is the claim-properties frame
(`build_claim_properties(get_nz_property_boundaries(...))`, one polygon per
claim with `claim_id`): `split_at_boundaries` splits on it and `assign_claim`
reads the claim from it, by the midpoint rule of section 3.5 with the
uphill/downhill side chosen from `wall_position` and `aspect_degrees`, so
`build_wall_lines` calls `wall_position()` before `assign_claim()`.
`build_wall_lines` samples `slope_degrees` and `aspect_degrees` at the
midpoint from `slope_3m_path` and `aspect_path` (3 m), passes
`slope_10m_path` to `boundary_lines`, and returns the section 3.5 frame minus
`wall_line_id`.

Tests in `tests/landloss/exposure/rw/test_lines.py`: a mapped wall snaps onto
a candidate edge 2 m away and not one 5 m away; a line crossing a boundary
splits in two; the claim rule on a boundary line for a fill and a cut wall;
a 0.4 m face is dropped unless mapped.

### 7.9 `landloss.exposure.rw.wall_probability` (changed)

**Deleted**: `mapped_wall_length_m`, `engineered_share`, `landform_at`,
`attach_evidence`, `wall_probability` (property form),
`size_class_probabilities`, `wall_probability_table` (property form),
`draw_walls`, `EVIDENCE_COLUMNS`, `PROBABILITY_COLUMNS`, `MAPPED_WALL_TYPE`
(its copy in `lines.py`, section 7.8, is the one definition from phase 2),
`ENGINEERED_GROUND_TYPES`, `PLAIN_LANDFORMS`, `MIN_MAPPED_WALL_LENGTH_M`,
`BETA_ENGINEERED_PREVALENCE`, `BETA_PLAIN_MAX_PREVALENCE`, the height
lognormal constants (`BETA_HEIGHT_LOG_SD`, `BETA_DRAWN_HEIGHT_BOUNDS_M`), and
their tests. **Kept**: `BETA_MAPPED_WALL_PROBABILITY = 0.9`, the one place the
mapped-wall floor is typed. `beta_population` loses `beta_wall_prevalence`,
`beta_wall_height_m` and `wall_lines` (nothing reads them) and keeps the
size and condition constants, `classify_wall_size` and `describe_population`.

**Added**:

```python
BETA_SOURCE_PROBABILITY = {"gns_mapped_wall": BETA_MAPPED_WALL_PROBABILITY, "slide_cut_fill_line": 0.6, "slide_cut_edge": 0.5, "slide_fill_edge": 0.5, "terrain_break": 0.4, "road_frontage": 0.25, "property_boundary": 0.15}
BETA_ROCK_CUT_FACTOR = 0.3
BETA_FLATLAND_MAX_PROBABILITY = 0.1
BETA_UNCONSENTED_POOR_SHARE = 0.7
BETA_PRE_1990_POOR_SHARE = 0.7
BETA_POST_1990_POOR_SHARE = 0.3
PROBABILITY_COLUMNS = ("p_wall", "p_wall_basis", "p_poor", "p_poor_basis")

def line_wall_probability(lines: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]
def poor_condition_probability(height_m: np.ndarray, dwelling_age_decade: pd.Series) -> tuple[np.ndarray, np.ndarray]
def wall_probability_table(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame
```

`line_wall_probability` applies, in order: the source prior; `× BETA_ROCK_CUT_FACTOR`
where `is_rock_cut`; `min(p, BETA_FLATLAND_MAX_PROBABILITY)` where
`is_flatland`; `max(p, BETA_MAPPED_WALL_PROBABILITY)` where `is_mapped_wall`,
basis `mapped`. It returns the probability and the basis string of the last
rule that changed it. The `beta`
names stay until the count bounds (T-50) replace them.
`poor_condition_probability`: `BETA_POOR_SHARE`; `BETA_UNCONSENTED_POOR_SHARE`
where `height_m < UNCONSENTED_WALL_HEIGHT_M`; age overrides where held.
`wall_probability_table` requires the section 3.5 columns and appends
`PROBABILITY_COLUMNS`. Tests rewritten in `test_wall_probability.py`.

As built (phases 2 to 4, accepted, G):

- Additive names: `BUILDING_ACT_DECADE = 1990`, the basis vocabularies
  `WALL_BASES` and `POOR_BASES` and their unpacked constants,
  `WALL_INPUT_COLUMNS`, `HEIGHT_COLUMN`, `AGE_COLUMN`, `BOUNDS_COLUMNS`, and
  `apply_count_bounds()` (section 7.10 amended; `apply_count_bounds` and
  `BOUNDS_COLUMNS` were removed on 2026-10-05, superseded by the wall unit
  claim update in landslide step 12,
  `.agents/plans/placing-retaining-walls-on-pifs.md`).
- `beta_population` also drops `_ramp`, `ID_COLUMN`, `AREA_COLUMN` and
  `COLUMNS`, which only the deleted `wall_lines` used.
- **"Nothing reads them" was wrong for two constants.** The loss module's
  `tests/landloss/loss/test_pricing.py` imports `BETA_MIN_HEIGHT_M` and
  `BETA_MAX_HEIGHT_M` as the range its set height per size class must sit
  inside. The loss module is owned elsewhere and is not edited, so the two
  stay in `beta_population` with a comment saying why, until its owner moves
  that test onto `MIN_WALL_HEIGHT_M` and an unbounded large class when
  re-confirming the set heights (**I-14**, section 3.7).

### 7.10 `landloss.exposure.rw.population` (new)

```python
def draw_wall_population(probabilities: gpd.GeoDataFrame, rng: np.random.Generator) -> gpd.GeoDataFrame
```

Two uniforms per line in line order: a wall exists where the first is below
`p_wall`; it is `poor` where the second is below `p_poor`. Returns the lines
that drew a wall, with `initial_condition`, `height_m` (= `face_height_m`),
`size_class`, `length_m` and the geometry, and the columns of section 3.7
except `rw_id` and `world_id`. The count bounds (T-50) scale `p_wall`
before the draw, through `wall_probability.apply_count_bounds()` (as built,
section 7.9), so the draw has no second form. (Superseded 2026-10-05: the
claim report counts now update the wall units in landslide step 12 before the
draw, and `apply_count_bounds` is removed;
`.agents/plans/placing-retaining-walls-on-pifs.md`.) Test in
`tests/landloss/exposure/rw/test_population.py`: a line at `p_wall = 1` always
draws, at 0 never; the same generator reproduces.

As built (phases 2 to 4, accepted, G): additive names `WALL_LINE_ID_COLUMN`,
`POPULATION_COLUMNS`, `HEIGHT_SOURCE_COLUMN`, `REQUIRED_COLUMNS`, `MODERN` and
`POOR`. A NaN `p_wall` draws nothing; claimless lines are returned for the
script to drop. Tests cover prefix independence of the draw and reproduction
by generator.

### 7.11 `landloss.hazard.landslide.urban.realisation` (new)

```python
OUTCOMES = ("standing", "failed_with_polygon", "absorbed", "superseded")
OUTCOME_RANK = {"superseded": 0, "failed_with_polygon": 1, "absorbed": 2, "standing": 3}   # lowest wins
NONE = -1                                    # no absorber, no superseder
SHARED_GROUND_TOLERANCE_M2 = 0.01            # intersection area above which two polygons share ground
URBAN_STREAM = "urban"
POPULATIONS = ("large", "urban")
POPULATION_COLUMN = "population"

def sample_pgv(points: gpd.GeoSeries, pgv_path: Path) -> pd.Series
def draw_failures(model: gpd.GeoDataFrame, pgv_m_s: pd.Series, rng: np.random.Generator) -> pd.DataFrame   # p_fail, uniform, failed
def resolve_overlaps(polygons: gpd.GeoSeries, areas: np.ndarray) -> np.ndarray   # index of the absorber per row, -1 for survivors
def supersede_by_large(evacuated: gpd.GeoSeries, large_evacuated: gpd.GeoSeries) -> np.ndarray   # position in large_evacuated or -1
def wall_outcomes(
    model: gpd.GeoDataFrame,
    walls: gpd.GeoDataFrame,
    draws: pd.DataFrame,
    absorbed_by: np.ndarray,
    superseded_by: np.ndarray,
    large_ids: pd.Series,
) -> pd.DataFrame
def to_landslide_rows(model: gpd.GeoDataFrame, draws: pd.DataFrame, survivors: np.ndarray) -> gpd.GeoDataFrame
def combine_with_large(urban_rows: gpd.GeoDataFrame, large_rows: gpd.GeoDataFrame) -> gpd.GeoDataFrame
```

Two polygons share ground where their intersection has an area above
`SHARED_GROUND_TOLERANCE_M2`; touching along an edge or at a corner is not
sharing ground (section 5.1). `draw_failures` gives every row with a wall the
uniform of the first row in model order carrying the same `wall_line_id`
(section 3.10, decision 34, built). `supersede_by_large` runs first, on the
**failed** rows' `evacuated` geometry only, and finds the large `evacuated
land` row sharing the most ground with each, ties to the earlier large row;
its result is mapped onto every model row, `NONE` where the row did not fail
(section 5.1, decision 35, built). `resolve_overlaps` is
`s1_simulate_landslides.drop_overlapping` generalised: largest first, stable
on ties, an absorbed polygon absorbs nothing, and a polygon absorbs those
sharing ground with it. It runs on the `evacuated` geometry of the failed
polygons no large slide superseded, so every absorber is a survivor. A wall
on polygons at several scales takes one outcome by `OUTCOME_RANK`.
`wall_outcomes` spines on `walls`, the world's population filtered to
`is_flatland` false, left-joins `model` on `rw_id`, carries `claim_id` and
`wall_line_id` from `walls`, and gives a wall with no polygon row `slope_id`
null, `outcome = "standing"` and `taken_by` null; the script prints that
count. `to_landslide_rows` writes three rows per survivor (evacuated,
inundated, imminent) with the section 3.10 columns, the `land_class` values
imported from `landloss.hazard.landslide.land_class`; `combine_with_large`
aligns the two schemas (missing columns null) and sorts by `landslide_id`,
`land_class`.

Tests in `tests/landloss/hazard/landslide/urban/test_realisation.py`: two
concentric failed polygons leave the larger; a failed urban polygon inside a
large evacuated circle is superseded, and one that did not fail there is
`standing`; a polygon touching a large one only along an edge is not
superseded, and two failures sharing only an edge or a corner both survive; a wall on an absorbed polygon reads `absorbed`; two rows with a
wall on one `wall_line_id` read one uniform, and rows without a wall keep
their own; the same `(w, r)` reproduces and `(w+1, r)` differs.

As built (phases 2 to 4, accepted, J2): signatures as above. The multi-scale
outcome rank (`OUTCOME_RANK`) and the most-shared-ground rule are in section
3.10's note. Decisions 34 and 35 (built, J) add the private
`_share_uniform_per_wall_line` beside `draw_failures`, and the tests above for
both; `wall_outcomes` ignores a superseder position set on a row that did not
fail.

### 7.12 `landloss.vul.shaking.fragility` (changed)

Kept as is for crossings. Added:

```python
def wall_failure_probability(
    walls: pd.DataFrame,
    pgv_m_s: np.ndarray,
    table: pd.DataFrame,
    *,
    pgv_pga_ratio: pd.Series,
) -> pd.DataFrame   # theta_base_pga_g, pgv_pga_ratio_m_s_per_g, theta, beta, fragility_source, failure_probability
```

Looks up `wall_curve(table, wall_class=UNNAMED_WALL_CLASS, size_class=..., initial_condition=...)`
per wall, converts PGA rows with `pga_to_pgv_theta(theta_pga_g, pgv_pga_ratio)`
(`pgv_pga_ratio` on `walls.index`, sampled by the step at the line midpoint
with `pgv_pga_ratio_m_s_per_g`, section 3.11; the ratio is recorded on the
output, NaN for PGV-native rows), applies `rate_factor = 1.0` and
`amp_factor = 1.0` (section 6), and evaluates `lognormal_failure_probability`.
Imports from `landloss.hazard.landslide.urban.fragility` (vul may depend on
hazard).

As built (phases 2 to 4, accepted, K1): as above, with the NaN rule and the
inline `theta` of section 3.11's note; `PGA_IM` and `PGV_IM` are read from the
urban fragility module.

### 7.13 `landloss.vul.landslide.flags` (changed)

Added:

```python
OUTCOME_FLAGS = {
    "failed_with_polygon": IS_DAMAGED_BY_SHAKING_COLUMN,
    "absorbed": IS_EVACUATED_COLUMN,
    "superseded": IS_EVACUATED_COLUMN,
}

def outcome_flags(outcomes: pd.DataFrame, *, id_column: str) -> pd.DataFrame
def wall_flags(walls: gpd.GeoDataFrame, landslides: gpd.GeoDataFrame, outcomes: pd.DataFrame, *, id_column: str) -> pd.DataFrame
```

`wall_flags` = `landslide_flags(walls, landslides)` OR `outcome_flags`, with
`is_damaged_by_shaking` from the outcome alone, plus `slope_id` and `outcome`
carried (null where the wall has no outcome row). `landslide_flags` is
unchanged. Tests added to `test_flags.py`.

The land-class vocabulary lives in hazard, so no hazard module imports
`landloss.vul` (`code-structure.md`: hazard → exposure → vul → loss). Phase 0
creates `landloss.hazard.landslide.land_class` with
`EVACUATED = "evacuated land"`, `INUNDATED = "inundated land"`,
`IMMINENT = "imminent land"`, `LAND_CLASSES = (EVACUATED, INUNDATED, IMMINENT)`
and `LAND_CLASS_COLUMN = "land_class"`. `landloss.vul.landslide.land.damaged_area`
re-points its `EVACUATED` and `INUNDATED` at that module and gains `IMMINENT`
from it, nothing else; `AREA_COLUMNS` does not include it.
`s1_simulate_landslides.py` drops its own literals for the same imports
(section 3.9).

As built (phases 2 to 4, accepted, K2): `slope_id` and `outcome` are built as
object Series so a missing value is `None` in memory under pandas 3; after the
parquet round trip they read back as `str` with NaN, which is "str, nullable".

### 7.14 `landloss.vul.loss_input` (changed)

```python
def build_rw_table(
    walls: gpd.GeoDataFrame,     # the world's population: rw_id, claim_id, size_class, length_m, geometry
    states: pd.DataFrame,        # step 9: rw_id, damage_state (flat-land walls only)
    flags: pd.DataFrame,         # step 11: rw_id, is_damaged_by_shaking, is_evacuated, is_inundated (every wall)
) -> gpd.GeoDataFrame
```

`is_damaged_by_shaking = (damage_state == REPLACE) | flags.is_damaged_by_shaking`,
with a missing state treated as no shaking damage. Every wall must have a
flags row (the existing `_merge_flags` check). `build_land_table` and
`build_crossing_tables` are unchanged. Tests updated in `test_loss_input.py`.

As built (phases 2 to 4, accepted, K2): as specified; the retaining wall tests
in `test_loss_input.py` are rewritten for the three-frame builder.

### 7.15 `landloss.io.readers` (addition)

`get_dsm(bbox, resolution=1, crs=DEFAULT_CRS, *, use_cache=True) -> Path`,
section 3.1. As built it comes with `dsm_cache_path` and `find_dsm_tiles`
(public, so tests fake the catalogue walk) and the constants `DSM_PATH_MARKER`
and `COG_GDAL_OPTIONS`: `linz_stac_utils` offers no DSM product, so
`find_dsm_tiles` walks the `/dsm_1m/` collections of the LINZ elevation STAC
catalogue (reusing `elevation.fetch_json` and `elevation.find_tiles`), orders
surveys newest first by their STAC temporal extent, and the tiles are
reprojected bilinearly into only the part of the target grid each reaches.
`get_dem` (`readers.py`) carries no licence text; the LINZ
elevation `Licence:` section to mirror is the one in `landloss.io.elevation`
(CC BY 4.0), and `get_dsm` carries its own `Licence:` and `Source:` sections
per `AGENTS.md`: the LINZ 1 m DSM, CC BY 4.0, attributed to LINZ and the
survey the tiles came from.

## 8. The two asset CSVs in `src/landloss/io/assets/`

### 8.1 `retaining-wall-fragility.csv`

One row per `(wall_class, size_class, initial_condition)`; the triple is
unique. Until the six classes are named the file carries `wall_class =
unnamed` and six rows.

| Column | Meaning |
| --- | --- |
| `wall_class` | `unnamed` for now |
| `size_class` | `small`, `medium`, `large` |
| `initial_condition` | `modern`, `poor` |
| `im` | `pga_g` or `pgv_m_s`: the intensity measure the published median is in |
| `theta` | The published median in `im` units |
| `beta` | The published dispersion |
| `published_height_m` | The wall height the curve was derived for |
| `damage_state` | The published state read as "replace" (e.g. `collapse`, `extensive`) |
| `source` | A `doc/references.bib` key, e.g. `koutsoupaki_2023` |
| `basis` | How the row was chosen: which published curve, and how condition shifted it |

Reader: `load_retaining_wall_fragility()` (section 7.7), validating the
columns, the uniqueness of the triple, `im` in `{"pga_g", "pgv_m_s"}` and
positive `theta` and `beta`. Phase 3 fills the values from
`.agents/context/retaining-wall-fragility.md`, with the modern rows from the
FS = 1.5 family and the poor rows from the lower-FS family of
[koutsoupaki_2023], and records the choice in `basis`.

README row:

`| retaining-wall-fragility.csv | Lognormal fragility (median, dispersion) per retaining wall class, size and initial condition, with the published intensity measure and source | Maintained by hand from .agents/context/retaining-wall-fragility.md — see below | landloss.hazard.landslide.urban.fragility.load_retaining_wall_fragility |`

### 8.2 `urban-fragility-anchors.csv`

One row per anchor point: a zone (or rating range), a demand, and the fraction
of polygons taken to fail there.

| Column | Meaning |
| --- | --- |
| `anchor_id` | `A01`, `A02`, ... |
| `source` | A bib key or GNS finding id (`kingsbury_1995`, `sr2015-016-F18`) |
| `zone` | Kingsbury zone 1–5, blank when the anchor is not zoned |
| `rating_min`, `rating_max` | The rating range the anchor applies to |
| `scenario` | Kingsbury scenario name or the event (`1`, `intermediate`, `2`, `port_hills_2011`, `kaikoura_2016_wellington`) |
| `pga_rock_g_min`, `pga_rock_g_max` | The demand range on rock, g |
| `class_word` | The source's failure class word (`few`, `some`, `many`, `widespread`, ...) |
| `fail_fraction` | The fraction of polygons failing that the class word is read as |
| `set_by` | Who set the fraction |
| `basis` | Why |

Reader: `load_urban_fragility_anchors()` validating columns and that
`fail_fraction` lies in [0, 1].

README row:

`| urban-fragility-anchors.csv | The qualitative anchors the urban failure fragility medians are fitted to: Kingsbury scenarios, the MM thresholds, the Wellington low-demand record and the Port Hills, each read as a fraction of polygons failing, with who set each number and why | Maintained by hand — see below | landloss.hazard.landslide.urban.fragility.load_urban_fragility_anchors and hazard/landslide/validations/urban/ |`

Both rows and a short section each go in `src/landloss/io/assets/README.md`;
phase 0 adds the rows with the files as empty-but-valid headers, and phase 3
fills them.

As built (phases 2 to 4, accepted, H): both files are filled and their README
sections written; section 3.8's note gives the rows.

## 9. Ground map attribute vocabulary and precedence

### 9.1 Values

`material` (exact strings):

| Value | Meaning | Kingsbury F_geology |
| --- | --- | --- |
| `rock` | Greywacke rock, weathering grade unknown | 4 (`GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED`, as the NLM mapping already assumes for Wellington basement) |
| `rock_uw_mw` | Unweathered to moderately weathered rock, where graded | 0 |
| `rock_hw_cw` | Highly to completely weathered rock | 4 |
| `rock_crushed` | Crushed and shattered greywacke | 8 |
| `colluvium` | Colluvium, talus, boulders, residual soil mantle | 10 |
| `loess` | | 10 |
| `alluvium` | Alluvium, fan, beach and foreshore deposits | 10 |
| `fill_engineered` | Engineered fill | 10 |
| `fill_uncontrolled` | Uncontrolled fill, landfill | 10 |
| `reclamation` | Harbour reclamation | 10 |
| `unknown` | No source reaches | NaN |

Open water is not ground: pieces whose only material source says water are
dropped from the map.

`modification`: `cut`, `fill`, `natural`, `unknown`.
`prior_failure`: `relict`, `recent`, `none`.
`gw_depth_class`: `saturated` (depth ≤ `GROUNDWATER_SATURATED_DEPTH_M`, 1 m),
`poorly_drained` (≤ 3 m), `well_drained`, using the breaks in
`landloss.hazard.landslide.susceptibility`.
`*_confidence`: `high`, `medium`, `low`.

### 9.2 Source mapping

- SLIDE interpreted materials `Type` → material (the 14 classes; the mapper
  lists each, and `confidence` low/medium/high maps straight to
  `material_confidence`). The mixed fill classes take their natural material
  (`Mixed fill/rock` → `rock`; `Mixed fill/colluvium`,
  `Mixed fill/colluvium/rock`, `Mixed fill/talus` → `colluvium`;
  `Old alluvium (mixed fill)` → `alluvium`), and `Fill` and the five mixed
  classes (`SLIDE_FILL_TYPES`) also claim the modification `fill` at the
  polygon's own confidence (the lead, 2026-10-02; step 4 plan, phase 2).
- 1:50,000 geology `unit_code` → material: `Tt`, `Te`, `Ttm`, `Teb` → `rock`;
  `Q1nc` → `fill_uncontrolled`; `Q1af` → `colluvium`; alluvial gravel codes →
  `alluvium`; loess codes → `loess`; the mapper lists every code in the layer
  and raises on a new one. Confidence `medium`.
- NLM `l3_yp` → material: `Sedimentary`, `Metamorphic`, `Igneous` → `rock`;
  `Talus`, `Colluvium` → `colluvium`; `Loess` → `loess`; `River channel`,
  `Floodplain`, `Foreshore`, `Swamp` → `alluvium`; `Uncompacted fill` →
  `fill_uncontrolled`; `Compacted fill` → `fill_engineered`; `Water body` →
  dropped. Confidence `low`.
- SLIDE genesis `Type`, all fifteen values the reader documents, each claiming
  one attribute or none; the script filters the frame to the claiming types
  before building each `GroundSource`, and the mappers raise on anything else:
  - modification: `Cut slope` → `cut`; `Fill body`, `Landfill`, `Dam` → `fill`.
    Confidence `high` for cut slope, fill body and landfill (the three the
    reader's docstring says are complete), `low` for dam.
  - prior failure: `Landslide relict` → `relict`; `Landslide recent` →
    `recent`; `Rockfall` (Subtype `few` or `many`) → `relict`
    (**[decided here]**: scattered boulders are evidence the slope above has
    failed, undated, so both subtypes count as relict). Confidence `low` (not
    a section 3.2 column).
  - no claim: `Modified terrain` (its subtypes say what the ground is used
    for, not whether it was cut or filled), `Terracettes`, `Fan`, `Dune`,
    `Gully erosion`, `Beach`, `Swamp/wetland`, `Seepage`.

  `GENESIS_MODIFICATION_TYPES`, `GENESIS_PRIOR_FAILURE_TYPES` and
  `GENESIS_NO_CLAIM_TYPES` (section 7.3) hold the three groups, and a test
  asserts they partition the fifteen.
- WCC cut areas → `cut`, fill areas → `fill`, confidence `medium`.
- Residual: `cut-fill-residual-30m` below `−RESIDUAL_MODIFICATION_THRESHOLD_M`
  → `cut`, above `+` → `fill`, as polygons from the thresholded raster;
  confidence `low`. `fill_thickness_m` = the positive 100 m residual's mean
  over a fill piece.
- NLM groundwater depth, polygonised over the flatland (section 3.2) →
  `gw_depth_m` (source `nlm_gwd`, confidence `medium`), from which
  `build_ground_map` derives `gw_depth_class`; elsewhere
  `DEFAULT_GROUNDWATER_DEPTH_M`, source `assumed`.

### 9.3 Precedence (first wins)

| Attribute | Order |
| --- | --- |
| `material` | SLIDE interpreted materials → 1:50,000 geology → NLM `l3_yp` → `unknown` |
| `modification` | SLIDE genesis (cut slope, fill body, landfill, dam) → WCC cut and fill areas → SLIDE materials fill and mixed fill classes → residual → `natural` |
| `prior_failure` | SLIDE genesis landslide polygons → `none` |
| `gw_depth_class` | NLM groundwater on flatland → assumed default |
| `fill_thickness_m` | residual on fill pieces → NaN |
| `is_flatland` | NLM flatland `FLATLAND_NLM_VERSION` only |

The strength set follows `material` through `MATERIAL_STRENGTH_GRADE`:
`rock`/`rock_hw_cw` → `HW`, `rock_uw_mw` → `MW`, `rock_crushed` → `CW`,
`colluvium` → `COL`, `loess`/`alluvium` → `RS`, both fills and `reclamation`
→ `FILL`, `unknown` → NaN.

## 10. Segmentation parameters

| Parameter | Value | Where |
| --- | --- | --- |
| Slope bands | 0–10, 10–20, 20–30, 30–45, 45–60, 60+ degrees; a value on a break falls in the band above | `delineation.SLOPE_BANDS_DEG` |
| Aspect octants | 8, centred on N, NE, ... (N is 337.5–22.5); NaN aspect (flat) is octant −1 and joins any band-0 neighbour | `delineation.ASPECT_OCTANTS` |
| Connectivity | 4-connected | `label_patches` |
| Minimum patch | 9 cells (3 × 3) at every scale: 9, 81, 900 and 8,100 m² | `config.MIN_PATCH_CELLS` |
| Contour segment length | 25 m: a patch wider than this across the slope is split into equal pieces | `config.MAX_PATCH_LENGTH_M` |
| Snap tolerance | 3 m, for mapped walls onto candidate edges and candidate edges onto wall lines | `delineation.SNAP_TOLERANCE_M` |
| Coincident line tolerance | 3 m (the same constant) | `lines.collapse_coincident` |
| Domain | building outlines buffered 100 m, minus NLM flatland | `urban_domain` |
| Nesting parent | smallest coarser polygon covering ≥ 90% of the child | `nest_parents` |
| Scales | 1, 3, 10, 30 m; 50 m is not run in this build | `URBAN_SCALES_M` |

## 11. File ownership

Implementers and what each may create or edit. "Owns" means creates and edits
freely; a file not listed for an implementer is read-only to them. Phase 0
creates every package `__init__.py` listed below with its one-line docstring
and `__all__ = []`, so no implementer creates one.

Phase 0 creates: `src/landloss/hazard/landslide/urban/__init__.py`,
`src/scripts/landloss/hazard/landslide/steps/s4_ground_map/__init__.py`,
`.../s5_slope_units/__init__.py`, `.../s6_urban_slope_candidates/__init__.py`,
`.../s7_urban_slope_polygons/__init__.py`, `.../s8_urban_slope_fragility/__init__.py`,
`.../s9_urban_slope_realisation/__init__.py`,
`src/scripts/landloss/hazard/shaking/steps/s5_pgv_realisation/__init__.py`,
`src/scripts/landloss/hazard/landslide/validations/urban/__init__.py`; two
library modules written **in full** with their tests, `common/utils/ids.py`
(section 4, with `tests/landloss/common/utils/test_ids.py`) and
`hazard/landslide/land_class.py` (section 7.13), because B, C, E, F and J all
mint ids and J and K read the land classes; the empty library modules with
docstrings: `hazard/landslide/ground_map.py`, `hazard/landslide/slope_units.py`,
`hazard/landslide/urban/{delineation,geometry,fragility,realisation}.py`,
`exposure/rw/{lines,population}.py`; the two CSVs with headers only; the two
README rows, and the `wellington-greywacke-strength.csv` row's "Read by" cell
set to `landloss.hazard.landslide.ground_map.strength_from_material` (the
depth-to-rock row stays "Not yet read"; B does not read it); the constants;
the seeding change; shaking step 5; the `pyproject.toml` dependency and
`uv.lock`.

| Implementer | Owns |
| --- | --- |
| **A — terrain** | `common/utils/terrain.py`, `io/readers.py` (only `get_dsm` and its helpers), `s3_multiscale_slope/` (all files), `tests/.../test_terrain.py`, `tests/landloss/io/test_readers.py` (only the `get_dsm` tests), `tests/landloss/hazard/landslide/test_multiscale_slope_step.py` (added in phase 1) |
| **B — ground map** | `hazard/landslide/ground_map.py`, `s4_ground_map/`, `tests/landloss/hazard/landslide/test_ground_map.py` |
| **C — slope units** | `hazard/landslide/slope_units.py`, `common/utils/hydrology.py` (additions only), `s5_slope_units/`, `tests/.../test_slope_units.py`, `tests/.../test_hydrology.py` |
| **D — candidates** | `hazard/landslide/urban/delineation.py`, `s6_urban_slope_candidates/`, `tests/.../urban/test_delineation.py` |
| **E — wall lines** | `exposure/rw/lines.py`, `gen_wall_lines.py`, `fig_wall_lines.py`, `tests/landloss/exposure/rw/test_lines.py`; adds the `ROAD_FRONTAGE_DISTANCE_M` key to the step's `config.py` and the method and plan bullets for the new script |
| **F — polygons** | `hazard/landslide/urban/geometry.py`, `s7_urban_slope_polygons/`, `tests/.../urban/test_geometry.py` |
| **G — wall population (phase 2)** | `exposure/rw/wall_probability.py`, `exposure/rw/beta_population.py`, `exposure/rw/population.py`, `gen_wall_probability.py`, `gen_wall_population.py`, the step's `config.py`, method and plan, `tests/landloss/exposure/rw/test_wall_probability.py`, `test_beta_population.py`, `test_population.py`, `src/scripts/landloss/exposure/gen_exposure.py` and `exposure/config.py` (`WORLD_IDS`; the `gen_wall_lines`, `gen_wall_probability` and `gen_wall_population` steps; the runner paragraph below) |
| **H — fragility (phase 3)** | `hazard/landslide/urban/fragility.py`, the two CSVs' contents, their README sections (below the table), `s8_urban_slope_fragility/`, `validations/urban/`, `tests/.../urban/test_fragility.py` |
| **J — draws (phase 4)** | `s1_landslide_realisation/` (all files), `hazard/landslide/urban/realisation.py`, `s9_urban_slope_realisation/`, `tests/.../urban/test_realisation.py`, `src/scripts/landloss/hazard/gen_hazard.py` and `hazard/config.py` (`WORLD_IDS`; shaking s5 and landslide s3–s9 added to the runner; the runner paragraph below) |
| **K — vul (phase 4)** | `vul/shaking/fragility.py`, `vul/landslide/flags.py`, `vul/landslide/land/damaged_area.py` (re-pointing `EVACUATED` and `INUNDATED` at `hazard.landslide.land_class` and adding `IMMINENT`, section 7.13), `vul/loss_input.py`, every `vul/.../steps/` folder named in sections 3.11–3.15, `vul/config.py`, `vul/gen_vul.py`, `tests/landloss/vul/**`, `src/scripts/landloss/gen_all.py` and `scripts/landloss/config.py` (`WORLD_IDS`; the module order in the runner paragraph below) |

No implementer touches: any `status.md`; `src/landloss/domain/constants.py`;
`src/landloss/domain/loss_contract.py`; `src/landloss/hazard/realisation.py`;
`pyproject.toml`; `uv.lock`; `requirements.txt`; `README.md`; `AGENTS.md`;
`CLAUDE.md`; anything under `.agents/`; `doc/references.bib` (an implementer
needing a new entry lists it in their findings or plan file and the
architect adds it); the README table rows (phase 0); any file another
implementer owns. Step `config.py` files are owned with their step. The
`status.md` files are updated by the architect after each phase from the
method files.

Where E and D both need the candidates file, D runs first; E reads
`urban_slope_candidates_path`. Where F needs E's lines, E runs first. G needs
E; H needs F and G; J needs H and C; K needs J. `ids.py` and `land_class.py`
are phase 0, so no phase 1 implementer waits on D to mint.

The end-to-end runners **[decided here]**, because the urban chain crosses
modules both ways (exposure's wall lines read landslide steps 3–6; landslide
steps 7–9 read exposure's wall lines and population):

- `gen_hazard.main(*, pilot, realisation_ids, world_ids)` runs shaking s2–s5,
  liquefaction s2–s3, then landslide s3, s4, s5, s6 and s1 (the large model
  reads only hazard outputs). A second public function
  `gen_hazard.main_urban(*, pilot, realisation_ids, world_ids)` runs
  landslide s7, s8 and s9. J rewrites the module docstring, whose "the hazards
  read no exposure" no longer holds.
- `gen_exposure.main(*, pilot, realisation_ids, world_ids)` keeps
  `realisation_ids` for the crossing population (section 3.14) and runs
  `gen_wall_lines`, `gen_wall_probability` and `gen_wall_population` in that
  order after the insured land step (section 3.7).
- `gen_all.main(*, pilot, realisation_ids, world_ids)` runs `gen_hazard.main`,
  `gen_exposure.main`, `gen_hazard.main_urban`, `gen_vul.main`, and its
  docstring says why the hazard module runs twice.
- `gen_all.py` cannot run between G's phase 2 (`gen_exposure.main` then
  requires `world_ids`) and K's phase 4; the architect verifies phases 1–3 by
  running the new steps singly, as every step script is run anyway.

As built (phases 2 to 4, accepted): the runners are wired as above and all
four import. At the integration `gen_hazard.main` was made to pass step 1's
four placement keys (`LARGE_MIN_SOURCE_AREA_M2`, `URBAN_AREA_SHARE`,
`SOURCE_ASPECT_RATIO`, `CREST_WEIGHT`) from the step's `config.py`, as it does
for the other steps; without them it raised `TypeError` at step 1.
`gen_vul.main` passes `world_ids` and step 9's `RETURN_PERIOD_YR`. No runner
has been run end to end.

Review corrections (2026-10-02, all four built the same day), each inside
the files the table above gives its implementer: decisions 34 and 35 are J's (`urban/realisation.py`, step 9
and its tests); decision 36 is G's (`drawn_walls_path` in
`gen_wall_population.py`) and H's (the step 8 join and the wall test in
`urban/fragility.py`); decision 37 is K's (step 10 and
`tests/landloss/vul/test_property_damage_step.py`). The five loss calls are
the loss owner's.

## 12. Dependencies (phase 0)

- **scipy**: not declared in `pyproject.toml` (it is in `uv.lock` only as a
  transitive dependency), so a direct `import scipy` fails `deptry`. Add
  `"scipy>=1.14"` to `[project].dependencies`. Used by
  `scipy.ndimage.label` (delineation), `scipy.stats.norm` (fragility) and the
  k-means split (`scipy.cluster.vq`) in slope units. The `DEP002` ignore that
  phase 0 carried while nothing imported it was deleted at the phase 1
  integration.
- **pysheds**: not declared and not in the lock; neither is `numba`, which
  pysheds requires. `landloss.common.utils.terrain` records that numba forces
  a numpy downgrade this project will not tolerate, and the repository already
  carries D8 routing in `landloss.common.utils.hydrology`
  (`priority_flood`, `d8_receivers`, `flow_accumulation`). **[decided here]**:
  pysheds is **not** added; slope units are built on `hydrology.py` and
  `scipy.ndimage`. If a `uv lock` with pysheds is ever shown to keep
  `numpy>=2.1`, it can replace the routing stage without changing any
  signature in section 7.4. The slope units implementation plan records this.
- **affine**: a transitive dependency only (in `uv.lock`, not in
  `[project].dependencies`), so `from affine import Affine` under
  `src/landloss` fails `deptry` (DEP003), which the `prek` hook runs over
  `src`. Sections 7.4 and 7.5 import the type as
  `landloss.hazard.landslide.models.nowicki_2018.inputs` does,
  `from rasterio.transform import Affine`; no implementer adds `affine` to
  `pyproject.toml`.
- Nothing else. `scikit-image` is in the lock transitively and is not used
  (region growing is the alternative the plan did not choose).

## 13. Existing files that change, briefly

| File | Change |
| --- | --- |
| `src/landloss/domain/constants.py` | Section 1 block (phase 0) |
| `src/landloss/hazard/realisation.py` | Section 2 (phase 0) |
| `src/landloss/common/utils/terrain.py` | Section 7.1 additions; nothing removed |
| `src/landloss/io/readers.py` | `get_dsm` added |
| `src/landloss/exposure/rw/wall_probability.py` | Property-level model deleted; line-level functions of section 7.9 added; module docstring rewritten for lines |
| `src/landloss/exposure/rw/beta_population.py` | `beta_wall_prevalence`, `beta_wall_height_m`, `wall_lines` and their constants removed; the rest kept |
| `src/scripts/.../s3_multiscale_slope/gen_multiscale_slope.py` | Aspect written per scale; `RESOLUTIONS_M` grows from `(10, 30, 100)` to `(1, 3, 10, 30, 50, 100)`, the 1 m DEM fetched and every coarser grid block-meaned from it as now; path wrappers added |
| `src/scripts/.../s6_wall_population/gen_wall_probability.py` | Reads wall lines instead of properties; no DEM or GNS fetch; writes section 3.7 columns |
| `src/scripts/.../s6_wall_population/gen_wall_population.py` | Per world on `EXPOSURE_BASE_SEED`; `draw_wall_population`; drops claim-less lines; carries `wall_line_id`; `wall_population_path(world_id, *, pilot)`; `drawn_walls_path(world_id, *, pilot)`, every drawn wall before the filters (decision 36) |
| `src/scripts/.../s1_landslide_realisation/s1_simulate_landslides.py` | Placement per slope unit, Poisson count, truncated sizes above `LARGE_MIN_SOURCE_AREA_M2`, ellipse sources, string `landslide_id`, `population`, `unit_id`, `slope_id` columns; terrain read from step 3's rasters instead of fetched |
| `src/scripts/.../s1_landslide_realisation/fig_landslide_realisation.py` | Reads the new columns; otherwise as is |
| `src/scripts/.../s4_pga_realisation/` | A test only (section 3.0); the script is unchanged |
| `src/landloss/vul/shaking/fragility.py` | `wall_failure_probability` added; beta constant kept for crossings |
| `src/landloss/vul/landslide/flags.py` | `OUTCOME_FLAGS`, `outcome_flags`, `wall_flags` |
| `src/landloss/vul/landslide/land/damaged_area.py` | `EVACUATED` and `INUNDATED` re-pointed at `landloss.hazard.landslide.land_class`; `IMMINENT` added from it (section 7.13) |
| `src/landloss/vul/loss_input.py` | `build_rw_table(walls, states, flags)` |
| `vul/shaking/rw/steps/s9_wall_damage_state/*` | Flat-land only, PGV, wall curve, `(w, r)` naming |
| `vul/landslide/rw/steps/s11_wall_landslide_damage/*` | Outcome table, `wall_flags`, `(w, r)` naming |
| `vul/landslide/land/steps/s3_landslide_land_damage/*` | Combined realisation, `(w, r)` naming |
| `vul/landslide/culverts_bridges/steps/s11_crossing_landslide_damage/*` | Combined realisation, `(w, r)` naming |
| `vul/steps/s10_property_damage/*`, `vul/config.py`, `vul/gen_vul.py` | New readers, `(w, r)` naming, `WORLD_IDS` |
| `src/landloss/io/assets/README.md` | Two rows and two sections; the `wellington-greywacke-strength.csv` row's "Read by" cell becomes `landloss.hazard.landslide.ground_map.strength_from_material` (phase 0, section 11) |
| `src/scripts/landloss/exposure/gen_exposure.py`, `exposure/config.py` | `WORLD_IDS`; the `gen_wall_lines`, `gen_wall_probability` and `gen_wall_population` steps; `main` takes `world_ids` (G, phase 2; section 11) |
| `src/scripts/landloss/hazard/gen_hazard.py`, `hazard/config.py` | `WORLD_IDS`; shaking s5 and landslide s3–s6 added to `main`, s1 moved after them, s7–s9 in `main_urban`; docstring (J, phase 4; section 11) |
| `src/scripts/landloss/gen_all.py`, `scripts/landloss/config.py` | `WORLD_IDS`; module order hazard, exposure, hazard urban, vul; docstring (K, phase 4; section 11) |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | scipy (phase 0) |
| Every step's method and plan file, and the six `status.md` files (`hazard/landslide`, `exposure/rw`, `vul/landslide/rw`, plus `vul/shaking/rw`, `vul/landslide/land`, `vul/landslide/culverts_bridges`) | Updated in the same change as the scripts, by the step's implementer (method and plan) and the architect (status) |

## Decisions this contract made where the plan was open

1. `EXPOSURE_BASE_SEED = 2003`.
2. The aspect raster is `downhill_azimuth_degrees`; no new aspect function.
3. `RESOLUTIONS_M` keeps 100 m; curvature on the 3 m DEM; topographic position
   at 20 m on the 3 m DEM and 100 m on the 10 m DEM.
4. The DSM comes through a new `get_dsm` reader; vegetation height is NaN where
   no DSM covers.
5. No pysheds: slope units on `hydrology.py` plus scipy; scipy declared.
6. QMAP is not read; material off every source is `unknown`.
7. The ground map is a planar partition built by union overlay, attributed by
   representative-point lookup in precedence order; no unit is dropped from
   the slope units.
8. Id formats `GM`, `SU`, `UC`, `LS`; urban `landslide_id` equals `slope_id`;
   minting in `landloss.common.utils.ids`.
9. Segmentation: 3 × 3 cell minimum patch and 25 m contour length in step
   6's `config.py`; 3 m snap tolerance in `delineation.py`; 50 m not run.
10. Wall line rules: claim by midpoint with the uphill/downhill side rule on
    boundary lines; `wall_position` from the residual 3 m uphill; mapped walls
    under 0.5 m kept as small; driveway edges not a source.
11. Reconciliation functions live in `urban/geometry.py`; state geometry
    columns are `<kind>_<state>` and `None` for impossible states; fill wedge
    1.0 H; crest and toe lines by geometry; depth rules in 7.6.
12. Amplification and localised-median formulas are placeholders with the
    forms given; rate factors low 1.5 and high 1/1.5 as placeholders.
13. Step 8 does not read the anchor CSV; the PGV/PGA ratio is step 3's PGV
    grid over the unscaled TS1170.5 PGA grid, sampled at the representative
    point or line midpoint (not Table 3.2); one `unnamed` wall class.
14. Shaking step 5 recomputes step 4's factor from the same seed.
15. Step 1: Poisson count per unit, ellipse sources at aspect ratio 2,
    `LARGE_MIN_SOURCE_AREA_M2 = 700`, `URBAN_AREA_SHARE = 0.25` placeholder.
16. A third land class `imminent land` is written and ignored by the land step.
17. The crossing population stays per realisation; liquefaction and structure
    steps are untouched.
18. `build_rw_table(walls, states, flags)` spines on the population.
19. Implementers must make the pilot run; the full extent is the lead's.
20. The wall outcome table carries `taken_by`.
21. `ids.py` and `land_class.py` are written in phase 0; the end-to-end
    runners are rewired by G (`gen_exposure.py`), J (`gen_hazard.py`, with
    `main_urban`) and K (`gen_all.py`), and `gen_all.py` is not runnable
    between phases 2 and 4.

Decisions made at the phase 1 integration (2026-10-01), each recorded in the
section it changes:

22. Ground map: fill thickness by zonal mean in the script; SLIDE materials
    and genesis each split into three sources by confidence; defaults carry
    `assumed` and `low`; water yields to the next source (section 3.2).
23. Slope units: `hydrology.route_grid`; cells draining off the grid take the
    nearest catchment; positional k-means fallback; split and merge alternate
    (section 3.3).
24. Candidates: the `label_patches` class formula; split pieces carry the
    patch's slope and aspect; islands kept; representative-point fallback for
    fine patches under coarse rasters; `contour_length_m` public (section 3.4).
25. Wall lines: boundary lines only near buildings; the claim probe at twice
    the tolerance; the terrain-break lower neighbour by aspect (section 3.5).
26. Polygons: segment-normal crest and toe; the inundated strip spread at the
    evacuated depth with a 1 m floor, both for the lead to confirm; projected
    snap with an area-loss guard; `kingsbury_zone` nullable (section 3.6).
27. `interpolated_slope_value` and `continuous_rating` written ahead of phase
    3 so step 7 imports (section 7.7); `ROCK_MATERIALS` lives in
    `ground_map.py` (section 7.3).

Decisions made at the phases 2 to 4 integration (2026-10-02), each recorded
in the section it changes:

28. `apply_count_bounds` lives in `wall_probability.py`, not `population.py`
    (sections 7.9, 7.10). Superseded 2026-10-05: `apply_count_bounds` is
    removed and the wall unit claim update in landslide step 12 replaces it
    (`.agents/plans/placing-retaining-walls-on-pifs.md`).
29. `BETA_MIN_HEIGHT_M` and `BETA_MAX_HEIGHT_M` stay in `beta_population`
    until the loss owner moves its pricing test (section 7.9, **I-14**).
30. Step 8's PGV/PGA ratio reads the cell a point falls in, NaN off the grid
    (section 7.7).
31. Step 1 keeps `SIZE_EXPONENT = 2.1`; `BETA_SOURCE_AREA_FRACTION = 0.252`
    carries the coverage; ellipse axes and the seed cell are written as columns
    (section 3.9).
32. Step 9 resolves a wall on several polygons by outcome rank, and a polygon
    reached by several large ones by most shared ground (section 3.10).
33. Vul shaking rw step 9 draws on the vulnerability stream with the world
    appended (section 3.11).

Decisions made at the review of phases 2 to 4 (2026-10-02), each recorded in
the section it changes; all four are built (2026-10-02), tested on synthetic
inputs and not run over the pilot:

34. Step 9 draws one uniform per wall line: every row with a wall takes the
    uniform of the first row in model order on the same `wall_line_id`, so a
    wall on polygons at several scales fails at the published rate
    (sections 3.10, 7.11). Built (J).
35. Only a failed urban polygon is superseded, where its evacuated geometry
    shares ground with a large evacuated polygon (intersection area above
    `SHARED_GROUND_TOLERANCE_M2`); a wall a large slide reaches is left to vul
    step 11's line test, a positive length of line inside the polygon
    (sections 3.10, 5.1, 7.11). Built (J).
36. `gen_wall_population.py` also writes `drawn_walls_path(w)`, every wall
    the world drew before the claim and coverage filters, and step 8 joins on
    it, so uninsured walls shape the hazard with `rw_id` null
    (sections 3.7, 3.8).
37. Vul step 10 writes through `world_loss_input_path(table, world_id,
    realisation_id, *, pilot)`; `loss_input_path(table, realisation_id, *,
    pilot)` is kept, deprecated, resolving world 0, for the loss module until
    its owner moves to worlds (section 3.15). Built (K); the move is register
    task **T-66**.

## As built, close-out review (2026-10-02)

The final review of the whole chain changed these names and rules. They override
the sections cited, which have not been rewritten line by line.

- **A wall split at a property boundary.** `geometry.wall_line_on_edge` now
  records every sloping-land line on a polygon's edge in a new column,
  `wall_line_ids`, longest shared edge first, counting a line only where it
  runs within `EDGE_ALIGNMENT_MAX_DEG` (30 degrees) of the boundary.
  `wall_line_id` is still the line with the longest shared edge on the step 7
  file; on the step 8 model it is the line whose drawn wall the polygon takes.
  New functions: `geometry.edge_line_ids`, `geometry.sloping_lines`,
  `fragility.drawn_edge_walls` (sections 3.6, 3.8, 7.6, 7.7).
- **Step 9 joins walls to polygons through `wall_line_ids`**, not `rw_id`,
  and decision 34's shared uniform groups polygons by any wall line they share,
  through chains of shared lines (sections 3.10, 7.11).
- **A wall fails with any of its polygons** (the project lead's rule,
  2026-10-02). Polygons sharing a wall read one uniform but divide the wall
  median by their own amplification factor; if any of them fails, the wall has
  failed and every polygon on it fails (`realisation._fail_with_the_wall`), so
  the wall fails where its weakest polygon would and absorption keeps the
  largest (sections 3.10, 7.11).
- **Placeholder geometry constants** carry the beta prefix:
  `BETA_HEADSCARP_BAND_M`, `BETA_HEADSCARP_BAND_STEEP_M`,
  `BETA_FILL_WEDGE_HEIGHT_MULTIPLE`, `BETA_MIN_RUNOUT_M` (section 7.6). The
  model parameters `URBAN_RATE_FACTORS`, `LOCALISED_FRAGILITY_BETA`,
  `TOPOGRAPHIC_AMPLIFICATION_MAX`, the `LOCALISED_THETA_*` constants and step
  1's `URBAN_AREA_SHARE` and `SOURCE_ASPECT_RATIO` keep their names: they are
  lasting parameters whose values the anchoring sets, not beta shortcuts.
- **Step 9 prints the rate setting** and refuses a model file carrying more
  than one.
- **The return period** of shaking step 5, landslide step 8 and vul shaking rw
  step 9 is imported from shaking step 3's `config.py`.
- **Runners.** `gen_exposure.main` now runs `s2_build_accessibility` and passes
  `accessibility` to `s4_estimate_land_value.main`, which had been a missing
  keyword. Running `gen_hazard.py` runs `main()` only; `main_urban` follows the
  exposure module through `gen_all.py`. No runner has been run end to end.
- **The end-to-end chain test** is
  `tests/landloss/hazard/landslide/urban/test_chain_end_to_end.py`: world 1,
  earthquake 2, every step's real code from step 7 to the vul step 10 tables on
  a synthetic hillside.
