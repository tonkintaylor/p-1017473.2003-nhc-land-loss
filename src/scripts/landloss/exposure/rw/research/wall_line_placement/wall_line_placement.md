# Where a pif wall's line is drawn

Run 2026-10-12 over `wlg-pilot` by `gen_wall_line_options.py`, settings in
`config.py`, and again on 2026-10-13 with option 10 added. The script now
draws option 9 (option 7, which the lead was happy with on 2026-10-12, with
the toe points moved 0.5 m, its ends the lowest toe points off the spine's
ends, and no bend turning back more than 100°) and option 10, the lead's
choice of 2026-10-13 (`toe_outline.py`). The code for options 2 to 6 was removed at the lead's word, and their
results below, and options 7's and 8's, are from that day's earlier runs. Outputs (gitignored) in `temp/qgis/wall-line-placement-pilot/`:
one GeoPackage of lines per variant, `summary.csv`, the context layers and
`wall_line_placement.qgs`, built from them with the `making-qgis-projects`
builder.

## Question

The lead saw drawn walls sitting in the middle of their evacuated polygons
rather than near the downhill edge. A pif wall unit's line is its pif's spine
(ground step 3, `instability_zones.gen_pif_spines`), the longest path through
its pips. A pip is a cell more than 0.7 m above the cells 1, 3 and 5 m down
its fall, so pips are the crest and upper face cells of a step, and the spine
runs along the crest or the middle of the face. The evacuated polygon reaches
from the toe of the face up past the crest by its width behind the crest. Can
the line be drawn better from the downslope edge of the pif's points plus an
offset of 0.4 m (the lead, 2026-10-12)?

## Method

Each of the pilot's 4,740 pif units (4,642 siz, 98 low-height) is redrawn; the
857 GNS-only units have no pips and keep their line.

- **Option 2, vertex shift** (`vertex_shift`): each vertex of the spine moves
  along the local fall (the mean fall of the pips within 3 m) to the furthest
  downslope of the pif's points within 1 m of it across the fall, then 0.4 m
  further. The vertex count is kept, so the line keeps its bends. A line that
  then breaks the wall line rules (3 to 50 m, at most 3 bends, at most 185° of
  turning) is shifted whole, by the median reach of its vertices.
- **Option 3, refit** (`refit`): the spine is resampled every 1 m, each
  station moved the same way (square to the line), and the moved points
  simplified by the wall line rules (`bend_split.canonical_line`, from a 0.5 m
  tolerance doubled until the line fits). A refit that breaks the rules takes
  option 2's line.
- **Option 4, toe fit** (`toe_fit`, the lead's method, 2026-10-12): the toe
  points are the pif's points (its pips, and the cell each pip falls to at
  1 m, which takes its pip's fall) with no pip of the pif in their own
  downhill direction: within 22.5° of the fall (half the 45° between the
  eight directions) and 5 m (the pip test's furthest offset, so a pip across
  an inside corner of the pif does not count). A line is fitted to them that
  keeps the spine's two end points and has the spine's bend count, one fewer
  or one more (at most 3): each count's inner vertices are seeded from the
  spine's (less its gentlest bend, or plus the midpoint of its longest
  section), moved by a robust least-squares fit (soft L1, 0.5 m scale) of
  the toe points' distances to the line, each held within 6 m of its seed.
  The fewest bends whose median toe distance is within 0.25 m of the best
  are kept, among the fits that keep the wall line rules; where none does,
  the fit with the spine's count is kept (`breaks`). No 0.4 m offset is
  added.
- **Option 5, toe fit revised** (`toe_fit`, the lead, 2026-10-12): as
  option 4 with three changes. A pip blocks a point within 45° of its fall
  (not 22.5°); every toe point moves 0.4 m down its own fall before the fit;
  and the line runs from the moved toe point nearest the spine's start to
  the one nearest its end, rather than from the spine's own ends.
- **Option 6** (the lead, 2026-10-12): as option 5, with the angle widened
  to 60° (option 5 left toe points uphill of other toe points) and the
  spine's bend count only.
