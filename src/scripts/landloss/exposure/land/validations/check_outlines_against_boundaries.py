"""Check whether building outlines stay inside one property, or straddle several.

The insured land extent splits a building that straddles a property boundary
into one part per property, because a terrace of townhouses captured as a single
polygon across five freehold sections really is five buildings on five pieces of
land. This script measures how often that happens, and checks that the extent's
threshold is catching the cases that matter.

    uv run --frozen python src/scripts/landloss/exposure/land/validations/check_outlines_against_boundaries.py

The measure is **how much of each outline the single best-covering property
accounts for**. That is the right question rather than a count of boundaries
intersected, for two reasons:

- A property polygon that clips the corner of a neighbouring outline by a few
  centimetres is capture noise between two independently digitised layers, not a
  building on two titles. So the test is an area, with a floor in square metres
  as well as a share.
- An apartment block carries one unit title polygon per unit, **all on the same
  footprint**. Every one of them covers the whole outline, so the best coverage
  is near 100% and the block is correctly read as sitting in one property, even
  though it intersects dozens of boundaries.

An outline the best property covers only half of is a building on two pieces of
land. The run prints how many there are, how much ground sits outside the best
property, and -- the part that connects to the insured land extent -- how many
of them the sharing rule actually attached to more than one address.

It reports rather than asserts. A building straddling a boundary is a real thing
and LINZ captures it faithfully; what is wrong is this repository assuming it
never happens.

Needs ``LINZ_API_KEY`` in ``.env``, and the land value output on disk -- run
``src/scripts/landloss/exposure/land/steps/s2_land_value/s4_estimate_land_value.py``
first if it is not there.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.exposure.land.extent import (
    CLAIM_ID_COLUMN,
    OUTLINE_ID_COLUMN,
    assign_buildings_to_properties,
    build_claim_properties,
    drop_non_residential_buildings,
)
from landloss.io.readers import get_nz_building_outlines, get_nz_property_boundaries
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import config
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    fetch_extent,
    land_value_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TITLE_TYPE_COLUMN = "title_type"

# What the boundaries layer leaves on a property built from a parcel rather than
# from a rating unit or a spatialised title.
UNTITLED = "no title type"

# What counts as properly crossing rather than clipping. Both have to be passed:
# a share, so a large building is not condemned by a small absolute overhang,
# and an area, so a tiny shed is not condemned by a large relative one. Five
# square metres is well beyond any disagreement between two layers digitised
# from different sources, and 10% of a house is a room.
MIN_OUTSIDE_AREA_M2 = 5.0
MIN_OUTSIDE_SHARE = 0.10

# The quantiles the coverage distribution is described at.
DECILES = [0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]

RULE = "-" * 72


def best_property_coverage(buildings, boundaries):
    """Return how much of each outline its best-covering property accounts for.

    Args:
        buildings: The building outlines, carrying :data:`OUTLINE_ID_COLUMN`.
        boundaries: The property boundaries.

    Returns:
        One row per outline that meets a property, carrying the outline's own
        area, the area the best property covers, and that as a share. Outlines
        meeting no property are absent.
    """
    pieces = gpd.overlay(
        buildings[[OUTLINE_ID_COLUMN, buildings.geometry.name]],
        boundaries[[boundaries.geometry.name]],
        how="intersection",
        keep_geom_type=True,
    )
    if pieces.empty:
        return pd.DataFrame(
            columns=[OUTLINE_ID_COLUMN, "outline_area_m2", "covered_m2", "share"]
        )

    pieces = pieces.assign(_covered=pieces.geometry.area)
    # The single best property, not the sum: summing would count an apartment
    # block's stacked unit titles once per title and make every block look
    # perfectly covered several times over.
    best = pieces.groupby(OUTLINE_ID_COLUMN)["_covered"].max()

    areas = buildings.set_index(OUTLINE_ID_COLUMN).geometry.area
    coverage = pd.DataFrame({"covered_m2": best}).join(
        areas.rename("outline_area_m2"), how="left"
    )
    coverage["share"] = coverage["covered_m2"] / coverage["outline_area_m2"]
    coverage["outside_m2"] = coverage["outline_area_m2"] - coverage["covered_m2"]
    return coverage.reset_index()


def describe_coverage(coverage, buildings):
    """Print how well one property covers each outline."""
    print(RULE)
    print(f"Building outlines: {len(buildings):,}")
    missing = len(buildings) - len(coverage)
    print(f"  {missing:,} meet no property boundary at all")
    if coverage.empty:
        return

    quantiles = coverage["share"].quantile(DECILES)
    print("Share of each outline covered by its single best property:")
    print("  " + "  ".join(f"{q * 100:>4.0f}%={v:.1%}" for q, v in quantiles.items()))


def describe_crossings(coverage):
    """Print the outlines that properly straddle a boundary, and by how much.

    Returns:
        The outline identifiers that cross, for the caller to cross-reference.
    """
    outside_enough = coverage["outside_m2"] >= MIN_OUTSIDE_AREA_M2
    share_enough = (1 - coverage["share"]) >= MIN_OUTSIDE_SHARE
    crossing = coverage[outside_enough & share_enough]
    clipping = coverage[~(outside_enough & share_enough) & (coverage["share"] < 1.0)]

    print(RULE)
    print(
        f"Properly crossing a boundary -- at least {MIN_OUTSIDE_AREA_M2:,.0f} m2 "
        f"and {MIN_OUTSIDE_SHARE:.0%} of the outline outside its best property:"
    )
    print(f"  {len(crossing):,} of {len(coverage):,} outlines")
    if not crossing.empty:
        print(
            f"  they put {crossing['outside_m2'].sum():,.0f} m2 of building on a "
            "second property, median "
            f"{crossing['outside_m2'].median():,.1f} m2 each"
        )
        print(
            "  best-property share over those: "
            f"median {crossing['share'].median():.0%}, "
            f"lowest {crossing['share'].min():.0%}"
        )
    print(
        f"  {len(clipping):,} more overlap a second property by less than that, "
        "which is two layers digitised from different sources disagreeing"
    )
    if not clipping.empty:
        # Printed because the distinction between a building on two titles and
        # two layers disagreeing is the whole question, and a median in
        # centimetres-worth of area is what settles it.
        print(
            f"  those sit {clipping['outside_m2'].median():,.2f} m2 outside at "
            f"the median and {clipping['outside_m2'].quantile(0.9):,.2f} m2 at "
            "the 90th percentile"
        )
    return set(crossing[OUTLINE_ID_COLUMN])


def describe_crossing_titles(crossing_ids, buildings, boundaries):
    """Print what kinds of title the crossing outlines sit across.

    A building across two **unit titles** is an apartment block whose polygons
    happen not to coincide, and merging its addresses is right. A building
    across two **freehold** titles is a semi-detached pair or a terrace on
    separate sections, and merging those is wrong.
    """
    print(RULE)
    print("What the crossing outlines sit across:")
    if not crossing_ids:
        print("  none")
        return

    crossing = buildings[buildings[OUTLINE_ID_COLUMN].isin(crossing_ids)]
    pieces = gpd.overlay(
        crossing[[OUTLINE_ID_COLUMN, crossing.geometry.name]],
        boundaries[[TITLE_TYPE_COLUMN, boundaries.geometry.name]],
        how="intersection",
        keep_geom_type=True,
    )
    # Only the properties taking a real share of the building, so a clipped
    # corner does not decide what the outline is said to straddle.
    pieces = pieces[pieces.geometry.area >= MIN_OUTSIDE_AREA_M2]
    # A boundary built from a parcel rather than a rating unit or a title
    # carries no title type at all, and has to be named rather than dropped.
    pieces = pieces.assign(
        **{
            TITLE_TYPE_COLUMN: pieces[TITLE_TYPE_COLUMN]
            .fillna(UNTITLED)
            .replace("", UNTITLED)
        }
    )
    kinds = pieces.groupby(OUTLINE_ID_COLUMN)[TITLE_TYPE_COLUMN].agg(
        lambda types: " + ".join(sorted(set(types)))
    )
    counts = kinds.value_counts()
    counts.index.name = "title types the outline spans"
    print(
        pd.DataFrame(
            {"outlines": counts, "share": (counts / len(kinds)).map("{:.1%}".format)}
        ).to_string()
    )


def describe_effect_on_extent(crossing_ids, parts):
    """Print how many crossing outlines the extent actually split.

    This is the link between a fact about two LINZ layers and what the insured
    land extent does with it. An outline that straddles two properties is two
    buildings on two pieces of land, and the extent is built to split it; an
    outline that merely overhangs is left whole on the property holding most of
    it. The two counts below say how often each happened.
    """
    per_outline = parts.groupby(OUTLINE_ID_COLUMN)[CLAIM_ID_COLUMN].nunique()
    split = set(per_outline[per_outline > 1].index)

    print(RULE)
    print(f"Outlines standing on a claim property: {len(per_outline):,}")
    print(f"  {len(split):,} were split across more than one property")
    missed = crossing_ids & set(per_outline.index) - split
    print(
        f"  {len(missed):,} cross a boundary by the measure above but were not "
        "split, the second property carrying no dwelling and so no claim"
    )
    print(
        f"  {len(split - crossing_ids):,} were split although they overhang "
        "nothing -- they stand inside two claim properties that overlap each "
        "other, which the extent's exact-duplicate dissolve does not catch"
    )


def main(*, extent):
    """Report the building outlines that straddle a property boundary."""
    addresses = gpd.read_parquet(land_value_path(extent=extent))
    bbox = fetch_extent(addresses)

    print("Fetching the building outlines ...", flush=True)
    buildings = get_nz_building_outlines(bbox=bbox, crs=constants.DEFAULT_CRS)
    print("Fetching the property boundaries ...", flush=True)
    boundaries = get_nz_property_boundaries(bbox=bbox, crs=constants.DEFAULT_CRS)

    # Both layers carry the odd self-intersecting ring, which overlay refuses.
    buildings = buildings.set_geometry(buildings.geometry.make_valid())
    boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())
    # The same use filter the extent is built with, for the same reason the
    # claim properties are used below rather than the raw boundaries: this has
    # to measure the population that is actually buffered.
    buildings = drop_non_residential_buildings(buildings)
    buildings = buildings.reset_index(drop=True)
    buildings[OUTLINE_ID_COLUMN] = np.arange(len(buildings))

    print(RULE)
    print(f"Property boundaries over the extent: {len(boundaries):,}")

    # Measured against the claim properties rather than the raw boundaries, so
    # this and the extent look at the same thing: a road parcel is a boundary
    # but never a claim, and a building against the road reserve would otherwise
    # appear to straddle something.
    properties = build_claim_properties(boundaries)
    print(f"Claim properties: {len(properties):,}")

    coverage = best_property_coverage(buildings, properties)
    describe_coverage(coverage, buildings)
    crossing_ids = describe_crossings(coverage)
    describe_crossing_titles(crossing_ids, buildings, properties)

    parts = assign_buildings_to_properties(buildings, properties)
    describe_effect_on_extent(crossing_ids, parts)

    print(RULE)
    print(
        "A building on two titles is a real thing and LINZ captures it "
        "faithfully. The insured land extent splits one, so the two counts above "
        "are the same population seen from either side."
    )


if __name__ == "__main__":
    main(extent=config.EXTENT)
