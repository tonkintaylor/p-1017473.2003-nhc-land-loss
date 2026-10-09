**Failure polygons from the slope elements (library, phase 3 of the face-based urban
slope plan).** `landloss.hazard.landslide.slope_polygons` builds the evacuated polygon of
each element segment, with its imminent and inundated zones, along fall-line rays from
every crest cell. The width behind the crest is set by rule and measured horizontally: a
free-face takes the active wedge on the retained friction angle (0.45 H on fill at 42
degrees), a fill bank `BETA_FILL_BANK_WIDTH_H`, and a cut or natural bank the T-44
headscarp band. A free-face with the MM6 flag takes the whole stack above it, up to the
first bench wider than the width behind the crest below it. The imminent band runs to a
`BETA_REPOSE_ANGLE_DEG` line from the toe, never narrower than the T-45 band. The
inundated ground follows the de Vilder reach angle relations, dry or fill flow slide, and
can be clipped by an optional barrier grid. Long elements are cut at
`BETA_SEGMENT_VOLUME_M3`. Shared ground goes to the nearer crest, unless the polygons
start in separate catchments that face apart or one is a stack over the other.
Retrogression links, from below to above, are recorded with `BETA_RETROGRESSION_P` for
step 9. Nothing reads the polygons yet, and the pilot has not been run.
