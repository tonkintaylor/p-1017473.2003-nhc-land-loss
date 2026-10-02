# Plan: porting `local_read`/`local_save` as `tdrive_sync`, plus landloss versioned-data helpers

## Context

The reference implementation is
`p-1017473-national-liquefaction-model/src/common/io/public/local.py`. It
provides `local_save`/`local_read` against a T-drive "core" release directory,
backed by a local on-disk cache, an `IS_LOCAL_SAVE_MODE` flag that keeps
everything local, and a single global `OUTPUTS_VERSION` env var baked into
every path via an `override_version` string-substitution escape hatch.

This repo currently has no equivalent — T-drive paths are hardcoded
`Path(...)` literals scattered across scripts (e.g. `gen_ces_loss_data.py`,
`gen_observed_damage_db.py`, `fig_land_damage_v_lsn.py`). There is a related
but separate convention: the NLM's own *upstream* release directory
(`WorkingMaterial\new_versioned_releases\core\<NLM_VERSION>`), which this repo
only *reads from* (`NLM_VERSION`/`NLM_OBS_VERSION` in
`landloss/domain/constants.py`). That is a different concern from what we're
building here: this repo needs to *write and read its own* versioned
intermediate/output data, under
`T:\Auckland\Projects\1017473\1017473.2003\WorkingMaterial\versioned_data\`.

**This revision replaces an earlier draft** that passed `base_dir`/`version` as
keyword arguments on every call and used a per-call `version="scratch"`
sentinel. The user decided against per-call version arguments; the design
below reads `BASE_DIR`/`DATA_VERSION` from a config file instead. The
`"scratch"` idea survives, but relocated: it is now the literal value
`DATA_VERSION = "SCRATCH"` in `tdrive_sync_config.py` (a project-wide setting,
not a per-call argument), and a separate, orthogonal `TTDRIVE_SYNC_LOCAL_MODE`
env toggle handles the local-only working mode.

## Decisions (confirmed with user, across two rounds of clarification)

| Decision | Choice |
|---|---|
| Version/base_dir as function args | **No.** Removed entirely. Every `tdrive_sync` function resolves them itself. |
| Where `BASE_DIR`/`DATA_VERSION` live | A Python file, `tdrive_sync_config.py`, at the **project root** (alongside `pyproject.toml`). **Committed to git** — it is shared, team-wide config, the same status `NLM_VERSION` already has in `constants.py`. |
| Missing config file | Raise a clear, actionable error immediately — do not silently fall back to anything. |
| Local-only working mode | Two new `.env` vars: `TTDRIVE_SYNC_LOCAL_MODE` (bool) and `TTDRIVE_SYNC_LOCAL_VERSION` (str). |
| Save behaviour, local mode ON | Save **only** to the local cache, under `TTDRIVE_SYNC_LOCAL_VERSION`. Never touches T:. Always overwrites — no exists-check, no error (this is a personal, disposable working area). |
| Save behaviour, local mode OFF | Save straight to T: (and refresh the local cache mirror), under `DATA_VERSION`. **Raises an error if the file already exists** — the NLM original's safety net, restored — *unless* `DATA_VERSION == "SCRATCH"` (a literal, project-wide config value), in which case it overwrites without error. |
| Read behaviour, local mode ON | Check the local cache under `TTDRIVE_SYNC_LOCAL_VERSION` first: if present, return it — no network involved. Otherwise check the local cache under `DATA_VERSION`: if present, return it (no staleness check against T: — local mode means "don't touch the network unless there is truly nothing"). Otherwise fetch from T: at `DATA_VERSION`, populate the `DATA_VERSION` local cache, and return it. |
| Read behaviour, local mode OFF | Same as the ported NLM logic: resolve the local cache under `DATA_VERSION`, refresh it from T: if missing or stale (size/mtime/mode mismatch), return the resolved path. |
| Genericity | `tdrive_sync` itself has zero landloss/hazard/exposure/vul/loss knowledge. It only knows about `tdrive_sync_config.py` (which any consuming project supplies) and the two `.env` vars. `landloss` wraps it. |

## Architecture

```text
tdrive_sync_config.py        # NEW, project root, committed to git — supplied
                              # by *this* consuming project, not part of the
                              # tdrive_sync package
    BASE_DIR: Path             # T:\Auckland\Projects\1017473\1017473.2003\WorkingMaterial\versioned_data
    DATA_VERSION: str           # the current shared version, e.g. "v1" (placeholder — confirm actual value while implementing)

