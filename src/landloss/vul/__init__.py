"""Vulnerability calculations for each asset against each hazard.

Maps a hazard intensity at an asset onto a damage ratio, per cause of land
damage.

This is the only place the hazard and exposure models meet, so it is split on
both axes: hazard first (``liquefaction``, ``landslide``, ``shaking``), then the
exposure asset within it (``land``, ``rw``, ``culverts_bridges``). A damage
ratio is
specific to one pair, because liquefaction settlement under insured land and
shaking of a retaining wall are unrelated relationships.
"""
