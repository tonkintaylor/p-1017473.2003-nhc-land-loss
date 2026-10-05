# Plan: free-face based urban slope polygons and retaining wall candidates

> **Phase 1 (seeds, free-face and bank) is superseded by
> `building-pip-pif-siz-slope-polygons.md`; phases 2-5 stand.**

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
   slope, so the polygons do not follow the contours.
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

## Terms

The lead found "face" confusing (2026-10-02), so the plan uses these terms
throughout, and the code takes the same names.

| Term | Meaning |
| --- | --- |
| **Slope element** (element) | A piece of ground between a crest above it and a toe below it, grown from one seed (phase 1). Every element is either a free-face or a bank. Elements never overlap |
| **Free-face** | An element steeper than its ground can stand unsupported at its height (the step test, phase 1): a retaining wall or an unsupported oversteep cut. Every free-face is a wall candidate (phase 2) |
| **Bank** | An element under that angle: ground that can stand on its own, such as a 3 m grassy batter at 30° on weak rock, where the test angle is 45°. Not a wall candidate, but it can still fail locally, so it has a polygon |
| **Polygon** | The evacuated ground of an element (or of a stack of elements): the ground that goes when it fails (phase 3). The imminent band behind it and the inundated ground below it are zones attached to the polygon, not part of it |
| **Stack** | A relation between elements, not between cells: elements one above another along the fall line, the toe line of the upper meeting the crest line of the lower, directly or across a bench narrower than the lower's width behind its crest. An excavated toe under a steep slope, a wall below a bank, terraces |
| **Height band** | One of eight fixed height classes an element is put into once, from its crest-to-toe height (phase 1) |

## The idea

**The slope element is the unit.** Elements are found once, from the 1 m DEM,
and stored as a static layer. Both the retaining wall candidates and the
urban polygons are built from that layer, so a wall and the ground it holds up
come from the same object and nothing has to be reconciled afterwards.

- **Elements are grown from seeds.** Each cell's ground group, from the ground
  map, sets the minimum angle and step its ground needs before it is a
  free-face. Cells that exceed it are seeds, and seeds grow out to their crest
  and toe in order of how far they exceed it, so the strongest free-face
  claims its ground first (phase 1).
- A **wall candidate** is a free-face: its height is at least
  `MIN_WALL_HEIGHT_M` and its overall angle is steeper than its ground can
  stand unsupported at that height. The GNS mapped walls, the property
  boundaries and road frontages, and the SLIDE cut and fill edges become
  **evidence** on that free-face (they raise or lower its probability of being
  a wall), not sources of lines of their own (phase 2).
- A **polygon** is built from an element's own height, ground and the profile
  behind its crest, so a wall with level ground behind it takes a narrow
  wedge, and an excavated toe under a steep slope takes the slope above it
  (phase 3). It is not split by property boundaries or by anything else.
- One wall is one free-face, so the wall group of step 9 is the element, and
  the grouping problem disappears.

The literature backs the unit. The earthquake failures observed in and around
Wellington's urban area, in 1942 and 2013, were mostly on cuts and fills
rather than natural slopes [downes_2001; van_dissen_2013], as are most of the
sites forecast to fail in a Wellington Fault earthquake [hancox_perrin_2010]
(`downes2001-F07`, `vandissen2013-F01`, `sr2010-012-F01`), and every
published Wellington susceptibility criterion for a cut is stated as an
overall angle and a height, crest to toe [grant_taylor_1964; kingsbury_1995;
hancox_brabhaharan_1995; nzgs_2025_torlesse], which is what an element carries
and a slope-band patch does not. LiDAR slope maps pick up most cut slopes along
roads, railways, quarries and other excavations in Wellington City, where the
1994 regional maps did not [hancox_2013_slope_types].

This keeps the agreed design: land on a slope fails in a large landslide,
through its wall, or by localised failure; a polygon with a wall fails with
the wall; fragilities are lognormal on PGV; the rate setting stands; the step
8 and step 9 machinery is kept. The elements cover the wall and localised
failure; the large landslides keep their slope units [alvioli_2016] (step 5).

## Revision of 2026-10-02: the lead's review of the method

What the lead's review changed, and where:

1. **Terms.** "Face" is retired for free-face, bank, polygon and stack (Terms,
   above).
2. **Seeded growth replaces geomorphons.** Geomorphons at 10 to 50 m lookups
   are slow on a 1 m grid and blur a 1 m wall into its hillside. Elements are
   instead grown from seeds set by each cell's own ground and estimated height,
   ranked by the 3 m slope and stopped by grow angles, free-faces first and
   then banks (phase 1). Geomorphons are not built; they come back only
   as a comparison if the crests and toes land in the wrong places in stage D2.
3. **Elements partition the ground.** A wall in a slope is its own element,
   stacked between the bank above and below it, not nested inside one bank.
4. **A tall steep cut takes the slope above it.** A polygon's width behind the
   crest is set by rule, not by a pseudo-static calculation, and a free-face
   steeper than 50° and higher than 3 m takes the whole stack above it, to the
   first bench or ridge [kingsbury_1995; brabhaharan_2018] (phase 3).
5. **Polygons overlap only when they start in different places**, such as two
   gullies whose heads meet at a ridge; otherwise shared ground goes to the
   nearest crest (phase 3).
6. **Failure below raises the chance of failure above** (retrogression),
   carried as a conditional draw in step 9 (phase 3).
7. **Asperities are held in reserve**: stable ground that stops a polygon,
   added only if the toy or pilot examples show polygons running away
   (phase 3).
8. **The method is developed in three stages** before it is run at scale: toy
   terrain, real examples from the pilot, then the full pilot, each with
   figures for the report (Development, below).

## Literature review of phases 0 to 2 (2026-10-02)

Read against the GNS literature review in `temp/gns_review/` (finding ids in
brackets, `out/findings.csv`). What it changed in the phases below:

1. **The step test has a published basis.** "Steep enough to need retaining"
   is set by the steepest angle the element's ground stands at unsupported for
   its height, from NZGS Unit 7C.2 Figure 35 for rock [nzgs_2025_torlesse]
   (`nzgs2025-u7c2-F26`, checked against the page image on 2026-10-02), not by
   a slope threshold of this build's own. It is held as one lookup of eight
   fixed height bands by three ground groups (the lead asked for a few
   predetermined heights, 2026-10-02). Phase 1.
