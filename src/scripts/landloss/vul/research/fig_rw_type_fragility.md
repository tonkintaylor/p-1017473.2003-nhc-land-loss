# Retaining wall fragility by wall type: proposal and evidence

Run 2026-10-06 with `fig_rw_type_fragility.py`, which writes
`report/vul/rw/fig/rw-type-fragility.png`. The project lead confirmed the
curves on 2026-10-06, and since then landslide step 8 and vul shaking step 9
read them (`.agents/plans/assigning-retaining-wall-types.md`).

## Question

Can each proposed wall type be given a fragility curve from published sources,
and how do those curves compare with what Port Hills walls did in 2010 and 2011?

## Method

- **Replacement is read at the moderate damage state**, not the most severe,
  because moderate damage usually leads to full replacement in a claim (the
  lead, 2026-10-06). Every curve and comparator is on its source's moderate
  state.
- Each type is placed on one of the five initial-condition rungs of
  Koutsoupaki et al. (2023) [koutsoupaki_2023], Tables A1 to A5: DS2,
  horizontal displacement of 5% of H, on free-field PGA. The 3 m wall gives
  the small and medium classes and the 6 m wall the large class.
- Two types then scale both percentiles (the lead, 2026-10-06): new timber
  pole times 1.3 and engineered modern times 1.5. Concrete block and RC
  cantilever keep the Fs 1.5 rung unscaled.
- Every curve, the comparators included, is stored as its 15th and 50th
  percentiles, the PGA at which 15% and 50% of walls are replaced
  (`src/landloss/io/assets/retaining-wall-type-fragility.csv`, read by
  `landloss.hazard.landslide.urban.wall_type_fragility`), and drawn as the
  lognormal through them.
- A fill wall takes both percentiles times 0.85 and a cut wall times 1.15
  (the lead, 2026-10-06), drawn dotted and dash-dotted on each panel.
- Other published PGA curves are drawn beside a type where one is credible for
  it.
- de Silva et al. (2026) [de_silva_2026] give displacement against
  amax/ac, not a PGA curve. With ground type C (Table 2: a = 0.021,
  b = 1.684, σ = 0.848), a capacity uncertainty of 0.3 and DS2 at 0.15 m,
  the PGA median is 3.21 ac and the dispersion 0.53. The yield acceleration
  ac is set at 0.5 g for now (the lead), which puts p15/p50 at 0.92/1.61 g.
  The paper ran ac of 0.05 to 0.3 g, so 0.5 g is above its range.
- The Canterbury failure shares by type are drawn at the PGA recorded in the
  Port Hills on 22 February 2011, 1.0 to 1.7 g (Anderson et al. 2015, Table 1):
  Very Poor in [anderson_2015], the only class it gives by type, and Moderate
  plus Major in [stone_2015], Table 3.

## The rungs (DS2, moderate)

| Fs | 3 m p15/p50 (g) | 3 m β | 6 m p15/p50 (g) | 6 m β |
| --- | --- | --- | --- | --- |
| 1.5 | 0.44/0.86 | 0.654 | 0.54/1.09 | 0.679 |
| 1.4 | 0.37/0.70 | 0.604 | 0.45/0.86 | 0.629 |
| 1.3 | 0.35/0.65 | 0.609 | 0.41/0.80 | 0.644 |
| 1.2 | 0.31/0.59 | 0.617 | 0.36/0.71 | 0.661 |
| 1.1 | 0.27/0.51 | 0.630 | 0.32/0.63 | 0.658 |

The rungs are not evenly spaced. Most of the drop is from Fs 1.5 (dry) to
Fs 1.4, the first rise of the water table. Below that, the rungs are close
together.

## The proposal and the evidence

| Type | Curve, p15/p50 3 m (6 m) | Other published curve, moderate | Canterbury share |
| --- | --- | --- | --- |
| Gravity masonry | Fs 1.1: 0.27/0.51 (0.32/0.63) | Gravity road wall, ~3.6 m, 5% H: 0.10/0.36 g [cosentini_2019] Table 6; concrete gravity wall, 9 m, LS1: 0.12/0.46 g [li_2024] Fig. 18(a) | Stone masonry 18% Very Poor [anderson_2015]; stone facing 35% Moderate+Major [stone_2015] |
| Crib | Fs 1.2: 0.31/0.59 (0.36/0.71) | None found | 13% [anderson_2015]; concrete crib 30%, timber crib 28% [stone_2015] |
| Timber pole, old | Fs 1.3: 0.35/0.65 (0.41/0.80) | None found | Not split by age |
| Concrete block or RC cantilever | Fs 1.5: 0.44/0.86 (0.54/1.09) | RC cantilever abutment, 6 m, soil C, moderate: 0.29/0.60 g [kaynia_2011] Table 5.13 | Concrete masonry 5.5% [anderson_2015]; reinforced concrete 22% [stone_2015] |
| Timber pole, new | Fs 1.5 ×1.3: 0.57/1.12 (0.70/1.41) | None found | Timber pole 2.8% [anderson_2015]; post and panel 9% [stone_2015] |
| Landscaper timber | Fs 1.1: 0.27/0.51 (0.32/0.63) | None found | Not split |
| Engineered modern | Fs 1.5 ×1.5: 0.66/1.29 (0.81/1.63) | None usable | MSE 0% of 18 walls [anderson_2015] |

