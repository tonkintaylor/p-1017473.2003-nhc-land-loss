"""Run settings for the land damage probability step.

Everything that changes between one run of this step and the next, in one short
file. `gen_liq_ld_probabilities.py` beside it takes these as arguments and holds
no defaults of its own, so what a run did can be established by reading this
file and the git history of it, rather than by remembering which flags were
typed.

Step 3 reads this file too, for `PILOT`, rather than repeating the setting: it
reads the rasters this step writes, and the two disagreeing about the extent
would send it looking for a file that is not there.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Leave this True while the beta chain is being
# assembled: the pilot is 2.9 by 1.7 km against 59 by 54 km, and the National
# Liquefaction Model grids are national, so the clip is the expensive part.
PILOT = True

# Whether to apply the lateral spreading correction to P(at least Major) before
# the states are expanded (register task T-47). It reads the free faces step 1
# wrote for the same extent -- "pilot" or "study" -- so run step 1 with that
# EXTENT first.
LATERAL_SPREADING = True
