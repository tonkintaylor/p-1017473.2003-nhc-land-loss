# Re-evaluating tasks, module by module

How the project lead's task review is run, so someone other than the lead (or an
agent) can carry it on. Written from the culverts and bridges review with Maxim
Millen on 2026-10-08, the first module done this way.

## What is being reviewed

Every outstanding piece of work for one module, gathered from two places:

1. The submodule `status.md` files under `src/scripts/landloss/`, mainly their
   `## Next`, `## Validation` and `## Open decisions` sections, and the Loss
   contract items still marked `[~]` or `[ ]`. A module such as culverts and
   bridges spans several submodules (`exposure/culverts_bridges`,
   `vul/shaking/culverts_bridges`, `vul/landslide/culverts_bridges`) and the
   items they owe `loss`, so read all of them.
2. The project register workbook in the OneDrive project folder:

   ```text
   $env:USERPROFILE\OneDrive - Tonkin + Taylor Group Ltd\Data + Analytics - Documents\Projects\1017473.2003-nhc-land-loss\1017473.2003-nhc-land-loss-project-register.xlsx
   ```

   Read the live workbook, not `.agents/context/register.json`. The workbook is
   updated whenever a transcript is read in and rows are also added in Excel, so
   the JSON lags it. Search all four sheets (Tasks, Limitations, Improvements,
   Questions) for the module's terms, and skip rows already `Done`, `Dropped`
   or `Answered`.

Merge the two lists so an item that appears in both is presented once, under its
register ID.

## Categories

Each item is put in one of these, in order of priority:

| Category | Meaning |
| --- | --- |
| Urgent | Blocks development now. Not used for delivery deadlines: the run for the 9 October placeholder numbers was not urgent in this sense. |
| By Wed | A dated variant of urgent: has to be done for development by the coming Wednesday. |
| Pre-release | Needed before the model is released. |
| Final model | Needed in the final model. |
| Future | Beyond this engagement. |

An item can also be **dropped**, or **accepted** if it is a limitation to
disclose rather than work to do.

## Where each outcome is recorded

| Outcome | Where it goes |
| --- | --- |
| Urgent or By Wed | A row in `1017473.2003-nhc-land-loss-urgent-tasks.xlsx`, beside the register in the same folder, with the register ID if it has one, the module, owner, priority and due date. **Not** added to the main register. |
| Final model or Future | The main register. An item already there keeps its ID; reword it if the lead adds detail. A new one is appended through `register.json` and the append script. |
| Duplicate | Status `Dropped`, with the task text prefixed `Dropped - duplicate of T-nn.`; the surviving task's wording takes on anything the duplicate added. |
| Dropped item from a status file | Delete it from the status file. |
| Accepted limitation | A Limitations row with status `Accepted`. |
| A note the lead gives | Attribute it to the lead in `Source`, and file it on the sheet the lead names (a limitation is not a task). |

Follow the `recording-project-context` skill for every register write: append
new entries through `register.json` and `build_register.py`, edit the cell
directly to reword an existing row, and set statuses with the `status` command.
An un-numbered row typed into the workbook is given its ID in place rather than
appended again, so it is not duplicated. If the workbook is open in Excel the
save fails; ask for it to be closed rather than writing elsewhere.

Never invent an owner. Leave it `Unassigned` and ask.

## How the review is presented

1. Work one module at a time, in **groups of four items**.
2. Label each item with a **capital letter** (A, B, C, D), and put **where it came
   from in brackets straight after the title**: a register ID such as `(T-36)`
   or `(Q-02)`, or the status file, such as `(exposure-cb-status)` or
   `(loss-status)`.
3. Give each item about **two sentences** in plain language: what it is and why it
   matters. If the lead cannot tell what an item is asking, it is badly
   described; explain it in plain terms and wait rather than act on it.
4. Follow the chat numbering in `AGENTS.md` for everything around the items, and
   ask any question inside the item it belongs to.
5. After the lead classifies a group, record it, report in a few lines what was
   written where, and send the next group.
6. When a module is finished, ask which module comes next.

## Progress

| Module | State |
| --- | --- |
| Culverts and bridges | Done 2026-10-08. One item, sampling a culvert or bridge per realisation against an expected value per property, was waiting on the lead's decision to drop it or keep it as an open decision. |
| Shaking (`hazard/shaking`) | Done 2026-10-09. The sigma and correlated-field work was dropped as not applicable, T-16 dropped, the PGA-per-site-class validation is T-143 (final model), and the coarse demand grid is L-69. `vul/shaking/rw` is left to the retaining walls review. |
| Retaining walls, land, liquefaction, landslide, ground, loss | Not started. |

Update this table as each module is finished.
