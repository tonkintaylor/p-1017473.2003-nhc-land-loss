# Packaged assets

Small, slow-moving reference data that ships with the `landloss` package, so a
day-to-day run does not have to download or re-derive it. Everything here is
committed. Nothing here is large enough to belong in a cache.

| Asset | What it is | Written by | Read by |
| --- | --- | --- | --- |
| `study-areas.geoparquet` | Territorial authority boundaries for the four study authorities, from Stats NZ via T+T's Koordinates instance | `src/landloss/io/one_offs/gen_study_extent.py` | `src/landloss/io/area_of_interest.py` |
| `land-value-base-rates.csv` | Published QV rating revaluation anchors per territorial authority, plus the two derived inputs the land value model needs | Maintained by hand — see below | `landloss.exposure.land.land_value.load_base_rates` |
| `land-value-factors.csv` | Landform multipliers, terrain and accessibility coefficients, and clip multiples for the land value model | Maintained by hand — see below | `landloss.exposure.land.land_value.load_factors` |
| `land-value-centres.csv` | The centres the land value accessibility term is measured against, with a weight and decay length each | Maintained by hand — see below | `landloss.exposure.land.accessibility.load_centres` |
| `land-value-extra-stations.csv` | Railway stations missing from the LINZ Topo50 station layer, added to it for the accessibility term | Maintained by hand — see below | `landloss.exposure.land.accessibility.load_extra_stations` |
| `marc-2016-table-s1.csv` | Marc et al. (2016) Table S1, verbatim: the 40 earthquakes their total landslide area and volume expression was tested on | Converted from the supporting information's `.xls` (`context/lit/landslide/marc_2016/`) — see below | `src/landloss/io/one_offs/gen_marc_2016_table_s1.py` |
| `marc-2016-table-s1-subevents.csv` | The same table parsed to numbers, one row per earthquake or per sub-event of an earthquake sequence | `src/landloss/io/one_offs/gen_marc_2016_table_s1.py` | The landslide calibration (`.agents/plans/building-hancox-landslide-model-and-calibration.md`) |
| `wellington-greywacke-strength.csv` | Effective strength (c′, φ′), unit weight and undrained strength of Wellington greywacke, its soil mantle and fill by weathering grade, one row per value set, from published sources and T+T Wellington projects | Compiled from T+T Site Search excerpts of project reports, and from GNS SLIDE reports SR2019/40 and SR2019/51, 1 October 2026 — see below | `landloss.hazard.landslide.ground_map.strength_from_material` |
| `wellington-greywacke-depth-to-rock.csv` | Observed depths to weathered greywacke rock, and thicknesses of the colluvium and residual soil mantle, at Wellington-region T+T sites | As above | Not yet read; for landslide model 7 |
| `hancox-1997-figure-19-area-affected.csv` | Hancox et al. (1997) Figure 19: area affected by landsliding against magnitude for the report's 22 earthquakes, numbered and named as in its Table 2 | Digitised from `context/lit/landslide/hancox_1997/figures/page-075.png` by detecting each filled dot's pixel position and converting it against the axis ticks (a one-off, not kept) | `landloss.hazard.landslide.models.hancox_1997.relationships.get_figure_19` |
| `retaining-wall-type-fragility.csv` | Fragility per retaining wall type and height class (under 2 m, 2 m and over), on the moderate damage state, stored as the PGA at which 15% and 50% of walls are replaced; confirmed by the lead; read by `assign_fragility` (landslide step 8) and `wall_failure_probability` (vul shaking step 9) | Converted from Koutsoupaki et al. (2023) Tables A1 to A5, 6 October 2026 — see below | `landloss.hazard.landslide.urban.wall_type_fragility.load_wall_type_fragility` |
| `beta-retaining-wall-type-shares.csv` | The share of each retaining wall type by age bin and height band, which each wall's type is drawn from; judgement placeholders | Set by the project lead, 6 October 2026, for Nick Peters to revise — see below | `landloss.exposure.rw.wall_type.load_beta_wall_type_shares` |
| `beta-retaining-wall-frontage-multipliers.csv` | The multiplier each retaining wall type's share takes where the wall stands on a road frontage; judgement placeholders | As above | `landloss.exposure.rw.wall_type.load_beta_frontage_multipliers` |
| `urban-fragility-anchors.csv` | The qualitative anchors the urban failure fragility medians are fitted to: Kingsbury scenarios, the MM thresholds, the Wellington low-demand record and the Port Hills, each read as a damaged share of a zone's area or a share of matching polygons failing, with who set each number and why | Maintained by hand — see below | `landloss.hazard.landslide.urban.fragility.load_urban_fragility_anchors` and `hazard/landslide/validations/urban/` |
| `landslide-slope-thresholds.csv` | The steepest overall angle each ground group stands unsupported at, in two height bands (under 3.5 m, 3.5 m and over): the far-pair test of the seed instability zones | Maintained by hand — see below | `landloss.hazard.landslide.slope_elements.load_slope_thresholds` |
| `landslide-seed-thresholds.csv` | Per ground group, the near-pair step that makes a seed instability zone (`adjacent_step_m`), and the old free-face step and bank slope | Maintained by hand — see below | `landloss.hazard.landslide.slope_elements.load_seed_thresholds` |

