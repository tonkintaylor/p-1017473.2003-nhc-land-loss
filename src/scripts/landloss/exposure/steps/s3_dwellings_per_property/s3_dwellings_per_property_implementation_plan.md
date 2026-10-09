# Step 3 — Dwellings per property: implementation plan

**Status:** Phase 1 complete. A dwelling is an address point.

The step is numbered `s3` because step numbers run across the `exposure` module
rather than across one `steps/` folder. `s1` is the address spine, also at
module level, and `s2` is the land value under `land/`.

## Phase 1 — Count the address points (complete)

- [x] Reduce the LINZ property boundaries to claim properties, dropping road
      and water parcels and dissolving titles stacked on one footprint.
- [x] Count the address points standing inside each property.
- [x] Write the count per property and the address-to-claim mapping behind it.
- [x] Carry the title type and the property area, so the count can be read
      against what kind of property produced it.

## Phase 2 — A dwelling that is a dwelling

- [ ] Separate residential addresses from commercial ones, which currently
      count as dwellings on a mixed-use property.
- [ ] Recover minor dwellings that were never separately addressed, which the
      count misses entirely.
- [ ] Decide what a property with several addresses and one building is. A
      rating unit aggregating several titles takes every address inside it, and
      738 of the pilot's 962 multi-dwelling properties are freehold rather than
      unit-titled.

## Phase 3 — Reconcile against an external count

- [ ] Compare the dwelling count against the District Valuation Roll, which
      records dwellings per rating unit directly (**T-20**).
- [ ] Compare against the census dwelling counts by meshblock, as a second
      check at an aggregate level.

## Potential future improvements

- Report the count per territorial authority, so a systematic difference
  between the four is visible before it reaches the loss table.
- Carry the count of *addressable* buildings alongside it, once the outline
  layer's `use` column is populated well enough to tell a dwelling from a shed.
