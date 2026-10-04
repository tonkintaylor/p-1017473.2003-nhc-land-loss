# Slope elements and polygons on real pilot ground (stage D2)

Findings from `fig_pilot_example_slope_elements.py` in this folder, first run on
2026-10-03 and rerun on 2026-10-04 with the water mask and the lead's decisions. To
run it from the repository root (about 40 s):

```
uv run --frozen python src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_slope_elements.py
```

This is stage D2 of `.agents/plans/building-face-based-urban-slope-polygons.md`. The
settings, including the 12 sites and the reason each was picked, are in `config.py`
beside the script. The figures are in `report/hazard/landslide/slope-elements/fig/`
(`pilot_site_NN-name-pilot.png` and `pilot_sites_overview-pilot.png`).

## Question

Do the elements (phase 1) and polygons (phase 3) that passed the 19 toy grids behave
sensibly on real ground, and where they disagree with the GNS mapping of walls and
breaks in slope, is the model or the map at fault? No `BETA_` value was changed here:
nothing in the sites gave evidence to change one, and the grow tolerance was settled
at 3° (see "Decisions").

## Decisions

Made by the lead on 2026-10-04:

1. **Run-out over flat ground fans out.** Site 03's wide fan is as intended.
2. **The sea is masked with the LINZ coastline.** The mask is the NZ Coastlines and
   Islands Polygons (Topo 1:50k), layer 51153 (`get_nz_coastline_polygons`). Cells
   outside the land polygons are no data when the library runs.
3. **The grow tolerance stays at 3°** (the lead left the call to the build). On the
   pilot the result is the same at 2°, 3° and 5° (below), so the toy result decides:
   5° let a cut grow into the bank above it under noise (16 to 30 of 30 seeds, by
   case) and 3° passes 30 of 30.
4. **Site 05 disables banks for the re-run.** `config.py` sets its bank slope to
   100°, so the excavated-toe figure shows the free-face and the material legend
   calls out weak and stronger rock rather than a bank seed class.

| `BETA_FREE_FACE_GROW_TOL_DEG` | Elements | Free-faces | Polygons | Stack polygons | Land evacuated | GNS wall cells with a free-face | Sharp breaks matched |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2° | 10,765 | 7,589 | 12,520 | 1,026 | 22.5% | 64.2% | 86.9% |
| **3°** | 10,750 | 7,484 | 12,466 | 937 | 22.5% | 64.8% | 87.0% |
| 5° | 10,563 | 7,216 | 12,245 | 800 | 22.4% | 65.8% | 87.1% |

## Method

- **One run over the whole pilot**, then windows cut from it for each site, so a site
  sees the same elements it would in the full build. The library was run unchanged
  (`find_slope_elements`, `build_slope_polygons`) on the 1 m DEM of `wlg-pilot`.
- **Water mask.** The land polygons are rasterised to the DEM grid and every cell
  outside them is set to NaN for the run (11% of the grid). The Topo50 line agrees
  with the DEM: the sea is a flat -1.404 m, and only 60 of 773,722 masked cells
  stand above 1 m. A few thousand cells of the flat sea sit just inside the polygon,
  so a seawall's face to the sea bed is still found.
- **Ground.** Each element's ground group is the majority of the ground map under it
  (`ground_row`). `is_fill` and `fill_thickness_m` come from the ground map's
  `modification == "fill"`. The fill thickness is whatever the map carries.
- **Comparison data.** The GNS morphology layer (retaining walls, sharp and rounded
  breaks in slope, cut/fill lines) and the SLIDE genesis layer (cut slopes, fill
  bodies), read with `get_gns_slide_morphology` and `get_slide_genesis`.