## `land-value-base-rates.csv`

One row per territorial authority. `ta_name` matches the
`territorial_authority` values on the LINZ NZ Addresses layer exactly, which is
how the model joins addresses to their authority.

`ta_code`, `valuation_date`, `rating_units`, `avg_capital_value_nzd` and
`avg_land_value_nzd` are taken verbatim from the QV rating revaluation media
release cited in `source_url` for that row. Do not adjust them; they are the
published anchors the whole model is calibrated back onto.

The remaining two columns are derived, and are the judgement in the file.

### `index_to_2025_09` — researched

The four councils revalued on four different dates across a falling market, so
the published averages are not comparable until they are put on one basis. This
column is the multiplier that carries each authority's published average forward
to a common 2025-09-01 basis.

Index used: the **QV House Price Index for the greater Wellington region**,
which is region specific, published monthly, and produced by the same valuer
that carried out all four rating revaluations. QV published an annual change of
**-4.5% for the 12 months to July 2025** and **-3.3% for the 12 months to
October 2025**; interpolating between those two published figures gives
**-3.7% for the 12 months to September 2025**, which is the rate adopted here.

- <https://www.qv.co.nz/news/qv-house-price-index-july-2025-nz-homes-13-percent-cheaper-than-late-2021-peak/>
- <https://www.qv.co.nz/news/qv-house-price-index-october-2025-southern-strength-steadies-a-flat-housing-market/>

The annual rate is compounded monthly, `0.963 ** (months / 12)`, where `months`
is the gap between that authority's valuation date and 2025-09-01:

| Authority | Valuation date | Months to 2025-09 | `index_to_2025_09` |
| --- | --- | --- | --- |
| Porirua City | 2025-09-01 | 0 | 1.0000 (by definition) |
| Lower Hutt City | 2025-08-01 | 1 | 0.9969 |
| Upper Hutt City | 2025-06-01 | 3 | 0.9906 |
| Wellington City | 2024-09-01 | 12 | 0.9630 |

A single regional rate is applied to every authority on purpose. Each council's
own revaluation already carries that council's own market movement up to its own
valuation date; the index only has to cover the gap after it.

### `median_lot_size_m2` — judgement, not researched

Since 2026-10-01 the model rates each LINZ property on its measured area, per
rating unit for a unit-titled block. This figure is now the reference the
section size factor is relative to, and the divisor only for an address that
stands in no property. No
council, Stats NZ or LINZ publication gives a median residential lot size per
territorial authority. The Wellington Regional Housing and Business Development
Capacity Assessment uses a notional 600 m2 section for the region as a whole,
and that is the only published convention found; it is not a per-authority
median.

These figures are therefore documented judgement, anchored on that 600 m2
regional convention and spread by topography — Wellington City's hill suburbs
subdivide far tighter than the Hutt Valley's flat subdivisions, and Upper Hutt's
newer low-density growth areas are looser again.

| Authority | `median_lot_size_m2` | Reasoning |
| --- | --- | --- |
| Wellington City | 450 | Steep, tightly subdivided inner suburbs pull the median well below the regional convention |
| Porirua City | 550 | Mixed state-era and modern subdivision, between Wellington City and the valley |
| Lower Hutt City | 600 | The regional notional section size, matching flat valley subdivision |
| Upper Hutt City | 700 | The most recent, lowest-density greenfield growth in the study area |

