# Seismic Fragility Curves for Retaining Walls — Summary

Compiled 17 September 2026. Six representative published fragility function sets, spanning cantilever, gravity, quay and reinforced-soil retaining walls.

## Summary table

| # | Source | Wall type & characterisation attributes | Damage states (EDP & thresholds) | Intensity measure | Method |
|---|---|---|---|---|---|
| 1 | Argyroudis, Kaynia & Pitilakis (2013), *SDEE* 50:106–116 | Cantilever RC wall / bridge abutment on surface footing; **H = 6.0 and 7.5 m**; two soil profiles (strain-dependent stiffness & damping, Mohr–Coulomb); walls dimensioned to pseudo-static design | 4 states (minor / moderate / extensive / collapse) on **permanent vertical ground displacement** (backfill settlement) | **PGA**, free-field ground surface | 2D nonlinear FE time-history; two-parameter lognormal (median, β) |
| 2 | Ichii (2004), 13WCEE Paper 3040 | Gravity **caisson quay wall**, H = 13 m; **aspect ratio W/H = 0.65 / 0.90 / 1.05**; foundation **equivalent SPT N = 5–25**; normalised foundation (liquefiable) thickness **D₁/H = 0–1.0** | 4 degrees on **normalised residual seaward displacement d/H**: **0.05 / 0.10 / 0.20 / 0.30**, calibrated to restoration cost bands | **PGA at base layer** (0.1–0.6 g) | Effective-stress FE (FLIP, strain-space plasticity, liquefaction); MLE-fitted lognormal |
| 3 | Seo, Lee, Park & Kim (2022), *SDEE* 161 | Inverted-T cantilever wall with shear key, **H = 4 m**; **backfill slope 0° / 10° / 20°**; Korean site classes **S2–S5** (bedrock depth, V<sub>s</sub>) | 3 states on **relative wall displacement** = **0.02H / 0.05H / 0.1H** (0.08 / 0.20 / 0.40 m); and on **backfill settlement 0.05 / 0.15 / 0.30 m** | **PGA** (0.1–0.9 g) **+ CAV** — two-parameter fragility *surfaces* | 1D site response → FLAC2D; probabilistic seismic demand model |
| 4 | Cosentini & Bozzoni (2022), *SDEE* 152 | Roadway **gravity earth-retaining walls** (Italy); **trapezoid vs leaning** section; three heights; **flat vs sloped backfill**; >200 analyses | States on **horizontal displacement and rotation** of the wall | **PGV** (optimal) and **PGA**, screened from 35 candidate IMs on efficiency / practicality / proficiency / sufficiency | 2D nonlinear dynamic, 18 real records; validated against 2016 Central Italy damage survey |
| 5 | Li, Li, Cui, Ji, Zhang & Qing (2024), *SDEE* 183 | **Concrete gravity wall**, **H = 9 m** (Wenchuan, China; surveyed population 2–15.4 m); **backfill slope 0° and 12°**; soil and wall material properties randomised | States on **cumulative displacement index at wall top (δ<sub>CDI</sub>)** — captures sliding and overturning | Optimal IM selected via PSDM from three candidates | OpenSees incremental dynamic analysis + Monte Carlo; lognormal (μ, β) |
| 6 | Koutsoupaki, Sotiriadis, Klimis & Dokas (2023), *Geosciences* 14(1):2 | Cantilever walls, **H = 3, 6 and 9 m**, cohesionless backfill, all dimensioned to **FS = 1.5 dry**; primary variable is **initial condition** — water table raised to give **FS = 1.5 / 1.4 / 1.3 / 1.2 / 1.1** | 3 states on **horizontal displacement = 2% / 5% / 10% of H**; plus permanent vertical backfill displacement **0.05 / 0.15 / 0.40 m** | **PGA** (most efficient of PGA, PGV, CAV), free field | 2D FE; lognormal |

## Observations

- **EDP convention splits two ways.** Normalised displacement (d/H — sources 2, 3, 6) transfers between wall heights; absolute settlement (1, 3, 6) is what actually controls serviceability of a road or rail formation behind the wall. Several studies carry both and take the governing one.
- **d/H thresholds are remarkably consistent** at roughly 2 %, 5 % and 10 % of wall height for onshore walls. Ichii's quay-wall set is more permissive (5–30 %) because the consequence metric is berth restoration cost rather than traffic serviceability.
- **PGA dominates as the IM**, but both studies that formally screened IMs (4 and 5) found velocity- or duration-type measures competitive. Relevant for New Zealand subduction motions, where PGA alone tends to under-predict displacement demand.
- **Seismic design coefficient is rarely an explicit variable.** Most sets fix the design k<sub>h</sub> implicitly ("designed to code", "FS = 1.5") and instead vary geometry, backfill slope or groundwater. Source 1 is the closest to fragility conditioned on design level; otherwise a Newmark-type displacement model scaled to the design k<sub>h</sub> is the more defensible route.
- **HAZUS** treats retaining and quay walls only as generic "waterfront structures" keyed to permanent ground deformation, with no wall-type resolution — too coarse for most design-adjacent work.