2. **An element carries its overall angle crest to toe, not its peak 1 m
   slope**, because that is the quantity every criterion above is written in.
   Phase 1.
3. **The ground map has to be fixed before the elements read it.** SLIDE's
   mixed fill classes make 71% of the pilot fill, so almost no element is on
   rock, the rock-cut factor almost never applies, and the wall probability on
   greywacke cuts is too high. The fill strength is one densifying shear-box
   sample; it is read by nothing yet, but the phase 3 wedge will read it.
   Phase 0, and the step 4 plan. The lead accepted all three ground map
   changes on 2026-10-02.
4. **Rock cuts stand unsupported more often than steep implies.** Wellington
   greywacke cuts are commonly 55 to 75 degrees and many long-standing ones are
   unsupported (`nzgs2025-u7c2-F25`), as Nick Peters advised. The cover of soil
   and colluvium over the rock is usually under 1 m, 0.5 to 3 m on typical
   slopes and 5 to 10 m in old gullies [nzgs_2025_torlesse;
   hancox_2013_slope_types] (`nzgs2025-u7c2-F02`, `sr2013-058-F04`), so a tall
   cut is in rock for most of its height. Phase 2.
5. **Where the DEM is not LiDAR, there are no elements.** The 1 m LiDAR model
   is already "rather coarse" for a site-specific assessment
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
segments along long elements, the wedge by element type, failure style and
reach angle, imminent ground to a repose line, and amplification by height and
setting. The rules the lead's review added (stacks, overlap, retrogression,
asperities) are marked as added on 2026-10-02 and are not yet reviewed against
the literature beyond what they cite.

## References relied on

Keys are in `doc/references.bib`.

| Key | Used for |
| --- | --- |
| `townsend_2020` | GNS SLIDE: the manually mapped breaks in slope (top and bottom), cut slopes and fill bodies for Wellington City (over 1,600 fills and nearly 3,000 cuts in the central study area), used to test the crests and toes and as evidence |
| `kingsbury_1995` | Section 4.4.2: slopes over 45° "were expanded to include the entire slope they occupy, including an allowance for downslope runout", because a steep component "will generally control the stability of the entire slope"; a small steep area high on a gentle slope takes a tear-drop shape; ground next to existing landslides is highly susceptible. The stack rule and the retrogression rule. The Kingsbury factors also stay as the localised fragility's rating |
| `nzgs_2025_torlesse` | Figure 35: maximum unsupported cut angle by weathering grade and height, the step test. Cover thickness, cut angles in Wellington, the sheared ground near the major faults. Draft |
| `grant_taylor_1964` | The stable angle-height envelope for Wellington greywacke, the sheared zone about 0.8 km wide west of the Wellington Fault, and in-situ weathered cover standing at 60 degrees to 9 m |
| `hancox_perrin_2010` | Brabhaharan et al. (1994) susceptibility classes by cut height and angle, as tabulated there; the primary is not held. Failures below an asset that remove its support ("under-failures") as a distinct path; 10 of 36 forecast sites are high cuts or natural slopes with low toe cuts, the excavated toe |
| `hancox_brabhaharan_1995` | Closely jointed greywacke cut steeper than 45 degrees and higher than 5 m has high to very high susceptibility |
| `brabhaharan_2018`, `hancox_2015` | Steep (over 50 degrees) unsupported cuts higher than 3 m fail at MM6 or more |
| `hancox_2013_slope_types` | LiDAR slope maps detect most cut slopes; cover thickness; the Wellington slope profiles (Tables 2 and 3) as a check on element heights and angles |
| `nzgs_2025_recognition` | The 1 m LiDAR model is coarse for site work; pre-1960 cuts and non-engineered fills as a sign of potential failure; crown cracks as a sign of retrogression. Draft |
| `de_vilder_2024` | A map at a scale not markedly finer than its data. An assessment must include landslides below a site that may fail retrogressively up into it, and toe excavation as a trigger; a susceptibility map bounded by the maximum retrogression and runout; the Auckland Unitary Plan's 1V:3H (18.4°) screening slope on soils other than recent sediments, the bank grow angle |
| `anderson_2015` | Wall types, retained heights and performance by height in Canterbury, the analogue for wall heights; crib wall failures that started in the slope above or below the wall, or in the adjacent unretained slope |
| `monteith_2020`, `lyndsell_2019` | The Priscilla and Orchy Crescent fills: failure on the fill and rock contact, scarp up to 15 m, fill and colluvium strengths, as the check on the fill wedge |
| `brown_larkin_2005` | A Wellington hillside fill failing on its fill and rock interface; best-estimate fill strength |
| `nzgs_mbie_2017` | Module 6, earthquake resistant retaining wall design: the active wedge behind a retained height, the width of ground that goes with a failed wall |
| `de_vilder_2022` | Reach angle against volume by failure style (dry debris avalanche, fill flow slide): the runout below the toe |
| `hunter_fell_2003` | Travel distance of failures in constructed (cut and fill) and natural soil slopes, the primary behind de Vilder's fill relation |
| `massey_2020` | Volume from area, for the depth of the larger elements |
| `brabhaharan_2018` | Crest amplification factors by cut height and ridge or terrace setting (Tables 7.6 to 7.8); earthquake failures concentrated near crests |
| `de_vilder_2024` | Retrogression screened by an angle of repose from the slope base, the imminent band |
| `hancox_brabhaharan_1995` | SH58 cuts forecast to have 10 to 1,000 m³ failures at MM8 to MM9, the segment volume; the Sawmill cracks and repair |
| `kaiser_2014` | Measured Port Hills amplification, the upper check on the factor |
| `alvioli_2016` | Slope units, kept for the large models only |
| `jasiewicz_stepinski_2013` | Geomorphons. No longer the method (revision of 2026-10-02); a comparison only if stage D2 needs one |

GNS SR2012/22 (`sr2012-022-F01`, no bib key yet) is the precedent for adding,
at a cell, the probability that a landslide starts there and the probability
that one moves in from upslope.

