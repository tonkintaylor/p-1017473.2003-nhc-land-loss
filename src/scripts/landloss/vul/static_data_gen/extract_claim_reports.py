"""Read the figures out of the claim reports that step one fetched.

    uv run --frozen python src/scripts/landloss/vul/static_data_gen/extract_claim_reports.py
    uv run --frozen python src/scripts/landloss/vul/static_data_gen/extract_claim_reports.py --project 1502000
    uv run --frozen python src/scripts/landloss/vul/static_data_gen/extract_claim_reports.py --claims-list kaikoura-2016

**Step two of two.** Runs against the local copies ``fetch_claim_reports.py``
cached and never touches T:, so it can be rerun as often as the fields change.

**The Summary of Information table is the source.** Every recent T+T claim
report closes with it, in a consistent layout: whether the damage is natural
disaster damage, the evacuated and inundated land, the land at imminent risk
(additional evacuation, new inundation and re-inundation), the main access way,
and one block per retaining wall giving its whole length, retained height and
its damaged, imminently damaged, insured and total face areas. It is read row
by row as label and value, so a row it does not recognise is skipped rather
than breaking the rows after it.

A few things sit outside that table and are read where the report has them:

- the header -- job number, report date, addressee, claim type, site address
  and insurer claim number;
- the inspection date and the sentence saying which event the claim relates
  to, which is how the 2013 Seddon and 2016 Kaikoura reports will be told
  apart once they are fetched;
- the **construction issues table**, whose easy, moderate or hard ticks for
  construction access, earthworks and constructability are the costing tool's
  own site ratings (Q-10, T-40);
- the design and consent cost total, the width of the landslip, the damaged
  length of each wall as the property damage bullets give it, and the debris
  volume the remedial works remove.

**Nothing found is left blank, never guessed.** "Nil" reads as zero and "N/A"
as blank, and each report's ``missing`` column names the summary fields it
could not find, so a template that has drifted shows up as a column of gaps
rather than as plausible-looking zeros.

Writes three CSVs beside the step-one index, in
``src/landloss/common/assets/claim_reports/<project>/``:

- ``reports.csv`` -- one row per report;
- ``walls.csv`` -- one row per retaining wall in the summary table;
- ``remedial_walls.csv`` -- one row per wall the conceptual remedial works
  propose, which is what the replacement is sized at.
"""

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from scripts.landloss.paths import CLAIM_REPORTS_EXTRACTED_DIR, REPO_ROOT
from scripts.landloss.vul.static_data_gen.fetch_claim_reports import (
    DEFAULT_PROJECT,
    FETCHED,
    IndexRow,
    claims_list_path,
    index_path,
    read_index,
    wanted_by_programme,
)

# Where a claims list's extraction is written, one folder per list.
EXTRACTED_DIR = CLAIM_REPORTS_EXTRACTED_DIR

# The claims list's own columns carried onto each report row, by the name they
# take there.
LIST_COLUMNS = {
    "programme": "programme",
    "list_start_date": "start_date",
    "lon": "lon",
    "lat": "lat",
    "ta_name": "ta_name",
    "in_study_area": "in_study_area",
    "name_event_hint": "name_event_hint",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

REPORTS_NAME = "reports.csv"
WALLS_NAME = "walls.csv"
REMEDIAL_WALLS_NAME = "remedial_walls.csv"

# A tick in a Word check-box content control, or typed in by hand.
TICKED = {"☒", "☑", "✓", "✔", "x", "X"}

NUMBER = r"(\d+(?:\.\d+)?)"
AREA = re.compile(NUMBER + r"\s*m\s*[²2]", re.IGNORECASE)
VOLUME = re.compile(NUMBER + r"\s*m\s*[³3]", re.IGNORECASE)
LENGTH = re.compile(NUMBER + r"\s*m\b(?!\s*[²³23])", re.IGNORECASE)
MONEY = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
DATE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)?\s*((?:19|20)\d{2})\b",
    re.IGNORECASE,
)

# "Job No: 1502000.0005" (2016 on) or "T&T Ref : 85651.0043" (2013).
JOB_NUMBER = re.compile(r"^(?:job no\.?|t[&+]t ref)\s*:?\s*(\S+)", re.IGNORECASE)
# "Claim for Natural Disaster (Landslip) Damage", or without the brackets:
# "Claim for Natural Disaster Landslip Damage".
# The NHI Act template says "Natural Hazard" where the EQC Act ones say
# "Natural Disaster"; a structural report is headed "… Structural Assessment".
CLAIM_HEADING = re.compile(
    r"^claim for natural (?:disaster|hazard)\s*\(?\s*([^)]*?)\s*\)?\s*"
    r"(damage|structural assessment)\b",
    re.IGNORECASE,
)
# Where a site address starts: a street number, or a unit, flat or lot.
ADDRESS_START = re.compile(
    r"^(?:\d|(?:unit|units|flat|apartment|apt|lot)\b)", re.IGNORECASE
)
# A claim number standing alone on the line after the address: "P034050981".
BARE_CLAIM_NUMBER = re.compile(r"^[A-Z]{1,4}\d{6,}$")
# "Insurer claim number: C3781361" (2021) or "EQC Ref: 2016/016708" (2016).
CLAIM_NUMBER = re.compile(
    r"(?:claim (?:number|no\.?|ref(?:erence)?)|eqc ref(?:erence)?)\s*:?\s*(\S+)",
    re.IGNORECASE,
)
INSPECTED = re.compile(
    r"inspected the (?:subject )?(?:property|site) on (\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE,
)
# The sentence naming the event: "This claim relates to a rain event that
# occurred in July 2021" (2021), or "The landslip is believed to have occurred
# as a result of heavy rainfall events in mid-October 2016" (2016).
EVENT = re.compile(
    r"[^.]*\b(?:claim relates to|believed to have (?:occurred|been caused)|"
    r"occurred as a result of|(?:was|were) (?:triggered|caused) by)\b[^.]*\.",
    re.IGNORECASE,
)
# What the event sentence says caused it. Earthquake is tested first, so "a
# landslip caused by the earthquake and subsequent rain" reads as earthquake.
EVENT_CAUSES = {
    "earthquake": re.compile(
        r"earthquake|seismic|kaik[oō]ura|seddon|cook strait", re.IGNORECASE
    ),
    "rain": re.compile(r"rain|storm|weather|cyclone|flood", re.IGNORECASE),
}
LANDSLIP_WIDTH = re.compile(
    NUMBER + r"\s*m wide (?:landslip|landslide|slip)", re.IGNORECASE
)
# "Collapse to 3.4 m length of RTW 1" (2021), "Rotation to a 4 m section of
# RTW1" (Nelson 2016), "Rotation of a 2.0 m wide section of Retaining wall 1"
# (2013).
WALL_DAMAGE = re.compile(
    r"\b(collapse|damage|rotation|displacement|cracking|deflection|failure)\w*\s+"
    r"(?:to|of)\s+(?:a\s+)?" + NUMBER + r"\s*m\s+(?:(?:wide|long)\s+)?"
    r"(?:(?:length|section)\s+)?of\s+(?:rtw|retaining wall)\s*(\d+)",
    re.IGNORECASE,
)
DEBRIS = re.compile(r"est\.?\s*" + NUMBER + r"\s*m\s*[³3]", re.IGNORECASE)
ACTS = {
    "Earthquake Commission Act 1993": "EQC Act",
    "Natural Hazards Insurance Act 2023": "NHI Act",
}

