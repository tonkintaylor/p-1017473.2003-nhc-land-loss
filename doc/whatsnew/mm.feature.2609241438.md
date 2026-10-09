`landloss.io.kaikoura` reads GNS's Kaikōura earthquake landslide inventory v3.0
straight off T: — `get_kaikoura_landslide_source_areas` for the 31,623 source
area polygons and `get_kaikoura_landslide_debris_trails` for the 26,559 debris
trail polygons, both in NZTM. This is the calibration dataset the
estimating-eq-landslide-extent-wellington plan fits the model's size
distribution and reach-angle relationship to, and the same inventory
`landloss.hazard.landslide.geometry`'s `GAMMA` already comes from.

The delivery lives on another T+T project's own `SourceMaterial` folder rather
than this one's, so it is read the same way `landloss.io.nlm` reads the
National Liquefaction Model's release tree: an arbitrary absolute T: path,
through `tdrive_sync.get_cached`. Its own quirk is depth rather than size —
the path is over 200 characters before the file name even starts, so the
constant it is built from carries a `\\?\` prefix, and `copy_to_local`
defaults to False because mirroring a path that deep into the local cache
overflows Windows' path length limit on its own account.

Both readers rename the shapefiles' DBF-truncated columns (`Method`,
`Vol_p1SD`, …) to the names the delivery's companion CSV attribute tables give
them, snake_cased. Those CSVs were checked against the shapefiles and carry no
rows or values the shapefiles do not already have, so they are not read
separately.

The data is GNS Science's, Creative Commons Attribution 4.0 licensed — see the
module docstring for the citation and attribution wording to carry into any
figure or table built from it.
