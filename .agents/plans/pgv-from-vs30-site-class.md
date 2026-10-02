# PGV across the study area from Foster Vs30 and TS1170.5 Sa(1.0 s)

**Status:** Implemented as two steps rather than the one described below. The
site class was split out into `src/scripts/landloss/hazard/shaking/steps/s2_site_class/`
so that PGA can share the grid, and PGV is
`src/scripts/landloss/hazard/shaking/steps/s3_pgv/`, written in m/s rather than
cm/s. Progress is tracked in each step's implementation plan.

## Context

The shaking module has a PGA step (`steps/s1_pga_realisation`) but no PGV, and
several of the retaining wall fragility curves are velocity-based. The shaking
`status.md` already fixes the approach:

- Take the site class from the Foster et al. (2019) Vs30 model.
- Generate Sa(T1) on a 100 m grid at the 2500-year return period.
- Derive PGV from the same spectrum as **PGV (mm/s) ≈ 750 · Sa(1.0 s) [g]**,
  which is ×75 in cm/s.

That relation is already coded as
`landloss.hazard.shaking.pgv.pgv_cm_s_from_sa_1s` (`PGV_MM_S_PER_G_SA_1S = 750`),
so no new correlation is introduced here.

The Sa(1.0 s) grids per site class and return period already exist:

- `landloss.io.ts1170.get_ts1170_sa_t1(return_period_yr, site_class)` reads
  them, on the NLM's ~9.9 km NZTM grid.
- `static_data_gen/gen_ts1170_sa_t1.py` generates them from TS1170.5:2025 Table
  3.2.

Still missing are the Vs30 readers, the Vs30 → site class mapping, and a step
that combines them on a 100 m grid.

### The Vs30 data

Foster Vs30 v18.12 is held on the T+T data library at
`R:\DataLibrary\210.16_Vs30_NZ_Foster2019\v1_ref_Foster_v18.12`. A local copy
was used to check the layout.

- **Layers.** `VERSION18.12_AhdiYongWeightedMVN_nTcrp1.5_Vs30.tif` and
  `VERSION18.12_AhdiYongWeightedMVN_nTcrp1.5_sigma.tif`.
- **Grid.** EPSG:2193, with 100 m cells on 100 m-aligned bounds:
  1,000,000–2,126,400 E and 4,700,000–6,338,400 N.
- **Size.** 16384 × 11264 float32, nodata −3.4e38, about 740 MB each, so reads
  must be windowed to the extent.
- **Values.** Vs30 is in m/s (202–618 m/s over central Wellington). Sigma is a
  log standard deviation (0.11–0.71 there).
- **Provenance.** Per the folder README, the folder was supplied by Kevin
  Foster. The exception is `MODEL_AhdiAK_geologyclassifications.csv`, which came
  from the `fostergeotech/Vs30_NZ` GitHub repository.

Because the Foster grid is already 100 m NZTM and 100 m-aligned, the Vs30
raster clipped to the extent *is* the 100 m grid. No separate template is
built.

## Approach

### 1. Local cache

Copy the two `.tif` files (plus their `.tif.aux.xml`) into
`.tdrivecache/DataLibrary/210.16_Vs30_NZ_Foster2019/v1_ref_Foster_v18.12/`.
That is the mirror `tdrive_sync.get_cached_local_path` gives for the R: path,
so the readers find them without going to R:.

### 2. Readers: `src/landloss/io/vs30.py`

- `FOSTER_2019_DIR` is the R: folder above, with file-name constants for the
  Vs30 and sigma layers.
- `foster_2019_path(fname, *, copy_to_local=True)` resolves a file through
  `tdrive_sync.get_cached`.
- `get_foster_2019_vs30(bbox=None, *, copy_to_local=True)` and
  `get_foster_2019_vs30_sigma(bbox=None, *, copy_to_local=True)`:
  - open with `rioxarray.open_rasterio(masked=True)`;
  - call `rio.clip_box(*bbox)` before `.load()` so only the window is read;
  - load inside a context manager, as `landloss.io.nlm.get_nlm_scenario_raster`
    does.
- The module docstring carries the citation (Foster, Bradley, McGann &
  Wotherspoon 2019, *Earthquake Spectra*), the version, the grid facts above,
  and what sigma is.
- Tests go in `tests/landloss/io/test_vs30.py`:
  - use a tmp GeoTIFF with `foster_2019_path` monkeypatched;
  - check bbox clipping and that nodata becomes NaN;
  - apply the `ignore:Use \`@\` matmul` warning filter that the other raster
    reader tests use.

### 3. Site class: `src/landloss/hazard/shaking/site_class.py`

`ts1170_site_class_from_vs30(vs30)` applies TS1170.5:2025 Table 3.3 on Vs30
alone. Bins are `a < Vs30 ≤ b`, and the edges are a module constant.

| Vs30 (m/s) | Site class |
|---|---|
| > 750 | I (1) |
| 450–750 | II (2) |
| 300–450 | III (3) |
| 250–300 | IV (4) |
| 200–250 | V (5) |
| 150–200 | VI (6) |
| ≤ 150 | VII, returned as VI (6) |

VII is returned as VI because clause 3.1.3.2 floors VII at the VI spectrum, and
Table 3.2 carries no VII. NaN stays NaN.

