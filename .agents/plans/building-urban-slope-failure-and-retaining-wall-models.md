# Plan: building the urban slope failure model and the retaining wall model together

## Context

Model 6 of the landslide portfolio (`src/scripts/landloss/hazard/landslide/
potential-landslide-rebuild.md`, "The models") is the urban model: the small
failures on modified and natural slopes in and beside insured land that the
team expects to carry most of the loss (`.agents/context/land-damage-mechanisms.md`).
The retaining wall exposure (`src/scripts/landloss/exposure/rw/status.md`) is
the population of walls those slopes are held up by. The two have been planned
separately, and the step 6 wall population and the step 1 landslide realisation
run today with no link between them: a wall never holds a slope up, and a wall
that fails by shaking takes no ground with it.

The link is the point. Steep modified ground predicts both a wall and a
failure, and every inventory the models could be calibrated on records failures
net of the walls that existed. The design agreed on 1 October 2026 couples the
two at the realisation: a polygon of sloping land either has a wall, and then
fails if and only if the wall fails, or has none, and then fails through its
own fragility. Kingsbury (1995) is the published precedent, treating the wall as
an attribute of the modified slope (section 4.4.2: retained slopes designed for
seismic loading drop out of the high class; inadequate crib, shotcrete and light
concrete walls stay moderate to high) [kingsbury_1995].

The build is a chain of small, single-purpose scripts. The non-probabilistic
ground work comes first and is shared: terrain derivatives, a reconciled ground
map, slope units, candidate wall lines and candidate failure polygons. The
probabilistic parts, wall probabilities, polygon fragilities and the draws, come
after and read those products. Section 3 lists every script with its input,
method and output; it is the implementation plan.

Evidence from the GNS report review in `temp/gns_review/` is cited by its
finding id (for example `sr2013-058-F17`); each id resolves to a page and a
verbatim quote in `temp/gns_review/out/findings.csv`. `temp/` is not tracked, so
anything relied on in code or in the report is to be copied into
`context/lit/` with its citation. Citation keys in square brackets refer to
`doc/references.bib`.

## Decisions and assumptions

| Decision | Choice | Basis |
| --- | --- | --- |
| How sloping land fails | One of three ways and no other: in a large-model landslide, which supersedes the urban polygon; through its retaining wall, when the wall fails; or, with no wall, through a localised failure fragility. A polygon with a wall attached fails with the wall and only with the wall | Decided 2026-10-01 |
| Whose fragility | Every fragility belongs to a polygon. A polygon with a wall takes its fragility from the wall's class, size and condition; a polygon without one takes the localised fragility from its own attributes | Decided 2026-10-01 |
| Where the urban model runs | Off the NLM flatland, within 100 m of a building outline, on every territorial authority. No insured land mask | Decided 2026-10-01 |
| Flat-land walls | Stand alone with no polygon. `vul/shaking/rw` step 9 keeps them, on PGV-based curves, and is restricted to them | Decided 2026-10-01 |
| Order of construction | Candidate polygons are first found from the terrain alone, non-probabilistically. Candidate wall lines are then established, and the polygons are reconciled to them: snapped and split so a wall is always a polygon edge | Decided 2026-10-01 |
| Property boundaries | Split the candidate wall lines only. Polygons follow the terrain and are not split | Decided 2026-10-01. Walls rarely run across a boundary except in the road corridor; council walls are out of scope (**I-05**) |
| Walls below 0.5 m | Not modelled | Decided 2026-10-01 |
| Wall height | Read from the 1 m DEM at the line and classed small (below 1 m), medium (1 to 2.5 m), large (above 2.5 m). No height distribution | Decided 2026-10-01 |
| Wall condition | Modern or poor, drawn against a probability set from the dwelling age where held, from the height (a wall under 1.5 m is likely unconsented and so more likely poor) and from the wall type where known | Proposed; Nick Peters' advice in `exposure/rw/status.md` |
| Claim report extraction (**T-50**) | A later phase, arriving as a minimum and maximum number of walls per property. It runs before the probability script and modifies the line probabilities inside each property | Decided 2026-10-01 |
| Nested polygons | Allowed, from delineation at several scales. Overlaps are resolved largest first at the draw | Decided 2026-10-01 |
| What a polygon stores | A fragility function of the demand, a lognormal CDF with a median and a dispersion, not a probability | Decided 2026-10-01 |
| Intensity measure | PGV for every fragility, the flat-land wall curves included. Published PGA-based curves are converted with the study's own PGV to PGA ratio | Decided 2026-10-01 |
| Where PGV is sampled | At the polygon's representative point, the point nearest its centre | Decided 2026-10-01 |
| Dispersion of the localised fragility | 0.6 until the anchoring sets it; the wall curve sets carry their own | Assumed 2026-10-01 |
| Topographic amplification | Folded into the polygon's fragility median | Decided 2026-10-01 |
| Urban failure rate setting | A config value, low, medium or high, scaling every urban fragility median by one factor, written into the model file and printed by every run | Decided 2026-10-01 |
| Realisation structure | Exposure worlds `w` and hazard earthquakes `r` are separate indices with separate seeds. One world for now; many earthquakes | Decided 2026-10-01 |
| Identifiers | Every candidate wall line, drawn wall and failure polygon carries a unique id; a wall's outcome records the polygon it belongs to, null on flat land | Decided 2026-10-01 |
| The large and small split | By population, not by one area. Urban polygons carry their own sizes; the share removed from the large models' coverage is the share of the calibration inventory inside the urban size range | Decided 2026-10-01; evidence in section 10 |
| Slope units | Delineated early, after the ground map, as the realisation unit of the large models | Decided 2026-10-01 |
| Ground map | One reconciled, non-probabilistic map of material, modification, flatland, groundwater and prior failure, built before anything that reads geology | Decided 2026-10-01 |
| Fixed geometry | Each polygon carries fixed evacuated, inundated and imminent-risk polygons keyed by its wall state; a realisation only decides whether it fails | Accepted 2026-10-01; rules to be researched (section 7) |
| Data not coming | The SME suburb estimate, the manual mapping, the remote sensing pilot and the ICNZ database | Decided 2026-10-01 |

## 1. The objects and their ids

