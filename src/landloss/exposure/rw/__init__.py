"""Retaining walls as an insured asset: where they are, how big, what condition.

A wall is settled on replacement value up to its own sub-cap rather than on the
value of the land it holds up, so it is carried as its own asset with its own
geometry rather than as an attribute of the land.

No retaining wall dataset exists for the study area, so the population has to be
inferred (**L-04**). The candidate wall lines come from
:mod:`landloss.exposure.rw.lines`, the probability that each line is a wall and
that the wall is in poor condition from
:mod:`landloss.exposure.rw.wall_probability`, and one exposure world's drawn
population from :mod:`landloss.exposure.rw.population`.
:mod:`landloss.exposure.rw.beta_population` holds the size and condition
classes every wall is carried in. :mod:`landloss.exposure.rw.age` dates each
property's walls, in four bins, from its titles and survey plan.
"""
