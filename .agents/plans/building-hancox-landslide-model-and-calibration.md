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
2. **The calibration of every large model** (1, 2, 5 and 7). Every one of them
   is checked against two independent constraints:
   - **Extent**, from Hancox: the area affected by landsliding against
     magnitude, the maximum distance at which each size of landslide occurs,
     and the intensity threshold below which there is none.
   - **Amount**, from Marc et al. (2016): the total area (and volume) of
     landsliding an earthquake triggers.

   Kaikōura (Mw 7.8, 2016), where both were observed, tests both.

Hancox's area affected is the area **within which** landslides occurred, not the
area that slid (about 20,000 km² for 1855 Wairarapa), so it constrains extent
only. Marc supplies the amount. The two are complementary, which is why they are
built together.

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

- [ ] `landloss.hazard.landslide.models.hancox_1997.relationships`:
      `area_affected_km2(mw)` with its ±1 SE band, and the inverse
      `mw_from_area_affected`, both as published.
- [ ] Digitise the Figure 19 points (area affected against magnitude for each
      earthquake, `context/lit/landslide/hancox_1997/figures/page-075.png`) into
      a CSV beside the figure, and check the digitised points refit to
      0.96 M − 3.7 within the published standard errors.
- [ ] Digitise the Figure 20.1 and 20.2 upper-bound envelopes (maximum
      epicentral distance for each size class, and by MM zone) and hold them as
      `max_distance_km(mw, size_class)`.
- [ ] Slope classes from Hancox (2010) Table 2. **As printed, the historical
      EIL column sums to 109%** (1%, 9%, 39%, 60%; the 60% splits as 40% for
      36–45° and 20% above 45°). Checked against the scan, so this is the
      published table, not an OCR error. Use the shares normalised to 100%, say
      so, and check against the 1997 report's own slope analysis (section 3.5,
      Figure 22.1) whether the 39% or the 60% is the figure at fault.
- [ ] Unit tests: A(5) ≈ 100 km², A(8.2) ≈ 20,000 km² (the report's quoted
      range), the inverse round-trips, and the shares sum to 1.

### Phase 2 — Marc et al. (2016)

- [ ] `landloss.hazard.landslide.calibration.marc_2016`: total area (eq. 12)
      and total volume (eq. 11) from moment magnitude, mean asperity depth R0,
      mechanism (reverse, strike-slip, normal), fault length (Leonard 2010, with
      the strike-slip form above the critical moment), modal slope S_mod and
      A_topo, with the Monte Carlo percentiles.
- [ ] `modal_slope_and_a_topo(dem, rupture)`: 30 m slope, modal slope per 1 km
      cell, A_topo as the share of the predicted landsliding that falls on cells
      with modal slope ≥ 8°.
- [x] **Obtain the supporting information.** Table S1 (the 40 events' moment,
      R0, mechanism, S_mod, A_topo and estimated A and V) is in
      `context/lit/landslide/marc_2016/` and packaged as
      `src/landloss/io/assets/marc-2016-table-s1.csv`, with a numeric version,
      one row per sub-event, in `marc-2016-table-s1-subevents.csv`.
- [ ] Reproduce the paper's predictions event by event from Table S1, the check
      that our implementation matches theirs. Nine of the events are in New
      Zealand, which also gives the Hancox work New Zealand points.
- [ ] Unit tests: the paper's reference case (thrust, R0 = 10 km, A_topo = 1,
      α_V = 0.05) against Figure 1b, and b saturating above M_h.

### Phase 3 — The calibration interface

- [ ] `landloss.hazard.landslide.calibration`, used by every large model:
  - `scale_to_total(coverage, cell_area, target_km2)` scales a coverage grid so
    its landslide area equals a target, capped at full coverage per cell.
  - `extent_mask(grid, source, mw)` zeroes cells beyond Hancox's area affected
    and maximum distances for the event, and below the intensity threshold.
  - `fit_transfer_function(relative_hazard, observed_coverage)` fits a monotone
    map from a relative hazard (models 2 and 7) to coverage by binning, as
    Nowicki Jessee did for their equation 9.
  - A report of what each constraint changed: total area before and after,
    and area removed by the extent mask.
- [ ] Unit tests: scaling preserves the pattern and hits the target; the mask
      removes only cells beyond the envelope.

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
- [ ] The first consumer: model 1 (Nowicki Jessee) run on Kaikōura, before and
      after calibration, which also closes the "overall scaling" modification
      in the rebuild note.