| Object | Id | Minted by | Varies by world |
| --- | --- | --- | --- |
| Candidate wall line | `wall_line_id`, `WL<nnnnnnn>` | `gen_wall_lines.py`, sorted by location | No |
| Drawn wall | `rw_id`, `<claim_id>-RW<nn>`, carrying its `wall_line_id` | `gen_wall_population.py`, as now | Yes |
| Candidate failure polygon | `candidate_id` | `gen_urban_slope_candidates.py` | No |
| Failure polygon | `slope_id`, `SP<nnnnnnn>`, carrying the `wall_line_id` on its edge if any | `gen_urban_slope_polygons.py`, sorted by location | No |
| Failure in a realisation | `landslide_id`, carrying `slope_id` for urban failures | the realisation scripts | Per world and earthquake |
| Ground map polygon | `ground_id` | `gen_ground_map.py` | No |
| Slope unit | `unit_id` | `gen_slope_units.py` | No |

### 1.1 Candidate wall lines (exposure)

A line where a wall could stand. Sources, in the order they are trusted: the GNS
SLIDE mapped retaining walls (`get_gns_slide_morphology`, 11,288 segments,
about 280 km, Wellington City only, visible from above: evidence a wall exists,
never that one does not); the edges of the SLIDE genesis cut slopes and fill
bodies (`get_slide_genesis`, 2,987 cuts and 1,606 fills) and the SLIDE cut and
fill lines; breaks in slope in the terrain derivatives on sloping ground within
100 m of a building, a face of 0.5 m or more steep at 1 m inside ground gentle
at 10 to 30 m, the terrace-and-face signature of a cut, a fill or a wall; and
section boundaries, road frontages and driveway edges on sloping ground.

Each line is split at property boundaries and carries: its face height from the
DEM and size class; the material under it from the ground map, so that a rock
cut lowers the chance of a wall (Oriental Bay and Evans Bay are the worked
examples in `exposure/rw/status.md`); fill wall or cut wall, from its position
against the local aspect, a wall on the downhill edge of a platform holding fill
or one at the toe of a cut holding the face; and on flat land or not. Walls are
a typical Wellington construction for both cases (`sr2019-040-F32`,
`sr2019-051-F33`), and most hold fill or soil rather than rock (Nick Peters).

### 1.2 Candidate failure polygons (hazard)

A piece of sloping ground, off the NLM flatland and within 100 m of a building,
bounded by its crest and toe breaks in slope, found from the terrain alone at
several scales so that a 1 m face is one polygon inside the 10 m bank that
contains it. Once the candidate wall lines exist, the candidates are reconciled
to them: an edge within a tolerance of a line is moved onto it, and a candidate
straddling a line is split along it. The result is the failure polygon, with
its `slope_id` and the `wall_line_id` on its edge if there is one. Polygons are
not split at property boundaries.

Each failure polygon carries: its geometry and the fixed evacuated, inundated
and imminent-risk polygons for each wall state it can be in (section 7); the
terrain and ground attributes read from the pre-steps; the Kingsbury rating
built from them; and, per world, the one fragility that applies.

The user's example: the 1 m face and the 10 m slope are both rows, each with
its own fragility, and the realisation draws both. If the bank fails the face
is absorbed, its wall flagged, its ground counted once inside the bank's
polygon; if only the face fails, the face's geometry applies. The net chance
that the face's ground is damaged is one minus the product of the two survival
probabilities, so the rate anchoring targets the net rate on ground.

### 1.3 The ground map (hazard)

One non-probabilistic polygon map of the ground, reconciled from every geology
and material source the project holds, with attributes everything downstream
reads: material, modification, flatland, groundwater, prior failure, and the
strength and Kingsbury geology value that follow from the material. Section 9.

### 1.4 Slope units (hazard)

One hillslope facet from a drainage line at the bottom to the ridge at the top,
with one broad aspect, roughly 1 to 100 ha: the unit a large failure is placed
in, not the unit the large models are fitted on. Section 10.

## 2. The realisation structure

- An **exposure world** `w` is one draw of the wall population, seeded from
  `EXPOSURE_BASE_SEED` with the world id and the `"exposure"` stream. One world
  for now; four or five later.
- A **hazard earthquake** `r` is one modelled earthquake: its shaking, its
  large-model landslides, its liquefaction and its urban slope failures, all
  seeded from `BASE_SEED` with the earthquake id and one stream per hazard, as
  `landloss.hazard.realisation` does today. The urban draw is the `"urban"`
  stream of earthquake `r`, reading world `w`'s model file and earthquake `r`'s
  PGV field, and is seeded on both ids.
- Files that depend on both carry both ids, `...-w000-r003...`; files that
  depend on one carry one.
- Loss runs over every pair.

The urban slope draw keeps the earthquake's `r` rather than taking an index of
its own, because it is part of that earthquake: the same PGV field shakes the
large models and the urban polygons, and a claim's causes can only be summed
within one earthquake. A third index would multiply the runs and break that.

Why separate seeds for `w` and `r`: whether a wall exists is a fact we do not
know, not something the earthquake decides. Redrawing walls per earthquake
averages away the uncertainty in the claim count NHC is asking about.

## 3. The scripts, in run order

Steps are numbered in run order within each submodule. The existing landslide
steps keep their numbers: step 3 is extended, step 2's library is reused, and
step 1 is reworked and runs after step 5. Every step folder carries its
`config.py`, implementation plan and method file as `adding-steps-scripts`
sets out, and each `gen_` script has a `fig_` companion drawing its output over
the pilot.

### 3.1 Ground work, non-probabilistic, world independent

**`hazard/landslide/steps/s3_multiscale_slope/gen_multiscale_slope.py`** (exists; extended)

- Input: the LINZ 1 m DEM over the extent.
- Method: block-mean the DEM to 3, 10, 30 and 50 m and compute Horn slope and
  aspect at every scale, as now with 1 and 3 m added.
- Output: `temp/hazard/landslide/dem-<n>m.tif` and `slope-<n>m.tif`, plus
  `aspect-<n>m.tif`, per scale.

**`hazard/landslide/steps/s3_multiscale_slope/gen_terrain_derivatives.py`** (new)

- Input: the 1 m DEM, the coarser DEMs from the script above, the LINZ 1 m DSM
  where flown.
- Method: face height as local relief in a 5 and a 10 m window; the cut and
  fill residual, the 1 m surface minus the 30 m and 100 m surfaces, negative
  for cut and positive for fill; profile curvature; topographic position at
  two windows; vegetation height as DSM minus DEM.
- Output: one raster per derivative under `temp/hazard/landslide/terrain/`.

**`hazard/landslide/steps/s4_ground_map/gen_ground_map.py`** (new)

