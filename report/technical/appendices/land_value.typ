// Appendix: calculation of land value. Written for readers of the technical
// report, who have not seen the code: say what the method does, not where it
// lives. Numbers from:
//
//     TTDRIVE_SYNC_LOCAL_MODE=True uv run --frozen python src/scripts/landloss/loss/report/gen_report_numbers.py
//
// The figures are drawn by loss/validations/gen_qv_average_rate.py. The method
// is written up in src/scripts/landloss/loss/qv_land_value_method.md. The
// limitations and improvements carry their register IDs in comments.
//
// The QV rating roll is sensitive: state only counts, medians and the worked
// examples, never a property's value.

#import "../lib.typ": inputs-table, model-figure, num, pct, review

#let d = yaml("/report/loss/qv-land-value/tab/report-numbers.yaml")
#let s = d.settings
#let src = d.sources
#let r = d.rates
#let ex = d.examples.valuer
#let ty = d.examples.typical
#let money(x) = [\$#num(x)]
#let rate(x) = [\$#num(x)/m²]

= Calculation of land value <land-value>

#review[This appendix was agreed at one to two pages, with about half a page
each of limitations and future improvements. Trim once the content is settled.]

== Context

NHC settles damage to insured land at the lesser of the cost of repair and the
land cover cap, and the main part of the cap is the value of the damaged
insured land. This appendix describes how the model puts a value per square
metre on damaged land. How much land is damaged comes from @liquefaction and the
landslide appendix; the comparison with the cost of repair is in
@cost-estimation.

Each property's land value is taken from its QV rating valuation. Dividing that
value by the property's area gives an average over the whole section, but on a
large section most of that area is garden, bush or paddock that adds little to
the value. The average therefore undervalues the ground under and around the
house, which is where damaged insured land lies. Valuers treat a section the
same way: the house site carries most of the value, and the rest of the section
is worth a fraction of its rate per square metre. NHC has advised that it has
no set rule for valuing part of a section, and that a higher rate should apply
to the land under and around the dwelling. The model therefore spreads each
property's land value over three tiers that step down from the house outwards,
and values damaged land at the rate of the tier it lies in.

== Inputs

#inputs-table(
  [Land value of each rating unit],
  [QV rating valuations for Wellington City, Lower Hutt City, Porirua City and
    Upper Hutt City], [QV, supplied to the project; sensitive],
  [Change in value since each council's revaluation],
  [QV House Price Index, greater Wellington region], [Published],
  [Property boundaries], [LINZ NZ Property Boundaries], [CC BY 4.0],
  [Building outlines], [LINZ NZ Building Outlines], [CC BY 4.0],
  [Insured land of each property], [This study's insured land extent], [--],
)

#review[Check the LINZ building outlines dataset name and licence against the
insured land write-up.]

== Method

=== Land value of each property

A property's land value is the sum of the land values of the rating units on
it. The four councils revalued on different dates in a falling market, so each
value is brought to a common date of 1 September 2025 using the QV House Price
Index for the greater Wellington region. QV published an annual change of
−4.5% for the 12 months to July 2025 and −3.3% for the 12 months to October
2025; between the two, the change for the 12 months to September 2025 is taken
as −3.7%, applied month by month from each council's revaluation date
(@lv-index).

#figure(
  table(
    columns: 3,
    align: (left, right, right),
    table.header([*Council*], [*Revaluation date*], [*Factor to 1 September 2025*]),
    ..s.councils.pairs().map(((name, c)) => (
      name,
      datetime(
        year: int(c.valuation_date.slice(0, 4)),
        month: int(c.valuation_date.slice(5, 7)),
        day: int(c.valuation_date.slice(8, 10)),
      ).display("[day padding:none] [month repr:long] [year]"),
      num(c.index, digits: 4),
    )).flatten(),
  ),
  caption: [The factor each council's rating land values are multiplied by to
    bring them to 1 September 2025.],
) <lv-index>

A property that is not on the rating roll, or is on it only as non-residential
units such as an institution's grounds or a commercial block, takes the median
land value of the properties in its suburb. Land a title shares with others,
such as an access lot or a subdivision's reserve, is left out of the property's
area. Land values exclude GST, which is added when the value is compared with
the cost of repair.

#review[This may not be correct. The model treats QV rating land values as
excluding GST and adds GST before comparing them with the cost of repair.
Confirm whether rating valuations include or exclude GST, and whether adding
it is right for the land cover cap.]

=== Three tiers of land

Each property's land is split into three tiers, stepping down from the house
(@lv-tiers). The rate under the house, _R_, is set so that the three tiers add
back to the property's land value _V_:

