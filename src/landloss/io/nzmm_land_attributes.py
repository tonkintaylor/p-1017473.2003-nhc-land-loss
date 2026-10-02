"""Reader for the NZMM address land attributes extract for the Wellington councils.

Sensitive:
    Supplied by NHC as sensitive data. Content derived from it -- summaries,
    statistics, model results -- may be published, but the file itself may not
    be reproduced: never commit or publish it, a sample of its rows, or its
    records re-tabulated, such as one row per property.

    It must be destroyed at the end of the project, and that covers every copy:
    the one on T: under ``SourceMaterial/SENSITIVE``, the mirror
    :func:`nzmm_land_attributes_path` keeps in the local tdrive_sync cache
    (``.tdrivecache``), and any extract of its rows.

One row per address, against the property it sits on, across Wellington City,
Lower Hutt, Porirua and Upper Hutt. Each property carries four land attributes
-- land area, a retaining wall flag, a mean slope class and a swimming pool
flag -- that repeat on every one of its addresses, so anything counted per
property has to be counted on ``property_id``, not on rows.

The file is pipe-delimited, with text fields quoted and blanks left empty.
About a quarter of its rows are exact copies of another row -- one Hutt Central
property alone appears 12,888 times over 345 addresses -- so they are dropped on
the way in: a repeat carries nothing, and left in it weights every row count
towards the few large multi-unit properties where it happens.
"""

from pathlib import Path

import pandas as pd

import tdrive_sync
from landloss.domain import constants

# The supplied header, renamed to snake_case and, where the value has a unit,
# carrying it. Read in this order, so a resupply with columns added, dropped or
# renamed is refused rather than half read.
_COLUMNS = {
    "Property_ID": "property_id",
    "QPID": "qpid",
    "Full_Address": "full_address",
    "Full_Primary_Road_Name": "road_name",
    "Locality_Name": "locality",
    "Town_Name": "town",
    "TA_Name": "territorial_authority",
    "LandArea": "land_area_m2",
    "RetainingWallInd": "has_retaining_wall",
    "MeanSlope": "mean_slope_class",
    "SwimmingPool": "has_swimming_pool",
}

# Integer columns as nullable integers, so a property with no land area stays
# blank rather than turning the column to float, and a resupply carrying a
# decimal fails the read rather than being truncated.
_INTEGER_COLUMNS = ("Property_ID", "QPID", "LandArea", "MeanSlope")
_DTYPES = dict.fromkeys(_COLUMNS, "string") | dict.fromkeys(_INTEGER_COLUMNS, "Int64")

# The supplier's Y/N indicators, and what each means here.
_FLAGS = {"Y": True, "N": False}
_FLAG_COLUMNS = ("RetainingWallInd", "SwimmingPool")


def nzmm_land_attributes_path(*, copy_to_local: bool = True) -> Path:
    """Resolve the NZMM land attributes file, caching it locally.

    Args:
        copy_to_local: Whether to mirror the file into the local cache, and
            refresh that copy when the one on T: has changed. The cached copy
            is as sensitive as the original; see the module docstring.

    Returns:
        The path to read: the local cache copy where there is one, otherwise the
        file on T:.
    """
    return tdrive_sync.get_source_mat(
        constants.NZMM_LAND_ATTRIBUTES_SOURCE_PATH, copy_to_local=copy_to_local
    )


def get_nzmm_land_attributes(*, copy_to_local: bool = True) -> pd.DataFrame:
    """Read the NZMM address land attributes, one row per distinct address row.

    Sensitive:
        Supplied by NHC as sensitive data. Summaries and results derived from
        it may be published; the file, any of its rows, and its records
        re-tabulated may not be reproduced. It is destroyed at the end of the
        project, with the local cache copy and any extract of its rows. See the
        module docstring.

    What is and is not known about the attributes, from the extract itself
    rather than from any documentation, so each needs confirming with the
    supplier before a number derived from it is quoted:

    - ``property_id`` and ``qpid`` match one to one. Whether ``property_id`` is
      the LINZ property ID the address spine is keyed on is not confirmed.
    - ``land_area_m2`` is taken to be square metres, consistent with a median
      property of about 600. It is blank for about a fifth of properties, most
      of them unit titles.
    - ``mean_slope_class`` is a code, 1 to 3, not a slope. What the classes
      bound is not documented. The share of properties flagged with a retaining
      wall rises with the code, which fits it increasing with steepness.
    - ``has_retaining_wall`` is set on about 3% of properties. How it is
      populated is not documented, so read True as a recorded wall and False
      as no record, not as no wall.
    - Rows with no ``property_id`` carry no attributes, and some properties
      carry none either: the three attribute flags and the slope class are
      blank together or not at all.

    Source:
        Supplied to this project by NHC as sensitive data, and held on T:
        under ``SourceMaterial/SENSITIVE``. Not open data.

    Args:
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The address rows with exact repeats dropped, columns renamed as in
        :data:`_COLUMNS`: the identifiers and ``land_area_m2`` and
        ``mean_slope_class`` as nullable integers, the address fields as text,
        and ``has_retaining_wall`` and ``has_swimming_pool`` as nullable
        booleans. Blanks are missing values throughout.

    Raises:
        ValueError: If the header is not the one this reader was written
            against, or a flag column carries anything but Y, N or a blank.
    """
    path = nzmm_land_attributes_path(copy_to_local=copy_to_local)

    # Everything not named an integer is read as text, and only an empty field
    # counts as missing: pandas' default list would otherwise take a locality or
    # address spelt "NA" for a blank.
    raw = pd.read_csv(
        path,
        sep="|",
        dtype=_DTYPES,
        keep_default_na=False,
        na_values=[""],
    )

    if list(raw.columns) != list(_COLUMNS):
        msg = (
            f"{path.name} has columns {list(raw.columns)}, but this reader was "
            f"written against {list(_COLUMNS)}. Check what changed in the "
            "supply before updating the reader to match."
        )
        raise ValueError(msg)

    for column in _FLAG_COLUMNS:
        unexpected = set(raw[column].dropna()) - set(_FLAGS)
        if unexpected:
            msg = (
                f"{path.name} column {column} carries {sorted(unexpected)}, but "
                f"only {sorted(_FLAGS)} or a blank are understood."
            )
            raise ValueError(msg)
        raw[column] = raw[column].map(_FLAGS).astype("boolean")

    return raw.drop_duplicates(ignore_index=True).rename(columns=_COLUMNS)
