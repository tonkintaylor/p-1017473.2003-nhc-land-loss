"""Put a probability on each candidate wall line, and one on its condition.

Reads the candidate wall lines ``gen_wall_lines.py`` wrote and writes one row
per line carrying the probability that the line is a wall, from its source,
lowered on a rock cut, capped on the flat land and lifted where GNS mapped a
wall along it, and the probability that the wall is in poor condition, from
the dwelling age where held and otherwise from the height. Each probability
carries the rule that set it.

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_probability.py

Run ``gen_wall_lines.py`` first. This script reads nothing else: no elevation
model, no GNS layer, and no dwelling age parquet, because none is held in this
build, so ``dwelling_age_decade`` stays null and every condition probability
comes from the height or the default. The count bounds from the claim report
extraction (**T-50**) are not read either; ``apply_count_bounds`` in
`landloss.exposure.rw.wall_probability` is where they enter once held.

**Every number is judgement and none of it is evidence about Wellington.** The
GNS mapping is one-sided: it covers Wellington City only and shows only the
walls visible from above, so it raises a probability where a wall is mapped
and never lowers one where none is. The reasoning behind every number is in
`landloss.exposure.rw.wall_probability`.

This is run once. ``gen_wall_population.py`` draws each world from the file it
writes.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np

from landloss.exposure.rw.beta_population import SIZE_CLASSES
from landloss.exposure.rw.lines import SOURCES
from landloss.exposure.rw.wall_probability import (
    POOR_BASES,
    WALL_BASES,
    wall_probability_table,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_lines import (
    wall_lines_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "wall-probability"

RULE = "-" * 72


def wall_probability_path(*, pilot):
    """Return the file a run writes the probabilities to.

    Args:
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def _by(table, column, order, weights=None):
    """Return the line count, and the expected walls, by one column's values."""
    grouped = table.groupby(column, observed=True)
    out = grouped.size().to_frame("lines")
    if weights is not None:
        out["expected_walls"] = grouped[weights].sum()
    return out.reindex(order, fill_value=0)


def describe_probabilities(table):
    """Print the probabilities the worlds are drawn from."""
    print(RULE)
    p_wall = table["p_wall"].to_numpy(dtype=float)
    print(f"Candidate lines: {len(table):,}")
    if table.empty:
        return
    print(f"  expected walls: {p_wall.sum():,.0f} ({p_wall.mean():.1%} of lines)")
    quantiles = np.percentile(p_wall, [0, 25, 50, 75, 100])
    labels = ("min", "25%", "median", "75%", "max")
    print(
        "  p_wall: "
        + "   ".join(f"{k}={v:.2f}" for k, v in zip(labels, quantiles, strict=True))
    )
    print("By source:")
    print(_by(table, "source", SOURCES, weights="p_wall").to_string())
    print("By the rule that set p_wall:")
    print(_by(table, "p_wall_basis", WALL_BASES, weights="p_wall").to_string())
    print("By size class:")
    print(_by(table, "size_class", SIZE_CLASSES, weights="p_wall").to_string())
    print("By the rule that set p_poor:")
    poor = _by(table, "p_poor_basis", POOR_BASES)
    poor["p_poor"] = table.groupby("p_poor_basis", observed=True)["p_poor"].mean()
    print(poor.to_string())
    held = table["dwelling_age_decade"].notna().sum()
    print(f"Lines with a dwelling age held: {int(held):,}")


def main(*, pilot):
    """Compute the wall probabilities and write them out.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
    """
    lines_file = wall_lines_path(pilot=pilot)
    print(f"Reading the candidate wall lines from {lines_file} ...")
    lines = gpd.read_parquet(lines_file)

    table = wall_probability_table(lines)
    describe_probabilities(table)

    out_path = wall_probability_path(pilot=pilot)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(table):,} lines with probabilities to {out_path}")
    print(
        "Every number is judgement standing in for the claim report extraction "
        "(T-50); it is not evidence about Wellington."
    )


if __name__ == "__main__":
    main(pilot=config.PILOT)