## Phases

The phases say what is built; the **Development** section after phase 0 says
the order it is proven in. Phases 1 and 3 are written first as library code
and proven on toy terrain (stage D1) and on pilot examples (stage D2) before
the full pilot (stage D3). Phase 2 is built after stage D2 has settled the
elements.

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
      25 minutes to seconds over the pilot. The elements are born as a label
      grid, so they use the same reduction directly.
- [ ] **A water mask.** The sea is masked with the LINZ NZ Coastlines and Islands
      Polygons (Topo 1:50k), layer 51153, read by `get_nz_coastline_polygons`:
      every cell outside the land polygons is no data before the elements are
      found. Decided 2026-10-04 and run in the stage D2 script; the pipeline step
      has to carry it, with the DEM source mask below.
- [ ] **A DEM source mask.** Step 3 writes, beside the 1 m DEM, which cells are
      LiDAR and the survey year of each (L-12). Elements are found only on
      LiDAR cells; elsewhere the elements layer is empty and says so, and the
      wall chain reports the share of claims with no LiDAR rather than
      silently finding no walls there [de_vilder_2024; nzgs_2025_recognition].
      The survey year is carried onto each element, so a wall built after the
      flight is known to be missing.
- [ ] **Ground map fixes the elements read** (step 4 plan, phase 2):
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

### Development — toy terrain, pilot examples, then the full pilot

Added 2026-10-02 at the lead's request. The growth and polygon rules of phases
1 and 3 hold several judgement numbers, and the way to set them is to watch
them work on ground whose answer is known. Each stage ends with figures for
the report and a stop for the lead's review. Figures go to
`report/hazard/landslide/slope-elements/fig/`; the scripts and their findings
documents go in `src/scripts/landloss/hazard/landslide/research/slope_elements/`,
and every `BETA_` value changed in a stage is recorded in that stage's
findings document with the reason.

