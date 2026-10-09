---
name: writing-weekly-updates
description: Generate the weekly progress update for NHC from the status.md files — fan out a reader per status file, compose the general updates, fill release_updates/weekly_update_template.typ and write update_week_of_<monday>.typ for the project lead to edit and finalise. Use whenever asked for the weekly update, a weekly summary, a progress update, or a client update.
---

# Writing the weekly update

The weekly progress update to NHC is **generated from the `status.md` files**,
not written from scratch. Those files are kept current as the work moves (see
`maintaining-status-files`), so the update is a rendering of them rather than a
fresh account of the week. Anything that is not in a status file does not belong
in the update; if something is missing, fix the status file first and regenerate.

The output is a Typst file the project lead edits and finalises. Never present it
as final, and never compile-and-send it.

## 1. Where things live

```text
release_updates/
    weekly_update_template.typ        # the template, with {{handlebars}}
    fill_update.py                    # substitutes a content JSON into it
    update_week_of_2026-09-14.typ     # one per week, generated, then hand-edited
```

The file is named for **the Monday of the current week**, whatever day it is
generated on: `update_week_of_<YYYY-MM-DD>.typ`. Compute it rather than guessing:

```powershell
uv run --frozen python -c "import datetime as dt; t=dt.date.today(); print((t-dt.timedelta(days=t.weekday())).isoformat())"
```

If that file already exists, **do not overwrite it** — it may already carry the
lead's edits. Report that it exists and ask.

## 2. The template

`weekly_update_template.typ` is A4 with narrow margins and five sections:

| # | Section | Table columns |
| --- | --- | --- |
| 1 | General updates | none — a numbered list |
| 2 | Hazard | Liquefaction, Landslide, Shaking |
| 3 | Exposure | Land, Retaining walls, Culverts |
| 4 | Vulnerability | Liquefaction, Landslide, Shaking |
| 5 | Loss | a label column and one content column |

Each table has a **`Plan and progress`** row and a `What's next` row.

`Plan and progress` renders that submodule's `Approach` bullets **with their
marks**: ✓ done, a filled half-circle and italics for partly done, ▸ for next,
and a grey dot for planned. A legend sits beside the date. This is the point of
the section — the plan is stable week to week, so the marks moving *are* the
progress, and the diff between two updates is exactly what changed.

**Never decide a mark yourself.** Take it from the status file's `Approach`
bullet. If a bullet has no mark, render it as planned and say so; do not infer
"done" from `Where it is now`.

`What's next` stays a numbered list: marks carry no order, and `Next` holds
decisions that are not plan items, like choosing the river layer.
In section 4 the assets are grouped **inside** each hazard cell — `*Land*` on
its own line, then its list, then a blank line before the next asset.

The handlebars are `{{date}}`, `{{general_updates}}`, and
`{{<module>_<column>_status}}` / `{{<module>_<column>_next}}` for every cell.
List them from the template rather than from memory:

```powershell
uv run --frozen python -c "import re,pathlib; print(sorted(set(re.findall(r'\{\{(\w+)\}\}', pathlib.Path('release_updates/weekly_update_template.typ').read_text(encoding='utf-8')))))"
```

## 3. Be very brief

This is the instruction that matters most, because the status files are much
longer than the update, and the first draft of every run will be too long.

**The budget is about 8 words — 55 characters — per item, and at most three
items per cell.** A three-column cell on narrow-margin A4 is only about 35
characters wide, so "one line" is not achievable: an item is a *phrase*, not a
sentence, and it wraps onto a second line at most. `General updates` spans the
full width, so it takes a short sentence, but still only three items.

- A cell says what changed and what is next, never why. The reasoning stays in
  the status file.
- No item carries a second clause, a semicolon joining two statements, or a
  trailing "…, which closes T-15" justification. Split it or cut it.
- **Never cite a register ID.** `T-15`, `L-08`, `I-08` mean nothing to a reader
  who cannot open the register, and most readers of this document cannot. Say
  the thing instead: not "closing T-25" but "revalue on measured area"; not
  "(T-01, T-06)" but "confirmation with NHC outstanding". The same goes for
  internal dataset and column names — `claim_id` is not client-facing.
- Cut script names, file paths and academic citations. A named dataset the
  client would recognise, like the Foster Vs30 model, is worth keeping.
- **Every plan item is a task**, phrased as an instruction with a leading verb:
  "Get land damage probabilities for 2500y using TS1170.5", not "Land damage
  probabilities, 2500-yr". A noun phrase reads as a topic; a task reads as work.
