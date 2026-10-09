The land excess was wrong in two ways at once. It is **10% of what would
otherwise be paid, per claim**, floored at $500 and capped at $5,000 --
confirmed by Virginie Lacrosse on 2026-09-25. The module charged a flat $500
**per dwelling**, so a property with twenty-nine dwellings paid the $5,000
ceiling against $4,600 of liquefaction damage and was settled at nothing. It
now pays $500 and is paid $4,100.

Across the pilot the excess falls from $3.43 m to $2.86 m, and **252 more
claims are paid anything at all** -- the count zeroed by the excess drops from
888 to 636. The settlement total falls even so, from $13.68 m to $13.13 m,
because the claims that now clear the floor are small ones and the large ones
lose the per-dwelling discount they never should have had.

**This contradicts the explainer, which is why both rules are still runnable.**
`.agents/context/nhi-act-land-cover-explainer.md` states a flat "$500 per
dwelling, capped at $5,000" and works all three of its examples that way; the
two disagree by $4,500 on its own first example. `PolicySettings` defaults to
the rate, and `PolicySettings(excess_per_dwelling_nzd=500.0)` reproduces the
explainer. The three worked examples are tested against the explainer's rule,
because that is the document they come from, and the default is tested beside
them. Somebody has to settle it (**Q-12**) before a number goes to NHC.

One thing the correction did not decide: the 10% is taken on
``min(repair cost, cap)`` rather than on the repair cost, so a claim is never
charged an excess on cost NHC is not bearing. Both readings give the same
answer on every example given; they diverge only where the cap binds.
