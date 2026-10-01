**Claims are chosen from Site Search before any report is copied.**
`gen_claims_lists.py` turns Site Search exports into claims lists, one row per
claim subproject with its coordinates. Each claim is tagged with the study-area
territorial authority it falls in, using the study area boundaries rather than
a bounding box. Four lists are in
`src/landloss/common/assets/claim_reports/claims-lists/`: Kaikōura 2016 (1,903
claims, 1,152 in the study area), Seddon 2013 (252 and 191), IAG 1502000 (2,874
and 514) and Suncorp 1501000 (1,696 and 397). A README records the queries.

`fetch_claim_reports.py --claims-list NAME [--study-area-only]` fetches only
the subprojects on a list, across every project it spans. It now finds a
project under its owning office or under `T:\Archive\TT` without its leading
zeros, which is where the 2013 and 2016 EQC programmes are filed, and finds a
subproject filed inside another subproject's folder.
