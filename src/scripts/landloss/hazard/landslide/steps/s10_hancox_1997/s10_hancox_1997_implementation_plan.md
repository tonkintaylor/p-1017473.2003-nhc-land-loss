# Step 10 — Hancox (1997) coverage: implementation plan

**Status:** The forward model and pipeline wiring are built and unit tested; a
pilot run and the event validations remain open.

## Phase 1 — Build model 3 (complete)

- [x] Convert each shaking realisation's PGV to Modified Mercalli intensity
      with the PGV-only Worden et al. (2012) relation.
- [x] Apply Hancox et al.'s MM7 Wellington threshold and maximum epicentral
      distance at the beta Mw 8.1, 25 km scenario.
- [x] Weight the 10 m slope cells so failed area follows Hancox (2010) Table
      2's slope-class shares.
- [x] Exclude the step 4 NLM flatland before the amount is apportioned, so
      step 1's no-large-source-on-flatland rule does not reduce the Marc total.
- [x] Take the event-wide amount from Marc et al. (2016), apportion it by the
      modelled share of Hancox's area affected, and cap coverage at one.
- [x] Write one 10 m coverage raster per shaking realisation and hand it to
      step 1's large-landslide placement.

## Phase 2 — Run Wellington

- [ ] Run the step and step 1 over `wlg-pilot`, inspect the printed total and
      slope-class distribution, and draw the step 1 validation figure.
- [ ] Run the four territorial authorities after the pilot checks pass.

The run uses the existing TS1170.5 return-period PGV realisations. No new
shaking layer or replacement of that demand is part of this phase.

## Phase 3 — Refine Marc's amount inputs and validate

- [ ] Replace the central sensitivity in `config.py` with asperity depths and
      onshore fractions from the NSHM 2022 Hikurangi interface geometry. This
      changes only Marc's event-wide amount; the Hancox MM threshold continues
      to use the TS1170.5-derived PGV.
- [ ] Report the present `R0 = 22.5 km`, all-onshore result as a sensitivity,
      not as a calibrated interface prediction.
- [ ] Run the Hancox extent and Marc amount tests on Kaikōura, then the
      available subduction inventories, as set out in
      `.agents/plans/building-hancox-landslide-model-and-calibration.md`.

## Potential future improvements

- Carry a spatial source distance field when the study adopts a rupture model.
- Replace the single central Marc interface sensitivity with the plan's
  geometry, ground-motion and duration sensitivities.
