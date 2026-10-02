"""Loss: damage turned into what NHC would actually pay.

The last of the four modules, and the only one where money and policy wording
enter. That is deliberate: keeping the Act in one place is what makes the policy
settings a parameter of a run rather than something threaded through the model,
so comparing two sets of settings re-runs `loss` alone.

:mod:`landloss.loss.policy` holds a scenario's settings as a value, defaulting
to the Act as it stands. :mod:`landloss.loss.settlement` applies them, building
the land cover cap and settling each claim against it.

The module also owns more costing than its name suggests. `vul` emits a damage
verdict for retaining walls, culverts and bridges rather than a price, so every
dollar attached to a land structure is worked out here, in
:mod:`landloss.loss.pricing`.

`vul` hands over four tables -- land, retaining walls, culverts and bridges --
each carrying ``claim_id`` and coordinates, so this module aggregates onto a key
it is given rather than minting one. Land arrives as an area and a market rate
per non-overlapping polygon; structures arrive as a damage flag per cause, and
since a damaged structure is replaced rather than repaired, any flag being true
means one replacement. The full contract is
``.agents/plans/asset-pricing-approach.md`` section 1, which also lists what it
does not carry. See ``.agents/context/nhi-act-land-cover-explainer.md`` for the
settlement mechanics the arithmetic follows.
"""
