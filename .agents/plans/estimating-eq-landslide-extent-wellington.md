# Plan: estimating the spatial extent of earthquake-induced landslides, Wellington

## Context

NHC needs to know how much land damage a severe Wellington earthquake causes, and
what different policy settings would cost. Landslides are the dominant
uncertainty in that answer — `project-objectives.md` records that NHC's interest
in affordability "places a large share of the weight on how many landslides are
predicted, which is also one of the larger uncertainties in the work."

The model needs more than a count. NHC settles on **insured land** (in practice
the 8 m line from the dwelling), and `code-structure.md` separates *landslide
loss of support* from *landslide runout* because that distinction "decides whose
insured land the damage falls on". Answering the policy question therefore
requires landslide **footprints**, not just probabilities: where each failure
starts, how big it is, and where the debris ends up.

Register task **T-22** is the open decision this plan resolves — estimate extent
explicitly, or classify each property full/partial/nil. This plan takes the
explicit route, which was already the team's preferred direction and is the only
one that represents a landslide crossing several properties. Improvement **I-08**
(GNS's rules for distinguishing smaller and larger failures on the same slope) is
absorbed into it via an inventory-fitted size distribution, which achieves the
same end without depending on a model the team cannot obtain.

`src/landloss/hazard/` is currently empty scaffolding. This is its first content.

## Decisions and assumptions

| Decision | Choice | Basis |
|---|---|---|
| T-22 extent method | Explicit source + runout polygons | Preferred direction; required for loss-of-support vs runout split |
| Size distribution | Inventory-fitted, from Kaikōura V3 | NZ greywacke, 31,623 source polygons, public |
| Displacement method | Bray & Macedo (2019) crustal; Bray, Macedo & Travasarou (2018) subduction | Skill §4.4 |
| Rate calibration | Nowicki Jessee (2018) areal coverage, as an independent check | Constrains the dominant uncertainty |
| GWRC slope failure layer | Validation target, not an input | 1995 vintage; qualitative 1–5 zones, not a rate |

**Assumption to confirm:** the seismic demand is the TS1170.5 dataset already
chosen for the project. The VS site class is still open (**T-15**) — the plan
carries it as a parameter rather than blocking on it.

## The GWRC slope failure layer

Established while planning, and it changes how this layer is used.

It is **directly accessible over ArcGIS REST**, so no Koordinates access is
needed (it is not on T+T's instance — I checked):

```
https://services5.arcgis.com/n4qyP7iVOnJlCVth/arcgis/rest/services/WR_SlopeFailure/FeatureServer/0
```

Polygons in NZTM (EPSG:2193). Fields are `LSKEY` and `SEVERITY`, the latter a
five-level ordinal — `1 Low`, `2`, `3 Moderate`, `4`, `5 High`. Kingsbury (1995),
WRC/PP-T-95/06, five susceptibility zones from very low to very high.

Three things follow:

1. **It is a susceptibility zonation, not a rate.** It cannot tell us how much
   land fails, only where failure is more likely. It validates the *pattern* of
   the model; Nowicki Jessee `Ac` and the Kaikōura inventory constrain the
   *amount*.
2. **Its own basis matches this project's premise.** Kingsbury found slope angle
   and **modification** the most critical factors — the same conclusion as the
   team's view that losses sit on modified slopes. That supports the two-population
   approach in Risk 1 rather than contradicting it.
3. **It already excludes liquefaction-induced failures**, which lines up with the
   Zone 5 mask in Step 1 — the two treatments are consistent.

**Coverage caveat to check first.** The layer's data extent is E 1,741,479–
1,794,980, N 5,421,003–5,492,421. The study area runs E 1,735,093–1,794,002,
N 5,410,973–5,464,683. So the layer appears not to reach ~6 km of the study
area's western edge (Porirua/Titahi Bay) or ~10 km of its southern edge
(Wellington's south coast) — while extending well north into Kapiti, which is out
of scope. Coastal escarpment was something NHC explicitly asked to include, so
confirm the real coverage before relying on this layer to validate those areas.

## Approach

### Step 1 — Terrain and demand grids

Build the per-cell inputs over the hill country of the four territorial
authorities.

- **Add a raster reader.** `io/readers.py` is vector-only today. Add
  `load_koordinates_raster_extent`, mirroring `get_koordinates_layer_extent`
  exactly (int layer ID vs `Path`, bbox, CRS, same caching decision). Use
  `ttpy.gis.raster.io.load_raster`, as the hurunui project does at
  `p-1099456-hurunui-high-level-geotech/src/hgeo/io/readers.py`.
- **Terrain derivatives** from the LINZ DEM: slope, plan/profile curvature,
  relative relief, and D8 flow direction (needed to route runout in Step 4).
  Curvature matters specifically here — coseismic failures favour **convex**
  ridge crests and spurs, close to the reverse of the rainfall pattern
  (Meunier et al. 2008, skill §1).
- **Mask to hill country.** Exclude GWRC Zone 5 soft sediment; the skill is
  explicit that there "liquefaction/lateral spreading governs, not classic slope
  stability — keep it out of the hill-country susceptibility layer". Without this
  the model will invent landslides in Petone and Te Aro.
- **Topographic amplification** on the PGA input: ~1.3× moderately steep, ~1.5×
  for slopes >60° (skill §4.4).

Carries limitation **L-12**: the DEM is a merge of survey years (Wellington 2023,
Hutt 2025), so derived slope is not of uniform vintage.

### Step 2 — Failure probability per cell

- Yield acceleration `ky` from an infinite-slope static factor of safety, with
  c′, φ′, unit weight and failure depth assigned per geological unit.
- Newmark displacement `D` from `ky` and the amplified demand, splitting by source
  mechanism — crustal faults (Wellington, Ohariu/Pukerua/Moonshine) via Bray &
  Macedo (2019); Hikurangi subduction via BMT (2018). Do not use one regression
  for both.
- `D` → probability of failure per cell.
- **Calibrate the absolute rate** against Nowicki Jessee (2018) areal coverage
  `Ac` for the same shaking. This is the step that most needs an independent
  check, because total landslide area drives the loss answer.

### Step 3 — Discrete landslide realisation (the core)

This converts a probability surface into individual landslides, which is what
makes per-property attribution possible.

1. Expected total source area for the event = Σ (P_failure × cell area),
   reconciled against the `Ac` estimate from Step 2.
2. Sample individual source areas from a size distribution fitted to the
   **Kaikōura V3 inventory** (DesignSafe PRJ-5827; 31,623 source polygons),
   filtered to greywacke — 70.4% of Kaikōura landslides were in Pahau terrane
   greywacke, the same Torlesse rock as Wellington's hills. Use a truncated
   power law / three-parameter inverse gamma; Massey et al. (2020) report
   α ≈ 2.10 with x_min ≈ 500 m².
3. Seed sources at cells drawn with probability ∝ P_failure, and grow each to its
   sampled area across the slope facet (connected cells of similar aspect).
4. Stop when the sampled areas sum to the target total.

The size distribution is what delivers **I-08** — "smaller and larger failures on
the same slope" — without needing GNS's proprietary rules.

### Step 4 — Runout footprint

- Convert source area to volume via `V = αA^γ`; Massey et al. (2020) give
  γ ≈ 1.46–1.47 for rotational/translational/compound slides, with debris
  avalanches shallower.
- Sample a reach angle (H/L, Fahrböschung) from the Kaikōura debris-trail data
  (26,559 trail polygons), conditioned on volume.
- Route debris down the steepest-descent path from the source toe until the H/L
  budget is exhausted; widen laterally as a function of volume.
- Emit **two polygon sets per realisation, kept separate**: source (loss of
  support) and debris trail (runout). `vul` needs a damage ratio per cause, and
  the two are settled differently.

### Step 5 — Per-property intersection and Monte Carlo

- Intersect each realisation with insured land per property (8 m line).
- Repeat N times → a distribution of affected area per property per cause, rather
  than a single expected value.
- Spatial correlation between retaining-wall height and landslide probability
  (flagged in `project-scope.md` Phase 3) falls out naturally, because each
  realisation is a physically coherent event.

## Files

**New library code** (`src/landloss/hazard/`, Google-style docstrings, fully
typed — ruff runs `select = ["ALL"]` here):

- `terrain.py` — slope, curvature, relief, flow direction; hill-country mask.
- `demand.py` — TS1170.5 demand, site class, topographic amplification.
- `newmark.py` — `ky` from static FoS; Bray & Macedo (2019) and BMT (2018).
- `susceptibility.py` — displacement → P(failure); `Ac` cross-check.
- `landslide_extent.py` — size distribution, seeding, source polygons.
- `runout.py` — volume from area, reach angle sampling, debris routing.

**Changed:**

- `src/landloss/io/readers.py` — add `load_koordinates_raster_extent`.
- `src/landloss/domain/constants.py` — layer IDs for the DEM, geology and Zone 5
  sediment, plus the GWRC slope failure FeatureServer URL, beside the existing
  `NZ_ADDRESSES_LAYER_ID` / `TERRITORIAL_AUTHORITY_LAYER_ID`.
- `src/landloss/io/readers.py` — a small `load_arcgis_feature_layer` for the GWRC
  service. It is an ArcGIS REST endpoint rather than Koordinates, so
  `get_koordinates_layer_extent` does not cover it; `geopandas.read_file` reads
  the query endpoint directly.

**New one-off:** `src/landloss/io/one_offs/gen_landslide_stats.py` — fit the size
and reach-angle distributions from the Kaikōura inventory once, and commit the
fitted parameters as a small packaged asset. Follow `gen_study_extent.py`
exactly: `argparse`, validate before writing, commit the derived asset so nobody
needs the 31k-polygon inventory day to day.

**New run scripts:** `src/scripts/landloss/hazard/landslide/steps/` (01 terrain,
02 demand, 03 displacement, 04 sources, 05 runout, 06 per-property) and
`src/scripts/landloss/hazard/landslide/validations/` (below).

**Reuse rather than rewrite:**

- `get_koordinates_layer_extent`, `resolve_api_key` — `src/landloss/io/readers.py`
- `get_study_areas`, `study_area_bbox`, `SMALL_WLG_PILOT` —
  `src/landloss/io/area_of_interest.py`. Develop against `SMALL_WLG_PILOT`
  (4.7 km²) before running the full 59 × 54 km extent.
- The one-off + committed-asset pattern — `src/landloss/io/one_offs/gen_study_extent.py`

## Verification

**Unit tests** (`tests/landloss/hazard/`, mirroring the source tree, behavioural
names with a one-line "why" docstring, no network — follow
`tests/landloss/io/test_readers.py`):

- A known slope, `ky` and demand reproduce a published Bray & Macedo worked value.
- Sampled source areas reproduce the fitted power-law exponent within tolerance.
- A landslide on a planar slope runs out to the distance its reach angle implies.
- Source and runout polygons are returned separately and never merged.
- No landslide is generated inside the Zone 5 mask.

**Validations** (`src/scripts/landloss/hazard/landslide/validations/` — checks on outputs,
not unit tests):

- Landslide density against the **GWRC `SEVERITY` 1–5 zonation**: simulated
  density should rise monotonically from zone 1 to zone 5. This is a rank
  correlation check, not an absolute one, because the layer is a susceptibility
  zonation rather than a rate.
- Total areal coverage against Nowicki Jessee (2018) `Ac`.
- Simulated size distribution and reach angles against the Kaikōura inventory.
- **Proportion of landslides confined to a single property.** Local expectation
  (`land-damage-mechanisms.md`) is that most earthquake-induced landslides will be
  confined to one property, with multi-property failures concentrated in gullies.
  If the model does not reproduce that, it is wrong regardless of how well it
  matches the literature.

**End to end:** run the six steps over `SMALL_WLG_PILOT`, then intersect with
`get_nz_addresses` output for the same extent and confirm every property receives
an affected-area distribution per cause. Then `uv run --frozen pytest` and
`uv run --frozen prek -a`.

## Risks and open items

1. **Kaikōura is a rural analogue for an urban problem.** Its inventory is
   natural slopes in the Kaikōura ranges. Wellington's losses are expected on
   *modified* slopes — cuts behind houses, fill behind retaining walls
   (`land-damage-mechanisms.md`). A size distribution fitted to Kaikōura will
   under-represent the small, engineered failures that drive claims. Mitigation:
   model modified-slope failures as a **second population**, conditioned on the
   cut-and-fill and retaining-wall data (**T-09**, **T-11**, **T-19**, **T-20**),
   and state the split in the report. This is the biggest technical risk here.
2. **The GWRC layer may not cover the south coast or western Porirua** — see the
   coverage caveat above. Check before relying on it there.
3. **The 1995 scanned map booklets have not been read in full.** The Hutt Valley
   PDF is a scanned image with no text layer and no renderer available here; the
   Wellington OCR version exceeds the fetch size limit. The classification
   scheme and Kingsbury's criteria above come from the layer schema and secondary
   sources, so confirm the exact zone definitions against the booklets
   (`gw.govt.nz/document/189/`) before quoting them in the report.
4. **L-08 stands**: the GNS/PRUE model is a cross-comparison only, not an input.
5. Rain-induced failure after shaking, aftershocks and fault rupture remain out
   of scope per `project-scope.md`.

## Sources

Method and regional context come from the `seismic-landslide-hazard-wellington`
skill in this repository. Beyond it:

- GWRC slope failure layer (ArcGIS REST, fields and `SEVERITY` domain read
  directly from the service):
  <https://services5.arcgis.com/n4qyP7iVOnJlCVth/arcgis/rest/services/WR_SlopeFailure/FeatureServer/0>
- Kingsbury (1995), *Earthquake induced slope failure hazard*, WRC/PP-T-95/06 —
  map booklets at <https://www.gw.govt.nz/document/189/earthquake-induced-slope-failure-hazard-study-maps-and-booklets/>
- Massey et al. (2020), volume characteristics of Kaikōura landslides:
  <https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2019JF005163>
- Kaikōura landslide inventory v3.0 (source and debris-trail polygons):
  <https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/PRJ-5827>
- Nowicki Jessee et al. (2018), global coseismic landslide model and areal
  coverage: <https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2017JF004494>
- Malamud et al. (2004), landslide inventories and their statistical properties:
  <https://onlinelibrary.wiley.com/doi/10.1002/esp.1064>
- Modelling earthquake-induced landslide impacts on infrastructure systems in
  Wellington (NZGS): <https://www.nzgs.org/libraries/modelling-earthquake-induced-landslide-impacts-on-infrastructure-systems-in-wellington/>

Written 2026-09-17. Not yet reviewed or agreed with the project team.
