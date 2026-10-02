# Plan (skeleton): anchoring and calibrating the urban slope fragilities

**This is a skeleton, written for review.** It sets out what exists, what
the pilot showed, and the questions the anchoring has to answer, and leaves
the method open. The reviewer is invited to develop it: to propose the
anchors, the fitting, the targets and the checks, and to say where the
evidence below is too thin to carry a number. Points where a view is
specifically wanted are marked **Reviewer:**.

## Context

Every urban failure polygon carries a lognormal fragility on PGV, median
`theta` and dispersion `beta`
(`landloss.hazard.landslide.urban.fragility`, landslide step 8). A polygon
with a wall takes the wall's curve by size and condition; a polygon without
one takes a localised curve whose median falls with its Kingsbury rating. All
the numbers that set these curves are placeholders:

| Number | Placeholder | Where |
| --- | --- | --- |
| Localised median at rating 0 and at 150 | 3.0 and 0.6 m/s, log-linear between | `LOCALISED_THETA_AT_ZERO_RATING_M_S`, `LOCALISED_THETA_AT_MAX_RATING_M_S` in `fragility.py` |
| Localised dispersion | 0.6 | `LOCALISED_FRAGILITY_BETA` in `landloss.domain.constants` |
| Rate setting multipliers on every median | low 1.5, medium 1.0, high 1/1.5 | `URBAN_RATE_FACTORS` in `landloss.domain.constants` |
| Wall curves | Koutsoupaki et al. (2023), one unnamed wall class by size and condition, converted from PGA to PGV at each site's ratio | `src/landloss/io/assets/retaining-wall-fragility.csv` |
| Topographic amplification | 1.0 to 1.5, from position and slope | `TOPOGRAPHIC_AMPLIFICATION_MAX` |

The pilot run of 2 October 2026 used them and failed far too much ground:
44% of polygons, 36% of the urban domain evacuated, 88% of sloping walls
replaced, against the order of 1% coverage the literature gives for strong
shaking. The demand is the TS1170.5 2,500-year field as the standard gives it
(**T-26**, decided 2026-10-02): PGA 1.68 to 1.77 g on site classes II and III
over the pilot, PGV 1.1 to 2.0 m/s.

What is built for the anchoring, and not yet run:

- `src/landloss/io/assets/urban-fragility-anchors.csv`: 21 anchor rows. A01 to
  A15 read Kingsbury (1995) Tables 1 and 7 (five susceptibility zones against
  three scenarios, each with a PGA on rock, each cell a failure class turned
  into a fraction failing). A16 to A21 are from the GNS report review: the
  Kaikōura 2016 shaking in Wellington with no urban failures recorded, the Port
  Hills 2011 cut and fill failures, and the forecasts for Wellington cuts and
  fills. The class-word-to-fraction readings were set by the build agent for
  review; each row carries who set it and why.
- `hazard/landslide/validations/urban/fig_urban_fragility_anchors.py` and
  `table_urban_fragility_anchors.py`: draw the low, medium and high curves per
  zone against the anchors and fit the localised constants and a dispersion
  (`fit_localised_fragility`).

The urban polygons themselves are being rebuilt from faces
(`.agents/plans/building-face-based-urban-slope-polygons.md`). The anchoring
should be run on the face polygons, not on the banded patches, because the
rate a fragility has to produce depends on what one polygon is.

## Questions the anchoring has to answer

1. **What does a fraction failing refer to?** Kingsbury's classes describe how
   widespread failures are over a zone; a fragility gives the probability that
   one polygon fails. Turning one into the other needs a polygon size and a
   count per area. **Reviewer:** is per-polygon the right unit, or should the
   anchor be the share of area failing?
2. **The net rate on the ground.** A step face can sit inside a bank, and a
   piece of ground fails if either does. The anchors describe the ground, so
   the per-polygon medians have to be set with the nesting in mind.
3. **The demand is beyond the anchors.** Kingsbury's strongest scenario is
   0.5 to 0.8 g on rock; the study's demand is 1.0 to 1.8 g. The fit
   extrapolates. **Reviewer:** which evidence constrains the curves at 1 to 2 g
   (the Port Hills 2011 is the only observed case at that level)?
4. **The total.** The urban failures plus the large-model failures should sum
   to a total area consistent with Marc et al. (2016) and Nowicki Jessee et
   al. (2018) for the demand, and the large models are calibrated that way
   already. **Reviewer:** is a total-area target the right top-level check for
   the urban population, which those relations were not fitted on?
5. **Walls.** The Koutsoupaki curves are for cantilever walls designed to a
   factor of safety, in PGA; Wellington's walls are mostly older gravity,
   crib and timber pole walls. **Reviewer:** are these curves usable at all,
   what would replace them, and what does the rate setting mean for walls?
6. **What low, medium and high bracket.** The setting multiplies every median
   by one factor. **Reviewer:** should the bracket be set by the spread of the
   anchors, by the fit's uncertainty, or by judgement, and should walls and
   localised failures move together?

