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
# APPLIED since 2026-10-08, when REPAIR_RATES were refitted to the Canterbury
# claimant-only means (T-65), so the drop-out is no longer inside the costs:
# COSTS_INCLUDE_NON_CLAIMANTS in landloss.vul.liquefaction.costs says so. The
# source of those means gave a rough likelihood of settlement per pair of
# states -- 10% for None and Minor, 60% for Moderate and Major, 100% for Severe
# and Very severe -- which these roughly agree with; it was described as a stab,
# so the placeholders are kept rather than set from it.
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
# claim, drawn per claim around its mean with a lognormal spread of
# per_claim_sigma. 2010/2011 dollars excluding GST, before the excess, per
# claim. The loss module settles on these (vul step 10 hands it area_cost_nzd).
#
# Fitted by step 3 (s3_repair_rate_calibration) on 2026-10-08 to the Canterbury
# claimant-only cost per state (costs_liq_ld_claimant_costs_2011.csv, T-65), a
# calibration target only: the three rates to the means, then the spread to the
# quartiles, all six states weighted by claim count, over the pilot's 644
# claims with the drop-out on. Modelled mean over Canterbury: None 1.19, Minor
# 0.87, Moderate 1.01, Major 0.71, Severe 1.14, Very severe 0.76. The quartiles
# of None, Minor and Moderate, 86% of the Canterbury claims, land within about
# 30%; Severe and Very severe stay too narrow, their cost being mostly area
# drawn from tight ranges (L-39).
#
# The inundated rate comes out near zero however the fit is weighted (0.09
# unweighted, 0.52 by root claim count): Canterbury paid Moderate claims
# ($1,351) barely more than Minor ($1,291), while Moderate is given 25% to 70%
# of the insured land inundated (L-39) and Minor none. Either clearing ejecta
# cost little because volunteers did it (L-40), or Moderate's inundated share is
# too high; Major and Very severe, both under-priced, point at the area ranges.
# Re-run step 3 after changing the area ranges, the overlap, the drop-out rates
# or the cost table, and copy its values here; it says when these are stale.
REPAIR_RATES = {
    "inundated_nzd_per_m2": 1.28,
    "evacuated_nzd_per_m2": 27.47,
    "per_claim_nzd": 1094.0,
    "per_claim_sigma": 1.01,
}

# Whether ejecta is cleared without the Student Volunteer Army's unpaid labour,
# which the Canterbury costs -- and so the inundated rate fitted to them --
# carry (L-40). True multiplies the inundated rate by NO_SVA_INUNDATED_MULTIPLIER.
NO_SVA = False
# How much more clearing ejecta costs without volunteers: 1 / (1 - f), where f
# is the share of the ejecta the SVA cleared at no charge, which the Canterbury
# claims therefore never paid for. After the February 2011 earthquake the SVA
# cleared about 260,000 t of an estimated 400,000 t of ejecta, f = 0.65, giving
# 2.9; a share of 50% to 75% gives 2 to 4. Rough, from public figures gathered
# by Perrie Gilbert on 2026-10-08: the SVA's tonnage may include streets and
# parks that land claims never paid for, which would put f, and the multiplier,
# lower. It corrects the volunteer effect only, not an inundated share that is
# too high (L-39).
NO_SVA_INUNDATED_MULTIPLIER = 2.9
