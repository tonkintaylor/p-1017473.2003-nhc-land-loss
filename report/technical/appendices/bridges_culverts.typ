// Appendix: estimation of locations of bridges and culverts. Written for
// readers of the technical report, who have not seen the code: say what the
// method does, not where it lives. Numbers and the map from:
//
//     uv run --frozen python src/scripts/landloss/exposure/culverts_bridges/report/fig_crossing_map.py
//     uv run --frozen python src/scripts/landloss/exposure/culverts_bridges/report/gen_report_numbers.py
//
// The accessway settings are read from the insured land numbers, written by
// exposure/land/report/gen_report_numbers.py. The limitations and
// improvements carry their register IDs in comments.

#import "../lib.typ": inputs-table, limitations-table, model-figure, num, pct, review

#let d = yaml("/report/exposure/culverts_bridges/tab/report-numbers.yaml")
#let x = d.study_area
#let land = yaml("/report/exposure/land/tab/report-numbers.yaml").settings

= Estimation of locations of bridges and culverts <crossings>

== Context

NHC covers a bridge or culvert on the insured land, which includes the main
accessway to the dwelling. No inventory of private bridges and culverts exists,
so the model estimates where they are.

== Inputs

@crossings-inputs-table lists the inputs to the estimate of bridge and culvert locations.

#figure(
  inputs-table(
    [Named watercourses, as centrelines], [LINZ NZ River Name Lines (Pilot)],
    [CC BY 4.0],
    [Named watercourses, as areas], [LINZ NZ River Name Polygons (Pilot)],
    [CC BY 4.0],
    [Insured accessway of each property], [This study's insured land extent],
    [--],
  ),
  caption: [Inputs to the estimate of bridge and culvert locations.],
) <crossings-inputs-table>

== Method

A bridge or culvert is there to carry an accessway over water, so the model
places one wherever a property's insured accessway crosses a watercourse. The
accessway is modelled as a #num(land.driveway_width_m) m wide route from the
main dwelling to the road, of which the first #num(land.insured_access_m) m
from the dwelling is insured. Any named watercourse counts, whether it is mapped as a centreline or,
for wider rivers, as an area, and a crossing found on both is counted once.
Only crossings lying wholly within the property's insured land are kept.

For each simulated earthquake, every crossing is sampled as either a culvert
(#pct(d.settings.culvert_probability) probability) or a bridge
(#pct(1 - d.settings.culvert_probability) probability). The split is
engineering judgement: there is no record of private bridges and culverts to
set it from, and nothing about a crossing in the data says which it is. The
applicable hazard section describes how each crossing type is damaged, and
@cost-estimation describes how the resulting damage is costed.

#review[Virginie notes that NHC, in their review of the draft report, asked
what evidence supports the #pct(d.settings.culvert_probability) /
#pct(1 - d.settings.culvert_probability) split. The code records it as
engineering judgement fitted to nothing. Add the reasoning behind it here (for
example, that most private crossings of small streams are piped), or say it is
a placeholder pending a sample check.]

== Results

Over the four territorial authorities, #num(x.crossings) insured accessways
cross a named watercourse. In the simulated earthquake shown in @crossings-map,
#num(x.by_structure.culvert) of the crossings are culverts and
#num(x.by_structure.bridge) bridges. All but
#num(x.by_source.at("polygons", default: 0)) were found on the watercourse
centrelines.

#model-figure(
  d.figures.map,
  [The culvert and bridge crossings on insured accessways, for one simulated
    earthquake.],
) <crossings-map>

== Limitations and future improvements

// Named-only floor (s7 method), CULVERT_PROBABILITY judgement, I-18 driveway
// routing, coverage filter.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @crossings-limitations-table lists each, its likely effect on the
modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [Only named watercourses are mapped. Crossings of the many small unnamed
        and piped streams are not included in the data source, the LINZ NZ
        River Name Lines and Polygons. Hence, the number of crossings is a lower
        bound.],
      [*Under-prediction* of bridge and culvert losses.],
      [Include unnamed watercourses, for example from the LINZ Topo50 river
        centrelines.],
    ),
    (
      [The split between culverts and bridges is judgement, not fitted to
        observations.],
      [*Unknown.* Both are costed alike, so the split matters only where they
        are damaged differently.],
      [Set the share of culverts and bridges from a sample checked against
        aerial imagery, or against a sample of past NHC land claims.],
    ),
    (
      [The accessway is a modelled route rather than a surveyed one, so a
        crossing may be placed where the real driveway does not go, or missed
        where it does.],
      [*Mixed.* Crossings are both added and missed.],
      [Route the modelled accessways along the property's real access to the
        street rather than in a straight line between the dwelling and the
        road.],
    ),
    (
      [A crossing lying partly outside the insured land, such as one at the
        road boundary, is excluded.],
      [*Under-prediction*, where such a crossing is in fact insured.],
      [Check a sample of crossings located at the property boundary against
        aerial imagery and property titles.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <crossings-limitations-table>

#review[The impacts on losses in @crossings-limitations-table are a first draft. Check the direction
given for each.]
