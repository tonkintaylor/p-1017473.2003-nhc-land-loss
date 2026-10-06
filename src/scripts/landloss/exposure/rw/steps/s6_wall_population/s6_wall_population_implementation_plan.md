# Step 6 — Retaining wall population: implementation plan

**Status:** Phase 2 complete in shape, and phase 2e built: the candidates are
the wall units of landslide step 12, with their probability, claim update and
draw per world, read into the probability table and the population (ran over
the pilot on 2026-10-05). The numbers are judgement until the claim report
extraction (**T-50**) lands; phase 2d reads it. Phase 3, a wall type per wall
from its age, height and road frontage in place of the modern and poor
condition, is built (2026-10-06) and not yet run on real data. Phases 1, 1b
and 1c, the per-property interim model, are superseded and their code is
deleted.

## Phase 1 — A population of the right shape (superseded)

Drew at most one wall per insured property against a slope-driven prevalence,
sized it from the slope, placed it as a line along the contour at the
property's own point, and seeded it on the hazard realisation. Every piece is
replaced by phase 2: the lines come from geometry, the height from the DEM,
the draw from a world seed. The size classes it defined (`classify_wall_size`,
`describe_population`, `landloss.exposure.rw.beta_population`) are the one
part kept; its initial conditions were retired for the wall type (phase 3).

## Phase 1b — Coverage filter and wall id for the loss contract (complete)

- [x] Keep only the walls that intersect their own claim's insured land
      buffered by 2 m (`keep_walls_on_insured_land`), and print the counts kept
      and dropped (`describe_coverage`).
- [x] Give each kept wall a stable `rw_id`, minted after the filter on walls
      sorted by location (`sort_by_location`, `mint_asset_ids`).
- [ ] Rerun over the pilot box and record the kept and dropped counts in the
      method file.

## Phase 1c — Interim: a probability per property (superseded)

Put `p_wall`, a lognormal height and size class probabilities on each
property, from the slope lifted by the GNS earthworks share, capped on an NLM
plain and set to the mapped-wall floor where a wall was mapped on the
property. Dropped with phase 2b: a property-level probability cannot say where
a wall is or give a property more than one. The mapped-wall floor
(`BETA_MAPPED_WALL_PROBABILITY`) and the one-sided reading of the mapping
carry over to the line probability; the NLM landform cap becomes the ground
map's `is_flatland` cap.

## Phase 2 — Candidate wall lines with a probability on each line

**Identify where walls are, as lines, and give each line a probability.** Nothing
is decided per property. A wall is a located line, so the same line is what the
coverage filter, the landslide footprint intersection and the settlement read.
A property with two or three walls is simply a property with two or three
candidate lines that drew, each with its own height and condition.

### Phase 2a — The candidate lines (`gen_wall_lines.py`, complete)

Candidate lines come from geometry that marks where a wall could be
(`landloss.exposure.rw.lines`, contract sections 3.5 and 7.8):

- [x] The edges of the urban slope model's candidate failure polygons, as the
      terrain breaks: the downhill edge of a finest-scale candidate at or above
      45 degrees with a 5 m face of at least `MIN_WALL_HEIGHT_M`, against a
      neighbour below 20 degrees (`terrain_break_lines`). The crest edge is not
      a line; step 7 reconciles the polygons to the lines (decided 2026-10-01);
      see `hazard/landslide/status.md`.
- [x] The GNS SLIDE mapped retaining walls (`get_gns_slide_morphology`), as
      lines, snapped onto the nearest candidate edge within
      `SNAP_TOLERANCE_M` (`mapped_wall_lines`, `snap_to_candidate_edges`). They
      are the only observed walls, so they carry the highest precedence and
      `is_mapped_wall`. The mapping is one-sided (visible from above,
      Wellington City only), so it raises a line's probability and never
      lowers another's.
- [x] The edges of GNS SLIDE cut slopes and fill bodies (`get_slide_genesis`,
      `genesis_edge_lines`) and the cut/fill lines in the morphology layer
      (`slide_cut_fill_lines`), where a wall holds the toe or crest of the
      earthwork.
- [ ] Sharp breaks in slope from the GNS morphology (the concave and convex
      `Type` values), within and beside the insured land, for ground the SLIDE
      mapping does not reach. Steps in the DEM are covered by the terrain
      breaks above; the morphology breaks are not read.