- Input: the 1:50,000 geology (`get_wellington_urban_geology`), the SLIDE
  interpreted materials and genesis layers, the WCC earthworks polygons, the NLM
  geomorphology, flatland and groundwater depth, the cut and fill residual, the
  strength table in `src/landloss/io/assets/`, and later NZGD boreholes.
- Method: reconcile the sources by precedence into one polygon map and attach
  the attributes in section 9; no probability anywhere.
- Output: `temp/hazard/landslide/ground-map[-pilot].geoparquet`, one row per
  `ground_id`.

**`hazard/landslide/steps/s5_slope_units/gen_slope_units.py`** (new)

- Input: the 10 m DEM and aspect, the ground map's flatland flag.
- Method: flow routing on pysheds, a channel network at a tried threshold,
  sub-basins per channel link split into left and right half-basins, neighbours
  of similar aspect merged, units over about 50 ha split by aspect variance;
  section 10.
- Output: `temp/hazard/landslide/slope-units[-pilot].geoparquet`, one row per
  `unit_id`.

**`hazard/landslide/steps/s6_urban_slope_candidates/gen_urban_slope_candidates.py`** (new)

- Input: the slope and aspect rasters at 1, 3, 10 and 30 m, the terrain
  derivatives, the ground map, building outlines.
- Method: take the domain off the flatland and within 100 m of a building;
  segment it at each scale into patches of similar slope and aspect with no
  steepness cut-off (section 8.2); split patches longer than the contour
  length taken from the GNS wall segments; read the terrain and ground
  attributes onto each patch. Walls are not read.
- Output: `temp/hazard/landslide/urban-slope-candidates[-pilot].geoparquet`,
  one row per `candidate_id`, nested rows allowed.

**`exposure/rw/steps/s6_wall_population/gen_wall_lines.py`** (new)

- Input: the terrain derivatives, the ground map, the SLIDE mapped walls and
  cut and fill lines, the genesis cut and fill edges, property boundaries,
  building outlines, roads, the slope candidates.
- Method: build the candidate lines from the sources in 1.1, snap the mapped
  walls to the nearest candidate edge, split every line at property boundaries,
  read the face height from the DEM and class it, read the material from the
  ground map, mark fill wall or cut wall and on flat land, drop faces under
  0.5 m, mint `wall_line_id`.
- Output: `temp/exposure/wall-lines[-pilot].geoparquet`, one row per line, no
  probability.

**`hazard/landslide/steps/s7_urban_slope_polygons/gen_urban_slope_polygons.py`** (new)

- Input: the slope candidates, the wall lines.
- Method: move candidate edges within a tolerance onto a wall line, split a
  candidate that straddles a line, mint `slope_id`, record the `wall_line_id` on
  each polygon's edge, compute the fixed evacuated, inundated and imminent-risk
  polygons and depths for each wall state the polygon can be in from the rules
  in section 7, and compute the Kingsbury rating and the amplification factor.
- Output: `temp/hazard/landslide/urban-slope-polygons[-pilot].geoparquet`, one
  row per `slope_id`, with the per-state geometry as extra geometry columns.

### 3.2 The wall population, probabilistic, per exposure world

**`exposure/rw/steps/s6_wall_population/gen_wall_count_bounds.py`** (later phase)

- Input: the claim report extraction (**T-50**), the address spine.
- Method: read the number of walls per claim and turn it into a minimum and a
  maximum per property.
- Output: `temp/exposure/wall-count-bounds.parquet`, one row per `claim_id`.

**`exposure/rw/steps/s6_wall_population/gen_wall_probability.py`** (reworked to lines)

- Input: the wall lines, the dwelling age where held, the count bounds where
  present.
- Method: a probability per line from its source, slope, height, material,
  position and subdivision age, lifted where a wall is mapped and lowered on
  rock; where count bounds exist, scale the probabilities inside each property
  so the expected count sits within them; a probability of poor condition per
  line from dwelling age, height under 1.5 m and wall type.
- Output: `temp/exposure/wall-probability[-pilot].geoparquet`, one row per
  `wall_line_id`.

**`exposure/rw/steps/s6_wall_population/gen_wall_population.py`** (reworked)

- Input: the wall probabilities, the insured land polygons.
- Method: draw whether each line is a wall and its condition on the exposure
  seed and world id, with the count truncated to the bounds where they exist;
  keep the coverage filter; mint `rw_id` and carry `wall_line_id`.
- Output: `temp/exposure/wall-population-w<NNN>[-pilot].geoparquet`.

### 3.3 The urban model, probabilistic, per exposure world

**`hazard/landslide/steps/s8_urban_slope_fragility/gen_urban_slope_fragility.py`** (new)

- Input: the failure polygons, the wall population for world `w`, the wall
  fragility table and the anchor table in `src/landloss/io/assets/`, the PGV to
  PGA ratio from the shaking grids, `config.URBAN_RATE`.
- Method: join each polygon to the drawn wall on its edge, if that line drew
  one in world `w`; give the polygon the wall-derived fragility by class, size
  and condition, converted to PGV, or the localised fragility from its rating;
  divide the median by the amplification factor and multiply by the rate factor;
  keep the geometry for that state.
- Output: `temp/hazard/landslide/urban-slope-model-w<NNN>[-pilot].geoparquet`,
  one row per `slope_id`, the file for review and the report, with every
  adjustment as its own column.

### 3.4 Shaking per earthquake

**`hazard/shaking/steps/s5_pgv_realisation/gen_pgv_realisations.py`** (new)

- Input: the step 3 PGV grid, the lognormal factor step 4 draws per earthquake.
- Method: scale PGV by the same factor as PGA, so one earthquake's two measures
  agree.
- Output: `temp/hazard/shaking/pgv-r<NNN>[-pilot].tif`.

### 3.5 The draws per earthquake

**`hazard/landslide/steps/s1_landslide_realisation/s1_simulate_landslides.py`** (reworked)

- Input: the large-model coverage raster, the slope units, the size
  distribution above the urban range.
- Method: per unit, the expected failed area from the raster becomes a count of
  failures through the size distribution; each is seeded at the highest-coverage
  cell weighted toward the crest, grown along the facet to its sampled area and
  across neighbouring units when larger than its own; runout as now until
  phase 4 of that step's plan replaces it.
- Output: `temp/hazard/landslide/landslide-realisation-r<NNN>[-pilot].geoparquet`,
  `population` of `large`.

**`hazard/landslide/steps/s9_urban_slope_realisation/gen_urban_slope_realisation.py`** (new)

