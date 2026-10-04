# Pips, Pifs and Sizs: Replacing the Bank Rule and the Seeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the free-face/bank seeding of the urban slope model with a simple stage 1 (pips, grouped into pifs, tested to give sizs), grow the sizs by the existing watershed, and feed the existing evacuated-zone builder twice: every siz walled, and none walled.

**Architecture:** A new library module `landloss.hazard.landslide.instability_zones` finds *pips* (potential instability points) on the 1 m DEM alone, joins them into *pifs* (potential instability faces), and tests every pif over all pairs of its points to flag *sizs* (seed instability zones). The sizs seed the existing `_grow_by_limit` watershed; the grown elements go through a shared assembly function (extracted from `find_slope_elements`, so the old entry point is untouched in behaviour) and then into the unchanged `build_slope_polygons`. The siz table is saved because the retaining-wall (RW) workflow reads it.

**Tech Stack:** Python 3.13, numpy, scipy (`cKDTree`, `ndimage`, `sparse.csgraph`), pandas, geopandas, shapely, pytest, `uv`, prek.

This plan supersedes **phase 1 (seeds, free-face vs bank)** of
`.agents/plans/building-face-based-urban-slope-polygons.md`. Phase 3 (polygons) is reused as is.

## Global Constraints

- Run everything with `uv run --frozen ...`. Pre-commit: `uv run --frozen prek run --files <paths>`. **Do not commit** (the lead has asked for no commits); the "commit" step of the usual TDD loop is replaced by "run prek on touched files".
- Create and edit files only with the `create`/`edit` tools; never write file contents from PowerShell.
- No `argparse`; run settings in `config.py`; `main()` has no defaults; no `try/except`/`exists()` guards that print and return.
- Naming: functions that fetch are `get_`, derived layers `gen_`, figures `fig_`. Assessment functions in the library must **not** start with `test_` (pytest would collect them when imported into a test module).
- Ruff is `select = ["ALL"]`, line length 88. Watch RUF100, RUF043 (raw-string `match=`), SIM300, ISC004.
- `src/landloss/` and `steps/` never import from a `research/` folder.
- Keep `slope_elements.find_slope_elements` and its public behaviour: `fig_toy_slope_elements.py` still uses it, and the 662 landslide tests must stay green (897 with io).
- Do not touch the other agent's Hancox/Kritikos model files.
- Cite by `doc/references.bib` key in square brackets; no new references are needed.
- Every touched submodule updates its `status.md` in the same change (skill `maintaining-status-files`), and a new changelog fragment `doc/whatsnew/mm.feature.<yymmddhhmm>.md` is written (never append to an old one).
- The agreed rules, copied from the lead (2026-10-04):
  - **Pip:** a cell higher than the cell 1, 3 and 5 m away, in the same one of **8 directions**, each time by more than **0.7 m**. No material, no other DEM. Diagonals are 1.41 m per cell, so the drop needed along a diagonal is scaled by 1.41 (our default; the lead said "work out what 5 m means").
  - **Pif:** pips within **2 m** of each other are joined.
  - **Siz:** a pif is a siz if, over **every pair of its points** (distance and delta_h):
    - pairs **under 3 m** apart: the delta_h reaches `adjacent_step_m` for the ground group (soil 0.7 m, weak rock 3.0 m, stronger rock 3.0 m), so a 1-2 m rock wall is **not** a siz and a 3 m one is;
    - pairs **3 m or more** apart: the angle reaches the group's slope threshold for the pair's delta_h band. Below 3.5 m: 35 / 45 / 53 degrees; from 3.5 m: 32 / 40 / 48 degrees (soil / weak rock / stronger rock).
  - **Ground group:** read at the pif's pips (the ground above the face), by majority. Ground mapped as **fill is soil_like, never rock**.
  - **Growth by watershed is kept**, as is the polygon builder, run **twice**: A every siz walled, B none walled.
  - The siz table keeps **every pif** with its max angle above and below 3.5 m, its max delta_h and whether it qualifies; the RW workflow reads it.

## Design notes the lead should know about

1. **Support points.** Pips are the *upper* cell of a drop, so on a vertical wall every pip of a pif sits at the same height and no pair has a delta_h. To give the pair matrix something to measure, each pif's point set is its pips **plus the cells each pip falls to** (1, 3 and 5 m along the pip's fall direction). Pairs among those points are then crest-to-foot pairs. This is our addition to the lead's "distance between all pips and delta_h".
2. **Soil is automatically a siz.** A pip already drops more than 0.7 m in one cell (35 degrees or steeper at 1 cell), so on soil the near test (0.7 m) is met by every pif. This follows from the rules as given; the 0.7 m is what keeps little blips out, and the junk filters (below) drop what is left.
3. **A one-cell spike is a pip** (it is higher than the cells 1, 3 and 5 m away). It becomes a one-cell pif, and on soil a siz, but its grown element is dropped by the existing junk filters (length under 3 m). Do not assert otherwise in tests.
4. **Pair cost.** All pairs within pifs would be about 1.4 billion on the pilot (the largest pif has 24,526 pips). Pairs are capped at **30 m** (a 16 m face at 32 degrees runs about 26 m), found with a row window on row-sorted points and computed in blocks. A 30 m cap is about 156 M pairs on the pilot. Pip detection (0.8 s) and clustering (about 0.1 s) are cheap, growth and polygons are unchanged (old total 27 s). **Gate:** record the pilot's timings in Task 8; if the siz test alone exceeds about 60 s, subsample the points of pifs over 5,000 points (keep every second crest row) before going further, and tell the lead.
5. **Banks and strips.** There is no bank pass and no free-face/bank split. The along-contour segmentation in `slope_polygons._segments` is left as is.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/landloss/io/assets/landslide-slope-thresholds.csv` | Modify: two rows (0.5 and 3.5 m) with the new angles. |
| `src/landloss/io/assets/landslide-seed-thresholds.csv` | Modify: add `adjacent_step_m` column. |
| `src/landloss/hazard/landslide/slope_elements.py` | Modify: relax `load_seed_thresholds` column check; `rasterise_ground_map(..., fill_as_soil=)`; extract `_assemble_elements` from `find_slope_elements`. |
| `src/landloss/hazard/landslide/instability_zones.py` | Create: pips, pifs, siz assessment, growth entry point, siz table I/O, `with_walls`. |
| `tests/landloss/hazard/landslide/test_instability_zones.py` | Create. |
| `tests/landloss/hazard/landslide/test_slope_elements.py` | Modify: loader and raster tests; fix any expectation tied to the old 8-band table. |
| `src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_slope_elements.py` | Modify: factor the input loading into `get_pilot_inputs`. |
| `src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_instability_zones.py` | Create: four-panel site figures for A and B, siz file writer, large-polygon flags. |
| `src/scripts/landloss/hazard/landslide/research/slope_elements/config.py` | Modify: `LARGE_POLYGON_M2`. |
| `.../research/slope_elements/pilot_example_slope_elements.md`, `.../landslide/status.md`, `src/landloss/io/assets/README.md`, `.agents/plans/building-face-based-urban-slope-polygons.md`, `doc/whatsnew/` | Docs (Task 8). |

---

### Task 1: Threshold CSVs and loaders

**Files:**
- Modify: `src/landloss/io/assets/landslide-slope-thresholds.csv`
- Modify: `src/landloss/io/assets/landslide-seed-thresholds.csv`
- Modify: `src/landloss/hazard/landslide/slope_elements.py` (`load_seed_thresholds`, ~201-247)
- Test: `tests/landloss/hazard/landslide/test_slope_elements.py`

**Interfaces:**
- Consumes: existing `load_slope_thresholds(path) -> (edges, {group: angles})`, `GROUND_GROUPS`.
- Produces: the two-band slope table via the existing `HEIGHT_BANDS_M`, `STEP_ANGLE_DEG`; `load_adjacent_step_thresholds(path=SEED_THRESHOLDS_PATH) -> dict[str, float]` (added in `instability_zones.py`, Task 3, reading the new column; this task only changes the CSV and keeps `load_seed_thresholds` working).

- [ ] **Step 1: Write the failing test** (append to `test_slope_elements.py`)

```python
def test_shipped_slope_table_has_the_two_siz_bands():
    edges, angles = slope_elements.load_slope_thresholds()
    assert edges == (0.5, 3.5)
    assert angles["soil_like"] == (35.0, 32.0)
    assert angles["weak_rock"] == (45.0, 40.0)
    assert angles["stronger_rock"] == (53.0, 48.0)


def test_seed_loader_accepts_the_adjacent_step_column(tmp_path):
    path = tmp_path / "seed.csv"
    path.write_text(
        "ground_group,min_step_height_m,bank_min_slope_deg,adjacent_step_m\n"
        "soil_like,0.5,18.4,0.7\n"
        "weak_rock,0.5,18.4,3.0\n"
        "stronger_rock,0.5,18.4,3.0\n"
    )
    steps, _ = slope_elements.load_seed_thresholds(path)
    assert steps["soil_like"] == 0.5
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --frozen pytest tests/landloss/hazard/landslide/test_slope_elements.py -k "two_siz_bands or adjacent_step_column" -q`
Expected: both FAIL (old 8-row table; extra column rejected).

- [ ] **Step 3: Implement**

Replace the whole of `landslide-slope-thresholds.csv` with:

```
height_from_m,soil_like,weak_rock,stronger_rock
0.5,35,45,53
3.5,32,40,48
```

Replace the whole of `landslide-seed-thresholds.csv` with:

```
ground_group,min_step_height_m,bank_min_slope_deg,adjacent_step_m
soil_like,0.5,18.4,0.7
weak_rock,0.5,18.4,3.0
stronger_rock,0.5,18.4,3.0
```

In `load_seed_thresholds`, change the column check so the extra column is allowed and update the docstring `Args` to name `adjacent_step_m` ("read by `landloss.hazard.landslide.instability_zones`"):

```python
    columns = {"ground_group", "min_step_height_m", "bank_min_slope_deg"}
    if not columns <= set(table.columns) or sorted(table["ground_group"]) != sorted(
        GROUND_GROUPS
    ):
