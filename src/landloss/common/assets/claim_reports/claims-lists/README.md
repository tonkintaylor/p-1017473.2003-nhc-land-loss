# Claims lists

Lists of claim subprojects to fetch reports for, built from T+T's Site Search
on 2026-09-30, with the other insurers' lists added on 2026-10-06. Each claim
carries its coordinates, so it is tagged with the study-area territorial authority it falls in (`ta_name`, `in_study_area`)
before any report is copied.

Built by `src/scripts/landloss/vul/static_data_gen/gen_claims_lists.py` from
Site Search exports. Site Search is reachable only through its claude.ai
connector, so each export is a saved `search_project_metadata` result. The
queries are below so the lists can be rebuilt or extended.

| List | Claims | In the study area |
|---|---|---|
| `kaikoura-2016.csv` | 1,903 | 1,152 |
| `seddon-2013.csv` | 252 | 191 |
| `iag-1502000.csv` | 2,874 | 514 |
| `suncorp-1501000.csv` | 1,696 | 397 |
| `loss-adjusters-1502100.csv` | 76 | 16 |
| `tower-1503000.csv` | 612 | 152 |
| `fmg-1504000.csv` | 589 | 16 |
| `mas-1505000.csv` | 371 | 102 |
| `ando-1506000.csv` | 281 | 21 |
| `chubb-1507000.csv` | 23 | 0 |
| `qbe-1508000.csv` | 2 | 2 |
| `allianz-1509000.csv` | 1 | 0 |

## The queries

Every query returned `project_number_full`, `project_name`,
`project_long_name`, `client`, `start_date`, `owning_office`,
`project_manager` and `points`, with `limit` well above the count returned.

- **`kaikoura-2016`**: client `Natural Hazards Commission Toka Tū Ake`, the
  box `[[-40.8, 172.3], [-43.2, 175.4]]` (Wellington to Hurunui), start date
  2016-11-14 to 2017-12-31.
- **`seddon-2013`**: the same client, the box `[[-40.8, 173.5], [-42.3, 175.4]]`
  (Wellington and Marlborough, east of Nelson), start date 2013-07-19 (the
  first large foreshock) to 2014-06-30.
- **`iag-1502000`** and **`suncorp-1501000`**: project numbers 1501000 to
  1502000.9999, any client, split by project. 1501000 is Suncorp's brands
  (Vero and AA Insurance). Rerun on 2026-10-06, it returned the same 2,874 and
  1,696 subprojects, so neither list was rebuilt.
- **The other insurers** (T-81, 2026-10-06): project numbers 1502100 to
  1509999.9999, any client, sorted by start date, split by project into one
  list per insurer. The three loss adjusters' codes -- 1502100 Sedgwick (45
  claims), 1502200 McLarens (21) and 1502300 Gallagher Bassett (10) -- share
  `loss-adjusters-1502100`, since their claims are underwritten by IAG or
  Tower; read the underwriter from `client`. Each count includes the parent's
  own `.0000` row, as the other lists do.
- **1600000**, the NHC "Non-BAU Insurance Claims" code, was queried the same
  way on 2026-10-06 and held only its parent row, opened 2026-10-01, so it
  has no list yet.

The parent projects 1503000 to 1508000 were all opened, or reopened, on
2026-10-01, and three of their names are swapped: 1505000 is named "Ando
Insurance Claims", 1506000 Chubb and 1507000 MAS. The claims under them say
otherwise, in both their `client` and their report file names: 1505000 is MAS
(Medical Insurance Society; 358 of 371 claims, 342 of 360 report names),
1506000 is Ando (275 of 281, 267 of 273) and 1507000 is Chubb (22 of 23, all
19). The lists are named for the claims, not the parent names.

## What the lists do and do not say

- **A start date is when T+T took the claim on, not when the event happened.**
  The earthquake programmes also carry storm claims from the same months: the
  June 2013 Wellington storm, and rain in Nelson. The report's own event
  sentence, read at extraction, settles which event a claim was.
  `name_event_hint` records the year some offices put in the subproject name
  (`EQC13`, `EQC2016`), as a clue only.
- **Coverage is Site Search's.** A claim Site Search has no record of, or no
  point for, is missing or outside the study area here. Every claim in these
  four lists has a point.
- **Where the programmes sit.** The EQC claims are subprojects of regional
  programmes: 0085650, 0085651 and 0085800 (Wellington, 2013); 0086101 to
  0086103 (Wellington, 2016); 1011600 to 1011603 and 1001700 to 1001710
  (Marlborough, Kaikōura and Hurunui, 2016 to 2017); 0871310, 0871311,
  0871320, 0871351 and 0871352 (Nelson and Marlborough). Project 1001154 is the
  Kaikōura response umbrella and holds no house claims, so `gen_claims_lists.py`
  leaves it out. The closed programmes are in the archive under their number
  without leading zeros: mostly `I:\<project>` (e.g. `I:\85650`), some under
  `T:\Archive\TT\<project>`, sometimes beside empty stub folders under the
  owning office.