- **Option 7** (the lead, 2026-10-12): as option 6, with a pip up to 8 m
  downhill of a point (not 5 m) making it not a toe point. A pif with no toe
  point left keeps its spine (`no-toe`). The script also writes an outline
  of each pif's points (`pif-hulls.gpkg`, a concave hull grown half a cell),
  coloured so touching pifs differ, to show which pips belong to which pif.
- **Option 8** (the lead, 2026-10-12): as option 7, with the toe points
  moved 0.5 m (not 0.4 m), and each end the spine's end projected down the
  pif's mean fall to the toe: of the moved toe points within 1 m of the line
  from the spine's end down the fall, and 10 m of the end, the furthest
  downhill (the nearest toe point where there is none). Where both ends come
  to the same toe point the spine is moved, unchanged, onto it
  (`translated`; option 7 drew a zero-length line there).
- **Option 9** (the lead, 2026-10-12): as option 8, with each end the moved
  toe point on the lowest ground (1 m DEM) within 45° either side of the
  perpendicular to the spine's end segment, on its downhill side, and 10 m of
  the spine's end; and no bend of the line turning back more than 100°. The
  fit penalises a bend past 100° (1 m of residual per degree over), and a
  bend still past it after the fit is dropped and the line refitted
  (`bend-dropped`).
- **Option 10** (the lead, 2026-10-13; option A of the 120 case comparison
  in `temp/wall-line-brief/options/findings.md`, where options B, element
  toe cells, and C, a bench plane below the face, were also tried):
  - *The line* (`toe_outline.draw_line`) is taken from the pif's cell outline
    (its pips and 1 m points as 1 m squares), walked every 0.5 m. The longest
    run of the outline whose outward normal is within 45° of the local fall
    (widened to 60°, 75° or 90° only when no run is 4 m long) is the toe;
    gaps in it of 6, 3, 1.5, 9 and 12 m are bridged in turn. Each run is
    regularised by an exact dynamic programming fit (`fit_polyline`): 0 to 3
    bends, each paying a penalty that grows with length, sections of 3 m or
    more, no bend over 100°, at most 185° of turning, then a robust least
    squares polish of the vertices. Short end hooks are cut. The candidate
    with the fewest pips more than 0.75 m beyond it downhill, plus penalties
    for a poor fit, a chord across a notch and S jogs, is kept. A pif with
    no downhill run keeps option 9's line (`fallback-opt9`).
  - *The pips it holds* (`toe_outline.assign`): a pip is on the wall when
    its fall, widened 45° either side and 200 m long, meets the line. The
    rest, grouped across one-cell gaps, are a pif with no wall (p_wall 0)
    when more than 5 pips; fewer go back to the wall's pif, as does a group
    with over half its edge on it. The wall's pif must touch (8-connected):
    a group of wall pips within 3 m of the line stays, any other joins the
    no-wall pif it touches, or is one of its own when over 5 pips.
  - Units are drawn in 16 processes (`toe_outline.draw_units`).
- **The points** the downslope edge is read from: the pips (`pips`), or the
  pips and the cell each falls to 1 m below (`points`). A pif's points that
  are not pips are the cells each pip falls to at 1, 3 and 5 m, which only the
  pair test reads; the 3 and 5 m ones lie below the face, so only the 1 m
  ones are tried.
- **Snap** (`-snap`): every moved point within 1 m of a LINZ property
  boundary moves onto it before the line rules are applied.
- Each line is measured as exposure rw step 6 measures a unit's line
  (`gen_unit_boundary_flags`, `gen_unit_properties`), and against the 1 m DEM:
  the mean elevation of 11 points along the new line less that along the
  spine.

## Results

Times are the line drawing alone, one process, on the pilot's 4,740 pif units.
Over Upper Hutt's 54,903 pif units option 7 first took 338 s (toe test 283 s,
fit 55 s), the toe test comparing every point of a pif with every pip of it,
which took 2.8 s and 3.7 GB for the largest pif (6,242 pips). With a KD-tree
testing only the pairs within the look distance it takes 159 s (toe test
100 s, fit 59 s; 0.15 s and 0.1 GB for that pif) and draws identical lines
and toe points; on the pilot the toe test went from 4.5 s to 3.1 s.

