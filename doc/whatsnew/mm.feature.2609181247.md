Added `src/scripts/landloss/vul/static_data_gen/get_nhi_act_claims_data.py`,
which converts the two NHC land claims workbooks (the cohort modelling extract
and the settled land claims export) supplied under SourceMaterial into CSV
assets under `src/scripts/landloss/vul/assets`. Their paths are exposed as
`scripts.landloss.paths.NHI_ACT_LAND_CLAIMS_COHORT_CSV` and
`NHI_ACT_SETTLED_LAND_CLAIMS_CSV`. Two research figures read them:
`fig_land_claims_cohort.py` plots indicative land repair cost against damaged
land area, coloured by the damaged land description, and
`fig_settled_land_claims.py` plots total settlement amount against total cost
to repair for the settled claims.