Sense check against the market evidence bands the project lead supplied: these
give blended rates of roughly $1,330/m2 for Wellington City, $760/m2 for
Porirua, $690/m2 for Lower Hutt and $620/m2 for Upper Hutt, which sit between
the supplied hill and flat bands for each city as they should.

## `land-value-factors.csv`

Long-form `parameter,value,basis` rows. The `basis` cell carries the derivation
so a valuer can check the number without reading any code.

`landform_factor_elevated_flat` is present but unused: Phase 1 classifies only
`hill` and `flat`. Separating elevated flat land needs the DEM, which arrives in
Phase 2, so the factor sits here waiting rather than being applied.

The clip multiples are judgement bounds, not researched figures. They bound
the land value per rating unit, and the floor applies only to a property of one
rating unit. The model
re-solves the per-authority normalising constant after clipping and re-applies
the clip once, so clipping moves value between properties without changing the
authority's modelled mean.

The amenity rows -- `sea_view_premium`, `coast_premium`,
`coast_decay_length_m`, `winter_sun_premium`, the two `amenity_modifier_clip_*`
bounds, the four `sea_view_*` settings that say how the view is measured, and
the five `winter_sun_*` settings that say how the sun is sampled --
are judgement too; `s3_build_amenity.py` reads the settings and
`landloss.exposure.land.land_value.amenity_modifier` the premium and bounds.

The five accessibility rows -- `accessibility_elasticity`,
`rail_station_premium`, `rail_station_decay_length_m` and the two
`accessibility_modifier_clip_*` bounds -- are judgement too, apart from the
400 m decay length, which is the implementation plan's.

## `land-value-centres.csv`

One row per centre: `name`, `kind` (`regional`, `city` or `local`), `weight`,
`decay_length_m`, WGS84 `lon` and `lat`, and a `basis` cell.

- The four CBD weights and both decay lengths are the land value step's
  implementation plan. Local centres take weights from the plan's 0.05 to 0.10
  band by judgement, ranked by the size of the centre, and the plan's 3 km
  secondary centre decay length.
- Positions are placed by hand on each centre's main shopping street, and are
  approximate to a few hundred metres. `fig_town_centres.py` draws them, and is
  where they are checked.
- The list is a first cut. Porirua's suburban centres and Upper Hutt's are not
  in it.

## `land-value-extra-stations.csv`

One row per station: `name`, WGS84 `lon` and `lat`, and a `basis` cell saying
why it is missing from LINZ and how it was placed. It holds Wellington Station
only: the Topo50 station points (layer 50318) carry every suburban station in
the study area but not the terminus. A row stops mattering, without being
deleted, once LINZ adds the station, because an added station within
`DUPLICATE_STATION_M` of one the layer carries is dropped.

## `marc-2016-table-s1.csv`

Table S1 of the supporting information to Marc, Hovius, Meunier, Gorum & Uchida
(2016), *JGR Earth Surface* 121(4), 640–663, doi:10.1002/2015JF003732. The
original `.xls` and the supporting information PDF, which carries the table's
caption, are in `context/lit/landslide/marc_2016/`.

The cell text is as published. Only three things were changed: the columns were
given snake_case names, repeated spaces inside a cell were collapsed, and
`comprehensive_inventory` was added. That column is True for the first 11 rows,
which the caption separates from the other 29 as the comprehensive inventories.
Units follow the original headers: volume in km³ with its range, area in km²,
mean asperity depth R0 in km with its 1σ (or a range where the depth is
unknown, written "?"), modal slope in degrees with its range, and seismic moment
in 10¹⁹ N·m with its 2σ, followed by the fault type in braces.

Codes, from the caption:

- **Volume estimation method**, the letter after the volume. M = scanned and
  corrected inventory of mapped polygons, converted with an empirical
  volume–area relationship. N = the total volume of about 5–20 very large
  bedrock landslides. L = an estimate from the literature. F = a published
  frequency–size distribution, converted and integrated. B = extrapolated from
  the largest landslides, assuming a universal frequency–size distribution.
  P = field photographs and field reports.
- **`!`** after R0: taken from a published rupture inversion; otherwise from the
  hypocentral depth and other assumptions.
- **`*`** after the name: an earthquake sequence, with a foreshock or aftershock
  of more than 30% of the main shock's moment. Its sub-events are separated by
  "/" (depths) and "+" (moments).
