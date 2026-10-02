# Code structure

The analysis is split into four modules that run in sequence: **hazard** defines
what the ground does, **exposure** defines what is on it, **vul** works out how
badly each asset is damaged, and **loss** turns that damage into money. Each
depends only on the ones before it, so a change to the policy settings re-runs
`loss` alone, while a change to the seismic demand re-runs everything.

## The four modules

| Module | Responsibility |
| --- | --- |
| `hazard` | Defines the shaking, liquefaction and landslide extents. |
| `exposure` | Defines the assets in terms of location, extent and attributes. |
| `vul` | Vulnerability calculations for each asset against each hazard. |
| `loss` | Combines damage ratios with replacement ratios and policy settings to give financial loss. |

`hazard` is the demand side and knows nothing about properties. `exposure` is
where a property's insured land extent and its attributes — slope, retaining
walls, services, land value — are assembled. `vul` is the only place the two meet,
producing a damage ratio per asset per hazard. `loss` is the only place money and
policy wording enter, which is what keeps the policy settings a parameter of the
study rather than something baked through the model.

## Submodules: the two axes

Three of the four modules are split again, because neither the hazards nor the
insured assets behave alike and mixing them in one namespace hides that.

| Module | Split by | Submodules |
| --- | --- | --- |
| `exposure` | Insured asset type | `land`, `rw` (retaining walls), `culverts_bridges` |
| `hazard` | Hazard | `liquefaction`, `landslide`, `shaking` |
| `vul` | Hazard, then asset type | `<hazard>/<asset>`, e.g. `liquefaction/land` |
| `loss` | Not split | — |

The asset axis is the one the policy cares about: land is settled on its value,
a retaining wall on replacement value up to the sub-cap, and a culvert as a
private service. The hazard axis is the one the physics cares about. `vul` is
split on both because a damage ratio only means anything for one pair of them —
liquefaction settlement under insured land and shaking of a retaining wall are
unrelated relationships, and an aggregate of the two is not a number anybody can
use.

`loss` is left flat. It reads damage ratios that already carry their hazard and
asset, and adds only money and policy wording.

**A submodule is created when there is something to put in it**, not up front.
At the time of writing the populated ones are `exposure/land`,
`hazard/liquefaction`, `hazard/landslide`, `vul/liquefaction/land`,
`vul/landslide/rw` and `vul/landslide/culverts_bridges`; the rest appear as the
work reaches them.

### Each submodule carries a `status.md`

Every submodule of `exposure`, `hazard` and `vul` holds a `status.md` beside its
scripts, at its own level — `exposure/<asset>/`, `hazard/<hazard>/`,
`vul/<hazard>/<asset>/`. It summarises the current approach for that piece of
work and what will be done next. `hazard/shaking/status.md` is the worked
example the others follow. `loss` is flat, so it would take a single
`loss/status.md`.

Sections run `## Approach`, `## Where it is now`, `## Next`, then
`## Validation` and `## Open decisions`. The approach comes first because the
state on its own means nothing without it. Keep it brief — a bullet states the
decision and at most the one clause explaining why; the argument for a choice
belongs in the step's method or plan file, not here.

This is a different document from the plan and method files that every step
folder carries. Those are per-step and narrow — the method file states only what
is implemented, and the implementation plan holds everything aspirational. A
`status.md` sits one level up, at the hazard, and is allowed to hold both: it is
the orientation page for someone asking "where has the shaking work got to, and
what is next?". It points at the step files for detail rather than restating
them.

Because it carries intent alongside state, a `status.md` has to be explicit
about what does not exist. Where nothing is implemented, it says so and labels
the approach as intended, rather than describing a method as though the code were
already there.

### Where cross-cutting work sits

`steps/`, `validations/`, `report/` and `research/` are submodules of whichever
level the work belongs to, not of the module. Work specific to one asset or one
hazard goes in that submodule. Work shared across all of them stays at the
module level, because filing it under one asset or one hazard would be a lie
about what reads it:

- `exposure/steps/s1_address_spine/` — the property spine. Land, retaining walls
  culverts and bridges all hang off the same addresses.
- `hazard/research/fig_cross_sections.py` — valley cross-sections, read by the
  liquefaction and the landslide work alike.
- `vul/static_data_gen/`, `vul/assets/` and `vul/research/` — the NHC claims
  datasets, which are not split by cause of damage.

## Where the code lives

Each module appears twice, and the split is deliberate:

```text
src/landloss/{hazard,exposure,vul,loss}/
src/scripts/landloss/{hazard,exposure,vul,loss}/
```

- `src/landloss/<module>/` is the **library**: reusable, tested logic with no
  assumptions about a particular run. This is the code handed to NHC.
- `src/scripts/landloss/<module>/` is the **run**: the orchestration that points
  the library at this study's datasets and settings.

The two trees mirror each other down to the submodule, so
`landloss.exposure.land.land_value` is exercised by
`src/scripts/landloss/exposure/land/steps/s2_land_value/`, and `tests/` mirrors
the library the same way.

Within the scripts tree, at the module level or at any submodule below it:

