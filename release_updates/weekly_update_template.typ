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

*Week of {{date}}* #h(1fr) #text(size: 8pt, fill: luma(35%))[#mdone done #h(5pt) #mpart _partly done_ #h(5pt) #mnext next #h(5pt) #mtodo planned]

== 1. General updates

{{general_updates}}

== 2. Hazard

#table(
  ..grid3,
  table.header([*Liquefaction*], [*Landslide*], [*Shaking*]),
  statusrow(3),
  [
    {{hazard_liquefaction_status}}
  ],
  [
    {{hazard_landslide_status}}
  ],
  [
    {{hazard_shaking_status}}
  ],
  nextrow(3),
  [
    {{hazard_liquefaction_next}}
  ],
  [
    {{hazard_landslide_next}}
  ],
  [
    {{hazard_shaking_next}}
  ],
)

== 3. Exposure

#table(
  ..grid3,
  table.header([*Land*], [*Retaining walls*], [*Culverts and bridges*]),
  statusrow(3),
  [
    {{exposure_land_status}}
  ],
  [
    {{exposure_rw_status}}
  ],
  [
    {{exposure_culverts_bridges_status}}
  ],
  nextrow(3),
  [
    {{exposure_land_next}}
  ],
  [
    {{exposure_rw_next}}
  ],
  [
    {{exposure_culverts_bridges_next}}
  ],
)

== 4. Vulnerability

#table(
  ..grid3,
  table.header([*Liquefaction*], [*Landslide*], [*Shaking*]),
  statusrow(3),
  [
    {{vul_liquefaction_status}}
  ],
  [
    {{vul_landslide_status}}
  ],
  [
    {{vul_shaking_status}}
  ],
  nextrow(3),
  [
    {{vul_liquefaction_next}}
  ],
  [
    {{vul_landslide_next}}
  ],
  [
    {{vul_shaking_next}}
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
    {{loss_status}}
  ],
  table.cell(fill: luma(96%))[_What's next_],
  [
    {{loss_next}}
  ],
)
