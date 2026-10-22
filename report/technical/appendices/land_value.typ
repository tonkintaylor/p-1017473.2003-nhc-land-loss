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

#import "../lib.typ": inputs-table, limitations-table, model-figure, num, pct, review

#let d = yaml("/report/loss/qv-land-value/tab/report-numbers.yaml")
#let s = d.settings
#let src = d.sources
#let r = d.rates
#let ex = d.examples.valuer
#let ty = d.examples.typical
#let money(x) = [\$#num(x)]
#let rate(x) = [\$#num(x)/m²]

= Calculation of land value <land-value>

== Context

This appendix describes how the model puts a value per square metre on damaged
insured land, which makes up the main part of the land cover cap. How much land
is damaged comes from @liquefaction and @landslide-damage. The comparison with
the cost of repair is in @cost-estimation.

Each property's land value is taken from its QV rating valuation, brought to
1 September 2025. Land value is not spread evenly across a property: the land
under the house, for example, is worth more than the garden. If the QV land
value is averaged over the whole section, it undervalues the ground under and
around the house, where damaged insured land lies, and overvalues the garden,
bush or paddock. This is more noticeable for larger properties. NHC has advised
that it has no set rule for valuing part of a section, but that valuers apply a
higher rate to the land under and around the dwelling. For the purpose of this
work, the model spreads each property's land value over three tiers that step
down from the house, and values damaged land at the rate of the tier it lies
in.

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
Index for the greater Wellington region (@lv-index).#footnote[The annual change
  in value is QV's own, from its published House Price Index: it is
  interpolated between QV's published changes for the 12 months to July 2025
  and to October 2025, and compounded monthly over the time from each council's
  revaluation to 1 September 2025.]

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

A property whose land value cannot be read off the rating roll takes the median
land value of the properties in its suburb. A property whose rating units are
all non-residential, such as a reserve or a commercial site, is not counted as
a claim. Most such properties are reached only by the edge of a neighbour's
house, which is counted on the neighbour's own property. Land a title shares with others,
such as an access lot or a subdivision's reserve, is left out of the property's
area. The QV land value is taken as including GST.

=== Three tiers of land

Each property's land is split into three tiers, stepping down from the house
(@lv-tiers). The rate under the house, $R$, is set so that the three tiers add
back to the property's land value $V$:

$ R = V / (A_"house" + #s.insured_ratio A_"insured" + #s.uninsured_ratio A_"rest") $

where $A_"house"$ is the area of the building footprints, $A_"insured"$ is the
rest of the insured land and $A_"rest"$ is the rest of the section, up to a
maximum of #num(s.max_uninsured_m2) m².

#figure(
  table(
    columns: 3,
    align: (left, left, right),
    table.header([*Tier*], [*Land*], [*Rate*]),
    [1], [Under the house: the building footprints on the property], [$R$],
    [2], [The rest of the insured land: the land around the house and the
      accessway], [$#s.insured_ratio R$],
    [3], [The rest of the section, up to #num(s.max_uninsured_m2) m²],
    [$#s.uninsured_ratio R$],
    [--], [Any land beyond that], [Nil],
  ),
  caption: [The three tiers each property's land value is spread over.],
) <lv-tiers>

The ratios of #s.insured_ratio and #s.uninsured_ratio were calibrated with a
valuer, who reviewed the example in @lv-example-valuer and expected that, on a
#num(ex.area_m2) m² section with land worth #money(ex.value), roughly half of
the value lies under the house: about \$300,000, or about \$2,000/m². The
ratios first proposed, 0.5 and 0.15, put only about
#money({
  let full = ex.value / (ex.footprint_m2 + 0.5 * ex.ring_m2 + 0.15 * calc.min(ex.outer_m2, s.max_uninsured_m2))
  calc.round(full * ex.footprint_m2, digits: -3)
}) there.#footnote[The valuer reviewed this one example section, on 13 October
  2026; the ratios have not been checked against other sections.]

#review[Virginie suggests the valuer's review be described in a footnote, with
John to advise on how to name or describe the valuer and the review. The
footnote above is a placeholder until then.]

On a small section, where the insured land covers most of the property, there
is little land in the third tier to take value, and the rates come close to the
section's average. The third tier is counted up to
#num(s.max_uninsured_m2) m², the minimum-sized site in the Act; land beyond it
is treated as bare land outside the cover and valued at nothing.#footnote[Without
  that limit, a lifestyle block of tens of hectares would spread its value over
  every paddock and leave the land around its house at a few dollars a square
  metre.]

=== Valuing damaged land

The model counts only damage within the insured land. Damage elsewhere on the
property contributes nothing to the land cover cap. Only the first two tiers
therefore value damaged land, as follows:

- Landslide damage is located on the property, so the part of it under the
  house is valued at $R$ and the rest at $#s.insured_ratio R$.
- Liquefaction damage has no location within the insured land, so it is valued
  at the insured land's average rate: the first two tiers together, weighted by
  area. That is its expected value if the damage is spread evenly over the
  insured land.
- Where a property has both landslide and liquefaction damage, its damaged area
  is taken as the larger of the two, and valued at the rate of the cause that
  damaged it.

=== Examples

