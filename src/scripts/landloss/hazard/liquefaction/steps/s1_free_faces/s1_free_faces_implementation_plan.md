# Step 1 — Free faces: implementation plan

**Status:** Phase 1 complete and runnable.

## Phase 1 — Rebuild the NLM's free-face layer (complete)

- [x] Read the river name lines and the topo50 river, lake, swamp and lagoon
      polygons and coastline for an extent, through
      `landloss.io.readers.get_nz_topo50_water` and the layer IDs in
      `landloss.domain.constants`, matching the NLM's.
- [x] Keep the named rivers and the extra IDs, the water bodies of at least 5 ha,
      and the coast, with the NLM's `wtype` values (T-46).
- [x] Write one GeoPackage per extent under `temp/hazard/liquefaction/`, and
      print a count and a length or area per type.
- [x] Test the filters without the network:
      `tests/landloss/hazard/liquefaction/test_waterways.py`.

## Phase 2 — Buffers

- [x] Buffer at 100 m and 200 m into lateral spreading zones, and modify the
      probabilities of land damage states 4 to 6 by zone (T-47): done in step 2,
      `landloss.hazard.liquefaction.lateral_spreading`.
- [x] Read every extent 200 m wider than itself, so a free face just outside it
      still counts.

## Phase 3 — Review the layer for Wellington

- [ ] Check whether any watercourse not named a river should be added by ID,
      as the NLM did around Bottle Lake (T-48).
- [ ] Decide whether rock and seawall coast should be excluded, if the
      probabilities underneath turn out not to suppress it.