- [x] **Stage D1 — toy terrain.** A small library module,
      `landloss.hazard.landslide.synthetic_terrain`, builds each case as a 1 m
      DEM with a ground group grid, with and without LiDAR-like noise at the
      survey's stated vertical accuracy. Each case's expected outcome is
      written down before it is run, in `toy_slope_elements.md`, and each case
      becomes a regression test in `tests/`. Built and run twice (the review of
      2026-10-02 is the second build): all 19 grids (the plan's 12 cases plus
      three added — case 13's soil-like batters, case 14's two gully heads on
      a ridge bent so they face 60° apart rather than case 6's 180°, and
      case 15's undulating hills, a negative control) pass on the noise-free
      run, on noise seed 7, and on all 30 noise seeds (570 of 570); findings,
      the `BETA_` changes made on the evidence, and the open points for the
      lead are in `toy_slope_elements.md`.
      The cases:

      | # | Case | What it should show |
      | --- | --- | --- |
      | 1 | A 2 m vertical retaining wall, level ground above and below | One free-face; polygon the level-ground wedge, about 0.45 H on fill (phase 3) |
      | 2 | The same wall with ground rising at 20° behind it | A free-face with a bank stacked on it; the polygon takes the wall's width only, and the bank is linked by retrogression |
      | 3 | An excavated toe: a 4 m cut at 60° at the foot of a 30° bank 15 m high, soil-like ground; then the same with a 2 m cut | 4 m: the cut carries the stack-dominant flag, so the polygon runs to the bank's crest. 2 m: the cut's width only, the bank linked by retrogression |
      | 4 | The same 4 m cut under a 15° slope | The slope is under the grow angle, so not an element: the cut's width only |
      | 5 | Two terraces, each with a 2 m wall, with a bench between them 1 m wide and then 8 m wide | Narrow bench: one stack. Wide bench: two separate polygons |
      | 6 | Two adjacent gullies whose steep heads meet at a ridge | Two elements in different catchments; their polygons may overlap at the ridge top and nowhere else |
      | 7 | A convex slope, rounding gradually over its crest | Where the crest lands; free-face or bank by its overall angle, not its peak cell |
      | 8 | A concave slope, easing gradually into its toe | Where the toe lands |
      | 9 | A road cut 200 m long and 4 m high | One element, cut into segments by volume (phase 3) |
      | 10 | A 1.5 m wall halfway down a 25° bank | Three stacked elements (bank, wall, bank), not one bank |
      | 11 | A 0.3 m step on level ground | No element |
      | 12 | A bank on weak rock at 40°, 3 m high, then 12 m high | A bank at 3 m (test angle 45°), a free-face at 12 m (34°) |

      Figures: one per case, a plan view over hillshade and a cross-section,
      each showing the elements (free-face or bank), the polygon, and the
      imminent and inundated zones at their true size
      (`fig_toy_slope_elements.py`).
- [x] **Stage D2 — real examples from the pilot.** Built 2026-10-03: twelve
      sites, a whole-pilot run and a GNS agreement count. No `BETA_` value was
      changed. Deviations: GNS holds no wall height, so a wall's height is the
      DEM-measured free-face height; the figure code is self-contained
      because the toy figure script was being refactored; the sites exposed a
      need for a water mask (the DEM's flat sea reads as seawall free-faces),
      which the lead decided on 2026-10-04 should be the LINZ coastline and
      which the script now applies, and a fill caveat (74% of the pilot ground
      map is fill until step 4 is rerun). The lead also confirmed that
      run-out over flat ground fans out, and the grow tolerance was settled at 3°. The urban/large overlap count is left to D3. Findings and the
      points for the lead are in `pilot_example_slope_elements.md`. The brief:
      eight to twelve sites in
      `SMALL_WLG_PILOT`, listed with the reason each was picked in the stage's
      `config.py`, covering: a GNS mapped wall of known height; a SLIDE fill
      body in a gully; a SLIDE cut slope; an excavated toe under a natural
      slope; two adjacent gullies; a long road cut; stacked terraces; a steep
      bank with no wall; and, if the pilot holds one, a mapped failure.
      Each site gets the stage D1 figure over the real hillshade and contours,
      with the GNS walls and SLIDE breaks in slope drawn for comparison
      (`fig_pilot_example_slope_elements.py`, findings in
      `pilot_example_slope_elements.md`). The judgement numbers are tuned
      here, not in stage D3.
- [x] **Stage D3 — the full pilot.** Built as step 12
      (`steps/s12_urban_slope_faces/`, 2026-10-04) over the pilot: the
      pipeline, the wall candidates' evidence (with each pif's property and
      the GNS-only wall candidates, 2026-10-05) and the checks that need only
      those layers, with counts and timings in its method file. The walls'
      probability, the fragility and the share of urban ground that fails in a
      realisation (the order of 1% check) are phase 4 of that step's plan. The
      literature's order of 1% is the number the first pilot missed by a
      factor of about 40.

### Phase 1 — The static slope elements layer

A new script, `hazard/landslide/static_data_gen/gen_slope_elements.py`, with
the library in `landloss.hazard.landslide.slope_elements`. Revised on
2026-10-02 to grow elements from seeds in place of geomorphons.

- [ ] **Step height raster.** At every 1 m cell, the rise across 3 m against
      the rise across 9 m along the downhill direction, `(3 x short - long) /
      2`: the estimator already used for property boundaries
      (`landloss.exposure.rw.lines.step_height_m`), here as a raster. Zero on
      an even hillside; the height of a step at the cell.
- [ ] **Each cell's own threshold.** From the ground map, the cell's ground
      group (soil-like, weak rock, stronger rock; off the map, weak rock).
      From its step height, an **estimated** height band. From the two, the
      cell's threshold angle, `STEP_ANGLE_DEG[group][estimated band]`, and its
      minimum step, `MIN_WALL_HEIGHT_M`. The estimate is a guess made before
      the element exists: the band that decides free-face or bank is measured
      after growth (below). The step height reads low on a tall bank whose
      rise is spread over more than 9 m, so the estimate under-reads tall
      elements; it only orders the growth, and stage D1 case 12 checks the
      final test recovers.
- [ ] **Exceedance and seeds.** A cell is eligible where its step height is at
      least its minimum step or its 3 m slope is over its threshold angle. Its
      exceedance is its **3 m slope** minus its threshold angle, in degrees,
      and that is the priority (the lead, 2026-10-02): the 3 m slope is
      steadier than the 1 m one on a noisy bank. The step height is a gate,
      not a second score, because mixing metres and degrees in one ranking
      needs a weight nobody has published. A short wall reads low on the
      3 m slope (under 20° across a 2 m wall), so it enters by the step gate
      and ranks low; the two-pass growth below keeps a bank from taking it.
      A seed is one connected patch of eligible cells.
- [ ] **Growth, strongest first, in two passes, stopped by grow angles (the
      lead, 2026-10-02).** Seeds grow by priority flood, the cell of highest
      exceedance taken first, so where two seeds compete the stronger claims
      the ground and the weaker stops against it. This is a marker-controlled
      watershed on the negated exceedance, `scipy.ndimage.watershed_ift` on
      an integer grid: no Python loop and no new dependency.
  1. **Free-face pass.** The free-face seeds grow only into cells whose 1 m
     slope is at least their own threshold angle less
     `BETA_FREE_FACE_GROW_TOL_DEG` (judgement, proposed 5°, so the rounded
     edge cells of a wall stay with it). So a wall grows up to where the
     ground eases off at its top, and stops there even if a 30° bank carries
     on above it.
  2. **Bank pass.** The cells left over with a 3 m slope of at least
     `BETA_GROW_ANGLE_DEG` seed and grow the same way, only into unclaimed
     cells at or over that angle. Proposed 18.4° (1V:3H), the slope above
     which the Auckland Unitary Plan flags land on soils other than recent
     sediments as possibly unstable [de_vilder_2024] (`devilder2024-F12`),
     held as judgement because it was written as a screening slope, not as a
     stopping rule. Ground under it is a bench, a platform or open gentle
     hillside, and is not an element.
  3. **Crest and toe.** Where growth stops, the boundary cell whose outside
     neighbour is higher is on the crest, the one whose outside neighbour is
     lower is on the toe, and the rest are the element's ends along the
     slope. A wall's crest is where the ground eases below its grow angle
     at the top, and its toe where it eases at the bottom.
  4. Growth also stops against another element (the cell is claimed), along
     the slope where a wall peters out (the step height under
     `MIN_WALL_HEIGHT_M` and the slope under the grow angle), and at the edge
     of the LiDAR (phase 0).

  So an excavated toe under a 30° slope becomes two elements, a free-face
  (the cut) with a bank stacked on it, and a 2 m wall halfway down a 25° bank
  becomes three (bank, wall, bank). The stack links say how they sit, and
  phase 3 says when the polygon climbs them.
- [ ] **Elements.** The grown label grid is the elements layer; each label is
      one element, with its crest and toe lines traced as in step 3 of the
      growth. Each element carries:
  - its height, crest minus toe elevation, measured on fall-line transects
    across it and taken as the median, with the maximum kept;
  - its **overall angle**, `atan(height / horizontal distance crest to toe)`,
    measured square to the contour; this is the angle every cut criterion
    below is written in [grant_taylor_1964; kingsbury_1995;
    nzgs_2025_torlesse], and on a 1 m grid the peak cell slope of a wall reads
    much steeper than the element it belongs to;
  - its mean and maximum 1 m slope, its length along the contour, its aspect,
    its peak step height, its seed exceedance, and the DEM survey year
    (phase 0);
  - its ground map material, modification and `ground_id`, taken as the
    majority over the element rather than at its midpoint, because SLIDE
    fill edges often sit on the element itself, with fill at the crest and
    natural ground at the toe.
- [ ] **Height band.** Each element is put once into one of eight fixed height
      bands, `HEIGHT_BANDS_M`, and everything downstream reads the band
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

      A grown region under 0.5 m high is dropped: it is not an element. The
      bands do four jobs: they pick the column of the step test (below); the
      costing size class is bands 1, 2 to 3, and 4 to 8; Anderson et al.'s
      fragility height classes are bands 1 to 2, 3, 4, and 5 to 8; and the
      rock factor in the wall probability applies from band 4 (phase 2). All
      are unions of bands, so no re-binning happens later. The continuous
      height is still written, for the checks.
- [ ] **Free-face or bank: one lookup** (confirmed by the lead as written,
      2026-10-02). An element is a **free-face**, a wall
      candidate, where its overall angle exceeds the angle in
      `STEP_ANGLE_DEG[group][band]`, and a **bank** otherwise. The ground
      map's materials fall into three groups, so the whole test is 24 numbers
      in one table in `landloss.hazard.landslide.slope_elements`, and it reads
      no strength value:

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
    the check on tall elements, not the test, because most house-lot cuts fall
    below them (`granttaylor1964-F04`). An element off the ground map is
    tested as weak rock.
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

  A free-face is a wall or an unsupported oversteep cut; which of the two is
  phase 2's evidence, not this test. The thresholds others have used are
  written onto each element as flags, for the checks and the Kingsbury rating,
  not as tests: steeper than 50° and higher than 3 m, the cut that fails at
  MM6 [brabhaharan_2018; hancox_2015] (`brabhaharan2018-F03`,
  `sr2015-016-F05`); steeper than 45° and higher than 5 m, high to very high
  susceptibility in closely jointed greywacke [hancox_brabhaharan_1995]
  (`sr1995-005-F07`, a scan, not machine-checked).
- [ ] **Gentle ground is not an element.** A cell becomes part of an element
      only by growing from a seed, and a seed needs a step or a slope over its
      threshold, so open gentle hillside carries no element. The earlier
      draft's "no slope cut-off" is withdrawn: the localised failures in the
      Wellington record are on cuts, fills and steep ground (The idea, above),
      and the natural hillside is the large models' (step 5).
- [ ] **Stack links.** For each element, the elements whose toe meets its
      crest, directly or across a bench, with the bench width. Read off the
      label grid by shifting each label one cell uphill along the fall line.
      Phase 3 decides which links make a stack.
- [ ] **Catchments.** Each element's upslope catchment, by D8 flow on the 3 m
      DEM, labelled by pointer doubling (each cell takes its downslope cell's
      label, repeated until stable, about log2 of the path length passes),
      so it stays vectorised. Written as a label raster; phase 3's overlap
      rule reads it.
- [ ] Written per territorial authority to the versioned store
      (`landloss.io.versioned_store.save_hazard`), tiled with an overlap margin
      so the 1 m grid fits in memory, with a reader. It reads only the LINZ
      DEM, its source mask and the ground map, so it is rerun when the DEM or
      the ground map changes, not with the pipeline.
- [ ] Figures: the elements over the hillshade and contours, coloured
      free-face or bank, and the QGIS project's layers, for the lead's review
      before phase 2 (stages D1 and D2).

### Phase 2 — Retaining wall candidates from the free-faces

Exposure step 6 (`gen_wall_lines.py`) is rewritten on the elements layer.

- [ ] A wall candidate is a free-face; its line is the free-face's centreline, its
      retained height the free-face height, its position `fill` where it
      holds up a platform above it and `cut` where it holds up a slope. A
      cut-and-fill platform has both, a cut wall at its back and a fill wall
      at its front, with houses and services straddling the contact
      [monteith_2020] (`sr2019-051-F09`); each is its own free-face.
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
    `sr2013-058-F04`), the rock factor applies to a cut free-face in height band 4
    or above (over 2.5 m, judgement within that range) and not to a shorter
    one, which is in the cover and needs a wall to stand steep.
    Crushed rock near the Wellington Fault takes no rock factor
    [grant_taylor_1964; nzgs_2025_torlesse] (`granttaylor1964-F16`,
    `nzgs2025-u7c2-F08`);
  - how far the free-face's angle exceeds its `STEP_ANGLE_DEG` entry: a free-face far
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
      (several `rw_id` on one wall); the free-face is not.
