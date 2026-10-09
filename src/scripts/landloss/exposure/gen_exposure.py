"""Run every exposure step end to end, after the ground module.

    uv run --frozen python src/scripts/landloss/exposure/gen_exposure.py

The address spine, the terrain, accessibility and amenity attributes and the land value
per address, the insured land extent and the dwellings on each claim, then the
retaining wall population -- the wall age shares, the wall units (the pif
pieces and GNS-only walls of the ground module, each drawn walled or not per
exposure world), a probability on each unit and the population per world --
and the crossing population per realisation. The extent, worlds and
realisations come from ``config.py`` beside this; anything else a step reads,
such as whether to reuse a cached download, comes from that step's own
``config.py``.

The wall units read the ground module's siz table, GNS-only walls and pif cut
and fill, so ``gen_ground.py`` runs before this module and ``gen_all.py`` holds
that order. The hazard module's urban zones read the wall draws written here,
so it runs after. The property age shares read the QV rating roll from the T:
drive and exposure step 8's property ages, which no orchestrator runs: run
``gen_rwt_age.py`` and ``table_rwt_age_by_suburb.py`` by hand first, or the
age step stops and says so.
"""

from scripts.landloss.exposure import config
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population import (
    config as crossing_config,
)
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population import (
    gen_crossing_population,
)
from scripts.landloss.exposure.land.steps.s2_land_value import (
    config as land_value_config,
)
from scripts.landloss.exposure.land.steps.s2_land_value import (
    s1_build_terrain_attributes,
    s2_build_accessibility,
    s3_build_amenity,
    s4_estimate_land_value,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    config as insured_land_config,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    gen_insured_land,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    config as wall_config,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_age,
    gen_wall_population,
    gen_wall_probability,
    gen_wall_units,
)
from scripts.landloss.exposure.steps.s1_address_spine import (
    config as spine_config,
)
from scripts.landloss.exposure.steps.s1_address_spine import (
    s1_build_address_spine,
)
from scripts.landloss.exposure.steps.s3_dwellings_per_property import (
    config as dwellings_config,
)
from scripts.landloss.exposure.steps.s3_dwellings_per_property import (
    gen_dwellings_per_property,
)
from scripts.landloss.pipeline import run_steps


def main(*, extent, realisation_ids, world_ids):
    """Run the exposure steps in order.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which modelled earthquakes to draw the crossing
            population for.
        world_ids: Which exposure worlds to draw the retaining wall
            population for.
    """
    run_steps(
        "exposure",
        [
            (
                "s1, address spine",
                lambda: s1_build_address_spine.main(
                    extent=extent, fresh=spine_config.FRESH, out=spine_config.OUT
                ),
            ),
            (
                "land s2, terrain attributes",
                lambda: s1_build_terrain_attributes.main(
                    extent=extent,
                    fresh=land_value_config.FRESH,
                    spine=land_value_config.SPINE,
                    out=land_value_config.TERRAIN,
                    window=land_value_config.WINDOW_M,
                ),
            ),
            (
                "land s2, accessibility",
                lambda: s2_build_accessibility.main(
                    extent=extent,
                    fresh=land_value_config.FRESH,
                    spine=land_value_config.SPINE,
                    out=land_value_config.ACCESSIBILITY,
                ),
            ),
            (
                "land s2, amenity",
                lambda: s3_build_amenity.main(
                    extent=extent,
                    fresh=land_value_config.FRESH,
                    spine=land_value_config.SPINE,
                    out=land_value_config.AMENITY,
                ),
            ),
            (
                "land s2, land value per address",
                lambda: s4_estimate_land_value.main(
                    extent=extent,
                    fresh=land_value_config.FRESH,
                    spine=land_value_config.SPINE,
                    terrain=land_value_config.TERRAIN,
                    accessibility=land_value_config.ACCESSIBILITY,
                    amenity=land_value_config.AMENITY,
                    out=land_value_config.LAND_VALUE_OUT,
                    cohorts=land_value_config.COHORTS_OUT,
                ),
            ),
            (
                "land s5, insured land extent",
                lambda: gen_insured_land.main(
                    extent=extent,
                    use_cached_extent=insured_land_config.USE_CACHED_EXTENT,
                    residential_rule=insured_land_config.RESIDENTIAL_RULE,
                    max_dwelling_footprint_m2=(
                        insured_land_config.MAX_DWELLING_FOOTPRINT_M2
                    ),
                    min_crossing_area_m2=insured_land_config.MIN_CROSSING_AREA_M2,
                    min_crossing_share=insured_land_config.MIN_CROSSING_SHARE,
                    driveway_half_width_m=(insured_land_config.DRIVEWAY_HALF_WIDTH_M),
                    max_driveway_length_m=(insured_land_config.MAX_DRIVEWAY_LENGTH_M),
                ),
            ),
            (
                "s3, dwellings per property",
                lambda: gen_dwellings_per_property.main(
                    extent=extent, use_cached_extent=dwellings_config.USE_CACHED_EXTENT
                ),
            ),
            (
                # The wall age shares give the wall units their age (the lead,
                # 2026-10-07); they read QV (on T:), exposure step 8 and the
                # LINZ properties, so they run before the wall units.
                "rw s6, wall age",
                lambda: gen_wall_age.main(
                    extent=extent, age_extent=wall_config.AGE_EXTENT
                ),
            ),
            (
                "rw s6, wall units",
                lambda: gen_wall_units.main(
                    extent=extent,
                    use_cached_layers=wall_config.USE_CACHED_LAYERS,
                    max_bends=wall_config.WALL_MAX_BENDS,
                    min_segment_m=wall_config.WALL_MIN_SEGMENT_M,
                    max_length_m=wall_config.WALL_MAX_LENGTH_M,
                    max_turn_deg=wall_config.MAX_TOTAL_TURN_DEG,
                    holdout_share=wall_config.CLAIM_HOLDOUT_SHARE,
                    holdout_seed=wall_config.CLAIM_HOLDOUT_SEED,
                    world_ids=world_ids,
                ),
            ),
            (
                "rw s6, wall probability",
                lambda: gen_wall_probability.main(
                    extent=extent, use_cached_layers=wall_config.USE_CACHED_LAYERS
                ),
            ),
            (
                "rw s6, wall population",
                lambda: gen_wall_population.main(extent=extent, world_ids=world_ids),
            ),
            (
                "culverts and bridges s7, crossing population",
                lambda: gen_crossing_population.main(
                    extent=extent,
                    realisation_ids=realisation_ids,
                    use_cached_extent=crossing_config.USE_CACHED_EXTENT,
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
