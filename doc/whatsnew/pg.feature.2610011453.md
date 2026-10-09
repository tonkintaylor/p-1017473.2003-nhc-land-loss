**The land rate per square metre is now modelled directly, per property.**
Each address used to be valued as if it stood on its authority's assumed lot
(450 m2 in Wellington City), and its rate per square metre was that value over
the assumption. `s4_estimate_land_value.py` now measures the LINZ property each
address stands on and models its rate: location factors times a section size
factor, `(area per rating unit / assumed lot)` to the power
`section_area_elasticity - 1` (0.5, with a 150 m2 floor in
`section_area_min_m2`; both new judgement rows in `land-value-factors.csv`). A
site's land value is its rate times its area, and each authority is calibrated
so that total site value over total rating units is its published average,
which is how the published figure is built. A unit-titled block is rated per
unit, so its land is the sum of its units' rather than one oversized garden; a
freehold title is sized on its whole area however many addresses stand on it.

The outputs gain `site_land_value_nzd` (the whole property),
`rating_units_on_property`, `addresses_on_property` and `lot_size_m2`;
`land_value_nzd` is the site value per rating unit. An address in no property
keeps the assumed lot. Against 11 hand-checked land values the median rate moves
from 0.69 to 0.89 of actual. The first full run downloads the LINZ property
boundaries, which step s5 already needed.
