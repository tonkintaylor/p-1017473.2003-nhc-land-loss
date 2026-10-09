# Step 3 — Dwellings per property: method

- The step counts the **dwellings on every claim property**, which is the
  multiplier NHC applies to both sub-caps and to the excess, and so is what sets
  the retaining wall cap. It is run by `gen_dwellings_per_property.py`.
- It sits at **module level** rather than under `land/` because every asset
  class needs it: a retaining wall's sub-cap is per dwelling on the property it
  stands on, and so is a bridge's.
- Claim properties come from `landloss.exposure.land.extent.build_claim_properties`,
  which reads the LINZ property boundaries, drops the road and water parcels,
  and dissolves boundaries with identical geometry so a unit-titled block is one
  claim rather than one claim per unit.
- **A dwelling is an address point standing inside the property**, counted by
  `landloss.exposure.land.extent.count_dwellings`. An address falling inside two
  overlapping properties is counted once, in the lower claim identifier, so the
  portfolio total adds up.
- **A dwelling here is an address point, not a self-contained dwelling.** LINZ
  gives each unit of a block its own address, which is what makes the count work
  for flats, but it also gives one to a commercial tenancy and gives none to a
  minor dwelling that was never separately addressed. The count is a floor on a
  block and an over-count on a mixed-use building.
- Two files are written under `temp/exposure/`:
  - `dwellings-per-property[-pilot].parquet` — one row per property with at
    least one dwelling, carrying `claim_id`, `dwelling_count`,
    `property_area_m2`, `boundary_rows` and `title_type`.
  - `address-to-claim[-pilot].parquet` — the address-to-claim rows behind the
    count. It exists because everything upstream is keyed on an address and
    everything downstream on a claim, and without the mapping the two cannot be
    reconciled.
- Over the Wellington pilot: 8,591 addresses over 7,498 claim properties, of
  which 4,494 carry at least one dwelling. The median property has one dwelling,
  the 99th percentile has 14 and the largest has 205. Of the 962 properties with
  more than one dwelling, 738 are freehold — a rating unit that aggregates
  several titles, not only unit-titled blocks.

Potential future improvements see
`s3_dwellings_per_property_implementation_plan.md`.
