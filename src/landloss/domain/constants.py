"""Constants shared across the landloss modules."""

from enum import StrEnum

# NZGD2000 / New Zealand Transverse Mercator 2000
DEFAULT_CRS = "EPSG:2193"

# Koordinates domains. T+T's own instance holds the internal layers; LINZ layers
# are served from their own domain by the same API, with a separate key.
TTGROUP_DOMAIN = "ttgroup.koordinates.com"
LINZ_DOMAIN = "data.linz.govt.nz"

# The public Koordinates catalogue, which serves third-party open data such as
# the Greater Wellington hazard layers. A separate account from the two above,
# so its key does not work on either of them.
KOORDINATES_PUBLIC_DOMAIN = "koordinates.com"

# Landcare Research's LRIS portal, another Koordinates instance, which serves
# the land cover and soils datasets. Its key is separate again.
LRIS_DOMAIN = "lris.scinfo.org.nz"

# The environment variable holding the API key for each domain.
API_KEY_ENV_VARS = {
    TTGROUP_DOMAIN: "TNT_KOORDINATES_API_KEY",
    LINZ_DOMAIN: "LINZ_API_KEY",
    KOORDINATES_PUBLIC_DOMAIN: "KOORDINATES_PUBLIC_API_KEY",
    LRIS_DOMAIN: "LRIS_API_KEY",
}

# https://data.linz.govt.nz/layer/123113-nz-addresses/
NZ_ADDRESSES_LAYER_ID = 123113

# https://data.linz.govt.nz/layer/103632-nz-river-name-lines-pilot/
# River name lines carry the ``name`` and ``feat_type`` attributes that the
# topo50 river centrelines lack, which is what lets named rivers be told apart
# from the smaller streams and creeks.
NZ_RIVER_NAME_LINES_LAYER_ID = 103632

# https://data.linz.govt.nz/layer/103631-nz-river-name-polygons-pilot/
# The areal extent of the wider rivers, which the name lines carry only as a
# centreline. A crossing test against the lines alone would miss exactly the
# rivers wide enough to need a bridge, so the culvert and bridge work reads both.
NZ_RIVER_NAME_POLYGONS_LAYER_ID = 103631

# https://data.linz.govt.nz/layer/51153-nz-coastlines-and-islands-polygons-topo-150k/
# The land polygons of the mainland and islands, from Topo50, in NZGD2000. Land
# is inside the polygon and the sea outside, which is what a water mask needs.
NZ_COASTLINE_POLYGONS_LAYER_ID = 51153

# The topo50 water layers the National Liquefaction Model's lateral spreading
# free-face layer is built from, beside the river name lines: the areas of the
# wider rivers, lakes, lagoons and swamps, and the coastline. The same IDs as
# ``common.constants`` on the NLM's lateral-spread branch, so both studies read
# the same features.
# https://data.linz.govt.nz/layer/50328-nz-river-polygons-topo-150k/
NZ_RIVER_POLYGONS_TOPO50_LAYER_ID = 50328
# https://data.linz.govt.nz/layer/50293-nz-lake-polygons-topo-150k/
NZ_LAKE_POLYGONS_TOPO50_LAYER_ID = 50293
# https://data.linz.govt.nz/layer/50292-nz-lagoon-polygons-topo-150k/
NZ_LAGOON_POLYGONS_TOPO50_LAYER_ID = 50292
# https://data.linz.govt.nz/layer/50359-nz-swamp-polygons-topo-150k/
NZ_SWAMP_POLYGONS_TOPO50_LAYER_ID = 50359
# https://data.linz.govt.nz/layer/50258-nz-coastlines-topo-150k/
NZ_COASTLINES_TOPO50_LAYER_ID = 50258

# https://lris.scinfo.org.nz/layer/123148-lcdb-v60-land-cover-database-version-60-mainland-new-zealand/
# LCDB v6.0, released October 2025. Polygons carrying a land cover class at each
# of six time steps from summer 1996/97 to summer 2023/24.
NZ_LCDB_V60_LAYER_ID = 123148

# Territorial Authority 2025 boundaries, mirrored on the T+T Koordinates
# instance. LINZ does not publish territorial authority boundaries; they
# originate from Stats NZ.
TERRITORIAL_AUTHORITY_LAYER_ID = 122409

