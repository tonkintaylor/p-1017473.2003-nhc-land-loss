"""Land as an insured asset: its extent, its landform and what it is worth.

The land itself is the asset NHC cover attaches to most directly, and the one
whose value has to be modelled rather than looked up. This subpackage holds
that modelling: :mod:`landloss.exposure.land.landform` splits the exposure
population into flat and sloping ground, and
:mod:`landloss.exposure.land.land_value` puts a modelled land value on every
address in the spine.

The address spine those both read is one level up, in
:mod:`landloss.exposure.addresses`, because retaining walls, culverts and
bridges hang
off the same properties.
"""
