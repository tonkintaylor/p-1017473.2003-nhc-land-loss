"""Count the dwellings on every claim property.

A claim is a property, and the number of dwellings on it is the multiplier NHC
applies to both sub-caps and to the excess -- so it is what sets the retaining
wall cap. It is counted from the address points standing inside the property
boundary, one dwelling per address:

    uv run --frozen python src/scripts/landloss/exposure/steps/s3_dwellings_per_property/gen_dwellings_per_property.py

This sits at module level rather than under ``land/`` because every asset class
needs it. A retaining wall's sub-cap is per dwelling on the property it stands
on, and so is a bridge's, so the count belongs to the property rather than to
the land exposure that happens to compute it first.

What it writes is two files: the count per property, and the address-to-claim
rows behind it. The second exists because an address is how everything upstream
is keyed and a claim is how everything downstream is, and without the mapping
the two cannot be reconciled -- which address became which claim is exactly the
question anyone auditing a number will ask.

**A dwelling here is an address point, not a self-contained dwelling.** LINZ
gives a unit of a block its own address, which is what makes the count work for
flats, but it also gives one to a commercial tenancy and gives none to a minor
dwelling that was never separately addressed. The count is therefore a floor on
a block and an over-count on a mixed-use building, and it is the count the beta
runs on.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd

from landloss.domain import constants
from landloss.exposure.land.extent import (
    BOUNDARY_ROW_COLUMN,
    CLAIM_ID_COLUMN,
    DWELLING_COUNT_COLUMN,
    PROPERTY_AREA_COLUMN,
    TITLE_TYPE_COLUMN,
    build_claim_properties,
    count_dwellings,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_property_boundaries
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    fetch_extent,
    land_value_path,
)
from scripts.landloss.exposure.steps.s3_dwellings_per_property import config
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "dwellings-per-property"
ADDRESS_MAP_STEM = "address-to-claim"

# The quantiles the dwelling count is described at. Deciles would be wasted on a
# distribution that is 1 for most of its length.
SHARES = [0.5, 0.9, 0.99, 1.0]

RULE = "-" * 72


def dwellings_per_property_path(*, extent):
    """Return the file a run writes the count per property to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.parquet"


def address_to_claim_path(*, extent):
    """Return the file a run writes the address-to-claim mapping to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{ADDRESS_MAP_STEM}{suffix}.parquet"


def describe_counts(counts, addresses, properties):
    """Print how the dwellings fell across the properties."""
    print(RULE)
    print(f"Addresses: {len(addresses):,}")
    print(f"Claim properties: {len(properties):,}")
    print(f"  with at least one dwelling: {len(counts):,}")
    print(f"  with none: {len(properties) - len(counts):,}")

    dwellings = counts[DWELLING_COUNT_COLUMN]
    print(f"Dwellings counted: {int(dwellings.sum()):,}")
    outside = len(addresses) - int(dwellings.sum())
    print(
        f"  {outside:,} addresses stand outside every claim property and are "
        "counted nowhere"
    )
    print("Dwellings per property:")
    print(
        "  "
        + "  ".join(f"{int(q * 100)}%={dwellings.quantile(q):,.0f}" for q in SHARES)
    )

    print("  by size of property:")
    sizes = counts[DWELLING_COUNT_COLUMN].value_counts().sort_index()
    for dwelling_count, properties_with in sizes.head(6).items():
        print(f"    {dwelling_count} dwellings: {properties_with:,} properties")
    beyond = int(sizes[sizes.index > 6].sum())
    if beyond:
        print(f"    7 or more: {beyond:,} properties")

    if TITLE_TYPE_COLUMN in counts.columns:
        multi = counts[counts[DWELLING_COUNT_COLUMN] > 1]
        titles = multi[TITLE_TYPE_COLUMN].fillna("no title type").value_counts()
        print(f"  the {len(multi):,} properties with more than one dwelling are:")
        for title, count in titles.items():
            print(f"    {title}: {count:,}")


def main(*, extent, use_cached_extent):
    """Write the dwelling count per claim property, and the address mapping.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        use_cached_extent: Whether to reuse already-fetched LINZ layers.
    """
    value_path = land_value_path(extent=extent)
    print(f"Reading the addresses from {value_path} ...", flush=True)
    addresses = gpd.read_parquet(value_path)

    print("Fetching the property boundaries ...", flush=True)
    boundaries = get_nz_property_boundaries(
        bbox=fetch_extent(addresses),
        crs=constants.DEFAULT_CRS,
        use_cache=use_cached_extent,
    )
    boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())

    properties = build_claim_properties(boundaries)
    dwellings = count_dwellings(properties, addresses)

    counts = (
        dwellings.groupby(CLAIM_ID_COLUMN)
        .size()
        .rename(DWELLING_COUNT_COLUMN)
        .reset_index()
    )
    carried = [PROPERTY_AREA_COLUMN, BOUNDARY_ROW_COLUMN, TITLE_TYPE_COLUMN]
    counts = counts.merge(
        properties[[CLAIM_ID_COLUMN, *[c for c in carried if c in properties.columns]]],
        on=CLAIM_ID_COLUMN,
        how="left",
        validate="1:1",
    )
    describe_counts(counts, addresses, properties)

    out_path = dwellings_per_property_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(counts):,} properties to {out_path}")

    map_path = address_to_claim_path(extent=extent)
    dwellings.to_parquet(map_path)
    print(f"Wrote {len(dwellings):,} address-to-claim rows to {map_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, use_cached_extent=config.USE_CACHED_EXTENT)
