# `costs_liq_ld_claimant_costs_2011.csv`

The cost of a Canterbury liquefaction land claim, by observed **land damage
state**, over the properties that **lodged a claim** only: how many claims, their
mean, and their lower quartile, median and upper quartile.

## Source

Supplied by Virginie Lacrosse via Perrie Gilbert on 2026-10-08, extracted
from the Canterbury land claims with retaining wall (RTW), culvert (CLV) and
bridge (BRI) claims excluded. The name of the source dataset is to be recorded
here.

## Calibration only

**These figures are what the model is checked against, never what it reads in.**
Maxim Millen asked on 2026-10-08 that they be used to calibrate and compare,
not as inputs. The model prices a claim from the ground it lost; these say
whether the prices it arrives at look like what Canterbury paid. Nothing
outside the calibration step (vul liquefaction land step 3) reads them.

## What the numbers are

- **Claimant-only.** Properties that never claimed are not in them at $0. This
  is what T-65 asked for, and what lets the model draw the drop-out from damage
  to claim rather than carry it inside the costs (Q-17). Claims that came in
  under the excess are in them, at their value before the excess.
- **Before the excess.** The amount the claim was worth, not what was paid
  after the excess was taken off.
- **2010/2011 New Zealand dollars, excluding GST**, like the percentile table
  (**L-23**, **L-24**).
- **Canterbury events, flat land only, liquefaction only.** Claims involving a
  retaining wall, culvert or bridge are excluded, so these are costs of
  liquefied land alone and must not be used for hill land, landslide damage or
  wall and crossing repair.
- **`source_code` 11 to 16** are the source's codes for land damage states 1
  (None) to 6 (Very severe), confirmed by Perrie Gilbert.
- **Right-skewed.** In every state the median is well below the mean, so the
  mean is carried by a tail of large claims. The quartiles are what show it.

## Columns

| Column | Meaning |
| --- | --- |
| `LD_refined_state` | Refined land damage state, 1 to 6 |
| `state_name` | None, Minor, Moderate, Major, Severe, Very Severe |
| `source_code` | The source's code for the state, 11 to 16 |
| `claims` | Number of claims |
| `mean_cost_nzd` | Mean cost of a claim |
| `cost_25th_percentile_nzd` | Lower quartile |
| `cost_50th_percentile_nzd` | Median |
| `cost_75th_percentile_nzd` | Upper quartile |

## How it is used

Vul liquefaction land step 3 fits the liquefied land repair rates
(`landloss.vul.liquefaction.repair_rates`) to the means, each state weighted by
its claim count, and then fits the spread of the per-claim cost between claims
to the quartiles, weighted the same way. The spread has a mean of one, so
fitting it leaves the means where the rates put them.

The means here replaced, on 2026-10-08, the means that step used to estimate
from the 50th and 85th percentiles of `costs_liq_ld_refined_states_2011.csv`,
which average over non-claimants at $0. These run below those estimates --
Moderate is $1,351 here against about $2,600 estimated from the percentile
table -- although that table includes non-claimants at $0 and so would be
expected to be the lower of the two. Why is not known. These are taken as the
more reliable (Perrie Gilbert, 2026-10-08).

## What the source also gave, and is not packaged

- **Figures for each pair of states**, None with Minor, Moderate with Major and
  Severe with Very severe. They are the claim-weighted combination of the rows
  here, so they add nothing.
- **A likelihood of settlement** per pair of states: 10% for None and Minor,
  60% for Moderate and Major, 100% for Severe and Very severe. It was described
  as a rough estimate, to be run past John Leeves and James R, so it is noted
  beside the drop-out rates in the liquefaction land step's config rather than
  packaged. It counts claims that came in under the excess and were paid $0 as
  settled.
