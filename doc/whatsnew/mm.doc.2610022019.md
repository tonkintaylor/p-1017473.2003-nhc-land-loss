**The retaining wall status now says how the three wall datasets are reached and used.** It
covers the GNS SLIDE mapped walls, the NHC NZMM flag and the claim reports. Only GNS
locates a wall, so it stays the only evidence on a candidate line. All three are
incomplete, each in its own way, so `p_wall` is not fitted to them. Instead they are held
out and used for a one-sided cross-validation once the face-based candidates are settled.
`apply_count_bounds` stays off until the lead decides.
