# Liquefaction vulnerability, land: status

**Status:** Canterbury observed damage database built, and the cost rates now
price a Wellington realisation end to end.

**Updated:** 2026-10-02

## Approach

- Settle liquefaction land damage from an **observed land damage state**, and
  attach a **cost to each state**, rather than modelling a damage ratio and
  multiplying it by land value. Canterbury gives observed states and settled
  costs for the same properties, which is the strongest evidence the study has.
- Keep **states** and **categories** apart. States are the severity scale, 1 to
  6, None through Very Severe. Categories are the nine damage types NHC pays
  out on, 1 to 9, where 8 is ILV and 9 is IFV. The costs are keyed on states
  and cover categories 1 to 7, so **ILV and IFV costs are excluded**.
- Take the category costs from the **Dec 2016 ILVR land liability rates**,
  packaged under `src/landloss/vul/liquefaction/assets/` as
  `costs_liq_ld_refined_states_2011.csv` with its own README. They are
  2010/2011 dollars excluding GST, carried as 15th, 50th and 85th
  percentiles so the spread within a category survives.
- Calibrate against the **Canterbury earthquake sequence**, joining NHC's
  settled losses to the National Liquefaction Model's mapped land damage
  observations (`steps/s1_ces_observed_damage/`).
- Keep to **flat land**. The Canterbury evidence is flat land liquefaction
  damage, the observed damage database is masked to flat land, and the packaged
  costs carry the same restriction.

Agreed 2026-09-30, so that `vul` hands `loss` what an NHC claim report would
contain -- evacuated and inundated land -- and `loss` does the costing.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [ ] Give each land damage state an **evacuated** (cracked) area and an
  **inundated** (ejecta) area, drawn uniformly within the state's range, from
  the MBIE descriptions of each state (**T-55**, owner Perrie Gilbert):

  | State | Evacuated (m²) | Inundated, share of insured land |
  | --- | --- | --- |
  | 1 None | 0 | 0 |
  | 2 Minor | 1 | 0 |
  | 3 Moderate | 1 | 25% to 70% |
  | 4 Major | 1 to 10 | 30% to 100% |
  | 5 Severe | 10 to 40 | 30% to 100% |
  | 6 Very severe | 40 to 100 | 30% to 100% |

  Evacuated land is an area in m² and inundated land a percentage of the
  insured land (confirmed by Perrie Gilbert, 2026-09-30). Moderate inundation
  was first put at 5% to 25% and revised to 25% to 70% in the same call. All
  the ranges are judgement (**L-39**).
- [ ] Take the **total damaged area** as evacuated plus inundated less a 30%
  overlap between them, and value liquefied land in the land cover cap over
  that rather than over the whole insured area (**T-56**) -- the whole-area
  reading gives caps that are much too high.
- [ ] Set **repair rates** for inundated and evacuated liquefied land, chosen so
  the modelled costs roughly reproduce the Canterbury cost table, and add a
  **no-SVA flag** that raises the inundated rate, since the Canterbury clearing
  costs carry the Student Volunteer Army's unpaid work (**T-57**, **L-40**). The
  Canterbury rates stay for the liquefaction repair cost until the new rates
  replace them.

## Loss contract

What this module owes the land table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Supply `Liq_LD_state` per insured land polygon, written as `ld_state`. A
  property off the liquefaction grid is state 1, None, at no cost.
- [x] Carry `land_id`, `claim_id` and coordinates. The coordinates come from
  the insured-land geometry, on the s10 land table.

## Where it is now

- `steps/s1_ces_observed_damage/gen_observed_damage_db.py` builds the observed
  damage database: one row per insured property per event, over the three
  Canterbury events, masked to flat land. Its method is written up in the step
  folder.
- `report/fig_land_damage_maps.py` maps the observed land damage.
- The category cost rates are packaged as a committed asset with a README
  recording their source, units and limitations, and
  `landloss.vul.liquefaction.costs` reads them.
