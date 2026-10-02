"""Summarise the first 20 IAG 1502000 claim reports for landslide mentions.

Reads ``claims-report-paths-iag-1502000.csv`` (built by
``find_iag_1502000_final_reports.py``), fetches each report's docx from T:
through ``tdrive_sync`` (caching it locally), and pulls out of the report
text:

- the claim type and site address, both read off the fixed line the T+T claim
  report template carries just below its "Claim for Natural Disaster (...)
  Damage" heading, e.g. "A Person, 1 Example Road, Suburb";
- whether the report mentions landslide/landslip damage at all;
- whether it goes on to describe an evacuated and/or an inundated land
  extent, the two ways NHC settles landslide land damage, and the area (and,
  where the report gives one, the volume) of each;
- whether a retaining wall is reported damaged and/or undamaged.

The area/volume and retaining wall figures are read off the "Property damage"
table most reports carry, which lists an "Area of insured land damaged:"
block ("Evacuated:"/"Inundated:" each followed by an "N m2", sometimes with an
"(N m3)" volume alongside), and, where a wall is present, a
"Damaged: (insured face area)" figure per retaining wall. This is a
best-effort parse of a template that varies between report writers and
years -- a handful of multi-hazard or multi-location reports mix figures from
more than one damage area, and any field the parse can't find is left blank
rather than guessed at.

Run:

    uv run --frozen python src/scripts/landloss/vul/static_data_gen/gen_iag_1502000_landslide_claims_summary.py

Reads only the first REPORT_COUNT rows of the source CSV -- this is a first
look at how common each flag is across the claims book, not a full run.
Results are saved to claims-landslide-summary-iag-1502000.csv.
"""

import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import tdrive_sync as ts
from scripts.landloss import paths

REPORT_COUNT = 20

# The docx WordprocessingML namespace, unqualified paragraph/text/body tags are
# read against below.
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# The template heading every claim report opens with, right before the line
# carrying the customer's name and the site address.
CLAIM_TYPE_PATTERN = re.compile(r"^claim for natural disaster", re.IGNORECASE)

# The "Property damage" table's own headings, in document order: the primary
# land-damage block starts here and ends at whichever of the "at imminent
# risk"/"main access way" headings comes next.
LAND_DAMAGED_HEADING = re.compile(
    r"^(?:insured )?area of insured land damaged\s*:?\s*$", re.IGNORECASE
)
LAND_DAMAGE_BLOCK_END = re.compile(
    r"^(?:insured )?area of insured land at imminent risk|^main access way",
    re.IGNORECASE,
)
AREA_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*m[²2]", re.IGNORECASE)
VOLUME_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*m[³3]", re.IGNORECASE)

# The per-wall damage figure in the retaining wall table, e.g.
# "Damaged: (insured face area): 6.0 m2" (or "Nil" for an undamaged wall).
RETAINING_WALL_DAMAGED_AREA = re.compile(
    r"damaged:?\s*\(insured face area\):?\s*([\d.]+|nil)", re.IGNORECASE
)
# Narrative fallbacks for reports where a wall isn't in the formal table.
RETAINING_WALL_DAMAGED_NARRATIVE = re.compile(
    r"(collapse|rotat\w*|undermin\w*)[^.]{0,80}retaining wall"
    r"|retaining wall[^.]{0,80}(collapse|rotat\w*|undermin\w*)",
    re.IGNORECASE,
)
RETAINING_WALL_UNDAMAGED_NARRATIVE = re.compile(
    r"no damage[^.]{0,80}retaining wall"
    r"|retaining wall[^.]{0,80}(?:no damage|not damaged|undamaged)",
    re.IGNORECASE,
)


def _area_or_nil(text: str) -> float | None:
    """Return the first "N m2" figure in text, or 0.0 for a "Nil" extent."""
    match = AREA_PATTERN.search(text)
    if match:
        return float(match.group(1))
    return 0.0 if re.search(r"\bnil\b", text, re.IGNORECASE) else None