_R_ = _V_ ÷ (_A_#sub[house] + #s.insured_ratio × _A_#sub[insured] +
#s.uninsured_ratio × _A_#sub[rest])

where _A_#sub[house] is the area of the building footprints, _A_#sub[insured]
the rest of the insured land and _A_#sub[rest] the rest of the section, counted up to
#num(s.max_uninsured_m2) m².

#figure(
  table(
    columns: 3,
    align: (left, left, right),
    table.header([*Tier*], [*Land*], [*Rate*]),
    [1], [Under the house: the building footprints on the property], [_R_],
    [2], [The rest of the insured land: the land around the house and the
      accessway], [#s.insured_ratio × _R_],
    [3], [The rest of the section, up to #num(s.max_uninsured_m2) m²],
    [#s.uninsured_ratio × _R_],
    [--], [Any land beyond that], [Nil],
  ),
  caption: [The three tiers each property's land value is spread over.],
) <lv-tiers>

The ratios of #s.insured_ratio and #s.uninsured_ratio were calibrated to the
expectation that, on a #num(ex.area_m2) m² section with land worth
#money(ex.value), roughly half of the value lies under the house
(@lv-validation).

#review[The calibration rests on one valuer's expectation for one example
section. Does the source need to be more concrete than this, for example a
written opinion from the valuer, or published guidance on how land value is
spread across a section?]

On a small section, where the insured land covers most of the property, there
is little land in the third tier to take value, and the rates come close to the
section's average. The third tier is counted up to
#num(s.max_uninsured_m2) m², the minimum-sized site in the Act; land beyond it
is treated as bare land outside the cover and valued at nothing. Without that
limit, a lifestyle block of tens of hectares would spread its value over every
paddock and leave the land around its house at a few dollars a square metre.

=== Valuing damaged land

Damaged land is insured land, so only the first two tiers value it:

- Landslide damage is located on the property, so the part of it under the
  house is valued at _R_ and the rest at #s.insured_ratio × _R_.
- Liquefaction damage has no location within the insured land, so it is valued
  at the insured land's average rate: the first two tiers together, weighted by
  area. That is its expected value if the damage is spread evenly over the
  insured land.
- Where both damage the same insured land, the rate of the cause that damages
  more of it applies.

@lv-examples works the tiers through two sections. The first is
a #num(ex.area_m2) m² section with land worth #money(ex.value), a
#num(ex.footprint_m2) m² house and #num(ex.ring_m2) m² more of insured land.
The rate under the house is #rate(ex.footprint_rate), #money(ex.footprint_value)
in all; the rest of the insured land is #rate(ex.ring_rate) and the rest of the
section #rate(ex.outer_rate). Liquefaction damage on it would be valued at
#rate(ex.insured_rate), against a section average of #rate(ex.average_rate).
The second is a typical section, with the median area, house and insured land
of the properties in the study, at the median average rate: there
#pct(ty.footprint_value / ty.value) of the land value lies under the house.

#model-figure(
  d.figures.examples,
  [The three tiers on two sections. Each bar is a tier: its width is the
    tier's area and its height the rate it is valued at.],
) <lv-examples>

== Results

Of the #num(src.claims) insured properties in the four territorial
authorities, #num(src.by_source.at("qv")) take their land value from the
rating roll and #num(src.by_source.at("suburb median", default: 0)) from their
suburb's median, #num(src.non_residential) of them because they are on the roll
only as non-residential units.

@lv-rates gives the median rates over the #num(r.properties) properties on the
roll, by the size of the property. The correction factor is the rate damaged
land is valued at, as a multiple of the property's average rate. It is close to
one for liquefaction on small sections, where the insured land is most of the
section, and grows with the size of the section, as intended.

#let bands = r.by_area.pairs()
#figure(
  table(
    columns: 6,
    align: (left, right, right, right, right, right),
    table.header(
      [*Property area*], [*Properties*], [*Average rate*],
      [*Liquefaction rate*], [*Under the house*], [*Liquefaction factor*],
    ),
    ..bands.map(((band, b)) => (
      band, num(b.properties), rate(b.average_rate), rate(b.insured_rate),
      rate(b.footprint_rate), [#num(b.liquefaction_factor, digits: 2)×],
    )).flatten(),
    [All], num(r.properties), rate(r.overall.average_rate),
    rate(r.overall.insured_rate), rate(r.overall.footprint_rate),
    [#num(r.overall.liquefaction_factor, digits: 2)×],
  ),
  caption: [Median rates by property area, excluding GST: the property's
    average rate, the rate liquefaction damage is valued at, the rate under the
    house, and the median liquefaction correction factor.],
) <lv-rates>

== Validation <lv-validation>

A valuer reviewed the first of the two examples. With the ratios first
proposed, 0.5 and 0.15, the example put about
#money({
  let full = ex.value / (ex.footprint_m2 + 0.5 * ex.ring_m2 + 0.15 * calc.min(ex.outer_m2, s.max_uninsured_m2))
  calc.round(full * ex.footprint_m2, digits: -3)
}) of its land value under the house. The valuer expected about \$300,000
there, about \$2,000/m². One example fixes one combination of the two ratios,
not both: the rate on the rest of the insured land was kept near the
\$400/m² it had, and value was taken off the rest of the section, which gives
the ratios of #s.insured_ratio and #s.uninsured_ratio now used.

#review[The valuer's review (13 October 2026) is the only check of the ratios.
Name the valuer, or describe their role, if that can be shared.]

== Limitations

// T-153 / L-79, L-78, L-80, liquefaction average, both causes, 4,000 m² cap, T-24.
- The tier ratios are judgement, set from one valuer's example of a large
  section, and have not been checked on suburban sections, where they put
  #pct(ty.footprint_value / ty.value) of a typical section's value under the
  house.
- The values are rating valuations, not market valuations of damaged land. NHC
  uses adjusted rating values to settle claims only for uniform land affected
  by flooding or inundation, not for landslide claims.
- Liquefaction damage is valued at the insured land's average rate, because the
  model does not say where on the insured land it lies.
- Where landslide and liquefaction damage the same land, the rate of the larger
  applies to all of it.
- The #num(s.max_uninsured_m2) m² limit on the third tier is a judgement.
- One regional house price index brings all four councils' values to a common
  date, although values in each council moved differently.

== Future improvements

// T-153, T-24, L-80.
- Have a registered valuer review the tier ratios across a range of sections,
  including typical suburban ones.
- Agree the index factors with a registered valuer.
- Value liquefaction damage by where it lies on the property, if the damage
  model is extended to locate it.
