# Claim reports: status

**Status (2026-10-06): done for now.** All twelve lists are fetched and
extracted: every insurer parent code from 1501000 to 1509000 and the EQC 2013
and 2016 programmes. 4,345 reports fetched (3,956 of them Word files), 3,954
extracted, about 96% without a gap. 2,193 accepted land claims are in scope:
inside the study area, or earthquake claims from anywhere (see "Second
analysis" below). One gap is left
open, logged in the register:

- **PDF-only reports are not read** (I-15). About 380 Kaikōura-list reports
  survive only as PDFs. They could roughly double the 508 earthquake claims,
  but need a PDF library, which was declined on 2026-09-30.

The other gap, project numbers the claims lists had not identified (I-16), is
closed by T-81: the lists now cover every parent code in "Job numbering"
below. The NHC code 1600000 has no claims under it yet, so it is the one to
recheck later.

The task comes from Maxim Millen's handover call on 2026-09-25 (**T-50**): pull the
figures out of T+T's past claim reports to inform the landslide and retaining
wall assumptions in the model.

## How it works

Two steps, kept apart so the files are only ever fetched once
(Maxim: "so that we don't need to rerun the extraction of files each time we
want to add more data").

0. **`gen_claims_lists.py`** turns Site Search exports into claims lists in
   `src/landloss/common/assets/claim_reports/claims-lists/`: one row per claim
   subproject, with its coordinates and the study-area authority it falls in.
   The queries are recorded in the README there. Fetching from a list is how
   the reports are chosen before anything is copied.
1. **`fetch_claim_reports.py`** reads T: through `tdrive_sync`, finding each
   project under its owning office or the archive (`T:\Archive\TT`, `I:\`)
   and combining the copies where it is in more than one. For each subproject
   it takes a `.docx` report from IssuedDocuments, then any `.docx` there, then
   one from WorkingMaterial, and records a PDF only as a last resort. It caches
   **only the report's text** (`word/document.xml`), about a twentieth of the
   report, and writes `<project>/report-index.csv`. `--claims-list`,
   `--study-area-only`, `--programmes`, `--limit`, `--all`, `--refresh` and
   `--dry-run` control it; `--slim-cache` shrinks a cache of whole reports. The
   index is saved every ten subprojects, so a stopped run resumes. A folder
   it may not open, or may not even check is a folder (1504000.0472), is
   recorded as unreadable rather than stopping the run (fixed 2026-10-06).
2. **`extract_claim_reports.py`** reads the cached text only (never T:) and
   writes `reports.csv`, `walls.csv` and `remedial_walls.csv`, per project or,
   with `--claims-list`, to `extracted/<list>/` with each claim's coordinates
   joined on. Its main source is the Summary of Information table. `--show`
   prints what the parse sees in a report, to diagnose a template it misses.
   The claimant's name is dropped from the address.
   Neither step's output is committed. Step one's index stays in the repo,
   where `.gitignore` excludes everything under `claim_reports/` except
   `claims-lists/`. Step two writes to `CLAIM_REPORTS_EXTRACTED_DIR` in
   `scripts/landloss/paths.py`, Maxim Millen's folder
   `U:\MAMI\land-loss\claim_reports\extracted` (2026-10-06), which the analysis
   and the retaining wall validation read from too, so whoever runs the
   extraction updates the one copy every script uses.

Claude cannot run step one: T:, P: and I: are reachable only through the T+T
Network Browse MCP, which is not available, so a developer runs it in their
own terminal. Claude can run step zero, through the Site Search connector, and
step two and the analysis, which read only the local cache. The cache is on
the machine that ran step one; step two's outputs are on U:, not in the repo.

## What is extracted

From the summary table:

- evacuated and inundated land, summed across the columns where a 2013 report
  gives one per landslip;
- land at imminent risk: additional evacuation, new inundation, re-inundation;
- the same for the main access way, in `access_*` columns, and the claim's
  totals across both in `total_*`;
- whether the claim was accepted, and which rows the table does not carry
  (`absent_rows`) as distinct from rows it could not read (`missing`);
- one row per retaining wall: whole length, retained height, and the damaged,
  imminent, insured and total face areas.

From the rest of the report:

- the header: job number, date, addressee, claim type, address and claim number;
- the inspection date, the event sentence and which Act applied;
- each wall's damaged and collapsed length, from the property damage bullets.
  A second reading, damaged face over retained height, sits alongside it;
- the construction issues tick boxes, as the costing tool's E, M and D ratings.
  These are what the loss module currently has to proxy (Q-10, T-40);
- the design and consent cost total, the landslip width and the debris volume;
- each wall the conceptual remedial works propose: length, height, pole SED
  and embedment.

Findings from report 0005 so far:

- The design and consent cost is $20,500 excluding GST. The loss module charges
  $5,100 per claim.
- The replacement wall proposed is 2.7 m high on 350 mm poles, replacing walls
  of 1.4 and 1.5 m. Replacements can be larger than the walls they replace, and
  can merge walls.

## Next

1. **Fetched everything** with `--all` (2026-10-01).
2. **Re-extracted all four lists** (2026-10-01); 80 reports (3.8%) still have
   a gap.
3. **Analysis written** (2026-10-01):
   `src/scripts/landloss/vul/research/analyse_claim_reports.py` writes
   `research/vul/claim_reports/claim_report_findings.md`, and the same tables
   in `claim_report_findings.xlsx` (one sheet each, with a contents sheet),
   all local only. See "First analysis" below.
4. **Join slope** at each claim's coordinates, for the ratio against slope.
5. **Earthquake claims in the programmes outside Wellington.** Done by the
   `--all` fetch of 2026-10-01, which took every programme on the Kaikōura
   and Seddon lists: 459 Kaikōura and 35 Seddon earthquake claims.
6. The open gap: read the PDF-only reports (I-15). The other, project numbers
   the claims lists had not identified (I-16), is closed by step 7.
7. **Fetched every parent code** (T-81, 2026-10-06): listed the job folders
   under each parent code in "Job numbering" below, then fetched and
   extracted them. Listed 2026-10-06: every subproject of 1502100 to
   1509000, 1,955 in all, 309 in the study area, in one list per insurer
   (`tower-1503000`, `fmg-1504000`, `mas-1505000`, `ando-1506000`,
   `chubb-1507000`, `qbe-1508000`, `allianz-1509000`, and
   `loss-adjusters-1502100` for the three adjusters' codes; queries and counts
   in the claims-lists README). IAG and Suncorp had
   nothing new in Site Search, and 1600000 has no subprojects yet.
   Fetched 2026-10-06: 1,871 reports (1,870 Word files), 22 unreadable, 56
   with no report. Extracted: 1,869 reports, 1,760 accepted land
   claims, 289 in the study area, 575 walls; 71 (3.8%) with a gap, 23 of
   them with no summary table found. Almost all rain (1,623 rain, 16
   earthquake, 230 no recognised cause), so earthquake claims stay the
   thinnest part of the sample. One report (1506000.0116) failed to cache
   because its cache path passes Windows' 260-character limit.
8. **Analysis rerun** over all twelve lists (2026-10-06), keeping only the
   study area plus earthquake claims; see "Second analysis" below.

## Job numbering

How the claim job numbers are set up, as passed to Perrie Gilbert on
2026-10-06. It is the basis for listing every job folder (T-81).

- **Insurer first, then one sub-code per claim; no event level.** Each insurer
  or claims handler has a parent code, and sub-codes under it are handed out
  in order as claims come in, one per property:

  | Parent | Insurer or handler |
  | --- | --- |
  | 1501000 | Suncorp |
  | 1502000 | IAG |
  | 1502100 | Sedgwick |
  | 1502200 | McLarens |
  | 1502300 | Gallagher Bassett |
  | 1503000 | Tower |
  | 1504000 | FMG |
  | 1505000 | MAS |
  | 1506000 | Ando |
  | 1507000 | Chubb |
  | 1508000 | QBE |
  | 1509000 | Allianz |
  | 1600000 | "Non-BAU Insurance Claims" for the Natural Hazards Commission |

  1505000 to 1507000 are as the claims under them show, in their `client`
  and their report file names. The parent projects' own names in Site Search,
  and the notes this table came from, have them as Ando, Chubb and MAS, which
  is swapped (claims-lists README).

  IAG runs from .0001 (July 2021) to about .2891 (October 2026).
- **The event is not in the number.** Storm, landslip and earthquake claims
  share one sequence. The event has to come from the start date and location,
  or from the report. Runs of claims help, such as the Marlborough Sounds
  claims in early August 2021 and the Oamaru and Cape Palliser runs in
  July and August 2026.
- **"EQC - address" became "NHC - address"** when EQC became the Natural
  Hazards Commission. It is the same kind of job.
- **The parent code is the channel, not always the underwriter.** A few IAG
  sub-codes list AA Insurance, Tower or Ando as the client.
- **The insurer's claim number is usually in the file name.** C3781306 in
  `T+T_2021-IAG-C3781306-Report` looks like IAG's claim number, which would
  link to insurer data better than the T+T sub-code. The 2026-10-06 fetch
  bears it out: almost every 1506000 report name carries a `C0` number in the
  same place, and the header's claim number is extracted as `claim_number`.
  Not yet checked that the two agree.
- **An address can return under a new code.** One IAG address appears in 2021
  and again in 2026 under a later sub-code, which is useful for repeat damage.

## Decisions

- **Filter before fetching, not after.** Lists with coordinates decide which
  subprojects to fetch (`--claims-list`). A whole report is about 4 MB, mostly
  photographs, which is also why only its text is cached (2026-10-01).
- **No PDF library** (2026-09-30). A PDF-only report is recorded, not read;
  a draft or working-copy docx is used where one exists, and flagged.
- **Nothing read from a report is committed** (2026-10-01). The claims lists
  may be; the report index, the extracted CSVs and the IAG 1502000 summaries
  may not, and nor may notes tying a finding to a named subproject. The address
  still drops the claimant's name, as a second guard.
- **Keep rain-triggered claims as well as earthquake ones.** Most Wellington
  claims are rain landslips. They still inform the imminent-to-evacuated ratio,
  the overlap of extents, failure size and wall damage. The event is recorded
  so the data can be filtered to earthquakes later.
- **The study area is Wellington City, Hutt City, Upper Hutt and Porirua.**
  Only earthquake claims are used from outside it; rain and unknown claims
  outside it are left out (Perrie Gilbert, 2026-10-06). The analysis applies
  this, on each claim's `in_study_area` and `event_cause`. The other insurers'
  lists were fetched without `--study-area-only`, so their out-of-area reports
  sit in the local cache unused; a later fetch from them should add the flag.

## Findings so far

- **Declined claims are in the lists.** One Seddon-list report is headed
  "(Earthquake) Damage", but its summary says the damage is not natural
  disaster damage: the cracking was historic settlement. Filter on
  `claim_accepted` before analysing extents.
- **The first batch from both earthquake lists is all storm damage**
  (2026-09-30). 18 Kaikōura-list reports (86101) are rain, most after the
  12 November 2016 Wellington storm two days before the earthquake; 11 of 12
  Seddon-list reports (85650) cite the June 2013 storm, and the twelfth is a
  declined earthquake claim. A list is taken in date order, so the storm
  backlog comes first. Earthquake claims are to be looked for in the
  programmes outside Wellington (`--programmes 1011602 1011603 1001700 1001710`
  for Kaikōura, `871310 871311` for Seddon).
- **The earthquake lists carry rain claims.** Two Kaikoura-list reports, one
  from Wellington and one from Nelson, describe landslips that followed rain in
  October and November 2016. Filter on `event_cause`.
- **A replacement can change construction.** One Nelson report replaces a timber
  pole wall with 190 mm block masonry. The loss module assumes a replacement
  keeps the old wall's construction.

## First analysis (2026-10-01)

1,989 accepted land claims from 2,085 Word reports: 496 earthquake (459
Kaikōura, 35 Seddon), 1,234 rain, 259 with no recognised cause. Land areas use
the 1,766 single-column reports. Descriptive only: the sample is shaped by who
claimed, which insurer used T+T, and which reports survive as Word files.

- **Imminent against evacuated land.** Imminent evacuation over evacuated area:
  0.14 pooled, median 0.31 per claim (rain 0.40, earthquake 0). 68% of claims
  have some imminent evacuation. Earthquake claims evacuate more (median 7.5 m2
  against 3 m2) and carry almost no imminent risk.
- **Evacuation and inundation together.** Evacuated only 34%, both 41%,
  inundated only 12%, neither 14%. Inundated over evacuated area: median 1.11
  (earthquake 0.50, rain 1.20). Inundated depth (NHI Act reports): median
  0.57 m.
- **Failure size.** Landslip width median 5 m (p90 13 m).
- **Walls.** 27% of claims list a wall. Timber 54%; concrete, block and crib
  36%, against the 30% concrete the loss module assumes. Retained height
  median 1.2 m (p90 2.4 m); whole length median 10 m; damaged share of the
  length median 0.52.
- **Replacements.** 33% are taller than the tallest existing wall (216 claims
  with both heights); 46% change construction (290 pairs), mostly timber to
  block or concrete and concrete to block. Supports the sizing rule added to
  the loss module, and argues against keeping the old construction.
- **Site ratings.** Construction access is mostly D (492 D, 282 E, 247 M);
  earthworks and constructability are spread across E and M, with about a
  quarter D. The older "hard" and "moderate" ratings are read as D and M.
- **Design and consent fees.** Median $14,000 excl GST (earthquake $10,000,
  rain $14,000; p10 $6,000, p90 $26,000) across all claims, wall or not,
  against the $5,100 the loss module charges per claim with a wall.

## Second analysis, study area plus earthquakes (2026-10-06)

All twelve lists, with the scope rule of 2026-10-06 (see "Decisions"): 2,193
accepted land claims, 508 earthquake from anywhere, and 1,380 rain and 305
unknown inside the study area. 1,556 rain and unknown claims from outside it
are left out. Land areas use the 1,935 single-column reports. The sample table
now breaks down by list, and so by insurer.

- **Imminent against evacuated land.** Pooled 0.15; median 0.33 per claim
  (rain 0.42, earthquake 0). 70% of claims have some imminent evacuation.
- **Evacuation and inundation together.** Evacuated only 33%, both 43%,
  inundated only 11%, neither 13%. Inundated over evacuated median 1.12
  (earthquake 0.55, rain 1.20).
- **Failure size.** Landslip width median 5 m, p90 13 m.
- **Walls.** 27% of claims list a wall, 25% of those more than one. Timber
  53%; concrete, block and crib 37%, against the 30% concrete the loss module
  assumes. Retained height median 1.2 m (p90 2.5 m); whole length median
  10 m; damaged share median 0.52.
- **Replacements.** 35% taller than the tallest existing wall (257 claims);
  48% change construction (338 pairs).
- **Site ratings.** Construction access mostly D (656 D, 324 E, 311 M);
  earthworks and constructability spread across E and M, about a quarter D.
- **Design and consent fees.** Median $14,000 excl GST (earthquake $10,000,
  rain $14,000; p10 $6,000, p90 $27,000), against the $5,100 the loss module
  charges per claim with a wall.

These are close to the first analysis, whose IAG and Suncorp claims were
already study area only; it differed by 88 rain and unknown claims from
outside the study area on the Kaikōura and Seddon lists, now left out. An
earlier run of this analysis the same day pooled every
region and moved several figures (timber 64%, landslip width median 7 m); those
came from the out-of-area rain claims and are superseded.

## Open questions

- **The event behind each claim.** The earthquake lists are claims T+T took on
  in the months after each event, and the same programmes carry storm claims
  from those months (the June 2013 Wellington storm, Nelson rain). Only the
  report says which event a claim was.

- **Can a subproject hold two claims?** One IAG subproject has a report under
  a final folder and a later report carrying a different claim number.
  Step one keeps only the first. If one subproject can hold several claims,
  step one should fetch one report per claim. The reverse also happens: one
  report's file name carries two claim numbers (2026-10-06).
- **Misfiled folders.** Two `1501000.*` (Suncorp) folders sit inside 1502000,
  and a `1505000.*` folder inside 1506000 (2026-10-06). None had a report,
  but the index should say which project a folder belongs to.
- **Whether the reports list undamaged walls.** In 0005 every wall listed was
  damaged. Perrie's reading is that the reports generally list only damaged
  walls, so the wall count may be a count of damaged walls.
