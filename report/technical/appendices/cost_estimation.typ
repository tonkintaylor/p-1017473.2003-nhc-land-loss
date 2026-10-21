// Appendix: calculation of cost estimation. Written for readers of the
// technical report, who have not seen the code: say what the method does, not
// where it lives. Numbers from:
//
//     uv run --frozen python src/scripts/landloss/loss/report/gen_cost_report_numbers.py
//
// The calibration rows are those s3_repair_rate_calibration last wrote. The
// limitations and improvements carry their register IDs in comments.

#import "../lib.typ": inputs-table, num, pct, review

#let d = yaml("/report/loss/costs/tab/report-numbers.yaml")
#let w = d.walls
#let l = d.landslide
#let c = d.crossings
#let o = d.on_costs
#let q = d.liquefaction
#let p = d.policy
#let money(x) = [\$#num(x)]
#let per-m2(x) = [\$#num(x, digits: 2)/m²]
#let date(s) = datetime(
  year: int(s.slice(0, 4)), month: int(s.slice(5, 7)), day: int(s.slice(8, 10)),
).display("[day padding:none] [month repr:long] [year]")

= Calculation of cost estimation <cost-estimation>

#review[The transcript budgeted about two pages for retaining walls and one for
liquefaction. This draft also covers landslide-damaged land and bridges and
culverts, which the model costs too. Trim once the content is settled.]

== Context

For each claim, the model estimates what the damage would cost to repair and
compares it with the land cover cap, which is built from the value of the
damaged land (@land-value) and the undepreciated value of any damaged retaining
walls, bridges and culverts. This appendix describes how the repair cost and
the undepreciated values are estimated for each kind of damage:

+ Retaining walls (@cost-walls).
+ Land damaged by landslides (@cost-landslide).
+ Land damaged by liquefaction (@cost-liquefaction).
+ Bridges and culverts (@cost-crossings).

The costs of each kind of damage on a claim are added together, with the
costs of running the job (@cost-on-costs), and GST is added.

== Inputs

#inputs-table(
  [Retaining wall and site clearing rates],
  [NHC's costing tool, as at #date(w.rates_as_at)], [NHC, supplied to the project],
  [Liquefaction land claim costs], [NHC's settled costs from the Canterbury
    earthquake sequence, claimants only], [NHC, supplied to the project],
  [Construction cost growth since 2011],
  [Stats NZ Labour Cost Index, construction salary and wage rates],
  [CC BY 4.0],
  [Bridge and culvert replacement cost], [T+T judgement], [--],
)

== Method

=== Retaining walls <cost-walls>

Walls are priced with the simple square-metre calculator in NHC's costing tool,
which NHC's cost assessors use to price land claims. Its rates are per square
metre of wall face, exclude GST, are derived by a quantity surveyor and are
revised every four months; the model uses those current on
#date(w.rates_as_at). Each wall type in the model is priced at one of the
tool's rates (@cost-wall-rates).

