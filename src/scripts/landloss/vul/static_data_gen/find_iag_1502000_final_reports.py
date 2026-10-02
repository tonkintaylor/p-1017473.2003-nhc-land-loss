"""Find the final issued report docx for each IAG subproject.

For every subproject folder under
\\\\ttgroup.local\\corporate\\Auckland\\Projects\\1502000, this looks under
IssuedDocuments (recursively, e.g. "Final Report" or "Draft Report"
subfolders) for files that are .docx and have "report" in the filename, and
picks the most recently modified one as that subproject's final report.

Run:

    uv run --frozen python src/scripts/landloss/vul/find_iag_1502000_final_reports.py

Results are saved to
src/scripts/landloss/vul/assets/claims-report-paths-iag-1502000.csv
"""

from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

BASE_PATH = Path(r"\\ttgroup.local\corporate\Auckland\Projects\1502000")
OUTPUT_PATH = Path(__file__).parent / "assets" / "claims-report-paths-iag-1502000.csv"

# Subproject folders are named "<project number>.<subproject number>", e.g.
# "1502000.2575" (sometimes with a trailing suffix such as " SUPERSEDED").
SUBPROJECT_PATTERN = re.compile(r"^(\d+)\.(\d+)")


def find_final_report(subproject_dir: Path) -> tuple[Path, datetime] | None:
    """Return the most recently modified report docx under IssuedDocuments, if any."""
    issued_documents_dir = subproject_dir / "IssuedDocuments"
    try:
        if not issued_documents_dir.is_dir():
            return None

        candidates = [
            path
            for path in issued_documents_dir.rglob("*.docx")
            if "report" in path.name.lower() and not path.name.startswith("~$")
        ]
        if not candidates:
            return None

        best = max(candidates, key=lambda path: path.stat().st_mtime)
        return best, datetime.fromtimestamp(best.stat().st_mtime, tz=UTC)
    except OSError as exc:
        print(f"  skipping {subproject_dir.name}: {exc}")
        return None


def process_subproject(subproject_dir: Path) -> dict[str, str] | None:
    """Build the CSV row for one subproject, or None if it has no report."""
    match = SUBPROJECT_PATTERN.match(subproject_dir.name)
    if match is None:
        return None
    project_number, subproject_number = match.groups()

    result = find_final_report(subproject_dir)
    if result is None:
        return None
    report_path, last_modified = result

    return {
        "project_number": project_number,
        "subproject_number": subproject_number,
        "subproject": subproject_dir.name,
        "report_path": str(report_path),
        "last_modified": last_modified.strftime("%Y-%m-%d"),
    }


def main() -> int:
    subproject_dirs = sorted(path for path in BASE_PATH.iterdir() if path.is_dir())
    print(f"Found {len(subproject_dirs)} subproject directories under {BASE_PATH}")

    rows = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {
            executor.submit(process_subproject, subproject_dir): subproject_dir
            for subproject_dir in subproject_dirs
        }
        for count, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            if row is not None:
                rows.append(row)
            if count % 200 == 0:
                print(f"  processed {count}/{len(subproject_dirs)}")

    rows.sort(key=lambda row: (row["project_number"], row["subproject_number"]))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_number",
                "subproject_number",
                "subproject",
                "report_path",
                "last_modified",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