def extract_land_damage(paragraphs: list[str]) -> dict[str, float | None]:
    """Read the evacuated/inundated area and volume off the damage table.

    Looks only at the report's primary "Area of insured land damaged:" block,
    not any secondary "main access way" block a report may also carry.
    """
    block: list[str] = []
    in_block = False
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if in_block:
            if LAND_DAMAGE_BLOCK_END.match(stripped):
                break
            block.append(stripped)
        elif LAND_DAMAGED_HEADING.match(stripped):
            in_block = True

    evacuated_area = inundated_area = inundated_volume = None
    for index, line in enumerate(block):
        window = " ".join(block[index : index + 3])
        if line.lower().startswith("evacuated"):
            evacuated_area = _area_or_nil(window)
        elif line.lower().startswith("inundated"):
            inundated_area = _area_or_nil(window)
            volume_match = VOLUME_PATTERN.search(window)
            inundated_volume = float(volume_match.group(1)) if volume_match else None

    total_area = (
        evacuated_area + inundated_area
        if evacuated_area is not None and inundated_area is not None
        else None
    )
    return {
        "evacuated_land_area_m2": evacuated_area,
        "inundated_land_area_m2": inundated_area,
        "inundated_land_volume_m3": inundated_volume,
        "total_damaged_land_area_m2": total_area,
    }


def extract_retaining_wall_flags(full_text: str) -> dict[str, bool]:
    """Flag whether the report records a damaged and/or an undamaged wall."""
    damaged_areas = [
        0.0 if value.lower() == "nil" else float(value)
        for value in RETAINING_WALL_DAMAGED_AREA.findall(full_text)
    ]
    return {
        "mentions_damaged_retaining_wall": any(area > 0 for area in damaged_areas)
        or bool(RETAINING_WALL_DAMAGED_NARRATIVE.search(full_text)),
        "mentions_undamaged_retaining_wall": any(area == 0 for area in damaged_areas)
        or bool(RETAINING_WALL_UNDAMAGED_NARRATIVE.search(full_text)),
    }


def read_paragraphs(path: Path) -> list[str]:
    """Return a docx's paragraph text, in document order, empty ones dropped."""
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    # Our own claim reports, not untrusted input -- stdlib ElementTree is fine.
    body = ET.fromstring(document_xml).find(f"{W_NS}body")  # noqa: S314
    paragraphs = [
        "".join(run.text or "" for run in paragraph.iter(f"{W_NS}t"))
        for paragraph in body.iter(f"{W_NS}p")
    ]
    return [text for text in paragraphs if text.strip()]


def summarise_report(paragraphs: list[str]) -> dict[str, str | bool]:
    """Pull the claim type, address and landslide/extent flags out of a report."""
    full_text = "\n".join(paragraphs).lower()

    claim_type = ""
    address = ""
    for index, paragraph in enumerate(paragraphs):
        if CLAIM_TYPE_PATTERN.match(paragraph.strip()):
            claim_type = paragraph.strip()
            if index + 1 < len(paragraphs):
                address = paragraphs[index + 1].strip()
            break

    return {
        "claim_type": claim_type,
        "address": address,
        "has_landslide": "landslide" in full_text or "landslip" in full_text,
        "mentions_evacuated_extent": "evacuat" in full_text,
        "mentions_inundated_extent": "inundat" in full_text,
        **extract_land_damage(paragraphs),
        **extract_retaining_wall_flags(full_text),
    }


def main() -> int:
    with paths.IAG_1502000_REPORT_PATHS_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[:REPORT_COUNT]

    summaries = []
    for row in rows:
        print(f"{row['subproject']}: caching and reading report")
        local_path = ts.get_cached(Path(row["report_path"]))
        summary = summarise_report(read_paragraphs(local_path))
        summaries.append(
            {
                "project_number": row["project_number"],
                "subproject_number": row["subproject_number"],
                **summary,
                "report_path": row["report_path"],
            }
        )

    paths.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    with paths.IAG_1502000_LANDSLIDE_SUMMARY_CSV.open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    landslide_count = sum(1 for summary in summaries if summary["has_landslide"])
    evacuated_count = sum(
        1 for summary in summaries if summary["mentions_evacuated_extent"]
    )
    inundated_count = sum(
        1 for summary in summaries if summary["mentions_inundated_extent"]
    )
    damaged_wall_count = sum(
        1 for summary in summaries if summary["mentions_damaged_retaining_wall"]
    )
    undamaged_wall_count = sum(
        1 for summary in summaries if summary["mentions_undamaged_retaining_wall"]
    )
    print(f"Wrote {len(summaries)} rows to {paths.IAG_1502000_LANDSLIDE_SUMMARY_CSV}")
    print(f"{landslide_count}/{len(summaries)} mention landslide/landslip")
    print(f"{evacuated_count}/{len(summaries)} mention an evacuated extent")
    print(f"{inundated_count}/{len(summaries)} mention an inundated extent")
    print(f"{damaged_wall_count}/{len(summaries)} mention a damaged retaining wall")
    print(
        f"{undamaged_wall_count}/{len(summaries)} mention an undamaged retaining wall"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
