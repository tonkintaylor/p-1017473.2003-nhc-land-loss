The `loss` module now settles a claim. `landloss.loss.settlement` implements the
Natural Hazards Insurance Act's own arithmetic: a **land cover cap** built from
the assessed market value of the damaged insured land plus, for each kind of
land structure, the *lesser* of its undepreciated value and the per-dwelling
sub-cap; then a settlement of the lesser of that cap and the repair cost, less
the excess. `settle()` takes a `DamagedClaim` and returns a `Settlement`
carrying the cap, the excess, each structure's contribution and whether the cap
bound, because those are what the study's questions are about and none of them
can be recovered from the total afterwards. Scalars settle one claim, arrays
settle a portfolio.

This replaces the "value or repair, not both" election the team's working notes
describe. That reading is looser than the Act, which never offers a choice — it
builds the cap *from* the value and pays the lesser. The two give different
answers whenever repair cost falls between market value and the cap.

Two consequences are carried in the code rather than left to a caller to
remember. A sub-cap limits a structure's *contribution to the cap*, not the
settlement, so a wall whose undepreciated value is below the sub-cap contributes
that value and the sub-cap never binds; and repair cost and undepreciated value
are different numbers with different scopes, so both are required. Every amount
crossing the boundary is GST-inclusive and named `_incl_gst_` to say so, since
that is the basis the Act compares on.

`landloss.loss.policy` holds the settings as a frozen `PolicySettings` rather
than as module constants, so a scenario is a value that can be passed around and
two can run in the same process. It defaults to the Act as it stands and carries
`total_cap_nzd`, which has no equivalent in the present Act and is the setting
NHC is considering, alongside `include_imminent_damage` for pricing the removal
of the imminent damage provision.

The arithmetic is tested against the three worked examples in
`.agents/context/nhi-act-land-cover-explainer.md`, which are the only fully
specified settlements the study has. `.agents/plans/asset-pricing-approach.md`
sets out how each asset is priced against each hazard to produce the repair
costs and undepreciated values this module consumes.
