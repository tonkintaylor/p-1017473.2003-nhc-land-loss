"""Exposure model: the assets, by location, extent and attributes.

Defines what is at risk — where each property is, how much insured land it
has, and the attributes that drive its vulnerability.

Split by the kind of insured asset, because each is valued and settled
differently: ``land`` (the insured land itself), ``rw`` (retaining walls,
settled on replacement value up to the sub-cap) and ``culverts_bridges``. The
address
spine in :mod:`landloss.exposure.addresses` stays at this level, because all
three hang off the same properties.
"""
