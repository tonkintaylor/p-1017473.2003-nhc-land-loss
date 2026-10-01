"""Fetch the final issued claim report for each subproject of a T+T project.

    uv run --frozen python src/scripts/landloss/vul/static_data_gen/fetch_claim_reports.py
    uv run --frozen python src/scripts/landloss/vul/static_data_gen/fetch_claim_reports.py --project 1502000 --limit 10
    uv run --frozen python src/scripts/landloss/vul/static_data_gen/fetch_claim_reports.py --subprojects 0001 0002
    uv run --frozen python src/scripts/landloss/vul/static_data_gen/fetch_claim_reports.py --claims-list iag-1502000 --study-area-only --limit 50

**Fetch from a claims list where there is one.** ``--claims-list`` takes a list
built by ``gen_claims_lists.py`` from Site Search, which already knows every
claim's coordinates, and fetches only the subprojects on it -- across as many
projects as the list spans, ``--limit`` counted over all of them.
``--study-area-only`` keeps the claims inside the four study authorities. This
is how the whole-project walk is avoided: most of a project's reports are
claims the study does not need, at about 4 MB each.

**Where the project is.** A live project sits under its owning office and a
closed one in the archive (``I:\\``, and some under ``T:\\Archive\\TT``),
without its leading zeros. Every root in ``PROJECT_ROOTS`` is searched and the
copies combined, because a project can be in more than one: an office folder of
empty stubs beside the archived one with the files. A subproject filed inside
another one's folder is found as well.

**Step one of two.** This only gets the files: it finds each subproject's
report on T:, copies it into the local tdrive_sync cache, and records what it
fetched in an index. Reading figures out of the reports is a separate step,
run against the cache, so that adding a field to the extraction never means
fetching thousands of files again.

**Which file is the report.** A ``.docx``, draft or not, because that is what
the extraction reads; see :func:`choose_report` for the order. In short:
``IssuedDocuments`` first (searched recursively, so "Final report" and dated
subfolders are found), then ``WorkingMaterial`` and its subfolders, then a PDF
in ``IssuedDocuments`` as a last resort that is recorded but not read. A file
counts as a report if "report" or "rpt" is in its name (or, in
``WorkingMaterial``, its folder's name); sketches and photographs never do.
Within a folder, one with "final" in its path beats one without, and among
equals the most recently modified wins -- the rule the IAG 1502000 index was
built with, plus the preference for a final that Maxim Millen gave. The index
records ``is_draft`` and ``source_folder``, because a draft's figures can
differ from what was issued. A subproject with no candidate is recorded as
such rather than silently dropped, so a gap in the index can be told from a
subproject nobody looked at.

**It is incremental, and it resumes.** A subproject already in the index is
skipped, so raising ``--limit`` fetches only the new ones, and ``--all`` fetches
everything. The index is saved every ten subprojects and again when a run stops
-- finished, interrupted or failed -- so a stopped run carries on from where it
was when started again. ``--refresh`` looks at every subproject again. Subprojects are taken in folder order, so the first batch is
always the same batch.

**Only the report's text is cached, and nothing from it is committed.** A
``.docx`` is a zip, and step two reads one member of it, ``word/document.xml``;
that alone is read from T: and cached, as ``<report>.docx.document.xml`` in the
gitignored ``.tdrivecache/``, which leaves the photographs -- most of a
report's 4 MB -- on T:. A PDF is not cached, since step two does not read one.
The index holds paths, dates and the chosen file's name. ``--slim-cache``
converts a cache filled with whole reports before this, offline.

This reads T: directly through ``tdrive_sync``, so it runs on a machine with
the drive mapped. The index is written to
``src/landloss/common/assets/claim_reports/<project>/report-index.csv``.
"""

import argparse
import csv
import os
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