- **Mapping**: the image resolution where the inventory came from imagery; G is
  field surveys on the ground and occasional aerial surveys only.
- **Fault type**: SS strike-slip, R reverse, N normal.

Values that look wrong in the published table are kept as published, not
corrected:

- 1929 Buller: volume 0.9 km³ with a range of 0.05–0.23 km³, which does not
  bracket it.
- 2008 Iwate: range 0.021–0.45 km³ around 0.032 km³, probably 0.045.
- "1935, Wairoa": the Wairoa earthquake was 1932.
- 1931 Napier and 1935 Wairoa: fault type `{S}`, not one of the caption's codes.
- 1997 Umbria-Marche: two sub-events but no `*`.

## `marc-2016-table-s1-subevents.csv`

Written by `src/landloss/io/one_offs/gen_marc_2016_table_s1.py` from the verbatim
table, and regenerated with it. One row per earthquake, or per sub-event of a
sequence (47 rows for 40 earthquakes). Event-level values (volume and area,
modal slope, `a_topo`) repeat on each sub-event's row; `r0_km`,
`hypocentral_depth_km`, `moment_nm` and `mw` are the sub-event's own. `mw` is
computed from the moment as (2/3)(log10 M0 − 9.1), the relationship the paper
uses. Where the paper gives R0 as unknown with a range ("? (8-24)"), `r0_km` is
empty and `r0_min_km`/`r0_max_km` carry the range.

## `wellington-greywacke-strength.csv` and `wellington-greywacke-depth-to-rock.csv`

Compiled on 1 October 2026 from T+T Site Search excerpts of project reports,
design calculations and letters; no file on the network drives was opened
directly. Every project behind them was checked in Site Search and none is
marked confidential. Only Wellington-region (Torlesse) greywacke is included;
Auckland, Northland, Coromandel, Waikato and Nelson jobs are left out, and
client names are not recorded.

- `source_type` is `published` (a paper or report T+T reports quote),
  `practice` (a convention those reports describe) or `tt_project`.
- `grade` normalises the weathering description: `RS` residual soil, `CW`,
  `HW`, `MW`, `SW`, `UW` and ranges between them (`CW-HW`), `COL` colluvium,
  `FILL` placed fill, `RM` a rock mass of unstated grade.
- `basis` says how the values were derived — back-analysis, laboratory,
  Hoek-Brown, correlation or judgement. Back-analysed values are the ones the
  landslide rebuild note prefers.
- **`check` is true where the excerpt was ambiguous.** Site Search returns
  tables flattened to text, and empty cells vanish, so a value can land in the
  wrong column. `note` says what is uncertain. Confirm those rows against the
  document before relying on them. For the GNS rows it marks a value the
  source contradicts elsewhere.
- `document` is the path of the source under the T+T corporate share, relative
  to its root, or the DOI for a published GNS report.

Most rows are design parameters for one slope or wall, not a regional ground
model; the published values most often quoted are O'Riley et al. (2006) and
Pender (1977), neither yet obtained.

Rows S48–S57 come from two GNS SLIDE (Wellington) reports, read from the PDFs
and checked against the page images on 1 October 2026:

- **SR2019/40** (Lyndsell, Carey & Bruce 2019), S48–S51: GNS's own drained direct
  shear tests on fill and buried colluvium at Orchy Crescent (intact core) and
  Priscilla Crescent (the <2 mm fraction, remoulded). Unit weights are converted
  from the reported bulk densities. All tests are drained and slow, at 50–400 kPa
  normal stress; nothing cyclic or undrained was reported.
- **SR2019/51** (Monteith 2020, prepared by Aurecon), S52–S57: the values GNS
  supplied for slope modelling of the same two fills and of the Ngauranga Gorge
  cut. Its colluvium (S53) disagrees with SR2019/40's (S50) for the same
  material, and both rows are flagged `check`.

The same two reports give unconfined compressive and Brazilian strengths of
Wellington greywacke and cataclasite core by weathering grade, which have no
column here.

