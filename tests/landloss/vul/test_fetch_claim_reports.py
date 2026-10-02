"""Choosing and indexing each subproject's claim report.

The T: drive is never touched: every test builds a project tree in a temporary
folder and replaces the tdrive_sync copy with a stub that records what it was
asked for.
"""

import os
import zipfile
from pathlib import Path

import pytest

from scripts.landloss.vul.static_data_gen import fetch_claim_reports as fcr

PROJECT = "1502000"


def touch(path: Path, *, mtime: float) -> Path:
    """Create an empty file with the given modification time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def cached(monkeypatch) -> list[Path]:
    """Stub the T: copy, returning the list of paths it was asked to cache."""
    calls: list[Path] = []

    def fake_cache(path: Path) -> Path:
        calls.append(path)
        return Path("cache") / path.name

    monkeypatch.setattr(fcr, "cache_report_text", fake_cache)
    return calls


@pytest.fixture
def root(tmp_path) -> Path:
    """A project with four subprojects covering each case."""
    project = tmp_path / PROJECT
    issued = project / f"{PROJECT}.0001" / "IssuedDocuments"
    # A later draft must not beat an earlier final.
    touch(issued / "Final report" / "T+T_Report.docx", mtime=1_000)
    touch(issued / "Draft" / "T+T_Report v2.docx", mtime=2_000)
    touch(issued / "Final report" / "~$T+T_Report.docx", mtime=3_000)
    touch(issued / "Photos.docx", mtime=3_000)

    # No final anywhere: the latest report wins.
    issued = project / f"{PROJECT}.0002 SUPERSEDED" / "IssuedDocuments"
    touch(issued / "T+T_Report v1.docx", mtime=1_000)
    touch(issued / "T+T_Report v2.docx", mtime=2_000)

    (project / f"{PROJECT}.0003" / "IssuedDocuments").mkdir(parents=True)
    (project / f"{PROJECT}.0004").mkdir()
    (project / "Admin").mkdir()
    return tmp_path


def run(root: Path, tmp_path: Path, **kwargs) -> dict[str, fcr.IndexRow]:
    """Fetch into an index under the temporary folder."""
    kwargs.setdefault("limit", 10)
    return fcr.fetch(
        PROJECT, project_roots=(root,), out=tmp_path / "index.csv", **kwargs
    )


def test_a_final_beats_a_later_draft(root, tmp_path, cached):
    row = run(root, tmp_path)[f"{PROJECT}.0001"]
    assert row.status == fcr.FETCHED
    assert row.report_name == "T+T_Report.docx"
    assert row.is_final


def test_without_a_final_the_latest_report_wins(root, tmp_path, cached):
    row = run(root, tmp_path)[f"{PROJECT}.0002 SUPERSEDED"]
    assert row.report_name == "T+T_Report v2.docx"
    assert not row.is_final


def test_lock_files_and_non_reports_are_never_chosen(root):
    issued = root / PROJECT / f"{PROJECT}.0001" / "IssuedDocuments"
    names = {path.name for path in fcr.report_candidates(issued)}
    assert "~$T+T_Report.docx" not in names
    assert "Photos.docx" not in names


def test_final_in_the_project_path_does_not_mark_every_report_final(tmp_path):
    issued = tmp_path / "Final projects" / "IssuedDocuments"
    report = touch(issued / "T+T_Report.docx", mtime=1_000)
    assert not fcr.is_final(report, issued)


def test_subprojects_without_a_report_are_recorded_not_dropped(root, tmp_path, cached):
    index = run(root, tmp_path)
    assert index[f"{PROJECT}.0003"].status == fcr.NO_REPORT
    assert index[f"{PROJECT}.0004"].status == fcr.NO_ISSUED_DOCUMENTS
    assert "Admin" not in index


def test_the_limit_counts_reports_fetched(root, tmp_path, cached):
    index = run(root, tmp_path, limit=1)
    assert sum(row.status == fcr.FETCHED for row in index.values()) == 1
    assert len(cached) == 1


def test_a_second_run_fetches_only_what_is_new(root, tmp_path, cached):
    run(root, tmp_path, limit=1)
    run(root, tmp_path, limit=10)
    # Each report copied once, across both runs.
    assert len(cached) == 2
    index = fcr.read_index(tmp_path / "index.csv")
    assert index[f"{PROJECT}.0001"].is_final
    assert index[f"{PROJECT}.0001"].cached_path


def test_refresh_looks_again(root, tmp_path, cached):
    run(root, tmp_path)
    run(root, tmp_path, refresh=True)
    assert len(cached) == 4


def test_a_dry_run_copies_and_writes_nothing(root, tmp_path, cached):
    index = run(root, tmp_path, dry_run=True)
    assert cached == []
    assert not (tmp_path / "index.csv").exists()
    assert index[f"{PROJECT}.0001"].report_name == "T+T_Report.docx"


def test_subprojects_can_be_named(root, tmp_path, cached):
    index = run(root, tmp_path, wanted=["2"])
    assert list(index) == [f"{PROJECT}.0002 SUPERSEDED"]


def test_an_archived_project_is_found_without_its_leading_zeros(tmp_path):
    office, archive = tmp_path / "office", tmp_path / "archive"
    office.mkdir()
    (archive / "85650").mkdir(parents=True)
    assert fcr.find_project_dirs("0085650", (office, archive)) == [archive / "85650"]


def test_a_project_under_no_root_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError, match="0085650"):
        fcr.find_project_dirs("0085650", (tmp_path,))


def test_a_subproject_filed_inside_another_is_found(tmp_path):
    project = tmp_path / "86101"
    touch(
        project / "86101.0360" / "86101.0371" / "IssuedDocuments" / "Report.docx",
        mtime=1_000,
    )
    names = [path.name for path in fcr.subproject_dirs(project)]
    assert names == ["86101.0360", "86101.0371"]
    assert [p.name for p in fcr.subproject_dirs(project, ["0371"])] == ["86101.0371"]


def test_a_claims_list_fetches_across_projects_and_can_keep_the_study_area(
    tmp_path, cached, monkeypatch
):
    for project in ("85650", "86101"):
        touch(
            tmp_path / project / f"{project}.0001" / "IssuedDocuments" / "Report.docx",
            mtime=1_000,
        )
    claims = tmp_path / "list.csv"
    claims.write_text(
        "subproject,in_study_area\n85650.0001,True\n86101.0001,False\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fcr, "CLAIM_REPORTS_ASSETS_DIR", tmp_path / "assets")
    assert fcr.wanted_by_programme(claims) == {"85650": ["0001"], "86101": ["0001"]}
    assert fcr.wanted_by_programme(claims, study_area_only=True) == {"85650": ["0001"]}
    assert fcr.wanted_by_programme(claims, programmes=["0086101"]) == {
        "86101": ["0001"]
    }
    fetched = fcr.fetch_list(claims, limit=10, project_roots=(tmp_path,))
    assert fetched == 2
    assert (tmp_path / "assets" / "85650" / fcr.INDEX_NAME).exists()


def test_a_pdf_is_taken_only_where_there_is_no_docx_at_all(tmp_path):
    issued = tmp_path / "IssuedDocuments"
    touch(issued / "T+T_2016-016598_FinalReport.pdf", mtime=2_000)
    touch(issued / "T+T_2016-016598_Report Sketches.pdf", mtime=3_000)
    assert fcr.choose_report(tmp_path)[0].name == "T+T_2016-016598_FinalReport.pdf"
    # A draft docx, even one not named as a report, beats the PDF final.
    touch(issued / "LAAC.20170320.dft.16598.docx", mtime=1_000)
    assert fcr.choose_report(tmp_path)[0].name == "LAAC.20170320.dft.16598.docx"
    # And a docx named as a report beats that.
    touch(issued / "T+T_2016-016598_DRAFT_Report.docx", mtime=500)
    assert fcr.choose_report(tmp_path)[0].name == "T+T_2016-016598_DRAFT_Report.docx"


@pytest.mark.parametrize(
    ("name", "draft"),
    [
        ("CLM-2016-010371_DRAFT_Report.docx", True),
        ("T+T 20167-000486 Report Draft for LA Review.docx", True),
        ("LAAC.20170227.dft.2085Kenepuru.docx", True),
        ("LAAC.20161202.EQC.drt.282Hampden.docx", True),
        ("LAAC.20161202.EQC.fnl.282Hampden.docx", False),
        ("T+T_2016016708_FINAL Report.docx", False),
        ("T+T_2021-IAG-C3781361_Final Report.docx", False),
    ],
)
def test_drafts_are_flagged(name, draft):
    assert fcr.is_draft(Path(name)) is draft


def test_an_index_from_before_drafts_were_flagged_still_reads(tmp_path):
    index = tmp_path / "index.csv"
    index.write_text(
        "project_number,subproject_number,subproject,status,is_final\n"
        "1502000,0001,1502000.0001,fetched,True\n",
        encoding="utf-8",
    )
    row = fcr.read_index(index)["1502000.0001"]
    assert row.is_final
    assert not row.is_draft


def test_working_material_is_searched_when_issued_documents_has_no_docx(tmp_path):
    touch(tmp_path / "IssuedDocuments" / "T+T_FinalReport.pdf", mtime=2_000)
    working = tmp_path / "WorkingMaterial"
    touch(working / "Calcs" / "slope stability notes.docx", mtime=5_000)
    touch(working / "Final report" / "20210812.adw.8caesarspl.docx", mtime=1_000)
    touch(working / "Drafts" / "2013_000113_T&T rpt 1.docx", mtime=3_000)
    report, folder = fcr.choose_report(tmp_path)
    # "Final report" is in the folder name, so it is a final; the notes are
    # never a candidate however recent.
    assert report.name == "20210812.adw.8caesarspl.docx"
    assert folder.name == "WorkingMaterial"


def test_working_material_alone_is_enough(tmp_path, cached):
    subproject = tmp_path / PROJECT / f"{PROJECT}.0001"
    touch(subproject / "Working Material" / "T+T rpt.docx", mtime=1_000)
    row = fcr.index_subproject(subproject)
    assert row.status == fcr.FETCHED
    assert row.source_folder == "Working Material"


def test_the_source_folder_is_recorded(root, tmp_path, cached):
    row = run(root, tmp_path)[f"{PROJECT}.0001"]
    assert row.source_folder == "IssuedDocuments"


@pytest.mark.parametrize(
    ("name", "final"),
    [
        ("LAAC.20161202.EQC.fnl.282Hampden.docx", True),
        ("aaje.20170309.Towai35EQC.FinalRev1.docx", True),
        ("T+T_2016-016728_Report.docx", False),
        # "fnl" inside a word is not an abbreviation.
        ("T+T_Report_Finlay St.docx", False),
    ],
)
def test_finals_are_recognised_by_their_abbreviation_too(tmp_path, name, final):
    assert fcr.is_final(tmp_path / name, tmp_path) is final


def test_a_project_split_between_office_and_archive_uses_the_copy_with_files(
    tmp_path, cached
):
    office, archive = tmp_path / "office", tmp_path / "archive"
    # The office holds an empty stub; the archive holds the report.
    (office / "871310" / "871310.3803").mkdir(parents=True)
    touch(
        archive / "871310" / "871310.3803" / "IssuedDocuments" / "Report.docx",
        mtime=1_000,
    )
    # And a subproject only the office has.
    touch(
        office / "871310" / "871310.4197" / "IssuedDocuments" / "Report.docx",
        mtime=1_000,
    )
    index = fcr.fetch(
        "0871310", limit=10, project_roots=(office, archive), out=tmp_path / "i.csv"
    )
    assert index["871310.3803"].status == fcr.FETCHED
    assert "archive" in index["871310.3803"].report_path
    assert index["871310.4197"].status == fcr.FETCHED


def test_a_docx_in_one_copy_beats_a_pdf_in_another(tmp_path):
    first, second = tmp_path / "a" / "1.0001", tmp_path / "b" / "1.0001"
    touch(first / "IssuedDocuments" / "Report.pdf", mtime=2_000)
    touch(second / "IssuedDocuments" / "Report.docx", mtime=1_000)
    report, _ = fcr.choose_across([first, second])
    assert report.suffix == ".docx"


def test_a_folder_that_cannot_be_read_does_not_stop_the_run(tmp_path, monkeypatch):
    project = tmp_path / "1502000"
    locked = project / "1502000.1937"
    locked.mkdir(parents=True)
    touch(project / "1502000.0001" / "IssuedDocuments" / "Report.docx", mtime=1_000)
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == locked:
            raise PermissionError(5, "Access is denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    names = [path.name for path in fcr.subproject_dirs(project)]
    assert names == ["1502000.0001", "1502000.1937"]
    # And indexing it records it as unreadable rather than raising.
    assert fcr.index_subproject(locked).status in {
        fcr.UNREADABLE,
        fcr.NO_ISSUED_DOCUMENTS,
    }


def test_an_interrupted_run_keeps_what_it_did_and_a_rerun_carries_on(
    tmp_path, cached, monkeypatch
):
    project = tmp_path / PROJECT
    for number in range(1, 6):
        touch(
            project / f"{PROJECT}.{number:04d}" / "IssuedDocuments" / "Report.docx",
            mtime=1_000,
        )
    out = tmp_path / "index.csv"
    real = fcr.index_subproject
    calls = {"n": 0}

    def stop_on_the_fourth(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 4:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(fcr, "index_subproject", stop_on_the_fourth)
    with pytest.raises(KeyboardInterrupt):
        fcr.fetch(PROJECT, limit=100, project_roots=(tmp_path,), out=out)
    assert len(fcr.read_index(out)) == 3

    monkeypatch.setattr(fcr, "index_subproject", real)
    before = len(cached)
    fcr.fetch(PROJECT, limit=100, project_roots=(tmp_path,), out=out)
    assert len(fcr.read_index(out)) == 5
    # Only the two not yet done are copied on the rerun.
    assert len(cached) - before == 2


def test_the_index_is_saved_as_the_run_goes(tmp_path, cached, monkeypatch):
    monkeypatch.setattr(fcr, "CHECKPOINT_EVERY", 2)
    saves = []
    real_write = fcr.write_index
    monkeypatch.setattr(
        fcr,
        "write_index",
        lambda path, rows: (saves.append(len(rows)), real_write(path, rows)),
    )
    project = tmp_path / PROJECT
    for number in range(1, 6):
        touch(
            project / f"{PROJECT}.{number:04d}" / "IssuedDocuments" / "Report.docx",
            mtime=1_000,
        )
    fcr.fetch(PROJECT, limit=100, project_roots=(tmp_path,), out=tmp_path / "i.csv")
    assert saves[:2] == [2, 4]


def test_all_lifts_the_limit(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        fcr, "fetch", lambda project, **kwargs: seen.update(kwargs) or {}
    )
    fcr.main(["--project", PROJECT, "--all"])
    assert seen["limit"] > 10**9


def make_docx(
    path: Path, *, text: bytes = b"<document/>", photo_bytes: int = 0
) -> Path:
    """Write a minimal .docx: its document.xml, and optionally a large photo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", text)
        if photo_bytes:
            archive.writestr("word/media/image1.jpeg", os.urandom(photo_bytes))
    return path


