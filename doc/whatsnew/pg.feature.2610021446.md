**Liquefied land can now be priced from the ground it lost.** A new step,
`s3_repair_rate_calibration`, fits a rate per m² of inundated land, a rate per m² of
evacuated land and a fixed cost per claim to the Canterbury mean cost per land damage state,
Minor to Very severe, estimating each mean from the 50th and 85th percentiles through a
lognormal (T-57). Over the pilot it fits $10.39 per m² inundated, $19.66 per m² evacuated
and $995 per claim, 2010/2011 dollars excluding GST, reproducing each state's mean to within
0.83 to 1.24 (L-45); the fixed cost is there because Minor loses almost no ground. The rates
are held in `REPAIR_RATES` in the liquefaction land damage step's `config.py`, which now
writes `area_cost_nzd` per claim beside the Canterbury lookup, with a `NO_SVA` flag raising
the inundated rate by a placeholder 1.5 for clearing without volunteers (Q-18). The rates are
**provisional**: fitted to costs diluted with non-claimants' $0s, they are not validated
and are to be refitted against claimant-only costs (T-65). The loss module still settles on
the lookup.
