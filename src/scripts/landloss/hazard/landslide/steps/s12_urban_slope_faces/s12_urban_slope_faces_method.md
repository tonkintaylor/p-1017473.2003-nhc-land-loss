# Step 12 — Urban slope faces: method

- The DEM comes from step 3 (`dem_path`) and the ground map from step 4
  (`ground_map_path`), both for the extent in `config.py`. `get_dem()` in
  `gen_urban_slope_faces.py` sets every cell outside the LINZ NZ Coastlines and
  Islands Polygons to no data (step 13 reads the DEM through it too), and
  `get_inputs()` adds the ground map, rasterised to ground groups with fill
  read as soil.
- `landloss.hazard.landslide.instability_zones.find_instability_zones` finds the
  pips, pifs and sizs, cuts every pif into pieces by the wall rules, grows the pieces of the sizs into elements with the watershed growth,
  and carries each element's siz and its angles. The rules and thresholds are
  in `.agents/plans/building-pip-pif-siz-slope-polygons.md` and the two CSV
  files `landslide-slope-thresholds.csv` and `landslide-seed-thresholds.csv`
  in `landloss/io/assets/` that the library reads.
- **The pifs are the pieces** (the lead, 2026-10-06). The siz test is made
  on the whole pif, then `split_pifs` cuts it along its spine by the rule
  the walls are cut by, one implementation for both
  (`landloss.hazard.landslide.bend_split.cut_path`): a new piece wherever
  following the spine within `WALL_STRAY_TOLERANCE_M` (2 m) would need more
  than `WALL_MAX_BENDS` (3) bends or bends turning more than
  `MAX_TOTAL_TURN_DEG` (185°) in all, no piece shorter than
  `WALL_MIN_SEGMENT_M` (3 m) along it (a shorter one joins a neighbour),
  and none longer than `MAX_PIF_SPAN_M`, 50 m (20 m until this decision; a
  cap since 2026-10-04, when whole hillsides grew as one element). A piece
  whose line is over 50 m is cut first at its line's own bends (the fewest
  cuts that bring every part under 50 m, the most even of those) and what
  is still over 50 m into equal parts; pifs take no boundary stage
  (`bend_split.cap_ranges`, the lead, 2026-10-06). The
  spine is the pif's longest shortest path; a branch sticking out from it
  by more than twice the pif's mean thickness (and 3 m) is a path of its
  own, so a spur or the leg of a T is cut too, while the width of a thick
  face is not a branch; each pip goes to the piece whose stretch of path is
  nearest. Property boundaries play no part (the 50 m boundary cut is the
  walls' alone). A piece's ends are at least 3 m apart (a shorter piece
  joins a neighbour; one folded into a horseshoe is cut where it turns), and
  its line, the siz table's `spine`, is the stretch of path it was cut on
  (`bend_split.canonical_line`), not a path found again through its pips:
  so every piece is 3 to 50 m long with at most 3 bends turning at most
  185° by construction,
  and `find_instability_zones` refuses any that is not
  (`bend_split.rule_breaks`). Before any of this a pif whose spine is under
  `BETA_MIN_PIF_LENGTH_M` (3 m) is dropped, as one of under three pips is
  (`drop_short_pifs`, the lead, 2026-10-06). Each piece is a pif of its own: its own
  `pif_id`, pips, spine and end falls, wall evidence, property and step 13
  class (step 13 runs on the siz table, so on the pieces), with
  `parent_pif_id` and the whole pif's `threshold_angle_deg`,
  `near_step_pass`, `far_angle_pass` and `is_siz` (`piece_table`); its
  heights and pair angles are its own. Each siz piece grows one element, so
  an element's `siz_id` is a siz table row, and a long face can be shared
  between walls.
- A pif holds at least `BETA_MIN_PIF_PIPS` (3) pips (the lead, 2026-10-06,
  matching the 3 m shortest element): `cluster_pifs` leaves a smaller cluster
  at 0 and numbers the pifs it keeps from 1 with no gaps, so such pips are in
  no pif, no siz and no wall candidate, and the siz table (`gen_siz_table`)
  and step 13 see only the kept pifs.
- Pifs most of whose pips lie in a LINZ building outline are dropped before
  the siz test (the lead, 2026-10-06), so a roof's edge or a building's wall
  is never a pif, siz, element or wall candidate. `gen_urban_slope_faces.py`
  reads the outlines (`get_nz_building_outlines`, the layer `building_m` is
  measured on) before the pipeline, rasterises them onto the DEM by cell
  centre (`building_mask()`) and passes the grid as `exclude` to
  `find_instability_zones`, which drops a pif with more than half its pips on
  it (`instability_zones.exclude_pifs`) right after `cluster_pifs` and
  renumbers the rest; the library stays on rasters. The count is printed.
- Every siz is a wall candidate and a wall must have a polygon (the lead,
  2026-10-06), so every region a siz pif piece grows is kept as an element
  (`_assemble_elements(..., keep_all=True)`), even where the keep rule of
  `find_slope_elements` (at least 0.5 m high and 3 m long, no gentler than the
  18.4° grow angle, crossed by a transect) would drop it. `kept_by_rule`
  records which passed. A short or gentle element is measured as it is; one
  under 0.5 m high is raised to 0.5 m (a siz's pips each drop more than 0.7 m,
  so a lower reading is a transect artefact), and one no transect crosses
  takes a run of 0 (a step the DEM cannot resolve, as a one-interval
  transect is read) and its elevation range as height
  (`slope_elements._measure_regardless`), so its width, depth and volume can
  be built.
- The width behind every polygon's crest, walled or not, is at least
  `BETA_MIN_EVACUATED_WIDTH_H` (0.5) of the element's height and never under
  `BETA_MIN_EVACUATED_WIDTH_M` (1 m), along its whole crest
  (`slope_polygons.min_evacuated_width_m`, the lead, 2026-10-06). It is applied
  to every polygon, not only walled ones: a bank on a siz is as steep as a
  wall's face, and the T-44 band of 0.5 to 1 m left the bare polygon of a tall
  siz narrower than its walled one. The floor governs wherever it is wider than
  the type's rule: the wall's wedge on fill's 42° (0.45 H) and the fill bank
  (0.45 H) always, the half-metre headscarp band always, and the one-metre
  band above 2 m high. `width_rule` stays the
  type's rule and `width_floored` says where the floor set the width.
- Fill and its thickness are read onto each element by `fill_by_element()` from
  the element's majority ground map row.
- `build_slope_polygons` builds the evacuated, imminent and inundated zones
  twice, with `with_walls` setting every element walled (`walled`) or none
  (`bare`). `zone_polygons()` writes one row per polygon and zone to
  `urban-slope-zones-<scenario>.parquet`. Since 2026-10-06 the two bounds are
  built by `gen_urban_slope_wall_zones.py`, not the faces script, because
  they include the elements on the GNS-only units' lines, which exist only
  once the wall units do.
- The evidence for a retaining wall is read onto every pif by
  `landloss.hazard.landslide.wall_candidates.wall_candidate_evidence`: distance
  to a GNS mapped wall and to a GNS cut/fill line, whether any point of the pif
  is in a SLIDE cut slope or fill body, the ground map's material and
  modification at the pif's centre, the distance to the nearest building (all
  distances recorded to `SEARCH_M`), and the pif's height band. A pif is a wall
  candidate if it is a siz (class `siz`) or a GNS mapped wall lies within
  `GNS_WALL_MATCH_M` of it (class `small`). No probability is put on a
  candidate.
