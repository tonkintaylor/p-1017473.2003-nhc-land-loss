"""Run the hazard steps end to end, after the ground and exposure modules.

    uv run --frozen python src/scripts/landloss/hazard/gen_hazard.py

Shaking first (site class, which reads the ground module's ground map for the
cells the Foster Vs30 model leaves unclassed, PGV, then the PGA and PGV
realisations), then liquefaction (free faces, land damage probabilities, then
states), then landslide: the slope units (step 1), the Hancox 1997 coverage
(step 2), the large-model landslide realisations (step 3), the zones of each
exposure world's drawn walls (step 4), the fragility of those zones (step 5)
and the urban realisation per world and earthquake (step 6).

Landslide steps 4 to 6 read exposure rw step 6's wall units and each world's
draw of them, which read the ground module, so ``gen_all.py`` runs ground,
exposure, then this. The extent, realisations and worlds come from
``config.py`` beside this; anything else a step reads comes from that step's
own ``config.py``.

The slope failure susceptibility (step 7) and the Kritikos et al. 2015 model
(step 8) are not run here: step 3 calls the coverage model it is set to use,
and step 7 rebuilds the GWRC model for comparison against the supplied grid
rather than feeding the chain.
"""

from scripts.landloss.hazard import config
from scripts.landloss.hazard.landslide.steps.s1_slope_units import (
    config as slope_units_config,
)
from scripts.landloss.hazard.landslide.steps.s1_slope_units import gen_slope_units
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997 import (
    config as hancox_config,
)
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997 import (
    gen_hancox_1997_coverage,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import (
    config as large_config,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import (
    s1_simulate_landslides,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones import (
    config as wall_zones_config,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones import gen_wall_zones
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import (
    config as fragility_config,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import (
    gen_urban_slope_fragility,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.hazard.liquefaction.steps.s1_free_faces import (
    gen_liq_free_faces,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities import (
    config as ld_probabilities_config,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities import (
    gen_liq_ld_probabilities,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states import (
    gen_liq_ld_states,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class import gen_site_class
from scripts.landloss.hazard.shaking.steps.s3_pgv import config as pgv_config
from scripts.landloss.hazard.shaking.steps.s3_pgv import gen_pgv
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation import (
    config as pga_config,
)
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation import (
    gen_pga_realisations,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import (
    config as pgv_realisation_config,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import (
    gen_pgv_realisations,
)
from scripts.landloss.pipeline import run_steps


def main(*, extent, realisation_ids, world_ids):
    """Run the hazard steps in order.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to run.
        world_ids: Which exposure worlds to build the urban zones, fragility
            and realisations for; the worlds exposure rw step 6 draws.
    """
    ids = {"extent": extent, "realisation_ids": realisation_ids}
    run_steps(
        "hazard",
        [
            (
                "shaking s2, site class",
                lambda: gen_site_class.main(extent=extent),
            ),
            (
                "shaking s3, PGV",
                lambda: gen_pgv.main(
                    extent=extent, return_period_yr=pgv_config.RETURN_PERIOD_YR
                ),
            ),
            (
                "shaking s4, PGA realisations",
                lambda: gen_pga_realisations.main(
                    **ids, return_period_yr=pga_config.RETURN_PERIOD_YR
                ),
            ),
            (
                "shaking s5, PGV realisations",
                lambda: gen_pgv_realisations.main(
                    **ids, return_period_yr=pgv_realisation_config.RETURN_PERIOD_YR
                ),
            ),
            (
                "liquefaction s1, free faces",
                lambda: gen_liq_free_faces.main(extent=extent),
            ),
            (
                "liquefaction s2, land damage probabilities",
                lambda: gen_liq_ld_probabilities.main(
                    extent=extent,
                    lateral_spreading=ld_probabilities_config.LATERAL_SPREADING,
                ),
            ),
            (
                "liquefaction s3, land damage states",
                lambda: gen_liq_ld_states.main(**ids),
            ),
            (
                "landslide s1, slope units",
                lambda: gen_slope_units.main(
                    extent=extent,
                    channel_threshold_ha=slope_units_config.CHANNEL_THRESHOLD_HA,
                    channel_thresholds_tried_ha=slope_units_config.CHANNEL_THRESHOLDS_TRIED_HA,
                    aspect_merge_tolerance_deg=slope_units_config.ASPECT_MERGE_TOLERANCE_DEG,
                    min_unit_area_ha=slope_units_config.MIN_UNIT_AREA_HA,
                    max_unit_area_ha=slope_units_config.MAX_UNIT_AREA_HA,
                ),
            ),
            (
                "landslide s2, Hancox 1997 coverage",
                lambda: gen_hancox_1997_coverage.main(
                    extent=extent,
                    realisation_ids=realisation_ids,
                    scenario_mw=hancox_config.SCENARIO_MW,
                    site_distance_km=hancox_config.SITE_DISTANCE_KM,
                    marc_r0_km=hancox_config.MARC_R0_KM,
                    marc_fault_type=hancox_config.MARC_FAULT_TYPE,
                    marc_onshore_fraction=hancox_config.MARC_ONSHORE_FRACTION,
                    marc_modal_slope_deg=hancox_config.MARC_MODAL_SLOPE_DEG,
                    marc_a_topo=hancox_config.MARC_A_TOPO,
                ),
            ),
            (
                "landslide s3, large-model landslide realisations",
                lambda: s1_simulate_landslides.main(
                    **ids,
                    coverage_model=large_config.COVERAGE_MODEL,
                    large_min_source_area_m2=large_config.LARGE_MIN_SOURCE_AREA_M2,
                    urban_area_share=large_config.URBAN_AREA_SHARE,
                    source_aspect_ratio=large_config.SOURCE_ASPECT_RATIO,
                    crest_weight=large_config.CREST_WEIGHT,
                ),
            ),
            (
                "landslide s4, wall zones per world",
                lambda: gen_wall_zones.main(
                    extent=extent,
                    use_cached_layers=wall_zones_config.USE_CACHED_LAYERS,
                    world_ids=world_ids,
                ),
            ),
            (
                "landslide s5, urban slope fragility",
                lambda: gen_urban_slope_fragility.main(
                    extent=extent,
                    world_ids=world_ids,
                    urban_rate=fragility_config.URBAN_RATE,
                    return_period_yr=fragility_config.RETURN_PERIOD_YR,
                ),
            ),
            (
                "landslide s6, urban slope realisations",
                lambda: gen_urban_slope_realisation.main(
                    extent=extent,
                    world_ids=world_ids,
                    realisation_ids=realisation_ids,
                ),
            ),
        ],
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        world_ids=config.WORLD_IDS,
    )