- Input: the model for world `w`, the PGV field for earthquake `r`, the
  large-model realisation for `r`.
- Method: sample PGV at each polygon's representative point, evaluate the
  fragility, draw on the hazard seed keyed by `w` and `r`, absorb nested
  failures largest first, supersede any urban failure inside a large-model
  evacuated polygon, and write the fixed geometry of the survivors beside the
  large-model polygons.
- Output: `temp/hazard/landslide/landslide-realisation-w<NNN>-r<NNN>[-pilot].geoparquet`,
  with `population` of `large` or `urban` and `slope_id` on urban rows; and
  `temp/hazard/landslide/urban-wall-outcome-w<NNN>-r<NNN>[-pilot].parquet`, one
  row per sloping-land wall with `rw_id`, `wall_line_id`, `slope_id` and
  `outcome`.

### 3.6 Vulnerability, per property

**`vul/shaking/rw/steps/s9_wall_damage_state/gen_wall_damage_state.py`** (restricted, PGV)

- Input: the wall population for `w`, the PGV field for `r`, the wall fragility
  table.
- Method: for flat-land walls only, the PGV-converted wall curve by class, size
  and condition, and a draw as now.
- Output: as now, flat-land walls only, keyed on `w` and `r`.

**`vul/landslide/rw/steps/s11_wall_landslide_damage/gen_wall_landslide_damage.py`** (extended)

- Input: the wall population, the combined realisation, the urban wall
  outcomes.
- Method: set the contract flags per wall from the outcome and the intersections
  (section 5.2); carry `slope_id`.
- Output: as now, keyed on `w` and `r`.

**`vul/landslide/land/steps/s3_landslide_land_damage/gen_landslide_land_damage.py`** (file name only)

- Input: the insured land polygons from exposure step 5, the combined
  realisation.
- Method: as now, per insured land polygon: intersect the evacuated, inundated
  and imminent polygons of both populations, union the inundated pieces, and
  write the area and depth of each kind of damaged ground. This is where the
  chain cycles per property.
- Output: as now, keyed on `w` and `r`.

**`vul/landslide/culverts_bridges/steps/s11_crossing_landslide_damage/gen_crossing_landslide_damage.py`** (file name only)

**`vul/steps/s10_property_damage/gen_property_damage.py`** (ids only)

- Input: the seven files it reads now, by their new names.
- Method: as now, assemble the four tables `loss` reads per claim; a wall is
  insured if it passed the exposure coverage filter, as now.
- Output: the four tables, keyed on `w` and `r`.

### 3.7 Validation

**`hazard/landslide/validations/urban/fig_urban_fragility_anchors.py`** and
**`table_urban_fragility_anchors.py`** (new)

- Input: the anchor table, the fragility functions, the Kingsbury scenario PGAs.
- Method: draw the low, medium and high curves per rating against the anchors
  in section 6; write the class-word-to-fraction table.
- Output: a figure and a CSV under `report/hazard/landslide/urban-fragility/`.

## 4. The fragility rows

Every fragility belongs to a polygon and is a lognormal CDF on PGV:

    P(fail | PGV) = Phi( ln(PGV / theta) / beta )

The row carries `im` (`pgv_m_s`), `theta_base`, `amp_factor`, `rate_factor`,
`theta` (`theta_base / amp_factor * rate_factor`), `beta`, `fragility_basis`
(`wall` or `localised`) and `fragility_source`, so every adjustment is visible.

### 4.1 A polygon with a wall

`theta_base` and `beta` come from the published wall curve sets compiled in
`.agents/context/retaining-wall-fragility.md`, indexed on wall class, size and
condition, held in `src/landloss/io/assets/retaining-wall-fragility.csv` with a
`source` column per row. Condition enters here and nowhere else: a poor wall
takes a lower median, with the shape of the shift taken from the
initial-condition family in [koutsoupaki_2023]. PGA-based curves are converted
to PGV with the study's own PGV to PGA ratio per site class from the shaking
grids, recorded on the row. The six wall classes are still unnamed; until they
are, the table carries one class per size and condition.

### 4.2 A polygon without a wall

`theta_base` is a decreasing function of the polygon's Kingsbury rating,
computed from its own slope at its own scale, face height, material,
modification and groundwater by `landloss.hazard.landslide.susceptibility`,
with the slope factor interpolated rather than stepped so the probability rises
continuously with steepness. The function is set by the anchoring in section 6.
`beta` is 0.6 until the anchoring sets it. Gentle ground gets a very high
median rather than being dropped.

### 4.3 Amplification

`amp_factor` comes from topographic position and slope: 1.0 on even ground,
rising to about 1.5 on crests, spurs and faces steeper than 60 degrees. The
range is bracketed by 1.2 to 1.4 at the crest of Wellington cut and fill slopes
(`sr2019-051-F35`), up to 2 on a Port Hills ridge crest and 1.5 to 4 inside a
deformed area from weak motion (`sr2015-016-F21`, `sr2013-058-F38`), and the
published rigid-block factors of about 1.3 and 1.5 [rathje_bray_2001;
ashford_sitar_2002]. Earthquake sources favour convex crests and spurs where
rainfall favours hollows [meunier_2008]; the gully picture in
`land-damage-mechanisms.md` is about size and material and enters through
section 7.

### 4.4 The rate setting

`config.URBAN_RATE` is `"low"`, `"medium"` or `"high"`, mapped to one
multiplier on `theta_base` by `URBAN_RATE_FACTORS` in
`landloss.domain.constants`. Medium is 1.0 by definition; low and high are set
by the anchoring and bracket the medium by the spread between the anchors. The
setting is written into the model file and printed by every run.

## 5. The realisation draw and the wall outcome

### 5.1 The draw

For each world `w` and earthquake `r`, `gen_urban_slope_realisation.py`:

1. Reads the model file for `w` and the PGV field for `r`, and samples PGV at
   each polygon's representative point.
2. Evaluates each row's fragility and draws a uniform from the `"urban"` stream
   seeded on `w` and `r`.
3. Resolves nesting among the failed polygons largest first: a failed polygon
   whose evacuated polygon intersects a larger surviving one is absorbed, as
   `drop_overlapping()` does today.
4. Reads the large-model realisation for `r`. An urban failure whose evacuated
   polygon intersects a large-model evacuated polygon is superseded: its ground
   counts once, in the large polygon.
