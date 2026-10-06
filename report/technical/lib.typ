// Style and helpers shared by every section of the technical report.
//
// Paths are absolute from the repository root, so the report is compiled with
// the root set there:
//
//     typst compile --root . report/technical/technical_report.typ

#let register = json("/.agents/context/register.json")

// Page and type, matching report/loss/loss_method_summary.typ.
#let style(body) = {
  set page(paper: "a4", margin: (x: 2cm, y: 2cm), numbering: "1")
  set text(font: "Arial", size: 10pt, lang: "en", region: "nz")
  set par(leading: 0.6em, justify: true)
  set heading(numbering: "1.1")
  show heading.where(level: 1): set text(size: 15pt)
  show heading.where(level: 1): set block(above: 1.6em, below: 0.8em)
  show heading.where(level: 2): set text(size: 12pt)
  show heading.where(level: 2): set block(above: 1.3em, below: 0.6em)
  show heading.where(level: 3): set text(size: 10pt)
  show figure.caption: set text(size: 9pt)
  set table(stroke: 0.4pt + luma(70%), inset: 5pt)
  show table: set text(size: 9pt)
  body
}

// A number with thousands separators, rounded to `digits` decimal places.
#let num(value, digits: 0) = {
  let rounded = calc.round(value, digits: digits)
  let whole = str(calc.trunc(calc.abs(rounded)))
  let grouped = ""
  for (i, ch) in whole.clusters().rev().enumerate() {
    if i > 0 and calc.rem(i, 3) == 0 { grouped = "," + grouped }
    grouped = ch + grouped
  }
  let sign = if rounded < 0 { "−" } else { "" }
  if digits == 0 { return sign + grouped }
  let fraction = str(calc.round(calc.abs(rounded) - calc.trunc(calc.abs(rounded)), digits: digits))
  let decimals = if fraction.contains(".") { fraction.split(".").at(1) } else { "" }
  sign + grouped + "." + decimals + "0" * (digits - decimals.len())
}

// A probability or share as a percentage.
#let pct(value, digits: 0) = num(value * 100, digits: digits) + "%"

// Register entries by ID, as a list with each ID shown, so a reader can find
// the entry and the report cannot drift from it. `kind` is one of the
// register's sections: "Tasks", "Limitations", "Improvements", "Questions".
#let from-register(kind, ids) = {
  let field = (
    Tasks: "Task", Limitations: "Limitation",
    Improvements: "Improvement", Questions: "Question",
  ).at(kind)
  let entries = register.at(kind).filter(entry => entry.ID in ids)
  list(..entries.map(entry => [*#entry.ID.* #entry.at(field)]))
}

// A figure from a path the section's YAML gives, or a placeholder naming the
// script that draws it when the figure has not been drawn yet.
#let model-figure(path, caption, script: none, width: 100%) = figure(
  if path == none {
    block(
      width: width, height: 4cm, fill: luma(95%), stroke: 0.4pt + luma(70%),
      align(center + horizon, text(size: 9pt, fill: luma(40%))[
        Figure not drawn yet#if script != none [: run #raw(script)]
      ]),
    )
  } else {
    image("/" + path, width: width)
  },
  caption: caption,
)

// Where an input came from, and under what licence.
#let inputs-table(..rows) = table(
  columns: (2.2fr, 2fr, 1fr),
  align: left,
  table.header([*Input*], [*Source*], [*Licence*]),
  ..rows.pos().flatten(),
)
