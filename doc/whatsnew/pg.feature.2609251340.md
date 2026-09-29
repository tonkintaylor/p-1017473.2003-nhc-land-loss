**A new wall is never smaller than the one the site already had.** Where a claim
carries a damaged wall and landslide ground beyond what repairing it reinstates,
sizing the new wall on the leftover area alone could propose a garden edge
beside a two-metre structure. `at_least_the_existing_wall` floors the size class,
and the length is floored at the existing wall's, on the reasoning that the
ground has already shown what it needs. A claim with no wall is not floored.

It bites on 3 of the pilot's 39 invented walls -- the other 36 are on claims with
no wall at all -- and takes new walls from $1.23 m to $1.25 m. The settlement
total does not move, because those three already settle at their cap. It will
matter more as the retaining wall population grows.

**The static viewer gained a basemap and lost two bugs.** Leaflet draws the map
now, with four key-free basemaps -- light grey, aerial, topographic and
OpenStreetMap -- and a *None* option that makes the page work with no network at
all. Tiles are the only thing on the page that reaches the internet; no claim
data ever leaves it.

The two bugs were worth recording. The dots were coloured with CSS custom
properties, which a canvas cannot resolve, so the fills were silently dropped --
every colour is now a literal hex. And the first basemap was CARTO's, which now
requires an API key, and a key embedded in a file handed to a client is a
problem of its own.

The viewer also gained the average settlement per claim, over all claims and
over the paid ones. They differ by nearly a factor of two on the pilot, $2,993
against $5,753, because almost half the claims are paid nothing -- so both are
labelled with the denominator they use.

`gen_viewer_stress_data.py` writes a region-sized file to find out where the page
slows down: **98,263 claims over the four territorial authorities, 10.2 MB**. The
geography is real -- every dot is an address exposure found, with its own land
rate and slope -- and the damage is drawn from the pilot, preserving its exact
claim mix so the histograms are exercised properly. It is synthetic, it says so
in its name, and it is gitignored.

`report/loss/loss_method_summary.typ` is a two-page method note for a
non-technical reader, with all 23 assumptions numbered so a meeting can take
them one at a time and record a decision against each.
