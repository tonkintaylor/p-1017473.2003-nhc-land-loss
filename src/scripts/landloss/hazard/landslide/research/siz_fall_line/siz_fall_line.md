# Siz test: every pair on the whole pif against each piece's fall lines

`gen_siz_test_comparison.py` beside this file, run 2026-10-08 over the
Wellington and Porirua pilots. Table:
`report/hazard/landslide/siz-fall-line/tab/siz-test-comparison.csv`. Layers and
QGIS projects (pips and pieces by verdict, 1 m contours, the 1 m slope):
`temp/hazard/landslide/research/siz-fall-line/` (gitignored).

## Why

Ground step 3 (then landslide step 12) decided whether a pif is a siz by comparing every pair of its points
(its pips and the cells 1, 3 and 5 m down each pip's fall line) up to 30 m
apart (`instability_zones.PAIRS_TEST`), on the whole pif, and every piece cut
from it took that verdict. The test was 70% of the step's time (131 of 187 s
on the Porirua pilot, most of the 8.9 h over Porirua), because the pairs grow
with the square of a pif's size and nearly all of them run along the face,
where they never set the steepest angle. And one steep stretch made every
piece of a long pif a siz, up to hundreds of metres from it. The lead
(2026-10-08) asked whether reading each pip's own slope and the drop in front
of it would do the job, and for the test to be made on each piece after the
split.

## The variants compared, on every piece

- **old**: the pair test on the whole pif, inherited by the piece (ground step 3
  until 2026-10-08).
- **d8**: the fall-line test (`FALL_LINE_TEST`) on the piece's own pips, each
  pip read down the nearest of the eight directions, one cell at a time,
  stopping 5 m past the last cell of its piece so the drop is the face's.
  Pairs under 3 m use the ground group's step; 3 to 30 m its angle for the
  drop's band.
- **new**: the same along each pip's true downhill direction
  (`terrain_layers`' `downhill_row`, `downhill_col`), what ground step 3 now runs.

An open fall line, running the full 30 m down the hillside, was tried first
and dropped: its largest drop was a median 3.5 m bigger than the pair test's
because it carries on below the toe, and `wall_candidates.py` bands the wall
candidates on that drop.

## Findings

| | Wellington pilot | Porirua pilot |
| --- | --- | --- |
| Whole pifs / pieces | 5,155 / 6,220 | 5,810 / 6,779 |
| Siz pieces, old | 4,884 | 3,603 |
| Siz pieces, d8 | 4,749 | 3,379 |
| Siz pieces, new | 4,790 | 3,466 |
| Old only / new only | 96 / 2 | 143 / 6 |
| Seconds, old / new | 18.4 / 4.0 | 82.6 / 7.9 |

- The new test is 5 to 10 times faster here, where it rebuilds the terrain
  layers; ground step 3 already has them, so in the pipeline it is about 20 times
  faster, and the siz test over Porirua costs minutes rather than hours.
- **Soil is unchanged** (3,913 to 3,914 and 2,157 to 2,159 siz pieces). Every
  difference is in weak rock, which loses about 10% (971 to 876, 1,446 to
  1,307).
- Following the true downhill direction wins back about 40% of what the eight
  directions lost (136 to 96, 228 to 143): a face whose downhill lies between
  two of the eight read gentler along either.
- What remains lost is borderline (the old test passed most at 40 to 41
  degrees against a 40 degree limit) or the gentle ends of rock faces that
  took a steep stretch's verdict before. About 1% of pips.

## Next

- Rerun the pilots and Porirua with the new test (ground step 4 plan, `s4_slope_faces_implementation_plan.md`, phase 5b).
- The lead to look at pieces of mixed steepness in the QGIS projects and
  decide whether the split should also cut on steepness.