- [x] Section boundaries and road-frontage edges on sloping ground
      (`boundary_lines`: the claim property boundaries noded and merged, road
      frontages within `config.ROAD_FRONTAGE_DISTANCE_M` of a road centreline,
      both kept only on a 10 m slope of at least `MIN_SLOPING_GROUND_DEG` and
      within `URBAN_BUILDING_DISTANCE_M` of a building), which is where
      Wellington walls are usually found: at the edge of the section, not the
      middle of it.
- [x] Keep a boundary or road frontage only where the 1 m DEM steps at least
      `MIN_WALL_HEIGHT_M` across it (`step_height_m`, the project lead,
      2026-10-02); its face height is that step.
- [x] Apply the same test to the SLIDE cut and fill edges and cut/fill lines,
      which mark earthworks rather than walls (2026-10-02).
- [x] Trim each tested line to its stepped stretches rather than keeping or
      dropping it whole on its median (`keep_stepped_parts`), bridging dips of
      up to `MAX_STEP_GAP_M` and keeping runs of at least `MIN_STEP_RUN_M`,
      both 3 m, chosen over the pilot from a sweep of 1 to 5 m (method file).
      Tested; measured over the pilot into a scratch folder, not yet rerun
      into `temp/` or through the chain.
- [ ] Check the step test against the NZMM retaining wall flag per address
      (`landloss.io.nzmm_land_attributes`) and the GNS mapped walls: the share
      of flagged addresses with a stepped candidate, and of mapped walls with
      a step under them.
- [ ] Driveway edges. Step 5 does not write the driveway corridors separately,
      so they are not a source in this build (decided 2026-10-01).
- [ ] Cut-and-fill model and road batter geometry from the councils
      (**T-11**, **T-20**) once obtained.
- [x] Segment and de-duplicate the candidates so one wall is one line, and record
      which source each line came from (`collapse_coincident` keeps the
      highest-precedence line among coincident ones; `split_at_boundaries` cuts
      every line at the claim property boundaries; `source` is recorded).
- [x] Read the face height along each line from the 5 m local relief
      (`face_height_m`), class it (`classify_wall_size`), mark fill or cut
      from the residual uphill (`wall_position`), read the ground map at the
      midpoint, and assign the claim by the midpoint with the uphill/downhill
      rule on boundary lines (`assign_claim`). Faces under
      `MIN_WALL_HEIGHT_M` are dropped unless a wall is mapped there.
- [x] Mint `wall_line_id` by location (`mint_wall_line_ids`) and draw the lines
      by source (`fig_wall_lines.py`).
- [ ] Run over the pilot box and record the counts by source in the method
      file; then over the four territorial authorities. The collapse and the
      split are per-line loops over an STRtree, which is fine for the pilot
      and untested at the full extent.
- [ ] The snap moves each vertex of a mapped wall independently, so a wall
      whose ends alone are within tolerance of a candidate edge is bent rather
      than moved whole. Replace with a whole-line snap when step 7's
      reconciliation shows it matters.

### Phase 2b — A probability per line (`gen_wall_probability.py`, complete)

Each line takes a probability from what the lines step read onto it
(`landloss.exposure.rw.wall_probability`, contract sections 3.7 and 7.9):

- [x] A prior by source (`BETA_SOURCE_PROBABILITY`), highest for a GNS mapped
      wall and lowest for a property boundary, lifted to at least
      `BETA_MAPPED_WALL_PROBABILITY` where a wall is mapped along the line
      (`line_wall_probability`), with the rule that set it recorded in
      `p_wall_basis`.
