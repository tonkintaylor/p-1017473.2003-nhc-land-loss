// Appendix: calculation of liquefaction damage. Written for readers of the
// technical report, who have not seen the code: say what the method does, not
// where it lives. Numbers from two scripts, the hazard's (NLM to a land damage
// state per cell) and the land vulnerability's (a property's state to the
// ground it loses):
//
//     uv run --frozen python src/scripts/landloss/hazard/liquefaction/report/gen_report_numbers.py
//     uv run --frozen python src/scripts/landloss/vul/liquefaction/land/report/gen_report_numbers.py
//
// The figures are drawn by hazard/liquefaction/report/fig_lateral_spreading.py.
// The limitations and improvements are written out here rather than read from
// the project register, whose wording names code; each carries its register
// ID in a comment.

#import "../lib.typ": inputs-table, model-figure, num, pct, review

#let d = yaml("/report/hazard/liquefaction/tab/report-numbers.yaml")
#let s = d.settings
#let a = d.study_area
#let v = yaml("/report/vul/liquefaction/tab/report-numbers.yaml")
#let vs = v.settings
#let va = v.study_area
#let states = ("None", "Minor", "Moderate", "Major", "Severe", "Very Severe")
// A range drawn within, "low to high", or the one value where they are equal.
#let span(bounds, fmt) = if bounds.at(0) == bounds.at(1) { fmt(bounds.at(0)) } else [
  #fmt(bounds.at(0)) to #fmt(bounds.at(1))
]

= Calculation of liquefaction damage <liquefaction>

#review[The appendix runs to about six pages against the four agreed with
Maxim Millen; it is to be trimmed once the content is settled.]

== Context

Liquefaction damages the flat land of the study area: the Hutt Valley floor, the
reclaimed and low-lying ground around the harbour, and the Porirua basin. NHC
settles that damage on the insured land of a property, and an NHC claim report
records it as the ground lost: land evacuated, cracked, opened or spread, and
land inundated, covered by ejected sand and silt. This appendix describes how
the model gets from a simulated earthquake to that ground, for every insured
property on flat land, in two parts:

+ Hazard: the land damage state of every part of the flat land, on a six-step
  severity scale from None to Very Severe (@liq-lateral-spreading to
  @liq-states).
+ Damage: the evacuated and inundated land of each property, given its state
  (@liq-ground).

The damaged land is costed in @cost-estimation, and valued in @land-value.

The model does not simulate liquefaction itself. It takes the probabilities of
land damage at the 2,500-year return period from the National Liquefaction
Model (NLM) @tonkin_taylor_2026, applies the NLM's correction for lateral
spreading towards rivers, lakes and the coast, which has been developed for the
NLM but is not yet built into the probabilities it supplies, and, for each
simulated earthquake, samples a damage state for each part of the flat land
from the corrected probabilities. The version of the NLM used is built on the
draft TS1170.5 earthquake demands, so every probability here is provisional
until the NLM is rebuilt on the published ones.

#review[The NLM report is cited as v5.2 (May 2026) from the issued file's name;
the title, client and job number were read off the v5.0 title page. Check them
against the v5.2 title page.]

== Inputs

#inputs-table(
  [Probability of at least Moderate, and of at least Major, land damage, on a
    100 m grid],
  [National Liquefaction Model, 2026 pre-release update; 2,500-year return
    period, median liquefaction severity and median groundwater],
  [T+T, internal],
  [Named rivers], [LINZ NZ River Name Lines], [CC BY 4.0],
  [Rivers, lakes, swamps and lagoons], [LINZ Topo50 water polygons], [CC BY 4.0],
  [Coastline], [LINZ NZ Coastlines (Topo 1:50k)], [CC BY 4.0],
  [Land damage states and fragility curves],
  [Canterbury earthquake sequence land damage observations], [T+T, internal],
  [Descriptions of the land damage states],
  [Land observation categories, None to Very Severe @tonkin_taylor_2013],
  [Public report],
  [Insured land of each property], [This study's insured land extent], [--],
)

== Method

