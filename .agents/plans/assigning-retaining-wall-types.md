# Plan: assigning each retaining wall a type, and a fragility by type

Written 2026-10-06 for whoever implements it. Self-contained: read this, then
the files under "Read first". The decisions here are the project lead's of
2026-10-06 unless a line says otherwise.

## Purpose

The wall model gives every wall one curve per size class and condition (modern
or poor), from Koutsoupaki et al. (2023) [koutsoupaki_2023]. Condition is set
from height and dwelling age (`landloss.exposure.rw.wall_probability`). In
Canterbury, failure tracked wall type far more than anything else
[anderson_2015] [stone_2015]. Wall type in Wellington tracks the era a wall was
built in, its height, and whether it stands on a road frontage (meeting with
Nick Peters). This plan:

- draws a **wall type** for every wall from its age, height and road frontage;
- gives each type **its own fragility curve**, stored as two PGA percentiles;
- shifts the curve for a wall retaining **fill** (weaker) or a **cut**
  (stronger);
- **drops the separate condition axis** (`p_poor`, `initial_condition`),
  because the type now carries it and keeping both counts age twice.

## Read first

- `src/scripts/landloss/vul/research/fig_rw_type_fragility.md`: the curves,
  the evidence beside them, and how far the Canterbury shares can be trusted.
  The figure is `report/vul/rw/fig/rw-type-fragility.png`.
- `src/landloss/hazard/landslide/urban/wall_type_fragility.py` and
  `src/landloss/io/assets/retaining-wall-type-fragility.csv` (README section
  beside it).
- `src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`: the four age
  bins and why they break where they do.
- `.agents/context/retaining-wall-fragility.md`: the published curve review
  and the Canterbury comparison.

## Built already (2026-10-06)

- [x] **The type curves, confirmed by the lead.** Seven types × three size
  classes, each stored as `p15` and `p50`, the free-field PGA at which 15% and
  50% of walls are replaced, read from Koutsoupaki Tables A1 to A5 (3 m wall
  for small and medium, 6 m for large). The damage state is the **moderate**
  DS2, `Ux = 5% of H`, because moderate damage usually leads to full
  replacement in a claim. New timber pole takes its rung times 1.3 and
  engineered modern times 1.5 (`type_factor`); block and RC stay unscaled.
  `load_wall_type_fragility` turns each pair back into a lognormal
  (`theta = p50`, `beta = ln(p50 / p15) / 1.036`).
- [x] **The fill and cut shift.** `FILL_CAPACITY_FACTOR = 0.85` and
  `CUT_CAPACITY_FACTOR = 1.15` scale both percentiles; an unknown position
  keeps the stored curve (`position_factor`, `wall_type_failure_probability`).
- [x] Tests: `tests/landloss/hazard/landslide/urban/test_wall_type_fragility.py`.
- [x] The research figure and findings
  (`src/scripts/landloss/vul/research/fig_rw_type_fragility.py`).

Since 2026-10-06 landslide step 8 and vul shaking step 9 read the type table.

**Changed 2026-10-07 (the lead): two height classes, not three size
classes.** The table is keyed on `(wall_type, height_class)`, 14 rows:
`under_2_m` (height below 2.0 m, or unknown) and `2_m_and_over`, from each
drawn wall's `height_m` (`wall_type_fragility.height_class`). `size_class`
stays on every wall for the loss module's pricing; only the fragility lookup
moved. Gravity masonry, old timber pole, block or RC cantilever and landscaper
timber take the published height effect switched (`height_effect =
switched`): taller walls of these types are the worse, so `under_2_m` takes
the 6 m curve and `2_m_and_over` the 3 m curve. Crib, new timber pole and
engineered modern have no height effect (`none`) and take the 3 m curve for
both. `wall_type_curves` and `wall_type_failure_probability` take `height_m`
in place of `size_class`. The table below gives the 3 m and 6 m readings; the
height rule picks between them.

## The wall types and their curves

All on DS2, moderate, `Ux = 5% of H`.

