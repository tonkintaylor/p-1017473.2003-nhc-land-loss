**The land cover cap now values liquefied land over its damaged area, not the whole
section.** The liquefaction land damage step writes `damaged_area_m2` per claim: the
evacuated plus the inundated area, less 30% of the evacuated taken to lie under the
inundated (no more than the inundated area), capped at the insured area, so a property
both wholly inundated and evacuated is damaged once over (T-56). It reaches the loss module
as a new land table column, `Liq_LD_damaged_area`, which `landloss.loss.claims.damaged_area_m2`
now reads in place of the whole insured area of any liquefied polygon. The 30% is an
assumption about how the agreed overlap is measured, held as `EVACUATED_OVERLAP_SHARE` in
the step's `config.py` and to be verified (L-44). Over the pilot the land value the cap
compares against falls from $1,520M to $445M across 1,767 liquefied claims.
