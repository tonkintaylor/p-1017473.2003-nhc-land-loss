# Agent Instructions

See the .agents/skills directory. You MUST use skills for all tasks.

You must start with `using-superpowers` for EVERY task, no matter how small. Keep `self-reflecting` active throughout — invoke it whenever you encounter failures, retries, or corrections. Before finishing you MUST use `verifying-claims` to verify your work, no matter what.

These are essential skills.

Use the `using-prek-pre-commit` skill when running pre-commit checks.

Extended thinking should only trigger for multi-step reasoning problems. When in doubt, respond directly without extended analysis.

## Script naming

A script is named for what it produces, so a directory listing says what each
file is for without opening it. Use these prefixes:

| Prefix | Produces |
| --- | --- |
| `fig_` | A figure, for the report or for a validation. |
| `table_` | A CSV table for the report. |
| `gen_` | A generated layer — data this project derives and writes out. |
| `get_` | A retrieved layer — data fetched from a source someone else maintains. |

Do not use `plot_`; a figure script is `fig_`. The `gen_` and `get_` distinction
is the one that carries weight: it separates code that creates new data, which
has to be re-run deliberately and its output tracked, from code that only fetches
what already exists. Reading a LINZ layer through Koordinates is a `get_`;
deriving the study area boundaries from that layer is a `gen_`.

`gen_` and `get_` apply to functions as well as to filenames, so a function that
retrieves a layer is `get_`, not `load_` or `fetch_`.

## Changelog fragments

Changelog fragments in `doc/whatsnew/` are named
`{initials}.{type}.{yymmddhhmm}.md`, for example `mm.feature.2609251430.md`, and
towncrier assembles them into `CHANGELOG.md` at release. The initials are those of
the developer writing the fragment and the timestamp is when they wrote it.

The scheme exists because the earlier `{issue_num}.{type}.md` names were in
practice a running counter, not JIRA numbers: two branches in progress at once
each took the next free number, so every merge between them collided on the same
filenames. Initials keep two people's names apart, and the timestamp keeps one
person's names apart across branches. Towncrier reads the part before the type as
the issue and prints it beside the entry, so the changelog shows who made each
change, and it reads the digits after the type as a counter that orders entries
by date.

- Write a new fragment for every change. Do not append to an existing fragment,
  even one on the same topic: two branches appending to one file conflicts
  whatever the file is called.
- The type is one of the `[[tool.towncrier.type]]` directories in
  `pyproject.toml`.
- The timestamp has to be digits only. Towncrier ignores a non-numeric suffix,
  and two such names with the same initials and type then abort the build.
- Two hooks in `.pre-commit-config.yaml` enforce this. `whatsnew-fragment-name`
  rejects an old numbered name or one missing its timestamp. `towncrier-draft`
  runs `towncrier build --draft`, which rejects initials not in `issue_pattern`
  and two fragments that resolve to the same name.

To add a contributor, add their initials to `issue_pattern` under
`[tool.towncrier]` in `pyproject.toml` (for example `"mm|pg|ab"`). If two people
share initials, give one of them a third letter.

To change the naming scheme again, rename every existing fragment in one commit
with `git mv`, so history follows the files and git's rename detection can carry
edits from other branches across. Do it straight after the open branches have
been merged together, when no one has fragments in flight, and tell the other
developers before they write their next fragment. Take each fragment's author and
date from the commit that added it
(`git log --diff-filter=A --format='%an|%ad' -- <file>`). A fragment first created
in a merge commit, where a conflict was resolved by renumbering, has no add commit
on its own branch. Attribute it by searching for its code with
`git log --all -S"<identifier>"`. Build `towncrier build --draft` before and after
the rename and check the entry count is unchanged. On Windows, run it with
`PYTHONUTF8=1` or `python -X utf8`, because the default console encoding cannot
print the macrons in the fragments.

## Koordinates readers

Every reader of a Koordinates layer must record that layer's data licence in its
docstring, under a `Licence:` section, together with what the licence requires of
us in practice — not just its name. Most of these datasets are CC BY, which
obliges us to attribute the source in anything derived and published, so the
obligation has to be visible to whoever is writing the figure or table, not
buried on a portal page.

Take the licence from the layer's own metadata rather than assuming. The
Koordinates API answers anonymously for metadata, even where downloading needs a
key:

    curl -s "https://<domain>/services/api/v1.x/layers/<layer_id>/"

