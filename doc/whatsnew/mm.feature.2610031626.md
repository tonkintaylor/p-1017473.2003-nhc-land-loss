**Two more toy cases prove the slope elements library against gully geometry it had
not been tested on.** Case 14 bends a ridge so its two gully heads face 60° apart
(case 6's faced 180° apart), giving two elements in disjoint catchments whose polygons
overlap only through `WITHIN_WIDTH`, not `SEPARATE_CATCHMENTS`, confirming
`BETA_FACING_APART_DEG` does not misfire below its 90° threshold. Case 15 is an
undulating-hills negative control: genuinely wavy terrain with no element anywhere.
Both are regression tests in `tests/landloss/hazard/landslide/`, and
`toy_slope_elements.md` records the two false-start constructions (angle-scaled trough
collapse; fixed-width collapse with no delay before erosion) that case 14 needed before
it worked. All 19 toy grids now pass noise-free, at noise seed 7, and over 30 noise
seeds (570 of 570).
