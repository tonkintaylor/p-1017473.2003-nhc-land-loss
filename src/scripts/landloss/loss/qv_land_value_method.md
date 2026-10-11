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
| 2 | The rest of the insured land: the 8 m buffer and the accessway | `0.5 × R` |
| 3 | The uninsured remainder of the property | `0.15 × R` |

`R` is set so that the three tiers add back to the property's QV land value `V`:

```latex
R = \frac{V}{A_{footprint} + 0.5\,A_{ring} + 0.15\,A_{outer}}
```

Damaged land is insured land, so only tiers 1 and 2 price it:

- **Landslide damage is located.** Vul intersects the landslide ground with the
  footprint, so the part under the house takes `R` and the rest takes `0.5R`.
- **Liquefaction damage is an area with no location.** It takes the insured
  land's average rate, tiers 1 and 2 together weighted by area. That is its
  expected value if the damage is spread evenly over the insured land.
- **A polygon with both** is valued by the larger cause, because the damaged
  area loss counts is the larger of the two.

**Example.** Take a 3,000 m² section with a QV land value of $600,000, a 150 m²
house and 800 m² of insured land. Rates exclude GST:

- `R` = 600,000 ÷ (150 + 0.5 × 650 + 0.15 × 2,200) = **$745/m²** under the
  house. The rest of the insured land is $373/m², and the land beyond it is
  $112/m².
- Liquefaction damage takes the insured land's average, **$443/m²**. The old
  average over the whole section would have been $200/m².
- A 100 m² landslide with 40 m² under the house takes
  (40 × 745 + 60 × 373) ÷ 100 = **$522/m²**.
- The three tiers still add up to $600,000.

Where the insured land covers the whole section, as it does on most small
sections, there is no outer tier to take value, and the rates come close to
the section's average.

## Details

- **QV land value.** Every rating unit on the claim property is summed and
  indexed to the common valuation date of 1 September 2025. The per-council
  factors are those the land value model uses (`land-value-base-rates.csv`).
  A rating unit that spans two claim properties cannot be split, so those
  properties are left out, as is any property with a unit missing its value.
- **Not on the roll.** A property whose value cannot be read off the roll takes
  the median land value per m² of the run's properties in its suburb that can,
  times its own property area, and is then tiered the same way. If no property
  in its suburb can be read off the roll, it takes the median over the whole
  run. The run prints how many claims took each source.
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
| `INSURED_RATIO` | `0.5` | Tier 2's rate as a share of tier 1's |
| `UNINSURED_RATIO` | `0.15` | Tier 3's rate as a share of tier 1's |

The two ratios are **placeholders until a valuer sets them** (T-153). They must
step down: 0 ≤ uninsured ≤ insured ≤ 1. Changing them needs only loss rerun.

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
