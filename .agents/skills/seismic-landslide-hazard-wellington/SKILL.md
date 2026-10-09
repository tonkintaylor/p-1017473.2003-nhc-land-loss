---
name: seismic-landslide-hazard-wellington
description: Use whenever assessing or modelling earthquake-induced (coseismic) landslide hazard — comparing it against rainfall-induced landslides, adapting or correcting a rainfall-calibrated landslide susceptibility model for seismic triggering, running Newmark sliding-block or seismic slope displacement analysis, or doing geospatial landslide hazard work anywhere in the Wellington region (Wellington City, Lower Hutt, Upper Hutt, Porirua). Also trigger on "very strong earthquake" scenarios, NZ Modified Mercalli intensity terminology, Wellington Fault / Ohariu-Pukerua-Moonshine / Hikurangi subduction zone scenarios, seismic cut-and-fill design, or Tonkin + Taylor's internal Newmark / seismic-demand Knowledge Shots (KS 737, KS 741) — even if the user doesn't say "landslide" or "seismic" explicitly.
---

# Seismic (earthquake-induced) landslide hazard

Distilled from a geotechnical/engineering-geology discussion covering the general earthquake-vs-rainfall landslide framework, then a Wellington-region (Wellington City, Lower Hutt, Upper Hutt, Porirua) geospatial application for a "very strong earthquake" scenario.

## 1. Earthquake- vs rainfall-induced landslides

| | Rainfall-induced | Earthquake-induced |
|---|---|---|
| Trigger | Infiltration raises pore pressure / cuts suction over hours–days | Instant inertial loading; liquefaction in saturated sand/silt |
| Depth | Shallow, usually <1–3 m (wetting front) | Wide range: shallow disrupted slides to deep-seated rock-mass failure |
| Topography | **Concave** — hollows, valley heads, drainage lines (flow converges) | **Convex** — ridge crests, spurs (seismic waves amplify there); a near-reversal of the rainfall pattern (Meunier, Hovius & Haines 2008) |
| Geology | Weathered mantle over a permeability break; residual/pyroclastic soils | Jointed/sheared rock, fault-proximal zones, loose saturated sediment |
| Size/frequency | Many small–moderate slips per storm | Fewer events, but includes the largest failures (rock avalanches); scales with magnitude and source distance |

Geology overlaps more than topography does: genuinely weak/weathered/sheared material is susceptible to both triggers, but for different reasons (permeability contrast vs joint/rock-mass degradation) — a given geological unit can still be one-trigger-dominant.

## 2. Adapting a rainfall-calibrated model for seismic use

Don't drop a seismic-intensity term into a rainfall-calibrated equation — the failure mechanism has a different shape.

