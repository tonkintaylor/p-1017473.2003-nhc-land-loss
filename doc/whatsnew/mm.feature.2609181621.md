Added the `CHRISTCHURCH` study extent to `landloss.io.area_of_interest`, covering
the city and the Canterbury plains around it, and `LandformArea` to
`landloss.exposure.land.landform` — a named extent that is a rectangle cut down
to either the flat or the sloping land inside it, as the National Liquefaction
Model flatland layer draws them. `CHCH_FLAT_ONLY` and `CHCH_SLOPE_ONLY` are the
two halves of the Christchurch extent. A `LandformArea` offers `geometry()`,
`to_geoseries()` and `clip()`, so it can be passed to a reader or used to mask a
frame in the same way as an `AreaOfInterest`; resolving one reads the flatland
layer, so it needs `TNT_KOORDINATES_API_KEY`.

`gen_observed_damage_db.py` now masks the Canterbury loss records to
`CHCH_FLAT_ONLY` and no longer joins the modelled LSN grid. What is in
`observed_damage_db.parquet` is therefore decided by a named extent rather than
by how far the LSN grid reached, and the database states limitation L-09 — the
Canterbury sequence is flat land liquefaction evidence — instead of asserting it
in prose. The `lsn_p50` column is gone.

Observed damage is now carried as one of the six land damage states the
observation layers code in `dissolve_col` — 1 none observed, 2 minor, 3 moderate,
4 major, 5 severe, 6 very severe — in a new `observed_land_damage_state` column,
rather than folded into five bands with `Major +` at the top.
`observed_land_damage_category` holds the state's label, so its vocabulary
changes accordingly. Where an observation names a mechanism rather than a grade,
`OBS_HAZ_MAP` reads `Lateral Spreading` as state 5 and `Liquefaction` and
`Liquefaction Ejecta` as state 3. A property covered only by ungraded polygons
keeps a null state and a category of `Unknown`, which is still distinct from a
property no polygon covered.

`fig_land_damage_v_lsn.py` is replaced by `fig_land_damage_maps.py`, which draws
three map panels across the Christchurch extent — one per event — with every
property at its own location, coloured by its land damage state on a green to red
ramp, over the shared report basemap. Ungraded and unsurveyed properties are drawn
in grey, so the figure also shows how complete the observation coverage is. It
writes `land-damage-states-by-event.png` to `report/vul/liquefaction/land/fig/`
and needs network access for the basemap.
