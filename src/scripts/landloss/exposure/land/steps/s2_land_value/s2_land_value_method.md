# Step 2 — Land value: method

- The step runs on the address spine from step 1. Both
  `s1_build_terrain_attributes.py` and `s4_estimate_land_value.py` read
  `temp/exposure/address-spine.geoparquet` and rebuild it from LINZ in their own
  `get_spine()` if it is not there, so either script runs on a clean checkout.
- The run settings of the scripts — `PILOT`, `FRESH`, the `SPINE`,
  `TERRAIN`, `ACCESSIBILITY`, `LAND_VALUE_OUT` and `COHORTS_OUT` path overrides
  and the `WINDOW_M` override — are read from the one `config.py` in this folder
  and passed into each `main()` as keyword arguments; `s1`, `s2`, `s4` and
  `fig_town_centres.py` take no command-line arguments. Sharing `PILOT`,
  `TERRAIN` and `ACCESSIBILITY` keeps s4 reading what s1 and s2 wrote.
- Each address is tagged flat or hill by
  `landloss.exposure.land.landform.classify_landform`, against the National
  Liquefaction Model flatland polygons read by
  `landloss.exposure.land.landform.get_flatland`. An address lying exactly on a
  flatland boundary is hill, because the join is `within` rather than
  `intersects`.
- The NLM is reused rather than a slope surface rebuilt from a DEM, and what
  that reuse costs is carried as limitation L-16 in the project register; the
  module docstring of `src/landloss/exposure/landform.py` records both.
- `classify_landform` assigns hill and flat only. The third class,
  `elevated_flat`, is assigned separately by
  `landloss.exposure.land.landform.assign_elevated_flat` from a terrain attribute,
  and the module docstring of `src/landloss/exposure/landform.py` records why
  the two are kept apart — the flatland join is a spatial question with no
  raster in it, and stays runnable on an extent no DEM has been fetched for.
- The terrain attributes are built by `s1_build_terrain_attributes.py`, which
  reads the same spine, fetches the elevation model through
  `landloss.io.readers.get_dem` and writes one row per address. The DEM is
  LINZ's, served from the STAC catalogue rather than Koordinates — LiDAR where
  it has been flown, falling back to the 8 m contour-derived model where it has
  not — which is the same elevation data the National Liquefaction Model stands
  on; the docstring of `get_dem` carries that and the survey-vintage limitation.
- The working resolution is `landloss.domain.constants.DEM_RESOLUTION_M`, and
  the comment on that constant is where the choice is argued: the study area at
  1 m is about 3.2 billion cells, at 10 m about 32 million, and nothing the land
  value model asks of the terrain is decided at finer than 10 m.
- Slope in degrees is computed by
  `landloss.common.utils.terrain.slope_degrees`, using Horn's 3x3 kernel — the
  one GDAL, ArcGIS and the NLM all use, so a slope from here is comparable with
  a slope quoted from any of them. Its docstring carries the kernel and the
  reason it is written out in numpy rather than taken from a library.
- Relative height is computed by
  `landloss.common.utils.terrain.topographic_position`: elevation minus the mean
  elevation of a square neighbourhood centred on the cell, in metres, positive
  on terraces and spurs and negative on valley floors. The neighbourhood width
  is the `topographic_position_window_m` row of
  `src/landloss/io/assets/land-value-factors.csv`, converted to an odd number of
  cells by `window_in_cells`; the window lives in the factors asset rather than
  in the script because the elevated flat threshold is only meaningful against a
  position measured over it.
- The DEM is fetched over the spine's own extent buffered by half that window
  plus one cell, computed by `dem_bbox()` in `s1_build_terrain_attributes.py`. A
  centred rolling window has no answer within half a window of the edge of its
  grid, so without the buffer every address around the outside of the extent
  would sample NaN because of where the extent was drawn rather than because of
  anything about the ground.
- Both derivative rasters are written to `temp/exposure/terrain-slope.tif` and
  `temp/exposure/terrain-position.tif` by
  `landloss.common.utils.terrain.write_raster`, sampled at every address point
  by `sample_at_points`, and the sampled values written to
  `temp/exposure/terrain-by-address.geoparquet` carrying `address_id`,
  `slope_deg`, `topographic_position_m` and the geometry. All four take a
  `-pilot` suffix when `PILOT` is True.
