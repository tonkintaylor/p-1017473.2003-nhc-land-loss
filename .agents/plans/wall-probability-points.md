# Plan: a points-based probability that a wall candidate is a wall

Written 2026-10-07 for review by the lead; **implemented 2026-10-07** with the
lead's decisions below (`wall_units.gen_wall_points`). Replaces the
multiplied factors of `wall_units.gen_wall_prior` (step 12). Builds on
`placing-retaining-walls-on-pifs.md`, whose candidate model (SIZ pieces,
low-height walls, GNS-only pieces, each independent) is unchanged.

## The lead's decisions (2026-10-07)

1. Flatland is not scored. Length scores −5 under 5 m only.
2. Step 13 class: a cut in rock deeper than **2.0 m** (was 2.5 m) −20; fill
   and cut and fill +5; natural −15.
3. Geology: a cut in soil (alluvium, loess, colluvium, the fill materials)
   **+10**; highly or completely weathered rock (`rock_hw_cw`) and crushed
   rock (`rock_crushed`) score as soil, not rock.
4. Age: the property's wall age shares from exposure rw step 6
   (`wall-age{suffix}.parquet`: `p_pre_1970`, `p_1970_1991`, `p_1992_2004`,
   `p_2005_on`) score −10, −5, 0, +10, share-weighted, on the candidate's
   primary property; a missing file or property scores 0 with a loud warning.
   `gen_wall_age` now runs in `gen_hazard` before the wall units (it was in
   `gen_exposure`, after them).
5. Verticality: per pip, the drop to the first cell over the largest drop
   within 3 cells; per pif piece, the median, in the siz table as
   `verticality`; bins under 0.4 −20, 0.4–0.5 −5, 0.5 and over +10.
6. NHC-land-attrs flag: +5 points; the NZMM Poisson-binomial update and
   `BETA_NZMM_*` are removed. The claim update stays.
7. Scale: 20 points per doubling, logistic. Outputs `wall_points`, `p_prior`,
   `wall_points_explain`; the table in
   `src/landloss/io/assets/wall-probability-points.csv`.
8. Interim calibration: the total expected walls after the floor and the
   claim update is 60% of the 3,997 of the factor prior (about 2,398). The
   GNS floor falls 0.95 → 0.80 and a GNS-only candidate 0.8 → 0.70 (the
   lead's correction the same day; a first cut to 0.57 and 0.48 was too
   aggressive); `BETA_WALL_BASE_P` is solved for the total (0.225), marked
   interim.

## Why change

The prior today multiplies probabilities: 0.5 for a SIZ piece, times the
height band, the step 13 class (fill ×1.3, natural ×0.5, rock cut ×0.3), the
setting (road frontage ×2.0, property boundary ×1.5) and the tall-face taper,
then clipped to 1. The factors stack past 1: a cut, fill or uncertain face on
a road frontage reaches 1.0 with no mapped wall, more certain than a GNS
mapped wall (floor 0.95). About 470 pilot candidates sat at 0.75 to 1.0.

## The scale

- Each attribute adds points; points add on the log-odds scale.
- **20 points double the odds** (`BETA_WALL_POINTS_PER_DOUBLING = 20`).
- **0 points is the base probability** `BETA_WALL_BASE_P` (start 0.30; set in
  calibration step 3 below).
- p = 1 / (1 + exp(−(logit(base) + points × ln 2 / 20))).

| Points | −40 | −20 | 0 | +20 | +40 | +60 |
| --- | --- | --- | --- | --- | --- | --- |
| p at base 0.30 | 0.10 | 0.18 | 0.30 | 0.46 | 0.63 | 0.77 |

No total can reach 0 or 1, a strong attribute moves an uncertain face a lot
and a near-certain one a little, and the form is a logistic regression, so
the points can later be fitted without changing it.

## What stays outside the points

1. **GNS mapped wall: a floor.** A piece with a GNS wall within 2 m is at
   least 0.80 (was 0.95); a GNS-only candidate is 0.70 (was 0.8), interim
   (decision 8).
