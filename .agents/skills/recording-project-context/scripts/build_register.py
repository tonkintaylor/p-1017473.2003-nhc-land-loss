"""Maintain the project register workbook.

The register accumulates over the life of the project, from many transcripts and
ad-hoc requests, so this script never rebuilds the workbook. It appends entries it
has not seen before and leaves every existing row alone, which is what lets the
workbook be edited directly in Excel between runs.

Two commands:

    append <entries.json> [workbook.xlsx]   add any entries whose ID is new
    status <ID> <status> [workbook.xlsx]    set one row's status

An entry given without an ID is allocated the next one in its sheet's sequence,
and the ID is written back into the entries JSON, so a later append recognises
the entry rather than allocating it another ID and adding it twice.

The workbook is the source of truth for the Status column. The JSON supplies an
entry's initial status when the row is first created and is ignored for it
thereafter, so marking something done in Excel survives the next append.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# The register lives in the OneDrive-synced project folder rather than the repo, so
# the team can open it. The user is resolved from the environment: the folder is
# shared, so a hardcoded username would be wrong for everyone but its author.
DEFAULT_WORKBOOK = (
    Path.home()
    / "OneDrive - Tonkin + Taylor Group Ltd"
    / "Data + Analytics - Documents"
    / "Projects"
    / "1017473.2003-nhc-land-loss"
    / "1017473.2003-nhc-land-loss-project-register.xlsx"
)

SHEETS: dict[str, list[str]] = {
    "Tasks": ["ID", "Task", "Owner", "Phase", "Source", "Status", "Updated"],
    "Limitations": ["ID", "Limitation", "Affects", "Source", "Status", "Updated"],
    "Improvements": [
        "ID",
        "Improvement",
        "Rationale",
        "Phase",
        "Source",
        "Status",
        "Updated",
    ],
    # Questions nobody on the team can answer yet. Distinct from a task: a task
    # has someone who can go and do it, whereas a question is waiting on an
    # answer that has to come from outside, usually from NHC.
    "Questions": [
        "ID",
        "Question",
        "Asked of",
        "Answer",
        "Source",
        "Status",
        "Updated",
    ],
}

ID_PREFIXES = {"Tasks": "T", "Limitations": "L", "Improvements": "I", "Questions": "Q"}

# Each sheet closes out differently: a task gets done, a limitation gets mitigated
# or is accepted as a permanent caveat, an improvement gets scheduled or dropped.
STATUSES = {
    "Tasks": ("Open", "In progress", "Done", "Dropped"),
    "Limitations": ("Open", "Mitigated", "Accepted", "Dropped"),
    "Improvements": ("Parked", "Scheduled", "Done", "Dropped"),
    "Questions": ("Open", "Asked", "Answered", "Dropped"),
}

CLOSED_STATUSES = {"Done", "Dropped", "Mitigated", "Accepted", "Answered"}

# Wide enough to read a sentence without wrapping the whole sheet.
WIDE_COLUMNS = {
    "Task",
    "Limitation",
    "Improvement",
    "Rationale",
    "Affects",
    "Question",
    "Answer",
}
WIDE_WIDTH = 70
NARROW_WIDTH = 14

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
CLOSED_FONT = Font(color="808080", italic=True)


def today() -> str:
    """Return the local date, which is what a reader of the register expects."""
    return datetime.now(tz=UTC).astimezone().date().isoformat()


def sheet_for(entry_id: str) -> str | None:
    """Return the sheet an ID belongs to, based on its prefix."""
    for name, prefix in ID_PREFIXES.items():
        if entry_id.upper().startswith(f"{prefix}-"):
            return name
    return None


def header_of(sheet: Worksheet) -> list[str]:
    """Return the sheet's column names in their on-disk order."""
    return [cell.value for cell in sheet[1]]


