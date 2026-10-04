# Summary: Kritikos, Robinson & Davies (2015)

**The paper is too big for git (about 98 MB), so it is stored at `U:\MAMI\Literature`,
not in this folder.** The file is
`kritikos-2015-regional-coseismic-landslide-hazard-without-inventories.pdf`.

Kritikos, T., Robinson, T.R. & Davies, T.R.H. (2015). Regional coseismic landslide
hazard assessment without historical landslide inventories: A new approach.
*Journal of Geophysical Research: Earth Surface*, 120, 711–729.
<https://doi.org/10.1002/2014JF003224>

This is a summary written from the paper's text. Page numbers are the journal's own
(711–729). The membership curves (Figure 5) are given only as plots, so their values
are not reproduced here; they would have to be digitised from the paper.

## What the paper does

1. It builds a relative coseismic landslide hazard model for earthquake scenarios in
   regions with **no landslide inventory and no geotechnical data**.
2. The factors and their fuzzy membership curves are derived from two well-mapped
   events, the 1994 Northridge and 2008 Wenchuan earthquakes.
3. The curves are then applied unchanged to the 1999 Chi-Chi earthquake as a blind test.
4. The output is a **relative probability of landsliding (0 to 1) per pixel**, not a
   calibrated probability. The authors call it an "order-of-magnitude estimate only"
   (p. 726).

## Method

1. **Fuzzy membership.** Each factor is converted to a 0–1 membership.
   - Landslide density per class is the frequency ratio: (landslide pixels in class ÷
     pixels in class) ÷ (all landslide pixels ÷ all pixels) (eq. 3).
   - Curves are fitted to the frequency ratios in ArcGIS, choosing the shape by R².
   - Some curves are then altered by hand to allow for known inventory quirks. An
     example is the Wenchuan slope-angle curve, lowered at gentle slopes because the
     inventory includes lateral spreads.
2. **Fuzzy Gamma overlay** combines the memberships (eq. 4). It is
   (product of the μᵢ)^(1−γ) × (1 − product of (1−μᵢ))^γ, and it is chosen over
   AND/OR/Sum/Product because it captures the combined effect of several factors.
   - γ between 0.8 and 0.9 gave the best compromise between high hazard at landslide
     pixels and low hazard at flat, non-landslide pixels.
   - γ = 0.9 was adopted, because over-estimating is preferred to under-estimating in
     scenario work. γ = 0.8 changed the Wenchuan AUC by only 0.005.
3. **Average memberships.** The Northridge-specific and Wenchuan-specific curves are
   averaged (Figure 5) into one set for use elsewhere.
4. **Training and test split.** Each inventory is randomly split 50:50 (declustered).
   Frequency ratios come from the training half and performance is scored on the test
   half.
5. **Evaluation.** Success-rate curves and their area under the curve (AUC) are used.
   Pixel values are binned into 100 classes and the share of landslides in each is
   accumulated from high to low. AUC above 0.7 is treated as good.

## Factors

| Factor | Kept? | How it behaves (frequency ratio) |
| --- | --- | --- |
| Shaking intensity (MM) | Yes, the trigger | Landsliding starts at MM V and rises steadily to MM IX in both events. Used instead of PGA, because PGA gave contrasting shapes (Wenchuan rising, Northridge Gaussian). |
| Slope angle | Yes | Rises with slope in 5° classes up to 50° (last class >50°). Northridge falls off above 45°, which the authors attribute to little steep terrain reaching MM VII or more, not to slope itself. |
| Distance to mapped active faults | Yes | Highest next to a fault and falling quickly. Negligible beyond about 10 km. Classes are 5 km out to 10 km and 10 km beyond. |
| Slope position (TPI, four classes) | Yes | Highest on ridges, then midslopes, valleys and flat plains. This is a proxy for topographic amplification. |
| Distance to streams | Tested, then dropped from the final four | Falls with distance, highest within 1–1.5 km. Streams are defined by a 1 km² contributing area, in 0.5 km classes. |
| Slope aspect | No | The two events disagree (Northridge south to west, Wenchuan south to east). The authors link this to the direction of wave propagation. |
| Slope curvature | No | No significant effect. |
| Geotechnical or lithology | Not used | Excluded on purpose so the method is not tied to its training areas. |

