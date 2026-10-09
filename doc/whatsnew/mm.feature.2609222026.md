Added step 6 of the exposure model, a stand-in retaining wall population at
`src/scripts/landloss/exposure/rw/steps/s6_wall_population/`. It draws at most
one wall per insured property against a slope-driven prevalence, sizes it by
retained height into the agreed small, medium and large classes, gives it a
modern or poor initial condition, and places it as a line along the contour.
Over the pilot box that is 758 walls over 4,764 properties.

The population is a beta stand-in for a model that does not exist yet, so every
public name in `landloss.exposure.rw.beta_population` carries a `beta` prefix and
the run says plainly that the output is not evidence about Wellington. Prevalence
is calibrated against nothing; the SME estimate by suburb (**T-19**) is what
replaces it.
