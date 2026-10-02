"""Tests for reading the NZMM address land attributes extract.

The extract is sensitive, so nothing here is taken from it: every file is written
to ``tmp_path`` by the test that reads it, from made-up rows in the supplied
layout, and ``nzmm_land_attributes_path`` -- the one place that would reach T: --
is replaced. Nothing touches the network or the network drive.
"""

import pandas as pd
import pytest

from landloss.domain import constants
from landloss.io import nzmm_land_attributes

HEADER = (
    "Property_ID|QPID|Full_Address|Full_Primary_Road_Name|Locality_Name|"
    "Town_Name|TA_Name|LandArea|RetainingWallInd|MeanSlope|SwimmingPool"
)

# Two addresses on property 1, the second supplied twice; one address on
# property 2 with no land area; and one address matched to no property.
ROWS = (
    '1|11|"5"|"EXAMPLE STREET"|"SUBURB"|"TOWN"|"CITY"|600|"N"|1|"N"',
    '1|11|"5A"|"EXAMPLE STREET"|"SUBURB"|"TOWN"|"CITY"|600|"N"|1|"N"',
    '1|11|"5A"|"EXAMPLE STREET"|"SUBURB"|"TOWN"|"CITY"|600|"N"|1|"N"',
    '2|22|"1/7"|"SAMPLE ROAD"|"NA"|"TOWN"|"CITY"||"Y"|3|"Y"',
    '||"9"|"SAMPLE ROAD"|"SUBURB"||"CITY"||||',
)


def write_extract(path, header=HEADER, rows=ROWS):
    """Write a pipe-delimited extract in the supplied layout, CRLF as supplied."""
    path.write_text("\r\n".join([header, *rows]) + "\r\n", encoding="ascii")
    return path


@pytest.fixture
def supplied(monkeypatch):
    """Return a function that stands a written extract in for the one on T:."""

    def use(path):
        monkeypatch.setattr(
            nzmm_land_attributes,
            "nzmm_land_attributes_path",
            lambda *_, **__: path,
        )
        return path

    return use


def test_columns_are_renamed_and_typed(tmp_path, supplied) -> None:
    """Integers stay integers through blanks, and the Y/N flags become booleans."""
    supplied(write_extract(tmp_path / "extract.txt"))

    df = nzmm_land_attributes.get_nzmm_land_attributes()

    assert list(df.columns) == [
        "property_id",
        "qpid",
        "full_address",
        "road_name",
        "locality",
        "town",
        "territorial_authority",
        "land_area_m2",
        "has_retaining_wall",
        "mean_slope_class",
        "has_swimming_pool",
    ]
    assert df["property_id"].dtype == "Int64"
    assert df["land_area_m2"].dtype == "Int64"
    assert df["mean_slope_class"].dtype == "Int64"
    assert df["has_retaining_wall"].dtype == "boolean"
    assert df["full_address"].dtype == "string"
    assert df["has_retaining_wall"].tolist() == [False, False, True, pd.NA]
    assert df["land_area_m2"].tolist() == [600, 600, pd.NA, pd.NA]


def test_exact_repeats_are_dropped_but_a_propertys_other_addresses_are_kept(
    tmp_path, supplied
) -> None:
    """Only a full repeat goes: two addresses on one property are two rows."""
    supplied(write_extract(tmp_path / "extract.txt"))

    df = nzmm_land_attributes.get_nzmm_land_attributes()

    assert len(df) == 4
    assert df["full_address"].tolist() == ["5", "5A", "1/7", "9"]
    assert df.index.tolist() == [0, 1, 2, 3]


def test_only_an_empty_field_counts_as_missing(tmp_path, supplied) -> None:
    """A locality spelt "NA" is text, not a blank."""
    supplied(write_extract(tmp_path / "extract.txt"))

    df = nzmm_land_attributes.get_nzmm_land_attributes()

    assert df["locality"].tolist() == ["SUBURB", "SUBURB", "NA", "SUBURB"]
    assert df["town"].isna().tolist() == [False, False, False, True]


def test_a_flag_other_than_y_or_n_is_refused(tmp_path, supplied) -> None:
    """A resupply that codes the flags differently fails rather than reads as NA."""
    rows = ('1|11|"5"|"EXAMPLE STREET"|"SUBURB"|"TOWN"|"CITY"|600|"U"|1|"N"',)
    supplied(write_extract(tmp_path / "extract.txt", rows=rows))

    with pytest.raises(ValueError, match="RetainingWallInd carries \\['U'\\]"):
        nzmm_land_attributes.get_nzmm_land_attributes()


def test_a_changed_header_is_refused(tmp_path, supplied) -> None:
    """A renamed column fails the read rather than arriving under the old name."""
    header = HEADER.replace("MeanSlope", "SlopeClass")
    supplied(write_extract(tmp_path / "extract.txt", header=header))

    with pytest.raises(ValueError, match="this reader was written against"):
        nzmm_land_attributes.get_nzmm_land_attributes()


def test_the_path_resolves_through_source_material_and_caches_by_default(
    tmp_path, monkeypatch
) -> None:
    """The file is read from SourceMaterial, mirrored into the local cache."""
    calls = []

    def record(relative_path, **kwargs):
        calls.append((relative_path, kwargs))
        return tmp_path / "resolved.txt"

    monkeypatch.setattr("tdrive_sync.get_source_mat", record)

    result = nzmm_land_attributes.nzmm_land_attributes_path()

    assert calls == [
        (constants.NZMM_LAND_ATTRIBUTES_SOURCE_PATH, {"copy_to_local": True})
    ]
    assert result == tmp_path / "resolved.txt"