- [ ] `gen_wall_probability.py` puts a probability on each candidate from the
      evidence, replacing the per-source priors. Every weight is `BETA_`
      judgement until **T-50**; the literature gives the direction of each
      piece of evidence, not its size.
- [ ] Each wall carries its free-face's `height_band` (phase 1). The three costing
      size classes are bands 1, 2 and 3, and 4 to 8; Anderson et al.'s height
      classes (below 1.5, 1.5 to 2.5, 2.5 to 3.5, above 3.5 m)
      [anderson_2015] are bands 1 and 2, 3, 4, and 5 to 8. Nothing downstream
      bins a height again.

### Phase 3 — Failure polygons from the elements

Landslide steps 6 and 7 are replaced by one step on the elements layer. Reviewed
against the literature on 2026-10-02 (finding ids in backticks,
`temp/gns_review/out/findings.csv`). Each rule below says what it rests on;
**proposals for the lead** are marked as such, and numbers that are ours (a
conversion, a reading off a figure, a judgement) say so.

**One footprint in three parts, not a circle (A-07 retired for the urban
population).** A failure on an element is the element, the ground behind its
crest that goes with it, and the ground below its toe that the debris covers.
In the terms of this plan the first two are the polygon (the evacuated
ground); the imminent band behind it and the inundated ground below it are
zones attached to the polygon.
Slides have a cracked head behind a steep headscarp and flank scarps that lose
height downslope; flows are elongate, longer than they are wide, with little
upslope cracking [nzgs_2025_recognition] (`nzgs2025-u2-F03`, `F04`, `F05`).
So the footprint is built along and across the element from its own geometry,
not as a circle on a centre. Earthquake failures concentrate near crests, 56%
in the upper quartile of slopes at Northridge [brabhaharan_2018]
(`brabhaharan2018-F19`), which is where the evacuated part sits.

- [ ] **The width behind the crest by rule, not by a pseudo-static calculation
      (the lead, 2026-10-02).** The widths in "Evacuated ground, by element
      type" below are measured horizontally back from the crest, over
      whatever ground lies behind it. No Mononobe-Okabe or trial-wedge sum is
      used: at the shaking of a Wellington Fault event a pseudo-static wedge
      has no solution on most slopes, which says the slope is unstable but not
      how much of it goes. How far a failure climbs is set by the stack rule
      instead.