# The summary table's section headings, in the order the template gives them.
# "Summary of Information" (2016 on) or "Summary Information (all costs excl
# GST)" (2013).
# … or "Summary of damage information" (NHI Act).
SUMMARY_HEADING = re.compile(r"^summary (?:of )?(?:damage )?information", re.IGNORECASE)
# "Area of insured land damaged" (2021) or "Area of Land damaged" (2016).
LAND_DAMAGED = re.compile(r"area of (?:insured )?land damaged", re.IGNORECASE)
# "… at imminent risk" (EQC Act) or "… subject to imminent damage" (NHI Act).
LAND_IMMINENT = re.compile(
    r"land (?:at imminent risk|subject to imminent damage)", re.IGNORECASE
)
ACCESS_WAY = re.compile(r"^main access ?way", re.IGNORECASE)
WALLS_SECTION = re.compile(r"^retaining walls? (?:supporting|within)", re.IGNORECASE)
# "Retaining wall 1 – Timber pole…" (2021) or "RTW 2 – Red brick…" (2016).
WALL_START = re.compile(
    r"^(?:retaining wall|rtw)\s*(\d+)\s*[–—-]?\s*(.*?):?\s*$", re.IGNORECASE
)
# A wall block with no number, as the Nelson office wrote them: "Timber Pole
# retaining wall – 200 mm dia poles at 2m centres:". Recognised only inside the
# walls section, as a heading row with nothing in its value cell.
UNNUMBERED_WALL = re.compile(r"retaining wall.*:\s*$", re.IGNORECASE)
DWELLING = re.compile(r"^dwelling (?:and|&) appurtenant", re.IGNORECASE)
SERVICES = re.compile(r"^services within", re.IGNORECASE)
CROSSINGS = re.compile(r"^bridges? or culverts?", re.IGNORECASE)
NATURAL_DISASTER = re.compile(
    r"^is this natural (?:disaster|hazard) damage", re.IGNORECASE
)
REMEDIAL = re.compile(r"^(?:conceptual remedial works|remedial option)", re.IGNORECASE)
REMEDIAL_HEADING = r"^(?:conceptual|potential|proposed) remedial works"
NOTE = re.compile(r"^note\s*:", re.IGNORECASE)

RATING_ROWS = {
    "construction access": "construction_access",
    "earthworks required": "earthworks_required",
    "constructability/reinstatement": "constructability_reinstatement",
}
RATING_CODES = {
    "easy": "E",
    "moderate": "M",
    "hard": "D",
    "difficult": "D",
    "n/a": "NA",
}

# The remedial works' own wall specification, one block per wall.
# "construct a timber pole retaining wall", or, where one sentence covers
# several walls, "constructing three cantilevered timber pole retaining walls
# as follows:" -- in which case each wall then gets its own labelled block.
REMEDIAL_WALL = re.compile(
    r"construct(?:ing)? (an?|two|three|four|five|six|\d+) (.+?) retaining walls?\b",
    re.IGNORECASE,
)
# The label heading each of those blocks: "Landslip 1 / Retaining wall A:".
REMEDIAL_LABEL = re.compile(
    r"^(?:landslip\s*\d+\s*/\s*)?retaining wall\s+([a-z0-9]+)\s*:?\s*$", re.IGNORECASE
)
# A retained height in a wall heading: "…; up to 800 mm retained height".
HEADING_HEIGHT = re.compile(
    r"(?:up to\s+)?" + NUMBER + r"\s*(mm|m)\s+retained height", re.IGNORECASE
)
# "replacing the damaged section of RTW1 as follows:", where the construction
# comes on the next line: "4 m long Type II 190 mm block masonry wall".
REMEDIAL_REPLACE = re.compile(
    r"replac(?:e|ing) the damaged (?:section of )?(rtw\s*\d+)", re.IGNORECASE
)
LONG_WALL_TYPE = re.compile(NUMBER + r"\s*m\s+long\s+(.+?)\s+wall\b", re.IGNORECASE)
# Dimensions written into the construct phrase, lifted out of the construction.
INLINE_LONG = re.compile(NUMBER + r"\s*m\s+long\b,?", re.IGNORECASE)
INLINE_HIGH = re.compile(NUMBER + r"\s*m\s+(?:high|tall)\b,?", re.IGNORECASE)
REMEDIAL_FOR = re.compile(r"rtw\s*(\d+(?:\s*(?:\+|and|&)\s*rtw\s*\d+)*)", re.IGNORECASE)
# Spacing is loose in the older reports: "1 m  maximum retained height".
LONG_WALL = re.compile(NUMBER + r"\s*m\s+long wall", re.IGNORECASE)
# In metres, or in millimetres in the 2013 reports: "800 mm  maximum retained
# height".
MAX_HEIGHT = re.compile(NUMBER + r"\s*(mm|m)\s+maximum retained height", re.IGNORECASE)
# "200 mm SED" or "200 mm diameter SED".
SED = re.compile(r"(\d+)\s*mm\s+(?:dia(?:meter)?\.?\s+)?sed", re.IGNORECASE)
# The estimate total, per wall in the 2013 reports: "TOTAL (Excluding GST)".
ESTIMATE_TOTAL = re.compile(r"^total\s*\(excl", re.IGNORECASE)
EMBEDMENT = re.compile(r"embedment\s*" + NUMBER + r"\s*m", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Reading the document.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Block:
    """A paragraph, or a table row as its cells, in document order."""

    text: str
    cells: tuple[str, ...] = ()

    @property
    def is_row(self) -> bool:
        """Whether this is a table row rather than a paragraph."""
        return bool(self.cells)


def _text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def read_blocks(path: Path) -> list[Block]:
    """Return a docx's paragraphs and table rows, in order.

    A row's cells are found at any depth, because a check-box content control
    wraps its cell and hides it from a search of the row's direct children --
    which is how the construction issues ticks first read as blank.

    Args:
        path: The ``.docx``.

    Returns:
        The blocks. Empty paragraphs are dropped.
    """
    # Step one caches only the report's text, word/document.xml, as a
    # ".document.xml" file; a whole .docx is still read from inside its zip.
    # The reports are T+T's own, copied from the T: drive, so they are trusted.
    if path.name.lower().endswith(".xml"):
        # Word's own document part, from T+T's own reports: not untrusted input.
        root = ET.fromstring(path.read_bytes())  # noqa: S314
    else:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))  # noqa: S314
    body = root.find(W + "body")
    blocks: list[Block] = []
    for element in body if body is not None else []:
        if element.tag == W + "p":
            text = _text(element)
            if text:
                blocks.append(Block(text))
        elif element.tag == W + "tbl":
            for row in element.iter(W + "tr"):
                cells = tuple(_text(cell) for cell in row.iter(W + "tc"))
                if any(cells):
                    blocks.append(Block(" | ".join(cells), cells))
    return blocks


