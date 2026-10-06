"""Run the hazard steps end to end, in two passes around the exposure module.

    uv run --frozen python src/scripts/landloss/hazard/gen_hazard.py

:func:`main` runs everything that reads no exposure: first the landslide
multiscale slope, terrain derivatives and ground map (shaking step 2 reads the
ground map's materials for the cells the Foster Vs30 model leaves unclassed),
then shaking (site class, PGV, then the PGA and PGV realisations), liquefaction
(free faces, land damage probabilities, then states), then the rest of the
landslide ground work -- the slope units, the urban slope candidates, step
12's urban slope faces, step 13's pif cut and fill (which the wall units read), and step 12's wall units (drawn per exposure world) and
per-world zones -- and last the large-model landslide realisations,
which read only hazard outputs. Exposure rw step 6 reads step 12's wall units,
so they are built in this pass. The extent, realisations and worlds come from ``config.py``
beside this; anything else a step reads comes from that step's own
``config.py``.

:func:`main_urban` runs the rest of the landslide chain, steps 8 and 9: the
fragility of each world's urban failure polygons (step 12's zones of that
world's wall draw) and the urban realisation per world and earthquake. These
read the exposure module's drawn walls and wall population, so the hazard
module no longer runs in one pass before or after exposure: ``gen_all.py``
runs :func:`main`, then the exposure module (whose wall population reads step
12's draw), then :func:`main_urban`, then vul. Running this file runs
:func:`main` only: it redraws the wall units, and step 8 stops on zones and
drawn walls from different draws, so run ``gen_all.py`` for the whole chain,
or the exposure module and then :func:`main_urban` by hand. Step 7's
polygons are no longer built; step 12's zones replace them.

The slope failure susceptibility step is not run: nothing downstream reads it
yet, as it rebuilds the GWRC model for comparison against the supplied grid
rather than feeding the chain.
"""

from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    config as wall_population_config,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import gen_wall_age
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
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    config as faces_config,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    gen_urban_slope_faces,
    gen_urban_slope_wall_units,
    gen_urban_slope_wall_zones,
)
from scripts.landloss.hazard.landslide.steps.s13_pif_cut_fill import (
    config as cut_fill_config,
)
from scripts.landloss.hazard.landslide.steps.s13_pif_cut_fill import (
    gen_pif_cut_fill,
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
    """Run the hazard steps that read no exposure, in order.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to run.
        world_ids: Which exposure worlds to draw the step 12 wall units for
            and build their zones; the worlds exposure rw step 6 populates.
    """
    ids = {"extent": extent, "realisation_ids": realisation_ids}
    run_steps(
        "hazard",
        [
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
                "landslide s12, urban slope faces",
                lambda: gen_urban_slope_faces.main(
                    extent=extent,
                    use_cached_layers=faces_config.USE_CACHED_LAYERS,
                    gns_wall_match_m=faces_config.GNS_WALL_MATCH_M,
                    search_m=faces_config.SEARCH_M,
                    gns_only_min_length_m=faces_config.GNS_ONLY_MIN_LENGTH_M,
                    end_window_m=faces_config.PIF_END_WINDOW_M,
                    max_bends=faces_config.WALL_MAX_BENDS,
                    stray_tolerance_m=faces_config.WALL_STRAY_TOLERANCE_M,
                    min_segment_m=faces_config.WALL_MIN_SEGMENT_M,
                    max_turn_deg=faces_config.MAX_TOTAL_TURN_DEG,
                    wall_max_length_m=faces_config.WALL_MAX_LENGTH_M,
                    wall_height_reach_m=faces_config.WALL_HEIGHT_REACH_M,
                    wall_height_quantile=faces_config.WALL_HEIGHT_QUANTILE,
                ),
            ),
            (
                # The wall age shares give the wall points their age (the lead,
                # 2026-10-07); they read QV (on T:), exposure step 8 and the
                # LINZ properties on the step 3 DEM's bbox, none of step 12, so
                # they run here, before the wall units.
                "rw s6, wall age",
                lambda: gen_wall_age.main(
                    extent=extent, age_extent=wall_population_config.AGE_EXTENT
                ),
            ),
            (
                "landslide s13, pif cut and fill",
                lambda: gen_pif_cut_fill.main(
                    extent=extent,
                    use_cached_layers=cut_fill_config.USE_CACHED_LAYERS,
                ),
            ),
            (
                "landslide s12, wall units",
                lambda: gen_urban_slope_wall_units.main(
                    extent=extent,
                    use_cached_layers=faces_config.USE_CACHED_LAYERS,
                    max_bends=faces_config.WALL_MAX_BENDS,
                    min_segment_m=faces_config.WALL_MIN_SEGMENT_M,
                    max_length_m=faces_config.WALL_MAX_LENGTH_M,
                    max_turn_deg=faces_config.MAX_TOTAL_TURN_DEG,
                    holdout_share=faces_config.CLAIM_HOLDOUT_SHARE,
                    holdout_seed=faces_config.CLAIM_HOLDOUT_SEED,
                    world_ids=world_ids,
                ),
            ),
            (
                "landslide s12, wall zones per world",
                lambda: gen_urban_slope_wall_zones.main(
                    extent=extent,
                    use_cached_layers=faces_config.USE_CACHED_LAYERS,
                    world_ids=world_ids,
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
    """Run the urban slope chain, landslide steps 8 and 9, after exposure.

    Step 8 reads step 12's zones of each world's wall draw (built in
    :func:`main`) and exposure rw step 6's drawn walls of the same draw; step
    7's polygons are not built, as step 12's zones replace them.

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
        "8 and 9, gen_hazard.main_urban) reads the exposure module's drawn walls "
        "and wall population, which must be redrawn from these wall units "
        "first: run gen_all.py, or exposure/gen_exposure.py and then "
        "gen_hazard.main_urban."
    )