- **Figures.** Each site is four map panels that walk through the method, each with
  its own legend. (1) The seeds alone, drawn as dots so the ground map's material
  shows through: free-face seeds, which are the steepest cells (a step of 0.5 m or
  more, or a 3 m slope over the step-test angle, trimmed to the step), and bank
  seeds, which are the ground left over steeper than 18.4° except for site 05, where
  `config.py` raises the bank slope to 100° for the re-run. The site 05 legend names
  weak and stronger rock. (2) The elements grown from those seeds, each outlined. The crest and
  toe cells are not drawn: they matter to the polygons (the width is measured behind
  the crest, the runout from the toe), not to showing the elements. (3) The
  free-faces as retaining wall candidates, coloured by whether a GNS wall (within
  2 m) or a GNS sharp break (within 3 m) lies near, with element heights. This is the
  only panel that draws GNS lines, and only those two layers. Phase 2 is not built, so every free-face takes the wall
  wedge; this panel shows evidence a wall probability could weigh and is not that
  method. (4) The polygons: each evacuated polygon's own edge, over fills for the
  evacuated, imminent and inundated zones. The library does not keep the seeds, so
  the script reruns its private `_free_face_pass` and `_bank_pass` to recover them.
  Bank seeds already take every cell over the bank angle, so a bank is one region
  however large and the polygons are where it is split. The
  overview draws every polygon's evacuated ground over the pilot. The plot code is
  self-contained: `fig_toy_slope_elements.py` was being refactored when this was
  built, so only its colours were copied. A palette change there will not carry over.
- **Agreement with GNS** is counted by cells on the 1 m grid, over the whole pilot,
  with a distance transform to the nearest wall, break or element edge.

## Sites

The table gives each site's window (free-faces and banks whose centroid is inside, the
tallest free-face, polygons, how many of them took the wall rule and the headscarp band,
stacked polygons, evacuated area and volume, fill elements, and the GNS wall length).

| Site | Free-faces | Banks | Tallest m | Polygons | Wall rule | Band rule | Stacks | Evacuated m² | Volume m³ | Fill elements | GNS wall m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01 wall, soil | 44 | 14 | 4.6 | 62 | 44 | 1 | 3 | 5,840 | 8,141 | 55 | 288 |
| 02 wall, tall | 27 | 10 | 7.3 | 37 | 27 | 2 | 5 | 2,819 | 3,339 | 31 | 192 |
| 03 wall, flat | 17 | 10 | 9.5 | 41 | 27 | 4 | 14 | 5,596 | 19,550 | 19 | 192 |
| 04 road cut | 13 | 5 | 15.9 | 21 | 16 | 2 | 5 | 4,872 | 5,854 | 9 | 0 |
| 05 excavated toe | 30 | 6 | 11.3 | 37 | 31 | 1 | 3 | 3,419 | 2,924 | 25 | 139 |
| 06 fill platform | 26 | 16 | 9.1 | 43 | 27 | 5 | 3 | 4,783 | 3,253 | 29 | 9 |
| 07 large fill, cut | 48 | 17 | 3.8 | 68 | 48 | 2 | 3 | 5,237 | 5,036 | 61 | 250 |
| 08 adjacent catchments | 28 | 17 | 4.3 | 48 | 28 | 0 | 2 | 3,609 | 6,331 | 45 | 341 |
| 09 seawall | 3 | 13 | 1.8 | 16 | 3 | 0 | 0 | 1,419 | 641 | 16 | 0 |
| 10 steep bank | 43 | 22 | 7.6 | 65 | 43 | 0 | 5 | 4,384 | 5,467 | 65 | 168 |
| 11 mapped failure | 11 | 7 | 7.0 | 21 | 11 | 1 | 3 | 2,561 | 7,084 | 13 | 2 |
| 12 gentle control | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Large elements cut into many polygons, over every polygon that reaches each window
(including elements whose centroid is outside it). No polygon is large (the biggest is
1,664 m²), because the volume segmentation caps them; the large thing is the element
they are cut from, so a big bank becomes a strip of narrow polygons along its contour.

