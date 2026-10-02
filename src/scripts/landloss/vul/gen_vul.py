"""Run every vulnerability step end to end, ending at the loss module's input.

    uv run --frozen python src/scripts/landloss/vul/gen_vul.py

Reads what the exposure and hazard modules wrote, so both run first, including
the hazard module's urban pass (``gen_hazard.main_urban``), which reads the
exposure module's wall population. The damage steps per hazard and asset come
first, in any order, since none reads another; step 10 then assembles them into
the four tables the loss module reads,
``temp/vul/loss-input-<table>-w<nnn>-r<nnn>[-pilot].geoparquet``.

The extent, worlds and realisations come from ``config.py`` beside this;
anything else a step reads comes from that step's own ``config.py``. The
landslide and retaining wall steps take the exposure worlds as well as the
earthquakes, because a wall population is a draw of its own; the liquefaction
and structure steps take the earthquakes only.

The Canterbury observed damage database (liquefaction step 1) is not run. It is
the calibration evidence behind the cost rates, not a link in the chain.
"""

from scripts.landloss.pipeline import run_steps
from scripts.landloss.vul import config
from scripts.landloss.vul.landslide.culverts_bridges.steps.s11_crossing_landslide_damage import (
    gen_crossing_landslide_damage,
)
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import (
    gen_landslide_land_damage,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import (
    gen_wall_landslide_damage,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    config as liq_config,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    gen_liq_land_damage,
)
from scripts.landloss.vul.shaking.culverts_bridges.steps.s9_structure_damage_state import (
    gen_structure_damage_state,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import (
    config as wall_state_config,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import (
    gen_wall_damage_state,
)
from scripts.landloss.vul.steps.s10_property_damage import gen_property_damage


def main(*, pilot, world_ids, realisation_ids):
    """Run the vulnerability steps in order.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        world_ids: Which exposure worlds to run, for the steps that read a
            wall population or the combined landslide realisation.
        realisation_ids: Which modelled earthquakes to run.
    """
    ids = {"pilot": pilot, "realisation_ids": realisation_ids}
    worlds = {**ids, "world_ids": world_ids}
    run_steps(
        "vul",
        [
            (
                "liquefaction land s2, land damage",
                lambda: gen_liq_land_damage.main(
                    **ids, cost_percentile=liq_config.COST_PERCENTILE
                ),
            ),
            (
                "landslide land s3, damaged area",
                lambda: gen_landslide_land_damage.main(**worlds),
            ),
            (
                "shaking rw s9, wall damage state",
                lambda: gen_wall_damage_state.main(
                    **worlds, return_period_yr=wall_state_config.RETURN_PERIOD_YR
                ),
            ),
            (
                "shaking culverts and bridges s9, structure damage state",
                lambda: gen_structure_damage_state.main(**ids),
            ),
            (
                "landslide rw s11, wall landslide damage",
                lambda: gen_wall_landslide_damage.main(**worlds),
            ),
            (
                "landslide culverts and bridges s11, crossing landslide damage",
                lambda: gen_crossing_landslide_damage.main(**worlds),
            ),
            (
                "s10, the loss module's four tables",
                lambda: gen_property_damage.main(**worlds),
            ),
        ],
    )


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
