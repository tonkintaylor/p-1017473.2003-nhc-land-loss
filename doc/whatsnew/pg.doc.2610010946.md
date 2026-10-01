**The register and status files now carry the driveway and claim-rate points
from the 1 October Wellington land model review.** The register gains T-60 to
T-64, L-41, L-42 and Q-15: one driveway per property as its main access way,
the 60 m driveway cap (the code stops only at 300 m), missing roads and parcels
in new subdivisions, non-residential buildings counted by default, and a table
of which liquefaction land damage states lead to a claim. The exposure/land and
vul/liquefaction/land status files record them.

Raw meeting transcripts are no longer kept in the repository.
`.agents/context/transcripts/` is removed, and the `recording-project-context`
skill now says not to commit the raw source.

**Nothing read from a claim report is committed any more.** `.gitignore` now
excludes everything under `claim_reports/` except the claims lists, and the IAG
1502000 report-path and landslide-summary CSVs are no longer tracked; both
stay on disk where the scripts write them. Notes and changelog
entries that tied a finding to a named subproject now describe it without
the identifier, and a real claimant's name in a docstring is replaced with a
placeholder.
