# Asset pricing and settlement approach

How every insured asset is priced against every hazard, and how those prices
become a settlement. This is the plan for the `loss` module, and it is what
**T-34** asks to be run past John Leeves.

Marks: **[confirmed]** is settled by a source in the repository, named at the
point of use. **[proposed]** is this document's suggestion and needs a decision.

Two sources carry most of the weight, and they do not agree with each other in
every place:

- `.agents/context/nhi-act-land-cover-explainer.md` — the Act's own mechanics,
  from Bridget Attwood at NHC. **Authoritative.** Where it conflicts with the
  team's working understanding, it wins.
- `.agents/context/nhc-costing-tool.md` — how NHC actually prices a repair,
  from Chris Ewens. Authoritative on the cost build-up, silent on policy.

## 1. What `loss` receives

**[confirmed]** — the `vul` output contract, set by Maxim Millen on 2026-09-23.
It supersedes the earlier sketch in `.agents/plans/beta-build.md`, which had one
land frame keyed on `address_id` with a row per cause.

`vul` hands over **four tables**, not one frame. Every table carries `claim_id`
and coordinates; each also carries its own asset identifier.

**Land** — one row per insured land polygon, the polygons being non-overlapping,
so a claim's areas can be summed without double counting.

| Column | What it is |
| --- | --- |
| `land_id` | The polygon |
| `claim_id` | The claim it belongs to |
| `Liq_LD_state` | The liquefaction land damage state |
| `Liq_LD_damaged_area` | Insured area damaged by liquefaction: evacuated plus inundated less their overlap, no more than the polygon. Added 2026-10-02 (**T-56**), beyond the contract as confirmed |
| `total_insured_land_area` | The whole insured area of the polygon |
| `land_slide_total_insured_land_area` | Insured area taken by landslide |
| `inundated_insured_area` | Insured area buried by material coming to rest |
| `inundated_mean_depth` | How deep that material lies |
| `evacuated_area` | Area the material came from |
| `footprint_area` | The claim's building footprint. Added 2026-10-11 |
| `property_area` | The whole claim property. Added 2026-10-11 |
| `land_slide_footprint_area` | Landslide ground under the footprint. Added 2026-10-11 |
| `suburb` | The suburb the claim's addresses mostly stand in. Added 2026-10-11 |

No land value: since 2026-10-11 `loss` values damaged land itself, from each
property's QV land value in three tiers (`landloss.loss.qv_land_value`,
`src/scripts/landloss/loss/qv_land_value_method.md`). It replaces the
contract's `$/m2 market value`.

**Retaining walls** — one row per insured wall: `rw_id`, `claim_id`, `rw_size`
(small, medium or large), `rw_length`, and three damage flags,
`is_damaged_by_shaking`, `is_evacuated`, `is_inundated`.

**Culverts** — `culvert_id`, `claim_id`, `is_inundated`, `is_damaged`.

**Bridges** — `bridge_id`, `claim_id`, `is_damaged_by_shaking`, `is_evacuated`,
`is_inundated`. The identifier was absent from the contract as first written and
was confirmed on 2026-09-23 as belonging there, so every table identifies its
own asset.

Four consequences, in the order they bite:

- **`claim_id` arrives from upstream.** It is not minted at this boundary, which
  is what the earlier contract had and what **L-11** was written against. `loss`
  aggregates four tables onto a key it is given rather than creating one.
- **Every dollar attached to a structure is `loss`'s to compute.** `vul` hands
  over a verdict, not a price — and now a verdict per cause rather than a single
  damage state. Since a damaged structure is replaced rather than repaired, any
  flag being true means one replacement, not one per flag.
- **Land arrives half-priced**, as an area and a market rate, so `loss` still
  produces the repair cost. Because the rate and the area arrive separately, the
  Act's area cap can finally be applied — it is the lesser of the damaged area
  and the cap that is valued, and a pre-multiplied market value would have
  thrown away the area the cap needs.
- **Damage is decomposed by mechanism, in named columns rather than rows per
  cause.** `vul` supplies `land_slide_total_insured_land_area` as the union of
  the evacuated and inundated footprints, as
  `.agents/context/nhc-land-cover-and-settlement.md` requires (vul step 3,
  `landslide_area_m2`), so `loss` need not take that union itself (**Q-06**).