Rows S58–S63 are Pender's (1980) consolidated undrained triaxial results for
highly and completely weathered greywacke from five central Wellington sites, 193
specimens grouped by void ratio. They are taken from Table 7 of the NZ
Geotechnical Society's Unit 7C.2 guidance on Torlesse greywacke (draft for
feedback, September 2025), checked against the page image on 2 October 2026.
Pender's own paper is not held. φ′ falls from 35.7° at void ratio 0.25–0.4 to
27.1° at 0.8–0.9. The lower 95% limit on c′ is zero or below for every class, and
the guide advises c′ = 0 under high groundwater. These rows give no unit weight,
so `strength_from_material` does not choose them.

**Which fill row the ground map reads.** S52 (22 kN/m³, c′ 2 kPa, φ′ 42°), the
value GNS supplied for modelling the Priscilla and Orchy Crescent fills, named
explicitly in `STRENGTH_GRADE_PICKS` in `landloss.hazard.landslide.ground_map`
(the lead, 2026-10-02). The pick rule alone would take S48, the first complete,
published, unflagged `FILL` row: φ′ 45.7° with c′ 0 from the first shear stage
of one intact core sample at Orchy Crescent, which densified over successive
stages and showed no peak. Both rows stay unflagged; the choice is the code's,
not the row order's.

In the depth table, `horizon` says what the depth is measured to (Scala
refusal, base of colluvium, top of CW–HW rock), because the reports differ.

## `retaining-wall-fragility.csv` (retired)

Retired on 6 October 2026, when the model moved to the wall type curves of
`retaining-wall-type-fragility.csv` (`.agents/plans/assigning-retaining-wall-types.md`).
It held one curve per `(wall_class, size_class, initial_condition)`, every
`wall_class` `unnamed`, read out of Koutsoupaki et al. (2023)
[koutsoupaki_2023] on DS3, *extensive* (`Ux = 10% of H`), with `modern` the
Fs = 1.5 family and `poor` the Fs = 1.1 family; the file is in the git history.
Two of its readings carry over to the type table:

- **Intensity measure**: the paper's PGA rows, not its PGV rows. The paper
  found PGA the most efficient of its measures, and its PGV medians carry the
  PGV/PGA ratio of its eight Greek rock-site records (about 50 to 80 cm/s per
  g), which is not Wellington's. The conversion to PGV is made at each wall
  with the study's own ratio from the shaking grids
  (`landloss.hazard.landslide.urban.fragility.pgv_pga_ratio_m_s_per_g`) and
  recorded on the model file.
- **Size**: `small` and `medium` took the 3 m wall, the lowest height
  published and the nearest to both; `large` took the 6 m wall. The type
  table keys on height class instead (below).

## `retaining-wall-type-fragility.csv`

Confirmed by the project lead (6 October 2026), and read by
`landloss.hazard.landslide.urban.fragility.assign_fragility` (landslide step 8) and
`landloss.vul.shaking.fragility.wall_failure_probability` (vul shaking step 9). One row per
`(wall_type, height_class)`, every pair present (14 rows). Each curve is stored as two
points on it: `p15` and `p50`, the free-field PGA (`im = pga_g`) at which 15%
and 50% of walls are replaced. The loader turns them back into a lognormal,
`theta = p50` and `beta = ln(p50 / p15) / 1.036`. `published_height_m` and
`published_fs` name the Koutsoupaki et al. (2023) [koutsoupaki_2023] curve each
row was read from (Tables A1 to A5, the 3 m wall R.W.3 or the 6 m wall R.W.6),
and `basis` gives the published median and dispersion, why the wall type takes
that rung, and the height rule.

**Height class** (the lead, 7 October 2026). The curve is chosen by the
wall's `height_m`, not its size class: `under_2_m` below 2.0 m (and where the
height is not known), `2_m_and_over` at 2.0 m and above
(`wall_type_fragility.height_class`). `size_class` stays on every wall and is
what the loss module prices on; only this lookup moved. `height_effect` says
which published height each class takes:

- `switched` (gravity masonry, old timber pole, block or RC cantilever,
  landscaper timber): taller walls of these types are the worse, so
  `under_2_m` takes the 6 m curve and `2_m_and_over` the 3 m curve, the
  opposite of the paper, whose taller wall is the stronger.
- `none` (crib, new timber pole, engineered modern): no height effect; both
  classes take the 3 m curve. The damage state is DS2, *moderate*,
