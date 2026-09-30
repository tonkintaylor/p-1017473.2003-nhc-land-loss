# Datasets and where they come from

Worked through on a Miro board in the kick-off meeting on 16 September 2026, where
each dataset was colour-coded by source. This is the wish list with a realistic
lens applied, not a confirmed inventory — most of these were still being chased at
the time of the meeting, and the corresponding chase-up tasks are in the register.

## From LINZ

Daniel Le Roux owns sourcing these, delegating within the GIS team.

| Dataset | Notes |
| --- | --- |
| Property ID and coordinates | The chosen unique identifier |
| Land and property areas | Feeds insured land area |
| Building outlines | Feeds insured land area |
| Property type | Freehold and cross-lease are confirmed; whether multi-unit buildings are identified is unconfirmed |
| DEM | High resolution, but a merge of different survey years — Wellington 2023, Hutt City 2025, Porirua unknown |
| Apartment structures | Nice to have, dependent on the multi-unit decision |
| Railway stations | Topo50 station points (layer 50318), for the land value accessibility term; read by `get_nz_rail_stations`. Carries no Wellington Station, which `land-value-extra-stations.csv` adds |

The DEM does not need to be re-stitched. An existing tool built for the National
Liquefaction Model assembles regional extents on the fly, and the GIS team already
holds the underlying data.

## From the National Liquefaction Model

- Geology and geomorphology, including the flat versus sloping land split.
- Expected liquefaction damage at a given level of shaking.
- Services.
- Lateral spreading, from a pilot whose first stage has just completed.

The sloping land representation in this data is simplified. It was accepted as a
sensible base model on that understanding.

## Calculated by T+T

- Slope gradient from the DEM. More than one gradient measure is likely — one
  feeding retaining wall exposure and one feeding slope failure.
- Insured land area, derived from land area and building outlines.
- Insurance penetration, applied as a fixed 90% variable rather than sourced.

## From councils

Wellington City, Hutt City, Upper Hutt, Porirua and Greater Wellington Regional
Council are all in scope for requests, and the local district councils hold
material the regional council does not.

- Capital and land values. Councils hold these for rating purposes, which avoids
  paying QV.
- The Wellington City Council cut-and-fill model.
- The Wellington City Council retaining wall database, which covers council rather
  than private walls.
- Greater Wellington's two landslide susceptibility layers.

Known contacts: Ryan Dunn at Wellington City Council, Michelle Van Nick at Hutt
City, and Amelia Stocks internally for both the retaining wall database and a
previous Wellington City Council road corridor piece. NHC may also approach the
councils in parallel, since a request from them may carry more weight.

## From GNS Science

Open layers, read by `landloss.io.readers`; the licence and what it obliges us to
credit are in each reader's docstring.

- The SLIDE geomorphology of the Wellington urban area (morphology lines,
  interpreted materials, genesis polygons), Wellington City only:
  `get_gns_slide_morphology`, `get_slide_interpreted_materials` and
  `get_slide_genesis`. The genesis layer has cut slopes, fill bodies and the
  only mapped landslide inventory; its licence is not recorded.
  The morphology lines include about 11,000 retaining wall segments, the only
  mapped walls this study has. They are the ones visible from above, in
  Wellington City only, so they are evidence that a wall exists and never that
  one does not; step 6 of the retaining wall exposure reads them that way.
- The 1:50,000 geology of Wellington City and most of Hutt City, Upper Hutt and
  Porirua (Begg & Mazengarb 1996, geological map 22), from GNS's GeoServer WFS:
  `get_wellington_urban_geology`. It carries no faults or structural data.

## From NHC

- Land damage claim costs for Wellington, or a sample if the full set is not
  feasible. NHC can extract this but is unsure it can do so in time, and it is not
  disaggregated by damage type such as retaining walls.
- A slope failure estimate from their loss modelling team, for cross-comparison.
  They will need the shaking intensities to produce it.
- The exact land cover policy wording, and the policy settings to be tested.

Andrew Kang was identified as the claims data contact and Ali as the loss
modelling contact, but all approaches now route through Bridget Attwood.

## Property files

Wellington City Council building information reports cost around $35 plus GST with
a one working day turnaround, and would show consented work including retaining
walls above 1.5 metres. This route was parked: there is not enough time in the
engagement to work through it, and it would need ordering immediately to be
useful. Marlborough District Council publishes its property files online and was
raised as a possible free surrogate, though the terrain is not steep enough to be
a close analogue.

## What is not obtainable

- A dataset of privately owned retaining walls. None is known to exist.
- Which individual properties are insured.
- Driveway extents, which are not in the LINZ data and are hard to separate from
  kerbs and footpaths by remote sensing.
- Private stormwater and wastewater services. Councils hold public services and
  the connection points only.

## A working note on tooling

The GIS and geotechnical teams have workflows that are not readily compatible —
broadly, everything goes into ArcGIS or nothing does. Agreeing how the two teams
share data is a live task rather than an assumption.

## A caution on names

Names in this file were transcribed from a meeting recording and some spellings
are uncertain. Verify before addressing correspondence to anyone listed here.