- Each pif is tied to a property by `wall_candidates.property_of_pifs`: the LINZ
  NZ Property Boundaries polygon (`get_nz_property_boundaries`) holding most of
  its pips. The siz table carries `property_id`, `property_source`,
  `valuation_reference`, `title_type`, `property_is_road`, `property_share` (the
  fraction of the pif's pips in that property) and `n_properties` (how many
  properties its pips touch). `describe_properties()` prints how many pifs
  are on road parcels or straddle properties.
- Every stretch of GNS mapped wall with no pip within `GNS_WALL_MATCH_M` is made
  a candidate of its own, class `gns_only`, by
  `wall_candidates.gen_gns_only_candidates`: stretches under
  `GNS_ONLY_MIN_LENGTH_M` are dropped and longer ones are cut into equal pieces
  no longer than `MAX_PIF_SPAN_M`. Each carries its length, midpoint, property
  (the one holding most of its length), ground map material and modification,
  and nearest building. They are written as lines to
  `urban-slope-gns-wall-candidates.parquet` (`gns_only_path()`).
- The siz table (every pif, the pips as a MultiPoint, the evidence and property
  columns) is written to `urban-slope-sizs.parquet` by `gen_urban_slope_faces.py`,
  and the grown elements as polygons to `urban-slope-elements.parquet`. All are
  under `temp/hazard/landslide/`, with `extent_suffix(extent)` on the name.
- For joining pieces of one wall end to end, the siz table also carries
  `pip_direction` (each pip's fall direction, an index into `DIRECTIONS`, in
  the order of the MultiPoint's points) and, from
  `instability_zones.gen_pif_spines`, the pif's `spine` (the longest shortest
  path through its pips joined within `PIF_JOIN_M`, by a double sweep on the
  whole graph: a minimum spanning tree's longest path folds back on a face two
  or more cells thick, with both ends at one end), `spine_length_m`, the two
  spine ends (`end_a_x`, `end_a_y`, `end_b_x`, `end_b_y`), the mean fall
  direction of the pips within `PIF_END_WINDOW_M` of each end
  (`end_a_fall_deg`, `end_b_fall_deg`) and `fall_resultant` (1 for a straight
  face). `property_of_pifs` adds `rateable_property_id` and `rateable_share`:
  the property with most of the pif's pips unless that is a road parcel, then
  the non-road property with the next most (ties to the lowest id), NA if
  none. A GNS-only piece gets its `rateable_property_id` by the same rule on
  length. Stacked unit titles (identical geometry) count once, as the title
  `landloss.exposure.land.extent.stack_representatives` picks (the lowest
  `source_id`), the same title `build_claim_properties` makes the claim and
  `gen_property_wall_records` gives the record to. The GNS-only file is
  indexed by `gns_only_id`.
