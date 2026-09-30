# Plan: building model 2 — Kritikos, Robinson & Davies (2015)

## Context

Model 2 of the landslide portfolio (`src/scripts/landloss/hazard/landslide/
potential-landslide-rebuild.md`, "The models") is the fuzzy-logic coseismic
landslide hazard model of Kritikos, Robinson & Davies (2015). It was built at the
University of Canterbury for regions with no landslide inventory and no
geotechnical data, which is Wellington's situation, and it needs only three
inputs: shaking intensity, a DEM and an active fault map. Allstadt et al. (2018)
could not run it globally only for want of a global fault map; the NZ Active
Faults Database removes that obstacle here.

It is a **large-landslide** model: it sits above the agreed size split
(provisionally 500 m² of source area, with 1,000 m² as the sensitivity case) and
does not represent cut, fill or retaining. The small urban population is
model 6.

The paper is summarised in `context/lit/landslide/kritikos_2015/
kritikos-2015-summary.md`. The PDF is not in git (about 98 MB); it is held at
`U:\MAMI\Literature`.

Two facts about the paper shape this plan:

- **The membership functions are published only as plots** (Figure 5, the
  average curves). No parameters are tabulated, so the curves have to be
  digitised, and the digitisation checked by reproducing the paper's own
  scores.
- **The output is a relative probability (0 to 1), not a coverage.** The
  authors call it "an order-of-magnitude estimate only". Turning it into
  landslide area needs the calibration built in the model 3 plan
  (`building-hancox-landslide-model-and-calibration.md`).

## Decisions and assumptions

