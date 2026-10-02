Readers for two National Liquefaction Model layers: `get_nlm_geomorphology`,
whose `l3_yp` material classes now supply the geology factor of the slope
failure susceptibility scheme, and `get_gwd_median_depth`, whose median
groundwater depth supplies the groundwater factor. The depth grid is modelled
over flat land only, so hill country is assumed to sit at 4 m and therefore to
drain. Reading the two factors rather than holding them constant is what makes
the lowest susceptibility zone reachable: the rebuilt zonation now matches the
published Greater Wellington layer closely across the bottom two zones, where
before it sat a zone high everywhere.
