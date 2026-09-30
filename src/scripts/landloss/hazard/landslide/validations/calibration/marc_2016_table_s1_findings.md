# Marc et al. (2016) rebuild: check against the paper's Table S1

Results of `fig_marc_2016_table_s1.py`, run on 30 September 2026, on
`landloss.hazard.landslide.calibration.marc_2016` and the paper's 40 earthquakes
(`src/landloss/io/assets/marc-2016-table-s1-subevents.csv`). The figure is
`report/hazard/landslide/calibration/fig/marc-2016-table-s1.png`.

## The implementation reproduces the paper's fit

The paper fitted its landscape sensitivity and steepness scale on 26
earthquakes: the 40, less its 11 named outliers and the 3 with no source-depth
constraint. Refitting both on the same 26 with our code:

| Constant | Our refit | Paper |
| --- | --- | --- |
| Volume steepness scale T_SV | 11.7° | 11.6 ± 0.6° |
| Volume sensitivity α*V | 4,569 m³ km⁻² | 4,174 ± 212 m³ km⁻² |
| Area steepness scale T_SA | 17.2° (12 events) | 15.8 ± 1.5° (13 events) |
| Area sensitivity α*A | 4,238 m² km⁻² | 3,445 ± 325 m² km⁻² |

The steepness scale is reproduced almost exactly, and the volume sensitivity to
within 10%, about two of the paper's standard errors. The area fit is on one
event fewer than the paper's, and the paper does not say which 13 it used, so
the larger gap there is expected. **The code is the paper's model.** The
remaining difference is of the size that small choices produce, for example
how a sequence's sub-events are combined, or a depth assigned where the table
leaves it unknown.

## Predictions at the paper's own constants

- On the 26 fitted events: 20 within a factor of 2, none worse than a factor of
  2.9, median ratio of estimated to predicted 1.01.
- On all 40: 20 within a factor of 2 for volume (the paper reports 63%), and 7
  of 17 for area (the paper reports 11 of 17). The shortfall is concentrated
  in the paper's own outliers, which are exactly the events our code misfits
  most: Friuli, Umbria-Marche, 1994 Arthur's Pass, Avaj, Denali, Rotoehu,
  L'Aquila, Cucapah, Yushu, Lorca and 2011 Nagano. The paper's percentages
  appear to count an event as within a factor of 2 where its uncertainty range
  reaches that far, which this script does not do.

## The two equations read as the physics requires

- **Eq. 7, fault length:** the 2/5 power applies to the whole ratio, with a
  shear modulus of 33 GPa. Only this reading reproduces the paper's stated
  3.5–225 km for Mw 5–8; we get 3 km and 188 km.
- **Eq. 8, strike-slip length** once the fault width saturates: written so that
  it joins eq. 7 at about 33 km. As printed, it does not join.

Both are tested in `tests/landloss/hazard/landslide/test_calibration_marc_2016.py`.

## New Zealand events

Nine of the 40 are in New Zealand. Estimated over predicted volume:

| Event | Ratio | Note |
| --- | --- | --- |
| 1929 Arthur's Pass | 0.70 | |
| 1929 Buller (Murchison) | 1.89 | The only NZ event with a total area as well; area ratio 0.99 |
| 1931 Napier | 1.25 | |
| 1932 Wairoa (printed as 1935) | 0.98 | |
| 1968 Inangahua | 0.42 | Overpredicted 2.4 times |
| 2003 Fiordland | 0.57 | |
| 1855 Wairarapa | 0.16 | Source depth unknown; R0 taken as half the 16 km hypocentre, as the paper's methods do for Mw > 7.5 |
| 1994 Arthur's Pass | 0.11 | One of the paper's outliers |
| 2004 Rotoehu | 19 | One of the paper's outliers; Mw 5.5, from field reports |

Six of the nine are within a factor of about 2.4. The misfits are the two
outliers the paper names, and 1855, whose source depth is not known. 1855 is
also the one historical Mw ~8 New Zealand event, the size of the study's
forward scenario. A deeper source (R0 nearer 16 km) would bring it closer.

## What this does not establish

- Calibration of a Wellington total. Marc is fitted on shallow crustal
  earthquakes, and the study's forward scenario is a Hikurangi subduction
  interface event (see the landslide `status.md`).
- Kaikōura, which post-dates the paper and is the out-of-sample test in phase 4
  of the calibration plan.
