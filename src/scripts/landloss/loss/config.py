"""Run settings for running the whole loss module end to end.

`gen_loss.py` beside this runs every step of the module in order. The two
settings here override each step's own `config.py`, so the whole module runs
over one extent and one set of realisations.

The policy settings are not here, and deliberately so.
:class:`landloss.loss.policy.PolicySettings` is a value rather than a module of
constants, precisely so that two scenarios can run in the same process; putting
a scenario in this file would make comparing two of them a pair of edits rather
than a loop. A step runs the Act as it stands unless it is handed otherwise.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Must match the run of vul step 10, whose four tables
# this module reads.
PILOT = True

# Which modelled earthquakes to run. Each must already have been run through the
# exposure, hazard and vulnerability modules.
REALISATION_IDS = [0]
