"""Run settings for the slope units step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and its git
history. The values are the contract's (section 3.3 of
`.agents/plans/urban-slope-build-contract.md`).
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Steps 3 and 4 must have been run over the same extent.
PILOT = True

# The upstream area, in hectares, at which a cell becomes a channel. The channel
# network sets the sub-basins the half-basins are cut from, so a lower threshold
# gives more, smaller units.
CHANNEL_THRESHOLD_HA = 5.0

# The thresholds the run reports a sensitivity over: the unit count and the
# median unit area at each. The layer written is the one at CHANNEL_THRESHOLD_HA.
CHANNEL_THRESHOLDS_TRIED_HA = (1.0, 5.0, 20.0)

# Neighbouring units whose circular mean aspects differ by less than this, in
# degrees, are merged while the merged unit stays under MAX_UNIT_AREA_HA.
ASPECT_MERGE_TOLERANCE_DEG = 45.0

# A unit under this area, in hectares, is absorbed into the neighbour whose
# aspect is most like its own.
MIN_UNIT_AREA_HA = 1.0

# A unit over this area, in hectares, is split in two by the variance of its
# aspect until none is over.
MAX_UNIT_AREA_HA = 50.0