| Variant | Time (s) | Fallback | Median move (m) | 90th pct move (m) | Ground on the line vs spine (median, share of height) | Lower than the spine | Primary property changed | On road frontage | On a property boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current (spine) | – | – | 0 | 0 | 0 | – | – | 11.4% | 42.2% |
| opt2-pips | 0.7 | 257 whole | 0.79 | 2.17 | −0.70 m (−0.49 H) | 93% | 12.3% | 12.0% | 42.2% |
| opt2-pips-snap | 1.2 | 301 whole | 0.83 | 2.19 | −0.73 m (−0.51 H) | 93% | 13.3% | 12.0% | 42.4% |
| opt2-points | 0.6 | 280 whole | 1.77 | 3.08 | −1.40 m (−0.96 H) | 100% | 24.2% | 12.0% | 39.6% |
| opt3-pips | 3.7 | 50 opt2 | 0.60 | 2.51 | −0.43 m (−0.31 H) | 82% | 12.9% | 12.0% | 42.2% |
| opt3-pips-snap | 5.3 | 129 opt2 | 0.71 | 2.53 | −0.52 m (−0.37 H) | 84% | 14.3% | 12.1% | 43.1% |
| opt3-points | 3.7 | 58 opt2 | 1.51 | 3.40 | −1.18 m (−0.83 H) | 99% | 22.8% | 11.8% | 39.9% |
| opt4-toe | 25.5 | 56 breaks | 0.82 | 2.32 | −0.64 m (−0.44 H); −0.91 m (−0.63 H) on the 71% it moves | 95% of those moved | 11.7% | 12.3% | 43.2% |
| opt5 | 26.8 | 60 breaks | 1.22 | 2.96 | −0.94 m (−0.66 H) | 90% | 18.2% | 12.1% | 41.6% |
| opt6 | 9.8 | 561 breaks | 1.05 | 3.14 | −0.87 m (−0.61 H) | 92% | 17.3% | 11.9% | 40.5% |
| opt7 | 10.0 | 577 breaks, 3 no toe | 1.06 | 3.33 | −0.88 m (−0.63 H) | 92% | 17.8% | 12.0% | 40.4% |
| opt8 | 8.3 | 727 breaks, 35 translated, 3 no toe | 1.79 | 3.80 | −1.41 m (−0.99 H) | 99% | 26.2% | 11.7% | 39.2% |
| opt9 | 9.5 | 785 breaks, 237 translated, 62 bend dropped, 3 no toe | 1.97 | 4.40 | −1.52 m (−1.06 H) | 100% | 27.7% | 11.3% | 38.2% |
| opt10 | 8.6 (16 processes; 27 in one) | 46 outline-wide, 2 option 9 | 1.90 | 4.13 | – | – | 29.5% | 11.5% | 39.0% |

The median share of each line inside its ground step 3 element (the face
cells, with the rounded crest and toe cells) is 0.97 for the spine, 0.98 to
1.00 for the pip variants, 0.97 for option 4, and 0.69 (option 2) and 0.81
(option 3) on the points, 0.92 for option 5, 0.93 for option 6 and 0.92 for
option 7, 0.74 for option 8 and 0.68 for option 9, whose lines mostly lie
on or past the toe edge of the element.

Bend counts against the spine's (rows the spine, columns the fit), option 4
then option 5:

| Spine bends | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| 0 | 1,346 | 1,891 | – | – |
| 1 | 117 | 685 | 205 | – |
| 2 | – | 214 | 147 | 20 |
| 3 | – | – | 59 | 56 |

| Spine bends | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| 0 | 1,346 | 1,891 | – | – |
| 1 | 154 | 707 | 146 | – |
| 2 | – | 242 | 120 | 19 |
| 3 | – | – | 66 | 49 |

## Findings

1. Every variant moves the line downslope: on the pips by 0.6 to 0.8 m at the
   median, to where the ground is about half the wall's height below the
   spine's, so the line reads the middle of the step on the 1 m DEM; on the
   pips and their 1 m points by 1.5 to 1.8 m, to near the foot of the face
   (0.83 to 0.96 of the height down), and partly past the element's toe.
