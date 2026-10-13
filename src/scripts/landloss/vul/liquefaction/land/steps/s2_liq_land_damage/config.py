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
# Back-calculated by step 3 (s3_repair_rate_calibration) on 2026-10-12 (Perrie
# Gilbert): a 500 m² section losing the middle of each state's ranges below is
# priced at the Canterbury claimant-only median (costs_liq_ld_claimant_costs_
# 2011.csv, T-65, a calibration target only), Minor to Very severe weighted by
# claim count; then the spread fitted to the quartiles holding the median. The
# None state is not fitted and costs nothing. per_claim_nzd is the mean of the
# per-claim draw; its median is $794.
#
# The Student Volunteer Army cleared the first of every site's ejecta for
# nothing (L-40): step 3's VOLUNTEER_CLEARED_M2, 250 m², judgement -- about
# what a Moderate site is given, so Canterbury's Moderate claims cost no more
# than Minor ones, as its medians show. The inundated rate is what claims paid
# per m² beyond it; NO_SVA pays it on all the ejecta. Against Lower Hutt's
# claims priced from their own ground, both x1.42 to today, the modelled median
# over Canterbury's is in step 3's comparison output. Re-run step 3 after
# changing the area ranges, the section, the allowance or the cost table, and
# copy its values here; it says when these are stale.
REPAIR_RATES = {
    "inundated_nzd_per_m2": 3.39,
    "evacuated_nzd_per_m2": 18.57,
    "per_claim_nzd": 1207.0,
    "per_claim_sigma": 0.92,
    "volunteer_cleared_m2": 250.0,
}

# Whether ejecta is cleared without the Student Volunteer Army's unpaid labour,
# which the Canterbury costs -- and so the inundated rate fitted to them --
# carry (L-40). With volunteers, the first volunteer_cleared_m2 of each site's
# ejecta (REPAIR_RATES) is cleared for nothing, as in Canterbury; True pays for
# all of it. The loss viewer's switch does the same without a rerun.
NO_SVA = False