import tdrive_sync as ts
from scripts.landloss.paths import CLAIM_REPORTS_ASSETS_DIR, REPO_ROOT

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Where a project's folder may be. Live projects sit under their owning office;
# closed ones move to the archive, which is where the 2013 and 2016 EQC
# programmes are now. Tried in order.
PROJECT_ROOTS = (
    Path(r"T:\Auckland\Projects"),
    Path(r"T:\Wellington\TT Projects"),
    Path(r"T:\Wellington\Projects"),
    Path(r"T:\Christchurch\Projects"),
    Path(r"T:\Nelson\Projects"),
    Path(r"T:\Archive\TT"),
    # The main archive, e.g. I:\85650. T:\Archive\TT holds only some archived
    # projects (85651 but not 85650), so both are searched.
    Path("I:\\"),
)
DEFAULT_PROJECT = "1502000"
CLAIMS_LISTS_DIR = CLAIM_REPORTS_ASSETS_DIR / "claims-lists"
DEFAULT_LIMIT = 10
# The member of a .docx holding its text and tables -- all the extraction
# reads -- and the suffix its cached copy is given.
DOCUMENT_MEMBER = "word/document.xml"
TEXT_SUFFIX = ".document.xml"

# How often the index is saved during a run, in subprojects looked at.
CHECKPOINT_EVERY = 10
INDEX_NAME = "report-index.csv"

# Subproject folders are named "<project>.<subproject>", sometimes with a
# trailing suffix such as " SUPERSEDED".
SUBPROJECT_PATTERN = re.compile(r"^(\d+)\.(\d+)")

# What a subproject's row says about how it went.
FETCHED = "fetched"
NO_ISSUED_DOCUMENTS = "no IssuedDocuments or WorkingMaterial folder"

ISSUED_DOCUMENTS = "IssuedDocuments"
# Spelt both ways across the offices' folder templates.
WORKING_MATERIAL = ("WorkingMaterial", "Working Material")

# How the offices named a report: "Final Report", "T&T rpt", "finalrpt".
REPORT_NAME = re.compile(r"report|rpt", re.IGNORECASE)
NO_REPORT = "no report docx or pdf"

# Attachments issued alongside a report, often with "report" in their names.
NOT_A_REPORT = re.compile(r"sketch|photo|drawing|appendix", re.IGNORECASE)

# A draft, as the offices named them: "DRAFT_Report", "Draft for LA Review",
# "LAAC.20170227.dft.2085Kenepuru", "LAAC.20161202.EQC.drt.282Hampden".
DRAFT = re.compile(r"draft|(?<![a-z])(?:dft|drt)(?![a-z])", re.IGNORECASE)

# A final, likewise: "Final Report", "FINAL", and the Nelson office's
# "LAAC.20161202.EQC.fnl.282Hampden".
FINAL = re.compile(r"final|(?<![a-z])fnl(?![a-z])", re.IGNORECASE)
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class IndexRow:
    """One subproject's entry in the index."""

    project_number: str
    subproject_number: str
    subproject: str
    status: str
    report_path: str = ""
    report_name: str = ""
    is_final: bool = False
    is_draft: bool = False
    source_folder: str = ""
    last_modified: str = ""
    cached_path: str = ""
    fetched_at: str = ""


def report_candidates(
    issued_documents: Path, suffix: str = ".docx", *, named_report: bool = True
) -> list[Path]:
    """Return every file of one type under IssuedDocuments that could be the report.

    Args:
        issued_documents: A subproject's ``IssuedDocuments`` folder.
        suffix: ``".docx"`` or ``".pdf"``.
        named_report: Keep only files with "report" in the name. Off, any file
            of the type counts, which is how a draft named like
            ``LAAC.20170320.dft.2085Kenepuru.docx`` is found.

    Returns:
        The candidates, in no particular order. Word's ``~$`` lock files, and
        the sketch and photograph attachments issued beside a report, are
        excluded.
    """
    return [
        path
        for path in issued_documents.rglob(f"*{suffix}")
        if (not named_report or REPORT_NAME.search(path.name))
        and not path.name.startswith("~$")
        and not NOT_A_REPORT.search(path.name)
    ]