| Site | Polygons reaching | Largest polygon m² | Most polygons from one element | Largest element m² |
| --- | --- | --- | --- | --- |
| 01 wall, soil | 69 | 731 | 5 | 1,312 |
| 02 wall, tall | 43 | 705 | 1 | 1,462 |
| 03 wall, flat | 45 | 697 | 7 | 1,157 |
| 04 road cut | 43 | 959 | 16 | 45,132 |
| 05 excavated toe | 89 | 888 | 47 | 72,255 |
| 06 fill platform | 76 | 1,664 | 20 | 15,328 |
| 07 large fill, cut | 78 | 702 | 4 | 2,044 |
| 08 adjacent catchments | 58 | 692 | 3 | 15,691 |
| 09 seawall | 17 | 1,124 | 1 | 1,095 |
| 10 steep bank | 76 | 694 | 5 | 15,691 |
| 11 mapped failure | 29 | 684 | 4 | 888 |
| 12 gentle control | 0 | 0 | 0 | 0 |

## Whole pilot

- 10,750 elements: 7,484 free-faces and 3,266 banks. 7,511 (about 70%) are on fill.
- 12,466 polygons: 8,281 fill flow slides and 4,185 dry debris avalanches.
- Width rules: 7,630 wall wedges, 2,930 fill-bank wedges, 1,906 headscarp bands.
- 937 stack polygons. Overlaps: 4,458 `within_width`, 3,045 `stack`, 5
  `separate_catchments`. 20,644 retrogression links.
- Evacuated ground is 1,497,519 cells (1,383,756 distinct): **20.0% of the grid and
  22.5% of the land**, none of it on masked water. Before the mask, 1,500,226 cells.
- Runtime 31.2 s for the pilot.

## Agreement with GNS

| Check | Share |
| --- | --- |
| GNS wall cells with a free-face within 2 m | 64.8% |
| GNS wall cells with any element within 2 m | 83.2% |
| GNS sharp-break cells with an element crest or toe within 3 m | 87.0% |
| GNS rounded-break cells with an element crest or toe within 3 m | 70.2% |
| Free-face crest cells within 2 m of a GNS wall | 14.6% |
| Free-face crest cells within 3 m of a GNS break | 31.9% |
| Free-face crest cells within 3 m of any GNS wall, break or cut/fill line | 47.6% |
| Free-face crest cells inside a SLIDE cut slope or fill body | 16.9% |

The first four rows ask whether the model finds what the map shows, and it mostly does.
The last four ask the reverse and the answer is low: only 15% of free-face crests are on
a GNS wall. That is expected, not a failure. Most free-faces are cut batters, terrace
edges and natural steps that GNS does not map as walls, and GNS mapped retaining walls
and breaks only where its mappers saw them. 14.6% is not a precision figure for the
model.

## Findings

1. **The model finds the mapped walls.** At site 01 the crest and toe sit on the GNS
   wall and the wedge is narrow, as a 2.9 m wall on soil-like ground should give. 84% of
   GNS wall cells have an element within 2 m, and 87% of sharp breaks have a crest or
   toe within 3 m.
2. **GNS holds no wall height.** The plan asked for "a GNS mapped wall of known height".
   The layer has `Type`, `Subtype` and `SHAPE_Length` only, so a wall's height here is
   the height the model measures from the DEM under the free-face. The sites compare
   position, not height. A height check needs a source of surveyed wall heights, which
   the project does not have.
3. **The coast is masked, and the seawall stays.** The DEM's sea surface is flat at
   -1.404 m, so every seawall was a free-face against it, and the first run gave
   evacuated, imminent and inundated zones in the water. With the LINZ mask no
   evacuated cell is on water and the pilot's polygons fall from 12,478 to 12,466.
   Site 09 still has its 428 m free-face, 1.8 m high: the Topo50 line lies a few
   metres seaward of the wall, so the face down to the sea bed is inside the land
   polygon. That is a real wall, not water, so it is kept. The mask is a few lines in
   this script, so the pipeline step must carry it (phase 0).
