# Plan: placing retaining walls on the potential instability faces

Written 2026-10-05 for whoever implements it. Self-contained: read this, then the
files under "Read first". The step plans (landslide step 12 phase 4, retaining
wall step 6 phase 2e) carry the checklist and point here.

## Purpose

The urban slope model (`building-pip-pif-siz-slope-polygons.md`) builds the
evacuated zone twice, with every siz walled and with none. This plan replaces
those two scenarios with a probability that each wall is there, so a realisation
draws which faces are walled. It also fixes how the retaining wall exposure
(`exposure/rw`) gets its candidate walls: the pifs, not the free-face lines of the
earlier faces plan.

Every probability below is judgement until the claim report extraction (**T-50**)
calibrates it. The literature gives each piece of evidence its direction, not its
size. Keep every weight as a named `BETA_` constant in
`landloss.domain.constants`, not inline.

## Built already (commit `de0cea1`, 2026-10-05)

- **Pifs and sizs:** the siz table, one row per pif, is
  `temp/hazard/landslide/urban-slope-sizs{suffix}.parquet`
  (`gen_urban_slope_faces.py`). Index `pif_id`; pips as a MultiPoint; columns
  include `is_siz`, `max_delta_h_m`, `height_band`, `ground_group`,
  `ground_material`, `ground_modification`, `gns_wall` (a GNS mapped wall within
  2 m of a pip), `gns_wall_m`, `building_m`, `candidate_class`
  (`siz`, `small` or `none`), and, from `property_of_pifs`, `property_id`,
  `valuation_reference`, `title_type`, `property_is_road`, `property_share` and
  `n_properties`.
- **GNS-only candidates:** `urban-slope-gns-wall-candidates{suffix}.parquet`,
  lines of 3 to 20 m, class `gns_only`, with `property_id`, ground material and
  `building_m`. These are mapped walls with no pip within 2 m (979 pieces, 8.9 km
  of 30.7 km mapped, over the pilot).
- **Elements** (`urban-slope-elements{suffix}.parquet`) carry `siz_id`, which is
  a `pif_id` in the siz table (checked over the pilot: all 9,204 elements map,
  to 5,441 distinct pifs, because the pieces of a pif and neighbouring sizs grow
  into shared elements). A wall draw is per pif, so turn it into element flags
  by `siz_id`; an element grown from several pifs needs a rule (walled if any of
  its pifs is). `with_walls(found, walled)` takes a Series of flags indexed by
  element label.

## Method

Everything is per property. A property is a LINZ NZ Property Boundaries polygon
(`property_id`).

1. **Wall units.** One wall can be several pifs (a long wall is cut at 20 m, and a
   wall with a gap is two pifs), so count walls, not pifs. Join candidate pifs
   (`candidate_class` in `siz`, `small`) and `gns_only` pieces of one property
   into wall units when their ends or nearest points are within a joining
   distance (start at 5 m, a `config.py` setting) and they run roughly parallel
   (bearing within 30°, using `fall_bearing_deg` for pifs). A wall unit takes the
   highest `max_delta_h_m`, the lowest `building_m`, and the ground and height
   band of its longest member. A pif that straddles properties
   (`n_properties > 1`, about a fifth of pifs) goes to the property with most of
   its pips (`property_share`) unless that is a road parcel, in which case take
   the rateable property with the next most pips; if none, drop the wall from the
   exposure and keep it in the hazard (it still fails). Write the unit table with
   its member pif ids so every unit maps back to elements.
2. **Prior.** For each wall unit, `p_prior` from its height band (the eight bands
   in `landslide-slope-thresholds.csv`), whether it is a siz, and the ground map:
   rock walls are rarer than soil ones (Wellington greywacke cuts stand at 55 to
   75° unsupported [nzgs_2025_torlesse]; apply the rock reduction only to cuts
   taller than the soil cover, band 4 and up, over 2.5 m), fill gets a higher
   prior, and a wall below about 0.5 m is less likely to be resolved by the grid.
   Start from the existing `p_wall` logic in
   `exposure/rw/steps/s6_wall_population/gen_wall_probability.py` and move its
   weights across. The ground map is fine for now; its fill and rock-grade
   changes are open (landslide status) and will move this prior, not its shape.
3. **GNS floor.** A wall unit with a GNS mapped wall on it
   (`gns_wall`) is at least **0.95**. A `gns_only` unit is set at **0.8**; a
   `gns_only` unit that joins a pif wall unit takes the 0.95 floor from the
   join. GNS is the only dataset that locates a wall, so only it is evidence on a
   candidate.
