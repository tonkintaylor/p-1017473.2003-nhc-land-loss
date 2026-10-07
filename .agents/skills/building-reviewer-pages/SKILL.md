---
name: building-reviewer-pages
description: >-
  Build or extend a reviewer page: one self-contained HTML file that walks a
  reviewer through how a model chain works, step by step, with a d3 flow
  diagram, maps of example sites cut from the current outputs, pilot-wide
  charts, key tables, numbered assumption boxes, cross-sections and a click-to-
  trace panel that follows one asset from input to damage. Use when the user
  asks for a reviewer tool, an explainer, a walkthrough, a "how does this module
  work" page or an HTML viewer of a module's method, wants to add a chain
  (liquefaction land, culverts, loss) beside the retaining wall one, or wants a
  step, map layer, chart, assumption or example site added to an existing page.
---

# Building reviewer pages

A reviewer page explains one model chain to the lead and a colleague who walk
through it together and record, against numbered assumptions, what they accept
and what must change. It lives in `src/scripts/landloss/reviewer/`, and its
first chain is retaining walls (`gen_reviewer_rw.py`). Read that script and
`template.html` before changing anything; this skill says why they are built the
way they are and how to extend them.

## The rules that make it work

1. **Show, never recompute.** Every map layer and count is cut from an output a
   step already wrote. The only computation allowed is drawing what a step
   saved: evaluating a fitted surface from its stored coefficients
   (`eval_quadratic`), or a lognormal curve from a table's p15 and p50. If the
   page needs a number no step writes (the points behind `p_prior`, say), say so
   on the page and ask for the step to write it. Never rebuild it in the
   generator.
2. **Import paths from the steps.** Get every file path from the step script's own
   path function (`wall_units_path(extent=...)`) in one `layer_files()` dict, so
   a renamed output follows automatically. Never type a `temp/...` path.
3. **A missing output is reported, not fatal.** `read_output()` returns `None` for
   a file that is not there, and the step shows "not built". This is the one
   place an explicit `path.exists()` is right: the page's job is to report state.
4. **Say when it is stale.** The wall work is rerun by several agents at once, so
   one build can mix runs. Keep `STALENESS_PAIRS` (a downstream file must be no
   older than its input) and `row_checks()` (row counts that must agree) current
   with the chain. Pair outputs of *different* scripts only: two files written
   seconds apart by one script make a false alarm.
5. **Sites are coordinates, not ids.** Unit, pif and wall ids are minted afresh on
   every run, so `sites.toml` stores an NZTM point and a `why` line. Pick sites
   with a throwaway query over the outputs (the densest cell, a fill on a road
   frontage, a forced polygon, a claim-raised unit) and record what each was
   chosen to show.
6. **Constants by name.** Write `{BETA_GNS_WALL_UNIT_FLOOR}` in the TOML, never
   `0.8`. `fill_constants()` fills it at build time from the modules in
   `CONSTANT_SOURCES` (`landloss.domain.constants`, then
   `instability_zones` for `PIP_DROP_M` and `PIF_JOIN_M`; add a module there
   when a step keeps its constants elsewhere), and raises on a name it cannot
   find. The wall constants changed
   three times in one afternoon while the first page was being built.
7. **Assumption ids are permanent.** `RW-A01`… are what the review transcript
   cites. Append new ones with the next number, mark a dropped one
   `status = "retired"` with what replaced it, and never renumber. Statuses are
   `decided` (give `decided = "the lead, <date>"`), `beta`, `pending` (name who
   in `note`), `adopted`, `check` (code and written method disagree) and
   `retired`. Take each from the code first and the method and status files
   second, and give its `source`.
8. **Date the narrative.** Each step's `checked` is when its text was last read
   against the code. The page flags a step whose newest output is later; update
   `checked` only after re-reading the step.
9. **Define before abbreviating.** Spell out every coined term at its first use
   on the page, which is the overview, not the step that introduces it: "a
   **pip**, a *potential instability point*". Take the expansion from the
   module docstring that coined it, never guess it.
10. **An arrow means "is made from".** Check every flow edge against the code.
    Where an input only flags, filters or raises something (GNS walls flag pifs
    but make none; buildings only remove pifs), give the edge a third element,
    a label, which the diagram shows as a numbered marker by its source with
    the text in a key below.
11. **The page is internal.** It embeds claim ids and claim report counts, so
   `report/reviewer/` is gitignored and the header says the file must not leave
   T+T. Never publish it as an Artifact or send it anywhere.

## Layout

| File | Holds |
| --- | --- |
| `reviewer/gen_reviewer_<chain>.py` | Reads outputs, cuts sites, builds sections and charts, inlines the JSON into the template. |
| `reviewer/template.html` | The generic page: d3 7.9, Leaflet 1.9.4 and marked 12 from cdnjs, everything else inline. Only `LAYER_STYLE` and `DRAW_ORDER` know about a chain. |
| `reviewer/config.py` | `EXTENT`, `WORLD_ID`, `REALISATION_ID`, `SITE_HALF_WIDTH_M`. No CLI arguments. |
| `reviewer/<chain>/steps.toml` | Title, overview, flow nodes and edges, inputs, and one `[[steps]]` table per step. |
| `reviewer/<chain>/assumptions.toml` | The numbered register. |
| `reviewer/<chain>/sites.toml` | Example sites. |

The output is `report/reviewer/<chain>/<chain>-reviewer<extent_suffix>.html`.

