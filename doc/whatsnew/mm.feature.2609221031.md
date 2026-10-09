The landslide hazard module now has a runnable first cut, taking the
extend-ESNZ route the module's `status.md` describes.
`src/scripts/landloss/hazard/landslide/steps/s1_landslide_realisation/s1_simulate_landslides.py`
turns the supplied 32 m probability grid into individual landslides: it samples
each cell independently against its own probability, draws a source area from a
bounded power law between 3 m² and 3000 m², places it as an area-exact circle at
the cell centre, drops the smaller of any overlapping pair, and moves each
failure downhill by a distance ramping from 1 m to 40 m with the slope. The
output is one GeoParquet holding two polygons per landslide — the source as
`evacuated land` and the displaced footprint as `inundated land` — kept apart
because NHC settles loss of support and runout differently.
`fig_landslide_realisation.py` beside it draws where the landslides are, one
neighbourhood close up with a runout arrow per failure, the size distribution and
the displacement assumption. Both assume rather than measure: the size exponent,
the displacement ramp and the circular shape are placeholders, and independent
cell sampling omits the clustering a real event has. The step's method document
and its phased plan say so, and say what replaces each.

Two pieces of it are library code rather than script, because they outlive the
model. `landloss.common.utils.terrain` gains `downhill_azimuth_degrees`, the
direction of steepest descent as a compass bearing, sharing one Horn gradient
with the existing `slope_degrees` so the steepness and the bearing cannot drift
apart, plus `azimuth_offsets` and `cell_size`. The bearing is read against the
raster's own coordinates rather than an assumed north-up convention, so a grid
stored either way up describes the same hillside. The new
`landloss.io.source_material` reads rasters supplied to the project on the T:
drive through `tdrive_sync`, resolving nodata to NaN, clipping to an extent in
the raster's own projection and reprojecting into the caller's;
`get_eil_landslide_probability` is the landslide grid's reader, with its path in
`EIL_PROBABILITY_SOURCE_PATH` in `landloss.domain.constants`.