- `gen_urban_slope_faces.py` also keeps the found elements as a pickle,
  `urban-slope-found.pkl` (`found_path()`), so the per-world zones are built
  from them without finding them again.
- Counts and timings are printed by `describe()`. Over the `wlg-pilot` extent
  (2026-10-06, with the three-pip pif, the kept siz elements and the minimum
  width): 353,740 pips, 6,892 pifs, 4,953 sizs (4,447 of 4,447 soil pifs and
  506 of 2,445 weak rock) and 8,729 elements in 30.3 s, 164 of them kept
  only because a siz grew them (19 with no transect); every siz pif grows an
  element. The polygons take 7.7 s (walled, 8,729 polygons, 681,973 m²
  evacuated) and 9.2 s (bare, 8,903 polygons, 666,087 m²). The minimum width
  sets the width of every polygon on the pilot, walled or bare: the retained
  ground takes the fill's 42° everywhere, so the wall's wedge (0.45 H) never
  reaches half the height. The pifs are 4,953 `siz` candidates and 106
  `small` ones (a GNS wall with no siz); 1,833 are not candidates. Every pif
  is in a property polygon; 510 are on road parcels and 2,357 straddle two
  or more properties. 1,000 GNS-only candidates (10,106 m of the 30,676 m of
  mapped wall, 3 to 20 m long) are made. Before the three-pip rule
  (2026-10-05): 12,015 pifs, 8,223 sizs (3,270 of them under three pips),
  9,204 elements, 2,782 siz pifs growing none, 640,878 m² walled and
  612,654 m² bare, and 979 GNS-only candidates.
- `table_urban_slope_face_checks.py` writes three tables to
  `report/hazard/landslide/urban-slope-faces/tab/`. `gns-agreement.csv`: with
  a pip within 2 m, 63% of the GNS mapped wall length is near a siz and 67%
  near any pif; within 3 m, 59% of the sharp breaks in slope are near a siz and
  66% near any pif, and 38% and 44% of the rounded breaks. Only 5% of the GNS
  cut/fill lines have a pip within 2 m. `polygon-sizes.csv`: median evacuated
  polygon 56 m² (walled), 90th percentile 150 m², largest 551 m², none over
  `LARGE_POLYGON_M2`. `sizs-by-group-band.csv`: the pifs by ground group and
  the two height bands.