The response carries `license` (title, type, version, url), `publisher` and any
`doi`, which is everything the docstring needs.

Record the publisher and any DOI in a `Source:` section alongside it. Layer IDs
belong in `landloss.domain.constants` with the portal URL in a comment, never
inline in the reader.

## Reference documents

A paper, report or map booklet that the method is being read out of gets
**downloaded into `temp/reference/<topic>/`** rather than linked and re-fetched.
`temp/` is gitignored, so none of it is tracked and none of it is a licensing
decision — it is a working copy, kept because a URL that answered today is not
guaranteed to answer next month, and because searching a local PDF beats
re-reading a web page.

- Name the file so it says what it is without being opened:
  `{author}-{year}-{short-title}.pdf`, for example
  `kingsbury-1995-eq-slope-failure-wellington-WRC-PP-T-95-06.pdf`.
- Keep a `SOURCES.md` in each topic folder listing every file, one line on what
  it is, and the URL it came from. A PDF whose provenance has been lost is worth
  less than no PDF.
- **If a document turns out to be genuinely relied on** — its numbers are in the
  code, or the report will cite it — it moves somewhere durable and the move is
  recorded. `temp/` is a staging area, not a library, and it can be deleted at
  any time without warning.
- **The durable home is `context/lit/<topic>/<author_year>/`**, tracked in git,
  for example
  `context/lit/landslide/nowicki_jessee_2018/nowicki-jessee-2018-global-seismic-landslide-model.pdf`.
  Each topic folder carries a `SOURCES.md` in the same form as the `temp/` one.