- `steps/` builds the model or models for that level. A step is a stage of the
  build, ordered and re-runnable, and lives in its own numbered folder with an
  implementation plan and a method file — see the `adding-steps-scripts` skill.
  Step numbers run across the module, so a step is not renumbered when it moves
  into a submodule: `s1_address_spine` sits under `exposure/steps/` and
  `s2_land_value` under `exposure/land/steps/`.
- `validations/` checks the intermediate and final outputs of that level.
- `report/` produces the figures and tables the report uses.
- `research/` holds exploratory analysis that is not part of the reported
  pipeline.

Validations exist as their own layer because most of what can go wrong in this
work is a silently wrong input rather than a crash — a DEM merged across survey
years, a property with no insured land area, a damage ratio above one. A
validation is a check on an output, not a unit test of a function; unit tests
belong in `tests/`.

Every folder carries an `__init__.py`, and its docstring says what belongs in
that folder — with the submodules that is the cheapest way for a directory
listing to explain itself.

## Paths out of the repo

Scripts sit at several different depths now, so nothing counts `parents[N]` for
itself. `src/scripts/landloss/paths.py` resolves the repo root once and exposes
`REPO_ROOT`, `REPORT_DIR`, `RESEARCH_DIR` and `TEMP_DIR`; every script imports
from there. The same applies inside the library: the packaged data files are
reached through `landloss.io.ASSETS_DIR` rather than by walking back up from
whichever module wants them.

A miscounted `parents[N]` does not raise — it writes an output somewhere nobody
looks for it — which is exactly why the count is made once, in one place, rather
than in each file that moves.

## Shared support code

Three packages sit outside the four modules because all of them need them:

- `src/landloss/domain/` — constants shared across the model: the default CRS
  (NZTM, `EPSG:2193`), the Koordinates domains and their API key variables, and
  layer IDs. `loss_contract.py` holds the column names of the tables `vul` hands
  to `loss`, which every producer imports rather than retyping.
- `src/landloss/io/` — readers for the datasets the models are built from, and
  `area_of_interest.py`, which holds the named study extents.
- `src/landloss/common/utils/` — helpers belonging to no one module. `plot.py`
  holds the map panel styling, ported from the National Liquefaction Model so a
  figure from this study reads the same as one from that one.

### Figures

A report output directory mirrors the module path of the script that writes it,
then names the topic, so the figure and the code that made it are findable from
each other:

| Script | Writes to |
| --- | --- |
| `hazard/liquefaction/report/fig_waterway_map.py` | `report/hazard/liquefaction/fig/` |
| `hazard/landslide/validations/fig_landslide_vulnerability_model_gwrc.py` | `report/hazard/landslide/fig/` |
| `exposure/land/steps/s2_land_value/fig_land_value_map.py` | `report/exposure/land/land-value/fig/` |
| `vul/liquefaction/land/report/fig_land_damage_maps.py` | `report/vul/liquefaction/land/fig/` |
| `hazard/research/fig_cross_sections.py` | `research/hazard/cross_sections/fig/` |
| `hazard/landslide/research/fig_wcc_earthworks_completeness.py` | `research/hazard/landslide/wcc_earthworks_completeness/fig/` |

Report figures go under `report/`, exploratory ones under `research/`, and CSV
tables under a `tab/` directory beside the `fig/`. Both roots are reached through
`REPORT_DIR` and `RESEARCH_DIR` in `src/scripts/landloss/paths.py`.

Any directory named `fig` is gitignored, so figures are regenerated rather than
committed, and the script that produces one is the record of how it was made. A
`tab/` directory is not ignored, because a CSV table is small, readable in a diff
and often the thing handed to someone who does not run Python.

### Weekly updates

`release_updates/` holds `weekly_update_template.typ` and one
`update_week_of_<monday>.typ` per week, generated from the `status.md` files and
then edited by hand. The `.typ` is the deliverable and is tracked;
`release_updates/*.pdf` is gitignored, because a compiled PDF is regenerated from
the source the same way a figure is.

### Areas of interest

An extent is defined once, in WGS84, and converted to whatever CRS a caller needs
via `.bbox(crs)`. Defining them in one place stops an extent being re-typed from a
map into each script. `SMALL_WLG_PILOT` is a roughly 2.9 by 1.7 km box in central
Wellington, about 4.7 km², for exercising the workflow end to end before it is run
over the full study area.

### Koordinates access and caching

Layers come from two Koordinates domains, each with its own API key read from
`.env`: `ttgroup.koordinates.com` via `TNT_KOORDINATES_API_KEY` for T+T's own
layers, and `data.linz.govt.nz` via `LINZ_API_KEY` for LINZ layers. The key is
chosen from the domain rather than a single shared variable.

Caching happens at two levels, which matters because layers such as NZ Addresses
are national:

1. ttpy caches the whole downloaded layer under `KOOPCACHE_DIR`, keyed by layer
   ID, version and a hash of the layer details. A layer is downloaded once.
2. `landloss.io.readers` caches the clipped extent under `KOOPCACHE_DIR/extents`,
   keyed by the source file name — which encodes the layer version — plus the CRS
   and bounding box. Asking for the same extent again skips reading and clipping
   the source.

