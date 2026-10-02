# Step 1 — Address spine: method

- The exposure population is every current address on land in the four
  Wellington territorial authorities, read from the LINZ NZ Addresses layer by
  `s1_build_address_spine.py` through `landloss.exposure.addresses.get_addresses`.
- The address layer is used in preference to a parcel layer because it already
  carries `territorial_authority` and `suburb_locality` on every point, which
  are the two units the study reports by. The reasoning, and the identifier
  chosen to join the rest of the study back to, are in the module docstring of
  `src/landloss/exposure/addresses.py`.
- The read is clipped to the territorial authority boundaries packaged with
  `landloss.io.area_of_interest.get_study_areas`, not to their bounding box, so
  the Wairarapa addresses inside that rectangle are excluded. The four
  authorities the boundaries cover are `STUDY_AREA_TA_CODES` in
  `landloss.domain.constants`.
- Retired and proposed addresses, water addresses, and addresses with no usable
  geometry are dropped by `landloss.exposure.addresses.filter_addresses`. The
  lifecycle and land flags it tests are `CURRENT_LIFECYCLE` and `LAND_FLAG`, and
  the columns carried forward are `ADDRESS_COLUMNS`, all in the same module.
- Geometry is tested at the shapely level rather than with `GeoSeries.notna`,
  because clipping to a boundary is what produces the empty geometry being
  looked for; the comment in `filter_addresses` records why.
- The spine is written to `temp/exposure/address-spine.geoparquet`, or to
  `address-spine-pilot.geoparquet` when `PILOT` is True, so a pilot run cannot
  overwrite the full spine. `temp/` is gitignored, and the directory comes from
  `TEMP_DIR` in `scripts.landloss.paths` rather than from a `parents[N]` count in
  the script; the repository root it resolves to is printed by every run.
- The run settings — `PILOT`, `FRESH` and the `OUT` path override — are read
  from `config.py` beside the script and passed into `main()` as keyword
  arguments; the script takes no command-line arguments.
- The run prints each authority's address count beside the rating unit count
  from its published district revaluation, and the ratio between them, in
  `describe_counts()`. Those published counts are the `QV_RATING_UNITS` constant
  in the script, and they come from the same four revaluations that supply
  `src/landloss/io/assets/land-value-base-rates.csv`.
- The largest suburb localities are printed by `describe_suburbs()`, as a shape
  check on the unit the land value cohorts are later grouped by.
- The filtering is covered without the network by
  `tests/landloss/exposure/test_addresses.py`, which fakes the reader rather
  than reaching LINZ.

## Known weaknesses

- The LINZ NZ Addresses layer carries no residential or commercial flag, so
  shops, offices and warehouses sit in the spine beside dwellings. The
  population is every current land address, which is wider than the dwellings
  NHC covers; the module docstring of `src/landloss/exposure/addresses.py`
  states the same limit.
- Because of that, the address-to-rating-unit ratio `describe_counts()` prints
  is an upper bound on the multi-unit and cross-lease share rather than a
  measurement of it — commercial addresses inflate it by an unknown amount. The
  run says so in its own output.
- The layer carries no land area, so every per-square-metre figure downstream
  rests on the per-authority `median_lot_size_m2` assumption documented in
  `src/landloss/io/assets/README.md` rather than on a measured parcel.

Potential future improvements: see `s1_address_spine_implementation_plan.md`.
