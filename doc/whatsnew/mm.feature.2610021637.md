**The three retaining wall datasets are compared property by property.** New scripts in
`src/scripts/landloss/exposure/rw/validations/` place the GNS SLIDE mapped walls, the NHC
NZMM retaining wall flag and the walls listed in the claim reports on the LINZ property
boundaries. They write aggregate tables, charts and hexagon maps to
`report/exposure/rw/rw-datasets/`, and the findings go in `rw_dataset_comparison.md`. The
NZMM flag reaches the map through QV's valuation number, written the way LINZ writes it by
the new `landloss.io.qv_rating_roll.linz_valuation_reference`. Over urban Wellington City,
GNS and NHC agree on 933 of the 17,156 properties either records a wall on (kappa 0.03).