| Decision | Choice | Basis |
|---|---|---|
| Factors | MM intensity, slope angle, distance to mapped active faults, slope position (TPI, four classes) | The paper's final four-factor model (section 4.4 and conclusions). Distance to streams is dropped, as the paper drops it |
| Memberships | The paper's **average** curves (Figure 5, dashed), digitised | Built to be applied beyond the training events; event-specific curves are not transferable |
| Aggregation | Fuzzy gamma, γ = 0.9 | The paper's choice; γ = 0.8 changed Wenchuan AUC by 0.005, so tested as a sensitivity |
| Resolution | 60 m, one grid for every layer | The paper's DEMs are 60 m and it stresses that all layers must share one resolution |
| DEM | LINZ elevation, aggregated to 60 m | Local and current; the paper used 60 m ASTER |
| Active faults | NZ Active Faults Database 1:250,000 (GNS Science 2016, doi:10.21420/R1QN-BM52), horizontal distance to mapped traces | Held in the cross-project data library as `R:\DataLibrary\210.20_active_faults_NZ_NZAFD_AF250\` (V1, downloaded 2026-09-30 from the GNS WFS layer `gns:af250_download`), read by a reader in `landloss.io` in the same way as `landloss.io.gfdb`. Licence CC BY 3.0 NZ, as the GNS WFS service states it; attribute GNS Science |
| Shaking | MM intensity per cell from the study's own PGV (the shaking module's `s2_pgv` step), converted with the PGV form of Worden et al. (2012), without its distance and magnitude terms. With log = log10 PGV (cm/s): MMI = 3.78 + 1.47 log for log ≤ 0.53, and MMI = 2.89 + 3.16 log above it. Capped at MM X; the memberships are flat beyond IX | Decided (see below) |
| Output | Relative hazard H (0–1), then coverage through the model 3 calibration | The paper gives no coverage; the portfolio needs one |
| Size population | Large only (above the split) | Agreed split |

**Forward-use scenario.** The study works at a return period, not a scenario, so
where a magnitude or a source distance is needed the study assumes every site is
**25 km from an Mw 8.1 event**, the modal event in the NSHM deaggregation of
Wellington PGA at Vs30 = 400 m/s (recorded with its source in the landslide
`status.md`) (`BETA_SCENARIO_MW`, `BETA_SITE_DISTANCE_KM`,
defined in the model 3 plan). Model 2 does not need either: its trigger is MM
intensity, which comes from the study's shaking, and its fault term is
distance to *mapped* faults, a static property of the site rather than distance
to the rupture. The scenario enters model 2 only through the calibration.

## Approach

### Phase 1 — Digitise the memberships

- [ ] Render Figure 5 (journal p. 721) from the PDF at high resolution into
      `context/lit/landslide/kritikos_2015/figures/`, as was done for Hancox.
- [ ] Digitise the five average (dashed) curves: MM (V to IX), slope angle
      (0–5° to >50°, 5° classes), distance to active faults (0–5 km to >50 km),
      distance to streams (for the record; not used), and the four slope
      position values (flat, valley, midslope, ridge).
- [ ] Hold them in `landloss.hazard.landslide.models.kritikos_2015.memberships`
      as tabulated points with linear interpolation between them, each table
      commented with where it was read from. Extrapolation is flat beyond the
      plotted range.
- [ ] Unit tests: every membership lies in 0–1, rises (MM, slope) or falls
      (fault distance) as the figure shows, and the four slope position values
      are in the published order (ridge > midslope > valley > flat).

### Phase 2 — Inputs

- [ ] `inputs.py`: slope angle on the 60 m grid, from LINZ elevation aggregated
      to 60 m, reusing `landloss.common.utils.terrain`.
- [ ] Slope position: TPI classified into four classes following Jenness et al.
      (2013), as the paper does. The paper does not state its TPI neighbourhood;
      choose one, record it as a judgement, and test a smaller and a larger
      radius.
- [ ] Distance to mapped active faults: a reader in `landloss.io` for the NZ
      Active Faults Database in the data library
      (`210.20_active_faults_NZ_NZAFD_AF250`, V1), following `landloss.io.gfdb`,
      and horizontal distance to the nearest trace on the 60 m grid. R: is read
      by the project lead's runs, not Claude's.
- [ ] MM intensity: convert the study's PGV to MM with Worden et al. (2012),
      PGV form (`landloss.hazard.shaking` gains a `mmi_from_pgv`). For the validation events, read MM directly from the
      ShakeMap `grid.xml` (`landloss.io.shakemap` already carries `mmi`).

### Phase 3 — The model

- [ ] `model.py`: memberships applied per factor, combined by fuzzy gamma
      (paper eq. 4) with γ = 0.9, returning H on the 60 m grid. Cells below
      slope 5° are reported but flagged, as the paper scores both with and
      without them.
- [ ] Unit tests: fuzzy gamma against a hand-computed case; γ = 0 reduces to the
      fuzzy product, γ = 1 to the fuzzy sum.

### Phase 4 — Reproduce the paper (the check that the digitisation is right)

- [ ] Rebuild the success-rate AUC for the paper's events with our digitised
      curves: Northridge 0.904 and Wenchuan 0.839 (average memberships, whole
      study area), and the blind Chi-Chi test, 0.921. Inventories from the USGS
      Ground Failure Database (`landloss.io.gfdb`), ShakeMap MMI from the USGS
      event pages, a 60 m DEM, and active faults from a global fault map (GEM
      Global Active Faults) for those regions.
- [ ] Acceptance: within about 0.02 of each published AUC. The GFDB inventories
      may not be the exact versions the paper used (Wenchuan in particular), so
      a larger gap is investigated before it is accepted or blamed on the
      digitisation.
- [ ] Record the result in a findings file beside the validation scripts
      (`src/scripts/landloss/hazard/landslide/validations/kritikos_2015/`).
- [ ] **Note:** GFDB is read off `R:`, which Claude may not access. These runs
      are made by the project lead.

### Phase 5 — The New Zealand check: Kaikōura

- [ ] Run the model for Kaikōura with the USGS ShakeMap (version 16) MMI, LINZ
      elevation and the NZ Active Faults Database, and score it against the GNS
      inventory (`landloss.io.kaikoura`, source areas) by success-rate AUC.
- [ ] Test one greywacke adjustment. The model has no geology, and Hancox et al.
      (1997) set Wellington's landsliding threshold one intensity level higher
      (MM7) for greywacke. Compare the AUC and the fitted transfer function
      (phase 6) with the MM membership shifted by one intensity on greywacke,
      and without the shift.

### Phase 6 — From relative hazard to coverage

- [ ] Fit a transfer function from H to areal coverage on Kaikōura: bin cells by
      H, take the observed coverage in each bin (source areas, and source plus
      trail, kept separate), and fit a monotone curve, as Nowicki Jessee fitted
      their equation 9. This is New Zealand's own conversion, from New Zealand's
      only complete coseismic inventory.
- [ ] Apply the model 3 calibration: scale the total to the Marc et al. (2016)
      amount and zero it outside the Hancox extent
      (`landloss.hazard.landslide.calibration`, built in the model 3 plan).

### Phase 7 — Wellington forward run

- [ ] A step under `src/scripts/landloss/hazard/landslide/steps/` (next free
      number), following the `adding-steps-scripts` skill: coverage on the 60 m
      grid over the study area, from the study's MM, then handed to the
      realisation machinery with the size distribution truncated below at the
      split.
- [ ] Method and plan files for the step; `status.md` updated.

## Files

| File | Purpose |
|---|---|
| `src/landloss/hazard/landslide/models/kritikos_2015/memberships.py` | Digitised average memberships |
| `src/landloss/hazard/landslide/models/kritikos_2015/inputs.py` | 60 m slope, TPI slope position, fault distance, MM |
| `src/landloss/hazard/landslide/models/kritikos_2015/model.py` | Fuzzy gamma aggregation |
| `src/landloss/io/active_faults.py` | NZ Active Faults Database reader |
| `src/scripts/landloss/hazard/landslide/validations/kritikos_2015/` | Reproduction of the paper, the Kaikōura check, findings |
| `src/scripts/landloss/hazard/landslide/steps/s<n>_kritikos_2015/` | Wellington forward run |
| `context/lit/landslide/kritikos_2015/figures/` | Rendered Figure 5 and the digitised points |
| `tests/landloss/hazard/landslide/models/test_kritikos_2015.py` | Unit tests |

## Verification

- The digitised curves reproduce the paper's three AUCs within about 0.02.
- The Kaikōura AUC is reported, with and without the greywacke shift.
- After calibration, total landslide area matches the Marc target and nothing
  lies outside the Hancox extent.

## Risks and open items

- **The MM conversion is decided but influential.** Worden et al. (2012), PGV
  form, for three reasons. It is the conversion the USGS ShakeMap uses to turn
  ground motion into MMI, so it matches how MMI is produced for the events the
  model was trained and is checked on. The paper downloaded its MMI from the
  USGS in 2014, so this is likely but not certain for its three events. PGV
  tracks intensity better than PGA at the MM VII–IX range that matters here.
  And the study already produces PGV. Its scatter (a standard deviation of
  about 0.6–0.7 intensity units) is carried into the realisations. The New
  Zealand GMICEs of Moratalla et al. (2021) are the sensitivity case.
  Coefficients are from the USGS `shakelib` implementation (`wgrw12`); check
  them against the paper when it is obtained.
- **Digitisation error** is small compared with the model's own stated
  precision, but is only known once phase 4 reproduces the AUCs.
- **Fault density.** The fault membership was fitted where mapped faults are
  sparse. Wellington is dense with mapped active faults, so much of the study
  area is within 10 km of one. Check how much of the area the fault term
  saturates.
- **No geology.** Greywacke is represented only through the phase 5 shift, if
  it is kept.
- **TPI scale** is not stated in the paper and is scale-dependent (the paper's
  own discussion); it is a sensitivity, not a fixed value.

## Sources

- Kritikos, T., Robinson, T.R. & Davies, T.R.H. (2015). Regional coseismic
  landslide hazard assessment without historical landslide inventories: a new
  approach. *JGR Earth Surface* 120, 711–729. doi:10.1002/2014JF003224.
- Allstadt, K.E., Jibson, R.W., Thompson, E.M., et al. (2018), *BSSA* 108(3B),
  1649–1664 (`context/lit/landslide/allstadt_2018/`).
- Hancox, G.T., Perrin, N.D. & Dellow, G.D. (1997), GNS Client Report 43601B
  (`context/lit/landslide/hancox_1997/`).
- Jenness, J., Brost, B. & Beier, P. (2013). Land Facet Corridor Designer
  (topographic position index classification). Not yet obtained.
- Worden, C.B., Gerstenberger, M.C., Rhoades, D.A. & Wald, D.J. (2012).
  Probabilistic relationships between ground-motion parameters and Modified
  Mercalli intensity in California. *BSSA* 102(1), 204–221. Not yet obtained;
  coefficients read from the USGS `shakelib` `wgrw12` module.
- Moratalla, J.M., et al. (2021). New ground motion to intensity conversion
  equations (GMICEs) for New Zealand. Not yet obtained; confirm the full
  citation when it is. The sensitivity case.
- GNS Science (2016). New Zealand Active Faults Database 1:250,000 scale.
  doi:10.21420/R1QN-BM52. Langridge, R.M. et al. (2016), *NZ Journal of Geology
  and Geophysics* 59(1), doi:10.1080/00288306.2015.1112818.
