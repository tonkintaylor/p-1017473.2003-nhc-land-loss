**2013 reports covering several landslips are read in full.** A 2013 summary
table has one column per landslip, and the claim's areas are now their sum;
before, only the first column was read. The same applies to wall face areas.
A 2013 wall block has no height row, so the height comes from its heading
("up to 800 mm retained height"). Damage given as "a 2.0 m wide section of
Retaining wall 1", or as a "Failure", now counts towards the damaged length.

Remedial works written as "constructing three cantilevered timber pole
retaining walls", with a labelled block per wall, give one row per wall with
its label. Heights in millimetres are read.

`reports.csv` gains `n_landslips` and `landslip_widths_m`, and
`estimate_includes_construction`: the 2013 per-wall estimates price the wall
itself and are now summed, where the later reports price design and consent
only and leave construction to the estimator.
