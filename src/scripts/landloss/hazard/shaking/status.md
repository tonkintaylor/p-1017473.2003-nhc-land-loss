# Shaking hazard: status

**Status:** A PGA field per realisation runs, off the NLM grid. Coarse: one
cell covers the whole pilot box. A PGV field per realisation, scaled by the
same factor, is built (step 5) and tested on synthetic inputs, and has not yet
been run over the pilot.

**Updated:** 2026-10-06

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Take the TS1170.5 PGA demand from the Table 3.2 grids
  `static_data_gen/gen_ts1170_grids.py` builds the way the National
  Liquefaction Model (NLM) built its own, reproducing its 2500-year site
  class 5 grid cell for cell, so both studies compute their demand the same way.
- [x] Take the site class from the **Foster et al. (2019) V<sub>s</sub>30 model**
  instead of a single assumed class. This resolves **T-15** by mapping the
  class per point rather than assigning one per landform.
- [x] Generate **PGA** and **Sa(T₁)** across the study extent on a **100 m grid**,
  both at the **2500-year return period**.
- [x] Derive **PGV** from the same TS1170.5 spectrum rather than generating it
  independently, as **PGV (mm/s) ≈ 750 · Sa(1.0 s) [g]**. Several of the
  retaining wall fragility curves in
  `.agents/context/retaining-wall-fragility.md` are velocity-based.
- [x] Scale PGV per realisation by the factor PGA takes, so one modelled
  earthquake's two measures agree.
- [ ] Replace the flat 10% coefficient of variation and the one field-wide
  multiplier with the ground motion model's own sigma and a spatially
  correlated field, PGA and PGV each with their own dispersion.
**Parked.** NSHM (2022) scenario demands run through a GMPE in OpenQuake were
held as the alternative to TS1170.5. That route is parked: the demand comes from
TS1170.5. It would produce the same PGA and PGV layers from the same
V<sub>s</sub>30 input, so it stays reinstatable if the decision is revisited.


## Beta build

A first end-to-end run is being assembled that produces the right data
structures rather than the right numbers; see
`.agents/plans/beta-build.md` for the whole chain.

The shaking beta first read the **NLM's site class 5 PGA raster directly**
(`s1_pga_realisation`, retired 2026-09-30). Steps 2 to 5 replace it: a site
class per cell, PGA and PGV demand per cell, and one realisation of each from a
**10% coefficient of variation** shared between the two measures.

The output structure is a raster of PGA in g and a raster of PGV in m/s, one
of each per realisation.

## Where it is now

`steps/s2_site_class/` writes a TS1170.5 site class per 100 m cell over the
extent, from the Foster et al. (2019) V<sub>s</sub>30 model on that model's own
grid; cells Foster leaves empty along the harbour edge take the class of the
nearest classed cell within 200 m, and any still unclassed take a default
V<sub>s</sub>30 for their majority material on ground step 2's ground map
(uncontrolled fill 200 m/s, Class VI; `BETA_GROUND_MAP_DEFAULT_VS30_M_S`, the
whole table confirmed by the lead on 2026-10-06), so
ground step 2 now runs first. Over the pilot every urban slope polygon now
has a site class: 8 harbour-edge cells on reclaimed fill took the fill default.
A source raster records which cells came from where. The profile criteria of
TS1170.5 Table 3.3 are not applied (**L-38**).

`steps/s3_pgv/` writes Sa(1.0 s) and PGV per cell, the TS1170.5 Table 3.2
demand of each cell's site class at 2500 years, with PGV (mm/s) =
750 × Sa(1.0 s) (g). `steps/s4_pga_realisation/` writes one PGA field per
realisation the same way, scaled by one lognormal draw against a 10%
coefficient of variation, seeded from the project realisation stream.
`gen_hazard.main` runs shaking steps 2 to 5 in order.

**The demand grids are about 9,930 m across a cell**, so within one demand cell
PGA and PGV change only where the site class does, and the realisation
multiplier is one number over the whole field. Variation between assets within
a realisation still comes mostly from the fragility draw, not from the shaking.

`steps/s5_pgv_realisation/` writes one PGV field per realisation: the PGV grid
step 3 wrote, scaled by the same lognormal factor step 4 puts on PGA for that
realisation id, recomputed from the same seed, so one modelled earthquake's PGA
and PGV agree. Output `temp/hazard/shaking/pgv-rNNN[-pilot].tif`; a unit test
holds the two steps' factors together. Two steps read it through `pgv_path`:
landslide step 6 (`s6_urban_slope_realisation`) and vul shaking rw step 9
(`s9_wall_damage_state`), the urban slope realisation and the flat-land wall
damage state of `.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`.
Step 5 is tested end to end on synthetic inputs and has not yet been run over
the pilot: `temp/hazard/shaking/` holds no `pgv-rNNN` raster.

`steps/s1_pga_realisation/`, which read the NLM's site class 5 PGA grid
directly, was retired on 2026-09-30; its method file records how it ran.

## Next

1. Run step 5 over the pilot (`gen_hazard.main` now runs it after step 4).
2. Replace the flat 10% coefficient of variation with the ground motion
   model's own sigma, PGA and PGV each taking their own (step 4's plan, phase
   4; step 5's plan, phase 2).
3. Replace the single field-wide multiplier with a spatially correlated random
   field, written by step 4 and read by step 5 rather than recomputed from the
   seed.

## Validation

- Mean PGA per site class against the NSHM values for that class — the check
  that the Foster classes are paired with the right demand. A script under
  `validations/`, not a unit test.

## Open decisions

- **T-15** — the site class decision above. Step 2 adopts Foster, which closes
  it; the register entry still reads as open and needs updating.
- **T-26** is closed (the lead, 2026-10-02): the TS1170.5 2,500-year demands
  as the standard gives them, per site class, and the NSHM scenario route is
  parked. Over the pilot that is 1.68 to 1.77 g on site classes II and III,
  larger than the roughly 1 g the scope was written around.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
