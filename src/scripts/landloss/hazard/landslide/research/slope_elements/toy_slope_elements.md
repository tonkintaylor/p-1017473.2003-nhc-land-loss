# Slope elements on toy terrain (stage D1)

Findings from `fig_toy_slope_elements.py` in this folder. The script was first run on
2026-10-02, and rerun the same day after the review of that build. To run it from the
repository root:

```
uv run --frozen python src/scripts/landloss/hazard/landslide/research/slope_elements/fig_toy_slope_elements.py
```

This is stage D1 of `.agents/plans/building-face-based-urban-slope-polygons.md`. This
document describes the second build. "What was changed" lists every change made after
the review, with the reason for each.

## Question

Do the seeded growth of phase 1 (`landloss.hazard.landslide.slope_elements`) and the
polygon rules of phase 3 (`landloss.hazard.landslide.slope_polygons`) give the answer
the plan expects on ground whose answer is known? Where they do not, is the algorithm
wrong or is the expectation wrong?

## Method

- **Terrain.** The 12 cases of the plan's Development table are built by
  `landloss.hazard.landslide.synthetic_terrain` as 1 m DEMs. Cases 3, 5 and 12 have two
  parts each. Stage D1 adds case 13: two 3 m soil-like batters, one at 37° and one at
  33°, either side of the soil-like 35° test; case 14: two gully heads on a ridge that
  bends at a nose, to test the `BETA_FACING_APART_DEG` threshold at an angle other than
  case 6's 180°; and case 15: undulating hills, to test that rolling ground under the
  grow angle gives no element. That makes 19 grids. Every profile but cases 6 and 9
  falls east and is the same on every row; cases 14 and 15 are two-dimensional and fall
  on neither axis.
- **Rotated copies.** `rotate_toy_case` turns any profile case to another bearing. The
  regression tests use it for cases 1 and 3, and for vertical walls 0.6 to 1.6 m high on
  all three ground groups.
- **Ground.** Cases 9 and 12 are weak rock and every other case is soil-like. The walls
  of cases 1, 2 and 5 are on fill (`is_fill` on their free-faces). The ground rising
  behind case 2's wall is natural, because the first build marked it as fill by
  mistake. Every other case is cut or natural ground, so it runs out as a dry debris
  avalanche.
- **Free-faces.** Every free-face takes a wall's wedge on φ' 42°
  (`BETA_DEFAULT_RETAINED_PHI_DEG`, the fill's value), because phase 2 has not been built
  and the ground map gives no φ' for each material. This includes soil-like cuts (cases
  3, 4, 7, 8 and 13) and weak rock (cases 9 and 12). Colluvium at 24 to 28° would give
  about 0.6 H rather than 0.45 H. Behind a face inclined at 40 to 45°, the Rankine plane
  (about 66°) is steeper than the face itself. On those faces `H tan(45 − φ'/2)` is a
  rule, not mechanics.
- **Runs.** Each grid is run without noise and with LiDAR-like noise
  (`BETA_LIDAR_NOISE_SD_M` = 0.05 m, seed 7, the seed the tests use). It is then rerun
  under 30 noise seeds (0 to 29). The noise is independent for each cell. Real LiDAR
  error is spatially correlated and smoothed by gridding, so the pass rates show
  robustness to noise, not survey performance.
- **Checks.** Each expected outcome is a check function in the script. The
  expectations are the plan's table, copied unchanged below. The checks were written
  after a first exploratory run. Two of them are weaker than the table, and both are
  stated here:
  - Case 9's check accepts end pieces under 10 m long beside the one long element.
  - Case 9's terrain was rebuilt (see "What was changed", item 11).

  Every other check encodes the table. Since the review, the case 2 and case 3 (2 m)
  checks are tighter: the polygon must stop within one cell of its own width behind the
  crest, where before it could stop up to 3 m back.
- **Figures.** There is one PNG per case, four plans and two sections, for both the
  noise-free and the noisy run (see "Diagnostic plans redesigned" below):
  - **Plan 1, diagnostic.** A flat background by ground group (red soil-like, amber weak
    rock, green stronger rock; a toy case's ground is uniform, so this is one colour per
    case), 90%-index contours labelled every 2 or 5 m, every cell within 80% of its own
    threshold angle as a point coloured by its eligibility ratio (1.0 = at threshold;
    `coolwarm`, centred at 1.0 over every run in the case so the two columns share a
    scale), hollow circles for cells eligible by step height and crosses for cells
    eligible by the 3 m slope, and a dashed convex-hull "lasso" around each element's own
    near-threshold cells.
  - **Plan 2, shape.** The same contours, each element's own cell boundary (orange
    free-face, green bank), the evacuated zone as modelled (grey fill, solid outline),
    the imminent zone (amber hatch) and the inundated zone (blue), each free-face's
    illustrative no-wall band (dashed outline, widened from the as-modelled band; see
    below) and illustrative wall centreline (solid line through its crest cells).
  - **Sections**, true scale, unchanged from the first build: the elements, the polygon
    outline, the imminent and inundated zones at cell size, and each evacuated cell to
    its own depth.

  On the profile cases the 5 rows at each grid edge are greyed out and labelled "grid
  edge rows". There is also an overview of every noise-free section.