def working_candidates(working_material: Path) -> list[Path]:
    """Return the docx files under WorkingMaterial that look like the report.

    Searched through every subfolder, but kept to files named as a report, or
    sitting in a folder so named ("Final report\\20210812.adw.8caesarspl.docx"):
    WorkingMaterial holds every other Word file the job produced as well.
    """
    out = []
    for path in working_material.rglob("*.docx"):
        if path.name.startswith("~$") or NOT_A_REPORT.search(path.name):
            continue
        below = path.relative_to(working_material).as_posix()
        if REPORT_NAME.search(below):
            out.append(path)
    return out


def is_draft(path: Path) -> bool:
    """Return whether a report's file name marks it as a draft."""
    return bool(DRAFT.search(path.name))


def is_final(path: Path, issued_documents: Path) -> bool:
    """Return whether "final" appears in the path below IssuedDocuments.

    Only the part below ``IssuedDocuments`` is looked at, so a project folder
    that happens to contain the word cannot mark every report final.
    """
    return bool(FINAL.search(path.relative_to(issued_documents).as_posix()))


def _best(candidates: list[Path], folder: Path) -> Path:
    """Return the final if there is one, then the most recently modified."""
    return max(
        candidates, key=lambda path: (is_final(path, folder), path.stat().st_mtime)
    )


def choose_report(subproject_dir: Path) -> tuple[Path, Path] | None:
    """Return the subproject's report and the folder it was found in.

    A ``.docx`` is taken wherever there is one, draft or not, because that is
    what the extraction reads. The 2013 and 2016 EQC finals were often issued as
    PDF only, with the ``.docx`` left as a draft whose name need not say
    "report", or kept in WorkingMaterial rather than issued at all. So the
    order is:

    1. a ``.docx`` in IssuedDocuments named as a report;
    2. any ``.docx`` in IssuedDocuments;
    3. a ``.docx`` in WorkingMaterial named as a report, or in a folder so
       named, searched through its subfolders;
    4. a PDF in IssuedDocuments, recorded so the gap shows but not read.

    Within a step a final beats the rest and then the latest wins. A draft's
    figures can differ from what was issued, which is why the index records
    ``is_draft`` and ``source_folder``.

    Args:
        subproject_dir: The subproject's folder.

    Returns:
        The chosen report and the folder searched to find it, or ``None`` if
        there is no candidate anywhere.
    """
    issued = subproject_dir / ISSUED_DOCUMENTS
    working = next(
        (
            subproject_dir / name
            for name in WORKING_MATERIAL
            if (subproject_dir / name).is_dir()
        ),
        None,
    )
    steps = []
    if issued.is_dir():
        steps += [
            (issued, lambda: report_candidates(issued)),
            (issued, lambda: report_candidates(issued, named_report=False)),
        ]
    if working is not None:
        steps.append((working, lambda: working_candidates(working)))
    if issued.is_dir():
        steps.append((issued, lambda: report_candidates(issued, ".pdf")))
    for folder, find in steps:
        if candidates := find():
            return _best(candidates, folder), folder
    return None


def text_cache_path(report: Path) -> Path:
    """Return where a report's text is cached: beside its tdrive_sync mirror.

    ``…\\IssuedDocuments\\Report.docx`` is cached as
    ``.tdrivecache\\…\\IssuedDocuments\\Report.docx.document.xml``.
    """
    local = ts.get_cached_local_path(report)
    return local.with_name(local.name + TEXT_SUFFIX)


