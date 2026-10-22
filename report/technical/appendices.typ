// The appendices to the study's technical report. The main report is written in
// Word, outside the repository; these set out the methodology and results in
// more detail than its body does, one file each under appendices/, and are
// compiled here as a document of their own:
//
//     typst compile --root . report/technical/appendices.typ
//
// Before compiling, run each appendix's numbers scripts, named at the top of
// its file. Each appendix is a level-one heading, lettered A, B, C, so a
// reference to one reads "Appendix A" and to a part of one "Section A.3".
// Review notes (#review) are shown unless show-review is set false in lib.typ.

#import "lib.typ": review, style
#show: style

#align(center)[
  #v(4cm)
  #text(size: 22pt, weight: "bold")[Land loss modelling for the Natural Hazards Commission]
  #v(0.6em)
  #text(size: 14pt)[Wellington, Hutt and Porirua: appendices to the technical report]
  #v(1.2em)
  #text(size: 11pt, fill: luma(40%))[
    Draft for internal review · #datetime.today().display("[day] [month repr:long] [year]")
  ]
]
#pagebreak()

#outline(depth: 2)
#pagebreak()

#set heading(numbering: "A.1")

// Tables and figures are numbered within their appendix, Table B.1, Figure B.1,
// so each appendix reads the same on its own as in the whole.
#set figure(numbering: n => numbering("A.1", counter(heading).get().first(), n))
#show heading.where(level: 1): it => {
  counter(figure.where(kind: table)).update(0)
  counter(figure.where(kind: image)).update(0)
  it
}

#review[The appendices are lettered from A here. Match the letters to those the
main report refers to once the full set is in.]

#include "appendices/bridges_culverts.typ"

#pagebreak()
#include "appendices/liquefaction_damage.typ"

#pagebreak()
#include "appendices/cost_estimation.typ"

#pagebreak()
#include "appendices/land_value.typ"

#pagebreak()
#bibliography("/doc/references.bib", title: [References], style: "apa")
