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

## Proposed phases (to be developed)

### Phase 1 — Review the anchors

- [ ] The reviewer checks the 21 anchor rows and the class-word readings.
- [ ] Add anchors from documents still to be obtained, with full citations:
      the Christchurch 2011 landslides (`dellow_2011`), Port Hills rockfall
      against PGA (`massey_2014`), and the unfiltered Canterbury hill-property
      claims if NHC supplies them (**T-17**, **T-18**).

### Phase 2 — Fit on the face polygons

- [ ] Run the anchoring validation on the face-based polygons of the pilot.
- [ ] Fit the localised medians and dispersion to the net rate on the ground.
- [ ] Set the low and high multipliers.

### Phase 3 — Check the result

- [ ] The pilot's share of polygons and of area failing, by Kingsbury zone and
      wall state, against the anchors.
- [ ] Total failed area, urban plus large, against Marc et al. (2016) and
      Nowicki Jessee et al. (2018) at the demand.
- [ ] The share of failures confined to one property, against the local
      expectation in `.agents/context/land-damage-mechanisms.md`.

## References

`kingsbury_1995`, `koutsoupaki_2023`, `marc_2016`, `nowicki_jessee_2018`,
`hancox_1997`, `de_vilder_2022`, `dellow_2011`, `massey_2014`, and the GNS
report findings cited by id in the anchor table (`temp/gns_review/`). Keys are
in `doc/references.bib`.

Written 2026-10-02 as a skeleton for review.
