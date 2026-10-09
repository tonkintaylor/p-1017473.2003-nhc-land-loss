# How complete is the WCC earthworks record?

Findings from `fig_wcc_earthworks_completeness.py`, run 23 September 2026.

## Question

Wellington City Council's earthmoving cut and fill polygons
(`landloss.io.readers.get_wcc_cut_areas`, `get_wcc_fill_areas`) are an index of
the earthworks the council holds plans for. They are the obvious source for the
slope modification factor in an earthquake-induced slope failure susceptibility
model, but only if they capture most of the earthworked ground. GNS Science's
SLIDE geomorphic mapping (`get_gns_slide_morphology`) was drawn independently
from imagery and elevation models and includes a "Cut/fill line" type, so it is
a cheap check on how much the council record misses.

## Method

- Inputs: the 2,421 GNS "Cut/fill line" features (240 km), and the 203 WCC cut
  and 250 WCC fill polygons merged into one earthworks footprint. GNS does not
  say whether a line is a cut or a fill, so the two WCC layers are not compared
  separately.
- GNS to WCC (completeness): the length of each GNS line lying within a
  tolerance of the WCC footprint, clipped along the line rather than counted
  per line (`gns_length_within`).
- WCC to GNS: whether each WCC polygon has any GNS cut/fill line within the same
  tolerance (`wcc_polygons_matched`). Only the 439 polygons inside the GNS
  mapping extent are counted; 14 in the far north fall outside it.
- Tolerances of 0, 5, 10, 20 and 50 m. A GNS line marks the edge of an
  earthwork, so it often sits on or just outside a WCC polygon boundary; a
  fraction that keeps climbing with the buffer is picking up neighbouring
  ground rather than the same earthwork.

## Results

The full table is in
`research/hazard/landslide/wcc_earthworks_completeness/tab/wcc-earthworks-vs-gns-cut-fill.csv`,
and the map (GNS lines coloured by whether they fall within 10 m of WCC) in the
`fig/` folder beside it.

| Tolerance | GNS length near WCC | WCC polygons with a GNS line |
| --- | --- | --- |
| 0 m | 54.4 km (22.6%) | 261 of 439 (59.5%) |
| 5 m | 64.4 km (26.8%) | 278 of 439 (63.3%) |
| 10 m | 70.5 km (29.3%) | 287 of 439 (65.4%) |
| 20 m | 77.9 km (32.4%) | 299 of 439 (68.1%) |
| 50 m | 93.7 km (39.0%) | 323 of 439 (73.6%) |

## Findings

1. The WCC record holds well under half of the earthworked ground GNS can see:
   about 30% of GNS cut/fill length at 10 m, and under 40% even at 50 m. It
   cannot be the only source for slope modification, and ground with no WCC
   polygon has not been shown to be natural.
2. The gaps are geographic. On the map, unmatched GNS lines concentrate in the
   southern suburbs (Island Bay, Owhiro Bay, Brooklyn), the Miramar peninsula,
   the inner suburbs and the Ngauranga to Kaiwharawhara escarpment.
   Johnsonville to Newlands and Karori match best.
3. A third of WCC polygons have no GNS line near them, so the GNS lines cannot
   replace the council record either. The two are complementary: each captures
   earthworks the other does not.
4. Some unmatched GNS length is not subdivision earthworks. The CBD waterfront
   and airport reclamation edges show up as unmatched, so part of the 70% is a
   difference in what each source sets out to capture rather than a gap in the
   council record.

## Implications for the susceptibility model

- A slope modification layer should combine both sources rather than choose
  one.
- The GNS lines need turning into areas before they can stand alongside the WCC
  polygons, for example by buffering downslope or by pairing with the DEM.
  Neither source gives cut height, cut angle or fill thickness.

## Caveats

- Both sources cover Wellington City only; nothing here says anything about
  Porirua, Lower Hutt or Upper Hutt.
- The WCC cut layer is CC BY-ND 4.0 and the fill layer records no licence, so
  the figure is for internal use and must not be published without the
  council's agreement. The GNS layer is CC BY 4.0.
- The geographic pattern in finding 2 is read off the map by eye, not measured.
