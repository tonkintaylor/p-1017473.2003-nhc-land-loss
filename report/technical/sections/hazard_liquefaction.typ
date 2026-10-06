// Liquefaction hazard. Numbers from:
//
//     uv run --frozen python src/scripts/landloss/hazard/liquefaction/report/gen_report_numbers.py

#import "../lib.typ": from-register, inputs-table, model-figure, num, pct

#let d = yaml("/report/hazard/liquefaction/tab/report-numbers.yaml")
#let s = d.settings
#let a = d.study_area
#let states = ("None", "Minor", "Moderate", "Major", "Severe", "Very Severe")

== Liquefaction <liquefaction>

=== Context

Liquefaction damages the flat land of the study area: the Hutt Valley floor, the
reclaimed and low-lying ground around the harbour, and the Porirua basin. NHC
settles that damage on the insured land of a property, and the Canterbury
earthquake sequence gives the costs of settling it per *land damage state*, a
six-step severity scale from None to Very severe. This module supplies, for one
modelled earthquake, the land damage state of every part of the flat land, which
the vulnerability module then reads at each property.

It does not model liquefaction itself. It takes the National Liquefaction
Model's (NLM) probabilities of land damage at the 2,500-year return period,
adjusts them for lateral spreading towards rivers, lakes and the coast, which
the NLM release does not yet include, and draws a state from them. The NLM
release in use (#d.meta.nlm_release) is built on the draft TS1170.5 demands, so
every probability here is provisional until it is rebuilt on the published
ones.

=== Inputs

#inputs-table(
  [P(at least Moderate) and P(at least Major) land damage, 100 m grids],
  [National Liquefaction Model release #d.meta.nlm_release; 2,500-year scenario,
    liquefaction severity number at the 50th percentile, median groundwater],
  [T+T, internal],
  [River name lines (rivers kept by name)],
  [LINZ NZ River Name Lines (Pilot), layer 103632], [CC BY 4.0],
  [River, lake, swamp and lagoon polygons],
  [LINZ Topo50, layers 50328, 50293, 50359 and 50292], [CC BY 4.0],
  [Coastline], [LINZ NZ Coastlines (Topo 1:50k), layer 50258], [CC BY 4.0],
)

=== Method

The module runs in three steps, each a script under
`src/scripts/landloss/hazard/liquefaction/steps/`:

+ *Free faces* (@liq-free-faces): the rivers, lakes and coast a laterally
  spreading block of ground moves towards.
+ *Land damage probabilities* (@liq-probabilities): the NLM's two exceedance
  grids, corrected for lateral spreading and expanded to the six states.
+ *Land damage states* (@liq-states): one state drawn per cell for each modelled
  earthquake.

==== Free faces <liq-free-faces>

The free faces are the NLM's own lateral spreading layer, rebuilt from the same
sources with the same filters, so this study and the NLM buffer the same ground.
A river is kept where its name line is named a river; rivers, lakes, swamps and
lagoons are kept as polygons of at least #num(s.min_free_face_area_ha) ha, the
threshold the NLM chose by testing which gave the clearest link between distance
and damage in Christchurch; and the coastline is kept whole. Each extent is read
#num(s.far_field_m) m wider than itself, so a free face just outside it still
counts.

==== Land damage probabilities <liq-probabilities>

The NLM supplies two exceedance probabilities per 100 m cell: P(at least
Moderate) and P(at least Major). They are first corrected for lateral spreading,
then differenced into bands and expanded to six states.

*Lateral spreading.* The free faces are buffered into a near zone, within
#num(s.near_field_m) m, a middle zone, #num(s.near_field_m) to
#num(s.far_field_m) m, and a far zone beyond. P(at least Major) is raised in
the near zone and lowered in the far one, following the NLM's piecewise
correction:

- *Near a free face*, it is multiplied by #num(s.near_multiplier) up to
  #num(s.knee, digits: 3) and raised by a fixed #num(s.near_lift_above_knee,
  digits: 2) above it.
- *Far from one*, it is divided by #num(s.far_divisor) up to
  #num(s.knee, digits: 3) and lowered by a fixed #num(s.far_drop_above_knee,
  digits: 2) above it.
- *In the middle zone*, it takes the midpoint of the two.

A cell takes the zones in proportion to its area in each, measured on a
#num(s.supersample) by #num(s.supersample) grid of sub-cells, because a 100 m
cell is as wide as the near zone. P(at least Moderate) is left as it is, and the
corrected P(at least Major) is capped at it, so the correction moves probability
between the Moderate band and the states above it rather than adding any.

*Six states.* The pair is differenced into three bands: None (below Moderate),
Moderate, and Major or worse. The release carries no Minor, Severe or Very
severe, so they are made by splitting bands in fixed shares: None is split
#pct(s.none_shares.None) None and #pct(s.none_shares.Minor) Minor, and Major or
worse #pct(s.major_shares.Major) Major, #pct(s.major_shares.Severe) Severe and
#pct(s.major_shares.at("Very Severe")) Very severe. Splitting conserves the
probability in each cell, and the step refuses a cell whose six do not sum to
one.

