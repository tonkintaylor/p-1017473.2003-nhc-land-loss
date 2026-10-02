"""Run the whole pipeline end to end: hazard, exposure, hazard urban, then vul.

    uv run --frozen python src/scripts/landloss/gen_all.py

Each module runs through its own ``gen_<module>.py``, with the extent, worlds
and realisations set in ``config.py`` beside this, so every module runs over
the same ground, the same wall populations and the same earthquakes. It ends
at the four tables the loss module reads,
``temp/vul/loss-input-<table>-w<nnn>-r<nnn>[-pilot].geoparquet``; the loss
module itself is not run from here.

The hazard module runs twice because the urban slope chain crosses modules
both ways. Its first pass (``gen_hazard.main``) builds the shaking, the
liquefaction and the landslide ground work (terrain, ground map, slope units,
urban slope candidates) and the large landslide model, none of which reads an
exposure output. The exposure module's wall lines then read those landslide
layers, and its wall population is drawn per world. The hazard module's second
pass (``gen_hazard.main_urban``) reconciles the urban slope polygons to the
wall lines, assigns each polygon its fragility for the walls of each world,
and draws the urban realisation, so it can only run after exposure. The
vulnerability module reads everything above.
"""

from scripts.landloss import config
from scripts.landloss.exposure import gen_exposure
from scripts.landloss.hazard import gen_hazard
from scripts.landloss.vul import gen_vul


def main(*, pilot, world_ids, realisation_ids):
    """Run every module in order: hazard, exposure, hazard urban, vul.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        world_ids: Which exposure worlds to draw and run.
        realisation_ids: Which modelled earthquakes to run.
    """
    ids = {"pilot": pilot, "world_ids": world_ids, "realisation_ids": realisation_ids}
    gen_hazard.main(**ids)
    gen_exposure.main(**ids)
    gen_hazard.main_urban(**ids)
    gen_vul.main(**ids)


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
