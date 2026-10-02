Added `landloss.io.readers.get_nz_land_cover` for the LCDB v6.0 land cover
polygons, served from Landcare Research's LRIS portal. LRIS is a third
Koordinates instance alongside LINZ and T+T's own, so it brings a new
`LRIS_DOMAIN` and a separate `LRIS_API_KEY`, which must be set in `.env` before
the layer can be read. The data is licensed CC BY 4.0 and requires attribution;
the terms are recorded in the reader's docstring.