## Literature review: the curves against Canterbury (2026-10-02)

Part C of the second review (`temp/handoff-remaining-review.md`) read the wall
curves against `temp/gns_review/` (finding ids in backticks,
`out/findings.csv`). The one observed population is Anderson, Wood and Scott
(2015) [anderson_2015]. It covers 2,991 Christchurch walls, most of them in
the Port Hills, through the 2010 to 2011 sequence (`anderson2015-F01`). That
paper was in the second review batch, which had an independent check, and the
height shares used below were read off its Figure 2 again on 2026-10-02.
Every proposal is for the lead. Numbers that are ours say so.

### What Canterbury shows

- **The shaking matched the study's demand.** Port Hills stations recorded
  PGA of 1.0 to 1.7 g on 22 February 2011 and up to 2.0 g on 13 June 2011
  (Table 1 of the paper, checked against the text).
- **About one wall in ten failed.** About 10% were Very Poor (collapse,
  partial collapse, or excessive movement with failure of more than 5 m² of
  face); 10.6% were Poor, 22.3% Average and 41.6% Good, with 15.5% not
  assessed (`anderson2015-F08`, `F15`, ours, Figure 2 weighted by Table 3).
- **Taller walls failed more.** The Very Poor share was 7.1% under 1.5 m,
  10.2% at 1.5 to 2.5 m, 13.9% at 2.5 to 3.5 m and 22.5% above 3.5 m
  (`anderson2015-F13`, read off Figure 2).
- **Type mattered most.** About 18% of stone masonry walls were Very Poor,
  against 13% of crib, 5.5% of concrete masonry, 5.3% of gabion, 2.8% of
  timber pole and none of the MSE walls (`anderson2015-F11`). Stone masonry
  gravity walls failed through inertia, narrow footings and low robustness
  (`F31`). Most walls designed and built to modern practice performed very
  well, and many not designed for earthquake actions performed adequately
  (`F32`).
- **Three caveats, all pointing the same way.**
  - The rates are cumulative over the whole sequence, not one event
    (`F21`), so one event's rate is lower.
  - The sample leans to council road walls and to walls over 1.5 m (`F02`,
    `F03`).
  - Port Hills walls often retained strong loess and acted more as facings
    (`F30`).

  Each makes the Canterbury rate an upper bound for a single event on
  Wellington house-lot walls of the same height and type.

### What the curves give

The Koutsoupaki et al. (2023) cantilever curves [koutsoupaki_2023] the model
read from `retaining-wall-fragility.csv` until 2026-10-06 (DS3, by size and
condition; since replaced by the DS2 wall type curves of
`retaining-wall-type-fragility.csv`) give, at 1.0, 1.3 and 1.7 g (ours):

| Class | Median (g) | P(replace) at 1.0 / 1.3 / 1.7 g |
| --- | --- | --- |
| small and medium, modern | 1.11 | 0.44 / 0.59 / 0.74 |
| small and medium, poor | 0.67 | 0.74 / 0.85 / 0.93 |
| large, modern | 1.43 | 0.30 / 0.45 / 0.60 |
| large, poor | 0.82 | 0.62 / 0.76 / 0.87 |

**The curves overpredict against Canterbury**, by about four to ten times at
the study's shaking, against about 10% Very Poor summed over the whole
sequence. That is part of why 88% of sloping walls were replaced in the
pilot. They also make the 6 m wall stronger than the 3 m one, where
Canterbury's taller walls failed more; the lead is not concerned by that
(2026-10-02). Several things make the Canterbury rate low as a comparison:

- it is cumulative over a sequence, but over walls of all types, many of them
  facings on strong loess (`anderson2015-F30`);
- the sample leans to council road walls (`F03`);
- about 15.5% of walls were not assessed (`F10`).

So the Canterbury shares are the observed comparison, not a replacement.

The curves get the effect of condition about right. Their modern-to-poor
median ratio is 1.65. At β 0.6, that is the ratio between an 18% and a 4%
failure share at one PGA, about Anderson's stone masonry against timber pole
and concrete masonry (ours).

### The lead's decision, and the proposals that remain

**Decided (the lead, 2026-10-02): keep the Koutsoupaki curves.** They are
published and can be justified; medians fitted to Canterbury would be hard to
justify, because the Canterbury rates mix event, wall type and sample
selection. The report states that the curves overpredict against
Christchurch, with the comparison above, as a known conservatism.

1. **Two damage states, with "replace" read as Very Poor in the comparison.**
   Anderson's Very Poor is collapse, partial collapse, or excessive
   displacement with consequential damage. That matches the model's
   "replace", and the lead's point that few damaged walls are repaired. The
   Average and Poor classes (about a third of walls, `anderson2015-F09`),
   with 100 to over 200 mm of outward movement, are "none". Poor plus Very
   Poor (17.5%, 21.1% and 28.3% by the three costing size classes, against
   7.1%, 10.2% and 17.6% for Very Poor alone, `anderson2015-F16`) is the
   comparison's upper end. EQC treats reinstating a failed wall as land
   reinstatement (`sr2018-027-F03`). The movement thresholds are typical
   values, not strict ones (`anderson2015-F36`).