- [x] Lowered on a rock cut (`BETA_ROCK_CUT_FACTOR` where `is_rock_cut`, from
      the ground map's material and modification): a rock cut stands
      unsupported and is claimed for spalling or slides, not wall failure
      (Oriental Bay and Evans Bay are the worked examples). The ground map
      reads the GNS 1:50,000 geology and the SLIDE interpreted materials
      where they reach, so colluvium, fan and fill are already told apart
      from rock on the line.
- [x] Capped on the NLM flat land (`BETA_FLATLAND_MAX_PROBABILITY` where
      `is_flatland`).
- Retired 2026-10-06: the probability of poor condition per line
  (`poor_condition_probability`, `p_poor`, `p_poor_basis` and their `BETA_`
  shares). The wall type (phase 3) carries what it did, and keeping both
  would count age twice.
- Dropped: the count bounds hook, a scaling of the probabilities inside each
  claim between a minimum and maximum count. Its maximum lowered
  probabilities and its scaling ignored the priors' shape; it was removed on
  2026-10-05 for the per-property claim update on the wall units (phase 2e).
- [x] Read the retained height at each line from the 1 m DEM, as the face
      height across it, and class it small, medium or large on the agreed
      boundaries; no height distribution is drawn (decided 2026-10-01). Done
      on the lines in phase 2a (`face_height_m`); the draw carries it as
      `height_m`.
- [ ] Let the slope across the line and on the land it would hold up move the
      prior: a boundary on a 30 degree hillside is more likely retained than
      one on 6 degrees. Not in `p_wall` yet; the boundary sources are only
      kept above `MIN_SLOPING_GROUND_DEG`.
- [ ] Let the wall position move the prior: a fill edge below a platform is
      more often retained than a cut toe the owner may have left as a batter.
- [ ] Soil over rock at the line (the ground map's `material` beyond the rock
      cut rule) raising the prior, because walls there stabilise soil rather
      than rock. The cover over Wellington greywacke is usually under 1 m and
      0.5 to 3 m on typical slopes [nzgs_2025_torlesse;
      hancox_2013_slope_types], so a cut shorter than the cover is a soil cut;
      phase 2e makes this the face height test on the rock factor.
- [ ] Mark lines on new subdivisions as very likely to have walls, from the
      subdivision or dwelling age once held.
- [x] Wall type (gravity masonry, crib, timber pole, block and RC,
      landscaper timber, engineered): drawn per wall per world (phase 3).
- [ ] Give a property several lines of independent height and construction. A
      property with several walls is not all small or all large. Partly there:
      each line carries its own face height; the type draw is independent
      per line rather than shared across a property.

### Phase 2c — A draw per exposure world (`gen_wall_population.py`, complete)

- [x] Draw each line independently in the world (`draw_wall_population`):
      two uniforms per line in line order, the first for existence against
      `p_wall`, so a line's draw does not depend on lines after it. The
      second drew the retired condition and is still drawn, so the existence
      stream is unchanged; the type is drawn on its own stream (phase 3).
- [x] Key the draw on `EXPOSURE_BASE_SEED` and the world id of its own,
      separate from the hazard seed and realisation id, so a few wall
      populations pair with many hazard realisations (decided 2026-10-01).
      `config.WORLD_IDS` replaces `REALISATION_IDS`; the file is
      `wall-population-wNNN[-pilot].geoparquet`.
- [x] Write the drawn lines in the shape the contract reads: `rw_id`,
      `claim_id`, `wall_line_id`, `world_id`, size class, wall type, age bin,
      height,
      length, position, flat land, source, material and the line geometry.
      Claimless lines are dropped (**I-05**), the coverage filter is kept and
      `rw_id` minted after both.
- [x] Write every wall the world drew, before the claim and coverage
      filters, to `drawn-walls-wNNN[-pilot].geoparquet`
      (`drawn_walls_path`), with the minted `rw_id` joined back on
      `wall_line_id` and null for a wall the filters dropped
      (`attach_rw_ids`), so landslide step 8 models the slope with uninsured
      walls in place (decision 36 of the build contract).
- [x] Run the scripts from `gen_exposure.py` after the insured land step,
      over `exposure/config.py`'s `WORLD_IDS`; `gen_wall_age.py` runs before
      the population.
- [ ] Run over the pilot box and record the lines drawn, the claim and
      coverage counts, the drawn walls without an `rw_id` and the population
      by size class and wall type in the method file; then over the four
      territorial authorities.
- [x] Re-point the vul rw steps 9 and 11 at the world-keyed population: both
      `gen_wall_damage_state.py` and `gen_wall_landslide_damage.py` now read
      `wall_population_path(world_id, extent=...)` with `(w, r)` naming
      (phase 4 of the build, contract sections 3.11 and 3.12).

### Phase 2d — Calibration against the claim report extraction (**T-50**)

The extraction is the only calibration source the study will have and arrives
after the build starts: the SME suburb estimate, the manual mapping study, the
remote sensing pilot and the ICNZ database will not be obtained (decided
2026-10-01).

- [ ] Extract the per-claim wall count that landslide step 12's
      `gen_property_wall_records` reads: the `claim_walls` column of the claim
      and NZMM layer (`validations/config.PROPERTIES_PATH`, written by
      `gen_rw_dataset_properties.py`). The minimum and maximum bounds file
      (`gen_wall_count_bounds.py`) is dropped: nothing reads bounds since the
      wall unit claim update replaced `apply_count_bounds` (2026-10-05).
- Dropped: reading the bounds in `gen_wall_probability.py`. The claim report
  counts update the wall units in landslide step 12 instead (phase 2e).
- [ ] Replace the `BETA_` source priors, the rock cut factor and the flat land
      cap with values fitted so the expected counts match the extraction by
      suburb, and drop the `BETA_` prefixes.
- [ ] Measure the fraction of real walls the GNS mapping captures, from the
      claims with walls at addresses inside the SLIDE footprint, replacing the
      fixed `BETA_MAPPED_WALL_PROBABILITY`.
- [ ] Fit the wall length distribution along the contour to the GNS mapped wall
      segments now, and check it against the extraction later.
- [ ] Height, and so size class, stays a judgement until a source for it
      exists; the set heights the loss module prices at (0.75, 1.75, 2.75 m)
      are to be re-confirmed against the 0.5–1.0, 1.0–2.5 and 2.5+ m ranges
      the DEM face height gives (**I-14**). Anderson et al.'s 2,991
      Christchurch walls are the nearest published height distribution: 54%
      under 1.5 m, 26% 1.5 to 2.5 m, 11% 2.5 to 3.5 m, 9% over 3.5 m
      [anderson_2015] (`anderson2015-F05`), weighted to road walls and to
      walls over 1.5 m, so a shape check rather than a target. The 2.5 m break
      matches theirs; the 1 m break cannot be tested against it.

### Phase 2e — Rebuild on the faces (literature review, 2026-10-02)

The candidates are rebuilt from the pifs of landslide step 12 (the face-based
build, `.agents/plans/building-pip-pif-siz-slope-polygons.md`). Built there
2026-10-05: each pif is tied to its LINZ property, and each stretch of GNS
mapped wall with no pip near it is a `gns_only` line candidate. The full plan is
`.agents/plans/placing-retaining-walls-on-pifs.md`. The order from
here, per property:

- [x] Wall units: adjacent candidate pifs and GNS-only pieces on one property
      joined into walls, with a rule for pifs that straddle two properties
      (landslide step 12, `gen_urban_slope_wall_units.py`).
- [x] A prior from the height band, a rock cut and fill on the ground map.
- [ ] The landslide step 13 cut and fill class in the prior and as each
      wall's `wall_position` (today fill where the unit is on fill, else cut).
- [x] The GNS floor: 0.95 on a wall unit with a mapped wall on it, 0.8 on a
      `gns_only` candidate.
- [x] Raise from the property databases through the Poisson-binomial update
      described in the status: NZMM flag to an expected minimum of 2 walls,
      claim reports to a per-property count (30% held out). No five-round
      allocation, as the update is exact and has no order effect.
- [x] `gen_wall_probability.py` reads the wall units in place of the lines,
      and ties each to its claim; `gen_wall_population.py` takes which units
      are walls from step 12's draw for the world and draws each wall's type
      (phase 3).
- [~] Cross-validation on the held-out claims, GNS and the strata: the
      tables are written by landslide step 12
      (`table_urban_slope_wall_checks.py`); no calibration until **T-50**.
- [ ] Walls on the flat land: every unit is a face of sloping ground, so
      `is_flatland` is False throughout.
- [ ] Landslide step 8's edge join reads `wall_line_id` against the step 7
      line ids; the drawn walls now carry wall unit ids, so it matches none
      until steps 8 and 9 read step 12's zones (step 12 plan, phase 5).
- [ ] Remove `gen_wall_lines.py`, `fig_wall_lines.py` and the line
      probability once nothing reads them (landslide step 7 and the chain test
      do today).

The earlier text of this phase, from the free-face faces layer, follows.
(`.agents/plans/building-face-based-urban-slope-polygons.md`, phases 1 and 2),
which replaces phase 2a's line sources with evidence on one face. What the
review of `temp/gns_review/` adds:

- [ ] **A candidate is a face steeper than its ground stands unsupported**,
      read from one lookup of eight fixed height bands by three ground groups,
      NZGS Unit 7C.2 Figure 35 for rock and 35° for soil and fill
      [nzgs_2025_torlesse], not every face over `MIN_WALL_HEIGHT_M` (faces
      plan, phase 1). The wall carries the band; the size class is a union of
      bands.
- [ ] **The rock-cut factor needs rock on the ground map.** With SLIDE's mixed
      fill classes mapped to fill, 71% of the pilot is fill and `is_rock_cut`
      is rarely true, so the factor that carries Nick Peters's advice does
      little. The step 4 remap is the prerequisite (step 4 plan, phase 2;
      accepted by the lead 2026-10-02).
- [ ] **The rock-cut factor applies to a cut taller than the cover**, height
      band 4 and up (over 2.5 m), because greywacke cuts commonly
      stand unsupported at 55 to 75° [nzgs_2025_torlesse]
      (`nzgs2025-u7c2-F25`) while the soil cover above them does not; not to
      crushed rock near the Wellington Fault [grant_taylor_1964;
      nzgs_2025_torlesse].
- [ ] **A cut-and-fill platform has two walls**, a cut at its back and a fill
      at its front, with houses straddling the contact [monteith_2020]
      (`sr2019-051-F09`): two faces, two candidates, consistent with Nick
      Peters's two to four walls per property.
- [ ] **No faces off LiDAR.** Where step 3's source mask says the contour
      model, report the claims with no candidate for that reason rather than
      as claims with no wall [de_vilder_2024; nzgs_2025_recognition].
- [ ] **Age into wall type and the fill class**, from step 8: suburb earthworks
      followed the 1950s machinery [lyndsell_2019], earthfill standards came in
      the mid-1970s [monteith_2020], pre-1960 cuts and non-engineered fills are
      a warning sign [nzgs_2025_recognition]. Anderson et al. tie wall type to
      era in Christchurch, stone masonry the oldest and worst performing, crib,
      gabion, block and timber pole more modern [anderson_2015]
      (`anderson2015-F07`, `F11`), the evidence for reading age as type.
      Age into type is built (phase 3); age into the fill class is not.
- [ ] Keep every weight `BETA_`: the literature gives the direction of each
      piece of evidence, not its size, and no published source gives wall
      prevalence in Wellington (`sr2019-040-F32`, `sr2019-051-F33`: walls are
      "a typical Wellington construction method", no counts). **T-50** stays
      the only calibration.

## Phase 3 — Wall type from age, height and road frontage (built 2026-10-06)

The plan is `.agents/plans/assigning-retaining-wall-types.md`.

- [x] The age shares of each property (`gen_wall_age.py`,
      `landloss.exposure.rw.wall_age`): the QV rating roll's dwelling decade,
      exposure step 8's own title or plan date where the dwelling age is
      missing or the lot is `BETA_LOT_OLDER_GAP_YEARS` older, then the suburb
      and the extent shares.
- [x] The type fractions by age bin and height band and the road frontage
      multipliers, packaged as `beta-` CSVs in `landloss/io/assets`
      (`landloss.exposure.rw.wall_type`).
- [x] Draw each candidate's age bin, the rebuild shift
      (`BETA_WALL_REBUILT_SHARE`) and its type per world on the
      `WALL_TYPE_STREAM` stream (`draw_wall_types`), over every candidate so
      it does not change with the existence draw, and write `wall_type` and
      `age_bin` on the population and the drawn walls in place of
      `initial_condition`.
- [x] Retire `p_poor`, `p_poor_basis`, `poor_condition_probability`,
      `INITIAL_CONDITIONS` and the `BETA_` poor shares.
- [ ] Run `gen_wall_age.py` (it reads the QV roll from T:) and the population
      over the pilot, and record the type mix per age bin here and in the
      method file.
- [ ] Nick Peters reviews the type fractions; compare the drawn mix per age
      bin with the claim reports (**T-50**).

## Phase 4 — Costing reads the line

- [x] Take a wall's length from the line. A drawn wall is its line, so
      `length_m` is the line's length and no longer comes from the area of the
      section.
- [ ] Confirm with the loss team that size class affects costing while initial
      type only affects the probability of failure, and that the pricing
      heights stand against the new size ranges (**I-14**).

## Potential future improvements

- Read the type from evidence where a wall's type is known (a claim report or
  a site visit) rather than drawing it.
- Use houses across gullies, which likely sit on thicker colluvium or fill with
  wetter soils, as a predictor. Not obviously usable, so it is not in phase 2.
- Exclude non-residential properties such as the zoo near Yabby Creek Road with a
  land-use layer rather than by hand, so they draw no lines.
- Share one type draw across the lines of a property per height band, where
  the walls were built together; each line draws its own type today.
