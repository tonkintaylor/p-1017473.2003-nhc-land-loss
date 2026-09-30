# Claim reports: status

**Status (2026-10-01):** The two steps and the claims lists are built and
tested. About 190 reports are extracted across the four lists, 98% of them
without a gap, over five templates: IAG 2021, Suncorp 2021, EQC Wellington 2016,
EQC Nelson 2016 and EQC 2013. The full fetch (`--all`) is next, then the
analysis, which does not exist yet.

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
   index is saved every ten subprojects, so a stopped run resumes.
2. **`extract_claim_reports.py`** reads the cached text only (never T:) and
   writes `reports.csv`, `walls.csv` and `remedial_walls.csv`, per project or,
   with `--claims-list`, to `extracted/<list>/` with each claim's coordinates
   joined on. Its main source is the Summary of Information table. `--show`
   prints what the parse sees in a report, to diagnose a template it misses.
   The claimant's name is dropped from the address, since the CSVs are
   committed.

Claude cannot run step one: T:, P: and I: are reachable only through the T+T
Network Browse MCP, which is not available, so a developer runs it in their
own terminal. Step two's outputs are in the repo and can be read.

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

1. **Fetch everything** with `--all`: IAG and Suncorp with `--study-area-only`,
   and both earthquake lists in full, since their claims outside Wellington are
   the point. About 2,800 reports; the text-only cache keeps it under 1 GB.
2. **Re-extract all four lists** and look at the gaps with `--show`. On the
   first 190 reports: two IAG reports had no summary table found (0218, 0257),
   one had three rows missing (0220), and 13 had no event sentence the parse
   recognises.
3. **Write the analysis**: the imminent-to-evacuated ratio, the overlap of
   evacuated and inundated land, failure size, wall counts and damaged
   lengths, and the loss module's assumptions (site ratings, design fees,
   replacement size and construction). Filter to `claim_accepted`, split by
   `event_cause`, use the `total_*` columns, and treat reports with
   `summary_columns` above 1 separately -- summing is right for one column
   per landslip (2013) and double counts for one per inspection.
4. **Join slope** at each claim's coordinates, for the ratio against slope.
5. Look for earthquake claims in the programmes outside Wellington
   (`--programmes`); if they are few, report that as a finding.

## Decisions

- **Filter before fetching, not after.** Lists with coordinates decide which
  subprojects to fetch (`--claims-list`). A whole report is about 4 MB, mostly
  photographs, which is also why only its text is cached (2026-10-01).
- **No PDF library** (2026-09-30). A PDF-only report is recorded, not read;
  a draft or working-copy docx is used where one exists, and flagged.
- **Claimants' names are not committed** (2026-10-01). The address keeps the
  site address only; insurer and EQC claim numbers stay.
- **Keep rain-triggered claims as well as earthquake ones.** Most Wellington
  claims are rain landslips. They still inform the imminent-to-evacuated ratio,
  the overlap of extents, failure size and wall damage. The event is recorded
  so the data can be filtered to earthquakes later.
- **The study area is Wellington City, Hutt City, Upper Hutt and Porirua.**
  The Seddon and Kaikōura claims are kept wherever they are.

## Findings so far

- **Declined claims are in the lists.** 85651.0043 is on the Seddon list and
  headed "(Earthquake) Damage", but its summary says the damage is not natural
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
- **The earthquake lists carry rain claims.** 86101.6708 and 871351.8037 are
  both on the Kaikoura list, and both landslips followed rain in October and
  November 2016. Filter on `event_cause`.
- **A replacement can change construction.** 871351.8037 replaces a timber
  pole wall with 190 mm block masonry. The loss module assumes a replacement
  keeps the old wall's construction.

## Open questions

- **The event behind each claim.** The earthquake lists are claims T+T took on
  in the months after each event, and the same programmes carry storm claims
  from those months (the June 2013 Wellington storm, Nelson rain). Only the
  report says which event a claim was.

- **Can a subproject hold two claims?** 1502000.0003 has
  `…C3781478_Report_Rev1.docx` under a final folder, and a later
  `…C3917925_Report - December 2021 claim.docx` with a different claim number.
  Step one keeps only the first. If one subproject can hold several claims,
  step one should fetch one report per claim.
- **Misfiled folders.** Two `1501000.*` (Suncorp) folders sit inside 1502000.
  Neither had a report, but the index should say which project a folder
  belongs to.
- **Whether the reports list undamaged walls.** In 0005 every wall listed was
  damaged. Perrie's reading is that the reports generally list only damaged
  walls, so the wall count may be a count of damaged walls.
