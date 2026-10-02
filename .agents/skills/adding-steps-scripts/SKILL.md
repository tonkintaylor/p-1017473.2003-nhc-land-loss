---
name: adding-steps-scripts
description: How a step is laid out under a steps/ folder in src/scripts/landloss — its own numbered folder holding the scripts, a phased implementation plan with progress checked off, and a method file describing what is actually implemented and pointing at where each piece lives. Use whenever adding a new step to any module, changing the scripts inside an existing step, or asked where a step's methodology or its planned work is written down.
---

# Adding and changing step scripts

A step is a stage of a module's build: ordered, re-runnable, and owned by one
folder. Every step in the repository carries the same two markdown files beside
its scripts — a plan of what is intended, and a method description of what is
actually there. This skill defines that convention and what has to happen to the
two files when the scripts change.

The split exists because the two documents are read at different times by
different people. The project report is assembled later, from method files that
are already current; the team meanwhile keeps iterating quickly on the scripts.
If the methodology only ever existed as intent, writing the report would mean
reverse engineering four modules' worth of scripts at the point when there is
least time to do it. Keeping the description current as the work happens is
cheaper than reconstructing it afterwards.

The guiding rule follows from that: **the method file describes what the code
does today, never what it is meant to do.** Anything aspirational — a refinement
not yet coded, a dataset not yet obtained, a simplification to be revisited —
belongs in the implementation plan and nowhere else.

## 1. Which `steps/` folder the step belongs in

`steps/` is not only a module-level folder. `exposure`, `hazard` and `vul` are
each split into submodules — by insured asset type, by hazard, and by both — and
`steps/` exists at whichever level the step's work actually belongs to. Before
creating a folder, decide which that is:

| The step's work is specific to | Its `steps/` folder |
| --- | --- |
| One insured asset type | `exposure/<land\|rw\|culverts_bridges>/steps/` |
| One hazard | `hazard/<liquefaction\|landslide\|shaking>/steps/` |
| One hazard and one asset type | `vul/<hazard>/<asset>/steps/` |
| Everything in the module alike | `<module>/steps/` |

The last row is the exception, not the default. The address spine is there
(`exposure/steps/s1_address_spine/`) because land, retaining walls, culverts
and bridges
all hang off the same properties; a step that only serves one of them does not
belong at that level. See `.agents/context/code-structure.md` for the two axes
and why they are split that way.

## 2. The layout of a step folder

Each step lives in its own numbered subfolder under the `steps/` directory,
named `s<n>_<topic>`:

```text
src/scripts/landloss/exposure/
    steps/
        __init__.py
        s1_address_spine/          # shared: every asset type hangs off it
            ...
    land/
        steps/
            __init__.py
            s2_land_value/
                __init__.py
                config.py                  # the run settings; see section 2a
                s2_land_value_implementation_plan.md
                s2_land_value_method.md
                s1_build_terrain_attributes.py
                s4_estimate_land_value.py
                fig_land_value_map.py
```

Step numbers run across the whole module, not across one `steps/` folder, which
is why `s2_land_value` is `s2` even though it is the only step under
`exposure/land/`. The number carries the run order, so a step folder is not
renumbered once other steps or documents refer to it — including when it moves
into a submodule.

The two markdown files are prefixed with the step folder's own name, which keeps
them distinguishable when several are open at once and makes them findable by
name across modules.

Both markdown files are **tracked in git**. They are the step's documentation,
not scratch notes, and their diffs are how a reviewer sees the methodology change
alongside the code that changed it.

Every new folder needs an `__init__.py` with a one-line module docstring naming
the level it belongs to, matching the existing `"""Steps that build the land
exposure."""` under `exposure/land/steps/`. With the submodules in place, that
docstring is what a directory listing has to explain itself with, so
`"""Steps."""` is not enough.

Scripts inside follow the naming prefixes in `AGENTS.md` — `fig_`, `table_`,
`gen_`, `get_` — and the run settings pattern in section 2a. Each carries a
module docstring with the literal run command and any required `.env` keys.

## 2a. Run settings live in the step's `config.py`

**A step script takes no command line arguments.** No `argparse`, no other
parser, no flags. A flag left off the command line is invisible afterwards, and
a realisation is a result somebody has to be able to account for months later.
`AGENTS.md` states the prohibition; this section says what to do instead.

Everything that changes between one run and the next goes in a `config.py`
beside the scripts, read in the `if __name__ == "__main__":` block and passed
into `main()` as keyword arguments:

```python
# config.py
"""Run settings for the landslide realisation step."""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Leave this True while the model is being changed.
PILOT = True

# The random seed, so a realisation reproduces exactly.
SEED = 1017473
```

