---
name: recording-project-context
description: Turn a meeting transcript, email or note into durable project context — tasks, limitations and future improvements in the project register workbook, refinements to the project objectives and scope, and standalone context notes on recurring topics. Use whenever the user supplies a transcript, meeting notes or correspondence and asks for it to be captured, recorded or turned into actions.
---

# Recording project context

This project accumulates its understanding in two places: a spreadsheet register
of things to do or watch, and a set of markdown context files under
`.agents/context`. This skill defines how a raw input — a transcript, an email, a
set of notes — is split between them.

The guiding rule is that nothing in the source should be paraphrased into
something stronger than it was. If a task had no clear owner, it has no owner. If
a limitation was raised as a possibility, record it as a possibility.

Do not commit the raw source. Meeting transcripts and forwarded emails are
verbatim, carry side conversation and personal remarks, and the repository is
shared; what the repository keeps is the register, the status files and the
context notes, each entry naming its source by meeting title and date.

## 1. Read the source and classify

Work through the source once and sort what it contains into five buckets:

- **Tasks** — something a person has to do. Includes decisions that are owed, data
  that has to be sourced, and analysis that has to be run.
- **Limitations** — a constraint, simplification or known weakness in the
  approach. These are the things that will need to be disclosed in the report.
- **Improvements** — things worth doing that are likely out of scope for the
  current engagement.
- **Questions** — something nobody on the team can answer yet. The distinction
  from a task is who can act: a task has someone who can go and do it, whereas a
  question is waiting on an answer that has to come from outside, usually from
  NHC. Do not file a question as a task with an owner who cannot answer it.
- **Refinements** — new clarity on what the project is trying to do, or on a scope
  item that was previously vague.
- **General context** — background on a topic that will be referred to repeatedly
  (e.g. how claims are settled, how the insured land definition works). This is
  not an action; it is knowledge.

A single sentence in the source can land in more than one bucket. A limitation
often implies a task to quantify it, and an improvement is often the thing that
would remove a limitation.

## 2. Update the register workbook

The register is **not** kept in the repository. It lives in the OneDrive-synced
project folder so the wider team can open it:

```text
$env:USERPROFILE\OneDrive - Tonkin + Taylor Group Ltd\Data + Analytics - Documents\Projects\1017473.2003-nhc-land-loss\1017473.2003-nhc-land-loss-project-register.xlsx
```

Always write the user portion of that path as `$env:USERPROFILE` (or
`Path.home()` in Python) rather than a literal username. The folder is shared, so
a path with one person's username in it is wrong for everyone else who opens it.

The workbook has three sheets, each with fixed columns:

| Sheet | Columns |
| --- | --- |
| `Tasks` | ID, Task, Owner, Phase, Source, Status, Updated |
| `Limitations` | ID, Limitation, Affects, Source, Status, Updated |
| `Improvements` | ID, Improvement, Rationale, Phase, Source, Status, Updated |
| `Questions` | ID, Question, Asked of, Answer, Source, Status, Updated |

A question carries the `Answer` column so the reply lands beside what was asked
rather than in a transcript nobody reopens. Fill it in when the answer arrives
and set the status to `Answered`.

### The register is append-only

The register grows over the whole project, from many transcripts and from
requests to add a single item. **It is never rebuilt.** The script appends rows
whose ID is new and does not touch anything already in the workbook, which is
what allows the user to work in the file directly in Excel between runs.

This splits ownership, and the split matters:

- `.agents/context/register.json` owns the **wording** of each entry. It is the
  version-controlled log of what each source produced, so changes are reviewable
  in a diff. Add new entries to the end of it; do not rewrite or delete existing
  ones.
- The **workbook owns Status**. The JSON supplies a status only when a row is
  first created and is ignored for that row afterwards, so a task ticked off in
  Excel stays ticked off through every later append.

Because of that split, never re-word an entry by editing the JSON and re-running:
the append will skip the existing ID and nothing will change. To correct the
wording of a row already in the workbook, say so and edit the cell.

### Statuses

Each sheet closes out differently. The script rejects anything outside its list,
and greys out a row once it reaches a closing status.