```

- [ ] **Step 4: Run the whole landslide suite**

Run: `uv run --frozen pytest tests/landloss/hazard/landslide -q`
Expected: the two new tests PASS. The old pipeline now reads the two-band table, so any older test that pinned an angle from the 8-band table may fail; for each, change the expectation to the new table's value (35/45/53 under 3.5 m, 32/40/48 from 3.5 m) and note it in the final summary. Do not weaken the assertion otherwise. Finish with the suite green.

- [ ] **Step 5: Lint**

Run: `uv run --frozen prek run --files src\landloss\hazard\landslide\slope_elements.py tests\landloss\hazard\landslide\test_slope_elements.py`
Expected: pass (re-run if a hook rewrote files).

---

### Task 2: Fill-aware ground group raster

**Files:**
- Modify: `src/landloss/hazard/landslide/slope_elements.py` (`rasterise_ground_map`, ~1922)
- Test: `tests/landloss/hazard/landslide/test_slope_elements.py`

**Interfaces:**
- Consumes: `ground_group_codes(materials)`, `GROUND_GROUPS`, `OFF_MAP_GROUND_GROUP`.
- Produces: `rasterise_ground_map(ground_map, transform, shape, *, fill_as_soil: bool = False) -> (group, position)`. With `fill_as_soil=True`, a piece whose `modification` is `"fill"` is `soil_like` whatever its `material`. Default `False` keeps old behaviour.

- [ ] **Step 1: Failing test**

```python
def test_fill_as_soil_overrides_rock_material():
    ground_map = gpd.GeoDataFrame(
        {"material": ["rock", "rock"], "modification": ["fill", "none"]},
        geometry=[shapely.box(0, 0, 5, 10), shapely.box(5, 0, 10, 10)],
        crs=2193,
    )
    transform = Affine(1, 0, 0, 0, -1, 10)
    plain, _ = slope_elements.rasterise_ground_map(ground_map, transform, (10, 10))
    soil, _ = slope_elements.rasterise_ground_map(
        ground_map, transform, (10, 10), fill_as_soil=True
    )
    weak = slope_elements.GROUND_GROUPS.index("weak_rock")
    soil_like = slope_elements.GROUND_GROUPS.index("soil_like")
    assert (plain == weak).all()
    assert (soil[:, :5] == soil_like).all()
    assert (soil[:, 5:] == weak).all()
```

(Add `import shapely`, `from affine import Affine`, `import geopandas as gpd` to the test imports if missing.)

- [ ] **Step 2:** Run `uv run --frozen pytest tests/landloss/hazard/landslide/test_slope_elements.py -k fill_as_soil -q`. Expected: FAIL (`unexpected keyword argument`).

- [ ] **Step 3: Implement.** Change the signature to `def rasterise_ground_map(ground_map, transform, shape, *, fill_as_soil=False)`, add to the docstring `fill_as_soil: Whether ground mapped as fill (``modification`` is ``"fill"``) is soil_like whatever its material: fill is soil, not rock.`, and after `codes = (...)`:

```python
if fill_as_soil and len(ground_map):
    is_fill = ground_map["modification"].to_numpy() == "fill"
    codes = np.where(is_fill, GROUND_GROUPS.index("soil_like"), codes).astype(np.int8)
```

- [ ] **Step 4:** Run the same command. Expected: PASS. Then `uv run --frozen pytest tests/landloss/hazard/landslide -q` stays green.

---

### Task 3: Pips and pifs

**Files:**
- Create: `src/landloss/hazard/landslide/instability_zones.py`
- Create: `tests/landloss/hazard/landslide/test_instability_zones.py`

**Interfaces:**
- Consumes: `slope_elements.GROUND_GROUPS`, `slope_elements.SEED_THRESHOLDS_PATH`.
- Produces:
  - constants `PIP_DROP_M = 0.7`, `PIP_OFFSETS_M = (1.0, 3.0, 5.0)`, `PIF_JOIN_M = 2.0`, `NEAR_PAIR_M = 3.0`, `MAX_PAIR_M = 30.0`
  - `load_adjacent_step_thresholds(path=SEED_THRESHOLDS_PATH) -> dict[str, float]`, and `ADJACENT_STEP_M`
  - `@dataclass(frozen=True) class Pips: mask: NDArray[bool]; direction: NDArray[int8]` (index into `DIRECTIONS`, -1 off pips)
  - `DIRECTIONS`, `BEARING_DEG`
  - `find_pips(dem, cell_size_m) -> Pips`
  - `cluster_pifs(mask, cell_size_m) -> tuple[NDArray[int32], int]` (labels 1..n on pip cells, 0 elsewhere)

- [ ] **Step 1: Failing tests** (create `test_instability_zones.py`)

```python
"""Tests for the pip, pif and siz stage of the urban slope model."""

import numpy as np
import pytest

from landloss.hazard.landslide import instability_zones as zones

SHAPE = (30, 80)
C_TOP = 20


def _wall(height_m: float) -> np.ndarray:
    cols = np.arange(SHAPE[1])
    return np.tile(np.where(cols <= C_TOP, height_m, 0.0), (SHAPE[0], 1))


def _ramp(height_m: float, slope_deg: float) -> np.ndarray:
    cols = np.arange(SHAPE[1], dtype=float)
    z = height_m - (cols - C_TOP) * np.tan(np.radians(slope_deg))
    return np.tile(np.clip(z, 0.0, height_m), (SHAPE[0], 1))


def test_a_one_metre_wall_gives_a_line_of_pips_facing_east():
    pips = zones.find_pips(_wall(1.0), 1.0)
    assert pips.mask.sum() == SHAPE[0]
    assert pips.mask[:, C_TOP].all()
    assert (pips.direction[:, C_TOP] == 1).all()


def test_a_half_metre_step_is_not_a_pip():
    assert not zones.find_pips(_wall(0.5), 1.0).mask.any()


def test_a_slope_gentler_than_the_drop_gives_no_pips():
    assert not zones.find_pips(_ramp(10.0, 30.0), 1.0).mask.any()


def test_nodata_neighbours_make_no_pip():
    dem = _wall(1.0)
    dem[:, C_TOP + 1 :] = np.nan
    assert not zones.find_pips(dem, 1.0).mask.any()


def test_pips_two_metres_apart_share_a_pif_and_three_do_not():
    mask = np.zeros((20, 30), dtype=bool)
    mask[5, 5] = mask[5, 7] = mask[5, 10] = True
    labels, n = zones.cluster_pifs(mask, 1.0)
    assert n == 2
    assert labels[5, 5] == labels[5, 7] != 0
    assert labels[5, 10] not in (0, labels[5, 5])
    assert labels[~mask].max() == 0


def test_adjacent_step_thresholds_by_group():
    assert zones.ADJACENT_STEP_M == {
        "soil_like": 0.7,
        "weak_rock": 3.0,
        "stronger_rock": 3.0,
    }


def test_adjacent_step_loader_rejects_a_missing_column(tmp_path):
    path = tmp_path / "seed.csv"
    path.write_text(
        "ground_group,min_step_height_m,bank_min_slope_deg\nsoil_like,0.5,18.4\n"
    )
    with pytest.raises(ValueError, match="adjacent_step_m"):
        zones.load_adjacent_step_thresholds(path)
```

- [ ] **Step 2:** Run `uv run --frozen pytest tests/landloss/hazard/landslide/test_instability_zones.py -q`. Expected: FAIL (module not found).

- [ ] **Step 3: Create `instability_zones.py`**

```python
"""Pips, pifs and sizs: the first stage of the urban slope model.

A **pip** (potential instability point) is a cell higher than the cell 1, 3 and
5 m away in the same one of eight directions, each time by more than
:data:`PIP_DROP_M`. It reads the 1 m DEM alone: no material, no other DEM. The
0.7 m keeps little blips out while still catching a wall of about that height.
Along a diagonal a cell is 1.41 m away, so the drop needed is scaled by 1.41.

A **pif** (potential instability face) joins the pips within :data:`PIF_JOIN_M`
of each other. It is tested over every pair of its *points*, which are its pips
and the cells each pip falls to (so a vertical wall, whose pips all sit at the
same height, still has a crest and a foot to measure between). Pairs under
:data:`NEAR_PAIR_M` apart must step by the ground group's ``adjacent_step_m``;
pairs further apart, up to :data:`MAX_PAIR_M`, must be as steep as the group's
slope threshold for the pair's height
(``landslide-slope-thresholds.csv``). A pif that passes is a **siz** (seed
instability zone). Ground mapped as fill is soil, not rock.

The sizs seed the watershed growth of
:mod:`landloss.hazard.landslide.slope_elements`, and the grown elements go to
:func:`landloss.hazard.landslide.slope_polygons.build_slope_polygons`. The siz
table (every pif, with its maximum angles and delta_h and the siz flag) is
also the input of the retaining-wall workflow.
"""