# The four territorial authorities making up the study area, by their
# TA2025_V1_00 code, as agreed at the kick-off meeting.
STUDY_AREA_TA_CODES = {
    "044": "Porirua City",
    "045": "Upper Hutt City",
    "046": "Lower Hutt City",
    "047": "Wellington City",
}

# https://koordinates.com/layer/4069-wellington-region-earthquake-induced-slope-failure/
# Greater Wellington's earthquake-induced slope failure susceptibility zones.
GWRC_SLOPE_FAILURE_LAYER_ID = 4069

# The layer's SEVERITY column is a string, and only three of the five classes
# carry a word alongside the number. Mapping to an integer is what makes the
# classes sortable and colourable.
GWRC_SEVERITY_RANKS = {
    "1 Low": 1,
    "2": 2,
    "3 Moderate": 3,
    "4": 4,
    "5 High": 5,
}

# https://ttgroup.koordinates.com/layer/125307-wcc-earthmoving-cut-areas/
# https://ttgroup.koordinates.com/layer/125311-wcc-earthmoving-fill-areas/
# Wellington City Council's record of where subdivision earthworks cut into and
# filled over the natural ground, mirrored onto the T+T instance for this study.
# Two layers rather than one because a cut and a fill on the same site behave
# differently in an earthquake: a cut face fails by losing support from below, a
# sidling fill by sliding on the contact it was placed on.
WCC_CUT_AREAS_LAYER_ID = 125307
WCC_FILL_AREAS_LAYER_ID = 125311

# https://ttgroup.koordinates.com/layer/125308-gns-slide-morphological-data/
# GNS Science's mapped linear geomorphic features of urban Wellington -- scarps,
# cliffs, breaks in slope, drainage lines and some retaining walls -- from the
# MBIE-funded SLIDE programme, mirrored onto the T+T instance for this study.
GNS_SLIDE_MORPHOLOGY_LAYER_ID = 125308

# https://ttgroup.koordinates.com/layer/125309-gns-slide-morphological-data-genesis/
# The companion polygon layer from the same study: the process that formed each
# piece of ground -- cut slope, fill body, landfill, landslide, and so on.
# Identical to sub-layer 2 of GNS_SLIDE_SERVICE_URL below (6,401 polygons).
GNS_SLIDE_GENESIS_LAYER_ID = 125309

# The supplied earthquake-induced landslide probability grid, below the
# project's SourceMaterial folder on T:. Read by
# landloss.io.source_material.get_eil_landslide_probability; forward slashes so
# the path reads the same on any platform.
#
# One probability of slope failure per cell, on a 32 m grid covering Wellington
# (1,730,628 - 1,791,588 E, 5,409,316 - 5,459,044 N in NZTM, float32, NaN nodata,
# about 57% of cells carrying a value). The cell size is read off the file rather
# than assumed anywhere, so a resupply at another resolution needs no code change.
# Two things about it are taken from the file name rather than from
# documentation, and both need confirming with the supplier before any number
# derived from it is quoted: that "PGA2g" names the shaking level the grid is
# conditioned on, and what that level is in g. Nothing in the code depends on
# the answer -- the grid is used as supplied -- but the report cannot describe
# the result without it.
EIL_PROBABILITY_SOURCE_PATH = "EILProb_Wellington/EILProb_PGA2g.tif"

# Where a landslide model needs a magnitude or source distance, the 2,500-year
# demand is represented by the modal event in the NSHM 2022 deaggregation of
# Wellington PGA at Vs30 = 400 m/s. Hancox model 3 reads both; models driven
# only by the study's shaking do not. These beta stand-ins go when a spatial
# source model is adopted.
BETA_SCENARIO_MW = 8.1
BETA_SITE_DISTANCE_KM = 25.0

# The NZMM address land attributes extract for the four Wellington councils,
# below the project's SourceMaterial folder on T:. Read by
# landloss.io.nzmm_land_attributes.get_nzmm_land_attributes. Sensitive: it sits
# under SENSITIVE/ and is to be destroyed at the end of the project -- see that
# module's docstring.
NZMM_LAND_ATTRIBUTES_SOURCE_PATH = (
    "SENSITIVE/NZMM_ADDRESS_WellingtonTLAs_LandAttributes"
    "/NZMM_ADDRESS_WellingtonTLAs_LandAttributes.txt"
)

