# Plan: face-based urban slope polygons and retaining wall candidates

## Context

The first pilot run of the urban slope chain (2 October 2026) built and ran end
to end, and showed that the way it finds ground that can fail does not stand
up. This plan replaces it. It is the plan a reviewer should read alongside
`src/scripts/landloss/hazard/landslide/status.md` and
`src/scripts/landloss/exposure/rw/status.md`; the build it changes is
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`.

What the pilot showed, each checked against the files the run wrote:

1. **The urban polygons are not tied to a published method.** Landslide step 6
   cuts the ground near buildings into patches of one slope band (0-10, 10-20,
   20-30, 30-45, 45-60, 60+ degrees) and one of eight aspect directions, at 1,
   3, 10 and 30 m, merges patches under nine cells and cuts any patch wider
   than 25 m across the slope into strips. The bands, the octants and the 25 m
   (the mean GNS wall segment length) were this build's own choices. Patch edges
   fall where the slope crosses a band edge, not at the crest or the toe of a
   face, so the polygons do not follow the contours.
2. **Step 7 splits and snaps every polygon to every candidate wall line.** The
   snapping moved neighbouring polygons' vertices independently, so 54,804
   pairs of 1 m polygons overlap by 16 ha in total, and the splitting cut the
   polygons at property boundaries, against the decision that only walls are
   split at boundaries.
3. **Walls were grouped through shared polygons.** One group chained 737 walls
   and 11,555 polygons under one draw, because any walls bounding the same
   polygon were treated as one wall.
4. **Most candidate walls were property boundaries with no step.** Every
   boundary on ground of 5 degrees or more was a candidate: 4,540 of 8,342
   lines. The step test now required (decided 2026-10-02, built) keeps 1,574.
5. **Steps 6 and 7 take 49 of the run's 67 minutes**, almost all of it in
   per-polygon Python loops: zonal statistics read one polygon at a time onto
   59,132 patches, and shapely splits and buffers one polygon at a time.

## The idea

**A face is the unit.** A face is a piece of ground between a crest (a convex
break in slope above it) and a toe (a concave break below it): a retaining
wall, a cut face, the batter of a fill, or a steep natural bank. Faces are
found once, from the 1 m DEM alone, and stored as a static layer. Both the
retaining wall candidates and the urban failure polygons are built from that
layer, so a wall and the ground it holds up come from the same object and
nothing has to be reconciled afterwards.

- A **wall candidate** is a face that is a sharp step: its toe-to-crest height
  is at least `MIN_WALL_HEIGHT_M` and it is steeper than its ground can stand
  unsupported at that height (phase 1, "Step or bank"). The GNS mapped walls,
  the property boundaries and road frontages, and the SLIDE cut and fill edges
  become **evidence** on that face (they raise or lower its probability of
  being a wall), not sources of lines of their own.
- A **failure polygon** is a face plus the ground that goes with it when it
  fails: a wedge behind the crest, and a runout zone below the toe. It is not
  split by property boundaries or by anything else.
- One wall is one face, so the wall group of step 9 is the face, and the
  grouping problem disappears.

The literature backs the unit. The earthquake failures observed in and around
Wellington's urban area, in 1942 and 2013, were mostly on cuts and fills
rather than natural slopes [downes_2001; van_dissen_2013], as are most of the
sites forecast to fail in a Wellington Fault earthquake [hancox_perrin_2010]
(`downes2001-F07`, `vandissen2013-F01`, `sr2010-012-F01`), and every
published Wellington susceptibility criterion for a cut is stated as an
overall angle and a height, crest to toe [grant_taylor_1964; kingsbury_1995;
hancox_brabhaharan_1995; nzgs_2025_torlesse], which is what a face carries and
a slope-band patch does not. LiDAR slope maps pick up most cut slopes along
roads, railways, quarries and other excavations in Wellington City, where the
1994 regional maps did not [hancox_2013_slope_types].

This keeps the agreed design: land on a slope fails in a large landslide,
through its wall, or by localised failure; a polygon with a wall fails with
the wall; fragilities are lognormal on PGV; the rate setting stands; the step
8 and step 9 machinery is kept.

## Literature review of phases 0 to 2 (2026-10-02)

Read against the GNS literature review in `temp/gns_review/` (finding ids in
brackets, `out/findings.csv`). What it changed in the phases below:

1. **The step test has a published basis.** "Steep enough to need retaining"
   is set by the steepest angle the face's ground stands at unsupported for its
   height, from NZGS Unit 7C.2 Figure 35 for rock [nzgs_2025_torlesse]
   (`nzgs2025-u7c2-F26`, checked against the page image on 2026-10-02), not by
   a slope threshold of this build's own. It is held as one lookup of eight
   fixed height bands by three ground groups (the lead asked for a few
   predetermined heights, 2026-10-02). Phase 1.
2. **A face carries its overall angle crest to toe, not its peak 1 m slope**,
   because that is the quantity every criterion above is written in. Phase 1.
3. **The ground map has to be fixed before the faces read it.** SLIDE's mixed
   fill classes make 71% of the pilot fill, so almost no face is on rock, the
   rock-cut factor almost never applies, and the wall probability on greywacke
   cuts is too high. The fill strength is one densifying shear-box sample; it
   is read by nothing yet, but the phase 3 wedge will read it. Phase 0, and
   the step 4 plan. The lead accepted all three ground map changes on
   2026-10-02.
4. **Rock cuts stand unsupported more often than steep implies.** Wellington
   greywacke cuts are commonly 55 to 75 degrees and many long-standing ones are
   unsupported (`nzgs2025-u7c2-F25`), as Nick Peters advised. The cover of soil
   and colluvium over the rock is usually under 1 m, 0.5 to 3 m on typical
   slopes and 5 to 10 m in old gullies [nzgs_2025_torlesse;
   hancox_2013_slope_types] (`nzgs2025-u7c2-F02`, `sr2013-058-F04`), so a tall
   cut is in rock for most of its height. Phase 2.
5. **Where the DEM is not LiDAR, there are no faces.** The 1 m LiDAR model is
   already "rather coarse" for a site-specific assessment
   [nzgs_2025_recognition] (`nzgs2025-u2-F23`), and a map should not be shown
   at a scale markedly finer than its data [de_vilder_2024]
   (`devilder2024-F28`); the 8 m contour model cannot locate a wall. Phase 0.
6. **Wall heights have a Canterbury analogue.** Of 2,991 Christchurch walls,
   54% retain under 1.5 m, 26% 1.5 to 2.5 m, 11% 2.5 to 3.5 m and 9% over
   3.5 m [anderson_2015] (`anderson2015-F05`), from a sample weighted to road
   walls and to walls over 1.5 m (`F02`, `F03`), so the residential share under
   1.5 m is likely higher. Phase 4.

How far to trust it: findings from the first review batch (the SR reports,
including SR2010/12, SR2013/58, SR2019/40 and SR2019/51) had no independent
check, so a number from them is read off the page before it becomes a
parameter (`temp/gns_review/README.md`, section 7). The NZGS units are drafts
for feedback and their numbers may change.

Phase 3 was reviewed in a second part on 2026-10-02. Its findings and
proposals are written into the phase itself, under each rule it changes:
segments along long faces, the wedge by face type, failure style and reach
angle, imminent ground to a repose line, and amplification by height and
setting.

## References relied on

Keys are in `doc/references.bib`.

| Key | Used for |
| --- | --- |
| `jasiewicz_stepinski_2013` | Geomorphons: classifying each DEM cell as flat, peak, ridge, shoulder, spur, slope, hollow, footslope, valley or pit. Shoulder is the crest and footslope the toe of a face |
| `townsend_2020` | GNS SLIDE: the manually mapped breaks in slope (top and bottom), cut slopes and fill bodies for Wellington City (over 1,600 fills and nearly 3,000 cuts in the central study area), used to test the detector and as evidence |
| `kingsbury_1995` | Section 4.4.2: a steep component controls the stability of the whole slope it sits on; a steep facet is expanded to the slope it occupies, with a runout allowance. The Kingsbury factors also stay as the localised fragility's rating |
| `nzgs_2025_torlesse` | Figure 35: maximum unsupported cut angle by weathering grade and height, the step test. Cover thickness, cut angles in Wellington, the sheared ground near the major faults. Draft |
| `grant_taylor_1964` | The stable angle-height envelope for Wellington greywacke, the sheared zone about 0.8 km wide west of the Wellington Fault, and in-situ weathered cover standing at 60 degrees to 9 m |
| `hancox_perrin_2010` | Brabhaharan et al. (1994) susceptibility classes by cut height and angle, as tabulated there; the primary is not held |
| `hancox_brabhaharan_1995` | Closely jointed greywacke cut steeper than 45 degrees and higher than 5 m has high to very high susceptibility |
| `brabhaharan_2018`, `hancox_2015` | Steep (over 50 degrees) unsupported cuts higher than 3 m fail at MM6 or more |
| `hancox_2013_slope_types` | LiDAR slope maps detect most cut slopes; cover thickness; the Wellington slope profiles (Tables 2 and 3) as a check on face heights and angles |
| `nzgs_2025_recognition` | The 1 m LiDAR model is coarse for site work; pre-1960 cuts and non-engineered fills as a sign of potential failure. Draft |
| `de_vilder_2024` | A map at a scale not markedly finer than its data |
| `anderson_2015` | Wall types, retained heights and performance by height in Canterbury, the analogue for wall heights |
| `monteith_2020`, `lyndsell_2019` | The Priscilla and Orchy Crescent fills: failure on the fill and rock contact, scarp up to 15 m, fill and colluvium strengths, as the check on the fill wedge |
| `brown_larkin_2005` | A Wellington hillside fill failing on its fill and rock interface; best-estimate fill strength |
| `nzgs_mbie_2017` | Module 6, earthquake resistant retaining wall design: the active wedge behind a retained height, the width of ground that goes with a failed wall |
| `de_vilder_2022` | Reach angle against volume by failure style (dry debris avalanche, fill flow slide): the runout below the toe |
| `hunter_fell_2003` | Travel distance of failures in constructed (cut and fill) and natural soil slopes, the primary behind de Vilder's fill relation |
| `massey_2020` | Volume from area, for the depth of the larger faces |
| `brabhaharan_2018` | Crest amplification factors by cut height and ridge or terrace setting (Tables 7.6 to 7.8); earthquake failures concentrated near crests |
| `de_vilder_2024` | Retrogression screened by an angle of repose from the slope base, the imminent band |
| `hancox_brabhaharan_1995` | SH58 cuts forecast to have 10 to 1,000 m³ failures at MM8 to MM9, the segment volume; the Sawmill cracks and repair |
| `kaiser_2014` | Measured Port Hills amplification, the upper check on the factor |
| `alvioli_2016` | Slope units, kept for the large models only |

## Phases

### Phase 0 — Prerequisites

- [ ] **One extent for every step.** Landslide step 3 snaps its extent outward
      and step 4 uses the pilot box, so 9,144 pilot candidates fell outside
      the ground map and took no material. Every step reads its extent from one
      function, because a configurable default is resolved in one place:
      `run_extent(name)`, phase 0 of
      `.agents/plans/running-per-territorial-authority.md`, which this phase
      shares.
- [ ] **Vectorised zonal statistics.** One helper in
      `landloss.common.utils.terrain` that rasterises the polygons once to a
      label grid and reduces each raster by `np.bincount` (mean, max, min,
      count), replacing the per-polygon reads. Step 1 already sums per slope
      unit this way. Expected to take step 6's attribute reading from about
      25 minutes to seconds over the pilot.
- [ ] **A DEM source mask.** Step 3 writes, beside the 1 m DEM, which cells are
      LiDAR and the survey year of each (L-12). Faces are found only on LiDAR
      cells; elsewhere the faces layer is empty and says so, and the wall
      chain reports the share of claims with no LiDAR rather than silently
      finding no walls there [de_vilder_2024; nzgs_2025_recognition]. The
      survey year is carried onto each face, so a wall built after the flight
      is known to be missing.
- [ ] **Ground map fixes the faces read** (step 4 plan, phase 2):
  - SLIDE's mixed fill classes mapped to their natural material, with fill
    recorded as the modification, so that a cut through "Mixed fill/rock"
    reads as a rock cut and the Kingsbury geology factor reads the natural
    ground [townsend_2020];
  - the fill strength read from the GNS analysis set for Wellington fill
    rather than from one densifying shear-box sample [monteith_2020;
    lyndsell_2019];
  - the sheared ground within about 0.8 km west of the Wellington Fault marked
    `rock_crushed` [grant_taylor_1964; nzgs_2025_torlesse].

  All three accepted by the lead on 2026-10-02; the step 4 plan sets out the
  evidence. The step test does not read the strength (phase 1); the phase 3
  wedge will.

### Phase 1 — The static faces layer

A new script, `hazard/landslide/static_data_gen/gen_faces.py`, with the
library in `landloss.hazard.landslide.faces`.

- [ ] **Step height raster.** At every 1 m cell, the rise across 3 m against
      the rise across 9 m along the downhill direction, `(3 x short - long) /
      2`: the estimator already used for property boundaries
      (`landloss.exposure.rw.lines.step_height_m`), here as a raster. Zero on
      an even hillside; the height of a step at the cell.
- [ ] **Geomorphons** on the 1 m and 3 m DEMs, with a lookup distance tried at
      10, 20 and 50 m, written as class rasters. Implemented in numpy in
      `terrain` (eight line-of-sight directions), checked against
      WhiteboxTools' `Geomorphons` on a test tile so no dependency is added.
- [ ] **Faces.** Connected cells between a shoulder and a footslope, with the
      crest line traced along the shoulder cells and the toe line along the
      footslope cells. Each face carries:
  - its height, crest minus toe elevation;
  - its **overall angle**, `atan(height / horizontal distance crest to toe)`,
    measured square to the contour; this is the angle every cut criterion
    below is written in [grant_taylor_1964; kingsbury_1995;
    nzgs_2025_torlesse], and on a 1 m grid the peak cell slope of a wall reads
    much steeper than the face it belongs to;
  - its mean and maximum 1 m slope, its length along the contour, its aspect,
    its peak step height, and the DEM survey year (phase 0);
  - its ground map material, modification and `ground_id` at the face's
    midpoint, the ground the step test reads.
- [ ] **Height band.** Each face is put once into one of eight fixed height
      bands, `FACE_HEIGHT_BANDS_M`, and everything downstream reads the band
      rather than a continuous rule (the lead, 2026-10-02: keep the height
      handling to a few predetermined heights). Every break comes from
      something the model already has to honour:

      | Band | Height (m) | Why the break is there |
      | --- | --- | --- |
      | 1 | 0.5 to 1.0 | `MIN_WALL_HEIGHT_M`; the small/medium costing break |
      | 2 | 1.0 to 1.5 | The Building Act consent exemption [nz_parliament_2004]; Anderson et al.'s first class [anderson_2015] |
      | 3 | 1.5 to 2.5 | The medium/large costing break; Anderson et al. |
      | 4 | 2.5 to 3.5 | Anderson et al. |
      | 5 | 3.5 to 6 | NZGS Figure 35 [nzgs_2025_torlesse] |
      | 6 | 6 to 10 | NZGS Figure 35 |
      | 7 | 10 to 16 | NZGS Figure 35 |
      | 8 | over 16 | Above Figure 35; Grant-Taylor's envelope begins about here [grant_taylor_1964] |

      Below band 1 a face is a bank whatever its angle. The costing size class
      and Anderson et al.'s fragility classes are both unions of bands, so no
      re-binning happens later. The continuous height is still written, for
      the checks.
- [ ] **Step or bank: one lookup.** A face is a **step**, a wall candidate,
      where its overall angle exceeds the angle in `STEP_ANGLE_DEG[group][band]`,
      and a **bank** otherwise. Steps can sit inside banks (a wall in a slope);
      that is the only nesting left. The ground map's materials fall into
      three groups, so the whole test is 24 numbers in one table in
      `landloss.hazard.landslide.faces`, and it reads no strength value:

      | Group | Materials | Bands 1 to 5 (to 6 m) | Band 6 (6 to 10 m) | Bands 7 and 8 (over 10 m) |
      | --- | --- | --- | --- | --- |
      | Soil-like | every fill, `colluvium`, `loess`, `alluvium`, `reclamation`, `rock_crushed` | 35° | 35° | 35° |
      | Weak rock | `rock`, `rock_hw_cw`, `unknown` | 45° | 45° | 34° |
      | Stronger rock | `rock_uw_mw` | 53° | 45° | 34° |

  - **The rock rows are NZGS Unit 7C.2 Figure 35** (Hawley et al. 1977;
    Mahoney 1975), the maximum unsupported cut angles near Wellington housing
    [nzgs_2025_torlesse] (`nzgs2025-u7c2-F26`, checked against the page image
    on 2026-10-02): completely and highly weathered 1 on 1 to 10 m and 2 on 3
    to 16 m; moderately weathered 4 on 3 to 6 m. The degree conversions are
    ours. `rock_uw_mw` takes the moderately weathered row, the conservative
    end of its class; Figure 35's 63° and 76° for slightly weathered and fresh
    rock wait on a weathering grade the ground map does not carry. Band 8
    keeps the 10 to 16 m angle; Grant-Taylor's envelope and NZGS Figure 36 are
    the check on tall faces, not the test, because most house-lot cuts fall
    below them (`granttaylor1964-F04`). A face off the ground map is tested
    as weak rock.
  - **The soil-like 35° is judgement**, a round number inside the published
    friction angles for this ground (Pender's highly to completely weathered
    greywacke 27 to 36° [nzgs_2025_torlesse], compacted fill 32 to 42°
    [brown_larkin_2005; monteith_2020], the buried colluvium under the Orchy
    fill 24 to 28° [lyndsell_2019; monteith_2020]) and at the floor of Figure 35
    (34°). Crushed rock joins this group because Figure 35 has no row for it
    and Grant-Taylor reduces stable angles by 5 to 10° for jointing
    [grant_taylor_1964] (`granttaylor1964-F25`), which takes the weak rock
    45° to about 35°. Grant-Taylor's in-situ weathered cover standing at 60°
    to 9 m (`granttaylor1964-F18`) is an upper bound for undisturbed cover,
    not for cut or placed ground, and is not used.

  A face over the angle is a wall or an unsupported oversteep cut; which of
  the two is phase 2's evidence, not this test. The thresholds others have
  used are written onto each face as flags, for the checks and the Kingsbury
  rating, not as tests: steeper than 50° and higher than 3 m, the cut that
  fails at MM6 [brabhaharan_2018; hancox_2015] (`brabhaharan2018-F03`,
  `sr2015-016-F05`); steeper than 45° and higher than 5 m, high to very high
  susceptibility in closely jointed greywacke [hancox_brabhaharan_1995]
  (`sr1995-005-F07`, a scan, not machine-checked).
- [ ] No slope cut-off: a gentle face is still a face, with a low rating.
- [ ] Written per territorial authority to the versioned store
      (`landloss.io.versioned_store.save_hazard`), tiled with an overlap margin
      so the 1 m grid fits in memory, with a reader. It reads only the LINZ
      DEM, its source mask and the ground map, so it is rerun when the DEM or
      the ground map changes, not with the pipeline.
- [ ] Figures: the faces over the hillshade and contours, coloured step or
      bank, and the QGIS project's layers, for the lead's review before
      phase 2.

### Phase 2 — Retaining wall candidates from the faces

Exposure step 6 (`gen_wall_lines.py`) is rewritten on the faces layer.

- [ ] A wall candidate is a step face; its line is the face's centreline, its
      retained height the face height, its position `fill` where the face
      holds up a platform above it and `cut` where it holds up a slope. A
      cut-and-fill platform has both, a cut wall at its back and a fill wall
      at its front, with houses and services straddling the contact
      [monteith_2020] (`sr2019-051-F09`); each is its own face.
- [ ] Evidence attached to each candidate:
  - a GNS mapped wall within the snap tolerance, one-sided because GNS mapped
    only walls visible from above and only in Wellington City
    [townsend_2020];
  - a property boundary or road frontage along it;
  - a SLIDE cut slope or fill body edge along it [townsend_2020];
  - its ground map material and modification. **Rock lowers it**: greywacke
    cuts commonly stand at 55 to 75° and many long-standing ones are
    unsupported [nzgs_2025_torlesse] (`nzgs2025-u7c2-F25`). Because the cover
    over the rock is usually under 1 m, and 0.5 to 3 m on typical slopes
    [nzgs_2025_torlesse; hancox_2013_slope_types] (`nzgs2025-u7c2-F02`,
    `sr2013-058-F04`), the rock factor applies to a cut face in height band 4
    or above (over 2.5 m, judgement within that range) and not to a shorter
    one, which is in the cover and needs a wall to stand steep.
    Crushed rock near the Wellington Fault takes no rock factor
    [grant_taylor_1964; nzgs_2025_torlesse] (`granttaylor1964-F16`,
    `nzgs2025-u7c2-F08`);
  - how far the face's angle exceeds its `STEP_ANGLE_DEG` entry: a face far
    over it is more likely held up by something;
  - its distance to a building;
  - the age bin of its claim property from rw step 8, once read onto the
    lines: suburb-scale earthworks followed the earth-moving machinery of the
    1950s [lyndsell_2019] (`sr2019-040-F28`), earthfill standards did not
    exist until the mid-1970s [monteith_2020] (`sr2019-051-F06`), and pre-1960
    cuts and non-engineered fills are flagged as a sign of future failure
    [nzgs_2025_recognition] (`nzgs2025-u2-F09`). The age enters `p_poor` and
    the fill's engineered or uncontrolled class first; whether it enters
    `p_wall` waits on the claim report extraction (**T-50**).
- [ ] A GNS mapped wall with no step under it stays a candidate, classed
      small, because the 1 m grid cannot resolve a wall under about half a
      metre (I-03).
- [ ] The wall line is split at property boundaries for the loss table
      (several `rw_id` on one wall); the face is not.
- [ ] `gen_wall_probability.py` puts a probability on each candidate from the
      evidence, replacing the per-source priors. Every weight is `BETA_`
      judgement until **T-50**; the literature gives the direction of each
      piece of evidence, not its size.
- [ ] Each wall carries its face's `height_band` (phase 1). The three costing
      size classes are bands 1, 2 and 3, and 4 to 8; Anderson et al.'s height
      classes (below 1.5, 1.5 to 2.5, 2.5 to 3.5, above 3.5 m)
      [anderson_2015] are bands 1 and 2, 3, 4, and 5 to 8. Nothing downstream
      bins a height again.

### Phase 3 — Failure polygons from the faces

Landslide steps 6 and 7 are replaced by one step on the faces layer. Reviewed
against the literature on 2026-10-02 (finding ids in backticks,
`temp/gns_review/out/findings.csv`). Each rule below says what it rests on;
**proposals for the lead** are marked as such, and numbers that are ours (a
conversion, a reading off a figure, a judgement) say so.

**One footprint in three parts, not a circle (A-07 retired for the urban
population).** A failure on a face is the face, the ground behind its crest
that goes with it, and the ground below its toe that the debris covers.
Slides have a cracked head behind a steep headscarp and flank scarps that lose
height downslope; flows are elongate, longer than they are wide, with little
upslope cracking [nzgs_2025_recognition] (`nzgs2025-u2-F03`, `F04`, `F05`).
So the footprint is built along and across the face from its own geometry,
not as a circle on a centre. Earthquake failures concentrate near crests, 56%
in the upper quartile of slopes at Northridge [brabhaharan_2018]
(`brabhaharan2018-F19`), which is where the evacuated part sits.

- [ ] **One failure polygon per face segment**, carrying the face's id and a
      segment number; no snapping, no splitting at property boundaries.
      **Proposal for the lead: segment long faces along the contour.** A face
      can run hundreds of metres along a road cut, and no failure in the
      record is that long:
  - Wellington cut failures in the June 1942 earthquake and the 1976, 2006
    and 2008 storms were about 10² to 10⁴ m³ [hancox_2013_slope_types]
    (`sr2013-058-F12`, checked against the page on 2026-10-02);
  - every SH58 cut steeper than 1V:1H was forecast to be "affected by small
    to moderate-sized failures (10-1,000 m³)" at MM8 to MM9, not to fail
    whole [hancox_brabhaharan_1995] (`sr1995-005-F08`, checked against the
    scan);
  - most Port Hills 2011 failures were under 100 m³ (`sr2015-016-F18`).

  The segment length is **ours**: a face is cut along the contour wherever
  the evacuated volume of the run so far (below) reaches
  `BETA_FACE_SEGMENT_VOLUME_M3`, proposed as 1,000 m³ (the top of the SH58
  forecast and the middle of the Wellington record), with no segment shorter
  than one face height. A short face stays one segment. Without this, one
  polygon on a 200 m wall fails the whole wall at once, where Canterbury
  walls often collapsed only in part (`anderson2015-F24`), and the anchoring
  has no stable unit (anchoring plan, question 1). This is the one exception
  to "no splitting" above, and it cuts along the face only.
- [ ] **Evacuated ground, by face type.** The face, plus a band behind the
      crest whose width depends on what holds the face up.
  - **A wall (a step face with a wall drawn), cut or fill:** the active
    wedge behind the retained height, `H x tan(45 - phi'/2)`
    [nzgs_mbie_2017], with phi' the friction angle of the retained ground.
    A fill wall reads the fill's phi' 42° from the GNS analysis set, which
    gives 0.45 H [monteith_2020] (`sr2019-051-F14`); this is the strength the
    lead accepted for the ground map on 2026-10-02. Brown and Larkin's 32°
    low case gives 0.55 H [brown_larkin_2005]. A cut wall reads the cover's
    phi' from the ground map. The depth is the retained height at the wall,
    tapering to zero at the back of the wedge, as before.
  - **A fill batter with no wall (a fill bank): proposal for the lead,
    0.45 H** (the same wedge on the fill's phi'), with 0.25 H and 0.65 H as
    the low and high cases. The friction angle alone cannot set this width.
    Wellington fills fail on the fill and rock contact, through the buried
    colluvium [brown_larkin_2005; lyndsell_2019; monteith_2020], and the slip
    surface follows that contact rather than a Coulomb plane. At Orchy the
    modelled surface runs mainly through the weak colluvium at the fill base,
    "before extending to behind the break in slope" at the top
    (`sr2019-051-F23`, checked against the page). At Priscilla it starts on a
    steep section of the fill and rock interface (`sr2019-051-F22`).
    - The low case: read off the Priscilla CS2 pseudo-static RS2 plot at
      SRF 1 (PDF page 143, **our reading** on 2026-10-02), the moving layer
      is 5 to 8 m thick on a slope about 24 m high and about 26° overall, and
      the displaced zone starts about 6 m behind the fill crest, about
      0.25 H.
    - The high case: the colluvium's phi' 23.7° (`sr2019-051-F15`) as a
      Coulomb wedge gives 0.65 H. It is an upper bound, because the colluvium
      lies under the fill, not behind its crest.
    - The handoff asked for a test against the 2013 Priscilla failure itself
      (a scarp up to 15 m below Nos 35, 37 and 39; `sr2019-051-F08`, checked
      against the page). The report cannot support it, because it gives no
      plan dimensions behind the crest. GNS holds pre- and post-modification
      DEMs of the site (`sr2019-051-F39`), which would.

    The depth is the fill thickness where the ground map has one, otherwise
    the volume-area relation (A-06).
  - **A cut or natural bank with no wall:** the face plus the headscarp band
    of **T-44** (half a metre, or a metre on slopes over 30°), as the build
    plan had it. The evidence is cracking, not evacuation:
    - tension cracks 150 to 200 mm wide above the Sawmill batter failure on
      SH58 (`sr1995-005-F19`, `F21`, `sr2013-058-F22`);
    - small failures over the following nine months kept over-steepening
      the top of the failure area (`sr1995-005-F18`);
    - crest cracking in the Port Hills (`sr2015-016-F19`, `F20`).

    None of them gives a distance, so T-44 stays a judgement band, and the
    ground beyond it goes to imminent (below). The depth is the cover
    thickness: usually under 1 m, 0.5 to 3 m on typical Wellington slopes and
    5 to 10 m in old gullies [nzgs_2025_torlesse; hancox_2013_slope_types]
    (`nzgs2025-u7c2-F02`, `sr2013-058-F04`). Kaikōura failures in greywacke
    were mostly 1 to 10 m deep (`nzgs2025-u7c2-F34`).
- [ ] **Failure style per face**, which picks the runout relation.
      **Proposal for the lead:**

      | Face | Style | Reach angle relation |
      | --- | --- | --- |
      | Cut or natural bank, rock or cover, with or without a wall | Dry debris avalanche | de Vilder et al. Figure 2.3, dry, below 100,000 m³ |
      | Fill, with or without a wall | Fill flow slide | de Vilder et al. Figure 2.6, fill flow slides |

      Wellington greywacke slopes most likely fail as debris avalanches
      [de_vilder_2022] (`sr2019-038-F15`). Fills take the flow-slide
      relation even in an earthquake. Failures of New Zealand urban fill
      slopes "typically do not occur during or immediately after earthquake
      shaking", but later, as water enters the cracks the shaking opened
      [brown_larkin_2005; monteith_2020] (`sr2019-051-F07`, checked against
      the page). The as-built Priscilla and Orchy fills move 0.03 and 0.07 m
      drained but about 2.2 m saturated under the 2,500-year record
      (`sr2019-051-F20`). So a fill that fails is a wet fill. If the lead
      agrees, this settles the open decision on whether a fill in an
      earthquake takes the dry relation or the flow-slide one.
- [ ] **Inundated ground: the reach angle from the crest (replaces A-08).**
      H and L are both measured from the crest of the source to the toe of
      the deposit [hunter_fell_2003; de_vilder_2022] (`hunter2003-F01`,
      `sr2019-038-F01`, `mcdougall2017-F01`). So the deposit toe is where a
      line from the face's crest, dipping at `atan(H/L)`, meets the ground
      below. It is traced down the DEM along the face's fall line, which
      handles a toe on sloping ground without Hunter and Fell's α2
      substitution (`hunter2003-F11`, `F24`). Both relations were checked
      against the figure images on 2026-10-02:
  - **Dry debris avalanches:** `log(H/L) = -0.033 log(V) + 0.0315`, R² 0.113,
    N 144 (`sr2019-038-F03`, Figure 2.3). H/L is 0.92 at 100 m³, 0.86 at
    1,000 m³ and 0.79 at 10,000 m³ (our evaluation, `F04`).
  - **Fill flow slides:** `log(H/L) = -0.090 log(V) - 0.148`, R² 0.299
    (`sr2019-038-F20`, Figure 2.6, where it is printed without the
    logarithms, `F21`). H/L is 0.47 at 100 m³, 0.38 at 1,000 m³ and 0.31 at
    10,000 m³ (our evaluation). The two Wellington flow slides on the figure
    plot at about 0.27, near 3,000 to 5,000 m³, below the median (our
    reading).

  What the relations give, in face heights beyond the toe on flat ground
  (**ours**, `L/H - cot(face angle)` at the median):

  | Failure | Face | Reach beyond the toe |
  | --- | --- | --- |
  | Dry, 1,000 m³ | 45° | 0.2 H |
  | Dry, 1,000 m³ | 60° | 0.6 H |
  | Dry, 1,000 m³ | vertical wall | 1.2 H |
  | Fill flow slide, 1,000 m³ | 35° batter | 1.2 H |

  - A dry failure off a bank flatter than about 40° deposits on the face
    itself and leaves no inundated ground below the toe. Hunter and Fell saw
    the same for small slides on unconfined paths (`hunter2003-F25`).
  - V is the segment's evacuated volume. The dry relation barely depends on
    it (exponent -0.033), so an error in volume hardly moves a cut's runout.
  - The fixed geometry takes the median, the 50% exceedance line
    (`sr2019-038-F02`). The scatter is about 0.075 in log10 for dry failures
    and 0.098 for fills (`F05`, `F24`, **ours**, measured off the plotted
    lines), kept for a later draw.
  - The inundated strip is as wide as the segment. Debris from a gully
    orifice spreads as a lobe (`nzgs2025-u2-F04`), but no width ratio is
    given.
  - The strip is clipped at the next building outline or road, because
    debris from a cut behind a house stops at the house. Hunter and Fell
    found that type 1 cut slides obstructed by buildings plotted at or above
    the trend, so they ran shorter (`hunter2003-F13`).
  - Fill faces in gullies (confined paths) run significantly farther than
    unconfined ones (`hunter2003-F26`). The median fill line already
    includes gully cases, so no extra factor is proposed.
  - **Why not Hunter and Fell's own cut relation:** their cut fits are on
    Hong Kong weathered granite and volcanic soils, with the trigger not
    stated (`hunter2003-F05`, `F12`), and the fit they recommend for type 1
    cuts is in effect a fit to all cuts (`F40`). They are the check instead,
    with their loose-fill mean H/L of 0.405 (SD 0.094, 50 to 10,400 m³;
    `F14`) set beside de Vilder's fill line. Hunter and Fell's Table 2 sign
    typo and Figure 12 exponent typo (`F37`, `F38`) do not touch the
    relations used here.
- [ ] **Imminent ground: regression to the angle of repose from the toe
      (revises A-10; T-45). Proposal for the lead.** GNS planning guidance
      screens retrogression as land above a slope within an angle of the
      slope base. The angle reflects the angle of repose, because a slope
      steeper than its angle of repose may fail back to it [de_vilder_2024]
      (`devilder2024-F08`). The imminent band is the ground between the back
      of the evacuated band and the point where a line from the toe at the
      repose angle meets the ground behind the crest, and is never narrower
      than the T-45 band.
  - **The repose angle is ours:** 35° for every material, a judgement held
    as `BETA_REPOSE_ANGLE_DEG`. It is checked against the Cook Strait cliff
    that GNS judged to be near its natural angle of repose, 30 to 35°, under
    shaking (`sr2013-042-F19`, checked against the page).
  - **What it gives behind the crest** (**ours**,
    `H x (cot 35° - cot face angle)`): 1.4 H behind a vertical wall, 0.85 H
    behind a 60° cut and 0.43 H behind a 45° cut. A bank at 35° or less
    gets nothing from the rule and takes the T-45 band alone.
  - **The Auckland Unitary Plan rule is the upper check, not the rule.** It
    flags land within 2.5 H behind the base of a cliff (`devilder2024-F10`),
    a 21.8° line. As cited it is inconsistent about where the distance is
    measured from, so read the Unitary Plan text before relying on it.
  - **Imminent means land a future event could take within twelve months**,
    as EQC treated it for the claims GNS studied (`sr2018-027-F02`, checked
    against the page). Works on such land were a significant cost in most of
    those claims (`sr2018-027-F14`). The Sawmill repair on SH58 needed
    substantially more land above the cut than the failure took
    (`sr1995-005-F32`).
  - **Coherent slides that crack without evacuating fall in this band, not
    in evacuated.** They are about 10% of the landslides recognised after New
    Zealand earthquakes (`brabhaharan2018-F26`, `sr2015-016-F19`).
- [ ] **Topographic amplification by face height and setting. Proposal for
      the lead.** The placeholder (`amplification_factor` in
      `landloss.hazard.landslide.urban.geometry`) reaches its maximum of 1.5
      on any face at 60°, which amplifies every steep house-lot wall. The
      literature makes amplification a property of the slope the face sits
      on and of its height:
  - the proposed NZTA crest factors for cuts under 30 m are 1.0, 1.2 and 1.4
    on ridges at 0 to 15°, 15 to 30° and over 30°, and 1.0, 1.0 and 1.1 on
    terrace slopes [brabhaharan_2018] (`brabhaharan2018-F05`, `F06`, Tables
    7.6 and 7.7, checked against the text on 2026-10-02);
  - the lower-bound code factors match a 20% aggravation only for slopes
    over 13 m high and steeper than 17° (`brabhaharan2018-F23`, the
    criterion on PDF page 35).

  So a face reads 1.0 unless it is over 13 m high or on a ridge, and the
  factor applies to the evacuated part near the crest, where the
  amplification is (Table 7.8, `F07`). Ridge or terrace comes from the 100 m
  topographic position that step 3 already writes.
  - Measured amplification in the Port Hills ran higher: up to 1.5 to 4
    times in PGA inside a deforming area (`sr2015-016-F21`), and up to 6
    times in spectral ratio at a cliff edge whose PGA ratio was only 1.3
    [kaiser_2014] (`kaiser2014-F08`, `F09`). These came from weak motions on
    loess.
  - The gap between modelled and observed amplification is partly soil
    amplification (`brabhaharan2018-F22`), which the site class already
    carries.
  - The Monteith fill analyses left amplification out and put it at 1.2 to
    1.4 at slope tops (`sr2019-051-F35`), inside the ridge range.
- [ ] The Kingsbury rating per face, from its own slope, height, material,
      modification and groundwater [kingsbury_1995]. The height factor reads
      the face height rather than step 3's `face-height-10m` local relief,
      which this plan removes, and the slope factor reads the face's overall
      angle (phase 1).
- [ ] Step 8 and step 9 read the face polygons. Step 9 groups by face, so one
      wall is one draw, and a wall split into segments (above) is one draw
      per segment.

The review leaves four questions open, all for the lead:

1. the segment volume;
2. the fill bank width (0.25, 0.45 or 0.65 H);
3. the repose angle, and whether it varies by material;
4. whether the urban runout should also carry a probability of reaching
   beyond the median, as the risk literature does (`mcdougall2017-F05`,
   `F07`), rather than one fixed polygon.

### Phase 4 — Checks

- [ ] Detection against the GNS mapped walls: the share with a step face
      within 2 m (recall), which replaces the fixed 0.9 detection figure.
- [ ] Faces against the SLIDE breaks in slope and cut slopes and fill bodies
      in Wellington City: precision and recall of crests and toes.
- [ ] Face heights and overall angles against the surveyed Wellington slope
      profiles of Hancox et al. (2013), Tables 2 and 3
      [hancox_2013_slope_types], where the profiles fall in the pilot.
- [ ] Step faces by material and angle against NZGS Figure 36's surveyed
      Wellington cuts and Grant-Taylor's envelope, for the faces over 11 m
      [nzgs_2025_torlesse; grant_taylor_1964].
- [ ] The drawn wall heights against Anderson et al.'s Canterbury shares
      [anderson_2015] (54% under 1.5 m, 26% 1.5 to 2.5 m, 20% over 2.5 m), as
      a shape check only: their sample is weighted to road walls and to walls
      over 1.5 m, and Port Hills loess is not Wellington greywacke. A cluster
      just under 1.5 m is expected, the height the Building Act exempts from
      consent [nz_parliament_2004] and the one Nick Peters named.
- [ ] Face counts, heights and lengths by suburb, and against the 10^2 to
      10^4 m3 Wellington cut failures (`hancox_2013_slope_types`).
- [ ] Failure segments (phase 3) by volume against the 10^2 to 10^4 m3
      Wellington cut failures [hancox_2013_slope_types] (`sr2013-058-F12`)
      and the under-100 m3 Port Hills failures (`sr2015-016-F18`).
- [ ] Reach beyond the toe against the Wellington flow slides on de Vilder et
      al.'s Figure 2.6 [de_vilder_2022] and, for dry failures, against the
      Kaikōura inventory (`landloss.io.kaikoura`), measured crest to deposit
      toe as the relations are.
- [ ] The fill bank wedge against the pre- and post-failure terrain of
      Priscilla Crescent, if GNS will share its DEMs (`sr2019-051-F39`).
- [ ] The share of failure polygons on more than one property, against the
      local expectation that most earthquake failures stay on one
      (`.agents/context/land-damage-mechanisms.md`, A-15) and the evidence
      that gully fills and colluvium are where multi-property failures happen:
      one Wellington hillside fill runs beneath several lots
      [brown_larkin_2005] (`brown2005-F28`, `F29`), solifluxion colluvium
      fills old gullies about 10 m wide and 5 m deep
      [hancox_2013_slope_types] (`sr2013-058-F06`), and the Priscilla failure
      took three properties (`sr2019-051-F08`).
- [ ] The pilot rerun end to end, timed per step.

## What it removes

Landslide step 6 (`s6_urban_slope_candidates`) and step 7
(`s7_urban_slope_polygons`) as they stand: the slope bands, the octants, the
four scales, the 25 m strips, the splitting and snapping to wall lines, and
the terrain-break and boundary line sources in `landloss.exposure.rw.lines`.
Their figures and tests go with them. Steps 3, 4, 5, 8 and 9 stay, with step 9
grouping by face. Step 3's `face-height-5m` and `face-height-10m` local relief
layers go too once nothing reads them: local relief reads high on any
hillside, which is why the boundaries already moved to the step test.

## Speed

The static part of the run (steps 3 to 7 and the exposure steps) is
independent of the exposure world and the earthquake, and today `gen_all.py`
reruns it every time. The faces layer is computed once per territorial
authority and read thereafter; with the vectorised zonal statistics and no
per-polygon splitting, the expectation is that the pilot's 49 minutes in steps
6 and 7 falls to a few minutes, and a run of many earthquakes costs about half
a minute each over the pilot. To be measured in phase 4.

## Open decisions

- The geomorphon lookup distance, and whether the 3 m DEM or the 1 m one
  gives the cleaner crests and toes.
- **The step test** (phase 1): the eight height bands and the 24-entry
  `STEP_ANGLE_DEG` lookup, as proposed; in particular the soil-like 35°, the
  one entry that is judgement, and the stronger rock row, which waits on a
  mapped weathering grade (step 4 plan, phase 3).
- The rock factor from height band 4 (over 2.5 m), the cut height taken to be
  through the cover and into rock, from a published 0.5 to 3 m.
- Whether the faces layer lives in the shared versioned store or a local
  cache.
- **Phase 3, from the 2026-10-02 review, all proposals for the lead:**
  - segmenting long faces at `BETA_FACE_SEGMENT_VOLUME_M3`, proposed
    1,000 m³;
  - a wall's wedge on the retained ground's phi' (0.45 H for fill), and a
    fill bank's at 0.45 H with 0.25 and 0.65 H as the cases; a cut or natural
    bank with no wall keeps the T-44 band;
  - dry debris avalanche runout for cuts and natural banks and the fill flow
    slide line for every fill [de_vilder_2022];
  - imminent ground to a 35° repose line from the toe [de_vilder_2024],
    `BETA_REPOSE_ANGLE_DEG`;
  - amplification by face height and ridge or terrace setting
    [brabhaharan_2018] in place of the slope-driven placeholder.

Written 2026-10-02. Phases 0 to 2 reviewed against the literature on
2026-10-02, and phase 3 and the phase 4 checks it adds on 2026-10-02 (second
part of the review); the plan as a whole not yet reviewed by the lead.
