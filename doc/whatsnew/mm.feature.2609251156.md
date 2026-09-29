**Properties off the liquefaction grid now carry damage state N/A, not state 1.**
Vul step 2, `s2_liq_land_damage`, used to write land the liquefaction model does
not cover as state 1, None. That state is surveyed flat land that showed no
damage, so it conflated "not damaged" with "cannot liquefy". Off-grid properties
now have a null `ld_state` and `state_name` "N/A", still at no cost. The null
passes through to `Liq_LD_state` in the land table, which the loss module reads
as not liquefied, so settlements are unchanged.