Four things the contract does not carry, each of which `loss` needs:

- **No dwelling count.** Both sub-caps and the excess multiply by dwellings in
  the residential building, and nothing in the four tables supplies one
  (**Q-07**).
- **No wall height.** The rates are charged per square metre of wall face, which
  is retained height by length; `rw_length` arrives and `rw_size` is a band, so
  `loss` turns a size class into a height. Settled for now as **set values** of
  0.75 m, 1.75 m and 2.75 m — see section 1.1.
- **No `cost_year` or `rate_basis`.** The earlier contract carried both. Their
  absence reads as every rate being stated at one cost year, which is worth
  confirming before a rate from a different year is mixed in.

Bridges and culverts are also described asymmetrically — culverts carry a
generic `is_damaged` and no `is_evacuated`, bridges carry `is_damaged_by_shaking`
and do have `is_evacuated`. Whether that is deliberate is **Q-09**.

### 1.1 Turning a wall size class into a height **[confirmed]**

`vul` sends `rw_size` and `rw_length`; the rate is charged on wall face, so a
band has to become a height. The agreed first cut is a **set value per class**:

`beta_population` draws heights over 0.4 to 3.0 m, so a class holds its band
clipped to that range, and each set height is the middle of what its class can
actually contain:

| Class | Band | Realised range | Priced at |
| --- | --- | --- | --- |
| small | below 1 m | 0.4 to 1.0 m | **0.75 m** |
| medium | 1 to 2.5 m | 1.0 to 2.5 m | **1.75 m** |
| large | 2.5 m and above | 2.5 to 3.0 m | **2.75 m** |

The three land a clean metre apart, and each classifies back to its own size
class — which is what rules out pricing small at 1 m, since the band is *below*
1 m and `classify_wall_size` reads 1 m as medium. A test asserts that round
trip, so this mapping and those bands cannot drift apart unnoticed.

What follows is that a size class carries **no variation of its own**: every
medium wall in the study is 1.75 m, so the spread in wall cost across the
portfolio comes from length and the site ratings alone. Drawing a height within
the band, or setting it off the slope the wall sits on, would add that variation
back. Deferred as **I-14**.

### 1.2 The site multiplier applies to wall construction only **[confirmed]**

The allowance for construction access, earthworks required, and constructability
and reinstatement goes on the **wall construction subtotal** — the square metre
rate by the wall face area — and on nothing else. It does not reach inundation
removal, land reinstatement, or any other line of the scope of works.

`nhc-costing-tool.md` records Chris Ewens describing the multipliers as applying
to the Land SOW subtotal, which is the broader reading. The narrower scope is the
decision for this study, and `landloss.loss.pricing` implements it.

Two things follow:

- **The ratings are per wall, not per claim.** A markup on one wall's
  construction cannot be a claim-level figure, so the three belong beside
  `rw_size` and `rw_length` on the retaining wall table.
- **The `vul` contract does not carry them** (**Q-10**). `SiteRatings` is a
  required argument with no default, so no wall can be priced until they arrive
  — the same hard stop the dwelling count creates for `settle`.

They are not a lookup. For a real claim the three come from a table in the duty
geotechnical report, and at NHC's scale from flyover or satellite imagery;
neither exists for a synthetic population, so for this study they have to be
inferred, as wall prevalence and height are. The inputs are already held in
`exposure`: slope drives earthworks and constructability, and
`landloss.exposure.land.driveways` computes the building-to-road path that
construction access turns on.

## 2. The settlement calculation

**[confirmed]** — `nhi-act-land-cover-explainer.md`, with three worked examples.
This is the spine; the pricing sections below exist to feed it.

- A **land cover cap** is assembled per residential building:

  ```text
  land_cover_cap = market_value(damaged insured land areas)
                 + min(udv_retaining_walls,  n_dwellings x $50,000 + GST)
                 + min(udv_bridges_culverts, n_dwellings x $25,000 + GST)
  ```

- **Entitlement = the lesser of the total repair cost and the land cover cap**,
  less the excess.
