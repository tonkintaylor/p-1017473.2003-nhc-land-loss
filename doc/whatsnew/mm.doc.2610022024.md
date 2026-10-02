**A claim report now raises the wall probabilities on its property rather than setting a
minimum count** (decision recorded in the retaining wall status). On a claimed property
whose report lists n walls, each candidate line's `p_wall` is to be conditioned on at least
n of the property's lines being walls. That raises every line and never lowers one. It
replaces `apply_count_bounds`, and a seeded share of claims is held out for the
cross-validation.
