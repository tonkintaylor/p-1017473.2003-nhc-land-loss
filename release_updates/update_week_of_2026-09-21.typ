// Weekly progress update — Typst template.
//
// The handlebar placeholders are replaced with content lifted from the status.md
// files under src/scripts/landloss/. See the `writing-weekly-updates` skill for how
// one is generated and what goes in each section.
//
// Replacement text is Typst markup. A "Plan and progress" cell is one marked
// plan item per line -- #done[...], #part[...], #next[...] or #todo[...] -- and
// a "What's next" cell is a numbered list, one `+ item` per line. An asset group
// inside a vul cell is `*Land*` on its own line followed by its items.
//
// This file does not compile until the handlebars are substituted. Compile a
// filled copy with:
//
//     typst compile release_updates/update_week_of_<monday>.typ

#set page(paper: "a4", margin: (x: 1.2cm, y: 0.9cm))
#set text(font: "Arial", size: 9.5pt)
#set par(leading: 0.5em)
#set enum(indent: 0pt, body-indent: 4pt, spacing: 0.4em)
#show heading.where(level: 1): set text(size: 14pt)
#show heading.where(level: 2): set text(size: 10.5pt)
#show heading.where(level: 2): set block(above: 0.7em, below: 0.35em)

#let statusrow(n) = table.cell(colspan: n, fill: luma(96%))[_Plan and progress_]
#let nextrow(n) = table.cell(colspan: n, fill: luma(96%))[_What's next_]

// Progress marks. Each is its own block with a hanging indent, so a wrapped
// item lines up under its own text rather than under the next item's marker,
// and items stack without needing explicit line breaks.
#let pitem(marker, body) = block(
  above: 0pt, below: 1.5pt, width: 100%,
  par(hanging-indent: 10pt)[#marker#h(3pt)#body],
)
#let mdone = text(fill: rgb("#1a7f37"))[✓]
#let mpart = text(fill: rgb("#8a6d00"))[◐]
#let mnext = text(fill: rgb("#0b5cad"))[▸]
#let mtodo = text(fill: luma(60%))[·]

#let grp(body) = block(above: 4pt, below: 2pt, width: 100%, strong(body))

#let done(body) = pitem(mdone, body)
#let part(body) = pitem(mpart, emph(body))
#let next(body) = pitem(mnext, body)
#let todo(body) = pitem(mtodo, body)

#let grid3 = (
  columns: (1fr, 1fr, 1fr),
  align: top + left,
  inset: 3.5pt,
  stroke: 0.5pt + luma(70%),
)

= NHC land loss — weekly update

*Week of 2026-09-21* #h(1fr) #text(size: 8pt, fill: luma(35%))[#mdone done #h(5pt) #mpart _partly done_ #h(5pt) #mnext next #h(5pt) #mtodo planned]

== 1. General updates

+ Study area confirmed with NHC as Wellington City, Lower Hutt, Upper Hutt and Porirua.
+ Seismic demand set from TS1170.5 at the 2500-year return period.
+ Landslide model route — validate, extend or rebuild — is the decision now blocking work.
+ Awaiting land damage claim costs from NHC, and council land value and retaining wall data.

== 2. Hazard

#table(
  ..grid3,
  table.header([*Liquefaction*], [*Landslide*], [*Shaking*]),
  statusrow(3),
  [
    #grp[Prototype]
    #part[Get land damage (LD) probabilities for 2500y using TS1170.5]
    #part[Buffer rivers to obtain lateral spreading (LS) zones]
    #next[Modify LD probabilities inside LS zones]
    #todo[Generate realisations of LD]
    #grp[Beyond prototype]
    #todo[Switch National Liquefaction Model (NLM) to LD categories 1-6]
    #todo[Refine LS buffer zones]
  ],
  [
    #part[Use the existing 25 m probability model]
    #next[Choose between validating, extending and rebuilding it]
    #todo[Add spatial correlation]
    #todo[Add small failures]
    #todo[Add runout]
  ],
  [
    #next[Port the NLM code for TS1170.5 PGA demands]
    #todo[Take site class from the Foster Vs30 model]
    #todo[Generate PGA and Sa(T1) on a 100 m grid at 2500y]
    #todo[Derive PGV from the TS1170.5 spectrum]
  ],
  nextrow(3),
  [
    + Decide on the river layer; all have oddities.
    + Build the LS probability modifier.
  ],
  [
    + Choose between validating, extending or rebuilding the model.
    + Check the model grid over the study extent.
  ],
  [
    + Obtain the Foster Vs30 layer over the study area.
    + Port the NLM code for TS1170.5 PGA demands.
  ],
)

== 3. Exposure

#table(
  ..grid3,
  table.header([*Land*], [*Retaining walls*], [*Culverts and bridges*]),
  statusrow(3),
  [
    #part[Model a land value rate per square metre]
    #next[Generate driveways from dwelling to roadway]
    #todo[Buffer buildings by 8 m for the insured extent]
    #todo[Attribute the extent to property boundaries]
  ],
  [
    #todo[Classify walls by type, size and initial condition]
    #todo[Predict wall locations and sizes]
    #todo[Set initial condition from dwelling age]
    #part[Collect the four training datasets]
    #part[Pilot remote sensing detection of walls]
  ],
  [
    #todo[Detect watercourse crossings of the insured accessway]
    #todo[Read both the river line and river polygon layers]
    #todo[Sample a culvert or a bridge at each crossing]
  ],
  nextrow(3),
  [
    + Obtain the property boundary and roadway layers.
    + Generate driveways and the 8 m buffer.
    + Revalue on measured area rather than assumed lot size.
  ],
  [
    + Name the wall classes and the size thresholds.
    + Bring the collected data and mapping pilot into the repo.
    + Obtain the insurance council wall database.
  ],
  [
    + Add a reader for the river polygon layer.
    + Detect crossings once the accessway exists.
    + Sample structures and write one per property.
  ],
)

== 4. Vulnerability

#table(
  ..grid3,
  table.header([*Liquefaction*], [*Landslide*], [*Shaking*]),
  statusrow(3),
  [
    + Not reported this week.
  ],
  [
    #grp[Land]
    #todo[Read source and runout polygons separately]
    #next[Cost repair from the T+T remediation schedule]
    #todo[Size works from slip geometry]
    #todo[Select the cheapest feasible repair scheme]
    #todo[Settle at the lower of repair cost and land value]
  ],
  [
    + Not reported this week.
  ],
  nextrow(3),
  [
    + Not reported this week.
  ],
  [
    #grp[Land]
    + Confirm the rate basis; the two sources disagree.
    + Bring the rate schedule into the repository.
  ],
  [
    + Not reported this week.
  ],
)

== 5. Loss

#table(
  columns: (auto, 1fr),
  align: top + left,
  inset: 3.5pt,
  stroke: 0.5pt + luma(70%),
  table.cell(fill: luma(96%))[_Plan and progress_],
  [
    + Not reported this week.
  ],
  table.cell(fill: luma(96%))[_What's next_],
  [
    + Not reported this week.
  ],
)