- The walled and bare zones above are the bounds. What downstream reads is the
  wall placement (`.agents/plans/placing-retaining-walls-on-pifs.md`), in
  `landloss.hazard.landslide.wall_units`, run by
  `gen_urban_slope_wall_units.py`:
  - **Units.** The candidate pifs (`siz` and `small`) and the GNS-only pieces
    are joined into wall units across property boundaries (the lead,
    2026-10-06: no join rule reads the property, so one GNS mapped wall
    feature is one unit however many lots it crosses, and pifs and GNS-only
    pieces join whatever their property; before, every join needed one
    `rateable_property_id`): members within
    `GNS_WALL_MATCH_M` of one GNS mapped wall feature (segments within
    `GNS_FEATURE_SNAP_M` of each other, `gen_gns_wall_features`) join; a
    GNS-only piece within `GNS_ONLY_MERGE_M` of a pif joins it where its
    bearing is within `GNS_ONLY_MERGE_MAX_ANGLE_DEG` (45°) of the pif's strike
    at the spine end nearest it (2026-10-06: before, it joined whatever its
    direction, and on the pilot unit `WU0001918` joined an east-west mapped
    wall to a north-south pif across it); and two pifs
    join end to end where their facing ends are within `WALL_JOIN_GAP_M`,
    offset along the fall by no more than `WALL_JOIN_MAX_OFFSET_M` and with end
    falls within `WALL_JOIN_BEARING_TOL_DEG`, or at a corner within
    `WALL_CORNER_GAP_M` whose falls turn by more than
    `WALL_JOIN_BEARING_TOL_DEG` and no more than `WALL_CORNER_MAX_ANGLE_DEG`
    (`gen_wall_units`; two faces falling the same way are never a corner, so
    terraces stacked down a slope stay apart however close their ends). A
    unit takes the highest member's height, the nearest building and the
    ground of its longest member.
  - **Walls and lines** (the lead, 2026-10-06; the bends rule first, then
    the boundaries; `wall_units.gen_unit_lines`). The joined members are
    chained end to end: points every 0.5 m, their minimum spanning tree, its
    longest path, then each branch left off it (a T in a mapped wall) as a
    path of its own from where it joins, if at least 3 m. Each path is
    walked from one end, and a wall runs as far as Douglas-Peucker at
    `WALL_STRAY_TOLERANCE_M` (2 m, about the 90th percentile of the old
    spine-to-line distance) follows it with at most `WALL_MAX_BENDS` (3)
    bends turning no more than `MAX_TOTAL_TURN_DEG` (185°) in all; the next
    wall starts there. Each wall's line is that simplification with every
    straight section under `WALL_MIN_SEGMENT_M` (3 m) merged into its
    neighbours, a wall whose ends are under 3 m apart joins a neighbour, and
    a wall whose ends are still under 3 m apart is a straight line. A wall
    whose line is over `WALL_MAX_LENGTH_M` (50 m) is then cut in the lead's
    order (2026-10-06, "if over 50 m, then split on bends; if no bends then
    split on boundaries, then split on evenly divide"): at its own bends
    (the fewest cuts that bring every part under 50 m, the most even of
    those; where no set does, the single most even cut, and again); a part
    with no bend left where it crosses property boundaries (road parcels
    included; consecutive stretches in one property kept together, pieces
    under 3 m merged into a neighbour); and what is still over 50 m into
    equal pieces. Each wall is its own unit, holding the members nearest
    most of their points (a pif straddling a cut goes to the wall with most
    of its pips; every member is in exactly one unit). A member is never
    split, so a wall no member is nearest joins the unit of the member
    nearest most of its points where the two run on end to end and the
    joined line keeps every rule; otherwise it is dropped. Every unit is one
    LineString, 3 to 50 m, at most 3 bends turning at most 185° (the lead,
    2026-10-06): `gen_wall_units` refuses any unit that breaks a rule. A wall line whose ends fold back under 3 m
    apart (a small loop of members) is the straight line between its two
    points furthest apart. `length_m` is the lines' length (what exposure rw step 6
    draws), `length_original_m` the members' summed length, `n_bends` the
    most bends of any of its lines.
  - **Properties.** `wall_units.gen_unit_properties` intersects each unit's
    line with the LINZ properties (stacked titles once): `property_lengths_m`
    lists every non-road property it enters by at least
    `BETA_MIN_WALL_LENGTH_IN_PROPERTY_M` (1 m) with the length inside it,
    longest first, and `n_properties` counts them; `property_id`, the primary,
    is the non-road property holding most of the line (ties to the lowest
    id), NA where it is on road parcels only. The primary is what the claim,
    the exposure draw and the per-unit checks use.
  - **Height from the siz table, class from step 13.** A pif's `height_m`
    is the siz table's `near_drop_p80_m` (the lead, 2026-10-06), written by
    `gen_urban_slope_faces.py` (`instability_zones.gen_pif_near_drops`): the
    `WALL_HEIGHT_QUANTILE` (0.7) quantile over its pips of each pip's near
    drop, the fall to the lowest DEM cell within `WALL_HEIGHT_REACH_M` (2 m)
    below it along its own fall direction (1 and 2 cells; 1 cell on a
    diagonal). The lead set 0.7 within 2 m on 2026-10-06, after 0.8 within
    3 m put 18% of walled units under 1.5 m and 0.6 within 2 m put 72%. Step 13's walk to the foot of the face,
    used until then, ran up to 15 m down long batters and hillsides and
    overstated the height (the tall face taper hit 2,013 pilot units), as
    `max_delta_h_m`, the largest drop of any pip pair, did before it (kept
    only for reference). The script reads step 13's pif table
    (`urban-slope-pif-cut-fill.parquet`) for the class alone and stops,
    telling you to run step 13, if it is missing or older than the siz
    table. Each GNS-only piece's height is the
    step the 1 m DEM makes across it (`landloss.exposure.rw.lines.step_height_m`).
    A unit takes the `cut_fill_class` of its longest pif; where pifs tie for
    the longest, the tied class most of its pifs hold, then the lowest pif id.
    A GNS-only unit is `unknown`.
  - **Probability.** `gen_wall_prior` sets the prior from the `BETA_` weights
    in `landloss.domain.constants`: siz or small, the height band of the
    unit's `height_m` (`prior_height_band`; the siz table's `height_band`,
    from `max_delta_h_m`, is left for the hazard), then one factor by the
    unit's class. `fill` and `cut_and_fill` take
    `BETA_FILL_WALL_FACTOR`; `cut` on a rock material with a height over
    `BETA_ROCK_CUT_MIN_HEIGHT_M` takes `BETA_ROCK_CUT_FACTOR` (a cut in soil,
    or a lower one in rock, keeps its prior); `natural` takes
    `BETA_NATURAL_WALL_FACTOR`; `uncertain` and `unknown` are unchanged.
    Then the setting (approved 2026-10-06, `wall_units.gen_unit_boundary_flags`):
    a unit with at least half its line within `BETA_WALL_BOUNDARY_DISTANCE_M`
    (2 m) of a road parcel's boundary takes `BETA_ROAD_FRONTAGE_WALL_FACTOR`
    (2.0), else one that near a non-road property boundary takes
    `BETA_BOUNDARY_WALL_FACTOR` (1.5): on the pilot, candidate pifs within
    2 m of a boundary carry a GNS wall 20% of the time against 8% off one
    (32% against 12% on a road frontage), within each height band; set
    under those ratios because GNS maps the walls visible from above.
    Last, `tall_face_factor` (2026-10-06): the prior keeps all of itself up
    to `BETA_TALL_FACE_TAPER_START_M` (5 m) of `height_m`, falling linearly
    to `BETA_TALL_FACE_MIN_FACTOR` (0.1) at `BETA_TALL_FACE_TAPER_END_M`
    (8 m) and above, as a face that high is rarely retained in full on a
    residential lot. Each sets `p_prior_basis` (`road_frontage`,
    `property_boundary`, `tall_face`) and a flag (`is_road_frontage`,
    `is_property_boundary`, `tall_face_factor`). The GNS floor and the
    claim update apply on top, so a mapped wall stays at 0.95. The ground
    map's fill (material or `modification`) and the SLIDE fill bodies no
    longer set the prior. `gen_gns_floor`
    lifts a unit with a GNS mapped wall to `BETA_GNS_WALL_UNIT_FLOOR` and sets
    a GNS-only unit at `BETA_GNS_ONLY_WALL_PROBABILITY`. The claim and NZMM
    layer (`exposure/rw/validations/config.PROPERTIES_PATH`) is read onto each
    LINZ property by the smallest record polygon holding its representative
    point (`gen_property_wall_records`), and `gen_wall_unit_probability`
    updates each property's units on the walls its claim report lists
    (`p_claims`) and on the larger of that and `BETA_NZMM_MIN_WALLS` where
    NZMM is true (`p_claims_nzmm`), with the Poisson-binomial
    (`gen_count_update`). A unit is a wall on every property in its
    `property_lengths_m`: each property is updated over all the units on it,
    each from its floor, and a unit on several keeps the highest of its
    updates (each is conditioned on a record of that property and none
    lowers a probability); `n_units` in the candidates missing table counts
    every unit on the property. NZMM is applied modestly: where its count is the
    larger, a unit moves only `BETA_NZMM_UPDATE_WEIGHT` (0.3) of the way from
    its claims update to the full NZMM update, so an NZMM flag is weaker than a
    claim report listing two walls. `CLAIM_HOLDOUT_SHARE` of the claimed properties,
    picked with `CLAIM_HOLDOUT_SEED`, are never updated. `p_wall` is
    `p_claims_nzmm` where `USE_NZMM_UPDATE`, else `p_claims`; each part
    carries the rule that set it.
  - **Draws.** `gen_wall_draws` draws each unit walled, for each world in
    `WORLD_IDS` (read from exposure rw step 6's config, the worlds it
    populates), on the `wall_units` stream under `EXPOSURE_BASE_SEED`.
  - Written under `temp/hazard/landslide/`: the unit table
    (`urban-slope-wall-units.geoparquet`, `wall_units_path()`), the draws
    (`urban-slope-wall-draws.parquet`), the properties whose units cannot hold
    their listed walls (`urban-slope-wall-candidates-missing.parquet`) and the
    records on each property with the hold-out
    (`urban-slope-wall-property-records.parquet`). The last two are per
    property and stay under `temp/`.
