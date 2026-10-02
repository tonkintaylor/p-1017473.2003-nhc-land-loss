# Land exposure: status

**Status:** The claim is the property. Land value modelled per square metre and
applied to an insured land extent buffered off every building on the property,
driveways included, clipped to the boundary.

**Updated:** 2026-10-01

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

The module ends at one layer, `insured-land`, carrying one row per `claim_id`
with a rate per square metre, a dwelling count and the insured land polygon.
Everything below exists to produce that layer.

- [~] Take the insured extent as an **8 m buffer of the building outlines, combined
  with the driveway**, rather than the whole parcel. That is the land NHC
  settles on, so it is the extent the hazard modules intersect against. The
  buffer is built; the driveway is not.
- [>] **Generate driveways** as the shortest path from each building outline to the
  roadway, since no driveway dataset exists for the study area. This resolves
  **I-10**, which proposed mapping them by remote sensing.
- [x] Attribute the extent against the **property boundaries**, which supply the
  identifier and the property each piece of insured land belongs to, and clip it
  to them so a buffer cannot reach onto the neighbour's section.
- [~] Apply the modelled **rate per square metre** to the insured extent, with a
  **premium on land within 2 m of a building** — the land immediately supporting
  the dwelling is worth more than the rest of the section, and it is also the
  land whose loss matters most.
- [x] Key on `claim_id`, which is the **property**. The LINZ property boundary
      sets the claim, every building outline inside it sets the insured land
      extent, and the address points inside it count the dwellings. This closed
      **L-11**: the claim key is minted here rather than at the `loss` boundary,
      because the property is what a claim is made over.
- [x] Take the dwelling count from the address points inside the property, since
      that is what both sub-caps and the excess are multiplied by. Step 3 at
      module level writes it out for the other asset classes.
- [x] **Split a building that straddles a boundary** by more than 5 m² and 10%,
      counting it in both properties; drop a smaller overhang as boundary error.

Land value per square metre is a step in its own right and is already built; see
`steps/s2_land_value/`.

## Loss contract

What this module owes the land table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Supply a `land_id` per insured land polygon, `<claim_id>-L01`, minted in
  `steps/s5_insured_land_extent/`.
- [x] Supply `claim_id`, the LINZ property boundary's identifier.
- [~] Supply the `$/m2 market value`, written both sides of GST as
  `land_rate_excl_gst_nzd_per_m2` and `land_rate_incl_gst_nzd_per_m2` by
  `landloss.domain.gst.add_gst`; only the inclusive rate reaches `loss`. Still
  the mean of the address rates (`Next` 2), each now divided by its measured
  section rather than an assumed lot, and step 2's rate is assumed to exclude
  GST.
- [x] Supply `total_insured_land_area`, written as `area_m2`.
- [x] Supply coordinates, as the insured land polygon.
- [x] Supply `dwelling_count`. The contract omits it, but `loss` needs it for
  the sub-caps and the excess (**Q-07**).

## Where it is now

The rate per square metre and the polygon it is applied to both exist, and the
polygon now includes the driveway and is cut to the property boundary.

- `../steps/s1_address_spine/` builds the address spine that this and every other
  asset hangs off. It sits at module level because retaining walls, culverts
  and bridges
  read it too.
- `steps/s2_land_value/` values every address — landform class, DEM slope and
  topographic position, and the indexed rating valuations — and writes
  `land-value-by-address.geoparquet` under `temp/exposure/`. That layer is the
  `land-value` input the rest of the chain consumes.
- `validations/check_land_value_totals.py` checks those outputs against the
  published anchors.
- `../steps/s3_dwellings_per_property/` counts the dwellings on every claim
  property and writes the address-to-claim mapping behind it. It sits at module
  level because the sub-caps on walls and crossings are per dwelling too.
- `steps/s5_insured_land_extent/` builds the claim properties from the LINZ
  property boundaries, buffers every building standing on one by 8 m, unions the
  driveways in and clips the result to the boundary, writing
  `insured-land.geoparquet` under `temp/exposure/` carrying `land_id`,
  `claim_id`, `land_rate_nzd_per_m2`, `area_m2`, `property_area_m2`, `building_count`,
  `dwelling_count` and the polygon. That layer is what the hazard modules
  intersect against.
- Over the Wellington pilot that is **4,388 claims covering 8,438 of the 8,591
  dwellings**, on 225.7 ha. Under the address-keyed model it was 4,764 addresses
  of 8,591, the rest passing through the whole chain contributing nothing.
- The insured land is 93% of the property at the median, because the 8 m line
  reaches the boundary on a typical Wellington section.
- 3,004 claim properties carry no dwelling and a further 106 no building. Bare
  sections belong in that group; so do address points LINZ has placed outside
  their own boundary, and only the second is an error.
- The building outlines are read by `landloss.io.readers.get_nz_building_outlines`
  against `NZ_BUILDING_OUTLINES_LAYER_ID`, the roads by `get_nz_address_roads`
  and the property boundaries by `get_nz_property_boundaries` against
  `NZ_PROPERTY_BOUNDARIES_LAYER_ID`.
