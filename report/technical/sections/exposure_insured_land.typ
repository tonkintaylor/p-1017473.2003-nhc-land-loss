// Insured land and its value. Numbers from:
//
//     uv run --frozen python src/scripts/landloss/exposure/land/report/gen_report_numbers.py

#import "../lib.typ": from-register, inputs-table, model-figure, num, pct

#let d = yaml("/report/exposure/land/tab/report-numbers.yaml")
#let s = d.settings
#let f = s.factors
#let v = d.land_value
#let i = d.insured_land
#let extent-name(extent) = if extent == "wlg-pilot" [the Wellington pilot] else [the study area]

== Insured land <insured-land>

=== Context

NHC's land cover is not the whole section. It is the land under and within
#num(s.buffer_m) m of the dwelling and its appurtenant structures, and the main
access way to the dwelling within #num(s.insured_access_m) m of it, and NHC
settles damage to it at the lesser of the cost of repair and the value of the
damaged land. This module supplies, for every residential property in the study
area, the polygon of land NHC insures, the number of dwellings on it, which the
per-dwelling sub-caps and excess multiply by, and the value of its land per
square metre. The hazard modules measure their damage against the polygon, and
the loss module values it with the rate.

The claim is the property: one LINZ property boundary, every building standing
on it, and every address point inside it. Land values are modelled, not
observed, until QV's rating roll replaces them.

=== Inputs

#inputs-table(
  [Property boundaries], [LINZ NZ Property Boundaries, layer 122657], [CC BY 4.0],
  [Building outlines], [LINZ NZ Building Outlines, layer 101290], [CC BY 4.0],
  [Address points], [LINZ NZ Addresses, layer 123113], [CC BY 4.0],
  [Road centrelines], [LINZ NZ Addresses: Roads, layer 123110], [CC BY 4.0],
  [Elevation (slope, relative height, views, sun)],
  [LINZ elevation models, LiDAR where flown], [CC BY 4.0],
  [Flat and sloping land], [National Liquefaction Model flatland], [T+T, internal],
  [Railway stations], [LINZ Topo50 railway stations, layer 50318], [CC BY 4.0],
  [Average land value per territorial authority],
  [QV rating valuation media releases, one per authority], [Public],
  [Land value factors and town centres],
  [Project judgement, each with its basis, in `src/landloss/io/assets/`],
  [T+T],
)

=== Method

The module runs in two steps under `src/scripts/landloss/exposure/land/steps/`:

+ *Land value* (@land-value): a rate per square metre for every address.
+ *Insured land extent* (@insured-extent): the insured polygon for every
  property, with the rate and the dwelling count on it.

==== Land value <land-value>

Each authority's published average land value is indexed to a common date,
#s.valuation_date, and spread across its addresses by multipliers. The
multipliers move value between properties within an authority and never change
its total: a normalising constant is solved so the authority's modelled mean
equals the indexed average exactly.

- *Landform.* An address is hill or flat by the NLM's flatland, and flat land
  standing more than #num(f.elevated_flat_min_topographic_position_m) m above
  its surroundings over a #num(f.topographic_position_window_m) m window is
  elevated flat. Flat land is worth #num(f.landform_factor_flat, digits: 2)
  times hill and elevated flat #num(f.landform_factor_elevated_flat, digits: 2)
  times.
- *Terrain, access and amenity.* Within each authority and landform, value is
  shifted by slope and relative height; by closeness to the town centres and to
  railway stations; and by the share of directions with a view of the sea, the
  distance to the coast and the share of winter sun. Each modifier averages one
  within its group, so it redistributes value rather than adding any.
- *Limits.* No address is valued at less than
  #num(f.rate_clip_min_multiple, digits: 2) or more than
  #num(f.rate_clip_max_multiple, digits: 1) times its authority's average.

The rate is taken as excluding GST and grossed up at #pct(s.gst_rate) before it
reaches the loss module.

==== Insured land extent <insured-extent>

- *Claim properties.* The LINZ property boundaries, less road and water parcels,
  with boundaries of identical geometry dissolved, so a block of unit titles on
  one footprint is one claim rather than one per unit.
- *Dwellings.* The address points inside the property. A property with none
  carries no insured land.
