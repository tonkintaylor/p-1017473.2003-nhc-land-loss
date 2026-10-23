// Appendix: calculation of landslide damage. Written for readers of the
// technical report, who have not seen the code: say what the method does, not
// where it lives. Numbers from:
//
//     uv run --frozen python src/scripts/landloss/hazard/landslide/report/gen_report_numbers.py
//
// Method from landslide steps 2 (Hancox coverage, Marc total), 3 (large
// realisation), 5 and 6 (urban fragility and realisation; slope_polygons,
// urban.fragility, urban.wall_type_fragility), and vul landslide land step 3
// and rw step 11. The limitations carry their register IDs in comments.

#import "../lib.typ": inputs-table, limitations-table, model-figure, num, pct, review

#let l = yaml("/report/hazard/landslide/tab/report-numbers.yaml")
#let s = l.settings
#let x = l.study_area
#let lg = s.large
#let ro = s.runout
#let fr = s.fragility
#let kb = s.kingsbury
#let area(pop, cls) = pop.area_km2.at(cls, default: 0)

= Calculation of landslide damage <landslide-damage>

== Context

Earthquake shaking causes landslides of two kinds that matter to residential
land. Large landslides, on natural hillsides, can carry away or bury whole
properties, and are modelled from the regional record of how much ground New
Zealand earthquakes have failed. Small failures of cuts, fills and retaining
walls in urban areas affect a part of a property, and are modelled one slope
face at a time. Both are drawn for each simulated earthquake, and both damage
land in the same three ways:

- Evacuated land is the ground the failure removed.
- Inundated land is the ground the debris came to rest on.
- Imminent land is ground behind a failure that is left at risk of further
  failure. It is reported but not counted as damaged.

The main report describes the earthquake scenario and its shaking.

== Inputs

@ls-inputs-table lists the inputs to the landslide model.

