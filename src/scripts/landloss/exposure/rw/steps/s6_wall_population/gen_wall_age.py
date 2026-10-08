"""Put a share per age bin on every property a retaining wall can stand on.

Reads the QV rating roll's dwelling decade, exposure step 8's title and survey
plan date and its per-suburb age table, and combines them under the rules in
`landloss.exposure.rw.wall_age` into one row per LINZ property in the extent,
carrying the share of its walls in each age bin and the rule that set them:

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_age.py

**The QV rating roll is read from the T: drive**
(`landloss.io.qv_rating_roll.get_qv_rating_roll`), so this runs from a session
that can reach it. Run exposure step 8 first (``gen_rwt_age.py`` then
``table_rwt_age_by_suburb.py``) over ``AGE_EXTENT`` in ``config.py``, and
ground step 4's ``gen_slope_faces.py`` over ``EXTENT``, whose DEM bbox
the LINZ property boundaries are read on; that cache is shared with
``gen_wall_probability.py``.

The wall type draw (``.agents/plans/assigning-retaining-wall-types.md``) picks
each wall's bin from its property's shares. The rules and the 20 year gap that
marks a rebuilt dwelling are judgement.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import pandas as pd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN
from landloss.exposure.land.extent import build_claim_properties
from landloss.exposure.rw import age
from landloss.exposure.rw.wall_age import (
    AGE_BASES,
    AGE_BASIS_COLUMN,
    AGE_SHARE_COLUMNS,
    PROPERTY_ID_COLUMN,
    combine_wall_ages,
    own_lot_dates,
    property_qv_ages,
)
from landloss.exposure.rw.wall_probability import claim_of_properties
from landloss.io.area_of_interest import extent_suffix
from landloss.io.qv_rating_roll import get_qv_rating_roll
from landloss.io.readers import get_nz_property_boundaries
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age.gen_rwt_age import (
    rwt_age_path,
)
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age.table_rwt_age_by_suburb import (
    SUBURB_COLUMNS,
    table_path,
)
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    CRS,
    dem_bbox,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "wall-age"

# Said wherever exposure step 8's outputs are missing.
RUN_STEP_8_FIRST = (
    "run exposure step 8 gen_rwt_age.py then table_rwt_age_by_suburb.py "
    "over AGE_EXTENT first"
)

# The step 8 columns read: the lot's date, bin and the rule that set them, and
# the suburb that keys the fallback table.
AGE_COLUMNS = [
    CLAIM_ID_COLUMN,
    *SUBURB_COLUMNS,
    age.EST_YEAR_COLUMN,
    age.AGE_BIN_COLUMN,
    age.AGE_BASIS_COLUMN,
]
PROPERTIES_COLUMN = "properties"

RULE = "-" * 72


def wall_age_path(*, extent):
    """Return the file a run writes the property age shares to.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.parquet"


