"""Run settings for the Kritikos (2015) relative hazard step."""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# One hazard grid is written per shaking realisation because the MM membership
# reads that realisation's PGV.
REALISATION_IDS = [0]

# The gamma of the fuzzy gamma operator. The paper uses 0.9; 0.8 is its
# sensitivity.
GAMMA = 0.9

# The TPI neighbourhood width in metres. The paper does not state one, so this
# is a judgement: 600 m is 11 cells at 60 m. Run 300 and 1200 as sensitivities.
TPI_WINDOW_M = 600.0

# The standard deviation TPI is standardised by, in metres, or None to take it
# from the extent being run. None makes the classes depend on the extent, so
# fix it to the full-study value once that is known.
TPI_SD_M = None

# "mapped" measures distance to the mapped active faults in the NZ Active Faults
# Database; "far_field" holds the fault term at its far-field value everywhere,
# which is the plan's proposal for the base case under an interface scenario
# (no mapped fault ruptures). The decisions table of the plan names "mapped"
# as the base case until the lead decides.
FAULT_TERM = "mapped"

# The events the hazard-to-coverage transfer function is fitted on, from
# validations/kritikos_2015/event_inputs.EVENTS: the two the paper's memberships
# were derived from, so that model 2 stays independent of Kaikoura, which is
# where the portfolio is tested (the plan's phase 6). The curve is fitted with
# this file's GAMMA, TPI_WINDOW_M and FAULT_TERM, and the hazard script refuses
# a curve fitted with different ones.
FIT_EVENTS = ["northridge", "wenchuan"]

# How far the fitting study area extends beyond each inventory's bounding box,
# in metres. The paper does not define one; the AUC reproduction found it moves
# the score more than anything else, and it moves the low-hazard end of the
# coverage curve the same way.
FIT_MARGIN_M = 0.0

# The number of hazard bins the curve is fitted over.
FIT_N_BINS = 20

# Reuse downloaded event inputs and the per-event GFDB cache.
USE_CACHE = True