- **Define an acronym once, then use it.** "Buffer rivers to obtain lateral
  spreading (LS) zones", then "Modify LD probabilities inside LS zones". Define
  it at its first appearance in reading order — down a column, then across.
- Where the status file says the work has not begun, one item: "Not started."
- The finished update fits on **one page**. If it does not, the items are too
  long; shorten them rather than changing the template.

## 4. Generating one

Read `workflow-authoring` and run a workflow; the fan-out is a reader per status
file, and the files are independent, so `pipeline()` fits.

1. **Discover** — an agent globs `src/scripts/landloss/**/status.md` at run time
   rather than working from a list baked into the script. Files appear between
   runs, and somebody may be writing one while the update is generated.
2. **Read** — one agent per status file, returning structured
   `{module, column, status[], next[]}` with the brevity rules in section 3
   already applied. Have it return the file's `Updated` date too, so a stale
   file is visible.
3. **Compose** — one agent over all the summaries, writing `general_updates` and
   nothing else. It needs every summary at once, so this is a genuine barrier.
4. **Fill** — write a content JSON mapping every handlebar to its list of
   items, then run the committed filler. Do not write a fresh substitution
   script and do not retype the template:

   ```powershell
   uv run --frozen python release_updates/fill_update.py <content.json> release_updates/update_week_of_<monday>.typ
   ```

   `fill_update.py` takes each handlebar's indentation from the template line it
   sits on, and hard-fails on an unknown key, an unused key or a handlebar left
   in the output. A content entry is a plain string (a numbered-list item),
   `[mark, text]` where mark is `x`/`~`/`>`/`" "` (a marked plan item), or
   `[label, [entries]]` (a bold group — the asset groups in vul, and the
   prototype / beyond-prototype split). Re-check for new status files at this point —
   one can land after the readers have run.
5. **Verify** — compile it, and run two checks in parallel: one agent tracing
   every item back to a sentence in a status file, and one on brevity and
   structure. Both are worth having; on the first run they caught three
   overstatements and a systematic length miss between them.

Cells with no status file get `+ Not reported this week.`, and the user is told
which ones. Two phrasings to avoid:

- **"No status file yet."** — the client has no idea what a status file is. It
  describes this repository's layout, not the project.
- **"Not started."** — often false. `hazard/liquefaction` and
  `vul/liquefaction/land` both carry real work that has no status file yet, so
  writing "not started" against them would be wrong in front of NHC.

"Not reported this week." is true either way and reads as a prompt to fill the
gap in.

### The one source outside the status files

`General updates` may also draw on `.agents/context/register.json`, because
cross-cutting facts — a data request outstanding, a decision owed — live there
and in no status file. Nothing else may.

Take the register's wording seriously when you do. A task at `Status: Open` is
**proposed**, not agreed: the first run wrote "study area agreed as Wellington
City, Lower Hutt, Upper Hutt and Porirua" when T-01 and T-06 were both still
open, which would have told the client something was settled when it was not.
Likewise never count what is open ("two decisions remain") — every register task
is open, so a count understates it.

## 5. Compile before reporting done

```powershell
typst compile release_updates/update_week_of_<monday>.typ
```

The template compiles only once every handlebar is gone, so a clean compile is
also the check that none were missed. `fill_update.py` refuses to write a file
with a handlebar left in it, so the two checks are independent.

Render it and look at it — layout bugs do not fail the compile:

```powershell
typst compile --format png --ppi 110 release_updates/update_week_of_<monday>.typ page{n}.png
```

More than one page means the items are too long.

**Leave the compiled PDF in `release_updates/`.** The project lead reads the
rendered document, not the Typst source, so the PDF is part of what you hand
over — do not tidy it away once the layout is checked. It stays gitignored
(`release_updates/*.pdf`) because the `.typ` is the tracked source, but
gitignored is not a reason to delete it from disk. Clean up only the
intermediate PNGs.

## 6. Verify before reporting done

- The filename carries this week's **Monday**, not today.
- No `{{` remains in the output, and `typst compile` exits 0.
- Every cell has at least one item; a module with no status file says "No
  status file yet.", and one whose status file says it has not begun says "Not
  started."
- No item runs past about 55 characters, no item carries a second clause, and
  no cell has more than three items.
- The document is one page.
- Nothing in the update is absent from a `status.md`. This is the one that
  matters — an invented item goes to the client.
- Any status file whose `Updated` date is stale is reported to the user, not
  quietly rendered as though current.
- The compiled PDF is sitting in `release_updates/` next to the `.typ`.
- The user is told the file is a draft to edit, and where it is.