| Type | Koutsoupaki rung | p15/p50, 3 m (g) | p15/p50, 6 m (g) | Evidence |
| --- | --- | --- | --- | --- |
| `gravity_masonry` (stone, brick, mass concrete) | Fs 1.1 | 0.27/0.51 | 0.32/0.63 | Stone masonry 18% Very Poor [anderson_2015]; stone facing 35% Moderate+Major [stone_2015]; gravity walls 0.10/0.36 g [cosentini_2019] and 0.12/0.46 g [li_2024] |
| `crib` | Fs 1.2 | 0.31/0.59 | 0.36/0.71 | Crib 13% [anderson_2015]; concrete 30%, timber 28% Moderate+Major [stone_2015] |
| `timber_pole_old` (before July 1992) | Fs 1.3 | 0.35/0.65 | 0.41/0.80 | Judgement: unengineered or decayed |
| `block_rc_cantilever` | Fs 1.5 | 0.44/0.86 | 0.54/1.09 | Concrete masonry 5.5% [anderson_2015]; RC 22% [stone_2015]; RC cantilever 0.29/0.60 g [kaynia_2011] |
| `timber_pole_new` (engineered, after July 1992) | Fs 1.5 ×1.3 | 0.57/1.12 | 0.70/1.41 | Timber pole 2.8% [anderson_2015]; post and panel 9% [stone_2015] |
| `landscaper_timber` (unconsented, under 1.5 m) | Fs 1.1 | 0.27/0.51 | 0.32/0.63 | Judgement |
| `engineered_modern` (MSE, soil nail, large RC) | Fs 1.5 ×1.5 | 0.66/1.29 | 0.81/1.63 | MSE 0% of 18 walls [anderson_2015] |

The curves sit above the Canterbury failure shares, more so on the moderate
state than they did on the extensive one; that is the known conservatism the
lead accepted on 2026-10-02. The type split sets the ratio between types, not
that level.

## Method

### 1. The age of a wall

1. **Dwelling age first.** The QV rating roll's `building_age_indicator`, the
   decade the main building was built, read by
   `landloss.io.qv_rating_roll.get_qv_rating_roll` from T:
   `SourceMaterial/SENSITIVE/_Filedrop_ Natural Hazards Data Sets`
   (`constants.QV_RATING_ROLL_SOURCE_DIR`), joined to the property on its
   valuation reference. A decade cannot split at July 1992 or 2005: count the
   1990s in `1992_2004` and split the 2000s at 2005 as the bin note says.
2. **Property age second.** Exposure step 8's title and survey plan date
   (`landloss.exposure.rw.age`, `rwt-age{suffix}.geoparquet`), used:
   1. where the dwelling age is missing, in its place;
   2. where the lot is 20 or more years older than the dwelling (a rebuild on
      an old section), the wall's bin is drawn half from the lot's bin and
      half from the dwelling's, because the original walls may have stayed;
   3. where the dwelling is older than the lot (infill or a reissued title),
      not at all.
3. **Neither held:** draw the bin from the suburb's `p_<bin>` shares.
4. **Walls rebuilt since the house:** with probability `BETA_WALL_REBUILT_SHARE`
   (start 0.2), move the wall's bin to a later one before drawing its type.

### 2. Drawing the type

Each wall draws its type, per exposure world, on its own stream, from one row
of a table of fractions indexed by age bin and height band; each row sums to 1.
The height bands are under 1.5 m, 1.5 to 2.5 m, and over 2.5 m: 1.5 m is the
consent threshold, which is what changes the type, so they differ from the
size classes on purpose.

The fractions below are **placeholders for Nick Peters to revise**, then to
check against the claim reports (step 4). Keep them as a packaged CSV, not
inline, with a `BETA_` note that they are judgement.

| Age bin | Height | gravity_masonry | crib | block_rc | pole_old | pole_new | landscaper | engineered |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pre_1970 | <1.5 | .40 | .05 | .10 | .10 | 0 | .35 | 0 |
| pre_1970 | 1.5–2.5 | .60 | .10 | .10 | .20 | 0 | 0 | 0 |
| pre_1970 | >2.5 | .75 | .10 | .05 | .10 | 0 | 0 | 0 |
| 1970_1991 | <1.5 | .10 | .10 | .20 | .20 | 0 | .40 | 0 |
| 1970_1991 | 1.5–2.5 | .10 | .30 | .25 | .35 | 0 | 0 | 0 |
| 1970_1991 | >2.5 | .10 | .40 | .30 | .20 | 0 | 0 | 0 |
| 1992_2004 | <1.5 | 0 | .05 | .20 | 0 | .25 | .50 | 0 |
| 1992_2004 | 1.5–2.5 | 0 | .10 | .30 | 0 | .55 | 0 | .05 |
| 1992_2004 | >2.5 | 0 | .10 | .30 | 0 | .45 | 0 | .15 |
| 2005_on | <1.5 | 0 | 0 | .20 | 0 | .30 | .50 | 0 |
| 2005_on | 1.5–2.5 | 0 | 0 | .30 | 0 | .60 | 0 | .10 |
| 2005_on | >2.5 | 0 | 0 | .30 | 0 | .45 | 0 | .25 |

