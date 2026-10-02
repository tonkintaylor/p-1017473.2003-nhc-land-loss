# Step 9 — Culvert and bridge damage state: implementation plan

**Status:** Phases 1 and 1a complete, but unexercised — the pilot holds no crossings.

## Phase 1 — A damage state on every structure (complete)

- [x] Read the crossing population and the realisation's PGA field.
- [x] Sample PGA at each structure and carry it onto the output.
- [x] Draw no damage or replace against a failure probability.
- [x] Carry the kind of structure through as the asset, so the loss module can
      price a culvert and a bridge differently under their shared sub-cap.
- [x] Seed the draw from the realisation's vulnerability stream.
- [x] Report an empty population as a coverage fact rather than a blank table.

## Phase 1a — Ids and geometry for the loss contract (complete)

- [x] Carry `crossing_id` and `claim_id` from step 7 on every row, so vul
      step 10 can split the table into culverts and bridges by id.
- [x] Carry each structure's geometry and write GeoParquet, so the loss tables
      get their coordinates.
- [x] Sample PGA at `representative_point()` rather than the line midpoint,
      because the coverage filter can pass polygons and geometry collections.
- [x] Write an empty GeoDataFrame with the full columns and CRS when the
      population is empty.
- [ ] Re-run over real data after exposure steps 5 and 7 are re-run.

## Phase 2 — A population worth running over

- [ ] Run over the full study area, where the named watercourse layers do
      produce crossings. The pilot box contains none, so nothing here has been
      exercised against real rows.
- [ ] Widen the population beyond named watercourses. Most private crossings
      are over unnamed drains and gullies, which is most of what is missing.

## Phase 3 — A real fragility

- [ ] Define separate fragility curves for culverts and bridges. They fail
      differently and the flat 70% treats them as one.
- [ ] Index the curve on span, material and age once the population carries
      them.

## Potential future improvements

- Let a landslide take out a crossing, which in the hill suburbs is the more
  likely cause than shaking alone.
- Model the access consequence. A written-off crossing can strand a property
  whose land is otherwise undamaged, which the current chain cannot express.
