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

## Built already (commit `b59bfe7`, 2026-10-05)

- **Pifs and sizs:** the siz table, one row per pif, is
  `temp/hazard/landslide/urban-slope-sizs{suffix}.parquet`
  (`gen_urban_slope_faces.py`). Index `pif_id`; pips as a MultiPoint; columns
  include `is_siz`, `max_delta_h_m`, `height_band`, `ground_group`,
  `ground_material`, `ground_modification`, `gns_wall` (a GNS mapped wall within
  2 m of a pip), `gns_wall_m`, `building_m`, `candidate_class`
  (`siz`, `small` or `none`), and, from `property_of_pifs`, `property_id`,
  `valuation_reference`, `title_type`, `property_is_road`, `property_share` and
  `n_properties`. Since added (2026-10-05): `pip_direction` (each pip's
  fall direction, in the MultiPoint's order), the pif's spine, its two ends
  and the fall at each (`gen_pif_spines`), `fall_resultant`, and the
  rateable property (`rateable_property_id`, `rateable_share`).
- **GNS-only candidates:** `urban-slope-gns-wall-candidates{suffix}.parquet`,
  lines of 3 to 20 m, class `gns_only`, with `property_id`, ground material and
  `building_m`. These are mapped walls with no pip within 2 m (979 pieces, 8.9 km
  of 30.7 km mapped, over the pilot), indexed by `gns_only_id`.
- **Cut and fill per pif** (landslide step 13, 2026-10-05):
  `urban-slope-pif-cut-fill{suffix}.parquet`, one row per pif with
  `cut_fill_class` (`cut`, `cut_and_fill`, `fill`, `natural`, `uncertain` or
  `unknown`), and `urban-slope-pif-cut-fill-pips{suffix}.parquet`, each pip
  with the foot of its face. The order is step 12's faces, step 13, then step
  12's wall units and wall zones (`gen_hazard.main`); the wall units script
  stops if step 13's tables are missing or older than the siz table.
- **Elements** (`urban-slope-elements{suffix}.parquet`) carry `siz_id`, which is
  a `pif_id` in the siz table (checked over the pilot: all 9,204 elements map,
  to 5,441 distinct pifs, because a pif cut into pieces grows several
  elements). Each element has exactly one pif, and every element's pif is a
  siz and so in a wall unit, so an element is walled where its pif's unit is.
  `with_walls(found, walled)` takes a Series of flags indexed by element
  label.

## Method

Everything is per property. A property is a LINZ NZ Property Boundaries polygon
(`property_id`).

1. **Wall units.** One wall can be several pifs (a long wall is cut at 20 m, and a
   wall with a gap is two pifs), so count walls, not pifs. Since 2026-10-06
   the siz table's pifs are pieces cut by the walls' bends rule along each
   pif's spine, 3 to 50 m (`parent_pif_id` names the whole pif; a pif under
   3 m is none), and a pif's wall height is the 70th percentile of its
   pips' near drops (the lowest cell within 2 m below each pip), not step
   13's walk to the foot. Every wall unit is one line of 3 to 50 m with at
   most 3 bends turning at most 185° in all; a longer wall is cut at its
   bends, then at property boundaries, then evenly. Join candidate pifs
   (`candidate_class` in `siz`, `small`) and `gns_only` pieces into wall
   units **end to end only**, across property boundaries (the lead,
   2026-10-06; before, each join needed one property). The joined members
   are cut into walls where following them within 2 m needs a fourth bend,
   and a wall over 50 m again at the property boundaries it crosses; each
   wall is a unit. A unit is drawn as a line of at most 3 bends and no
   section under 3 m, and carries its length
   in every property it enters by at least 1 m (`property_lengths_m`); its
   primary property holds most of the line:
   - **Where GNS maps the wall, it is the join.** Pifs within 2 m of one GNS
     mapped wall feature are one unit, however many properties it crosses.
   - **Elsewhere, two pieces join when** the gap between their facing ends is
     within the joining distance (start at 5 m), they are offset up or down the
     slope by no more than about 1.5 m (the offset measured along the fall
     direction at those ends), and the fall directions at those ends are within
     30°. A corner is allowed: ends within about 3 m join where the falls turn
     by more than the 30° and up to 90°; two faces falling the same way are
     never a corner, so stacked terraces stay apart however close their ends
     (review fix, 2026-10-05). All four values are `config.py` settings.
   - **Why.** Checked over the pilot on 2026-10-05: a rule of 5 m, same
     property and `fall_bearing_deg` within 30° joined 2,303 candidate pairs,
     only 197 of them on one GNS wall, and 61% offset more than 2 m along the
     fall (stacked terraces, not one wall with a gap). It also caught only 25%
     of neighbouring pifs that one GNS wall crosses, because walls turn corners
     and one bearing per pif cannot follow them.
   - **Directions at the ends, not one bearing per pif.** `fall_bearing_deg` is
     the mean of the pips' eight-way fall directions over the whole pif, which
     means nothing on an L-shaped or curved pif (and cancels on a U around a
     platform). Do not split pifs at bends: an L-shaped wall is one wall in a
     claim report, and splitting would change the hazard's elements. Instead
     store, per pif, its spine (the longest shortest path through its pips
     joined within `PIF_JOIN_M`, by a double sweep on the whole graph; a
     minimum spanning tree's longest path folds back on a face two or more
     cells thick, with both ends at one end), the two spine ends, the mean fall direction of the pips
     within a few metres of each end (`end_a_fall_deg`, `end_b_fall_deg`), and
     how much it bends (the mean resultant length of its pips' fall vectors, 1
     for a straight face). Joining compares the facing ends' values. The pips'
     own directions are in `Pips.direction`
     (`landloss.hazard.landslide.instability_zones`); write them out with the
     siz table so this needs no second pip run.

   A wall unit takes the
   highest member height, the lowest `building_m`, and the ground and height
   band of its longest member. A pif's height is the 80th percentile over its
   pips of the drop from pip to the foot of its face, from landslide step 13's
   pip table (`gen_pif_wall_heights`, `WALL_HEIGHT_QUANTILE` in step 12's
   `config.py`; the lead, 2026-10-06). It was the pif's `max_delta_h_m`, the
   largest drop of any pip pair, which overstated the retained height: on the
   pilot only 29% of walled units were under 1.5 m, against 54% in Anderson et
   al. [anderson_2015]. `max_delta_h_m` stays on the unit for reference; a
   `gns_only` piece keeps the DEM step across it. A pif that straddles properties
   (`n_properties > 1`, about a fifth of pifs) goes to the property with most of
   its pips (`property_share`) unless that is a road parcel, in which case take
   the rateable property with the next most pips; if none, drop the wall from the
   exposure and keep it in the hazard (it still fails). A `gns_only` piece takes
   its property by the same rule on length. Stacked unit titles count once, as
   the lowest `source_id` (`landloss.exposure.land.extent.stack_representatives`),
   the title the claim, the records and the pifs all go to. Write the unit table with
   its member pif ids so every unit maps back to elements.
