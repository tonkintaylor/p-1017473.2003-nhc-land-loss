**The 2016 EQC report template is read as well as the 2021 one.** The summary
table's older wording is accepted: "Area of Land damaged", "RTW 2 – …" wall
headings, "At imminent risk" and "Insured" face areas, "EQC Ref:" claim
numbers, and "Potential Remedial Works". A retained height given as a range
("0.5 m to 1.5 m") is recorded at its tallest, with the range kept in
`retained_height_text`. Checked against a 2016 Kaikōura-list report.

Two new columns in `reports.csv`:

- `event_cause`: earthquake, rain or blank, read from the event sentence.
  One Kaikōura-list report describes a landslip that followed rain in October
  2016, which is why the lists alone cannot say which claims were earthquake
  damage.
- `notes`: the "Note:" lines under the summary table, for example that a wall is
  shared with a neighbour and its damage split between two claims.

The event sentence is now found a paragraph at a time. Searched across the
joined text, a header with no full stops let a job number be read as the year.

`fetch_claim_reports.py` falls back to a report PDF where a subproject has no
report `.docx`, ignoring sketch and photograph attachments. Many 2013 and 2016
finals were issued as PDF only. The extraction lists these but does not read
them yet.