2. Option 2 keeps the spine's shape and is about five times faster. Its shift
   breaks the line rules on 5 to 6% of units (a vertex pushed past a short
   section or a sharp turn), which are shifted whole.
3. Option 3 follows the downslope edge between the spine's vertices and
   breaks the rules on only 1 to 3%. It moves the line less at the median,
   because the simplification keeps the line within 0.5 m (or more) of the
   moved points, and 6% of its lines end up higher than the spine where the
   simplification cuts a corner.
4. The snap adds 0.04 to 0.11 m to the median move, and puts at most 1% more
   units on a property boundary. Most pif lines near a
   boundary are already within the 2 m the wall points read.
5. The wall probability changes through the line in three ways. The length
   points (−5 under 5 m) move with option 2, which shortens lines where
   vertices close in on the inside of a bend: 19.7% of units under 5 m on the
   spine, 22.7 to 23.0% on option 2, 19.6 to 20.7% on option 3. The setting
   points read the share of the line within 2 m of a boundary or road, which
   barely changes (road frontage 11.4% to 12.0%). The primary property, which
   carries the age points, the NZMM flag and the claim update, changes for 12
   to 14% of units on the pips and 23 to 24% on the points, because a wall
   often stands on a boundary and a move of under a metre puts most of its
   line on the next property. The building distance (`building_m`) is read
   off the pif's pips (ground step 4, `wall_candidates._nearest_m`), not the
   line, so no variant changes it. The base probability is solved for the
   pilot's expected walls, so any variant taken into the pipeline needs that
   solve rerun.
6. Option 4 follows the toe band closely where the pif is a band along one
   face (the median toe point lies 0.53 to 0.58 m off the fitted line,
   against 0.64 to 1.26 m off the spine). The spine's ends are usually toe
   points already (median 0 m from one), but holding them fixed means a
   straight spine can only stay where it is (1,346 units, 28%, unmoved) or
   take one bend to reach down to the toe (1,891), which makes a shallow V
   and lengthens the line (median 1.05 times the spine, 1.27 at the 75th
   percentile). Over a wide field of pips (a hillside rather than a wall)
   most points have a pip below them, the toe points are few and far off,
   and the fit is pulled across the field. It takes 25.5 s on the pilot, as
   a Python loop of three fits a unit.
7. Option 5 moves every line, by 1.22 m at the median, to where the ground
   is two thirds of the wall's height below the spine's: the foot of the
   face plus the 0.4 m. The median moved toe point lies 0.48 to 0.56 m off
   the fitted line, against 0.99 to 1.45 m off the spine. With the ends free
   to move to the toe, a straight wall is shifted whole rather than left
   behind; the shallow Vs remain where the toe bows away from the spine's
   chord (1,891 straight spines take a bend). Its lines are 1.03 times the
   spine at the median but 3.7 times at the 99th percentile, up to 10.6
   times: a short spine on a wide field of pips, whose nearest toe points
   lie metres off, and at an inside corner the fit can spike towards the
   other face's toe. The primary property changes for 18% of units.
8. Option 6's 60° angle cuts the toe points from 169,144 to 99,544 and keeps
   the lines close to the spine's length (0.98 times at the median, 1.69 at
   the 99th percentile, 2.9 at most), so the long lines of option 5 go. The
   median moved toe point lies 0.59 m off the line. Held to the spine's
   bend count, a straight spine stays straight: where the toe bows away
   from it the line takes the chord between the end toe points and can sit
   back near the spine in the middle. 561 lines (12%) break the wall line
   rules, mostly by being under 3 m (365): on a short spine the toe points
   nearest its ends lie inside them, so the line is shorter than the spine
   (median 2.8 m against 4.5 m for those units), and 25% of option 6's lines
   are under 5 m against 20% of the spines. The inside-corner spike of
   option 5 remains where the spine has bends to seed it.