def style_header(sheet: Worksheet, index: int, column: str) -> None:
    """Format one header cell and set its column width."""
    cell = sheet.cell(row=1, column=index, value=column)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    width = WIDE_WIDTH if column in WIDE_COLUMNS else NARROW_WIDTH
    sheet.column_dimensions[get_column_letter(index)].width = width


def ensure_sheet(workbook: Workbook, name: str, columns: list[str]) -> Worksheet:
    """Return the named sheet, creating it or adding any columns it is missing."""
    if name not in workbook.sheetnames:
        sheet = workbook.create_sheet(name)
        for index, column in enumerate(columns, start=1):
            style_header(sheet, index, column)
        sheet.freeze_panes = "A2"
        return sheet

    sheet = workbook[name]
    header = header_of(sheet)
    for column in columns:
        if column not in header:
            style_header(sheet, len(header) + 1, column)
            header.append(column)
    return sheet


def existing_ids(sheet: Worksheet) -> dict[str, int]:
    """Map each ID already in the sheet to its row number."""
    found: dict[str, int] = {}
    for row in sheet.iter_rows(min_row=2):
        value = row[0].value
        if value:
            found[str(value).strip().upper()] = row[0].row
    return found


def next_id(prefix: str, used: set[str]) -> str:
    """Return the next free ID for a prefix, continuing the existing sequence."""
    numbers = [
        int(entry.split("-", 1)[1])
        for entry in used
        if entry.startswith(f"{prefix}-") and entry.split("-", 1)[1].isdigit()
    ]
    return f"{prefix}-{max(numbers, default=0) + 1:02d}"


def style_row(sheet: Worksheet, row_number: int, *, closed: bool) -> None:
    """Wrap a row's text, and grey it out once it is closed."""
    for cell in sheet[row_number]:
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        if closed:
            cell.font = CLOSED_FONT


def open_workbook(path: Path) -> Workbook:
    """Load the workbook, or start a new one if it does not exist yet."""
    if path.exists():
        return load_workbook(path)
    workbook = Workbook()
    workbook.remove(workbook.active)
    return workbook


def append_to_sheet(
    sheet: Worksheet, name: str, entries: list[dict[str, str]]
) -> tuple[list[str], list[str], list[str]]:
    """Append entries with unseen IDs.

    An entry without an ID is given the next one in the sheet's sequence, and the
    ID is set on the entry in ``entries`` so the caller can save it back.

    Returns:
        The IDs added, the IDs skipped as already present, and the IDs allocated
        to entries that had none.
    """
    header = header_of(sheet)
    present = existing_ids(sheet)
    allocated = set(present)
    added: list[str] = []
    skipped: list[str] = []
    new_ids: list[str] = []

    for position, entry in enumerate(entries):
        entry_id = str(entry.get("ID", "")).strip().upper()
        if entry_id and entry_id in present:
            skipped.append(entry_id)
            continue
        if not entry_id:
            entry_id = next_id(ID_PREFIXES[name], allocated)
            # Recorded on the entry itself, so the caller can write it back to
            # the JSON. An entry left without an ID would be allocated a fresh
            # one, and appended again, on every later run.
            entries[position] = {"ID": entry_id, **entry}
            new_ids.append(entry_id)
        allocated.add(entry_id)

        row = dict(entry, ID=entry_id)
        row.setdefault("Status", STATUSES[name][0])
        row.setdefault("Updated", today())
        sheet.append([row.get(column, "") for column in header])
        style_row(sheet, sheet.max_row, closed=row["Status"] in CLOSED_STATUSES)
        added.append(entry_id)

    sheet.auto_filter.ref = sheet.dimensions
    return added, skipped, new_ids