- **Excess** is $500 per dwelling, capped at $5,000.
- The multiplier is the **number of dwellings in the residential building** —
  not the number of walls, not the number of owners.
- **Two residential buildings on a site means two caps**, worked out separately.
  An appurtenant structure (garage, shed) extends the insured footprint but adds
  no cap.
- Undamaged and uninsured structures are excluded from the calculation.

Three things follow that the model has to get right:

- **The sub-cap is not the wall's contribution.** The contribution is the
  *lesser* of undepreciated value and the sub-cap. A modest timber pole wall
  with a $30,000 undepreciated value contributes $30,000, and the $57,500 limit
  never binds (explainer, Example 3).
- **"Value or repair, not both" is looser than the Act.** The team's working
  note describes an election; the Act describes `min(repair, cap)` where the cap
  is *built from* market value. **[proposed]** implement the Act's arithmetic and
  treat the election language as shorthand for it. Worth confirming with John,
  because it changes what a claim settles at whenever repair cost sits between
  market value and the cap.
- **Land is insured on an indemnity basis**, not replacement. Market value is
  the *prior* value — immediately before the damage, at the date of loss.

### Area cap on the land valued

- Area cap = **the lesser of the district plan minimum area and 4,000 m²**; with
  no district plan minimum it is 4,000 m².
- Damaged area ≤ area cap → value the actual damaged area.
- Damaged area > area cap → value a hypothetical area **equal to the area cap**,
  in the same place with the same features.
- **[proposed]** hold the four territorial authorities' district plan minimum
  lot sizes as a constant table. Nothing in the repository carries them yet.

## 3. The two costings for a land structure

**[confirmed]** — the explainer is explicit, and it is what Chris was describing
from the other side.

Every damaged wall, culvert and bridge needs **both** numbers. They are not
alternatives:

| | Reinstatement / repair cost (SOW) | Undepreciated value (UDV) |
| --- | --- | --- |
| Question | What will it cost to fix? | What would it have cost to build new? |
| Scope | The real remedial solution | The whole insured structure, even if only part is damaged |
| Age | n/a | No deduction for age |
| Includes | Demolition, enabling works, site access, compliance with current standards | **None of those** |
| Feeds | The repair-cost side of `min(repair, cap)` | The cap, via `min(udv, sub-cap)` |

- This is exactly why Chris said under-depreciated value comes out lower than
  the Land SOW, and it settles that question: the gap is the excluded items, not
  depreciation.
- **[proposed]** carry `repair_cost_nzd` and `udv_nzd` as separate columns on
  every structure row. A single "wall cost" cannot serve both sides.
- **Note the asymmetry**: UDV is costed across the *whole insured wall* even
  where only part failed. Since `vul` emits a binary `replace` per wall, the
  beta gets this right by construction — but if a partial-damage state is ever
  added, UDV must not follow it down.

### 3.1 Both numbers come off the same rate **[confirmed]**

Confirmed against the costing spreadsheet on 2026-09-23: **the tool uses the
same square-metre rates for undepreciated value as for the Land SOW.** So:

```text
repair cost = m2 rate x wall face area x (1 + site multiplier)
udv         = m2 rate x wall face area
```

The site allowance is the whole of the difference. Access, earthworks and
constructability are what it costs to work on this particular site; they are not
part of what the wall cost to build, so they have no place in UDV.

This settles an earlier misreading in this file. Chris Ewens's "set fees for
under-depreciated value" and UDV being "without the additional items the
square-metre rates build into the Land SOW" do **not** mean a separate rate
table. They mean UDV is the wall rate alone, without the other Land SOW lines
that sit beside it — inundation removal, enabling works, reinstatement, the
compliance items — and without the site multiplier.

Two consequences:

- **Repair cost can never come out below UDV**, the multiplier never being
  negative. That is the direction Chris said the two run, but here it holds by
  construction, so it is a check on the arithmetic rather than evidence the gap
  is the right size.
- **No age or condition enters UDV.** Undepreciated means no deduction for age,
  so a twenty-year-old wall and a new one of the same construction and size are
  worth the same, and `initial_condition` has no bearing on it.

