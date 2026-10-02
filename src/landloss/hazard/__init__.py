"""Hazard model: the shaking, liquefaction and landslide extents.

Defines the demand side of the problem — what the ground does in the
modelled event, independent of what is built on it.

Split by hazard into ``liquefaction``, ``landslide`` and ``shaking``, each with
its own inputs and its own intensity measure. Terrain that more than one of them
reads, such as the valley cross-sections in
:mod:`landloss.hazard.cross_sections`, stays at this level.
"""
