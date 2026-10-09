# Retaining wall datasets compared, property by property

**Run:** 2026-10-02. **Scripts:** `gen_rw_dataset_properties.py`, then
`table_rw_dataset_agreement.py`, `fig_rw_dataset_agreement.py` and
`fig_rw_dataset_maps.py`, all beside this file, with settings in `config.py`.
Tables are in `report/exposure/rw/rw-datasets/tab/` and figures in
`report/exposure/rw/rw-datasets/fig/`.

## Question

Three datasets say where retaining walls are. How many walls do they agree on,
and how many are only in one of them?

## The datasets

- **GNS SLIDE mapped walls** [townsend_2020]: 11,288 line segments, 280 km,
  mapped from imagery and elevation over urban Wellington City only. GNS says
  they are "some" walls: only those visible from above. Read by
  `landloss.io.readers.get_gns_slide_morphology`.
- **NHC NZMM land attributes**: a Y/N `RetainingWallInd` per property over the
  four councils. Sensitive. How it is populated is not documented. Read by
  `landloss.io.nzmm_land_attributes.get_nzmm_land_attributes`.
- **Claim reports**: the walls T+T engineers listed in 2,085 extracted land
  claim reports (four claims lists, accepted and declined), from
  `extract_claim_reports.py`. A report lists the walls that matter to the claim,
  so "none listed" is not "no wall".

## Method

- **Unit:** the LINZ property polygon (roads and hydro parcels left out), the
  only unit all three share. 174,001 in the study area.
- **NHC onto the map:** NZMM has no geometry. Its `qpid` joins one to one to
  QV's rating roll, and the roll's valuation number, written by
  `landloss.io.qv_rating_roll.linz_valuation_reference`, matches the LINZ
  `valuation_reference`. 99.9% of NZMM properties are placed, and 4,634 of the
  4,640 flagged.
- **GNS onto properties:** a property has a GNS wall where at least 1 m of
  wall lies within 1 m of it (`TOLERANCE_M`, `MIN_WALL_LENGTH_M`), so a wall on
  a shared boundary counts for both neighbours. Wall counts are of connected
  lines; the segments barely join (11,288 become 11,489 parts), so a count is
  close to a count of segments. The area GNS mapped is the convex hull of every
  SLIDE morphology line inside Wellington City. That hull overstates the area
  to the west, where there are few properties.
- **Claims onto properties:** each report's geocoded point is placed in its
  property, or on the nearest within 15 m if it falls in a road. 1,551 of 2,085
  reports are placed; the rest are outside the study area. A property claimed
  more than once takes the largest wall count.
- **Populations:** each comparison uses only the properties every dataset in
  it covers. GNS against NHC: 70,674 properties in the area GNS mapped that
  NZMM flags either way. Three-way: the 921 claimed properties among them.

## Results

| Dataset | Extent | Properties | Record a wall |
|---|---|---|---|
| GNS SLIDE | Urban Wellington City | 80,676 | 20.5% |
| NHC NZMM | Four councils | 156,640 | 3.0% (WCC 4.3%) |
| Claim reports | Claimed properties | 1,411 | 26.3% |

**GNS against NHC** (`rw-dataset-agreement-gns-nhc.csv`,
`rw-dataset-agreement-gns-nhc.png`), 70,674 properties at 1 m:

| | Properties |
|---|---|
| Both | 933 |
| GNS only | 13,998 |
| NHC only | 2,225 |
| Neither | 53,518 |

- Both record a wall on 5.4% of the properties either records one on.
- GNS maps a wall on 30% of the properties NHC flags; NHC flags 6% of the
  properties GNS maps a wall on.
- Cohen's kappa is 0.03, about what chance gives.
- The tolerance makes no difference. From 0 to 5 m, both stays at 5.4% of
  either: a wider buffer adds GNS properties, not agreement.

**All three, on 921 claimed properties** (`rw-dataset-agreement-claims.csv`,
`rw-dataset-upset-claims.png`):

- All three agree on 44% of them, almost all of it agreement on no wall (409
  properties). All three record a wall on 2% (19).
- The rest is spread across every combination of one or two datasets, with
  "GNS only" (17%) and "claims only" (12%) the largest.

**Against what the claim report lists** (`rw-dataset-claims-recall.csv`,
`rw-dataset-claims-recall.png`), claimed properties in the area GNS mapped:

