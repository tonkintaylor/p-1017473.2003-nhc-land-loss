**NHI Act reports are read.** Every report from the Natural Hazards Insurance
Act template was missing either its natural-hazard row or its whole summary
table. It says "Natural Hazard" where the EQC Act reports say "Natural
Disaster", "subject to imminent damage" where they say "at imminent risk", and
heads its table "Summary of damage information"; all are now read.

- `inundated_volume_m3` keeps the volume the NHI Act template gives beside
  the inundated area ("130 m2 / 210 m3").
- The template's unfilled example wall block ("Whole wall length: m") is no
  longer counted as a wall.
- `report_kind` marks a structural assessment ("… Structural Assessment"),
  which has no land table, apart from a land report.
- `--show` also prints the tables after the summary, where the NHI Act
  reports list their retaining walls.
