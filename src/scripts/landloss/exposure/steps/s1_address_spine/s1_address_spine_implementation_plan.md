# Step 1 — Address spine: implementation plan

**Status:** Phase 1 complete. Phases 2 and 3 wait on parcel data and on a use
code that the LINZ address layer does not carry.

## Phase 1 — Build the spine from the LINZ address layer (complete)

- [x] Read the NZ Addresses layer over the four territorial authorities, clipped
      to the real boundaries rather than their bounding box
      (`s1_build_address_spine.py`).
- [x] Cut the layer back to current addresses on land, and to the columns the
      rest of the study groups by
      (`landloss.exposure.addresses.filter_addresses`).
- [x] Write the spine out as a geoparquet under `temp/exposure/`, with a
      separate pilot name so a pilot run cannot replace the full spine.
- [x] Print the per-TA address count beside each authority's published rating
      unit count, with the ratio, as the first measurement for register task
      T-23.
- [x] Cover the filtering with tests that do not touch the network
      (`tests/landloss/exposure/test_addresses.py`).

## Phase 1a — Run settings in config.py (complete)

- [x] Replace the command-line flags with `config.py` beside the script
      (`PILOT`, `FRESH`, `OUT`), read in the `__main__` block and passed
      into `main()` as keyword arguments.

## Phase 2 — Join LINZ parcels for land area (register task T-07)

- [ ] Join a parcel layer to the spine, so land area comes from a measured
      parcel rather than the per-authority `median_lot_size_m2` in
      `src/landloss/io/assets/land-value-base-rates.csv` that the land value
      step assumes today.
- [ ] Decide how an address that matches no parcel, or several, is handled, and
      print the count of each so the join is auditable in the run output.
- [ ] Derive the insured land polygon from the parcel — the 8 m line from the
      dwelling — and carry it beside the parcel area. This, not the full parcel,
      is the extent NHC settles on and the extent the landslide hazard and
      vulnerability modules intersect against.
- [ ] Feed the measured area back into step 2, replacing the assumed lot size in
      the rate per square metre.

## Phase 3 — Filter to residential once a use code is available

- [ ] Attach a land use or property category to each address, which the LINZ
      address layer does not carry, and narrow the population to residential.
      Until then the published residential averages are applied to shops,
      offices and warehouses alongside dwellings.
- [ ] Re-run the per-TA counts once the filter exists, since the
      address-to-rating-unit ratio is only interpretable after the
      non-residential addresses are out of the numerator.

## Phase 4 — Quantify the multi-unit and cross-lease share (register task T-23)

- [ ] Identify multi-unit, cross-lease and shared-land properties directly,
      rather than inferring their scale from the address-to-rating-unit ratio
      that `describe_counts()` prints.
- [ ] Decide whether those properties stay in the exposure population, which is
      the decision register task T-23 exists to evidence.

## Potential future improvements

- Reconcile the spine against NHC's own policy records, which would settle the
  residential question and the multi-unit question at once. Not available; it
  depends on what NHC is able to release.
- Confirm the LINZ property ID on the address layer joins to the hazard,
  vulnerability and loss modules without a spatial join.
- A figure showing the spine's coverage against the territorial authority
  boundaries, for the report.
- Cache the spine per territorial authority rather than as one file, so a single
  authority can be rebuilt without re-reading the other three.