- [ ] **Stacks: a tall steep free-face takes the slope above it. Added
      2026-10-02; proposal for the lead.** Taking out the toe of a steep slope
      removes support for the ground above it, and the record says this is a
      common way for Wellington ground to fail:
  - Kingsbury used slopes over 45° as the prime indicator of very high
    susceptibility and zoned them "to include the entire slope they occupy,
    including an allowance for downslope runout", on the assumption that "if
    a slope contains an extremely steep component, then that will generally
    control the stability of the entire slope"; a small steep area high on a
    gentle slope took a tear-drop shape instead [kingsbury_1995] (section
    4.4.2, read from the Hutt Valley sheet's text on 2026-10-02);
  - 10 of the 36 sites forecast to fail along the bulk water pipelines are
    high cuts or natural slopes with low (about 6 to 10 m) toe cuts
    [hancox_perrin_2010] (`sr2010-012-F01`);
  - toe excavation is a listed trigger, often after a lag of years
    [de_vilder_2024] (`devilder2024-F24`).

  Kingsbury mapped regional slopes and would not have seen a garden wall, so
  the rule needs a height as well as an angle. It uses the flag phase 1
  already writes, `stack_dominant_cut`: steeper than 50° and higher than
  3 m [brabhaharan_2018; hancox_2015], the cut observed to fail from MM6
  shaking — a fixed geometric threshold computed once from the element's own
  angle and height, never a read of a realisation's demand. The rule, on the
  stack links of phase 1:
  1. A link makes a stack where the bench between the lower element's crest
     and the upper element's toe (ground under `BETA_GROW_ANGLE_DEG`) is
     narrower than the lower element's width behind its crest. A wider bench
     breaks the stack (stage D1 case 5).
  2. A free-face carrying the stack-dominant flag takes the whole stack
     above it: its polygon runs to the crest of the highest linked element.
     Every element is at least `BETA_GROW_ANGLE_DEG` steep, so this is
     Kingsbury's "entire slope", ending at the first bench, platform or
     ridge (case 3).
  3. Any other element takes only its own width behind its crest, even where
     that reaches into the element above (case 2). The element above is then
     linked to it by the retrogression rule (below), not swallowed by it.
  4. The runout below the toe (below) uses the height of the polygon, toe of
     the lowest to crest of the highest element in it, not the free-face's
     alone.

  A tall stack reaches ground the large-landslide models (slope units, step
  5) also claim. **Open:** whether the urban polygon gives way to the slope
  unit there, or the two are drawn independently and the loss counts the
  ground once. Stage D2 shows how often it happens.
- [ ] **Graded stack extent, held in reserve. Added 2026-10-03; proposal for
      the lead.** Rule 2 above takes the stack-dominant free-face's polygon
      unconditionally to the first bench, platform or ridge, reading
      Kingsbury's "entire slope" as all-or-nothing. His own text already
      draws a line short of that: "a small steep area high on a gentle
      slope" takes a tear-drop shape instead [kingsbury_1995], so the
      whole-stack reading only holds where the free-face is large against
      what sits above it, not whenever it is merely dominant. Held in
      reserve, not built, until stage D1 or D2 shows the binary rule over- or
      under-reaching a named case: each successive linked element above the
      free-face would also have to clear some fraction of its own margin
      over `BETA_GROW_ANGLE_DEG` (or its free-face threshold) to keep the
      climb going, stopping the polygon (a tear-drop) the first time an
      element above falls under it. This is a fixed geometric test, computed
      once like the flag itself, not a read of demand. No fraction is
      proposed; nothing in stage D1's cases yet needs one.
- [ ] **Polygons overlap only when they start in different places. Added
      2026-10-02; proposal for the lead.** Elements never overlap (phase 1),
      but a polygon reaches behind its crest, and two can reach the same
      ground. The rule:
  1. If the two elements' upslope catchments (phase 1) are disjoint, the two
     failures start in different places, such as two gullies whose heads meet
     at a ridge (case 6): both polygons keep the shared ground.
  2. Otherwise, as for neighbours along one slope or segments of one element,
     the shared ground goes to the element whose crest is nearest, so the
     polygons tile.
  3. Where two polygons keep shared ground and both fail in one realisation,
     step 9 counts the ground once.
- [ ] **Failure below raises the chance of failure above (retrogression).
      Added 2026-10-02; proposal for the lead.** Ground that loses its support
      from below is more likely to go:
  - a Level B assessment must include landslides below a site that may fail
    retrogressively up into it [de_vilder_2024] (`devilder2024-F15`), and a
    susceptibility map is bounded by the maximum distance a slope may
    retrogress (`devilder2024-F18`, no value given);
  - failures below an asset that remove its support are their own path
    [hancox_perrin_2010] (`sr2010-012-F17`); several Canterbury crib wall
    failures started in the slope below the wall or in the adjacent
    unretained slope [anderson_2015] (`anderson2015-F24`);
  - Kingsbury zoned ground next to existing landslides as highly susceptible
    [kingsbury_1995]; crown cracks behind a headscarp signal retrogression
    [nzgs_2025_recognition] (`nzgs2025-u2-F12`).

  How it enters: ground inside a stack's polygon already fails with the
  free-face at its foot (stacks, above). For a linked element above the
  polygon (a stack broken by a bench, or the first element over the limit),
  step 9 raises its failure probability when the element below it fails,
  `p_above | below fails = 1 - (1 - p_above) x (1 - BETA_RETROGRESSION_P)`.
  `BETA_RETROGRESSION_P` is judgement: the literature gives the direction and
  no size. The opposite direction, a failure above running out onto ground
  below, is the inundated zone (below), the second of the two probabilities
  GNS adds at a cell (`sr2012-022-F01`).
- [ ] **Graded retrogression probability, held in reserve. Added 2026-10-03;
      proposal for the lead.** `BETA_RETROGRESSION_P` is one flat number for
      every linked pair. The literature's direction — more support lost
      below, more likely to go above — scales with how much is removed and
      how close the ground above already sits to its own threshold, so a
      function of the lower polygon's height (or volume) and the upper
      element's angle margin over its own stability threshold is physically
      better founded than a constant. Held in reserve rather than built: the
      literature gives no magnitude for the flat number either, so a graded
      form adds flexibility, not evidence, until stage D2 or a validation
      dataset gives something to fit its shape against.
      `BETA_RETROGRESSION_P = 0.5` stands as the placeholder meanwhile.
- [ ] **Asperities, held in reserve. Added 2026-10-02.** Stable ground that
      should stop a polygon from growing: a rib or outcrop of strong rock near
      the surface, or another rigid feature. Two kinds of stop are already in
      the rules above (a bench wider than the wedge, and a catchment divide),
      so no asperity mask is built unless stages D1 or D2 show polygons
      running away: stacks running up whole hillsides, polygons far over the
      10² to 10⁴ m³ of the Wellington record (`sr2013-058-F12`), or the stage
      D3 failing share well over the literature's order of 1%. If needed, a
      `BETA_ASPERITY_SOURCES` mask is added to the growth and to the stack
      rule, starting from mapped `rock_uw_mw` at the surface; it is empty
      until then.
- [ ] **Phased growth, an alternative held in reserve. Added 2026-10-03;
      proposal for the lead.** A second way to stop the same runaway growth
      the asperity mask is reserved for, without needing a rock mask: grow in
      a small fixed number of distance-capped phases instead of one
      unbounded flood per pass, so an element cannot cross a long chain of
      only-just-qualifying ground on a uniform near-threshold slope. Phase 1
      grows as now but stops at a cumulative distance from its seed; later
      phases relax the cap (and optionally the angle) so a strongly
      exceeding patch still reaches as far as it does today, while a chain of
      marginal cells does not. Needs one new raster (cumulative distance from
      seed, one `scipy.ndimage` call) and a small fixed loop over phases, the
      same shape as today's two passes — no new architecture. Held in
      reserve alongside the asperity mask until stage D1 or D2 shows a
      uniform near-threshold slope actually producing a runaway bank or
      stack; built only then, and only if the asperity mask alone does not
      resolve it.
- [ ] **One failure polygon per element segment**, carrying the element's id and a
      segment number; no snapping, no splitting at property boundaries.
      **Proposal for the lead: segment long elements along the contour.** An element
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

  The segment length is **ours**: an element is cut along the contour wherever
  the evacuated volume of the run so far (below) reaches
  `BETA_SEGMENT_VOLUME_M3`, proposed as 1,000 m³ (the top of the SH58
  forecast and the middle of the Wellington record), with no segment shorter
  than one element height. A short element stays one segment. Without this, one
  polygon on a 200 m wall fails the whole wall at once, where Canterbury
  walls often collapsed only in part (`anderson2015-F24`), and the anchoring
  has no stable unit (anchoring plan, question 1). This is the one exception
  to "no splitting" above, and it cuts along the element only.
- [ ] **Evacuated ground, by element type.** The element, plus a band behind the
      crest whose width depends on what holds the element up.
  - **A wall (a free-face with a wall drawn), cut or fill:** the active
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
  - **A cut or natural bank with no wall:** the element plus the headscarp band
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
- [ ] **Failure style per element**, which picks the runout relation.
      **Proposal for the lead:**

      | Element | Style | Reach angle relation |
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
      line from the element's crest, dipping at `atan(H/L)`, meets the ground
      below. It is traced down the DEM along the element's fall line, which
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

  What the relations give, in element heights beyond the toe on flat ground
  (**ours**, `L/H - cot(element angle)` at the median):

  | Failure | Element | Reach beyond the toe |
  | --- | --- | --- |
  | Dry, 1,000 m³ | 45° | 0.2 H |
  | Dry, 1,000 m³ | 60° | 0.6 H |
  | Dry, 1,000 m³ | vertical wall | 1.2 H |
  | Fill flow slide, 1,000 m³ | 35° batter | 1.2 H |

  - A dry failure off a bank flatter than about 40° deposits on the element
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
  - Fill elements in gullies (confined paths) run significantly farther than
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
    `H x (cot 35° - cot element angle)`): 1.4 H behind a vertical wall, 0.85 H
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
- [ ] **Topographic amplification by element height and setting. Proposal for
      the lead.** The placeholder (`amplification_factor` in
      `landloss.hazard.landslide.urban.geometry`) reaches its maximum of 1.5
      on any element at 60°, which amplifies every steep house-lot wall. The
      literature makes amplification a property of the slope the element sits
      on and of its height:
  - the proposed NZTA crest factors for cuts under 30 m are 1.0, 1.2 and 1.4
    on ridges at 0 to 15°, 15 to 30° and over 30°, and 1.0, 1.0 and 1.1 on
    terrace slopes [brabhaharan_2018] (`brabhaharan2018-F05`, `F06`, Tables
    7.6 and 7.7, checked against the text on 2026-10-02);
  - the lower-bound code factors match a 20% aggravation only for slopes
    over 13 m high and steeper than 17° (`brabhaharan2018-F23`, the
    criterion on PDF page 35).

  So an element reads 1.0 unless it is over 13 m high or on a ridge, and the
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
- [ ] The Kingsbury rating per element, from its own slope, height, material,
      modification and groundwater [kingsbury_1995]. The height factor reads
      the element height rather than step 3's `face-height-10m` local relief,
      which this plan removes, and the slope factor reads the element's overall
      angle (phase 1).
