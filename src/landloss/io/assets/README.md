# Packaged assets

Small, slow-moving reference data that ships with the `landloss` package, so a
day-to-day run does not have to download or re-derive it. Everything here is
committed. Nothing here is large enough to belong in a cache.

| Asset | What it is | Written by | Read by |
| --- | --- | --- | --- |
| `study-areas.geoparquet` | Territorial authority boundaries for the four study authorities, from Stats NZ via T+T's Koordinates instance | `src/landloss/io/one_offs/gen_study_extent.py` | `src/landloss/io/area_of_interest.py` |
| `land-value-base-rates.csv` | Published QV rating revaluation anchors per territorial authority, plus the two derived inputs the land value model needs | Maintained by hand — see below | `landloss.exposure.land.land_value.load_base_rates` |
| `land-value-factors.csv` | Landform multipliers and clip multiples for the land value model | Maintained by hand — see below | `landloss.exposure.land.land_value.load_factors` |
| `marc-2016-table-s1.csv` | Marc et al. (2016) Table S1, verbatim: the 40 earthquakes their total landslide area and volume expression was tested on | Converted from the supporting information's `.xls` (`context/lit/landslide/marc_2016/`) — see below | `src/landloss/io/one_offs/gen_marc_2016_table_s1.py` |
| `marc-2016-table-s1-subevents.csv` | The same table parsed to numbers, one row per earthquake or per sub-event of an earthquake sequence | `src/landloss/io/one_offs/gen_marc_2016_table_s1.py` | The landslide calibration (`.agents/plans/building-hancox-landslide-model-and-calibration.md`) |

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

The model divides a modelled land value by this to get a rate in $/m2. No
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

The clip multiples are judgement bounds, not researched figures. The model
re-solves the per-authority normalising constant after clipping and re-applies
the clip once, so clipping moves value between properties without changing the
authority's modelled mean.

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