**Limitation, stated in the docstring.** The classification uses Vs30 alone.
Table 3.3 also depends on profile characteristics that Vs30 does not carry:

- Class I needs no more than 3 m of soil or weathered rock over bedrock,
  otherwise the site is Class II.
- II/III and V/VI depend on underlying low-velocity layers and soft-soil
  thicknesses.

So weathered-rock sites with Vs30 > 750 m/s are classed I. Class VII sites get
the VI spectrum without the site-specific analysis the TS requires.

`select_by_site_class(site_class, grids_by_class)` picks, per cell, the grid
matching that cell's class from a `{class: DataArray}` mapping on one grid. It
gives NaN where the class is NaN.

Tests go in `tests/landloss/hazard/shaking/test_site_class.py`:

- bin edges: 750 → 2, 750.1 → 1, 450 → 3, 150 → 6, 100 → 6;
- NaN handling, and both array and DataArray input;
- that the selection picks the right grid per cell.

### 4. Step: `src/scripts/landloss/hazard/shaking/steps/s2_pgv/`

Laid out per `.agents/skills/adding-steps-scripts/SKILL.md`:

- `__init__.py`.
- `config.py`: `PILOT = True`, `RETURN_PERIOD_YR = 2500`.
- `gen_pgv.py`, with `main(*, pilot, return_period_yr)`:
  1. Take the extent bbox from `resolve_extent(pilot)` in
     `s1_pga_realisation/gen_pga_realisations.py`, imported rather than copied.
  2. Read `get_foster_2019_vs30(bbox)`, which is the 100 m grid.
  3. Classify with `ts1170_site_class_from_vs30`.
  4. Read the six `get_ts1170_sa_t1(return_period_yr, c)` grids and match each
     to the Vs30 grid with `rio.reproject_match(vs30, resampling=nearest)`.
     They are ~9.9 km cells, so this is a lookup, not an interpolation.
  5. Get Sa(1.0 s) from `select_by_site_class`, then PGV from
     `pgv_cm_s_from_sa_1s`.
  6. Write the outputs with `landloss.common.utils.terrain.write_raster` under
     `TEMP_DIR / "hazard" / "shaking"`, as s1 does:
     - `site-class-100m{-pilot}.tif`
     - `sa-t1-{rp}yr-100m{-pilot}.tif`
     - `pgv-{rp}yr-100m{-pilot}.tif`

     The names come from one `output_path(kind, return_period_yr, pilot)` that
     downstream steps import.

  The `__main__` block passes the `config` values as keyword arguments and does
  not end with `raise SystemExit`.
- `fig_pgv.py`: maps of site class and PGV, written to
  `report/hazard/shaking/pgv/fig/`.
- `s2_pgv_implementation_plan.md`, in phases with `[ ]` boxes and ending with
  `## Potential future improvements`. The phases:
  1. Vs30 readers.
  2. Site class and selection.
  3. `gen_pgv.py` on the pilot, with the figure.
  4. Full study area and the method document.
- `s2_pgv_method.md` describes the implemented method only. It points at the
  functions and files above, states the Vs30-only limitation, and ends with
  ``Potential future improvements: see `s2_pgv_implementation_plan.md`.``

### 5. Project register

Append one entry to the `Limitations` list in `.agents/context/register.json`.
Leave the ID out so the script allocates the next one, and set the status to
`Accepted`. The wording:

> Site class is assigned from Foster et al. (2019) Vs30 alone, without the
> profile criteria of TS1170.5 Table 3.3, so rock with weathered cover
> (Vs30 > 750 m/s) is taken as Site Class I and Class VII sites get the Class VI
> spectrum.

Set Affects to the shaking PGV and Sa(1.0 s), and Source to the 2026-09-30
decision. Then run:

```powershell
uv run --with openpyxl python .agents/skills/recording-project-context/scripts/build_register.py append .agents/context/register.json
```

The workbook must be closed in Excel for the append to save.

### 6. Housekeeping

- Add a changelog fragment, `doc/whatsnew/mm.feature.<yymmddhhmm>.md`.
- Leave the shaking `status.md` alone, because status files carry only what the
  project lead supplies; offer wording instead.
- Do not touch `src/landloss/loss/`, `BETA_SITE_CLASS` or the s1 step.

## Verification

- Run `uv run --frozen pytest`, then `uv run --frozen prek -a` until it is
  clean, then `uv run --frozen ruff check --select FIX`.
- Run `gen_pgv.main(pilot=True, return_period_yr=2500)` and check:
  - the outputs are 100 m and aligned to the Vs30 grid;
  - at a sampled cell, PGV equals 75 × the class-matched `get_ts1170_sa_t1`
    value;
  - the site-class histogram is plausible for Wellington (Vs30 of 202–618 m/s
    should give mostly II–V).
- Render `fig_pgv.py` and look at the maps.

## Potential future improvements

- PGA on the same 100 m site-class grid, replacing s1's fixed site class 5 and
  `BETA_SITE_CLASS`.
- Use the Vs30 sigma layer for multiple site classes (clause 3.1.3.4), either as
  an envelope or as a draw per realisation.
- Use Table 3.1 values inside settlement boundaries, instead of the 0.1° grid.
- Cite the source of the 750 mm/s per g relation in `pgv.py`.
