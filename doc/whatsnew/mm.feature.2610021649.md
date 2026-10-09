**The ground map no longer reads SLIDE's mixed fill classes as fill throughout.**
"Mixed fill/rock", "Mixed fill/colluvium", "Mixed fill/colluvium/rock", "Mixed
fill/talus" and "Old alluvium (mixed fill)" now take their natural material (rock,
colluvium or alluvium, colluvium ahead of rock) and record fill as the modification, with
the SLIDE materials layer a modification source below the SLIDE genesis and the WCC
earthworks areas. Every fill material now reads strength row S52, the set GNS supplied for
modelling the Priscilla and Orchy Crescent fills (c′ 2 kPa, φ′ 42°, 22 kN/m³), named in
`landloss.hazard.landslide.ground_map.STRENGTH_GRADE_PICKS`, instead of S48. Both were
accepted by the lead on 2 October 2026; step 4 has to be rerun to apply them.
