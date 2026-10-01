# Step 2 — Land value: implementation plan

**Status:** Phases 0, 1 and 2 complete, and stage 3a of Phase 3 built but not
yet run with the stations fetched. Stage 3b is decided by the Days Bay test
below, Phase 4 is next, Phase 5 waits on the District Valuation Roll data that
register task T-20 covers, and Phase 6 on the hazard module.

The scripts in this folder are numbered so that `s1` to `s3` are the three
attributes attached before the valuation and `s4` is the valuation itself.
Terrain is `s1`, built by Phase 2, and accessibility `s2`, built by Phase 3;
`s3` is reserved for amenity, so the remaining gap is deliberate rather than
missing.

## Phase 0 — The steps-folder convention (complete)

- [x] Write the convention down as a repository skill,
      `.agents/skills/adding-steps-scripts/SKILL.md`, so every step is laid out
      the same way and the methodology is current when the report is assembled.
- [x] Carry the two markdown files in every step folder — a phased
      implementation plan holding everything aspirational, and a method file
      describing only what is implemented.

## Phase 1 — Value every address from the published rating valuations (complete)

- [x] Tag each address as flat or hill against the NLM flatland layer
      (`landloss.exposure.land.landform.classify_landform`).
- [x] Index the four published average land values onto a common valuation date
      (`landloss.exposure.land.land_value.index_base_rates`).
- [x] Spread each authority's indexed average across its addresses in proportion
      to a landform multiplier, with a per-authority normalising constant that
      holds the modelled mean on the published figure
      (`landloss.exposure.land.land_value.estimate_land_value`).
- [x] Write the valued addresses and the per-suburb cohort table
      (`s4_estimate_land_value.py`).
- [x] Print the modelled mean against the published average, so the calibration
      is visible without opening the outputs.
- [x] Map the modelled rate across the study area (`fig_land_value_map.py`).
- [x] Check the outputs against the published anchors, the rating unit counts,
      the known market order and the shape of the rate distribution
      (`src/scripts/landloss/exposure/land/validations/check_land_value_totals.py`).

## Phase 2 — DEM terrain (complete)

- [x] Derive continuous slope from the DEM, as a gradient every address carries
      in its own right (`landloss.common.utils.terrain.slope_degrees`, Horn's
      3x3 kernel). The binary flat/hill cut is kept rather than replaced: the
      published market bands the landform factors come from are priced on the
      class, so slope enters as a within-class modifier instead.
- [x] Derive relative topographic position, so an address is placed against the
      land around it rather than only against its own slope
      (`landloss.common.utils.terrain.topographic_position`, over the
      `topographic_position_window_m` neighbourhood in the factors asset).
- [x] Assign the elevated flat class — flat land raised above the surrounding
      floodplain — which Phase 1 declared in
      `landloss.exposure.land.landform.LANDFORM_CLASSES` and priced but could not
      assign (`landloss.exposure.land.landform.assign_elevated_flat`, above the
      `elevated_flat_min_topographic_position_m` threshold).
- [x] Sample both derivatives onto every address in the spine
      (`s1_build_terrain_attributes.py`), over the spine's extent buffered by
      half the topographic position window so that the addresses around the
      outside of the extent are not NaN purely by construction.
- [x] Spread value within a landform class by a continuous terrain modifier
      (`landloss.exposure.land.land_value.terrain_modifier`), standardised and
      rescaled within territorial authority and class so that the class keeps
      all of the between-class signal and the modifier only redistributes
      inside it.
- [x] Map the two attributes so they can be checked against the coastline and
      the contours before they are allowed to move anybody's land value
      (`fig_terrain_attributes.py`).
- [x] Re-derive the landform factors now three classes exist. Only
      `landform_factor_elevated_flat` moved, from 3.10 to 2.06: the old number
      was a premium flat and sea view market band, and the class is now assigned
      from terrain alone. Hill stays the reference class at 1.00 and flat stays
      the 1.72 ratio against it, both unchanged. The fitted version of all three
      is Phase 5.
- [x] Build on `ttpy.gis.raster` rather than a private raster stack
      (`landloss.common.utils.terrain` wraps `get_rolling_aggregation`,
      `save_raster` and `extract_point_values`), and add `rioxarray`, `xarray`
      and `rasterio` as direct dependencies.
- Dropped: building on `ttpy.gis.flatland`. The NLM flatland layer already
  arrives through `landloss.io.readers.get_koordinates_layer_extent`, so there
  is no second path to consolidate and the change would only move working
  code.

## Phase 2a — Run settings in config.py (complete)

- [x] Replace the command-line flags of `s1_build_terrain_attributes.py` and
      `s4_estimate_land_value.py` with one shared `config.py` in this folder,
      read in each `__main__` block and passed into `main()` as keyword
      arguments. The figure scripts keep their own arguments for now.

## Phase 2b — Section size (complete)

