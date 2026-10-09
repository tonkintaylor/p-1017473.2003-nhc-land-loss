**A lot under 10 m2 is now rated from its neighbours.** Five addresses in the
study area stand on LINZ properties of 1 to 10 m2, and valued on their own the
clip floor -- a quarter of the authority's average land value -- spread over a
few square metres gave them rates of $15,000 to $144,000 per m2. Such a lot is
now left out of the calibration and takes the median rate of its 10 nearest
addresses with a lot of their own, with `lot_size_source` `neighbours`. The
threshold and the neighbour count are new rows in `land-value-factors.csv`.

**Multi-dwelling sites are rated as the houses around them.** A site with more
than one rating unit, or five or more addresses on its title, now takes the
median rate factor of its 10 nearest single-dwelling sites before the
calibration, so the land under an apartment block or a housing estate is priced
as the neighbouring land is. Sized per rating unit, unit-titled blocks had rated
1.4 to 2 times their neighbours; sized whole, freehold estates had rated about a
fifth of theirs. A new `rate_source` column marks the addresses rated from their
neighbours.

The calibration is now solved exactly with the value clip in place, rather than
solved, clipped and re-solved once, and the value ceiling is set per dwelling
rather than per rating unit. The single re-solve had left ordinary houses
pinned at the floor whenever very large sites dominated its first pass.
