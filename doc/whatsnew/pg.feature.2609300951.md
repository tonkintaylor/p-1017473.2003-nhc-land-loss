**Claim reports are fetched in a step of their own.** `fetch_claim_reports.py`
finds each subproject's report under `IssuedDocuments` on T:, copies it into
the local tdrive_sync cache, and records what it fetched in
`src/landloss/common/assets/claim_reports/<project>/report-index.csv`. Reading
figures out of the reports will be a separate step run against the cache, so
adding a field never means fetching the files again.

A report with "final" in its path below `IssuedDocuments` beats a later one
without; otherwise the latest `.docx` with "report" in its name wins. A
subproject with no report is recorded as such rather than dropped. Runs are
incremental: `--limit 10` fetches the first ten, and running it again with a
higher limit fetches only the new ones. `--subprojects` restricts it to named
subprojects, ready for the Suncorp 1501000 list, and `--dry-run` lists what
would be fetched without copying anything.