#figure(
  inputs-table(
    [Ground shaking (PGA and PGV) for each simulated earthquake], [This
      study's shaking model (main report)], [--],
    [Slope, terrain and ground attributes], [This study's ground model
      (@ground-model)], [--],
    [Wall candidates and walls], [This study's retaining wall model
      (@retaining-walls)], [--],
    [Flatland extent], [National Liquefaction Model @tonkin_taylor_2026], [--],
    [Landslide area, distance and slope relationships], [#cite(<hancox_1997>, form: "prose")],
    [--],
    [Event landslide area], [#cite(<marc_2016>, form: "prose")], [--],
    [Landslide size distribution], [#cite(<massey_2020>, form: "prose")], [--],
    [Slope susceptibility rating], [#cite(<kingsbury_1995>, form: "prose")], [--],
    [Debris travel angle], [#cite(<hunter_fell_2003>, form: "prose")], [--],
  ),
  caption: [Inputs to the landslide model.],
) <ls-inputs-table>

== Method: large landslides

=== How much ground fails

The total area of landsliding in the scenario earthquake comes from the
relationship of #cite(<marc_2016>, form: "prose") between an earthquake's
magnitude, depth and fault type and the area of landslides it triggers. For a
magnitude #num(s.scenario_mw, digits: 1) reverse-fault earthquake whose
rupture lies #num(s.marc.r0_km, digits: 1) km deep, it gives
#num(s.marc.event_total_km2, digits: 1) km#super[2] over the whole event.
Counting all of the rupture as onshore makes this an upper case.

The study area takes a share of that total. Landslides can occur only where
the shaking is at least Modified Mercalli intensity #num(s.mm_threshold),
within #num(s.hancox_distance_km) km of the earthquake, the furthest a
magnitude #num(s.scenario_mw, digits: 1) earthquake has triggered landslides in
New Zealand, and off flatland @hancox_1997. The intensity is converted from
the modelled peak ground velocity @worden_2012. The study area's share is its
eligible area over the #num(s.hancox_area_affected_km2) km#super[2] that
#cite(<hancox_1997>, form: "prose") give as affected by an earthquake of that
magnitude, multiplied by #num(s.marc.share_factor, digits: 1). The multiplier
allows for the shaking being strongest above the rupture, where Wellington
lies: weighting the share by the shaking rather than by area gave
#num(s.marc.share_factor, digits: 1) times the area share for Lower Hutt.

#review[The 2.3 multiplier is an interim choice (13 October 2026), to be
replaced by a shaking-weighted share once the national seismic hazard model's
interface geometry places the rupture. Confirm it should be described as
interim here.]

The study area's landslide area is spread across the eligible ground by slope,
in the shares @hancox_1997 observed (@ls-slope-table). The printed shares sum
to more than 100%, so the very steep share is taken as the remainder, split
between the two steepest classes in the printed ratio.

#let slope-names = (
  gentle: [Gentle], moderate: [Moderate], steep: [Steep],
  very_steep: [Very steep], extremely_steep: [Extremely steep],
)
#let edges = s.slope_class_edges_deg
#figure(
  table(
    columns: (1.4fr, 1.4fr, 1fr, 1fr),
    align: (left, left, right, right),
    table.header([*Slope class*], [*Slope (degrees)*], [*Printed share*],
      [*Share used*]),
    ..s.slope_shares.keys().enumerate().map(((i, k)) => (
      slope-names.at(k),
      [#num(edges.at(i), digits: 1)--#num(edges.at(i + 1), digits: 1)],
      pct(s.slope_shares_printed.at(k)),
      pct(s.slope_shares.at(k)),
    )).flatten(),
  ),
  caption: [Share of landslide area on each slope class.],
) <ls-slope-table>

=== Where each landslide is

The eligible ground is divided into slope units, areas of hillside that face
the same way. Each unit's expected landslide area sets how many landslides it
has, sampled from a Poisson distribution. Each landslide's source area is
sampled between #num(lg.min_source_area_m2) and
#num(lg.max_source_area_m2) m#super[2] from a power law with exponent
#num(lg.size_exponent, digits: 1), the exponent measured on the landslides of
the 2016 Kaikōura earthquake @massey_2020. Smaller failures are left to the
urban model below.

Each landslide starts at a cell sampled from the unit's most susceptible
cells, with cells on crests and spurs weighted up by
#pct(lg.crest_weight), because earthquake-triggered landslides favour them.
The source is an ellipse #num(lg.aspect_ratio, digits: 0) times as long
downslope as across, with the start cell at its crest. Where two sources
overlap, the larger is kept. The debris is the same ellipse moved downhill by
#num(lg.min_displacement_m) m on a slope of
#num(lg.min_displacement_slope_deg) degrees or less, rising in a straight line
to #num(lg.max_displacement_m) m on a slope of
#num(lg.max_displacement_slope_deg) degrees or more. The source is evacuated
land and the debris inundated land.

#review[The aspect ratio of 2 and the displacement range are placeholders. The
aspect ratio is to be measured on the Kaikōura source polygons. Confirm these
can be described as judgement.]

== Method: urban slope failures

=== Failure polygons

Every steep face found in @retaining-walls, walled or not, is given a failure
polygon: the shape the ground would take if the face failed. The polygon has
three parts:

- Evacuated land runs from the toe of the face to behind its crest, by the
  width a failure wedge would take in the face's material. It is never less
  than #num(ro.min_evacuated_width_h, digits: 1) times the face height nor
  less than #num(ro.min_evacuated_width_m) m.
- Inundated land runs downhill from the toe, as far as the travel angle of
  #cite(<hunter_fell_2003>, form: "prose") carries the debris. Where the
  ground below the toe is flatter than #num(ro.steep_downslope_deg) degrees,
  the travel angle is set by the steepness of the face, and otherwise by the
  steepness of the ground below. The shaking carries the debris further, by
  between #num(ro.seismic_runout_m.at("1"), digits: 1) and
  #num(ro.seismic_runout_m.at("5")) m depending on the slope's susceptibility
  zone. The runout is held to #num(ro.max_runout_h.at(0)),
  #num(ro.max_runout_h.at(1)) or #num(ro.max_runout_h.at(2)) times the face
  height on flat, moderate and steep ground below, and to the distance over
  which the debris would still lie at least
  #num(ro.min_deposit_depth_m, digits: 1) m deep.
- Imminent land runs from behind the evacuated land to where a line at
  #num(ro.repose_angle_deg) degrees from the toe meets the ground: the angle of
  repose the slope would settle to @de_vilder_2024.

#review[The description of the evacuated width (a failure wedge in the
material) and of the imminent band is a summary of several geometric rules.
Check it reads correctly.]