- [ ] Findings file beside the validation scripts
      (`src/scripts/landloss/hazard/landslide/validations/calibration/`).

### Phase 5 — Model 3 as a model

- [ ] `landloss.hazard.landslide.models.hancox_1997.model`: coverage over the
      study area as
  - zero where the study's MM is below MM7 (Wellington Region threshold),
  - zero outside the extent (under the forward scenario, nowhere in the study
    area),
  - elsewhere, a density per slope class proportional to Table 2's share
    divided by that class's share of the area, so that the landslides fall on
    slopes in the proportions Hancox observed,
  - scaled so the total matches the amount (phase 3).
- [ ] Slope at 10 m from the multiscale stack (`s3_multiscale_slope`), stated as
      a judgement: Hancox measured slope angles of individual failures, not of a
      coarse grid.
- [ ] Wellington forward step under `src/scripts/landloss/hazard/landslide/steps/`
      (next free number), with method and plan files, handing coverage to the
      realisation machinery above the size split.

### Phase 6 — Where the Wellington amount comes from

- [ ] Decide how the forward total is set, and record it in the rebuild note.
      Options, given the caution above:
  1. **The models' own shaking-driven totals, after calibration on events.** The
     scaling constants are fitted on Kaikōura and GFDB events against Marc and
     the observations, then applied with the study's 2500-year shaking.
     Preferred, because it keeps the shaking consistent with the rest of the
     study.
  2. **Marc's total for the scenario earthquake**, apportioned to the study
     area. It needs a rupture model, which the scenario lacks, and it inherits
     the shaking mismatch.
- [ ] The constants `BETA_SCENARIO_MW` and `BETA_SITE_DISTANCE_KM` in
      `landloss.domain.constants`, with a comment naming each term that reads
      them.

## Files

| File | Purpose |
|---|---|
| `src/landloss/hazard/landslide/models/hancox_1997/relationships.py` | Area affected, maximum distances, thresholds, slope-class shares |
| `src/landloss/hazard/landslide/models/hancox_1997/model.py` | Model 3 coverage |
| `src/landloss/hazard/landslide/calibration/__init__.py` | Scaling, extent mask, transfer function |
| `src/landloss/hazard/landslide/calibration/marc_2016.py` | Marc total area and volume, with uncertainty |
| `src/landloss/domain/constants.py` | `BETA_SCENARIO_MW`, `BETA_SITE_DISTANCE_KM` |
| `context/lit/landslide/hancox_1997/figures/*.csv` | Digitised Figure 19, 20.1 and 20.2 data |
| `src/scripts/landloss/hazard/landslide/validations/calibration/` | Kaikōura test of both constraints, findings |
| `src/scripts/landloss/hazard/landslide/steps/s<n>_hancox_1997/` | Wellington forward run |
| `tests/landloss/hazard/landslide/models/test_hancox_1997.py`, `tests/landloss/hazard/landslide/test_calibration.py` | Unit tests |

## Verification

- The digitised Figure 19 points refit to the published regression.
- Marc reproduces its own Table S1 predictions (once obtained).
- At Kaikōura: Marc's predicted total area against the GNS inventory's, and
  Hancox's A(7.8) against the observed extent, each reported as a ratio.
- Model 1 at Kaikōura before and after calibration.

## Risks and open items

- **Extent and amount are different things,** and Hancox is extent only. Kept
  distinct throughout.
- **Marc is calibrated on shallow continental earthquakes.** The subduction
  events it shows (Tohoku, Pisco) are for reference only. An Mw 8.1 at 25 km
  from Wellington may well be a Hikurangi interface rupture beneath the city
  rather than a crustal fault. Record which source the deaggregation mode is:
  if it is the interface, the scenario lies outside Marc's calibration, and
  outside Hancox's historical events too, whose large earthquakes are all
  crustal, 1855 Wairarapa (Mw 8.2) included.
- **Marc's shaking is not the study's shaking** (see the caution above), which
  is why option 1 in phase 6 is preferred.
- **Hancox (2010) Table 2 does not sum to 100%** as printed.
- **Digitising** Figures 19, 20.1 and 20.2 adds a small error; the Figure 19
  refit is its check.
- **Kaikōura's observed extent** depends on how the boundary is drawn around the
  inventory; draw it the way Hancox describes, and report the sensitivity.
- **GFDB** is read off `R:`, which Claude may not access; runs using it are made
  by the project lead.

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