# ---------------------------------------------------------------------------
# Values.
# ---------------------------------------------------------------------------


def area(text: str) -> float | None:
    """Return the first area in ``text``: "Nil" is zero, "N/A" is blank."""
    if match := AREA.search(text):
        return float(match.group(1))
    return 0.0 if re.search(r"\bnil\b", text, re.IGNORECASE) else None


def length(text: str) -> float | None:
    """Return the first length in metres in ``text``, or blank."""
    match = LENGTH.search(text)
    return float(match.group(1)) if match else None


def metres(number: str, unit: str) -> float:
    """Return a length in metres from a number and "m" or "mm"."""
    return float(number) / (1000.0 if unit.lower() == "mm" else 1.0)


def area_across(cells: tuple[str, ...]) -> float | None:
    """Return the areas in a row's value cells, summed.

    A 2013 report gives one column per landslip -- "Evacuated: | 1 m2 | 2 m2 |
    1 m2" -- and the claim's area is their sum. A later report has a single
    value cell, which this reads the same as :func:`area`. "Nil" counts as
    zero, and so is "N/A", which in an area row means there is none of that
    kind of land; a cell with no area in it ("Included above") is skipped.
    """
    values = [
        0.0 if re.match(r"^\s*n/?a\b", cell, re.IGNORECASE) else area(cell)
        for cell in cells
        if cell.strip()
    ]
    known = [number for number in values if number is not None]
    return round(sum(known), 3) if known else None


def max_length(text: str) -> float | None:
    """Return the largest length in ``text``: "0.5 m to 1.5 m" reads as 1.5.

    A wall whose retained height varies along its run is charged on its
    tallest section, which is what the replacement has to retain.
    """
    lengths = [float(found) for found in LENGTH.findall(text)]
    return max(lengths) if lengths else None


def volume(text: str) -> float | None:
    """Return the first volume in cubic metres in ``text``, or blank."""
    match = VOLUME.search(text)
    return float(match.group(1)) if match else None


def money(text: str) -> float | None:
    """Return the first dollar figure in ``text``, or blank."""
    match = MONEY.search(text)
    return float(match.group(1).replace(",", "")) if match else None


def label(block: Block) -> str:
    """Return a row's first cell, or a paragraph's text."""
    return block.cells[0] if block.is_row else block.text


def value(block: Block) -> str:
    """Return a row's cells after the first, joined."""
    return " ".join(cell for cell in block.cells[1:] if cell).strip()


# ---------------------------------------------------------------------------
# The Summary of Information table.
# ---------------------------------------------------------------------------


@dataclass
class Wall:
    """One retaining wall as the summary table describes it."""

    wall_number: int
    description: str
    construction: str = ""
    whole_length_m: float | None = None
    retained_height_m: float | None = None
    retained_height_text: str = ""
    damaged_face_m2: float | None = None
    imminent_face_m2: float | None = None
    insured_face_m2: float | None = None
    total_face_m2: float | None = None
    damaged_length_m: float | None = None
    collapsed_length_m: float | None = None
    damaged_length_from_face_m: float | None = None


WALL_ROWS = {
    re.compile(r"^whole wall length", re.IGNORECASE): ("whole_length_m", length),
    re.compile(r"^retained height", re.IGNORECASE): ("retained_height_m", max_length),
    re.compile(r"^damaged\b", re.IGNORECASE): ("damaged_face_m2", area),
    re.compile(r"^(?:imminent damage|at imminent risk)", re.IGNORECASE): (
        "imminent_face_m2",
        area,
    ),
    re.compile(r"^insured\b", re.IGNORECASE): ("insured_face_m2", area),
    re.compile(r"^total wall", re.IGNORECASE): ("total_face_m2", area),
}


@dataclass
class Summary:
    """What the Summary of Information table says."""

    found: bool = False
    natural_disaster: str = ""
    evacuated_m2: float | None = None
    inundated_m2: float | None = None
    imminent_evacuation_m2: float | None = None
    imminent_new_inundation_m2: float | None = None
    imminent_reinundation_m2: float | None = None
    inundated_volume_m3: float | None = None
    access_evacuated_m2: float | None = None
    access_inundated_m2: float | None = None
    access_imminent_evacuation_m2: float | None = None
    access_imminent_new_inundation_m2: float | None = None
    access_imminent_reinundation_m2: float | None = None
    main_access_way: str = ""
    # The land-area fields whose row appeared in the table, read or not.
    seen: set[str] = field(default_factory=set)
    # Value columns in the land-area rows: one per landslip in a 2013 report,
    # one per inspection in a report revised after reinspection.
    summary_columns: int = 0
    dwelling: str = ""
    services: str = ""
    bridges_culverts: str = ""
    remedial_works: str = ""
    notes: str = ""
    walls: list[Wall] = field(default_factory=list)


def summary_rows(blocks: list[Block]) -> list[Block]:
    """Return the table rows from the Summary of Information heading on.

    The table ends where the rows do: the first paragraph after the heading
    that is not a row, once at least one row has been seen.
    """
    start = next(
        (i for i, block in enumerate(blocks) if SUMMARY_HEADING.match(block.text)),
        None,
    )
    if start is None:
        return []
    rows: list[Block] = []
    for block in blocks[start + 1 :]:
        if block.is_row:
            rows.append(block)
        elif rows:
            break
    return rows


