**The toy slope-elements figures now show why a cell was or was not seeded, and what a
free-face's evacuated extent would be without a wall.** Each case's first plan colours
the ground by material group (red soil-like to green stronger rock), draws 90%-index
contours, and marks every cell within 80% of its own threshold with the same
eligibility ratio the library's own free-face pass computes, hollow circles for cells
eligible by step height and crosses for cells eligible by slope, lassoed per element.
The second plan shows each element's shape, its evacuated/imminent/inundated zones, an
illustrative no-wall band (widened from the modelled extent, since removing a wall can
only grow the setback) and an illustrative wall centreline. `toy_slope_elements.md`
records the design. Fixed along the way: geopandas boundary plots reject matplotlib
dash-tuples (use a string linestyle), the no-wall band's scale factor was floored the
wrong way round, and the shared eligibility colorbar must be added after
`tight_layout`, not before.
