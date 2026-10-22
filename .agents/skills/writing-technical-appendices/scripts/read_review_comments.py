"""Read a reviewed appendix: its tracked changes, its comments, and its edits.

    uv run --no-project --with pypandoc-binary python -I read_review_comments.py
        <reviewed.docx> [<sent.docx>]

Prints how many tracked insertions and deletions the reviewed file carries,
every comment with its author and the text it is anchored to, and, when the
version that was sent is given, a paragraph-by-paragraph diff of the text with
the tracked changes accepted. Edits made without tracking only show in that
diff, so pass the sent version whenever there is one.

The reviewed file is only read, never written.
"""

import difflib
import re
import sys
import zipfile

import pypandoc

sys.stdout.reconfigure(encoding="utf-8")

TEXT = re.compile(r"<w:(?:t|delText)(?:\s[^>]*)?>([^<]*)</w:(?:t|delText)>")


def text_of(xml):
    """Return the visible text in a stretch of WordprocessingML."""
    return "".join(TEXT.findall(xml))


def comments(path):
    """Yield (author, comment, anchored text, text before) for each comment."""
    with zipfile.ZipFile(path) as z:
        document = z.read("word/document.xml").decode("utf-8")
        if "word/comments.xml" not in z.namelist():
            return
        notes = z.read("word/comments.xml").decode("utf-8")
    for m in re.finditer(r"<w:comment\b([^>]*)>(.*?)</w:comment>", notes, re.DOTALL):
        cid = re.search(r'w:id="(\d+)"', m.group(1)).group(1)
        author = re.search(r'w:author="([^"]*)"', m.group(1)).group(1)
        body = " / ".join(
            text_of(par)
            for par in re.findall(r"<w:p\b.*?</w:p>", m.group(2), re.DOTALL)
        )
        parts = re.split(
            rf'<w:commentRangeStart w:id="{cid}"[^>]*/>', document, maxsplit=1
        )
        if len(parts) == 2:
            anchor = re.split(
                rf'<w:commentRangeEnd w:id="{cid}"[^>]*/>', parts[1], maxsplit=1
            )[0]
            yield author, body, text_of(anchor), text_of(parts[0])[-120:]
        else:
            yield author, body, "?", "?"


def tracked_counts(path):
    """Return the number of tracked insertions and deletions."""
    with zipfile.ZipFile(path) as z:
        document = z.read("word/document.xml").decode("utf-8")
    return document.count("<w:ins "), document.count("<w:del ")


def paragraphs(path):
    """Return the document's text, tracked changes accepted, one paragraph a line."""
    md = pypandoc.convert_file(
        path, "plain", extra_args=["--track-changes=accept", "--wrap=none"]
    )
    return [line.strip() for line in md.splitlines() if line.strip()]


def main(reviewed, sent=None):
    """Print the reviewed file's changes and comments, and its edits on ``sent``."""
    ins, dels = tracked_counts(reviewed)
    print(f"Tracked changes: {ins} insertions, {dels} deletions\n")
    for author, body, anchor, before in comments(reviewed):
        print(f"[{author}] {body}\n   ON: «{anchor[:300]}»\n   AFTER: …{before}\n")
    if sent:
        print("Text changes (- sent, + reviewed):")
        for line in difflib.unified_diff(
            paragraphs(sent), paragraphs(reviewed), lineterm="", n=0
        ):
            if not line.startswith(("---", "+++", "@@")):
                print(line)


if __name__ == "__main__":
    main(*sys.argv[1:3])
