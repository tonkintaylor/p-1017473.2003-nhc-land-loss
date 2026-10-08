"""Run settings for the land exposure validations that take any.

Read by ``gen_building_classification.py`` and ``gen_land_value_vs_qv.py``.
Everything that changes between one run and the next, so what a run did can be
established by reading this file and its git history rather than by remembering
which flags were typed.
"""

from pathlib import Path

# The extent to classify the building outlines over: "full" for the four
# territorial authorities, or a name from landloss.io.area_of_interest.EXTENTS.
# The national outlines, addresses and boundaries are cached locally, so the
# full study area takes a couple of minutes.
EXTENT = "full"

# Whether to class each property by its use on the QV rating roll as well, and
# say where that disagrees with the footprint rule. The roll is read from T:
# through tdrive_sync, so a run with this on needs T: access. It is sensitive:
# the layer written carries only the derived class, never a roll field.
USE_QV_ROLL = True

# The footprint thresholds the run reports what the size rule would drop at,
# alongside the 500 m2 the insured land step uses.
FOOTPRINT_THRESHOLDS_M2 = (300.0, 500.0, 750.0, 1000.0, 2000.0)

# Where the classified outlines are written, for viewing in QGIS. Outside the
# repository, because the layer is regenerated rather than versioned.
OUT_DIR = (
    Path("U:/") / "MAMI" / "land-loss" / "exposure" / "land" / "building-classification"
)

# --- gen_land_value_vs_qv.py ---------------------------------------------------

# The extent to compare the modelled land value over: "full", or a name from
# landloss.io.area_of_interest.EXTENTS. The land value step (s2_land_value/s4)
# has to have been run over the same extent.
LAND_VALUE_QV_EXTENT = "full"

# Whether to compare only properties the roll uses residentially (R, L and the
# rural categories, as landloss.exposure.land.residential_use classes them).
# The model values residential land, so a shop or a warehouse on the roll is not
# a like-for-like comparison.
LAND_VALUE_QV_DWELLING_USES_ONLY = True

# Suburbs with fewer matched properties than this are left out of the suburb
# panel and layer, so no suburb figure stands for a handful of rating units.
LAND_VALUE_QV_MIN_SUBURB_PROPERTIES = 20

# Whether to write the per-property layer, which carries the roll's land value
# beside the model's. It is a working extract of the sensitive roll: written
# under temp/ only, never shared, and destroyed with the roll at the end of the
# project. The suburb layer and the figure carry summaries only.
LAND_VALUE_QV_WRITE_PROPERTY_LAYER = True