5. Writes the evacuated, inundated and imminent-risk polygons of the surviving
   urban failures from their fixed geometry, each with a `landslide_id`, its
   `slope_id`, a `population` of `urban` and its depth, beside the large-model
   polygons. Evacuated polygons never overlap; inundated polygons may, as now.
6. Writes the wall outcome for every wall in world `w` on sloping land:
   `rw_id`, `wall_line_id`, `slope_id` and `outcome`, one of `standing`,
   `failed_with_polygon` (the polygon failed through the wall), `absorbed` (a
   larger urban polygon took it) or `superseded` (a large-model landslide took
   it). Flat-land walls do not appear; they have no polygon.

### 5.2 The contract flags

`loss` reads three flags per wall, `is_damaged_by_shaking`, `is_evacuated` and
`is_inundated` (`landloss.domain.loss_contract`), and any flag true means one
replacement, so which flag is set does not change the cost. It changes which
cause the report attributes the replacement to. The mapping, proposed:

| Outcome | Flag set |
| --- | --- |
| `failed_with_polygon` | `is_damaged_by_shaking` |
| `absorbed` or `superseded`, or the line inside any evacuated polygon | `is_evacuated` |
| the line inside any inundated polygon | `is_inundated` |
| flat-land wall written off by step 9 | `is_damaged_by_shaking` |

`vul/landslide/rw` step 11 applies it, reading the outcome table and the
combined realisation, and carries `slope_id` on every row.

## 6. Anchoring the rate setting

There is no earthquake inventory of urban Wellington failures. The largest
rock-site motion recorded in central Wellington since 2000 is 0.15 g, and 1855
predates the cuts and fills (`sr2019-038-F13`, `sr2019-040-F29`). The anchors
are qualitative and from analogues, and the judgement in using them goes in the
report as a table.

1. **Kingsbury (1995), Tables 1 and 7.** Five susceptibility zones against
   three scenarios, each scenario with a PGA on rock, each cell a failure class
   with described sizes and extent.

   | Scenario | Intensity | PGA on rock |
   | --- | --- | --- |
   | 1 | MM V to VI | 0.02 to 0.06 g |
   | Intermediate | MM VII to VIII | 0.1 to 0.2 g |
   | 2 | MM IX to X | 0.5 to 0.8 g |

   Reading each class as a fraction of polygons failing gives three points on
   the demand axis per zone, enough to fit a median and a dispersion for the
   medium curve per zone, and so per rating. The class-word-to-fraction table is
   the judgement, written down as `src/landloss/io/assets/urban-fragility-anchors.csv`
   with a column saying who set each number and why. The study's demand (PGA
   about 1 g; PGV 0.96 to 2.11 m/s over the four territorial authorities at
   2,500 years) sits above scenario 2, so the top row is the closest point and
   the curves extrapolate a little beyond it.
2. **The MM thresholds.** Landsliding from MM6 nationally, MM7 in the Wellington
   Region [hancox_1997]; slides in roadside cuttings and unsupported
   excavations are MM8 effects and general landsliding on steep slopes MM9
   (`qmap10-2000-F21`, `sr2010-012-F07`); MM6 or more causes small to large
   failures on steep unsupported cuts over 3 m (`sr2015-016-F05`). These fix the
   lower tail: near nothing below about 0.1 g on rock, cuts before natural
   slopes.
3. **Wellington's own low-demand record.** 2013 Cook Strait: one small rock
   fall on an old quarry face on the south coast and small falls on a harbour
   fill (`sr2013-042-F03`, `F04`, `F11`); 2016 Kaikōura at 0.15 g on rock in
   central Wellington with no urban cut or wall failures recorded
   (`sr2019-038-F13`). The curves must give almost nothing there.
4. **Port Hills 2011, the high-demand anchor.** At 1 to 2 g, cut slopes and
   some fill slopes failed in many cases (`sr2019-038-F14`, `sr2019-040-F31`),
   most failures under 100 m³ (`sr2015-016-F18`), with crest cracking damaging
   houses (`sr2015-016-F20`). Sources to obtain: [dellow_2011] for the
   landslide account, [massey_2014] for rockfall against PGA, and the
   unfiltered Canterbury land claims with hill properties if NHC's set arrives
   (**T-17**, **T-18**). What is wanted is the fraction of cuts, fills and walls
   that failed, which is the top of the medium curve.
5. **The forecasts for Wellington cuts.** At MM9 to 10, large failures on
   unsupported high cuts steeper than 45 to 50 degrees and widespread
   landsliding on the many 5 to 20 m cuts steeper than 50 to 60 degrees
   (`sr2013-058-F17`); all SH58 cuts steeper than 45 degrees expected to have
   10 to 1,000 m³ failures at MM VIII to IX (`sr1995-005-F08`); batters at 45
   to 50 degrees reasonably resistant (`sr1995-005-F11`). These order the
   medians by cut angle and height.
6. **Fills.** No Wellington fill has felt more than MM7; at MM8 to 10 many earth
   fills could crack and slump (`sr2013-058-F29`). Urban fill failures in New
   Zealand often come later, as water enters cracks the shaking opened
   (`sr2019-051-F07`, citing [brown_larkin_2005]), and the as-built Priscilla and
   Orchy fills move centimetres drained but over two metres saturated under the
   2,500-year record (`sr2019-051-F20`). So the fill curves carry the groundwater
   factor, and delayed failure is a stated limitation: a fill that fails in the
   weeks after the earthquake is counted as an earthquake failure where it would
   be claimed as one, which the EQC definition allows (`sr2018-027-F01`).

The low and high settings then sit at the spread between anchors 1, 4 and 5
read generously and conservatively.

## 7. The fixed geometry rules

Each polygon's evacuated, inundated and imminent-risk polygons are computed once
by `gen_urban_slope_polygons.py` for each wall state it can be in. The rules
below are the starting points; each is to be researched and justified in the
report, as phase 2 work.

| Element | No wall (cut or natural) | Fill wall failed | Cut wall failed |
| --- | --- | --- | --- |
| Evacuated | The face, plus a headscarp band above the crest: half a metre, or a metre on slopes over 30 degrees (**T-44**) | The wedge behind the wall: a multiple of the retained height back into the platform, at least the active wedge of about half the height, up to one or two heights for loose fill with a sloping backfill | The face above the wall plus the headscarp band |
| Depth | 1 to 2 m, the colluvium thickness Kingsbury gives; deeper on fill bodies, from the fill thickness in the ground map | The retained height at the wall, tapering to zero at the back of the wedge | As no wall |
| Inundated | Runout from the toe at the dry debris avalanche reach angle | Runout at the fill flow slide reach angle, about twice as far | As no wall |
| Imminent | A second band behind the headscarp (**T-45**) | The platform behind the wedge, cracked but standing | As no wall |

