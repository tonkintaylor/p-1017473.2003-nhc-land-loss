**A report is found even where only a draft or working copy survives.** Where
a subproject's `IssuedDocuments` has no report `.docx`, `fetch_claim_reports.py`
now takes any `.docx` there, draft or not, and then looks through
`WorkingMaterial` and its subfolders for a `.docx` named as a report, or kept
in a folder so named. A PDF is the last resort, recorded but not read.
Many 2013 and 2016 EQC finals were issued as PDF only.

"rpt" now counts as a report as well as "report", as in the 2013 `…_T&T rpt.docx`
files and the 2021 `…finalrpt.docx` working copies. The index gains `is_draft`
and `source_folder`, because a draft's figures can differ from what was issued.
Indexes written before these columns existed still read.