def summary_notes(blocks: list[Block]) -> str:
    """Return the "Note:" paragraphs straight after the summary table.

    They carry what the table cannot: that a wall is shared with a neighbour
    and its damage split between two claims, for one.
    """
    start = next(
        (i for i, block in enumerate(blocks) if SUMMARY_HEADING.match(block.text)),
        None,
    )
    if start is None:
        return ""
    notes: list[str] = []
    seen_rows = False
    for block in blocks[start + 1 :]:
        if block.is_row:
            seen_rows = True
            continue
        if not seen_rows:
            continue
        if NOTE.match(block.text):
            notes.append(block.text)
        else:
            break
    return " ".join(notes)


# The land-area rows each section of the summary carries, and the field each
# fills. The 2013 template has a single imminent "Inundation:" row, of land not
# yet buried, which is what the later "New inundation" means.
_IMMINENT_ROWS = (
    (r"^evacuat", "imminent_evacuation_m2"),
    (r"^re-?inundat", "imminent_reinundation_m2"),
    (r"^(?:new )?inundat", "imminent_new_inundation_m2"),
)
LAND_SECTIONS = {
    "damaged": ((r"^evacuat", "evacuated_m2"), (r"^inundat", "inundated_m2")),
    "imminent": _IMMINENT_ROWS,
    "access_damaged": (
        (r"^evacuat", "access_evacuated_m2"),
        (r"^inundat", "access_inundated_m2"),
    ),
    "access_imminent": tuple(
        (pattern, "access_" + field_name) for pattern, field_name in _IMMINENT_ROWS
    ),
}


def _heading(summary: Summary, name: str, text: str, section: str) -> str | None:
    """Return the section a heading row opens, or ``None`` if it is not one.

    The main access way can carry its own damaged and imminent blocks, whose
    rows must not overwrite the claim's own ("Evacuation: Included in areas
    above"), so its headings are told apart from the claim's.
    """
    if NATURAL_DISASTER.match(name):
        summary.natural_disaster = text
        return section
    access = bool(re.search(r"main access", name, re.IGNORECASE))
    opened: str | None = None
    if LAND_DAMAGED.search(name):
        opened = "access_damaged" if access else "damaged"
    elif LAND_IMMINENT.search(name):
        opened = "access_imminent" if access else "imminent"
    elif ACCESS_WAY.match(name):
        summary.main_access_way = text
        opened = "access"
    elif WALLS_SECTION.match(name):
        opened = "walls"
    elif REMEDIAL.match(name):
        opened = "remedial"
    else:
        for pattern, attribute in (
            (DWELLING, "dwelling"),
            (SERVICES, "services"),
            (CROSSINGS, "bridges_culverts"),
        ):
            if pattern.match(name):
                setattr(summary, attribute, text)
                opened = ""
                break
    return opened


def _new_wall(summary: Summary, name: str, text: str, section: str) -> Wall | None:
    """Return the wall a row opens a block for, or ``None`` if it opens none."""
    if match := WALL_START.match(name):
        # "Retaining Wall 1 (RTW1) – Cement mortar boulder wall": the bracketed
        # label repeats the number, so it is dropped before the construction
        # is read off.
        number = int(match.group(1))
        description = re.sub(
            r"^\(rtw\s*\d+\)\s*[–—-]?\s*",
            "",
            match.group(2).strip(),
            flags=re.IGNORECASE,
        )
    elif section == "walls" and not text and UNNUMBERED_WALL.search(name):
        # Numbered in order, so a single unnumbered wall is RTW 1 -- which is
        # how the damage bullets of those reports refer to it.
        number, description = len(summary.walls) + 1, name.rstrip(":").strip()
    else:
        return None
    return Wall(
        wall_number=number,
        description=description,
        construction=description.split("–")[0].split(" - ")[0].strip(),
    )


def _read_wall_row(wall: Wall, name: str, row: Block, text: str) -> None:
    """Fill the wall attribute a row inside a wall block carries."""
    for pattern, (attribute, parse) in WALL_ROWS.items():
        if pattern.match(name):
            setattr(
                wall,
                attribute,
                area_across(row.cells[1:]) if parse is area else parse(text),
            )
            if attribute == "retained_height_m":
                wall.retained_height_text = text
            return


def _read_land_row(summary: Summary, section: str, name: str, row: Block) -> None:
    """Fill the land area a row inside a land section carries."""
    for pattern, field_name in LAND_SECTIONS[section]:
        if re.match(pattern, name, re.IGNORECASE):
            setattr(summary, field_name, area_across(row.cells[1:]))
            summary.seen.add(field_name)
            if field_name == "inundated_m2":
                # "5 m2 / 3 m3": the NHI Act template gives the volume too.
                volumes = [
                    float(found.group(1))
                    for cell in row.cells[1:]
                    if (found := VOLUME.search(cell))
                ]
                summary.inundated_volume_m3 = sum(volumes) if volumes else None
            summary.summary_columns = max(summary.summary_columns, len(row.cells) - 1)
            return


def _has_figures(wall: Wall) -> bool:
    """Return whether a wall block carries any figure at all."""
    return any(
        getattr(wall, attribute) is not None for attribute, _ in WALL_ROWS.values()
    ) or bool(HEADING_HEIGHT.search(wall.description))


def _later_walls(blocks: list[Block], summary_row_count: int) -> list[Wall]:
    """Return the wall blocks in the tables after the summary table.

    The NHI Act template lists its retaining walls in a table of their own
    after the summary ("Refer to retaining wall summary information below"),
    with the same rows as a wall block inside the summary. Only a numbered
    "Retaining Wall N" heading opens a block here, so nothing else in those
    later tables -- ratings, costs, photograph captions -- is taken for a wall.
    """
    start = next(
        (i for i, block in enumerate(blocks) if SUMMARY_HEADING.match(block.text)),
        None,
    )
    if start is None:
        return []
    later = [block for block in blocks[start + 1 :] if block.is_row]
    walls: list[Wall] = []
    wall: Wall | None = None
    for row in later[summary_row_count:]:
        name, text = label(row).strip(), value(row)
        if WALL_START.match(name):
            wall = _new_wall(Summary(), name, text, "")
            walls.append(wall)
        elif wall is not None:
            _read_wall_row(wall, name, row, text)
    return [each for each in walls if _has_figures(each)]