2. **Prior.** For each wall unit, `p_prior` from the height band of its
   wall height `height_m` (the two bands of `landslide-slope-thresholds.csv`,
   split at 3.5 m, and 0 below 0.5 m; not the siz table's band, which is from
   `max_delta_h_m` and stays for the hazard), whether it is a siz, and the cut and fill class of landslide step
   13 (`urban-slope-pif-cut-fill{suffix}.parquet`; the lead, 2026-10-06). A
   unit takes the class of its longest member pif, or, where pifs tie for the
   longest, the tied class most of its pifs hold; a `gns_only` unit is
   `unknown`. By class:
   - `fill` and `cut_and_fill` take the higher fill prior
     (`BETA_FILL_WALL_FACTOR`), the front and back of a platform
     [monteith_2020];
   - `cut` in rock taller than the soil cover (a ground map rock material and
     a height over 2.5 m) takes the rock reduction (`BETA_ROCK_CUT_FACTOR`):
     Wellington greywacke cuts stand at 55 to 75° unsupported
     [nzgs_2025_torlesse]. A cut in soil, or a lower one in rock, keeps its
     prior;
   - `natural` takes `BETA_NATURAL_WALL_FACTOR`, since a face that falls no
     more than the ground around it is a bank, not an earthwork;
   - `uncertain` and `unknown` are unchanged.

   The ground map's fill (a fill material, or its `modification`, which is
   fill on 88% of the pilot's candidates) and the SLIDE fill bodies no longer
   set the prior; before the class, the rock reduction read every face in
   rock over 2.5 m as a cut and reached 2,583 pilot units. A wall below about
   0.7 m (about 1.0 m where it faces a diagonal) makes no pips, so it is a
   candidate only where GNS maps it: that is the drop a pip needs at 1, 3 and
   5 m (`PIP_DROP_M`, `PIP_OFFSETS_M` in `instability_zones.py`), and GNS
   walls 2 to 5 m from a pip show a step of only 0.4 to 0.5 m. No prior is
   lowered for it.
   Start from the existing `p_wall` logic in
   `exposure/rw/steps/s6_wall_population/gen_wall_probability.py` and move its
   weights across. The ground map is fine for now; its fill and rock-grade
   changes are open (landslide status) and will move this prior, not its shape.
