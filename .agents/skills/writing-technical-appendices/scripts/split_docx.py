"""Split the appendices HTML into one Word document per appendix.

    python split_docx.py <appendices.html> <out_dir>

Each appendix runs from its level-two heading to the next, and takes a
References list holding only the works it cites.
"""

import re
import sys
import tempfile
from pathlib import Path

from tidy_docx import main as to_docx

HEADING = re.compile(r'<h2 id="[^"]*">(.*?)</h2>', re.DOTALL)


def plain(html):
    """Return the text of an HTML fragment, its tags removed."""
    return re.sub(r"<[^>]+>", "", html).strip()


def main(html_path, out_dir):
    """Write one Word file per appendix into ``out_dir``."""
    html = Path(html_path).read_text(encoding="utf-8")
    head, body = html.split("<body>", 1)
    body, tail = body.rsplit("</body>", 1)
    bib_start = body.index('<section role="doc-bibliography"')
    bib = body[bib_start:]
    items = {
        key: li
        for li, key in re.findall(r'(<li id="(loc-\d+)">.*?</li>)', bib, re.DOTALL)
    }
    content = body[:bib_start]
    starts = [
        m for m in HEADING.finditer(content) if re.match(r"[A-Z] ", plain(m.group(1)))
    ]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(content)
        chunk = content[m.start() : end]
        cited = sorted(
            set(re.findall(r'href="#(loc-\d+)"', chunk)), key=lambda k: int(k[4:])
        )
        refs = ""
        if cited:
            refs = (
                '<section role="doc-bibliography"><h2>References</h2>'
                '<ul style="list-style-type: none">'
                + "".join(items[k] for k in cited if k in items)
                + "</ul></section>"
            )
        title = plain(m.group(1))
        letter, name = title.split(" ", 1)
        doc_html = f"{head}<body>{chunk}{refs}</body>{tail}"
        with tempfile.TemporaryDirectory() as tmp:
            piece = Path(tmp) / "appendix.html"
            piece.write_text(doc_html, encoding="utf-8")
            to_docx(
                piece,
                out / f"Appendix {letter} - {name}.docx",
                subtitle=f"Appendix {letter}: {name}",
            )


if __name__ == "__main__":
    main(*sys.argv[1:3])
