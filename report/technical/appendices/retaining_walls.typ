// Appendix: retaining wall locations, types and sizes. Written for readers of
// the technical report, who have not seen the code: say what the method does,
// not where it lives. Numbers from:
//
//     uv run --frozen python src/scripts/landloss/exposure/rw/report/gen_report_numbers.py
//
// Method from ground step 3 (pips, pifs, sizs, wall lines; instability_zones),
// exposure rw step 6 (wall units, points, GNS floor, claim update, worlds) and
// landloss.exposure.rw.wall_type (types). The validation reads the rw-datasets
// tables. The limitations carry their register IDs in comments.

#import "../lib.typ": inputs-table, limitations-table, num, pct, review

#let w = yaml("/report/exposure/rw/tab/report-numbers.yaml")
#let s = w.settings
#let x = w.study_area
#let labels = (:)
#for row in s.type_labels { labels.insert(row.wall_type, row.label) }
#let type-order = s.type_labels.map(row => row.wall_type)
#let recall = w.validation.claims_recall.find(r => r.claim_report == "lists a wall")
#let coverage(name) = w.validation.coverage.find(r => r.dataset == name)

// Readable names for the points table's attributes and bins.
#let attribute-names = (
  verticality: [Verticality: share of the drop in the first metre],
  height: [Face height],
  length: [Face length],
  building: [Distance to the nearest building],
  setting: [Setting],
  class: [Earthworks at the face],
  rock_cut: [Cut in rock],
  soil_cut: [Cut in soil],
  age: [Age of the property's walls],
  nhc_land_attrs: [NHC property records],
)
#let bin-names = (
  road_frontage: [Within #num(s.boundary_distance_m) m of a road boundary],
  property_boundary: [Within #num(s.boundary_distance_m) m of another property boundary],
  fill: [Fill],
  cut_and_fill: [Cut and fill],
  natural: [Natural bank],
  pre_1970: [Before 1970],
  "1970_1991": [1970 to 1991],
  "1992_2004": [1992 to 2004],
  "2005_on": [2005 on],
  flagged: [Property recorded as having a wall],
)
#let age-names = (
  pre_1970: [Before 1970],
  "1970_1991": [1970--1991],
  "1992_2004": [1992--2004],
  "2005_on": [2005 on],
)
#let band-names = (
  under_1_5_m: [under 1.5 m],
  "1_5_to_2_5_m": [1.5--2.5 m],
  over_2_5_m: [2.5 m and over],
)

= Retaining wall locations, types and sizes <retaining-walls>

== Context

NHC covers retaining walls within the insured land that support the land or
the dwelling. No inventory of retaining walls exists for the study area, so
the model estimates where walls are likely to be, how high and long they are,
and what they are built of. A wall is never known to exist: each candidate
carries a probability, and each simulated world draws which candidates are
walls. @landslide-damage describes how the walls are damaged, and
@cost-estimation how they are costed.

== Inputs

@rw-inputs-table lists the inputs to the wall model.

#figure(
  inputs-table(
    [Ground elevation, 1 m grid], [LINZ], [CC BY 4.0],
    [Ground material, modification and slope], [This study's ground model
      (@ground-model)], [--],
    [Building outlines], [LINZ NZ Building Outlines], [CC BY 4.0],
    [Property and road boundaries], [LINZ NZ Primary Parcels], [CC BY 4.0],
    [Mapped retaining walls, urban Wellington City], [GNS Science SLIDE
      (Wellington) @townsend_2020], [To confirm],
    [Retaining walls listed on site], [NHC claim reports, past events in the
      study area], [Private],
    [Property flag for a retaining wall], [NHC property records], [Private],
    [Date of each property's title and survey plan], [LINZ NZ Property Titles
      List], [CC BY 4.0],
  ),
  caption: [Inputs to the retaining wall model.],
) <rw-inputs-table>

== Method

=== Finding faces that could be walls

A retaining wall shows on the elevation model as a sharp step. The model looks
for such steps directly, without reading any other layer, in three stages:

+ A potential instability point is a 1 m cell that stands more than
  #num(s.pip_drop_m, digits: 1) m above the cells
  #s.pip_offsets_m.map(m => num(m)).join(", ", last: " and ") m away in the
  same direction, tested in eight directions. Requiring the drop at all three
  distances keeps out the small bumps of the elevation model while still
  catching a wall about #num(s.pip_drop_m, digits: 1) m high.
+ A potential instability face joins the points within #num(s.pif_join_m) m
  of each other. A face needs at least #num(s.min_pif_pips) points and a
  length of #num(s.min_pif_length_m) m. Faces lying mostly within a building
  outline are dropped, since a roof edge is not ground, as are faces more than
  #num(s.building_reach_m) m from any building, since NHC covers walls only
  near a dwelling.