=== Susceptibility rating

Each face is rated for susceptibility to failure with the method of
#cite(<kingsbury_1995>, form: "prose"), developed for the Wellington region.
The rating sums six factors, each scored from 0 to 10 and weighted:

$ R = #kb.weights.slope F_"slope" + #kb.weights.modification F_"modification"
  + #kb.weights.height F_"height" + #kb.weights.geology F_"geology"
  + #kb.weights.landslides F_"landslides" + #kb.weights.groundwater F_"groundwater" $

to a maximum of #num(kb.max_rating). The factors come from the ground model
(@ground-model). The landslide factor is set to 0, because prior failures are
mapped only in part of the study area. The rating places the face in one of
five zones, from very low to very high, with breaks at
#kb.zone_breaks.map(b => num(b)).join(", ", last: " and ").

=== Fragility

Whether a face fails in an earthquake is set by a fragility curve: the
probability of failure at a given peak ground acceleration at the site. Each
curve is lognormal, defined by the acceleration at which 15% and 50% of faces
fail. Faces sloping off flatland have their curves lowered by a factor of
#num(fr.topographic_amplification, digits: 1), to allow for the amplification
of shaking on ridges and slopes.

A face with no wall takes a curve set by its rating. The curve was set by the
project lead at two ratings (@ls-localised-table) and runs in straight lines,
in the logarithm of acceleration, between and beyond them, so that a gentle,
low-rated face is very unlikely to fail.

#figure(
  table(
    columns: (1.4fr, 1fr, 1.4fr, 1.4fr),
    align: (left, right, right, right),
    table.header([*Kingsbury zone*], [*Rating*], [*PGA at which 15% fail (g)*],
      [*PGA at which 50% fail (g)*]),
    ..fr.localised_points.map(p => (
      [Zone #p.point.split("_").last()],
      num(p.rating),
      num(p.p15, digits: 2),
      num(p.p50, digits: 2),
    )).flatten(),
  ),
  caption: [The two points that set the fragility of faces with no wall.],
) <ls-localised-table>

A walled face takes the curve of its wall type (@ls-wall-fragility-table).
The curves were set by the project lead so that they flatten as the walls
strengthen, spaced evenly between garden timber, the weakest, and modern
reinforced concrete. Both values are multiplied by
#num(fr.tall_factor, digits: 2) for a wall #num(fr.tall_wall_m) m or higher,
by #num(fr.fill_factor, digits: 2) for a wall retaining fill and by
#num(fr.cut_factor, digits: 2) for a wall retaining a cut, since fill walls
carry looser ground and taller walls more load.

#figure(
  table(
    columns: (2.2fr, 1.2fr, 1.2fr),
    align: (left, right, right),
    table.header([*Wall type*], [*PGA at which 15% fail (g)*],
      [*PGA at which 50% fail (g)*]),
    ..fr.wall_curves.map(c => (c.label, num(c.p15, digits: 2), num(c.p50, digits: 2))).flatten(),
  ),
  caption: [Fragility of walls under 2 m high, by type.],
) <ls-wall-fragility-table>

#review[The wall curves are the project lead's judgement (13 October 2026);
until then they were read from Koutsoupaki et al. (2023). The 0.85 and 1.15
factors are also judgement. Confirm the reasons given for them, and whether to
add the fragility curve figure (drawn by the urban fragility figure script,
not yet generated).]

In each simulated earthquake, each face fails where a number sampled uniformly
between 0 and 1 falls below its probability of failure. A wall runs along
several faces, and one number is shared along it, so a wall fails or stands as
a whole.

