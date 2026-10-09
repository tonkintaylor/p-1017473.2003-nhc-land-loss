r"""Model 2: the fuzzy-logic coseismic landslide hazard model of Kritikos et al.

Kritikos, Robinson & Davies (2015) built a relative landslide hazard model for
regions with no landslide inventory and no geotechnical data. It needs three
inputs -- shaking intensity, a DEM and an active fault map -- and scores each
cell from 0 to 1 by combining four fuzzy memberships with a fuzzy gamma
operator (``.agents/plans/building-kritikos-2015-landslide-model.md``).

- :mod:`.memberships` holds the paper's average membership curves, digitised
  from its Figure 5.
- :mod:`.inputs` builds the 60 m slope, slope position and fault distance the
  memberships read.
- :mod:`.model` combines the memberships into the relative hazard.
- :mod:`.evaluation` scores a hazard map against an inventory and fits the
  transfer function from relative hazard to coverage.

The output is a **relative** hazard, "an order-of-magnitude estimate only" in
the authors' words, and the model is a large-landslide model: it does not
represent cut, fill or retaining.

Source:
    [kritikos_2015] Kritikos, T., Robinson, T.R. & Davies, T.R.H. (2015).
    Regional coseismic landslide hazard assessment without historical
    landslide inventories: a new approach. *JGR Earth Surface* 120, 711-729.
    doi:10.1002/2014JF003224. Summarised at
    ``context/lit/landslide/kritikos_2015/``; the PDF is held at
    ``U:\\MAMI\\Literature``.
"""
