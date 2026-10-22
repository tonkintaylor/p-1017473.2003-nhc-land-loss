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
//
// Revised from Maxim Millen's review of 2026-10-21: his tracked changes taken
// in, his comments kept as review notes.

#import "../lib.typ": inputs-table, limitations-table, model-figure, num, pct, review

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

== Context

Liquefaction damages the flat land of the study area: the Hutt Valley floor, the
reclaimed and low-lying ground around the harbour, and the Porirua basin. Over
the study area, #num(a.cells_with_probability) grid cells,
#num(a.area_with_probability_km2, digits: 1) km#super[2], are flat land with a
probability of liquefaction damage. The rest is sloping land, which the
National Liquefaction Model (NLM) @tonkin_taylor_2026 does not cover. This
appendix describes the liquefaction component of insured land damage across two
modules:

+ Hazard: the land damage state of every part of the flat land, on a six-step
  severity scale from None to Very Severe (@liq-lateral-spreading to
  @liq-states).
+ Damage: the evacuated and inundated land of each property, given its state
  (@liq-ground).

The damaged land is costed in @cost-estimation, and valued in @land-value.

== Inputs

#inputs-table(
  [Probability of at least Moderate, and of at least Major, land damage, on a
    100 m grid],
  [National Liquefaction Model, 2026 pre-release update; 2,500-year return
    period and median groundwater],
  [Internal],
  [Named rivers], [LINZ NZ River Name Lines], [CC BY 4.0],
  [Rivers, lakes, swamps and lagoons], [LINZ Topo50 water polygons], [CC BY 4.0],
  [Coastline], [LINZ NZ Coastlines (Topo 1:50k)], [CC BY 4.0],
  [Land damage states and fragility curves],
  [Canterbury earthquake sequence land damage observations], [Internal],
  [Insured land of each property], [This study's insured land extent], [--],
)

== Method

The 100 m grid probabilities of at least Moderate and at least Major land
damage, P(≥ Moderate) and P(≥ Major), for the 2,500-year return period were
taken from the NLM as the starting point for this work, to align with the
2,500-year seismic hazard used in this study. The following steps were taken to
produce a realisation of the six land damage states:

+ Lateral spreading (@liq-lateral-spreading): P(≥ Major) is adjusted
  towards the rivers, lakes and coast that spreading ground moves towards.
+ Six land damage states (@liq-probabilities): the two adjusted
  probabilities are expanded to all six states.
+ Sampling the states (@liq-states): in each simulated earthquake, each cell's
  state is sampled from its six probabilities.
+ Damaged ground (@liq-ground): each property's evacuated and inundated land
  follows from its state.

=== Lateral spreading <liq-lateral-spreading>

Damage is worse close to a free face, an open bank or shore that the ground
can spread towards. The NLM project has an adjustment (in development) that
accounts for the increased probability of higher damage states closer to free
faces. This adjustment is applied to the baseline probabilities.

The choice of free faces is also still in development, as no single GIS layer
identifies them suitably. This study adopts the approach currently used in the NLM
lateral spreading pilot, rebuilt from the same LINZ sources with the same rules.
The free faces are the watercourses named as rivers; the rivers, lakes, swamps
and lagoons of at least #num(s.min_free_face_area_ha) ha (a size chosen in the
NLM because it gave the clearest link between distance and damage in
Christchurch), and the whole coastline. Free faces up to #num(s.far_field_m) m
outside the study area are included, since they affect the ground just inside
it. @liq-free-faces lists the free face features and their total lengths.

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
) <liq-free-faces>

For the adjustment, the flat land is divided into three zones by its distance
from the nearest free face: a near zone within #num(s.near_field_m) m, a middle
zone from #num(s.near_field_m) to #num(s.far_field_m) m, and a far zone beyond
#num(s.far_field_m) m. Only P(≥ Major) is changed. @liq-correction shows the
adjustment, where the NLM baseline probability is adjusted depending on its
value and the zone the land is in.