- `validations/check_outlines_against_boundaries.py` measures the buildings that
  straddle a boundary: 241 of the pilot's 6,927 outlines do so by more than 5 m2
  and 10%, and 77% of those span two freehold titles -- semi detached and
  terraced houses captured as one polygon. A further 3,227 overhang by a median
  of 0.30 m2, which is the two layers disagreeing.
- The 2 m premium is not implemented.
- The rate per square metre is modelled directly, per site, and calibrated
  so that total site value over total rating units is each authority's
  published average (2026-10-01). It is built on the measured area of each
  address's property, so the rate and the property area the insured land is
  cut from now describe the same ground. The per-authority
  `median_lot_size_m2` survives only as the reference the size factor is
  relative to and the fallback for an address standing in no property.

## Next

1. Decide how a route too steep to be a driveway is handled, and what happens
   to a building with no drivable route below it.
2. Value the claim from the property rather than from the mean of the rates of
   the addresses standing on it. Since 2026-10-01 the land value step models
   the rate per site and every address on a property carries it, so the mean is
   exact for a property; what is left is valuing it as one row.
3. Done 2026-10-01: the land value step measures each address's property from
   the property boundaries and divides the rate by its area (Phase 2b of
   `steps/s2_land_value/`). What is left of **T-25** is the fallback lot size
   for the few addresses in no property.
4. Add the 2 m premium to the rate per square metre.
5. Dissolve property boundaries that overlap heavily without being identical.
   0.2 ha of the pilot's 225.7 ha is still claimed by two properties.
6. Separate the bare sections from the address points placed outside their own
   boundary, among the 3,004 properties carrying no dwelling.
7. Revise the land value estimate to mimic how councils set land value rates --
   premiums for sea views and for closeness to centres, and hazard discounting
   -- following `.agents/plans/estimating-land-values-wellington.md`
   (**T-49**, owner Perrie Gilbert, agreed 2026-09-25). Sense-check it against a
   few CV land values looked up by hand on homes.co.nz or QV -- the land value,
   not the capital value -- and not scraped. Council values may yet arrive
   (2026-09-30); keep progressing until they do. Building on licensed values
   would put everything derived from them under that licence, so the further
   the model gets on open data first, the better. Stage 3a of the plan,
   straight-line accessibility to the main centres and to railway stations, is
   built (`steps/s2_land_value/s2_build_accessibility.py`), and so is Phase 4:
   sea view, distance to the coast and winter sun
   (`steps/s2_land_value/s3_build_amenity.py`).
8. Done 2026-10-02: one driveway per property, routed from its largest
   building as the main dwelling (**T-60**). Parcel 3989118, which carried two
   because it has two dwellings, now carries one. Whether a second dwelling
   earns its own is still **Q-15**, for John Leeves.
9. Done 2026-10-02: only the first 60 m of the route from the dwelling is
   insured (**T-61**). `MAX_DRIVEWAY_LENGTH_M`, 300 m, stays as the distance
   beyond which a dwelling has no road to reach. Only the part of a driveway
   inside the property boundary counts, as before.
10. Check for a newer roading layer over the new subdivision off Yabby Creek
    Road (as transcribed), where missing roads make the generated driveways long
    (**T-62**). The same area has no property boundaries or addresses yet
    (**L-41**).
11. Exclude non-residential sites using a land use layer rather than by hand
    (**T-63**); the building use field is too incomplete, so buildings default
    to residential (**L-42**). The zoo was the example. Low priority unless the
    false positives start to show in the costs.

## Validation

- Insured land area per property against the parcel area it sits inside, per
  territorial authority. A distribution that is a plausible share of the section
  is the check that the buffer and the driveway are behaving.
- Count of properties with no building outline, and of buildings with no route
  to a roadway, printed per territorial authority so the joins are auditable
  rather than silently dropping properties.
- Driveway lengths against the sections they cross — a driveway longer than the
  parcel is a routing failure.
- Total modelled insured land value against the published rating valuation
  totals, extending `validations/check_land_value_totals.py` once area is
  measured rather than assumed.

## Open decisions

- **T-07** — the remaining LINZ datasets. **Closed.** Building outlines, roads
  and property boundaries are all read and pinned as named constants.
- **T-25** — the assumed lot size. Mostly closed: rates are divided by the
  measured section, and the assumed lot is left as the fallback and the
  reference for the size factor.
- **L-11** — the claim-level identifier. **Closed.** The claim is the property,
  and `claim_id` is the LINZ property boundary's own source identifier.
- **T-23** — multi-unit, cross-lease and shared-land properties. A block now
  settles as one claim over one piece of ground, carrying the count of the
  address points on it. What is still open is what a rating unit aggregating
  several titles should be: one pilot property takes 205 addresses, and a large
  rural rating unit can swallow a row of houses.
- The gradient above which a generated driveway route is not a credible
  driveway, and what happens to the building when no route below it exists.
- The size of the 2 m premium, which is engineering judgement until the District
  Valuation Roll data lands under **T-20**.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
