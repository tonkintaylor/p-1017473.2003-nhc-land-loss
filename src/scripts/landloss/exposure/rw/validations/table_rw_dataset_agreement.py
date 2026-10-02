"""Tabulate where the three retaining wall datasets agree, property by property.

    uv run --frozen python src/scripts/landloss/exposure/rw/validations/table_rw_dataset_agreement.py

Reads the layer ``gen_rw_dataset_properties.py`` writes, so run that first.
Settings are in ``config.py``. Every table is an aggregate over at least a few
hundred properties: the per-property layer is sensitive and is not reproduced.

Each comparison is made over the properties every dataset in it covers:

- GNS against NHC over urban Wellington City, the area GNS mapped, on properties
  NZMM carries a flag for;
- either against the claim reports over the claimed properties whose report
  says how many walls it lists, inside the area GNS mapped where GNS is in it.

Writes to ``report/exposure/rw/rw-datasets/tab/``:

- ``rw-dataset-coverage.csv``: what each dataset covers and flags;
- ``rw-dataset-agreement-gns-nhc.csv``: both, one or neither, per tolerance;
- ``rw-dataset-agreement-claims.csv``: every combination of the three, on
  claimed properties GNS mapped;
- ``rw-dataset-claims-recall.csv``: how often GNS and NHC flag a property whose
  claim report does, and does not, list a wall;
- ``rw-dataset-by-slope.csv`` and ``rw-dataset-by-ta.csv``: the share flagged
  by NZMM slope class and by council;
- ``rw-dataset-wall-counts.csv``: walls the claim report lists against walls GNS
  mapped, on claimed properties GNS mapped.

Findings are written up in ``rw_dataset_comparison.md`` beside this script.
"""

import sys

import pandas as pd

