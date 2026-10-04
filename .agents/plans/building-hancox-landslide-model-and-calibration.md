# Plan: building model 3 — Hancox et al. — and the calibration of the large models

## Context

Model 3 of the landslide portfolio (`src/scripts/landloss/hazard/landslide/
potential-landslide-rebuild.md`, "The models") is built from the New Zealand
empirical relationships of Hancox, Perrin & Dellow (1997, 2002) and Hancox
(2010), derived from 22 historical New Zealand earthquakes. It has two roles,
and this plan builds both, because they share the same code:

1. **A model in its own right.** Where landsliding occurs (an envelope from
   magnitude, distance and intensity) and how it is distributed within that
   envelope (by slope class).
2. **Two tests reported beside every large model** (1, 2, 4, 5 and 7), not a
   calibration of them. The project lead decided on 2026-10-02 that each
   large model keeps its own published calibration, because scaling every
   model to one target would make them agree whatever their structure, and
   the portfolio would then measure no model uncertainty (rebuild note, "How
   they combine"). The two constraints are:
   - **Extent**, from Hancox: the area affected by landsliding against
     magnitude, the maximum distance at which each size of landslide occurs,
     and the intensity threshold below which there is none.
   - **Amount**, from Marc et al. (2016): the total area (and volume) of
     landsliding an earthquake triggers.

   Kaikōura (Mw 7.8, 2016), where both were observed, tests both.

Hancox's area affected is the area **within which** landslides occurred, not the
area that slid (about 20,000 km² for 1855 Wairarapa), so it constrains extent
only. **Model 3 takes its amount from Marc** (the lead, 2026-10-02): Marc's
total for the scenario earthquake, apportioned over the Hancox area affected
by slope class, gives the study area its share. Marc is the one shared
relationship that sets a number, and it sets it for model 3 alone.

The papers are in `context/lit/landslide/`: `hancox_1997/` (the scan, with a
searchable markdown version and the key figures as page images),
`hancox_2002/`, `hancox_2010/` and `marc_2016/`.

## The forward-use scenario

The study works at a return period (the 2500-year TS1170.5 demand), not a
scenario earthquake. Where a relationship needs a magnitude or a source
distance, the study assumes **every site in the study area is 25 km from an
Mw 8.1 event**. That is the modal event in the NSHM deaggregation of Wellington
PGA at Vs30 = 400 m/s, per the project lead; its source is recorded in the
landslide `status.md` for the report:

```python
# landloss.domain.constants
BETA_SCENARIO_MW = 8.1
BETA_SITE_DISTANCE_KM = 25.0
```

They carry `BETA_` because they stand in for a real source model and go when one
is adopted. What they do, relationship by relationship:

| Relationship | Needs M or distance? | At Mw 8.1, 25 km |
|---|---|---|
| Hancox area affected, log10 A = 0.96 M − 3.7 | M | A ≈ 11,900 km² (±1 SE: about 4,400–32,000 km²), an equivalent radius of about 62 km. Every site at 25 km is inside it |
| Hancox maximum distance by landslide size (Figures 20.1, 20.2) | M and distance | Every size class, up to very large, occurs within 100 km for M ≥ 6.9 at MM8 or more, so every class is possible at 25 km |
| Hancox intensity threshold (MM6 in NZ, MM7 in the Wellington Region) | Intensity only | From the study's own shaking, not the scenario |
| Marc total area and volume | M, source depth, fault length | An event total over the whole affected area, not a total within the study area |
| Marc local density, P = α (a − a_c) | M and distance | See the caution below |

So **for calibration the scenario is not needed**: calibration runs on real
events (Kaikōura, and GFDB events) with their real geometry. **For forward
use** it is needed, but only by the magnitude- and distance-dependent terms.
Under it, the Hancox extent does not clip anything in the study area, and every
landslide size class is possible everywhere. That is worth stating in the
report, because it means the extent calibration shapes the models on real events
but is not binding on the Wellington answer.

**A caution on combining the scenario with the study's shaking.** Marc's shaking
term is a 1 Hz source acceleration with geometric spreading only (a = b·ξS/R,
with b·ξS ≈ 4,000 m at saturation, rising to about 4,300 m at Mw 8.1). Taking
25 km as the distance to the source, that gives about 0.17 g, barely above
Marc's 0.15 g threshold, so Marc's own geometry puts
the study area at the edge of landsliding. Typical ground-motion models give a
PGA of the order of 0.2–0.4 g at that distance. The study's 2500-year TS1170.5
PGA is about 1 g in Wellington. The 25 km / Mw 8.1 assumption and the 2500-year
demand therefore describe different levels of shaking. The plan uses the study's
own shaking for every shaking-dependent term. It uses the scenario only for
terms that need a magnitude or a distance and have no shaking input (Hancox's
area affected and maximum distances). It does not use Marc's distance-based
density forward.

## Decisions and assumptions

| Decision | Choice | Basis |
|---|---|---|
| Hancox area affected | log10 A = 0.96 (±0.16) M − 3.7 (±1.1), SE of estimate ±0.43, A in km² | Hancox et al. (1997) section 3.3, checked against the scan (PDF page 81) |
| Hancox maximum distances | Upper-bound envelopes for each landslide size class, digitised from Figures 20.1 and 20.2 | Only published as plots |
| Intensity threshold | MM7 in the Wellington Region; MM6 elsewhere in NZ | Hancox et al. (1997) PDF page 80, attributed to greywacke |
| Slope distribution | Hancox (2010) Table 2, historical earthquake-induced landslides by slope class | The only NZ-wide slope distribution for EILs |
| Marc amount | Total area, eq. (12): α*A = 3,445 ± 325 m² km⁻², T_SA = 15.8 ± 1.5°; total volume, eq. (11): α*V = 4,174 ± 212 m³ km⁻², T_SV = 11.6 ± 0.6°; a_c = 0.15; b_sat·ξS = 4,000 m (2,800 m for normal faults); M_h = 6.75; Boore & Atkinson (2008) 1 Hz terms; Leonard (2010) fault length; l_asp = 3 km | Marc et al. (2016) sections 3–4 |
| Marc uncertainty | Monte Carlo over the paper's stated parameter distributions (rupture velocity 2000 ± 200 m/s, a_c 0.15 ± 0.02, b_sat·ξS 4000 ± 400 m, M_h 6.75 ± 0.1), reported as 25th/50th/75th percentiles | Marc et al. (2016) section 3.3 |
| Landscape steepness for Marc | Modal slope of 30 m slope within 1 km cells; A_topo from cells with modal slope ≥ 8° | Marc et al. (2016) section 3.2 |
| Scenario for forward use | Mw 8.1 at 25 km, beta constants | Modal event of the NSHM deaggregation of Wellington PGA at Vs30 = 400 m/s (project lead) |
| Size population | Large only, above the agreed split | Agreed split |

## Approach

### Phase 1 — The Hancox relationships

- [x] `landloss.hazard.landslide.models.hancox_1997.relationships`:
      `area_affected_km2(mw, n_se)` with its ±1 SE band, and the inverse
      `mw_from_area_affected`, both as published.
- [x] Digitise the Figure 19 points (area affected against magnitude for each
      earthquake, `context/lit/landslide/hancox_1997/figures/page-075.png`),
      packaged as `src/landloss/io/assets/hancox-1997-figure-19-area-affected.csv`
      so the tests can read it. Leaving out the two smallest events (Peria
      1963, Waiotapu 1983), as the report does, the 20 points refit to
      log10 A = 0.97 M − 3.72, SE 0.45, R² 0.67 (published: 0.96 M − 3.7,
      0.43, 68%).
- [x] `max_distance_km(mw, size_class)`: the Figure 20.1 solid upper-bound
      line, digitised as log10 D = 0.464 M − 1.32 (10, 29, 84 and 304 km at
      M 5, 6, 7 and 8.2, against the text's 10, 30, 100 and ~300), with each
      size class's smallest magnitude and distance cap taken from the section
      3.4 text: moderate–large M ≥ 6.5 within 70 km; very large M ≥ 6.9 and
      extremely large M ≥ 7.1, both within 100 km. The Figure 20.2 MM zones are
      not digitised; the intensity threshold covers what the model needs from
      them.
- [x] Slope classes from Hancox (2010) Table 2. **As printed, the historical
      EIL column sums to 109%** (1%, 9%, 39%, 60%; the 60% splits as 40% for
      36–45° and 20% above 45°). Checked against the scan, so this is the
      published table, not an OCR error. Checked against the 1997 report's own
      slope analysis (section 3.5, Figure 22.1): counting the ~145 landslides
      plotted there by slope gives about 4%, 14%, 39% and 43%, so the 39%
      stands and the 60% is at fault. **Adopted:** 1%, 9%, 39%, and the 51%
      remainder for very steep, split 2:1 at 45° as printed (34% and 17%).
- [x] Unit tests (`tests/landloss/hazard/landslide/models/test_hancox_1997.py`):
      the Figure 19 refit, the inverse round-trips, the distances against the
      text, the size-class thresholds and the shares. The earlier idea of
      testing A(5) ≈ 100 km² and A(8.2) ≈ 20,000 km² was wrong: those are the
      report's upper-bound figures, and the mean line gives 13 km² and
      14,900 km².

### Phase 2 — Marc et al. (2016)

- [x] `landloss.hazard.landslide.calibration.marc_2016`: total area (eq. 12)
      and total volume (eq. 11) from moment magnitude, mean asperity depth R0,
      mechanism (reverse, strike-slip, normal), fault length (Leonard 2010, with
      the strike-slip form above the critical moment), modal slope S_mod and
      A_topo, with the Monte Carlo percentiles, plus `seismic_term_km2` and
      `fit_sensitivity` for refitting the sensitivity on other events. Eqs. 7
      and 8 are implemented as the physics requires rather than as printed (see
      the module docstring).
- [ ] `modal_slope_and_a_topo(dem, rupture)`: 30 m slope, modal slope per 1 km
      cell, A_topo as the share of the predicted landsliding that falls on cells
      with modal slope ≥ 8°.
- [x] **Obtain the supporting information.** Table S1 (the 40 events' moment,
      R0, mechanism, S_mod, A_topo and estimated A and V) is in
      `context/lit/landslide/marc_2016/` and packaged as
      `src/landloss/io/assets/marc-2016-table-s1.csv`, with a numeric version,
      one row per sub-event, in `marc-2016-table-s1-subevents.csv`.
- [x] Reproduce the paper's predictions event by event from Table S1
      (`validations/calibration/fig_marc_2016_table_s1.py`). Refitting on the
      paper's 26 events returns T_SV = 11.7° (paper 11.6°) and α*V within 10%
      of the paper's; see `marc_2016_table_s1_findings.md`.
- [x] Unit tests: fault length over the paper's stated range, strike-slip
      continuity, b saturating at M_h, the closed-form point-source integral
      against numerical integration of eq. 4, and Chi-Chi reproduced
      (`tests/landloss/hazard/landslide/test_calibration_marc_2016.py`).
- [ ] Decide how Marc is used for the Hikurangi interface scenario, which is
      outside its crustal calibration. Options and a recommendation are under
      "Marc for the Hikurangi interface" below. `Source.onshore_fraction`,
      the only code change option A needs, is in place and tested.

### Phase 3 — The calibration interface

- [x] `landloss.hazard.landslide.calibration` (`constraints.py`, exported from
      the package). Since the lead's decision of 2026-10-02 its scaling is
      applied to model 3 only (to Marc's total); for every other model
      `calibrate(...)` is run as a report, its `CalibrationReport` giving the
      total and footprint against Marc and Hancox, and the scaled grid is not
      used:
  - `scale_to_total(coverage, cell_area, target_km2)` scales a coverage grid so
    its landslide area equals a target, capped at full coverage per cell.
  - `extent_mask(epicentral_distance_km, mw, mm)` removes cells beyond
    Hancox's maximum distance for the event and size class, and below the
    intensity threshold. **Hancox's area affected is not a mask.** The areas
    are irregular and asymmetric about the epicentre. For a long rupture such
    as Kaikōura, whose epicentre is at one end, a circle of that area around
    the epicentre would clip landsliding that occurred. It is reported instead,
    against the model's footprint.
  - `fit_transfer_function(relative_hazard, observed_coverage)` fits a monotone
    map from a relative hazard (models 2 and 7) to coverage by quantile
    binning and pooling adjacent violators, as Nowicki Jessee did for their
    equation 9.
  - `calibrate(...)` applies the mask and the scaling and returns a
    `CalibrationReport`: total area before and after, area removed by the
    mask, the scale factor, and the footprint against Hancox's area affected
    (±1 SE).
- [x] Unit tests (`tests/landloss/hazard/landslide/test_calibration.py`):
      scaling preserves the pattern and hits the target, including where the
      per-cell cap binds; the mask removes only cells beyond the envelope or
      below the threshold; the transfer function is monotone and recovers a
      known map.

### Phase 4 — The Kaikōura test of both constraints

- [ ] Observed amount: total source and debris-trail area from the GNS
      inventory (`landloss.io.kaikoura`), replacing the ~20 km² quoted from
      Allstadt et al.
- [ ] Observed extent: the area within which landslides occurred, drawn around
      the inventory as Hancox drew it (a boundary around reported landslide
      localities), replacing the "about 10,000 km²" quoted from Allstadt et al.
- [ ] Marc for Kaikōura: Mw 7.8, the multi-fault rupture length, R0 from the
      published slip models, S_mod and A_topo from LINZ elevation. Kaikōura
      post-dates the paper, so this is an out-of-sample test of Marc itself.
- [ ] Hancox for Kaikōura: A(7.8) ≈ 6,100 km² against the observed extent, and
      the maximum distances against the inventory.
- [ ] The first consumer: model 1 (Nowicki Jessee) run on Kaikōura as
      published, its total and footprint reported against the observations
      (no rescaling; a scaled run is a diagnostic only). This replaces the
      "overall scaling" modification in the rebuild note.
- [ ] Findings file beside the validation scripts
      (`src/scripts/landloss/hazard/landslide/validations/calibration/`).

### Phase 5 — Model 3 as a model

- [x] `landloss.hazard.landslide.models.hancox_1997.model`: coverage over the
      study area as
  - zero where the study's MM is below MM7 (Wellington Region threshold),
  - zero outside the extent (under the forward scenario, nowhere in the study
    area),
  - elsewhere, a density per slope class proportional to Table 2's share
    divided by that class's share of the area, so that the landslides fall on
    slopes in the proportions Hancox observed,
  - scaled so the total matches the amount, Marc's total for the scenario
    apportioned to the study area (phase 6; model 3 is the one model scaled
    to Marc).
- [x] Slope at 10 m from the multiscale stack (`s3_multiscale_slope`), stated as
      a judgement: Hancox measured slope angles of individual failures, not of a
      coarse grid.
- [x] Wellington forward step
      (`steps/s10_hancox_1997/gen_hancox_1997_coverage.py`), with method and
      plan files, handing coverage to the realisation machinery above the size
      split. Its committed Marc settings are the central interface sensitivity
      in this plan (`R0 = 22.5 km`, modal slope 22°, `A_topo = 1`, all
      asperities onshore), explicitly a beta until NSHM geometry replaces it.
      That replacement affects only Marc's amount: the Hancox MM threshold
      already reads each realisation's TS1170.5-derived PGV.

### Phase 6 — Where the Wellington amount comes from

- [x] Decide how the forward total is set (the lead, 2026-10-02): **each
      model sets its own** ("How they combine" in the rebuild note), and
      **model 3 takes Marc's total for the scenario earthquake** (option 2
      below), apportioned to the study area over the Hancox area affected and
      the slope-class shares. Option 1 is withdrawn for the models that have
      their own amount. For the interface scenario Marc needs the real
      interface depth ("Marc for the Hikurangi interface", option A), because
      the total moves from about 90 km² to nothing between 15 and 29 km.
      The options as first set out, given the caution above:
  1. **The models' own shaking-driven totals, after calibration on events.** The
     scaling constants are fitted on Kaikōura and GFDB events against Marc and
     the observations, then applied with the study's 2500-year shaking.
     Preferred, because it keeps the shaking consistent with the rest of the
     study.
  2. **Marc's total for the scenario earthquake**, apportioned to the study
     area. It needs a rupture model, which the scenario lacks, and it inherits
     the shaking mismatch.
- [x] The constants `BETA_SCENARIO_MW` and `BETA_SITE_DISTANCE_KM` in
      `landloss.domain.constants`, with a comment naming each term that reads
      them.

## Marc for the Hikurangi interface

Marc et al. (2016) left subduction events out of their fit for one stated
reason: their asperities are mostly offshore and deep, so onshore shaking is
moderate. Tohoku and Pisco plot, for reference, with volumes like those of
Mw 6 continental events. Beneath Wellington the interface is under land, so
that reason does not hold there. Two physical differences remain: the 1 Hz
source term (Boore & Atkinson 2008 is a crustal model), and the much longer
duration of an interface rupture.

What the unmodified formula gives at Mw 8.1 (reverse, Leonard length 216 km,
72 asperities, b·S = 4.30 km), with every asperity onshore, modal slope 22° and
A_topo 1:

| R0 (km) | Peak 1 Hz a (g) | Total area (km²) | Total volume (km³) |
|---|---|---|---|
| 15 | 0.29 | 88 | 0.18 |
| 20 | 0.22 | 36 | 0.07 |
| 22.5 | 0.19 | 18 | 0.04 |
| 25 | 0.17 | 6 | 0.01 |
| 28.7 | 0.15 | 0 | 0 |

Across the plausible range of interface depths the shaking barely clears
a_c = 0.15, so the depth decides almost the whole answer. Marc cannot be applied
to the interface without a real depth for it.

Options, cheapest first:

- **A. Geometry only, within Marc's physics.** Represent the rupture as
  asperities at their real depths, from the NSHM 2022 Hikurangi interface
  geometry. Count only those beneath land (`Source.onshore_fraction`, or one
  `Source` per depth band), with a reverse mechanism and no refit. Test it on
  the subduction events with estimated totals: Tohoku and Pisco from Marc's
  Figure 1, and any subduction inventory in GFDB. Adopt it if it reproduces
  them within Marc's factor of 2.
- **B. Swap the source term.** Scale b·S by the ratio of an interface
  ground-motion model's 1 Hz spectral acceleration to Boore & Atkinson's at the
  same magnitude and distance, using the interface models in the NSHM 2022
  logic tree. It is one multiplier and needs no refit, but those models have
  to be run.
- **C. A duration factor.** Multiply the sensitivity by
  (D_interface / D_crustal)^k. This is the physically missing term, but one or
  two events at best constrain k, so it is a sensitivity, not a calibration.
- **D. Refit the sensitivity on subduction events.** The principled answer, but
  there are too few onshore subduction inventories to fit two parameters.

Recommendation: **A as the base, with B and C as reported sensitivities.**
The lead's phase 6 decision makes model 3 the exception: Marc sets its
Wellington total, while it remains a reported test beside the other large
models. The built step uses the central `R0 = 22.5 km`, all-onshore sensitivity
until A supplies the interface depth beneath the study area and its onshore
fraction. A also needs Marc's estimated volumes for Tohoku and Pisco (read from
Figure 1 or its sources).

## Files

| File | Purpose |
|---|---|
| `src/landloss/hazard/landslide/models/hancox_1997/relationships.py` | Area affected, maximum distances, thresholds, slope-class shares |
| `src/landloss/hazard/landslide/models/hancox_1997/model.py` | Model 3 coverage |
| `src/landloss/hazard/landslide/calibration/constraints.py` | Scaling, extent mask, transfer function, calibration report (exported from the package) |
| `src/landloss/hazard/landslide/calibration/marc_2016.py` | Marc total area and volume, with uncertainty |
| `src/landloss/domain/constants.py` | `BETA_SCENARIO_MW`, `BETA_SITE_DISTANCE_KM` |
| `src/landloss/io/assets/hancox-1997-figure-19-area-affected.csv` | Digitised Figure 19 points |
| `src/scripts/landloss/hazard/landslide/validations/calibration/` | Kaikōura test of both constraints, findings |
| `src/scripts/landloss/hazard/landslide/steps/s<n>_hancox_1997/` | Wellington forward run |
| `tests/landloss/hazard/landslide/models/test_hancox_1997.py`, `tests/landloss/hazard/landslide/test_calibration.py` | Unit tests |

## Verification

- The digitised Figure 19 points refit to the published regression.
- Marc reproduces its own Table S1 predictions (once obtained).
- At Kaikōura: Marc's predicted total area against the GNS inventory's, and
  Hancox's A(7.8) against the observed extent, each reported as a ratio.
- Model 1 at Kaikōura as published, against the observations.

## Risks and open items

- **Extent and amount are different things,** and Hancox is extent only. Kept
  distinct throughout.
- **The forward scenario is a subduction event, outside Marc's calibration.**
  The project lead confirms the Mw 8.1 at 25 km is the Hikurangi interface.
  Marc is fitted on shallow crustal earthquakes, and excluded subduction events
  because deep offshore ruptures deliver only moderate onshore shaking. Beneath
  Wellington that reasoning does not hold, since the interface lies about 20–25 km
  under the city. Hancox's historical events are all crustal too. Consequences:
  - Marc and Hancox **test the portfolio on crustal events** (Kaikōura, the
    Table S1 events, GFDB), which they are fitted for. Marc also sets model 3's
    Wellington total under the lead's phase 6 decision; the other models keep
    their own published amounts.
  - **Duration** is the physical difference. A subduction rupture shakes for
    much longer, which none of models 1–3 represents (Nowicki Jessee's
    cross-validation was worst on Tohoku). Carry this as a stated limitation,
    and test it on the subduction inventories in GFDB (Tohoku 2011 among them).
  - Marc's geometry can still be evaluated for the interface as a
    sensitivity (R0 about 20–25 km, a reverse mechanism, a rupture length from
    Leonard), reported as outside its calibration.
- **Marc's shaking is not the study's shaking** (see the caution above), which
  is why option 1 in phase 6 is preferred.
- **Hancox (2010) Table 2 does not sum to 100%** as printed.
- **Digitising** Figures 19, 20.1 and 20.2 adds a small error; the Figure 19
  refit is its check.
- **Kaikōura's observed extent** depends on how the boundary is drawn around the
  inventory; draw it the way Hancox describes, and report the sensitivity.
- **GFDB** is read off `R:`, which Claude may not access; runs using it are made
  by the project lead.
- **From the literature review of 2026-10-02** (part B; proposals for the lead,
  detail in the rebuild note, "What the literature review says about the
  route"):
  - **The area-affected relationship is likely a minimum.** June 1942
    landsliding was reported over about 6,500 km², against the 3,700 km² the
    1997 study used for it [downes_2001] (`downes2001-F21`, `F22`). Read the
    Kaikōura extent test with that in mind: an observed extent above A(7.8)
    is expected, not a failure of the relation.
  - **The Wellington MM7 threshold sits one level below the revised MM
    scale**, which first describes significant landsliding at MM8
    [dowrick_2008] (`dowrick2008-F05`). The 2013 Cook Strait events were
    judged threshold events for Wellington (`sr2013-042-F07`). Test both
    thresholds in the Kaikōura run.
  - **Kaikōura is a low case for the amount**: two to six times fewer
    landslides than magnitude-only relations predict (`massey2018-F06`), and
    fewer large ones than Murchison (`F07`). Carry Murchison (wet) and
    Inangahua as high cases. Season changes the area affected by 2 to 2.5
    times [dellow_hancox_2006] (`dellow2006-F05`), so state the season of
    every calibration event.
  - **Interface events landslide less for their magnitude**
    (`brabhaharan2018-F36`; Dusky Sound 2009, `sr2015-016-F22`), which
    supports phase 6 option 1. No evidence in the set quantifies duration.

## Sources

- Hancox, G.T., Perrin, N.D. & Dellow, G.D. (1997). Earthquake-induced
  landsliding in New Zealand and implications for MM intensity and seismic
  hazard assessment. GNS Client Report 43601B.
- Hancox, G.T., Perrin, N.D. & Dellow, G.D. (2002). *BNZSEE* 35(2).
- Hancox, G.T. (2010). *Australian Geomechanics* 45(3), 51–64.
- Marc, O., Hovius, N., Meunier, P., Gorum, T. & Uchida, T. (2016). A
  seismologically consistent expression for the total area and volume of
  earthquake-triggered landsliding. *JGR Earth Surface* 121(4), 640–663.
  doi:10.1002/2015JF003732. Supporting information, Table S1 included, in
  `context/lit/landslide/marc_2016/`.
- Leonard, M. (2010). Earthquake fault scaling. *BSSA* 100(5A). Not yet obtained.
- Boore, D.M. & Atkinson, G.M. (2008). NGA ground-motion relations. *Earthquake
  Spectra* 24(1). Not yet obtained.
- Allstadt, K.E., Jibson, R.W., Thompson, E.M., et al. (2018), *BSSA* 108(3B)
  (`context/lit/landslide/allstadt_2018/`).