4. **Run-out over flat ground fans out, as intended.** Site 03 shows the inundated
   reach of a polygon spreading as a wide fan, tens of metres wide, across a flat car
   park or terrace below a 2 m step. The lead confirmed this on 2026-10-04.
5. **Weak-rock banks and fill banks get very large polygons.** Sites 04, 05 and 10 have
   banks near 27 to 35° on weak rock or fill whose polygons cover whole hillsides.
   Site 04's tallest free-face is 15.9 m at 56° in weak rock and the stack above it
   takes up to five elements. Site 05's 11 m free-face carries fill-bank polygons far
   upslope. At 20% of the pilot evacuated, these hillsides dominate the number. They
   are the likeliest place for the order-of-1% check in D3 to fail.
6. **Fill is probably over-assigned.** About 74% of the ground map by area is fill, and
   70% of elements are on fill. The ground map's step 4 rerun is pending, so this is a
   map caveat, not yet a model result. Every number above that depends on fill (the
   fill-bank wedges, the fill flow slides, run-out) moves when the ground map does.
7. **Platforms are left alone.** Site 06's flat fill platform, about 100 m across,
   has no element inside it. Only the rim batters get polygons, as intended. Site 07,
   a deep cut beside the pilot's largest fill body, shows the same: elements sit on
   the cut walls and the rim, and none on the flat floor. The site was first picked as
   a fill in a gully. The figure shows a quarry-like cut with a fill rim, and the
   reason in `config.py` was reworded to match.
8. **The control holds.** Site 12 (about 4°) has no element and no polygon. Across the
   pilot nearly every 50 m window above about 8° has an element within 20 m, so a
   gentle site is a fair control.
9. **One `separate_catchments` pair at site 08.** Its polygons are small and the rule
   fires only five times across the pilot.
10. **The mapped failure sits inside a polygon.** At site 11, the single SLIDE recent
    landslide (a source area of 3.5 m²) lies on a 5 m free-face and the polygon's crest
    takes the scar. One event is not a test of the model.

## Pips, pifs and sizs (2026-10-04)

The lead rejected the bank seeds, so the seeding above was replaced
(`.agents/plans/building-pip-pif-siz-slope-polygons.md`;
`landloss.hazard.landslide.instability_zones`). Everything above this section
describes the earlier seeding; the figures it quotes were drawn with it. The new
figures are `pilot_instability_<site>-pilot.png`, four map panels: pips (orange in
a siz, blue not), the elements grown from the sizs, and the evacuated zones with
every siz walled and with none walled
(`fig_pilot_example_instability_zones.py`).

- **Rules.** A pip is a cell that drops more than 0.7 m per metre of distance
  (scaled by 1.41 on diagonals) to the cell 1, 3 and 5 away in one of eight
  directions, from the DEM alone. Pips within 2 m form a pif. A pif is a siz if
  any pair of its points under 3 m apart differs by the group's near step (soil
  0.7 m, rock 3 m), or any pair 3 m or more apart is steeper than the group's
  angle for its height (35, 45, 53 degrees under 3.5 m; 32, 40, 48 from 3.5 m;
  soil, weak rock, stronger rock). Fill is soil. The sizs are grown with the
  existing watershed growth and the pif table (`temp/pilot-siz-pilot.parquet`:
  maximum angles above and below 3.5 m, delta_h, the siz flag) is kept for the
  retaining wall workflow.
- **Counts.** 353,740 pips, 12,015 pifs, 8,223 sizs (7,709 of 7,709 soil, 514
  of 4,306 weak rock) and 5,441 elements.
- **Speed.** 24.5 s for pips, pifs, sizs and growth, and 6.5 s (walled) and 7.8 s
  (unwalled) for the polygons, against 27 to 40 s for the old pipeline (same
  machine, different load), so about the same speed.