- Nodata is masked to NaN before either derivative is computed, by
  `mask_nodata()` in `s1_build_terrain_attributes.py`, and the run names which
  of the three nodata cases the DEM presented. Addresses that still sampled no
  value are counted per territorial authority by `describe_missing()` rather
  than passed quietly downstream.
- A flat address standing more than
  `elevated_flat_min_topographic_position_m` metres above its neighbourhood is
  promoted to `elevated_flat` by
  `landloss.exposure.land.landform.assign_elevated_flat`. A hill address is never
  promoted however high it stands, and an address with no topographic position
  keeps the class the flatland join gave it; the threshold is a row of
  `src/landloss/io/assets/land-value-factors.csv` with its basis on the row.
- Within a landform class, value is spread by the continuous terrain modifier
  `landloss.exposure.land.land_value.terrain_modifier`: slope and topographic
  position are standardised within each `TERRAIN_GROUP_COLUMNS` group, combined
  as `exp(beta_slope * z_slope + beta_tpi * z_tpi)`, clipped to the
  `terrain_modifier_clip_min` and `terrain_modifier_clip_max` rows of the
  factors asset, and rescaled so the group mean is exactly one.
- The standardising and the rescaling are both within the territorial authority
  and landform class rather than across them, and the module docstring of
  `src/landloss/exposure/land_value.py` sets out why: steep land is already
  classed as hill, so a slope term running across the classes would be paid for
  twice, once by the class and again by the slope. Held to a mean of one inside
  the group, the class keeps all of the between-class signal and the modifier
  does nothing but redistribute value inside it.
- An address the DEM had no value for, a cohort of one and a cohort whose
  addresses all share a value all resolve to a modifier of one rather than to
  NaN, which `_standardise_within_groups` carries and
  `tests/landloss/exposure/test_land_value.py` covers.
- Accessibility is measured by `s2_build_accessibility.py`, which reads the
  same spine and writes `temp/exposure/accessibility-by-address.geoparquet`
  carrying `address_id`, `gravity_accessibility`, `nearest_station_m` and the
  geometry, with a `-pilot` suffix when `PILOT` is True.
- `gravity_accessibility` is the straight-line gravity sum computed by
  `landloss.exposure.land.accessibility.gravity_accessibility` over the centres
  in `src/landloss/io/assets/land-value-centres.csv`, one row per centre with its
  weight, decay length, position and the basis for each on the row. The centres
  and their weights are shown in the figure produced by `fig_town_centres.py`,
  written to `report/exposure/land/land-value/fig/`, over the addresses
  coloured by their gravity accessibility on a log scale.
- `nearest_station_m` is the straight-line distance to the nearest LINZ Topo50
  railway station, read by `landloss.io.readers.get_nz_rail_stations` over the
  spine's extent buffered by `STATION_BUFFER_M` in `s2_build_accessibility.py`
  and measured by `landloss.exposure.land.accessibility.distance_to_nearest`.
  The run prints the names of the stations it found and does not filter them.
- The LINZ layer carries no Wellington Station, so the stations in
  `src/landloss/io/assets/land-value-extra-stations.csv` are added to it by
  `landloss.exposure.land.accessibility.add_stations`: an added station is kept
  if it falls inside the extent the layer was read over and is more than
  `DUPLICATE_STATION_M` from every station the layer already carries. The run
  names the stations it added.
- The run prints the deciles of gravity accessibility per territorial authority
  in `describe_gravity()` and the share of addresses within 400, 800 and 1,600 m
  of a station in `describe_station_distance()`.
- Within a landform class, value is also spread by the accessibility modifier
  `landloss.exposure.land.land_value.accessibility_modifier`: the logarithm of
  `gravity ** accessibility_elasticity * (1 + rail_station_premium *
  exp(-nearest_station_m / rail_station_decay_length_m))` is centred within
  each `TERRAIN_GROUP_COLUMNS` group, exponentiated, clipped to the
  `accessibility_modifier_clip_min` and `accessibility_modifier_clip_max` rows
  of the factors asset, and rescaled so the group mean is exactly one. The
  function's docstring sets out why it is centred in logs and why the group is
  the terrain modifier's.
