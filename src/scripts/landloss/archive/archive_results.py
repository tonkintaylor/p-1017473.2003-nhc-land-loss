"""Copy a finished run's results into the versioned data store on T:.

    uv run --frozen python src/scripts/landloss/archive/archive_results.py
    uv run --frozen python src/scripts/landloss/archive/archive_results.py --copy

The pipeline writes its results to ``temp/`` and does not save them through
``tdrive_sync``. This puts them where ``tdrive_sync.local_save`` would have,
with local-only mode off: ``BASE_DIR/DATA_VERSION/<module>/<path under
temp/<module>>``, the T: locations from ``tdrive_sync_config.py``. So
``temp/loss/settlement-w000-r000-porirua.parquet`` goes to
``…/versioned_data/v1/loss/settlement-w000-r000-porirua.parquet``.

**Each territorial authority comes from its own run** (``config.RESULT_SOURCES``):
a file is taken for an authority only from that authority's folder, and only
when its name carries the authority, so another run's out-of-date copy of the
same file is never picked up. The loss viewer and the equity figures under
``report/`` go to ``…/v1/report/``.

**Left out** (:func:`left_out`), each because it can be rebuilt or should not
leave this machine:

- the DEMs and what is derived from them alone: ``dem-``, ``slope-`` and
  ``aspect-`` grids at every resolution, and everything under ``terrain/``;
- the tile working caches, the ``*-tiles/`` and ``*-tiles-<extent>/``
  folders (each step's merged result beside them, such as
  ``urban-slope-found-<extent>.pkl``, is kept);
- ground layers left under ``hazard/landslide/`` from before the ground module
  had its own folder;
- the QV roll's per-property records: ``claim-valuation-links-*``, and the
  ``qv-tier-factors/`` and ``land-value-vs-qv/`` validation layers;
- anything not named for one of the authorities: the pilot, older "full"
  extent runs and the claim reports kept in ``temp/loss``.

Without ``--copy`` nothing is written to T: and T: is not read: the plan is
printed and written to ``temp/archive/``. With it, every target is checked
first and the copy stops if any exists with different contents
(:mod:`copying`). A manifest of every file -- path, source, size, time and
SHA-256 -- and a README naming the commit and the sources are written beside
the results as ``archive-<yymmddhhmm>-manifest.csv`` and ``-README.md``.
"""

import re
import sys
from pathlib import Path, PurePath

import tdrive_sync as ts
from scripts.landloss.archive import config
from scripts.landloss.archive.copying import (
    PlannedCopy,
    damage,
    describe_plan,
    git_commit,
    run_copy,
    stamp,
    write_manifest,
    write_plan_csv,
)
from scripts.landloss.paths import TEMP_DIR

# The pipeline's modules, each a folder under temp/ and under the version.
MODULES = ("ground", "exposure", "hazard", "vul", "loss")

# A DEM, or a slope or aspect grid built from it alone, at any resolution.
DEM_GRID = re.compile(r"^(dem|slope|aspect)-\d+m-")
# Validation layers that carry the QV roll property by property.
QV_FOLDERS = ("qv-tier-factors", "land-value-vs-qv")
QV_FILE_PREFIXES = ("claim-valuation-links-",)
# Ground layers left in hazard/landslide/ from before the ground module.
OLD_GROUND_PREFIXES = ("ground-map-",)


def authority_of(name: str, authorities) -> str | None:
    """Return the authority a file name is for, or None.

    The name must carry ``-<authority>`` followed by ``.`` or ``-``, as
    ``extent_suffix`` writes it, so ``dem-1m-lower-hutt.tif`` and
    ``settlement-w000-r000-lower-hutt.parquet`` are Lower Hutt's.
    """
    found = [
        authority
        for authority in authorities
        if re.search(rf"-{re.escape(authority)}(?=[.-])", name)
    ]
    return found[0] if len(found) == 1 else None


def left_out(relative: PurePath) -> str | None:  # noqa: PLR0911 -- one reason per rule
    """Return why a file under temp/ is not archived, or None to archive it.

    Args:
        relative: The file's path under ``temp/``, its module first.
    """
    name, parts = relative.name, relative.parts
    if parts[0] not in MODULES:
        return "not a module's output"
    if name.endswith(".partial"):
        return "unfinished write"
    # Ground's folders end in -tiles, hazard's carry -tiles- before the extent.
    if any(part.endswith("-tiles") or "-tiles-" in part for part in parts[:-1]):
        return "tile working cache"
    if "terrain" in parts or DEM_GRID.match(name):
        return "DEM or a grid derived from it"
    if any(folder in parts for folder in QV_FOLDERS) or name.startswith(
        QV_FILE_PREFIXES
    ):
        return "QV roll per-property records (sensitive)"
    if parts[:2] == ("hazard", "landslide") and name.startswith(OLD_GROUND_PREFIXES):
        return "ground layer left from before the ground module"
    return None