The NLM gives, for each 100 m grid cell of flat land, the probability of at
least Moderate land damage and the probability of at least Major land damage,
written below as P(≥ Moderate) and P(≥ Major). The model takes them through
four steps:

+ Lateral spreading (@liq-lateral-spreading): P(≥ Major) is corrected
  towards the rivers, lakes and coast that spreading ground moves towards.
+ Six land damage states (@liq-probabilities): the two corrected
  probabilities are expanded to all six states.
+ Sampling the states (@liq-states): in each simulated earthquake, each cell's
  state is sampled from its six probabilities.
+ Damaged ground (@liq-ground): each property's evacuated and inundated land
  follows from its state.

=== Lateral spreading <liq-lateral-spreading>

Damage is worse close to a free face, an open bank or shore that the ground
can spread towards. The NLM has a correction that accounts for the higher
damage states closer to free faces, but the probabilities in the version used
here do not yet include it, so the model applies the correction itself, in the
same way as the NLM.

#review[Check whether the NLM report describes the lateral spreading correction.
If it does, cite it here; if it is documented elsewhere, such as in the NLM
release notes, cite that instead.]

The free faces are those the NLM uses, rebuilt from the same LINZ
sources with the same rules, so this study and the NLM treat the same ground as
close to one. They are the watercourses named as rivers; the rivers, lakes,
swamps and lagoons of at least #num(s.min_free_face_area_ha) ha, the size the
NLM chose because it gave the clearest link between distance and damage in
Christchurch; and the whole coastline. Free faces up to #num(s.far_field_m) m
outside the study area are included, since they affect the ground just inside
it.

For the correction, the flat land is divided into three zones by its distance
from the nearest free face: a near zone within #num(s.near_field_m) m, a middle
zone from #num(s.near_field_m) to #num(s.far_field_m) m, and a far zone beyond
#num(s.far_field_m) m. Only P(≥ Major) is changed. It goes up in the near zone
and down in the far zone, by an amount that depends on how large it is to begin
with:

- Up to #pct(s.knee, digits: 1), the change is in proportion: the probability
  is multiplied by #num(s.near_multiplier) near a free face and divided by
  #num(s.far_divisor) far from one.
- Above #pct(s.knee, digits: 1), the change is a fixed amount:
  #num(s.near_lift_above_knee * 100) percentage points are added near a free
  face and #num(s.far_drop_above_knee * 100) are taken away far from one.

The two rules give the same result at #pct(s.knee, digits: 1), so the
correction has no jump there. In the middle zone, the corrected probability is
#if s.middle_far_weight == 0.5 [halfway between] else [a blend of] the near and
far values. @liq-correction-examples gives some examples.

#figure(
  table(
    columns: 4,
    align: (right, right, right, right),
    table.header(
      [*NLM P(≥ Major)*], [*Near zone*], [*Middle zone*], [*Far zone*],
    ),
    ..(0.03, s.knee, 0.2, 0.4).map(p => {
      let near = if p <= s.knee { p * s.near_multiplier } else { p + s.near_lift_above_knee }
      let far = if p <= s.knee { p / s.far_divisor } else { p - s.far_drop_above_knee }
      let middle = (1 - s.middle_far_weight) * near + s.middle_far_weight * far
      (pct(p, digits: 1), pct(near, digits: 1), pct(middle, digits: 1), pct(far, digits: 1))
    }).flatten(),
  ),
  caption: [Examples of the lateral spreading correction: P(≥ Major) from the
    NLM, and after the correction in each zone.],
) <liq-correction-examples>

A 100 m grid cell is as wide as the near zone, so many cells lie partly in two
zones. Such a cell takes a blend of the corrected values for those zones,
weighted by the share of its area in each.

P(≥ Moderate) is not changed, and the corrected P(≥ Major) is not allowed to
exceed it, since land cannot be more likely to suffer at least Major damage
than at least Moderate damage. The correction therefore moves probability
between Moderate and the more severe states, without changing the chance of at
least Moderate damage.

=== Six land damage states <liq-probabilities>

