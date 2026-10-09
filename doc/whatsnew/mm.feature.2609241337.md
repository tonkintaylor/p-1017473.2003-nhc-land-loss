The insured land extent no longer buffers off buildings that cannot be a home.
`drop_non_residential_buildings` in `landloss.exposure.land.extent` applies two tests
before anything is buffered, and a property left with no building then carries no insured
land, so a school site or a retail park leaves the portfolio of its own accord rather than
needing a rule of its own.

The first test is the name. The building outlines layer carries a `use` column that names
schools, hospitals, supermarkets, huts and shelters and says `Unknown` for every other
building — 3,209,472 of 3,236,141 outlines nationally. Everything named is dropped, rather
than a fixed list of known values, so a use LINZ adds to the layer later is excluded
without editing the filter. The cost of that choice is that it would empty the layer if
LINZ ever populated the column properly, so `gen_insured_land.py` prints the count and the
names of what it removed instead of removing it silently.

The second test is the size: a footprint over `MAX_DWELLING_FOOTPRINT_M2`, 500 m², is a
warehouse, a mall or an office block rather than a house. The pilot's outlines run to a
median of 120 m² and a 95th percentile of 290, so the threshold sits well clear of a large
house. It is measured on the outline as LINZ serves it, before anything is cut to a
property, because the same outline has to be ruled in or out consistently for every
property it touches — which does mean a terrace captured as one large polygon is judged
whole.

Neither test can say that a building *is* residential, only that it is not, so this is a
tidy-up rather than the residential filter the exposure population still needs. Nothing in
the address, property or building layers flags a dwelling: the addresses layer carries no
use field at all, and the property boundaries carry `title_type`, which is tenure rather
than use. Narrowing the population to residential properties means joining
`valuation_reference` on the property boundaries — populated on 90.8% of the pilot's
polygons — to a council rating information database for the property category under the
Rating Valuations Rules, which is step 1's Phase 3.

Over the Wellington pilot the two tests remove 322 of 10,256 outlines: 127 named (94
schools, 27 hospitals, 6 supermarkets) and 241 over 500 m², with 46 failing both. Against
the 4,388 claims and 225.7 ha the extent carried with neither filter, the name test costs
14 claims, 18.4 ha and 58 dwellings, and the size test a further 79 claims, 34.6 ha and 454
dwellings. The pilot now carries 172.7 ha over 4,295 claims and 7,926 dwellings.

The size test is the crude half and the 454 dwellings are the reason: an apartment block is
residential and has the footprint of a warehouse, so it goes with them and the flats inside
it lose their insured land. 665 of the 8,591 pilot dwellings now stand on a property
carrying no insured land, against 153 before either filter, and `describe_extent()` counts
them on every run rather than leaving them to be inferred from the difference. Exempting a
large outline that carries many address points is recorded in the step's implementation
plan as the way back.
