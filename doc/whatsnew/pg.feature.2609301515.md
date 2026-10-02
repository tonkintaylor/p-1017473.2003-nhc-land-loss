**A whole claims list is extracted in one command, with its coordinates.**
`extract_claim_reports.py --claims-list NAME [--study-area-only]` reads every
fetched report on a list, across all the projects it spans. It writes
`reports.csv`, `walls.csv` and `remedial_walls.csv` to
`src/landloss/common/assets/claim_reports/extracted/<list>/`. Each report row
carries its claim's coordinates, study-area authority, the date T+T took it on
and any event hint in its name, all taken from the list.