2. **Claim reports: the count update.** A report says how many walls a
   property has, which means something different for one candidate than for
   ten; fixed points cannot express that. The Poisson-binomial update after
   the points, with the 30% hold-out, is unchanged.
3. **NHC-land-attrs flag: becomes points** (below), not the update. It is a
   yes/no for the property with no count, agrees with GNS no better than
   chance (kappa 0.03) and its filling is undocumented; reading "yes" as
   "at least 2 walls" (today, weighted 0.3) over-reads it. This removes
   `BETA_NZMM_MIN_WALLS` and `BETA_NZMM_UPDATE_WEIGHT`.

Order: points → prior; GNS floor; claim update.

## Evidence from the pilot (2026-10-07)

A read-only check of the 4,975 pif candidates (SIZ and low-height) on the
pilot: the share with a GNS mapped wall within 2 m, by attribute (23.2%
overall), and a joint logistic fit of GNS presence on all attributes at once
(AUC 0.74), with its coefficients as points at 20 per doubling. Script:
scratchpad `wall_attr_check.py`, run on a snapshot of the step 12 outputs.

**The label is positive-only and visibility-biased.** GNS mapped the walls it
could see from above; a candidate without a GNS wall is not a "no". Anything
that makes a wall easier to see (a road frontage, an open flat street, a tall
or long face) lifts the GNS rate without making a wall likelier. So the
evidence sets the direction and a ceiling on each attribute's points, not its
size.

| Attribute | GNS rate by bin (lift) | Joint-fit points | Reading |
| --- | --- | --- | --- |
| Verticality (drop in the first cell / drop within 3 cells, median over pips) | 0.13 under 0.4 (×0.54) rising to 0.33 at 0.7–0.8 (×1.43), 0.23 above 0.9 | −18 under 0.5; 0 over 0.8 | Separates batters from steps; adds a little beyond the others (AUC 0.727 → 0.736). The fall above 0.9 is likely small isolated steps (kerbs, garden edges) GNS did not map |
| Near-drop height | 0.17 at 1.0–1.5 m, 0.32 at 1.5–2.5, 0.65 at 2.5–3.5 | −44 for 0.7–2.5 m (against taller) | Mostly visibility: taller walls are seen. Use modestly |
| Length | 0.13 under 5 m to 0.32 over 20 m | +29 over 10 m | Partly visibility, partly real (a 3 m piece is often a fragment) |
| Distance to building | 0.30 within 2 m, 0.06 at 20–50 m | +21 within 5 m | Real: walls hold house platforms |
| Road frontage | 0.48 vs 0.20 | +37 | Real and visible; keep strong but below the raw value |
| Property boundary (not road) | 0.32 vs 0.17 | +8 | Real; mostly explained by building distance and road frontage together |
| Step 13 class | cut and fill 0.32, cut 0.25, fill 0.21, uncertain 0.23, natural 0.14 | natural −8, fill +4 | Natural faces are less often walls |
| NLM flatland | 0.33 vs 0.20 | +12 | GNS sees walls along open flat streets; the lead's judgement is a modest reduction |
| Straightness, bends, turning | straight pieces lower (0.20) | 0 | No signal once length is held fixed: short pieces are straight. Drop |

## Proposed points table (judgement, informed by the evidence)

Held in a CSV, `src/landloss/io/assets/wall-probability-points.csv`
(attribute, bin, points, reason), every value `BETA`, replaced by
calibration.