## Expected outcomes (the plan's table, unchanged)

| # | Case | Expected |
| --- | --- | --- |
| 1 | A 2 m vertical retaining wall, level ground above and below | One free-face; polygon the level-ground wedge, about 0.45 H on fill |
| 2 | The same wall with ground rising at 20° behind it | A free-face with a bank stacked on it; the polygon takes the wall's width only, and the bank is linked by retrogression |
| 3 | An excavated toe: a 4 m cut at 60° at the foot of a 30° bank 15 m high, soil-like ground; then the same with a 2 m cut | 4 m: the cut carries the stack-dominant flag, so the polygon runs to the bank's crest. 2 m: the cut's width only, the bank linked by retrogression |
| 4 | The same 4 m cut under a 15° slope | The slope is under the grow angle, so not an element: the cut's width only |
| 5 | Two terraces, each with a 2 m wall, with a bench between them 1 m wide and then 8 m wide | Narrow bench: one stack. Wide bench: two separate polygons |
| 6 | Two adjacent gullies whose steep heads meet at a ridge | Two elements in different catchments; their polygons may overlap at the ridge top and nowhere else |
| 7 | A convex slope, rounding gradually over its crest | Where the crest lands; free-face or bank by its overall angle, not its peak cell |
| 8 | A concave slope, easing gradually into its toe | Where the toe lands |
| 9 | A road cut 200 m long and 4 m high | One element, cut into segments by volume |
| 10 | A 1.5 m wall halfway down a 25° bank | Three stacked elements (bank, wall, bank), not one bank |
| 11 | A 0.3 m step on level ground | No element |
| 12 | A bank on weak rock at 40°, 3 m high, then 12 m high | A bank at 3 m (test angle 45°), a free-face at 12 m (34°) |
| 13 (added in D1) | 3 m soil-like batters at 37° and 33° | A free-face at 37°, a bank at 33° (test angle 35°) |
| 14 (added in D1) | Two gully heads on a bent ridge, nominal fall bearings 60° and 120° apart | Two free-faces, facing apart under `BETA_FACING_APART_DEG`; disjoint catchments, but the ground they both reach near the nose is kept by both (`within_width`), not `separate_catchments` |
| 15 (added in D1) | Undulating hills, none of them steeper than 15° anywhere | No element |

## Observed outcomes

The pass or fail columns are for the noise-free run, the noisy run at seed 7, and the 30
noise seeds. H is the element's height, now measured between the breaks in slope at its
crest and toe (see "What was changed", item 1).

The table gives two widths:

- **Rule width** is the width behind the crest that the rule gives.
- **Kept width** (`width_realised_m`) is the width the polygon actually keeps: the
  median over its rays of the distance from the crest cell centre to the furthest cell
  centre kept. It moves in whole cells.

Runout is the inundated ground beyond the toe on the middle row.