- The view of the sea is measured by `s3_build_amenity.py`, which writes
  `temp/exposure/amenity-by-address.geoparquet` carrying `address_id`,
  `sea_view_share`, `coast_distance_m`, `winter_sun_share` and the geometry, with a `-pilot` suffix when `PILOT` is
  True. It fetches the DEM through `landloss.io.readers.get_dem` over the
  spine's extent buffered by the casting distance, and masks nodata with
  `mask_nodata()` from `s1_build_terrain_attributes.py`.
- `landloss.exposure.land.amenity.sea_mask` takes a DEM cell as sea when it lies
  outside the study area's land polygons (`get_study_areas`, land only) and
  stands no higher than `sea_view_max_sea_elevation_m`, or has no value.
  `landloss.exposure.land.amenity.sea_view_share` casts `sea_view_directions`
  rays from `sea_view_eye_height_m` above the ground at each address, out to
  `sea_view_max_distance_m` at the DEM's cell spacing, allowing for the Earth's
  curvature and refraction, and returns the share of directions in which a
  visible cell is sea. The four settings are rows of the factors asset.
  `landloss.exposure.land.amenity.measure_sea` returns that share together with
  `coast_distance_m`, the distance to the first sea cell along any ray whether
  or not it is visible: the straight-line distance to the coast to within the
  angle between two rays, NaN beyond the casting distance.
- `winter_sun_share` comes from the same rays. `measure_sea`, given a
  `landloss.exposure.land.amenity.WinterSun`, measures each address's horizon
  along every ray from `winter_sun_eye_height_m` above the ground, and
  `landloss.exposure.land.amenity.sunlit_share` runs the sun's path against it:
  of every sampled moment the sun is above the flat horizon, the share in which
  it also clears the address's horizon in that direction.
  `landloss.exposure.land.amenity.solar_position` gives the path from Cooper's
  declination and the hour angle in local solar time. The days are
  `winter_sun_days_sampled` spread from `winter_sun_first_day_of_year` to
  `winter_sun_last_day_of_year`, sampled every `winter_sun_minutes_step`
  minutes, built by `winter_sun_settings()` in `s3_build_amenity.py`; all four
  are rows of the factors asset.
- The run prints the share of the DEM taken as sea, the share of addresses
  with any view and the deciles of the share per territorial authority in
  `describe_shares()`, the share within 100, 250, 500 and 1,000 m of the coast in
  `describe_coast()`, the deciles of winter sun per authority in
  `describe_sun()`, and the suburbs with the widest median view in
  `describe_suburbs()`.
- Within a landform class, value is also spread by the amenity modifier
  `landloss.exposure.land.land_value.amenity_modifier`: the logarithm of `(1 +
  sea_view_premium * sea_view_share) * (1 + coast_premium *
  exp(-coast_distance_m / coast_decay_length_m)) * (1 + winter_sun_premium *
  winter_sun_share)` is centred within each
  `TERRAIN_GROUP_COLUMNS` group, exponentiated, clipped to the
  `amenity_modifier_clip_min` and `amenity_modifier_clip_max` rows, and
  rescaled to a group mean of one. `s4_estimate_land_value.py` joins the
  attribute with `read_amenity()` and `attach_amenity()`, and values without
  it, saying so, when the file is absent; `AMENITY` in `config.py` points s3
  and s4 at a different file.
- An address with no gravity value sits at the middle of its cohort, and one
  with no station distance takes no station premium; both resolve to a finite
  modifier, which `tests/landloss/exposure/land/test_land_value.py` covers.
- The published average land value for each territorial authority, its rating
  unit count, its index to the common valuation date and its median lot size are
  held in `src/landloss/io/assets/land-value-base-rates.csv`, one row per
  authority with the QV media release URL on the row. How the two derived
  columns were arrived at is written up in `src/landloss/io/assets/README.md`.
- The landform multipliers and the clip multiples are held in
  `src/landloss/io/assets/land-value-factors.csv`, one row per parameter with
  the derivation of the number in the `basis` cell on the same row.
