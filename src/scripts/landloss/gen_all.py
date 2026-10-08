"""Run the whole pipeline end to end: ground, exposure, hazard, then vul.

    uv run --frozen python src/scripts/landloss/gen_all.py

Each module runs through its own ``gen_<module>.py``, with the extent, worlds
and realisations set in ``config.py`` beside this, so every module runs over
the same ground, the same wall populations and the same earthquakes. It ends
at the four tables the loss module reads,
``temp/vul/loss-input-<table>-w<nnn>-r<nnn><suffix>.geoparquet``, where the
suffix is ``extent_suffix(extent)``: none for the full study, ``-pilot`` for
the Wellington pilot. The loss module itself is not run from here.

The modules run in the order they read each other. The ground module
(``gen_ground.main``) builds what the ground is, once per extent: the 1 m DEM
and terrain, the ground map, the instability zones (pips to elements), the
wall evidence on each pif and the pif cut and fill. The exposure module reads
it for the wall units and draws which of them are walled in each world. The
hazard module then builds the shaking, the liquefaction and the landslide
hazard, whose urban zones are built for each world's drawn walls. The
vulnerability module reads everything above.
"""

from landloss.io.area_of_interest import check_extent
from scripts.landloss import config, pipeline
from scripts.landloss.exposure import gen_exposure
from scripts.landloss.ground import gen_ground
from scripts.landloss.hazard import gen_hazard
from scripts.landloss.vul import gen_vul


def main(*, extent, world_ids, realisation_ids, start_from):
    """Run every module in order: ground, exposure, hazard, vul.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: Which exposure worlds to draw and run.
        realisation_ids: Which modelled earthquakes to run.
        start_from: None to run everything, or the module and step to start
            at (``config.START_FROM``; :func:`pipeline.starting_from`).
    """
    check_extent(extent)
    ids = {"extent": extent, "world_ids": world_ids, "realisation_ids": realisation_ids}
    with pipeline.starting_from(start_from):
        gen_ground.main(extent=extent)
        gen_exposure.main(**ids)
        gen_hazard.main(**ids)
        gen_vul.main(**ids)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
        start_from=config.START_FROM,
    )
