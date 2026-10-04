# Step 12 — Urban slope faces: method

- The DEM comes from step 3 (`dem_path`) and the ground map from step 4
  (`ground_map_path`), both for the extent in `config.py`. `get_inputs()` in
  `gen_urban_slope_faces.py` sets every cell outside the LINZ NZ Coastlines and
  Islands Polygons to no data, and rasterises the ground map to ground groups
  with fill read as soil.
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
- The siz table (every pif, the pips as a MultiPoint, the evidence columns) is
  written to `urban-slope-sizs.parquet` by `gen_urban_slope_faces.py`, and the
  grown elements as polygons to `urban-slope-elements.parquet`. All are under
  `temp/hazard/landslide/`, with `extent_suffix(extent)` on the name.
- Counts and timings are printed by `describe()`. Over the `wlg-pilot` extent:
  353,740 pips, 12,015 pifs, 8,223 sizs (7,709 of 7,709 soil pifs and 514 of
  4,306 weak rock) and 9,204 elements in 24.8 s; the polygons take 6.8 s
  (walled, 9,204 polygons, 640,878 m² evacuated) and 8.7 s (bare, 9,354
  polygons, 612,654 m²). The pifs are 8,223 `siz` candidates and 197 `small`
  ones (a GNS wall with no siz); 3,595 are not candidates.
- `table_urban_slope_face_checks.py` writes three tables to
  `report/hazard/landslide/urban-slope-faces/tab/`. `gns-agreement.csv`: with
  a pip within 2 m, 63% of the GNS mapped wall length is near a siz and 67%
  near any pif; within 3 m, 59% of the sharp breaks in slope are near a siz and
  66% near any pif, and 38% and 44% of the rounded breaks. Only 5% of the GNS
  cut/fill lines have a pip within 2 m. `polygon-sizes.csv`: median evacuated
  polygon 56 m² (walled), 90th percentile 150 m², largest 551 m², none over
  `LARGE_POLYGON_M2`. `sizs-by-group-band.csv`: the pifs by ground group and
  the two height bands.

Potential future improvements: see `s12_urban_slope_faces_implementation_plan.md`.
