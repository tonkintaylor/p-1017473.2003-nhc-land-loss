# Are the pifs in cut, fill or natural ground?

Findings from `gen_pif_cut_fill.py` and `fig_pif_cross_sections.py`, run 5 October
2026 over the Wellington pilot (`wlg-pilot`), on the pifs landslide step 12 wrote
the same day.

## Question

Each pif (`landloss.hazard.landslide.instability_zones`) is a step in the 1 m DEM.
For the wall and slope models we want to know whether the step is a cut face, a
fill batter, a benched terrace (both) or natural ground, and whether that can be
read from the DEM alone.

## Method

- **Natural surface, two estimates.** `rolling_mean`: the DEM averaged over a
  30 m square window (`config.ROLLING_WINDOW_M`), the lead's first idea.
  `fit_quadratic`: a quadratic surface fitted by least squares to every DEM
  cell within 15 m of the pif's points (`config.FIT_RADIUS_M`), so the surface
  bends with a crest or gully where the mean does not. The repository already
  had a close relative of the first: `landloss.common.utils.terrain.cut_fill_residual`
  (the DEM minus a 30 m or 100 m block mean), which step 3 writes and the ground
  map uses to class cells where no mapping reaches.
- **Crest and foot.** A pip is the crest of a drop by definition, so comparing
  pips alone with a smoothed surface reads nearly every pif as fill (see
  finding 1). Each pip is walked down its own fall direction to the first step
  flatter than 20 degrees, up to 15 m (`face_feet`), which gives the foot of the
  face below it.
- **Class** (`classify`). Per pif and per surface, the crest residual and foot
  residual are the medians over its pips of the DEM minus the surface. The
  *excess drop* (crest minus foot residual) is how much further the ground falls
  across the face than the natural surface does; 1 m or less is natural
  (`config.EXCESS_DROP_M`). The *position* (crest plus foot residual over the
  excess drop) runs from -1 (all of the excess below the surface: cut) to +1 (all
  above: fill); beyond plus or minus one third (`config.POSITION_SPLIT`) is cut
  or fill, between is cut and fill.
