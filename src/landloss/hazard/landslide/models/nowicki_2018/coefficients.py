"""The fitted coefficients of the Nowicki Jessee et al. (2018) landslide model.

Every number here is read from the paper
(``context/lit/landslide/nowicki_jessee_2018/``): the regression terms and the
class coefficients from Table 3, the areal coverage conversion from equation 9.
The only numbers not from the paper are the operational settings in
:data:`USGS_OPERATIONAL`, which come from the USGS ``groundfailure`` package's
``jessee_2018`` model (tag 1.3.2) and are kept separate so a run can say which
of the two it is.

The lithology and land cover terms are categorical. A class listed here takes
its coefficient; a class absent from Table 3 is either the regression's
reference category or was absent from the training data. Either way it enters
the logit as zero, which is what the USGS coefficient rasters do too.
"""

from types import MappingProxyType

# Table 3: the intercept and the continuous terms of equation 8.
INTERCEPT = -6.30
LN_PGV = 1.65  # ln(PGV), PGV in cm/s
SLOPE = 0.06  # per degree of slope
CTI = 0.03  # compound topographic index
LN_PGV_X_SLOPE = 0.01  # ln(PGV) x slope in degrees; the paper's amplification proxy

# Table 3, glim75c<n>: the lithology coefficients, keyed by GLiM's two-letter
# top-level class code. The paper numbers the classes 1-16 alphabetically by
# that code (1 ev ... 16 wb), which is how glim75c3 is metamorphics and
# glim75c11 siliciclastic sedimentary; ev (evaporites, class 1) is the
# reference category, and ig (ice and glaciers) and wb (water bodies) carry no
# coefficient.
GLIM_COEFFICIENTS = MappingProxyType(
    {
        "mt": -1.87,  # metamorphics
        "nd": -0.66,  # no data
        "pa": -0.78,  # acid plutonic rocks
        "pb": -1.88,  # basic plutonic rocks
        "pi": -1.61,  # intermediate plutonic rocks
        "py": -1.05,  # pyroclastics
        "sc": -0.95,  # carbonate sedimentary rocks
        "sm": -1.36,  # mixed sedimentary rocks
        "ss": -1.92,  # siliciclastic sedimentary rocks
        "su": -3.22,  # unconsolidated sediments
        "va": -1.54,  # acid volcanic rocks
        "vb": -1.50,  # basic volcanic rocks
        "vi": -0.81,  # intermediate volcanic rocks
    }
)

# Table 3, globcover<n>: the land cover coefficients, keyed by GlobCover 2009
# class value. Class 11 (post-flooding or irrigated croplands) is the reference
# category and 210 (water bodies) carries no coefficient. Class 170 (closed
# broadleaved forest permanently flooded, saline or brackish water) is not in
# Table 3, but the USGS coefficient raster gives it class 180's 1.19, and
# Table 3's description of 180 ("... fresh, brackish, or saline water") reads
# as the two having been merged; 170 follows the USGS here. Checked on the
# Loma Prieta extent, where this makes our raster match the USGS one exactly.
GLOBCOVER_COEFFICIENTS = MappingProxyType(
    {
        14: 0.91,  # rainfed croplands
        20: 0.88,  # mosaic cropland
        30: 0.78,  # mosaic vegetation
        40: 0.68,  # closed to open broadleaved evergreen or semi-deciduous forest
        50: 0.30,  # closed broadleaved deciduous forest
        60: 1.77,  # open broadleaved deciduous forest/woodland
        70: 1.71,  # closed needleleaved evergreen forest
        90: -1.26,  # open needleleaved deciduous or evergreen forest
        100: 1.50,  # closed to open mixed broadleaved and needleleaved forest
        110: 0.68,  # mosaic forest or shrubland/grassland
        120: 1.13,  # mosaic grassland/forest or shrubland
        130: 0.79,  # closed to open shrubland
        140: 1.03,  # closed to open herbaceous vegetation
        150: 0.54,  # sparse vegetation
        160: 2.34,  # closed to open broadleaved forest regularly flooded
        170: 1.19,  # permanently flooded saline forest: class 180's, as USGS
        180: 1.19,  # grassland or woody vegetation on regularly flooded soil
        190: 0.30,  # artificial surfaces and associated areas
        200: -0.06,  # bare areas
        220: -0.18,  # permanent snow and ice
        230: -1.08,  # no data (burnt areas, clouds)
    }
)

# Equation 9: areal coverage LP = exp(a + b P + c P^2 + d P^3), fitted to the
# complete polygon inventories only. It runs from 0.05% when P is 0 to 25.6%
# when P is 1.
COVERAGE_A = -7.592
COVERAGE_B = 5.237
COVERAGE_C = -3.042
COVERAGE_D = 4.035

# The operational settings of the USGS groundfailure package's jessee_2018
# model (src/gfail/models/jessee_2018.py and
# defaultconfigfiles/models/jessee_2018.ini at tag 1.3.2). None of these is in
# the paper. They are applied only when a run asks for the operational variant.
USGS_OPERATIONAL = MappingProxyType(
    {
        # Unconsolidated sediments raised from -3.22 to -1.36 (the code tests
        # for <= -3.21), "to better reflect that this unit is not actually
        # strong" -- the mixed sedimentary value.
        "unconsolidated_coefficient": -1.36,
        # CTI is clipped to the range the model was fitted over. The package
        # also declares a PGV clip of 0-211 cm/s, but only applies its clips
        # in a pre-processing hook that the shaking layers never pass through,
        # so PGV is in practice not clipped; it is not clipped here either.
        "cti_clip": (0.0, 19.0),
        # Cells at or below 2 degrees, or above 90, have zero coverage.
        "slope_min_deg": 2.0,
        "slope_max_deg": 90.0,
        # Cells shaken below 2 %g have no estimate at all (NaN).
        "pga_min_pct_g": 2.0,
        # The model's own standard deviation where no raster of it is supplied,
        # in logit units.
        "default_logit_std": 0.03,
        # Coverage is rounded to four decimal places on output.
        "round_decimals": 4,
    }
)