9. Option 7's 8 m look cuts the toe points from 99,544 to 92,641; 1,683
   units lose some. Most lines barely move: 841 (18%) move more than 0.5 m
   from option 6's, 238 more than 5 m. It does not remove the toe points
   along the cut between two pieces of a split pif (30% of pif units are
   such pieces), since only the piece's own pips are checked. At
   WU0004580, a piece of a hillside pif and the largest move (25 m), it
   drops the toe points in the middle of the field, where a gap in the pips
   left them clear at 5 m and option 6's line started at one; option 7's
   line runs 46 m along the piece's lower cut edge instead. Three small pifs, whose pips face each other within
   8 m, have no toe point and keep their spine.
10. Option 7's ends were the toe points nearest the spine's ends. On a
    straight spine near the crest these can be the pif's uphill corners,
    and the line then ran diagonally across the face; 30 of its lines were
    zero length, both ends on one toe point. Trimming each world 0
    evacuated polygon at its wall's line (a scratch test, the lead,
    2026-10-12) showed it: 567 of 4,661 polygons (12%) lost over a quarter
    of their own pif's pips, the face, to the trim. Option 8 projects each
    end down the fall, and that falls to 204 (4.4%). Its ground on the line
    is a whole wall height below the spine at the median (−1.41 m) and lower
    at 99% of units. Projected ends shorten short lines: 28% are under 5 m
    (20% of spines) and 727 break the wall line rules, mostly by length.
    Using the falls of the pips near each end, rather than the pif's mean
    fall, did worse (228 and 216 polygons for 3 m and 6 m), as the pips at
    a pif's corners fall across the face. The 35 translated spines are the
    worst placed: 16 of them cut away over a quarter of their pips.
11. Option 9 cuts the trimmed polygons that lose over a quarter of their
    pips to 146 (3.1%), and the evacuated area removed to 10.6%. No fitted
    line turns back more than 100° (447 of option 8's lines did, and 76
    spines). Two costs: on a short spine the two 45° sectors overlap, so
    both ends often take the same lowest toe point and the spine is
    translated (237 units, median spine 4.2 m); and lines are shorter, 33%
    under 5 m, with 699 of the 785 rule breaks under 3 m. The 62 lines whose
    bend had to be dropped are the worst for the trim (13% cut away their
    face): the ends turn the line back on itself, and with the bend gone the
    line is a chord across the face.

12. Option 10, scored on the pilot by the brief's proxies with option 9
    beside it (`temp/wall-line-brief/options/run_a_cone_pilot.py`): 73% of
    its lines lie within 1 m of the slope toe (69%), the median toe gap is
    −0.5 m for both, 81 of the 4,661 trimmed evacuated polygons lose over a
    quarter of their pif's pips (146), 22 counting only the pips of the
    wall's own pif, and 154 lines break the rules (785), all of them under
    3 m on pifs of a median 6 pips. Its lines are regular: 3,225 straight,
    1,174 with one bend, 318 with two, 23 with three. 929 units (20%) get a
    pif with no wall, 1,291 in all, holding 13% of the pips. On the 120
    cases it reproduced the lines the lead reviewed; four good cases lose
    part of their pif to a no-wall pif where the line stops short of the
    face (WU0000753, WU0002463, WU0003983, WU0003507). The no-wall pifs are
    written as pieces here (`pifs-opt10.gpkg`); ground step 3 does not yet
    split them, so their units and the base probability are unchanged.

## Caveats

- The fall is the nearest of the eight directions the pip test reads, so on a
  diagonal step the 0.4 m is along the diagonal.
- No ground truth is used. Where the wall stands is judged from the QGIS
  project and the DEM check above, not from mapped walls; the GNS mapped walls
  would be the check to run next.
- The zones are not rebuilt. A siz unit's evacuated polygon is grown from its
  pips whatever its line, so only the line moves. A low-height or GNS-only
  unit's line element and a forced polygon are drawn from the line, so they
  would move with it.

## What it would take

A chosen variant would be computed in ground step 3 beside `spine` (as a
`wall_line` column, the spine still used to cut the pifs and join their ends),
read by exposure rw step 6 as the unit's line, and the base probability
solved again. Option 10 also splits the no-wall pifs off as pif pieces of
their own, with no wall unit, before the elements are grown, so their
evacuated polygons are bare.