2. **Name the six wall classes after Anderson's types**, the one observed
   split: stone and mass-concrete masonry gravity, concrete block masonry,
   timber pole, crib, gabion, and MSE or engineered reinforced concrete.
   Their Very Poor shares were 18, 5.5, 2.8, 13, 5.3 and 0%
   (`anderson2015-F11`); the 0% for MSE is on 18 walls, so read it as "very
   low".
3. **Infer the wall type from the age and from the claim reports (the lead,
   2026-10-02).** The age bin gives the likely type, since type tracked era
   in Canterbury (`anderson2015-F07`): `pre_1970` is mostly stone and mass
   concrete gravity walls and untreated timber, `1970_1991` treated timber
   pole and concrete block cantilevers, and the later bins engineered walls
   (bin note). The claim reports (**T-50**) give the type where a wall was
   described, and the mix of types per age bin that the inference uses
   elsewhere. The type then sets the condition: the gravity masonry types
   read poor, the others read the age rule.
4. **One curve set for sloping and flat walls**, as now. The Canterbury walls
   are Port Hills hillside walls, so the comparison serves landslide step 8
   (walls on slopes) and vul shaking rw step 9 (flat-land walls).

## Other sources reviewed

- **Rahimi, Firoozfar & Alielahi (2024)** — back-to-back mechanically stabilised earth (MSE) walls with metal strip reinforcement; **overlap length 0.65–0.85H** as the characterisation parameter; scalar and vector fragility on **PGA and PGV**; FLAC2D, far-field vs near-field records. Increasing overlap from 0.65H to 0.85H reduced damage probability by up to 35 % (far-field) and 50 % (near-field).
- **SYNER-G Reference Report 4 (JRC)** — Sections 5.4 and Appendix C.4 cover harbour elements / waterfront structures; PGA and PGD based, limited wall-type resolution.

## References

1. Argyroudis, S., Kaynia, A.M. & Pitilakis, K. (2013). Development of fragility functions for geotechnical constructions: Application to cantilever retaining walls. *Soil Dynamics and Earthquake Engineering*, 50, 106–116. <https://www.sciencedirect.com/science/article/abs/pii/S0267726113000675>
2. Ichii, K. (2004). Fragility curves for gravity-type quay walls based on effective stress analyses. *13th World Conference on Earthquake Engineering*, Vancouver, Paper No. 3040. <https://www.iitk.ac.in/nicee/wcee/article/13_3040.pdf>
3. Seo, H., Lee, Y.-J., Park, D. & Kim, B. (2022). Seismic fragility assessment for cantilever retaining walls with various backfill slopes in South Korea. *Soil Dynamics and Earthquake Engineering*, 161, 107443. <https://www.sciencedirect.com/science/article/abs/pii/S0267726122002925>
4. Seo, H., Kim, B. & Park, D. (2022). Seismic fragility of inverted T-type retaining walls. *20th International Conference on Soil Mechanics and Geotechnical Engineering*, Sydney, Paper 358. <https://www.issmge.org/uploads/publications/1/120/ICSMGE_2022-358.pdf>
5. Cosentini, R.M. & Bozzoni, F. (2022). Fragility curves for rapid assessment of earthquake-induced damage to earth-retaining walls starting from optimal seismic intensity measures. *Soil Dynamics and Earthquake Engineering*, 152, 107017. <https://www.sciencedirect.com/science/article/abs/pii/S0267726121004395>
6. Li, Q., Li, P., Cui, K., Ji, Y., Zhang, D. & Qing, Y. (2024). Seismic fragility curves for concrete gravity retaining wall. *Soil Dynamics and Earthquake Engineering*, 183, 108806. <https://doi.org/10.1016/j.soildyn.2024.108806>
7. Koutsoupaki, E.-I., Sotiriadis, D., Klimis, N. & Dokas, I. (2023). Seismic fragility analysis of retaining walls dependent on initial conditions. *Geosciences*, 14(1), 2. <https://doi.org/10.3390/geosciences14010002>
8. Rahimi, M., Firoozfar, A. & Alielahi, H. (2024). Fragility curves for seismic vulnerability of back-to-back mechanically stabilized earth walls. *Geotechnical and Geological Engineering*. <https://link.springer.com/article/10.1007/s10706-024-02938-7>
9. Pitilakis, K., Crowley, H. & Kaynia, A.M. (eds.) (2013). *SYNER-G Reference Report 4: Guidelines for deriving seismic fragility functions of elements at risk*. JRC Scientific and Policy Report EUR 25880 EN. <https://publications.jrc.ec.europa.eu/repository/bitstream/JRC80561/lbna25880enn.pdf>
10. FEMA (2024). *Hazus Earthquake Model Technical Manual, Hazus 6.1*. <https://www.fema.gov/sites/default/files/documents/fema_hazus-earthquake-model-technical-manual-6-1.pdf>