def write_text(data: bytes, target: Path, *, mtime: float) -> None:
    """Write a report's text atomically, stamped with the report's own mtime."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    os.replace(part, target)
    os.utime(target, (mtime, mtime))


def cache_report_text(report: Path) -> Path | None:
    """Cache the one part of a report the extraction reads, not the report.

    A ``.docx`` is a zip archive, and its text and tables are the single member
    ``word/document.xml``; the photographs that make a report 4 MB are separate
    members. Reading that one member from T: transfers only its bytes, and
    caching it alone keeps about a twentieth of the space. The full report
    stays on T: at the index's ``report_path`` for anyone checking by hand.

    A PDF is not cached at all, since the extraction does not read one.

    Args:
        report: The chosen report on T:.

    Returns:
        The cached text, or ``None`` for a report that is not a ``.docx``.

    Raises:
        zipfile.BadZipFile: If the ``.docx`` is not a readable zip.
        KeyError: If it has no ``word/document.xml``.
    """
    if report.suffix.lower() != ".docx":
        return None
    target = text_cache_path(report)
    mtime = report.stat().st_mtime
    if target.exists() and target.stat().st_mtime >= mtime:
        return target
    with zipfile.ZipFile(report) as archive:
        data = archive.read(DOCUMENT_MEMBER)
    write_text(data, target, mtime=mtime)
    return target


def slim_cache(assets_dir: Path | None = None) -> tuple[int, int]:
    """Replace every whole report already cached with just its text.

    For caches filled before :func:`cache_report_text` existed. Runs offline:
    each cached ``.docx`` is read locally, its ``word/document.xml`` written
    beside it, the index pointed at that, and the ``.docx`` deleted. A cached
    PDF, which the extraction never reads, is deleted and its row left
    pointing at T: only.

    Returns:
        The reports slimmed, and the bytes freed.
    """
    slimmed = freed = 0
    for index_file in sorted(
        (assets_dir or CLAIM_REPORTS_ASSETS_DIR).glob("*/" + INDEX_NAME)
    ):
        index = read_index(index_file)
        changed = False
        for name, row in index.items():
            if not row.cached_path:
                continue
            cached = Path(row.cached_path)
            cached = cached if cached.is_absolute() else REPO_ROOT / cached
            if not cached.exists() or cached.name.endswith(TEXT_SUFFIX):
                continue
            size = cached.stat().st_size
            new_path = ""
            if cached.suffix.lower() == ".docx":
                try:
                    with zipfile.ZipFile(cached) as archive:
                        data = archive.read(DOCUMENT_MEMBER)
                except (zipfile.BadZipFile, KeyError) as exc:
                    print(f"  {name}: left as it is ({exc})")
                    continue
                target = cached.with_name(cached.name + TEXT_SUFFIX)
                write_text(data, target, mtime=cached.stat().st_mtime)
                new_path = repo_relative(target)
                freed -= target.stat().st_size
            cached.unlink()
            freed += size
            slimmed += 1
            index[name] = IndexRow(**{**asdict(row), "cached_path": new_path})
            changed = True
        if changed:
            write_index(index_file, index)
    print(f"Slimmed {slimmed} cached reports, freeing {freed / 1e6:,.0f} MB")
    return slimmed, freed


def repo_relative(path: Path) -> str:
    """Return a cached path relative to the repo root where it lies inside it.

    The index is committed, so an absolute path under one developer's home
    folder would point nowhere on anyone else's machine. A cache configured
    outside the repo is kept absolute, since there is nothing to be relative
    to.
    """
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def index_subproject(
    subproject_dir: Path | list[Path], *, fetch: bool = True
) -> IndexRow | None:
    """Find, and optionally cache, one subproject's report.

    Args:
        subproject_dir: The subproject's folder on T:, or every copy of it
            where the project is filed under more than one root.
        fetch: Whether to copy the report into the local cache. Off, the row
            records what would be fetched without copying anything.

    Returns:
        The subproject's row, or ``None`` if the folder is not a subproject.
    """
    copies = subproject_dir if isinstance(subproject_dir, list) else [subproject_dir]
    subproject_dir = copies[0]
    match = SUBPROJECT_PATTERN.match(subproject_dir.name)
    if match is None:
        return None
    project_number, subproject_number = match.groups()
    base = {
        "project_number": project_number,
        "subproject_number": subproject_number,
        "subproject": subproject_dir.name,
    }
    try:
        if not any(
            (copy / name).is_dir()
            for copy in copies
            for name in (ISSUED_DOCUMENTS, *WORKING_MATERIAL)
        ):
            return IndexRow(**base, status=NO_ISSUED_DOCUMENTS)
        chosen = choose_across(copies)
        if chosen is None:
            return IndexRow(**base, status=NO_REPORT)
        report, folder = chosen
        modified = datetime.fromtimestamp(report.stat().st_mtime, tz=UTC)
        cached = cache_report_text(report) if fetch else None
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"  {subproject_dir.name}: {exc}")
        return IndexRow(**base, status=UNREADABLE)
    return IndexRow(
        **base,
        status=FETCHED,
        report_path=str(report),
        report_name=report.name,
        is_final=is_final(report, folder),
        is_draft=is_draft(report),
        source_folder=folder.name,
        last_modified=modified.strftime("%Y-%m-%d"),
        cached_path=repo_relative(cached) if cached is not None else "",
        fetched_at=(datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M") if fetch else ""),
    )


def index_path(project: str) -> Path:
    """Return where a project's index is kept."""
    return CLAIM_REPORTS_ASSETS_DIR / project / INDEX_NAME