## Literature review (2026-10-02): the reviewer's answers

Read against the GNS literature review in `temp/gns_review/` (finding ids in
backticks, `out/findings.csv`). Every answer below is a **proposal for the
lead**; numbers that are ours say so. First-batch findings (the SR reports)
were checked against the page before being used here, as noted against each.

### The anchor rows

Three rows read their source more strongly than the source allows, and one
row cites a source that does not say what the row needs:

| Row | As built | What the page says | Proposal |
| --- | --- | --- | --- |
| A16 | Kaikōura 2016 at 0.15 g in central Wellington, "no urban cut or wall failures recorded", 0.001 | The finding (`sr2019-038-F13`) gives only the 0.15 g rock-site record. Nothing in the reviewed set records the absence of failures in 2016 | Replace the basis with 2013 (below) and keep 2016 only if a source for its absence of failures is found |
| A19 | Every SH58 cut steeper than 1V:1H fails somewhere at MM8 to MM9, read as one polygon in two | The cuts are "expected to be affected by small to moderate-sized failures (10-1,000 m³)" (`sr1995-005-F08`, checked against the scan, PDF page 51) | Read it as a share of face area, not of polygons: a 10 to 1,000 m³ failure on a long cut takes part of it. With the face segments of the faces plan (phase 3), 0.5 of segments is the upper end |
| A21 | At MM8 to MM10 many earth fills could crack and slump, read as three polygons in ten | "many earth fills could suffer **minor** cracking and slumping, and **in some cases** moderate to large earthquake-induced failures could occur, especially in fills that are poorly drained" (`sr2013-058-F29`, checked against the page) | Minor cracking and slumping is damaged ground that is not evacuated (A-14), not failure. Read the failing share from "in some cases", lower than 0.3 (**ours**: 0.05 to 0.1), and send the cracking to imminent ground |
| A20 | Batters at 45 to 50° reasonably resistant at MM8 to MM9, 0.05 | "Local evidence indicates that batters cut at 45°-50° can be expected to be reasonably resistant to earthquake shaking" (`sr1995-005-F11`, checked against the scan, PDF page 47) | Keep. The evidence itself is not given |

A new low-demand anchor, observed, from the second review batch (which had an
independent check):

- **The 2013 Cook Strait and Lake Grassmere earthquakes.** Wellington recorded
  PGA of 0.21 to 0.26 g [holden_2013] (`holden2013-F01`, `F02`, `F04`), and
  the only Wellington landslides seen were small debris falls in wave-cut
  fill at Kaiwharawhara Point and a small rock fall off an old quarry face
  at Lyall Bay, both on modified ground [van_dissen_2013]
  (`vandissen2013-F01`, `F02`). The shaking is above Kaikōura's 0.15 g and
  the outcome is observed, so this anchor should replace A16's reading.
  Caveats: the ground inspected after the August event is not stated
  (`vandissen2013-F22`), and the moderate shaking lasted under 8 s
  (`holden2013-F05`, `F06`), against the minutes of a Hikurangi interface
  event.

### Question 1: what a fraction failing refers to

**Anchor on the share of face area that evacuates, not on the share of
polygons.** Kingsbury's classes describe how widespread failure is over a
zone [kingsbury_1995], and the forecasts read the same way: the SH58 cuts are
"affected by" failures of a given size (above). The expected evacuated share
of a zone is `sum(p_i x A_i) / sum(A_i)` over its face polygons, so it can be
compared with an anchor whatever size one polygon is. A per-polygon anchor
changes meaning every time the face segmentation changes. The per-polygon
`p_fail` stays what step 9 draws on.

### Question 2: the net rate on the ground

No change from the skeleton. A step inside a bank, or a segment beside its
neighbour, both add to the evacuated share. The share in question 1 is
counted after step 9's absorption, so nested failures are counted once.

### Question 3: evidence at 1 to 2 g

The observed record at this level is thin and is not Wellington:

- **Port Hills 2011** (MM8 to MM9, about 1 to 2 g): highly damaging, but most
  failures were under 100 m³ (`sr2015-016-F18`); cut slopes and some fill
  slopes failed "in many cases" (`sr2019-038-F14`). Wellington's slope
  modification is far greater in size and scale than Christchurch's (same
  finding).
- **The Priscilla and Orchy forecasts at 1.09 g** (the scaled 2,500-year
  Kaikōura record): the as-built fills move 0.03 and 0.07 m drained by
  Newmark, and 0.15 and 0.08 m in RS2; with the water table at the ground
  surface they move about 2.2 m [monteith_2020] (`sr2019-051-F20`, Table 3,
  checked against the page; `F21`). The saturated case is the authors' stated
  worst case, "likely unrealistic" in full. **For fills, groundwater sets the
  outcome at this demand more than the shaking does.**
- **Dellow and Hancox (2006):** soil moisture moves the landslide response by
  up to two MM units. In an MM8 zone, the landslide damage ranges from the
  MM6 description when dry to the MM9 description when very wet
  [dellow_hancox_2006] (`dellow2006-F01` to `F03`, a scan, read by the
  second-batch checker).