| Attribute | Bin | Points |
| --- | --- | --- |
| Verticality | under 0.4 | −20 |
|  | 0.4–0.5 | −5 |
|  | 0.5 and over | +10 |
| Near-drop height | 0.7–1.0 m | −5 |
|  | 1.0–2.5 m | 0 |
|  | 2.5–5 m | +5 |
|  | 5–8 m | −20 (tall face, replaces the taper) |
|  | over 8 m | −60 |
| Length | under 5 m | −5 (the lead, 2026-10-07) |
|  | 5 m and over | 0 |
| Distance to building | under 2 m | +10 |
|  | 2–5 m | +5 |
|  | 5–20 m | 0 |
|  | over 20 m | −20 |
| Setting | road frontage | +20 |
|  | property boundary (not road) | +10 |
| Step 13 class | fill, cut and fill | +5 |
|  | natural | −15 |
|  | cut in rock over 2.0 m | −20 (the lead, 2026-10-07: −35 too extreme; 2.0 m not 2.5 m) |
| Geology | cut in soil (incl. HW/CW and crushed rock) | +10 |
| Age (share-weighted) | pre-1970 | −10 |
|  | 1970–1991 | −5 |
|  | 1992–2004 | 0 |
|  | 2005 on | +10 |
| NHC-land-attrs | property flagged | +5 |

A low-height wall starts at `BETA_LOW_HEIGHT_WALL_BASE_P` instead of the base,
but carries a GNS wall by definition, so its floor sets it.

Worked examples at base 0.30: a 2 m vertical cut face, 1 m from a house, on a
property boundary, 15 m long: +10 +0 +10 +10 = +30 → 0.55 (the lead: about
right). The same face
on a road frontage: +40 → 0.63. A 4 m natural batter (verticality 0.35), 30 m
from a building: −20 +5 −20 −15 = −50 → 0.07.

## Calibration

1. **Judgement points** as above, in the CSV.
2. **Ranking check against GNS:** within strata (height band, setting), do
   candidates with more points carry GNS walls more often? Tests direction and
   order only.
3. **Level:** set `BETA_WALL_BASE_P` so the expected walls per property match
   the held-out claims and the share of properties with a wall, and check the
   Anderson et al. height shape (54% under 1.5 m).
4. **Later, a fit:** logistic regression on GNS-labelled candidates with a
   positive-unlabelled correction (the GNS detection rate per setting as the
   labelling probability), rounded back to whole points. The visibility
   attributes (road frontage, height, length, flatland) get the strongest
   shrinkage.

## Outputs

Per candidate: `wall_points` (total), `p_prior`, and `wall_points_explain`
(the attribute bins that scored, e.g. "verticality 0.5 and over +10; setting
road_frontage +20; class natural -15"). `p_prior_basis` stays, as `points`
or `gns_only`. The floor, update, draw and
everything downstream read `p_prior` and `p_wall` as now.

## Where the code goes

- `instability_zones.gen_pif_near_drops`: also return each pip's drop at 1 and
  3 cells, so the siz table carries `verticality` (median over pips).
- `wall_units.gen_wall_points(units, table, *, base_p, per_doubling)` replaces
  `gen_wall_prior`; the units already carry height, length, `building_m`, the
  setting flags and `cut_fill_class`; add the property's NHC-land-attrs flag.
- `gen_wall_unit_probability`: drop the NHC-land-attrs update.
- Step 12 `config.py`: the CSV path, the base and points per doubling.
- Tests: the scale (0 points = base, +20 doubles the odds), each attribute's
  bins, the explain string, no probability reaching 1, the floor and update
  still on top.
- Retire `BETA_SIZ_WALL_PRIOR`, `BETA_WALL_PRIOR_HEIGHT_BAND_FACTOR`,
  `BETA_ROCK_CUT_FACTOR`, `BETA_FILL_WALL_FACTOR`,
  `BETA_NATURAL_WALL_FACTOR`, the boundary and road factors, the tall-face
  constants and the two NHC-land-attrs constants; keep the floor constants.

## Open decisions

1. The base probability (0.30 to start) and 20 points per doubling.
2. Verticality's top bin: the GNS rate falls above 0.9 (likely kerbs and
   garden edges unmapped); keep +10 there, or +5.
3. Whether to cap the prior below the GNS floor (e.g. 0.9). With log-odds a
   cap is rarely binding; the largest total the table allows (+55) gives
   0.74.
4. Flatland is not scored (the lead, 2026-10-07); the GNS evidence (+12)
   is likely visibility.
5. Whether height should carry any positive points, given GNS sees tall walls
   more easily.
