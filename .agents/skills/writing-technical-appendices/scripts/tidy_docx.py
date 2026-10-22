"""Tidy the pandoc output of the appendices for review in Word.

    python tidy_docx.py <in.html> <out.docx>

Converts the Typst HTML with pandoc, then: adds a title, fits images to the
text width, borders the tables, and shades the review notes.
"""

import datetime as dt
import re
import sys
import tempfile
from pathlib import Path

import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, RGBColor

TEXT_WIDTH = Cm(16)
REVIEW_FILL = "FFF4C2"


def strip_nav(html: str) -> str:
    """Drop the HTML table of contents; Word's navigation pane does that job."""
    return re.sub(r"<nav role=\"doc-toc\">.*?</nav>", "", html, flags=re.DOTALL)


def shade(paragraph, fill):
    """Shade a paragraph's background, as the review notes are in the PDF."""
    # python-docx has no public route to paragraph shading.
    ppr = paragraph._p.get_or_add_pPr()  # noqa: SLF001
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def border_tables(document):
    """Border every data table, skipping pandoc's one-cell figure wrappers."""
    for tbl in document.element.body.iter(qn("w:tbl")):
        tblpr = tbl.tblPr
        style = tblpr.find(qn("w:tblStyle"))
        if style is not None and style.get(qn("w:val")) == "FigureTable":
            continue
        for old in tblpr.findall(qn("w:tblBorders")):
            tblpr.remove(old)
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), "B3B3B3")
            borders.append(el)
        # Schema order: tblBorders comes before shd, tblLayout, tblCellMar, tblLook.
        later = [
            tblpr.find(qn(f"w:{tag}"))
            for tag in ("shd", "tblLayout", "tblCellMar", "tblLook")
        ]
        later = [el for el in later if el is not None]
        if later:
            later[0].addprevious(borders)
        else:
            tblpr.append(borders)
        # Pandoc centres every cell; a cell of running text reads better left.
        for par in tbl.iter(qn("w:p")):
            text = "".join(x.text or "" for x in par.iter(qn("w:t")))
            if len(text) > 25:
                ppr = par.get_or_add_pPr()
                for jc in ppr.findall(qn("w:jc")):
                    ppr.remove(jc)
                jc = OxmlElement("w:jc")
                jc.set(qn("w:val"), "left")
                ppr.append(jc)
        for run in tbl.iter(qn("w:r")):
            rpr = run.get_or_add_rPr()
            for tag in ("w:sz", "w:szCs"):
                el = OxmlElement(tag)
                el.set(qn("w:val"), "18")
                rpr.append(el)


def fit_images(document):
    """Scale any image wider than the text down to the text width."""
    for shape in document.inline_shapes:
        if shape.width > TEXT_WIDTH:
            ratio = TEXT_WIDTH / shape.width
            shape.width = TEXT_WIDTH
            shape.height = int(shape.height * ratio)


def add_title(document, subtitle_text):
    """Put the report title, the appendix's subtitle and the date at the top."""
    first = document.paragraphs[0]
    title = first.insert_paragraph_before(
        "Land loss modelling for the Natural Hazards Commission"
    )
    title.style = document.styles["Title"]
    subtitle = first.insert_paragraph_before(subtitle_text)
    subtitle.style = document.styles["Subtitle"]
    date = first.insert_paragraph_before(
        "Draft for internal review · "
        + dt.datetime.now().astimezone().strftime("%d %B %Y").lstrip("0")
    )
    date.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)


SUBTITLE = "Wellington, Hutt and Porirua: appendices to the technical report"


def main(html_path, out_path, subtitle=SUBTITLE):
    """Convert the HTML to Word with pandoc and tidy the result."""
    html = strip_nav(Path(html_path).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "appendices.html"
        clean.write_text(html, encoding="utf-8")
        raw = Path(tmp) / "raw.docx"
        pypandoc.convert_file(
            str(clean), "docx", outputfile=str(raw), extra_args=["--from=html"]
        )
        document = Document(str(raw))
    add_title(document, subtitle)
    fit_images(document)
    border_tables(document)
    for paragraph in document.paragraphs:
        if paragraph.text.startswith("Review:"):
            shade(paragraph, REVIEW_FILL)
        if paragraph.style.name in (
            "Image Caption",
            "Table Caption",
            "Captioned Figure",
        ):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for section in document.sections:
        section.left_margin = section.right_margin = Cm(2)
        section.top_margin = section.bottom_margin = Cm(2)
    document.save(out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