4. **Property databases (the update, unchanged from `exposure/rw/status.md`,
   "Wall datasets").** The claim reports and NZMM say how many walls a property
   has, not which candidate is the wall.
   - A claim report listing n walls: for each wall unit on the property,
     `P(wall | at least n walls) = p × P(at least n − 1 of the others) /
     P(at least n of all)`, each from the Poisson-binomial over the units'
     current probabilities. Every probability rises or stays; none falls. A
     report listing no walls changes nothing. If a property has fewer units than
     listed walls, every unit goes to 1 and the shortfall is written out as
     "candidates missing", not hidden.
   - NZMM `has_retaining_wall` is true: the same update with n = 2 (the lead's
     expected minimum for the database that does not say how many), applied
     modestly and flagged unreliable: NZMM agrees with GNS no better than chance
     (kappa 0.03) and its provenance is unknown. Make the n a `BETA_` constant
     and report results with and without NZMM.
   - Hold out a seeded 30% of claims; never update on them. Claims exist only on
     claimed properties, mostly hill land, so the update is biased towards them;
     do not fit any prior to the databases.
   - This replaces `apply_count_bounds` in the step 6 scripts; remove it in the
     same change.
   - Five 20% allocation rounds were considered and not taken: the per-property
     update is exact and has no order effect. They return only if a global wall
     target (a count NHC gives) appears, as a way to hit that target.
5. **Draw.** Per realisation, draw each wall unit walled with its probability
   from a seeded generator, one stream per realisation. The draw is shared: the
   same walls feed the hazard (`with_walls` Series, so the polygon builder gives
   the walled polygon) and the exposure (the walls that can fail or be damaged).
   Keep the two on one draw so a wall that is walled in the hazard is the wall
   that is exposed.
6. **Output.** A wall-unit table (id, member pif ids, property, geometry,
   probability and its parts: prior, GNS floor, update), written under
   `temp/hazard/landslide/`, and the per-realisation draws.

## Checks

One-sided, because a dataset with no wall is not evidence of no wall.

- **GNS recall:** share of mapped wall length within 2 m of a wall unit (target
  well above the 67% pif recall, since `gns_only` units cover the rest).
- **Claims, held-out 30%:** expected walls per claimed property (sum of unit
  probabilities) against the report's count, and P(at least one wall) on
  properties whose report lists one.
- **Strata** (NZMM slope class, council, age bin): modelled share of properties
  with a wall should not fall below the share any dataset records.
- **Height shape** of the drawn walls against Anderson et al. [anderson_2015].
- **Pilot counts:** expected walls, units, walled share of sizs and the change in
  the evacuated area against the two scenarios (640,878 m² walled, 612,654 m²
  bare, over the `wlg-pilot`).

## Where the code goes

- Library: `landloss/hazard/landslide/wall_units.py` (units and the Poisson-
  binomial update, pure functions, unit tested on small synthetic frames) beside
  `wall_candidates.py`. Name functions `gen_` for what derives data.
- Landslide step 12 (`steps/s12_urban_slope_faces/`): the wall-unit table and the
  draw into `with_walls`; its plan phase 4 ticks as each piece lands. Settings
  (joining distance, bearing tolerance, hold-out share, seed) go in its
  `config.py`; no argparse.
- Retaining wall step 6 (`exposure/rw/steps/s6_wall_population/`): reads the unit
  table instead of building lines; phase 2e of its plan.
- Update the step method files, both `status.md` files and add a
  `doc/whatsnew/{initials}.feature.{yymmddhhmm}.md` fragment for each change.

## Read first

- `src/landloss/hazard/landslide/wall_candidates.py` and its tests.
- `src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/` (method
  and plan).
- `src/scripts/landloss/exposure/rw/status.md`, "Wall datasets", and
  `exposure/rw/validations/rw_dataset_comparison.md`.
- `.agents/plans/building-pip-pif-siz-slope-polygons.md`.
- `.agents/context/nhc-land-cover-and-settlement.md` (how cover attaches to a
  property) and `.agents/context/land-damage-mechanisms.md`.

## Open decisions

- The joining distance and bearing tolerance for wall units (start values above).
- Whether the straddling-pif rule should prefer the property whose building is
  nearer rather than most pips.
- NZMM's n and whether to use it at all, pending NHC saying how the flag is
  filled.
- The prior's numbers, until T-50.
- Whether the fill and rock-grade ground map changes (pending) are made before
  the prior is set.
