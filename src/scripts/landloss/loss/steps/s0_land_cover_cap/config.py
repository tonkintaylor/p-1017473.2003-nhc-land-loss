"""Run settings for the land cover cap.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

The policy settings are deliberately **not** here. A scenario is a value --
:class:`landloss.loss.policy.PolicySettings` -- so that two can run in the same
process and a comparison is a loop rather than two edits to a file. This step
runs the Act as it stands, which is that class's own default.
"""

# The extent to run over: "full", or a name from
# landloss.io.area_of_interest.EXTENTS. Must match the run of vul step 10, whose
# four tables this reads.
EXTENT = "wlg-pilot"

# Which modelled earthquakes to cap.
REALISATION_IDS = [0]