#model-figure(
  d.figures.correction,
  [The adjusted P(≥ Major) against the NLM's, for each zone.],
  width: 65%,
) <liq-correction>

A 100 m grid cell is as wide as the near zone, so many cells lie partly in two
zones. Such a cell takes a blend of the adjusted values for those zones,
weighted by the share of its area in each.

P(≥ Moderate) is not changed, and the adjusted P(≥ Major) is not allowed to
exceed it, since land cannot be more likely to suffer at least Major damage
than at least Moderate damage. The adjustment therefore moves probability
between Moderate and the more severe states, without changing the chance of at
least Moderate damage.

The adjustment slightly lowers the average P(≥ Major) over the study area from
#pct(a.mean_p_major_or_worse_before, digits: 1) to
#pct(a.mean_p_major_or_worse_after, digits: 1): most of the flat land is far
from a free face, where it falls, while the ground near one rises sharply
(@liq-zones).
#if a.cells_capped == 0 [The adjusted P(≥ Major) never reached P(≥ Moderate).] else [The adjusted P(≥ Major) reached P(≥ Moderate), and was held there, in
#num(a.cells_capped) cells.]

#figure(
  table(
    columns: 4,
    align: (left, right, right, right),
    table.header([*Zone*], [*Grid cells*], [*Baseline*], [*Adjusted*]),
    ..a.by_zone.pairs().map(((zone, z)) => (
      upper(zone.first()) + zone.slice(1),
      num(z.cells),
      pct(z.mean_p_major_before, digits: 1),
      pct(z.mean_p_major_after, digits: 1),
    )).flatten(),
  ),
  caption: [Average P(≥ Major) in each lateral spreading zone, before and after
    the adjustment.],
) <liq-zones>

@liq-free-face-map shows the locations of the free faces, and @liq-change-map
shows the adjustment to P(≥ Major), cell by cell.

#model-figure(
  d.figures.zones,
  [The free faces over the study area.],
) <liq-free-face-map>

#model-figure(
  d.figures.change,
  [P(≥ Major) before and after the adjustment, and the change, cell by cell.],
) <liq-change-map>

=== Six land damage states <liq-probabilities>

The two adjusted probabilities divide each cell into three bands: below
Moderate, Moderate, and Major or worse. The NLM does not give Minor, Severe or
Very Severe, so these are made by splitting the bands in fixed proportions. The
proportions come from fragility curves fitted against the liquefaction severity
number (LSN) for all six states, using the Canterbury earthquake sequence data
@tonkin_taylor_2013. The fitted curves for at least Moderate and at least Major
match the NLM's own. The splits adopted here were chosen from the relative
proportions between the fragility curves of this six damage state analysis.

The band below Moderate is split #pct(s.none_shares.None) None and
#pct(s.none_shares.Minor) Minor. The band at Major or worse is split
#pct(s.major_shares.Major) Major, #pct(s.major_shares.Severe) Severe and
#pct(s.major_shares.at("Very Severe")) Very Severe. The proportions are held
constant at every LSN, although the fitted curves show them varying. The six
probabilities of each cell still add up to one.

=== Sampling the states <liq-states>

For each simulated earthquake, each cell's state is sampled at random from its
six probabilities, independently of its neighbours. The model therefore does
not capture the spatial clustering of real liquefaction damage. This matters
most where probabilities are near 50%, which is the case across much of the
Hutt Valley floor, and where few ground investigations constrain the extent of
damage. This limitation is not expected to significantly affect total damage
across the whole study area, since the study area far exceeds the spatial
correlation length: over-predictions and under-predictions would be expected to
cancel, since they happen on a scale of about 1 km while the study area is
about 40 km long.

=== Damaged ground <liq-ground>

Each insured property takes the state of the grid cell at a point inside its
insured land. A property on sloping land, outside the NLM, has no liquefaction
damage, which is different from the state None: None describes flat land that
could liquefy but showed no damage.