`Ux = 5% of H`, not the DS3 the condition table reads: moderate damage usually
leads to full replacement in a claim (the lead, 6 October 2026).
`type_factor` scales both percentiles of a type's rung: 1.3 for new timber
pole and 1.5 for engineered modern, 1 otherwise; the stored percentiles
already include it. The rungs are
judgement, ordered by the Port Hills failure shares by type [anderson_2015]
[stone_2015]; `src/scripts/landloss/vul/research/fig_rw_type_fragility.md`
sets them beside the other published curves.

A wall retaining fill takes both percentiles times 0.85 and a wall retaining a
cut times 1.15 (`FILL_CAPACITY_FACTOR`, `CUT_CAPACITY_FACTOR`, the lead,
6 October 2026); the table holds the curve before that shift.

## `beta-retaining-wall-type-shares.csv`

Judgement placeholders set by the project lead (6 October 2026) for Nick
Peters to revise, then to check against the type mix in the claim reports
(T-50); the `beta` name says they are not yet evidence. One row per
`(age_bin, height_band)`, every pair present, and one column per wall type in
`WALL_TYPES` (`landloss.hazard.landslide.urban.wall_type_fragility`); each row
sums to 1. `age_bin` is one of the four bins of `landloss.exposure.rw.age`
(`src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`). `height_band`
is `under_1_5_m`, `1_5_to_2_5_m` or `over_2_5_m`: 1.5 m is the consent
threshold, which is what changes the type, so the bands differ from the size
classes on purpose. The fractions follow the finding that wall type tracked the
era a wall was built in [anderson_2015] and the lead's meeting with Nick
Peters; `.agents/plans/assigning-retaining-wall-types.md` (section 2) holds
the table they were copied from.

## `beta-retaining-wall-frontage-multipliers.csv`

Judgement placeholders set by the project lead (6 October 2026) for Nick
Peters to revise. One row per wall type, every type present. Where a wall
stands on a road frontage, its row of `beta-retaining-wall-type-shares.csv`
is multiplied by `road_frontage_multiplier` and renormalised: gravity masonry
and block or RC cantilever ×1.5, crib ×0.5, landscaper timber ×0.3, the rest
×1. Retaining walls on a road boundary hold up driveways, garages and footpath
cuts, so they are more often the heavier types.

## `urban-fragility-anchors.csv`

