# `costs_liq_ld_refined_states_2011.csv`

Indicative land damage cost per property, by observed **land damage state**,
from the Canterbury earthquake sequence.

## Source

`T:\Christchurch\TT Projects\52020\WorkingMaterial\ILVR\Dec 2016 ILVR\Dec 2016
Land Liability v1.xlsx`, sheet "Rates Tables", table "Cat 1 to 7 Rates Table
(exc GST)".

A description of the study the rates come from is to be supplied by Virginie
Lacrosse and added here.

## States are not categories

The source table uses two numbering schemes that overlap numerically, which is
the single most important thing to understand before reading it.

- **Land damage categories** are the nine damage types NHC pays out on, numbered
  1 to 9 — cracking, sand boils and so on, with **8 being Increased Liquefaction
  Vulnerability (ILV)** and **9 being Increased Flooding Vulnerability (IFV)**.
  The table's title, "Cat 1 to 7", is naming the damage *types* the rates cover.
  It is not a row range, and there is no missing row.
- **Land damage states** are the severity scale, numbered 1 to 6 and named None,
  Minor, Moderate, Major, Severe and Very Severe. This is the source table's
  "Max Land Damage Index Value" column, and it is what the rows are keyed on.

This file is keyed on **states**. Confirmed by Virginie Lacrosse.

## What the numbers are

- **Payments in 2010/2011 New Zealand dollars per observed land damage state.**
  They are not escalated to any later date, so anything read out of this file
  has to be brought forward before it is compared with a present-day value.
- **Excluding GST**, per the source table's own heading.
- **They include properties that never claimed, at $0.** The figures average
  over all damaged properties in a state, not only those that lodged a claim,
  so they are "watered down" with zeros, as Virginie Lacrosse put it (Q-17).
  The drop-out from damage to claim is therefore already inside them, and
  `COSTS_INCLUDE_NON_CLAIMANTS` in `costs.py` records it. Rates over claimants
  only are to come from Virginie Lacrosse (T-66).
- The three cost columns are the **15th, 50th and 85th percentiles** of cost for
  a given maximum land damage index value, so the spread within a state is
  carried rather than a single point estimate.

## Columns

| Column | Meaning |
| --- | --- |
| `LD_refined_state` | Refined land damage state, 1 to 6 |
| `state_name` | None, Minor, Moderate, Major, Severe, Very Severe |
| `source_band` | The band label the row was read from in the source table |
| `cost_15th_percentile_nzd` | 15th percentile cost, 2010/2011 NZD, excluding GST |
| `cost_50th_percentile_nzd` | 50th percentile cost, 2010/2011 NZD, excluding GST |
| `cost_85th_percentile_nzd` | 85th percentile cost, 2010/2011 NZD, excluding GST |

## How the source bands map onto the states

The source table is banded rather than given per state, so one row there can
supply more than one state here:

- Band "none or 1" supplies state 1, None. The band merges no damage with index
  value 1, which is why a state named None still carries a non-zero median.
- Bands "2 or 2.5" and "3 or 3.5" supply states 2 and 3. The half values fall in
  with the whole value below them.
- Band "5 or 6" supplies states 5 and 6, which is why those two rows carry
  identical costs. They are not independent estimates.

## Limitations

- **These costs are for flatland only.** They come from Canterbury, where the
  observed damage is flat land liquefaction, and they must not be applied to
  hill land or to landslide damage.
- **ILV and IFV are excluded.** The rates cover damage categories 1 to 7, so
  Increased Liquefaction Vulnerability and Increased Flooding Vulnerability
  costs are not in these figures. Both were substantial in Canterbury, so a
  total built from this file alone understates what was paid.
- **Whether the costs include damage to retaining walls, culverts and bridges is
  not known.** Register task **T-27** covers confirming it. For retaining
  walls the project lead ruled on 2026-10-02 that a wall replaced by shaking on
  flat land and these land damage costs on the same claim are not a double
  count, so the figures are treated as excluding retaining walls. For culverts
  and bridges, until T-27 closes, treat the figures as land damage of unknown
  scope.
- The join from these states to mapped observations is not implemented. No code
  in the repository reads this file yet.