import math
from dataclasses import dataclass, replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from affine import Affine
from numpy.typing import ArrayLike, NDArray
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from landloss.hazard.landslide.slope_elements import (
    BETA_FREE_FACE_GROW_TOL_DEG,
    BANK,
    FREE_FACE,
    GROUND_GROUPS,
    HEIGHT_BANDS_M,
    OUTSIDE,
    SEED_THRESHOLDS_PATH,
    STEP_ANGLE_DEG,
    SlopeElements,
    _absorb_rounded_edges,
    _assemble_elements,
    _cell_size,
    _cost,
    _grow_by_limit,
    _relabel,
    height_band,
    step_angle_deg,
    terrain_layers,
)

# The drop, in metres, a pip has to make at each of the offsets: the lead's
# rule (2026-10-04), to keep blips of a few tenths out and keep walls of about
# 0.7 m in.
PIP_DROP_M = 0.7
# How far along the direction the drop has to hold, in metres.
PIP_OFFSETS_M = (1.0, 3.0, 5.0)
# Pips within this distance, in metres, are one pif.
PIF_JOIN_M = 2.0
# Pairs of points closer than this, in metres, are tested on the step between
# them; pairs further apart are tested on their angle.
NEAR_PAIR_M = 3.0
# Judgement: pairs further apart than this are not compared. A 16 m face at 32
# degrees runs about 26 m, and the pair count grows with the square of a pif's
# size (1.4 billion unbounded on the pilot).
MAX_PAIR_M = 30.0
# Rows of points compared against the rest at a time, to bound memory.
_BLOCK = 256

SIZ_PASS = "siz_pass"

# The eight directions as (row, column) steps, cardinals first so that a tie
# in the drop goes to a cardinal, and each one's bearing in degrees.
DIRECTIONS = ((-1, 0), (0, 1), (1, 0), (0, -1), (-1, 1), (1, 1), (1, -1), (-1, -1))
BEARING_DEG = np.array([0.0, 90.0, 180.0, 270.0, 45.0, 135.0, 225.0, 315.0])


def load_adjacent_step_thresholds(
    path: Path = SEED_THRESHOLDS_PATH,
) -> dict[str, float]:
    """Read the step, in metres, that makes two points under 3 m apart a siz.

    Args:
        path: The seed thresholds CSV, with the column ``adjacent_step_m`` and
            one row per ground group.

    Returns:
        The step by ground group.

    Raises:
        ValueError: If the column or a group is missing, or a step is not
            above zero.
    """
    table = pd.read_csv(path)
    if "adjacent_step_m" not in table.columns or sorted(
        table["ground_group"]
    ) != sorted(GROUND_GROUPS):
        msg = f"{path.name} needs the column adjacent_step_m and one row per group."
        raise ValueError(msg)
    steps = table.set_index("ground_group")["adjacent_step_m"]
    if not (steps > 0).all():
        msg = f"{path.name}: every adjacent_step_m must be above zero."
        raise ValueError(msg)
    return {group: float(steps[group]) for group in GROUND_GROUPS}


# The step between two points under NEAR_PAIR_M apart that makes a siz, by
# ground group (landslide-seed-thresholds.csv, adjacent_step_m): 0.7 m on soil
# keeps retaining walls of that height; 3 m in rock keeps 1-2 m rock walls out.
ADJACENT_STEP_M = load_adjacent_step_thresholds()

if len(HEIGHT_BANDS_M) != 2:
    msg = "landslide-slope-thresholds.csv needs exactly two height bands."
    raise ValueError(msg)
# The height at which the steeper angles give way to the gentler ones, in metres.
BAND_SPLIT_M = HEIGHT_BANDS_M[1]


@dataclass(frozen=True)
class Pips:
    """The pips of a DEM.

    Attributes:
        mask: True on a pip.
        direction: Per cell, the index into :data:`DIRECTIONS` the pip falls
            in (the direction of its largest drop at the furthest offset), -1
            where there is no pip.
    """

    mask: NDArray[np.bool_]
    direction: NDArray[np.int8]


def _shifted(grid: NDArray[np.float64], dr: int, dc: int, k: int) -> NDArray:
    """The grid read ``k`` cells away along ``(dr, dc)``, NaN off the grid."""
    out = np.full_like(grid, np.nan)
    height, width = grid.shape
    r0, r1 = max(0, -k * dr), min(height, height - k * dr)
    c0, c1 = max(0, -k * dc), min(width, width - k * dc)
    if r0 < r1 and c0 < c1:
        out[r0:r1, c0:c1] = grid[r0 + k * dr : r1 + k * dr, c0 + k * dc : c1 + k * dc]
    return out


def offset_cells(cell_size_m: float) -> tuple[int, ...]:
    """The pip offsets in whole cells, each at least one."""
    return tuple(max(1, round(offset / cell_size_m)) for offset in PIP_OFFSETS_M)


def find_pips(dem: ArrayLike, cell_size_m: float) -> Pips:
    """Find the pips on a DEM.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        cell_size_m: The cell size.

    Returns:
        The pips and the direction each falls in.
    """
    z = np.asarray(dem, dtype=float)
    offsets = offset_cells(cell_size_m)
    best = np.full(z.shape, -np.inf)
    direction = np.full(z.shape, -1, dtype=np.int8)
    for index, (dr, dc) in enumerate(DIRECTIONS):
        need = PIP_DROP_M * math.hypot(dr, dc)
        passes = np.ones(z.shape, dtype=bool)
        with np.errstate(invalid="ignore"):
            for k in offsets:
                passes &= (z - _shifted(z, dr, dc, k)) > need
            drop = z - _shifted(z, dr, dc, offsets[-1])
            better = passes & (drop > best)
        best = np.where(better, drop, best)
        direction = np.where(better, index, direction).astype(np.int8)
    return Pips(mask=direction >= 0, direction=direction)


def cluster_pifs(
    mask: NDArray[np.bool_], cell_size_m: float
) -> tuple[NDArray[np.int32], int]:
    """Join the pips within :data:`PIF_JOIN_M` of each other into pifs.

    Returns:
        ``(labels, n_pifs)``: a grid numbering the pifs from 1 on their pips,
        0 elsewhere.
    """
    rows, cols = np.nonzero(mask)
    labels = np.zeros(mask.shape, dtype=np.int32)
    if rows.size == 0:
        return labels, 0
    tree = cKDTree(np.column_stack([rows, cols]) * cell_size_m)
    pairs = tree.query_pairs(PIF_JOIN_M + 1e-9, output_type="ndarray")
    graph = coo_matrix(
        (np.ones(len(pairs), dtype=np.int8), (pairs[:, 0], pairs[:, 1])),
        shape=(rows.size, rows.size),
    )
    n_pifs, component = connected_components(graph, directed=False)
    labels[rows, cols] = component + 1
    return labels, int(n_pifs)
```

(The `assess_pifs`, growth and I/O code arrive in later tasks; the imports of names not yet defined — `_assemble_elements`, `Affine`, `gpd`, `shapely`, `replace`, `ndimage`, `OUTSIDE`, etc. — are added when they are first used. To keep this task's lint clean, **only import what the code written so far uses**: `math`, `dataclass`, `Path`, `np`, `pd`, `ArrayLike`, `NDArray`, `coo_matrix`, `connected_components`, `cKDTree`, `GROUND_GROUPS`, `HEIGHT_BANDS_M`, `SEED_THRESHOLDS_PATH`. Add the rest in Tasks 4-6.)

- [ ] **Step 4:** Run `uv run --frozen pytest tests/landloss/hazard/landslide/test_instability_zones.py -q`. Expected: all PASS. If `test_a_one_metre_wall...` fails on the direction index, check that `DIRECTIONS[1] == (0, 1)` (east) and that cardinals precede diagonals.

- [ ] **Step 5:** `uv run --frozen prek run --files src\landloss\hazard\landslide\instability_zones.py tests\landloss\hazard\landslide\test_instability_zones.py`. Expected: pass.

---

### Task 4: Siz assessment (the pair matrix)

**Files:**
- Modify: `src/landloss/hazard/landslide/instability_zones.py`
- Test: `tests/landloss/hazard/landslide/test_instability_zones.py`

**Interfaces:**
- Consumes: `find_pips`, `cluster_pifs`, `Pips`, `DIRECTIONS`, `BEARING_DEG`, `ADJACENT_STEP_M`, `BAND_SPLIT_M`, `STEP_ANGLE_DEG`, `GROUND_GROUPS`, `offset_cells`, `NEAR_PAIR_M`, `MAX_PAIR_M`.
- Produces: `assess_pifs(dem, pips, pif_labels, ground_group, transform) -> pd.DataFrame` indexed by `pif_id` (1..n) with columns `ground_group`, `n_pips`, `x`, `y`, `crest_z_m`, `toe_z_m`, `fall_bearing_deg`, `max_delta_h_m`, `max_angle_below_deg`, `max_angle_above_deg`, `threshold_angle_deg`, `near_step_pass`, `far_angle_pass`, `is_siz`.
  - `max_angle_*` are the steepest angle over pairs at least `NEAR_PAIR_M` apart whose delta_h is under / at least `BAND_SPLIT_M` (0 if none).
  - `threshold_angle_deg` is the group's angle for the band of the pif's `max_delta_h_m`.

- [ ] **Step 1: Failing tests** (append)

```python
from affine import Affine

from landloss.hazard.landslide.slope_elements import GROUND_GROUPS

TRANSFORM = Affine(1, 0, 0, 0, -1, SHAPE[0])


