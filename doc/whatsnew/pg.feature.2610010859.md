**The Suncorp reports' variants are read.** Checked against the summary rows of
four Suncorp reports:

- A claim heading without brackets ("Claim for Natural Disaster Landslip
  Damage"), a claim number alone on the line after the address, and "Insurer
  Claim Ref:".
- "N/A" in a land-area row reads as none of that land, not blank.
- The main access way's own damaged and imminent blocks go to new `access_*`
  columns. Before, "Evacuation: Included in areas above" in that block
  overwrote the claim's own imminent evacuation with a blank.

`missing` now names only rows that are in the table but could not be read. A
row the table does not carry goes in the new `absent_rows` column: a
Storm/Flood claim has no Evacuated row, and the 2013 template has no
Re-inundation row. `summary_columns` counts the value columns, one per
landslip in a 2013 report and one per inspection in a report revised after
reinspection, where summing them can double count.
