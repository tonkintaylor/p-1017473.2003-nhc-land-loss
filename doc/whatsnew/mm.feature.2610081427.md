New `ground` module, run first by `gen_all.py`. It holds the static work done
once per extent that both exposure and hazard read: ground step 1 terrain
(was landslide step 3), step 2 ground map (landslide step 4), step 3
instability zones (landslide step 14, now also holding the grid helpers and
`tiled.py`), step 4 slope faces (the wall evidence part of landslide step 12)
and step 5 pif cut and fill (landslide step 13), run by
`ground/gen_ground.py`. Their outputs move to `temp/ground/` and
`report/ground/`. Landslide step 12's wall units and per-world draws move to
exposure rw step 6 (`gen_wall_units.py`, `table_wall_unit_checks.py`, outputs
in `temp/exposure/`), and its per-world zones become landslide step 4
(`gen_wall_zones.py`). The pipeline now runs ground, exposure, hazard, vul;
the hazard module runs in one pass and `gen_hazard.main_urban` is gone. The
landslide steps are renumbered in run order: s1 slope units, s2 Hancox, s3
large-model realisations, s4 wall zones, s5 urban fragility, s6 urban
realisation, s7 susceptibility and s8 Kritikos (both not run by
`gen_hazard`). The pif and wall line rules live in ground step 3's config and
are read from there by ground step 4 and exposure rw step 6. Results are
unchanged: the Wellington pilot's siz table, elements, GNS-only walls, pif cut
and fill, wall units and draws are identical to the last run before the move.
