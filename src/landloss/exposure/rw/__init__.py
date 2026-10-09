"""Retaining walls as an insured asset: where they are, how big, what type.

A wall is settled on replacement value up to its own sub-cap rather than on the
value of the land it holds up, so it is carried as its own asset with its own
geometry rather than as an attribute of the land.

No retaining wall dataset exists for the study area, so the population has to be
inferred (**L-04**). The candidate walls are exposure step 6's wall units
(:mod:`landloss.hazard.landslide.wall_units`;
:mod:`landloss.exposure.rw.lines` keeps the wall positions and step height they
share), the probability that each is a wall from
:mod:`landloss.exposure.rw.wall_probability`, and one exposure world's drawn
population from :mod:`landloss.exposure.rw.population`.
:mod:`landloss.exposure.rw.beta_population` holds the size classes every wall is
carried in. :mod:`landloss.exposure.rw.age` dates each property from its titles
and survey plan, :mod:`landloss.exposure.rw.wall_age` combines that with the QV
dwelling age into age bin shares, and :mod:`landloss.exposure.rw.wall_type`
draws each wall's age bin and type from them.
"""
