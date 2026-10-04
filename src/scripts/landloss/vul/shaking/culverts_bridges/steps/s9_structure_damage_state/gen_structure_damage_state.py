"""Decide which culverts and bridges the shaking wrote off.

Reads the crossing population and the realisation's PGA field, and draws a
damage state per structure against its probability of failure.

    uv run --frozen python src/scripts/landloss/vul/shaking/culverts_bridges/steps/s9_structure_damage_state/gen_structure_damage_state.py

Two damage states only, **no damage** and **replace**, the same pair the
retaining walls use and for the same reason: a failed crossing is rebuilt rather
than patched. The fragility returns a **probability of failure at the ground
motion the structure saw**, and the state is a draw against it. The beta draws both kinds of structure against one flat
probability, so nothing here yet distinguishes a culvert from a bridge except
the label it carries into the loss module -- where they matter, because they
share a sub-cap but not a cost.

**Expect nothing over the Wellington pilot.** The crossing population is built
from named watercourses, the nearest of which is some kilometres away, so this
step legitimately writes zero rows there. That is the population's coverage, not
a failure of this step, and the run says so rather than printing an empty table.

**No cost is attached.** The loss module prices a written-off structure from its
undepreciated value, so what this writes is the state, not the money.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import pandas as pd

from landloss.common.utils.terrain import sample_at_points
from landloss.domain import constants
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    CROSSING_ID_COLUMN,
    REALISATION_ID_COLUMN,
)
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
from landloss.vul.shaking.fragility import (
    BETA_FAILURE_PROBABILITY,
    DAMAGE_STATE_COLUMN,
    REPLACE,
    beta_failure_probability,
    draw_damage_states,
)
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population.gen_crossing_population import (
    crossing_population_path,
)
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation.gen_pga_realisations import (
    pga_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.shaking.culverts_bridges.steps.s9_structure_damage_state import (
    config,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "structure-damage-state"

# The same stream the walls draw from: one per module, so that adding an asset
# class does not shift the draws of the ones already there.
RNG_STREAM = "vulnerability"

ASSET_COLUMN = "asset"
STRUCTURE_COLUMN = "structure"
PGA_COLUMN = "pga_g"
FAILURE_PROBABILITY_COLUMN = "failure_probability"

OUT_COLUMNS = [
    REALISATION_ID_COLUMN,
    CROSSING_ID_COLUMN,
    CLAIM_ID_COLUMN,
    ASSET_COLUMN,
    PGA_COLUMN,
    FAILURE_PROBABILITY_COLUMN,
    DAMAGE_STATE_COLUMN,
    "geometry",
]

RULE = "-" * 72


def structure_damage_state_path(realisation_id, *, extent):
    """Return the file a run writes one realisation's structure states to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.geoparquet"


def describe_states(states):
    """Print how the population split, by kind of structure."""
    print(RULE)
    print(f"Culverts and bridges: {len(states):,}")
    if states.empty:
        print(
            "  none over this extent. The crossing population follows named "
            "watercourses, and the pilot box contains none."
        )
        return

    split = pd.crosstab(states[ASSET_COLUMN], states[DAMAGE_STATE_COLUMN])
    print(split.to_string())
    print(
        f"  drawn against a flat {BETA_FAILURE_PROBABILITY:.0%} chance of failure, "
        "which is the beta's stand-in for a fragility curve"
    )

    pga = states[PGA_COLUMN]
    outside = int(pga.isna().sum())
    if outside:
        print(f"  {outside:,} structures fall outside the PGA field")
    if pga.notna().any():
        print(f"  PGA {pga.min():.3f} to {pga.max():.3f} g over the population")

    replaced = states[states[DAMAGE_STATE_COLUMN] == REPLACE]
    print(
        f"  {replaced['claim_id'].nunique():,} properties carry at least one "
        "structure to replace"
    )


def main(*, extent, realisation_ids):
    """Write a damage state per culvert and bridge, per realisation."""
    for realisation_id in realisation_ids:
        crossings = gpd.read_parquet(
            crossing_population_path(realisation_id, extent=extent)
        )
        raster = pga_path(realisation_id, extent=extent)
        print(f"Reading the PGA field from {raster} ...", flush=True)

        rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
        probability = beta_failure_probability(len(crossings))

        # PGA is read at a point guaranteed to lie on the structure. A crossing
        # kept by the coverage filter can be a polygon or a collection, on
        # which interpolating along a line is not defined.
        pga = (
            sample_at_points(raster, crossings.geometry.representative_point())
            if len(crossings)
            else pd.Series(dtype=float)
        )
        states = gpd.GeoDataFrame(
            {
                REALISATION_ID_COLUMN: realisation_id,
                CROSSING_ID_COLUMN: crossings[CROSSING_ID_COLUMN].to_numpy(),
                CLAIM_ID_COLUMN: crossings[CLAIM_ID_COLUMN].to_numpy(),
                # The kind of structure is the asset, because a culvert and a
                # bridge are priced differently even though they share a sub-cap.
                ASSET_COLUMN: crossings[STRUCTURE_COLUMN].to_numpy(),
                PGA_COLUMN: pga.to_numpy(),
                FAILURE_PROBABILITY_COLUMN: probability,
                DAMAGE_STATE_COLUMN: draw_damage_states(probability, rng),
            },
            geometry=crossings.geometry.to_numpy(),
            crs=crossings.crs,
        )[OUT_COLUMNS]
        describe_states(states)

        out_path = structure_damage_state_path(realisation_id, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        states.to_parquet(out_path)
        print(f"Wrote {len(states):,} rows to {out_path}")

    print(RULE)
    print(
        "States only. A written-off structure is priced from its undepreciated "
        "value in the loss module, which is not built yet."
    )


if __name__ == "__main__":
    main(extent=config.EXTENT, realisation_ids=config.REALISATION_IDS)
