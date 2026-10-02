"""Reader for QV's rating roll extract for the four Wellington councils.

Sensitive:
    Supplied directly by QV as sensitive data. Content derived from it --
    summaries, statistics, model results -- may be published, but the roll
    itself may not be reproduced: never commit or publish it, a sample of its
    rows, or its records re-tabulated, such as one row per rating unit.

    It must be destroyed at the end of the project, and that covers every copy:
    the one on T: under ``SourceMaterial/SENSITIVE``, the mirror
    :func:`qv_rating_roll_path` keeps in the local tdrive_sync cache
    (``.tdrivecache``), and any extract of its rows.

One row per rating unit, across Porirua (QV district 44), Upper Hutt (45), Hutt
City (46) and Wellington City (47): 167,369 units in the 2026-10-02 supply.
Each council's roll carries its own revaluation date, from September 2024 for
Wellington City to September 2025 for Porirua, so values compared across
councils are compared across dates.

The files carry no header, so every column name here is assigned rather than
supplied. The fields come in the order of the District Valuation Roll under the
Rating Valuations Rules 2008, which is also the order of the open LINZ
valuation roll that :func:`landloss.io.readers.get_nz_district_valuation_roll`
reads, and they are named with LINZ's column names wherever the values line up
with LINZ's, so code written against one roll reads the other.
``no_of_bedrooms`` is inferred, ``certificates_of_title`` and ``qpid`` are named
for what they hold, and the rest are ``field_NN`` by position, because their
meaning is unknown. ``README.md`` beside the files on T: gives the evidence
field by field, and a field specification from QV would settle the rest.

The files are DOS text (cp437, where "m²" is byte 0xFD) and unquoted: the odd
``"`` inside a legal description is text, not a quote.
"""

import csv
from pathlib import Path

import pandas as pd

import tdrive_sync
from landloss.domain import constants

# The 67 fields, in file order. See the module docstring for how they were named.
_COLUMNS = (
    "valuation_no_roll",
    "valuation_no_assessment",
    "valuation_no_suffix",
    "district_ta_code",
    "situation_number",
    "additional_situation_number",
    "situation_name",
    "legal_description",
    "land_area",
    "property_category",
    "ownership_code",
    "current_effective_valuation_date",
    "capital_value",
    "improvements_value",
    "land_value",
    "trees",
    "field_17",
    "field_18",
    "field_19",
    "field_20",
    "field_21",
    "field_22",
    "field_23",
    "no_of_bedrooms",
    "field_25",
    "field_26",
    "field_27",
    "improvements_description",
    "certificates_of_title",
    "field_30",
    "zoning",
    "actual_property_use",
    "units_of_use",
    "off_street_parking",
    "building_age_indicator",
    "building_condition_indicator",
    "building_construction_indicator",
    "building_site_coverage",
    "building_total_floor_area",
    "mass_contour",
    "mass_view",
    "mass_scope_of_view",
    "mass_total_living_area",
    "mass_deck",
    "mass_workshop_laundry",
    "mass_other_improvements",
    "mass_garage_freestanding",
    "mass_garaged_under_main_roof",
    "production",
    "sale_group",
    *(f"field_{position}" for position in range(51, 65)),
    "qpid",
    "field_66",
    "field_67",
)

# Counts, areas and dollars. Nullable, so a blank stays blank, and parsed
# strictly, so a resupply carrying text in one of them fails the read.
_INTEGER_COLUMNS = (
    "capital_value",
    "improvements_value",
    "land_value",
    "trees",
    "no_of_bedrooms",
    "units_of_use",
    "off_street_parking",
    "building_site_coverage",
    "building_total_floor_area",
    "mass_garage_freestanding",
    "mass_garaged_under_main_roof",
    "production",
    "qpid",
    "field_66",
    "field_67",
)
# Land area is in hectares, to four places; living area is supplied with four
# places too, although every value seen is whole.
_FLOAT_COLUMNS = ("land_area", "mass_total_living_area")

_FLAGS = {"Y": True, "N": False}
_FLAG_COLUMNS = ("mass_deck", "mass_workshop_laundry", "mass_other_improvements")

_DATE_COLUMN = "current_effective_valuation_date"
_DATE_FORMAT = "%d%m%Y"