def _assess(dem, group):
    pips = zones.find_pips(dem, 1.0)
    labels, _ = zones.cluster_pifs(pips.mask, 1.0)
    ground = np.full(dem.shape, GROUND_GROUPS.index(group), dtype=np.int8)
    return zones.assess_pifs(dem, pips, labels, ground, TRANSFORM)


def test_a_soil_wall_of_0_8_m_is_a_siz():
    table = _assess(_wall(0.8), "soil_like")
    assert table["is_siz"].all()
    assert table["near_step_pass"].all()


def test_a_rock_wall_of_2_m_is_not_a_siz_and_one_of_3_m_is():
    assert not _assess(_wall(2.0), "weak_rock")["is_siz"].any()
    assert _assess(_wall(3.0), "weak_rock")["is_siz"].all()
    assert _assess(_wall(3.0), "stronger_rock")["is_siz"].all()


def test_a_tall_rock_slope_uses_the_gentler_angle_above_3_5_m():
    # 42 degrees is under the 45 degree limit for faces under 3.5 m but over the
    # 40 degree limit from 3.5 m up, so height decides.
    tall = _assess(_ramp(10.0, 42.0), "weak_rock")
    assert tall["is_siz"].all()
    assert tall["max_angle_above_deg"].iloc[0] == pytest.approx(42.0, abs=0.5)
    assert not _assess(_ramp(3.0, 42.0), "weak_rock")["is_siz"].any()


def test_a_rock_slope_under_both_limits_is_not_a_siz():
    assert not _assess(_ramp(10.0, 38.0), "weak_rock")["is_siz"].any()


def test_a_soil_slope_of_36_degrees_is_a_siz_and_one_of_34_has_no_pips():
    assert _assess(_ramp(10.0, 36.0), "soil_like")["is_siz"].all()
    assert _assess(_ramp(10.0, 34.0), "soil_like").empty


def test_the_table_records_the_face_for_the_rw_workflow():
    row = _assess(_ramp(10.0, 50.0), "weak_rock").iloc[0]
    assert row["ground_group"] == "weak_rock"
    assert row["fall_bearing_deg"] == pytest.approx(90.0)
    assert row["crest_z_m"] == pytest.approx(10.0)
    assert row["toe_z_m"] < 1.0
    assert row["max_delta_h_m"] > 8.0
    assert row["threshold_angle_deg"] == 40.0


def test_pairs_further_than_the_cap_are_not_compared():
    cap = int(zones.MAX_PAIR_M)
    wide = np.zeros((10, 200))
    wide[:, :100] = 100.0
    wide[:, 100:] = 0.0
    pips = zones.find_pips(wide, 1.0)
    labels, _ = zones.cluster_pifs(pips.mask, 1.0)
    ground = np.zeros(wide.shape, dtype=np.int8)
    table = zones.assess_pifs(wide, pips, labels, ground, Affine(1, 0, 0, 0, -1, 10))
    assert (table["max_angle_below_deg"] == 0).all()
    assert cap == 30
```

- [ ] **Step 2:** Run `uv run --frozen pytest tests/landloss/hazard/landslide/test_instability_zones.py -q`. Expected: the new tests FAIL (`assess_pifs` missing).

- [ ] **Step 3: Implement** (append to `instability_zones.py`; add imports `from affine import Affine`, `from scipy import ndimage`)

```python
def _pair_stats(
    rows: NDArray[np.intp],
    cols: NDArray[np.intp],
    z: NDArray[np.float64],
    *,
    cell_size_m: float,
    step_m: float,
) -> tuple[float, float, float, bool]:
    """The pair statistics of one pif's points, sorted by row.

    Returns:
        ``(max_below, max_above, max_delta_h, near_pass)``: the steepest angle
        in degrees over pairs at least :data:`NEAR_PAIR_M` apart (and within
        :data:`MAX_PAIR_M`) whose delta_h is under / at least
        :data:`BAND_SPLIT_M`, the largest delta_h of any pair, and whether a
        pair under :data:`NEAR_PAIR_M` apart steps by ``step_m``.
    """
    reach = math.ceil(MAX_PAIR_M / cell_size_m)
    max_below = max_above = max_dh = 0.0
    near_pass = False
    for start in range(0, rows.size, _BLOCK):
        stop = min(start + _BLOCK, rows.size)
        lo = int(np.searchsorted(rows, rows[start] - reach, side="left"))
        hi = int(np.searchsorted(rows, rows[stop - 1] + reach, side="right"))
        dist = (
            np.hypot(
                rows[start:stop, None] - rows[None, lo:hi],
                cols[start:stop, None] - cols[None, lo:hi],
            )
            * cell_size_m
        )
        dh = z[start:stop, None] - z[None, lo:hi]
        valid = (dh > 0) & (dist <= MAX_PAIR_M)
        if not valid.any():
            continue
        near = valid & (dist < NEAR_PAIR_M)
        far = valid & ~near
        near_pass = near_pass or bool((dh[near] >= step_m).any())
        max_dh = max(max_dh, float(dh[valid].max()))
        angle = np.degrees(np.arctan2(dh, dist))
        high = dh >= BAND_SPLIT_M
        if (far & ~high).any():
            max_below = max(max_below, float(angle[far & ~high].max()))
        if (far & high).any():
            max_above = max(max_above, float(angle[far & high].max()))
    return max_below, max_above, max_dh, near_pass


def assess_pifs(
    dem: ArrayLike,
    pips: Pips,
    pif_labels: NDArray[np.int32],
    ground_group: ArrayLike,
    transform: Affine,
) -> pd.DataFrame:
    """Test every pif over all pairs of its points and flag the sizs.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        pips: From :func:`find_pips`.
        pif_labels: From :func:`cluster_pifs`.
        ground_group: The ground group code of every cell
            (:func:`landloss.hazard.landslide.slope_elements.rasterise_ground_map`
            with ``fill_as_soil=True``).
        transform: The grid's affine transform, north-up with square cells.

    Returns:
        One row per pif, indexed by ``pif_id`` (see the module docstring for
        the columns): all pifs, not only the sizs. ``is_siz`` is the near step
        test or the far angle test passing.
    """
    z = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    cell_size_m = _cell_size(transform)
    n_pifs = int(pif_labels.max())
    columns = [
        "ground_group",
        "n_pips",
        "x",
        "y",
        "crest_z_m",
        "toe_z_m",
        "fall_bearing_deg",
        "max_delta_h_m",
        "max_angle_below_deg",
        "max_angle_above_deg",
        "threshold_angle_deg",
        "near_step_pass",
        "far_angle_pass",
        "is_siz",
    ]
    if n_pifs == 0:
        return pd.DataFrame(columns=columns).rename_axis("pif_id")
    height, width = z.shape
    rows, cols = np.nonzero(pips.mask)
    owner = pif_labels[rows, cols].astype(np.int64)
    fall = pips.direction[rows, cols]
    step_r = np.array([d[0] for d in DIRECTIONS])[fall]
    step_c = np.array([d[1] for d in DIRECTIONS])[fall]

    # The points of a pif: its pips, and the cells they fall to at each offset.
    point_rows, point_cols, point_owner = [rows], [cols], [owner]
    for k in offset_cells(cell_size_m):
        r2, c2 = rows + k * step_r, cols + k * step_c
        inside = (r2 >= 0) & (r2 < height) & (c2 >= 0) & (c2 < width)
        inside[inside] = np.isfinite(z[r2[inside], c2[inside]])
        point_rows.append(r2[inside])
        point_cols.append(c2[inside])
        point_owner.append(owner[inside])
    all_rows = np.concatenate(point_rows)
    all_cols = np.concatenate(point_cols)
    all_owner = np.concatenate(point_owner)
    key = all_owner * height * width + all_rows * width + all_cols
    _, first = np.unique(key, return_index=True)
    all_rows, all_cols, all_owner = all_rows[first], all_cols[first], all_owner[first]
    order = np.lexsort((all_rows, all_owner))
    all_rows, all_cols, all_owner = all_rows[order], all_cols[order], all_owner[order]
    all_z = z[all_rows, all_cols]
    ends = np.cumsum(np.bincount(all_owner, minlength=n_pifs + 1))

    n_groups = len(GROUND_GROUPS)
    by_group = np.bincount(
        owner * n_groups + groups[rows, cols], minlength=(n_pifs + 1) * n_groups
    ).reshape(-1, n_groups)
    pif_group = by_group.argmax(axis=1)
    index = np.arange(1, n_pifs + 1)
    n_pips = np.bincount(owner, minlength=n_pifs + 1)
    sin = np.bincount(owner, np.sin(np.radians(BEARING_DEG[fall])), n_pifs + 1)
    cos = np.bincount(owner, np.cos(np.radians(BEARING_DEG[fall])), n_pifs + 1)
    pip_z = z[rows, cols]
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e

    table = pd.DataFrame(index=pd.Index(index, name="pif_id"))
    table["ground_group"] = np.asarray(GROUND_GROUPS)[pif_group[index]]
    table["n_pips"] = n_pips[index]
    table["x"] = ndimage.mean(x, owner, index)
    table["y"] = ndimage.mean(y, owner, index)
    table["crest_z_m"] = ndimage.maximum(pip_z, owner, index)
    table["toe_z_m"] = ndimage.minimum(all_z, all_owner, index)
    table["fall_bearing_deg"] = np.degrees(np.arctan2(sin[index], cos[index])) % 360.0

    stats = np.zeros((n_pifs, 4))
    for i, pif in enumerate(index):
        lo, hi = ends[pif - 1], ends[pif]
        group = GROUND_GROUPS[pif_group[pif]]
        stats[i] = _pair_stats(
            all_rows[lo:hi],
            all_cols[lo:hi],
            all_z[lo:hi],
            cell_size_m=cell_size_m,
            step_m=ADJACENT_STEP_M[group],
        )
    table["max_delta_h_m"] = stats[:, 2]
    table["max_angle_below_deg"] = stats[:, 0]
    table["max_angle_above_deg"] = stats[:, 1]
    below = np.array([STEP_ANGLE_DEG[g][0] for g in table["ground_group"]])
    above = np.array([STEP_ANGLE_DEG[g][1] for g in table["ground_group"]])
    table["threshold_angle_deg"] = np.where(stats[:, 2] >= BAND_SPLIT_M, above, below)
    table["near_step_pass"] = stats[:, 3].astype(bool)
    table["far_angle_pass"] = (stats[:, 0] >= below) | (stats[:, 1] >= above)
    table["is_siz"] = table["near_step_pass"] | table["far_angle_pass"]
    return table
