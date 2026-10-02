# Choice of retaining wall age bins

Exposure step 8 (`src/scripts/landloss/exposure/rw/steps/s8_infer_rwt_age/`)
puts every claim property's retaining walls in one of four construction
periods, and the report tabulates the share of each suburb's properties in each.
The dwelling's age stands in for the age of the retaining walls on the property,
and a wall's age is read as a guide to how it was designed, and so to how likely
it is to be in poor condition (`landloss.exposure.rw.wall_probability`). This
file records where the periods break and why. The bins are coded in
`landloss.exposure.rw.age` (`AGE_BINS`, `BIN_START_YEARS`).

The breaks follow changes in how residential retaining walls were designed and
regulated in New Zealand, not round decades.

## The bins

| Bin | Built | Opened by | Typical residential walls |
| --- | --- | --- | --- |
| `pre_1970` | Before 1970 | — | Mass concrete, brick and stone gravity walls, and untreated timber, sized by rule of thumb with no allowance for earthquake earth pressure |
| `1970_1991` | 1970 to June 1992 | Retaining wall design methods published, including for earthquake [mwd_1973] [wood_1973]; loadings to NZS 4203:1976 [standards_nz_1976] | Treated timber pole and reinforced concrete block cantilevers. The methods existed, but walls on house lots were seldom engineered and needed at most a council bylaw permit |
| `1992_2004` | July 1992 to 2004 | The Building Act 1991 and the Building Code [nz_parliament_1991]; loadings to NZS 4203:1992 [standards_nz_1992] | A wall retaining more than 1.5 m of ground, or carrying a surcharge, needs a building consent and is engineer designed |
| `2005_on` | 2005 onward | Earthquake actions to NZS 1170.5:2004 [standards_nz_2004]; the Building Act 2004 [nz_parliament_2004]; after the Canterbury earthquakes, Module 6 [nzgs_mbie_2017] | Earthquake demand set by the hazard factor, site subsoil class and return period, with published guidance for earthquake design of retaining walls |

## Why the breaks fall where they do

### 1992: the Building Act

This is the strongest break. The Building Act 1991 brought the Building Code
into force on 1 July 1992, and with it clause B1 Structure, which applies to a
retaining wall as to any other structure [nz_parliament_1991]. Since then a wall
retaining more than 1.5 m depth of ground, or supporting a surcharge such as a
driveway, a building or a slope above it, has needed a building consent, and in
practice an engineer's design and producer statements. The exemption for lower
walls carried into the Building Act 2004 as exemption 20 of Schedule 1
[nz_parliament_2004]. The wall model already splits here
(`BUILDING_ACT_DECADE`).

### 1970: the start of engineered walls

This break marks a cluster of changes in the early 1970s rather than one rule.
The Ministry of Works and Development published its retaining wall design notes
in 1973 [mwd_1973]. Wood's treatment of earthquake-induced soil pressures on
walls appeared the same year [wood_1973]. NZS 4203:1976 then set new structural
loadings [standards_nz_1976]. Over the same period, preservative-treated timber
poles made the cantilevered pole wall the usual choice in Wellington's hill
subdivisions, displacing gravity walls of mass concrete, brick and stone; that
is general practice rather than a rule, and it is not sourced to a document.

Walls built before 1970 are the ones most likely to have been built without
design, and to be at or past the end of their life.

### 2004: NZS 1170.5

NZS 1170.5:2004, published in December 2004, sets earthquake demand from a
hazard factor, the site subsoil class and a return period tied to the
structure's importance level [standards_nz_2004]. The compliance document for
clause B1 replaced NZS 4203 with the AS/NZS 1170 series from 1 December 2008
[dbh_2008], so a wall designed between 2005 and 2008 may have used either. The
Building Act 2004 tightened consenting over the same years [nz_parliament_2004].