# QV's rating roll extract for the four Wellington councils, one file per
# council keyed by QV's district code, below the project's SourceMaterial
# folder on T:. Read by landloss.io.qv_rating_roll.get_qv_rating_roll.
# Sensitive: supplied by QV and to be destroyed at the end of the project --
# see that module's docstring. The README.md beside the files records how the
# unlabelled fields were named.
QV_RATING_ROLL_SOURCE_DIR = "SENSITIVE/_Filedrop_ Natural Hazards Data Sets"
QV_RATING_ROLL_FILES = {
    "44": "Property44_20261002.txt",  # Porirua City
    "45": "Property45_20261002.txt",  # Upper Hutt City
    "46": "Property46_20261002.txt",  # Hutt City
    "47": "Property47_20261002.txt",  # Wellington City
}

# The global datasets the Nowicki Jessee (2018) landslide model is rebuilt
# from, below the project's SourceMaterial folder on T:. Each is put there by
# a get_ script in src/scripts/landloss/hazard/landslide/static_data_gen/,
# which holds the download URL, and read by landloss.io.global_datasets.
#
# GMTED2010 tiles are 30 x 20 degrees, named by their south-west corner. Two
# products are held: 7.5 arc-second median elevation (med075), which the
# model's slope is computed from, and 30 arc-second mean elevation (mea300),
# which its CTI is computed from.
GMTED2010_SOURCE_DIR = "global/gmted2010"
GMTED2010_TILES = {
    # Wellington: 50-30 degrees S, 150-180 degrees E.
    "wellington": "50S150E",
    # The 1989 Loma Prieta earthquake, the USGS reference run: 30-50 degrees N,
    # 150-120 degrees W.
    "loma_prieta": "30N150W",
}
GMTED2010_PRODUCTS = ("med075", "mea300")

# GLiM, the 2015 CCGM edition of the global lithological map, as delivered: a
# zipped file geodatabase.
GLIM_SOURCE_PATH = "global/glim/LiMW_GIS 2015.gdb.zip"

# GlobCover 2009 v2.3, the class raster extracted from ESA's delivery zip.
GLOBCOVER2009_SOURCE_PATH = "global/globcover2009/GLOBCOVER_L4_200901_200912_V2.3.tif"

# The USGS groundfailure package's Loma Prieta test data -- its prepared
# Nowicki Jessee inputs, ShakeMap and expected output -- which the rebuilt
# model is checked against. Pinned to one tag, because a later tag may change
# the target.
USGS_GROUNDFAILURE_TAG = "1.3.2"
USGS_GROUNDFAILURE_LOMA_PRIETA_DIR = (
    f"usgs_groundfailure/{USGS_GROUNDFAILURE_TAG}/tests/data/loma_prieta"
)

# https://data.linz.govt.nz/layer/123110-nz-addresses-roads/
# The roads of the LINZ addressing dataset, the same family the address spine
# comes from. Preferred over the topographic road centrelines because a driveway
# meets the road its address is numbered on, so the geometry and the naming
# already agree with the addresses rather than having to be reconciled.
NZ_ADDRESS_ROADS_LAYER_ID = 123110

# https://data.linz.govt.nz/layer/101290-nz-building-outlines/
# LINZ's building outlines, which the insured land extent is buffered off. NHC
# settles on the land around the dwelling rather than the whole parcel, so the
# building is what the extent is measured from.
NZ_BUILDING_OUTLINES_LAYER_ID = 101290

# https://data.linz.govt.nz/layer/50318-nz-rail-station-points-topo-150k/
# The Topo50 railway stations, which the land value accessibility term measures
# each address's distance to. Topo50 rather than a timetable feed because it is
# on LINZ with the rest of the exposure data and needs no further key; whether
# it carries stations that no longer take passengers is checked in the run.
NZ_RAIL_STATION_POINTS_LAYER_ID = 50318

# https://data.linz.govt.nz/layer/122657-nz-property-boundaries/
# LINZ's best available representation of a property, built from rating units
# first, then spatialised titles, then primary parcels. It is the only layer in
# the study that says what kind of title a property is held under
# (``title_type``), which is what separates a freehold section from a unit title
# or a cross-lease -- and therefore what says whether the addresses sharing one
# building outline are separately owned land or a share of the same land.
NZ_PROPERTY_BOUNDARIES_LAYER_ID = 122657

# https://data.linz.govt.nz/table/51567-nz-property-titles-list/
# Every live and part-cancelled Record of Title, without geometry or owners: the
# same titles as the NZ Property Titles layer (50804), plus the survey plan and
# head title that the layer leaves out. Read for ``issue_date``, which the
# retaining wall age step takes as a proxy for when the dwelling was built.
NZ_PROPERTY_TITLES_LIST_TABLE_ID = 51567