```

`ends[pif - 1]` is correct because `bincount(all_owner)` has a zero at index 0 (no point has owner 0), so `ends[0] == 0` and pif p's slice is `ends[p-1]:ends[p]`.

- [ ] **Step 4:** Run `uv run --frozen pytest tests/landloss/hazard/landslide/test_instability_zones.py -q`. Expected: all PASS. If a rock-angle test is off by a hair (an angle exactly on a limit), do not loosen the library: move the test slope 1 degree away from the limit and say so.

- [ ] **Step 5:** prek on the two files. Expected: pass.

---

### Task 5: Extract the shared post-growth assembly

A pure refactor: `find_slope_elements` keeps its behaviour; its second half becomes `_assemble_elements` so the new entry point can reuse it.

**Files:**
- Modify: `src/landloss/hazard/landslide/slope_elements.py` (`find_slope_elements`, ~1720-1900)

**Interfaces:**
- Consumes: the existing local variables of `find_slope_elements`.
- Produces: 

```python
def _assemble_elements(
    elevation: NDArray[np.float64],
    groups: NDArray[np.int8],
    transform: Affine,
    layers: TerrainLayers,
    labels: NDArray[np.int32],
    seed_grid: NDArray[np.int32],
    seed_score: NDArray[np.float64],
    grown_in_by_label: NDArray[np.str_],
    element_type_by_label: NDArray[np.str_] | None,
    core_grid: NDArray[np.bool_],
    categories: Mapping[str, ArrayLike] | None,
) -> SlopeElements:
```

- [ ] **Step 1: Record the baseline.** Run `uv run --frozen pytest tests/landloss/hazard/landslide -q` and note the pass count (must be unchanged afterwards).

- [ ] **Step 2: Move the code.** Cut everything in `find_slope_elements` from the line `n_labels = int(labels.max())` to the final `return SlopeElements(...)` into a new function `_assemble_elements` with the signature above (place it directly after `find_slope_elements`; give it a one-paragraph docstring: "The half of :func:`find_slope_elements` after the seeds have grown: measure the regions, drop the ones that are not elements, and build the table, catchments and stack links."). Inside the moved code make exactly three edits:

  1. Delete the `if n_labels:` block's two lines computing `bank_score` and `score = np.where(seed_grid > n_free_faces, bank_score, exceedance)`, and use the argument instead:

     ```python
         if n_labels:
             # Rounded to a micro-degree, ... (keep the existing comment)
             score = np.round(np.nan_to_num(seed_score, nan=-np.inf), _SCORE_DECIMALS)
     ```
  2. Replace `grown_in = np.where(kept <= n_free_faces, FREE_FACE_PASS, BANK_PASS)` with `grown_in = grown_in_by_label[kept]`.
  3. Replace the `elements.insert(1, "element_type", np.where(measured["is_free_face"], FREE_FACE, BANK))` call with:

     ```python
         element_type = (
             np.where(measured["is_free_face"], FREE_FACE, BANK)
             if element_type_by_label is None
             else element_type_by_label[kept]
         )
         elements.insert(1, "element_type", element_type)
     ```

  Rename in the moved code: `elevation`, `groups`, `layers`, `core_grid`, `categories`, `transform` keep their names and `cell_size_m = _cell_size(transform)` is recomputed at the top of `_assemble_elements`.

- [ ] **Step 3: Call it from `find_slope_elements`.** After building `labels` and `seed_grid` (the existing lines up to and including `seed_grid = np.where(labels > OUTSIDE, seed_grid, OUTSIDE).astype(np.int32)`), end the function with:

```python
    n_labels = int(labels.max())
    bank_score = layers.slope_coarse_deg - bank_seed_slope_deg(groups)
    seed_score = np.where(seed_grid > n_free_faces, bank_score, exceedance)
    by_label = np.arange(n_labels + 1)
    return _assemble_elements(
        elevation,
        groups,
        transform,
        layers,
        labels,
        seed_grid,
        seed_score,
        np.where(by_label <= n_free_faces, FREE_FACE_PASS, BANK_PASS),
        None,
        core_grid,
        categories,
    )
```

- [ ] **Step 4: Verify behaviour is unchanged.** Run `uv run --frozen pytest tests/landloss -q -x`. Expected: the same pass count as Step 1 (897 overall at the time of writing, before this plan's new tests). Any failure means the move changed behaviour: fix the move, never the test.

- [ ] **Step 5:** prek on `slope_elements.py`. Expected: pass.

---

### Task 6: Grow the sizs and build the elements

**Files:**
- Modify: `src/landloss/hazard/landslide/instability_zones.py`
- Test: `tests/landloss/hazard/landslide/test_instability_zones.py`

**Interfaces:**
- Consumes: `find_pips`, `cluster_pifs`, `assess_pifs`, `_assemble_elements(...)` (Task 5), `_grow_by_limit`, `_absorb_rounded_edges`, `_cost`, `_relabel`, `height_band`, `step_angle_deg`, `terrain_layers`, `_cell_size`, `BETA_FREE_FACE_GROW_TOL_DEG`, `FREE_FACE`, `BANK`, `OUTSIDE`, `SlopeElements`.
- Produces:
  - `@dataclass(frozen=True) class InstabilityZones: found: SlopeElements; pips: Pips; pif_labels: NDArray[int32]; sizs: pd.DataFrame` (the table of Task 4, all pifs)
  - `find_instability_zones(dem, ground_group, transform, *, categories=None, core=None) -> InstabilityZones`: elements are all `FREE_FACE` (walled), `grown_in == SIZ_PASS`, with the columns of `find_slope_elements` plus `siz_id` and the siz's `siz_threshold_angle_deg`, `siz_max_angle_below_deg`, `siz_max_angle_above_deg`, `siz_max_delta_h_m`.
  - `with_walls(found, walled) -> SlopeElements`: `walled` a bool or a `pd.Series` of bool indexed by element label; the element's type becomes `FREE_FACE` (wall wedge) where walled and `BANK` (headscarp band behind the crest) where not.

- [ ] **Step 1: Failing tests** (append)

```python
import pandas as pd

from landloss.hazard.landslide.slope_elements import BANK, FREE_FACE


def _zones(dem, group):
    ground = np.full(dem.shape, GROUND_GROUPS.index(group), dtype=np.int8)
    return zones.find_instability_zones(dem, ground, TRANSFORM)


def test_a_soil_cut_makes_one_walled_element_with_its_siz_recorded():
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    elements = result.found.elements
    assert len(elements) == 1
    row = elements.iloc[0]
    assert row["element_type"] == FREE_FACE
    assert row["grown_in"] == zones.SIZ_PASS
    assert row["height_m"] == pytest.approx(6.0, abs=1.0)
    assert row["siz_id"] in result.sizs.index
    assert row["siz_max_delta_h_m"] > 5.0


def test_a_rock_wall_of_2_m_makes_no_element():
    assert _zones(_wall(2.0), "weak_rock").found.elements.empty


def test_a_gentle_slope_makes_no_element():
    assert _zones(_ramp(10.0, 25.0), "soil_like").found.elements.empty


def test_with_walls_switches_the_element_type_per_element():
    found = _zones(_ramp(6.0, 60.0), "soil_like").found
    assert (zones.with_walls(found, True).elements["element_type"] == FREE_FACE).all()
    assert (zones.with_walls(found, False).elements["element_type"] == BANK).all()
    mixed = pd.Series([False], index=found.elements.index)
    assert (zones.with_walls(found, mixed).elements["element_type"] == BANK).all()


def test_the_unwalled_zone_is_narrower_than_the_walled_one_for_a_tall_wall():
    from landloss.hazard.landslide.slope_polygons import build_slope_polygons

    dem = _ramp(6.0, 80.0)
    found = _zones(dem, "soil_like").found
    walled = build_slope_polygons(zones.with_walls(found, True), dem, TRANSFORM)
    bare = build_slope_polygons(zones.with_walls(found, False), dem, TRANSFORM)
    assert len(walled.polygons) >= 1
    assert len(bare.polygons) >= 1
