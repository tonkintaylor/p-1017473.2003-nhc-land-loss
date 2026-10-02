`landloss.io.nlm.get_nlm_flatland` reads the National Liquefaction Model's own
flatland polygons straight off its release tree on T:, smoothed to a 200 m
spatial length. This is a separate delivery from the flatland cut this study
already reads through `landloss.exposure.land.landform.get_flatland`, which is
an earlier version mirrored to Koordinates.

The flatland product is cut and versioned on its own schedule, unrelated to the
`core` release tree's, so it is pinned by a new constant,
`FLATLAND_NLM_VERSION` (currently `V0p5`), rather than reusing
`CORE_NLM_VERSION`.
