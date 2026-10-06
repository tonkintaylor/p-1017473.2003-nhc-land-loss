# Urban localised fragility: calibration to Kingsbury damaged-area shares

## Decision: fit to the Kaikōura record and the polygon anchors (the lead, 2026-10-07)

After the first run below, the project lead chose option 4.2 (option 3 of the
list at the end, with A12 as an upper limit only). The localised
curve is fitted to two things:

1. **The Kaikōura record A16.** An expected damaged share of 0.001 of the
   whole non-flat pilot at 0.15 g on rock. Its weight equals the five polygon
   anchors together.
2. **The polygon anchors A17 to A21.** The mean failure probability of the
   matching bare polygons, averaged over each anchor's PGA range.

The median keeps its fall of five times from rating 0 to 150. Its scale and
beta are found by weighted least squares on the logits
(`area_calibration.fit_record_and_polygons`). Kingsbury's High scenario 2
share (A12, 0.25 of the non-flat area) is an upper limit only. The table
reports whether the adopted curve stays at or below it
(`urban-area-calibration-upper-limit.csv`). The share is capped in any case
by the 20% footprint coverage. None of A07 to A12 is fitted.

Why:

1. Kingsbury's scenario 1 and intermediate classes conflict with Kaikōura.
   They put 2% to 8% of urban hill ground damaged at 0.02 to 0.2 g, where
   the 2016 record at 0.15 g shows none.
2. His minor and significant classes describe other slope types: stream
   banks, natural slopes and loose rock.
3. The polygon anchors describe the urban cuts and fills the model draws.

The Kaikōura record gets the weight of the five polygon anchors combined. It
is the only observation of Wellington's urban ground itself, and the only
target at low demand. The polygon anchors are judgement readings of forecasts
and of another city's record, all at high demand. Equal weight stops their
number alone from overruling the record.

The area fit (to A10–A12 on the whole non-flat pilot) and the footprint fit
are kept in the table and figure as rejected alternatives.

**Status: code and tests only.** The adopted fit has not yet been run on the
pilot, because the pilot outputs were being rebuilt. Its constants, the A12
check and the wall comparison go here after that run, and only then into
`fragility.py` and `LOCALISED_FRAGILITY_BETA`.

## First run (2026-10-07): the agreed area fit, rejected

Run on 2026-10-07 on the `wlg-pilot` extent with `table_urban_area_calibration.py`
and `fig_urban_area_calibration.py`, which read the bare zones of landslide step
12, the step 4 ground map, the step 3 topographic position, the shaking step 2
and 3 grids, the TS1170.5 2500-year PGA grids and the step 8 world 0 model.
The tables are in `report/hazard/landslide/urban-fragility/tab/urban-area-calibration-*.csv`
and the figure is `report/hazard/landslide/urban-fragility/fig/urban-area-calibration.png`.

### Question

Can the localised (no wall) fragility be set by fitting it to [kingsbury_1995]
Table 1, with each class read as the damaged share of a zone's area? The method
was agreed with the project lead on 2026-10-07. If the fit works, does it agree
with the record and anchors that were not fitted?

### Method

1. The polygons are the 5,503 bare polygons inside the pilot box (of 6,441 in
   the zones file). They are built from step 12's `bare` zones the way step 8
   builds a world's polygons (`face_polygons` and `with_amplification`), and
   each one uses the localised curve. Step 8's world 0 model was not used,
   because it holds the walled zones of one wall draw: 5,072 polygons with
   different geometry.
2. The reference area is the non-flat pieces of the ground map (2.274 km2) on
   2 m cells. A cell is damaged where a failed polygon's evacuated or inundated
   zone covers its centre, with `P = 1 - prod(1 - p_i)` (polygons fail
   independently). Cells on flat land do not count.
3. The demand is the rock PGA times the polygon's site PGV per g of rock PGA.
   Site PGV comes from shaking step 3's grid, which equals
   `pgv_m_s_from_sa_1s` of the cell's own site class Sa(1 s) to within 1e-7.
   Rock PGA is TS1170.5 class I. The median is
   `localised_theta_base(rating) / amp_factor` at the medium rate. Each
   scenario is averaged over five log-spaced PGAs.