- **The MM scale:** "significant landsliding likely in susceptible areas"
  first appears at MM8 [dowrick_2008] (`dowrick2008-F05`), one level above
  the MM7 that A-11 takes from Hancox et al. (1997). Slides in roadside
  cuttings and unsupported excavations are an MM8 effect in the scale QMAP
  uses (`qmap10-2000-F21`, a scan from the first batch, not checked). Steep unsupported cuts over 3 m high fail from
  MM6 [brabhaharan_2018; hancox_2015] (`brabhaharan2018-F03`,
  `sr2015-016-F05`). So the curves should begin to rise at MM6 on the
  steepest faces and reach significant shares at MM8, not MM7.

The fit at 1 to 2 g is therefore an extrapolation constrained by Port Hills
alone. The proposal is to say so in the report, and to let the rate setting
carry the uncertainty (question 6) rather than add anchors that do not exist.

### Question 4: the total

**Keep the total-area check, but only as a check on the large and urban
populations together, never as a target for the urban one.** Marc et al.
(2016) and Nowicki Jessee et al. (2018) were fitted on natural landscapes,
and the urban failures are small and on modified ground, which those
inventories under-sample. GNS also rates its own earthquake-induced
landslide model as under-estimating (`sr2025-001-F05`). The urban population
is anchored on its own rows (Kingsbury, the forecasts, 2013, Port Hills).

### Question 5: walls

Deferred to part C of the review (the wall fragility and damage states),
which reads Anderson et al. (2015) on the 2,991 Canterbury walls by type and
height [anderson_2015]. One point bears on the anchoring now: about a third
of the Canterbury walls fell into the Average or Poor performance classes,
which have no counterpart in the model's two damage states
(`anderson2015-F09`). A wall that is damaged but does not fail is neither
"none" nor "replace".

### Question 6: what low, medium and high bracket

**Bracket by antecedent wetness, the one published driver of a two-unit
spread** [dellow_hancox_2006]:

- low = dry ground;
- medium = average;
- high = wet ground.

This gives the setting a physical meaning the lead can state. Its size is
**ours**: one MM unit is of the order of a doubling of PGA, so two units is
a factor of about two to four on the median, wider than the 1.5 now set. That
conversion still has to be taken from a published MM to PGA relation before
the factors are set; the review set does not give one directly.

Walls and localised failures should not move by the same factor:

- fills, walled or not, are the groundwater-sensitive ground
  (`sr2019-051-F20`, `F26`) and take the full spread;
- dry rock cuts take less.

**Proposal: two factor sets, one for fill and one for everything else.**

## Proposed phases (to be developed)

### Phase 1 — Review the anchors

- [x] The reviewer checks the 21 anchor rows and the class-word readings
      (2026-10-02, "The anchor rows" above): A16, A19 and A21 read their
      sources too strongly; A20 stands; the Kingsbury rows were not re-read.
- [ ] The lead decides the A16, A19 and A21 corrections and the 2013 anchor,
      and `urban-fragility-anchors.csv` is edited to match, each row's
      `set_by` and `basis` saying who decided.
- [ ] Add anchors from documents still to be obtained, with full citations:
      the Christchurch 2011 landslides (`dellow_2011`), Port Hills rockfall
      against PGA (`massey_2014`), and the unfiltered Canterbury hill-property
      claims if NHC supplies them (**T-17**, **T-18**).

### Phase 2 — Fit on the face polygons

- [ ] Run the anchoring validation on the face-based polygons of the pilot.
- [ ] Fit the localised medians and dispersion to the net rate on the ground.
- [ ] Set the low and high multipliers, by antecedent wetness, one set for
      fill and one for everything else (question 6), once a published MM to
      PGA relation fixes the size of one MM unit.

### Phase 3 — Check the result

- [ ] The pilot's share of polygons and of area failing, by Kingsbury zone and
      wall state, against the anchors.
- [ ] Total failed area, urban plus large, against Marc et al. (2016) and
      Nowicki Jessee et al. (2018) at the demand.
- [ ] The share of failures confined to one property, against the local
      expectation in `.agents/context/land-damage-mechanisms.md`.

## References

`kingsbury_1995`, `koutsoupaki_2023`, `marc_2016`, `nowicki_jessee_2018`,
`hancox_1997`, `de_vilder_2022`, `dellow_2011`, `massey_2014`,
`dellow_hancox_2006`, `dowrick_2008`, `holden_2013`, `van_dissen_2013`,
`monteith_2020`, `hancox_brabhaharan_1995`, `hancox_2013_slope_types`,
`brabhaharan_2018`, `anderson_2015`, and the GNS
report findings cited by id in the anchor table (`temp/gns_review/`). Keys are
in `doc/references.bib`.

Written 2026-10-02 as a skeleton for review. Reviewed against the GNS
literature review on 2026-10-02 (the section above): the answers are
proposals, and the method is still the lead's to settle.