- `gen_urban_slope_wall_zones.py` first gives every unit none of whose pifs
  grew an element (the GNS-only units and, since 2026-10-06, the units of
  `small` pifs, a GNS mapped wall on a pif that is not a siz:
  `units_without_element`) an element along its line. A small pif's unit
  takes a line element rather than growth from its pips: its pif failed the
  siz test, so growth at the siz threshold would keep little but its own
  pips and measure a face the test called not steep enough, while the line
  takes the unit's own wall height and the same width floor as every wall
  (`instability_zones.add_line_elements`, the lead, 2026-10-06): the line is
  burnt onto the grid, every cell it touches that no element holds, as an
  element of its own with `wall_unit_id` set, `grown_in` `wall_line`,
  `siz_id` 0, its height the unit's step height but never under
  `MIN_WALL_HEIGHT_M` (0.5 m), and a run of 0 (a step, 90 degrees). The
  elements are measured again so the edge roles, stack links and
  catchments see the new ones, and the old keep their labels and columns.
  The polygon builder then treats it as any other: the DEM sets which side
  is uphill (its crest cells are those whose uphill neighbour is off it),
  the width behind the crest is the floor, `max(0.5 H, 1 m)`, and the depth
  is the wall's planar slip (`0.5 H w` per metre) when walled, the bank's
  (fill thickness or cover depth) when not. These elements are written to
  `urban-slope-wall-elements.parquet` (`wall_elements_path()`), which
  landslide step 8 reads, and the walled and bare bounds are built from
  them. Then it builds the zones of each world's draw: an
  element is walled where its pif is in a walled unit, or its line is a
  walled unit's (`gen_element_walls`),
  and the zones are written to `urban-slope-zones-wNNN.parquet` in the shape
  of the two bounds. It reads the found elements the faces script kept, and
  refuses to run if they or the siz table are newer than the wall units.
  These per-world zones are what landslide step 8 reads, in place of step 7's
  polygons (2026-10-06): each polygon's wall is its element's wall unit, the
  id exposure rw step 6 writes as the drawn wall's `wall_line_id`, so the
  hazard and the exposure share one draw (step 8 method file). The bounds
  are never read downstream.
