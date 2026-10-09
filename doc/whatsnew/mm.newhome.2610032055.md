Renamed the slope-elements "MM6 flag" (`MM6_CUT_ANGLE_DEG`, `MM6_CUT_HEIGHT_M`,
the `mm6_cut` column) to `STACK_DOMINANT_ANGLE_DEG`, `STACK_DOMINANT_HEIGHT_M`
and `stack_dominant_cut`. The flag is a fixed geometric threshold on an
element's own angle and height, computed once from the DEM and ground map; it
never reads a realisation's seismic demand. The old name risked being mistaken
for a demand-conditioned (Modified Mercalli Intensity 6) input, which it is
not — only whether a stack-dominant polygon *triggers* depends on demand, not
its extent.