The remaining limitation is specification, not rates (**L-34**). One rate for
both assumes the replacement matches the wall that failed, where in practice a
failed wall is often rebuilt to a more substantial current standard — which
would want a higher rate on the repair side. The bias has a known direction:
settlement is `min(repair, cap) − excess`, so understating repair cost can only
lower a settlement or leave it at the cap, meaning the study **under-reports
NHC's liability** rather than over-reporting it. The same-rate approach is the
agreed basis meanwhile.

## 4. The pricing matrix

| Asset | Liquefaction | Landslide | Shaking |
| --- | --- | --- | --- |
| **Land** | `ld_state` → cost per property | Evacuated + inundated area → repair scheme | — none |
| **Retaining walls** | Deferred (**T-27**) | Loss of support → `replace` **[proposed]** | Fragility → `replace` **[confirmed]** |
| **Culverts, bridges** | Deferred (**T-27**) | Runout or washout → `replace` **[proposed]** | Fragility → `replace` **[confirmed]** |

Three of the nine cells are empty or deferred, deliberately:

- **Land × shaking** — shaking does not damage land directly. It reaches land
  through liquefaction and landslide, both of which are modelled as their own
  hazards. Leaving this blank is a decision, not an omission.
- **Structures × liquefaction** — settlement and lateral spread do fail walls,
  but the Canterbury land rates may already carry wall, culvert and bridge
  damage inside the per-property figure (**T-27**). **[proposed]** leave these
  cells empty until T-27 closes, because adding them now risks double counting
  the same damage. Reopen the moment the answer arrives.

### 4.1 Land × liquefaction **[confirmed]**

Source: `src/scripts/landloss/vul/liquefaction/land/status.md` and the packaged
asset's README.

- **Damage measure** — `ld_state` 1–6, one value sampled per address.
- **Quantity** — **one per property.** The packaged rates are a cost per
  property per state, not a rate per square metre.
- **Rate** — `costs_liq_ld_refined_states_2011.csv`, 15th / 50th / 85th
  percentiles, 2010/2011 NZD, **excluding GST**.
- **The percentile is a run-level parameter, not a column.** See section 5.1;
  the whole model runs once per percentile rather than carrying three costs down
  every row.
- **Escalate** 2010/2011 dollars to the study's valuation basis (**L-23**),
  with the index as a named constant.
- **States 5 and 6 carry identical costs**, both read from the source band
  "5 or 6". They are one estimate wearing two hats, not two independent ones, so
  the spread at the severe end is thinner evidence than it looks.
- **Flat land only.** These rates must not be applied to hill land or to
  landslide damage.
- **Excludes ILV and IFV** (**L-25**), both of which were large in Canterbury,
  so a total built from this file alone understates what was paid.

> **Discrepancy to resolve.** `beta-build.md` prices this cell as "Dec 2016 ILVR
> rate per m²" applied to "whole insured area". The packaged asset is a flat
> cost per property. One of the two has to change — **[proposed]** the asset is
> right and the beta-build row should read "cost per property".

### 4.2 Land × landslide **[proposed]**

Source: `src/scripts/landloss/vul/landslide/land/status.md`.

- **Damage measure** — evacuated area and inundated area within the insured land
  polygon, kept **separately**, each carrying its parent landslide's depth from
  `V = αA^γ` (γ ≈ 1.46, Massey et al. 2020).
- **Quantity** — the **union** of the two footprints, not their sum. Where
  evacuated and inundated ground overlap, that ground is damaged once.
  Inundated polygons may also overlap each other, so they must be dissolved
  before area is summed or a property under two landslides is charged twice.
- **Evacuated ground** — priced from the T+T landslip remediation schedule
  (`EQCcostestimatesRev10.xlsx` Rev 10, 4 December 2023), sizing the works from
  geometry: wall face area from crown length × scarp height, spoil and backfill
  volume from slip volume.
- **Inundated ground** — two rates per m², one for volumes a shovel and truck
  can clear and one for volumes needing an excavator, varied by access
  (**L-28**).
- **Select the repair scheme as the cheapest feasible** for the retained height
  and slope, so the scheme is a checkable output rather than an input.
