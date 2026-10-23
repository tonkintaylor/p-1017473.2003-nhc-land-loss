---
name: writing-technical-appendices
description: How the appendices to the NHC land loss technical report are written, numbered, reviewed and built — Typst under report/technical/appendices/, every number read from YAML a script writes, method-only prose for readers who have not seen the code, review notes left in the document, a closing limitations table with each limitation's impact on losses, and one Word file per appendix for review on SharePoint. Use when drafting, editing or restructuring any appendix, taking a reviewer's tracked changes or comments from a Word copy back into the Typst, rebuilding the PDF or the Word copies, or adding a figure, table, citation or limitation to one.
---

# Writing the technical appendices

The main technical report is written in Word, outside the repository. The
appendices give its methods and results in more detail than its body does, and
they are written here, in Typst, so that every number in them can be traced to
the code or the run it came from.

The rules below were set by Perrie Gilbert and Maxim Millen across several
review rounds in October 2026. Maxim's review of the liquefaction appendix set
the style the others follow.

## 1. Where things are

| What | Where |
| --- | --- |
| The document | `report/technical/appendices.typ`: title page, contents, the appendices in order, references |
| One file per appendix | `report/technical/appendices/<topic>.typ` |
| Shared style and helpers | `report/technical/lib.typ`: `style`, `num`, `pct`, `inputs-table`, `limitations-table`, `model-figure`, `review` |
| References | `doc/references.bib` |
| Numbers | `report/<module>/.../tab/report-numbers.yaml`, written by a `gen_report_numbers.py` beside the module's scripts |
| Figures | `report/<module>/.../fig/`, drawn by `fig_*.py` scripts (`fig/` folders are git-ignored) |
| Word copies for review | `report/technical/appendices-docx/`, one per appendix (untracked) |

The appendices, in order, with the page budgets agreed with Maxim (each plus
about half a page of limitations and half of improvements):

| Appendix | File | Budget |
| --- | --- | --- |
| Estimation of locations of bridges and culverts | `bridges_culverts.typ` | under a page, one map |
| Calculation of liquefaction damage (lateral spreading a subsection) | `liquefaction_damage.typ` | about 4 pages |
| Calculation of cost estimation | `cost_estimation.typ` | walls about 2, liquefaction about 1 |
| Calculation of land value | `land_value.typ` | 1 to 2 pages |
| Retaining wall types, locations and sizes | not yet written | 2 to 5 pages |
| Landslide model | not yet written | about 6 pages |

Letters are assigned by order in `appendices.typ`. A review note at the top asks
for them to be matched to the letters the main report uses.

## 2. Who the appendices are written for

Readers of the technical report: NHC and its reviewers. They have **not** seen
the repository and have no coding experience.

- **Method only.** No script, file, function, setting or column names; no
  release codes; no register IDs (L-, T-, Q-). Say what the method does, not
  where it lives.
- Keep the traceability out of the reader's way, in Typst `//` comments: the
  scripts that write the numbers at the top of each file, and the register IDs
  beside each limitation.
- **Cut what the main report already covers**: NHC's settlement rules (the
  cap, the sub-caps, the excess), how NHC claim reports describe damage, the
  provisional seismic demands, the study area. Point to the main report rather
  than repeat it.
- **Give the reason for each choice**: "to align with the 2,500-year seismic
  hazard", "still in development", "a share is used rather than the flat total
  because …".
- **Show a rule with a figure or a table, not its arithmetic.** The lateral
  spreading adjustment is a figure; the land value worked example is a table.
- **Put a result next to the method step it illustrates**, not in a distant
  Results section.
- **Drop checks that only confirm the code does what it says.** Keep checks
  against something independent, such as Canterbury claim costs.
- **Plain words for the method.** "Sampled from its probabilities", not "picked
  at random"; "uniformly sampled from the range"; the liquefaction lateral
  spreading change is an **adjustment**, not a correction.

## 3. House style

- **No bold in body text**: not for lead-in words, defined terms or list items.
  Bold is for table headers and for the direction word that opens an "Impact on
  losses" cell.
- Introduce every table and figure in the text with a cross-reference (`@label`)
  before it appears. A table nobody refers to is a review comment waiting.
- Refer to other appendices by label (`@cost-estimation`), which prints
  "Appendix C", never by name.
- Tables and figures are numbered within their appendix (Table B.1, Figure D.2).
  `appendices.typ` does this; do not number by hand.