The two corrected probabilities divide each cell into three bands: below
Moderate, Moderate, and Major or worse. The NLM does not give Minor, Severe or
Very Severe, so they are made by splitting the bands in fixed proportions. The
proportions were determined by fitting land damage fragility curves, against
the liquefaction severity number (LSN) @tonkin_taylor_2013, for all six states
to the Canterbury earthquake sequence dataset; the fitted curves for at least
Moderate and at least Major match the NLM's own two.

The band below Moderate is split #pct(s.none_shares.None) None and
#pct(s.none_shares.Minor) Minor. Of the band at Major or worse,
#pct(s.major_shares.Severe + s.major_shares.at("Very Severe")) is at least
Severe and #pct(s.major_shares.at("Very Severe")) is Very Severe, which gives
#pct(s.major_shares.Major) Major, #pct(s.major_shares.Severe) Severe and
#pct(s.major_shares.at("Very Severe")) Very Severe. The proportions are the same
at every LSN, although the fitted curves show them changing with it. The six
probabilities of each cell still add up to one.

#review[Maxim Millen is tidying the figure of the fitted fragility curves for
the six states; it goes here once drawn.]

=== Sampling the states <liq-states>

For each simulated earthquake, each cell's state is sampled from its six
probabilities. A state with a 30% probability in a cell is the one sampled in
about 30% of simulated earthquakes, so over many earthquakes each state occurs
as often as its probability says. The same simulated earthquake is
used across the liquefaction, landslide and shaking parts of the model, so they
describe one consistent event. Sloping land, which the NLM does not cover, is
given no liquefaction state at all; landslides are modelled there instead.

=== Damaged ground <liq-ground>

Each insured property takes the state of the grid cell at a point inside its
insured land. A property on sloping land, outside the NLM, has no liquefaction
damage, which is different from the state None: None describes flat land that
could liquefy but showed no damage.

The ground a property loses is then sampled from the range for its state in
@liq-ground-ranges, with every value in the range equally likely. The ranges are based on the
semi-quantitative descriptions of the land damage categories
@tonkin_taylor_2013, each of which describes the cracking a state brings and
the share of the land covered by ejecta. Evacuated land is an area in m²,
because a state cracks much the same ground whatever the size of the section,
while inundated land is a share of the insured land, because ejecta spreads
over a fraction of it. Neither can exceed the insured land.

#figure(
  table(
    columns: 4,
    align: (left, right, right, right),
    table.header(
      [*State*], [*Evacuated (m²)*], [*Inundated (share of insured land)*],
      [*Does not claim*],
    ),
    ..states.map(state => (
      state,
      span(vs.evacuated_area_m2.at(state), x => num(x)),
      span(vs.inundated_share.at(state), x => pct(x)),
      pct(vs.drop_out_rates.at(state)),
    )).flatten(),
  ),
  caption: [The ground lost in each land damage state, sampled for each property
    with every value in the range equally likely, and the share of properties
    in each state that do not make a land claim.],
) <liq-ground-ranges>

#review[To check: the Moderate inundated share does not follow the descriptions.
#cite(<tonkin_taylor_2013>, form: "prose") describes Moderate as generally less
than 25% of the site covered with ejecta and Major as more than 25%, but the model
draws Moderate from 25% to 70%. The range was first set at 5% to 25% and raised
to 25% to 70% in the 30 September 2026 call. Either record why here, or bring the
range back in line with the description.]

Evacuated and inundated land overlap, since cracked ground is often also
covered by ejecta. The damaged area counts the overlap once: it is the
evacuated plus the inundated land, less #pct(vs.evacuated_overlap_share) of the
evacuated land (but no more than the inundated land), and never more than the
insured land. The damaged area is what the land is valued over and the repair
is costed from.

#review[The shares that do not claim in @liq-ground-ranges are placeholders
awaiting Virginie Lacrosse's figures. Decide whether to show them here or only
in @cost-estimation.]

