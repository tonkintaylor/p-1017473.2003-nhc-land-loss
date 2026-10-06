"""Run every exposure step end to end.

    uv run --frozen python src/scripts/landloss/exposure/gen_exposure.py

The address spine, the terrain, accessibility and amenity attributes and the land value
per address, the insured land extent and the dwellings on each claim, then the
retaining wall population in four steps -- the candidate wall lines, a
probability on each, the age shares of each property, and one draw per
exposure world -- and the crossing
population per realisation. The extent, worlds and realisations come from
``config.py`` beside this; anything else a step reads, such as whether to reuse
a cached download, comes from that step's own ``config.py``.

The candidate wall lines read the terrain rasters, ground map and urban slope
candidates that landslide steps 3, 4 and 6 write, so ``gen_hazard.main`` runs
before this module; ``gen_all.py`` holds that order. The wall probability and
population read the wall units and their draws from landslide step 12, which
``gen_hazard.main`` runs (faces, then step 13's pif cut and fill, then the wall
units); without it, run ``gen_urban_slope_faces.py``,
``gen_pif_cut_fill.py`` and ``gen_urban_slope_wall_units.py`` by hand first, or
the wall probability stops and says so. The property age shares read the QV
rating roll from the T: drive and exposure step 8's property ages, which no
orchestrator runs: run ``gen_rwt_age.py`` and ``table_rwt_age_by_suburb.py``
by hand first, or the age step stops and says so.
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
    gen_wall_lines,
    gen_wall_population,
    gen_wall_probability,
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
                ),
            ),
            (
                "s3, dwellings per property",
                lambda: gen_dwellings_per_property.main(
                    extent=extent, use_cached_extent=dwellings_config.USE_CACHED_EXTENT
                ),
            ),
            (
                "rw s6, candidate wall lines",
                lambda: gen_wall_lines.main(
                    extent=extent,
                    use_cached_layers=wall_config.USE_CACHED_LAYERS,
                    road_distance_m=wall_config.ROAD_FRONTAGE_DISTANCE_M,
                ),
            ),
            (
                "rw s6, wall probability",
                lambda: gen_wall_probability.main(
                    extent=extent, use_cached_layers=wall_config.USE_CACHED_LAYERS
                ),
            ),
            (
                "rw s6, wall age",
                lambda: gen_wall_age.main(
                    extent=extent, age_extent=wall_config.AGE_EXTENT
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