- Every table, the inputs table included, is a captioned `#figure` with its
  caption **above** it (Virginie Lacrosse's review); a figure's caption sits
  below. `lib.typ` places them, and `tidy_docx.py` moves them above in Word,
  where pandoc puts them below.
- Each appendix runs: Context; Inputs (`inputs-table`); Method, with a
  subsection per step; Results; Validation; Limitations and future improvements.
- Formulas are Typst maths (`$ R = V / (...) $`); they reach Word as equations.
  Symbols in text and tables are maths too (`$R$`, `$A_"house"$`).
- Report figures carry **no title or footnote**, since the caption and the text
  give the context, and their text is large enough to read on the page. Where a
  validation figure exists with titles and notes, draw a separate report version
  rather than reuse it (see `report_example_figures` in
  `loss/validations/gen_qv_average_rate.py`). One figure per example, so each
  can be referred to on its own.

## 4. Every number comes from YAML

No number is typed into an appendix. Each appendix reads one or more
`report-numbers.yaml` files, written by a script that reads the constants that
set the model and the outputs of the run:

| Appendix | Numbers script |
| --- | --- |
| Bridges and culverts | `exposure/culverts_bridges/report/gen_report_numbers.py` (and `fig_crossing_map.py`) |
| Liquefaction damage | `hazard/liquefaction/report/gen_report_numbers.py`, `vul/liquefaction/land/report/gen_report_numbers.py` |
| Cost estimation | `loss/report/gen_cost_report_numbers.py` |
| Land value | `loss/report/gen_report_numbers.py` |

- Settings are read from the constants that set them (`pricing.py`, step
  `config.py` files), so a changed setting changes the appendix on the next run.
- Derived values are computed in Typst from settings (`#pct(1 - x)`, the worked
  examples) rather than stored.
- Runs over the four territorial authorities overlap at the edges, because each
  extent is a bounding box. Count each property, cell or crossing only in the
  authority it lies in (`within_authority` in the vul liquefaction script).
- **The QV rating roll is sensitive.** Write only counts, medians and the worked
  examples from it, never a property's value.
- Never read the T: drive directly. Scripts that need the roll run in local mode
  after confirming the cached files exist:
  `TTDRIVE_SYNC_LOCAL_MODE=True TTDRIVE_SYNC_LOCAL_VERSION=local uv run --frozen python …`
- Wherever a reviewer edits a number, check it against the YAML. If they
  disagree, leave a review note rather than overwrite either.

## 5. Review notes, not chat questions

Anything for the author to check or decide (an unverified source, a placeholder,
a discrepancy, an open choice) goes in the document as `#review[...]` at the
point it arises. The author reviews by reading top to bottom, so a question
asked in chat loses its context.

- Write the note to the author, plainly: what is uncertain and what would
  settle it. Phrase it as a question where the author has to decide.
- Remove a note once it is resolved. Do not keep notes about page budgets once
  the author has seen them.
- `--input review=false` compiles a copy without them.

## 6. Limitations and future improvements

One section per appendix, "Limitations and future improvements", holding one
table built with `limitations-table`: number, limitation, impact on losses,
improvement. Each row pairs a limitation with the improvement that would address
it.

```typst
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @liq-limitations-table lists each, its likely
effect on the modelled losses, and the improvement that would address it.

#figure(
  limitations-table(
    (
      [The NLM over-predicts damage in the interbedded silt deposits common in
        the Hutt Valley.],
      [*Over-prediction* of Hutt Valley losses.],
      [Apply the LSN#sub[Ic10] correction … @tonkin_taylor_2026_lsnic10.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <liq-limitations-table>
```

- The impact opens with its direction in bold: **Over-prediction**,
  **Under-prediction**, **Mixed** or **Unknown**, then a short reason.
- Impacts are judgement. When you draft them, add a review note asking the
  author to check each direction.
- Do not list as an improvement something the model or viewer already does (the
  viewer already runs a no-volunteer scenario).

## 7. Citations

- Cite with `@key` from `doc/references.bib`; the bibliography is APA. Two works
  by one author in one year get 2026a and 2026b automatically.
- Keys are `first_author_year` (organisations shortened: `tonkin_taylor_2026`),
  with a topic suffix for a second work in a year
  (`tonkin_taylor_2026_lsnic10`). Maxim prefers Papers-style keys
  (`Author:2026ab`); that is still open, and a rename is a find-and-replace.
- An entry written from anything other than the document itself carries a
  `note` saying so and what to verify.
- Typst quirks: a dataset is `@dataset` with `type = {Dataset}` (`@misc` prints a
  stray comma); an article number is `pages = {Article 04020142}` (a bare number
  loses its leading zero).
- The T+T document search can find issued reports for checking a reference; the
  network drives cannot be read directly.

## 8. Building

```powershell
# PDF, with review notes
typst compile --root . report/technical/appendices.typ
# PDF without them
typst compile --root . --input review=false report/technical/appendices.typ
```

The Word copies go Typst → HTML → Word, as Maxim proposed. Typst's HTML export
is experimental; pandoc comes from the `pypandoc-binary` package, so nothing is
installed system-wide:

```powershell
typst compile --root . --features html --format html report/technical/appendices.typ <scratch>/appendices.html
uv run --no-project --with pypandoc-binary --with python-docx python .agents/skills/writing-technical-appendices/scripts/split_docx.py <scratch>/appendices.html report/technical/appendices-docx
```

`split_docx.py` cuts the HTML at each appendix heading and gives each its own
title and a reference list of only the works it cites; `tidy_docx.py` borders the
tables, left-aligns long cells, fits images and shades review notes. Run them
without `-I`, so `split_docx.py` can import its sibling.

Cross-references between appendices keep their text in the separate Word files
but do not link across files.

**Rebuilding overwrites `report/technical/appendices-docx/`.** Reviewed copies
belong somewhere else, such as the author's Projects folder. On 2026-10-23 a
rebuild destroyed comments the author had put in those files, so
`split_docx.py` now refuses to run while any file there carries comments or
tracked changes. Before rebuilding, also ask whether anyone has been editing
the copies there; a file with plain edits and no comments is not caught.

Check the result by looking at it: render PDF pages to PNG (`typst compile
--ppi 80 … page-{0p}.png`), and export each Word file to PDF through Word (COM
from PowerShell) and render that, to catch tables, equations and figures that
come through badly.

## 9. Taking a review back into the Typst

1. Copy the reviewed Word file to a scratch folder; never edit it.
2. Read it, with the version that was sent if there is one:

   ```powershell
   uv run --no-project --with pypandoc-binary python -I .agents/skills/writing-technical-appendices/scripts/read_review_comments.py <reviewed.docx> <sent.docx>
   ```

   It prints the tracked-change counts, every comment with the text it is on,
   and the text changes. Edits made without tracking only show in that diff.
3. Apply the edits to the Typst in the reviewer's words, fixing only typos. Keep
   numbers coming from the YAML.
4. Check every factual claim a reviewer adds against the code before writing it
   in. Where it does not match (a figure the code records as judgement, a
   setting applied only in the viewer), keep their wording and add a review note
   saying what the code does.
5. Turn each comment into an edit, or into a review note where it needs the
   author or someone else.
6. From a reviewer's edits, carry their style to the appendices they did not
   review.
7. Rebuild the PDF and the Word copies, and look at the changed pages.

## 10. Facts that are easy to get wrong

- **GST**: costs are estimated excluding GST and grossed up before the
  comparison with the land cover cap. The QV land value is taken as already
  including GST and is not grossed up, so the comparison is like for like. The
  viewer works before GST and divides the land rate by 1.15.
- **Escalation**: only the 2011 Canterbury liquefaction costs are escalated
  (×1.42, the construction labour cost index). The costing tool rates are
  current prices.
- The Canterbury claimant costs **exclude** any claim with retaining wall,
  culvert or bridge repair.
- The 250 m² cleared by volunteers is recorded as calibration judgement; no
  250 m² figure was found in the NHC costing tool.
- The **90% insurance penetration** is a loss viewer setting, not applied in the
  damage steps, so claim counts in the appendices are before it.
- The **None state's claims** are an artefact of its 95% drop-out rate: they
  lose no ground and cost nothing.
- **Lower Hutt's free faces** in the 14 October 2026 build cover only the old
  pilot box (L-88). The fix is held back because the build was issued (T-167),
  and the appendix discloses it.

## 11. Finishing

- Run the hooks on the files touched: `uv run --frozen prek run --files …`
  (twice if the first run reformats).
- Add a changelog fragment for each change (`doc/whatsnew/pg.doc.<yymmddhhmm>.md`
  for writing, `pg.feature…` for a model change); never append to one.
- Commit only when asked. Stage the files of this work explicitly; leave the
  author's other uncommitted work (step configs, other features) and the Word
  copies out.