Hand checks of Wellington City land values on 2026-10-01 showed every
address being valued as if it stood on the assumed 450 m2 lot, so a 1,006 m2
Seatoun section and a 129 m2 Thorndon one were worth much the same, and every
rate per square metre was divided by the assumption rather than the section.

- [x] Measure each address's section as the whole LINZ property it stands on
      (`landloss.exposure.land.extent.section_area_per_address`, joined in
      `s4_estimate_land_value.py`). Splitting the area among the property's
      addresses was tried first and dropped: a published land value is for the
      property, and splitting doubled the rate of 13 Lawrence Street, Newtown,
      one 170 m2 property with three address points.
- [x] Size the value by `(section_area / assumed lot) ** 0.5`
      (`landloss.exposure.land.land_value.section_size_factor`, elasticity in
      the factors asset), leaving the per-authority normalisation to hold the
      total.
- [x] Divide the rate by the measured section rather than the assumed lot, with
      the assumed lot as the fallback and `lot_size_source` saying which.
- [x] Model the rate rather than the value: rate factor times site area is
      the site value, calibrated as total site value over total rating units
      against the published per-rating-unit average, so a unit-titled block is
      the sum of its units (`estimate_land_value`, `_value_one_ta`). It replaced
      a value-per-address model, under which every way of handling a property
      with several addresses -- split, whole, or counted once -- misrated
      apartment blocks or the houses around them.
- [x] Size a unit-titled block per rating unit, floored at
      `section_area_min_m2`, so a dense block is not extrapolated far below any
      real section (`section_size_factor`).
- [ ] Decide the size treatment for a freehold title with many dwellings on it.
      Sized as one large section today, at about a fifth of its neighbours'
      rate in Newtown. A cap on the size discount fixes those but would let
      rural parcels swamp the calibration, so it needs an urban/rural signal --
      the LCDB built-up class, or address density -- first.
- [ ] Settle `section_area_min_m2`. At 150 m2 unit-titled blocks rate about 1.4
      times their neighbouring houses in Te Aro and about twice in Thorndon and
      Johnsonville.
- [ ] Fit `section_area_elasticity` in the Phase 5 regression.
- [x] Count each property once in the authority mean
      (`landloss.exposure.land.land_value.property_weight`). Counted per
      address, the 14.5% of pilot addresses on properties over 5,000 m2 each
      took the whole property's size factor, and the normalisation took about
      44% off every ordinary property's value to pay for it; 13 Lawrence Street
      came out at 0.49 of its real rate, and 0.85 once each property counted
      once.

## Phase 3 — Accessibility (stage 3a built)

- [x] Give each address a gravity decay to the main centres,
      `A_i = sum over centres c of W_c * exp(-d_ic / L_c)`, with `W_c` the
      centre's weight — Wellington CBD 1.00, Lower Hutt CBD 0.30, Porirua CBD
      0.20, Upper Hutt CBD 0.12, local centres 0.05 to 0.10 — and `L_c` its
      decay length, 6 km for the Wellington CBD and 3 km for the secondary
      centres. The 3 km is applied to the local centres as well, which the plan
      left open (`landloss.exposure.land.accessibility.gravity_accessibility`,
      over `src/landloss/io/assets/land-value-centres.csv`).
- [x] Add a rail proximity term, `1 + a * exp(-d_station / 400 m)`, measured to
      the LINZ Topo50 station points
      (`landloss.io.readers.get_nz_rail_stations`).
- [x] Turn the two into a within-cohort modifier. Value is taken as
      proportional to `A_i ** elasticity`, times the rail term, centred in logs
      within territorial authority and landform class, clipped and rescaled to a
      mean of one, as the terrain modifier is
      (`landloss.exposure.land.land_value.accessibility_modifier`). The
      elasticity, the rail premium and the clip band are judgement rows in the
      factors asset.
- [x] Stage 3a: straight-line distance, which is cheap and needs no network
      data (`s2_build_accessibility.py`).
- [~] Run s2 and s4 over the pilot and the full study area with the stations
      fetched. s2 has run over the pilot, where no station is within the 2 km
      fetch buffer, so the pilot tests the gravity term alone; the modifier holds
      the authority mean and moves the pilot's suburb medians by about -6 to +5
      percent. The full study area, which is where the rail term acts, has not
      been run.
- [x] Add Wellington Station by hand. The LINZ Topo50 layer carries all 39
      suburban stations in the study area but not the terminus, which left
      Thorndon and Pipitea measured to Crofton Downs, 2.6 to 2.9 km away
      (`src/landloss/io/assets/land-value-extra-stations.csv`,
      `landloss.exposure.land.accessibility.add_stations`).
- [ ] Read the station list the run prints for stations that no longer take
      passengers. Topo50 describes a station as a passenger or freight point,
      and nothing filters it yet. Redwood appears twice, as its north and south
      platforms, which changes no distance.
