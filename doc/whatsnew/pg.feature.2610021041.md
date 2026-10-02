**A drop-out draw for liquefaction land claims, built but switched off.** The liquefaction
land damage step (`s2_liq_land_damage`) can now draw, per property and realisation, whether
its owner claims, at a drop-out rate per land damage state held in `DROP_OUT_RATES` in its
`config.py`. A property that drops out keeps the hazard's state as `hazard_ld_state` but
writes a null `ld_state` and no cost; `liq_claimed` records the draw. The rates -- 95%, 75%,
40% and 15% for None to Major, 0% for Severe and Very severe -- are **placeholders**
awaiting tuning on feedback from Virginie Lacrosse and John Leeves (T-64, Q-16). The draw
stays **off** while the packaged Canterbury costs average over all damaged properties,
non-claimants at $0, which `COSTS_INCLUDE_NON_CLAIMANTS` in
`landloss.vul.liquefaction.costs` records (Q-17); it comes on when claimant-only costs
replace them (T-65). Until then every property on the grid claims at the diluted cost, so
settlements come out somewhat low (L-43).