- **Check.** Against the GNS SLIDE genesis "Cut slope" and "Fill body" polygons
  (the siz table's `in_slide_cut` and `in_slide_fill`). They are a partial
  mapping, so "neither" is a baseline rather than a statement of natural ground.
- **Sections.** Three 100 m sections near pif 8220, set by hand in
  `config.SECTIONS`, drawn true scale with both surfaces, the pips coloured by
  class and the foot below each pip.

## Results

Tables in `research/hazard/landslide/pif_cut_fill/tab/` (`pif-classes.csv`,
`pif-classes-vs-slide.csv`); the per-pif table, the per-pip table and the rolling
mean surface in `temp/hazard/landslide/pif-cut-fill*-pilot.*`; the sections in
`research/hazard/landslide/pif_cut_fill/fig/pif-8220-cross-sections.png`.

All 12,015 pifs of the pilot:

| Class | Rolling | Poly |
| --- | --- | --- |
| cut | 2,695 | 2,083 |
| cut and fill | 1,550 | 2,405 |
| fill | 1,189 | 527 |
| natural | 6,581 | 7,000 |

The 3,341 pifs of 10 pips or more, as a share of each SLIDE group:

| SLIDE says | n | Rolling cut / c+f / fill / natural | Poly cut / c+f / fill / natural |
| --- | --- | --- | --- |
| cut slope | 199 | 0.62 / 0.19 / 0.13 / 0.07 | 0.68 / 0.19 / 0.02 / 0.11 |
| fill body | 301 | 0.55 / 0.26 / 0.09 / 0.09 | 0.48 / 0.38 / 0.03 / 0.12 |
| neither | 2,806 | 0.43 / 0.22 / 0.14 / 0.21 | 0.40 / 0.32 / 0.05 / 0.22 |

(35 pifs touch both a cut slope and a fill body and are left out.)

The two methods give the same class to 79% of pifs, 68% of those with 10 pips
or more.

## Findings

1. **Counting pips above the rolling mean does not separate fill.** Half the
   pifs have every pip above it, and the median share is 1.0 for SLIDE fill
   bodies and for unmapped ground alike. Only SLIDE cut slopes are lower (0.57).
   A pip is a crest, and a crest stands above any smoothed surface, natural or
   not.
2. **Crest and foot together pick out cut.** SLIDE cut slopes read as cut 62%
   (rolling) and 68% (poly) of the time, against 40-43% on unmapped ground.
3. **Neither method sees the mapped fill.** Pifs on SLIDE fill bodies read as
   fill 9% (rolling) and 3% (poly) of the time, no more than on unmapped
   ground, and as cut about half the time. Both surfaces are fitted to today's
   ground, so a gully fill tens of metres across *is* the local surface. What
   they measure is a platform cut into the top of the fill, not the fill.
4. **The surfaces absorb half of each step.** The median face drop is 1.4 m
   but the median excess drop only 0.9 m (rolling) and 0.9 m (poly), so most
   small pifs fall under the 1 m natural threshold. That threshold, not the
   ground, decides much of the natural class.
5. **Classes near the boundaries are unstable.** Pif 8219 has a rolling
   position of 0.34, just past the fill split, and reads as cut on the
   quadratic. Pif 8220 reads as cut and fill on both: its crest is 0.85 m
   above the rolling mean and its foot 0.68 m below it, which on the sections
   is the outer edge of one platform above the cut back of the next.
6. **Cut dominates everywhere** (40% of unmapped pifs). This may be real
   (benched hillside housing is cut into the slope with the spoil pushed over
   the edge), or a bias of the foot walk, which stops on the next platform's
   cut back. Not yet tested.

## Implications

- Present-day trend surfaces (a rolling mean, a local polynomial) can say
  whether a face is cut back into the slope or stands proud of it, at the
  scale of one or two platforms. They cannot recover a pre-development surface
  under large fills. That needs either older topography, or a surface
  interpolated across the disturbed ground from undisturbed ground around it
  (see the literature below).
- The SLIDE fill bodies and the WCC fill polygons
  (`wcc_earthworks_completeness.md`) remain the source for fill. The DEM method
  is at best a supplement for cut.

## Approaches in the literature

A search on 5 October 2026. Open-access copies are parked in
`temp/reference/cut-fill/`, listed in its `SOURCES.md`.

1. **Difference against an older surface.** This is the standard approach,
   wherever an older surface exists. The current DEM minus a pre-development
   surface gives the sign (cut or fill) and the thickness directly.
   - The old surface comes from historical contour maps or old aerial
     photographs. Terrone et al. (2021) did this for Genoa: 1840s contours,
     tension spline to 1 m, then differenced against LiDAR. Henselowsky et
     al. (2021) used historic maps over a German lignite mining area.
   - Japan's screening for large residential fills overlays contour maps from
     before and after development. The guideline is MLIT's 2015 large fill
     guideline (*大規模盛土造成地の滑動崩落対策推進ガイドライン及び同解説*). Wartman
     et al. (2013) describe the 2011 Tohoku fills that were mapped this way.
   - Its weakness is the vertical error of the old surface, which grows with
     slope (horizontal error times tan slope; Terrone et al. 2021). It is
     therefore worst on exactly the steep faces we are classifying.
   - **For Wellington this has already been done.** The SLIDE genesis cut
     slope and fill body polygons used as the check above came from
     subtracting GNS's 1938 and 1945 photogrammetric surface models from the
     2006 and 2013 LiDAR (Townsend et al. 2020; summary in
     `context/lit/landslide/townsend_2020/townsend-2020-summary.md`).
     - Those models have an RMS error of about 2.5 m, and the median pif face
       drops only 1.4 m. The polygons see the large earthworks; most pifs are
       below what they can resolve.
     - That fits finding 3: the SLIDE fill bodies are mostly large fills, which
       a local surface absorbs.
2. **Interpolating across the disturbed ground.** Mask the modified area and
   interpolate a surface over it from the undisturbed ground around it, by
   spline or kriging. This comes from quarry and mine reconstructions.
   - It works for isolated pits and pads.
   - It fails on a fully terraced hillside, where no undisturbed ground is
     near. Its anchors would have to come from reserves and bush.
3. **Low-pass and residual relief.** This family is what both methods above
   are.
   - Hillier and Smith (2008) separate a regional surface with a median filter
     and subtract it.
   - TPI (topographic position index; Weiss 2001) and DEV (deviation from mean
     elevation) are the normalised forms. De Reu et al. (2013) found DEV
     better in mixed landscapes.
   - The known weaknesses are the ones found here. The surface is biased by
     the earthworks themselves, and by the hill's own curvature (spurs read as
     fill, gullies as cut).
   - The remedies offered:
     1. a median or robust filter in place of the mean;
     2. fitting the local surface only to cells outside the faces and
        platforms;
     3. carrying the scatter of the fit as an uncertainty band rather than a
        fixed threshold.