- `steps/s2_liq_land_damage/` samples the hazard module's realised land damage
  state at every insured property and looks a cost up against it, writing one
  priced row per property per realisation. Over the Wellington pilot, 2,721 of
  4,764 properties carry a state; the remainder sit outside the liquefaction
  grid, which covers flat land as expected, and are written as state 1, None,
  at no cost, with `on_liq_grid` recording which were sampled.
- Step 2 carries a drop-out draw -- which properties on the grid go on to
  claim -- but leaves it off, because the current costs already average over
  non-claimants at $0. Every property on the grid claims at the diluted cost
  until claimant-only rates arrive (**T-65**, **L-43**). With the draw on at
  the placeholder rates, 908 of the pilot's 2,484 properties on the grid
  claimed, all 197 Severe and Very severe among them.
- The percentile is a run-level scenario rather than a column, because
  `min(repair, cap)` is non-linear and a settlement computed from a median cost
  is not the median settlement.

## Next

1. Check the modelled costs against the settled losses already in the observed
   damage database, which is the test of whether the 2016 rates reproduce what
   was actually paid.
2. Escalate the 2010/2011 rates to the study's valuation basis, holding the
   index as a named constant rather than in the asset. `cost_year` rides on
   every row until that lands.
3. Gross the rates up for GST at the loss boundary. They arrive excluding it
   and the Act compares on a GST-inclusive basis.
4. Run all three percentiles and report the portfolio total as a band.
5. Add the evacuated and inundated areas per state (**T-55**), and the damaged
   area the cap is valued over (**T-56**). Maxim Millen is revising the land
   damage states themselves (**T-54**), which is where the two pieces of work
   first meet.
6. Set the inundated and evacuated repair rates against the Canterbury table,
   with the no-SVA flag (**T-57**).
7. Tune the drop-out rates, the share of properties in each state that do not
   claim. Step 2 can draw claims at **placeholder** rates, `DROP_OUT_RATES`
   in its `config.py` -- 95%, 75%, 40% and 15% for None to Major, 0% for
   Severe and Very severe -- and they wait on Virginie Lacrosse's table
   (**T-64**) and her and John Leeves' feedback (**Q-16**). The draw is off
   until her claimant-only costs replace the current ones (**T-65**); her
   counts of damaged properties and claimants per band will validate it.

## Validation

- Modelled category costs against the settled Canterbury losses per property, on
  the same properties. The observed damage database holds both, so this is a
  direct comparison rather than a proxy.
- Distribution of properties across states 1 to 6, against the observed
  distribution in the Canterbury data.

## Tuning parameters

Values the model runs on that are judgement, held in config, and to be adjusted
on feedback rather than derived.

- **Drop-out rate per land damage state**, `DROP_OUT_RATES` in
  `steps/s2_liq_land_damage/config.py`. Placeholders by Perrie Gilbert, Severe
  and Very severe fixed at 0%; feedback from Virginie Lacrosse and/or John
  Leeves (**T-64**, **Q-16**). Not applied until the costs are claimant-only
  (**T-65**).

## Open decisions

- **The drop-out and the costs have to be on one basis.** The current
  Canterbury costs include non-claimants at $0 (**Q-17**, closed), so the
  drop-out stays off against them. Once claimant-only costs arrive (**T-65**)
  it comes on, and the T-57 repair rates are to be calibrated against
  claimants only, to match.

- **Whether retaining walls are handled explicitly or left inside the land
  damage cost.** The Canterbury rates may already include retaining wall,
  culvert and bridge damage, in which case modelling those assets separately
  would double count them. **T-27** covers confirming it, and the answer decides
  whether this module needs a retaining wall term at all.
- **How ILV and IFV are covered.** The packaged rates exclude both, and they
  were a large share of what was paid in Canterbury, so a total built from
  these rates alone understates the loss.
- **T-17**, **T-18** — NHC land damage claim costs for Wellington, which would
  let the Canterbury-derived rates be checked against a second population.
- The source description for the ILVR rates is still to be supplied by Virginie
  Lacrosse and added to the asset README.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
