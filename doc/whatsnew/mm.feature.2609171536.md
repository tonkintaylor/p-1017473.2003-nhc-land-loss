Added the first content of the exposure model. `landloss.exposure.addresses`
builds the address spine the study runs over, filtering the LINZ NZ Addresses
layer to current land addresses, and `landloss.exposure.land.landform` tags each one
flat or hill against the National Liquefaction Model flatland polygons.
`landloss.exposure.land.land_value` puts a modelled land value on every address: each
territorial authority's published QV average residential land value, indexed onto
a common valuation date, is spread across its addresses in proportion to a
landform multiplier, with a normalising constant that pulls the modelled mean
back onto the published average. The judgement in the multipliers therefore moves
value between properties and never changes what an authority is worth in total.
The published anchors and the model parameters are packaged as editable CSV
assets under `landloss.io.assets` so that a valuer can check them without reading
Python.

The scripts that run it are the first to follow a new convention: every step
under `src/scripts/landloss/<module>/steps/` now lives in its own numbered folder
carrying an implementation plan written in phases and a method file describing
the methodology as currently implemented, with the rule that changing a step's
scripts updates its method file in the same change. The convention is written up
as the `adding-steps-scripts` skill.