Runout comes from [de_vilder_2022], which fits reach angle H/L against volume by
failure style, with H and L measured from the crest to the toe of the deposit:
dry earthquake debris avalanches below 100,000 m³ have a median H/L of about
0.9 at 100 m³ and 0.8 at 10,000 m³, so the deposit toe lies 1.1 to 1.3 H from
the crest (`sr2019-038-F03`, `F04`); fill flow slides from Hong Kong and
Wellington have a median H/L of about 0.38 at 1,000 m³, so fills run about
twice as far as dry failures (`sr2019-038-F20`, `F21`, `F23`); the scatter is
about 0.08 to 0.1 in log10 (`F05`, `F24`), fixed at the median for the fixed
geometry. The two Wellington fill flow slides, Priscilla Crescent 2013 and
Halifax Crescent 2017, plot at H/L about 0.27 (`F25`). In the urban case the
runout is clipped at the next building outline or road, because debris from a
cut behind a house stops at the house. The primary for fill and cut runout is
[hunter_fell_2003]; the rock spall shadow angle of about 28 degrees is
[evans_hungr_1993].

The fill wedge rests on the earth pressure argument [nzgs_mbie_2017] and the
Wellington fill evidence: the Priscilla fill failed on a steep section of the
fill and rock interface, leaving a scarp up to 15 m high, with the moving layer
5 to 8 m thick on a 25 m slope (`sr2019-051-F08`, `F22`, `F25`); the Orchy
failure surface runs through the weak colluvium at the fill base and then
behind the break in slope at the top of the fill (`F23`). Buried colluvium at
the fill base, weaker than the fill, is expected under numerous Wellington
fills (`sr2019-040-F04`).

The headscarp band rests on **T-44** and on tension cracks observed 150 to
200 mm wide behind cut failures (`sr1995-005-F19`, `F21`), retreat by further
small failures over months (`F18`), and crest cracking in the Port Hills
(`sr2015-016-F19`, `F20`). The claim report extraction, when it lands, records
imminent-risk areas and is the check.

Depth for larger polygons falls back on the volume to area relation in
`landloss.hazard.landslide.geometry` [massey_2020], from outside Wellington
(A-06).

## 8. Delineation of the candidates

### 8.1 Domain

Off the NLM flatland (`get_nlm_flatland`, the release pinned by
`FLATLAND_NLM_VERSION`, carried on the ground map) and within 100 m of a
building outline. No insured land mask.

### 8.2 Scales and segmentation

Segmentation is how a slope raster is turned into polygons. Two ways:

- **Banded connected components**, the baseline. Classify the slope at a scale
  into bands (for example 0 to 10, 10 to 20, 20 to 30, 30 to 45, 45 to 60 and
  over 60 degrees) and the aspect into eight octants. Cells in the same band and
  octant that touch form one patch. Patches below a minimum area are merged into
  the neighbour they share the longest edge with. The bands are not a cut-off:
  every band, the gentlest included, produces polygons, and the gentle ones
  carry high medians. The patch edges fall on the band boundaries, which are
  the crest and toe lines wanted. No new dependency.
- **Region growing**, the alternative. Grow patches from seeds by similarity of
  slope and aspect without fixed bands, as scikit-image's superpixel methods
  do. Smoother edges; a new dependency; patch edges no longer sit on a named
  slope boundary.

The baseline runs at 1, 3, 10 and 30 m, with 50 m as an option. Nesting across
scales is wanted and kept. Within a scale a patch longer than the contour
length is split along the contour; the length comes from the GNS wall segment
lengths now, and from failure widths in the rainfall inventory when supplied.

Crest and toe lines are the patch boundaries. The reconciliation to wall lines
happens afterwards in `gen_urban_slope_polygons.py`.

### 8.3 Features read onto each candidate

From the terrain derivatives: slope and aspect at its own scale and at the
others; face height in the 5 and 10 m windows; the cut and fill residual;
curvature; topographic position at two windows; vegetation height; position
relative to the building outline, uphill for cuts and downhill for fills and
walls; distance to road frontage and section edge. From the ground map: the
attributes in section 9. Toe trims, house platforms cut into the toe of old sea
cliffs, appear on 42 of 55 Wellington slope profiles (`sr2013-058-F19`); the
residual and the building-relative position are what find them. The DEM's
mixed survey vintage (**L-12**) and the 1 m grid's inability to resolve
sub-metre walls (**I-03**) are stated limitations.

## 9. The ground map

One polygon map, non-probabilistic, built once by `gen_ground_map.py` before
anything that reads geology, and read by the candidates, the wall lines, the
slope units, step 2's rating, the strength-based model 7 and the exposure.

Sources and precedence, finest first where they overlap: the SLIDE interpreted
materials (14 classes at nominally 1:500, over 38% of Wellington City); the
SLIDE genesis cut slopes, fill bodies, landfills and landslides, and the WCC
earthworks polygons, for modification and prior failure; the 1:50,000 geology
[begg_mazengarb_1996] for the rock and the Tertiary and Quaternary units; the
NLM geomorphology `l3_yp` as the regional fallback, and QMAP [begg_2000]
outside all of them; the NLM groundwater depth on flat land; the cut and fill
residual from the terrain for modification where no mapping reaches.

Attributes per polygon: `material` (greywacke rock by weathering grade where a
grade is known, otherwise rock; colluvium; loess; alluvium; engineered fill;
uncontrolled fill; reclamation); `modification` (cut, fill, natural, unknown);
`is_flatland`; `gw_depth_class`; `prior_failure` (relict, recent, none);
`fill_thickness_m` where the residual or a borehole gives it; the Kingsbury
geology value and the strength set (`c_kpa`, `phi_deg`, `unit_weight_kn_m3`)
that follow from the material by lookup in
`src/landloss/io/assets/wellington-greywacke-strength.csv`; and a `source` and a
`confidence` per attribute.

Weathering grade is not mapped anywhere for Wellington. The option recorded in
`hazard/landslide/status.md`, depth to a weathering grade from New Zealand
Geotechnical Database boreholes interpolated into a surface, enters here when
taken up, as do the depth-to-rock observations already compiled in
`wellington-greywacke-depth-to-rock.csv` and the GNS fill and colluvium strengths
(`sr2019-040-F01` to `F05`, `sr2019-051-F14`, `F15`).

