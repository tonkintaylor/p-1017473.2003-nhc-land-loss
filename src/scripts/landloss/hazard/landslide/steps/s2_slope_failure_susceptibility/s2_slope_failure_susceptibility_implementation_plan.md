# Step 2 — Slope failure susceptibility: implementation plan

**Status:** Phase 1 and Phase 2 complete. The step runs over the Johnsonville
and Newlands pilot and writes a rating and a zone raster.

## Background

Greater Wellington's earthquake-induced slope failure layer is published
CC BY-ND, so nothing may be derived from it. This step rebuilds the scheme
behind it — Kingsbury (1995), WRC/PP-T-95/06 to /10 — from its own inputs, so
that the result is ours to use. The full method extraction, the licence
position, and what is and is not obtainable are in
`.agents/plans/rebuilding-gwrc-slope-failure-susceptibility.md`. Read that
before changing anything here.

Three scope decisions made on 23 September 2026 shape what is built:

1. **Residential land only.** Quarries, state highway and rail corridor cuts are
   out. Suburban subdivision earthworks are in, which is what the Wellington
   City Council layers hold.
2. **The geology factor is not mapped in detail.** Weathering state and
   crushed/shattered mapping are not chased. Geology and groundwater are instead
   read from the National Liquefaction Model, which is coarse but separates
   bedrock hill country from unconsolidated deposits and flat land with a
   shallow water table from hillside that drains — which is as much as the
   factors' weightings of 2 and 1 can justify.
3. **Validation is by visual comparison** against the published layer displayed
   unchanged. The published weightings are adopted as they stand and never
   re-tuned, so the unlocated Hancox et al. (1994) calibration report is not a
   blocker.

## Phase 1 — The scoring scheme (complete)

- [x] Implement Table 4's factor values and weightings and Table 5's zone bands
      in `landloss.hazard.landslide.susceptibility`.
- [x] Verify against Kingsbury's own worked examples in Table 6.
- [x] Band onto the same 1–5 ranks as the published layer's `SEVERITY`, so the
      two are directly comparable.
- [x] Record that the two lowest worked examples do not decompose into published
      class values, and reproduce only the three that do.

## Phase 2 — The factor grids and the rating (complete)

- [x] Add `local_relief` to `landloss.common.utils.terrain`, for the height of a
      steep face.
- [x] Add `WLG_EARTHWORKS_PILOT` to `landloss.io.area_of_interest`. The existing
      `SMALL_WLG_PILOT` sits over Mt Victoria and holds no earthworks polygons at
      all, so it cannot exercise the modification factor.
- [x] Slope angle from the elevation model at the coarse working resolution.
- [x] Cut angle and face height from the elevation model at the fine resolution,
      inside the mapped cut and fill polygons.
- [x] Aggregate the fine factors onto the coarse grid by maximum.
- [x] Geology from the NLM geomorphology landform classes, and groundwater from
      the NLM median depth grid with 4 m assumed off its flat-land footprint.
- [x] Landslides as a constant zero from `config.py`, for want of an inventory.
- [x] Write the rating and the zone rasters, and print the zone areas.

## Phase 3 — Visual comparison against the published layer

- [x] Figure putting the rebuilt zones beside the GWRC layer over the same
      extent, drawn by `fig_slope_susceptibility.py`.
- [ ] Decide, from that figure, whether the arithmetic alone is close enough to
      be useful, or whether Phase 4 is needed.

Over the pilot, with geology and groundwater read from the National
Liquefaction Model:

| Zone | Rebuilt | Published |
| --- | --- | --- |
| 1 Very low | 61.6% | 58.5% |
| 2 Low | 36.4% | 35.0% |
| 3 Moderate | 2.0% | 5.4% |
| 4 High | 0.0% | 1.0% |
| 5 Very high | 0.0% | 0.1% |

- **The bottom two zones now agree closely**, 61.6% against 58.5% and 36.4%
  against 35.0%. They did not while geology and groundwater were held constant:
  that put every cell at 30 points before any terrain was read, above the 20
  point band, so the very low zone was unreachable and the whole distribution
  sat one zone high. Reading the two factors from the NLM moved the baseline to
  8 points on hill country and 20 to 25 on the flats, and the agreement follows
  from that rather than from anything about the terrain.
- **The middle is now short rather than over-severe**, 2.0% against 5.4%.
- **The top is still missing**, 0.0% against 1.1%. At 10 m only 0.2% of cells
  exceed 45 degrees, and the 1995 map expanded every such facet to the whole
  slope it sat on. That plus the absent landslide inventory is the remaining
  gap, and it is what Phase 4 and Phase 5 address.