```python
# s1_simulate_landslides.py
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import config


def main(*, pilot, seed):
    """Draw one realisation of landslides and write it out.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        seed: The random seed, so the realisation reproduces exactly.
    """
    ...


if __name__ == "__main__":
    main(pilot=config.PILOT, seed=config.SEED)
```

Three rules follow, and the value of the pattern is lost if any is skipped.

- **`main()` takes the settings as arguments and holds no defaults of its own.**
  A default in the signature is a second place the value lives, and the two
  disagree the first time one is changed.
- **`main()` returns nothing.** No status code, and no
  `status = main(); if status: raise SystemExit(status)` dance — that surfaces
  in the PyCharm console the step is usually run from as a `SystemExit: 0`
  traceback. Let a genuine failure raise: the traceback says more than a printed
  message and a `return 1` would.
- **Every script in the step reads the same `config.py`.** A figure script that
  rebuilds the output path from its own copy of `PILOT` will one day draw a
  different extent from the one that was run. Have the script that writes the
  output expose a small function returning its path, and have the figure call
  it.

`config.py` is tracked, like the two markdown files: its diff is the record of
what a given run was configured to do.

Paths out of the repo come from `src/scripts/landloss/paths.py` — `REPORT_DIR`,
`RESEARCH_DIR`, `TEMP_DIR`, `REPO_ROOT`. Do not resolve the repo root with
`Path(__file__).resolve().parents[N]` in a step script: steps sit at several
different depths, and a miscounted `N` writes the output somewhere nobody looks
for it rather than raising.

## 3. The implementation plan

`<step>_implementation_plan.md` is written in phases, with progress marked off in
markdown checkboxes as each phase completes. It is the only place intent lives,
so it holds the work not yet done, the shortcuts taken deliberately, and the
improvements someone has asked for but that are not in the code.

Ticking a box is a statement that the code exists and runs, not that it was
started. A phase that turned out to be unnecessary is marked `Dropped` with a
reason rather than deleted — why a phase was abandoned is often the thing a later
reader needs.

Copy this template:

```markdown
# Step 2 — Land value: implementation plan

**Status:** Phase 2 in progress.

## Phase 1 — Source the rating values (complete)

- [x] Read the rating valuation layer for the study area (`get_rating_values.py`).
- [x] Confirm the parcel identifier joins to the exposure parcels.
- [x] Check the coverage across the four territorial authorities.

## Phase 2 — Derive a land value per parcel

- [x] Split the capital value into land and improvement components.
- [ ] Handle parcels carrying no valuation — currently dropped, which needs a
      decision on whether to infer a value from neighbours.
- [ ] Figure showing the land value distribution by territorial authority.

## Phase 3 — Revalue to the study date

- [ ] Apply an index from valuation date to the study date. Not started; the
      index source is still to be agreed with NHC.

## Potential future improvements

- Use sale prices rather than rating valuations where they are available; more
  accurate, but the data is not held for the full study area.
- Value the land separately from the retaining walls on it, which the current
  single figure per parcel does not distinguish.
```

## 4. The method file

`<step>_method.md` is a bullet-point description of the methodology **as
currently implemented**. Each bullet says what the step does and points at where
that information actually lives — the script, the function, the asset file, the
figure — rather than restating the content in prose.

This pointing rule is the substance of the convention. The project lead's own
example: the main centres the step uses are described as being *shown in the
figure produced by `fig_town_centres.py`*, rather than the list of centres being
retyped into the file. A restated list is a second copy that goes stale silently
the first time the script changes; a pointer cannot. So write a bullet as a
sentence about what happens, with the artefact that carries the detail named in
it.

Write plainly about what the code does. Do not hedge, do not describe
alternatives considered, and do not write "will" — any sentence with a "will" in
it belongs in the plan file.

The file **ends** with exactly this line, so a reader who wants to know what is
missing is sent to the one place that says:

```text
Potential future improvements: see `<step>_implementation_plan.md`.
```

Copy this template:

```markdown
# Step 2 — Land value: method

- Rating valuations are read for the four territorial authorities in the study
  area by `get_rating_values.py`, which pulls the valuation layer through
  Koordinates and clips it to the study extent.
- The valuation is joined to the exposure parcels on the parcel identifier by
  `join_valuations_to_parcels()` in `gen_land_value_per_parcel.py`. Parcels with
  no matching valuation are dropped, and the count dropped is printed by the run.
- Land value is taken as the land component of the rating valuation, not the
  capital value, so buildings are excluded — the split is done in
  `split_capital_value()`.
- The coverage achieved across the study area is shown in the figure produced by
  `fig_land_value_coverage.py`, written to `report/exposure/land_value/fig/`.
- Valuations are used at their own valuation date; no revaluation to a common
  date is applied.

Potential future improvements: see `s2_land_value_implementation_plan.md`.
```