## 10. Slope units and the large and small split

### 10.1 Delineation

On the 10 m DEM from step 3: D8 flow direction and accumulation; a channel
network at a threshold, with 1, 5 and 20 ha tried; sub-basins per channel link;
each sub-basin split along its channel into a left and a right half-basin;
neighbours of similar aspect merged, and anything over about 50 ha split by
aspect variance. This is the r.slopeunits logic [alvioli_2016] without GRASS.
It needs a flow routing library: **pysheds**, pure Python with numba, for
direction, accumulation and catchments, with the half-basin split written here.
A new dependency. The parameter sensitivity is reported.

### 10.2 Placement of large failures

Per unit, the expected failed area from the model raster becomes a count of
failures through the size distribution above the urban range. Each failure is
seeded at the highest-coverage cell within the unit, weighted toward the crest
by topographic position because earthquake sources favour crests, and grown
along the steepest-descent lines to its sampled area, elongated downslope at
the Kaikōura aspect ratio. A failure's size is drawn with no regard to the
unit; one larger than its unit grows into the adjacent units sharing its ridge
or face. The unit decides where a failure starts, not how large it can be.

### 10.3 The split, by population

The urban polygons are not bounded at 500 m²: a fill batter 15 m high and 50 m
long is 750 m² of face. The review's evidence on A-01 says the same from the
other side. SH58 cut failures invert to 11 to 530 m² of source, nine of ten
under 500 m² (`sr1995-005-F03`); recorded Wellington cut failures of 10² to
10⁴ m³ invert to about 140 to 3,300 m² and straddle the split
(`sr2013-058-F13`); the Brabhaharan et al. (1994) Low and Moderate classes, road
cuts and road-edge fills, run to 10⁴ m³ and so to 3,300 m² (`sr2010-012-F04`);
coseismic failures on highway cuts are 10³ to 10⁵ m³, mostly above the split,
but those are highway cuts, not residential (`sr2015-016-F06`); 74 to 84% of
landslides mapped after four New Zealand earthquakes were under 10³ m³, about
675 m² (`sr2015-016-F11`); and most Port Hills failures were under 100 m³, about
140 m² (`sr2015-016-F18`).

So the split is by population. The urban polygons carry whatever size their
geometry gives them, mostly under about 700 m² with a tail to a few thousand.
The share removed from the large models' coverage is the share of the
calibration inventory's area inside the urban size range, measured from the
Kaikōura source polygons (`landloss.io.kaikoura`), and the large-model size
distribution is drawn above that range. The sensitivity of the loss to the
boundary of the range is reported.

## 11. Phases

### Phase 0 — Prerequisites

- [ ] `EXPOSURE_BASE_SEED` in `landloss.domain.constants`, and a world id on
      `realisation_seed`.
- [ ] `hazard/shaking/steps/s5_pgv_realisation`.
- [ ] `doc/references.bib` (done) and the AGENTS.md note on citing by key.

### Phase 1 — Ground work

- [ ] Step 3 extended: 1 and 3 m scales, aspect, and `gen_terrain_derivatives.py`
      with `terrain.local_relief`, a residual function, curvature and vegetation
      height added to `landloss.common.utils.terrain`.
- [ ] Step 4, the ground map, with `landloss.hazard.landslide.ground_map`
      holding the precedence rules and the attribute lookups.
- [ ] Step 5, slope units, with `landloss.hazard.landslide.slope_units` on
      pysheds.
- [ ] Step 6, the slope candidates, with
      `landloss.hazard.landslide.urban.delineation`.
- [ ] `gen_wall_lines.py`, with `landloss.exposure.rw.lines`.
- [ ] Step 7, the failure polygons, with `landloss.hazard.landslide.urban.geometry`
      holding each geometry rule as a named function with its source in the
      docstring.
- [ ] Research and justify the geometry rules; record the sources in
      `context/lit/landslide/` and the bib.

### Phase 2 — The wall population

- [ ] `gen_wall_probability.py` reworked to lines, with the condition model.
- [ ] `gen_wall_population.py` reworked to draw per world on the exposure seed,
      carrying `wall_line_id`.
- [ ] Later: `gen_wall_count_bounds.py` and the constrained draw.

### Phase 3 — The urban model

- [ ] `landloss.hazard.landslide.urban.fragility`: the lognormal, the rating to
      median function, the amplification factor, the PGA to PGV conversion, the
      rate setting.
- [ ] `src/landloss/io/assets/retaining-wall-fragility.csv` and
      `urban-fragility-anchors.csv`, with readers.
- [ ] The anchoring validation figure and table.
- [ ] Step 8, the model file, and its review by the project lead before phase 4.

### Phase 4 — The draws and the vul changes

- [ ] Step 1 reworked onto slope units.
- [ ] Step 9, the urban realisation, with
      `landloss.hazard.landslide.urban.realisation`.
- [ ] Step 9 of `vul/shaking/rw` restricted to flat-land walls on PGV; step 11
      of `vul/landslide/rw` on the outcome table; the land, crossing and
      property damage steps on the new file names and ids.
- [ ] Checks: the share of urban failures confined to one property (A-15), and
      failed polygon sizes against the Wellington cut-failure record.

### Later

- [ ] Rainfall inventory, when supplied: failure widths, prior failure, the
      size check.
- [ ] NZGD boreholes into the ground map.
- [ ] Four or five exposure worlds.
- [ ] Sensitivity of the loss to the rate setting, the scales and the size
      range boundary, as a table.

## Files

**New library code** (`src/landloss/`): `exposure/rw/lines.py`,
`exposure/rw/population.py` (the per-world draw and the count bounds);
`hazard/landslide/ground_map.py`, `slope_units.py`; `hazard/landslide/urban/`
with `delineation.py`, `geometry.py`, `fragility.py`, `realisation.py`;
`hazard/realisation.py` gains the world id; `domain/constants.py` gains
`EXPOSURE_BASE_SEED`, `URBAN_BUILDING_DISTANCE_M`, `URBAN_SCALES_M`,
`MIN_WALL_HEIGHT_M`, `UNCONSENTED_WALL_HEIGHT_M`, `URBAN_RATE_FACTORS`,
`TOPOGRAPHIC_AMPLIFICATION_MAX`, `LOCALISED_FRAGILITY_BETA`; `io/assets/`
gains the two CSVs and their readers.