def test_only_the_reports_text_is_cached(tmp_path, monkeypatch):
    report = make_docx(
        tmp_path / "T" / "IssuedDocuments" / "Report.docx",
        text=b"<w:document>the text</w:document>",
        photo_bytes=200_000,
    )
    monkeypatch.setattr(
        fcr.ts, "get_cached_local_path", lambda path: tmp_path / "cache" / path.name
    )
    cached = fcr.cache_report_text(report)
    assert cached == tmp_path / "cache" / "Report.docx.document.xml"
    assert cached.read_bytes() == b"<w:document>the text</w:document>"
    assert cached.stat().st_size < report.stat().st_size / 100
    # Current, so a second call reads nothing from the report.
    monkeypatch.setattr(fcr.zipfile, "ZipFile", None)
    assert fcr.cache_report_text(report) == cached


def test_a_pdf_is_not_cached(tmp_path):
    report = touch(tmp_path / "Report.pdf", mtime=1_000)
    assert fcr.cache_report_text(report) is None


def test_a_cache_of_whole_reports_is_slimmed_offline(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    cached = make_docx(
        tmp_path / "cache" / "Report.docx", text=b"<doc/>", photo_bytes=100_000
    )
    pdf = touch(tmp_path / "cache" / "Report.pdf", mtime=1_000)
    fcr.write_index(
        assets / "1502000" / fcr.INDEX_NAME,
        {
            "1502000.0001": fcr.IndexRow(
                "1502000",
                "0001",
                "1502000.0001",
                fcr.FETCHED,
                report_path="T:/x/Report.docx",
                cached_path=str(cached),
            ),
            "1502000.0002": fcr.IndexRow(
                "1502000",
                "0002",
                "1502000.0002",
                fcr.FETCHED,
                report_path="T:/x/Report.pdf",
                cached_path=str(pdf),
            ),
        },
    )
    slimmed, freed = fcr.slim_cache(assets)
    assert slimmed == 2
    assert freed > 90_000
    assert not cached.exists()
    assert not pdf.exists()
    index = fcr.read_index(assets / "1502000" / fcr.INDEX_NAME)
    text = Path(index["1502000.0001"].cached_path)
    assert text.name == "Report.docx.document.xml"
    assert text.read_bytes() == b"<doc/>"
    assert index["1502000.0002"].cached_path == ""
