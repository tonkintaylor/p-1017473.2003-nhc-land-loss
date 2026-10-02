The insured land extent now includes the driveway, which NHC's definition has
always covered and the extent did not. `landloss.exposure.land.driveways`
generates one as the straight line from each building to the nearest point on
the nearest road, buffered to a corridor; roads come from the LINZ NZ Addresses:
Roads layer through the new `get_nz_address_roads`, chosen over the topographic
centrelines because it is the same addressing dataset the address spine uses.
This resolves **I-10**, which proposed mapping driveways by remote sensing.

Driveways are unioned in **before** the ground is partitioned between
neighbours. Merging them into a finished extent instead left 13.2 ha of the
pilot box, 4.3% of the summed area, belonging to two properties at once — which
would have been double counted by anything summing damaged area per property.

Over the pilot box 6,726 of 6,735 attached buildings reach a road, the median
driveway is 12.7 m, and the insured land is 290.1 ha with no overlap.
