**A fetch can run to completion, and pick up where it stopped.**
`fetch_claim_reports.py --all` fetches every report there is. The index is
saved every ten subprojects and again however a run ends -- finished,
interrupted with Ctrl+C, or failed -- so a rerun skips everything already
recorded and carries on from there. Before, the index was written only at the
end of each project, so an interrupted run lost that project's progress.
