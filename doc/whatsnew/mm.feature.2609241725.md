A new landslide hazard step, `s3_multiscale_slope`, builds a DEM and a Horn's
method slope raster at 10, 30 and 100 m. Only the 10 m DEM is fetched from LINZ;
the 30 and 100 m DEMs are block means of it, from the new
`landloss.common.utils.terrain.block_mean`, because LINZ's loader resamples
bilinearly and would sample rather than average the ground under a coarse cell.
The grids nest, and the run reports the share of the extent in Kingsbury's
slope classes at each cell size.
