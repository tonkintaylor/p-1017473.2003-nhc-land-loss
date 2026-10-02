"""Estimate when each claim property's retaining walls were built.

Reads the claim properties exposure step 3 counted dwellings on, dates each one
from the issue date of its titles and the survey plan its lot is on, under the
rules in `landloss.exposure.rw.age`, and writes one row per property carrying
the year, the age bin and the rule that set it:

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s8_infer_rwt_age/gen_rwt_age.py

Run exposure step 3 (``gen_dwellings_per_property.py``) first, over the same
extent, which ``EXTENT`` in ``config.py`` beside this script must match. Needs
``LINZ_API_KEY`` in ``.env``: the NZ Property Boundaries layer and the NZ
Property Titles List table are read from LINZ, both CC BY 4.0, so anything
published from the output credits Land Information New Zealand.

Every claim in the fetched extent is dated, not only those with a dwelling,
because the plan dates are fitted, and each property's neighbours read, from
all of them, the same way the Christchurch validation does. Only the properties
with a dwelling are written.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.exposure.land.extent import (
    CLAIM_ID_COLUMN,
    DWELLING_COUNT_COLUMN,
    TITLE_TYPE_COLUMN,
    build_claim_properties,
)
from landloss.exposure.rw import age
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_property_boundaries, get_nz_property_titles_list
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    fetch_extent,
    land_value_path,
)
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age import config
from scripts.landloss.exposure.steps.s3_dwellings_per_property.gen_dwellings_per_property import (
    address_to_claim_path,
    dwellings_per_property_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "rwt-age"

# The plan numbers whose fitted dates are printed, as a check on the fit: the
# pre-2001 Wellington district series, then the national series.
CHECK_PLANS = (
    1_000,
    10_000,
    30_000,
    60_000,
    90_000,
    300_000,
    400_000,
    500_000,
    600_000,
)

RULE = "-" * 72


def rwt_age_path(*, extent):
    """Return the file a run writes the property ages to.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def describe_fit(boundaries, titles):
    """Print the fitted date of a few plan numbers in the Wellington district."""
    fit = age.fit_dp_years(boundaries, age.title_issue_years(titles))
    print(RULE)
    for district, curve in fit.groupby(age.LAND_DISTRICT_COLUMN):
        if len(curve) < len(CHECK_PLANS):
            continue
        plans = np.array(CHECK_PLANS, dtype=float)
        years = np.interp(plans, curve[age.DP_COLUMN], curve[age.DP_YEAR_COLUMN])
        dated = "  ".join(
            f"DP {plan:,.0f}: {year:.0f}"
            for plan, year in zip(plans, years, strict=True)
        )
        print(f"Plan dates fitted in {district} from {len(curve):,} plans:")
        print(f"  {dated}")


def describe_ages(ages):
    """Print how the properties were dated and how they fall in the bins."""
    print(RULE)
    print(f"Properties with a dwelling dated: {len(ages):,}")
    print("By the rule that set the year:")
    print(ages[age.AGE_BASIS_COLUMN].value_counts(dropna=False).to_string())
    print("By bin:")
    bins = (
        ages[age.AGE_BIN_COLUMN]
        .value_counts(dropna=False)
        .reindex([*age.AGE_BINS, np.nan])
    )
    print((bins / len(ages)).round(3).to_string())


def main(*, extent, use_cached_extent):
    """Date every claim property and write the ones with a dwelling.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        use_cached_extent: Whether to reuse already-fetched LINZ boundaries.
    """
    value_path = land_value_path(extent=extent)
    print(f"Reading the addresses from {value_path} ...", flush=True)
    addresses = gpd.read_parquet(value_path)
    dwellings = pd.read_parquet(dwellings_per_property_path(extent=extent))
    claim_addresses = pd.read_parquet(address_to_claim_path(extent=extent))

    print("Fetching the property boundaries ...", flush=True)
    boundaries = get_nz_property_boundaries(
        bbox=fetch_extent(addresses),
        crs=constants.DEFAULT_CRS,
        use_cache=use_cached_extent,
    )
    boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())
    claims = build_claim_properties(boundaries)

    print("Reading the NZ Property Titles List ...", flush=True)
    titles = get_nz_property_titles_list()
    describe_fit(boundaries, titles)

    print("Dating the claim properties ...", flush=True)
    ages = age.infer_claim_ages(claims, boundaries, titles, id_column=CLAIM_ID_COLUMN)

    suburbs = age.claim_suburbs(claim_addresses, addresses, CLAIM_ID_COLUMN)
    out = (
        dwellings[[CLAIM_ID_COLUMN, DWELLING_COUNT_COLUMN, TITLE_TYPE_COLUMN]]
        .join(suburbs, on=CLAIM_ID_COLUMN)
        .merge(ages, on=CLAIM_ID_COLUMN, how="left", validate="1:1")
    )
    geometry = claims.set_index(CLAIM_ID_COLUMN).geometry
    out = gpd.GeoDataFrame(
        out, geometry=geometry.reindex(out[CLAIM_ID_COLUMN]).to_numpy(), crs=claims.crs
    )
    describe_ages(out)

    out_path = rwt_age_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(out):,} property ages to {out_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, use_cached_extent=config.USE_CACHED_EXTENT)