One row per anchor point. `measure` says what its `fail_fraction` is a share
of (below). A zone anchor has a Kingsbury `zone` or a susceptibility rating
range (`rating_min`, `rating_max`). A polygon anchor has the polygons it
applies to: `applies_to` (`all`, `cut` or `fill`, matched to the cut or fill
position of the polygon's wall unit), `slope_min_deg` (exclusive) and
`slope_max_deg` (inclusive), and `material` (blank for any). Every row also
has a `scenario` with its demand (`pga_rock_g_min`, `pga_rock_g_max`), where
that PGA was measured (`demand_at`), the source's failure `class_word`, the
`fail_fraction` that word is read as, and `set_by` and `basis` recording who
set the fraction and why. `source` is a `doc/references.bib` key or a GNS
finding id.

The rows are the anchors of section 6 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`,
revised with the project lead on 2026-10-07. Step 8 does not read this file.
The urban validation
(`src/scripts/landloss/hazard/landslide/validations/urban/`) draws the curves
against it and fits the localised median to it.

- `A01` to `A15` are Table 1 of [kingsbury_1995], the five susceptibility
  zones against the three scenarios. The scenario PGA on rock comes from its
  Table 7: scenario 1 (MM V-VI) is 0.02 to 0.06 g, the intermediate scenario
  (MM VII-VIII) 0.1 to 0.2 g and scenario 2 (MM IX-X) 0.5 to 0.8 g. Each
  zone's rating range is its band in
  `landloss.hazard.landslide.susceptibility.ZONE_BREAKS`. `A15` (very
  severe) is 0.4, not 0.5: about a tenth of very severe damage comes from
  large landslides, which the urban model excludes (the project lead).
- `A16` is the Wellington low-demand record (Kaikōura 2016, 0.15 g on rock,
  no urban failures recorded). Its measure is `zone_area` and it is read on
  the whole non-flat urban ground.
- `A17` to `A21` are the GNS findings for cuts and fills, revised as polygon
  anchors: the Port Hills (cut and fill polygons), cuts steeper than 50
  degrees, cuts steeper than 45 degrees, 45 to 50 degree cuts on rock, and
  fills. `A17`'s 1 to 2 g were recorded at strong motion stations
  (`demand_at` `site`). They already carry the site and topographic
  amplification, so the comparison uses the polygon's site PGV/PGA ratio and
  does not apply the amplification factor again.
- The 2013 Cook Strait findings (`sr2013-042-F03`, `F04`, `F11`) are not rows,
  because the plan gives no rock-site demand for them.

**What a fraction measures.** For a `zone_area` anchor it is the share of the
Kingsbury zone's non-flat area that small failures damage, not the share of
polygons. Damaged ground is the union of the evacuated and inundated zones,
and the area calibration (`landloss.hazard.landslide.urban.area_calibration`)
computes its expected share. Kingsbury's zones include runout (his section
4.4.2), but runout onto flat land is not counted. For a `polygon` anchor the
fraction is the share of the matching polygons that fail. Kingsbury's zoning
leaves seismically designed retained slopes out of the high category, so his
High fractions describe unretained or poorly retained ground. They apply to
the bare (no wall) model unchanged.

**The class-word-to-fraction reading is judgement, not a measurement**, and
every row says so in `set_by`. Kingsbury's classes are read as very minor
0.005, minor 0.02, significant 0.08, severe 0.25 and very severe 0.4. The GNS
findings' own words (`none_recorded`, `many`, `widespread`, ...) are read the
same way. The validation table
`report/hazard/landslide/urban-fragility/tab/urban-fragility-anchors.csv`
lists the words and fractions for the report. The project lead changes a
number by editing this file.

Kingsbury's words rise more slowly with demand than a lognormal at the model's
dispersion of 0.6 (`LOCALISED_FRAGILITY_BETA`), so the area calibration fits
the dispersion together with the median's scale. The first run (2026-10-07)
showed two problems:

1. On the wlg-pilot the bare footprints cover only 20% of the non-flat
   ground. `A12`'s 0.25 is therefore out of reach when the whole pilot is
   the reference.
2. `A16` (0.001 at 0.15 g) contradicts `A10` and `A11` (0.02 and 0.08 at
   0.02 to 0.2 g) on the same ground.

**Which anchors set the curve (the project lead, 2026-10-07).** After that
run the lead chose to fit the localised curve to two kinds of anchor:

1. `A16`, the Kaikōura record, as the expected damaged share of the whole
   non-flat ground at 0.15 g on rock. It weighs as much as the polygon
   anchors together.
2. The polygon anchors `A17` to `A21`, as the mean failure probability of
   the matching bare polygons.

Implemented in `area_calibration.fit_record_and_polygons`. `A12`
(Kingsbury High, scenario 2) is an upper limit the curve must stay under,
not a target. `A01` to `A11` and `A13` to `A15` are kept as checks.

The reasons:

1. Kingsbury's scenario 1 and intermediate classes conflict with the
   Kaikōura record.
2. They describe stream-bank, natural-slope and loose-rock failures, while
   the polygon anchors describe the urban cuts and fills the model draws.

`urban_area_calibration_findings.md` beside the validation scripts has the
details.

## `landslide-slope-thresholds.csv` and `landslide-seed-thresholds.csv`

The numbers the slope elements (`landloss.hazard.landslide.slope_elements` and
`instability_zones`) are found with, kept here so they can be read and edited in
one place. The code reads them when it is imported, so a changed value needs the
script run again, and the loaders reject a table that is malformed. Edit the
numbers, not the columns or the group names.

**Seed instability zones (the current method).** A pif (a cluster of pips, the
cells that drop 0.7 m per metre at 1, 3 and 5 cells) is a siz if either:

- **The near step**, `adjacent_step_m` in `landslide-seed-thresholds.csv`: some
  pair of its points less than 3 m apart differs in height by at least this for
  its ground group (0.7 m soil, 3.0 m weak and stronger rock, so that a 1 to 2 m
  rock wall is not a siz).
- **The far angle**, `landslide-slope-thresholds.csv`: some pair of its points at
  least 3 m apart is steeper than the group's angle for the pair's height band.
  The file is one row per band; `height_from_m` is the band's lower edge and
  there is one column of angles in degrees per ground group. As shipped the bands
  are under 3.5 m (35, 45, 53 degrees for soil, weak rock and stronger rock) and
  3.5 m and over (32, 40, 48), and the code requires exactly two. Fill is soil.

`min_step_height_m` and `bank_min_slope_deg` in `landslide-seed-thresholds.csv`
belong to the old seeding (`find_slope_elements`), which is kept only for the toy
figures and is to be retired. The rest of this section describes that old
seeding and the slope table's earlier eight-band form.

A cell was eligible as a seed in the old seeding on **either** of two tests:

- **The step test**, `min_step_height_m` in `landslide-seed-thresholds.csv`: the
  cell's step height is at least this for its ground group. One row for each of
  `soil_like`, `weak_rock` and `stronger_rock`, and no value under
  `MIN_WALL_HEIGHT_M` (0.5 m), because an element lower than that is dropped. All
  three are 0.5 m as shipped.
- **The slope test**, `landslide-slope-thresholds.csv`: the cell's 3 m slope is
  over the angle its ground group stands unsupported at. The angle depends on how
  tall the step is, so the file is one row per height band. `height_from_m` is the
  band's lower edge (a band runs to the next row's edge, the last has no top) and
  there is one column of angles in degrees for each ground group. A cell with no
  step reads the first row.

The same table decides, once an element has grown, whether it is a free-face (its
overall angle is over the angle for its group and band) or a bank (under it). The
ground group of each ground map material is `MATERIAL_GROUND_GROUP` in
`slope_elements.py`; `rock` is `weak_rock`, `rock_uw_mw` is `stronger_rock`, and
ground off the map is `weak_rock`.

The shipped bands and angles are the plan's, phase 1
(`.agents/plans/building-face-based-urban-slope-polygons.md`), confirmed by the
project lead on 2026-10-02. The band edges are `MIN_WALL_HEIGHT_M` and the
small/medium costing break (0.5, 1.0), the Building Act consent exemption
[nz_parliament_2004] and Anderson et al.'s classes [anderson_2015] (1.5, 2.5,
3.5), and NZGS Figure 35 [nzgs_2025_torlesse] (6, 10, 16). The rock angles are
Figure 35's maximum unsupported cut angles near Wellington housing, 1 on 1 to
10 m and 2 on 3 to 16 m for highly and completely weathered rock and 4 on 3 to
6 m for moderately weathered, converted to degrees by us. The soil-like 35 degrees
is judgement.

Cells that pass neither test can still seed a **bank**: any ground whose 3 m and
1 m slopes are at least `bank_min_slope_deg` in `landslide-seed-thresholds.csv`
for its ground group, and that no free-face has claimed. This is not the slope
test above and does not use the rock table; it is why a long rock hillside reads
as one big bank. Raise a group's value to stop its gentler ground seeding banks.
All three are 18.4 degrees as shipped (`BETA_GROW_ANGLE_DEG`), which is also the
lowest value accepted, because ground gentler than that is dropped later
anyway; the upper limit is 90.

Not in these files: the other `BETA_` settings and the step estimator. They are
constants in `slope_elements.py`.

## `wall-probability-points.csv`

The points that set the probability that a landslide step 12 wall candidate is
a retaining wall (`wall_units.gen_wall_points`; the lead, 2026-10-07; the plan
is `.agents/plans/wall-probability-points.md`). One row per bin:

- `attribute`: what is scored. `verticality`, `height` (`height_m`), `length`
  (`length_m`) and `building` (`building_m`) are numeric; `setting`
  (`road_frontage`, else `property_boundary`), `class` (landslide step 13's
  `fill`, `cut_and_fill`, `natural`), `rock_cut`, `soil_cut`, `age` and
  `nhc_land_attrs` are categories.
- `bin`: the bin's name, shown in each candidate's `wall_points_explain`. For
  `age` it names the share column (`p_<bin>`) of exposure rw step 6's wall age
  table.
- `lower`, `upper`: a numeric bin is `lower <= value < upper`; a blank is open.
  For `rock_cut`, `lower` is the depth a cut in rock must exceed.
- `points`: added to the candidate's total; `age` points are weighted by the
  property's share in each bin.
- `reason`: why, with the pilot's GNS rate where it informed the value.

The total sets the probability on a logistic scale:
`BETA_WALL_POINTS_PER_DOUBLING` points double the odds from `BETA_WALL_BASE_P`
at 0 points (`landloss.domain.constants`). Every value is judgement until the
claim reports calibrate it. An attribute the scoring does not read stops the
run.