def read_summary(blocks: list[Block]) -> Summary:
    """Read the Summary of Information table, row by row."""
    rows = summary_rows(blocks)
    summary = Summary(found=bool(rows))
    section = ""
    wall: Wall | None = None
    for row in rows:
        name, text = label(row).strip(), value(row)
        if (heading := _heading(summary, name, text, section)) is not None:
            section = heading
        elif (opened := _new_wall(summary, name, text, section)) is not None:
            section, wall = "walls", opened
            summary.walls.append(opened)
        elif section == "remedial" and text:
            summary.remedial_works = f"{name}: {text}"
            section = ""
        elif section == "walls" and wall is not None:
            _read_wall_row(wall, name, row, text)
        elif section in LAND_SECTIONS:
            _read_land_row(summary, section, name, row)
    # The NHI Act template ships an example wall block ("Whole wall length:
    # m", "Retained height: m to m") that is left unfilled when the walls are
    # given in a separate table instead. A block with nothing in it is that
    # template, not a wall.
    summary.walls = [each for each in summary.walls if _has_figures(each)]
    summary.walls += _later_walls(blocks, len(rows))
    # A 2013 wall block has no height row; the height is in its heading.
    for each in summary.walls:
        if each.retained_height_m is None and (
            found := HEADING_HEIGHT.search(each.description)
        ):
            each.retained_height_m = metres(found.group(1), found.group(2))
            each.retained_height_text = found.group(0)
    return summary


# ---------------------------------------------------------------------------
# What sits outside the summary table.
# ---------------------------------------------------------------------------


def read_ratings(blocks: list[Block]) -> dict[str, str]:
    """Return the construction issues ticks as the costing tool's E, M or D.

    The column a row is ticked in is named by the table's header row, so a
    template that reorders or adds columns still reads correctly. A row with
    no tick, or more than one, is left blank.
    """
    ratings = dict.fromkeys(RATING_ROWS.values(), "")
    header: tuple[str, ...] = ()
    for block in blocks:
        if not block.is_row:
            continue
        name = block.cells[0].strip().lower()
        if name.startswith("construction issues"):
            header = tuple(cell.strip().lower() for cell in block.cells)
            continue
        if name in RATING_ROWS and header:
            ticked = [
                header[i]
                for i, cell in enumerate(block.cells[1:], start=1)
                if i < len(header) and cell.strip() in TICKED
            ]
            if len(ticked) == 1:
                ratings[RATING_ROWS[name]] = RATING_CODES.get(ticked[0], ticked[0])
    return ratings


def section_paragraphs(blocks: list[Block], heading: str, until: str) -> list[str]:
    """Return the paragraphs from one heading up to the next named one."""
    out: list[str] = []
    inside = False
    for block in blocks:
        if block.is_row:
            continue
        if re.match(heading, block.text, re.IGNORECASE):
            inside = True
            continue
        if inside and re.match(until, block.text, re.IGNORECASE):
            break
        if inside:
            out.append(block.text)
    return out


def damaged_lengths(paragraphs: list[str]) -> dict[int, dict[str, float]]:
    """Return each wall's damaged and collapsed length from the damage bullets.

    "Collapse to 3.4 m length of RTW 1" and "Damage to 1.7 m length of RTW 1"
    both count towards RTW 1's damaged length; only the first counts towards
    its collapsed length.
    """
    out: dict[int, dict[str, float]] = {}
    for paragraph in paragraphs:
        for kind, metres, number in WALL_DAMAGE.findall(paragraph):
            wall = out.setdefault(int(number), {"damaged": 0.0, "collapsed": 0.0})
            wall["damaged"] += float(metres)
            if kind.lower().startswith("collapse"):
                wall["collapsed"] += float(metres)
    return out


@dataclass
class RemedialWall:
    """One wall the conceptual remedial works propose."""

    replaces: str
    construction: str
    label: str = ""
    length_m: float | None = None
    max_retained_height_m: float | None = None
    pole_sed_mm: float | None = None
    embedment_m: float | None = None


def _from_construct_phrase(match: re.Match[str], paragraph: str) -> RemedialWall:
    """Return the wall a "construct a … retaining wall" sentence proposes.

    The dimensions can be written into the phrase itself: "construct a 16m
    long anchored sprayed concrete retaining wall", or "an anchored 3.0 m long,
    2.5 m high sprayed concrete retaining wall". They are lifted out, and what
    is left is the construction.
    """
    replaces = REMEDIAL_FOR.search(paragraph)
    phrase = match.group(2)
    long_in = INLINE_LONG.search(phrase)
    high_in = INLINE_HIGH.search(phrase)
    construction = INLINE_HIGH.sub("", INLINE_LONG.sub("", phrase))
    return RemedialWall(
        replaces=replaces.group(0).upper().replace(" ", "") if replaces else "",
        construction=re.sub(r"[\s,]+", " ", construction).strip(" ,"),
        length_m=float(long_in.group(1)) if long_in else None,
        max_retained_height_m=float(high_in.group(1)) if high_in else None,
    )


def _fill_dimensions(wall: RemedialWall, paragraph: str) -> None:
    """Fill whichever of a proposed wall's dimensions a paragraph gives."""
    if (found := LONG_WALL.search(paragraph)) and wall.length_m is None:
        wall.length_m = float(found.group(1))
    if (found := LONG_WALL_TYPE.search(paragraph)) and wall.length_m is None:
        wall.length_m = float(found.group(1))
        if not wall.construction:
            wall.construction = found.group(2).strip()
    if (found := MAX_HEIGHT.search(paragraph)) and wall.max_retained_height_m is None:
        wall.max_retained_height_m = metres(found.group(1), found.group(2))
    if (found := SED.search(paragraph)) and wall.pole_sed_mm is None:
        wall.pole_sed_mm = float(found.group(1))
    if (found := EMBEDMENT.search(paragraph)) and wall.embedment_m is None:
        wall.embedment_m = float(found.group(1))


def read_remedial_walls(paragraphs: list[str]) -> list[RemedialWall]:
    """Return the walls the remedial works propose, with their dimensions."""
    walls: list[RemedialWall] = []
    # Set by "constructing three … retaining walls", for the labelled blocks
    # that follow it.
    several = ""
    for paragraph in paragraphs:
        text = paragraph.strip().lstrip("•").strip()
        if (match := REMEDIAL_LABEL.match(text)) and several:
            walls.append(
                RemedialWall(replaces="", construction=several, label=match.group(1))
            )
        elif match := REMEDIAL_WALL.search(paragraph):
            if match.group(1).lower() in ("a", "an"):
                walls.append(_from_construct_phrase(match, paragraph))
            else:
                several = match.group(2).strip()
        elif match := REMEDIAL_REPLACE.search(paragraph):
            walls.append(
                RemedialWall(
                    replaces=match.group(1).upper().replace(" ", ""), construction=""
                )
            )
        elif walls:
            _fill_dimensions(walls[-1], paragraph)
    return walls