```

- [ ] **Step 2:** Run the test file. Expected: new tests FAIL (`find_instability_zones` missing).

- [ ] **Step 3: Implement** (append; add the imports listed under Consumes, plus `replace` from dataclasses and `Mapping` from `collections.abc`)

```python
@dataclass(frozen=True)
class InstabilityZones:
    """The elements grown from the sizs, with the stage 1 results they came from.

    Attributes:
        found: The elements (all walled; see :func:`with_walls`), in the form
            :func:`landloss.hazard.landslide.slope_polygons.build_slope_polygons`
            takes.
        pips: The pips.
        pif_labels: The pifs on their pips' cells.
        sizs: The siz table, one row per pif (see :func:`assess_pifs`).
    """

    found: SlopeElements
    pips: Pips
    pif_labels: NDArray[np.int32]
    sizs: pd.DataFrame


def find_instability_zones(
    dem: ArrayLike,
    ground_group: ArrayLike,
    transform: Affine,
    *,
    categories: Mapping[str, ArrayLike] | None = None,
    core: ArrayLike | None = None,
) -> InstabilityZones:
    """Find the pips, pifs and sizs on a DEM and grow the sizs into elements.

    Each siz's pips seed the watershed growth of the old free-face pass, into
    cells steeper than the siz's own threshold angle less
    :data:`~landloss.hazard.landslide.slope_elements.BETA_FREE_FACE_GROW_TOL_DEG`
    (so material enters only here), and the grown regions go through the
    junk filters of :func:`landloss.hazard.landslide.slope_elements.find_slope_elements`
    (under 0.5 m high, under 3 m long, gentler overall than 18.4 degrees, no
    transect). The siz decision is made on the pif; a grown element is not
    re-tested.

    Args:
        dem: Ground elevation in metres on a north-up grid of square cells,
            NaN for nodata and outside the LiDAR.
        ground_group: The ground group code of every cell, with fill as soil
            (``rasterise_ground_map(..., fill_as_soil=True)``).
        transform: The grid's affine transform.
        categories: Integer grids to take the majority of over each element.
        core: A tile's core, as in ``find_slope_elements``.

    Returns:
        The elements, pips, pifs and the siz table.

    Raises:
        ValueError: If the grids do not share a shape.
    """
    elevation = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    if groups.shape != elevation.shape:
        msg = f"The ground group grid is {groups.shape}, the DEM {elevation.shape}."
        raise ValueError(msg)
    core_grid = np.ones(elevation.shape, dtype=bool)
    if core is not None:
        core_grid = np.asarray(core, dtype=bool)
        if core_grid.shape != elevation.shape:
            msg = f"The core grid is {core_grid.shape}, the DEM {elevation.shape}."
            raise ValueError(msg)
    cell_size_m = _cell_size(transform)
    layers = terrain_layers(elevation, cell_size_m)

    pips = find_pips(elevation, cell_size_m)
    pif_labels, _ = cluster_pifs(pips.mask, cell_size_m)
    sizs = assess_pifs(elevation, pips, pif_labels, groups, transform)

    band = height_band(np.nan_to_num(layers.step_height_m, nan=0.0))
    threshold = step_angle_deg(groups, band)
    exceedance = layers.slope_coarse_deg - threshold
    siz_ids = sizs.index[sizs["is_siz"]].to_numpy()
    n_seeds = int(siz_ids.size)
    lookup = np.zeros(len(sizs) + 1, dtype=np.int32)
    lookup[siz_ids] = np.arange(1, n_seeds + 1, dtype=np.int32)
    seeds = lookup[pif_labels]
    if n_seeds:
        limit = np.zeros(n_seeds + 1)
        limit[1:] = (
            sizs.loc[siz_ids, "threshold_angle_deg"].to_numpy()
            - BETA_FREE_FACE_GROW_TOL_DEG
        )
        slope = np.nan_to_num(layers.slope_fine_deg, nan=-np.inf)
        finite = np.isfinite(elevation) & np.isfinite(layers.slope_fine_deg)
        grown = _grow_by_limit(
            seeds,
            n_seeds,
            _cost(exceedance),
            slope=slope,
            finite=finite,
            limit=limit,
            cell_limit=np.nan_to_num(
                threshold - BETA_FREE_FACE_GROW_TOL_DEG, nan=np.inf
            ),
        )
        grown = _absorb_rounded_edges(grown, layers)
        present = np.bincount(grown.ravel()) > 0
        labels = _relabel(grown, present)
        seed_grid = _relabel(seeds, present[: seeds.max() + 1])
    else:
        labels = np.zeros(elevation.shape, dtype=np.int32)
        seed_grid = labels
    seed_grid = np.where(labels > OUTSIDE, seed_grid, OUTSIDE).astype(np.int32)
    n_labels = int(labels.max())
    found = _assemble_elements(
        elevation,
        groups,
        transform,
        layers,
        labels,
        seed_grid,
        exceedance,
        np.full(n_labels + 1, SIZ_PASS),
        np.full(n_labels + 1, FREE_FACE),
        core_grid,
        categories,
    )
    elements = found.elements
    seeded = elements["seed_row"].to_numpy() >= 0
    siz_id = np.zeros(len(elements), dtype=np.int64)
    siz_id[seeded] = pif_labels[
        elements["seed_row"].to_numpy()[seeded],
        elements["seed_col"].to_numpy()[seeded],
    ]
    elements = elements.assign(siz_id=siz_id)
    for column, source in (
        ("siz_threshold_angle_deg", "threshold_angle_deg"),
        ("siz_max_angle_below_deg", "max_angle_below_deg"),
        ("siz_max_angle_above_deg", "max_angle_above_deg"),
        ("siz_max_delta_h_m", "max_delta_h_m"),
    ):
        elements[column] = sizs[source].reindex(siz_id).to_numpy()
    return InstabilityZones(
        found=replace(found, elements=elements),
        pips=pips,
        pif_labels=pif_labels,
        sizs=sizs,
    )


def with_walls(found: SlopeElements, walled: bool | pd.Series) -> SlopeElements:
    """Set which elements carry a retaining wall.

    The polygon builder reads a ``free_face`` as a wall (the active wedge
    behind the crest) and a ``bank`` as no wall (the headscarp band behind the
    crest, or the fill bank rule).

    Args:
        found: The elements, from :func:`find_instability_zones`.
        walled: One flag for every element, or a Series of flags indexed by
            element label (missing elements are not walled).

    Returns:
        The elements with ``element_type`` set.
    """
    flags = (
        pd.Series(walled, index=found.elements.index)
        if isinstance(walled, bool)
        else walled.reindex(found.elements.index, fill_value=False)
    )
    element_type = np.where(flags.to_numpy(dtype=bool), FREE_FACE, BANK)
    return replace(found, elements=found.elements.assign(element_type=element_type))
```

- [ ] **Step 4:** Run the test file. Expected: PASS. If `test_a_soil_cut_makes_one_walled_element...` finds 0 or 2 elements, print `result.sizs` and `result.found.labels.max()` to see whether growth or a junk filter removed it; the expected cause of a split would be seeds growing apart, not a threshold issue, and the fix belongs in the growth call (not in loosening the test). If `siz_id` is 0 for an element, its seed peak cell was not a pip: check `seed_row`/`seed_col` are taken from `seed_grid`, which holds the seeds only.

- [ ] **Step 5:** `uv run --frozen pytest tests/landloss -q`, then prek on the two files. Expected: all green.

---

### Task 7: The siz file for the RW workflow

**Files:**
- Modify: `src/landloss/hazard/landslide/instability_zones.py`
- Test: `tests/landloss/hazard/landslide/test_instability_zones.py`

**Interfaces:**
- Consumes: the siz table (Task 4), `Pips`, `pif_labels`.
- Produces: `gen_siz_table(zones_result: InstabilityZones, transform: Affine, *, crs: int) -> gpd.GeoDataFrame` (one row per pif, indexed `pif_id`, the table's columns plus a `geometry` of the pif's pips as a MultiPoint at the cell centres); `write_siz_table(table, path) -> None` (GeoParquet) and `read_siz_table(path) -> gpd.GeoDataFrame` (`get_` is for fetching from outside the project; this reads our own file, so `read_`).

- [ ] **Step 1: Failing test**

```python
def test_the_siz_file_round_trips_with_point_geometry(tmp_path):
    result = _zones(_ramp(6.0, 60.0), "soil_like")
    table = zones.gen_siz_table(result, TRANSFORM, crs=2193)
    path = tmp_path / "siz.parquet"
    zones.write_siz_table(table, path)
    back = zones.read_siz_table(path)
    assert list(back.index) == list(result.sizs.index)
    assert back["is_siz"].tolist() == result.sizs["is_siz"].tolist()
    assert back.geometry.iloc[0].geom_type == "MultiPoint"
    assert back.crs.to_epsg() == 2193
```

- [ ] **Step 2:** Run it. Expected: FAIL (functions missing).

- [ ] **Step 3: Implement** (append)

```python
def gen_siz_table(
    result: InstabilityZones, transform: Affine, *, crs: int
) -> gpd.GeoDataFrame:
    """The siz table with each pif's pips as geometry, for the RW workflow.

    Args:
        result: From :func:`find_instability_zones`.
        transform: The grid's affine transform.
        crs: The EPSG code of the grid.

    Returns:
        The siz table (every pif, ``is_siz`` says which are sizs) with a
        MultiPoint of the pif's pip cell centres.
    """
    rows, cols = np.nonzero(result.pips.mask)
    owner = result.pif_labels[rows, cols]
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    points = pd.DataFrame({"x": x, "y": y, "pif_id": owner})
    geometry = {
        pif: shapely.MultiPoint(group[["x", "y"]].to_numpy())
        for pif, group in points.groupby("pif_id")
    }
    return gpd.GeoDataFrame(
        result.sizs,
        geometry=gpd.GeoSeries(geometry, crs=crs).reindex(result.sizs.index),
        crs=crs,
    )


