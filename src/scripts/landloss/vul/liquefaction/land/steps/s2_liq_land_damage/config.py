"""Run settings for the liquefaction land damage step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.
"""

# The extent to run over: "wlg-pilot" (the small Wellington pilot box),
# "wlg-earthworks-pilot" (Johnsonville and Newlands) or "full" (the four
# territorial authorities). Must match the runs of the liquefaction hazard and
# the insured land extent this reads.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

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

# The share of a claim's evacuated land taken to lie under its inundated land,
# so counted once in the damaged area the land cover cap is valued over (T-56):
# damaged = evacuated + inundated - overlap_share * evacuated, the overlap no
# more than the inundated land, the total no more than the insured land.
#
# ASSUMPTION, TO BE VERIFIED (L-44). Set by Perrie Gilbert on 2026-10-02 as 30%
# of the evacuated land; how the 30% overlap agreed on 2026-09-30 is measured
# has to be checked.
EVACUATED_OVERLAP_SHARE = 0.3

# What liquefied land costs to repair from the ground it lost (T-57): a rate per
# m² of inundated land, a rate per m² of evacuated land, and a fixed cost per
# claim. 2010/2011 dollars excluding GST, like the Canterbury table.
#
# PROVISIONAL, NOT A RESULT. Fitted by step 3 (s3_repair_rate_calibration) on
# 2026-10-02 to the Canterbury mean cost per state, Minor to Very severe, over
# the pilot's claims, against costs diluted with non-claimants' $0s, so the
# "per claim" cost is really per damaged property. They only re-express the
# Canterbury means per m² and are not validated; nothing settles on them. Re-run step 3 after changing the area ranges, the
# overlap or the cost table, and copy its values here; it says when these are
# out of date. The current table includes non-claimants at $0, so these rates
# are only consistent with the drop-out off, and are to be refitted against
# claimant-only costs (T-65).
REPAIR_RATES = {
    "inundated_nzd_per_m2": 10.39,
    "evacuated_nzd_per_m2": 19.66,
    "per_claim_nzd": 995.0,
}

# Whether ejecta is cleared without the Student Volunteer Army's unpaid labour,
# which the Canterbury costs -- and so the inundated rate fitted to them --
# carry (L-40). True multiplies the inundated rate by NO_SVA_INUNDATED_MULTIPLIER.
NO_SVA = False
# PLACEHOLDER, TO BE SET. How much more clearing ejecta costs without
# volunteers. A first guess by Perrie Gilbert, awaiting feedback from Virginie
# Lacrosse and/or John Leeves (T-57).
NO_SVA_INUNDATED_MULTIPLIER = 1.5