def site_address(line: str) -> str:
    """Return the site address from the report's claimant line, without names.

    The line reads "Claimant name(s), street address, suburb, city", and the
    claimant's name is dropped here so that no copy of the CSVs carries it. The
    address starts at, in order of preference:

    1. the first part that *begins* with a street number, or with "Unit",
       "Flat", "Apartment" or "Lot" -- so a trust or body corporate named with
       a number ("… Family 128 Trust, 84 Example Road") is not mistaken for it;
    2. failing that, the first number inside a part, for a name with no comma
       after it ("A Person 1 Example Street");
    3. failing that, the second part, since the first is where the name sits
       and losing a road name is the lesser harm.

    Examples:
        >>> site_address("A Person & B Person, 26 Example Street, Wellington")
        '26 Example Street, Wellington'
        >>> site_address("An Example Family 128 Trust, 84 Example Road, Suburb")
        '84 Example Road, Suburb'
        >>> site_address("A Person 1 Example Street, #3, Suburb")
        '1 Example Street, #3, Suburb'
        >>> site_address("Body Corporate 12345, Unit 3, 3A Example Way")
        'Unit 3, 3A Example Way'
        >>> site_address("C Person, Example Road, Suburb")
        'Example Road, Suburb'
    """
    parts = [part.strip() for part in line.split(",") if part.strip()]
    starts = next(
        (i for i, part in enumerate(parts) if ADDRESS_START.match(part)), None
    )
    if starts is not None:
        return ", ".join(parts[starts:])
    for i, part in enumerate(parts):
        if found := re.search(r"\d", part):
            return ", ".join([part[found.start() :], *parts[i + 1 :]])
    return ", ".join(parts[1:])


def read_header(blocks: list[Block]) -> dict[str, str]:
    """Return the job number, date, addressee, claim type, site address and claim no.

    The address is the site's, with the claimant's name taken off
    (:func:`site_address`).
    """
    out = dict.fromkeys(
        (
            "job_number",
            "report_date",
            "addressee",
            "claim_type",
            "report_kind",
            "address",
            "claim_number",
        ),
        "",
    )
    paragraphs = [block.text for block in blocks if not block.is_row]
    for i, text in enumerate(paragraphs[:30]):
        if (match := JOB_NUMBER.match(text)) and not out["job_number"]:
            out["job_number"] = match.group(1)
            following = paragraphs[i + 1 : i + 3]
            if following and DATE.search(following[0]):
                out["report_date"] = following[0]
                if len(following) > 1:
                    out["addressee"] = following[1]
        elif (match := CLAIM_HEADING.match(text)) and not out["claim_type"]:
            out["claim_type"] = match.group(1).strip()
            out["report_kind"] = (
                "structural" if "structural" in match.group(2).lower() else "land"
            )
            if i + 1 < len(paragraphs):
                out["address"] = site_address(paragraphs[i + 1])
            if i + 2 < len(paragraphs) and BARE_CLAIM_NUMBER.match(paragraphs[i + 2]):
                out["claim_number"] = paragraphs[i + 2]
        elif (match := CLAIM_NUMBER.search(text)) and not out["claim_number"]:
            out["claim_number"] = match.group(1)
    return out


# ---------------------------------------------------------------------------
# One report.
# ---------------------------------------------------------------------------

# The summary fields a report is expected to carry. Any left blank are named
# in its `missing` column.
EXPECTED = (
    "natural_disaster",
    "evacuated_m2",
    "inundated_m2",
    "imminent_evacuation_m2",
    "imminent_new_inundation_m2",
    "imminent_reinundation_m2",
)


def _sum_known(*values: float | None) -> float | None:
    """Return the sum of the values that are known, or blank if none is."""
    known = [value for value in values if value is not None]
    return round(sum(known), 3) if known else None


def _joined(walls: list[Wall], attribute: str) -> str:
    """Return one figure per wall, in wall order, as "19;2;7" (blank if unread)."""
    values = (getattr(wall, attribute) for wall in walls)
    return ";".join("" if number is None else f"{number:g}" for number in values)


def _total(walls: list[Wall], attribute: str) -> float | None:
    """Return a figure summed over the walls, or blank if no wall carries it."""
    values = [getattr(wall, attribute) for wall in walls]
    known = [number for number in values if number is not None]
    return round(sum(known), 2) if known else None


@dataclass
class Extracted:
    """Everything read from one report."""

    report: dict[str, object]
    walls: list[dict[str, object]]
    remedial_walls: list[dict[str, object]]


