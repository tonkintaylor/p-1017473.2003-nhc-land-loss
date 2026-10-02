# Can the SLIDE geomorphology maps be extracted from the report PDF?

Pilot run 30 September 2026 on map sheet A3 of Appendix 4 of Townsend et al.
(2020), GNS Science report 2019/28 (`context/lit/landslide/SOURCES.md`, `townsend_2020/`).
The pilot scripts were throwaway and are not committed: they need PyMuPDF,
scikit-image and scikit-learn, none of which the project depends on, and the
result below makes them unnecessary.

## Question

Appendix 4 holds 133 A3 map sheets (PDF pages 71-203), one per 1:500-mapped
tile, showing the morphology, interpreted materials and genesis layers over a
hillshade. Can the materials be recovered from those pictures as a georeferenced
layer?

## Method

- Each sheet is a raster (about 300 dpi) inside a vector frame. The frame is
  rendered at 300 dpi, giving 0.423 m per pixel.
- Georeferencing comes from the tick labels: the NZTM eastings and northings are
  printed as text with positions, and two ticks per axis give the scale (0.5669
  pt/m, i.e. 1,000 m = 567 pt) and offset. Sheet A3 covers about 1,744,478 -
  1,745,803 E and 5,420,566 - 5,421,692 N.
- Each map class is the legend swatch colour laid over the hillshade. Hillshade
  changes lightness but leaves the CIELAB a*/b* (hue and chroma) close to the
  swatch's, so a pixel is assigned to the class with the nearest a*/b*. White
  (outside the DSM), pure grey and the blue drainage lines are left unclassified.
- Check: rasterise the polygons from `get_slide_interpreted_materials` for the
  same extent onto the same grid and compare pixel by pixel.

## Results (sheet A3)

| Vector class | Area (ha) | Extracted as the same class | Unclassified |
| --- | --- | --- | --- |
| Rock at/near surface | 39.2 | 92.7% | 1.2% |
| Sand and gravel | 3.1 | 95.9% | 1.5% |
| Fill | 1.7 | 98.4% | 0.1% |
| Talus | 0.9 | 88.9% | 10.4% |
| Loess | 0.9 | 93.4% | 0.7% |
| Colluvium | 0.4 | 99.1% | 1.3% |
| Mixed fill/rock | 0.2 | 78.2% | 4.2% |
| Alluvium | 0.04 | 41.4% | 22.5% |
| Mixed fill/colluvium/rock | 0.9 | 0% | 96.7% |

Overall, 93% of the pixels classified by both agree, and only 0.2% of classified
map pixels lie outside every vector polygon. That confirms both that the
georeferencing is right to within a pixel or two and that the vector layer is
the same Version 1.0 mapping as the printed sheets.

## Findings

1. Extraction works for the well-separated colours (rock, fill, colluvium,
   loess, talus, sand and gravel).
2. It cannot separate the pale, low-chroma classes that differ by a few degrees
   of hue: sand and gravel, alluvium, boulders and old alluvium sit within about
   20 degrees of each other at chroma 14-22. Sheet A3 has no boulders or old
   alluvium, so those were not tested; alluvium (41%) shows the problem.
3. "Mixed fill/colluvium/rock" is pure grey (216, 216, 216) and water is
   near-white, so neither can be told from hillshade-only ground or from the
   background. It would need polygon-level reasoning, not a per-pixel rule.
4. Linework, hatching and the drainage blue would have to be masked and filled
   from neighbouring pixels to give clean polygons.
5. **It is not needed.** GNS serves the same polygons as vectors, and the
   repository already reads them: `get_slide_interpreted_materials` (14 classes,
   with a `confidence` field the maps lack) and `get_gns_slide_morphology`. The
   printed maps carry nothing the vectors do not.

## Implications

- Do not build a PDF map extraction pipeline. Use the vector layers.
- **The Genesis layer had no reader** when this pilot was run;
  `get_slide_genesis` now reads it. Sublayer 2 of the same service returned
  6,401 features on 30 September 2026: 2,987 cut slopes, 1,606 fill bodies, 1,058
  modified terrain, 494 relict and 88 recent landslides, 46 landfills, and
  smaller numbers of rockfall, fan, dune, terracette and other classes. It is
  the source of anthropogenically modified ground (cut slopes and fill bodies,
  which GNS completed) and of landslide polygons for the Wellington City part of
  the study area (which GNS calls less complete and less accurate), both
  relevant to the landslide models. `get_gns_slide_morphology` already points to it, and to
  the Koordinates mirror (layer 125309). Its licence is not recorded on either
  service (see `get_slide_genesis`).
- Licence: the report PDF carries no licence statement. The Koordinates mirror
  of the morphology layer records CC BY 4.0, while the materials service has no
  licence statement (see the reader docstrings). Confirm the terms with GNS
  before a layer derived from either is delivered.

## Caveats

One sheet of 133, chosen for being at the edge of the study area, with a
Wellington south-coast mix of rock, fill and sand and gravel. Nothing here says
how well the classifier would do on the urban sheets, where mixed fill classes
dominate. The Genesis counts are for the whole layer, not the sheet.