- *Buildings.* Outlines LINZ names as non-residential, or larger than
  #num(s.max_dwelling_footprint_m2) m#super[2], are dropped. A building
  straddling a boundary by more than #num(s.min_crossing_area_m2) m#super[2] and
  #pct(s.min_crossing_share) of its area is split between the properties.
- *Extent.* Every remaining building on the property is buffered by
  #num(s.buffer_m) m, garages and sheds as well as the dwelling.
- *Driveway.* One per property, from its largest building in a straight line to
  the nearest road centreline, #num(s.driveway_width_m) m wide, insured for its
  first #num(s.insured_access_m) m. A building more than
  #num(s.max_driveway_m) m from any road gets none.
- *Clip.* The union of the buffers and the driveway is clipped to the property,
  so no claim reaches onto a neighbour's land and no two claims overlap.

=== Results

*Land value.* #num(v.addresses) addresses over #extent-name(v.extent) are valued:
#pct(v.landform_share.flat) flat, #pct(v.landform_share.hill) hill and
#pct(v.landform_share.elevated_flat) elevated flat.

#figure(
  table(
    columns: 6,
    align: (left, right, right, right, right, right),
    table.header(
      [*Authority*], [*Addresses*], [*Average land value*],
      table.cell(colspan: 3, align: center)[*Median rate (\$/m#super[2], excl. GST)*],
      [], [], [], [*Hill*], [*Flat*], [*Elevated flat*],
    ),
    ..v.by_ta.pairs().map(((ta, t)) => (
      ta,
      num(t.addresses),
      [\$#num(t.indexed_mean_nzd)],
      num(t.median_rate_nzd_per_m2.hill),
      num(t.median_rate_nzd_per_m2.flat),
      num(t.median_rate_nzd_per_m2.elevated_flat),
    )).flatten(),
  ),
  caption: [Land value per territorial authority. The average is QV's published
    figure indexed to #s.valuation_date, which the model reproduces exactly.],
)

*Insured land.* Over #extent-name(i.extent), #num(i.claims) claims carry
#num(i.area_ha, digits: 1) ha of insured land and cover #num(i.dwellings_covered)
of the #num(i.addresses) address points. The median claim is
#num(i.median_area_m2) m#super[2] of insured land, #pct(i.median_share_of_property)
of its property: on a typical Wellington section the #num(s.buffer_m) m line
reaches the boundary. The median driveway is #num(i.median_driveway_m, digits: 1)
m to the road, and #pct(i.share_cut_at_insured_access, digits: 1) are longer
than #num(s.insured_access_m) m and cut there.

#model-figure(
  d.figures.insured_land,
  [Insured land over the Wellington pilot.],
  script: "exposure/land/steps/s5_insured_land_extent/fig_insured_land.py",
)

#model-figure(
  d.figures.land_value,
  [Modelled land rate per square metre over the Wellington pilot.],
  script: "exposure/land/steps/s2_land_value/fig_land_value_map.py",
)

=== Validation

*Totals.* Each authority's modelled mean land value equals QV's published
average indexed to #s.valuation_date. This holds by construction, so it checks
the arithmetic rather than the model.

*Suburb ranking.* Of the suburbs with at least 30 addresses, #num(v.suburb_ranking.suburbs_ranked)
are ranked by their median land value and set against which ought to sit in the
top or bottom half of the market. #num(v.suburb_ranking.expectations_met) of
#num(v.suburb_ranking.expectations_considered) do#if v.suburb_ranking.out_of_place.len() > 0 [;
#v.suburb_ranking.out_of_place.join(", ", last: " and ") sit in the lower half
although expected in the upper, and why is not yet established]. Switching to QV's rating roll (T-49) replaces this
check with a comparison against council values property by property.

*Coverage.* #num(i.addresses - i.dwellings_covered) of #extent-name(i.extent)'s
#num(i.addresses) address points carry no insured land, most of them flats in
apartment blocks dropped by the #num(s.max_dwelling_footprint_m2) m#super[2]
footprint test.

=== Limitations

#from-register("Limitations", ("L-20", "L-21", "L-35", "L-41", "L-42", "L-46", "L-47"))

=== Future improvements

#from-register("Improvements", ("I-12", "I-17", "I-18"))
#from-register("Tasks", ("T-49", "T-24"))
#from-register("Questions", ("Q-15",))