- `fig_urban_slope_wall_zones.py` draws, at each site of `FIG_SITES` (the
  stage D2 pilot sites), one panel per zone file in `FIG_ZONE_SCENARIOS`:
  the evacuated zones coloured by whether the element is walled, the imminent
  and inundated zones at their true shape over a hillshade, and the wall
  units. Set to `("walled", "bare")` it shows what the walls change; a world
  (`"w000"`) shows the pipeline's zones, its walled units solid. Written to
  `report/hazard/landslide/urban-slope-faces/fig/`.
- `gen_hazard.main` runs the faces script, step 13
  (`gen_pif_cut_fill.py`), then the wall units and wall zones scripts, after
  the ground map and before exposure, so `gen_all.py` runs end to end.
- `table_urban_slope_wall_checks.py` writes four aggregate tables to
  `report/hazard/landslide/urban-slope-faces/tab/`: `wall-gns-recall.csv`
  (mapped wall length within 2 m of a member's footprint),
  `wall-claims-holdout.csv` (the floor and both updates on the held-out
  claimed properties), `wall-strata.csv` (modelled and recorded wall shares
  by council, NZMM slope class and the age bin of exposure rw step 8, with
  `below_recorded` where the share of properties more likely than not to have
  a wall is below the largest recorded share; the age bin is one `not
  available` row, with its reason, where step 8 has not been run for the
  extent) and `wall-pilot-counts.csv`. The pif recall in `wall-gns-recall.csv`
  is computed from the siz table, not copied. Any value over
  fewer than `MIN_HEX_CLAIMS` properties is blanked and named in
  `suppressed`.
- Over the `wlg-pilot` extent (rerun 2026-10-06 with the three-pip pif, the
  kept siz elements, the minimum width and the GNS-only merge angle): the
  4,953 `siz` and 106 `small` pifs and 1,000 GNS-only pieces (5 with no step
  read) make 6,059 members on 998 mapped wall features, joined into 5,002
  units: 4,577 with a pif (4,407 on a property) and 425 GNS-only (332 on a
  property). Expected walls 1,818 from the prior, 2,580 after the floor,
  2,582 with the claims and 2,609 with NZMM; the claims leave 11 walls
  missing on 9 properties, NZMM 206 on 147. In world 0, 52.2% of the units
  and 50.4% of the sizs are walled, 58.6% of the elements, and the evacuated
  area is 679,143 m² in 8,785 polygons; every element's pif is in a unit.
  64% of the mapped wall length is within 2 m of a pif and 97% of a pif or
  GNS-only piece. 31% of the walled units are under 1.5 m, against 54% in
  Canterbury [anderson_2015]. Through exposure rw step 6 and landslide steps
  8 and 9, 185 of world 0's 1,570 insured sloping walls have no polygon
  (`slope_id` null), against 573 of 2,004 before: 175 on GNS-only units, 4
  on `small` pifs and 6 on siz pifs whose polygons lie in step 12's DEM
  margin outside the shaking grids, which step 8 leaves out.
  Rerun again on 2026-10-06 with the building outlines, the unit lines and
  the units across properties: 334 pifs dropped with most of their pips in
  a building outline, leaving 6,558 pifs, 4,676 sizs and 8,425 elements
  (672,136 m² evacuated walled, 656,367 m² bare); 1,005 GNS-only pieces;
  5,787 members join into 3,961 units (5,002 before), whose lines total
  86,689 m against 95,018 m of members, with 2,027 straight, 973 with one
  bend, 660 with two and 301 with three. 161 units are on road parcels
  only, 2,483 on one property, 815 on two and 502 on three or more (the
  longest, GNS walls along many back boundaries, up to 600 m and 30
  properties). Expected walls 1,908 (1,878 after the floor); the claims
  leave 6 walls missing on 6 properties, NZMM 133 on 105. In world 0, 49.0%
  of the units are walled and the evacuated area is 668,912 m²; 1,940 walls
  are drawn and 1,141 insured, 48 of which have no polygon in step 9 (42
  GNS-only, 2 `small`, 4 at the DEM margin). 23% of the walled units are
  under 1.5 m. The pif spines lie within 0.7 m of their unit's line at the
  median and 2.4 m at the 90th percentile, but 174 of the 460 units over
  50 m stray more than 5 m (up to 100 m): three bends cannot follow a long
  winding wall.
  Rerun a third time on 2026-10-06 with the bends and boundary split, the
  GNS-only polygons, the boundary and road frontage factors and the tall
  face taper: the 5,787 members make 4,647 units (3,961 before); 3,029
  straight, 870 with one bend, 438 with two and 310 with three; 4,154 one
  line and 493 several (the units of the long pifs, up to 56 lines and
  779 m). 99% of the member pifs' spine points lie within 2.0 m of a unit
  line (0.34 m median, 9.2 m at most; before, 15% lay more than 5 m off,
  where a long pif's other walls were dropped). Single lines over 50 m:
  211, 152 in one non-road property, 39 on road parcels only and 20 still
  entering a second property by 1 m or more (a stretch under 3 m merged
  into its neighbour, or a line weaving along a boundary). Properties entered: 215 units on road
  parcels only, 2,931 on one, 982 on two and 519 on three or more (48 at
  most, a long pif). 1,584 units are on a property boundary and 559 on a
  road frontage; 669 have a face over 5 m (306 over 8 m), 85 of them held
  at the GNS floor. Expected walls 2,639 (2,614 after the floor; 2,752
  without the tall face taper; the claims leave 8 walls missing on 7
  properties, NZMM 105 on 82). 407 GNS-only units, 404 given an element.
  Evacuated 681,983 m² walled, 666,134 m² bare and 678,132 m² in world 0
  (8,892 polygons). World 0 draws 2,657 walls, 1,668 insured, 15 with no
  polygon in step 9 (5 GNS-only units with no element or at the margin, 6
  `small`, 4 at the DEM margin). Walled units by height: 854 under 1.5 m,
  892 to 2.5 m, 732 to 5 m, 147 to 8 m and 27 over (437, 614, 583, 174 and
  132 before the taper and the new units); 32% under 1.5 m against 54% in
  Anderson et al.
  Rerun a fourth time on 2026-10-06 with the pif pieces and the small
  pifs' line elements: 6,558 whole pifs make 10,379 pieces (8 under three
  pips), 8,425 siz pieces (each with its element), 123 `small` and 1,831
  not candidates; step 13 classes all 10,379. 9,553 members make 6,713
  units (4,647 before): 3,784 straight, 1,638 with one bend, 741 with two
  and 550 with three; 6,296 one line and 417 several (up to 5 lines; 493,
  up to 56, before); 144 over 50 m, the longest 161 m (779 m before). 99%
  of the member pifs' spine points lie within 2.0 m of a unit line (0.36 m
  median, 9.3 m at most); 9 of the 144 units over 50 m stray more than
  5 m. Properties entered: 385 units on road parcels only, 4,034 on one,
  1,730 on two, 541 on three or more (12 at most, short units on
  overlapping unit titles). 2,016 units on a property boundary, 732 on a
  road frontage; 2,013 with a face over 5 m (each piece now has its own
  height, so more do; 1,020 over 8 m). Expected walls 3,347 (3,318 after
  the floor); the claims leave 5 walls missing on 5 properties, NZMM 79 on
  58. 421 units had no element (354 GNS-only, 67 of `small` pifs) and 419
  were given one. Evacuated 684,120 m² walled, 668,306 m² bare, 674,476 m²
  in world 0 (8,968 polygons). World 0 draws 3,347 walls, 1,945 insured,
  11 with no polygon in step 9: 10 whose polygons lie in step 12's DEM
  margin outside the shaking grids (step 8 leaves them out; 5 small, 3 siz,
  2 GNS-only) and 1 GNS-only unit whose line lies wholly on other elements.
  Walled units by height: 795 under 1.5 m, 960 to 2.5 m, 1,123 to 5 m, 365
  to 8 m, 100 over; 24% under 1.5 m against 54% in Anderson et al.
  Rerun a fifth time on 2026-10-06 with the pifs cut by the wall rules
  (50 m cap) and the near drop height: 6,558 whole pifs make 7,762 pieces
  (10,379 at the 20 m split), median spine 7.4 m, 90th percentile 36.7 m,
  99th 52.2 m and the longest 83 m (a piece's own spine can pass 50 m where
  its pips spread off the path it was cut on); 1,419 under 3 m (short pifs
  of three or more pips). 5,865 siz pieces, each with its element; 110
  `small`. Elements: 6,267 with the line elements (8,844 before), 1,100
  over 30 m and 55 over 50 m along the contour (55 and 16 before), the
  largest 1,370 m² (322 m²). 6,827 members make 5,540 units: 3,297
  straight, 1,133 with one bend, 647 with two, 463 with three; 5,299 one
  line and 241 several (417 before; 150 of them a single pif whose own
  spine needs a fourth bend or whose stretch sticks out); 268 over 50 m,
  the longest 174 m. Member spines lie within 1.0 m of their unit's line at
  the median, 2.0 m at the 90th percentile (99% of spine points within
  2.0 m of some line); 13 of the 268 units over 50 m stray more than 5 m.
  Properties entered: 282 on road parcels only, 3,346 on one, 1,265 on
  two, 647 on three or more (13 at most). Heights: 9 units over 5 m and 1
  over 8 m (2,013 and 1,020 before), so the tall face taper touches 9.
  Expected walls 3,462 (3,442 after the floor). 405 units had no element
  (339 GNS-only, 66 `small`), 402 given one. Evacuated 664,360 m² walled,
  657,483 m² bare and 662,315 m² in world 0 (6,510 polygons). World 0
  draws 3,461 walls, 1,963 insured, 23 with no polygon in step 9: 22 whose
  polygon's representative point lies in step 12's DEM margin outside the
  shaking grids (longer elements reach it more often) and 1 GNS-only unit
  whose line lies wholly on other elements. Walled units by height: 620 up
  to 1.5 m, 1,927 to 2.5 m, 903 to 5 m, 7 to 8 m and 1 over; 18% under
  1.5 m against 54% in Anderson et al.
  Rerun a sixth time on 2026-10-06 with the 3 m pif minimum, the lines
  kept by construction and the near drop at 0.6 within 2 m: 334 pifs on
  buildings and 1,403 with a spine under 3 m dropped, leaving 5,106 whole
  pifs in 6,163 pieces (4,829 siz, 93 `small`), each piece line 3.2 m at
  the 10th percentile, 9.2 m median, 48.2 m at most; 4,829 elements (1,115
  over 30 m, 50 over 50 m) and 472 line elements. 5,767 members make 4,834
  units, every one a single line: 2,806 straight, 1,229 with one bend, 563
  with two, 236 with three; none under 3 m or over 50 m (longest 50.0 m,
  shortest 3.0 m); no piece or unit breaks a rule, and 3,554 m of wall
  that no member was nearest was dropped. Member piece lines lie on their
  unit's line at the median and within 5.7 m at the 90th percentile (where
  part of a member's stretch was dropped). Properties entered: 307 units on
  road parcels only, 2,862 on one, 1,189 on two, 476 on three or more (11
  at most). 2,073 units on a property boundary, 588 on a road frontage;
  none over 5 m tall, so the tall face taper touches none. Expected walls
  3,272 (3,254 after the floor). Evacuated 655,394 m² walled, 648,727 m²
  bare, 653,235 m² in world 0 (5,474 polygons). World 0 draws 3,301 walls,
  1,830 insured, 23 with no polygon in step 9 (22 in the DEM margin, 1
  GNS-only unit whose line lies on other elements). Walled units by height
  (2,405 up to 1.5 m, 873 to 2.5 m, 20 to 5 m, none over): 73% under 1.5 m,
  70% of the pif units and 97% of the GNS-only units, against 54% in
  Anderson et al.
  Rerun a seventh time on 2026-10-06 with the 185° turning cap and the
  50 m cap cut at bends, then boundaries, then evenly: 6,220 pif pieces
  (4,884 siz, 91 `small`; before the turning cap 53 pieces turned more than
  185°), the cap cutting 387 at their bends and 72 evenly; 4,884 elements
  (1,130 over 30 m, 66 over 50 m) and 433 line elements. 5,820 members
  make 4,848 units (124 turned more than 185° before): 3,059 straight,
  1,176 with one bend, 516 with two, 97 with three; the cap cut 540 walls
  at their bends, 75 at property boundaries and 61 evenly; 2,381 m of wall
  no member was nearest dropped. No piece or unit breaks a rule, none is
  multi-line; the longest unit 50.0 m, the longest piece line 49.9 m.
  Expected walls 3,272; world 0 draws 3,233 walls, 1,775 insured, 21 with
  no polygon; evacuated 656,971 m² walled, 649,210 m² bare, 654,842 m² in
  world 0 (5,511 polygons). Walled units under 1.5 m: 72% (70% of the pif
  units, 97% of the GNS-only).