**Road frontage** is one row of multipliers applied to the wall's row and
renormalised: gravity masonry ×1.5, block/RC ×1.5, crib ×0.5, landscaper
timber ×0.3, the rest ×1. Retaining walls on a road boundary hold up
driveways, garages and footpath cuts. A wall unit is on a frontage where the
wall unit source reads it so (`road_frontage` in
`landloss.hazard.landslide.wall_units`); check that the flag reaches the drawn
walls.

### 3. Failure

`wall_type_failure_probability(pga_g, wall_type, height_m, wall_position,
table)` (`size_class` until 2026-10-07) gives each wall's probability of replacement. `wall_position` is the
unit's `fill` or `cut` (step 13's class, already on the drawn walls). It
replaces the `(wall_class, size_class, initial_condition)` lookup in:

- `landloss.hazard.landslide.urban.fragility` (walls on sloping land, landslide
  steps 8 and 9), which converts the PGA median to PGV with the study's ratio;
  the type table's `theta` goes through the same `pga_to_pgv_theta`;
- `landloss.vul.shaking.fragility.wall_failure_probability` (walls on flat
  land).

### 4. Calibration

- The type mix per age bin from the claim reports (**T-50**):
  `src/scripts/landloss/vul/research/analyse_claim_reports.py` already counts
  concrete, block, crib and timber walls; join each to its property's age bin.
- Anderson's finding that type tracked era in Canterbury
  (`anderson2015-F07`).
- The modelled replacement share against Stone's Moderate plus Major shares
  (28% over all council walls) and Anderson's about 10% Very Poor, as the
  observed comparison, not a target.

## Phases

### Phase 1: the age of each wall

- [x] Read the QV `building_age_indicator` onto every property through
  `get_qv_rating_roll`, binned to `AGE_BINS` (`landloss.exposure.rw.wall_age`,
  exposure step 6 `gen_wall_age.py`).
- [x] Combine it with step 8's property age by the rules in Method 1, writing
  the bin shares and which rule set them (`age_basis`).
- [x] Carry the bin onto the drawn walls (`age_bin`, drawn per wall per world
  from its property's shares; the wall units carry none).
- [x] Tests for each rule.

### Phase 2: the type draw

- [x] Package the Table 2 fractions and the frontage multipliers as a CSV with
  a README entry; validate that each row sums to 1.
- [x] Draw `wall_type` per wall per world in exposure step 6, on its own
  stream, after the rebuild shift (`landloss.exposure.rw.wall_type`,
  `gen_wall_population.py`).
- [x] Write `wall_type` onto the wall population; drop `p_poor`,
  `p_poor_basis` and `initial_condition`.

### Phase 3: the model reads the type curves

- [x] Replace the condition lookup in `hazard/landslide/urban/fragility.py`
  and `vul/shaking/fragility.py` with the type curves
  (`wall_type_fragility.wall_type_curves`, scaled by the wall's own fill or
  cut position).
- [x] Retire `retaining-wall-fragility.csv`, `INITIAL_CONDITIONS`, and the
  condition code in `wall_probability.py` (`BETA_UNCONSENTED_POOR_SHARE`,
  `BETA_PRE_1990_POOR_SHARE`, `BETA_POST_1990_POOR_SHARE`).
- [ ] Rerun the pilot chain from exposure step 6. The loss module reads
  `size_class` only, so it should not change; confirm with its owner before
  touching anything under `loss/`.

### Phase 4: calibration and checks

- [ ] Nick Peters reviews the Table 2 fractions and the old timber pole rung.
- [ ] Compare the drawn type mix per age bin with the claim reports (**T-50**).
- [ ] Compare the modelled replacement share by type with the Canterbury
  shares (findings doc).

## Future improvements (held, not planned)

- One type draw per property per height band, instead of one per wall, since
  walls on one lot tend to be one build.
- Geology (soil against rock) as a second multiplier on the type fractions.
- The age of large and road-frontage walls from the lot date, since a
  developer often built those at subdivision.
- A retained-material shift (rock against soil or colluvium), like the fill
  and cut shift.
- Use the de Silva et al. (2026) [de_silva_2026] road wall law with a yield
  acceleration per wall type (now drawn at 0.5 g and DS2 in the figure only).

## Open decisions

- The Table 2 fractions and the frontage multipliers (Nick Peters).
- `BETA_WALL_REBUILT_SHARE` and the 20 year gap that marks a rebuild.
