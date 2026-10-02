Added step 7 of the exposure model, the culvert and bridge population at
`src/scripts/landloss/exposure/culverts_bridges/steps/s7_crossing_population/`.
It intersects the insured accessways against both LINZ river layers — the name
lines and the newly pinned name polygons, read by `get_nz_river_name_polygons` —
and draws a culvert at 80% or a bridge at 20% at each crossing found, seeded
from the project realisation stream. Step 5 now writes the driveway corridors out
on their own so the accessway survives as a layer for this step to test against.

Each crossing records which river layer found it, so what reading the polygons
earns over reading the lines alone is visible per run.

Over the pilot box the population is empty, and the run says why: neither layer
returns a feature there and the nearest named watercourse is about 2.8 km away,
while the same readers return 9,233 lines and 37 polygons over the four
territorial authorities. The detection has therefore not yet met a real crossing.