def read_index(path: Path) -> dict[str, IndexRow]:
    """Return an existing index keyed by subproject folder name, or nothing."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {
        row["subproject"]: IndexRow(
            **{
                **row,
                "is_final": row.get("is_final", "") == "True",
                # Indexes written before drafts were flagged have no column.
                "is_draft": row.get("is_draft", "") == "True",
            }
        )
        for row in rows
    }


def write_index(path: Path, rows: dict[str, IndexRow]) -> None:
    """Write the index, in subproject order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=[field.name for field in fields(IndexRow)]
        )
        writer.writeheader()
        for name in sorted(rows):
            writer.writerow(asdict(rows[name]))


def subproject_dirs(project_dir: Path, wanted: list[str] | None = None) -> list[Path]:
    """Return the project's subproject folders, in order.

    Args:
        project_dir: The project folder on T:.
        wanted: Subproject numbers to keep, e.g. ``["0001", "0042"]``. ``None``
            keeps every subproject.

    Returns:
        The folders, sorted by name.
    """
    top = [path for path in project_dir.iterdir() if path.is_dir()]
    # Some offices filed a claim inside another claim's folder, e.g.
    # 86101.0360\86101.0371, so one level of nesting is searched as well. A
    # folder we are not allowed into (1502000.1937 is one) is kept as itself
    # -- its report is then recorded as unreadable -- rather than stopping
    # the whole run.
    nested = []
    for parent in top:
        if not SUBPROJECT_PATTERN.match(parent.name):
            continue
        try:
            children = list(parent.iterdir())
        except OSError as exc:
            print(f"  {parent.name}: cannot be read ({exc.strerror or exc})")
            continue
        nested += [
            child
            for child in children
            if child.is_dir() and SUBPROJECT_PATTERN.match(child.name)
        ]
    dirs = sorted(top + nested, key=lambda path: path.name)
    if wanted is None:
        return dirs
    keep = {number.zfill(4) for number in wanted}
    return [
        path
        for path in dirs
        if (match := SUBPROJECT_PATTERN.match(path.name)) and match.group(2) in keep
    ]


def find_project_dirs(
    project: str, roots: tuple[Path, ...] = PROJECT_ROOTS
) -> list[Path]:
    """Return every folder a project is filed in, across the roots.

    A project sits under its owning office while it is live and under the
    archive once it is closed, and an archived folder drops the leading zeros
    (``0085650`` is filed as ``85650``). **A project can be in both at once**:
    ``T:\\Nelson\\Projects\\871310`` holds empty stub folders while the claims'
    files are under ``T:\\Archive\\TT\\871310``, and
    ``T:\\Wellington\\TT Projects\\85650`` holds no subprojects at all. So every
    root is searched, with both spellings, and all the folders found are kept.

    Args:
        project: The project number, with or without leading zeros.
        roots: The folders to look under, in order.

    Returns:
        Each folder that exists, in root order.

    Raises:
        FileNotFoundError: If no root holds the project.
    """
    spellings = dict.fromkeys((project, str(int(project)), project.zfill(7)))
    found = [
        root / spelling
        for root in roots
        for spelling in spellings
        if (root / spelling).is_dir()
    ]
    if not found:
        tried = ", ".join(str(root) for root in roots)
        msg = f"project {project} is not under any of: {tried}"
        raise FileNotFoundError(msg)
    return list(dict.fromkeys(found))


