"""Run settings for the liquefaction land damage step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.
"""

# Whether to run over the small Wellington pilot box. Must match the runs of the
# liquefaction hazard and the insured land extent this reads.
PILOT = True

# Which modelled earthquakes to price.
REALISATION_IDS = [0]

# Which percentile of the settled Canterbury costs to run at. A **scenario, not
# a distribution**: the 15th, 50th and 85th are the spread of settled costs
# between properties assessed at the same damage state, and the 85th runs two to
# four times the median. The model is run once per value and the three portfolio
# totals reported as a cost-assumption band, rather than the percentile riding
# as a column, because min(repair, cap) is non-linear -- a settlement computed
# from a median cost is not the median settlement.
COST_PERCENTILE = 50

# The share of properties in each land damage state that do NOT make a
# liquefaction land claim, keyed on the state (1 None to 6 Very severe).
#
# PLACEHOLDERS, TO BE TUNED. The values are a first guess by Perrie Gilbert and
# need feedback from Virginie Lacrosse and/or John Leeves (T-64, Q-16). The
# only firm expectation is that Severe and Very severe damage is always claimed.
#
# NOT APPLIED YET. The packaged Canterbury costs average over every damaged
# property, non-claimants at $0, so they already carry the drop-out (Q-17);
# drawing it again would count it twice. The step leaves the draw off while
# landloss.vul.liquefaction.costs.COSTS_INCLUDE_NON_CLAIMANTS is True, and it
# comes on when claimant-only rates replace them (T-65). Virginie Lacrosse's
# counts of damaged properties and claimants per band will validate these.
DROP_OUT_RATES = {
    1: 0.95,  # None
    2: 0.75,  # Minor
    3: 0.40,  # Moderate
    4: 0.15,  # Major
    5: 0.0,  # Severe
    6: 0.0,  # Very severe
}

# The ground each land damage state takes, drawn uniformly within (low, high)
# per property (T-55): evacuated land -- cracked or spread -- in m², and
# inundated land -- under ejecta -- as a share of the insured land.
#
# JUDGEMENT, TO BE TUNED. Read off the MBIE descriptions of each state and agreed
# on 2026-09-30 (L-39); Moderate inundation was first put at 5% to 25% and
# revised to 25% to 70% in the same call. They are to be tuned with the repair
# rates per m² that multiply them, so the modelled cost per state reproduces
# the Canterbury table (T-57).
EVACUATED_AREA_M2 = {
    1: (0.0, 0.0),  # None
    2: (1.0, 1.0),  # Minor
    3: (1.0, 1.0),  # Moderate
    4: (1.0, 10.0),  # Major
    5: (10.0, 40.0),  # Severe
    6: (40.0, 100.0),  # Very severe
}
INUNDATED_SHARE = {
    1: (0.0, 0.0),  # None
    2: (0.0, 0.0),  # Minor
    3: (0.25, 0.70),  # Moderate
    4: (0.30, 1.00),  # Major
    5: (0.30, 1.00),  # Severe
    6: (0.30, 1.00),  # Very severe
}