# https://data.linz.govt.nz/table/114085-nz-properties-national-district-valuation-roll/
# The open subset of the District Valuation Roll: only the councils that let
# LINZ publish theirs, Christchurch among them and none of the study area. Read
# for ``building_age_indicator``, the decade code the age step is checked
# against.
NZ_DISTRICT_VALUATION_ROLL_TABLE_ID = 114085

# The National Liquefaction Model's flatland model, mirrored on the T+T
# Koordinates instance. This is the flat versus sloping land split the study
# takes from the NLM rather than rebuilding; the representation is simplified,
# which was accepted as a sensible base model (see data-sources.md).
NLM_FLATLAND_LAYER_ID = 120641

# The National Liquefaction Model's geomorphology model, also on the T+T
# instance. Carries the landform classes (``l2_geomorphology``) and the
# liquefaction susceptibility the exposure attributes are built from.
NLM_GEOMORPHOLOGY_LAYER_ID = 121398

# https://ttgroup.koordinates.com/layer/120794-gwd-median-depth/
# The National Liquefaction Model's median current groundwater depth, in metres
# below ground. A 100 m grid, national in extent but carrying a value over only
# the flat land the model covers -- about 7% of its cells -- so anything reading
# it has to decide what to assume off that footprint rather than treat the gap
# as nodata.
GWD_MEDIAN_DEPTH_LAYER_ID = 120794

# GNS Science's SLIDE geomorphology mapping of the Wellington urban area, served
# by Wellington City Council's ArcGIS instance. Public, no key, and the only
# place the near-surface materials layer is published -- the T+T instance
# mirrors only the morphology and genesis layers of the same study.
#
# Four sub-layers: 0 morphology (lines), 1 study area, 2 genesis, 3 interpreted
# materials. Mapped at nominally 1:500 from aerial photographs, LiDAR and
# limited fieldwork; see GNS Science report 2019/28. The study area is 114.6 km2
# and covers 38% of Wellington City and none of Porirua, Lower Hutt or Upper
# Hutt, so anything reading it needs a fallback off that footprint.
GNS_SLIDE_SERVICE_URL = (
    "https://gis.wcc.govt.nz/arcgis/rest/services/Environment/"
    "GNSSLIDEMorphologicalData/MapServer"
)
GNS_SLIDE_MORPHOLOGY_SUBLAYER = 0
GNS_SLIDE_STUDY_AREA_SUBLAYER = 1
GNS_SLIDE_GENESIS_SUBLAYER = 2
GNS_SLIDE_INTERPRETED_MATERIALS_SUBLAYER = 3

# GNS Science's GeoServer, which publishes its open map data as WFS and WMS with
# no key. The capabilities document (GetCapabilities) lists every layer and the
# licence for the whole service. GNS_URBAN_WELLINGTON_GEOLOGY_LAYER is the
# 1:50,000 geology of Wellington City and most of Hutt, Upper Hutt and Porirua
# (Begg & Mazengarb 1996, GNS Geological Map 22), a polygon layer in NZTM.
GNS_GEOSERVER_WFS_URL = "https://maps.gns.cri.nz/geoserver/gns/ows"
GNS_URBAN_WELLINGTON_GEOLOGY_LAYER = "gns:NZL-Urban_Wellington_geological_units"


class Cause(StrEnum):
    """The causes of financial land loss the model carries a damage measure for.

    A damage measure only means something for one cause: liquefaction settlement
    under insured land and a retaining wall shaken apart are unrelated
    relationships, and the policy settles them differently. So every row the
    vulnerability modules emit names its cause, and this is the vocabulary.

    A ``StrEnum``, so a member writes itself into a column or a file name.
    """

    LIQUEFACTION = "liquefaction"
    LANDSLIDE_EVACUATED = "landslide_evacuated"
    LANDSLIDE_INUNDATED = "landslide_inundated"
    SHAKING = "shaking"


# The seed every realisation's random draws are derived from. One project-level
# pin rather than a seed per step, because a realisation is one modelled
# earthquake across all three hazards: see landloss.hazard.realisation.
BASE_SEED = 1017473

# The seed every exposure world's draws derive from; separate from BASE_SEED
# because whether a wall exists is not something the earthquake decides.
EXPOSURE_BASE_SEED = 2003

