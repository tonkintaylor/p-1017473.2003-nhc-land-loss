The loss module settles. Step 1, `steps/s1_settlement/`, builds the repair cost
that step 0's cap had nothing to be compared against, and calls `settle()`. On
the pilot that is **$13.7 m paid over 2,031 claims** against a $1.35 bn cap: the
cap almost never binds, the excess takes everything on 892 claims, and the
constraint that decides a settlement is the repair cost.

**Where the repair cost comes from**, each line a stated assumption:

| Line | Pilot total | Basis |
| --- | --- | --- |
| Damaged walls replaced | $12.6 m | beta rate × face area × site multiplier × spec uplift |
| New walls for landslide ground | $1.2 m | a wall invented where ground went and none stood |
| Spoil cleared | $0.5 m | the tool's own $150/m³ line item |
| Consent, design, engineering, H&S, PM, survey | $3.6 m | the tool's own fee table, $5,100 per claim |
| Canterbury liquefaction | $2.9 m | settled costs per damage state |

**A replacement now costs more than the asset for two reasons, not one.** The
site multiplier is what a site costs to work on; the new
`PolicySettings.replacement_spec_uplift`, 20%, is that a failed wall is rebuilt
to a more substantial standard than the one that failed, which the square-metre
rates carry no allowance for (**L-34**). Undepreciated value carries neither, so
`UDV = face area × rate × GST` exactly, and everything that makes a repair
dearer lands only on the repair side of `min(repair, cap)`.

**Walls are no longer all priced at one rate.** 30% are priced as Reinforced
Concrete and the rest take one of the four timber pole rates, drawn evenly, so
the timber mean stays exactly where the old flat rate was and the population
gains a tail at each end. Which wall gets which is settled by **hashing its id**
rather than a seeded draw, so the same wall is the same construction on any
machine, in any order, however many walls there are. The point is the spread:
one rate gave a population with no wall dear enough to approach a sub-cap, which
answered "do the sub-caps bind" by averaging rather than by evidence.

**Three rates and one fee table now come from the costing tool rather than from
assumption.** The tool's `lists` sheet gave the spoil removal rate, "Clear site:
Load, cart and tip material" at $150/m³, and the six professional fees. Those
fees also settle an open question: the square-metre rates do **not** carry
design, consent or survey — they are separate line items, so a wall priced on
the rate alone was missing all of them. Fees are charged once per claim that
involves a wall, before the site multiplier so a difficult site costs more to
design as well as to build, and never in the undepreciated value.

**The contract gains `Liq_LD_cost_excl_gst_nzd`.** The Canterbury settled cost
was computed by vul step 2 and discarded at the boundary, so `loss` had a state
but no price.

**A damaged wall reinstates a metre of land for every metre of its length.**
Ground beyond that is charged for, by inventing a wall for the uncovered area —
one rule that covers both a claim with a wall and a claim without. The invented
wall follows the width of the failure, twice as wide as deep, plus a margin at
each end and never under 5 m.

Two results read carefully rather than at face value. **`capped` is an artefact
on a claim with no damaged land** — the cap is then the wall's value and the
repair is that value plus the allowances, so it caps by construction; of 1,095
capped pilot claims only 11 have damaged ground, and the run prints the split.
And **the Canterbury costs are 2010/2011 dollars, grossed up but not inflated**,
compared against land values and wall rates in today's dollars, because nothing
in the repository supplies an index.

`loss/validations/gen_calc_walkthrough.py` writes a 20-claim spreadsheet of the
whole calculation for review with people who will not read the code, choosing
claims to put one of every interesting case in front of a reader rather than
sampling at random.