def choose_across(copies: list[Path]) -> tuple[Path, Path] | None:
    """Return the best report among a subproject's copies in different roots.

    A copy yielding a ``.docx`` beats one yielding only a PDF, since that is
    what the extraction reads; otherwise the first copy with anything wins.
    """
    chosen = [found for copy in copies if (found := choose_report(copy))]
    docx = [found for found in chosen if found[0].suffix.lower() == ".docx"]
    return (docx or chosen or [None])[0]


def fetch(
    project: str,
    *,
    limit: int,
    wanted: list[str] | None = None,
    refresh: bool = False,
    dry_run: bool = False,
    project_roots: tuple[Path, ...] = PROJECT_ROOTS,
    out: Path | None = None,
) -> dict[str, IndexRow]:
    """Fetch up to ``limit`` new reports for a project and update its index.

    Args:
        project: The T+T project number, e.g. ``"1502000"``.
        limit: The most reports to fetch this run. Subprojects with no report
            do not count against it.
        wanted: Subproject numbers to restrict to, or ``None`` for all.
        refresh: Look again at subprojects already in the index.
        dry_run: Find the reports and print them without copying or writing.
        project_roots: Where project folders may be filed.
        out: The index file, defaulting to :func:`index_path`.

    Returns:
        The index as written.
    """
    out = out or index_path(str(int(project)))
    project_dirs = find_project_dirs(project, project_roots)
    index = read_index(out)
    # Each subproject's copies across the roots, in folder order.
    copies: dict[str, list[Path]] = {}
    for project_dir in project_dirs:
        dirs = subproject_dirs(project_dir, wanted)
        print(f"{len(dirs):,} subproject folders under {project_dir}")
        for subproject_dir in dirs:
            copies.setdefault(subproject_dir.name, []).append(subproject_dir)

    fetched = 0
    since_saved = 0
    # The index is saved every CHECKPOINT_EVERY subprojects and again however
    # the loop ends -- finished, interrupted with Ctrl+C, or failed -- so a
    # rerun skips everything already looked at and carries on from there.
    try:
        for name in sorted(copies):
            if fetched >= limit:
                break
            if not refresh and name in index:
                continue
            row = index_subproject(copies[name], fetch=not dry_run)
            if row is None:
                continue
            index[row.subproject] = row
            since_saved += 1
            if row.status == FETCHED:
                fetched += 1
                final = "final" if row.is_final else "NOT marked final"
                if row.is_draft:
                    final += ", DRAFT"
                if row.source_folder != ISSUED_DOCUMENTS:
                    final += f", from {row.source_folder}"
                print(
                    f"  {row.subproject}: {row.report_name} "
                    f"({final}, {row.last_modified})"
                )
            else:
                print(f"  {row.subproject}: {row.status}")
            if not dry_run and since_saved >= CHECKPOINT_EVERY:
                write_index(out, index)
                since_saved = 0
    finally:
        if not dry_run and since_saved:
            write_index(out, index)

    done = sum(row.status == FETCHED for row in index.values())
    if dry_run:
        print(f"Dry run: {fetched} reports found, nothing copied or written")
        return index
    write_index(out, index)
    print(f"Fetched {fetched} this run; {done} reports in the index at {out}")
    return index


def claims_list_path(name: str) -> Path:
    """Return a claims list by name, or the path itself if it is one."""
    path = Path(name)
    if path.suffix == ".csv" and path.exists():
        return path
    return CLAIMS_LISTS_DIR / f"{name}.csv"