==== Land damage states <liq-states>

For each modelled earthquake, one state is drawn per cell from its six
probabilities, using one uniform random number compared against their running
total. The random numbers come from the earthquake's own seeded stream, so the
same earthquake number means the same event in the liquefaction, landslide and
shaking modules. A cell the NLM does not cover, which is all sloping land, stays
empty rather than taking state None.

=== Results

Over the study area, #num(a.cells_with_probability) cells, #num(a.area_with_probability_km2, digits: 1)
km#super[2], carry a probability. The rest is sloping land, which the NLM does
not cover and the landslide module does.

#figure(
  table(
    columns: 3,
    align: (left, right, right),
    table.header([*Free face*], [*Features*], [*Length or perimeter (km)*]),
    ..a.free_faces.pairs().map(((kind, f)) => (
      upper(kind.first()) + kind.slice(1), num(f.features), num(f.km, digits: 1),
    )).flatten(),
  ),
  caption: [The free faces over the study area.],
)

The lateral spreading correction lowers the mean P(at least Major) over the
study area from #pct(a.mean_p_major_or_worse_before, digits: 1) to
#pct(a.mean_p_major_or_worse_after, digits: 1): most of the flat land is far
from a free face, where it falls, while the ground near one rises sharply.
#if a.cells_capped == 0 [The cap at P(at least Moderate) never bound.] else [The
cap at P(at least Moderate) bound in #num(a.cells_capped) cells.]

#figure(
  table(
    columns: 4,
    align: (left, right, right, right),
    table.header([*Zone*], [*Cells*], [*NLM*], [*Corrected*]),
    ..a.by_zone.pairs().map(((zone, z)) => (
      upper(zone.first()) + zone.slice(1),
      num(z.cells),
      pct(z.mean_p_major_before, digits: 1),
      pct(z.mean_p_major_after, digits: 1),
    )).flatten(),
  ),
  caption: [Mean P(at least Major) per lateral spreading zone, before and after
    the correction.],
)

#model-figure(
  d.figures.zones,
  [The free faces and the lateral spreading zones over the study area.],
  script: "hazard/liquefaction/report/fig_lateral_spreading.py",
)

#model-figure(
  d.figures.change,
  [P(at least Major) before and after the correction, and the change, cell by
    cell.],
  script: "hazard/liquefaction/report/fig_lateral_spreading.py",
)

#figure(
  table(
    columns: 2,
    align: (left, right),
    table.header([*State*], [*Mean probability*]),
    ..states.map(state => (state, pct(a.mean_state_probability.at(state), digits: 1))).flatten(),
  ),
  caption: [Mean probability of each land damage state over the cells the NLM
    covers, after the correction.],
)

=== Validation

*The correction reproduces the NLM's.* A baseline P(at least Major) of 20%
becomes #pct(0.2 + s.near_lift_above_knee) near a free face and
#pct(0.2 - s.far_drop_above_knee) far from one, as on the NLM's calibration
figure, and the correction itself is drawn against it below.

#model-figure(
  d.figures.correction,
  [The corrected P(at least Major) against the NLM's, for each zone.],
  script: "hazard/liquefaction/report/fig_lateral_spreading.py",
  width: 65%,
)

#if d.draw != none [
  *The draw against the probabilities.* Over the
  #if d.draw.extent == "wlg-pilot" [Wellington pilot] else [study area],
  #num(d.draw.cells) cells were drawn for earthquake #d.draw.realisation_id.
  The table sets the share drawn in each state beside its mean probability over
  the same cells. A share drawn from #num(d.draw.cells) cells varies by its
  standard error from one earthquake to the next, so a gap of more than about
  two standard errors in a state is worth looking at.

  #figure(
    table(
      columns: 4,
      align: (left, right, right, right),
      table.header([*State*], [*Drawn*], [*Probability*], [*Standard error*]),
      ..states.map(state => {
        let x = d.draw.at(state)
        (state, pct(x.drawn, digits: 1), pct(x.expected, digits: 1), pct(x.standard_error, digits: 1))
      }).flatten(),
    ),
    caption: [Share of cells drawn in each state for one modelled earthquake,
      beside the mean probability it was drawn from.],
  )
]

Neither check tests the probabilities against observed damage. The NLM is
validated against the Canterbury earthquake sequence in its own report; nothing
in this study has yet tested it in Wellington.

=== Limitations

#from-register("Limitations", ("L-16", "L-52", "L-53", "L-54"))

=== Future improvements

#from-register("Tasks", ("T-88", "T-72", "T-48"))
#from-register("Questions", ("Q-19",))
