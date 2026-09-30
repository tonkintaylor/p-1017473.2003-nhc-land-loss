# Summary: Marc, Hovius, Meunier, Gorum & Uchida (2016)

Marc, O., Hovius, N., Meunier, P., Gorum, T. & Uchida, T. (2016). A
seismologically consistent expression for the total area and volume of
earthquake-triggered landsliding. *Journal of Geophysical Research: Earth
Surface* 121(4), 640–663. <https://doi.org/10.1002/2015JF003732>

The files beside this one:

| File | What it is |
| --- | --- |
| `marc-2016-total-area-volume-eq-triggered-landsliding.pdf` | The paper, the authors' accepted version from the GFZ repository |
| `marc-2016-supporting-information.pdf` | Supporting information: Figures S1–S10, Table S2, and the caption of Table S1 |
| `marc-2016-supporting-table-s1.xls` | Table S1, the 40 earthquakes |

Table S1 is also packaged in the repository as
`src/landloss/io/assets/marc-2016-table-s1.csv` (verbatim) and
`marc-2016-table-s1-subevents.csv` (numeric); the assets README explains both.

## What the expression gives

1. One number per earthquake: the total area (eq. 12) or the total volume
   (eq. 11) of the landslides it triggers. There is no spatial pattern. In this
   study it is used to calibrate the **amount** of landsliding each large model
   predicts; see `.agents/plans/building-hancox-landslide-model-and-calibration.md`.
2. It starts from a local landslide density that is linear in shaking above a
   threshold, P = α (a − a_c) (eq. 1). Shaking is a 1 Hz source acceleration
   with geometric spreading only, a = b·ξS/R.
3. It integrates that density over the area around each wave source (eq. 5), and
   sums over the sources along the rupture, one per 3 km asperity (eq. 6).
4. Landscape steepness enters through the modal slope, exp(S_mod/T), and through
   A_topo, the share of the predicted landsliding that falls on cells with a
   modal slope of 8° or more.

## Constants

- a_c = 0.15 (normalised by g), the threshold acceleration.
- b_sat·ξS = 4,000 m for reverse and strike-slip faults, 2,800 m for normal
  faults. Hinge magnitude M_h = 6.75. Boore & Atkinson (2008) 1 Hz terms
  e5 = 0.6728, e6 = −0.1826, e7 = 0.054.
- Fault length from Leonard (2010), with a separate strike-slip form above the
  critical moment; seismogenic thickness 17 km.
- Area: α*_A = 3,445 ± 325 m² km⁻², T_SA = 15.8 ± 1.5°.
- Volume: α*_V = 4,174 ± 212 m³ km⁻², T_SV = 11.6 ± 0.6°.
- Uncertainty by Monte Carlo over rupture velocity (2,000 ± 200 m/s), a_c
  (0.15 ± 0.02), b_sat·ξS (4,000 ± 400 m) and M_h (6.75 ± 0.1), reported as the
  25th, 50th and 75th percentiles.
- Modal slope from the 30 m ASTER GDEM, in 1 km² cells.

## Performance

1. **Volume:** within a factor of 2 for 63% of the 40 earthquakes (R² = 0.76).
2. **Area:** within a factor of 2 for 11 of the 17 earthquakes where total area
   is constrained (R² = 0.73).
3. **Steepness:** low landscape steepness causes systematic overprediction, up
   to 50-fold for a modal slope of about 12°.
4. **Outliers:** some are put down to exceptionally strong rock, others to
   seismic source complexity. Two of the eleven are New Zealand events: 1994
   Arthur's Pass and 2004 Rotoehu.

## Scope

1. **Shallow continental earthquakes only:** hypocentres shallower than 25 km,
   onshore.
2. **Subduction events excluded:** subduction earthquakes were left out of the
   fit. Tohoku and Pisco are plotted in Figure 1 for reference only, with
   volumes similar to those of Mw 6 continental events.
3. **A New Zealand application in the paper:** an Alpine Fault scenario.

## Table S1: the New Zealand events

Nine of the 40 earthquakes are in New Zealand. All nine have their volume
estimated from large landslides (method N), apart from 2004 Rotoehu, which is
from field photographs and reports (P). Total area is given only for 1929
Buller. None is among the 11 comprehensive inventories.

| Earthquake | Mw (from Table S1's moment) | R0 (km) | Modal slope | A_topo | Fault |
| --- | --- | --- | --- | --- | --- |
| 1855 Wairarapa | 8.1 | unknown (8–24) | 25° | 0.25 | SS |
| 1929 Arthur's Pass | 6.8 | 6 | 34° | 1 | SS |
| 1929 Buller (Murchison) | 7.6 | 5 | 29° | 1 | R |
| 1931 Napier | 7.7 | 7.5 | 11° | 1 | S (as printed) |
| 1932 Wairoa (printed as 1935) | 7.2 | 12 | 14° | 1 | S (as printed) |
| 1968 Inangahua | 7.0 | 7.5 | 25° | 0.6 | R |
| 1994 Arthur's Pass | 6.7 | 9 | 34° | 1 | R |
| 2003 Fiordland | 7.2 | 20 | 32° | 0.3 | R |
| 2004 Rotoehu | 5.5 | 5 | 9° | 0.2 | N |

The values that look wrong as published (Buller's volume range, Iwate's range,
the Wairoa year, the `{S}` fault type) are listed in the assets README and kept
as published.

1855 Wairarapa is the one historical Mw ~8.1 New Zealand event in the table,
the size of the study's forward scenario. It was left out of the paper's
steepness fit because its source depth is unconstrained.