- Values are assigned by `landloss.exposure.land.land_value.estimate_land_value`: the
  published average is indexed onto `COMMON_VALUATION_DATE` by
  `index_base_rates`, each address takes its landform multiplier — multiplied by
  its terrain modifier whenever the frame carries both of `TERRAIN_COLUMNS` and
  by its accessibility modifier whenever it carries both of
  `ACCESSIBILITY_COLUMNS`, and by the landform multiplier alone when it carries
  neither — a normalising
  constant from `solve_normalising_constant` scales the multipliers so the
  authority's mean equals the indexed average, the result is clipped to the
  configured multiples of that average, and the constant is re-solved once
  across the unclipped addresses so the mean still lands on the published
  figure. `_value_one_ta` carries that arithmetic and the one case it is not
  exact in.
- The consequence of that design, stated in the module docstring of
  `src/landloss/exposure/land_value.py`, is that the landform judgement moves
  value between properties within an authority and never changes what the
  authority is worth in total.
- The terrain join is optional. `s4_estimate_land_value.py` reads the attributes
  with `read_terrain()` and joins them with `attach_terrain()` — a left merge on
  `address_id` validated one-to-one, with the unmatched count printed — and when
  the file is absent it prints what the run is going without and values on
  landform class alone. `TERRAIN` in `config.py` points both scripts at
  a different file.
- The accessibility join is optional in the same way. `s4_estimate_land_value.py`
  reads the attributes with `read_accessibility()` and joins them with
  `attach_accessibility()`, a left merge on `address_id` validated one-to-one
  with the unmatched count printed, and without the file it prints that it is
  valuing without the accessibility modifier. `ACCESSIBILITY` in `config.py`
  points s2, s4 and `fig_town_centres.py` at a different file.
- The run prints the calibration per territorial authority in
  `describe_calibration()` — the modelled mean, the indexed published average
  and the percentage difference between them — together with the hill, flat and
  elevated flat counts in `describe_landform()`, whose last column is the share
  of flat land the topographic position threshold promoted and is what that
  threshold is judged on.
- `describe_distinct_rates()` prints how many distinct rates to the cent the run
  produced, across addresses and across suburb cohorts. That count is what the
  terrain modifier is measured by: on landform class alone an address's rate
  depends on nothing but its authority and one of three classes, so four
  authorities can produce at most twelve rates between them however many
  addresses they hold.
- The per-address result is written to
  `temp/exposure/land-value-by-address.geoparquet`, and the cohort table from
  `landloss.exposure.land.land_value.summarise_by_suburb`, one row per territorial
  authority, suburb and landform class, to `temp/exposure/land-value-by-suburb.csv`.
  Both take a `-pilot` suffix when `PILOT` is True, so a pilot run cannot overwrite
  the full outputs.
- The distribution of the modelled rate across the study area is shown in the
  figure produced by `fig_land_value_map.py`, written to
  `report/exposure/land/land-value/fig/`. It draws one colour per distinct modelled
  rate while there are no more than `MAX_DISCRETE_CLASSES` of them, which is a
  run valued on landform class alone, and falls back to the `QUANTILE_CLASSES`
  quantile bins once the terrain modifier makes the surface continuous; both
  thresholds are constants in that script.
- The two terrain attributes themselves are shown in the figure produced by
  `fig_terrain_attributes.py`, also written to
  `report/exposure/land/land-value/fig/`: slope on a sequential ramp pinned at zero,
  topographic position on a diverging ramp held symmetric about zero. It takes
  the same `--pilot`, `--ta <name>` and `--ta all` arguments as
  `fig_land_value_map.py`, and reads the s1 output rather than rebuilding it,
  refusing with the command to run when the file is absent.
- `fig_land_value_map.py --ta "<name>"` draws a single territorial authority
  zoomed in, and `--ta all` writes one figure per authority. A per-authority map
  is framed on where its addresses are rather than on its boundary — the trim is
  `TA_FRAME_TRIM` in that script — because Wellington City's boundary runs west
  over Makara and Ohariu to the open coast, which is most of its area and a few
  hundred of its addresses. The colour classes are taken from the whole study
  area by the `reference` argument of `classify_rates`, so a rate keeps one
  colour across the set and the four maps can be read side by side.
