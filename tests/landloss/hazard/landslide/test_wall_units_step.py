"""Tests for step 12's wall units script: the claim layer it reads."""

import os

import pytest

from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    gen_urban_slope_wall_units as script,
)


@pytest.fixture
def claim_files(tmp_path, monkeypatch):
    """A claim layer and two claims lists' extractions, under tmp_path."""
    layer = tmp_path / "rw-datasets-by-property.geoparquet"
    layer.write_bytes(b"")
    extracted = tmp_path / "extracted"
    for name in ("old-list", "new-list"):
        (extracted / name).mkdir(parents=True)
        (extracted / name / "reports.csv").write_text("subproject\n")
    monkeypatch.setattr(script, "PROPERTIES_PATH", layer)
    monkeypatch.setattr(script, "CLAIM_REPORTS_EXTRACTED_DIR", extracted)
    monkeypatch.setattr(script, "CLAIMS_LISTS", ("old-list", "new-list"))
    return layer, extracted


def _set_mtime(path, seconds):
    os.utime(path, (seconds, seconds))


def test_a_claim_layer_newer_than_every_extraction_is_read(claim_files):
    layer, extracted = claim_files
    _set_mtime(extracted / "old-list" / "reports.csv", 1_000)
    _set_mtime(extracted / "new-list" / "reports.csv", 2_000)
    _set_mtime(layer, 3_000)
    script.check_records_current()


def test_a_claims_list_extracted_after_the_claim_layer_stops_the_step(claim_files):
    layer, extracted = claim_files
    _set_mtime(extracted / "old-list" / "reports.csv", 1_000)
    _set_mtime(layer, 2_000)
    _set_mtime(extracted / "new-list" / "reports.csv", 3_000)
    with pytest.raises(ValueError, match="new-list"):
        script.check_records_current()