4. **Classifying features from one DEM.** Sawada et al. (2013) classed mountain
   road sections as embankment or cut by logistic regression on a 2 m DEM.
   - The inputs were openness, the slope angles uphill and downhill, the
     original slope and plan curvature, each measured 5 to 15 m from the road
     edge.
   - The downhill slope angle was the strongest predictor.
   - Sections with retaining walls were the ones it got wrong.
   - It is the closest analogue to a face-by-face classifier.
5. **Terrain signatures and machine learning.**
   - SLLAC (Sofia et al. 2014) and the wider topographic signature framework
     (Tarolli et al. 2019; Cao et al. 2020) pick out terraced and engineered
     ground, but not the sign of the change.
   - Geomorphons (Jasiewicz and Stepinski 2013) give landform classes above
     and below a face. These could serve as classifier features.
6. **Classification practice.** The British Geological Survey's artificial
   ground classes are made, worked, infilled (worked then made), disturbed and
   landscaped ground (Rosenbaum et al. 2003; Price et al. 2011). Our "cut and
   fill" is their infilled ground.
   - Japanese earthquake experience shows the cut/fill boundary and the fill
     shoulder are where houses fare worst (Wartman et al. 2013; Kamai 2016).
   - MLIT's thresholds for a fill that matters are a valley fill of 3,000 m²
     or more, or a side-hill fill 5 m or more high on original ground of 20
     degrees or more.

### Worth trying next

1. A **robust local fit to anchor cells only**: a plane or quadratic fitted
   to the cells outside every pif's faces and feet, with the crest and foot
   residuals compared against the fit's own scatter. This addresses findings
   4 and 5 and needs no new data.
2. A **classifier trained on the SLIDE polygons**, in the style of Sawada et
   al. (2013). Inputs would be the slopes 5 to 15 m above and below the face,
   openness, geomorphons, the residuals above and the distance to a building.
   Cross-validation would say how far it can be trusted beyond the polygons.
3. **The GNS 1938 and 1945 surface models themselves**, if GNS will release
   them. They give a direct sign test where a face is large enough to beat
   their 2.5 m error.

### References