| Claim report | Properties | GNS flags | NHC flags | Either flags |
|---|---|---|---|---|
| Lists a wall | 235 | 34% | 26% | 51% |
| Lists none | 709 | 28% | 19% | 41% |

- Where an engineer listed a wall on site, GNS has one on a third of the
  properties and NHC on a quarter. Half are in neither.
- Both datasets flag a property only slightly more often when its report
  lists a wall than when it does not. Neither tells the two groups apart well.
- **NHC flags claimed properties four to six times as often as properties in
  general** (19 to 26% against 4.5% in the same area), whether or not the claim
  lists a wall. GNS flags claimed properties only somewhat more often (28 to 34%
  against 21%). Hill land alone does not explain the NHC gap (see slope, below).
  One possibility is that the NZMM flag is filled partly from claim or
  inspection records. That needs asking of NHC before the flag is used as
  evidence of a wall.

**By NZMM slope class** (`rw-dataset-by-slope.csv`, `rw-dataset-by-slope.png`):

| Slope class | NHC flags | GNS flags | Claims list a wall |
|---|---|---|---|
| 1 | 1.7% | 18% | 31% |
| 2 | 6.3% | 27% | 24% |
| 3 | 9.5% | 14% | 18% (33 claims) |

- NHC rises with the slope class. GNS rises from class 1 to 2. Claims fall:
  a claim on flatter land is more often a wall claim. Class 3 holds only 570
  properties.

**By council** (`rw-dataset-by-ta.csv`): NHC flags 4.3% in Wellington City, 3.2%
in Porirua, 1.2% in Lower Hutt and 0.8% in Upper Hutt. Claims list a wall on 22
to 34% of claimed properties in every council. Where a claim lists a wall, NHC
flags it 26% of the time in Wellington and Porirua, against 7 to 8% in the two
Hutts.

**Wall counts** (`rw-dataset-wall-counts.csv`, `rw-dataset-wall-counts.png`):
on 944 claimed properties GNS mapped, the number of walls GNS maps does not
follow the number the report lists. Of 181 properties whose report lists one
wall, GNS maps none on 120.

**Maps** (`rw-dataset-hex-wcc.png`, `rw-dataset-hex-study-area.png`): per
300 m hexagon over urban Wellington City and per 750 m over the four councils.
A hexagon holding fewer than 10 properties or 5 claims is left blank. GNS and
NHC each have their own pattern of high-share hexagons, and the hexagons where
both agree (panel c) are scattered rather than gathered in any one area.

## Findings

1. **The datasets record different walls.** GNS and NHC agree no more than
   chance on which properties have a wall, and neither picks out the
   properties an engineer found walls on much better than it picks out the
   ones where none was listed.
2. **The NZMM flag is far from an inventory.** It flags 3% of properties.
   Claim reports list a wall on a quarter of claimed properties, and the step 6
   wall population expects two to four walls on a typical hill property.
3. **GNS mapping is wider but not more specific.** It flags a fifth of
   properties in urban Wellington and a third of those where a claim lists a
   wall.
4. **The NZMM flag is concentrated on claimed properties**, out of proportion
   to slope. Find out how it is populated before using it.

## What it means for the wall model

- Neither GNS nor NZMM can be the truth to calibrate against. The claim reports
  are the only on-site record, and they list only the walls that matter to the
  claim.
- `BETA_MAPPED_WALL_PROBABILITY = 0.9` in
  `landloss.exposure.rw.wall_probability` assumes a GNS wall is almost always
  real. This comparison cannot test that, because a claim with no wall listed
  is not evidence of no wall. It does show that a GNS wall misses two thirds of
  the claimed properties with a listed wall, so the absence of a GNS wall
  should carry little weight. That matches the current code, which never lowers
  a probability for it.
- The NZMM flag is not yet worth adding as evidence on a candidate line.

## Caveats

- Claimed properties are hill properties that made a land claim. They are not
  a sample of all properties.
- "Lists none" means no wall mattered to the claim, not that there is none.
- A GNS wall on a shared boundary counts for both neighbours, which raises the
  GNS share. The tolerance table shows agreement does not depend on it.
- The area GNS mapped is a convex hull, wider than what GNS actually covered.
  Properties in the gap count as GNS "no wall".
- The per-property layer under `temp/exposure/rw/validations/` is derived from
  the NZMM extract and the claim reports. It is sensitive, and must be destroyed
  with the NZMM extract at the end of the project. Only aggregates are written
  to `report/`.