**Changed:** `exposure/rw/wall_probability.py` (lines), `vul/shaking/rw` step 9,
`vul/landslide/rw` step 11, `vul/landslide/land` step 3,
`vul/landslide/culverts_bridges` step 11 and `vul/steps/s10_property_damage`
(file names and ids).

**New step folders:** `hazard/landslide/steps/s4_ground_map/`, `s5_slope_units/`,
`s6_urban_slope_candidates/`, `s7_urban_slope_polygons/`,
`s8_urban_slope_fragility/`, `s9_urban_slope_realisation/`;
`hazard/shaking/steps/s5_pgv_realisation/`; `hazard/landslide/validations/urban/`.

**Tests** under `tests/landloss/` mirroring the library: the lognormal and its
conversion on known values; segmentation on a synthetic terrace-and-face DEM;
snapping on a candidate straddling a line; nesting resolution on two concentric
polygons; supersession on an urban polygon inside a large one; the fill wedge
and runout rules on a planar slope; the ground map precedence on overlapping
sources; seeds keyed on both ids reproducing.

## Verification

- The model file reviewed by the project lead, as a map and as a table of
  medians by rating and wall state.
- The curves against the anchors in section 6, in the validation figure.
- Over the pilot: the realised share of polygons failing against the fragility
  they were drawn from, per rate setting.
- The share of urban failures confined to one property (A-15) and the failed
  polygon sizes against the Wellington cut-failure record.
- Every run prints the rate setting, the world and earthquake ids, the counts
  of polygons by wall state, failed, absorbed and superseded, and the summed and
  dissolved areas by kind of ground.
- `uv run --frozen pytest` and `uv run --frozen prek -a`.

## Open decisions

- **The six wall classes**, still unnamed, which the fragility table is indexed
  on.
- **The contract flag mapping** in section 5.2, which attributes a replacement
  to a cause and does not change its cost.
- **The urban size range** that bounds the large models' size distribution and
  sets the share removed from their coverage (section 10.3).
- **Register housekeeping**: **T-19** and **T-10** to Dropped, **T-31** moot,
  and the wording of **L-04**, in the workbook.
- **The geometry rules** in section 7, once researched.

## Risks

1. **No local earthquake inventory of urban failures.** The rate setting is a
   bracket, not a calibration, and the loss scales with it. The sensitivity
   table and the anchoring table are how the report carries that.
2. **Walls under the canopy.** The GNS mapping sees only walls visible from
   above and the 1 m grid cannot resolve sub-metre faces, so candidate lines in
   bush-covered suburbs rest on the terrace-and-face signature and the section
   geometry. The claim extraction, when it lands, is the correction.
3. **Delayed fill failure.** Fills that crack in the shaking and fail in the
   weeks after are counted as earthquake failures where the policy would count
   them; the model cannot separate the two.
4. **Nested polygons and calibration.** The net rate on ground is what the
   anchors describe; the per-row medians must be set with the nesting depth in
   mind or the net rate doubles where polygons stack.
5. **Scale of the shaking grids.** PGV changes only where the site class does
   within a 9,930 m demand cell, so the spatial variation in failure comes from
   the polygons' attributes and amplification, not from the demand field.
6. **The ground map's precedence.** Where fine and coarse sources disagree the
   finer wins by rule, and the rule is a judgement recorded per attribute.

## Sources

Citation keys are in `doc/references.bib`. The GNS report review is in
`temp/gns_review/`, with `out/reports.csv` holding each report's citation and
DOI and `out/findings.csv` the findings cited above by id. Documents the plan
recommends obtaining, with full citations:

- Dellow, S., Yetton, M., Massey, C., Archibald, G., Barrell, D. J. A., Bell,
  D., Bruce, Z., Campbell, A., Davies, T., De Pascale, G., Easton, M., Forsyth,
  P. J., Gibbons, C., Glassey, P., Grant, H., Green, R., Hancox, G., Jongens,
  R., Kingsbury, P., Kupec, J., Macfarlane, D., McDowell, B., McKelvey, B.,
  McCahon, I., McPherson, I., Molloy, J., Muirson, J., O'Halloran, M., Perrin,
  N., Price, C., Read, S., Traylen, N., Van Dissen, R., Villeneuve, M. & Walsh,
  I. (2011). Landslides caused by the 22 February 2011 Christchurch earthquake
  and management of landslide risk in the immediate aftermath. *Bulletin of
  the New Zealand Society for Earthquake Engineering*, 44(4), 227–238.
  Citation to verify against the journal before use.
- Hunter, G. & Fell, R. (2003). Travel distance angle for "rapid" landslides in
  constructed and natural soil slopes. *Canadian Geotechnical Journal*, 40(6),
  1123–1141. https://doi.org/10.1139/t03-061. Named by de Vilder et al. (2022)
  as the primary for fill and cut runout.
- Evans, S. G. & Hungr, O. (1993). The assessment of rockfall hazard at the
  base of talus slopes. *Canadian Geotechnical Journal*, 30(4), 620–636.
  https://doi.org/10.1139/t93-054.
- Brown, P. & Larkin, T. (2005). The performance of hillside earth fills under
  earthquake loading. *Proceedings of the New Zealand Society for Earthquake
  Engineering Conference 2005*, Wairakei. Cited by Monteith (2020) for delayed
  fill failure; the paper number is not given there.
- Grant-Taylor, T. L. (1964). Stable angles in Wellington greywacke. *New
  Zealand Engineering*, 19(4), 129–130. The angle-height envelope for
  Wellington greywacke cuts, read by Hancox et al. (2013) as their Figure 17.
- New Zealand Geotechnical Society & Ministry of Business, Innovation and
  Employment (2017). *Earthquake geotechnical engineering practice. Module 6:
  Earthquake resistant retaining wall design*. Wellington: MBIE and NZGS. The
  earth pressure and wall-design reference for the fill wedge.
- Van Dissen, R., Abbott, E., Zinke, R., Ninis, D., Dolan, J., Little, T.,
  Rhodes, E., Litchfield, N., Hatem, A., Van Dissen, A. & Hogan, P. (2013).
  Landslides and liquefaction generated by the Cook Strait and Lake Grassmere
  earthquakes: a reconnaissance report. *Bulletin of the New Zealand Society
  for Earthquake Engineering*, 46(4), 196–200. Held at
  `U:\MAMI\Literature\new_lit\` and not yet extracted; the author list is to
  be checked against the journal.

Written 2026-10-01, revised the same day. Decisions as recorded in the table;
the rest is proposed and not yet reviewed with the project team.
