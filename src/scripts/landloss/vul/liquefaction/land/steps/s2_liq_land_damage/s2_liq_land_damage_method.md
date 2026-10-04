# Step 2 — Liquefaction land damage: method

- The step puts a **land damage state and a repair cost on every insured
  property**, and writes one row per property per realisation for the loss
  module to settle. It is run by `gen_liq_land_damage.py`.
- Properties come from `temp/exposure/insured-land[-pilot].geoparquet`, the
  layer step 5 writes, read through its own `insured_land_path()`.
- The damage state comes from the hazard module's realised state raster,
  `ld_state_path()`, sampled at each property's **representative point** with
  `landloss.common.utils.terrain.sample_at_points`. A property therefore carries
  one state rather than a mixture of the states under it.
- **A property outside the grid has damage state N/A, at no cost.** The
  liquefaction model covers flat land, as expected, so over the Wellington pilot
  roughly two properties in five sit off it. Off the grid is ground that cannot
  liquefy, so it has no liquefaction damage state at all: `ld_state` is null
  (a nullable integer column) and `state_name` is `OFF_GRID_STATE_NAME`, "N/A",
  in `gen_liq_land_damage.py`. It is deliberately not state 1, None, which is
  surveyed flat land showing no damage and carries a Canterbury cost. The null
  state passes through to `Liq_LD_state` in the land table, which the loss
  module reads as not liquefied. `on_liq_grid` records which properties were
  sampled, and the run prints the split.
- **Not every damaged property claims.** Each property on the grid draws, once
  per realisation, whether its owner makes a land claim, at the **drop-out
  rate** for its state: the share of properties in that state that do not
  claim. `landloss.vul.liquefaction.drop_out.draw_claims` makes the draw, from
  its own seeded stream, `liquefaction_claims`, so it is reproducible and
  independent of the wall and crossing draws. `liq_claimed` records it.
  - A property that drops out keeps the hazard's state in `hazard_ld_state`,
    but `ld_state` is null and the cost is zero, so the loss module reads it as
    it reads land off the grid: no liquefaction claim, and no damaged area in
    the cap. `state_name` names the hazard state.
  - It is a draw, not a weight. Scaling each cost by its claim rate gives the
    same expected repair cost, but the excess and `min(repair, cap)` are
    non-linear, so it would get the settlement wrong.
  - **The rates are placeholders and a tuning parameter**, `DROP_OUT_RATES` in
    `config.py`: 95%, 75%, 40% and 15% for None to Major, 0% for Severe and
    Very severe, which are always claimed. They await Virginie Lacrosse's
    table (**T-64**) and feedback from her and John Leeves (**Q-16**).
  - **The draw is off for now.** The packaged Canterbury costs average over
    every damaged property, non-claimants at $0 (**Q-17**), so the drop-out is
    already inside them. `COSTS_INCLUDE_NON_CLAIMANTS` in
    `landloss.vul.liquefaction.costs` records that, and while it is True every
    property on the grid claims at the diluted cost. Replacing the CSV with
    claimant-only rates and setting it False switches the draw on (**T-65**).
    In the meantime many small costs meet the excess where a few full ones
    would, so settlements come out somewhat low (**L-43**).
- **Each claim carries the ground it lost** (**T-55**): an evacuated area in
  m² -- cracked or spread -- and an inundated area under ejecta, drawn
  uniformly within its state's ranges by
  `landloss.vul.liquefaction.damaged_area.draw_damaged_areas`, from a stream of
  their own, `liquefaction_areas`, so switching the drop-out on does not move
  them.
  - Evacuated is drawn in m², because cracking is a few metres whatever the
    section's size; inundated is drawn as a share and multiplied by the insured
    area, because ejecta spreads over a fraction of it. Each is capped at the
    insured area. They may sum to more than it, since they overlap.
  - **The damaged area counts the overlap once** (**T-56**):
    `damaged_area_m2` is evacuated plus inundated less
    `EVACUATED_OVERLAP_SHARE` of the evacuated -- 30%, but no more than the
    inundated land -- capped at the insured area, by
    `landloss.vul.liquefaction.damaged_area.liquefied_area_m2`. A property
    wholly inundated and evacuated is damaged over its insured land and no
    more. The share is an assumption to be verified (**L-44**). The land table
    carries it to `loss` as `Liq_LD_damaged_area`, which values the land cover
    cap over it.
  - Both are zero wherever `ld_state` is null -- off the grid, or dropped out.
  - The ranges, `EVACUATED_AREA_M2` and `INUNDATED_SHARE` in `config.py`, are
    judgement from the MBIE state descriptions (**L-39**), to be tuned with the
    repair rates (**T-57**).
- **Each claim is also priced from its ground lost** (**T-57**), as
  `area_cost_nzd`: `REPAIR_RATES` in `config.py` per m² of inundated and of
  evacuated land plus a fixed cost per claim, fitted to the Canterbury means by
  step 3. Setting `NO_SVA` raises the inundated rate by
  `NO_SVA_INUNDATED_MULTIPLIER`, a placeholder (**Q-18**), for clearing ejecta
  without the Student Volunteer Army (**L-40**). It is zero where there is no
  claim. **The loss module still settles on `cost_nzd`, the lookup**;
  `area_cost_nzd` rides beside it until it is chosen to replace it.
- Costs are looked up, not modelled, by `landloss.vul.liquefaction.costs`. They
  are what NHC settled for land damage after the 2010 and 2011 Canterbury
  earthquakes, grouped by the damage state surveyed on the ground, and shipped
  in `costs_liq_ld_refined_states_2011.csv` beside that module.
- **The rates are a cost per property, not per square metre**, which is what
  `rate_basis = "per_property"` on every row records. An area never multiplies
  them: a property assessed at Moderate cost what it cost, whatever its size.
  Insured area and the GST-inclusive land rate ride along as columns because the loss module needs
  them for the market value side of the cap, not because the repair cost uses
  them.
- **The percentile is a run-level scenario**, set by `COST_PERCENTILE` in
  `config.py` and carried onto every row. The 15th, 50th and 85th are the spread
  of settled costs *between* Canterbury properties assessed at the same state,
  not a confidence interval, and the 85th runs two to four times the median. The
  model is run once per value because `min(repair, cap)` is non-linear.
- **States 5 and 6 carry identical costs**, both read from the source band
  "5 or 6", so the severe end rests on one estimate rather than two.
- The money is **2011 dollars excluding GST**, recorded in `cost_year` on every
  row because land values are indexed to a different date and the loss module
  compares the two.
- **Each row is keyed on `land_id` and `claim_id`**, both read from the insured
  land. `land_id` is minted at exposure step 5 and follows `realisation_id` as
  the first column; the names are imported from `landloss.domain.loss_contract`.
- Output is `temp/vul/liq-land-damage-r<nnn>[-pilot].parquet`, a plain parquet
  with **no geometry**. The coordinates on the land table are supplied at
  `vul/steps/s10_property_damage` from the insured-land geometry, joined on
  `land_id`.

Potential future improvements see
`s2_liq_land_damage_implementation_plan.md`.