=== Damage to land and walls

The failures of both kinds are combined, and where they overlap the ground is
counted once. A property's damaged land is its insured land within the
evacuated or inundated land of any failure. Imminent land is not counted as
damaged, since it has not moved. A wall is damaged where its own face fails,
or where another failure removes the ground it stands on, over the length
removed. Debris burying a wall does not on its own damage it.

== Results

In the simulated earthquake reported here, the model draws
#num(x.landslides.large.count) large landslides and
#num(x.landslides.urban.count) urban slope failures over the four territorial
authorities (@ls-results-table). Together they damage the insured land of
#num(x.land.properties_damaged) properties, evacuating
#num(x.land.evacuated_ha, digits: 1) ha and inundating
#num(x.land.inundated_ha, digits: 1) ha of it. Of the walls on insured land,
#pct(x.walls.failed_share) fail.

#figure(
  table(
    columns: (1.6fr, 1fr, 1.2fr, 1fr, 1.2fr, 1fr),
    align: (left, right, right, right, right, right),
    table.header(
      [*Territorial authority*], [*Large landslides*], [*Large, evacuated (km#super[2])*],
      [*Urban failures*], [*Urban, evacuated (km#super[2])*], [*Walls failed*],
    ),
    ..l.by_authority.pairs().map(((name, v)) => (
      name,
      num(v.landslides.large.count),
      num(area(v.landslides.large, "evacuated land"), digits: 2),
      num(v.landslides.urban.count),
      num(area(v.landslides.urban, "evacuated land"), digits: 2),
      pct(v.walls.failed_share),
    )).flatten(),
  ),
  caption: [Landslides and wall failures in one simulated earthquake.],
) <ls-results-table>

The share of walls that fail rises from
#pct(x.walls.failed_share_by_type.values().first()) for the strongest type
(#lower(x.walls.failed_share_by_type.keys().first())) to
#pct(x.walls.failed_share_by_type.values().last()) for the weakest
(#lower(x.walls.failed_share_by_type.keys().last())).

== Validation

The modelled landslide area has not been compared with the landslides of past
earthquakes, nor the large landslide area with the share of the Marc et al.
total it was set from.

#review[No validation of the landslide area, the urban failure rates or the wall
failure rates against past events was found. Is a comparison with the
landslides mapped after the 2016 Kaikōura earthquake, or with the urban slope
failures recorded after the 2013 Cook Strait and Seddon earthquakes, available
to report here?]

== Limitations and future improvements

// Marc total upper case and 2.3 share factor interim; aspect and displacement
// placeholders; landslide factor 0; wall curves and localised curve judgement;
// imminent land excluded; T-158 clipped walls.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @ls-limitations-table lists each, its likely
effect on the modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [The event landslide area counts all of the rupture as onshore, and the
        study area's share of it is an interim multiple of its area share.],
      [*Over-prediction* of large landslide losses.],
      [Weight the share by the shaking, once the rupture geometry is set by
        the national seismic hazard model.],
    ),
    (
      [The fragility curves of walls and of faces with no wall are the project
        lead's judgement, not fitted to observed failures.],
      [*Unknown.*],
      [Fit the curves to the slope and wall failures recorded after past New
        Zealand earthquakes.],
    ),
    (
      [The shape of a large landslide (an ellipse twice as long as wide) and
        the distance its debris travels are placeholders.],
      [*Mixed.*],
      [Measure both on the landslide inventory of the 2016 Kaikōura
        earthquake.],
    ),
    (
      [The landslide factor of the susceptibility rating is set to 0, so
        mapped prior failures do not raise a face's rating.],
      [*Under-prediction* on old landslides.],
      [Map prior failures across the study area and score the factor.],
    ),
    (
      [Imminent land is not counted as damaged, although NHC may settle land
        made unsafe by a failure next to it.],
      [*Under-prediction.*],
      [Agree with NHC how land at risk of further failure is settled, and
        count it where it is.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <ls-limitations-table>

#review[The impacts on losses in @ls-limitations-table are a first draft. Check
the direction given for each.]
