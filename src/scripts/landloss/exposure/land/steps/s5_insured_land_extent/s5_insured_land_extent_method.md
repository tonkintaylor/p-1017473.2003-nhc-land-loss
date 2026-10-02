# Step 5 — Insured land extent: method

- The step turns each **claim property** into the polygon the hazard modules are
  intersected against. `gen_insured_land.py` reads
  `temp/exposure/land-value-by-address.geoparquet` from step 2, fetches the
  property boundaries, building outlines and roads over its extent, builds the
  insured land and writes `temp/exposure/insured-land.geoparquet`. Both take a
  `-pilot` suffix when `config.PILOT` is set, so a pilot run cannot overwrite
  the full outputs.
- **The claim is the property, not the address.** That is the decision the step
  is built around and it replaces an earlier model keyed on address points, in
  which 40% of addresses found no building near enough to buffer and so carried
  no insured land at all. The module docstring of
  `src/landloss/exposure/land/extent.py` sets out the reasoning and what each
  part of it costs.
- The written layer carries `land_id`, `claim_id`,
  `land_rate_excl_gst_nzd_per_m2`, `land_rate_incl_gst_nzd_per_m2`, `area_m2`,
  `property_area_m2`, `building_count`, `dwelling_count` and the polygon, in
  that order.
- **The land rate is written both sides of GST.** Step 2's rate is taken as
  excluding GST and grossed up by `landloss.domain.gst.add_gst`, at `GST_RATE`
  of 15%, in `gen_insured_land.py`. Only the inclusive rate is handed to the
  loss module, as the land table's `$/m2 market value`
  (`landloss.vul.loss_input.build_land_table`).
- **`land_id` is minted here**, in `gen_insured_land.py`, by
  `landloss.exposure.asset_ids.mint_asset_ids` with `LAND_ID_SUFFIX`. It has the
  form `<claim_id>-L01`, numbered from 1 within the claim over the frame already
  sorted by `claim_id`. There is one polygon per claim today, so every id ends
  `-L01`; the id is kept separate so a claim split into several polygons later
  still gives the loss contract's land table one row per polygon. The column
  names come from `landloss.domain.loss_contract`, which `extent.py` and
  `driveways.py` also import `CLAIM_ID_COLUMN` from.
- **`address_id` stops here.** It is used only inside this step, to carry the
  step 2 rate onto a property through the address-to-claim rows. Nothing
  downstream of this step is keyed on `address_id`; every later exposure and
  vulnerability output is keyed on `claim_id` and the asset's own id.
- **Claim properties** come from `build_claim_properties`, which reads the LINZ
  NZ Property Boundaries layer through
  `landloss.io.readers.get_nz_property_boundaries` against
  `NZ_PROPERTY_BOUNDARIES_LAYER_ID`. It drops the road and water parcels, which
  are land with no residential cover over them, and dissolves boundaries with
  **identical geometry**, because a unit-titled block carries one boundary per
  unit on a single footprint and each would otherwise claim the whole block's
  insured land. Near-identical footprints are not caught, and the run prints how
  much property ground is still claimed twice.
- **The dwellings** are the address points standing inside the property, from
  `count_dwellings`. That count is what NHC's per-dwelling sub-caps and excess
  are multiplied by, so it is what sets the retaining wall cap — neither the
  land area nor the building count does. Step 3 at module level writes the same
  count out on its own, for the other asset classes to read.
- **A property with no address point carries no insured land**, because cover
  follows a residential building. A bare section belongs in that group; so does
  a property whose address point LINZ placed just outside its own boundary, and
  only the second is an error.
