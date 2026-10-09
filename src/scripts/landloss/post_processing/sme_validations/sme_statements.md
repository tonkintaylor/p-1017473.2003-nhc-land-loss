# SME validation statements (T-67)

What engineering experience of Wellington suggests, from an SME's notes and the
model sense check of 2026-10-05, set against what the model gives. Each test
has a script, `fig_sme_<n>_*.py`, that draws its figure into
`report/post_processing/sme_validations/fig/` and prints the numbers; settings
are in `config.py`.

## Tests

| # | Statement | Verdict |
|---|---|---|
| 1 | A third to a half of hill properties have a retaining wall of some kind. | Partly correct |
| 2 | Many walls are built to about 1 to 1.5 m, the height owners believe needs no consent. | Partly correct |
| 3 | About 80% of walls in the old suburbs (Kelburn, Karori, Kingston, Khandallah) date from about 1900 to the 1960s; Whitby's are mostly under 30 years old; Tītahi Bay is a 1950s to 1970s subdivision. | Partly correct |
| 4 | Sections are small, so a wall somewhere on a property quite likely supports insured land. | Correct |
| 5 | Most land claims come from cuts at the back of a house rather than fills at the front. | Incorrect |
| 6 | Most rock-cut failures are small: slumps or rockfall onto the land between house and slope. | Incorrect |
| 7 | Walls on flat land are few, and those there are low. | Partly correct |

Tests 1, 2 and 4 to 7 read the Wellington pilot box (world 0, realisation 0),
which is mostly flat central and eastern suburbs; re-run them on the full build
(T-68) by setting `EXTENT` in `config.py`. Test 3 reads the full study area.

## Results

1. **55% of hill properties have a wall** (1,443 properties), above the third to
   a half expected; suburbs range from 46% to 62%.
2. **The commonest height is 1 to 1.25 m, but most walls are taller.** 23% are
   1 to 1.5 m and 58% over 1.5 m; median 1.74 m against 1.2 m in the claim
   reports.
3. **Old suburbs are older, but not 80%** (table below).
4. **98% of walled properties have a wall meeting the insured land** (97% of
   walls).
5. **Failures sit as often in front of the house as behind it:** 43% behind,
   43% in front, 14% level (5,187 failure and claim pairs). Of failures with a
   wall, cut walls outnumber fill walls 1,981 to 849, so the walled failures do
   lean to cuts.
6. **Failures are about four times too large:** median 29 m² evacuated per
   damaged claim, against 7.5 m² for earthquake claims and 3 m² for rain claims
   in the claim reports.
7. **Flat properties have fewer and lower walls than hill ones, but not few:**
   20% walled against 55%, median 1.41 m against 1.93 m. The wall population's
   own NLM flatland flag puts none of its walls on flatland, so the walls on
   these properties stand on their sloping parts.

### Test 3: property age by suburb

Share of claim properties in each age bin, from
`report/exposure/rw/rwt-age/tab/rwt-age-by-suburb.csv`. The dwelling's age
stands in for its walls'.

| Suburb | Properties | Pre-1970 | 1970 to 1991 | 1992 to 2004 | 2005 on |
|---|---:|---:|---:|---:|---:|
| Kingston | 416 | 82% | 12% | 2% | 5% |
| Kelburn | 1,126 | 76% | 8% | 8% | 8% |
| Karori | 4,956 | 62% | 21% | 8% | 10% |
| Khandallah | 2,940 | 52% | 22% | 13% | 13% |
| Tītahi Bay | 2,747 | 54% | 25% | 5% | 16% |
| Whitby | 4,336 | 0% | 49% | 14% | 38% |

Kingston and Kelburn match; Karori and Khandallah are older than the rest of
the city but short of 80%. Whitby has no old stock, but half is 1970 to 1991,
older than under 30 years. Tītahi Bay fits, at 79% before 1992. Walls added
after the house are counted at the house's age.

## Other statements

Testable, but not taken forward for now:

- The thin soil mantle over a rock cut is usually left unretained.
- Over half of greywacke hill properties have a rock cut behind the house.
- Walls are more common on stepped platforms on shallower slopes than on steep
  greywacke.
- The big concrete and brick walls are in soil country (Karori, Thorndon,
  Mount Cook, Mount Victoria, Whitby, Porirua).
- New subdivisions commonly have walls.
- Development pushed up the hills onto harder sites as the easy land ran out.
- Under very strong shaking, a large share of old, brittle walls will fail.
- Fill and soil failures are rarer but can run out a long way as debris flows.
- Driveway-only failures are 10 to 20% of claims.
- The 1855 earthquake left large unrecorded rock failures along Evans Bay and
  the Pukerua Bay to Paekākāriki escarpment.
- About 10 to 20% of claimed hill properties involve a wall.
- Walls in Whitby, designed for rock but sitting in unmapped alluvium, fail even
  when new.
- Rock near the active faults is crushed and fails more readily.