- Each address is given its section area by `attach_section_areas()` in
  `s4_estimate_land_value.py`: the LINZ property boundaries, read by
  `landloss.io.readers.get_nz_property_boundaries` and reduced to claimable
  ground by `landloss.exposure.land.extent.build_claim_properties` (the same
  reduction step s5 uses), are joined to the addresses by
  `landloss.exposure.land.extent.section_area_per_address`, which gives each
  address the whole area of the property it stands on, so every address on a
  property carries the same area, size factor and rate. The run prints the measured share and the quartiles of section area per
  territorial authority against the assumed lot in `describe_section_areas()`.
- **The rate per square metre is what is modelled, and the land value follows
  from it** (`landloss.exposure.land.land_value.estimate_land_value`). Each
  address's rate factor is its landform factor times its terrain and
  accessibility modifiers times its section size factor; its property's site
  value is that factor times the site area; and the per-authority constant is
  solved so that total site value over total rating units equals the indexed
  published average, which is how the published per-rating-unit figure is
  built. `_value_one_ta` carries the solve.
- `section_area_per_address` also carries `addresses_on_property` and
  `rating_units_on_property`, the latter the property's `boundary_rows`: one per
  unit of a unit-titled block, whose titles LINZ stacks on one footprint, and
  one for a freehold title however many addresses stand on it.
- The section size factor, `landloss.exposure.land.land_value.section_size_factor`,
  multiplies the rate by `(max(area per rating unit, section_area_min_m2) /
  median_lot_size_m2) ** (section_area_elasticity - 1)`, both parameters rows of
  the factors asset. Per rating unit, so a unit-titled block is rated as the
  sections its units would each have and its land is the sum of theirs; a
  freehold property is sized on its whole area.
- Each property counts once in the calibration:
  `landloss.exposure.land.land_value.property_weight` weights an address by one
  over the addresses on its property, since every address on a property
  carries the property's area, rating units and site value.
  `ta_mean_land_value` computes the same per-rating-unit mean for the run's
  calibration table and for `check_land_value_totals.py`.
- The value clip bounds the site value per rating unit to the
  `rate_clip_min_multiple` and `rate_clip_max_multiple` rows times the indexed
  average. The floor applies only to a property of one rating unit, because a
  flat's share of its block's land is legitimately small.
- The outputs carry `land_rate_nzd_per_m2`; `site_land_value_nzd`, the whole
  property's land; `land_value_nzd`, that over the property's rating units,
  which is what a published per-property land value is; and `lot_size_m2`, the
  site area the rate is per, with `lot_size_source` `measured` or `assumed`. An
  address standing in no property is one rating unit on the per-authority
  `median_lot_size_m2` and takes a size factor of one, which is the model
  before areas were measured.
- The arithmetic is covered by `tests/landloss/exposure/test_land_value.py`,
  `tests/landloss/exposure/test_landform.py` and
  `tests/landloss/common/utils/test_terrain.py`, and the outputs of a real run are
  checked against the published anchors, the rating unit counts, the known
  market order of Wellington suburbs and the shape of the rate distribution by
  `src/scripts/landloss/exposure/land/validations/check_land_value_totals.py`.
- Two of those checks are reported rather than enforced while the model is this
  coarse, and both say so in the run output. The address count per rating unit
  is reported under `--pilot`, because a pilot box covers part of one authority.
  The right-skew test is reported whenever the run produces fewer than
  `SKEW_MIN_DISTINCT_RATES` distinct rates, because on landform class alone every
  address takes one of three values per authority and the sign of the skew is
  then decided by the class shares rather than by anything about the model. A run
  with the terrain modifier on clears that threshold by a wide margin, so the
  test is enforced there and reported only on a landform-only run.

## Known weaknesses

- The four authorities were valued up to a year apart across a falling market —
  the dates are on each row of `src/landloss/io/assets/land-value-base-rates.csv`
  — and they are brought onto one date by the `index_to_2025_09` factor. That
  factor is read off the published QV House Price Index for the greater
  Wellington region, with the September figure interpolated between two
  published annual changes, as `src/landloss/io/assets/README.md` sets out. No
  valuer has signed it off.
