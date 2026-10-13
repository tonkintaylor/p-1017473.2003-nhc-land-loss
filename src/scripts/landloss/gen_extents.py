"""Run the full model, including loss, sequentially over configured extents.

    uv run --frozen python -u src/scripts/landloss/gen_extents.py

Settings come from config.py beside this. Each extent runs ground, exposure,
hazard, vulnerability and loss before the next begins. All extent names are
checked before any work starts, and a failed stage stops the batch.
START_FROM_BY_EXTENT selects a restart step for individual extents; extents
without an entry run from the first step.
"""

from landloss.io.area_of_interest import check_extent
from scripts.landloss import config, gen_all
from scripts.landloss.loss import gen_loss


def main(*, extents, world_ids, realisation_ids, start_from_by_extent):
    """Run each extent in order with the same worlds and realisations.

    Args:
        extents: Ordered registered extent names to build.
        world_ids: Exposure worlds to run for every extent.
        realisation_ids: Earthquake realisations to run for every extent.
        start_from_by_extent: Restart module and step keyed by extent name.
    """
    for extent in extents:
        check_extent(extent)

    unknown = set(start_from_by_extent) - set(extents)
    if unknown:
        msg = f"Restart extents are not in EXTENTS: {', '.join(sorted(unknown))}"
        raise ValueError(msg)

    for number, extent in enumerate(extents, start=1):
        print(f"\nExtent {number}/{len(extents)}: {extent}", flush=True)
        ids = {
            "extent": extent,
            "world_ids": world_ids,
            "realisation_ids": realisation_ids,
        }
        gen_all.main(**ids, start_from=start_from_by_extent.get(extent))
        gen_loss.main(**ids)
        print(f"\nCompleted extent: {extent}", flush=True)


if __name__ == "__main__":
    main(
        extents=config.EXTENTS,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
        start_from_by_extent=config.START_FROM_BY_EXTENT,
    )