def wanted_by_programme(
    claims_list: Path,
    *,
    study_area_only: bool = False,
    programmes: list[str] | None = None,
) -> dict[str, list[str]]:
    """Return a claims list's subproject numbers, grouped by project.

    Args:
        claims_list: A list written by ``gen_claims_lists.py``.
        study_area_only: Keep only the claims inside the four study
            authorities.
        programmes: Keep only these projects, with or without leading zeros.

    Returns:
        Project number to the subproject numbers wanted from it, in list order.
    """
    with claims_list.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if study_area_only:
        rows = [row for row in rows if row["in_study_area"] == "True"]
    grouped: dict[str, list[str]] = {}
    for row in rows:
        project, _, sub = row["subproject"].partition(".")
        grouped.setdefault(project, []).append(sub)
    if programmes:
        keep = {str(int(number)) for number in programmes}
        grouped = {
            project: subs for project, subs in grouped.items() if project in keep
        }
    return grouped


def fetched_count(index: dict[str, IndexRow]) -> int:
    """Return how many reports an index holds."""
    return sum(row.status == FETCHED for row in index.values())


def fetch_list(
    claims_list: Path,
    *,
    limit: int,
    study_area_only: bool = False,
    programmes: list[str] | None = None,
    refresh: bool = False,
    dry_run: bool = False,
    project_roots: tuple[Path, ...] = PROJECT_ROOTS,
) -> int:
    """Fetch the claims on a list, project by project, up to ``limit`` in all.

    Returns:
        How many reports were fetched.
    """
    total = 0
    for project, wanted in wanted_by_programme(
        claims_list, study_area_only=study_area_only, programmes=programmes
    ).items():
        if total >= limit:
            break
        print(f"\n{project}: {len(wanted):,} claims on the list")
        before = fetched_count(read_index(index_path(project)))
        try:
            index = fetch(
                project,
                limit=limit - total,
                wanted=wanted,
                refresh=refresh,
                dry_run=dry_run,
                project_roots=project_roots,
            )
        except FileNotFoundError as exc:
            print(f"  skipped: {exc}")
            continue
        total += max(fetched_count(index) - before, 0)
    verb = "found (dry run, nothing copied)" if dry_run else "fetched"
    print(f"\n{total} reports {verb} from {claims_list.name}")
    return total


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and fetch."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--all",
        action="store_true",
        help="fetch every report there is, ignoring --limit; safe to stop and "
        "rerun, since the index is saved as it goes",
    )
    parser.add_argument(
        "--claims-list",
        help="a list from gen_claims_lists.py, by name (e.g. kaikoura-2016) "
        "or path; fetches only the subprojects on it, across projects",
    )
    parser.add_argument(
        "--programmes",
        nargs="+",
        help="with --claims-list, only these projects, e.g. 1011602 871310",
    )
    parser.add_argument(
        "--study-area-only",
        action="store_true",
        help="with --claims-list, keep only claims inside the four study authorities",
    )
    parser.add_argument(
        "--subprojects",
        nargs="+",
        help="subproject numbers to fetch, e.g. 0001 0042; default all",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="look again at subprojects already in the index",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be fetched without copying or writing anything",
    )
    parser.add_argument(
        "--slim-cache",
        action="store_true",
        help="replace every whole report already cached with just its text, "
        "offline, and exit",
    )
    args = parser.parse_args(argv)
    if args.slim_cache:
        slim_cache()
        return 0
    if args.all:
        args.limit = sys.maxsize
    if args.claims_list:
        fetch_list(
            claims_list_path(args.claims_list),
            limit=args.limit,
            study_area_only=args.study_area_only,
            programmes=args.programmes,
            refresh=args.refresh,
            dry_run=args.dry_run,
        )
        return 0
    fetch(
        args.project,
        limit=args.limit,
        wanted=args.subprojects,
        refresh=args.refresh,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
