"""The Nowicki Jessee et al. (2018) global coseismic landslide model, rebuilt.

A logistic regression of landslide occurrence on ln(PGV), slope, lithology, land
cover and a compound topographic index (equation 8, coefficients in Table 3),
converted to areal coverage -- the fraction of each ~250 m cell expected to be
covered by landslides -- by equation 9. It is model 1 of the landslide rebuild
note's portfolio (``src/scripts/landloss/hazard/landslide/
potential-landslide-rebuild.md``), on the large-landslide side of the size
threshold.

- :mod:`.coefficients` holds every number, from the paper, with the USGS
  operational settings kept apart.
- :mod:`.inputs` rebuilds the input layers from GMTED2010, GLiM and GlobCover
  2009 at the model's own resolutions.
- :mod:`.model` evaluates equations 8 and 9 on aligned grids.

The whole pipeline is ours; the USGS ``groundfailure`` package is used only as
the reference it is checked against, in
``src/scripts/landloss/hazard/landslide/validations/nowicki_2018/``.

Source:
    Nowicki Jessee, M.A., Hamburger, M.W., Allstadt, K., Wald, D.J., Robeson,
    S.M., Tanyaş, H., Hearne, M. & Thompson, E.M. (2018). A global empirical
    model for near-real-time assessment of seismically induced landslides.
    *JGR Earth Surface* 123, 1835-1859. doi:10.1029/2017JF004494. Held at
    ``context/lit/landslide/nowicki_jessee_2018/``.
"""

from landloss.hazard.landslide.models.nowicki_2018.inputs import (
    gen_model_grid,
    gen_model_inputs,
)
from landloss.hazard.landslide.models.nowicki_2018.model import NowickiResult, run

__all__ = ["NowickiResult", "gen_model_grid", "gen_model_inputs", "run"]