3. **GNS floor.** A wall unit with a GNS mapped wall on it
   (`gns_wall`) is at least **0.95**. A `gns_only` unit is set at **0.8**; a
   `gns_only` unit that joins a pif wall unit takes the 0.95 floor from the
   join. A `gns_only` piece within 5 m of a candidate pif on the same property
   joins that pif's unit (a `config.py` setting), so one wall is not counted
   twice, but only where it runs roughly along the pif's face: the angle
   between the piece's bearing and the pif's strike (perpendicular to the
   fall at the pif's spine end nearest the piece) is at most 45°
   (`GNS_ONLY_MERGE_MAX_ANGLE_DEG`; the lead's quick fix of 2026-10-06, after
   pilot unit `WU0001918` joined an east-west mapped wall to a north-south
   3-pip pif across it). Before that it joined whatever its direction: about 17% of mapped wall length (about 5 km over
   the pilot) is 2 to 5 m from a pip. Those stretches show a step of only 0.4
   to 0.5 m on the 1 m DEM (against 1.0 m at walls within 2 m of a pip), under
   the 0.7 m pip drop, so some may be a lower second wall beside the pif rather
   than the same wall drawn off; the 5 m merge accepts that. GNS is the only
   dataset that locates a wall, so only it is evidence on a candidate. GNS maps
   only the walls visible from above, so the part of a pif no mapped wall
   reaches is not evidence against a wall there: the floor applies to the
   whole unit.
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
     and report results with and without NZMM. "Modestly" is a weight: where
     NZMM's count is the larger, a unit moves `BETA_NZMM_UPDATE_WEIGHT` (0.3)
     of the way from its claims update to the full update on n = 2.
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
- **Every wall on a siz has a polygon** (2026-10-06): a pif needs at least
  three pips (`BETA_MIN_PIF_PIPS`), and every siz pif grows an element kept
  whatever the element keep rule says, so a wall drawn on a siz pif always
  has an evacuated polygon in landslide step 9 (before, 2,782 of 8,223 pilot
  siz pifs grew no element and 573 walls had no polygon). A `small` pif (a
  GNS wall with no siz) and a GNS-only unit still grow none.
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

- The joining distance, the up-or-down-slope offset, the end bearing tolerance
  and the corner distance for wall units (start values above).
- **Setting factors (approved 2026-10-06).** A unit mostly within 2 m of a
  road parcel boundary takes 2.0 on its prior, one mostly within 2 m of a
  property boundary 1.5, and a face over 5 m tapers to 0.1 of its prior at
  8 m (`BETA_ROAD_FRONTAGE_WALL_FACTOR`, `BETA_BOUNDARY_WALL_FACTOR`,
  `BETA_TALL_FACE_*`). Judgement until T-50.
- **Boundary walls (settled 2026-10-06).** Over the pilot, 44% of
  neighbouring pifs that one GNS wall crosses lie on different properties.
  A wall is now one unit across them, counted as a wall on every property
  it enters by 1 m in the claim update (a unit keeps the highest of its
  properties' updates) and drawn once on its primary property; the loss
  side is to count it on each property at the length inside it (vul rw
  status, Next). Whether a boundary changes the wall probability is the
  lead's, separately.
- Whether the straddling-pif rule should prefer the property whose building is
  nearer rather than most pips.
- NZMM's n, its weight (`BETA_NZMM_UPDATE_WEIGHT`, 0.3 from 2026-10-05, so
  `p_wall` takes a tempered NZMM update with `USE_NZMM_UPDATE` on) and whether
  to use it at all, pending NHC saying how the flag is filled.
- The prior's numbers, until T-50.
- Whether the rock-grade ground map change (pending) is made before the prior
  is set; the ground map now says only whether a cut is in rock.