- Over the `wlg-pilot` extent (2026-10-05, before the spine, corner, GNS-only
  property, stacked title and NZMM weight fixes later that day; rerun the
  faces, wall units, zones and checks scripts to refresh): the 8,420
  candidate pifs and 979
  GNS-only pieces (5 with no step read) fall on 998 mapped wall features and
  join into 7,248 units: 6,832 with a pif (6,512 on a property) and 416
  GNS-only (309 on a property). Expected walls: 2,413 from the prior over the
  pif units, 3,336 after the floor, 3,339 with the claims and 3,459 with NZMM.
  The records reach 5,411 LINZ properties: 70 claimed (21 held out), 19
  listing a wall, NZMM true on 216; the claims leave 8 walls missing on 7
  properties, NZMM 170 on 123. In world 0, 47.8% of the units and 46.9% of
  the sizs are walled, 54.4% of the elements, and the evacuated area is
  631,176 m² in 9,254 polygons, between the bounds. 67% of the mapped wall
  length is within 2 m of a pif and 97% of a pif or GNS-only piece. On the 21
  held-out claimed properties the mean expected walls is 0.46 (0.61 with
  NZMM) against 0.19 listed; P(at least one) on the 4 that list a wall is
  suppressed. 29% of the walled units are under 1.5 m, against 54% in
  Canterbury [anderson_2015]. These numbers also predate the wall height
  from step 13's face drops and the prior from its class (2026-10-06): under
  the old rules the rock cut factor applied to 2,583 units.

Potential future improvements: see `s12_urban_slope_faces_implementation_plan.md`.