# The urban slope model runs within this distance of a LINZ building outline,
# off the NLM flatland.
URBAN_BUILDING_DISTANCE_M = 100.0

# The cell sizes the urban failure candidates are delineated at; nesting across
# them is kept.
URBAN_SCALES_M = (1, 3, 10, 30)

# A candidate wall line with a DEM face lower than this is not modelled.
MIN_WALL_HEIGHT_M = 0.5

# Walls under this height are often built without consent and are more likely
# in poor condition.
UNCONSENTED_WALL_HEIGHT_M = 1.5

# Multiplier on every urban fragility median by config.URBAN_RATE. Medium is
# 1.0 by definition; low and high are placeholders to be set by the anchoring
# (.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md,
# section 6). A low failure rate is a higher median, so low > 1.
URBAN_RATE_FACTORS = {"low": 1.5, "medium": 1.0, "high": 1.0 / 1.5}

# The largest factor a crest, spur or face over 60 degrees divides a fragility
# median by.
TOPOGRAPHIC_AMPLIFICATION_MAX = 1.5

# Dispersion of the localised (no wall) fragility until the anchoring sets it.
LOCALISED_FRAGILITY_BETA = 0.6

# The minted id prefixes, every one in one place. Each id is the prefix and
# seven digits, minted by location (landloss.common.utils.ids).
# Candidate wall line ids, WL<7 digits>.
WALL_LINE_ID_PREFIX = "WL"
# Urban failure polygon ids, SP<7 digits>.
SLOPE_ID_PREFIX = "SP"
# Urban failure candidate ids, UC<7 digits>.
CANDIDATE_ID_PREFIX = "UC"
# Ground map polygon ids, GM<7 digits>.
GROUND_ID_PREFIX = "GM"
# Slope unit ids, SU<7 digits>.
UNIT_ID_PREFIX = "SU"
# Large-model landslide ids, LS<7 digits>, per realisation.
LARGE_LANDSLIDE_ID_PREFIX = "LS"


class NlmRelease(StrEnum):
    r"""The National Liquefaction Model core releases, as the folders name them.

    The releases live under
    ``T:\Auckland\Projects\1017473\WorkingMaterial\new_versioned_releases\core``,
    one directory per member. The folder names are not consistently punctuated --
    ``v2025p0_rc4`` has an underscore that ``v2026p0rc4`` does not -- which is
    exactly why they are listed here once rather than retyped into a path.

    A ``StrEnum``, so a member drops straight into a path join or an f-string and
    reads as the folder name it is.

    Add a member when the NLM publishes a release this study reads; the list is
    what the code has been pointed at, not everything the NLM has ever cut.
    """

    V2025P0_RC4 = "v2025p0_rc4"
    V2026P0_RC4 = "v2026p0rc4"
    V2026P0_RC6 = "v2026p0rc6"


# The National Liquefaction Model release this study reads, named once here so
# that every path reaching into the NLM's tree is built from it. The NLM turns
# releases over during the life of this study, and bumping this is how the study
# follows: there is one pin rather than one per sub-tree, so hazard layers,
# scenario grids and mapped observations cannot silently drift onto different
# releases from one another.
#
# A reader that genuinely has to stay on an older release names the member
# instead -- ``NlmRelease.V2025P0_RC4`` -- so that it is visible at the point of
# use rather than hidden in a second constant.
CORE_NLM_VERSION = NlmRelease.V2026P0_RC6

# The NLM's flatland product, under ``flatland`` in the same release tree as
# ``CORE_NLM_VERSION`` but cut on its own schedule and versioned separately from
# it -- ``V0p5``, not the ``core`` tree's ``v2026p0rc6`` -- so it needs its own
# pin rather than reusing ``CORE_NLM_VERSION``.
FLATLAND_NLM_VERSION = "V0p5"

# The cell size the study works at when deriving terrain attributes, in metres.
# The LINZ LiDAR is 1 m, but the study area is 59 by 54 km: at 1 m that is about
# 3.2 billion cells, which the amenity calculations in particular cannot carry.
# At 10 m it is about 32 million, and nothing the land value model asks of the
# terrain -- the gradient a section sits on, whether it stands above its
# surroundings, whether it can see the sea -- is decided at finer than 10 m.
# A slope feeding retaining wall exposure would need the native resolution and
# should not reuse this value.
DEM_RESOLUTION_M = 10