- **Against the old pipeline** (banks off at 100°, two-band table): 7,093
  evacuated polygons, 423,467 m² in total, largest 2,142 m². New walled: 5,513
  polygons, 619,213 m², 28 over 2,000 m²; new unwalled: 6,298 polygons, 603,495
  m², largest 1,631 m². There is no minimum pif size (half of the pifs have 3
  pips or fewer); only the element filters apply.
- **Site 05.** The hillside on the right gives one polygon of about 970 m², about
  ten of 50 to 240 m² and a scatter of fragments under 35 m², in the walled run
  (the unwalled run is the same shape).
- **Large polygons.** 28 evacuated polygons in the walled run exceed 2,000 m²
  (largest 4,694 m², at about 1749712 E 5424518 N), none inside a pilot site; the
  unwalled run has none. They are in the walled run's printed table for the lead
  to review before any threshold moves. Sites 07 and 08 read reasonably.
- **Not confirmed by the lead:** the 30 m pair cap, the 1.41 diagonal scaling,
  the support points, and every soil pif being a siz.

## What was not done

- **Phase 2 walls.** Not built, so every free-face takes a wall's wedge on φ' 42°. At
  the cut and natural free-faces that dominate the pilot this is the toy findings'
  caveat at 7,630 elements.
- **Overlap with the large model.** Counting how much of an urban polygon reaches
  slope-unit ground (the Hancox model's) was not done. It belongs in D3.
- **Ground map extent.** The ground map covers x 1748323 to 1751191 and y 5423605 to
  5425336, inside the DEM's bounds. Elements near the DEM edge have no ground row, and
  take weak rock. The sites sit inside the map.
- **The grow tolerance** is settled at 3° (see "Decisions").

## Points for the lead

1. Are the weak-rock hillside polygons (finding 5) acceptable, or does the free-face
   test angle on weak rock need to rise? `BETA_` values stay as they are until the
   lead says.
2. The mask handles the sea only. Does the study need lakes, harbour reclamations or
   the Wellington Harbour edge handled differently? (The mask follows Topo50, so a
   reclamation newer than the map is masked as sea.)
3. Sites 05 (72,255 m², 47 polygons from one bank), 04 (45,132 m², 16) and 06
   (15,328 m², 20) have a single huge bank element split into many narrow polygons;
   sites 07 and 08 read reasonably. Is that the right split, or should a large
   bank be cut into fewer, larger polygons, or into elements at its asperities? No
   threshold has been changed.

   The narrow polygons are the volume segmentation working as designed on an element
   it was not shaped for. `_segments` cuts an element along its contour, by running
   evacuated volume (1,000 m³), at positions measured with the element's single mean
   aspect. The cuts are therefore parallel lines at a fixed bearing, perpendicular to
   the contour. That suits a wall or cut whose evacuated ground is a few metres
   behind the crest. Site 05's bank is 454 m long and runs the whole hillside, so each
   slice is about 5 m wide across the contour and 60–475 m long down the fall line
   (109 slices from that one element, 47 of them in the figure window, median 675 m² each). They run diagonally
   because the mean aspect is 308°, and the edges are staircased because the cut
   position is binned on the 1 m grid. Options, if the lead wants a change: split a
   bank into sub-elements at asperities before measuring; cut perpendicular to the
   local contour instead of at the mean aspect; cap how far a bank grows downslope; or
   segment by downslope distance as well as along the contour.

## Re-running

No inputs besides the pilot DEM (`dem-1m-pilot.tif`, step 3), the ground map
(`ground-map-pilot.geoparquet`, step 4) and the LINZ coastline polygons (fetched and
cached on the first run) are needed. If the ground map is rebuilt,
rerun this script and update the numbers above. If a `BETA_` value is changed in the
library, also rerun the 19 toy cases and `uv run --frozen pytest tests/landloss/hazard/landslide`.
