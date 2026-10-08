"""Run settings for the Hancox (1997) large-landslide coverage step."""

from landloss.domain import constants

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# One coverage grid is written per shaking realisation because the Hancox MM
# threshold reads that realisation's PGV.
REALISATION_IDS = [0]

# The magnitude and site distance used only by Hancox's relationships that have
# no shaking input. The study's PGV supplies Modified Mercalli intensity.
SCENARIO_MW = constants.BETA_SCENARIO_MW
SITE_DISTANCE_KM = constants.BETA_SITE_DISTANCE_KM

# Marc et al. (2016) settings for the event-wide landslide area. These are the
# plan's central Hikurangi interface sensitivity, not a final source model:
# replace them with NSHM interface geometry when it is available. With every
# asperity counted onshore they are an upper case for this depth.
MARC_R0_KM = 22.5
MARC_FAULT_TYPE = "R"
MARC_ONSHORE_FRACTION = 1.0
MARC_MODAL_SLOPE_DEG = 22.0
MARC_A_TOPO = 1.0
