**Wellington Station is added to the railway stations the land value
accessibility term reads.** The LINZ Topo50 station layer carries every
suburban station in the study area but not the terminus, so Thorndon and
Pipitea were measured to Crofton Downs, 2.6 to 2.9 km away, and the CBD took
almost no rail premium. A new hand-maintained asset,
`land-value-extra-stations.csv`, is added to the fetched layer by
`landloss.exposure.land.accessibility.add_stations`, which drops any added
station within 250 m of one LINZ already carries, so the copy falls away once
LINZ adds it. With it, Pipitea is 47 m and Thorndon about 330 m from a station.
