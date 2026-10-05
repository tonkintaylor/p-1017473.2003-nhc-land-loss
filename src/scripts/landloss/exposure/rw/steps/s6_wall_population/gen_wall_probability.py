"""Put the wall units' probability, a claim and a condition on each candidate wall.

Reads the wall units landslide step 12 wrote (``gen_urban_slope_wall_units.py``)
and writes one row per unit in the shape the population draw reads: its
``p_wall`` as step 12 set it (prior, GNS floor and the claim report update),
the claim it belongs to, and the probability that the wall is in poor
condition, from the height. Each probability carries the rule that set it.

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_probability.py

Run landslide step 12 first, ``gen_urban_slope_faces.py``, then step 13's
``gen_pif_cut_fill.py``, then ``gen_urban_slope_wall_units.py``
(``gen_hazard.main`` runs them in that order). The LINZ
property boundaries are read on the bbox of that step's DEM, so the cache is
shared. No dwelling age parquet is held in this build, so
``dwelling_age_decade`` stays null and every condition probability comes from
the height or the default.

**Every number is judgement and none of it is evidence about Wellington.** The
GNS mapping is one-sided: it covers Wellington City only and shows only the
walls visible from above, so it raises a probability where a wall is mapped
and never lowers one where none is. The reasoning behind every number is in
`landloss.hazard.landslide.wall_units` and
`landloss.exposure.rw.wall_probability`.

This is run once. ``gen_wall_population.py`` draws each world from the file it
writes, with the walls step 12 drew for that world.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np

from landloss.exposure.land.extent import build_claim_properties
from landloss.exposure.rw.beta_population import SIZE_CLASSES
from landloss.exposure.rw.wall_probability import (
    POOR_BASES,
    claim_of_properties,
    gen_unit_probability_table,
)
from landloss.hazard.landslide.wall_units import P_WALL_BASES, UNIT_SOURCES
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_property_boundaries
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    CRS,
    dem_bbox,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_wall_units import (
    wall_units_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "wall-probability"

# Said wherever the step 12 wall units are missing.
RUN_STEP_12_FIRST = (
    "run landslide step 12 gen_urban_slope_faces.py then "
    "gen_urban_slope_wall_units.py first"
)

RULE = "-" * 72


def wall_probability_path(*, extent):
    """Return the file a run writes the probabilities to.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def read_wall_units(*, extent):
    """The step 12 wall units, refused loudly if that step has not been run.

    Raises:
        FileNotFoundError: If the wall unit table is not written.
    """
    path = wall_units_path(extent=extent)
    if not path.exists():
        msg = f"no wall units at {path}: {RUN_STEP_12_FIRST}"
        raise FileNotFoundError(msg)
    return gpd.read_parquet(path)


def _by(table, column, order, weights=None):
    """Return the unit count, and the expected walls, by one column's values."""
    grouped = table.groupby(column, observed=True)
    out = grouped.size().to_frame("units")
    if weights is not None:
        out["expected_walls"] = grouped[weights].sum()
    return out.reindex(order, fill_value=0)


def describe_probabilities(table):
    """Print the probabilities the worlds are drawn from."""
    print(RULE)
    p_wall = table["p_wall"].to_numpy(dtype=float)
    print(f"Candidate wall units: {len(table):,}")
    if table.empty:
        return
    print(f"  expected walls: {p_wall.sum():,.0f} ({p_wall.mean():.1%} of units)")
    quantiles = np.percentile(p_wall, [0, 25, 50, 75, 100])
    labels = ("min", "25%", "median", "75%", "max")
    print(
        "  p_wall: "
        + "   ".join(f"{k}={v:.2f}" for k, v in zip(labels, quantiles, strict=True))
    )
    on_claim = table["claim_id"].notna()
    print(
        f"  on a claim: {int(on_claim.sum()):,} units, "
        f"{p_wall[on_claim.to_numpy()].sum():,.0f} expected walls"
    )
    print("By source:")
    print(_by(table, "source", UNIT_SOURCES, weights="p_wall").to_string())
    print("By the rule that set p_wall:")
    print(_by(table, "p_wall_basis", P_WALL_BASES, weights="p_wall").to_string())
    print("By size class:")
    print(_by(table, "size_class", SIZE_CLASSES, weights="p_wall").to_string())
    print("By wall position:")
    print(table["wall_position"].value_counts().to_string())
    print("By the rule that set p_poor:")
    poor = _by(table, "p_poor_basis", POOR_BASES)
    poor["p_poor"] = table.groupby("p_poor_basis", observed=True)["p_poor"].mean()
    print(poor.to_string())


def main(*, extent, use_cached_layers):
    """Put a claim and the condition on each wall unit and write them out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        use_cached_layers: Whether to reuse the cached LINZ property
            boundaries.
    """
    units = read_wall_units(extent=extent)
    print(f"Read {len(units):,} wall units from {wall_units_path(extent=extent)}")
    boundaries = get_nz_property_boundaries(
        bbox=dem_bbox(extent=extent), crs=CRS, use_cache=use_cached_layers
    )
    claim_ids = claim_of_properties(boundaries, build_claim_properties(boundaries))

    table = gen_unit_probability_table(units, claim_ids)
    describe_probabilities(table)

    out_path = wall_probability_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(table):,} wall units with probabilities to {out_path}")
    print(
        "Every number is judgement standing in for the claim report extraction "
        "(T-50); it is not evidence about Wellington."
    )


if __name__ == "__main__":
    main(extent=config.EXTENT, use_cached_layers=config.USE_CACHED_LAYERS)
