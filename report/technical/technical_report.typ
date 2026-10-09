// The study's technical report, in the style of the National Liquefaction
// Model's. One section per exposure and hazard module; every number a section
// states is read from YAML a Python script writes, so it can be traced.
//
//     typst compile --root . report/technical/technical_report.typ
//
// Before compiling, run each section's numbers script, named at the top of
// its file under sections/.

#import "lib.typ": style
#show: style

#align(center)[
  #v(4cm)
  #text(size: 22pt, weight: "bold")[Land loss modelling for the Natural Hazards Commission]
  #v(0.6em)
  #text(size: 14pt)[Wellington, Hutt and Porirua: technical report]
  #v(1.2em)
  #text(size: 11pt, fill: luma(40%))[
    Draft for internal review · #datetime.today().display("[day] [month repr:long] [year]")
  ]
]
#pagebreak()

#outline(depth: 2)
#pagebreak()

= Exposure

#include "sections/exposure_insured_land.typ"

= Hazard

#include "sections/hazard_liquefaction.typ"
