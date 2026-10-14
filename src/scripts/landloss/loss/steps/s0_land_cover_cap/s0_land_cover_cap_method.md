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
  `world_loss_input_path()`, so the file names live in one place, once per
  exposure world in `WORLD_IDS` and earthquake in `REALISATION_IDS`. Its
  output, like step 1's, carries both in its name and its columns.

## Bringing polygons and walls onto the claim

- The Act settles a claim, so `landloss.loss.claims.land_by_claim()` brings the
  land polygons onto `claim_id` first. Polygons are non-overlapping, so their
  damaged areas **add**. The market rate does not add: it is averaged **weighted
  by the damaged area it values**, so the claim's value equals valuing each
  polygon separately and summing. There is one polygon per claim today, in which
  case both reduce to that polygon's own rate.
- A claim whose polygons disagree about the dwelling count is refused rather
  than resolved, because nothing here can say which count is right.
- `damaged_walls()` keeps a wall carrying `is_damaged_by_shaking` or
  `is_evacuated`. A damaged wall is replaced rather than repaired, so either flag
  being true is one replacement, not one per flag. **Inundated ground does not
  damage a wall** (T-158, the lead, 2026-10-14): a wall only buried by another
  failure's deposit keeps `is_inundated` on the table, but is not valued, and its
  deposit is cleared as land. An undamaged wall is dropped rather than priced at
  zero.
- Walls are summed over the claim before the sub-cap applies, because the
  sub-cap limits a claim's walls together rather than each wall on its own.

## The damaged area, from both causes

- Landslide damage arrives as an area, `land_slide_total_insured_land_area`,
  already unioned over the evacuated and inundated footprints by vul step 3.
- Liquefaction damage arrives as an area too, `Liq_LD_damaged_area` (**T-56**):
  the evacuated land plus the inundated land drawn for the claim's state, less
  the share of the evacuated taken to lie under the inundated -- 30%, an
  assumption to be verified (**L-44**) -- and no more than the polygon's insured
  area. It is zero where the polygon has no state: off the grid, None, or not
  claimed.
- The two are combined with a **maximum, not a sum**. Ground both liquefied and
  buried is one piece of damaged ground, and adding would value some of it
  twice. The maximum is exact where one cause reaches all the ground the other
  did; where they lie on different parts of the polygon it undercounts, by at
  most the smaller of the two.
- **The overlap and the combination are not confirmed.** They are the first
  thing to revisit if the land numbers look wrong.

## What the cap currently cannot count

- **A crossing's value is a flat figure.** Its undepreciated value is its
  replacement cost, $15,000 a metre of span over a 5 m default, because nothing
  supplies a span; the sub-cap then limits what it adds. The run prints the
  value and how much of it the sub-cap lets in.
- **Every wall is priced at its own type and height**, `rw_type` and
  `rw_height` as exposure drew them: the type at the costing tool row
  `retaining-wall-types.csv` names for it, the two timber pole types on the pile
  their height calls for (`TIMBER_POLE_HEIGHT_BANDS_M`). The rates span a factor
  of 21, so the mapping is the largest single assumption in the wall half of the
  cap.
- **A wall is valued over the length it is rebuilt over, never more than it
  had** (2026-10-14). Face area is `rw_height` by the valued length:
  `min(max(damaged length + 2 x 1 m, 3 m), wall length)`, where the damaged
  length is `rw_damaged_length` (the whole `rw_length` where the table has no
  such column) and the wall length is the sum of its pieces' `rw_length`. It is
  worked per wall by `landloss.loss.claims.wall_lengths_by_piece()` -- grouped
  on `parent_rw_id`, shared over the pieces in proportion to their damaged
  length -- so the margin is added once per wall. The cap and the repair price
  the same metres, except that the cap never counts more wall than the property
  had: a wall that failed whole is valued over its length and replaced over its
  length plus 2 m. The 1 m margin and 3 m minimum are invented
  (`LANDSLIDE_WALL_MARGIN_M`, `MIN_LANDSLIDE_WALL_LENGTH_M`).

## Output

- One row per claim, written to
  `temp/loss/land-cover-cap-r<nnn>[-pilot].parquet`, carrying `realisation_id`,
  `claim_id`, the damaged area and rate it was built from, the land value, the
  wall undepreciated value and what of it reached the cap, the cap itself, and a
  flag each for the area cap and the retaining wall sub-cap binding.
- The two flags are written rather than recomputed downstream because neither
  can be recovered from the cap afterwards, and the share of claims binding on
  each is one of the study's own validation checks.