src/tdrive_sync/             # generic, reusable, no landloss knowledge
    __init__.py                # public API: local_save, local_read, get_path,
                                # get_local_path, get_base_path
    _config.py                  # TdriveSyncConfig: finds & loads tdrive_sync_config.py
                                 # by walking up from cwd; reads TTDRIVE_SYNC_* env vars
    _formats.py                  # suffix -> save/read dispatch (gpkg/parquet/tif/csv/json/pickle/shp) — direct port
    _copy.py                     # atomic parallel-safe copy (_copy_one/_copy_to) — direct port
    _paths.py                     # path construction for the three tiers (T:, DATA_VERSION
                                   # cache, TTDRIVE_SYNC_LOCAL_VERSION cache) and the
                                   # local-mode read fallback chain

src/landloss/io/
    versioned_store.py         # save_hazard/read_hazard, save_exposure/read_exposure,
                                # save_vul/read_vul, save_loss/read_loss — thin wrappers
                                # that just prepend the module name as a sub_dir
```

### Why a root-level config file, not an env var or a landloss constant

- `tdrive_sync` must stay generic (usable from any project), so it cannot
  hardcode a landloss-specific path or import from `landloss`.
- `.env` (gitignored, per-developer, per-machine) is the wrong place for
  `BASE_DIR`/`DATA_VERSION` — those are project-wide, shared decisions the
  whole team must agree on and see in git history (exactly like
  `NLM_VERSION` today), not something each developer sets privately.
- A plain Python module at the project root is the seam: any project that
  wants to use `tdrive_sync` drops a `tdrive_sync_config.py` next to its
  `pyproject.toml`, and the package finds it by walking up from the current
  working directory — the same discovery pattern tools like `ruff`/`git`/
  `pre-commit` use to find their config, so it works regardless of which
  subdirectory a script is run from, as long as it's run from inside the
  repo (already the existing convention — see `README.md`/`CLAUDE.md`).

### `tdrive_sync` public API

```python
def local_save(
    obj: GeoDataFrame | DataFrame | DataArray | dict | Any,
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    **kwargs: Any,
) -> None: ...
def local_read(
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> GeoDataFrame | DataFrame | DataArray | dict | Any | Path: ...
def get_base_path(*, fname: str, sub_dirs: list[str] | None = None) -> Path: ...
def get_local_path(*, fname: str, sub_dirs: list[str] | None = None) -> Path: ...
def get_path(
    *, fname: str, sub_dirs: list[str] | None = None, copy_to_local: bool = True
) -> Path: ...
```

No `version`, `base_dir`, `override_version`, or `exists_ok` parameters
anywhere — a deliberate simplification versus the NLM reference, made possible
because there is now exactly one config source of truth per mode instead of a
per-call override mechanism.

### `_config.py`

```python
SCRATCH_VERSION = "SCRATCH"
"""DATA_VERSION sentinel: saves to T: overwrite instead of raising when a
file already exists at this version. Distinct from TTDRIVE_SYNC_LOCAL_VERSION,
which is a separate, purely-local working area."""


@dataclass(frozen=True)
class TdriveSyncConfig:
    base_dir: Path
    data_version: str


def find_config_file(start_dir: Path) -> Path:
    """Walk upward from start_dir looking for tdrive_sync_config.py."""
    ...  # raises TdriveSyncConfigError if not found by filesystem root


@functools.lru_cache
def load_config() -> TdriveSyncConfig:
    """Load and validate tdrive_sync_config.py, starting the search from cwd."""
    ...  # raises TdriveSyncConfigError if BASE_DIR/DATA_VERSION missing or wrong type


@dataclass(frozen=True)
class LocalModeSettings:
    enabled: bool
    local_version: str | None
    cache_dir: Path


def load_local_mode_settings() -> LocalModeSettings:
    """Read TTDRIVE_SYNC_LOCAL_MODE / TTDRIVE_SYNC_LOCAL_VERSION / TTDRIVE_SYNC_CACHE_DIR."""
    ...  # raises if LOCAL_MODE=True but LOCAL_VERSION is unset
```

`load_config` is loaded via `importlib.util.spec_from_file_location` (loading
the file directly by path, not via `sys.path`/`import`), so it works
regardless of whether the project root happens to be on `sys.path`.
`lru_cache` means the file is only read once per process; tests clear it with
`load_config.cache_clear()`.

### `_paths.py` — the three path tiers

```python
def base_path(config, *, fname, sub_dirs) -> Path:
    """T: path: config.base_dir / config.data_version / *sub_dirs / fname."""


def data_version_cache_path(config, settings, *, fname, sub_dirs) -> Path:
    """Local mirror of base_path, under settings.cache_dir, keyed by DATA_VERSION."""


def local_version_cache_path(config, settings, *, fname, sub_dirs) -> Path:
    """Purely local path, under settings.cache_dir, keyed by TTDRIVE_SYNC_LOCAL_VERSION."""
```

All three share the same relative layout — the network drive/UNC anchor is
stripped from `base_dir` (`Path(*base_dir.parts[1:])`) so the cache mirrors
the T: structure underneath `cache_dir`, with the version folder swapped for
whichever tier is being resolved.

### `local_save`/`local_read` control flow

```python
def local_save(obj, *, fname, sub_dirs=None, **kwargs):
    config = _config.load_config()
    settings = _config.load_local_mode_settings()
    sub_dirs = sub_dirs or []

    if settings.enabled:
        path = _paths.local_version_cache_path(
            config, settings, fname=fname, sub_dirs=sub_dirs
        )
        _formats.save(obj, path, **kwargs)  # always overwrites; local-only working area
        return

    local_path = _paths.data_version_cache_path(
        config, settings, fname=fname, sub_dirs=sub_dirs
    )
    base = _paths.base_path(config, fname=fname, sub_dirs=sub_dirs)

    if config.data_version != SCRATCH_VERSION and (
        local_path.exists() or base.exists()
    ):
        msg = (
            f"{base} already exists. Bump DATA_VERSION in tdrive_sync_config.py, "
            'or set it to "SCRATCH" to overwrite freely.'
        )
        raise FileExistsError(msg)

    _formats.save(obj, local_path, **kwargs)
    _copy.copy_to(src_path=local_path, dst_path=base)


def local_read(
    *, fname, sub_dirs=None, copy_to_local=True, return_path=False, **kwargs
):
    config = _config.load_config()
    settings = _config.load_local_mode_settings()
    sub_dirs = sub_dirs or []

    if settings.enabled:
        local_version_path = _paths.local_version_cache_path(
            config, settings, fname=fname, sub_dirs=sub_dirs
        )
        if local_version_path.exists():
            path = local_version_path
        else:
            data_path = _paths.data_version_cache_path(
                config, settings, fname=fname, sub_dirs=sub_dirs
            )
            if data_path.exists():
                path = data_path
            else:
                base = _paths.base_path(config, fname=fname, sub_dirs=sub_dirs)
                if not base.exists():
                    raise ValueError(f"Cannot find file: {base}")
                if copy_to_local:
                    _copy.copy_to(src_path=base, dst_path=data_path)
                    path = data_path
                else:
                    path = base
    else:
        path = get_path(
            fname=fname, sub_dirs=sub_dirs, copy_to_local=copy_to_local
        )  # ported NLM staleness-checked resolution

    return path if return_path else _formats.read(path, **kwargs)
```

Everything else — format dispatch table, the tempfile+atomic-replace copy for
parallel steps (`_copy.py`, kept as-is per user's earlier decision), and
`get_path`'s copy-down-if-missing-or-stale resolution for non-local-mode reads
— is a direct port of the NLM logic, just with `version`/`core_dir` replaced
by the config-resolved values.

**Dropped versus the NLM reference, deliberately, per user decision:**
`override_version`/string-substitution (there is one config source of truth
now, not a per-call override), the `exists_ok` *parameter* (the decision is
now driven entirely by whether `DATA_VERSION == "SCRATCH"`, not a caller flag),
and `_assert_local_path_matches_base_path` (existed only to guard the
override-version substitution, which no longer exists). The raise-if-exists
safety net itself is **kept** for normal (non-`"SCRATCH"`) T: saves — this
was the one point corrected after the first draft wrongly dropped it. The
"don't accidentally write T: from local mode" concern is handled by
construction — the local-mode save branch never computes a T: path at all —
rather than by a runtime path-prefix check.

### `landloss` versioned-data helpers

`src/landloss/io/versioned_store.py` — now very thin, since `tdrive_sync`
resolves `base_dir`/version entirely on its own:

```python
def save_hazard(obj, *, fname, sub_dirs=None, **kwargs) -> None:
    ts.local_save(obj, fname=fname, sub_dirs=["hazard", *(sub_dirs or [])], **kwargs)


def read_hazard(
    *, fname, sub_dirs=None, copy_to_local=True, return_path=False, **kwargs
):
    return ts.local_read(
        fname=fname,
        sub_dirs=["hazard", *(sub_dirs or [])],
        copy_to_local=copy_to_local,
        return_path=return_path,
        **kwargs,
    )


# ...and the same pair for exposure, vul, loss
```

Generated from one private `_save`/`_read` helper parameterised by module
name, so the eight public functions are one line each, not eight
implementations.

## Configuration

**`tdrive_sync_config.py`** (new, project root, committed to git):

```python
"""Project-wide tdrive_sync settings: where landloss's own versioned data lives."""

from pathlib import Path

BASE_DIR = Path(
    r"T:\Auckland\Projects\1017473\1017473.2003\WorkingMaterial\versioned_data"
)
DATA_VERSION = "v1"  # placeholder — confirm the actual current version with the team
# Set DATA_VERSION = "SCRATCH" to let saves at this version overwrite freely
# instead of raising when a file already exists.
```

This path is inside `T:\Auckland\Projects\1017473\1017473.2003`, i.e. within
the read-write area the repo's Copilot instructions allow — no conflict there.

**New in `.env.example`:**

```dotenv
# tdrive_sync — local-only working mode (never touches T: when on)
TTDRIVE_SYNC_LOCAL_MODE=False
TTDRIVE_SYNC_LOCAL_VERSION=
TTDRIVE_SYNC_CACHE_DIR=.tdrivecache
```

`TTDRIVE_SYNC_LOCAL_VERSION` is only required when `TTDRIVE_SYNC_LOCAL_MODE=True`
— `load_local_mode_settings` raises a clear error otherwise.

`.tdrivecache/` added to `.gitignore` alongside the existing `.koopcache/`
entry.

## Dependencies

`tdrive_sync` needs `pyarrow` directly (`pyarrow.parquet`, for the
has-a-geometry-column parquet sniff) — currently only a transitive dependency.
Add it to `[project.dependencies]` in `pyproject.toml`.

`pyproject.toml` needs an explicit wheel package list once there are two
top-level packages under `src/`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/landloss", "src/tdrive_sync"]
```

(Today hatchling auto-detects the single `src/landloss` package from the
project name; that stops working with a second top-level package.)

## Testing

`tests/tdrive_sync/` (mirrors `src/tdrive_sync/`, no real network drive):

- **Config discovery**: `find_config_file` walks up from a nested `tmp_path`
  subdirectory and finds a `tdrive_sync_config.py` placed at an ancestor;
  raises a clear error when none exists anywhere up to the filesystem root.
- **Config loading**: valid `BASE_DIR`/`DATA_VERSION` load correctly; missing
  or wrong-typed attributes raise a clear error.
- Tests exercise the *real* discovery+load path via
  `monkeypatch.chdir(tmp_path)` plus a real `tdrive_sync_config.py` fixture
  file written under `tmp_path`, with an autouse fixture calling
  `load_config.cache_clear()` between tests — not mocking `_config` internals.
- **Format round-trip** for each supported suffix (csv, json, pickle; parquet
  and gpkg with a small in-memory GeoDataFrame/DataFrame).
- **Local mode OFF, normal `DATA_VERSION`**: `local_save` raises
  `FileExistsError` when the file already exists at either the local-cache or
  "T:" (a `tmp_path` standing in for it) tier, and succeeds when it does not;
  `get_path` copies from "T:" into the local cache when missing or stale, and
  returns the cached path once present.
- **Local mode OFF, `DATA_VERSION == "SCRATCH"`**: `local_save` overwrites an
  existing file at both tiers without raising.
- **Local mode ON**: `local_save` writes only under the local-version cache
  tier, never touching the "T:" stand-in, and always overwrites; `local_read`
  exercises all three fallback steps — local-version hit, data-version-cache
  hit (no "T:" access), and final fall-through to "T:" with the data-version
  cache populated afterwards.
- **Atomic copy**: two threads "racing" to copy the same source file to the
  same destination both succeed and leave identical bytes (adapted from the
  reasoning in the original `_copy_one` docstring).

`tests/landloss/io/test_versioned_store.py`:

- Each of the eight wrapper functions calls `tdrive_sync.local_save`/
  `local_read` with `sub_dirs=["<module>", ...]` (monkeypatching
  `tdrive_sync.local_save`/`local_read`, since the wrapper's only job is that
  one line).

Run `uv run --frozen pytest` and `uv run --frozen prek -a` before considering
this done, per `CLAUDE.md`.

## Documentation

- **`README.md`** — new "Environment variables" section documenting *every*
  `.env` variable in `.env.example` (the existing Koordinates keys and
  `KOOPCACHE_DIR`, plus the three new `TTDRIVE_SYNC_*` vars), including a
  plain-language explanation of the local-mode fallback chain (local version →
  data-version cache → T:) so a new developer can understand it without
  reading `_config.py`.
- **`AGENTS.md`** — add a short note that any change adding or changing a
  `.env` variable must update the "Environment variables" section of
  `README.md` in the same change.
- **`.agents/context/code-structure.md`** — add a short section on
  `tdrive_sync`/`versioned_store.py` alongside the existing "Koordinates
  access and caching" section.
- Changelog entry: `doc/whatsnew/<initials>.feature.<yymmddhhmm>.md`.
- Docstrings throughout `tdrive_sync` (Google-style, fully typed — the
  package is linted with `select = ["ALL"]` same as `landloss`).

## How an agent (e.g. Copilot CLI) uses this

This repo's Copilot instructions treat `T:` as read-only everywhere except
inside `T:\Auckland\Projects\1017473\1017473.2003` — and `BASE_DIR` in
`tdrive_sync_config.py` is fixed inside that path, so *reads* are always fine
(read access to `T:` is unrestricted repo-wide) and *writes* through
`tdrive_sync` in this repo never leave the allowed subtree by construction.
That does not mean an agent should always write to the shared `DATA_VERSION`
freely — the two `.env` toggles vs. the committed config file carry very
different weight, and an agent should treat them differently:

- **`.env` (`TTDRIVE_SYNC_LOCAL_MODE`/`TTDRIVE_SYNC_LOCAL_VERSION`)** — private,
  gitignored, per-session. Cheap for an agent to flip on its own initiative;
  changing it affects nobody else and is not committed.
- **`tdrive_sync_config.py` (`BASE_DIR`/`DATA_VERSION`)** — shared, committed,
  team-visible. An agent should not edit this file, or delete/overwrite the
  file it points at, without the user explicitly asking for it — the same bar
  as any other commit that changes shared project state.

Pseudocode for the three things an agent actually does:

```python
# 1. Reading — always safe, in either mode. Just read.
def agent_read(fname, sub_dirs):
    return ts.local_read(fname=fname, sub_dirs=sub_dirs)


# 2. Iterating — exploring, re-running a step a dozen times, producing
#    throwaway intermediate files. Switch to local mode first so nothing
#    touches the shared T: version while iterating.
def agent_iterate(obj, fname, sub_dirs):
    ensure_env(
        TTDRIVE_SYNC_LOCAL_MODE="True", TTDRIVE_SYNC_LOCAL_VERSION="<session tag>"
    )
    ts.local_save(obj, fname=fname, sub_dirs=sub_dirs)  # local-only, overwrites freely


# 3. Publishing — writing the output the team is meant to see, once the user
#    has actually asked for that (not something an agent decides alone).
def agent_publish(obj, fname, sub_dirs):
    ensure_env(TTDRIVE_SYNC_LOCAL_MODE="False")
    try:
        ts.local_save(obj, fname=fname, sub_dirs=sub_dirs)  # writes T: at DATA_VERSION
    except FileExistsError:
        # Don't silently retry as SCRATCH or bump DATA_VERSION — ask the user,
        # since both are team-visible, committed decisions.
        ask_user(
            "File exists at the current DATA_VERSION. Bump the version, "
            'set DATA_VERSION="SCRATCH", or leave it?'
        )
```

The practical rule of thumb: an agent can read and can iterate (local mode)
without asking, because neither touches the shared drive or git history. It
should not write to the real `DATA_VERSION`, and never edits
`tdrive_sync_config.py`, without the user asking it to.

## Non-goals (explicitly out of scope for this plan)

- Migrating the existing hardcoded T-drive paths in `gen_ces_loss_data.py`,
  `gen_observed_damage_db.py`, and `fig_land_damage_v_lsn.py` to use the new
  helpers — a natural follow-up, not asked for here.
- Per-module version env vars (rejected earlier in favour of one shared
  `DATA_VERSION` in the config file).
- Changing the *upstream* NLM release-reading convention
  (`NLM_VERSION`/`NLM_OBS_VERSION`) — a separate, already-working concern.

## Open items to confirm during implementation

- The actual value to commit for `DATA_VERSION` in `tdrive_sync_config.py`
  (placeholder `"v1"` above) — confirm with the user before committing it.
- Whether `TTDRIVE_SYNC_LOCAL_VERSION` should have any validation on its shape
  (e.g. must not equal `DATA_VERSION`, to avoid a local write silently aliasing
  the shared version) — flag if this comes up while implementing, otherwise
  leave unconstrained.
