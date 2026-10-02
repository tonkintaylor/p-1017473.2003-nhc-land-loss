**Projects split between an office and the archive are found.** The
archive is on `I:\` (`I:\85650`), with some projects under `T:\Archive\TT`.
A project can also be in two places at once, such as empty stub folders under
`T:\Nelson\Projects\871310` and the real files in the archive. So
`fetch_claim_reports.py` now searches every root and combines each
subproject's copies, taking the report from whichever copy has one and
preferring a copy with a `.docx`. Previously it stopped at the first folder it
found, and reported every subproject of 871310 as having no report.