## Findings

- **The ordering holds.** The Canterbury shares rank the types in the same
  order as the proposed curves: masonry, then crib, then block and RC, then
  timber pole and MSE.
- **The published moderate curves sit on the weak side of their types.** The
  6 m RC curve [kaynia_2011] lies on the Fs 1.1 to 1.2 rungs, below the block
  and RC curve. Both gravity curves [cosentini_2019] [li_2024] rise faster
  than Fs 1.1 below about 0.5 g and flatten above it, because their β is
  large (1.2 to 1.3).
- **Every curve sits above the Canterbury shares.** At 1.0 to 1.7 g the
  proposed curves give about 0.25 to 0.97, against Moderate plus Major shares
  of 9 to 35% [stone_2015] and Very Poor shares of 0 to 18% [anderson_2015].
  Moving to the moderate state widens that gap. This is the known
  conservatism the lead accepted on 2026-10-02 (see
  `.agents/context/retaining-wall-fragility.md`). The type split changes the
  ratio between types, not that offset.
- **No published curve was found** for crib, timber pole, concrete block,
  gabion, residential masonry, or small MSE walls. For these, the rung is
  judgement ordered by the Canterbury shares.

## How far to trust the Canterbury shares

Both are counts over a real population of walls, not a sample built to be
representative of residential walls.

- **Anderson et al. (2015)**: 2,991 walls compiled from council, consultant
  and SCIRT inspection records and some residential inspections. Most
  supported council roads or the cuts above them. Walls were kept if the
  authors inspected them, if they were over 1.5 m, or if records were
  adequate. Inspection records exist mainly because a wall was damaged or
  important, which leans the sample towards damage; the 1.5 m cut leans it
  to taller walls; 15.5% were not assessed.
- **Stone et al. (2015)**: 967 council-owned walls on the Port Hills, the
  whole SCIRT-assessed council stock there, so close to a census of council
  walls. 43% are "non-structural" stone facings on self-supporting loess
  cuts, which carry little earth load. Their shares are for facings, not
  for gravity walls retaining fill, which the paper says performed worse.
- **Shared biases.** Council road walls, not private house-lot walls. Damage
  is cumulative over the 2010 to 2011 sequence. Loess stands unsupported
  when dry, so walls on it are lightly loaded. The walls standing in 2010
  had survived earlier events. The type labels are the inspectors', and
  Anderson's shares are read off a bar chart.
- **Net effect.** For one event on Wellington house-lot walls retaining
  colluvium or fill, the shares are biased low by the loess and road-wall
  stock, and high by the repeated shaking and the selection towards damage.
  The ranking of types is more trustworthy than the level.

## Caveats

- The Canterbury shares are cumulative over the sequence, lean to council road
  walls, and include stone facings on strong loess. They are an upper bound on
  one event's rate, not points on a curve.
- Anderson's shares by type are read off Figure 1 by pixel; the authors did not
  tabulate them, and give only Very Poor by type.
- [cosentini_2019] does not say whether its curve is for the flat or the
  sloping backfill model, and its β was assumed rather than fitted.
- The [kaynia_2011] damage state is absolute backfill settlement (15 to 30 cm
  for moderate), not a share of H, and β is mostly assumed.
- [li_2024] prints no fragility parameters. Its LS1 curve is fitted by eye to
  Fig. 18(a) (θ 0.46 g, β 1.3). The median agrees with Table 8's capacity
  through the Fig. 12(a) demand line, but the plotted β is wider than the
  Table 5 and 8 dispersions imply (about 1.0). It is a 9 m highway wall in
  clay, checked against the Wenchuan 2008 damage; a 12 degree backfill raises
  LS1 by nearly 25% at 0.4 g.
- Sources looked at and not drawn: [argyroudis_2013] and [seo_2022] (journal
  versions paywalled), Salmon et al. (2003; background unclear per SYNER-G),
  and Rahimi et al. (2024; 14 m back-to-back MSE). Working copies and their
  sources are in `temp/reference/rw-fragility/SOURCES.md`.
