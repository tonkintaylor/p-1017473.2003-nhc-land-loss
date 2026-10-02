The site multiplier's scope is settled and recorded: the allowance for
construction access, earthworks required, and constructability and
reinstatement applies to the **wall construction subtotal alone** — the square
metre rate by the wall face area — and reaches no other line of the scope of
works, not inundation removal and not land reinstatement.

`nhc-costing-tool.md` records Chris Ewens describing the multipliers as going on
the Land SOW subtotal, which is the broader reading. The narrower scope is the
decision for this study. `landloss.loss.pricing` already implemented it; what
was missing was anything saying so, which left the code and the meeting record
silently disagreeing.

It also settles the grain. A markup on one wall's construction cannot be a
claim-level figure, so the three ratings belong beside `rw_size` and `rw_length`
on the retaining wall table rather than on the claim. The `vul` contract carries
none of them and `SiteRatings` has no default, so no wall can be priced until
they arrive — the same hard stop the dwelling count creates for `settle`
(**Q-10**).

They are not a lookup for this study. A real claim takes them from a table in
the duty geotechnical report, and NHC at scale from flyover or satellite
imagery; neither exists for a synthetic population, so they have to be inferred
as wall prevalence and height are. The inputs are already in `exposure` — slope
drives earthworks and constructability, and `landloss.exposure.land.driveways`
computes the building-to-road path construction access turns on.
