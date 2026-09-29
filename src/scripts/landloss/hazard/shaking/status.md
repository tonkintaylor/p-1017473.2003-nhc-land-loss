# Shaking hazard: status

**Status:** A PGA field per realisation runs, off the NLM grid. Coarse: one
cell covers the whole pilot box.

**Updated:** 2026-09-29

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

Intended, not implemented.

- [>] Port the National Liquefaction Model (NLM) code for the TS1170.5 PGA
  demands — `gen_pga_layer` from `p-1017473-nlm-loss-modelling` — rather than
  rewriting it, so both studies compute their demand the same way.
- [ ] Take the site class from the **Foster et al. (2019) V<sub>s</sub>30 model**
  instead of a single assumed class. This resolves **T-15** by mapping the
  class per point rather than assigning one per landform.
- [ ] Generate **PGA** and **Sa(T₁)** across the study extent on a **100 m grid**,
  both at the **2500-year return period**.
- [ ] Derive **PGV** from the same TS1170.5 spectrum rather than generating it
  independently, as **PGV (mm/s) ≈ 750 · Sa(1.0 s) [g]**. Several of the
  retaining wall fragility curves in
  `.agents/context/retaining-wall-fragility.md` are velocity-based.
**Parked.** NSHM (2022) scenario demands run through a GMPE in OpenQuake were
held as the alternative to TS1170.5. That route is parked: the demand comes from
TS1170.5. It would produce the same PGA and PGV layers from the same
V<sub>s</sub>30 input, so it stays reinstatable if the decision is revisited.


## Beta build

A first end-to-end run is being assembled that produces the right data
structures rather than the right numbers; see
`.agents/plans/beta-build.md` for the whole chain.

The shaking beta reads the **NLM TS1170.5 PGA raster directly**: no Vs30, no
site class, and no port of `gen_pga_layer`. Realisations come from a **10%
coefficient of variation** on PGA. **PGV is not produced** — it may be dropped
from the study, so nothing downstream should depend on it yet.

The output structure is a raster of PGA in g, one per realisation.

## Where it is now

`steps/s1_pga_realisation/` writes one PGA field per realisation: the NLM's
2500-year site class 5 grid, clipped to the extent and scaled by one lognormal
draw against a 10% coefficient of variation, seeded from the project realisation
stream.

**The grid is national and about 9,930 m across a cell** — 149 by 114 cells over
New Zealand, PGA 0.35 to 1.3 g, median 0.59, with Wellington's cell at 1.0 g.
Over the four territorial authorities that is roughly 6 by 5 cells; over the
pilot box it is a **single cell**. So every property in the pilot reads the same
PGA, and because the realisation multiplier is shared across the field, every
asset in a realisation shakes identically. Variation between assets has to come
from the fragility draw, not from the shaking.

PGV is not produced as a layer yet, but the pieces exist:
`landloss.io.nlm` reads the NLM's 2500-year PGA and Sa(1.0 s) grids at any of
site classes 1-7 (`get_nlm_scenario_pga_2500yr`, `get_nlm_scenario_sa_t1_2500yr`),
and `landloss.hazard.shaking.pgv` converts Sa(1.0 s) to PGV. Where no site class
is otherwise set, `constants.BETA_SITE_CLASS` (site class 2) is read. The
shaking step itself still reads site class 5 PGA.

Nothing is implemented here. The folder holds this file and `__init__.py`, and
no script in the repository reads TS1170.5, V<sub>s</sub>30 or the National
Seismic Hazard Model.

The TS1170.5 demand itself is built and proven as a raster in the National
Liquefaction Model repository (`p-1017473-nlm-loss-modelling`). Porting it is
the outstanding work, not writing it.

## Next

1. Obtain the Foster et al. (2019) V<sub>s</sub>30 layer over the study area.
   After the beta, the site class comes per location from it, replacing
   `BETA_SITE_CLASS` (site class 2) wherever that is read.
2. Port the NLM code for the TS1170.5 PGA demands into a step under `steps/`,
   and confirm it reproduces the NLM's own output before modifying it.
3. Generate the 100 m grid of PGA and Sa(T₁) over the study area, taking the
   site class from the Foster layer rather than a single assumed class.
4. Add the Sa(1.0 s) → PGV conversion and write the PGV layer.

## Validation

- Mean PGA per site class against the NSHM values for that class — the check
  that the Foster classes are paired with the right demand. A script under
  `validations/`, not a unit test.

## Open decisions

- **T-15** — the site class decision above. Adopting Foster closes it.
- **T-26** is no longer open: the demand comes from TS1170.5 and the NSHM
  scenario route is parked. The register entry still reads as undecided and
  needs updating.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
