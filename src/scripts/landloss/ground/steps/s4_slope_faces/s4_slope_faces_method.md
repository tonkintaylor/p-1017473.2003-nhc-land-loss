# Ground step 4 — Slope faces: method

- The step reads the evidence for a retaining wall onto every pif of ground
  step 3's grid table, picks out the stretches of mapped wall no pif covers,
  and writes the siz table. It is run by `gen_slope_faces.py` (named "s4, slope
  faces" in `gen_ground.py`), after ground step 3, with the settings in
  `config.py` beside it; its output is under `temp/ground/`, with
  `extent_suffix(extent)` on each name.
- It reads the grid table `urban-slope-grid-sizs.parquet`
  (`gen_instability_zones.grid_sizs_path()`), and stops, telling you to run
  ground step 3, if it is missing. The search that made that table (the pips,
  pifs, pieces, the siz test, the growth and the tiling) is described in
  `s3_instability_zones_method.md`. Beside it the step reads the ground map of
  ground step 2 (`ground_map_path`), the LINZ building outlines, the GNS SLIDE
  morphology and genesis layers, the LINZ property boundaries and T+T's
  manually mapped walls, all on the bbox of the 1 m DEM of ground step 1
  (`dem_bbox()`), through the reader caches.
- **Mapped walls** are the GNS SLIDE mapped walls [townsend_2020] and, since
  2026-10-08, the walls T+T mapped by hand from aerial imagery
  (`get_tt_manual_walls`, Koordinates 125317: 71 walls, 1.1 km, Wellington
  pilot only), joined by `wall_candidates.gen_mapped_walls`. A manual wall
  within `MANUAL_WALL_DUPLICATE_M` (2 m) of a GNS wall is first dropped whole
  as the same wall mapped twice (the lead, 2026-10-08), and
  `describe_manual_walls()` prints how many were kept and dropped. Every kept
  manual wall is then used exactly as a GNS wall is, below: it is evidence on a
  pif (`gns_wall`, `gns_wall_m`), lifts a unit to the GNS floor (exposure rw
  step 6), and a stretch of it no pif covers becomes a `gns_only` candidate.
  "GNS mapped wall" below means either source; a `gns_only` candidate's
  `wall_source` (`gns` or `tt_manual`) says which. Over the `wlg-pilot` DEM box
  17 manual walls (367 m) fall inside: 4 (147 m) are dropped, each 82 to 100%
  of its length within 2 m of a GNS wall, and 13 (220 m) kept, beside 1,092 GNS
  walls (30.7 km). The checks in `table_slope_face_checks.py` and exposure rw
  step 6's `table_wall_unit_checks.py` still score the pifs against the GNS
  walls alone.
- The evidence for a retaining wall is read onto every pif by
  `landloss.hazard.landslide.wall_candidates.wall_candidate_evidence`: distance
  to a GNS mapped wall and to a GNS cut/fill line, whether any point of the pif
  is in a SLIDE cut slope or fill body, the ground map's material and
  modification at the pif's centre, the distance to the nearest building (all
  distances recorded to `SEARCH_M`), and the pif's height band. A pif is a wall
  candidate if it is a siz (class `siz`) or a GNS mapped wall lies within
  `GNS_WALL_MATCH_M` of it (class `low_height`, called `small` until
  2026-10-07). No probability is put on a candidate.
- Each pif is tied to a property by `wall_candidates.property_of_pifs`: the LINZ
  NZ Property Boundaries polygon (`get_nz_property_boundaries`) holding most of
  its pips. The siz table carries `property_id`, `property_source`,
  `valuation_reference`, `title_type`, `property_is_road`, `property_share` (the
  fraction of the pif's pips in that property) and `n_properties` (how many
  properties its pips touch). It also carries `rateable_property_id` and
  `rateable_share`: the property with most of the pif's pips unless that is a
  road parcel, then the non-road property with the next most (ties to the
  lowest id), NA if none. Stacked unit titles (identical geometry) count once,
  as the title `landloss.exposure.land.extent.stack_representatives` picks (the
  lowest `source_id`), the same title `build_claim_properties` makes the claim
  and `gen_property_wall_records` gives the record to. `describe_properties()`
  prints how many pifs are on road parcels or straddle properties.