| Case | Clean | Seed 7 | 30 seeds | Observed (noise-free) |
| --- | --- | --- | --- | --- |
| 1 wall | pass | pass | 30/30 | One free-face, H 2.00 m, read vertical (90°), band 3. Rule width 0.89 m, kept width 0 (under a cell, so the polygon is the wall's 2 cells). Volume 36 m³, or 0.94 m³/m against the triangle's 0.89. Runout 2 m (fill flow slide, H/L 0.52) |
| 2 wall, rising ground | pass | pass | 30/30 | Wall H 2.00 m, vertical. Bank H 4.73 m at 20.0°, stacked across a 0 m bench. Wall polygon is its own 2 cells (rule width 0.89 m). Bank linked by retrogression. The bank is natural, so it takes the T-44 band |
| 3 4 m cut | pass | pass | 30/30 | Cut H 4.00 m at 60.0°, band 5, stack-dominant. Its polygon climbs the 30° bank (H 14.15 m) to x 9.5 m, so the polygon is 18.4 m high. Two segments, 1,029 and 535 m³, mean depth 1.37 m. The bank's own polygon is nested inside it (stack overlap). Runout 2 m below the toe, from the cut's own crest |
| 3 2 m cut | pass | pass | 30/30 | Cut H 2.29 m at 49.1°, band 3, not stack-dominant. Rule width 1.02 m, kept width 1.0 m. It keeps the bank cell inside its width, shared with the bank's polygon (`within_width`). Bank linked by retrogression. No runout |
| 4 cut, 15° slope | pass | pass | 30/30 | One element only, the cut, H 4.00 m at 60.0°, stack-dominant. Nothing above it to climb. Rule width 1.78 m, kept width 1.0 m. Volume 130 m³. Runout 1 m |
| 5 narrow bench | pass | pass | 30/30 | **Merged, not stacked.** One free-face, H 4.00 m at 63.4°, stack-dominant. The 1 m bench is one cell, which Horn's kernel reads as part of both walls. One polygon over both walls. See problem 9 |
| 5 wide bench | pass | pass | 30/30 | Two vertical free-faces, H 2.00 m each, linked across a bench read as 6.0 m. Two polygons, no overlap, linked by retrogression |
| 6 gullies | pass | pass | 30/30 | Two free-faces (H 4.66 m, 44.1°, facing 270° and 90°), in separate catchments. Their polygons share 4 cells at the ridge (`separate_catchments`). The gully-floor banks of the first build are gone (item 9). Under noise a floor strip just over 18.4° can still survive (problem 4) |
| 7 convex crest | pass | pass | 30/30 | Free-face H 14.11 m at 43.2° overall (steepest cell 45°), band 7. Crest at x 16.5 m, against the 30° point at 16.9 m. The 1 m rounding bank of the first build is now mostly inside the free-face, because the grow limit is 32° (item 4). It appears under noise in some seeds. Rule width 6.28 m, kept width 6.0 m. One polygon of 1,477 m³, mean depth 1.77 m |
| 8 concave toe | pass | pass | 30/30 | Free-face H 14.11 m at 43.2°. Toe at x 25.5 m, against the 30° point at 25.1 m. Kept width 6.0 m. 1,287 m³, mean depth 1.54 m. Runout 2 m onto the easing |
| 9 road cut | pass | pass | 30/30 | One free-face 224 m long (the cut and its ramps), H 4.00 m at 60.0°, stack-dominant. **One polygon of 788 m³**: 3.5 m³/m is under the segment volume. Two end pieces 6 m long (0.74 m, vertical) where the cut fades out along the ramps. Runout 1 m. With φ' 0 (a wedge as wide as H), the regression test checks that the cut is segmented |
| 10 wall in bank | pass | pass | 30/30 | Bank (H 6.30 m, 25°), free-face (**H 1.50 m**, vertical, band 3) and bank (6.30 m, 25°), linked crest to toe both ways |
| 11 small step | pass | pass | 30/30 | No element |
| 12 3 m weak rock | pass | pass | 30/30 | Bank, H 3.00 m at 40.0°, band 4, test 45°. Its polygon is its own cells plus the 1 m band. No runout |
| 12 12 m weak rock | pass | pass | 30/30 | Free-face (grown in the bank pass), H 12.00 m at 40.0°, band 7, test 34°. Rule width 5.34 m, kept width 5.0 m. 1,060 m³, mean depth 1.39 m. No runout |
| 13 37° batter | pass | pass | 30/30 | Free-face, H 3.00 m at 37.0°, test 35° |
| 13 33° batter | pass | pass | 30/30 | Bank, H 3.00 m at 33.0°, test 35° |
| 14 gullies at bent ridge | pass | pass | 30/30 | Two free-faces, H 7.97 m, aspects 66.8° and 113.2° (46.3° apart, well under `BETA_FACING_APART_DEG`'s 90°). Catchments disjoint, no `drainage_links`. Their polygons share 18 cells near the nose, resolved `within_width`, not `separate_catchments` |
| 15 undulating hills | pass | pass | 30/30 | No element; steepest cell about 14.1°, under the grow angle everywhere |

**All 19 grids pass on the noise-free run, on seed 7 and under all 30 noise seeds (570
of 570).** This is after the changes below, two of which are `BETA_` changes made on
evidence from these runs (items 4 and 10).

Before those two changes, the corrected build failed under noise:

- Case 3 (4 m) passed 16 of 30 seeds, and in 3 seeds it had no free-face at all.
- Case 3 (2 m) passed 10 of 30.
- Case 6 passed 0 of 30.
- Case 10 passed 3 of 30.

The first build's 449 of 450 depended on a growth bug (item 3) that hid this
sensitivity.

Spread under noise, over the 30 seeds:

| Case | Tallest free-face |
| --- | --- |
| 1 | 2.05–2.14 m |
| 3, 4 m cut | 4.06–4.15 m |
| 3, 2 m cut | 2.31–2.41 m |
| 7 | 13.32–14.07 m |
| 12, 12 m | 11.99–12.09 m |

The element count still varies in case 6 (3 to 8, floor strips), in case 7 and case 8
(1 or 2, the rounding bank), and in case 9 (always the 2 end pieces).

### Off the grid's axes and on other ground (regression tests)

- **Walls.** Vertical walls 0.6, 0.8, 1.2 and 1.6 m high were run on all three ground
  groups at bearings of 90, 120 and 135°, that is 0, 30 and 45° to the grid. Each comes
  out as one free-face, read vertical, at its true height to 0.01 m. In the first build
  every one of these at 0.6 m was lost, and so were others: weak rock at 0.8 m, stronger
  rock up to 1.2 m, and several on the diagonal.
- **Case 1 rotated.** Case 1 at 110, 120 and 135° reads 2.0 m, with and without noise.
- **Case 3 rotated.** Case 3's 4 m cut at 110, 120 and 135° reads 60.1°, 62.0° and 60.0°,
  and keeps the stack-dominant flag and its bank link. The first build read 55.0°, 53.9°
  and 51.5° as the bearing moved off the grid.
- **Nodata.** A 5 by 4 m nodata hole in case 3's bank, with a nodata strip behind its
  crest, leaves the bank at 14.15 m, its height without the hole. In the first build the
  hole moved the bank from band 7 to band 4 (the review's 13.86 to 3.46 m). No crest
  cell lies beside the hole, and the bank is flagged `touches_nodata`.
- **Mixed ground.** A 40° bank that is soil-like on its north half and weak rock on its
  south half gives a free-face over the soil and a bank over the rock, each across its
  whole half.
- **Tiles.** Case 5 (wide bench) was split between its walls into two overlapping tiles,
  with a 14 m halo each side of the seam. The stitched evacuated cells and the
  retrogression link across the seam match the untiled run exactly.

## Timings

Each toy grid takes 0.02 to 0.04 s for the elements and under 0.09 s for the polygons.
The speed grid is case 10 mirrored and repeated, 1,000 by 1,100 cells. On it the
elements took 2.65 s and the polygons 2.39 s. That grid has only 60 long elements (860
polygons), so it measures the passes over the grid, not urban element density. The
Python loop over seeds in `_keep_reachable` has gone (item 4), so the free-face pass now
loops only over grow limits, of which there are at most 5.

## What was changed

These are the changes after the review of the first build, in order of weight. Each is
in the library unless it says otherwise.

1. **Elements are measured between their breaks in slope, not between the centres of
   their end cells** (`slope_elements._transects`). The first build measured a vertical
   wall's run between the centres of its two cells, 1 m on the grid and 1.41 m on the
   diagonal, so the step test was deciding on a grid artefact. The new measure:
   - Trims a gentle end cell, one the step estimator spread onto level ground beside a
     wall at an angle to the grid.
   - Reads a fall across one interval between two cell centres as a vertical step,
     because the DEM cannot resolve its run. The interval must be
     `BETA_STEP_MARGIN_DEG` steeper than the interval beyond each end. The height is
     taken less the fall of the ground either side over the half interval.
   - Moves each end of a wider face to where the face meets a straight line through the
     two cells beyond it. This is exact on ground made of straight pieces.

   Results:
   - Walls read vertical at their height.
   - Case 10's 1.5 m wall reads 1.50 m, not 1.97 m.
   - Banks read their built height: case 3's bank reads 14.15 m (built 15.0 m; its
     foot meets the cut's cells). Case 2's bank reads 4.73 m (5.5 m). The weak rock
     banks read 3.00 and 12.00 m.
   - Cuts read their built angle: case 3 and case 4 read 60.0°.

   The review proposed subtracting one cell from every run. That was not done, because
   it would read case 12's 3 m bank at 51.6° and make it a free-face. A face that falls
   across two intervals still reads its steeper interval: case 3's 2 m cut reads 49°,
   not 60°.
2. **Nodata is not a crest or a toe** (`_edge_roles`, `_transects`). A boundary cell is
   a crest or a toe only where the cell beyond it along the fall line has a 1 m slope.
   Otherwise it is an end. Transects cut short by nodata or the grid edge are left out
   of the median wherever the element has others. Each element now carries
   `touches_nodata`.
3. **A growth bug, found while testing item 2** (`_grow`). The cells growth may not
   enter are watershed markers of a barrier label. Their own flood used to beat a seed
   to allowed cells of high cost, so every element lost ground beside a barrier. Near
   nodata it lost a 12 by 12 cell block. At grid edges it lost about 4 rows, which is
   most of what the first build blamed on the 3 m block mean. Barrier cells now take the
   top cost, which the code already reserved for them. Banks now run to the grid edge
   rows (length 38 m, not 32 m).
4. **`BETA_FREE_FACE_GROW_TOL_DEG`: 5 → 3°, a `BETA_` change.** After item 3, the
   soil-like grow limit of 30° (35 − 5) sat exactly on the 30° bank above case 3's cut.
   Under noise the cut grew up into the bank:
   - At 5°: the 4 m cut kept its stack-dominant flag in 16 of 30 seeds, and in 3 seeds
     there was no free-face. The 2 m cut case passed 10 of 30.
   - At 3° (limit 32°): both passed 30 of 30. Walls, batters and case 10 are unchanged.

   Case 7's crest moves 1 m up the rounding, and its 1 m rounding bank mostly joins the
   free-face (still within 2 m of the 30° point). 2° gave the same as 3° on case 3, and
   on case 7 the same as 5°. The lead left the call to the build, and it was settled
   at 3° in stage D2: the pilot gives the same result at 2°, 3° and 5°
   (`pilot_example_slope_elements.md`), so this noise result decides.

   In the same pass, growth was changed in two other ways:
   - Seeds and patches are labelled within one ground group.
   - A cell is entered only where it is over its own ground's limit as well as the
     seed's (the review's per-cell allowance), and the grow limits are grown strictest
     first.

   `_keep_reachable` is no longer needed and was removed.
5. **Halo elements are kept** (`find_slope_elements(core=...)`,
   `build_slope_polygons`). Every element is kept, with `in_core` telling whose it is.
   The links, catchments and polygons are built on the whole tile, and the polygons,
   links and overlaps of halo elements are dropped only at the end, after the shared
   ground is settled. Elements also carry `seed_x` and `seed_y`, the seed peak in map
   coordinates. Ties go to the first cell in row order, so the same element has the same
   key on every tile.
6. **Free-face volume is the triangle toe–crest–back** (`planar_depth_m`,
   `element_depth_m`). Each of a free-face's own cells (face and wedge) is evacuated to
   a straight slip plane from its toe to the back of its width, 0.5 H w per metre on
   level ground. The first build gave the face's own plan area H/2 as well, so it counted
   ground under the toe's level. The figures now draw each cell's depth to the plane.
   Ground the stack takes keeps its own element's depth.
7. **Rule 3 of the stack rules is followed: an element takes its own width even into
   the element above it** (`_contest`). Ground that one polygon's width reaches into the
   element above is kept by both polygons, with the overlap reason `within_width`, and
   the retrogression link is kept. The first build's ray cut-off is removed. That
   cut-off had left case 7's free-face with 1.5 m of its 5.9 m. Case 7 now keeps 6.0 m
   of its 6.3 m, with no holes. See problem 11 for the conflict this resolves.
8. **A stack also runs out from its free-face's own crest.** The inundated zone is the
   union of the reach line from the stack's top and the reach line from the free-face's
   crest. Case 3's 4 m cut now runs out 2 m, against 1 m for the same cut alone (case
   4). Before this change it ran out 0 m. A polygon's debris no longer covers its own
   evacuated cells. The imminent band is reduced by the cells the polygon kept, not by
   what it first claimed.
9. **Regions gentler than the grow angle, regions no transect crosses, and regions
   shorter than `BETA_MIN_ELEMENT_LENGTH_M` are not elements.**
   - Gentler than the grow angle: this is the plan's own premise, and it removes case
     6's gully-floor strips.
   - No transect crosses: such a region has no crest on measured ground (strips along
     the grid edge), so it cannot be measured.
   - Shorter than `BETA_MIN_ELEMENT_LENGTH_M` (3 m along the contour, a new `BETA_`
     value): the free-face pass releases such regions to the bank pass. This was added
     because, once item 3 stopped barriers starving small regions, noise made 1 to 2 m
     pieces at the crest and toe of every bank pass the step test. Case 10 passed 3 of
     30 seeds without it and 30 of 30 with it.
10. **`BETA_STEP_MARGIN_DEG` = 10°, new.** A single interval is a vertical step only
    where it is 10° steeper than the ground beyond each end. With the free-face
    tolerance (3°) in its place, noise turned breaks in slope into vertical "walls".
    10° is about two and a half times the scatter of an interval's angle under 0.05 m
    noise. A 0.5 m wall set in a 35° bank still clears it by 15°.
11. **Case 9's terrain was rebuilt before the first build's findings.** This was not
    recorded in the first findings document. The first version was a 10° hillside with
    a road cut into it, a 5 m taper at each end, and ground falling away below the road.
    The current version has a level road along the foot of the hillside, the road level
    to the grid edge, and 20 m ramps at each end. The ramps remove the steep end walls
    the taper made, and with them the case's hardest test. Its check also accepts end
    pieces under 10 m, which is weaker than the table's "One element".
12. **Smaller changes:**
    - `seed_exceedance_deg` of a bank-pass element is now the bank pass's own measure
      (3 m slope less 18.4°).
    - If `_MAX_FREE_FACE_ROUNDS` runs out, the free-faces left are regrown before the
      bank pass.
    - The ridge stop is a named judgement, `BETA_RIDGE_DROP_M` (= `MIN_WALL_HEIGHT_M`).
    - The facing-apart angle is `BETA_FACING_APART_DEG`, and the module docstring says
      that this test is ours, added to the plan's overlap rule 1.
    - The default φ' is `BETA_DEFAULT_RETAINED_PHI_DEG`.
    - `stack_dominant_cut` and `hb1995_cut` are documented as geometric only (on banks
      too); the stack rule reads them on free-faces only.
    - In the script, `FILL_CASES` marks only the free-faces as fill.
    - `check_wall` now checks the polygon's cells, not the width ratio.
    - The figures grey out the grid-edge rows.

**`BETA_` values in stage D1:**

- `BETA_FREE_FACE_GROW_TOL_DEG`: changed 5 → 3°.
- `BETA_STEP_MARGIN_DEG` (10°): new.
- `BETA_MIN_ELEMENT_LENGTH_M` (3 m): new.
- `BETA_RIDGE_DROP_M`, `BETA_FACING_APART_DEG` and `BETA_DEFAULT_RETAINED_PHI_DEG`: give
  names to values that were already in use, unchanged.
- No other `BETA_` value was changed.

## 35° on soil-like ground

**There is no evidence here for changing 35°.** It seeds and keeps a free-face in every
soil-like case that should have one, including the new 37° batter, and leaves the 33°
batter a bank.

The first build said a wall under about 0.7 m could not pass 35°, and that this was
"below `MIN_WALL_HEIGHT_M` anyway". **That was wrong on two counts.**
`MIN_WALL_HEIGHT_M` is 0.5 m, not 0.7 m. And the limit was a grid artefact of item 1,
which was worse on rock ground (45° and 53°) and on the diagonal. It is now gone: a
0.6 m wall is a free-face on every group at every bearing tested.

## Two gully heads 60° apart, and undulating hills

Case 6's ridge is straight and its two gully heads face 180° apart, a mirror pair
either side of the ridge trace. Case 14 bends the ridge at a nose instead: one side
falls towards 60°, the other towards 120°, meeting `BETA_FACING_APART_DEG` (90°) at a
different angle than case 6's. Building it took two false starts, worth recording:

- **A trough whose width scales with angle collapses at the apex.** The first attempt
  measured each flank's cross-fall as an angle from its own fall bearing, scaled by
  radius from the nose (as case 6's gullies are built along a straight ridge, generalised
  naively to a bend). Angular width is unbounded as radius goes to zero, so near the nose
  both troughs always reached full depth regardless of the angle between them, merging
  into one element every time.
- **A fixed-width trough still collapses at the apex, by a different route.** Switching
  to a fixed-width Gaussian in a Cartesian cross-fall coordinate (case 6's own
  construction) was not enough on its own: near the nose, the perpendicular offset from
  *either* flank's own fall line shrinks towards zero for both flanks at once, so both
  troughs still reach near-full depth close together. The fix is a `start` distance: each
  flank only begins to deepen once it has fallen `start` = 5 m from the nose, so the two
  troughs are already apart by the time either cuts in.
- **Which line partitions the two flanks matters.** An apex-radiating partition (each
  flank owns the angular wedge on its own side of the bisector) never produces an
  overlap: each flank's own "behind crest" reach direction (opposite its fall bearing)
  then points away from the other flank, so the two polygons can never contest the same
  ground, whatever the parameters. The built case instead partitions on a straight line
  through the nose (here, an east–west line, `north >= apex_north`), mirroring case 6's
  own straight ridge trace turned 90° from the bisector of the two fall bearings (the
  only line that reflects 60° into 120°). Across that line each flank's reach can run
  into the other's territory, the way case 6's two flanks' reaches cross the ridge.

With this construction, the two gully heads measure 66.8° and 113.2° apart (46.3°, not
the nominal 60°, the bend pulling the measured aspect in from the input bearings; still
clearly under the 90° threshold, which is what the test needs), in disjoint catchments,
and the ground they both reach near the nose is kept by both under `within_width`
(18 cells), not `separate_catchments` — case 6 demonstrates the overlap rule when
catchments are disjoint **and** facing more than 90° apart; case 14 demonstrates it is
*not* `separate_catchments` when they face less than 90° apart, even though the
catchments are still disjoint.

Case 15 (undulating hills: a sum of five sinusoids on a 220 m grid, none of them
steeper than about 14.1°) is a straightforward negative control: rolling ground under
the grow angle everywhere gives no element, with or without noise, confirming the
library does not spuriously seed growth on gently undulating natural ground.

## Diagnostic plans redesigned

The first build's single plan (an unstretched hillshade with the polygon outline) did
not show why a cell was or was not seeded, or what an element would look like without a
wall. It is replaced by the two plans in "Figures" above:

- **Eligibility.** `eligibility_grids` reproduces
  `slope_elements._free_face_pass`'s own seed test cell for cell
  (`height_band` → `step_angle_deg` → compare against `slope_coarse_deg`), so the
  diagnostic plot's points are exactly the cells the free-face pass would itself judge
  eligible, not a separate approximation. The ratio it colours by is
  `max(step_ratio, slope_ratio)`, so a cell eligible by either test is shown by its
  larger exceedance.
- **No-wall band and wall centreline are illustrative, not modelled.** Phase 2 (which
  free-faces carry a wall, and where its line runs) has not been built. `no_wall_band`
  scales a free-face's own evacuated polygon outward from its toe by the ratio of
  `headscarp_band_width_m` (the width a bank's own rule would give the same element) to
  the width it actually kept, never below 1.0: removing a wall can only widen the
  setback, never narrow it. `wall_centreline` is the best-fit line through the
  free-face's own crest cells. Both are drawn dashed or thin to keep them visually
  distinct from the modelled evacuated zone.

## Open problems and implications

1. **The wall wedge on tall free-faces that are not walls (revised).** With the
   triangle volume, cases 7, 8 and 12 (12 to 14 m at 40 to 43°) have mean evacuated
   depths of 1.4 to 1.8 m and 1,060 to 1,480 m³, 35 to 39 m³ per metre. The first
   build's 5.8 to 6.6 m came from the volume error in item 6. These depths are inside the
   0.5 to 3 m Wellington cover range. So the argument for giving tall free-faces the bank
   depth is weaker than it was. What still stands is the width: 0.45 H puts the slip
   plane 6 m back from the crest of a 14 m natural slope. Phase 2 deciding which
   free-faces are walls remains the fix. **For the lead.**
2. **Runout for cut and natural ground is small, and a stack ran out shorter than its
   cut alone.** The dry debris avalanche relation (H/L 0.85 to 0.97) leaves 0 to 2 m of
   runout below every cut and bank here. Fill walls run out 2 to 6 m. In the first build
   the 4 m cut's stack ran out 0 m, against 1 m for the cut alone, because the reach line
   started at the stack's top. It now also takes the cut's own reach (item 8). The
   review asked for a stronger rule: the deposit should reach at least the base
   element's toe, for volume conservation. That was not built. **For the lead, with the
   plan's open question 4** (a probability of reaching beyond the median).
3. **Bank heights read short where a bank meets another element.** A bank's end at
   another element's cell is not extended to the break, so case 3's bank reads 14.15 m
   against 15.0 m built. The end that meets level ground is exact (case 12). This is a
   measurement limit and does not need a judgement.
4. **Gully floors under noise.** With noise, a strip of gully floor reads just over
   18.4° in some seeds (case 6, 3 to 8 elements) and takes a polygon on its own cells.
   The polygons share ground with the gully heads within their widths. The grow-angle
   drop removes the strip without noise.
5. **Case 6 does not isolate a gully head.** The toy gullies are trenches with steep
   side walls along their whole length, and they run to the grid edge, where they also
   show as free-faces in the section. The case tests catchment separation, not a
   head-only element.
6. **Case 7 does not test "overall angle, not peak cell".** Its overall angle (43.2°)
   and its steepest cell (45°) are both over 35°. A case with a 38° middle and a 30°
   overall angle on 6 m of soil-like ground would test it.
7. **Grid and tile edges.** After item 3, profile-case elements reach the grid-edge rows.
   What is left there comes from three things: Horn's kernel cannot fit on the border
   row, the 3 m slope reads NaN for about 4 cells, and the 9 m step span reads NaN for
   4.5 m. These are why the figures grey out 5 rows. On tiles, the halo has to hold the
   whole of every stack, including case 3's 26 m bank, not just 10 m. **A stack across a
   seam needs a halo at least as wide as the stack's reach.** That is the plan's Speed
   item 3, and it was not tested here: the tile test splits case 5, whose walls are 8 m
   apart. Two further limits:
   - An element longer along the contour than the halo is wide, such as a road cut
     across a seam, is still cut at the tile edge.
   - Seed keys are stable only where both tiles hold the element's peak cell.
8. **Segment volume.** With the triangle volume, the 4 m road cut (788 m³) is one
   polygon 224 m long. The first build's 100 m segments came from the volume error. A
   polygon 224 m long is still longer than any failure in the record, so the plan's open
   question on segmenting (by volume, or by a length as well) stands. **For the lead.**
9. **Narrow terraces merge.** Two 2 m walls on a 1 m bench read as one 4 m free-face at
   63°, which carries the stack-dominant flag. The plan expected "one stack". By the
   plan's own stack rule 1 they would not stack, because the 1 m bench is wider than the
   lower wall's 0.9 m width, and neither wall is stack-dominant. The plan's expectation
   and its rules disagree. The merge is defensible geotechnically, because walls set
   back by less than about their height act together. The check is marked as passing on
   the merge.
10. **A noisy 20° bank breaks up.** At seed 7, case 2's bank reads 1.91 m against
    4.73 m without noise, because it is only 1.6° over the grow angle. Its polygon still
    covers the bank, but its height band is wrong.
11. **The plan's overlap rule 2 and stack rule 3 disagree.** Overlap rule 2 says shared
    ground goes to the nearest crest. Stack rule 3 says an element takes its own width
    "even where that reaches into the element above". They disagree wherever an element
    lies directly above another. The first build silently followed rule 2 and stopped
    the rays, which left case 7's free-face with 1.5 m of a 5.9 m width while the
    findings reported 5.86 m. This build follows rule 3 (item 7): the lower polygon keeps
    the upper element's ground within its width, as an overlap of its own kind
    (`within_width`), and step 9 has to count that ground once. On urban ground (walls
    with gardens rising behind, cuts under banks) rule 2 would remove most wedges. **The
    choice is the lead's.**
12. **Walls in slopes still read slightly high under noise.** Case 10 reads 1.55 to
    1.64 m over 30 seeds. A wall of exactly 1.5 m falls in band 3, because a height on a
    break falls in the band above. The Building Act exemption is for walls *not
    exceeding* 1.5 m, so the break convention puts exactly 1.5 m on the wrong side.
    **For the lead** (it changes no number in `HEIGHT_BANDS_M`).
13. **Not done, for stage D2:**
    - Splitting banks by aspect sector before measuring them, so that a bank wrapping a
      spur gets a meaningful aspect, length and contour position.
    - A per-ray slip plane for free-faces a stack takes. They use the element's mean
      depth.
    - A mixed-ground toy case in the figures. Mixed ground is covered by a unit test
      only.

## Outstanding

`gen_ground_map.py` must be rerun for the pilot before stage D2. The ground map on disk
predates the mixed-fill remap and the S52 pick.

## Figures

All in `report/hazard/landslide/slope-elements/fig/`:

- `toy-01-wall.png`
- `toy-02-wall-rising-behind.png`
- `toy-03-excavated-toe-4m.png`
- `toy-03-excavated-toe-2m.png`
- `toy-04-cut-under-gentle-slope.png`
- `toy-05-terraces-narrow-bench.png`
- `toy-05-terraces-wide-bench.png`
- `toy-06-gullies-at-ridge.png`
- `toy-07-convex-crest.png`
- `toy-08-concave-toe.png`
- `toy-09-road-cut.png` (the plans are drawn on their side, north to the right)
- `toy-10-wall-in-bank.png`
- `toy-11-small-step.png`
- `toy-12-weak-rock-bank-3m.png`
- `toy-12-weak-rock-bank-12m.png`
- `toy-13-soil-batter-37deg.png`
- `toy-13-soil-batter-33deg.png`
- `toy-14-gullies-at-bent-ridge.png`
- `toy-15-undulating-hills.png`
- `toy-overview.png`
