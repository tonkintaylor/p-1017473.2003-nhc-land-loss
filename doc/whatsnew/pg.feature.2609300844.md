**The land excess is back to \$500 per dwelling, capped at \$5,000** — the
explainer's rule, which all three of its worked examples settle on. The 10% of
what is payable, once per claim, that Virginie Lacrosse described is still
runnable as `PolicySettings(excess_per_dwelling_nzd=None)`, since the two still
contradict each other (Q-12). A claim with nothing payable is charged nothing
under either.

Across the pilot the settlement rises from \$13.02 m to \$13.56 m, but fewer
claims are paid anything — 2,031 rather than 2,283 — because the count zeroed by
the excess goes back from 636 to 888. Single-dwelling claims pay \$500 however
large they are; the largest multi-dwelling properties pay the \$5,000 ceiling
however small.

The walkthrough's Calculation and Repair cost tabs, the viewer page and its CSV
check all follow: the excess settings are now "per dwelling" and "ceiling", and
both Python mirrors agree with the module to \$0.00.

**A timber pole wall's pile size is now set by its height**, rather than drawn
from the wall's id: below 1 m is 175 mm SED, 1 to 2 m is 250 mm, 2 to 3 m is
300 mm, and 3 m and above is 350 mm (`TIMBER_POLE_HEIGHT_BANDS_M`). The 30%
concrete share is unchanged and still chosen by id. The bands are assumed.

Because each size class is priced at one set height, each lands on one pile:
small (0.75 m) on \$643.19/m², medium (1.75 m) on \$744.69/m² and large (2.75 m)
on \$798.80/m². The 350 mm rate is not reached until heights are drawn rather
than set (I-14). A wall invented for a landslide takes the timber rate for its
height too, instead of the four-rate average. That average,
`BETA_WALL_RATE_EXCL_GST_NZD_PER_M2`, is gone, and the beta repair cost and UDV
functions now need a rate passed in. On its own this moves the pilot settlement
by about −\$10,000.