- **A file over 50 MB stays out of git**, because GitHub warns above that size
  (the hook's hard limit is 100 MB). It is kept at `U:\MAMI\Literature` and its
  `SOURCES.md` row says so, with the size, giving the same `{author}-{year}-{short-title}.pdf`
  name. Write a `<author>-<year>-summary.md` beside it in the `context/lit/`
  folder if the paper's content needs to be searchable from the repository.
- Do not put anything in `temp/reference/` that may not be redistributed inside
  T+T. Public reports and papers are fine; a client's confidential document is
  not.

## Project context

Background on what this project is for lives in `.agents/context`. Read these
before making decisions about methodology, outputs, or what belongs in the tool:

- `.agents/context/project-objectives.md` — what NHC has asked T+T to deliver and
  how the work is expected to be run.
- `.agents/context/project-scope.md` — the four project phases, their key tasks,
  the out-of-scope items, and the deliverables.
- `.agents/context/nhc-event-parameters-email.md` — NHC's brief on the event
  geography, exposure and insurance profile the study should be shaped around.
- `.agents/context/nhc-land-cover-and-settlement.md` — how NHC cover attaches to a
  property, how retaining walls and sub-caps are settled, and what is still unconfirmed.
- `.agents/context/land-damage-mechanisms.md` — the team's working picture of how land
  damage actually occurs in Wellington, and what that means for the model.
- `.agents/context/canterbury-land-claim-costs.md` — the Canterbury payout data the
  cost model is anchored on, what it excludes, and why its category numbers are
  damage types rather than severity levels.
- `.agents/context/nhc-costing-tool.md` — how NHC prices the repair of damaged land
  and land structures: the Land SOW build-up, the enabling works and
  constructability multipliers, and the rate sheet the study's own rates come from.
- `.agents/context/data-sources.md` — which dataset comes from where, and what is not
  obtainable.
- `.agents/context/nhc-natural-hazards-portal.md` — why the public Natural Hazards
  Portal must not be scraped, and what to ask NHC for instead.
- `.agents/context/code-structure.md` — the four analysis modules, the library and
  scripts split, and the causes of financial land loss the model represents.

The live register of tasks, limitations and future improvements is
`.agents/context/register.json`. It renders to a workbook in the OneDrive project
folder rather than the repo. Edit the JSON and
regenerate; see the `recording-project-context` skill.

## Module structure

`exposure`, `hazard` and `vul` are each split into submodules, in both
`src/landloss/` and `src/scripts/landloss/`: `exposure` by insured asset type
(`land`, `rw`, `culverts_bridges`), `hazard` by hazard (`liquefaction`,
`landslide`,
`shaking`), and `vul` by hazard and then asset type (`vul/liquefaction/land`).
`loss` is flat.

`steps/`, `validations/`, `report/` and `research/` are submodules of whichever
level the work belongs to. Work specific to one asset or one hazard goes in that
submodule; work shared across all of them — the address spine, the valley
cross-sections, the NHC claims datasets — stays at the module level. None of them
is created until there is something to put in it, and no submodule is created
speculatively either.

Every submodule of `exposure`, `hazard` and `vul` carries a brief `status.md`
at its own level — `exposure/<asset>/`, `hazard/<hazard>/`,
`vul/<hazard>/<asset>/` — with the sections `## Approach`, `## Where it is now`,
`## Next`, then `## Validation` and `## Open decisions`. It is the submodule's
orientation page, distinct from the per-step plan and method files, and it points
at those for detail rather than restating them. Where nothing is implemented yet
it says so plainly and labels the approach as intended.
`hazard/shaking/status.md` is the example.

These files are updated as the work moves and the weekly progress update to NHC
is assembled from them, so a stale one puts a wrong statement in front of the
client. Any change to a submodule's scripts updates that submodule's `status.md`
in the same change. Use the `maintaining-status-files` skill whenever you write
or update one.

## Weekly updates

The weekly progress update to NHC is generated from those status files into
`release_updates/update_week_of_<monday>.typ`, from the Typst template beside it,
and the project lead edits and finalises it. It is never written from scratch and
never sent. Use the `writing-weekly-updates` skill whenever you are asked for the
weekly update, a weekly summary or a progress update.

Repo-relative paths come from `src/scripts/landloss/paths.py` (`REPO_ROOT`,
`REPORT_DIR`, `RESEARCH_DIR`, `TEMP_DIR`) and packaged data files from
`landloss.io.ASSETS_DIR`. Scripts sit at several depths, so never resolve either
with a `Path(__file__).resolve().parents[N]` count of your own.

See `.agents/context/code-structure.md` for the reasoning behind both axes.

## Step scripts

Every step lives in its own numbered folder under a `steps/` directory, carrying,
alongside its scripts, an implementation plan written in phases and a method file
describing the methodology as currently implemented. Any change to a step's
scripts must update that step's method file in the same change. Step numbers run
across the module, so a step keeps its number when it sits in a submodule's
`steps/`.

Use the `adding-steps-scripts` skill whenever you add a step, change one, or
wonder where a piece of methodology should be written down.

## Research scripts

- A new utility a research script needs lives in the script itself or in the
  `research/` folder. A research script may rely on functions in
  `src/landloss/` and on outputs from `steps/`; if those change and a research
  script breaks, that is fine, because research scripts are not maintained.
- Research scripts are excluded from the pre-commit checks.
- `src/landloss/` and `steps/` never import from a `research/` folder. Ruff
  enforces this with `flake8-tidy-imports.banned-api` (TID251) in
  `pyproject.toml`, which lists each research package by name, so add a new
  `research/` folder to that list.

## Environment variables

`README.md`'s "Environment variables" section must document every variable in
`.env.example`. Any change that adds or changes a `.env` variable must update
that section in the same change — it is the one place a new developer can read
what every variable does without hunting through source.


## Script configuration

Scripts under `src/scripts/` must not use `argparse` (or any other CLI-argument
parser) to make paths or other settings configurable. Hardcode the paths
directly in the script instead, using `tdrive_sync`/`versioned_store` to
resolve anything that lives on T: or in the versioned data store. A script's
behaviour should be determined entirely by reading its source, not by
undocumented flags a caller might pass.

Settings that do change between runs — an extent, a seed, whether to reuse a
cache — go in a `config.py` beside the scripts, read in the
`if __name__ == "__main__":` block and passed into `main()` as keyword
arguments. `main()` holds no defaults of its own, and every script in the step
reads the same `config.py`. See section 2a of the `adding-steps-scripts` skill.

Do not guard against missing files or an unmapped T: drive with manual
`try`/`except`/`path.exists()` checks that print a friendly message and
`return 1`. Let the natural exception (`FileNotFoundError`, `ValueError`,
etc.) propagate — its traceback already says what went wrong.

`main()` should not return a status code, and the `if __name__ == "__main__":`
block should do nothing but read `config.py` and call it:

```python
if __name__ == "__main__":
    main(pilot=config.PILOT, seed=config.SEED)
```

Do not add a `status = main(); if status: raise SystemExit(status)` dance.