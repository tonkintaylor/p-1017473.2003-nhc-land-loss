**A first analysis of the claim reports.** `src/scripts/landloss/vul/research/analyse_claim_reports.py`
reads the extracted claim report CSVs and describes, for accepted land claims split by
earthquake and rain: land at imminent risk against land evacuated, how often evacuation and
inundation occur together, landslip size, wall constructions, heights and damaged lengths,
how replacements compare with the walls they replace, the site ratings, and the design and
consent fees, set against the loss module's placeholders. Its output stays local, under
`research/vul/claim_reports/`, with the data it comes from.