+ A face is steep where its drop is sharp enough for its ground: a step of
  #num(s.adjacent_step_m.soil_like, digits: 1) m within
  #num(s.near_pair_m) m in soil, or #num(s.adjacent_step_m.weak_rock) m in
  rock, or a slope steeper than the angle a bank of that material and height
  would stand at unsupported, of between
  #num(s.slope_thresholds.last().soil_like) and
  #num(s.slope_thresholds.first().stronger_rock) degrees.

Every steep face is a wall candidate. Two further kinds of candidate come from
the SLIDE wall map, which covers urban Wellington City: a face that is not
steep but has a mapped wall along it, and a mapped wall at least
#num(s.min_pif_length_m) m long with no face along it at all, because the
elevation model misses some walls under trees or behind buildings.

Each face is cut into wall candidates along its length, each with no more than
#num(s.wall_max_bends) bends, straight sections at least
#num(s.wall_min_segment_m) m long, and a length of no more than
#num(s.wall_max_length_m) m. A candidate's height is the
#num(s.height_quantile * 100)th percentile of the drops within
#num(s.height_reach_m) m of its line, so that one deep cell does not set the
height of the whole wall.

=== The probability that a candidate is a wall

Each candidate starts from a base probability of #num(s.base_p, digits: 3),
which is then raised or lowered by points for what is known about it
(@rw-points-table). The points are judgement, informed by how often the SLIDE
map shows a wall on faces of each kind. They change the odds of a wall rather
than the probability itself, so that a candidate can never pass 0 or 1:

$ p = 1 / (1 + exp(-(ln(p_0 / (1 - p_0)) + P ln 2 \/ #num(s.points_per_doubling)))) $

where $p_0$ is the base probability and $P$ the candidate's total points. Each
#num(s.points_per_doubling) points doubles the odds of a wall.

#figure(
  table(
    columns: (1.6fr, 2fr, auto),
    align: (left, left, right),
    table.header([*What is known*], [*Value*], [*Points*]),
    ..s.points.map(row => (
      attribute-names.at(row.attribute, default: row.attribute),
      bin-names.at(row.bin, default: upper(row.bin.first()) + row.bin.slice(1)),
      if row.points > 0 [+#row.points] else [#row.points],
    )).flatten(),
  ),
  caption: [Points added to a wall candidate for what is known about it.],
) <rw-points-table>

Where SLIDE maps a wall along the candidate, its probability is raised to at
least #num(s.gns_floor, digits: 2). A SLIDE wall with no face along it takes
#num(s.gns_only_p, digits: 2), lower, because the elevation model would
usually show a wall that is there.

Finally, NHC claim reports from past events list the retaining walls seen on
site. Where a report lists walls on a property, the probabilities of that
property's candidates are updated so that at least that many of them are
walls. A report that lists none is not used, because a report that does not
mention a wall is not evidence that there is none. A sample of #pct(s.claim_holdout_share) of the
claimed properties is held out of the update to test it.

=== Drawing the walls

Each simulated world draws which candidates are walls from their
probabilities, and the same world of walls is used for every earthquake, so
that the difference between earthquakes is the shaking and not the walls.

Each wall is then given a size class from its height (small under
#num(s.small_max_height_m, digits: 1) m, medium to
#num(s.medium_max_height_m, digits: 1) m, and large above) and a type. The
type depends on when the wall was built and how high it is
(@rw-type-shares-table). The construction age of walls is not recorded, so
each wall takes the age of its property, estimated from the dates of the
property's title and survey plan, and #pct(s.rebuilt_share) of walls move one
age band later, as rebuilt since the house. The height bands break at 1.5 m,
above which a wall needs a building consent, and at 2.5 m. The age bands break
at 1970, at July 1992, when the Building Act 1991 took effect, and at 2005.

#figure(
  text(size: 8pt, table(
    columns: (1.1fr, 1fr, ..type-order.map(_ => 0.9fr)),
    align: (left, left, ..type-order.map(_ => right)),
    table.header(
      [*Built*], [*Height*],
      ..type-order.map(t => text(weight: "bold", labels.at(t))),
    ),
    ..s.type_shares.map(row => (
      age-names.at(row.age_bin),
      band-names.at(row.height_band),
      ..type-order.map(t => if row.at(t) == 0 [--] else [#pct(row.at(t))]),
    )).flatten(),
  )),
  caption: [Share of walls of each type, by when the wall was built and its
    height.],
) <rw-type-shares-table>

Walls on a road frontage are more often masonry or concrete than walls within
a section, so on a frontage each type's share is multiplied by the factor in
@rw-frontage-table before the shares are rescaled to sum to one.

#figure(
  table(
    columns: (2fr, auto),
    align: (left, right),
    table.header([*Wall type*], [*Multiplier on a road frontage*]),
    ..s.frontage_multipliers.map(row => (
      labels.at(row.wall_type), num(row.road_frontage_multiplier, digits: 1),
    )).flatten(),
  ),
  caption: [Multipliers on the type shares of a wall on a road frontage.],
) <rw-frontage-table>

#review[The type shares, the frontage multipliers and the 20% rebuilt share are
judgement placeholders set by the project lead (6 October 2026), for Nick
Peters to revise. Confirm whether that review has happened, and if not, say so
in the text.]

== Results

Over the four territorial authorities, the model finds #num(x.candidates) wall
candidates, of which #num(x.drawn_walls) are walls in the world shown here,
totalling #num(x.drawn_length_km) km. Of these, #num(x.insured_walls) lie on
insured land (@rw-results-table).

#figure(
  table(
    columns: (1.6fr, 1fr, 1fr, 1fr, 1fr),
    align: (left, right, right, right, right),
    table.header(
      [*Territorial authority*], [*Candidates*], [*Walls*], [*Length (km)*],
      [*Walls on insured land*],
    ),
    ..w.by_authority.pairs().map(((name, v)) => (
      name, num(v.candidates), num(v.drawn_walls), num(v.drawn_length_km),
      num(v.insured_walls),
    )).flatten(),
  ),
  caption: [Wall candidates and the walls drawn, in one simulated world.],
) <rw-results-table>

Wellington City holds most of the walls, as it has both the steepest urban
land and the SLIDE map. The median wall is
#num(x.height_m.median, digits: 2) m high, and four in five are between
#num(x.height_m.p10, digits: 2) and #num(x.height_m.p90, digits: 2) m. As a
result, #pct(x.by_size.medium / x.drawn_walls) of walls are medium,
#pct(x.by_size.small / x.drawn_walls) small and
#pct(x.by_size.large / x.drawn_walls) large. Garden timber is the most common
type, at #pct(x.by_type.at("Garden timber") / x.drawn_walls) of walls.

#review[The heights are narrow: four in five walls are within about 0.7 m of
each other, so almost all are medium. The 70th percentile of the drops within
2 m may be smoothing tall walls down and lifting low ones. Check the heights
against a sample of walls of known height before the size mix is relied on.]

== Validation

The three records of where walls are agree poorly with each other. The SLIDE
map shows a wall on #pct(coverage("GNS SLIDE").share_flagged) of the
#num(coverage("GNS SLIDE").properties) properties it covers, NHC's property
records flag #pct(coverage("NHC NZMM").share_flagged) of
#num(coverage("NHC NZMM").properties) properties, and claim reports list a wall
at #pct(coverage("Claim reports").share_flagged) of
#num(coverage("Claim reports").properties) claimed properties. Where a claim
report lists a wall and SLIDE covers the property, SLIDE or the NHC records
show one at only #pct(recall.either_flagged_where_gns_mapped) of them. Each
record misses many walls, which is why the model uses them to raise
probabilities but never to lower them.

#pct(x.share_under_1_5_m) of the modelled walls are under 1.5 m high, against
54% of the walls surveyed after the Canterbury earthquakes @anderson_2015.

#review[The held-out claim check (expected walls against the walls the held-out
claim reports list) is built but has not been run for the four territorial
authorities, and no spot check of candidates against aerial imagery is
recorded. Run the hold-out check and report it here, or say neither has been
done. Also confirm the 54% from Anderson et al. (2015).]

