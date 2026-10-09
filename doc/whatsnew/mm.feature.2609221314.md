The land exposure now has a geometry. `landloss.exposure.land.extent` builds the
insured land extent — an 8 metre buffer of the building outlines, which is NHC's
own definition of the land it settles on — and
`src/scripts/landloss/exposure/land/steps/s5_insured_land_extent/gen_insured_land.py`
writes it to `temp/exposure/insured-land.geoparquet` with `address_id`,
`land_rate_nzd_per_m2`, `area_m2` and the polygon. That layer is what the hazard
modules are intersected against, replacing the address point the chain stopped
at before.

Each building is attached to its nearest address point, a property's buildings
are buffered and merged into one polygon, and ground within 8 metres of two
properties' buildings goes to the nearer building — a Voronoi partition over
points spaced along the contested outlines. That last step is what stops the
strip between two houses being counted twice when the vulnerability step sums
area per address, and the run re-measures its own output against a dissolve to
say so rather than assume it.

Driveways are part of the insured land definition and are not built. They are
where most retaining walls sit, so the omission is recorded in the module
docstring, in the step's method file and in the implementation plan rather than
left to be discovered.

`landloss.io.readers.get_nz_building_outlines` reads the LINZ NZ Building
Outlines layer for an extent, with the CC BY 4.0 licence and the attribution it
obliges on the reader. `fig_insured_land.py` draws the busiest neighbourhood in
a run at 120 m across, one colour per property with the building outlines over
the top, which is how the buffer and the split between neighbours are checked by
eye.
