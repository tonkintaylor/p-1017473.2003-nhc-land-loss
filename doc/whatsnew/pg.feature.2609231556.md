`loss` now prices a retaining wall's repair. `landloss.loss.pricing` carries the
29 square-metre rates from the NHC costing tool's `lists` sheet and the site
multiplier applied on top, so a wall's repair cost is the tool's own
arithmetic: `m2 rate x face area x (1 + site multiplier)`, grossed up to the
GST-inclusive basis `settle` compares on. Face area is retained height by
length, which is what the wall population already emits.

The multiplier settles **Q-04**. The tool rates three things — construction
access, earthworks required, and constructability and reinstatement — each
easy, moderate or difficult, and enumerates all 27 combinations. Every row is
the sum of a per-rating markup of 0%, 5% and 10%, so `SiteRatings` computes the
figure and the test suite checks it against all 27 rows rather than the module
storing the table. An all-difficult site attracts 30%, which is where the
tool's individual line items cap out — so Chris Ewens's revised "closer to 0, 5
and 10" was right and the earlier 15% each was not.

It also settles **Q-03**. The enabling works bands quoted at the demo as
"nothing for easy, about 15 for moderate, about 30 for difficult" are the
`EEE`, `MMM` and `DDD` rows of that same table, so they are multipliers rather
than dollar amounts in thousands.

Nothing yet says which of the 29 construction types a modelled wall is — the
population emits a size class and an initial condition instead — so every wall
is priced at `BETA_WALL_RATE_EXCL_GST_NZD_PER_M2`, the average of the four
non-driven timber pole rates, $766.6375 per m² excluding GST. The `beta` prefix
means what it means in `landloss.exposure.rw.beta_population`: it goes when the
mapping is settled, and no figure out of it is evidence about Wellington. Size
still moves the cost, but through face area rather than through the rate, and
initial condition does not move it at all — condition decides whether a wall
fails, which is `vul`'s question, not what replacing it costs.

Two things are absent because a figure has not arrived. **Undepreciated value**
is not produced: it comes from its own sheet of set fees and is the cost to
build the same wall new without the items the square-metre rates carry, so it
cannot be derived from them, and until it lands `settle` has no
`retaining_wall_udv_incl_gst_nzd` to take. **Enabling works and the compliance
items** are excluded, the rates carrying no allowance for the first and the
second being unquantified (**Q-05**).