== Limitations and future improvements

// L-04 no inventory; L-48 0.7 m step on the 1 m DEM; L-56/L-57; T-118, T-120
// type shares placeholders; age proxy (age.py); held-out check not run.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @rw-limitations-table lists each, its likely
effect on the modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [No inventory of retaining walls exists, and the records that exist miss
        many walls, so the probability that a candidate is a wall rests largely
        on judgement.],
      [*Unknown.*],
      [Build a sample inventory by surveying a set of streets, and fit the
        points to it.],
    ),
    (
      [Walls lower than about #num(s.pip_drop_m, digits: 1) m, and walls
        hidden under trees or buildings, do not show on the elevation model.
        Outside urban Wellington City there is no wall map to add them.],
      [*Under-prediction* of the number of walls.],
      [Add walls seen in aerial and street-level imagery, and extend the SLIDE
        mapping to the other councils.],
    ),
    (
      [The type shares, frontage multipliers and rebuilt share are judgement,
        not fitted to observations.],
      [*Unknown.* Type sets both the fragility and the repair cost.],
      [Have a local retaining wall specialist review the shares, and check
        them against claim reports that record wall type.],
    ),
    (
      [A wall's age is taken from its property's title and survey plan, which
        dates the house rather than the wall, and the 1990s fall in one age
        band, so the July 1992 break is approximate.],
      [*Mixed.*],
      [Use council building consent records to date consented walls.],
    ),
    (
      [Heights are read from the elevation model and fall in a narrow range,
        so few walls are small or large.],
      [*Mixed.* Repair cost rises steeply with height.],
      [Check modelled heights against walls of known height and adjust how the
        height is read.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <rw-limitations-table>

#review[The impacts on losses in @rw-limitations-table are a first draft. Check
the direction given for each.]