| Sheet | Statuses |
| --- | --- |
| `Tasks` | `Open`, `In progress`, `Done`, `Dropped` |
| `Limitations` | `Open`, `Mitigated`, `Accepted`, `Dropped` |
| `Improvements` | `Parked`, `Scheduled`, `Done`, `Dropped` |
| `Questions` | `Open`, `Asked`, `Answered`, `Dropped` |

`Accepted` means a limitation is a permanent caveat to disclose in the report
rather than something anyone intends to fix. Setting a status also stamps the
`Updated` column with today's date.

Do not close an entry off your own judgement. Mark something done when the user
says it is done, or when the session itself produced the evidence that it is.

### Rules for the entries themselves

- A task is **one sentence**, written as an instruction with a verb — "Confirm the
  seismic demand return period with NHC", not "Seismic demand".
- A limitation or improvement is **one to two sentences**, no more.
- Every question names who it is **Asked of**, and an answer is attributed to
  whoever actually gave it. An answer relayed by a colleague is not the same as
  one from the person with the authority, and the `Source` has to say which it
  was — a working answer recorded as an authoritative one is how a wrong
  assumption gets built on.
- Every task has an **Owner**. Use the person's name as it appears in the source.
  If the source genuinely does not say, write `Unassigned` rather than guessing —
  an owner invented here becomes an owner someone is chased about later.
- **Phase** is `1`, `2`, `3`, `4`, `Future` or `Unassigned`, matching the phases in
  `.agents/context/project-scope.md`.
- **Source** identifies where the entry came from, so it can be checked later: the
  transcript date, or the context filename. With several transcripts in the
  register this is the only way to tell which meeting produced a row, so it is not
  optional.
- IDs are stable: `T-01`, `L-01`, `I-01`, `Q-01`, and so on. Never reuse or renumber one —
  other documents may cite them. Omit the ID and the script allocates the next in
  sequence, which is safer than counting rows by hand: it continues from the
  workbook, so it also counts rows added directly in Excel. The script then writes
  the allocated ID back into the JSON, so the log and the workbook name the same
  entry the same way and the next append skips it rather than adding it again.
  Commit that rewrite of `register.json` along with the entry.

### Commands

Add any new entries from the JSON to the workbook:

```powershell
uv run --with openpyxl python .agents/skills/recording-project-context/scripts/build_register.py append .agents/context/register.json
```

Mark a single entry:

```powershell
uv run --with openpyxl python .agents/skills/recording-project-context/scripts/build_register.py status T-03 Done
```

Both default to the OneDrive workbook above, resolving the user from the
environment. Pass a trailing path to work on a different file. Run the script with
no arguments to print the resolved default and the valid statuses.

If the workbook is open in Excel the save will fail; ask the user to close it
rather than writing somewhere else.

## 3. Record refinements to objectives and scope

New clarity on the project's intent goes back into the existing context files
rather than into a new one, so there is a single place to read what the project
is for.

- In `.agents/context/project-objectives.md`, add bullets under the
  `## Refinements` heading.
- In `.agents/context/project-scope.md`, add a short `Refinements:` bullet list
  directly below the scope item it clarifies, so the refinement sits with the task
  it changes.

Keep the original text intact. A refinement annotates the agreed scope; it does
not quietly rewrite it. If a refinement genuinely contradicts the scope, say so in
the bullet and flag it to the user, because that is a variation rather than a
clarification.

## 4. Capture general context as its own file

When the source explains a topic that will come up again, write a new markdown
file in `.agents/context` named after the topic (`claims-settlement.md`,
`insured-land-definition.md`). Then:

- Give it a short heading stating what the topic is and where the understanding
  came from.
- Note anything the source left unresolved, so a later reader knows the file is
  partial rather than assuming it is complete.
- Add it to the list in `AGENTS.md` under "Project context", or it will not be
  read.

## 5. Verify before reporting done

- Every task has an owner, or an explicit `Unassigned`.
- No entry exceeds its sentence limit.
- Every new entry names its source.
- The append run reported the entries you expected as added, and everything else
  as already present.
- New context files are listed in `AGENTS.md`.
- `uv run --frozen prek -a` passes.
