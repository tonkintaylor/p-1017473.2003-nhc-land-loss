# Townsend et al. (2020): SLIDE (Wellington) geomorphology, in one page

Townsend, Massey, Lukovic, Rosser, de Vilder, Ries, Morgenstern, Ashraf, Jones &
Carey (2020), *SLIDE (Wellington): Geomorphological characterisation of the
Wellington urban area*, GNS Science report 2019/28, 194 p.,
doi:10.21420/CHRR-4G41. The PDF (231 MB) is not in git; see `SOURCES.md`. Written
from the report text on 1 October 2026; page numbers are the report's own.

## What it is

Version 1.0 of GNS's geomorphology mapping of Wellington City, made for the
MBIE-funded SLIDE project to find slopes people have cut and filled, and to give
slope-response models a map of the near-surface ground (pp. 1-5). Nominal scale
1:500, current to the 2013 aerial photographs and LiDAR. It covers part of
Wellington City only, nothing in Porirua, Lower Hutt or Upper Hutt. Appendix 4 is
133 map sheets; the data are three layers, read here by `get_gns_slide_morphology`,
`get_slide_interpreted_materials` and `get_slide_genesis`.

## The three layers

1. **Morphology** (lines): drainage, breaks in slope, ridges, cliffs, tension
   cracks, and *some* retaining walls.
2. **Interpreted materials** (polygons): rock at/near surface, talus, colluvium,
   loess, alluvium, old alluvium, sand and gravel, boulders, fill (built up by more
   than about 2 m) and four mixed-fill units. Mixed units are built-up ground where
   the materials could not be separated; fill/colluvium/rock is a "bucket" (p. 35).
3. **Genesis** (polygons): the process that made the ground. Cut slope, fill body
   and landfill are complete. Landslide (recent or relict), rockfall, fan, dune,
   terracettes, modified terrain and the rest are not.

## How it was made (pp. 14-21)

Digitised on screen from 2013 photographs and LiDAR, with limited fieldwork and
Google Street View checks. Cuts and fills came from subtracting 1938 and 1945
photogrammetric surface models from the 2006 and 2013 LiDAR: negative is cut,
positive is fill. Those models have an RMS error of about 2.5 m, so small
earthworks are hard to see. Each cut and fill is dated by the earliest photograph
it appears on, in the text field `DateOrigin` (`pre-1938`, `1945-1996`, `~2013`),
and 1938 and 1945 do not cover the whole area (p. 40).

## What it says about its own reliability

- Boundaries are bands a few metres to tens of metres wide, not lines (p. 45).
- The **genesis layer is "less complete"** and less accurate than the others,
  except cut slopes and fill bodies, and is meant to be updated (pp. 19, 36, 59).
  Landslides are recent or relict by appearance, not dated events.
- Materials are inferred from landforms. Colluvium 2-3 m thick can mantle ridges
  mapped as rock, and fossil gullies have no surface expression, so "rock at/near
  surface" can hide several metres of soil (p. 31).
- **Rock weathering and discontinuities were not assessed** (p. 45): the map says
  what is at the surface, not how strong it is.
- Fieldwork gaps in Kelburn, Northland, Newlands, Seatoun and Houghton Bay to
  Melrose. In the CBD it leans on Begg & Mazengarb (1996) (pp. 20, 45).
- Retaining walls are not an inventory, and whether a cut or fill was engineered
  is not identified (pp. 22, 37). It is a suburb-scale desktop map, not a
  substitute for site investigation (p. 45).

## Why it matters here

- About 1,600 fill bodies and nearly 3,000 cut slopes were mapped (p. 2), dated so
  that failure frequency can be compared with earthwork age (p. 40). That is the
  evidence base for a slope-modification factor.
- Most of the ~400 slope failures a year on Wellington's roads are on modified
  slopes in rain (p. 2). The strongest recorded rock-site shaking since 1940 is
  Kaikōura's 0.15 g, so how modified slopes behave in stronger shaking is unknown
  (p. 3).
- Coverage stops at the Wellington City boundary. For the Hutt Valley and Porirua
  use the 1:50,000 geology, `get_wellington_urban_geology`.
- Licence: the report carries no licence statement (`SOURCES.md`).
