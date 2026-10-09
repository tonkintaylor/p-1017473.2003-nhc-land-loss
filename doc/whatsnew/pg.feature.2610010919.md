**Only a report's text is fetched and cached, not its photographs.** A `.docx`
is a zip, and step two reads one member of it, `word/document.xml`.
`fetch_claim_reports.py` now reads just that member from T: and caches it as
`<report>.docx.document.xml`, leaving the photographs that make up most of a
4 MB report on T:. That cuts the full run's cache from about 11 GB to under
1 GB and transfers far less over the network. A PDF is no longer cached,
since it is not read. The full report stays at the index's `report_path`.

`--slim-cache` converts a cache already filled with whole reports, offline:
each is replaced by its text and the index repointed.