- [ ] Check the centres on the figure. They are placed by hand on the main
      shopping street and are approximate to a few hundred metres, which is
      small against a 3 km decay. The local centre list is a first cut: Porirua
      has none of its suburban centres (Whitby, Mana), and Upper Hutt none
      besides its CBD.
- [ ] Stage 3b: road-network travel time. The test that decides whether 3b is
      worth building is Days Bay and Eastbourne, about 9 km from the Wellington
      CBD in a straight line and a 25 minute drive around the harbour — if 3a
      prices them as inner suburbs, the network build is justified.
- [x] Show the centres and their weights in the figure produced by
      `fig_town_centres.py`, so the weights are reviewable on a map rather than
      in a table. Straight lines already show the problem stage 3b is for:
      Makara village scores the same gravity as Tawa.

## Phase 4 — Amenity: sea view and winter sun

Phase 2 left this phase an explicit target to be judged against. The elevated
flat factor was cut from 3.10 to 2.06 because the class is now assigned from
terrain alone, and 3.10 came from the premium flat and sea view market band —
Seatoun, Oriental Bay, the waterfront. The headroom between the two, roughly a
50 percent premium on top of elevated flat, is what sea view, winter sun and
accessibility are expected to earn by multiplying together. If the amenity
multipliers cannot lift a genuine Seatoun or Oriental Bay address back into that
band, either they are too weak or the 2.06 is too low, and the `basis` cell of
`landform_factor_elevated_flat` in `src/landloss/io/assets/land-value-factors.csv`
is where that argument is recorded.

- [ ] Sea view by inverted viewshed: because visibility is reciprocal, run
      WhiteboxTools viewshed from a few hundred station points sampled on the
      sea over a 10 m DEM and read the visible-station count off the land,
      rather than running a viewshed from every property.
- [ ] Winter sun by WhiteboxTools `time_in_daylight` over a June-July window
      with terrain shadowing. This is what separates a good Wellington section
      from a bad one, and what a plain aspect calculation misses.
- [ ] Work at 10 m resolution. A 1 m DEM over the study area is about 3.2
      billion cells, which is not a sensible cost for an amenity multiplier.

## Phase 5 — Calibration against the District Valuation Roll

- [ ] Refit the landform, terrain, accessibility and amenity factors by
      regression against council District Valuation Roll land values, when
      register task T-20 closes. Until then every factor in
      `src/landloss/io/assets/land-value-factors.csv` is engineering judgement
      and the within-authority distribution is unvalidated.
- [ ] Fit `accessibility_elasticity` and `rail_station_premium` in the same
      regression. Both are judgement: the elasticity was set so that Tawa comes
      out at about half of Thorndon within Wellington City.
- [ ] Fit `beta_slope` and `beta_tpi` in the same regression. Both are judgement
      set on what a standard deviation of terrain ought to be worth — 10 percent
      down for slope, 5 percent up for topographic position — and they are the
      two numbers that decide how hard the terrain pushes inside a cohort.
- [ ] Tune `elevated_flat_min_topographic_position_m` against the observed share
      of elevated flat land rather than against the inundation reasoning it was
      set from. The Wellington City pilot promotes about 10 percent of flat
      addresses at 3.0 m, which is mid-band against the 5 to 20 percent the
      threshold was aimed at, but the other three authorities have not been run
      and the Hutt Valley floor is a very different distribution.

## Phase 6 — Hazard discounts

- [ ] Discount land exposed to a modelled hazard, once the hazard module
      produces the layers to discount against.

## Potential future improvements

- Have a valuer sign off the `index_to_2025_09` factors, or replace them with a
  valuer's own basis. They are read off the published QV House Price Index for
  the greater Wellington region, with the September figure interpolated between
  two published annual changes.
- Use sale prices where they exist rather than the rating valuation averages.
  More accurate, but the data is not held for the full study area.
- Narrow the published averages to residential addresses. They are residential
  averages applied to every address, because the LINZ address layer has no
  residential flag; this is the same gap step 1's plan carries.
- Put a minimum address count on the suburb cohort table before any of it is
  shown to anyone. Now that the terrain modifier gives nearly every cohort its
  own median rate, the ranking `describe_suburbs()` prints is worth reading —
  but it has no floor on cohort size, so a two-address elevated flat cohort
  ranks alongside a two-thousand-address one. Rongotai elevated flat is the
  pilot's example, at two addresses and third by median rate.
- Revisit the clip multiples in the factors asset. They are judgement floors and
  ceilings rather than researched figures. There are now two bands rather than
  one — `rate_clip_min_multiple` and `rate_clip_max_multiple` on the value
  itself, and `terrain_modifier_clip_min` and `terrain_modifier_clip_max` on the
  within-cohort modifier — and the terrain modifier has widened the spread the
  outer band has to hold, so how often either binds is worth checking on a full
  run rather than assumed.
