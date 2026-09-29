# Step 0 — Land cover cap: method

- The step writes the **land cover cap on each claim**, per realisation, from
  the four tables vul hands over at step 10. It is run by
  `s0_gen_land_cover_cap.py` and adds no modelling of its own: the arithmetic is
  `landloss.loss.settlement` and `landloss.loss.pricing`, and the aggregation
  onto `claim_id` is `landloss.loss.claims`.
- The cap is the Act's own sum:

      land cover cap = market value of the damaged insured land
                     + min(retaining wall undepreciated value, its sub-cap)
                     + min(bridge and culvert undepreciated value, its sub-cap)

- **It stops short of a settlement.** A settlement is `min(repair cost, cap)`
  less the excess, and no repair cost exists yet: a wall's needs the three site
  ratings, of which only earthworks can be derived (**Q-10**), and damaged land
  has no Land SOW behind it. The cap is the half that can be built.
- It reads all four contract tables through vul step 10's own path function,
  `loss_input_path()`, so the file names live in one place.

## Bringing polygons and walls onto the claim

- The Act settles a claim, so `landloss.loss.claims.land_by_claim()` brings the
  land polygons onto `claim_id` first. Polygons are non-overlapping, so their
  damaged areas **add**. The market rate does not add: it is averaged **weighted
  by the damaged area it values**, so the claim's value equals valuing each
  polygon separately and summing. There is one polygon per claim today, in which
  case both reduce to that polygon's own rate.
- A claim whose polygons disagree about the dwelling count is refused rather
  than resolved, because nothing here can say which count is right.
- `damaged_walls()` keeps a wall carrying **any** of the three damage flags.
  A damaged wall is replaced rather than repaired, so any flag being true is one
  replacement, not one per flag. An undamaged wall is dropped rather than priced
  at zero.
- Walls are summed over the claim before the sub-cap applies, because the
  sub-cap limits a claim's walls together rather than each wall on its own.

## The damaged area, which the two causes measure differently

- Landslide damage arrives as an area, `land_slide_total_insured_land_area`,
  already unioned over the evacuated and inundated footprints by vul step 3.
- Liquefaction damage arrives as a **state** sampled at the property, with no
  area at all. This step reads a damaging state as damaging the polygon's
  **whole insured area**, on the grounds that the Canterbury cost rates the
  state indexes are per property. State 1 is "None" and is not damage; a missing
  state is not damage either.
- The two are combined with a **maximum, not a sum**. Ground both liquefied and
  buried is one piece of damaged ground, and adding would value some of it
  twice. The maximum is exact where one cause reaches all the ground the other
  did, and conservative otherwise.
- **Neither the reading nor the combination is confirmed.** They are the first
  thing to revisit if the land numbers look wrong.

## What the cap currently cannot count

- **Culverts and bridges contribute nothing.** Nothing prices a crossing yet, so
  a claim whose only damaged structure is a culvert caps on its land alone. The
  run prints how many there were so the gap is visible in the output.
- **Every wall is priced at the beta wall rate**, because nothing maps a
  modelled wall onto a construction type: 30% of walls, chosen by id, as
  reinforced concrete and the rest as timber pole, with the pile size set by
  height (`TIMBER_POLE_HEIGHT_BANDS_M`) — small walls on 175 mm SED, medium on
  250 mm, large on 300 mm. The rates span a factor of 21, so this is the
  largest single assumption in the wall half of the cap.
- Wall height comes from the size class, not from the wall: 0.75 m, 1.75 m and
  2.75 m for small, medium and large. Face area is that height by `rw_length`.

## Output

- One row per claim, written to
  `temp/loss/land-cover-cap-r<nnn>[-pilot].parquet`, carrying `realisation_id`,
  `claim_id`, the damaged area and rate it was built from, the land value, the
  wall undepreciated value and what of it reached the cap, the cap itself, and a
  flag each for the area cap and the retaining wall sub-cap binding.
- The two flags are written rather than recomputed downstream because neither
  can be recovered from the cap afterwards, and the share of claims binding on
  each is one of the study's own validation checks.
