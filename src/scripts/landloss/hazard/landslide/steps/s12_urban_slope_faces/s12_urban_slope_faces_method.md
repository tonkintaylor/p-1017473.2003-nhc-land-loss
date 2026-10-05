# Step 12 — Urban slope faces: method

- The DEM comes from step 3 (`dem_path`) and the ground map from step 4
  (`ground_map_path`), both for the extent in `config.py`. `get_dem()` in
  `gen_urban_slope_faces.py` sets every cell outside the LINZ NZ Coastlines and
  Islands Polygons to no data (step 13 reads the DEM through it too), and
  `get_inputs()` adds the ground map, rasterised to ground groups with fill
  read as soil.
- `landloss.hazard.landslide.instability_zones.find_instability_zones` finds the
  pips, pifs and sizs, cuts every pif spanning more than `MAX_PIF_SPAN_M` into
  pieces, grows the pieces of the sizs into elements with the watershed growth,
  and carries each element's siz and its angles. The rules and thresholds are
  in `.agents/plans/building-pip-pif-siz-slope-polygons.md` and the two CSV
  files `landslide-slope-thresholds.csv` and `landslide-seed-thresholds.csv`
  in `landloss/io/assets/` that the library reads.
- Fill and its thickness are read onto each element by `fill_by_element()` from
  the element's majority ground map row.
- `build_slope_polygons` builds the evacuated, imminent and inundated zones
  twice, with `with_walls` setting every element walled (`walled`) or none
  (`bare`). `zone_polygons()` writes one row per polygon and zone to
  `urban-slope-zones-<scenario>.parquet`.
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
- Counts and timings are printed by `describe()`. Over the `wlg-pilot` extent:
  353,740 pips, 12,015 pifs, 8,223 sizs (7,709 of 7,709 soil pifs and 514 of
  4,306 weak rock) and 9,204 elements in 24.8 s; the polygons take 6.8 s
  (walled, 9,204 polygons, 640,878 m² evacuated) and 8.7 s (bare, 9,354
  polygons, 612,654 m²). The pifs are 8,223 `siz` candidates and 197 `small`
  ones (a GNS wall with no siz); 3,595 are not candidates. Every pif is in a
  property polygon; 832 are on road parcels and 2,440 straddle two or more
  properties. 979 GNS-only candidates (8,940 m of the 30,676 m of mapped wall,
  3 to 20 m long) are made, 201 of them on road parcels.
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
    are joined into wall units on one property (`rateable_property_id`, NA
    where only road parcels are touched): members within
    `GNS_WALL_MATCH_M` of one GNS mapped wall feature (segments within
    `GNS_FEATURE_SNAP_M` of each other, `gen_gns_wall_features`) join; a
    GNS-only piece within `GNS_ONLY_MERGE_M` of a pif joins it; and two pifs
    join end to end where their facing ends are within `WALL_JOIN_GAP_M`,
    offset along the fall by no more than `WALL_JOIN_MAX_OFFSET_M` and with end
    falls within `WALL_JOIN_BEARING_TOL_DEG`, or at a corner within
    `WALL_CORNER_GAP_M` whose falls turn by more than
    `WALL_JOIN_BEARING_TOL_DEG` and no more than `WALL_CORNER_MAX_ANGLE_DEG`
    (`gen_wall_units`; two faces falling the same way are never a corner, so
    terraces stacked down a slope stay apart however close their ends). A
    unit takes the highest face, the nearest building and the ground of its
    longest member. Each GNS-only piece's height is the step the 1 m DEM makes
    across it (`landloss.exposure.rw.lines.step_height_m`).
  - **Probability.** `gen_wall_prior` sets the prior from the `BETA_` weights
    in `landloss.domain.constants` (siz or small, height band, a rock cut over
    `BETA_ROCK_CUT_MIN_HEIGHT_M`, fill from the ground map material or a SLIDE
    fill body; the ground map's `modification` is not read). `gen_gns_floor`
    lifts a unit with a GNS mapped wall to `BETA_GNS_WALL_UNIT_FLOOR` and sets
    a GNS-only unit at `BETA_GNS_ONLY_WALL_PROBABILITY`. The claim and NZMM
    layer (`exposure/rw/validations/config.PROPERTIES_PATH`) is read onto each
    LINZ property by the smallest record polygon holding its representative
    point (`gen_property_wall_records`), and `gen_wall_unit_probability`
    updates each property's units on the walls its claim report lists
    (`p_claims`) and on the larger of that and `BETA_NZMM_MIN_WALLS` where
    NZMM is true (`p_claims_nzmm`), with the Poisson-binomial
    (`gen_count_update`). NZMM is applied modestly: where its count is the
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
- `gen_urban_slope_wall_zones.py` builds the zones of each world's draw: an
  element is walled where its pif is in a walled unit (`gen_element_walls`),
  and the zones are written to `urban-slope-zones-wNNN.parquet` in the shape
  of the two bounds. It reads the found elements the faces script kept, and
  refuses to run if they or the siz table are newer than the wall units.
- `gen_hazard.main` runs the faces, wall units and wall zones scripts, after
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
  Canterbury [anderson_2015].

Potential future improvements: see `s12_urban_slope_faces_implementation_plan.md`.