So the disagreement is now confined to the top of the scale. For a loss model
reading susceptibility on insured land that is the part that matters, because
the high and very high zones are where the claims are, which argues for
Phase 4.

## Phase 4 — The 1995 generalisation rules

Not started. The published map is generalised polygons, not a scored grid, and
section 4.4.2 of the booklets sets out the rules used. Without them the rebuilt
grid is systematically less severe than the published map. Each rule is a
separate piece of work:

- [ ] Expand a steep facet to the whole slope it occupies.
- [ ] Add the downslope runout allowance.
- [ ] The tear-drop rule for a small steep area high on a gentle slope.
- [ ] Force every modified slope into the high or very high zone, which is what
      the source does regardless of the arithmetic.

## Phase 5 — Coverage

Not started. The cut and fill records reach about a tenth of insured land, and
only in Wellington City.

- [ ] Chase the equivalent earthworks records from Porirua, Lower Hutt and Upper
      Hutt.
- [ ] Detect cut faces and sidling fills from the elevation model over the
      insured land extent, for the nine tenths of Wellington City the records do
      not reach. This is the same terrain work the retaining wall exposure needs.
- [ ] Run over the full earthworks extent rather than the pilot. The fine pass is
      240 km² at the pilot's resolution, so this needs the fetch chunking before
      it is attempted.

## Phase 6 — A score per property

Not started. The scope decision is that the product is a susceptibility score on
insured land, not a regional map.

- [ ] Reduce the zone raster onto the insured land extent, one score per
      property.
- [ ] Decide the reduction: the maximum zone under the insured land, the area
      weighted mean, or the share of insured land in each zone.

## Known limitations carried by the current build

- The landslide factor is zero everywhere, because no inventory is held. That
  removes up to 20 of the 150 points and flattens the distinction the source
  drew between ground with old slides, ground with active slides, and ground
  with neither. The NLM geomorphology layer's own "Landslide" landform class was
  measured as a possible stand-in and ruled out: over the four territorial
  authorities it is 7 polygons, 1.94 km2, 0.14% of the study area, with **2**
  building outlines standing on it. It cannot carry a residential factor.
- Geology resolves to two values, because the NLM maps neither weathering nor
  shearing. Reading the finer `l3_yp` material class rather than
  `l2_geomorphology` keeps talus separate from landslide debris and leaves open
  water unscored, but it does not change that. Over the four territorial
  authorities the model is 443 polygons across 1,389 km2.
- The groundwater depth thresholds are this study's reading of Kingsbury's three
  named drainage conditions, which he never put a depth to, and they barely
  discriminate. Within the modelled footprint over the four territorial
  authorities the depths run p10 1.88 m to p90 2.94 m, so 91.3% of it falls in
  the single "poorly drained" class. In practice the factor is a 5 point offset
  on flat land and nothing on hill country.
- Depth is assumed at 4 m over the two thirds of the pilot the NLM groundwater
  grid does not model. That is a defensible reading of hillside drainage rather
  than a measurement.
- Slope modification is scored only inside mapped earthworks polygons. Everywhere
  else scores zero, which under this scheme means it cannot reach the high or
  very high zone on modification at all.
- The face height is local relief in a moving window, not a measured toe to crest
  height. A window wider than the face overstates it; a window narrower
  understates it.
- Fine factors are aggregated to the coarse grid by maximum, which follows the
  source's own statement that a steep component controls the stability of the
  whole slope, but it does mean a single steep cell lifts its whole coarse cell.

## Potential future improvements

- Fit the slope support length rather than assuming the coarse resolution
  matches the 1995 terrain model, and report how the zone areas move with it.
- Use the GNS SLIDE morphology layer's scarps and breaks in slope as a partial
  landslide inventory, and its retaining walls against the source's rule that
  adequately retained slopes are excluded from the high zone.
- Run the groundwater depth thresholds and the assumed off-footprint depth at
  other values and report how many properties change zone. One line each, and
  together they settle how much the two readings cost.
- Use the NLM flatland layer (`NLM_FLATLAND_LAYER_ID`) to stop the geology
  factor applying on flat ground. Kingsbury's colluvium and alluvium class is
  explicitly material *on slopes*, and scoring flat alluvium at the top of that
  class is what keeps the rebuilt flats a little more severe than the published
  ones. Waiting on a reader for that layer.