The amount of evacuated and inundated insured land on a property is then
uniformly sampled from the range for its state in @liq-ground-ranges. The
ranges are based on the semi-quantitative descriptions of the land damage
categories @tonkin_taylor_2013, each of which describes the cracking a state
brings and the share of the land covered by ejecta. The damage ranges are
slightly higher than the descriptions, because they apply to insured land; the
chance that the damage happened outside the insured land is captured in the
"Does not claim" column. Evacuated land is an area
in m², because a state cracks much the same ground whatever the size of the
section, while inundated land is a share of the insured land, because ejecta
spreads over a fraction of it. Neither can exceed the insured land.

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
      if state == "None" [--] else { pct(vs.drop_out_rates.at(state)) },
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
covered by ejecta. The damaged area counts the evacuated plus the inundated
land, less an overlap of #pct(vs.evacuated_overlap_share) of the evacuated land
(capped at the inundated area), and never more than the insured land. The damaged area is what the land is valued over and the repair
is costed from.

#review[Maxim has a concern about the sampling of which properties claim,
below, and is waiting on Virginie Lacrosse. The shares that do not claim in
@liq-ground-ranges are placeholders awaiting her figures. Decide whether to
show them here or only in @cost-estimation.]

Not every property in a damaged state goes on to make a claim. This can be
because the cost is less than the excess, which is handled in the financial
model. The percentages used here reflect that the damage may not have occurred
on insured land. In addition to the 90% insurance penetration applied across the model, each insured property
on flat land is sampled as claiming or not at the rate for its state in
@liq-ground-ranges; one that does not claim loses no ground. Whether a property
claims, how much ground it loses and its damage state are each sampled
separately, so a change to one does not alter the others.

#review[The 90% insurance penetration is applied in the loss viewer, where it
is a setting, not in the damage step this appendix reports. The claims in
@liq-ground-results are therefore before penetration. Either say so there, or
read the 90% from the viewer's setting rather than state it here.]

== Results

Over the four territorial authorities, #num(va.on_grid) of the
#num(va.properties) insured properties are on flat land. For one simulated
earthquake, @liq-ground-results gives how many of them fall in each state, how
many claim, and the ground a claim in each state loses, and @liq-ta-results
gives the same by territorial authority. In all, #num(va.claims) properties
claim, over #num(va.damaged_area_ha, digits: 1) ha of damaged land.

#review[To be decided (Maxim). Lower Hutt's numbers here and in the tables below
come from the 14 October 2026 build, whose Lower Hutt free faces cover only the
old pilot box, so its liquefaction damage is understated (the last limitation
below). The fix is held back because that build has been issued. Decide whether
to keep these numbers, with the limitation disclosed, or rerun Lower Hutt
before the appendix goes out.]

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

#review[The #num(va.by_state.None.claims) claims in the None state are an
artefact of its #pct(vs.drop_out_rates.None) drop-out rate above: these
properties are sampled as claiming, but lose no ground and cost nothing.]

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
) <liq-ta-results>

== Validation

#if d.draw != none [
  The sampled states were checked against the probabilities they are sampled
  from. For one simulated earthquake over the four territorial authorities,
  @liq-draw compares the share of the #num(d.draw.cells) grid cells given each state
  with the average probability of that state over the same cells. Because the
  states are sampled, the share varies from one simulated earthquake to the
  next by about its standard error, so a gap of more than about two standard
  errors would point to a problem.

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
  ) <liq-draw>
]

This check does not test the probabilities against observed damage. The NLM is
validated against the Canterbury earthquake sequence in its own report
@tonkin_taylor_2026; nothing in this study has yet tested it in Wellington. The
ground lost in each state is not validated directly either: it is tested only
through the repair costs it produces, against the Canterbury claim costs, in
@cost-estimation.

== Limitations and future improvements <liq-limitations>

