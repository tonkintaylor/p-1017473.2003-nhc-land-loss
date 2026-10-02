Packaged the Dec 2016 ILVR land liability rates as
`src/landloss/vul/liquefaction/assets/costs_liq_ld_refined_states_2011.csv`,
keyed on `LD_refined_state` 1 to 6 (None, Minor, Moderate, Major, Severe, Very
Severe) and carrying the 15th, 50th and 85th percentile costs in 2010/2011
dollars excluding GST, with a README recording the source, the band mapping, the
distinction between land damage states and land damage categories, and the
flatland-only limitation. Added
`src/scripts/landloss/vul/liquefaction/land/status.md`, which records that
liquefaction land damage is costed from observed land damage states.