- **Per-job items** — survey, geotechnical investigation, consents, inspections
  — apply **once per landslide** and are apportioned across the claims it
  crosses. Charged per claim they would dominate every small slip.
- For the largest landslides the cost exceeds the cap regardless, so precision
  stops paying for itself.

### 4.3 Retaining walls × shaking **[confirmed]**

Source: `src/scripts/landloss/exposure/rw/status.md`.

- **Damage measure** — `no damage` or `replace`, from a fragility curve keyed on
  wall class × size subclass × initial condition, against PGA.
- **Size subclasses** — small below 1 m, medium 1 to 2.5 m, large above 2.5 m.
- **Initial condition** — modern or poor, proxied from dwelling age.
- **Quantity** — one wall.
- **Rate basis** — **[proposed]** square metres of wall face (length × height)
  using the costing tool's *simple* calculator, which the team agreed to use
  over the detailed build-up. This bears directly on **T-32**, which asks
  whether cost scales with length or height: a face-area rate says **both**, and
  `beta-build.md`'s "cost per metre × wall length" quietly drops height. Flag it
  rather than letting the two documents diverge.
- **Add on top of the base rate**: enabling works and reinstatement (**Q-03**),
  excess earthworks and constructability (**Q-04**), and the compliance items —
  council stormwater connection and fall-from-height barrier (**Q-05**).
- **UDV excludes every one of those add-ons.** Same wall, two very different
  numbers. See section 3.
- Partial repair is not modelled; John put it at about 1% of cases (**L-31**).
- Walls qualify within **60 m** of the building, not 8 m, where necessary to
  support or protect the building or the insured land areas.

### 4.4 Retaining walls × landslide **[proposed]**

Nothing in the repository covers this cell, and it is a real gap:

- A wall standing in ground that has evacuated has lost its support and is gone,
  whatever the shaking did to it.
- **[proposed]** a wall whose line intersects an evacuated polygon is `replace`,
  independent of its shaking fragility. A wall under an inundated polygon is
  **[proposed]** also `replace`, since it is buried and would be rebuilt.
- Resolve to a **single** `replace` per wall per realisation. A wall failed by
  both shaking and landslide is one wall and one replacement.
- This needs a decision from Maxim: it is `vul`'s to emit, not `loss`'s to
  infer, so if it is wanted the landslide-to-wall path has to exist upstream.

### 4.5 Culverts and bridges × shaking **[confirmed]**

Source: `src/scripts/landloss/exposure/culverts_bridges/status.md`.

- **Damage measure** — `no damage` or `replace`, no intermediate state. John's
  reasoning: almost every bridge caps out anyway, and there are few enough that
  the choice barely moves the total.
- **Quantity** — one per structure. 80% of crossings are culverts, 20% bridges,
  sampled per realisation under a fixed seed.
- **Coverage filter, applied before any costing** — the **whole structure** must
  qualify. A bridge partly beyond 8 m is not insured unless it qualifies via the
  access way route, and a bridge with one abutment outside the property is not
  covered at all. Structures failing this test cost nothing.
- **Rate** — replacement cost per structure. Not packaged; **[proposed]** two
  flat figures, one per structure type, from the costing tool's `lists` sheet
  when it arrives (**T-38**).
- **T-36** — fragility curves for bridges and culverts are not obtained, so the
  `no damage` / `replace` split has nothing behind it yet.

### 4.6 Culverts and bridges × landslide **[proposed]**

- A culvert buried by runout or a bridge taken out by a slip is `replace`, on
  the same logic as 4.4.
- **[proposed]** structure intersects an evacuated or inundated polygon →
  `replace`, resolved to one replacement per structure per realisation.

## 5. Cost uncertainty and GST

### 5.1 The cost percentiles are a scenario, not a distribution

`costs_liq_ld_refined_states_2011.csv` carries a 15th, 50th and 85th percentile
for every land damage state. They are the spread of **actual settled costs
between Canterbury properties assessed at the same state** — not a confidence
interval on an estimate.

- The spread is large enough to dominate the result: the 85th percentile runs
  between **2 and 4 times the median** depending on the state, so the choice
  moves the liquefaction land component by more than most of the modelling
  decisions in this document.