def qv_rating_roll_path(fname: str, *, copy_to_local: bool = True) -> Path:
    """Resolve one council's file of the QV rating roll, caching it locally.

    Args:
        fname: The file's name below :data:`QV_RATING_ROLL_SOURCE_DIR`, one of
            the values of :data:`QV_RATING_ROLL_FILES`.
        copy_to_local: Whether to mirror the file into the local cache, and
            refresh that copy when the one on T: has changed. The cached copy
            is as sensitive as the original; see the module docstring.

    Returns:
        The path to read: the local cache copy where there is one, otherwise the
        file on T:.
    """
    return tdrive_sync.get_source_mat(
        f"{constants.QV_RATING_ROLL_SOURCE_DIR}/{fname}", copy_to_local=copy_to_local
    )


def _read_council(district: str, fname: str, *, copy_to_local: bool) -> pd.DataFrame:
    """Read one council's file, every field as stripped text, blanks as missing."""
    path = qv_rating_roll_path(fname, copy_to_local=copy_to_local)
    raw = pd.read_csv(
        path,
        sep="|",
        header=None,
        dtype="string",
        encoding="cp437",
        quoting=csv.QUOTE_NONE,
        keep_default_na=False,
        na_values=[""],
    )

    if raw.shape[1] != len(_COLUMNS):
        msg = (
            f"{path.name} has {raw.shape[1]} fields per row, but this reader was "
            f"written against {len(_COLUMNS)}. Check what changed in the supply "
            "before updating the reader to match."
        )
        raise ValueError(msg)
    raw.columns = list(_COLUMNS)

    # Text fields are padded in places ("DWG OBS OI " beside "DWG OBS OI"), and a
    # field holding only spaces is as blank as an empty one.
    raw = raw.apply(lambda column: column.str.strip().replace("", pd.NA))

    districts = set(raw["district_ta_code"].dropna())
    if districts != {district}:
        msg = (
            f"{path.name} is filed as QV district {district} but carries "
            f"district codes {sorted(districts)}."
        )
        raise ValueError(msg)
    return raw


def get_qv_rating_roll(*, copy_to_local: bool = True) -> pd.DataFrame:
    """Read QV's rating roll for the four Wellington councils, one row per unit.

    Sensitive:
        Supplied directly by QV as sensitive data. Summaries and results derived
        from it may be published; the roll, any of its rows, and its records
        re-tabulated may not be reproduced. It is destroyed at the end of the
        project, with the local cache copy and any extract of its rows. See the
        module docstring.

    The fields this study reads it for, and what is known about each:

    - ``land_value`` and ``capital_value``, in dollars at each council's
      ``current_effective_valuation_date``.
    - ``land_area``, in hectares, and 0 for a unit on shared land such as a
      flat or apartment, whose land sits with the parent title.
    - ``building_age_indicator``, the decade the main building was built, as
      ``"196"`` for the 1960s, with ``XXX`` where it is unknown and ``PRE``
      and ``AAA`` on a few units. It is filled on every residential dwelling.
    - ``qpid``, QV's property identifier, which joins one to one to the
      ``qpid`` of :func:`landloss.io.nzmm_land_attributes.get_nzmm_land_attributes`.

    Source:
        Supplied to this project directly by QV as sensitive data, and held on
        T: under ``SourceMaterial/SENSITIVE``. Not open data.

    Args:
        copy_to_local: Whether to mirror each file into the local cache.

    Returns:
        The four councils' rolls stacked, columns as in :data:`_COLUMNS`: text
        stripped of padding, with blanks as missing; counts, areas and dollars
        as nullable integers; ``land_area`` and ``mass_total_living_area`` as
        floats; the three ``mass_`` Y/N flags as nullable booleans; and
        ``current_effective_valuation_date`` as a date.

    Raises:
        ValueError: If a file does not carry the 67 fields this reader was
            written against, carries a district code other than the one it is
            filed under, or a flag column carries anything but Y, N or a blank.
    """
    roll = pd.concat(
        [
            _read_council(district, fname, copy_to_local=copy_to_local)
            for district, fname in constants.QV_RATING_ROLL_FILES.items()
        ],
        ignore_index=True,
    )

    for column in _FLAG_COLUMNS:
        unexpected = set(roll[column].dropna()) - set(_FLAGS)
        if unexpected:
            msg = (
                f"The QV rating roll's {column} carries {sorted(unexpected)}, but "
                f"only {sorted(_FLAGS)} or a blank are understood."
            )
            raise ValueError(msg)
        roll[column] = roll[column].map(_FLAGS).astype("boolean")

    for column in _INTEGER_COLUMNS:
        roll[column] = pd.to_numeric(roll[column]).astype("Int64")
    for column in _FLOAT_COLUMNS:
        roll[column] = pd.to_numeric(roll[column]).astype("Float64")
    roll[_DATE_COLUMN] = pd.to_datetime(roll[_DATE_COLUMN], format=_DATE_FORMAT)

    return roll