// NLM geomorphology, silts (LSN Ic10), groundwater, other NLM limitations,
// shallow gravels, L-52, L-53, L-54 and T-48/Q-19, L-39 and L-44, T-64/Q-16,
// L-88 and T-167. From Maxim Millen's table of 2026-10-22.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @liq-limitations-table lists each, its likely effect on the
modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [The NLM's geomorphology here comes from QMAP v4 @heron_2023, which is
        coarse in the study area.],
      [*Mixed.* Over-prediction in some places and under-prediction in others,
        depending on how the coarse units map to the actual ground.],
      [Add the Wellington City Council 1:50,000 geology map and the draft
        Porirua geology map to the NLM.],
    ),
    (
      [The NLM over-predicts damage in the interbedded silt deposits common in
        the Hutt Valley.],
      [*Over-prediction* of Hutt Valley losses.],
      [Apply the LSN#sub[Ic10] correction developed in the loss modelling work
        @tonkin_taylor_2026_lsnic10, or an equivalent.],
    ),
    (
      [The NLM uses the median groundwater depth, which is highly uncertain on
        the Hutt Valley floor because data are limited.],
      [*Unknown.* It could go either way, and the uncertainty is not carried
        into the losses.],
      [Use continuous groundwater monitoring logs, with input from
        hydrogeologists, to constrain the estimates.],
    ),
    (
      [The NLM report @tonkin_taylor_2026 notes several other limitations.],
      [*Mixed.*],
      [Improvements are detailed in the NLM technical report
        @tonkin_taylor_2026.],
    ),
    (
      [Shallow gravels under part of the Hutt Valley floor mean few ground
        investigations there go deep. Estimates for those geomorphological units
        therefore tend towards the national average for the units.],
      [*Over-prediction* where the shallow gravels are.],
      [Adjust performance there using local engineering judgement, and use
        region-specific rules for filtering ground investigations.],
    ),
    (
      [Three of the six states (Minor, Severe and Very Severe) are made by
        splitting the NLM's two probabilities in fixed proportions. The
        proportions are the same at every LSN, but the Canterbury curves show
        them changing with LSN.],
      [*Mixed.* Over-prediction at one end of the LSN range and
        under-prediction at the other.],
      [Rebuild the scenario outputs directly from fragility curves that give
        all six states.],
    ),
    (
      [Damage is not clustered. Each grid cell's state is sampled independently
        of its neighbours, so the map is speckled where real damage comes in
        patches.],
      [*Mixed.* Mean losses are not expected to vary significantly. The spread
        of losses between events is understated, so tail losses are likely
        under-predicted.],
      [Cluster the simulated damage so that neighbouring land is damaged
        together.],
    ),
    (
      [Free faces follow a rule, not geotechnical judgement. A channel named as
        a stream is never a free face, however deep its banks; the Waiwhetū and
        Porirua streams are examples. The whole coast is a free face, including
        rock and seawall coast that cannot spread.],
      [*Mixed.* Under-prediction beside streams with banks that can spread,
        and over-prediction along rock and seawall coast.],
      [Review the free faces, including adding the Waiwhetū Stream and the
        Porirua Stream.],
    ),
    (
      [The ground lost in each state is judgement. The ranges come from the
        semi-quantitative state descriptions @tonkin_taylor_2013 rather than
        from observations. The #pct(vs.evacuated_overlap_share) overlap of
        evacuated and inundated land is assumed.],
      [*Unknown.*],
      [Re-evaluate the CES data and compare with the separate classification in
        #cite(<geyin_2020>, form: "prose"), which used different thresholds and
        criteria to infer the distributions.],
    ),
    (
      [The share of properties that claim is provisional (@liq-ground-ranges).],
      [*Unknown.*],
      [Replace the rates with figures from NHC's claims experience, and account
        more explicitly for the reasons for not claiming, for example the size
        of the insured land relative to the property area.],
    ),
    (
      [Lower Hutt's free faces were determined only for a pilot area within
        that territorial authority, so they are incomplete. Most of Lower Hutt
        is therefore treated as far from a free face.],
      [*Under-prediction* of Lower Hutt losses.],
      [Rerun Lower Hutt with free faces over the whole city.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <liq-limitations-table>
