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

#import "../lib.typ": inputs-table, model-figure, num, pct, review

#let d = yaml("/report/exposure/culverts_bridges/tab/report-numbers.yaml")
#let x = d.study_area
#let land = yaml("/report/exposure/land/tab/report-numbers.yaml").settings

= Estimation of locations of bridges and culverts <crossings>

#review[Maxim estimated less than a page: one map and a paragraph.]

== Context

NHC covers a bridge or culvert on the insured land, which includes the main
accessway to the dwelling. No inventory of private bridges and culverts exists,
so the model estimates where they are.

== Inputs

#inputs-table(
  [Named watercourses, as centrelines], [LINZ NZ River Name Lines (Pilot)],
  [CC BY 4.0],
  [Named watercourses, as areas], [LINZ NZ River Name Polygons (Pilot)],
  [CC BY 4.0],
  [Insured accessway of each property], [This study's insured land extent],
  [--],
)

== Method

A bridge or culvert is there to carry an accessway over water, so the model
places one wherever a property's insured accessway crosses a watercourse. The
accessway is modelled as a #num(land.driveway_width_m) m wide route from the
main dwelling to the road, of which the first #num(land.insured_access_m) m is
insured. Any named watercourse counts, whether it is mapped as a centreline or,
for wider rivers, as an area, and a crossing found on both is counted once.
Only crossings lying wholly within the property's insured land are kept.

Each crossing is taken to be a culvert with a probability of
#pct(d.settings.culvert_probability) and a bridge otherwise, sampled for each
simulated earthquake. How they are damaged is described with each hazard, and
how they are costed in @cost-estimation.

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

#review[Consider checking a sample of the crossings against aerial imagery, to
see how many are real and what share are bridges.]

== Limitations

// Named-only floor (s7 method), CULVERT_PROBABILITY judgement, I-18 driveway
// routing, coverage filter.
- Only named watercourses are mapped, so crossings of the many small unnamed
  and piped streams are missed, and the number of crossings is a lower bound.
- The split between culverts and bridges is judgement, not fitted to
  observations.
- The accessway is a modelled route rather than a surveyed one, so a crossing
  may be placed where the real driveway does not go, or missed where it does.
- A crossing lying partly outside the insured land, such as one at the road
  boundary, is left out.

== Future improvements

- Include unnamed watercourses, for example from the LINZ Topo50 river
  centrelines.
- Route the modelled accessways along the property's real access to the street
  rather than in a straight line.
- Set the share of bridges from a sample checked against aerial imagery.
