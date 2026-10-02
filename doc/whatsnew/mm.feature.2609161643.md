Added `landloss.io.readers.get_nz_addresses` for the LINZ NZ Addresses layer, and
`landloss.io.area_of_interest.SMALL_WLG_PILOT` defining the Wellington pilot
extent. Clipped extents are now cached on disk, so re-requesting the same extent
of the same layer version does not re-read or re-clip the source.
