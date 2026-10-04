"""Run the hazard steps end to end, in two passes around the exposure module.

    uv run --frozen python src/scripts/landloss/hazard/gen_hazard.py

:func:`main` runs everything that reads no exposure: shaking (site class, PGV,
then the PGA and PGV realisations), liquefaction, then the landslide ground
work -- the multiscale slope and terrain derivatives, the ground map, the slope
units, the urban slope candidates -- and last the large-model landslide
realisations, which read only hazard outputs. The extent, realisations and
worlds come from ``config.py`` beside this; anything else a step reads comes
from that step's own ``config.py``.

:func:`main_urban` runs the rest of the landslide chain, steps 7 to 9: the
urban failure polygons, their fragility per exposure world, and the urban
realisation per world and earthquake. These read the exposure module's wall
lines and wall population, so the hazard module no longer runs in one pass
before or after exposure: ``gen_all.py`` runs :func:`main`, then the exposure
module (whose wall lines read the landslide ground work), then
:func:`main_urban`, then vul. Running this file runs :func:`main` only: it can
renumber or reshape the urban slope candidates, and step 7 reconciles them to
wall lines the exposure module drew from the candidates before, so running
:func:`main_urban` straight after it would build the polygons on stale lines
without an error. Run ``gen_all.py`` for the whole chain, or the exposure
module and then :func:`main_urban` by hand.

The slope failure susceptibility step is not run: nothing downstream reads it
yet, as it rebuilds the GWRC model for comparison against the supplied grid
rather than feeding the chain.
"""

from scripts.landloss.hazard import config
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import (
    config as large_config,
)
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import (
    s1_simulate_landslides,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    config as slope_config,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_multiscale_slope,
    gen_terrain_derivatives,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map import (
    config as ground_map_config,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map import gen_ground_map
from scripts.landloss.hazard.landslide.steps.s5_slope_units import (
    config as slope_units_config,
)
from scripts.landloss.hazard.landslide.steps.s5_slope_units import gen_slope_units
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates import (
    config as candidates_config,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates import (
    gen_urban_slope_candidates,
)
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons import (
    config as polygons_config,
)
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons import (
    gen_urban_slope_polygons,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    config as fragility_config,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    gen_urban_slope_fragility,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import (
    gen_urban_slope_realisation,
)
from scripts.landloss.hazard.landslide.steps.s10_hancox_1997 import (
    config as hancox_config,
)
from scripts.landloss.hazard.landslide.steps.s10_hancox_1997 import (
    gen_hancox_1997_coverage,
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
    """Run the hazard steps that read no exposure, in order.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to run.
        world_ids: Which exposure worlds to run. Unused by this pass, which
            draws nothing per world; carried so the two passes take the same
            arguments and ``gen_all.py`` passes one setting to both.
    """
    del world_ids
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
                "liquefaction s2, land damage probabilities",
                lambda: gen_liq_ld_probabilities.main(extent=extent),
            ),
            (
                "liquefaction s3, land damage states",
                lambda: gen_liq_ld_states.main(**ids),
            ),
            (
                "landslide s3, multiscale slope and aspect",
                lambda: gen_multiscale_slope.main(
                    extent=extent,
                    resolutions_m=slope_config.RESOLUTIONS_M,
                    use_cached_dem=slope_config.USE_CACHED_DEM,
                ),
            ),
            (
                "landslide s3, terrain derivatives",
                lambda: gen_terrain_derivatives.main(
                    extent=extent,
                    use_cached_dsm=slope_config.USE_CACHED_DSM,
                    face_height_windows_m=slope_config.FACE_HEIGHT_WINDOWS_M,
                    residual_base_resolutions_m=slope_config.RESIDUAL_BASE_RESOLUTIONS_M,
                    topographic_position_windows_m=slope_config.TOPOGRAPHIC_POSITION_WINDOWS_M,
                    curvature_resolution_m=slope_config.CURVATURE_RESOLUTION_M,
                ),
            ),
            (
                "landslide s4, ground map",
                lambda: gen_ground_map.main(
                    extent=extent,
                    use_cached_layers=ground_map_config.USE_CACHED_LAYERS,
                    default_gw_depth_m=ground_map_config.DEFAULT_GROUNDWATER_DEPTH_M,
                    residual_modification_threshold_m=ground_map_config.RESIDUAL_MODIFICATION_THRESHOLD_M,
                ),
            ),
            (
                "landslide s5, slope units",
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
                "landslide s6, urban slope candidates",
                lambda: gen_urban_slope_candidates.main(
                    extent=extent,
                    use_cached_layers=candidates_config.USE_CACHED_LAYERS,
                    scales_m=candidates_config.SCALES_M,
                    building_distance_m=candidates_config.BUILDING_DISTANCE_M,
                    min_patch_cells=candidates_config.MIN_PATCH_CELLS,
                    max_patch_length_m=candidates_config.MAX_PATCH_LENGTH_M,
                ),
            ),
            (
                "landslide s10, Hancox 1997 coverage",
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
                "landslide s1, large-model landslide realisations",
                lambda: s1_simulate_landslides.main(
                    **ids,
                    coverage_model=large_config.COVERAGE_MODEL,
                    large_min_source_area_m2=large_config.LARGE_MIN_SOURCE_AREA_M2,
                    urban_area_share=large_config.URBAN_AREA_SHARE,
                    source_aspect_ratio=large_config.SOURCE_ASPECT_RATIO,
                    crest_weight=large_config.CREST_WEIGHT,
                ),
            ),
        ],
    )


def main_urban(*, extent, realisation_ids, world_ids):
    """Run the urban slope chain, landslide steps 7 to 9, after exposure.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to run.
        world_ids: Which exposure worlds to run.
    """
    run_steps(
        "hazard urban",
        [
            (
                "landslide s7, urban slope polygons",
                lambda: gen_urban_slope_polygons.main(
                    extent=extent,
                    use_cached_layers=polygons_config.USE_CACHED_LAYERS,
                    road_half_width_m=polygons_config.ROAD_HALF_WIDTH_M,
                ),
            ),
            (
                "landslide s8, urban slope fragility",
                lambda: gen_urban_slope_fragility.main(
                    extent=extent,
                    world_ids=world_ids,
                    urban_rate=fragility_config.URBAN_RATE,
                    return_period_yr=fragility_config.RETURN_PERIOD_YR,
                ),
            ),
            (
                "landslide s9, urban slope realisations",
                lambda: gen_urban_slope_realisation.main(
                    extent=extent,
                    world_ids=world_ids,
                    realisation_ids=realisation_ids,
                ),
            ),
        ],
    )


if __name__ == "__main__":
    settings = {
        "extent": config.EXTENT,
        "realisation_ids": config.REALISATION_IDS,
        "world_ids": config.WORLD_IDS,
    }
    main(**settings)
    print("-" * 72)
    print(
        "Ran the first hazard pass only. The urban slope chain (landslide steps "
        "7 to 9, gen_hazard.main_urban) reads the exposure module's wall lines "
        "and wall population, which must be rebuilt from these candidates "
        "first: run gen_all.py, or exposure/gen_exposure.py and then "
        "gen_hazard.main_urban."
    )