- **The percentile cannot be applied after the caps.** `min(repair, cap)` is
  non-linear, so a settlement computed from a median cost is not the median
  settlement. Cost varies first; the cap truncates second. This is the reason
  `vul/liquefaction/land/status.md` insists the uncertainty reaches `loss`
  rather than being collapsed upstream.
- **[proposed]** carry the percentile as a **run-level parameter**: one scalar
  in the run configuration, the whole model run once per value, three portfolio
  totals reported as a cost-assumption band.
- The alternative — a `cost_percentile` column on every row — buys nothing here.
  Percentiles exist for **one of the nine cells** in section 4. Landslide land
  interpolates between the remediation schedule's easy and difficult columns,
  which is site difficulty rather than a cost distribution, and the structure
  costs carry no packaged uncertainty at all. The column would be null or
  meaningless nearly everywhere.

Two things to be careful of when the results are written up:

- **Running every property at the 85th percentile does not give the 85th
  percentile of the portfolio total.** It assumes every property errs high
  together. Report it as a systematic cost assumption, not a probabilistic
  bound, or it will be read as one.
- **Drawing each property independently is the opposite error.** The portfolio
  total would converge to a narrow band by the central limit theorem and imply
  precision the data does not support, because real costs correlate — the same
  contractors, the same ground conditions, the same assessors.

### 5.2 GST and cost basis

Every input arrives on a different basis, and the Act mixes them:

| Input | Basis |
| --- | --- |
| Canterbury liquefaction land costs | 2010/2011 NZD, **excluding** GST |
| Market value of damaged land | **Including** GST, at the date of loss |
| Retaining wall sub-cap | $50,000 **+ GST** per dwelling |
| Bridge and culvert sub-cap | $25,000 **+ GST** per dwelling |

- **[proposed]** hold every intermediate quantity **excluding GST**, with a
  single GST rate as a named constant, and convert at the points the Act
  specifies. Market value is the one input that has to be *de*-grossed on the
  way in.
- Escalate the Canterbury rates to the study's valuation basis before anything
  is compared with a present-day market value (**L-23**).
- If results are ever presented excluding GST, say so explicitly to NHC
  (**L-24**).

## 6. Imminent risk

**[confirmed]** that it is in scope — the Act counts imminent damage as damage,
and NHC are considering removing the provision under a land cap, so the study
has to be able to quantify what removing it does.

- The test is that a natural hazard has occurred and the loss is **more likely
  than not to occur within 12 months**, assuming normal weather and no
  remediation of the original damage.
- Entitlement must factor in **either** the cost to prevent the imminent damage
  (mitigation) **or** the cost to repair it once it occurs (future
  reinstatement). **[proposed]** take the lesser of the two, consistent with how
  the rest of the settlement resolves.
- Three forms, all following the evacuated/inundated principle: imminent damage
  of **evacuation**, of **inundation**, and of **re-inundation**.
- **[proposed]** carry it as its own `cause` value on every row it generates, so
  the whole of it can be switched off with a filter and the policy comparison
  becomes a single re-run. This is the headline number NHC has asked for; it
  should not require a code change to produce.
- Extent for evacuation comes from a general rule, not a model — the working
  suggestion is that the scarp regresses another half a metre on average, or a
  metre on slopes steeper than 30°, to be agreed (**T-44**).
- Price it at the baseline evacuated and inundated rates to start, while noting
  that the one NHC report the team has read needed an excavator to peel back a
  head scarp, which suggests imminent risk costs *more* than damage that has
  already happened.

## 7. Metrics and plots

What the module should produce, beyond the settlement table. Everything is per
realisation unless it says otherwise.

**Answering the policy question** — these are what the study is for:

- **Portfolio total against total cap**, swept across the range of total cap
  values under test. This is the single most useful output: one curve, the
  policy dial on the x-axis.
- **Imminent risk on versus off** — portfolio total both ways, and the
  difference as a share.
- **Share of claims binding on each constraint** — repair cost, land cover cap,
  retaining wall sub-cap, bridge and culvert sub-cap. A sub-cap that never
  binds is not doing any work.