from scripts.landloss.exposure.rw.validations import config
from scripts.landloss.exposure.rw.validations.rw_datasets import (
    BOTH,
    CLAIMS,
    GNS,
    GNS_ONLY,
    NEITHER,
    NHC,
    NHC_ONLY,
    category,
    claims_population,
    gns_flag,
    gns_nhc_population,
    load_properties,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CATEGORIES = (BOTH, GNS_ONLY, NHC_ONLY, NEITHER)

# The bins walls are counted in, the last open-ended.
CLAIM_WALL_BINS = (0, 1, 2, 3, 4, 5)
GNS_WALL_BINS = (0, 1, 2, 3)

RULE = "-" * 72


def share(flags: pd.Series) -> float:
    """Return the share of True among the known values."""
    known = flags.dropna()
    return float(known.mean()) if len(known) else float("nan")


def kappa(first: pd.Series, second: pd.Series) -> float:
    """Return Cohen's kappa between two boolean flags on the same properties."""
    first = first.astype(bool)
    second = second.astype(bool)
    observed = (first == second).mean()
    expected = first.mean() * second.mean() + (1 - first.mean()) * (1 - second.mean())
    return float((observed - expected) / (1 - expected))


def coverage_table(properties: pd.DataFrame) -> pd.DataFrame:
    """Return what each dataset covers, and how many properties it flags."""
    gns = properties.loc[properties["in_gns_coverage"], "gns_wall"]
    nhc = properties.loc[properties["has_nzmm"], "nhc_wall"]
    claims = claims_population(properties)["claim_wall"]
    rows = [
        (GNS, "Urban Wellington City", "Mapped wall lines", gns),
        (NHC, "Four councils", "Y/N flag per property", nhc),
        (CLAIMS, "Claimed properties", "Walls listed on site", claims),
    ]
    return pd.DataFrame(
        [
            {
                "dataset": name,
                "extent": extent,
                "record": record,
                "properties": len(flags),
                "flagged": int(flags.sum()),
                "share_flagged": share(flags),
            }
            for name, extent, record, flags in rows
        ]
    ).set_index("dataset")


def gns_nhc_table(properties: pd.DataFrame) -> pd.DataFrame:
    """Return GNS against NHC over the properties both cover, per tolerance."""
    population = gns_nhc_population(properties)
    rows = []
    for tolerance in config.TOLERANCES_M:
        gns = population[gns_flag(tolerance)]
        counts = category(gns, population["nhc_wall"]).value_counts()
        either = counts.get(BOTH, 0) + counts.get(GNS_ONLY, 0) + counts.get(NHC_ONLY, 0)
        rows.append(
            {
                "tolerance_m": tolerance,
                "properties": len(population),
                **{name: int(counts.get(name, 0)) for name in CATEGORIES},
                "both_of_either": counts.get(BOTH, 0) / either,
                "nhc_flags_gns_has": counts.get(BOTH, 0) / population["nhc_wall"].sum(),
                "gns_flags_nhc_has": counts.get(BOTH, 0) / gns.sum(),
                "kappa": kappa(gns, population["nhc_wall"]),
            }
        )
    return pd.DataFrame(rows).set_index("tolerance_m")


def claims_combinations(properties: pd.DataFrame) -> pd.DataFrame:
    """Return every combination of the three datasets on claimed GNS properties."""
    population = claims_population(gns_nhc_population(properties))
    flags = pd.DataFrame(
        {
            CLAIMS: population["claim_wall"].astype(bool),
            GNS: population["gns_wall"].astype(bool),
            NHC: population["nhc_wall"].astype(bool),
        }
    )
    combos = flags.value_counts().rename("properties").reset_index()
    combos["share"] = combos["properties"] / len(flags)
    return combos.sort_values("properties", ascending=False).reset_index(drop=True)


def claims_recall(properties: pd.DataFrame) -> pd.DataFrame:
    """Return how often GNS and NHC flag a property, by what its claim lists."""
    population = claims_population(properties)
    rows = []
    for listed, label in ((True, "lists a wall"), (False, "lists none")):
        group = population.loc[population["claim_wall"] == listed]
        mapped = group.loc[group["in_gns_coverage"]]
        rows.append(
            {
                "claim_report": label,
                "properties": len(group),
                "nhc_flagged": share(group["nhc_wall"]),
                "properties_gns_mapped": len(mapped),
                "gns_flagged": share(mapped["gns_wall"]),
                "nhc_flagged_where_gns_mapped": share(mapped["nhc_wall"]),
                "either_flagged_where_gns_mapped": share(
                    mapped["gns_wall"].fillna(value=False)
                    | mapped["nhc_wall"].fillna(value=False)
                ),
            }
        )
    return pd.DataFrame(rows).set_index("claim_report")


def by_group(properties: pd.DataFrame, column: str) -> pd.DataFrame:
    """Return the share each dataset flags, grouped on ``column``."""
    rows = []
    for value, group in properties.dropna(subset=[column]).groupby(column):
        nzmm = group.loc[group["has_nzmm"]]
        mapped = nzmm.loc[nzmm["in_gns_coverage"]]
        claims = claims_population(group)
        rows.append(
            {
                column: value,
                "properties_nzmm": len(nzmm),
                "nhc_flagged": share(nzmm["nhc_wall"]),
                "properties_gns_mapped": len(mapped),
                "gns_flagged": share(mapped["gns_wall"]) if len(mapped) else None,
                "nhc_flagged_where_gns_mapped": share(mapped["nhc_wall"])
                if len(mapped)
                else None,
                "claimed_properties": len(claims),
                "claim_lists_wall": share(claims["claim_wall"]),
                "nhc_flagged_where_claim_lists_wall": share(
                    claims.loc[claims["claim_wall"].astype(bool), "nhc_wall"]
                ),
            }
        )
    return pd.DataFrame(rows).set_index(column)


def binned(counts: pd.Series, bins: tuple[int, ...]) -> pd.Series:
    """Return wall counts as labels, the last bin open-ended."""
    last = bins[-1]
    return (
        counts.astype(int)
        .clip(upper=last)
        .map(lambda count: f"{count}+" if count == last else str(count))
    )


def wall_counts(properties: pd.DataFrame) -> pd.DataFrame:
    """Return claim report wall counts against GNS wall counts."""
    population = claims_population(properties)
    population = population.loc[population["in_gns_coverage"]]
    table = pd.crosstab(
        binned(population["claim_walls"], CLAIM_WALL_BINS).rename("claim_walls"),
        binned(population["gns_walls"], GNS_WALL_BINS).rename("gns_walls"),
    )
    return table.reindex(
        index=[*map(str, CLAIM_WALL_BINS[:-1]), f"{CLAIM_WALL_BINS[-1]}+"],
        columns=[*map(str, GNS_WALL_BINS[:-1]), f"{GNS_WALL_BINS[-1]}+"],
        fill_value=0,
    )


def build_tables(properties: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return every table, keyed by file name."""
    return {
        "rw-dataset-coverage.csv": coverage_table(properties),
        "rw-dataset-agreement-gns-nhc.csv": gns_nhc_table(properties),
        "rw-dataset-agreement-claims.csv": claims_combinations(properties),
        "rw-dataset-claims-recall.csv": claims_recall(properties),
        "rw-dataset-by-slope.csv": by_group(properties, "nzmm_slope_class"),
        "rw-dataset-by-ta.csv": by_group(properties, "ta"),
        "rw-dataset-wall-counts.csv": wall_counts(properties),
    }


def main() -> int:
    """Write the comparison tables and print them."""
    config.TAB_DIR.mkdir(parents=True, exist_ok=True)
    tables = build_tables(load_properties())
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        for name, table in tables.items():
            table.to_csv(config.TAB_DIR / name, float_format="%.4f")
            print(RULE)
            print(name)
            print(table.round(3).to_string())
    print(RULE)
    print(f"Wrote {len(tables)} tables to {config.TAB_DIR}")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