- **DEM.** 60 m ASTER for Northridge and Chi-Chi, and a 60 m DEM from Gorum et al.
  (2011) for Wenchuan. The authors stress that all layers must be the same resolution
  and match the scale of the assessment.
- **Inputs.** Only an isoseismal (MM) map, a DEM and an active fault map are needed at
  a new site.

## Training and test data

| | Northridge (1994, Mw 6.7) | Wenchuan (2008, Mw 7.9) | Chi-Chi (1999, Mw 7.7) |
| --- | --- | --- | --- |
| Role | Training | Training | Blind test |
| Landslides | 11,111 | 60,109 | 21,969 |
| Inventory source | Harp & Jibson (1996) | Gorum et al. (2011) | Dadson et al. (2004) |
| Mapped as | Polygons, converted to top points | Top points | Polygons, converted to top points |
| Minimum size | About 5 m wide | 600 m² source area | 3,600 m² |
| Imagery | Aerial photos and field studies | Satellite images and air photos, <15 m | 20 m satellite images |
| MM and fault sources | USGS ShakeMap and mapped faults | as Northridge | as Northridge |

## Results

1. **Earthquake-specific curves against average curves (AUC, whole study area).**
   - Northridge: 0.909 against 0.904.
   - Wenchuan: 0.843 against 0.839.
   - Averaging the curves costs almost nothing.
2. **Average curves on slopes >5° only.** Northridge 0.871 and Wenchuan 0.845.
   Northridge drops because its large areas of gentle ground were flattering the
   whole-area figure.
3. **Blind test on Chi-Chi.** AUC 0.921 for the whole area and 0.915 for slopes >5°.
   About 90% of observed landslides fall in the highest-hazard 20% of pixels (p. 724).
4. **Sensitivity (Table 2, drop-one-factor).**
   - Removing MM costs the most: Northridge 0.909 to 0.769 and Wenchuan 0.843 to 0.785.
   - Removing slope angle or faults costs little on its own.
   - Removing streams or slope position slightly raises AUC. Streams were dropped from
     the final set. Slope position was kept despite the small AUC loss, because
     without it hazard is unrealistically high on flat ground (Figure 9).

## Limitations the authors give

1. The model has only been proven in three settings. It is untested in heavily
   glaciated terrain such as Denali or the high Himalaya.
2. Results depend on inventory quality. Landslides from before the mainshock, from
   aftershocks or from post-event rain inflate the densities. The Chi-Chi inventory may
   include pre-event failures, since later work suggests about 13,000 landslides, not
   21,969.
3. TPI is scale-dependent, and it simplifies topographic amplification (it ignores
   direction, resonance and geology contrasts).
4. Classing continuous factors, and the manual adjustment of curves, add subjectivity.
5. The output is relative hazard for a scenario. It is not a probability of failure or
   a landslide size or volume, and it has no time dimension.

## Points to note for this project

1. The paper names the Southern Alps of New Zealand as the target type of region
   (p. 724). This is the reason it sits in the portfolio as a model needing no local
   inventory.
2. The trigger is MM intensity, so the scenario or event needs an MM field.
   Converting from a ShakeMap PGA or PGV is an extra step and adds its own uncertainty.
3. The authors state "order-of-magnitude" accuracy. Any use for loss modelling needs a
   separate calibration of relative hazard to an absolute landslide fraction. The
   paper does not provide one.
4. Fault-distance weighting depends on the density of the mapped active fault set.
   The authors note the mapped fault spacing affects the distance at which the effect
   fades. The New Zealand Active Faults Database is likely to be denser than the
   training maps.
5. Slope position, slope and stream layers all come from a 60 m DEM. A finer DEM will
   change the slope and TPI distributions the curves were fitted to, so the DEM
   resolution should match the paper's.

The average membership curves of Figure 5 are digitised in `figures/figure-5-average-membership-points.csv` (rendered page: `figures/page-721.png`), read to about 0.02. The check on that digitisation is the reproduction of the paper's AUCs, which is not yet done.
