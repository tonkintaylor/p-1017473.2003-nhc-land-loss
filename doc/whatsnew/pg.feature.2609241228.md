The dwelling count reaches the settlement. `landloss.loss.claims.dwelling_counts`
reads the count written by the module-level exposure step
`s3_dwellings_per_property` onto the claims being settled, returning it in the
order the caller's other arrays are in, ready to pass as `DamagedClaim`'s
`n_dwellings`. That closes **Q-07**, which was a hard stop: both land structure
sub-caps and the excess are multiplied by it, `settle` refuses a count below
one, and until the exposure step landed nothing produced one at all.

A claim with no row in the property table is **refused, not defaulted to one
dwelling**. Defaulting would halve the cap on a pair of flats and halve the
excess with it — one error raising a settlement and the other lowering it, so
nothing in the total would look wrong. A claim appearing twice in the table is
refused as ambiguous for the same reason. Every refusal names the claims it
found, up to five, so the failure points at the data rather than at the
arithmetic.

Two properties of the count are carried to the point of use, because neither is
visible in the number. **A dwelling is an address point**, not a self-contained
dwelling: LINZ gives a unit of a block its own address, which is what makes the
count work for flats, but it also gives one to a commercial tenancy and none to
a minor dwelling never separately addressed — so the count is a floor on a
block and an over-count on a mixed-use building. And **it scales three figures
at once**, two of which raise a settlement and one of which lowers it.

The column names are written out in `loss` rather than imported from
`exposure`, since the four top-level modules exchange data files rather than
symbols. A test holds the two sets of names to each other so they cannot drift
apart unnoticed.