4. The fit holds `theta_0 / theta_150 = 5` and finds `theta_0` and beta by
   least squares on the logit of the expected share. The targets are the High
   anchors A10 to A12 (0.02, 0.08, 0.25), with the whole non-flat pilot read
   as High (the lead's choice).
5. None of the checks is fitted:
   - Moderate: A07 to A09 on the non-flat cells whose nearest polygon
     (nearest evacuated zone) is rated Moderate. This is a Voronoi-like
     allocation; Low and High are reported the same way.
   - Kaikōura: A16 on the whole pilot.
   - Polygon anchors A17 to A21: the mean `p_i` over the matching polygons.
     Cut or fill is the polygon's wall-unit position, and the slope is the
     element's overall angle. A17 uses the site PGV/PGA ratio with no
     amplification.
   - Walls: step 8's walled polygons, comparing each wall type's base median
     with the no-wall median at the same polygon's rating.
6. An alternative fit, which was not agreed, uses only the non-flat cells
   under a footprint as the reference. It tests whether the wide reference is
   what breaks the agreed fit.

### Results

#### Fit

| Curve | Reference | theta at 0 (m/s) | theta at 150 (m/s) | beta | RMS logit residual |
| --- | --- | --- | --- | --- | --- |
| fitted (agreed) | whole non-flat pilot | 0.334 | 0.0668 | 1.006 | 0.259 |
| committed (placeholder) | | 3.0 | 0.6 | 0.6 | |
| footprint (alternative) | footprint cells only | 6.01 | 1.20 | 2.06 | 0.009 |

The footprints cover 20.1% of the non-flat pilot (zone 2 cells 23.5%,
zone 3 cells 24.6%, zone 4 cells 3.3%). With the whole pilot as reference, no
curve can damage more than 20.1%.

#### Zone shares (expected damaged share)

| Anchor | Reference | Target | Fitted | Committed |
| --- | --- | --- | --- | --- |
| A10 (fit) | whole pilot | 0.020 | 0.019 | 5e-8 |
| A11 (fit) | whole pilot | 0.080 | 0.096 | 1.2e-4 |
| A12 (fit) | whole pilot | 0.250 | 0.183 | 0.026 |
| A16 Kaikōura | whole pilot | 0.001 | 0.101 | 8e-5 |
| A07 | Moderate cells (1.51 km2) | 0.005 | 0.024 | 4e-8 |
| A08 | Moderate cells | 0.020 | 0.123 | 1.4e-4 |
| A09 | Moderate cells | 0.080 | 0.227 | 0.034 |
| A04 / A05 / A06 | Low cells (0.29 km2) | 0.005 / 0.005 / 0.02 | 0.011 / 0.080 / 0.199 | ~0 / ~0 / 0.010 |
| A10 / A11 / A12 | High cells (0.47 km2) | 0.02 / 0.08 / 0.25 | 0.006 / 0.021 / 0.032 | ~0 / ~0 / 0.011 |

The footprint alternative matches A10 to A12 (0.020, 0.081, 0.249) on its own
reference. On the same reference it gives A16 0.084 against 0.001, and A07 to
A09 on Moderate footprint cells 0.021, 0.084 and 0.256 against 0.005, 0.02
and 0.08.

#### Polygon anchors (share of matching polygons failing)

| Anchor | Polygons | n | Target | Fitted | Committed | Footprint |
| --- | --- | --- | --- | --- | --- | --- |
| A17 Port Hills, 1-2 g at site | all | 5,503 | 0.30 | 0.98 | 0.47 | 0.36 |
| A18 cuts > 50 deg, 0.5-0.8 g | cut | 1,845 | 0.30 | 0.96 | 0.28 | 0.30 |
| A19 cuts > 45 deg, 0.2-0.5 g | cut | 2,445 | 0.50 | 0.83 | 0.06 | 0.19 |
| A20 rock cuts 45-50 deg, 0.2-0.5 g | cut, rock | 496 | 0.05 | 0.76 | 0.02 | 0.16 |
| A21 fills, 0.2-0.8 g | fill | 1,274 | 0.30 | 0.83 | 0.10 | 0.21 |

#### Walls against no wall (median of wall base median / no-wall base median)

| Wall type | n | Fitted no-wall | Committed no-wall | Kingsbury 4.4.2 expects |
| --- | --- | --- | --- | --- |
| engineered_modern | 19 | 9.6 | 1.07 | stronger |
| timber_pole_new | 218 | 8.3 | 0.93 | stronger |
| block_rc_cantilever | 522 | 5.6 | 0.62 | stronger |
| timber_pole_old | 492 | 4.1 | 0.46 | between |
| crib | 255 | 3.6 | 0.40 | about equal |
| landscaper_timber | 699 | 3.3 | 0.37 | about equal |
| gravity_masonry | 1,113 | 3.1 | 0.35 | about equal |

### Findings

1. The agreed fit cannot reach its targets. A12's 0.25 is above the 20.1% of
   the non-flat pilot that the bare footprints cover. The fit tries to make
   almost every polygon fail at scenario 2 (A12 is 0.183 against 0.25) and
   meets the low scenario 1 share by widening beta to 1.0.
2. Every check rejects the agreed fit. Kaikōura is predicted 100 times too
   high (0.10 against 0.001). The Moderate shares are 3 to 6 times too high.
   The polygon anchors are 0.76 to 0.98 against 0.05 to 0.5. Under the fitted
   curve, every wall type, gravity masonry included, is 3 to 10 times
   stronger than no wall, where Kingsbury expects poor walls to be about
   equal. **The fit was therefore not adopted:** `fragility.py` still carries
   3.0 and 0.6.
3. The trouble lies in the anchors, not only in the reference. A16 says
   nothing failed at 0.15 g in central Wellington. A11 says 8% of High ground
   (2% of Moderate, A08) is damaged at 0.1 to 0.2 g. A single increasing curve
   on the same ground cannot satisfy both. Even the footprint alternative,
   which matches A10 to A12 exactly, misses A16 by a factor of 80.
4. Kingsbury's shares grow by only a factor of 12 across a factor of 18 in
   demand. A lognormal through them needs beta of about 2 (the footprint
   fit), against the 0.6 to 0.7 of the wall curves. Kingsbury's minor and
   significant classes describe stream-bank and natural-slope failures and
   loose rock, not mainly urban cuts and fills. That would explain both the
   flat rise and the clash with the Kaikōura record.
5. The committed placeholder (3.0 to 0.6, beta 0.6) is the closest to the
   polygon anchors at high demand (A18 0.28 against 0.30, A20 0.02 against
   0.05) and to Kaikōura (8e-5 against 0.001). It falls well short of
   Kingsbury's shares at scenario 1 and the intermediate scenario, and its
   no-wall median makes every wall type except engineered_modern and
   timber_pole_new weaker than no wall.

### Caveats

1. "Whole non-flat pilot = High" was the lead's choice. Per polygon, the pilot
   is mostly Moderate (4,372 of 5,503 polygons). The cells nearest a High
   polygon are only 3% covered, because High polygons sit beside large
   unmodified slopes.
2. Cut or fill comes from the polygon's wall unit (the pif cut and fill
   class), not from the ground map's `modification`. The ground map marks 92%
   of the elements as fill, the units mark 23%. Natural-slope units count as
   cut.
3. The polygons whose representative point lies outside the pilot box (938 of
   them, in step 12's DEM margin) are left out, as in step 8. Their runout
   near the edge is lost.
4. Footprints are counted on 2 m cell centres, so very narrow zones are
   under-counted.
5. The wall comparison uses step 8's world 0 walled polygons, whose geometry
   differs from the bare ones. Both medians are taken before the
   amplification factor.

### Options put to the project lead

Choose one of the following:

1. Keep the placeholder.
2. Re-read the scenario 1 and intermediate classes so that they agree with
   A16. For example, read them as damage mostly outside urban faces, or give
   them lower area fractions.
3. Restrict the fit to scenario 2 (A12, with A09 and A15) plus A16 and the
   polygon anchors.
4. Adopt the footprint alternative with its beta of 2.

The decision at the top of this file is option 3, with scenario 2 kept only as the A12 upper limit and not fitted.
