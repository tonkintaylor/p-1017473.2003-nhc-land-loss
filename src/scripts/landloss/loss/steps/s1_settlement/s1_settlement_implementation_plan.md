# Step 1 — Settlement: implementation plan

## Phase 1 — Settle on real data (complete)

- [x] Proxy the two site ratings nothing measures: driveway length for
      construction access, ground slope for constructability. Bands invented,
      spread checked against the pilot so all three classes are reachable.
- [x] Price a damaged wall's replacement at the beta flat rate with the site
      multiplier on top.
- [x] Take a damaged wall on the claim as reinstating the land it retained, so
      no land repair cost is added on top of it.
- [x] Where landslide ground has no damaged wall, invent one sized by area and
      volume, price it as a repair cost, and keep it out of the cap.
- [x] Carry the Canterbury liquefaction cost through the contract and gross it
      up for GST.
- [x] Settle a damaged crossing at its sub-cap by adding the limit to both
      sides.
- [x] Call `settle()` and cross-check the cap against step 0's.

## Phase 2 — Replace the placeholders

- [ ] Inflate the Canterbury costs from 2010/2011 to the study's dollars. They
      are compared against present-day land values today, which understates
      them by however much construction has risen. Needs an index nobody has
      supplied.
- [ ] Replace the beta flat wall rate with a mapping from size class and
      condition onto a construction type. The rates span a factor of 21, so this
      moves the answer more than every proxy here put together.
- [ ] Replace the rating proxies with the real thing, or confirm them. The duty
      geotechnical report supplies all three for a real claim (**Q-10**).
- [ ] Distinguish a claim with no driveway routed from one with a short
      driveway. Both rate easy today.
- [ ] Confirm the invented wall's geometry. The two-to-one aspect, the 2 m
      margin at each end and the 10 m minimum are all invented, and together
      they set how large the invented walls are -- the largest single lever on
      the landslide side of the repair cost. The damaged area still drives both
      the height, through the size class, and the length, which is one signal
      doing two jobs.

## Phase 3 — What the settlement still cannot see

- [ ] Enabling works and compliance, which the wall rates do not carry, so
      every wall repair cost is low by whatever they come to.
- [ ] **T-27**: whether the Canterbury land rates already include retaining wall
      damage. If they do, the 107 pilot claims carrying both a liquefaction
      state and a damaged wall are charged twice.
- [ ] A real price for culverts and bridges, in place of the sub-cap
      simplification. Untested either way: the pilot has none.

## Notes

- Step numbers run from 0 within the module and are unique across it, and a
  script carries its step's number. This is step 1 because step 0 runs first,
  not because it is the second script in a directory.
- The crossing path has **never executed on data**: the pilot's culvert and
  bridge tables are both empty. It is covered by reasoning, not by a run.
