# Valuing damaged land: QV land value in three tiers

The land cover cap values a claim's damaged land as the damaged area (up to the
area cap) times a rate. Since 2026-10-11 the **loss module sets that rate
itself**. It spreads each property's own land value on the QV rating roll over
the property in three tiers that step down from the house outwards, then values
the damaged land by the tier it lies in. Exposure no longer sends a land value,
and the earlier land value model plays no part in loss.

## Why

A property's land value divided by its area is an average over the whole
section. On a large section most of that area is garden, bush or paddock that
adds little to the value. The average therefore undervalues the ground around
the house, which is where damaged land usually is. Maxim Millen saw this
directly: dividing QV land values by property areas gave very low rates on big
properties.

NHC has no rule for valuing part of a section for a landslide claim (Bridget
Attwood, 2026-10-09; L-78). Its view was that a higher rate should apply to the
land under and around the dwelling. Valuers work the same way. The house site
carries most of the value, and the rest of a section is worth a fraction of its
rate per square metre: depth rules such as the "4-3-2-1" rule, and the
distinction between the primary site and surplus land. John Leeves described
the same three zones on the 2026-10-09 call: a high value under the dwelling,
another within about 8 m of it, and another beyond.

## How

Each claim property's land is split into three tiers, using the layers the
insured land step already builds:

| Tier | Area | Rate |
| --- | --- | --- |
| 1 | The building footprints on the property | `R`, the full rate |
| 2 | The rest of the insured land: the 8 m buffer and the accessway | `0.2 × R` |
| 3 | The uninsured remainder of the property | `0.02 × R` |

`R` is set so that the three tiers add back to the property's QV land value `V`:

```latex
R = \frac{V}{A_{footprint} + 0.2\,A_{ring} + 0.02\,A_{outer}}
```

Damaged land is insured land, so only tiers 1 and 2 price it:

- **Landslide damage is located.** Vul intersects the landslide ground with the
  footprint, so the part under the house takes `R` and the rest takes `0.2R`.
- **Liquefaction damage is an area with no location.** It takes the insured
  land's average rate, tiers 1 and 2 together weighted by area. That is its
  expected value if the damage is spread evenly over the insured land.
- **A polygon with both** is valued by the larger cause, because the damaged
  area loss counts is the larger of the two.

**Example.** Take a 3,000 m² section with a QV land value of $600,000, a 150 m²
house and 650 m² of insured land. Rates exclude GST:

- `R` = 600,000 ÷ (150 + 0.2 × 500 + 0.02 × 2,350) = **$2,020/m²** under the
  house, about $303,000 in all. The rest of the insured land is $404/m², and
  the land beyond it is $40/m².
- Liquefaction damage takes the insured land's average, **$777/m²**. The
  average over the whole section is $200/m².
- A 100 m² landslide with 40 m² under the house takes
  (40 × 2,020 + 60 × 404) ÷ 100 = **$1,051/m²**.
- The three tiers still add up to $600,000.

**Where the ratios come from.** A valuer reviewed this example on 2026-10-13
(T-153). With the first ratios, 0.5 and 0.15, it put $797/m² and about $120,000
under the house. The valuer expected about $300,000 there, about $2,000/m².
One example fixes one combination of the two ratios, not both. The ring was
kept near the $400/m² it had, and the value came off the rest of the section,
which gives 0.2 and 0.02. They have not been checked on a suburban section.
On a 700 m² section worth $490,000, with a 150 m² house and 400 m² insured,
they put about $357,000 (73%) under the house, at $2,380/m², against 47% with
the first ratios.

Where the insured land covers the whole section, as it does on most small
sections, there is no outer tier to take value, and the rates come close to
the section's average.

**Large blocks.** The uninsured remainder counts for no more than 4,000 m², the
Act's minimum-sized site (`MAX_UNINSURED_M2`, 2026-10-12). Land beyond it is
treated as bare land outside the cover and valued at nothing. Without the cap a
lifestyle block of tens of hectares spread its value over every paddock at
the outer tier's rate, leaving the land around its house at a few dollars a
square metre --
about 350 claims across the four councils under $10/m². A section with less
than 4,000 m² of uninsured land is unaffected. On a 58 ha Wainuiomata Coast
block worth $688,000 with 2,300 m² insured, the house site went from about
$8/m² to about $360/m² at the first ratios.

**Shared lots.** A title can include a share in a common lot -- an access lot,
or a subdivision's reserve. Timberlea's titles each carry a house lot and
shares in two lots of about 51 ha. The property area the tiers use leaves that
shared ground out (exposure step 5, `shared_area_m2`), so a house is valued
over its own lot; the property's shape keeps it, so insured land can still
reach an access way on it.

## Details