Note the fourth bullet naming a figure rather than describing it, and the last
one stating a simplification flatly. Both are true of the code as it stands, and
both are what the report needs.

## 5. Any script change updates the method file

**A change to a step's scripts updates that step's method file in the same
change.** Preventing drift between the two is the entire reason the convention
exists, and a method file three commits behind the code is worse than no method
file, because it is believed.

In practice:

| What changed in the scripts | What happens in the method file |
| --- | --- |
| A new script, or a new stage within one | A new bullet naming it |
| A function renamed or moved | The bullet pointing at it is corrected |
| A default, threshold or dataset swapped | The bullet stating the old one is rewritten |
| A figure added | A bullet naming the script and its `fig/` directory |
| A simplification implemented properly | The bullet describing it is rewritten, and the matching plan box is ticked |
| A script deleted | Its bullet is deleted |

If a change implements something the plan listed, tick the box in the plan **and**
add or rewrite the method bullet. Those two edits belong in the same commit as the
code; splitting them into a follow-up is how drift starts.

Only the method file is constrained this way. The plan can be edited on its own
whenever the intent changes, which is expected.

## 6. Figures and where plotting lives

A figure produced by a step goes to a directory that mirrors the step's own
module path, then names the topic — so `exposure/land/steps/s2_land_value/`
writes to `report/exposure/land/land-value/fig/`. Build the path from
`REPORT_DIR` (or `RESEARCH_DIR` for exploratory work) in
`src/scripts/landloss/paths.py`, never from a `parents[N]` count or a hardcoded
path.

Any directory named `fig` is gitignored, so figures are regenerated rather than
committed and the script is the record of how each one was made. That is exactly
why a method bullet may point at a figure: the figure itself is not in the
repository, but the script that draws it always is.

Keep the plotting logic in the step's script. Only genuinely shared styling — the
map panel helpers in `src/landloss/common/utils/plot.py` — belongs in the
library. A figure script is `fig_`, never `plot_`.

## 7. Checklist: adding a new step

1. Decide which `steps/` folder the step belongs in (section 1), then create
   `s<n>_<topic>/` under it with an `__init__.py` carrying a one-line module
   docstring. Number the step across the module, continuing from the highest
   `s<n>` already in it, wherever in the module that step sits.
2. Write `s<n>_<topic>_implementation_plan.md` first, in phases, with every box
   unticked. Writing the phases before the code is what makes the plan worth
   reading later.
3. Write the scripts, following the naming prefixes, and put every run setting
   in `config.py` beside them rather than in a flag (section 2a).
4. Write `s<n>_<topic>_method.md` describing what you actually built, with every
   bullet pointing at a script, function, asset or figure, and ending with the
   `Potential future improvements:` line.
5. Tick the plan boxes the work completed, and move anything you decided not to
   do into a later phase or the improvements list rather than dropping it.
6. Confirm both markdown files are tracked — no ignore rule covers them, but
   check, because a step documented only in an untracked file is a step
   documented nowhere.
7. Run the hooks. `uv run --frozen prek -a` only reaches files git already knows
   about, so a brand new step folder is skipped entirely and reports a clean
   pass over nothing. Either `git add -N` the new files first, or name them:
   `uv run --frozen prek run --files <path> [<path> ...]`.

## 8. Checklist: changing an existing step

1. Make the script change.
2. Re-read the step's method file top to bottom, not just the bullet you think is
   affected. A changed threshold often contradicts a second bullet elsewhere.
3. Correct every bullet the change made untrue, and add a bullet for anything new.
4. Tick any plan box the change completed, and add a new plan entry if the change
   created work or a new known limitation.
5. Check the method file still ends with the `Potential future improvements:`
   line pointing at that step's plan file.
6. Keep the code and the two markdown edits in one commit.
7. Run `uv run --frozen prek -a`.

## 9. Verify before reporting done

- The step folder is numbered, holds an `__init__.py`, and both markdown files
  are prefixed with the folder name.
- No sentence in the method file describes something the code does not do, and no
  "will" or "should" appears in it.
- Every method bullet names the script, function, asset file or figure that holds
  the detail, rather than restating the detail.
- The method file's last line is the `Potential future improvements:` line naming
  that step's implementation plan.
- Everything aspirational is in the plan file and only there.
- The step is in the `steps/` folder of the level its work actually belongs to,
  not at module level by default.
- Figures are written under a directory mirroring the step's module path, built
  from `REPORT_DIR`/`RESEARCH_DIR` and not from a `parents[N]` count, and no
  plotting logic moved into `src/landloss/`.
- `uv run --frozen prek -a` passes.