- Cao, W., Sofia, G., Tarolli, P. (2020). Geomorphometric characterisation of natural and anthropogenic land covers. *Progress in Earth and Planetary Science* 7, 2. https://doi.org/10.1186/s40645-019-0314-x
- De Reu, J., et al. (2013). Application of the topographic position index to heterogeneous landscapes. *Geomorphology* 186, 39-49. https://doi.org/10.1016/j.geomorph.2012.12.015
- Henselowsky, F., Rölkens, J., Kelterbaum, D., Bubenzer, O. (2021). Anthropogenic relief changes in a long-lasting lignite mining area ('Ville', Germany) derived from historic maps and digital elevation models. *Earth Surface Processes and Landforms* 46(9), 1725-1738. https://doi.org/10.1002/esp.5103
- Hillier, J.K., Smith, M. (2008). Residual relief separation: digital elevation model enhancement for geomorphological mapping. *Earth Surface Processes and Landforms* 33(14), 2266-2276. https://doi.org/10.1002/esp.1659
- Jasiewicz, J., Stepinski, T.F. (2013). Geomorphons - a pattern recognition approach to classification and mapping of landforms. *Geomorphology* 182, 147-156. https://doi.org/10.1016/j.geomorph.2012.11.005
- Kamai, T. (2016). 東京南西部における宅地谷埋め盛土の分布と災害リスク [Distribution of residential valley fills and its hazard risk in the south-western district of Tokyo]. DPRI Kyoto University research meeting FY2015, abstract D07. https://www.dpri.kyoto-u.ac.jp/hapyo/16/pdf/D07.pdf
- MLIT (2015). 大規模盛土造成地の滑動崩落対策推進ガイドライン及び同解説 Ⅰ編 変動予測調査編. https://www.mlit.go.jp/common/001089011.pdf
- Price, S.J., Ford, J.R., Cooper, A.H., Neal, C. (2011). Humans as major geological and geomorphological agents in the Anthropocene: the significance of artificial ground in Great Britain. *Philosophical Transactions of the Royal Society A* 369(1938), 1056-1084. https://doi.org/10.1098/rsta.2010.0296
- Rosenbaum, M.S., McMillan, A.A., Powell, J.H., Cooper, A.H., Culshaw, M.G., Northmore, K.J. (2003). Classification of artificial (man-made) ground. *Engineering Geology* 69(3-4), 399-409. https://doi.org/10.1016/S0013-7952(02)00282-X
- Sawada, K., Moriguchi, S., Tanaka, T., Asano, N., Iwata, M. (2013, year inferred from the symposium number). 詳細数値標高モデルとGISを用いた山岳道路盛土の抽出 [Extraction of embankments on mountain roads using a detailed digital elevation model and GIS]. Proceedings of the 25th Chubu Geotechnical Symposium. https://jgs-chubu.org/wp-content/uploads/pdfupload/download/syn5/pdf/25/s2526.pdf
- Sofia, G., Marinello, F., Tarolli, P. (2014). A new landscape metric for the identification of terraced sites: the Slope Local Length of Auto-Correlation (SLLAC). *ISPRS Journal of Photogrammetry and Remote Sensing* 96, 123-133. https://doi.org/10.1016/j.isprsjprs.2014.06.018
- Tarolli, P., Cao, W., Sofia, G., Evans, D., Ellis, E.C. (2019). From features to fingerprints: a general diagnostic framework for anthropogenic geomorphology. *Progress in Physical Geography* 43(1), 95-128. https://doi.org/10.1177/0309133318825284
- Terrone, M., Piana, P., Paliaga, G., D'Orazi, M., Faccini, F. (2021). Coupling historical maps and LiDAR data to identify man-made landforms in urban areas. *ISPRS International Journal of Geo-Information* 10(5), 349. https://doi.org/10.3390/ijgi10050349
- Townsend, D.B., Massey, C.I., Lukovic, B., Rosser, B.J., de Vilder, S.J., Ries, W., Morgenstern, R., Ashraf, S., Jones, K.E., Carey, J.M. (2020). SLIDE (Wellington): geomorphological characterisation of the Wellington urban area. GNS Science Report 2019/28. https://doi.org/10.21420/CHRR-4G41
- Wartman, J., Dunham, L., Tiwari, B., Pradel, D. (2013). Landslides in Eastern Honshu induced by the 2011 Tohoku earthquake. *Bulletin of the Seismological Society of America* 103(2B), 1503-1521. https://doi.org/10.1785/0120120128
- Weiss, A. (2001). Topographic position and landforms analysis. Poster, ESRI User Conference, San Diego. No stable URL found.

## Caveats

- One pilot extent, one window and one radius; neither was tuned.
- The SLIDE polygons are a partial mapping of earthworks, and the WCC record
  holds well under half (`wcc_earthworks_completeness.md`), so the "neither"
  row is not natural ground.
- The foot is found from a 20 degree slope rule along the pip's own eight-way
  fall direction, which may run along a face rather than across it.
- Run with the Koordinates layers read from the local `.koopcache`, because the
  Koordinates login was returning 502 on 5 October; the layers are the cached
  copies step 12 used.

Potential future improvements: see "Worth trying next" above.
