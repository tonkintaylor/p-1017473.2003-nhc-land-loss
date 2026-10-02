# Step 7 — Culvert and bridge crossings: implementation plan

**Status:** Phases 1, 1a and 1b complete. Empty over the pilot box, by geography.

## Phase 1 — Crossings of the right shape (complete)

- [x] Pin the LINZ river name polygons layer as a constant and add a reader
      beside `get_nz_river_name_lines`.
- [x] Have step 5 write the driveway corridors out, so the accessway survives as
      its own layer rather than only inside the insured land extent.
- [x] Detect crossings by intersecting the accessways against both river layers,
      recording which layer found each one.
- [x] Draw a culvert or a bridge at each crossing under the project realisation
      seed, and write one file per realisation.

## Phase 1a — Insured crossings with a stable id (complete)

- [x] Read the insured land from step 5 and keep only the crossings wholly
      inside their claim's insured land polygon (`covered_by`), printing the
      counts kept and dropped.
- [x] Mint a `crossing_id` per kept crossing, after sorting by claim and
      location and before the structure draw, so it is the same in every
      realisation. It is split into `culvert_id` and `bridge_id` at vul
      step 10.
- [x] Take `CLAIM_ID_COLUMN` from `landloss.domain.loss_contract`.

## Phase 1b — One row per physical crossing (complete)

- [x] Merge the crossings of one claim that intersect across the two river
      layers, before the coverage filter and the id, so a river found on both
      layers is one crossing, one `crossing_id` and one structure.
- [x] Allow `CROSSING_COVERAGE_TOLERANCE_M` in the `covered_by` test, so a
      crossing sharing the corridor edge with the insured land is not dropped
      for floating-point rounding.

## Phase 2 — Make the population mean something

- [ ] Run over the four territorial authorities. The pilot box holds no named
      watercourse at all, so nothing about the detection has been exercised
      against real crossings yet — only against synthetic geometry in the tests.
- [ ] Add the unnamed streams. Both LINZ layers carry named watercourses only,
      and the small accessway crossings this step exists to find are mostly on
      unnamed ones, so the count is a floor. The topo50 centrelines are the
      obvious source; whether they are needed is the open decision on
      `../../status.md`.
- [ ] Confirm the coverage of both layers over the study area. They are
      published as pilots, so a crossing rate derived from them should not be
      quoted until that is checked.

## Phase 3 — Beyond the generated accessway

- [ ] Re-detect once driveways are routed rather than drawn straight. A crossing
      is currently found where a straight line from the building to the road
      meets water, which is not where a real driveway crosses.

## Potential future improvements

- Replace the 80/20 split with something fitted. The figures are engineering
  judgement and will need disclosing in the report; no register limitation
  covers them yet.
- Carry the width of the watercourse onto the crossing, so a structure's size
  follows the span it has to cross rather than being uniform.
