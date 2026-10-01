**Land value now reflects accessibility to the main centres and to rail.** A
new step script, `s2_build_accessibility.py`, gives every address a
straight-line gravity accessibility to fifteen centres, from the Wellington CBD
down to local shopping streets, and its distance to the nearest LINZ Topo50
railway station. `s4_estimate_land_value.py` joins them on when they exist and
applies a second modifier: value scales with a power of accessibility, times a
premium that fades over about 400 m from a station, centred, clipped and
rescaled within each territorial authority and landform class, as the terrain
modifier is. Authority totals are unchanged by construction.

The centres, their weights and decay lengths are a new asset,
`land-value-centres.csv`, and `fig_town_centres.py` maps them over the
accessibility surface. The elasticity (0.5), rail premium (10 percent) and clip
band (0.6 to 1.6) are judgement rows in `land-value-factors.csv`, to be refitted
against the District Valuation Roll.

On the Wellington pilot without stations, suburb medians move by about -6 to +5
percent: Newtown and Hataitai up, Lyall Bay and Rongotai down. The step has not
yet been run with LINZ access, so the station term is untested on real data.