def write_siz_table(table: gpd.GeoDataFrame, path: Path) -> None:
    """Write the siz table as GeoParquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)


def read_siz_table(path: Path) -> gpd.GeoDataFrame:
    """Read a siz table written by :func:`write_siz_table`."""
    return gpd.read_parquet(path)
```

- [ ] **Step 4:** Run the test file. Expected: PASS. Then `uv run --frozen pytest tests/landloss -q` green, prek on both files.

---

### Task 8: Pilot run, figures, flags, docs

Research code is not maintained and is excluded from prek, so this task has no unit tests; verification is running it over the pilot.

**Files:**
- Modify: `src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_slope_elements.py` (factor out loading)
- Create: `src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_instability_zones.py`
- Modify: `src/scripts/landloss/hazard/landslide/research/slope_elements/config.py`
- Modify docs listed below

**Interfaces:**
- Consumes: `find_instability_zones`, `with_walls`, `gen_siz_table`, `write_siz_table`, `rasterise_ground_map(..., fill_as_soil=True)`, `build_slope_polygons`; from the old figure script `Pilot`, `window_slices`, `draw_base`, `draw_polygons`, `windowed_result`, `site_layers`, `draw_gns`, `polygon_handles`, `FILL_MODIFICATION`, `CRS`, `INK`, `FIG_DIR`.
- Produces: per-site PNGs `report/hazard/landslide/slope-elements/fig/pilot_instability_<site id>.png`, the siz file `temp/pilot-siz-<extent>.parquet`, and a printed list of large polygons for the lead.

- [ ] **Step 1: Factor the loading.** In `fig_pilot_example_slope_elements.py` move the first part of `get_pilot_run` (from `dem_da = rioxarray.open_rasterio(...)` to `group, position = rasterise_ground_map(...)`) into:

```python
def get_pilot_inputs(*, extent, fill_as_soil=False):
    """The DEM, water mask, ground groups and ground map of the pilot."""
    dem_da = rioxarray.open_rasterio(dem_path(1, extent=extent), masked=True).squeeze(
        "band", drop=True
    )
    dem = dem_da.to_numpy().astype("float64")
    transform = dem_da.rio.transform()
    bbox = dem_da.rio.bounds()
    land = get_nz_coastline_polygons(bbox=bbox, crs=CRS, use_cache=True)
    on_land = features.rasterize(
        [(geometry, 1) for geometry in land.geometry],
        out_shape=dem.shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    water = ~on_land
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    group, position = rasterise_ground_map(
        ground_map, transform, dem.shape, fill_as_soil=fill_as_soil
    )
    return (
        dem,
        np.where(water, np.nan, dem),
        water,
        transform,
        bbox,
        ground_map,
        group,
        position,
    )
```

and make `get_pilot_run` start with `dem, dem_run, water, transform, bbox, ground_map, group, position = get_pilot_inputs(extent=extent)` (same behaviour, old pipeline unchanged). Run the old script once to confirm it still draws (`uv run --frozen python src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_slope_elements.py`); expected: it prints the same whole-pilot summary as before.

- [ ] **Step 2: Config.** Add to `config.py`:

```python
# Evacuated polygons over this area, in square metres, are flagged for the lead
# to review (the old pilot's largest was 2,142 m2).
LARGE_POLYGON_M2 = 2000.0
# Where the siz table is written, for the RW workflow.
PILOT_SIZ_FILE = "pilot-siz"
```

- [ ] **Step 3: Create the figure script.** `fig_pilot_example_instability_zones.py`:

```python
"""Stage D2: pips, pifs, sizs and the evacuated zones on real pilot ground.

Runs :func:`landloss.hazard.landslide.instability_zones.find_instability_zones`
once over the whole pilot DEM, with fill taken as soil, and draws each site in
``config.PILOT_SITES`` as four map panels:

1. pips (dots, so the hillshade shows) coloured by whether their pif is a siz;
2. the elements grown from the sizs, each outlined;
3. the evacuated zones if **every siz has a retaining wall**;
4. the evacuated zones if **no siz has one**.

It also writes the siz table (every pif) for the retaining-wall workflow and
prints the evacuated polygons over ``config.LARGE_POLYGON_M2`` for review.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_instability_zones.py
"""

import time

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from rasterio import features

from landloss.hazard.landslide.instability_zones import (
    find_instability_zones,
    gen_siz_table,
    with_walls,
    write_siz_table,
)
from landloss.hazard.landslide.slope_polygons import EVACUATED, build_slope_polygons
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.research.slope_elements import config
from scripts.landloss.hazard.landslide.research.slope_elements import (
    fig_pilot_example_slope_elements as base,
)
from scripts.landloss.paths import TEMP_DIR

SIZ_COLOUR = "#eb6834"
NOT_SIZ_COLOUR = "#6e6e6e"


def get_zone_run(*, extent):
    """Run the zones and both wall scenarios over the whole pilot."""
    dem, dem_run, water, transform, bbox, ground_map, group, position = (
        base.get_pilot_inputs(extent=extent, fill_as_soil=True)
    )
    start = time.perf_counter()
    zones = find_instability_zones(
        dem_run, group, transform, categories={"ground_row": position}
    )
    zones_seconds = time.perf_counter() - start
    elements = zones.found.elements
    rows = elements["majority_ground_row"].to_numpy()
    on_map = rows >= 0
    modification = np.where(
        on_map, ground_map["modification"].to_numpy()[np.maximum(rows, 0)], ""
    )
    is_fill = pd.Series(modification == base.FILL_MODIFICATION, index=elements.index)
    thickness = pd.Series(
        np.where(
            is_fill,
            ground_map["fill_thickness_m"].to_numpy()[np.maximum(rows, 0)],
            np.nan,
        ),
        index=elements.index,
    )
    scenarios = {}
    for name, walled in (("walled", True), ("bare", False)):
        start = time.perf_counter()
        found = with_walls(zones.found, walled)
        result = build_slope_polygons(
            found, dem_run, transform, is_fill=is_fill, fill_thickness_m=thickness
        )
        scenarios[name] = (found, result, time.perf_counter() - start)
    return dem, water, transform, ground_map, zones, zones_seconds, scenarios


def pilot_view(dem, water, transform, ground_map, zones, scenario):
    """A ``Pilot`` the old drawing functions accept, for one wall scenario."""
    found, result, _ = scenario
    empty = np.zeros(dem.shape, dtype=bool)
    return base.Pilot(
        dem=dem,
        water=water,
        transform=transform,
        seed_free_face=zones.pips.mask,
        seed_bank=empty,
        found=found,
        result=result,
        ground_map=ground_map,
        walls=base.gpd.GeoDataFrame(geometry=[], crs=base.CRS),
        breaks=base.gpd.GeoDataFrame(geometry=[], crs=base.CRS),
        cut_fill_lines=base.gpd.GeoDataFrame(geometry=[], crs=base.CRS),
        genesis=base.gpd.GeoDataFrame({"Type": []}, geometry=[], crs=base.CRS),
        is_fill=pd.Series(dtype=bool),
        seconds=scenario[2],
    )


def draw_pips(ax, zones, rows, cols, bounds):
    """Pips as dots, orange where the pif is a siz and grey where it is not."""
    window = zones.pif_labels[rows, cols]
    is_siz = zones.sizs["is_siz"].reindex(
        np.arange(zones.sizs.index.max() + 1), fill_value=False
    )
    siz_cells = (window > 0) & is_siz.to_numpy()[window]
    for mask, colour in (
        (siz_cells, SIZ_COLOUR),
        ((window > 0) & ~siz_cells, NOT_SIZ_COLOUR),
    ):
        r, c = np.nonzero(mask)
        ax.scatter(
            bounds[0] + c + 0.5,
            bounds[3] - r - 0.5,
            s=base.SEED_DOT_SIZE,
            color=colour,
            lw=0,
            zorder=3,
        )
    return int(siz_cells.sum()), int(((window > 0) & ~siz_cells).sum())


def draw_elements(ax, found, rows, cols, transform):
    """Each element's outline, as polygons of its labelled cells."""
    window = found.labels[rows, cols]
    shifted = transform * (cols.start, rows.start)
    window_transform = type(transform)(
        transform.a, 0, shifted[0], 0, transform.e, shifted[1]
    )
    count = 0
    for geometry, label in features.shapes(
        window.astype("int32"), mask=window > 0, transform=window_transform
    ):
        x, y = zip(*geometry["coordinates"][0], strict=True)
        ax.plot(x, y, color=base.INK, lw=0.6, zorder=4)
        ax.fill(x, y, color=SIZ_COLOUR, alpha=0.3, lw=0, zorder=3)
        count += 1
    return count


