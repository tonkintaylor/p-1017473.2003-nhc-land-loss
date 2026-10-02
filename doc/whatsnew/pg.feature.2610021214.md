**Liquefaction claims now carry the ground they lost.** The liquefaction land damage step
(`s2_liq_land_damage`) draws, per claim and realisation, an evacuated area in m² and an
inundated share of the insured land, uniformly within ranges set for each land damage state
(T-55), and writes them as `evacuated_area_m2` and `inundated_area_m2`, each capped at the
insured area. The ranges -- evacuated 0, 1, 1, 1-10, 10-40 and 40-100 m², inundated 0%,
0%, 25-70% and 30-100% for Major to Very severe -- are judgement held in
`EVACUATED_AREA_M2` and `INUNDATED_SHARE` in its `config.py` (L-39), to be tuned with the
repair rates (T-57). Nothing downstream reads them yet: the cost is still the Canterbury
lookup, and valuing the cap over the damaged area is T-56.
