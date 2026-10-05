# Kritikos et al. (2015) reproduction: findings

Check that the model rebuilt from the digitised Figure 5 scores what the paper
scored on its own events [kritikos_2015]. Script:
`table_kritikos_2015_reproduction.py`; settings in `config.py`; inputs in
`event_inputs.py`. Output: `report/hazard/landslide/kritikos-2015-validation/tab/
kritikos_2015_reproduction.csv`.

## Result

Success-rate AUC, γ = 0.9, 600 m TPI window, study area the inventory's bounding
box. The published values are the paper's average memberships over the study
area, and over slopes above 5°.

| Event | Case | AUC | Paper | Difference |
| --- | --- | --- | --- | --- |
| Wenchuan | base | 0.831 | 0.839 | −0.008 |
| Wenchuan | slope > 5° | 0.801 | 0.845 | −0.044 |
| Northridge | base | 0.867 | 0.904 | −0.037 |
| Northridge | slope > 5° | 0.827 | 0.871 | −0.044 |
| Northridge | study area +5 km | 0.893 | 0.904 | −0.011 |
| Northridge | study area +15 km | 0.927 | 0.904 | +0.023 |

**The digitisation is good enough to use.** Wenchuan reproduces within 0.01.
Northridge is 0.037 low on the tightest study area and brackets the paper's value
as the area widens (0.893 at +5 km, 0.927 at +15 km), so the gap is the study
area, which the paper does not define, not the membership curves. Both events
are within the 0.02 acceptance for some reasonable study area.

## Sensitivities

| Case | Northridge | Wenchuan |
| --- | --- | --- |
| base | 0.867 | 0.831 |
| MMI ≥ 6 only | 0.845 | 0.703 |
| γ = 0.8 | 0.868 | 0.830 |
| TPI window 300 m | 0.867 | 0.831 |
| TPI window 1200 m | 0.868 | 0.828 |
| no fault term | 0.848 | 0.893 |
| study area +5 km | 0.893 | 0.835 |
| study area +15 km | 0.927 | 0.846 |

- **The study area moves the AUC more than any model choice.** Flat ground far
  from the landslides counts as an easy negative. This is also why an AUC from
  one extent cannot be compared with another's: the Wellington pilot's value
  will depend on its extent.
- **The TPI window and γ do not matter** (≤ 0.003). The 600 m window, which the
  paper does not give, is not a sensitive choice. γ = 0.8 changes Wenchuan by
  0.001, where the paper says 0.005.
- **Excluding gentle slopes costs about 0.04 on both events**, whereas the paper's
  Wenchuan value rises (0.839 to 0.845). This is unexplained. Either the paper
  scored the over-5° case in some other way, such as keeping all cells in the
  area and ranking only the steeper ones, or the 5° membership at the foot of
  the slope curve is a little off. It does not change which model to use, but it
  is open.
- **The fault term depends on the fault map.** With the GEM Global Active Faults
  as the stand-in, switching the fault term off *raises* Wenchuan from 0.831 to
  0.893, while it helps Northridge (0.848 to 0.867). The likely reason is that
  Wenchuan's landslides spread over the whole Longmen Shan, well beyond the
  mapped traces, so a membership that falls with distance penalises them; this
  was not tested. The paper's own fault maps are not available, so this says
  only that the term is sensitive to the fault map. It is
  relevant to the lead's decision on `FAULT_TERM = "mapped"` against
  `"far_field"` (plan, decisions table), and to Wellington, where the mapped
  faults will be the AF250 traces.

## What was not reproduced

- **Chi-Chi (0.921).** The GFDB v4 holds only the liquefaction of the 1999
  earthquake (Chu et al., 2004), not the Dadson et al. (2004) landslide
  inventory the paper used. It needs that inventory.
- The paper's training and test split (random halves of 100 classes) is not
  repeated, since a score on all cells has no fitting to hold out.

## Inputs, and where they differ from the paper's

| Input | Used here | Paper |
| --- | --- | --- |
| Landslides | GFDB v4: Harp and Jibson (1995), 11,111 polygons (representative point); Gorum et al. (2011), 60,109 points | Same inventories, tops of polygons |
| Intensity | USGS ShakeMap atlas grid, bilinear | ShakeMap |
| DEM | Copernicus GLO-30 averaged to 60 m | ASTER 60 m; Gorum et al.'s 60 m |
| Faults | GEM Global Active Faults, harmonised, 55 km reach | Regional mapped faults |
| Study area | Inventory bounding box (+ margins shown) | Not defined |

The GFDB is read with `landloss.io.gfdb` from the copy of the delivery in
`.tdrivecache/DataLibrary/130.10_ground_failure_inventory_INT_Schmitt2022/`
(see the changelog fragment for how it got there). An exact
`event_name = '...'` filter raised a GDAL index error in `filegdbindex.cpp` on
this geodatabase, so the reader now filters with `LIKE` and compares exactly in
pandas. Rerunning the script as committed, from the cache, gives the same table.

## The transfer function from H to coverage

`steps/s11_kritikos_2015/gen_kritikos_2015_transfer_function.py` fits it on
the same two events, over the inventory bounding box, with the step's settings
(γ 0.9, TPI 600 m, mapped faults). Tables: `report/hazard/landslide/
kritikos-2015-validation/tab/kritikos_2015_transfer_function*.csv`.

| Event | Cells | Observed mean coverage | Pooled curve gives |
| --- | --- | --- | --- |
| Northridge | 1.71 M | 0.39% | 1.05% (2.7× over) |
| Wenchuan | 16.1 M | 1.29% | 0.61% (2.1× under) |

- The pooled curve rises from 0.005% at H 0.09 to 0.36% at 0.48, 0.89% at 0.62,
  1.87% at 0.77 and 3.84% at 0.865.
- The events disagree. Where both exceed 0.01% the curves differ by 1.3× to 70×:
  Wenchuan is higher over H 0.4–0.75 and saturates near 4.5% above 0.74;
  Northridge is lower in the middle and steep at the top. The same H does not
  mean the same coverage in the two earthquakes, so the pooled curve is a
  compromise and the per-event curves are the honest range.
- Wenchuan's points carry no area. Coverage there is the published 811 km²
  [gorum_2011] (a secondary-source figure, `verify`) divided by the count and
  spread as discs, which conserves area. It includes runout, so it is not the
  same quantity as Northridge's source polygons (mean 2,144 m² against 13,490 m²).
  A first version capped coverage per cell and lost most of the area (0.37%).
- Not yet run: other study-area margins, which moved the AUC by up to 0.06, and
  so will move this curve.

## Licences and sources

Working copies sit in `temp/reference/kritikos_2015_validation/` with a
`SOURCES.md`. ShakeMap grids are USGS public domain. The GEM faults are Styron
and Pagani (2020) under CC BY-SA 4.0 (verify the version). Copernicus GLO-30 is
free with attribution to ESA. None is redistributed.
