"""Run the ground steps end to end: what the ground is, once per extent.

    uv run --frozen python src/scripts/landloss/ground/gen_ground.py

The ground module comes first in ``gen_all.py``, before exposure and hazard,
because both read it and it depends on no exposure world and no earthquake:

1. the 1 m DEM, the multiscale slope and aspect and the terrain derivatives
   (step 1), which every module reads;
2. the ground map (step 2), read by shaking step 2 and the landslide steps;
3. the instability zones (step 3): the pips, pifs and their pieces, the siz
   test and the elements on the 1 m DEM, which skips itself when its last run
   still holds;
4. the slope faces (step 4): the wall evidence read onto each pif;
5. the pif cut and fill (step 5), which exposure rw step 6's wall units read.

The extent comes from ``config.py`` beside this; anything else a step reads
comes from that step's own ``config.py``.
"""

from scripts.landloss.ground import config
from scripts.landloss.ground.steps.s1_terrain import config as terrain_config
from scripts.landloss.ground.steps.s1_terrain import (
    gen_multiscale_slope,
    gen_terrain_derivatives,
)
from scripts.landloss.ground.steps.s2_ground_map import config as ground_map_config
from scripts.landloss.ground.steps.s2_ground_map import gen_ground_map
from scripts.landloss.ground.steps.s3_instability_zones import (
    config as zones_config,
)
from scripts.landloss.ground.steps.s3_instability_zones import gen_instability_zones
from scripts.landloss.ground.steps.s4_slope_faces import config as faces_config
from scripts.landloss.ground.steps.s4_slope_faces import gen_slope_faces
from scripts.landloss.ground.steps.s5_pif_cut_fill import config as cut_fill_config
from scripts.landloss.ground.steps.s5_pif_cut_fill import gen_pif_cut_fill
from scripts.landloss.pipeline import run_steps


def main(*, extent):
    """Run the ground steps in order.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
    """
    run_steps(
        "ground",
        [
            (
                "s1, multiscale slope and aspect",
                lambda: gen_multiscale_slope.main(
                    extent=extent,
                    resolutions_m=terrain_config.RESOLUTIONS_M,
                    slope_resolutions_m=terrain_config.SLOPE_RESOLUTIONS_M,
                    use_cached_dem=terrain_config.USE_CACHED_DEM,
                ),
            ),
            (
                "s1, terrain derivatives",
                lambda: gen_terrain_derivatives.main(
                    extent=extent,
                    residual_base_resolutions_m=terrain_config.RESIDUAL_BASE_RESOLUTIONS_M,
                    topographic_position_windows_m=terrain_config.TOPOGRAPHIC_POSITION_WINDOWS_M,
                ),
            ),
            (
                "s2, ground map",
                lambda: gen_ground_map.main(
                    extent=extent,
                    use_cached_layers=ground_map_config.USE_CACHED_LAYERS,
                    default_gw_depth_m=ground_map_config.DEFAULT_GROUNDWATER_DEPTH_M,
                    residual_modification_threshold_m=ground_map_config.RESIDUAL_MODIFICATION_THRESHOLD_M,
                ),
            ),
            (
                "s3, instability zones",
                lambda: gen_instability_zones.main(
                    extent=extent,
                    use_cached_layers=zones_config.USE_CACHED_LAYERS,
                    rebuild=zones_config.REBUILD,
                    max_bends=zones_config.WALL_MAX_BENDS,
                    stray_tolerance_m=zones_config.WALL_STRAY_TOLERANCE_M,
                    min_segment_m=zones_config.WALL_MIN_SEGMENT_M,
                    max_turn_deg=zones_config.MAX_TOTAL_TURN_DEG,
                    end_window_m=zones_config.PIF_END_WINDOW_M,
                    wall_height_reach_m=zones_config.WALL_HEIGHT_REACH_M,
                    wall_height_quantile=zones_config.WALL_HEIGHT_QUANTILE,
                    building_reach_m=zones_config.BUILDING_REACH_M,
                    max_untiled_cells=zones_config.MAX_UNTILED_CELLS,
                    tile_core_m=zones_config.TILE_CORE_M,
                    tile_margin_m=zones_config.TILE_MARGIN_M,
                    tile_crop_pad_m=zones_config.TILE_CROP_PAD_M,
                    tile_workers=zones_config.TILE_WORKERS,
                ),
            ),
            (
                "s4, slope faces",
                lambda: gen_slope_faces.main(
                    extent=extent,
                    use_cached_layers=faces_config.USE_CACHED_LAYERS,
                    gns_wall_match_m=faces_config.GNS_WALL_MATCH_M,
                    manual_wall_duplicate_m=faces_config.MANUAL_WALL_DUPLICATE_M,
                    search_m=faces_config.SEARCH_M,
                    gns_only_min_length_m=faces_config.GNS_ONLY_MIN_LENGTH_M,
                    max_bends=faces_config.WALL_MAX_BENDS,
                    stray_tolerance_m=faces_config.WALL_STRAY_TOLERANCE_M,
                    max_turn_deg=faces_config.MAX_TOTAL_TURN_DEG,
                    wall_max_length_m=faces_config.WALL_MAX_LENGTH_M,
                ),
            ),
            (
                "s5, pif cut and fill",
                lambda: gen_pif_cut_fill.main(
                    extent=extent,
                    use_cached_layers=cut_fill_config.USE_CACHED_LAYERS,
                ),
            ),
        ],
    )


if __name__ == "__main__":
    main(extent=config.EXTENT)
