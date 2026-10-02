"""Tests for reading QV's rating roll extract for the Wellington councils.

The roll is sensitive, so nothing here is taken from it: every file is written
to ``tmp_path`` by the test that reads it, from made-up rows laid out field by
field as the supply is, and ``qv_rating_roll_path`` -- the one place that would
reach T: -- is replaced. Nothing touches the network or the network drive.

The rows are built by field position, 1 to 67, rather than from the reader's own
column names, so the tests check the naming instead of repeating it.
"""

import pandas as pd
import pytest

from landloss.domain import constants
from landloss.io import qv_rating_roll

N_FIELDS = 67

# One plausible residential rating unit, by 1-based field position.
TYPICAL = {
    1: "15421",
    2: "100",
    5: "5",
    7: "EXAMPLE ST",
    8: "LOT 1 DP 1",
    9: ".0506",
    10: "RD196B",
    11: "1",
    12: "01092025",
    13: "700000",
    14: "300000",
    15: "400000",
    **dict.fromkeys((17, 18, 19, 20, 25, 26, 27), "0"),
    24: "3",
    28: "DWG OBS OI ",
    29: "WN/1A/1",
    31: "9A",
    32: "91",
    33: "1",
    34: "1",
    35: "196",
    36: "GG",
    37: "WI",
    38: "120",
    39: "160",
    40: "EF",
    41: "N",
    42: "N",
    43: "125.0000",
    44: "Y",
    45: "N",
    46: "N",
    47: "0",
    48: "1",
    49: "0",
    50: "25",
    64: "A",
    66: "650000",
    67: "380000",
}


def make_row(district, qpid, at=None):
    """Return one pipe-delimited row, the typical unit with ``at`` laid over it."""
    fields = {**TYPICAL, 4: district, 65: str(qpid), **(at or {})}
    return "|".join(fields.get(position, "") for position in range(1, N_FIELDS + 1))


@pytest.fixture
def supplied(tmp_path, monkeypatch):
    """Return a function that stands written council files in for those on T:."""

    def use(rows_by_district):
        files = {}
        for district, rows in rows_by_district.items():
            fname = f"Property{district}_test.txt"
            (tmp_path / fname).write_bytes(("\r\n".join(rows) + "\r\n").encode("cp437"))
            files[district] = fname
        monkeypatch.setattr(constants, "QV_RATING_ROLL_FILES", files)
        monkeypatch.setattr(
            qv_rating_roll,
            "qv_rating_roll_path",
            lambda fname, **_: tmp_path / fname,
        )

    return use


def test_fields_are_named_by_position_and_typed(supplied) -> None:
    """The fields the study reads land under their names, in usable types."""
    supplied({"44": [make_row("44", 3038844)]})

    unit = qv_rating_roll.get_qv_rating_roll().iloc[0]

    assert unit["district_ta_code"] == "44"
    assert unit["land_area"] == pytest.approx(0.0506)
    assert unit["capital_value"] == 700_000
    assert unit["land_value"] == 400_000
    assert unit["current_effective_valuation_date"] == pd.Timestamp("2025-09-01")
    assert unit["building_age_indicator"] == "196"
    assert unit["mass_contour"] == "EF"
    assert unit["mass_total_living_area"] == pytest.approx(125.0)
    assert unit["no_of_bedrooms"] == 3
    assert unit["qpid"] == 3038844
    assert unit["field_66"] == 650_000


def test_text_is_stripped_flags_are_booleans_and_blanks_are_missing(
    supplied,
) -> None:
    """Padding goes, Y/N become True/False, and an empty field is missing."""
    supplied({"44": [make_row("44", 1, at={6: "  ", 45: ""})]})

    roll = qv_rating_roll.get_qv_rating_roll()

    assert roll["improvements_description"].tolist() == ["DWG OBS OI"]
    assert roll["mass_deck"].dtype == "boolean"
    assert roll["mass_deck"].tolist() == [True]
    assert roll["mass_other_improvements"].tolist() == [False]
    assert roll["mass_workshop_laundry"].isna().all()
    assert roll["additional_situation_number"].isna().all()
    assert roll["valuation_no_suffix"].isna().all()


def test_the_councils_are_stacked_in_file_order(supplied) -> None:
    """Each council's file is read and the rows follow one another."""
    supplied(
        {
            "44": [make_row("44", 1), make_row("44", 2)],
            "47": [make_row("47", 3, at={12: "01092024"})],
        }
    )

    roll = qv_rating_roll.get_qv_rating_roll()

    assert roll["district_ta_code"].tolist() == ["44", "44", "47"]
    assert roll["qpid"].tolist() == [1, 2, 3]
    assert roll.index.tolist() == [0, 1, 2]


def test_dos_text_and_a_literal_quote_are_read_as_supplied(supplied) -> None:
    """The cp437 squared sign decodes, and a quote mark is text, not quoting."""
    legal = 'FLAT 1 ON LOT 2 "A" SO 1 HAVING 1/2 SH IN 766m²'
    supplied({"46": [make_row("46", 1, at={8: legal, 9: ".0000"})]})

    unit = qv_rating_roll.get_qv_rating_roll().iloc[0]

    assert unit["legal_description"] == legal
    assert unit["land_area"] == 0


def test_a_row_of_the_wrong_width_is_refused(supplied) -> None:
    """A resupply with a field added or dropped fails rather than shifting."""
    supplied({"44": [make_row("44", 1)[: -len("|380000")]]})

    with pytest.raises(ValueError, match="has 66 fields per row"):
        qv_rating_roll.get_qv_rating_roll()


def test_a_file_carrying_another_councils_code_is_refused(supplied) -> None:
    """A file filed under one district but holding another's units fails."""
    supplied({"44": [make_row("44", 1), make_row("45", 2)]})

    with pytest.raises(ValueError, match="filed as QV district 44"):
        qv_rating_roll.get_qv_rating_roll()


def test_a_flag_other_than_y_or_n_is_refused(supplied) -> None:
    """A recoded flag fails the read rather than arriving as missing."""
    supplied({"44": [make_row("44", 1, at={44: "U"})]})

    with pytest.raises(ValueError, match="mass_deck carries \\['U'\\]"):
        qv_rating_roll.get_qv_rating_roll()


def test_the_path_resolves_through_source_material_and_caches_by_default(
    tmp_path, monkeypatch
) -> None:
    """Each file is read from the roll's SourceMaterial folder, cached locally."""
    calls = []

    def record(relative_path, **kwargs):
        calls.append((relative_path, kwargs))
        return tmp_path / "resolved.txt"

    monkeypatch.setattr("tdrive_sync.get_source_mat", record)

    result = qv_rating_roll.qv_rating_roll_path("Property44_20261002.txt")

    assert calls == [
        (
            f"{constants.QV_RATING_ROLL_SOURCE_DIR}/Property44_20261002.txt",
            {"copy_to_local": True},
        )
    ]
    assert result == tmp_path / "resolved.txt"
