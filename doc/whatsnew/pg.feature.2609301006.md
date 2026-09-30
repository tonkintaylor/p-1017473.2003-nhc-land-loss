**Claim reports are read into three CSVs.** `extract_claim_reports.py` runs
against the reports `fetch_claim_reports.py` cached, never T:, and writes
`reports.csv`, `walls.csv` and `remedial_walls.csv` beside the index.

The Summary of Information table is the source: evacuated and inundated land,
the land at imminent risk (additional evacuation, new inundation and
re-inundation), the main access way, and each retaining wall's length, retained
height and damaged, imminently damaged, insured and total face areas. Around it
the script also reads:

- the header: job number, date, addressee, claim type, address and claim number;
- the inspection date, the event the claim relates to, and which Act applied;
- the damaged and collapsed length of each wall, from the property damage
  bullets;
- the construction issues tick boxes, as the costing tool's E, M and D ratings
  (Q-10, T-40);
- the design and consent cost, the landslip width, the debris volume, and each
  wall the remedial works propose.

"Nil" reads as zero and "N/A" as blank, and a `missing` column names any
summary field that could not be found, so template drift shows up as gaps.
Checked field by field against one 2021 IAG report.

The step-one index now records cached paths relative to the repo, so it is
usable on another machine once committed.