- `median_lot_size_m2` is documented judgement anchored on a 600 m2 regional
  convention, not a researched per-authority median. It is now the reference
  the section size factor is relative to and the fallback for an unmeasured
  address, rather than the divisor of every rate; the derivation behind each
  of the four numbers is in `src/landloss/io/assets/README.md`.
- A freehold property with many addresses -- a housing estate on one title --
  is sized as one large section, so its rate is discounted as a big garden's
  would be: Newtown's properties of 20 or more addresses, a median 6,538 m2,
  rate at about a fifth of the suburb's houses. A rating unit that aggregates
  several titles is measured over all of them, as Oriental Bay's 31 Hay Street
  is (771 m2 against a 339 m2 title). `section_area_elasticity` and
  `section_area_min_m2` are judgement.
- The distribution within an authority rests entirely on the three-class
  landform split and the terrain modifier, and every number behind both is in
  the `basis` column of `src/landloss/io/assets/land-value-factors.csv` as
  judgement. Nothing validates it: the
  suburb ranking check in `check_land_value_totals.py` reports how many of the
  suburbs in its `EXPECTED_HIGH_SUBURBS` and `EXPECTED_LOW_SUBURBS` constants
  land in the expected half of the modelled ranking, and prints how few distinct
  medians the model produces across all of them, but its status is
  informational and never fails the run. District Valuation Roll land
  values, which register task T-20 covers, are what the factors are fitted
  against once they arrive.
- The three numbers that decide what the terrain does to a value are engineering
  judgement, not fitted coefficients, and each says so on its own row of
  `src/landloss/io/assets/land-value-factors.csv`. The elevated flat threshold
  `elevated_flat_min_topographic_position_m` decides how much of the flat land
  takes the raised-terrace premium at all; `beta_slope` and `beta_tpi` decide how
  hard the two derivatives push inside a cohort. The regression against
  District Valuation Roll land values, which register task T-20 covers, is
  what replaces all three; until it runs the terrain modifier is a plausible
  shape rather than a measured one.
- The elevated flat factor is a terrain premium and is not the view premium.
  2.06 pays flat, sunny, easy-to-build-on ground a modest premium over ordinary
  flat land, and the `basis` cell on that row records what the number is
  deliberately not paying for: the earlier 3.10 came from the premium flat and
  sea view market band, which describes Seatoun, Oriental Bay and the waterfront,
  while the class is now assigned from terrain alone and picks up every drive-on
  terrace in Karori, Khandallah, Johnsonville, Maungaraki and Pinehaven.
  Nothing in this step models sea view or winter sun, so an elevated flat
  address is credited with neither.
- The elevation model is a merge of LiDAR surveys flown in different years
  across the study area — Wellington in 2023, Hutt City in 2025, Porirua
  unknown — which is limitation L-12 in the project register and is recorded
  in the docstring of `landloss.io.readers.get_dem`. A step in slope or in
  topographic position across a survey boundary may therefore be an artefact
  of the join between two surveys rather than a landform, and every address
  within half a topographic position window of such a boundary has some of
  the other survey in its neighbourhood mean.
- Accessibility is measured in straight lines, which overstates how close the
  far side of the harbour is to the Wellington CBD — Days Bay and Eastbourne are
  about 9 km away as the crow flies and a 25 minute drive — and gives Makara
  village the same gravity as Tawa. The centres are placed by hand, and the
  elasticity, the rail premium and the clip band are judgement, each on its row
  of the two assets.
- The sea view is measured over the bare-earth DEM, so houses and trees in
  front of an address do not block it, which overstates the view from flat
  land a few rows back from a beach. One eye height serves every address. The
  same holds for winter sun: a neighbouring house or tree does not shade a
  section, only the terrain does, and the horizon is read along the nearest of
  72 rays to the sun's bearing.
- The published averages are residential averages applied to every address,
  because the LINZ NZ Addresses layer carries no residential flag. That gap
  belongs to step 1 and is carried in its method file as well.

Potential future improvements: see `s2_land_value_implementation_plan.md`.