@lv-example-table demonstrates an example for a #num(ex.area_m2) m² section with
land worth #money(ex.value), a #num(ex.footprint_m2) m² house and
#num(ex.ring_m2) m² more of insured land, which is graphically represented in
@lv-example-valuer. Liquefaction damage on it would be valued at
#rate(ex.insured_rate), the insured land's average, compared to the section
average of #rate(ex.average_rate).

#figure(
  table(
    columns: 4,
    align: (left, right, right, right),
    table.header([*Tier*], [*Area (m²)*], [*Rate*], [*Value*]),
    [Under the house], num(ex.footprint_m2), rate(ex.footprint_rate),
    money(ex.footprint_m2 * ex.footprint_rate),
    [Rest of the insured land], num(ex.ring_m2), rate(ex.ring_rate),
    money(ex.ring_m2 * ex.ring_rate),
    [Rest of the section], num(ex.outer_m2), rate(ex.outer_rate),
    money(calc.min(ex.outer_m2, s.max_uninsured_m2) * ex.outer_rate),
    [Whole section], num(ex.area_m2), rate(ex.average_rate), money(ex.value),
  ),
  caption: [The three tiers on a #num(ex.area_m2) m² section with land worth
    #money(ex.value), including GST.],
) <lv-example-table>

#model-figure(
  d.figures.valuer,
  [The three tiers on the #num(ex.area_m2) m² section of @lv-example-table.
    Each bar is a tier: its width is the tier's area and its height the rate it
    is valued at per m².],
) <lv-example-valuer>

@lv-example-typical shows how the land value would be distributed on a more
typical #num(ty.area_m2) m² section with land worth #money(ty.value). The
section takes the median area, house and insured land of the properties in the
study area, at the median average rate. On it, the tiers put
#pct(ty.footprint_value / ty.value) of the land value under the house.

#model-figure(
  d.figures.typical,
  [The three tiers on a typical section of #num(ty.area_m2) m² with land worth
    #money(ty.value). Each bar is a tier: its width is the tier's area and its
    height the rate it is valued at per m².],
) <lv-example-typical>

== Results

Of the #num(src.claims) insured properties in the four territorial
authorities, #num(src.by_source.at("qv")) take their land value from the
rating roll and #num(src.by_source.at("suburb median", default: 0)) from their
suburb's median. A further #num(src.non_residential) properties on
non-residential land only are not counted as claims.


@lv-rates gives the median rates over the #num(r.properties) properties that
take their land value from the rating roll, by the size of the property.

#let bands = r.by_area.pairs()
#figure(
  table(
    columns: 5,
    align: (left, right, right, right, right),
    table.header(
      [*Property area*], [*Properties*], [*Average rate*],
      [*Liquefaction rate*], [*Under the house*],
    ),
    ..bands.map(((band, b)) => (
      band, num(b.properties), rate(b.average_rate), rate(b.insured_rate),
      rate(b.footprint_rate),
    )).flatten(),
    [All], num(r.properties), rate(r.overall.average_rate),
    rate(r.overall.insured_rate), rate(r.overall.footprint_rate),
  ),
  caption: [Median rates by property area, including GST: the property's
    average rate, the rate liquefaction damage is valued at, and the rate under
    the house.],
) <lv-rates>

== Limitations and future improvements

// T-153 / L-79, L-78, L-80, liquefaction average, both causes, 4,000 m² cap,
// T-24.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @lv-limitations-table lists each, its likely effect on the
modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [The tier ratios are judgement, following a discussion with one valuer,
        and have not been validated more widely or for a range of property
        sizes.],
      [*Unknown.*],
      [Have a registered valuer review the tier ratios across a range of
        sections, including typical suburban ones.],
    ),
    (
      [The values are rating valuations, not market valuations of damaged land.
        NHC uses adjusted rating values to settle claims only for uniform land
        affected by flooding or inundation, not for landslide claims.],
      [*Unknown.*],
      [Agree the use of rating valuations with NHC.],
    ),
    (
      [Liquefaction damage is valued at the insured land's average rate,
        because the model does not predict where on the insured land it
        lies.],
      [*Mixed.* Correct on average, but over or under for any one property.],
      [Value liquefaction damage by where it lies on the property, if the
        damage model is extended to locate it.],
    ),
    (
      [Where a property has both landslide and liquefaction damage, the larger
        damaged area and its cause's rate are used, rather than each valued
        separately.],
      [*Under-prediction* where the two damage different parts of the insured
        land.],
      [Combine the two causes by location, but this can only be done if the
        location of liquefaction damage on the property can be identified.],
    ),
    (
      [The #num(s.max_uninsured_m2) m² limit on the third tier is a
        judgement.],
      [*Unknown.* It affects only properties larger than about
        #num(s.max_uninsured_m2) m².],
      [Confirm the limit with a registered valuer.],
    ),
    (
      [One regional house price index brings all four councils' values to a
        common date, although values in each council moved differently.],
      [*Mixed.*],
      [Agree the index factors with a registered valuer.],
    ),
    (
      [Values are brought to 1 September 2025, not to the date of this study
        (the fourth quarter of 2026).],
      [*Unknown.* It depends whether property prices have risen or fallen since
        September 2025.],
      [Update the adjustment to the current date, agreed with QV.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <lv-limitations-table>

#review[The impacts on losses in @lv-limitations-table are a first draft. Check the direction
given for each.]
