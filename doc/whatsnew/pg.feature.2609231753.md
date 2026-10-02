The Act's area cap is now applied. `landloss.loss.settlement.damaged_land_value_nzd`
values the **lesser of the damaged area and the cap**, so damage beyond it is
valued as though it stopped there, and `Settlement` carries both the land value
and `area_cap_bound`. The cap was a setting on `PolicySettings` that nothing
read, which meant a large landslide built an unbounded land cover cap —
precisely the claims the cap exists to limit.

Making it apply required the claim to change shape. `DamagedClaim` and
`land_cover_cap_nzd` now take **`damaged_area_m2` and
`land_rate_incl_gst_nzd_per_m2`** in place of a pre-multiplied
`market_value_incl_gst_nzd`, because the cap acts on the area and a
pre-multiplied value has already discarded it. This is also the shape `vul`
sends, which carries a `$/m2` market value and the damaged areas per land
polygon. The explainer's worked examples are unchanged by it: 60 m² at $750 is
the $45,000 they state.

`landloss.loss.pricing` gains the first line of the Land SOW, inundation
removal. `inundation_volume_m3` takes the inundated insured area and the mean
depth `vul` sends, and `classify_inundation_earthworks` turns that volume into
an easy, moderate or difficult rating that feeds straight into `SiteRatings`.
That makes earthworks the one of the three site ratings a land claim can answer
from its own geometry rather than having to be told.

**The volume bands are assumed and have not been confirmed by anyone at NHC.**
The repository records the distinction only qualitatively — two rates, "one for
volumes a shovel and a truck can clear, one for volumes needing an excavator"
(**L-28**) — and attaches no volume to either, nor did the costing tool demo.
The thresholds used are 20 m³, above which hiring a machine beats hand tools,
and 200 m³, above which a mini excavator gives way to a full-size machine and
truck cartage. Both were reasoned from plant capability rather than taken from a
source, adopted as a working assumption so the chain could run, and are the
first thing to replace when NHC give a figure (**Q-11**). They are not idle:
through the earthworks rating they set the markup on any retaining wall on the
same property. A claim with no inundation rates easy, which is an answer rather
than a gap.

**Clearing the spoil is not costed on its own.** The volume sets the earthworks
rating and buys nothing else, on the reading that the rating is already
expressing what the clearing costs. That is a simplification rather than a
finding (**L-33**), and it has a visible cost: the multiplier reaches wall
construction alone, so a claim with inundated ground and no retaining wall
attracts nothing for the clearing — real work priced at zero. If inundation
removal turns out to be its own line item it wants a rate per cubic metre and a
place in the repair cost, not just a nudge to a multiplier.