- [ ] Step 8 and step 9 read the element polygons. Step 9 groups by element, so one
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

- [ ] Detection against the GNS mapped walls: the share with a free-face
      within 2 m (recall), which replaces the fixed 0.9 detection figure.
- [ ] Elements against the SLIDE breaks in slope and cut slopes and fill bodies
      in Wellington City: precision and recall of crests and toes.
- [ ] Element heights and overall angles against the surveyed Wellington slope
      profiles of Hancox et al. (2013), Tables 2 and 3
      [hancox_2013_slope_types], where the profiles fall in the pilot.
- [ ] Free-faces by material and angle against NZGS Figure 36's surveyed
      Wellington cuts and Grant-Taylor's envelope, for the elements over 11 m
      [nzgs_2025_torlesse; grant_taylor_1964].
- [ ] The drawn wall heights against Anderson et al.'s Canterbury shares
      [anderson_2015] (54% under 1.5 m, 26% 1.5 to 2.5 m, 20% over 2.5 m), as
      a shape check only: their sample is weighted to road walls and to walls
      over 1.5 m, and Port Hills loess is not Wellington greywacke. A cluster
      just under 1.5 m is expected, the height the Building Act exempts from
      consent [nz_parliament_2004] and the one Nick Peters named.
- [ ] Element counts, heights and lengths by suburb, and against the 10^2 to
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
- [ ] Added 2026-10-02: how many polygons come from stacks and how far up
      they run; how much ground two polygons keep in common under the overlap
      rule, and that it sits at catchment divides; how often a stack reaches
      a slope unit's ground (phase 3, stacks).