Not every property in a damaged state goes on to make a claim. Whether each
property on flat land claims is sampled at the rate for its state in
@liq-ground-ranges, so that, for example, about
#pct(vs.drop_out_rates.Moderate) of properties in the Moderate state do not
claim; one that does not claim loses no ground. Whether a property claims, how
much ground it loses and its damage state are each sampled separately, so a
change to one does not alter the others.

== Results

=== Hazard

Over the study area, #num(a.cells_with_probability) grid cells,
#num(a.area_with_probability_km2, digits: 1) km#super[2], are flat land with a
probability of liquefaction damage. The rest is sloping land, which the NLM
does not cover and the landslide model does.

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

The lateral spreading correction lowers the average P(≥ Major) over the study
area from #pct(a.mean_p_major_or_worse_before, digits: 1) to
#pct(a.mean_p_major_or_worse_after, digits: 1): most of the flat land is far
from a free face, where it falls, while the ground near one rises sharply.
#if a.cells_capped == 0 [The corrected P(≥ Major) never reached P(≥ Moderate).] else [The corrected P(≥ Major) reached P(≥ Moderate), and was held there, in
#num(a.cells_capped) cells.]

#figure(
  table(
    columns: 4,
    align: (left, right, right, right),
    table.header([*Zone*], [*Grid cells*], [*NLM*], [*Corrected*]),
    ..a.by_zone.pairs().map(((zone, z)) => (
      upper(zone.first()) + zone.slice(1),
      num(z.cells),
      pct(z.mean_p_major_before, digits: 1),
      pct(z.mean_p_major_after, digits: 1),
    )).flatten(),
  ),
  caption: [Average P(≥ Major) in each lateral spreading zone, before and after
    the correction.],
)

#model-figure(
  d.figures.zones,
  [The free faces and the lateral spreading zones over the study area.],
)

#review[The legend of this map reads "River (named, or kept by ID)"; "kept by
ID" is a term from the code and should be reworded when the figure is redrawn.]

#model-figure(
  d.figures.change,
  [P(≥ Major) before and after the correction, and the change, cell by cell.],
)

=== Damage

Over the four territorial authorities, #num(va.on_grid) of the
#num(va.properties) insured properties are on flat land. For one simulated
earthquake, @liq-ground-results gives how many of them fall in each state, how
many claim, and the ground a claim in each state loses. In all,
#num(va.claims) properties claim, over #num(va.damaged_area_ha, digits: 1) ha of
damaged land.

#review[Lower Hutt's numbers here and in the tables below come from the
14 October 2026 build, whose Lower Hutt free faces cover only the old pilot box,
so its liquefaction damage is understated (the last limitation below). The fix
is held back because that build has been issued. Decide whether to keep these
numbers, with the limitation disclosed, or rerun Lower Hutt before the appendix
goes out.]

#figure(
  table(
    columns: 7,
    align: (left, right, right, right, right, right, right),
    table.header(
      [*State*], [*Properties*], [*Share*], [*Claims*],
      [*Evacuated (m²)*], [*Inundated (m²)*], [*Damaged (share)*],
    ),
    ..states.map(state => {
      let x = va.by_state.at(state)
      let has = x.claims > 0
      (
        state, num(x.properties), pct(x.share_of_on_grid, digits: 1), num(x.claims),
        if has { num(x.mean_evacuated_m2, digits: 1) } else [--],
        if has { num(x.mean_inundated_m2) } else [--],
        if has { pct(x.mean_damaged_share) } else [--],
      )
    }).flatten(),
  ),
  caption: [Properties on flat land in each land damage state for one simulated
    earthquake, their share of those on flat land, how many claim, and the
    average ground lost per claim, with the damaged area as a share of the
    insured land.],
) <liq-ground-results>

#figure(
  table(
    columns: 5,
    align: (left, right, right, right, right),
    table.header(
      [*Territorial authority*], [*Properties*], [*On flat land*], [*Claims*],
      [*Damaged land (ha)*],
    ),
    ..v.by_authority.pairs().map(((name, x)) => (
      name, num(x.properties), num(x.on_grid), num(x.claims),
      num(x.damaged_area_ha, digits: 1),
    )).flatten(),
  ),
  caption: [Insured properties, those on flat land, claims and damaged land per
    territorial authority, for the same earthquake.],
)