- **Settlement with the current scheme against the proposed one**, claim by
  claim, as a scatter with the 1:1 line drawn.

**Understanding the result**:

- Contribution by **cause**, stacked — liquefaction land, landslide loss of
  support, landslide runout, retaining walls, culverts and bridges.
- Contribution by **asset**.
- **Exceedance curve** of settlement per claim.
- **Distribution across realisations** of the portfolio total. Plot the cost
  percentile as three separate curves rather than widening one — it is a
  systematic assumption, not a random variable, and merging the two axes would
  present it as though it were. See section 5.1.
- **Map** of mean settlement per property, and aggregated per suburb.
- Mean settlement and claim count **by suburb** and by territorial authority.

**Checking the result**:

- Claims settling at exactly a sub-cap, counted — a spike is either real or a
  bug, and it is worth knowing which.
- Claims where repair cost is below the excess, so settlement is nil.
- Properties with damage but no cover, from the bridge and wall qualification
  filters, counted rather than dropped silently.

## 8. What has to be decided before this can be built

The settlement core in section 2 needs none of these: it is pure arithmetic and
the explainer's three worked examples test it. Everything below either shapes a
data structure, and so is expensive to retrofit, or supplies a number that a
flagged placeholder can stand in for until it lands.

### Shapes a data structure — decide before writing code

- **The dwelling count.** Every sub-cap is `n_dwellings x $50,000 / $25,000`,
  and the multiplier is dwellings **in the residential building**.
  `insured-land.geoparquet` carries `building_count`, not a dwelling count, and
  nothing upstream produces one. Either the address spine gains the attribute or
  the model assumes one dwelling per building and says so. This touches every
  cap in the study.
- **The claim key.** `claim_id` is the LINZ property, set by
  `build_claim_properties` in exposure step 5 and carried unchanged through
  exposure and `vul` (see `beta-build.md`, *The identifier*). It is one named
  function rather than an assumption spread across the modules, because
  **Q-01** may still change what a claim is.
- **Whether landslide drives wall and structure damage** — sections 4.4 and
  4.6. This is `vul`'s output to emit, not `loss`'s to infer, so it has to be
  decided before `vul` is built rather than bolted on after.
- **The cost percentile as a run-level parameter** — section 5.1. **[proposed]**
  and not blocking, but it decides whether the percentile is a scalar in the run
  configuration or a column on every row.

### Supplies a number — a flagged placeholder will do meanwhile

Ordered by how much is blocked behind them:

1. **Q-03, Q-04** — the enabling works bands and the excess earthworks and
   constructability percentages. Every structure repair cost scales with these
   and the source contradicts itself. Nothing in section 4.3 is trustworthy
   until they close.
2. **T-27** — whether the Canterbury land rates already include retaining wall,
   culvert and bridge damage. Decides whether the liquefaction column of the
   matrix stays empty, and whether modelling walls separately double counts.
   For retaining walls the project lead ruled on 2026-10-02 that a wall
   replaced by shaking on flat land and the liquefaction land damage on the
   same claim are not a double count; culverts and bridges are still open.
3. ~~**The retaining wall cap.**~~ — **settled.** It is **$50,000 + GST per
   dwelling**, as the explainer states. The flat $25,000 figure in
   `nhc-land-cover-and-settlement.md` was stale and has been corrected, along
   with the explainer's note about the conflict. Remember the sub-cap is a limit
   on the wall's *contribution to the cap*, not a ceiling on the settlement:
   the contribution is the lesser of undepreciated value and the sub-cap.
4. **T-32** — length or height for wall repair cost. Section 4.3 proposes face
   area, which contradicts `beta-build.md`.
5. **Q-01** — whether a property can carry more than one claim. The whole
   settlement is computed per residential building; multiple claims per property
   would change the unit.
6. **Q-02** — how sub-caps interact where a property carries more than one.
7. **The liquefaction land cost basis** — per property or per m². Section 4.1.
8. **Whether landslide drives wall and structure damage** — sections 4.4 and
   4.6. Needs to exist in `vul` if it is wanted.
9. **District plan minimum lot sizes** for the four territorial authorities,
   for the area cap.