#figure(
  table(
    columns: 3,
    align: (left, left, right),
    table.header([*Wall type*], [*Costing tool rate*], [*Rate (\$/m²)*]),
    ..w.types.map(t => (
      t.label,
      if t.rate == none [Timber pole, by height] else [#t.rate_item],
      if t.rate == none [See @cost-timber] else [#num(t.rate, digits: 2)],
    )).flatten(),
  ),
  caption: [The costing tool rate each wall type is priced at, excluding GST.],
) <cost-wall-rates>

A timber pole wall needs a stiffer pile the more ground it retains, so its rate
follows its height (@cost-timber).

#figure(
  table(
    columns: 3,
    align: (left, left, right),
    table.header([*Retained height*], [*Pile*], [*Rate (\$/m²)*]),
    ..w.timber_bands.enumerate().map(((i, b)) => {
      let lower = if i == 0 { none } else { w.timber_bands.at(i - 1).below_m }
      (
        if lower == none [Under #num(b.below_m) m]
        else if b.below_m == none [#num(lower) m and over]
        else [#num(lower) to #num(b.below_m) m],
        [#b.item.split(": ").at(1)],
        num(b.rate, digits: 2),
      )
    }).flatten(),
  ),
  caption: [The timber pole wall rate by retained height, excluding GST.],
) <cost-timber>

#review[The height bands for the timber pile sizes were set as a first cut,
not taken from a design guide. Check whether they need a source.]

The undepreciated value of a damaged wall is the rate for its own type times
its face area, with no deduction for age. Its repair cost is that of the wall
it is rebuilt as. A failed wall is rebuilt as the timber pole wall its height
calls for, except a reinforced concrete block wall, which goes back like for
like. A replacement is built to a more substantial current standard than the
wall it replaces, which the rates do not allow for, so the repair cost carries
a further #pct(w.spec_uplift).

The face area is the wall's retained height times the length rebuilt: the
damaged length, plus #num(w.margin_m) m at each end to tie into the sound wall,
and at least #num(w.min_length_m) m. The undepreciated value is taken over the
same length, but never more than the wall's whole length.

The costing tool adds to a wall's cost for a difficult site, through three
ratings: construction access, earthworks required, and constructability and
reinstatement. Each is easy, moderate or difficult, adding
#pct(w.markup.E), #pct(w.markup.M) or #pct(w.markup.D), so a site difficult on
all three costs #pct(w.max_site_multiplier) more. The model has no site visit,
so it sets each rating from what it knows of the claim (@cost-ratings).

#figure(
  table(
    columns: 5,
    align: (left, left, left, left, left),
    table.header([*Rating*], [*Set from*], [*Easy*], [*Moderate*], [*Difficult*]),
    [Construction access], [The longest driveway on the property],
    [Up to #num(w.access_driveway_m.at(0)) m],
    [Up to #num(w.access_driveway_m.at(1)) m],
    [Over #num(w.access_driveway_m.at(1)) m],
    [Constructability], [The steepest ground at the property's addresses],
    [Up to #num(w.constructability_slope_deg.at(0))°],
    [Up to #num(w.constructability_slope_deg.at(1))°],
    [Over #num(w.constructability_slope_deg.at(1))°],
    [Earthworks required], [The volume of landslide debris to clear],
    [Up to #num(w.earthworks_m3.at(0)) m³],
    [Up to #num(w.earthworks_m3.at(1)) m³],
    [Over #num(w.earthworks_m3.at(1)) m³],
  ),
  caption: [How each site rating is set.],
) <cost-ratings>

#review[The thresholds in this table are judgement, set so the model could run,
and have not been confirmed by NHC. Decide whether to say so here as well as
in the limitations.]

=== Land damaged by landslides <cost-landslide>

Landslide debris on insured land is cleared at #money(l.spoil_rate_per_m3) per
m³, the costing tool's rate to load, cart and tip material, over the volume of
each landslide's debris on the land. Where a landslide removes ground and no
damaged wall held it, the model allows for a new timber pole wall to reinstate
the ground, priced as a rebuilt wall is above. Its height and length follow the
size of the landslide. Such a wall is a cost of the repair but never an asset
that was lost, so it adds nothing to the undepreciated value.

=== Land damaged by liquefaction <cost-liquefaction>

Liquefaction damage is costed from the ground lost (@liquefaction):

- #per-m2(q.rates.evacuated_nzd_per_m2) of evacuated land, cracked, opened or
  spread;
- #per-m2(q.rates.inundated_nzd_per_m2) of land covered by ejecta, beyond the
  first #num(q.rates.volunteer_cleared_m2) m², which volunteers cleared for
  nothing in Canterbury;
- a fixed cost per claim, averaging #money(q.rates.per_claim_nzd), which
  varies from claim to claim.

A property in the None state costs nothing. The rates are in #q.cost_year
dollars, excluding GST, and were set so that a #num(q.section_m2) m² section
losing the middle of each state's range of ground costs what NHC's Canterbury
claimants in that state typically cost (@cost-validation). They are brought to
today's prices by multiplying by #num(q.escalation, digits: 2), the growth in
the Stats NZ Labour Cost Index for construction salary and wage rates from the
March 2011 quarter to the December 2025 quarter.

#review[The #num(q.escalation, digits: 2) escalation was adopted as a
placeholder on instruction. It follows labour costs only, not plant and
materials. Check whether a better index is wanted before this goes out.]

=== Bridges and culverts <cost-crossings>

A damaged bridge or culvert is replaced at #money(c.rate_per_m) per metre of
span, over a span of #num(c.default_span_m) m, which is
#money(c.rate_per_m * c.default_span_m), since nothing gives each crossing's
span. One that is only covered by debris costs #money(c.clearing) to clear.
The undepreciated value is the replacement cost.

=== Costs of running the job <cost-on-costs>

The costing tool prices professional fees separately from the walls: consent,
design, engineering, health and safety, project management and survey, which
come to #money(o.fees_total). A claim with wall works is charged
#pct(o.fees_share) of what its walls cost to build, or #money(o.fees_total) if
that is more. The same claims are charged #pct(o.mob_demob_share) of the walls
and fees, at least #money(o.mob_demob_min), to set up and clear the site.
Project management is a further #pct(o.project_management_share) of the walls,
fees, site set-up and any bridge or culvert. A contingency of
#pct(o.contingency_share) goes on the whole repair of every claim, last. None of
these except the contingency is added to a liquefaction cost, which comes from
what NHC settled and so already stands for everything that claim cost.

#let ex-height = 1.5
#let ex-damaged = 6
#let ex-rate = w.timber_bands.at(1).rate
#let ex-length = calc.max(ex-damaged + 2 * w.margin_m, w.min_length_m)
#let ex-area = ex-height * ex-length
#let ex-site = w.markup.M + w.markup.E + w.markup.M
#let ex-wall = ex-rate * ex-area * (1 + ex-site) * (1 + w.spec_uplift)
#let ex-fees = calc.max(o.fees_share * ex-wall, o.fees_total)
#let ex-mob = calc.max(o.mob_demob_share * (ex-wall + ex-fees), o.mob_demob_min)
#let ex-pm = o.project_management_share * (ex-wall + ex-fees + ex-mob)
#let ex-before = ex-wall + ex-fees + ex-mob + ex-pm
#let ex-cont = o.contingency_share * ex-before
#let ex-total = ex-before + ex-cont

@cost-example works through a timber pole wall #num(ex-height, digits: 1) m
high that fails over #num(ex-damaged) m, on a site of moderate access, easy
earthworks and moderate slope. The costs of running the job are more than the
wall itself, which is typical of a small wall.

#figure(
  table(
    columns: 2,
    align: (left, right),
    table.header([*Item*], [*Cost (\$, excluding GST)*]),
    [Wall: #num(ex-area) m² at #per-m2(ex-rate), plus #pct(ex-site) for the
      site and #pct(w.spec_uplift) for the higher standard], num(ex-wall),
    [Professional fees], num(ex-fees),
    [Site set-up], num(ex-mob),
    [Project management], num(ex-pm),
    [Contingency], num(ex-cont),
    [*Repair cost*], [*#num(ex-total)*],
    [*Repair cost including GST*], [*#num(ex-total * (1 + p.gst_rate))*],
  ),
  caption: [The repair cost of a timber pole wall #num(ex-height, digits: 1) m
    high, failed over #num(ex-damaged) m and rebuilt over #num(ex-length) m.],
) <cost-example>

=== From repair cost to settlement

All costs are estimated excluding GST, and GST at #pct(p.gst_rate) is added
before they are compared with the land cover cap. The wall and the bridge and
culvert parts of the cap are each limited to #money(p.wall_sub_cap) and
#money(p.crossing_sub_cap) per dwelling. The settlement is the lesser of the
repair cost and the cap, less an excess of #money(p.excess_per_dwelling) per
dwelling, up to #money(p.excess_max).

== Validation <cost-validation>

#if q.calibration != none [
  The liquefaction rates were set against NHC's Canterbury claim costs.
  @cost-liq-calibration compares the median cost of a Canterbury claimant in
  each state with the modelled cost of a #num(q.section_m2) m² section losing
  the middle of that state's range of ground, both in #q.cost_year dollars.

  #figure(
    table(
      columns: 5,
      align: (left, right, right, right, right),
      table.header(
        [*State*], [*Canterbury claims*], [*Ground lost (m²)*],
        [*Canterbury median*], [*Modelled*],
      ),
      ..q.calibration.map(x => (
        x.state_name, num(x.canterbury_claims),
        [#num(x.section_evacuated_m2) evacuated, #num(x.section_inundated_m2) inundated],
        money(x.canterbury_p50_nzd), money(x.section_p50_nzd),
      )).flatten(),
    ),
    caption: [The median Canterbury claimant cost in each state against the
      modelled cost of a #num(q.section_m2) m² section, excluding GST.],
  ) <cost-liq-calibration>

  The fit is within about 10% from Minor to Severe. The modelled cost rises
  less steeply than Canterbury's beyond that, and is well below it for Very
  Severe, which had only
  #num(q.calibration.at(-1).canterbury_claims) Canterbury claims.
]

#if q.comparison != none [
  Applied to the properties of Lower Hutt with their own sections and sampled
  ground, the modelled median cost per claim is between
  #num(calc.min(..q.comparison.map(x => x.modelled_over_canterbury_p50)), digits: 2)
  and
  #num(calc.max(..q.comparison.map(x => x.modelled_over_canterbury_p50)), digits: 2)
  times the Canterbury median, state by state.
]

#review[The Lower Hutt comparison was run on 12 October 2026, before the
14 October build. Rerun it if these numbers are kept.]

The retaining wall, landslide and bridge and culvert costs have not been
checked against settled claims.

#review[Consider checking a sample of modelled wall repair costs against the
costs in T+T's claim reports, if time allows.]

== Limitations

// L-30, L-62/L-63, Q-10/L-29, Q-11, L-34, L-31, L-23/L-74, L-40, L-25, L-76.
- The wall rates are a snapshot of rates NHC revises every four months, and are
  thought more likely to be too low than too high. Fixed costs per job mean a
  small wall costs relatively more than its area suggests.
- The site ratings are set from the driveway, the slope and the debris volume,
  with thresholds that are judgement, rather than from a site visit.
- Each wall type is mapped to a single costing tool rate, from
  #money(calc.min(..w.types.filter(t => t.rate != none).map(t => t.rate))) to
  #money(calc.max(..w.types.filter(t => t.rate != none).map(t => t.rate))) per
  m², so the mapping is one of the larger assumptions in the wall costs.
- The #pct(w.spec_uplift) allowance for rebuilding to a higher standard is a
  flat judgement.
- A partly damaged wall is rebuilt over its damaged length plus a margin; repairs
  short of rebuilding are not modelled.
- The landslide reinstatement wall's height and length are set from the size of
  the landslide by judgement, and landslide land repair has no costing schedule
  of its own yet.
- The liquefaction costs are from Canterbury, escalated by a labour cost index
  only, and carry the effect of volunteers clearing ejecta for nothing.
- The liquefaction costs exclude increased liquefaction and flooding
  vulnerability, which were a large share of what NHC paid in Canterbury.
- Every bridge and culvert is priced at one span, since nothing gives each
  crossing's span.

== Future improvements

// T-38/L-30, Q-10, Q-11, T-27, I-13, landslide schedule, L-23.
- Update the wall rates from NHC's costing tool at each four-monthly revision.
- Replace the site rating thresholds with figures from NHC's cost assessors.
- Confirm whether the Canterbury liquefaction costs already include retaining
  wall, bridge and culvert damage, so they are not counted twice.
- Price walls with the costing tool's detailed build-up once wall dimensions are
  known well enough to justify it.
- Price landslide land repair from T+T's landslip cost schedule.
- Replace the liquefaction escalation with an index that follows plant and
  materials as well as labour.
