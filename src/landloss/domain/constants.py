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

# https://data.linz.govt.nz/layer/122657-nz-property-boundaries/
# LINZ's best available representation of a property, built from rating units
# first, then spatialised titles, then primary parcels. It is the only layer in
# the study that says what kind of title a property is held under
# (``title_type``), which is what separates a freehold section from a unit title
# or a cross-lease -- and therefore what says whether the addresses sharing one
# building outline are separately owned land or a share of the same land.
NZ_PROPERTY_BOUNDARIES_LAYER_ID = 122657

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