def plan_results(sources, *, target_of) -> tuple[list[PlannedCopy], dict[str, int]]:
    """Plan the copy of each authority's results from its own run's folder.

    Args:
        sources: ``{authority: temp folder}``.
        target_of: Maps a path under ``temp/`` to its path on T:.

    Returns:
        The files to copy, and how many were left out for each reason.
    """
    plan, skipped = [], {}
    for authority, root in sources.items():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            relative = PurePath(path.relative_to(root))
            if authority_of(relative.name, sources) != authority:
                continue
            reason = left_out(relative)
            if reason is not None:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            plan.append(
                PlannedCopy(
                    path,
                    target_of(relative),
                    f"{authority} {relative.parts[0]}",
                    note=f"from {root}",
                )
            )
    return plan, skipped


def plan_reports(root: Path, globs, skip, *, target_of) -> list[PlannedCopy]:
    """Plan the copy of the report outputs, each under report/ on T:."""
    plan = []
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not any(word in path.name for word in skip):
                relative = PurePath(path.relative_to(root))
                plan.append(
                    PlannedCopy(
                        path,
                        target_of(PurePath("report", relative)),
                        f"report {relative.parent.as_posix()}",
                    )
                )
    return plan


def on_tdrive(relative: PurePath) -> Path:
    """Return where a path under temp/ goes on T:, as tdrive_sync would save it."""
    return ts.get_base_path(fname=relative.name, sub_dirs=list(relative.parts[:-1]))


def readme(plan, skipped, sources, commit) -> str:
    """Return the archive's README: what this is, from where and at what commit."""
    lines = [
        "# Archived run results",
        "",
        (
            f"Copied by `src/scripts/landloss/archive/archive_results.py` at commit "
            f"`{commit}`, {len(plan):,} files. Every file is listed in the manifest "
            "beside this, with its SHA-256."
        ),
        "",
        "Each territorial authority's results come from the run that built them:",
        "",
        *[f"- {authority}: `{root}`" for authority, root in sources.items()],
        "",
        "Left out, by reason:",
        "",
        *[f"- {reason}: {count:,} files" for reason, count in sorted(skipped.items())],
    ]
    return "\n".join(lines) + "\n"


def main(*, sources, report_root, report_globs, report_skip, copy):
    """Plan the archive, print it, and copy it when asked.

    Args:
        sources: ``{authority: temp folder}`` (``config.RESULT_SOURCES``).
        report_root: The report/ folder.
        report_globs: The report outputs to include, as globs under it.
        report_skip: Words that leave a report file out when in its name.
        copy: Whether to copy to T:; otherwise only the plan is written.
    """
    plan, skipped = plan_results(sources, target_of=on_tdrive)
    plan += plan_reports(report_root, report_globs, report_skip, target_of=on_tdrive)
    version_root = ts.get_base_path(fname="x").parent
    print(f"Archiving to {version_root}")
    describe_plan(plan)
    print("Left out:")
    for reason, count in sorted(skipped.items()):
        print(f"  {reason:<50} {count:>5} files")
    plan_path = TEMP_DIR / "archive" / f"results-plan-{stamp()}.csv"
    write_plan_csv(plan, plan_path)
    print(f"Wrote the plan to {plan_path}")
    print("Checking every source file is whole ...", flush=True)
    damaged = [
        (item.source, reason) for item in plan if (reason := damage(item.source))
    ]
    for path, reason in damaged:
        print(f"  DAMAGED {path}: {reason}")
    print(f"  {len(damaged)} of {len(plan)} files damaged; a copy refuses them all")
    if not copy:
        print("Dry run: nothing was copied. Run again with --copy to copy.")
        return
    run_copy(plan)
    when, commit = stamp(), git_commit()
    write_manifest(
        plan, version_root / f"archive-{when}-manifest.csv", root=version_root
    )
    with (version_root / f"archive-{when}-README.md").open(
        "x", encoding="utf-8"
    ) as file:
        file.write(readme(plan, skipped, sources, commit))
    print(f"Copied, and wrote archive-{when}-manifest.csv and -README.md")


if __name__ == "__main__":
    main(
        sources=config.RESULT_SOURCES,
        report_root=config.REPORT_ROOT,
        report_globs=config.REPORT_GLOBS,
        report_skip=config.REPORT_SKIP,
        copy="--copy" in sys.argv[1:],
    )