- **A building that cannot be a home is dropped**, by
  `drop_non_residential_buildings` in `landloss.exposure.land.extent`, before
  anything is buffered. Two tests, both of which rule buildings out and neither
  of which can rule one in:
  - **The name.** The outlines layer's `use` column names schools, hospitals,
    supermarkets, huts and shelters and says `Unknown` for everything else —
    3,209,472 of 3,236,141 outlines nationally. Anything named is dropped rather
    than a fixed list being excluded, so a use LINZ adds later is handled without
    editing the filter.
  - **The size.** A footprint over `MAX_DWELLING_FOOTPRINT_M2`, 500 m², is a
    warehouse, a mall or an office block rather than a house. The pilot's
    outlines run to a median of 120 m² and a 95th percentile of 290, so the
    threshold sits well clear of a large house. It is measured on the outline as
    served, before anything is cut to a property, so a terrace captured as one
    large polygon is judged whole — the same outline has to be ruled in or out
    consistently for every property it touches.

  `describe_building_filter()` in `gen_insured_land.py` prints what each test
  removed. A property left with no building then carries no insured land, which
  is how a school site or a retail park leaves the portfolio without a rule of
  its own.
- **The size test is the crude half, and it costs dwellings.** An apartment
  block is residential and has the footprint of a warehouse, so it is dropped
  with them and the flats inside it lose their insured land. That is why
  `describe_extent()` counts the dwellings on occupied properties that ended up
  with no building rather than leaving them to be inferred. Neither test says a
  building *is* residential, so what remains is still houses, offices and small
  commercial units together: this is a tidy-up, not the residential filter the
  study needs, which is step 1's Phase 3.
- **Every building inside the property sets the extent**, buffered by
  `INSURED_LAND_BUFFER_M` and the buffers merged by `buffer_buildings`. A
  garage, a sleepout and a shed are **appurtenant structures and are buffered
  like the dwelling**, so a property with three structures gives one piece of
  insured land and a `building_count` of three.
- **A building straddling a boundary is split**, by
  `assign_buildings_to_properties`. A piece is kept when it is the building's
  largest, or when it is at least `MIN_CROSSING_AREA_M2` and
  `MIN_CROSSING_SHARE` of the building — 5 m² and 10%. A semi detached pair
  captured as one outline is two buildings on two properties and is split; an
  outline overhanging by less is left whole on the property holding most of it,
  the overhang being the outline and boundary layers disagreeing along a shared
  edge. `validations/check_outlines_against_boundaries.py` measures both.
- **Driveways** are generated by `landloss.exposure.land.driveways` from each
  building part to the nearest road and unioned into the extent before it is
  clipped. A split terrace routes one driveway per half.
- **The extent is clipped to its own property** by `clip_to_property`. An 8 m
  line from a house near a boundary reaches onto the neighbour's section, and
  that ground is not covered by this claim. The part of a driveway beyond the
  boundary goes the same way: it runs onto the road reserve. Clipping is also
  what makes the extents pairwise disjoint, and it **replaces** the rule the
  address-keyed model needed, which partitioned contested ground between
  neighbours on whichever building was nearest.
- `describe_extent()` in `gen_insured_land.py` re-measures the result against
  its own dissolve, so a run states rather than assumes how much ground is
  claimed twice. Over the pilot that residual is 0.23 ha in 172.7, and it comes
  from property boundaries that overlap each other.
- Over the Wellington pilot: 11,352 boundaries reduce to 7,498 claim properties,
  4,494 of which carry a dwelling and 4,295 of those a building. Of the 10,256
  building outlines read, 322 cannot be a home and are dropped — 127 named (94
  schools, 27 hospitals, 6 supermarkets) and 241 over 500 m², with 46 failing
  both tests. The 9,934 kept have a median footprint of 118 m². The result is
  172.7 ha of insured land over 4,295 claims covering **7,926 of the 8,591
  dwellings**. The insured land is 93% of the property at the median, because
  the 8 m line reaches the boundary on a typical Wellington section.
- What the two filters cost the pilot, against 4,388 claims and 225.7 ha with
  neither: the name test took 14 claims, 18.4 ha and 58 dwellings; the size test
  took a further 79 claims, 34.6 ha and 454 dwellings. The area is out of
  proportion to the 3.1% of outlines removed because a school block, a hospital
  ward and a warehouse are large buildings on large sites, and the 8 m apron
  goes with the footprint.
- **665 of the 8,591 pilot dwellings now stand on a property carrying no insured
  land**, against 153 before either filter. Most of that increase is apartment
  blocks caught by the size test, and it is the number to watch if the threshold
  is revisited.

Potential future improvements see
`s5_insured_land_extent_implementation_plan.md`.