- **QV land value.** Every rating unit on the claim property is summed and
  indexed to the common valuation date of 1 September 2025. The per-council
  factors are those the land value model uses (`land-value-base-rates.csv`).
  A rating unit that spans two claim properties cannot be split, so those
  properties are left out, as is any property with a unit missing its value.
- **Not on the roll.** A property whose value cannot be read off the roll takes
  the median land value of the run's properties in its suburb that can, and is
  then tiered the same way. If no property in its suburb can be read off the
  roll, it takes the median over the whole run. The run prints how many claims
  took each source. It is the median value, not the median rate times the
  property's area (2026-10-13): a house on a large title sits on a typical
  residential site, and a 58 ha title at its suburb's rate came to $2.8 billion,
  which the tiers then put on its house site at millions of dollars a m².
- **Non-residential units.** A property whose rating units are all
  non-residential (an institution's grounds, a park, a commercial block) is
  valued as though it were not on the roll, because its value is not a
  house's: one 11-dwelling claim sat on a $208m unit of 13 ha.
- **GST.** The QV value is taken as excluding GST, and the rates are grossed up
  for the Act's comparison, as before.
- **Footprint.** This is the buildings the insured land is buffered off,
  merged per claim, so a garage overlapping the house counts once. Exposure
  writes it as a layer (`claim-footprints<suffix>.geoparquet`), and vul's
  landslide step intersects the landslide ground with it.
- **Where it runs.** Loss steps s0 and s1 read the roll from T: once per run.
  They join it to the valuation references exposure wrote
  (`claim-valuation-links<suffix>.parquet`) and apply the rates to the land
  table before it is aggregated onto the claim.

## Settings

Both ratios are in `landloss.loss.qv_land_value`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `INSURED_RATIO` | `0.2` | Tier 2's rate as a share of tier 1's |
| `UNINSURED_RATIO` | `0.02` | Tier 3's rate as a share of tier 1's |
| `MAX_UNINSURED_M2` | `4000` | The most of tier 3 counted; land beyond it is valued at nothing |

The two ratios are set from one valuer's example (2026-10-13), and the cap is
a judgement; both await a valuer's review over more cases (T-153). The ratios must step down: 0 ≤ uninsured ≤ insured ≤ 1. Changing any
of them needs only loss rerun.

## What has to be rerun

For each extent:

1. Exposure s5 writes the footprints, the valuation links and the new columns.
2. Vul landslide s3 measures the ground under the footprint, and liquefaction
   s2 and property damage s10 carry the new columns.
3. Loss is rerun with T: access, because it reads the roll.

The ground, the hazards and the rest of exposure are unaffected.

## Limitations

- **The ratios are judgement** until a valuer gives figures (T-153).
- **The rate follows QV's land value, which is a rating valuation**, not a
  market valuation of damaged land. NHC uses adjusted rating values only for
  uniform land with flooding or inundation, never to settle a landslide claim
  (L-78).
- **Liquefaction damage takes the average**, because nothing says where on the
  insured land it lies.
- **Where both causes damage a polygon,** the larger sets the rate, just as it
  sets the area.
- **The roll is sensitive.** QV's terms allow results derived from it to be
  published, but not the roll itself, nor its records re-tabulated one row per
  rating unit (`landloss.io.qv_rating_roll`). A rate derived from one
  property's land value is close to that record. Check with QV or NHC that
  per-property rates may be shared before they leave T+T, including in the loss
  viewer's CSV.

## Code

- `landloss.loss.qv_land_value`: the indexed QV land value per claim, the
  suburb fallback, the tier arithmetic and the damaged land rates.
- `landloss.vul.landslide.land.damaged_area.footprint_damaged_area`: the
  landslide ground under the footprint.
- `loss/steps/s0_land_cover_cap/s0_gen_land_cover_cap.py`
  (`load_qv_land_values`, `value_land`), used by s1 as well.
- Tests: `tests/landloss/loss/test_qv_land_value.py`.
- `loss/validations/gen_qv_average_rate.py`: the figures, over the four
  councils (`report/loss/qv-land-value/fig/`) -- each rate the tiers apply,
  the correction factors (how far the tiers move a rate off the property's
  average QV rate), and the tiers on a valuer's example and a typical section.
  At 0.2 and 0.02, liquefied ground takes a median 1.16 times the property's
  average, landslide ground under the house 2.5 times, and landslide ground
  around it about half (0.2 times the footprint factor).
- `loss/validations/gen_qv_tier_factors.py`: suburb and property layers with a
  QGIS project (`temp/loss/qv-tier-factors/`), and a tier layer that cuts each
  property into its three tiers, each carrying its QV rate per m² (the
  property and tier layers are sensitive).