def extract(blocks: list[Block], *, subproject: str = "") -> Extracted:
    """Read one report's blocks into its rows.

    Args:
        blocks: :func:`read_blocks`.
        subproject: The subproject the report came from, carried on every row.

    Returns:
        The report's own row, its walls and its proposed remedial walls.
    """
    text = "\n".join(block.text for block in blocks)
    summary = read_summary(blocks)
    damage = section_paragraphs(
        blocks, r"^property damage", r"^(eqc|nhc|natural hazards) consid|^imminent risk"
    )
    remedial = section_paragraphs(
        blocks, REMEDIAL_HEADING, r"^additional information|^summary of information"
    )
    lengths = damaged_lengths(damage)
    for wall in summary.walls:
        if wall.wall_number in lengths:
            wall.damaged_length_m = lengths[wall.wall_number]["damaged"]
            wall.collapsed_length_m = lengths[wall.wall_number]["collapsed"]
        # A second reading of the same length, off the summary table: the
        # damaged face spread over the wall's retained height. Where the bullets
        # give no length this is the only one, and where both exist a
        # disagreement marks a report worth opening.
        if wall.damaged_face_m2 is not None and wall.retained_height_m:
            wall.damaged_length_from_face_m = round(
                wall.damaged_face_m2 / wall.retained_height_m, 2
            )

    # Searched a paragraph at a time: over the joined text, a "sentence" runs
    # back to the last full stop, which in a header of addresses and job
    # numbers can be several paragraphs up.
    event = next(
        (
            match
            for block in blocks
            if not block.is_row and (match := EVENT.search(block.text))
        ),
        None,
    )
    event_text = event.group(0).strip() if event else ""
    event_when = MONTH_YEAR.search(event_text) if event_text else None
    inspected = INSPECTED.search(text)
    # A report can describe several landslips, each with its own width.
    widths = [float(found) for found in LANDSLIP_WIDTH.findall(" ".join(damage))]
    debris = DEBRIS.search(" ".join(remedial))
    # One estimate total per wall in a 2013 report, so they are summed; a
    # summary "Total Cost" row alongside them would count them twice, so the
    # generic "TOTAL" row is only the fallback.
    totals = [
        found
        for block in blocks
        if block.is_row
        and ESTIMATE_TOTAL.match(block.cells[0].strip())
        and (found := money(value(block))) is not None
    ]
    design_total = (
        sum(totals)
        if totals
        else next(
            (
                money(value(block))
                for block in blocks
                if block.is_row and block.cells[0].strip().upper().startswith("TOTAL")
            ),
            None,
        )
    )
    # The 2013 estimates price the wall itself ("Construct wall | $3,000");
    # the later ones leave construction "TBA" for the estimator, so the total
    # is design and consent only.
    # A summary row reading "$20,500 + construction costs" is the design total
    # with construction left to the estimator, so only a construct row priced
    # outright counts.
    includes_construction = any(
        block.is_row
        # "Construct wall", not "Construction observations", an inspection fee.
        and re.search(r"\bconstruct(?!ion)", block.cells[0], re.IGNORECASE)
        and money(value(block)) is not None
        and not re.search(r"\+|tba", value(block), re.IGNORECASE)
        for block in blocks
    )
    damaged_walls = [wall for wall in summary.walls if (wall.damaged_face_m2 or 0) > 0]
    header = read_header(blocks)
    report: dict[str, object] = {
        "subproject": subproject,
        **header,
        "act": next((short for act, short in ACTS.items() if act in text), ""),
        "inspection_date": inspected.group(1).strip() if inspected else "",
        "event_description": event_text,
        # The event sentence first; failing that the claim heading, since a
        # 2013 report with no event sentence is still headed "Claim for
        # Natural Disaster (Earthquake) Damage".
        "event_cause": next(
            (
                cause
                for source in (event_text, header["claim_type"])
                for cause, pattern in EVENT_CAUSES.items()
                if pattern.search(source)
            ),
            "",
        ),
        "event_month": (event_when.group(1) or "").title() if event_when else "",
        "event_year": event_when.group(2) if event_when else "",
        "summary_found": summary.found,
        "natural_disaster": summary.natural_disaster,
        # Whether the report found natural disaster damage at all. A declined
        # claim reads "No", and its "Nil" areas mean nothing was accepted, not
        # that nothing moved -- so it belongs out of any analysis of extents.
        "claim_accepted": (
            summary.natural_disaster.lower().startswith("yes")
            if summary.natural_disaster
            else None
        ),
        "evacuated_m2": summary.evacuated_m2,
        "inundated_m2": summary.inundated_m2,
        "inundated_volume_m3": summary.inundated_volume_m3,
        "imminent_evacuation_m2": summary.imminent_evacuation_m2,
        "imminent_new_inundation_m2": summary.imminent_new_inundation_m2,
        "imminent_reinundation_m2": summary.imminent_reinundation_m2,
        "main_access_way": summary.main_access_way,
        "access_evacuated_m2": summary.access_evacuated_m2,
        "access_inundated_m2": summary.access_inundated_m2,
        "access_imminent_evacuation_m2": summary.access_imminent_evacuation_m2,
        "access_imminent_new_inundation_m2": (
            summary.access_imminent_new_inundation_m2
        ),
        "access_imminent_reinundation_m2": summary.access_imminent_reinundation_m2,
        # The claim's whole insured land: that within 8 m of the dwelling plus
        # that on or supporting the main access way, which the table gives in
        # separate blocks. A claim can have all its damage on the access way
        # (1501000.0008), so neither block alone is the claim's damage.
        **{
            f"total_{kind}": _sum_known(
                getattr(summary, kind), getattr(summary, f"access_{kind}")
            )
            for kind in (
                "evacuated_m2",
                "inundated_m2",
                "imminent_evacuation_m2",
                "imminent_new_inundation_m2",
                "imminent_reinundation_m2",
            )
        },
        "summary_columns": summary.summary_columns,
        "dwelling": summary.dwelling,
        "services": summary.services,
        "bridges_culverts": summary.bridges_culverts,
        "n_walls": len(summary.walls),
        "n_walls_damaged": len(damaged_walls),
        "wall_lengths_m": _joined(summary.walls, "whole_length_m"),
        "wall_damaged_lengths_m": _joined(summary.walls, "damaged_length_m"),
        "wall_damaged_faces_m2": _joined(summary.walls, "damaged_face_m2"),
        "damaged_face_total_m2": _total(summary.walls, "damaged_face_m2"),
        "imminent_face_total_m2": _total(summary.walls, "imminent_face_m2"),
        "n_landslips": len(widths),
        "landslip_width_m": max(widths) if widths else None,
        "landslip_widths_m": ";".join(f"{width:g}" for width in widths),
        "debris_volume_m3": float(debris.group(1)) if debris else None,
        **read_ratings(blocks),
        "design_consent_cost_excl_gst_nzd": design_total,
        "estimate_includes_construction": includes_construction,
        "remedial_works": summary.remedial_works,
        "notes": summary_notes(blocks),
    }
    # `missing` is a row that is in the table but could not be read -- the
    # sign of a template the parse has not met. A row the table does not carry
    # at all is `absent_rows` instead: a Storm/Flood claim has no Evacuated row,
    # and the 2013 template no Re-inundation row, and neither is a failure. A
    # declined claim ("Is this natural disaster damage? No") has no areas to
    # find, so its blanks are neither.
    areas = [name for name in EXPECTED if name != "natural_disaster"]
    report["absent_rows"] = (
        ";".join(name for name in areas if name not in summary.seen)
        if summary.found
        else ""
    )
    if not summary.found:
        report["missing"] = "summary table not found"
    elif report["claim_accepted"] is False:
        report["missing"] = ""
    else:
        report["missing"] = ";".join(
            name
            for name in EXPECTED
            if report[name] in (None, "")
            and (name == "natural_disaster" or name in summary.seen)
        )
    return Extracted(
        report=report,
        walls=[{"subproject": subproject, **asdict(wall)} for wall in summary.walls],
        remedial_walls=[
            {"subproject": subproject, **asdict(wall)}
            for wall in read_remedial_walls(remedial)
        ],
    )


# ---------------------------------------------------------------------------
# The run.
# ---------------------------------------------------------------------------


def cached_file(cached_path: str) -> Path:
    """Resolve an index's cached path, relative to the repo or absolute."""
    path = Path(cached_path)
    return path if path.is_absolute() else REPO_ROOT / path


