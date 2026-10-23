// Appendix: calculation of cost estimation. Written for readers of the
// technical report, who have not seen the code: say what the method does, not
// where it lives. Numbers from:
//
//     uv run --frozen python src/scripts/landloss/loss/report/gen_cost_report_numbers.py
//
// The calibration rows are those s3_repair_rate_calibration last wrote. The
// limitations and improvements carry their register IDs in comments.

#import "../lib.typ": inputs-table, limitations-table, num, pct, review

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

== Context

This appendix describes how the repair cost, and the undepreciated value that
feeds the land cover cap, are estimated for each kind of damage:

+ Retaining walls (@cost-walls).
+ Land damaged by landslides (@cost-landslide).
+ Land damaged by liquefaction (@cost-liquefaction).
+ Bridges and culverts (@cost-crossings).

The costs of each kind of damage on a claim are added together, with the
costs of running the job (@cost-on-costs). All costs are estimated excluding
GST, and GST at #pct(p.gst_rate) is added before they are compared with the
land cover cap. The land values in the cap are taken as already including GST
(@land-value), so the two are compared like for like. The costing tool rates are current prices; only the Canterbury
liquefaction costs, which are in #q.cost_year dollars, are escalated.

== Inputs

@cost-inputs-table lists the inputs to the cost estimate.

#figure(
  inputs-table(
    [Retaining wall and site clearing rates],
    [NHC's costing tool, as at #date(w.rates_as_at)], [NHC, supplied to the project],
    [Liquefaction land claim costs], [NHC's settled costs from the Canterbury
      earthquake sequence, claimants only], [NHC, supplied to the project],
    [Construction cost growth since 2011],
    [Stats NZ Labour Cost Index, construction salary and wage rates],
    [CC BY 4.0],
    [Bridge and culvert replacement cost], [T+T judgement], [--],
  ),
  caption: [Inputs to the cost estimate.],
) <cost-inputs-table>

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

The undepreciated value of a damaged wall is calculated by multiplying the
applicable unit rate for its existing wall type by its face area, with no
allowance for depreciation or age.

The repair cost is based on the wall type used for the repair. In most cases, a
failed wall is replaced with a timber pole wall of the required height. The
exception is a reinforced concrete block wall, which is replaced on a
like-for-like basis.

Because replacement walls are generally built to a more substantial standard
than the walls they replace, and this difference is not reflected in the unit
rates, a further #pct(w.spec_uplift) is added to the calculated repair cost.

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
  nothing in Canterbury (explained in @cost-validation);
- a fixed cost per claim, averaging #money(q.rates.per_claim_nzd), which
  varies from claim to claim.

A property in the None state costs nothing. The Canterbury costs exclude any
claim that included retaining wall, bridge or culvert repair, so they stand for
land repair alone. The rates are in #q.cost_year
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
come to #money(o.fees_total). NHC considered that total light, so a claim with
wall works is charged #pct(o.fees_share) of what its walls cost to build, or
#money(o.fees_min) if that is more. A share is used rather than the flat total because a large wall
needs more design, engineering and supervision than the flat fee allows, while
a small one still needs a consent. The same claims are charged #pct(o.mob_demob_share) of the walls
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
#let ex-fees = calc.max(o.fees_share * ex-wall, o.fees_min)
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

  The first #num(q.rates.volunteer_cleared_m2) m² of ejecta on each site is
  taken to have been cleared for nothing, as volunteers, notably the Student
  Volunteer Army, did across Canterbury. It is about the area of ejecta a
  Moderate site is given, and with it a Moderate claim costs no more than a
  Minor one, as the Canterbury medians show (@cost-liq-calibration). The fit
  is about as good for any area from 200 to 300 m².

  #review[You noted that the #num(q.rates.volunteer_cleared_m2) m² comes from
  the NHC costing spreadsheet as the area that can be cleared by hand. The
  copy of the costing tool (version 1.10) has an hourly rate for hand loading
  of inundation but no #num(q.rates.volunteer_cleared_m2) m² area, and the
  model records the figure as calibration judgement. Point to where the
  spreadsheet gives it, and that will be cited here.]
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

== Limitations and future improvements

// L-30, L-62/L-63, Q-10/L-29, Q-11, L-34, L-31, L-23/L-74, L-40, L-25, L-76;
// T-38, Q-10, Q-11, I-13, landslide schedule.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @cost-limitations-table lists each, its likely effect on the
modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [The wall rates are a snapshot of rates NHC revises every four months,
        and are thought more likely to be too low than too high. Fixed costs per
        job mean a small wall costs relatively more than its area suggests.],
      [*Under-prediction* of wall repair costs.],
      [Update the wall rates from NHC's costing tool at each four-monthly
        revision.],
    ),
    (
      [The site ratings are set from the driveway, the slope and the debris
        volume, with thresholds that are judgement, rather than from a site
        visit.],
      [*Unknown.*],
      [Replace the site rating thresholds with figures from NHC's cost
        assessors.],
    ),
    (
      [Each wall type is mapped to a single costing tool rate, from
        #money(calc.min(..w.types.filter(t => t.rate != none).map(t => t.rate)))
        to
        #money(calc.max(..w.types.filter(t => t.rate != none).map(t => t.rate)))
        per m², so the mapping is one of the larger assumptions in the wall
        costs.],
      [*Mixed.*],
      [Price walls with the costing tool's detailed build-up once wall
        dimensions are known well enough to justify it.],
    ),
    (
      [The #pct(w.spec_uplift) allowance for rebuilding to a higher standard is
        a flat judgement.],
      [*Unknown.*],
      [Confirm the allowance with NHC's cost assessors.],
    ),
    (
      [A partly damaged wall is rebuilt over its damaged length plus a margin;
        repairs short of rebuilding are not modelled.],
      [*Over-prediction* where a repair would do.],
      [Add a repair option for walls with minor damage.],
    ),
    (
      [The landslide reinstatement wall's height and length are set from the
        size of the landslide by judgement. Landslide land repair is costed as
        debris clearing and that wall only, rather than from a landslip repair
        schedule.],
      [*Unknown.*],
      [Price landslide land repair from T+T's landslip cost schedule.],
    ),
    (
      [The liquefaction costs are from Canterbury, escalated by a labour cost
        index only, and carry the effect of volunteers clearing ejecta for
        nothing.],
      [*Under-prediction* where volunteers would not be available.],
      [Replace the escalation with an index that follows plant and materials as
        well as labour.],
    ),
    (
      [The liquefaction costs exclude increased liquefaction and flooding
        vulnerability, which were a large share of what NHC paid in
        Canterbury.],
      [*Under-prediction* of liquefaction losses.],
      [Include increased vulnerability if it is brought into the study's
        scope.],
    ),
    (
      [Every bridge and culvert is priced at one span, since nothing gives each
        crossing's span.],
      [*Mixed.*],
      [Estimate each crossing's span from the watercourse width.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <cost-limitations-table>

#review[The impacts on losses in @cost-limitations-table are a first draft. Check the direction
given for each.]