== Validation

The correction reproduces the NLM's: a P(≥ Major) of 20% becomes
#pct(0.2 + s.near_lift_above_knee) near a free face and
#pct(0.2 - s.far_drop_above_knee) far from one, as on the NLM's calibration
figure. The correction is drawn against the NLM's probability below.

#model-figure(
  d.figures.correction,
  [The corrected P(≥ Major) against the NLM's, for each zone.],
  width: 65%,
)

#if d.draw != none [
  The sampled states can also be checked against the probabilities they are
  sampled from. For one simulated earthquake over the four territorial
  authorities, the table compares the
  share of the #num(d.draw.cells) grid cells given each state with the average
  probability of that state over the same cells. Because the states are sampled,
  the share varies from one simulated earthquake to the next by about its standard error, so a
  gap of more than about two standard errors would point to a problem.

  #figure(
    table(
      columns: 4,
      align: (left, right, right, right),
      table.header([*State*], [*Simulated*], [*Probability*], [*Standard error*]),
      ..states.map(state => {
        let x = d.draw.at(state)
        (state, pct(x.drawn, digits: 1), pct(x.expected, digits: 1), pct(x.standard_error, digits: 1))
      }).flatten(),
    ),
    caption: [Share of grid cells given each state in one simulated earthquake,
      beside the average probability of that state.],
  )
]

Neither check tests the probabilities against observed damage. The NLM is
validated against the Canterbury earthquake sequence in its own report
@tonkin_taylor_2026; nothing in this study has yet tested it in Wellington. The
ground lost in each state is not validated directly either: it is tested only
through the repair costs it produces, against the Canterbury claim costs, in
@cost-estimation.

== Limitations

// L-16, draft demands, L-52, L-53, L-54, L-39 and L-44, T-64/Q-16, L-88.
- Ground conditions are the NLM's. The probabilities rest on the NLM's
  geology, geomorphology and groundwater, which simplify the ground and were
  accepted as a sensible base model rather than a precise one.
- The earthquake demands are provisional. The NLM version used is built on
  the draft TS1170.5 demands, and its probabilities will change when it is
  rebuilt on the published ones.
- Three of the six states are derived. Minor, Severe and Very Severe are made
  by splitting the NLM's two probabilities in fixed proportions, held the same
  at every LSN although the Canterbury curves show them changing with it.
- Damage is not clustered. Each grid cell's state is sampled independently of
  its neighbours', so
  the share of land in each state is right but the size of damaged patches is
  not: real liquefaction damage is clustered, while the simulated map is
  speckled.
- Free faces follow a rule, not geotechnical judgement. A channel named a
  stream is not a free face however deep its banks, and the whole coast is one,
  including rock and seawall coast that cannot spread.
- The ground lost in each state is judgement. The evacuated and inundated
  ranges are read from the descriptions of each state rather than fitted to
  observations, and the share of evacuated land lying under ejecta is an
  assumption.
- The share of properties that claim is provisional. The rates in
  @liq-ground-ranges are placeholders until figures from NHC's claims
  experience are available.
- Lower Hutt's free faces are incomplete. In the run reported here, Lower
  Hutt's free faces cover only a small part of the Hutt Valley, so most of
  Lower Hutt is treated as far from a free face and its liquefaction damage is
  understated.

== Future improvements

// T-167, T-54, NLM rebuild, L-53, T-48/Q-19, T-64/Q-16.
- Rerun Lower Hutt with free faces over the whole city.
- Take all six states from the NLM once it provides them, in place of the
  fixed split of two.
- Rebuild on the published TS1170.5 demands once the NLM is.
- Cluster the simulated damage, so that neighbouring land is damaged together
  as it is in an earthquake.
- Review the free faces: whether further watercourses with banks that can
  spread, such as the Waiwhetū Stream, which is not named as a river, should be
  added.
- Replace the share of properties that claim with figures from NHC's claims
  experience.
