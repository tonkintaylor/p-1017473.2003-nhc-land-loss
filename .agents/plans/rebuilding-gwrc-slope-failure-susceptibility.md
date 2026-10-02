# Rebuilding the GWRC earthquake-induced slope failure susceptibility layer

## Why this is being looked at

`report/hazard/landslide/fig/gwrc-slope-failure-severity.png` is drawn from the
Greater Wellington layer read by `landloss.io.readers.get_gwrc_slope_failure`
(Koordinates layer 4069). That layer is published **CC BY-ND** — attribution,
no derivatives. We may reproduce it unchanged, which is what the figure does,
but we may not publish anything derived from it. Any use beyond a picture —
scoring our own model against it cell by cell, clipping it into a delivered
layer, blending it into a combined susceptibility surface — sits on the wrong
side of that line or close enough to it to need legal advice.

Rebuilding the zonation from its own inputs removes the restriction, because
the product would be ours. It also fixes two things the licence has nothing to
do with: the layer's coverage stops about 6 km short of the study area's
western edge (Porirua/Titahi Bay) and about 10 km short of the southern edge
(Wellington's south coast), and its slope input is a 1995 digital terrain model
built from 20 m contours rather than LiDAR.

This document extracts the method from the published sources so the rebuild can
be judged on what it would actually take. It does not commit to doing it.

## The source chain

| Layer of the chain | What it is | Obtainable |
| --- | --- | --- |
| Koordinates layer 4069 / GWRC ArcGIS `WR_SlopeFailure` | The digitised polygons, fields `LSKEY` and `SEVERITY` | Yes, CC BY-ND |
| Kingsbury (1995), WRC/PP-T-95/06 to /10 | Five map sheets at 1:40,000 with explanatory booklets — the published method | Yes, free PDFs from GWRC |
| Brabhaharan, Hancox, Perrin & Dellow (1994) | Works Consultancy Services contract report to WRC; the detailed study the booklets summarise | Not found online; would need a request to GWRC |
| Hancox, Dellow & Perrin (1994) | DSIR/GNS review of historical earthquake-induced slope failures in the region, used to calibrate the ratings | Not found online |

The booklets are the important find. All four sheets covering the study area —
Wellington, Porirua and SH58, Hutt Valley, and SH2 Upper Hutt to Featherston —
carry the **identical** factor table, the identical rating bands and the
identical mapping rules. The scoring scheme is one scheme applied region-wide,
so a rebuild has one method to implement, not four.

Source PDFs:

- Wellington (WRC/PP-T-95/06), OCR'd:
  <https://www.gw.govt.nz/assets/Documents/2025/05/EQ-SLOPE-FAILURE_Wellington_March-1995-OCR.pdf>
- Porirua and SH58 (WRC/PP-T-95/07):
  <https://www.gw.govt.nz/assets/Documents/Documents/2025/11/EQ-SLOPE-FAILURE_Porirua-and-SH-58_March-1995-347963.PDF>
- Hutt Valley (WRC/PP-T-95/08):
  <https://www.gw.govt.nz/assets/Documents/Documents/2025/11/EQ-SLOPE-FAILURE_Hutt-Valley_March-1995-347702.PDF>
- SH2 Upper Hutt to Featherston (WRC/PP-T-95/10):
  <https://www.gw.govt.nz/assets/Documents/Documents/2025/11/EQ-SLOPE-FAILURE_SH-2_Upper-Hutt-to-Featherston_March-1995-347961.PDF>

All four have a text layer and read cleanly with `pdftotext -layout`.

## The method, as published

### The scoring

Six factors. Each is divided into classes, each class carries a **factor value**
`F` on a 1–10 scale, and each factor carries a **weighting** `W`. The
susceptibility rating is

    Rs = Σ (F × W)

with a maximum of 150. Values and weightings were assigned subjectively, from
historical and geological evidence of earthquake-induced slope failure in the
region, then refined against the historical record (booklet Table 4).

| Factor | Symbol | W | Class | F |
| --- | --- | --- | --- | --- |
| Slope angle | F<sub>SL</sub> | 4 | < 20° | 0 |
| | | | 20–35° | 2 |
| | | | 35–45° | 4 |
| | | | 45–60° | 8 |
| | | | > 60° | 10 |
| Slope modification | F<sub>SM</sub> | 4 | cut slope 35–45° | 4 |
| | | | cut slope 45–60° | 8 |
| | | | cut slope > 60° | 10 |
| | | | sidling fills | 10 |
| Slope height | F<sub>SH</sub> | 2 | 0–5 m | 0 |
| | | | 5–10 m | 4 |
| | | | 10–20 m | 8 |
| | | | > 20 m | 10 |
| Geology | F<sub>G</sub> | 2 | UW–MW greywacke | 0 |
| | | | HW–CW greywacke | 4 |
| | | | crushed and shattered greywacke | 8 |
| | | | colluvium / alluvium | 10 |
| Existing landslides | F<sub>L</sub> | 2 | none present | 0 |
| | | | old slides | 5 |
| | | | active slides | 10 |
| Groundwater | F<sub>W</sub> | 1 | well drained | 0 |
| | | | poorly drained | 5 |
| | | | saturated | 10 |

Three qualifications travel with the table:

- **Slope height applies only to slopes steeper than 45°**, mainly cuts. The
  booklets say explicitly that it is not appropriate for natural slopes of
  35–45° such as coastal cliffs or the Wellington Fault scarp.
- **Vegetation was deliberately excluded** as relatively unimportant in this
  region.
- Slope angle and slope modification carry weighting 4 each. Together they are
  80 of the 150 available points, and the booklets say they "were used primarily
  to define the boundaries of the hazard zones on the maps". Everything else is
  secondary.

The worked examples in booklet Table 6 reproduce these weightings exactly, which
is how the table above was verified against OCR damage: the Moderate example
sums to 96 against a stated band of 60–100, High to 138 against 100–140, and
Very High to 150 against > 140.

### The zones

| Zone | `SEVERITY` | Rs | Map colour | Typical ground |
| --- | --- | --- | --- | --- |
| Very low | 1 Low | 0–20 | Green | Flat and low-lying areas |
| Low | 2 | 20–60 | Yellow | Gentle hill country, low cuts |
| Moderate | 3 Moderate | 60–100 | Orange | Gentle to moderate slopes, moderate cuts |
| High | 4 | 100–140 | Red | Steep slopes, high cuts |
| Very high | 5 High | > 140 | Purple | Very steep slopes and high cuts |

The `SEVERITY` column of the modern layer is this zonation. It is a
**susceptibility** classification — where failure is more likely — and not a
rate, a probability or an expected area.

### The mapping rules, which matter as much as the arithmetic

The 1995 product is not a scored raster. It is generalised polygons, drawn under
rules set out in booklet section 4.4.2:

- Slopes above 45° were the prime indicator of very high susceptibility.
- A steep area was **expanded to the entire slope it occupies, plus an allowance
  for downslope runout** — in some cases all the way to the valley floor.
- Where only a small steep area sat high on a gentle slope, a **tear-drop shape**
  was zoned to represent the likely extent of the failure.
- **All** modified slopes fall in High or Very High, on the assumption that cut
  slopes are less stable than unmodified ones. Quarry slopes are treated as the
  least stable of all.
- Existing landslides **and ground adjacent to them** are High.
- Retained slopes designed to resist seismic shaking are excluded from the high
  category. Inadequate crib walls, shotcrete and light concrete walls are zoned
  moderate to high.
- The zones were then checked against the historical earthquake-induced
  landslide record and the factor values and weightings **refined until they
  agreed with it**, before being used as the basis for mapping.

That last point is the one that cannot be reproduced from the published sources.
The numbers in the table are the output of a calibration loop whose target — the
Hancox et al. (1994) historical review — we do not hold.

### Input scales

- Slope angle: 1:25,000 slope maps from a digital terrain model derived from
  **20 m contours**.
- Cut slopes: mapped at 1:50,000 generally, 1:10,000 to 1:20,000 in urban areas.
- Geology: a generalised engineering geology map; the booklets note detailed rock
  mass data existed only in localised areas.
- Landslides: air photo interpretation, with few large landslides found.
- Published at 1:40,000.

### Slope failure potential, which is a separate product

Susceptibility crossed with an earthquake scenario gives **potential** — the
booklets' Table 1 — expressed as classes from very minor to very severe with
volume bands attached. The scenarios are:

| Scenario | MM on rock | PGA on rock | Probability in 50 years |
| --- | --- | --- | --- |
| 1 — M7 at ~100 km, shallow | V–VI | 0.02–0.06 g | ≥ 90% |
| Intermediate — regional event | VII–VIII | 0.1–0.2 g | ~45% |
| 2 — M7.5 Wellington Fault, Wellington–Hutt segment | IX–X | 0.5–0.8 g | ~10% |

The study's threshold finding is that **MM VII is the threshold for significant
earthquake-induced slope failure** in the region; MM VI has occurred about ten
times since 1840 with no significant landsliding, and widespread failure needs
MM VIII–X, which has happened four times. Failures caused by liquefaction are
excluded from the study throughout, which is consistent with the Zone 5 soft
sediment mask the landslide module already applies.

The potential classes are a lookup table, not a calculation, and they would come
across into a rebuild unchanged.

## What a rebuild would need

| Factor | W | Source for a rebuild | State |
| --- | --- | --- | --- |
| Slope angle | 4 | LINZ LiDAR DEM via `readers.get_dem`, then `common.utils.terrain.slope_degrees` | Have it |
| Slope modification | 4 | WCC earthmoving cut and fill areas, plus road, rail and quarry cuts and retaining walls | The hard one — see below |
| Slope height | 2 | Toe-to-crest height of the steep facet, from the 1 m DEM inside the modification polygons | Processing task, not a data gap |
| Geology | 2 | GNS QMAP for colluvium/alluvium against greywacke; fault proximity as a proxy for crushed and shattered | Partly available, proxies needed |
| Existing landslides | 2 | GNS New Zealand Landslide Database; council records | Not held; availability and licence unknown |
| Groundwater | 1 | Booklet generalises to extreme conditions; a constant is defensible | Trivial, and worth 10 of 150 points |

### Slope: the two-scale derivation

The class thresholds — 20°, 35°, 45°, 60° — were calibrated against slope from a
terrain model built from 20 m contours and mapped at 1:25,000. Slope is a
property of the length it is measured over, so the question is what support
length reproduces that.

Horn's kernel on the study's 10 m DEM measures gradient over about 20 to 30 m,
which is close to the 1995 support length. **Working at 10 m is therefore not a
compromise, it is the closest available match to the calibration**, and
`common.utils.terrain.slope_degrees` already does it. Slope from the native 1 m
LiDAR would be systematically steeper over the same ground — it resolves
benches, cut faces and micro-relief the contour model averaged away — and
feeding it into 1995 thresholds would push large areas into Very High and
produce a different product.

The smarter version is to use both scales, because **Kingsbury used both
scales**: slope angle was mapped at 1:25,000 and cut slopes at 1:10,000 to
1:20,000 in urban areas. That division lines up exactly with the factors:

- **F<sub>SL</sub>, the natural slope angle**, from the 10 m DEM. Broad terrain,
  broad support, thresholds as published.
- **F<sub>SM</sub> the cut angle and F<sub>SH</sub> the cut height**, from the
  native 1 m LiDAR, inside the modification polygons only. A cut face 10 m high
  at 50° is one cell wide at 10 m and is averaged away to something like 20°;
  at 1 m it is ten cells wide and resolves properly. The 45–60° and >60° classes
  are unreachable at 10 m.

The cost objection to 1 m does not apply here. `DEM_RESOLUTION_M` is 10 m
because 1 m over the whole study area is about 3.2 billion cells, but the
modification factor is only ever evaluated inside mapped cut and fill polygons —
6.3 km², about 6.3 million cells. The fine pass is affordable precisely because
it is spatially restricted.

Whichever is chosen, the sensitivity of the zone areas to the support length has
to be tested and stated rather than asserted.

### Slope modification: what the WCC earthmoving layers do and do not give

Two layers were supplied in September 2026 and now have readers,
`get_wcc_cut_areas` and `get_wcc_fill_areas`:

| | Cut areas (125307) | Fill areas (125311) |
| --- | --- | --- |
| Polygons | 203 | 250 |
| Area | 2.8 km² | 3.5 km² |
| Extent | 1,743,714–1,755,067 E, 5,421,786–5,442,256 N | 1,743,715–1,754,974 E, 5,421,193–5,442,304 N |
| Licence | CC BY-ND 4.0 | none recorded |

They are **an index of the council's earthworks records, not a terrain model**.
Every attribute is a pointer back to an archived plan — `CW_file_number`,
`SR_Number`, `Aussies_drawer_number`, `Archives_Online_Link`, `TroveID` — with
`Comments` naming the streets and usually the consent years. There is no depth,
no height and no angle. What they give is **where to look**; the 1 m LiDAR gives
the numbers.

Three gaps follow, and the first two are large:

1. **Coverage is Wellington City's western and northern hill suburbs only** —
   roughly Karori to Churton Park. Nothing in Porirua, Lower Hutt or Upper Hutt
   (one fill polygon clips the Porirua boundary and is otherwise noise), and
   nothing on the south coast or in the eastern suburbs. Three of the four
   territorial authorities have no modification factor at all.
2. **Subdivision earthworks only.** Kingsbury's largest modified slopes are the
   state highway, rail and quarry cuts — Ngauranga Gorge, the Hutt Road, the
   urban motorway, the Johnsonville line and the NIMT, and the Horokiwi, Kiwi
   Point and Owhiro Bay quarries, which the booklets single out as the least
   stable slopes in the region. None of these is subdivision work, so none is in
   these layers.
3. **Nothing about retaining.** The mapping rules turn on whether a slope is
   adequately retained — seismically designed walls are excluded from the high
   category, inadequate crib walls and shotcrete drop to moderate or high.
   `data-sources.md` records that no private retaining wall dataset exists and
   the WCC database covers council walls only.

### Reproducing the generalisation

Beyond the factors, the polygon generalisation has to be reproduced or the
result is not comparable with the original: expanding steep facets to the whole
slope, adding the runout allowance, and the tear-drop rule for small steep areas
high on a gentle slope. A scored raster and the 1995 polygons are different
things, and a rank correlation between them would be measuring that difference
as much as anything else.

## What is reproducible and what is not

Reproducible: the factor classes, the values, the weightings, the summation, the
rating bands, the zone definitions, the scenario lookup and the MM VII threshold.
All of it is published in the booklets and consistent across all four sheets.

Not reproducible from the published sources:

1. **The calibration.** The values and weightings were refined against the
   historical landslide record in Hancox et al. (1994), which we do not hold. We
   can adopt the published numbers, but we cannot check them or re-tune them to a
   modern inventory without that report or a substitute.
2. **The engineering geology map** the geology factor was read from, including
   weathering state. QMAP is coarser and does not map weathering.
3. **The 1994 landslide inventory** behind the landslides factor.
4. **The engineering judgement** in the polygon boundaries — which retained
   slopes were considered adequately designed, which quarry faces were included,
   where a tear-drop was drawn.

A rebuild therefore reproduces the *scheme* faithfully and the *map*
approximately. It would not reproduce the 1995 polygons and should not be
presented as doing so.

## Where this now lives

Option 3 below was taken and built. The scheme is
`landloss.hazard.landslide.susceptibility`, and the step that runs it is
`src/scripts/landloss/hazard/landslide/steps/s2_slope_failure_susceptibility/`.
That step's own method file describes what is implemented and its implementation
plan carries the phases still open, including the first comparison against the
published layer. This document stays as the method extraction and the record of
why the rebuild was done at all; it is not updated as the code changes.

## Scope decisions, 23 September 2026

Three calls taken after the first pass, which between them cut the outstanding
list roughly in half.

1. **Residential land only.** The product is not a wall-to-wall regional
   susceptibility map. It is a susceptibility score on **insured land** — the
   ground around dwellings — which is what the loss model settles on anyway.
   This is the largest of the three changes and it is worked through below.
2. **The geology factor is not worth mapping in detail.** Weathering state and
   crushed/shattered zones are dropped; see below for why the source itself
   supports this.
3. **Validation is by visual comparison** against the GWRC layer where it has
   coverage. The published values and weightings are adopted as they stand and
   not re-tuned, so Hancox et al. (1994) stops being a blocker. Displaying the
   ND layer unchanged beside our own is inside the licence, so this is also the
   cheapest validation available.

### What "residential only" removes

- **Quarries, entirely.** Horokiwi, Kiwi Point and Owhiro Bay are not
  residential ground. The booklets call quarry faces the least stable slopes in
  the region, and it no longer matters to us.
- **State highway and rail corridor cuts, mostly.** A Ngauranga Gorge cut face
  does not damage insured residential land. The exception is the suburban road
  cut — the booklets note that "all the suburban roads in the hilly areas
  include significant cut slopes", and those form the uphill or downhill
  boundary of real sections.
- **The need for coverage over non-residential hill country**, which is most of
  the area the 1995 map covers.

What it does **not** remove is the coverage gap in Porirua, Lower Hutt and Upper
Hutt. Those three have residential hill country too, and no earthworks records
in hand.

The useful consequence is that the WCC earthmoving layers are **subdivision**
earthworks — exactly the residential population — so the one dataset we have is
aimed at the one population we care about. And restricting the score to insured
land makes the 1 m fine pass cheaper again, because it only has to run over the
insured land extent rather than over whole hillsides.

### How much residential ground the earthmoving layers actually reach

Measured over the earthworks bounding box (1,743,714–1,755,067 E,
5,421,193–5,442,304 N), which holds 100,997 LINZ addresses and 76,038 building
outlines:

| | Addresses on it | Buildings touching it |
| --- | --- | --- |
| Cut areas | 4,201 | 4,430 |
| Fill areas | 4,408 | 4,904 |
| Either | **8,533** (8.4%) | 8,061 |

Against an 8 m buffer on every building as a stand-in for insured land: 37.38
km² of proxy insured land in that box, of which **3.59 km², or 9.6%, sits on
mapped earthworks**. Read the other way, **59% of the 6.08 km² of mapped
earthworks is proxy insured land** — these layers are mostly residential ground,
which confirms they are aimed at the population this study cares about.

Two things follow, and the second is the important one.

- **8,500 addresses is a population worth having.** It justifies the licence
  conversation with the council on its own.
- **The modification factor will reach only about one insured-land polygon in
  ten, even inside the one area that has records.** The other nine score
  F<sub>SM</sub> = 0 and so cannot reach High or Very High on modification at
  all, while the 1995 rules put *every* modified slope in one of those two
  zones. Our map will therefore come out systematically less severe than the
  GWRC one, and the visual comparison in decision 3 will show exactly that. It
  is a coverage artefact, not a modelling disagreement, and it has to be said
  out loud or it will be misread as one.

That second point also changes what the LiDAR fallback is for. It is not only
for the three territorial authorities with no records — it is needed inside
Wellington City too, because an archive of consented subdivision earthworks
cannot capture the older suburbs. The booklets say as much: "Older subdivisions
in the hills have fewer large-scale cuts and fills, but all the suburban roads
in the hilly areas include significant cut slopes."

Caveats on the numbers: the 8 m buffer is taken around every building outline,
including garages and sheds, rather than around dwellings, and it skips the
driveway and shared-ground handling the real insured land extent does; and the
box is the earthworks extent, not all of Wellington City. Both make this a
sizing exercise rather than an exposure result.

### Why the geology factor can be a constant

The source says so itself. Booklet section 4.2.3: geology "was less important
for this study because of the relative uniformity of bedrock type in the
Region", with the steep slopes "underlain by greywacke rock with a variable but
generally thin (1 to 2 metre) surface layer of colluvium".

The arithmetic agrees. The factor is weighted 2, the second lowest, so it spans
0 to 20 of 150. And in Kingsbury's own five worked examples it contributes 4,
4, 20, 20 and 20 — **a single value for everything Moderate and above**, which
is all the ground that matters here.

So: set F<sub>G</sub> to the colluvium-over-greywacke value on hill country, as
Kingsbury effectively did, and read the colluvium/alluvium against greywacke
split from QMAP if it is there. Do not chase weathering state, the
crushed/shattered class, the NZ Active Faults Database proxy or the 1:50,000
urban geological sheets. Expect QMAP at 1:250,000 not to resolve a 1–2 m
colluvium veneer on hillslopes, so expect a constant in practice.

A constant shifts every score equally, so it changes nothing about the ranking
and only moves where the fixed band boundaries bite. State it as a limitation,
and check it by re-running the score with the greywacke value instead and
reporting how many properties change zone. That is a one-line sensitivity test,
not a data programme.

## What is still missing, as at 23 September 2026

1. **Subdivision earthworks records for Porirua, Lower Hutt and Upper Hutt —
   40 points, and now the main gap.** Ask those three councils for their
   equivalent of the WCC earthmoving layers. This is a smaller and more likely
   ask than the NZTA, KiwiRail and quarry chase it replaces, because it is the
   same kind of record from the same kind of body.
2. **Cut and fill detection from LiDAR, over the insured land extent only.**
   Not just a fallback for the three councils with no records: the measurement
   above shows the WCC archive reaches only about a tenth of insured land even
   where it does cover, so this is needed inside Wellington City as well.
   Bounded by construction, because the extent is already computed, and it is
   the same terrain work the retaining wall exposure needs.
3. **Whether a slope is retained, and whether the retaining is seismically
   designed.** The mapping rules lift or drop a slope on this alone.
   `data-sources.md` records that no private retaining wall dataset exists, so
   this is a known dead end; the newly mirrored GNS SLIDE morphology layer
   (`GNS_SLIDE_MORPHOLOGY_LAYER_ID`) carries some retaining walls among its
   mapped linear features and is worth testing as a partial answer.
4. **A landslide inventory — 20 points.** The GNS New Zealand Landslide Database
   is the obvious candidate and is not held; availability and licence both need
   checking, and the old/active split may not survive whatever is obtainable.
   The GNS SLIDE morphology layer's scarps and breaks in slope may substitute
   for part of it.
5. **A licence position on the WCC layers.** See below. This is a blocker on
   publishing anything derived, not a data gap.

Nothing on this list blocks a first cut over Wellington City's residential hill
suburbs, which is where the cut and fill records are and where the cut-and-fill
failure mode the project cares about is concentrated.

## Options

1. **Do not rebuild.** Keep the GWRC layer as it is used today — displayed
   unchanged, as a visual check on where the model puts landslides, with the
   coverage gaps stated. Costs nothing and stays inside the licence.
2. **Rebuild faithfully.** Implement the six factors and the generalisation
   rules, on modern data, over the whole study area. Produces a licence-clean
   layer with no coverage gaps that can be scored against, clipped and
   delivered. Gated on modification data for the whole study area, which does
   not exist today.
3. **Rebuild the factors, score them with Kingsbury's weights.** Build the factor
   grids the landslide module needs anyway — slope, modification, geology,
   landslides — and apply the published values and weightings as a by-product.
   Skip the polygon generalisation and keep the result as a scored grid, stated
   as "the Kingsbury (1995) scheme on modern data", not as a reproduction of the
   GWRC map.

**Recommendation: option 3, over Wellington City first, once the WCC licence is
settled.** The factor grids are on the critical path for the landslide module
regardless of what is decided here, so the scoring is close to free once they
are in place, and the WCC earthmoving layers make the modification factor
buildable over exactly the hill suburbs where the cut-and-fill failure mode the
project cares about is concentrated. The polygon generalisation is the expensive
part and it buys only comparability with a 1995 map, which is not a project
deliverable. Option 2 is worth revisiting only if the layer itself, rather than
the validation, turns out to be something NHC wants, and only if modification
data arrives for the other three territorial authorities.

Worth weighing against all three: the GWRC layer is currently a **validation
target, not an input**. The module's hazard comes from the supplied ESNZ
probability grid. Rebuilding a subjective 1995 weighting scheme to validate a
modern probabilistic model is a modest prize, and the same effort spent on the
slope modification layer serves the model directly.

## Licence note

Reproducing a *method* is not making a derivative of a *dataset*; copyright does
not cover methods or facts, and the booklets are GWRC's own published
explanation of how the map was made. Re-digitising the 1995 map sheets, by
contrast, would produce the same data by another route and is not the path here.
This is a reading, not advice — if a rebuilt layer is to be delivered to NHC or
published, get it confirmed, and in the meantime keep the ND layer to unchanged
display only.

**The rebuild does not escape the problem it was meant to escape.** The WCC
earthmoving cut layer is itself tagged CC BY-ND 4.0 on the T+T mirror, and the
fill layer carries no licence at all. A susceptibility layer built on them is a
derivative of them, so trading the GWRC ND licence for these two is no trade.
The two layers are the *only* source of the modification factor, which is 40 of
the 150 points, so there is no version of this rebuild that routes around them.
Settle the terms with Wellington City Council before any of this is built, not
after.

## Open items

1. **Settle the WCC earthmoving licence.** The cut layer is ND and the fill
   layer is untagged. Ask the council what terms actually apply and whether a
   derived susceptibility layer may be published. This gates the whole rebuild.
2. Ask GWRC for the Brabhaharan et al. (1994) and Hancox et al. (1994) contract
   reports. They are the calibration basis and neither appears to be online. The
   request can ride along with the existing approach for Greater Wellington's two
   landslide susceptibility layers.
3. Confirm the licence position on layer 4069 with whoever advises on it before
   anything derived from it leaves the repository.
4. Chase modification records for Porirua, Lower Hutt and Upper Hutt, and for
   road, rail and quarry cuts anywhere. Without them the rebuild is a Wellington
   City product.
5. Decide the slope support length before any factor grid is built, and record
   the sensitivity of the zone areas to it. The recommendation above is 10 m for
   the natural slope factor and 1 m inside the modification polygons.

## Sources

- Kingsbury, P.A. (1995). *Earthquake induced slope failure hazard*, map sheets
  and booklets, WRC/PP-T-95/06 to WRC/PP-T-95/10, Wellington Regional Council.
  Index page:
  <https://www.gw.govt.nz/document/189/earthquake-induced-slope-failure-hazard-study-maps-and-booklets/>
- Brabhaharan, P., Hancox, G.T., Perrin, N.D. & Dellow, G.D. (1994). *Earthquake
  induced slope failure hazard study, Wellington Region: Study area 1 —
  Wellington City.* Works Consultancy Services contract report to WRC. Not
  located.
- Hancox, G.T., Dellow, G.D. & Perrin, N.D. (1994). *Earthquake induced slope
  failure hazard study, Wellington Region: Review of historical records of
  earthquake induced slope failures.* IGNS contract report. Not located.
- Brabhaharan, P. & Jennings, D.N. (1993). *Liquefaction hazard study, Wellington
  Region.* Cited by the booklets as the reason liquefaction-induced failures are
  excluded.
- Varnes, D.J. (1978). *Slope movement types and processes.* The failure
  classification the booklets use.
- Layer 4069 on Koordinates, CC BY-ND:
  <https://koordinates.com/layer/4069-wellington-region-earthquake-induced-slope-failure/>
- The same data over ArcGIS REST, which needs no Koordinates key:
  <https://services5.arcgis.com/n4qyP7iVOnJlCVth/arcgis/rest/services/WR_SlopeFailure/FeatureServer/0>
- WCC Earthmoving — Cut Areas, CC BY-ND 4.0, read by
  `landloss.io.readers.get_wcc_cut_areas`:
  <https://ttgroup.koordinates.com/layer/125307-wcc-earthmoving-cut-areas/>
- WCC Earthmoving — Fill Areas, no licence recorded, read by
  `landloss.io.readers.get_wcc_fill_areas`:
  <https://ttgroup.koordinates.com/layer/125311-wcc-earthmoving-fill-areas/>

Written 2026-09-23. Not yet reviewed or agreed with the project team.