def draw_site(site, view_walled, view_bare, zones, *, intervals, max_contours):
    x, y, half = site["x"], site["y"], site["half_size_m"]
    rows, cols, bounds = base.window_slices(view_walled, x, y, half)
    fig = plt.figure(figsize=(13, 14.6))
    grid = fig.add_gridspec(
        2, 2, left=0.06, right=0.99, top=0.9, bottom=0.1, hspace=0.46, wspace=0.14
    )
    axes = [fig.add_subplot(grid[i, j]) for i in range(2) for j in range(2)]
    for ax in axes:
        base.draw_base(
            ax,
            view_walled,
            rows,
            cols,
            bounds,
            intervals=intervals,
            max_contours=max_contours,
            by_material=ax is axes[0],
        )
    n_siz, n_not = draw_pips(axes[0], zones, rows, cols, bounds)
    n_elements = draw_elements(
        axes[1], view_walled.found, rows, cols, view_walled.transform
    )
    base.draw_polygons(
        axes[2], view_walled, base.windowed_result(view_walled, rows, cols)
    )
    base.draw_polygons(axes[3], view_bare, base.windowed_result(view_bare, rows, cols))
    titles = (
        f"1. Pips: {n_siz} in sizs (orange), {n_not} not (grey)",
        f"2. Elements grown from the sizs: {n_elements}",
        "3. Evacuated zones, every siz walled",
        "4. Evacuated zones, no siz walled",
    )
    for ax, title in zip(axes, titles, strict=True):
        ax.set_title(title, fontsize=9, loc="left")
    axes[0].legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=SIZ_COLOUR, label="pip in a siz"),
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                color=NOT_SIZ_COLOUR,
                label="pip, pif not a siz",
            ),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=2,
        fontsize=7,
    )
    fig.suptitle(f"Site {site['id']}: {site['name']}", fontsize=11)
    base.FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = base.FIG_DIR / f"pilot_instability_{site['id']}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def flag_large_polygons(result, transform, *, threshold_m2, label):
    """Print the evacuated polygons over the threshold, largest first."""
    cells = result.cells[result.cells["zone"] == EVACUATED]
    area = cells.groupby("polygon").size() * transform.a * -transform.e
    big = area[area > threshold_m2].sort_values(ascending=False)
    print(f"\n=== {label}: {len(big)} evacuated polygons over {threshold_m2:,.0f} m2")
    if big.empty:
        return
    where = (
        cells[cells["polygon"].isin(big.index)]
        .groupby("polygon")[["row", "col"]]
        .mean()
    )
    table = pd.DataFrame(
        {
            "area_m2": big.round(0),
            "x": transform.c + (where.loc[big.index, "col"] + 0.5) * transform.a,
            "y": transform.f + (where.loc[big.index, "row"] + 0.5) * transform.e,
        }
    )
    print(table.head(25).round(0).to_string())


def main(
    *, extent, sites, contour_intervals_m, max_contours, large_polygon_m2, siz_file
):
    dem, water, transform, ground_map, zones, zones_seconds, scenarios = get_zone_run(
        extent=extent
    )
    sizs = zones.sizs
    print(
        f"Pips, pifs, sizs and growth over the {extent} pilot in {zones_seconds:.1f} s; "
        f"scenario polygons in {scenarios['walled'][2]:.1f} s and {scenarios['bare'][2]:.1f} s"
    )
    print(
        f"{int(zones.pips.mask.sum()):,} pips, {len(sizs):,} pifs, "
        f"{int(sizs['is_siz'].sum()):,} sizs, "
        f"{len(zones.found.elements):,} elements"
    )
    print(sizs.groupby("ground_group")["is_siz"].agg(["size", "sum"]).to_string())
    siz_path = TEMP_DIR / f"{siz_file}{extent_suffix(extent)}.parquet"
    write_siz_table(gen_siz_table(zones, transform, crs=base.CRS), siz_path)
    print(f"Siz table: {siz_path}")
    walled_view = pilot_view(
        dem, water, transform, ground_map, zones, scenarios["walled"]
    )
    bare_view = pilot_view(dem, water, transform, ground_map, zones, scenarios["bare"])
    for label, view in (
        ("every siz walled", walled_view),
        ("no siz walled", bare_view),
    ):
        flag_large_polygons(
            view.result, transform, threshold_m2=large_polygon_m2, label=label
        )
    for site in sites:
        print(
            draw_site(
                site,
                walled_view,
                bare_view,
                zones,
                intervals=contour_intervals_m,
                max_contours=max_contours,
            )
        )


if __name__ == "__main__":
    main(
        extent=config.PILOT_EXTENT,
        sites=config.PILOT_SITES,
        contour_intervals_m=config.PILOT_CONTOUR_INTERVALS_M,
        max_contours=config.PILOT_MAX_CONTOURS,
        large_polygon_m2=config.LARGE_POLYGON_M2,
        siz_file=config.PILOT_SIZ_FILE,
    )
```

Before running, check that `config.PILOT_SITES` entries carry `id` and `name` keys (read `config.py` lines ~100-200); if the keys differ, use the ones they have. `extent_suffix` is imported but must be used as written (the file name); if `TEMP_DIR` is a `Path` the f-string is fine.

- [ ] **Step 4: Run and read the result.** Run `uv run --frozen python src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_instability_zones.py`.
  Expected: it prints the timings, the pip/pif/siz/element counts by ground group, the siz file path, the two large-polygon tables, and one PNG path per site. **Performance gate:** the first printed time (pips, pifs, sizs, growth) should be of the order of the old pipeline's `find_slope_elements` (14 s) plus the pair test; if it exceeds about 75 s, apply the subsampling in design note 4 and re-run. Record the printed times in the findings doc.

- [ ] **Step 5: Look at the figures** for sites 05, 07 and 08 (the lead's reference sites: 7 and 8 looked reasonable before, 5 is the hillside). View the PNGs. Do **not** tune thresholds. Report to the lead: which pilot sites produce evacuated polygons over `LARGE_POLYGON_M2` (from the printed tables, map each (x, y) to the nearest site), and whether the hillside at site 05 now splits into several polygons (the lead's target is 6-12).

- [ ] **Step 6: Docs** (all in the same change):
  - `src/landloss/io/assets/README.md`: in the threshold CSVs section, describe the two-band slope table (35/45/53 under 3.5 m; 32/40/48 from 3.5 m) as the siz far-pair test, and `adjacent_step_m` as the siz near-pair step (0.7 / 3.0 / 3.0), and say that `min_step_height_m` and `bank_min_slope_deg` belong to the old seeding.
  - `src/scripts/landloss/hazard/landslide/status.md` (use the `maintaining-status-files` skill; edit in place): under **Where it is now** replace the seeding bullets with pips/pifs/sizs, growth kept, A/B wall scenarios, the siz table as the RW input, with the measured counts and times from Step 4; under **Next** put the large-polygon review and the retirement of the bank code; under **Open decisions** the 30 m pair cap, the 1.41 diagonal scaling and the support points.
  - `src/scripts/landloss/hazard/landslide/research/slope_elements/pilot_example_slope_elements.md`: a short section "Pips, pifs and sizs" with the rules, the counts, the timings and the flagged sites.
  - `.agents/plans/building-face-based-urban-slope-polygons.md`: add under the title a line "Phase 1 (seeds, free-face and bank) is superseded by `building-pip-pif-siz-slope-polygons.md`; phases 2-5 stand."
  - Changelog: `doc/whatsnew/mm.feature.<yymmddhhmm>.md` with the time from `Get-Date -Format yyMMddHHmm`, one paragraph: "Urban slope model: pips, pifs and sizs replace the free-face and bank seeding; ground mapped as fill is soil; the siz table is saved for the retaining-wall workflow."

- [ ] **Step 7: Final verification.** Run `uv run --frozen pytest -q` (expect all green) and `uv run --frozen prek run --files <every touched non-research file>` (expect pass, re-running until no hook rewrites files). Do not commit.

---

## Deferred (not part of this plan)

- **Retire the old bank code** (`_bank_pass`, `BANK_SEED_SLOPE_DEG`, the bank half of `find_slope_elements`, `landslide-seed-thresholds.csv` columns `min_step_height_m` and `bank_min_slope_deg`) once `fig_toy_slope_elements.py` is refactored off `find_slope_elements`.
- **Which sizs carry a wall** (the RW workflow). `with_walls` already takes a per-element Series, so the RW result plugs in without changing the polygon builder.
- **A step folder** for the siz file (`steps/`, with plan and method files) once the lead settles where the file lives; until then it is written to `temp/`.
- **Along-contour strips** in `slope_polygons._segments`.

## Self-Review

- **Spec coverage:** pips (8 directions, 0.7 m at 1/3/5 m, no material or second DEM) Task 3; pifs at 2 m Task 3; siz test over all pairs with the near step (soil 0.7, rock 3.0) and far angle by pair delta_h and the new 35/45/53 and 32/40/48 table Tasks 1 and 4; fill is soil Task 2; max angles above/below 3.5, delta_h and the flag stored, and the file for the RW workflow Tasks 4 and 7; watershed growth kept Task 6; evacuated zone twice (all walled, none) Tasks 6 and 8; speed and the pair cap Design note 4 and the Task 8 gate; flag large polygons without tuning Task 8. Rock walls of 1-2 m are not sizs: `test_a_rock_wall_of_2_m...`.
- **Placeholder scan:** none; the one mechanical move (Task 5) lists its three edits explicitly and is gated by the existing suite.
- **Type consistency:** `assess_pifs(dem, pips, pif_labels, ground_group, transform)` is the same in Tasks 4, 6 and the tests; `find_instability_zones` returns `InstabilityZones(found, pips, pif_labels, sizs)` used in Tasks 6-8; `with_walls(found, walled)` in Tasks 6 and 8; `_assemble_elements` signature in Tasks 5 and 6 matches (11 positional arguments, in the same order).
- **Risks to watch:** `_grow_by_limit` seeds are pip cells (the upper edge), not 1 m footprints, so growth starts from the crest line; if an element is under-grown on the toy ramps, look at the seeds first. The `_`-prefixed imports from `slope_elements` are intentional; if ruff flags them, make the few needed names public in `slope_elements` rather than suppressing.
