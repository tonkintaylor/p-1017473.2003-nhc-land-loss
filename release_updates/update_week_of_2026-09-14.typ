// Weekly progress update — Typst template.
//
// The handlebar placeholders are replaced with content lifted from the status.md
// files under src/scripts/landloss/. See the `writing-weekly-updates` skill for how
// one is generated and what goes in each section.
//
// Replacement text is Typst markup: a numbered list is one `+ item` per line,
// and an asset group inside a vul cell is `*Land*` on its own line followed by
// its list. Keep every item to one line.
//
// This file does not compile until the handlebars are substituted. Compile a
// filled copy with:
//
//     typst compile release_updates/update_week_of_<monday>.typ

#set page(paper: "a4", margin: (x: 1.3cm, y: 1.1cm))
#set text(font: "Arial", size: 9.5pt)
#set par(leading: 0.5em)
#set enum(indent: 0pt, body-indent: 4pt, spacing: 0.4em)
#show heading.where(level: 1): set text(size: 14pt)
#show heading.where(level: 2): set text(size: 10.5pt)
#show heading.where(level: 2): set block(above: 0.9em, below: 0.45em)

#let statusrow(n) = table.cell(colspan: n, fill: luma(96%))[_Current status_]
#let nextrow(n) = table.cell(colspan: n, fill: luma(96%))[_What's next_]

#let grid3 = (
  columns: (1fr, 1fr, 1fr),
  align: top + left,
  inset: 3.5pt,
  stroke: 0.5pt + luma(70%),
)

= NHC land loss — weekly update

*Week of 2026-09-14*

== 1. General updates

+ Study area proposed as the four Wellington territorial authorities, not yet confirmed (T-01, T-06).
+ Landslide model route — build new or extend the ESNZ model — is the decision now blocking work.
+ Awaiting NHC land claim costs (T-17, T-18), council land values and retaining wall records.

== 2. Hazard

#table(
  ..grid3,
  table.header([*Liquefaction*], [*Landslide*], [*Shaking*]),
  statusrow(3),
  [
    + Not reported this week.
  ],
  [
    + ESNZ model in hand, not yet used.
    + Lacks spatial correlation, small failures and runout.
    + Route undecided; L-08 limits ESNZ use.
  ],
  [
    + Not started.
  ],
  nextrow(3),
  [
    + Not reported this week.
  ],
  [
    + Agree the route with the project team.
    + Check the ESNZ grid over the study extent.
    + Add correlation, small failures and runout.
  ],
  [
    + Port the NLM ground motion calculation.
    + Adopt the Foster Vs30 site class model (T-15).
    + PGA, Sa(T1) and PGV at the 2500-year return period.
  ],
)

== 3. Exposure

#table(
  ..grid3,
  table.header([*Land*], [*Retaining walls*], [*Culverts*]),
  statusrow(3),
  [
    + Land value modelled per square metre for every address.
    + Insured land extent not built yet.
    + Land area still an assumed median lot size (T-25).
  ],
  [
    + Not reported this week.
  ],
  [
    + Not reported this week.
  ],
  nextrow(3),
  [
    + Read the property boundary and roadway layers.
    + Generate driveways and the 8 m building buffer.
    + Write the insured land extent and revalue on measured area.
  ],
  [
    + Not reported this week.
  ],
  [
    + Not reported this week.
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
    *Land*
    + Not started; approach drafted, not agreed.
    + Repair cost capped at land value.
    + Needs NHC land claim costs (T-17, T-18).
  ],
  [
    + Not reported this week.
  ],
  nextrow(3),
  [
    + Not reported this week.
  ],
  [
    *Land*
    + Confirm the rate basis; the two sources disagree.
    + Package the rate schedule into the repository.
    + Build the per-claim take-off once polygons exist.
  ],
  [
    + Not reported this week.
  ],
)

== 5. Loss

#table(
  columns: (1fr),
  align: top + left,
  inset: 3.5pt,
  stroke: 0.5pt + luma(70%),
  statusrow(1),
  [
    + Not reported this week.
  ],
  nextrow(1),
  [
    + Not reported this week.
  ],
)
