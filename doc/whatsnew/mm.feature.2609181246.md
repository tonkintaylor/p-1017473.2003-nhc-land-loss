Added `landloss.io.elevation.sample_elevation`, which samples the LINZ 1 m LiDAR
DEM at points by walking the open elevation STAC catalogue and reading only the
cells beneath them, taking each point from the most recent survey that covers it.
Added `landloss.hazard.cross_sections`, which defines a section by a centre, a
bearing and a length so a perpendicular pair is perpendicular by construction,
samples the DEM along it, and locates where it crosses a mapped watercourse.
`src/scripts/landloss/hazard/research/fig_cross_sections.py` uses both to draw
four sections -- Wainuiomata, Ōrongorongo, and a perpendicular pair across and
along the Hutt Valley -- into `research/`. The elevation data is CC BY 4.0 and
requires attribution.