- Every stretch of GNS mapped wall with no pip within `GNS_WALL_MATCH_M` is
  cut into candidates of its own, class `gns_only`, by
  `wall_candidates.gen_gns_only_candidates`: stretches under
  `GNS_ONLY_MIN_LENGTH_M` are dropped and longer ones are cut by the shared
  line rules (`wall_candidates.split_by_rules`, `bend_split`; the lead,
  2026-10-07, in place of an equal 20 m cut), whose settings are ground step 3's
  `config.py`: at most `WALL_MAX_BENDS` bends within `WALL_STRAY_TOLERANCE_M`,
  turning at most `MAX_TOTAL_TURN_DEG`, 3 to `WALL_MAX_LENGTH_M` (50 m) long, a
  piece over 50 m cut at its bends, then at property boundaries, then evenly. A
  mapped wall within `GNS_WALL_MATCH_M` of a pif piece is no candidate of its
  own: it sets that piece's `gns_wall` flag. Each carries its length, midpoint,
  property (the one holding most of its length, and a `rateable_property_id` by
  the pif rule on length), ground map material and modification, and nearest
  building. They are written as lines to
  `urban-slope-gns-wall-candidates.parquet` (`gns_only_path()`), indexed by
  `gns_only_id`.
- The siz table (every pif, the pips as a MultiPoint, the grid columns of ground
  step 3 including the wall height `near_drop_p80_m`, the spine and end falls,
  and the evidence and property columns of this step) is written to
  `urban-slope-sizs.parquet` (`siz_table_path()`) by `gen_slope_faces.py`. Ground
  step 5 reads it for the pifs; exposure rw step 6 reads it and the GNS-only
  file for the wall units.
- Counts are printed by `main()` (the class counts and the GNS-only summary),
  `describe_properties()` and `describe_manual_walls()`. Over the `wlg-pilot`
  extent (2026-10-08, the per-piece fall-line siz test, run by `gen_ground.py`):
  6,220 pif pieces, 4,790 `siz` and 98 `low_height` candidates, 1,332 none;
  612 pifs on road parcels and 2,770 straddling two or more properties; 17 T+T
  manual walls (367 m), 13 kept and 4 dropped as GNS duplicates; and 859
  GNS-only pieces (10,471 m of 30,896 m of mapped wall). On 2026-10-07 (the
  pairs siz test): 4,884 `siz` and 91 `low_height` candidates. Earlier (2026-10-06): 4,953 `siz` candidates and 106 `low_height`
  ones, 1,833 pifs not candidates; every pif is in a property polygon, 510 on
  road parcels and 2,357 straddling two or more properties.
- `table_slope_face_checks.py` writes three tables to
  `report/ground/urban-slope-faces/tab/`. `gns-agreement.csv`: with a pip
  within 2 m, 63% of the GNS mapped wall length is near a siz and 67% near any
  pif; within 3 m, 59% of the sharp breaks in slope are near a siz and 66% near
  any pif, and 38% and 44% of the rounded breaks. Only 5% of the GNS cut/fill
  lines have a pip within 2 m. `polygon-sizes.csv`: the evacuated polygons of
  each scenario by area (median evacuated polygon 56 m² walled, 90th percentile
  150 m², largest 551 m², none over `LARGE_POLYGON_M2`, at 2026-10-06); it reads
  the zone files of landslide step 4, so that step has to have run for it.
  `sizs-by-group-band.csv`: the pifs by ground group and the two height bands.
- The wall units, their probability and the claim update, and the draws per
  world are built from this step's tables by exposure rw step 6
  (`gen_wall_units.py`, `s6_wall_population_method.md`). The zones of each
  world's walls are built by landslide step 4 (`gen_wall_zones.py`,
  `s4_wall_zones_method.md`).

Potential future improvements: see `s4_slope_faces_implementation_plan.md`.
