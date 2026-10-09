# Plan: estimating land values across the study area

This plan does not live here. Under the steps-folder convention (see the
`adding-steps-scripts` skill), a plan belonging to a specific step lives beside
that step's scripts, so that the plan and the code it describes cannot drift
apart or be found separately.

The land value model is step `s2_land_value` of the exposure module. Its plan is:

    src/scripts/landloss/exposure/land/steps/s2_land_value/s2_land_value_implementation_plan.md

and the description of what is currently implemented is:

    src/scripts/landloss/exposure/land/steps/s2_land_value/s2_land_value_method.md

In short: each address takes its territorial authority's published QV average
residential land value, indexed to a common 1 September 2025 basis, scaled by a
landform multiplier, with a per-authority normalising constant that forces the
modelled mean back onto the published average. That makes the authority totals
correct by construction against free, citable data, so judgement only ever moves
value between properties rather than changing the total. Later phases add DEM
terrain, a gravity decay on distance to centres, sea view and winter sun, and a
regression refit against council District Valuation Roll data once register task
T-20 closes.