The extent cache applies only when a bounding box is given, because without a clip
it would store a second full copy of a layer ttpy has already cached.

**On measurement, the extent cache is not currently earning its keep.** Reading
the Wellington pilot extent (8,591 addresses) out of the 809 MB NZ Addresses
layer, alternating five times each way, gave a median of 1.68 s cached against
1.79 s uncached, with the ranges overlapping. GeoPackage carries a spatial index,
so pushing the bounding box down into the read is already fast whatever the size
of the source, and reading a small cached copy back costs about the same.

The expensive step is the download, and ttpy already caches that. Keep this in
mind before relying on the extent cache for performance; it may be worth removing
in favour of the pushdown alone.

Because the extent cache key includes the layer version, a new version of a layer
upstream produces a new key rather than a stale hit. Pass `use_cache=False` to
force a re-read.

## Versioned data storage (tdrive_sync)

`src/tdrive_sync/` (imported as `ts`) is a small, generic package for saving and
reading this project's own intermediate and output data on the shared `T:` drive,
under a project-wide `DATA_VERSION`. It knows nothing about landloss — it is
configured by a committed `tdrive_sync_config.py` at the repo root (`BASE_DIR`,
`DATA_VERSION`, `SOURCE_MATERIAL_DIR`) and a set of `TTDRIVE_SYNC_*` environment
variables that let a developer work entirely against a local, disposable cache
instead of `T:`. See `README.md`'s "Environment variables" section for the full
local-mode fallback chain, and the package's own docstrings for the mechanics
(format dispatch, atomic copying, path resolution).

`ts.get_source_mat("relative/path.csv")` is the read-only counterpart for data
someone else supplied (NHC, another team) rather than data this project
generates: it fetches from `SOURCE_MATERIAL_DIR` on `T:` and caches locally,
with no `DATA_VERSION`, no save side, and no local-only working mode fallback.

`src/landloss/io/versioned_store.py` is the thin, landloss-specific layer on top:
`save_hazard`/`read_hazard`, `save_exposure`/`read_exposure`, `save_vul`/
`read_vul` and `save_loss`/`read_loss` each just prepend the module's name to
`sub_dirs` before delegating to `ts.local_save`/`ts.local_read`, so the four
modules share one `DATA_VERSION` without their files colliding.

This is separate from the NLM's own *upstream* release directory
(`CORE_NLM_VERSION` in `landloss/domain/constants.py`), which this repo only
reads from — `versioned_store` is for data this project derives and writes out
itself.

`src/landloss/io/nlm.py` reads that upstream release tree
(`T:\Auckland\Projects\1017473\WorkingMaterial\new_versioned_releases`, one
level above this project's own folder, shared across every subproject) through
`ts.get_cached`, a generic tdrive_sync helper for caching an arbitrary absolute
T: path locally with no `DATA_VERSION`/`SOURCE_MATERIAL_DIR` concept attached —
the same read-only, no-save, no-local-mode contract as `get_source_mat`.

`CORE_NLM_VERSION` is the single pin for the `core` sub-tree: the scenario grids
`landloss.io.nlm` reads, the mapped observations the vul steps read, and
anything else reaching into `new_versioned_releases/core` all resolve through
it, so two readers of that sub-tree cannot quietly end up on different
releases. The releases themselves are the `NlmRelease` enum beside it, which
exists because the folder names are inconsistently punctuated (`v2025p0_rc4`
against `v2026p0rc4`) and so are easy to mistype into a path. A reader that
genuinely has to stay on an older release names the enum member at the point of
use rather than adding a second project-wide constant.

The `flatland` sub-tree is cut and versioned on its own schedule, unrelated to
`core`'s, so it is pinned separately as `FLATLAND_NLM_VERSION` (e.g. `V0p5`)
rather than reusing `CORE_NLM_VERSION`. `landloss.io.nlm.get_nlm_flatland`
reads it, and is distinct from `landloss.exposure.land.landform.get_flatland`,
which reads an earlier flatland cut mirrored to Koordinates.

## Causes of financial land loss

These are the distinct causes the model has to represent. They are not
interchangeable: each has its own hazard input, its own vulnerability
relationship, and its own treatment under the policy, so `vul` carries a damage
ratio per cause rather than one aggregate figure per asset.

- **Land settlement and cracking** — liquefaction-induced settlement and
  differential movement of the land itself.
- **Ejecta** — material ejected to the surface, and the cost of clearing it.
- **Landslide loss of support** — land removed from beneath or beside the
  property by a failure originating on it.
- **Landslide runout** — material arriving from a failure originating elsewhere,
  including from council land above.
- **Underground services damaged** — damage to the private services within the
  property.
- **Retaining walls fail** — failure of the walls themselves, settled on
  replacement value up to the cap rather than on the value of the land.

The distinction between loss of support and runout matters for the policy
question, because it decides whose insured land the damage falls on. See
`nhc-land-cover-and-settlement.md` for how each is settled and
`land-damage-mechanisms.md` for the physical processes behind them.