def command_append(source: Path, output: Path) -> int:
    """Append entries whose ID is new, leaving every existing row untouched."""
    data = json.loads(source.read_text(encoding="utf-8"))

    unknown = set(data) - set(SHEETS)
    if unknown:
        print(f"error: {source} has unknown sheet keys: {', '.join(sorted(unknown))}")
        return 1

    workbook = open_workbook(output)
    added: dict[str, list[str]] = {}
    skipped: list[str] = []
    allocated: list[str] = []

    for name, columns in SHEETS.items():
        # Touch every sheet, not just the ones with entries, so an older workbook
        # picks up any added columns across the board rather than sheet by sheet.
        sheet = ensure_sheet(workbook, name, columns)
        entries = data.get(name, [])
        if not entries:
            continue
        sheet_added, sheet_skipped, sheet_allocated = append_to_sheet(
            sheet, name, entries
        )
        allocated.extend(sheet_allocated)
        if sheet_added:
            added[name] = sheet_added
        skipped.extend(sheet_skipped)

    workbook.save(output)

    # Write any IDs just allocated back into the source, so the JSON log names
    # the same IDs as the workbook and the next append skips these entries.
    if allocated:
        source.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote allocated IDs back to {source}: {', '.join(allocated)}")

    for name in SHEETS:
        ids = added.get(name, [])
        if ids:
            print(f"{name}: added {len(ids)} ({', '.join(ids)})")
    if skipped:
        print(f"already present, left untouched: {', '.join(sorted(set(skipped)))}")
    if not added:
        print("nothing new to add")
    print(f"saved {output}")
    return 0


def command_status(entry_id: str, status: str, output: Path) -> int:
    """Set one row's status, stamp the date, and grey the row out if it is closed."""
    entry_id = entry_id.strip().upper()
    name = sheet_for(entry_id)
    if name is None:
        print(f"error: cannot tell which sheet {entry_id} belongs to")
        return 1

    if not output.exists():
        print(f"error: workbook does not exist: {output}")
        return 1

    workbook = load_workbook(output)
    if name not in workbook.sheetnames:
        print(f"error: workbook has no {name} sheet")
        return 1

    sheet = ensure_sheet(workbook, name, SHEETS[name])
    row_number = existing_ids(sheet).get(entry_id)
    if row_number is None:
        print(f"error: {entry_id} is not in the {name} sheet")
        return 1

    allowed = STATUSES[name]
    match = [value for value in allowed if value.lower() == status.strip().lower()]
    if not match:
        print(f"error: {name} status must be one of: {', '.join(allowed)}")
        return 1
    status = match[0]

    header = header_of(sheet)
    sheet.cell(row=row_number, column=header.index("Status") + 1, value=status)
    sheet.cell(
        row=row_number,
        column=header.index("Updated") + 1,
        value=today(),
    )
    style_row(sheet, row_number, closed=status in CLOSED_STATUSES)

    workbook.save(output)
    print(f"{entry_id}: {status}")
    return 0


def usage() -> int:
    """Print how to call the script, including the default workbook location."""
    name = Path(sys.argv[0]).name
    print(f"usage: {name} append <entries.json> [workbook.xlsx]")
    print(f"       {name} status <ID> <status> [workbook.xlsx]")
    print(f"default workbook: {DEFAULT_WORKBOOK}")
    for sheet, values in STATUSES.items():
        print(f"  {sheet} statuses: {', '.join(values)}")
    return 2


def main() -> int:
    """Dispatch to the append or status command."""
    args = sys.argv[1:]
    if not args:
        return usage()

    command, rest = args[0], args[1:]

    if command == "append" and len(rest) in {1, 2}:
        output = Path(rest[1]) if len(rest) == 2 else DEFAULT_WORKBOOK
        if not output.parent.is_dir():
            print(f"error: output folder does not exist: {output.parent}")
            return 1
        return command_append(Path(rest[0]), output)

    if command == "status" and len(rest) in {2, 3}:
        output = Path(rest[2]) if len(rest) == 3 else DEFAULT_WORKBOOK
        return command_status(rest[0], rest[1], output)

    return usage()


if __name__ == "__main__":
    raise SystemExit(main())