def _require(path):
    """Refuse loudly a step 8 output that is not written.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        msg = f"no {path}: {RUN_STEP_8_FIRST}"
        raise FileNotFoundError(msg)
    return path


def property_lot_ages(claim_ids, *, age_extent):
    """Step 8's lot date, bin and suburb of each property, through its claim.

    Args:
        claim_ids: The claim per property, from ``claim_of_properties``.
        age_extent: The extent step 8 was run over.

    Returns:
        Indexed by ``property_id``, the suburb columns, ``est_year``,
        ``age_bin`` and ``age_basis`` of each property on a claim step 8 wrote.
    """
    ages = pd.read_parquet(
        _require(rwt_age_path(extent=age_extent)), columns=AGE_COLUMNS
    )
    ages = ages.set_index(ages[CLAIM_ID_COLUMN].astype(str)).drop(
        columns=CLAIM_ID_COLUMN
    )
    ages = ages[~ages.index.duplicated()]
    claims = claim_ids.astype(str)
    on_claim = claims[claims.isin(ages.index)]
    out = ages.loc[on_claim.to_numpy()]
    out.index = on_claim.index.rename(PROPERTY_ID_COLUMN)
    return out


def suburb_shares(lot_ages, suburbs):
    """The suburb share per bin of each property step 8 gave a suburb.

    Args:
        lot_ages: Output of :func:`property_lot_ages`.
        suburbs: Step 8's per-suburb age table.

    Returns:
        Indexed by ``property_id``, the share per bin, NaN where the suburb is
        not in the table.
    """
    keyed = suburbs.set_index(SUBURB_COLUMNS)[list(AGE_SHARE_COLUMNS)]
    keys = pd.MultiIndex.from_frame(lot_ages[SUBURB_COLUMNS])
    return pd.DataFrame(
        keyed.reindex(keys).to_numpy(),
        index=lot_ages.index,
        columns=list(AGE_SHARE_COLUMNS),
    )


def extent_shares(lot_ages, suburbs):
    """The share per bin over the extent, for a property with no suburb.

    The mean of the shares of the suburbs the extent's properties are in,
    weighted by each suburb's dated properties; every suburb in the table where
    none of them is.

    Args:
        lot_ages: Output of :func:`property_lot_ages`.
        suburbs: Step 8's per-suburb age table.

    Returns:
        The share per bin, indexed by ``AGE_SHARE_COLUMNS``, summing to 1.
    """
    present = pd.MultiIndex.from_frame(suburbs[SUBURB_COLUMNS]).isin(
        pd.MultiIndex.from_frame(lot_ages[SUBURB_COLUMNS])
    )
    table = suburbs[present] if present.any() else suburbs
    table = table.dropna(subset=list(AGE_SHARE_COLUMNS))
    weights = table[PROPERTIES_COLUMN].astype(float)
    shares = table[list(AGE_SHARE_COLUMNS)].mul(weights, axis=0).sum() / weights.sum()
    return shares / shares.sum()


def describe_ages(ages):
    """Print how the properties were aged and their mean shares."""
    print(RULE)
    print(f"Properties aged: {len(ages):,}")
    print("By the rule that set the shares:")
    print(
        ages[AGE_BASIS_COLUMN]
        .value_counts()
        .reindex(AGE_BASES, fill_value=0)
        .to_string()
    )
    print("Mean share per bin:")
    print(ages[list(AGE_SHARE_COLUMNS)].mean().round(3).to_string())


def main(*, extent, age_extent):
    """Combine the dwelling, lot and suburb ages of every property and write them.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        age_extent: The extent exposure step 8 was run over, whose property
            ages and per-suburb table are read.
    """
    # The cache gen_wall_probability.py fetches on the same bbox; refresh it
    # there with USE_CACHED_LAYERS.
    boundaries = get_nz_property_boundaries(
        bbox=dem_bbox(extent=extent), crs=CRS, use_cache=True
    )
    claim_ids = claim_of_properties(boundaries, build_claim_properties(boundaries))
    print(
        f"Read {len(boundaries):,} LINZ property boundaries, {len(claim_ids):,} on a claim"
    )

    qv = property_qv_ages(get_qv_rating_roll(), boundaries)
    lot_ages = property_lot_ages(claim_ids, age_extent=age_extent)
    # Only a lot's own title or plan date; a neighbourhood year goes to the
    # suburb tier.
    titles = own_lot_dates(lot_ages)
    suburbs = pd.read_csv(_require(table_path("suburb", extent=age_extent)))
    # Every property in the extent is in the fallback, with no shares where
    # step 8 gave it no suburb, so each one gets a row.
    fallback = suburb_shares(lot_ages, suburbs).reindex(claim_ids.index)

    ages = combine_wall_ages(qv, titles, fallback, extent_shares(lot_ages, suburbs))
    ages = ages[ages.index.isin(claim_ids.index)]
    describe_ages(ages)

    out_path = wall_age_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ages.to_parquet(out_path)
    print(RULE)
    print(f"Wrote the age shares of {len(ages):,} properties to {out_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, age_extent=config.AGE_EXTENT)
