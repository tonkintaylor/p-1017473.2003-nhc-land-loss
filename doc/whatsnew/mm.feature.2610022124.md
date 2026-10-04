**Slope elements: free-faces and banks grown from seeds on the 1 m DEM (library, phase 1
of the face-based urban slope plan).** `landloss.hazard.landslide.slope_elements` finds
the pieces of ground between a crest and a toe that the wall candidates and the urban
failure polygons will be built from. Each cell's ground group and estimated height band
set its step test angle (`STEP_ANGLE_DEG`, the 24 numbers over eight `HEIGHT_BANDS_M`);
seeds are ranked by the 3 m slope exceedance and grown by watershed in two passes, the
free-faces first and then the banks, stopped by `BETA_FREE_FACE_GROW_TOL_DEG` and
`BETA_GROW_ANGLE_DEG`. Each element carries its height, overall angle, height band,
free-face or bank, the MM6 and Hancox-Brabhaharan cut flags, majority ground, stack links
with bench widths and a D8 catchment label. `landloss.hazard.landslide.synthetic_terrain`
builds the 15 stage D1 toy cases, with optional LiDAR-like noise, and every case is a
regression test. Nothing reads the elements yet; the pilot has not been run.
