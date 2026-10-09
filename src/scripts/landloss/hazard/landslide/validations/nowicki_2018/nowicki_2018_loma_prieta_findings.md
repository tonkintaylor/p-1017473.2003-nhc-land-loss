# Nowicki Jessee (2018) rebuild: Loma Prieta check against the USGS

Results of the two scripts beside this file, run on 29 September 2026 against the
USGS `groundfailure` package's Loma Prieta test case at tag 1.3.2. The model is
`landloss.hazard.landslide.models.nowicki_2018`, run in its operational variant,
because that is how the USGS target was made. Figures are written to
`report/hazard/landslide/nowicki-2018-validation/fig/`.

The comparison grid is the USGS target's own: GMTED2010 7.5 arc-second cells
inside the ShakeMap's extent, 337 × 578 cells. Its outermost row and column are
left out. They sit half a cell beyond the last ShakeMap node, where the USGS
leaves a gap and GDAL's bilinear resampling extrapolates. Every one of the 877
cells that differ in that way is on that border.

## 1. The equations: our implementation on the USGS inputs

`fig_nowicki_2018_loma_prieta_model.py`, drawing `loma-prieta-model-against-usgs.png`.

| Quantity | Result |
| --- | --- |
| Cells compared (land, interior) | 117,636 |
| Coverage within 0.0001 of the USGS | 99.99% |
| Largest coverage difference | 0.0002 |
| Coverage standard deviation within 0.0001 | 99.997% |
| Cells empty in one and not the other | 0 |
| Total landslide area, ours against USGS | 36.99 km² against 36.99 km² |

The USGS rounds coverage to four decimal places, so a difference of 0.0001 to
0.0002 is rounding. Our reading of equations 8 and 9, the operational settings
(`coefficients.USGS_OPERATIONAL`) and the delta-method uncertainty reproduces the
reference implementation.

Getting there settled three details the paper does not state, and the code now
follows the USGS on each:

- GlobCover class 170 takes class 180's coefficient of 1.19 (see the comment in
  `coefficients.GLOBCOVER_COEFFICIENTS`).
- Classes absent from Table 3 take 0.
- PGV is not clipped, although the USGS configuration declares a clip, because
  the package never applies it to the shaking layers.

## 2. The layers: rebuilt from raw sources against the USGS rasters

`fig_nowicki_2018_loma_prieta_layers.py`, drawing
`loma-prieta-layers-against-usgs.png`.

Each rebuilt layer compared with the USGS's own, on the target grid:

| Layer | Agreement |
| --- | --- |
| Slope | r = 0.933; ours 0.05° steeper on average; mean absolute difference 1.00° |
| Lithology coefficient | Same class coefficient in 98.2% of cells |
| Land cover coefficient | Same class coefficient in 85.5% of cells on the target grid; 99.999% on GlobCover's own grid |
| CTI | r = 0.82; ours 0.47 lower on average; mean absolute difference 1.03 |

The **swap test** reruns the model on the USGS inputs with one layer at a time
replaced by ours, then on all of ours. This is the comparison that matters,
because a layer can differ and barely move the answer:

| Run | r against target | Total area | Against USGS |
| --- | --- | --- | --- |
| USGS inputs | 1.000 | 36.99 km² | 0.0% |
| Our slope | 0.921 | 37.60 km² | +1.7% |
| Our lithology | 0.992 | 36.97 km² | −0.0% |
| Our land cover | 0.898 | 36.81 km² | −0.5% |
| Our CTI | 0.999 | 36.26 km² | −1.8% |
| **All rebuilt inputs** | **0.809** | **36.72 km²** | **−0.6%** |

What each layer's difference comes from:

- **Slope** is the layer with most leverage, at 0.06 per degree plus the
  interaction term. The formula is the paper's: the gradient of GMTED2010 7.5
  arc-second median elevation, by central differences, as GMT computes it. The
  difference is in the elevation values the gradient is taken of.
  - The USGS's slope raster is on a grid registered to whole multiples of 7.5
    arc-seconds, 0.5 arc-seconds off GMTED2010's own tiles, so the USGS must
    have resampled the elevations before differentiating.
  - Computing slope on GMTED2010's native grid and resampling the slope left
    ours 0.17° steeper and total area +5.0%. Resampling the DEM onto the
    USGS-registered grid first, as `gen_model_inputs` now does on the grid
    from `gen_model_grid`, cuts that to 0.05° and +1.7%.
  - No choice of ours reproduces their slope cell for cell. Nearest, bilinear,
    cubic and average resampling, central and Horn stencils, and the median,
    mean and breakline GMTED products all top out at r ≈ 0.93. Their elevation
    grid has been through an interpolation step the paper and the package do
    not document.
  - Slope is a derivative, so small elevation differences between two
    interpolations become large slope differences cell by cell: a mean absolute
    difference of 1° with almost no bias. Only the USGS's own processing script
    would close the remaining scatter.
- **Lithology** differs only along polygon boundaries. The 2015 CCGM edition of
  GLiM is used, not the 2012 v1.0, and it changes nothing that matters here.
- **Land cover** maps class for class: on GlobCover's own grid, 99.999% of 3.76
  million cells take the same coefficient as the USGS raster. The 85.5% on the
  target grid is the USGS raster's own geometry. It is a resample of GlobCover,
  offset 0.2 cells in longitude and with a latitude spacing that drifts 0.36
  cells across its extent, so near every class boundary it and GlobCover pick
  different source cells. GlobCover is noisy at the pixel scale, which makes
  that 14.5% of cells, but it moves total area by only 0.5%.
- **CTI** is the one layer where the DEM itself differs, not just its processing. It is recomputed from GMTED2010 30 arc-second elevation (flow routing in
  `landloss.common.utils.hydrology`; area in km², as HYDRO1k counted it). The
  USGS's HYDRO1k was built from a different DEM (GTOPO30), in a different
  projection, with its own conditioning. Upstream area also changes by orders
  of magnitude between a channel cell and its neighbour, so a channel routed
  one cell over moves the index by several units. The correlation stops at
  0.82.
  Treating GMTED2010's 0 m sea as nodata reproduces the USGS CTI's own coastline
  almost exactly. CTI carries a coefficient of only 0.03, so a mean absolute
  difference of 1.0 is worth 0.03 in the logit, and the whole layer moves total
  area by 1.8%.

## What this establishes

- The implementation is right: on the USGS inputs, our code gives the USGS
  answer.
- The layer build is close enough to use. Rebuilt from public sources with our
  own code, the model gives total landslide area within 1% of the USGS's
  (−0.6%), and a cell-by-cell correlation of 0.81 with its coverage. The
  cell-scale scatter is mostly slope, from an elevation resampling the USGS
  applied and did not document; the totals agree.
- This is a check of the rebuild, not of the model. Allstadt et al. (2018)
  found the model overpredicts New Zealand landsliding (see the rebuild note's
  "What Allstadt et al. (2018) found on Kaikōura"). Agreement with the USGS says
  we have their model, not that their model is right for Wellington.

## Caveats

- One event, one extent. Loma Prieta is Californian coast ranges, not NZ
  greywacke.
- The check was run locally on copies of the source files downloaded to a
  scratch folder, with only the T: path resolution patched. The files are the
  ones the `get_` scripts in `static_data_gen/` download to T:, from the same
  URLs; rerun both scripts once those files are in place to confirm them from
  T:.