- **Keep**: static geotechnical parameters (depth to failure surface, effective c′/φ′, unit weight) — both approaches need these for a static factor of safety.
- **Replace the trigger term**: swap the infiltration/pore-pressure time series for a **Newmark sliding-block analysis** — critical (yield) acceleration from the static FoS, run against PGA/PGV/spectral acceleration (see §4.4 for currently recommended methods).
- **Re-weight terrain proxies** if the model is statistical: contributing area / TWI / distance-to-stream are rainfall-specific and bias toward valleys. Add ridge-top curvature, relative relief, rock-mass quality, distance-to-fault, and a ground-motion (PGA/PGV) grid.
- **Better than retrofitting**: start from a seismic-specific base model (e.g. USGS's global coseismic-landslide logistic regression, or a Newmark-based method) and use the rainfall inventory only to calibrate static strength/depth inputs.
- **Mind the coupling**: wet antecedent conditions lower the critical acceleration (compound hazard is worse than either alone); shaking itself elevates rainfall-triggered susceptibility for several subsequent wet seasons as loosened material gets mobilised.

## 3. Cut and fill implications

The governing case differs by location as well as trigger — check long-term drained, rainfall/infiltration transient, **and** seismic pseudo-static/Newmark cases separately rather than assuming one bounds the others.

- **Cuts**: rainfall design leans on drainage (crest cut-offs, subsoil drains, benching, drained long-term strength). Seismic design leans on dynamic stability — flatter batters/reinforcement where the cut sits on a ridge/convex break (amplification), plus joint-controlled block/rockfall checks rainfall analysis wouldn't flag.
- **Fill**: rainfall design leans on internal drainage blankets and surface shedding. Seismic design leans on compaction density (avoiding fill densification/liquefaction), ductile reinforcement (geogrid), and the fill–foundation contact on sloping ground.
- **Location dictates which governs**: earthworks in valley/drainage positions tend to be rainfall/groundwater-governed; earthworks near ridgelines tend to be seismic/amplification-governed. State this explicitly per cut/fill location rather than one FoS target site-wide.
- **Maintenance vs one-off**: rainfall performance depends on drains staying functional for the asset's life; seismic performance is a rare-event, displacement-acceptance check rather than something maintained against.

## 4. Wellington region module (Wellington City / Lower Hutt / Upper Hutt / Porirua)

### 4.1 "Very strong" is a specific rung — pin it down before modelling

On the ShakeMap / Worden et al. (2012) scale, **"very strong" = MMI VII ≈ 0.15–0.25g PGA (≈20 cm/s PGV)**. This is *short of* the regional "big one": a direct Wellington Fault rupture reaches MM VIII–XI region-wide (0.5–0.8g) — severe/extreme, not "very strong". GeoNet's own public NZ scale skips the term entirely (weak→light→moderate→strong→severe→extreme, with "severe" assigned to MM7) — confirm which convention the deliverable's audience expects before quoting a level.

A genuine "very strong" event for these four areas is one of:
1. The outer/attenuated part of a proximal rupture (Wellington Fault; or Porirua's Ohariu/Pukerua/Moonshine set) — a few km off-trace, or firm/bedrock sites near a rupture that's already "severe+" on soft ground nearby.
2. A regionally distributed but non-maximum event (GWRC's own "Scenario 1": M~7 at ~100 km gives MM V–VI on bedrock, MM VIII–IX on soft sediment; MM7+ on bedrock has roughly an 80-year return period).
3. A **Hikurangi subduction** event (credible planning scenario M8.9) — "severe to extreme" for the Wellington region generally, but delivered over **minutes rather than seconds**, with MMI7+ sustained across most of the North Island. This is the scenario most likely to put a large, contiguous "very strong" footprint over all four areas at once, rather than a fault-proximal hot spot.

### 4.2 Geology and topography

All four areas sit on Torlesse Supergroup "greywacke" (jointed sandstone/argillite) hill country — Wellington's town-belt/south-coast hills, the Western Hutt Hills, Porirua's Aotea/Whitby/Titahi Bay hills, Upper Hutt's Akatarawa/Remutaka margins.

- **Valley/basin soft sediment** — Te Aro and the harbour-margin reclamation, Petone–Alicetown–Melling–Naenae in the Hutt Valley, the Porirua Basin — is mapped by GWRC as "Zone 5" (>10 m soft/loose material, 5–20× amplification vs bedrock). This is where "very strong" gets reached even from a modest/distant trigger, and where **liquefaction/lateral spreading governs, not classic slope stability** — keep it out of the hill-country susceptibility layer.
- **Porirua's hill soils** are loess-mantled and highly erodible once vegetation cover is disturbed — weight susceptibility accordingly and plan faster revegetation windows on cuts there.
- Upper Hutt: same fault-bounded valley system and greywacke hill country, but pull GWRC's Upper Hutt sheet directly rather than assuming it mirrors Lower Hutt's zone boundaries.

### 4.3 Fault / source inventory

| Source | Type | Magnitude | Notes |
|---|---|---|---|
| Wellington Fault (Wellington–Hutt Valley segment) | Shallow crustal, dextral strike-slip | M7.5 | Runs through Wellington CBD and the Hutt Valley; ~600-yr return period; up to 5 m horizontal / 1 m vertical surface displacement |
| Ohariu / Pukerua / Moonshine faults | Shallow crustal | M7.2–7.7 combined | Ohariu runs beneath Porirua CBD; 800–7,000-yr recurrence; recently re-mapped with LiDAR (Porirua Fault Trace Study) |
| Hikurangi subduction zone | Subduction interface/intraslab | Credible planning scenario M8.9 | Offshore; widest, longest-duration shaking footprint of the three; also a tsunami source |

### 4.4 Correction methodology specific to this region

- **Ground motion input**: prefer **NSHM 2022** spectral acceleration over NZS1170.5 (now outdated for NZ seismicity). If the project already has a TS1170.5 seismic-demand dataset, that's the direct input.
- **Displacement method — split by source mechanism** (don't use one regression for both):
  - Shallow crustal (Wellington Fault, Ohariu/Pukerua/Moonshine): **Bray & Macedo (2019)**.
  - Subduction interface/intraslab (Hikurangi): **Bray, Macedo & Travasarou (2018)** / the BM23 subduction variant.
  - Jibson (2007) is regional-screening/preliminary only — not for site-specific design.
  - Where a site's hazard is a mix of both mechanisms, check which dominates before picking a method (T+T: consult the Earthquake Engineering GeoCOTE — see §4.6).
- **Topographic correction** (rainfall models don't need this): apply an amplification factor to the rigid-block PGA input — **~1.3× for moderately steep slopes, ~1.5× for slopes >60°** (Rathje & Bray 2001; Ashford & Sitar 2002) — at ridge crests and convex breaks.

### 4.5 Datasets to pull rather than rebuild

- GWRC / Koordinates: **"Wellington Region Earthquake Induced Slope Failure"** — existing susceptibility layer from the WRC slope-failure-series coverages (Publication WRC/PP-T-95/06). Use as a starting zonation to validate/update, not derive from scratch.
- GWRC **Combined Earthquake Hazard maps** (ground shaking, liquefaction, slope failure, fault rupture combined; Wellington, Porirua, Hutt Valley, Kapiti).
- GWRC **Ground Shaking Hazard map series** (1992, sheets 1–5: Wellington, Porirua/Tawa, Lower Hutt, Upper Hutt, Kapiti) — dated but still the most granular geology-tied Zone 1–5 amplification mapping available; cross-check against modern NSHM2022 Vs30/site class.
- **Porirua Fault Trace Study** — LiDAR re-mapping of the Ohariu/Pukerua/Moonshine traces; better than 1990s trace work for near-fault buffers in Porirua.
- **Calibration data point**: the 2016 Kaikōura earthquake — a distant-but-large trigger that still caused significant liquefaction/lateral spreading at CentrePort, Wellington (soft-sediment amplification behaviour matching GWRC's "Scenario 1" pattern above).

### 4.6 Internal Tonkin + Taylor references

- **KS 737** — "Derivation of earthquake loading parameters for design including TS 1170.5" — PGA/response-spectra derivation methodology (NZS1170.5, NZGS/MBIE 2021, AS/NZS TS1170.5:2025).
- **KS 741** — "Seismic Slope Displacement – Newmark Block Analysis and Dynamic Stress Deformation Analysis" — the firm's Newmark spreadsheet (NSHM2022-enabled), source-mechanism guidance, topographic amplification factors, and dynamic stress-deformation analysis guidance for higher-risk/importance projects or where liquefaction is present.
- For fault-mechanism-contribution questions on a specific site: **EQEngGeoCoTEAdmin@tonkintaylor.co.nz**.
- Related KS worth a look: Seismic Slope Stability; Liquefaction – Lateral Spreading; Site Subsoil Class NZS1170.5:2004; Selection of Subsoil Class for Liquefiable Sites.

## 5. Key references

- Meunier, Hovius & Haines (2008) — topographic control on coseismic landslide distribution.
- Bray & Macedo (2019) — shallow crustal seismic slope displacement.
- Bray, Macedo & Travasarou (2018) — subduction zone seismic slope displacement.
- Jibson (2007) — regional coseismic landslide displacement regression (screening only).
- Rathje & Bray (2001); Ashford & Sitar (2002) — topographic amplification factors for rigid-block PGA input.
- GWRC Seismic Hazard Map Series: Ground Shaking Hazard (1992) — Wellington, Porirua/Tawa, Lower Hutt, Upper Hutt, Kapiti.
- GWRC Combined Earthquake Hazard maps; Publication WRC/PP-T-95/06 (earthquake-induced slope failure).
- GNS Science / East Coast LAB — Hikurangi Subduction Zone M8.9 credible planning scenario.
- USGS ShakeMap instrumental intensity scale (Worden et al. 2012).
