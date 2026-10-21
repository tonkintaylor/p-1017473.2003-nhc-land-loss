"""Write the numbers the liquefaction damage appendix quotes about damaged ground.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/report/gen_report_numbers.py

The appendix's hazard half, from the NLM to a land damage state per cell, reads
its numbers from ``hazard/liquefaction/report/gen_report_numbers.py``. This
writes the other half, from a property's state to the ground it loses, so every
number the appendix states can be traced to the code or the run it came from
rather than typed in. The YAML has four parts:

- ``meta``: when and from which commit it was written, the realisation, and the
  step 2 run read for each territorial authority with the date it was written.
- ``settings``: the evacuated area and inundated share per state, the overlap
  share and the drop-out rates, read from step 2's ``config.py``, so a changed
  setting changes the appendix on the next run.
- ``study_area``: over the four territorial authorities, how many properties
  sit on the liquefaction grid and in each state, how many claim, and the ground
  each claim loses, by state.
- ``by_authority``: the same counts for each territorial authority.

Each authority's run is over its bounding box, which takes in the edges of its
neighbours, so a property is counted only in the run of the authority its
insured land lies in, placed at the representative point step 2 sampled the
state at. Reads step 2's outputs under ``temp/`` only, never the T: drive.
Written to ``report/vul/liquefaction/tab/report-numbers.yaml``.
"""

import datetime as dt
import sys

import geopandas as gpd
import pandas as pd
import yaml

from landloss.domain.loss_contract import LAND_ID_COLUMN
from landloss.hazard.liquefaction.land_damage import LD_STATES
from landloss.io.area_of_interest import get_area_of_interest, get_study_areas
from landloss.vul.liquefaction.damaged_area import (
    DAMAGED_AREA_COLUMN,
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import config
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage.gen_liq_land_damage import (
    CLAIMED_COLUMN,
    HAZARD_STATE_COLUMN,
    ON_GRID_COLUMN,
    liq_land_damage_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "vul" / "liquefaction" / "tab" / "report-numbers.yaml"
# The four territorial authorities of the study, by extent name.
AUTHORITY_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
REALISATION_ID = 0
HECTARE_M2 = 10_000


def by_state_name(table):
    """Return a table keyed on state code 1 to 6 keyed on the state's name."""
    return {name: table[code] for code, name in enumerate(LD_STATES, start=1)}


def settings():
    """Return the values the ground lost per state is drawn with."""
    return {
        "evacuated_area_m2": {
            name: list(bounds)
            for name, bounds in by_state_name(config.EVACUATED_AREA_M2).items()
        },
        "inundated_share": {
            name: list(bounds)
            for name, bounds in by_state_name(config.INUNDATED_SHARE).items()
        },
        "evacuated_overlap_share": config.EVACUATED_OVERLAP_SHARE,
        "drop_out_rates": by_state_name(config.DROP_OUT_RATES),
    }


def within_authority(damage, extent):
    """Keep the properties whose insured land lies in the extent's authority."""
    name = get_area_of_interest(extent).name
    insured = gpd.read_parquet(
        insured_land_path(extent=extent), columns=[LAND_ID_COLUMN, "geometry"]
    )
    authorities = get_study_areas(insured.crs)
    boundary = authorities.loc[authorities["name"] == name].union_all()
    inside = insured.representative_point().within(boundary)
    return damage[damage[LAND_ID_COLUMN].isin(insured.loc[inside, LAND_ID_COLUMN])]


def read_runs(realisation_id):
    """Return each authority's step 2 run, trimmed to the authority, and its file.

    Raises:
        FileNotFoundError: If step 2 has not been run for an authority.
        ValueError: If a property is placed in two authorities.
    """
    runs = {}
    for extent in AUTHORITY_EXTENTS:
        path = liq_land_damage_path(realisation_id, extent=extent)
        if not path.exists():
            msg = f"No step 2 run for {extent}: run gen_liq_land_damage.py for it"
            raise FileNotFoundError(msg)
        runs[extent] = (within_authority(pd.read_parquet(path), extent), path)
    land_ids = pd.concat([damage[LAND_ID_COLUMN] for damage, _ in runs.values()])
    if land_ids.duplicated().any():
        msg = f"{int(land_ids.duplicated().sum())} properties in two authorities"
        raise ValueError(msg)
    return runs


def counts(damage):
    """Return how many properties there are, on the grid, and claiming."""
    return {
        "properties": len(damage),
        "on_grid": int(damage[ON_GRID_COLUMN].sum()),
        "claims": int(damage[CLAIMED_COLUMN].sum()),
        "damaged_area_ha": round(
            float(damage[DAMAGED_AREA_COLUMN].sum()) / HECTARE_M2, 1
        ),
    }


def ground_lost(claims):
    """Return the mean ground the claims lose, or None if there are none."""
    if claims.empty:
        return None
    return {
        "mean_insured_area_m2": float(claims["area_m2"].mean()),
        "mean_evacuated_m2": float(claims[EVACUATED_AREA_COLUMN].mean()),
        "mean_inundated_m2": float(claims[INUNDATED_AREA_COLUMN].mean()),
        "mean_damaged_m2": float(claims[DAMAGED_AREA_COLUMN].mean()),
        "mean_damaged_share": float(
            (claims[DAMAGED_AREA_COLUMN] / claims["area_m2"]).mean()
        ),
    }


def study_area(damage):
    """Return the properties in each state and the ground their claims lose."""
    on_grid = int(damage[ON_GRID_COLUMN].sum())
    states = {}
    for code, name in enumerate(LD_STATES, start=1):
        in_state = damage[HAZARD_STATE_COLUMN].eq(code).fillna(value=False)
        claims = damage[in_state & damage[CLAIMED_COLUMN]]
        states[name] = {
            "properties": int(in_state.sum()),
            "share_of_on_grid": float(in_state.sum() / on_grid) if on_grid else None,
            "claims": len(claims),
            **(ground_lost(claims) or {}),
        }
    return {**counts(damage), "by_state": states}


def main(*, realisation_id):
    """Compute the numbers and write the YAML."""
    runs = read_runs(realisation_id)
    damage = pd.concat([frame for frame, _ in runs.values()], ignore_index=True)
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "realisation_id": realisation_id,
            "runs": {
                extent: {
                    "file": path.relative_to(REPO_ROOT).as_posix(),
                    "written": dt.datetime.fromtimestamp(path.stat().st_mtime)
                    .astimezone()
                    .date()
                    .isoformat(),
                }
                for extent, (_, path) in runs.items()
            },
        },
        "settings": settings(),
        "study_area": study_area(damage),
        "by_authority": {
            get_area_of_interest(extent).name: counts(frame)
            for extent, (frame, _) in runs.items()
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(yaml.safe_dump(numbers["study_area"], sort_keys=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main(realisation_id=REALISATION_ID)
