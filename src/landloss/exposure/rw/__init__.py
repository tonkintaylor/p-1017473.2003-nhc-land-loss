"""Retaining walls as an insured asset: where they are, how big, what condition.

A wall is settled on replacement value up to its own sub-cap rather than on the
value of the land it holds up, so it is carried as its own asset with its own
geometry rather than as an attribute of the land.

No retaining wall dataset exists for the study area, so the population has to be
inferred (**L-04**). :mod:`landloss.exposure.rw.beta_population` is the beta
stand-in for that inference, and :mod:`landloss.exposure.rw.wall_probability`
turns it and the mapped evidence into a probability per property and draws a
realisation from that.
"""