def write_rows(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    """Write rows to a CSV with a fixed column order."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def extract_rows(rows: dict[str, IndexRow]) -> list[Extracted]:
    """Extract the fetched reports among some index rows, keyed by subproject."""
    results: list[Extracted] = []
    for name, row in sorted(rows.items()):
        if row.status != FETCHED:
            continue
        # Step one falls back to a PDF where no report .docx exists, and does
        # not cache it, since a PDF is not read here.
        if row.report_path.lower().endswith(".pdf"):
            print(f"  {name}: {row.report_name} is a PDF; not read")
            continue
        path = cached_file(row.cached_path) if row.cached_path else None
        if path is None or not path.exists():
            print(f"  {name}: cached copy missing at {path}; run step one again")
            continue
        result = extract(read_blocks(path), subproject=name)
        results.append(result)
        report = result.report
        print(
            f"  {name}: {report['claim_type'] or '?'}, "
            f"evacuated {report['evacuated_m2']}, inundated {report['inundated_m2']}, "
            f"{report['n_walls']} walls ({report['n_walls_damaged']} damaged)"
            + (f" -- missing {report['missing']}" if report["missing"] else "")
        )
    return results


def write_results(results: list[Extracted], out_dir: Path) -> None:
    """Write the three CSVs for a set of extracted reports."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_rows(
        out_dir / REPORTS_NAME,
        [result.report for result in results],
        list(results[0].report),
    )
    write_rows(
        out_dir / WALLS_NAME,
        [wall for result in results for wall in result.walls],
        ["subproject", *(item.name for item in fields(Wall))],
    )
    write_rows(
        out_dir / REMEDIAL_WALLS_NAME,
        [wall for result in results for wall in result.remedial_walls],
        ["subproject", *(item.name for item in fields(RemedialWall))],
    )
    print(f"Extracted {len(results)} reports into {out_dir}")


def run(project: str, *, out_dir: Path | None = None) -> list[Extracted]:
    """Extract every fetched report in a project's index.

    Args:
        project: The T+T project number.
        out_dir: Where to write, defaulting to beside the index.

    Returns:
        What was read from each report.
    """
    results = extract_rows(read_index(index_path(project)))
    if not results:
        print("Nothing to extract: run fetch_claim_reports.py first")
        return results
    write_results(results, out_dir or index_path(project).parent)
    return results


def run_list(
    claims_list: Path,
    *,
    study_area_only: bool = False,
    out_dir: Path | None = None,
) -> list[Extracted]:
    """Extract every fetched report on a claims list, across its projects.

    Each report row gains the list's own columns for its claim --
    coordinates, study-area authority, the date T+T took it on, the name's
    event hint -- so ``reports.csv`` can be mapped and filtered without a
    second join.

    Args:
        claims_list: A list written by ``gen_claims_lists.py``.
        study_area_only: Keep only the claims inside the four study authorities.
        out_dir: Where to write, defaulting to ``extracted/<list name>``.

    Returns:
        What was read from each report.
    """
    with claims_list.open(newline="", encoding="utf-8") as f:
        on_list = {row["subproject"]: row for row in csv.DictReader(f)}
    results: list[Extracted] = []
    for project, wanted in wanted_by_programme(
        claims_list, study_area_only=study_area_only
    ).items():
        index = read_index(index_path(project))
        names = {f"{project}.{sub}" for sub in wanted}
        rows = {name: row for name, row in index.items() if name in names}
        if rows:
            print(f"\n{project}: {len(rows):,} of {len(names):,} claims fetched")
        results += extract_rows(rows)
    if not results:
        print("Nothing to extract: fetch from the list first")
        return results
    for result in results:
        claim = on_list.get(str(result.report["subproject"]), {})
        for column, source in LIST_COLUMNS.items():
            result.report[column] = claim.get(source, "")
    write_results(results, out_dir or EXTRACTED_DIR / claims_list.stem)
    return results


def show(subprojects: list[str]) -> None:
    """Print what the parse sees in each named subproject's cached report.

    The first paragraphs, the property damage and imminent risk sections, and
    every summary table row with its cells separated by `` | `` -- enough to
    see why a field came out blank, without opening the report.
    """
    for name in subprojects:
        project = name.partition(".")[0]
        row = read_index(index_path(project)).get(name)
        if row is None or row.status != FETCHED:
            print(f"\n===== {name}: not fetched")
            continue
        path = cached_file(row.cached_path)
        print(f"\n===== {name}: {path.name}")
        if not path.exists() or path.suffix.lower() not in (".docx", ".xml"):
            print("  (no cached .docx to read)")
            continue
        blocks = read_blocks(path)
        paragraphs = [block.text for block in blocks if not block.is_row]
        print("-- first paragraphs")
        for text in paragraphs[:12]:
            print(f"  {text}")
        for heading, until in (
            (r"^property damage", r"^(eqc|nhc|natural hazards) consid"),
            (r"^imminent (?:risk|damage)$", REMEDIAL_HEADING),
        ):
            print(f"-- {heading.strip('^')}")
            for text in section_paragraphs(blocks, heading, until)[:15]:
                print(f"  {text}")
        print("-- summary table rows")
        for block in summary_rows(blocks):
            print("  " + " | ".join(cell for cell in block.cells))
        print("-- every table row after the summary heading (first 60)")
        start = next(
            (i for i, block in enumerate(blocks) if SUMMARY_HEADING.match(block.text)),
            len(blocks),
        )
        later = [block for block in blocks[start + 1 :] if block.is_row]
        for block in later[len(summary_rows(blocks)) : len(summary_rows(blocks)) + 60]:
            print("  " + " | ".join(cell for cell in block.cells))


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and extract."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument(
        "--claims-list",
        help="a list from gen_claims_lists.py, by name (e.g. kaikoura-2016) or "
        "path; extracts every fetched report on it, across projects",
    )
    parser.add_argument(
        "--study-area-only",
        action="store_true",
        help="with --claims-list, keep only claims inside the four study authorities",
    )
    parser.add_argument(
        "--show",
        nargs="+",
        metavar="SUBPROJECT",
        help="print the header lines and summary table rows the parse sees for "
        "these subprojects (e.g. 1501000.0016), to diagnose a template it misses",
    )
    args = parser.parse_args(argv)
    if args.show:
        show(args.show)
        return 0
    if args.claims_list:
        run_list(
            claims_list_path(args.claims_list), study_area_only=args.study_area_only
        )
        return 0
    run(args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