A `[[steps]]` entry names `outputs` and `inputs` (keys of `layer_files()`),
`layers` (keys of `LAYER_STYLE`; the first `visible` are switched on), `charts`
(keys `pilot_summaries()` writes), `tables` (CSV paths from the repo root),
optional `section = true` for a cross-section card, optional `pip_example = true`
for the worked pip rule, `checked` and `narrative`
(markdown; `RW-Ann` in it becomes a link to the box).

## Adding a chain

1. Copy `gen_reviewer_rw.py` to `gen_reviewer_<chain>.py` and make a `<chain>/`
   folder with the three TOML files. Keep the template shared; only add layer
   styles to it.
2. Map the chain first. Find each step's folder, scripts, path functions, outputs
   (rows, geometry, CRS), the joins between them and the existing `report/**/tab`
   CSVs. Delegate this sweep to an Explore agent and keep only its map.
3. Write `layer_files()`, the column lists for each layer (only chosen columns
   reach the page), `site_layers()`, `pilot_summaries()` and the checks.
4. Write the assumptions from the code. Where the method file disagrees with the
   code, mark it `check`.
5. `.gitignore` already ignores `report/reviewer/`. Confirm the new page lands
   under it with `git check-ignore -v <page>` before the first build is shared.

## Adding a map layer, chart or cross-section

- **Layer:** add a column list and a cut in `site_layers()` (use `around(frame, box)`;
  for a table of points, filter `x`/`y` and build points), then a `LAYER_STYLE`
  entry (`name`, `kind`, `style(props, stepId)`, optional `key`, `ramp`, `trace`)
  and its place in `DRAW_ORDER`. Every colour is a literal hex: a Leaflet canvas
  cannot resolve CSS custom properties.
- **Chart:** return `{"kind": "bar" | "tiles" | "table" | "curves", ...}` from
  `pilot_summaries()` under a key, and name the key in the step's `charts`.
- **Worked rule example:** follow `pip_example()` and `pipRule()`. The
  generator reads the real cells around one pip the model found, in the
  direction the model recorded, and passes the rule's constants from the code;
  the page applies the rule to them and lets the reviewer click any cell to
  test it. Choose an example where a test passes only narrowly, so the
  threshold is visible.
- **Cross-section:** follow `pif_section()`. Run the line along the direction the
  step itself measured in (for step 13, the pip's walk to its foot), sample the
  DEM, evaluate the step's saved surface, and draw both ends of the measurement.
  Draw it at true scale where it fits and label the vertical exaggeration
  otherwise. Say on the page when a class rests on medians over many points and
  the section shows one.

## Verifying a build

1. Run the generator from the PyCharm console or
   `uv run --frozen python src/scripts/landloss/reviewer/gen_reviewer_rw.py`.
   It prints the outputs read, the layers per site, the sections and the file
   size. Keep the page under about 10 MB: trim columns and coordinate precision
   (`COORDINATE_PRECISION_DEG`) before cutting sites.
2. Render it headless and count console errors. Any `CONSOLE` line is a failure:

   ```bash
   "/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new \
     --disable-gpu --user-data-dir="<scratchpad>\\chrome" --enable-logging=stderr \
     --virtual-time-budget=20000 --window-size=1400,9000 \
     --screenshot="<scratchpad>\\page.png" "file:///<repo>/report/reviewer/rw/rw-reviewer-pilot.html" \
     2>&1 | grep CONSOLE
   ```

   Append `#trace=<unit id>` to the URL to render the trace panel. Crop the tall
   screenshot with Pillow and look at each section, maps included.
3. Run `uv run --frozen prek run --files <changed files>` and the separate
   `uv run --frozen ruff check --select FIX` check.
4. Read the freshness panel and report every failing check to the user. A
   failing check is a finding about the model, not a bug in the page.

## Common mistakes

| Mistake | Consequence | Instead |
| --- | --- | --- |
| A TOML key such as `flow.edges = [...]` after `[[flow.nodes]]` tables | It becomes a key of the last node, and the flow diagram throws | Put scalar keys in a `[flow]` table *before* the arrays of tables. |
| Adding a Leaflet vector layer before `fitBounds` | `Cannot read properties of undefined (reading 'min')` | Draw extras after the view is set. |
| Laying an NZTM hillshade straight on a lat/lng box | Corners metres off the 1 m faces | Warp it to EPSG:3857 first, and add it to the `tilePane` with `mix-blend-mode: multiply` so it reads as relief, not a grey sheet. |
| Inlining JSON with `</` in it | The closing script tag ends the data early | `write_page()` escapes `</` as `<\/`. |
| Hard-coding a column that a step owner may rename | The build breaks when the table changes (the fragility table moved from `size_class` to `height_class`) | Read the column once, say in a docstring which names it has had, and fail loudly on any other. |
| Using a coined abbreviation (pip, pif, siz) before defining it | The reviewer reads the overview and diagram without knowing the terms | Define it in full in the overview, and again where its step begins. |
| An unlabelled arrow from an input that only flags or filters | The diagram claims GNS walls make pifs | Label the edge, and say in the step's text what the input does and does not do. |
| Quoting numbers from method files | The page states values the code no longer uses | Read the code and use constant placeholders. |
| Recomputing a missing intermediate in the generator | The page can disagree with the model it explains | Show what exists, and name the missing output as a finding. |
