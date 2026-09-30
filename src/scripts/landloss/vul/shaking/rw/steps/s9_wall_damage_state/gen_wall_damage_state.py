"""Decide which retaining walls the shaking wrote off.

Reads the wall population and the realisation's PGA field, and draws a damage
state per wall against its probability of failure.

    uv run --frozen python src/scripts/landloss/vul/shaking/rw/steps/s9_wall_damage_state/gen_wall_damage_state.py

Two damage states only, **no damage** and **replace**. Repair is not modelled
because very few damaged walls are repaired in practice, so the state is a coin
weighted by the fragility rather than a position on a scale.

The fragility returns a **probability of failure at the ground motion the wall
saw**, which is what a fragility curve is, and the state is a draw against it.
That stays true however well the shaking field is resolved.

The beta's fragility is one flat number for every wall,
:data:`~landloss.vul.shaking.fragility.BETA_FAILURE_PROBABILITY`. It ignores the
wall's size class, its initial condition and the acceleration it saw, all three
of which the population and the PGA field already carry -- so when the published
curves arrive the inputs are there and only the probability changes. The PGA is
sampled and reported now for that reason, and because a run that never looked at
the hazard would not notice a wall sitting outside it.

**No cost is attached.** The loss module prices a written-off wall from its
undepreciated value, so what this writes is the state, not the money.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd

from landloss.common.utils.terrain import sample_at_points
from landloss.domain import constants
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    REALISATION_ID_COLUMN,
    RW_ID_COLUMN,
)
from landloss.hazard.realisation import realisation_seed
from landloss.vul.shaking.fragility import (
    BETA_FAILURE_PROBABILITY,
    DAMAGE_STATE_COLUMN,
    REPLACE,
    beta_failure_probability,
    draw_damage_states,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation.gen_pga_realisations import (
    pga_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "wall-damage-state"

# One stream for the whole vulnerability module, so that adding a hazard or an
# asset class does not shift the draws of the ones already there.
RNG_STREAM = "vulnerability"

ASSET = "retaining wall"
ASSET_COLUMN = "asset"
PGA_COLUMN = "pga_g"
FAILURE_PROBABILITY_COLUMN = "failure_probability"

RULE = "-" * 72


def wall_damage_state_path(realisation_id, *, pilot):
    """Return the file a run writes one realisation's wall states to."""
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.geoparquet"


def describe_states(states):
    """Print how the population split, and what share that is."""
    print(RULE)
    print(f"Retaining walls: {len(states):,}")
    if states.empty:
        return

    counts = states[DAMAGE_STATE_COLUMN].value_counts()
    for state, count in counts.items():
        print(f"  {state}: {count:,} ({100 * count / len(states):.1f}%)")
    print(
        f"  drawn against a flat {BETA_FAILURE_PROBABILITY:.0%} chance of failure, "
        "which is the beta's stand-in for a fragility curve"
    )

    pga = states[PGA_COLUMN]
    outside = int(pga.isna().sum())
    if outside:
        print(f"  {outside:,} walls fall outside the PGA field")
    if pga.notna().any():
        print(f"  PGA {pga.min():.3f} to {pga.max():.3f} g over the population")

    replaced = states[states[DAMAGE_STATE_COLUMN] == REPLACE]
    print(
        f"  {replaced[CLAIM_ID_COLUMN].nunique():,} properties carry at least one "
        "wall to replace"
    )


def main(*, pilot, realisation_ids):
    """Write a damage state per retaining wall, per realisation."""
    for realisation_id in realisation_ids:
        walls = gpd.read_parquet(wall_population_path(realisation_id, pilot=pilot))
        raster = pga_path(realisation_id, pilot=pilot)
        print(f"Reading the PGA field from {raster} ...", flush=True)

        # Rows stay in population order, which step 6 sorts by claim and
        # location, so each wall's draw is tied to its rw_id.
        rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
        probability = beta_failure_probability(len(walls))

        states = gpd.GeoDataFrame(
            {
                REALISATION_ID_COLUMN: realisation_id,
                RW_ID_COLUMN: walls[RW_ID_COLUMN].to_numpy(),
                CLAIM_ID_COLUMN: walls[CLAIM_ID_COLUMN].to_numpy(),
                ASSET_COLUMN: ASSET,
                "size_class": walls["size_class"].to_numpy(),
                "initial_condition": walls["initial_condition"].to_numpy(),
                "height_m": walls["height_m"].to_numpy(),
                "length_m": walls["length_m"].to_numpy(),
                # A wall is a line; it is sampled at its midpoint, which is
                # within a few metres of either end at these lengths and well
                # inside one cell of the PGA grid.
                PGA_COLUMN: sample_at_points(
                    raster, walls.geometry.interpolate(0.5, normalized=True)
                ).to_numpy(),
                FAILURE_PROBABILITY_COLUMN: probability,
                DAMAGE_STATE_COLUMN: draw_damage_states(probability, rng),
            },
            # The wall line rides through so the loss table carries coordinates.
            geometry=walls.geometry.to_numpy(),
            crs=walls.crs,
        )
        describe_states(states)

        out_path = wall_damage_state_path(realisation_id, pilot=pilot)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        states.to_parquet(out_path)
        print(f"Wrote {len(states):,} rows to {out_path}")

    print(RULE)
    print(
        "States only. A written-off wall is priced from its undepreciated value "
        "in the loss module, which is not built yet."
    )


if __name__ == "__main__":
    main(pilot=config.PILOT, realisation_ids=config.REALISATION_IDS)
