# Step 5 — Insured land extent: implementation plan

**Status:** Phases 1 to 3a complete. The claim is the property, the extent is
clipped to it, and buildings that straddle a boundary are split. Phase 4 is the
land value loop, which waits on the District Valuation Roll data.

The step is numbered `s5` because step numbers run across the `exposure` module
rather than across one `steps/` folder. `s1` is the address spine and `s3` the
dwelling count, both at module level, and `s2` is the land value.

## Phase 1 — The 8 metre buffer (complete)

- [x] Read the LINZ NZ Building Outlines layer for an extent, with the licence
      and publisher on the reader
      (`landloss.io.readers.get_nz_building_outlines`).
- [x] Buffer the outlines by the insured land distance and merge them into one
      polygon per claim (`landloss.exposure.land.extent.buffer_buildings`),
      appurtenant structures included.
- [x] Write the layer with the rate per square metre carried onto it
      (`gen_insured_land.py`).
- [x] Print what found what, the ground claimed twice, and the measured area
      against the lot size step 2 assumed (`describe_*` in `gen_insured_land.py`).
- [x] Draw the close-up the buffer is judged by eye against
      (`fig_insured_land.py`).
- [x] Cover the arithmetic with synthetic geometries
      (`tests/landloss/exposure/land/test_extent.py`).

## Phase 2 — Driveways (complete)

- [x] Read the LINZ roadway layer over the study extent, pinned as a named
      constant beside `NZ_BUILDING_OUTLINES_LAYER_ID`.
- [x] Generate a driveway as the shortest path from each building part to the
      roadway. This resolves **I-10**, which proposed mapping them by remote
      sensing.
- [x] Combine the driveway with the 8 metre buffer before the extent is clipped,
      so the part on the road reserve is removed with everything else outside
      the property.
- [ ] Decide the gradient above which a generated route is not a credible
      driveway, and what happens to a building with no route below it.

## Phase 3 — The property is the claim (complete)

This phase replaced the address-keyed model outright. Under it, a building went
to exactly one address, so **40% of addresses carried no insured land at all**
and passed through the whole chain contributing nothing, while a block of flats
put several claims on ground that settles as one.

- [x] Read the LINZ property boundary layer, pinned as
      `NZ_PROPERTY_BOUNDARIES_LAYER_ID`.
- [x] Make the property the claim, one row per distinct piece of ground
      (`build_claim_properties`). Road and water parcels are dropped and titles
      stacked on one footprint are dissolved.
- [x] Count the dwellings from the address points inside the property
      (`count_dwellings`), which is what the per-dwelling sub-caps multiply.
- [x] Buffer every building on the property, appurtenant structures included.
- [x] Split a building that properly straddles a boundary into one part per
      property, and drop a smaller overhang as boundary error
      (`assign_buildings_to_properties`).
- [x] Clip the extent to the property, so a buffer cannot reach across a
      boundary onto land the policy does not cover (`clip_to_property`). This
      also replaced the Voronoi partition of contested ground.

Over the pilot this takes coverage from 4,764 addresses of 8,591 to **8,438
dwellings of 8,591**, on 4,388 claims.

- [ ] Dissolve property boundaries that overlap heavily without being identical.
      0.2 ha of the pilot's 225.7 ha is still claimed by two properties.
- [ ] Look at the 3,004 properties carrying no dwelling and the 106 carrying no
      building, and separate the bare sections from the address points LINZ has
      placed outside their own boundary.
- [ ] Check what a rating unit that aggregates several titles does to the claim.
      One pilot property takes 205 addresses, and a large rural rating unit can
      swallow a row of houses.

## Phase 3a — land_id for the loss contract (complete)

- [x] Mint a `land_id` per insured land polygon, `<claim_id>-L01`, with
      `landloss.exposure.asset_ids.mint_asset_ids`, and write it first on
      `insured-land.geoparquet` (`gen_insured_land.py`).
- [x] Take `CLAIM_ID_COLUMN` in `extent.py` and `driveways.py` from the shared
      `landloss.domain.loss_contract`, so the name is defined once.
- [x] Keep `address_id` internal to this step; nothing downstream is keyed on it.

## Phase 3b — GST on the land rate (complete)

- [x] Write the rate both excluding and including GST, grossing it up with
      `landloss.domain.gst.add_gst` rather than inline arithmetic.
- [x] Hand only the GST-inclusive rate on to the loss module's land table.
- [ ] Confirm that step 2's rating-valuation rate is exclusive of GST, which
      this phase assumes.

## Phase 4 — Close the loop on land value

- [ ] Feed the measured insured area back into step 2 in place of the
      per-authority `median_lot_size_m2`, which closes most of **T-25**. The
      property area is now carried on every row, so the comparison is available.
- [ ] Value the claim from the property rather than from the mean of the rates
      of the addresses on it, which is the stand-in the step currently uses.
- [ ] Apply the premium on land within 2 m of a building, once the District
      Valuation Roll data of **T-20** is there to size it against.
- [ ] Extend `validations/check_land_value_totals.py` to check total modelled
      insured land value against the published rating valuation totals, now that
      area is measured rather than assumed.

## Phase 5 — Validate the extent

- [ ] Insured land area against property area, per territorial authority. The
      pilot gives 93% at the median, and a different distribution in a flatter
      authority is the check that the buffer is behaving.
- [ ] Count of properties with no building outline and of addresses outside
      every boundary, per territorial authority, as a validation rather than a
      line of run output.

## Potential future improvements

- Distinguish a dwelling from a garage or a shed. The outline layer's `use`
  column now takes the named institutions out — schools, hospitals,
  supermarkets, huts and shelters, 1.2% of the pilot's outlines — and a 500 m²
  footprint cap takes the warehouses and office blocks, a further 1.9%. But the
  column says `Unknown` for every other building and a shed is small, so the
  extent is still buffered off every remaining structure on a property. That is
  the right answer for appurtenant structures and the wrong one for a building a
  dwelling-triggered cover would not reach. Separating a house from a shed needs
  something the layer does not carry.
- Recover the apartment blocks the 500 m² footprint cap removes. It is the crude
  half of the filter: a block of flats is residential and has the footprint of a
  warehouse, and the cap costs the pilot 454 dwellings' insured land against 58
  for the name test. A property carrying many address points on one large
  outline is an apartment block rather than a warehouse, so `dwelling_count`
  from step 3 is the obvious thing to exempt on, and the threshold itself
  (`MAX_DWELLING_FOOTPRINT_M2`) should be checked against the footprint
  distribution in a flatter authority before the full run.
- Narrow the population to residential properties, which is step 1's Phase 3 and
  the bigger half of the same problem: the use filter removes named
  institutions, not the shops, offices and warehouses that carry no `use` value.
  The route is `valuation_reference` on the property boundaries, populated on
  90.8% of the pilot's polygons, joined to a council rating information database
  for the property category under the Rating Valuations Rules.
- Speed. The extent is now one overlay and one clip rather than a Voronoi
  diagram over every contested outline, so the partitioning cost that made the
  address-keyed model slow has gone.
