The loss module runs on real data. `src/scripts/landloss/loss/gen_loss.py`
runs step 0, `steps/s0_land_cover_cap/`, over the four tables vul hands
across at step 10 and writes the **land cover cap on each claim** to
`temp/loss/land-cover-cap-r<nnn>[-pilot].parquet`. On the pilot that is 4,388
claims, 1,835 of them with damaged ground, a total cap of $1.18 bn of which
$8.3 m is retaining wall undepreciated value. The module goes through
`scripts.landloss.pipeline.run_steps` rather than a single script, so a
settlement step joins it without the runner changing shape. It is not wired
into `gen_all.py`, which still ends at vul.

**It builds the cap, not a settlement, and that is the honest stopping point.**
A settlement is `min(repair cost, cap)` less the excess, and no repair cost
exists on either side: a wall's needs the three site ratings, of which only
earthworks can be derived (**Q-10**), and damaged land has no Land SOW behind
it. The cap is the half that can be built, and the half most of the study's
questions are about. Two gaps are printed by the run rather than left to be
discovered — culverts and bridges contribute nothing, because nothing prices a
crossing yet, and every wall is priced at the beta flat rate standing in for a
construction type nothing supplies.

`landloss.loss.claims` gains the aggregation onto `claim_id` that the Act needs,
which was item 5 of the module's Next list. `land_by_claim()` sums the damaged
areas of a claim's polygons, which are non-overlapping, and averages the market
rate **weighted by the damaged area it values**, so a claim's value equals
valuing each polygon separately and adding; with one polygon per claim today
both reduce to that polygon's own rate. A claim whose polygons disagree about
the dwelling count is refused rather than resolved. `damaged_walls()` keeps a
wall carrying any of the three flags, since a damaged wall is replaced rather
than repaired and any flag being true is one replacement.

**The damaged area needed a reading the contract does not supply.** `vul` sends
landslide damage as an area but liquefaction damage as a *state* with no area
at all. `damaged_area_m2()` reads a damaging state as damaging the polygon's
whole insured area, on the grounds that the Canterbury rates the state indexes
are per property, and combines the two causes with a **maximum rather than a
sum** so ground damaged both ways is valued once. Neither is confirmed; both
are recorded as questions in the module's `status.md` and in the step's method
document, and they set the land half of every liquefaction claim's cap.

One result is worth watching rather than filing: **the retaining wall sub-cap
bound on no claims at all.** The module's own validation list calls out a
sub-cap that never binds as doing no work, so this is either the population
being genuinely modest or the beta wall rate being too low to reach $57,500.
