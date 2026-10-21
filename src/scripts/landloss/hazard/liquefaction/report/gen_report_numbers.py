"""Write the numbers the technical report's liquefaction section quotes.

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/report/gen_report_numbers.py

Every number the section states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has four parts:

- ``meta``: when and from which commit it was written, and the NLM release.
- ``settings``: the values the model is set with, read from the constants that
  set them, so a changed setting changes the report on the next run.
- ``study_area``: the NLM grids and the lateral spreading correction over the
  four territorial authorities, computed the way
  ``fig_lateral_spreading.py`` computes them, from the local cache step 2
  keeps. This script never reads the T: drive.
- ``draw``: the states drawn by step 3 for one realisation, over the four
  territorial authorities, each from its own authority's run. Each run covers
  its authority's bounding box, which takes in the edges of its neighbours, so
  a cell is counted only in the run of the authority its centre lies in. Left
  out if step 3 has not been run for all four.

It also lists which of the section's figures exist, so the section can show a
placeholder rather than fail when one has not been drawn. Written to
``report/hazard/liquefaction/tab/report-numbers.yaml``.
"""

import datetime as dt
import subprocess
import sys

import numpy as np
import rioxarray
import yaml
from rasterio.enums import Resampling

from landloss.domain import constants
from landloss.hazard.liquefaction.land_damage import (
    BETA_MAJOR_SHARES,
    BETA_NONE_SHARES,
    LD_STATES,
    beta_expand_ld_probabilities,
)
from landloss.hazard.liquefaction.lateral_spreading import (
    FAR_DIVISOR,
    FAR_FIELD_M,
    KNEE,
    MIDDLE_BAND_FAR_WEIGHT,
    NEAR_FIELD_M,
    NEAR_MULTIPLIER,
    SUPERSAMPLE,
    ZONES,
    apply_lateral_spreading,
    far_weight_grid,
    lateral_spreading_zones,
    zone_grid,
)
from landloss.hazard.liquefaction.waterways import MIN_FREE_FACE_AREA_M2
from landloss.io.area_of_interest import (
    FULL_EXTENT,
    get_area_of_interest,
    get_study_areas,
)
from scripts.landloss.hazard.liquefaction.report.fig_lateral_spreading import (
    extent_frame,
    mask_outside,
    read_cached_nlm,
    read_free_faces,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities.gen_liq_ld_probabilities import (
    beta_probability_path,
    clip_to_extent,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
)
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "hazard" / "liquefaction" / "tab" / "report-numbers.yaml"
FIG_DIR = REPORT_DIR / "hazard" / "liquefaction" / "fig"
# The figures the section shows, by the key it refers to them by.
FIGURES = {
    "zones": FIG_DIR / "lateral-spreading-zones-study-area.png",
    "change": FIG_DIR / "lateral-spreading-change-study-area.png",
    "correction": FIG_DIR / "lateral-spreading-correction.png",
}
HECTARE_M2 = 10_000
# The four territorial authorities of the study, by extent name.
AUTHORITY_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
REALISATION_ID = 0


def git_commit():
    """Return the short hash of the commit the numbers were written from."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return result.stdout.strip() or "unknown"


def settings():
    """Return the values the liquefaction hazard is set with."""
    return {
        "return_period_years": 2500,
        "base_seed": constants.BASE_SEED,
        "min_free_face_area_ha": MIN_FREE_FACE_AREA_M2 / HECTARE_M2,
        "near_field_m": NEAR_FIELD_M,
        "far_field_m": FAR_FIELD_M,
        "knee": KNEE,
        "near_multiplier": NEAR_MULTIPLIER,
        "far_divisor": FAR_DIVISOR,
        # Above the knee the correction is a fixed shift, the one the
        # multiplier and divisor make at the knee itself.
        "near_lift_above_knee": KNEE * NEAR_MULTIPLIER - KNEE,
        "far_drop_above_knee": KNEE - KNEE / FAR_DIVISOR,
        "middle_far_weight": MIDDLE_BAND_FAR_WEIGHT,
        "supersample": SUPERSAMPLE,
        "none_shares": dict(BETA_NONE_SHARES),
        "major_shares": dict(BETA_MAJOR_SHARES),
    }


def mean(grid):
    """Return a grid's mean over the cells that carry a value."""
    return float(np.nanmean(grid.to_numpy()))


def study_area():
    """Return the NLM grids and the lateral spreading correction over the study area."""
    area = extent_frame(FULL_EXTENT)
    all_faces, faces = read_free_faces(FULL_EXTENT, area)
    zones = lateral_spreading_zones(all_faces)
    bbox = tuple(float(v) for v in area.total_bounds)
    moderate = clip_to_extent(read_cached_nlm("moderate"), bbox, "moderate")
    major = clip_to_extent(read_cached_nlm("major"), bbox, "major")
    major = major.rio.reproject_match(moderate, resampling=Resampling.nearest)
    moderate = mask_outside(moderate, area)
    major = mask_outside(major, area)
    corrected, capped = apply_lateral_spreading(
        moderate, major, far_weight_grid(zones, major)
    )
    zone = zone_grid(zones, major).to_numpy()
    before, after = major.to_numpy(), corrected.to_numpy()
    carried = np.isfinite(before)

    by_zone = {}
    for code, name in ZONES.items():
        in_zone = (zone == code) & carried
        by_zone[name] = {
            "cells": int(in_zone.sum()),
            "mean_p_major_before": float(before[in_zone].mean())
            if in_zone.any()
            else None,
            "mean_p_major_after": float(after[in_zone].mean())
            if in_zone.any()
            else None,
        }

    faces = faces.assign(length_km=faces.length / 1000)
    free_faces = {
        str(kind): {
            "features": len(group),
            "km": round(float(group["length_km"].sum()), 1),
        }
        for kind, group in faces.groupby("wtype")
    }
    states = beta_expand_ld_probabilities(moderate, corrected)
    resolution = abs(float(moderate.x[1] - moderate.x[0]))
    return {
        "grid_resolution_m": resolution,
        "cells_with_probability": int(carried.sum()),
        "area_with_probability_km2": round(int(carried.sum()) * resolution**2 / 1e6, 1),
        "mean_p_moderate_or_worse": mean(moderate),
        "mean_p_major_or_worse_before": mean(major),
        "mean_p_major_or_worse_after": mean(corrected),
        "cells_capped": int(capped.to_numpy().sum()),
        "by_zone": by_zone,
        "free_faces": free_faces,
        "mean_state_probability": {state: mean(states[state]) for state in LD_STATES},
    }


def read_grid(path):
    """Return a single-band raster, NaN where it carries no value."""
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze(drop=True).load()


def authority_frame(extent):
    """Return the outline of the authority an extent is named for, as a frame."""
    name = get_area_of_interest(extent).name
    areas = get_study_areas(constants.DEFAULT_CRS)
    return areas.loc[areas["name"] == name]


def drawn_cells(realisation_id, extent):
    """Return one authority's drawn states and their six probabilities, as arrays.

    Only the cells whose centre lies in the authority and that carry a state.
    """
    area = authority_frame(extent)
    states = mask_outside(read_grid(ld_state_path(realisation_id, extent=extent)), area)
    values = states.to_numpy()
    drawn = np.isfinite(values)
    probabilities = {
        state: read_grid(beta_probability_path(state, extent=extent)).to_numpy()[drawn]
        for state in LD_STATES
    }
    return values[drawn], probabilities


def draw(realisation_id, *, extents):
    """Return each state's share drawn beside its mean probability, or None.

    Both over the cells step 3 drew in the four authorities, from the
    probability grids step 2 wrote for the same runs, with the standard error a
    share drawn from that many cells carries, so a reader can judge the gap.
    """
    paths = {extent: ld_state_path(realisation_id, extent=extent) for extent in extents}
    if not all(path.exists() for path in paths.values()):
        return None
    runs = [drawn_cells(realisation_id, extent) for extent in extents]
    states = np.concatenate([values for values, _ in runs])
    cells = len(states)
    out = {
        "extents": list(extents),
        "realisation_id": realisation_id,
        "written": {
            extent: dt.datetime.fromtimestamp(path.stat().st_mtime)
            .astimezone()
            .date()
            .isoformat()
            for extent, path in paths.items()
        },
        "cells": cells,
    }
    for code, state in enumerate(LD_STATES, start=1):
        expected = float(
            np.mean(np.concatenate([probabilities[state] for _, probabilities in runs]))
        )
        out[state] = {
            "drawn": float(np.mean(states == code)),
            "expected": expected,
            "standard_error": float(np.sqrt(expected * (1 - expected) / cells)),
        }
    return out


def main(*, draw_extents, realisation_id):
    """Compute the numbers and write the YAML."""
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "nlm_release": str(constants.CORE_NLM_VERSION.value),
        },
        "settings": settings(),
        "study_area": study_area(),
        "draw": draw(realisation_id, extents=draw_extents),
        "figures": {
            key: path.relative_to(REPO_ROOT).as_posix() if path.exists() else None
            for key, path in FIGURES.items()
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(yaml.safe_dump(numbers["study_area"], sort_keys=False))
    print(yaml.safe_dump(numbers["draw"], sort_keys=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main(draw_extents=AUTHORITY_EXTENTS, realisation_id=REALISATION_ID)
