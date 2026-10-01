**Land values now reflect a view of the sea, closeness to it, and winter sun.** A new step script,
`s3_build_amenity.py`, casts rays from every address over the LINZ DEM -- 72
bearings, out to 5 km, from 5 m above the ground -- and records the share of
directions in which the sea is visible, sea being DEM cells outside the study
area's land and at or near sea level, and the distance to the nearest sea along
any of them. `s4_estimate_land_value.py` joins it on
when present and applies a third within-cohort location modifier, `(1 +
sea_view_premium * share) * (1 + coast_premium * exp(-distance / 250 m))`
(premiums 1.0 and 0.25), centred, clipped to 0.8-2.0 and
rescaled within each territorial authority and landform class, so authority
totals are unchanged. The view is measured over the bare-earth DEM, so
buildings and trees do not block it. The settings and the premium are new
judgement rows in `land-value-factors.csv`. The same rays give each address its horizon from garden height,
and the sun's June-July path is run against it: `winter_sun_share` is the share
of the time the sun is up that it clears the terrain, and enters the modifier as
`1 + winter_sun_premium * share` (premium 0.3).