- [ ] Added 2026-10-02: the share of urban ground in a polygon that fails in
      a realisation, against the order of 1% the literature gives (stage D3).
      This is the check the first pilot failed, at 44%.
- [ ] The stage D1 toy cases kept as regression tests, so a later change to a
      threshold that breaks one of them shows.
- [ ] The pilot rerun end to end, timed per step.

## What it removes

Landslide step 6 (`s6_urban_slope_candidates`) and step 7
(`s7_urban_slope_polygons`) as they stand: the slope bands, the octants, the
four scales, the 25 m strips, the splitting and snapping to wall lines, and
the terrain-break and boundary line sources in `landloss.exposure.rw.lines`.
Their figures and tests go with them. Steps 3, 4, 5, 8 and 9 stay, with step 9
grouping by element. Step 3's `face-height-5m` and `face-height-10m` local relief
layers go too once nothing reads them: local relief reads high on any
hillside, which is why the boundaries already moved to the step test.

## Speed

The static part of the run (steps 3 to 7 and the exposure steps) is
independent of the exposure world and the earthquake, and today `gen_all.py`
reruns it every time. The elements layer is computed once per territorial
authority and read thereafter; with the vectorised zonal statistics and no
per-polygon splitting, the expectation is that the pilot's 49 minutes in steps
6 and 7 falls to a few minutes, and a run of many earthquakes costs about half
a minute each over the pilot. To be measured in phase 4.

How the elements and polygons stay fast (added 2026-10-02; expectations,
not measurements):

1. **Every per-cell step is whole-array numpy or scipy**: slopes, the step
   height (array shifts), the threshold lookup, the exceedance, the
   two-pass `watershed_ift` (compiled, close to linear in the cell count),
   the element attributes by `np.bincount` on the label grid, and the
   catchments by pointer doubling (about 20 whole-array passes).
2. **Only the stack and retrogression rules loop in Python**, over elements
   (thousands per territorial authority), not over cells.
3. **It is parallel by tile.** Tiles of about 2 km with an overlap margin
   wider than the tallest stack's reach are independent. Each tile keeps
   only the elements whose seed lies in its core, so a seam element is built
   once, whole, by one tile. Tiles run in a process pool from the standard
   library (`concurrent.futures`), so no dependency is added; territorial
   authorities are independent too. A stack that outruns the margin is
   reported, not cut, and the margin is widened.
4. **Memory**: a 2 km tile is 4 million cells, a few tens of MB per raster
   in float32, so several tiles fit side by side.

## Open decisions

- **The growth (phase 1), settled in stages D1 and D2:** the two grow
  angles, `BETA_GROW_ANGLE_DEG` (18.4° proposed) and
  `BETA_FREE_FACE_GROW_TOL_DEG`, and whether the estimated
  height band orders the seeds well enough on tall banks. Decided by the lead
  on 2026-10-02: the 3 m slope ranks the seeds, and grow angles stop the
  growth. Stage D1 found the proposed 5° tolerance let a cut grow into the
  bank above it under noise (16 to 30 of 30 seeds, depending on the case) and
  rebuilt it at 3°, which passes 30 of 30. Settled at 3° in stage D2 (2026-10-04):
  the pilot gives the same result at 2°, 3° and 5°, so the toy noise result decides
  (`pilot_example_slope_elements.md`).
- **Added 2026-10-02, phase 3, all proposals for the lead:**
  - stacks: a bench narrower than the width behind the crest links two
    elements, and a free-face over 50° and 3 m takes the whole stack above it
    [kingsbury_1995; brabhaharan_2018];
  - whether a stack reaching slope unit ground gives way to the large model
    or is drawn independently with the ground counted once;
  - overlap kept only between elements with disjoint catchments; otherwise
    the nearest crest takes the ground;
  - retrogression as a conditional draw, `BETA_RETROGRESSION_P`;
  - asperities only if stages D1 or D2 show polygons running away.
- **The step test** (phase 1): confirmed by the lead on 2026-10-02, the eight
  height bands and the 24-entry `STEP_ANGLE_DEG` lookup as written, the
  soil-like 35° included. The stronger rock row still waits on a mapped
  weathering grade (step 4 plan, phase 3).
- The rock factor from height band 4 (over 2.5 m), the cut height taken to be
  through the cover and into rock, from a published 0.5 to 3 m.
- Whether the elements layer lives in the shared versioned store or a local
  cache.
- **Phase 3, from the 2026-10-02 review, all proposals for the lead:**
  - segmenting long elements at `BETA_SEGMENT_VOLUME_M3`, proposed
    1,000 m³;
  - a wall's wedge on the retained ground's phi' (0.45 H for fill), and a
    fill bank's at 0.45 H with 0.25 and 0.65 H as the cases; a cut or natural
    bank with no wall keeps the T-44 band;
  - dry debris avalanche runout for cuts and natural banks and the fill flow
    slide line for every fill [de_vilder_2022];
  - imminent ground to a 35° repose line from the toe [de_vilder_2024],
    `BETA_REPOSE_ANGLE_DEG`;
  - amplification by element height and ridge or terrace setting
    [brabhaharan_2018] in place of the slope-driven placeholder.

Written 2026-10-02. Phases 0 to 2 reviewed against the literature on
2026-10-02, and phase 3 and the phase 4 checks it adds on 2026-10-02 (second
part of the review). Revised the same day after the lead's review of the
method: the terms, seeded growth in place of geomorphons, the stack, overlap,
retrogression and asperity rules, and the development stages. The plan as a
whole is not yet signed off by the lead.