This break separates wall performance less sharply than 1992 does, because a
consented wall built after 1992 was already engineered under clause B1. The
larger change in practice came after the Canterbury earthquakes of 2010 and
2011, and is written down in Module 6 [nzgs_mbie_2017], so 2011 would be a
defensible alternative. The break is kept at 2004 because that is when the
loading standard and the Act changed. Walls built since either date are a small
share of most established suburbs, so the choice moves few walls.

## Where the bins are used

- Step 8 writes one bin per claim property; how it is inferred is in that
  step's method file, `s8_infer_rwt_age_method.md`.
- The report table gives, per suburb, the share of properties in each bin as
  `p_pre_1970`, `p_1970_1991`, `p_1992_2004` and `p_2005_on`, which sum to one.

## Reading a source onto the bins

- **Dwelling age stands in for wall age.** The first wall on a lot is usually
  built with the house, but walls are rebuilt, so the walls on a property are
  often younger than its dwelling. The table gives the oldest the walls are
  likely to be.
- **Walls under 1.5 m are built without consent in every period.** The wall
  model's height rule (`UNCONSENTED_WALL_HEIGHT_M`) handles them, so the age
  bins matter most for taller walls.
- **A decade-coded source cannot split at 1992 or 2005.** The District Valuation
  Roll gives a decade per rating unit. Count the 1990s in `p_1992_2004`, which
  puts 1990 and 1991 in the wrong bin, a small error. Split the 2000s at 2005
  using annual consent counts for the territorial authority.

## Literature review (2026-10-02)

Part C of the second review (`temp/handoff-remaining-review.md`) read these
bins against `temp/gns_review/` (finding ids in backticks). Every point is a
**proposal for the lead**.

- **The 1970 break is supported as the end of the gravity masonry era.** In
  Canterbury, wall type tracked era: historic walls were dressed stone
  masonry, dry stacked or mortared, while crib, gabion, concrete block, timber
  pole and MSE walls are more modern [anderson_2015] (`anderson2015-F07`).
  Stone masonry was the worst performer, about 18% Very Poor against 2.8% for
  timber pole (`F11`). So `pre_1970` is where the poor condition belongs most.
- **Two other dates are in the literature, and neither is a bin edge.**
  - 1960: non-engineered fills and cuts built before 1960 are flagged as a
    sign of future landslides [nzgs_2025_recognition] (`nzgs2025-u2-F09`).
  - The mid-1970s: New Zealand earthfill standards did not exist until then
    [monteith_2020] (`sr2019-051-F06`). Suburb-scale earthworks followed the
    earth-moving machinery of the 1950s [lyndsell_2019] (`sr2019-040-F28`).

  Both concern the ground behind a wall, the cut or fill, rather than the
  wall. **Proposal:** keep the four bins for the wall, and read 1960 and the
  mid-1970s into the fill's engineered or uncontrolled class in the ground
  map and the faces, not into `p_poor`.
- **Age is not monotone for fills.** Wellington's oldest and largest fills
  (Kelburn and Anderson Parks, about 1885 to 1910) survived a century of
  storms and earthquakes without obvious damage, while houses on 1970s and
  1980s fills at Kelson were seriously damaged by fill failures in rain
  [hancox_2013_slope_types] (`sr2013-058-F26`, checked against the page). So
  do not let a fill's age alone raise its failure rate.
- **Code and bins disagree at the Building Act.** `wall_probability` splits
  `p_poor` at 1990 (`BETA_PRE_1990_POOR_SHARE`, `BETA_POST_1990_POOR_SHARE`),
  where the bins and the Act split at July 1992. With a decade-coded roll the
  difference is the same small error the section above describes, but the
  constant names should follow the bins.
- **The bins also give the wall type** (the lead, 2026-10-02): `pre_1970`
  mostly stone and mass concrete gravity walls and untreated timber,
  `1970_1991` treated timber pole and concrete block cantilevers, and the
  later bins engineered walls, with the claim reports (**T-50**) giving the
  type where a wall was described and the mix per bin. The type then sets the
  condition the Koutsoupaki curves read. Their modern-to-poor median ratio,
  1.65, matches Anderson's stone masonry against timber pole and concrete
  block at one PGA.
