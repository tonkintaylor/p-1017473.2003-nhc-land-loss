**Remedial wall dimensions written into the construct phrase are read.**
"construct a 16m long anchored sprayed concrete retaining wall" now gives a
16 m wall of "anchored sprayed concrete". Before, the whole phrase landed in
`construction` and the length was lost.

`fetch_claim_reports.py --claims-list NAME --programmes 1011602 871310` fetches
from only the named projects on a list. In the first batch every claim on both
earthquake lists turned out to be storm damage (the June 2013 and
12 November 2016 Wellington storms), because a list is taken in date order;
this reaches the programmes outside Wellington.
