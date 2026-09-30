r"""Reader for the TS1170.5:2025 site demand parameters by grid point (Table 3.2).

SNZ TS 1170.5:2025 publishes its seismic demand as four parameters per site
class and annual probability of exceedance (APoE): PGA, the short-period
spectral acceleration Sa,s, and the two corner periods Tc and Td. Table 3.2 gives
them on a 0.1 x 0.1 degree latitude/longitude grid covering New Zealand, and
applies everywhere outside the urban and rural settlement boundaries of the
TS's Figure 3.2 (Table 3.1, by location name, applies inside them). Clause
3.1.2 says to take the nearest grid point.

The four parameters are not a spectrum by themselves: Sa,s is the height of the
constant-acceleration plateau, not a value at any one period, and Tc and Td are
the periods where the spectrum's shape changes. Sa(T) at a given period comes
from them through Equations 3.2 to 3.5 of clause 3.1.2.

The table carries Site Classes I to VI. There is no Site Class VII: the TS
requires a site-specific response analysis for it (clause 3.1.3.2), floored at
the Site Class VI spectrum. Site classes are returned as the integers 1 to 6,
the convention :mod:`landloss.io.nlm` uses for the NLM's seismic-standard grids.

Held on the cross-project data library, like :mod:`landloss.io.gfdb`, but read
through ``tdrive_sync.get_cached`` rather than straight off ``R:``: it is one
CSV, the shape the local cache mirroring is built around, and the cache path
drops the drive letter, so the local copy lives at
``.tdrivecache/DataLibrary/210.14_seismic_demands_NZ_TS1170_5/v1/``.

Source:
    Standards New Zealand (2025). SNZ TS 1170.5:2025 Structural design
    actions -- Part 5: Earthquake actions -- New Zealand. Table 3.2, site
    demand parameters by grid point, as distributed with the TS's digital
    files ([TS1170.5_README_2025]).

Licence:
    Copyright Standards New Zealand; the TS is accessed under MBIE's
    sponsored copyright licence. Confirm the terms the digital table was
    obtained under before redistributing it.
"""

from pathlib import Path

import pandas as pd
import rioxarray
import xarray as xr

import tdrive_sync

# The catalogue entry's v1 folder, read directly for the same reason as
# landloss.io.gfdb.GFDB_V4_DIR: there is no Master/ pointer on this share.
TS1170_DIR = Path(r"R:\DataLibrary\210.14_seismic_demands_NZ_TS1170_5\v1")

TS1170_TABLE_3_2_FNAME = "TS1170-5_Table3-2_2025-3.csv"

# The site classes the table carries, in the Roman numerals its column
# prefixes use, mapped to the integers returned.
SITE_CLASS_NUMERALS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}

# The annual probabilities of exceedance the table carries, as return periods.
RETURN_PERIODS_YR = (25, 50, 100, 250, 500, 1000, 2500)

# The grids derived from the table by
# src/scripts/landloss/hazard/shaking/static_data_gen/gen_ts1170_grids.py, one
# GeoTIFF per measure, return period and site class, each measure in its own
# folder beside the table: Sa(1.0 s) from the clause 3.1.2 spectrum, and PGA as
# the table gives it.
TS1170_GRID_MEASURES = ("sa_t1", "pga")
TS1170_SA_T1_DIR = TS1170_DIR / "sa_t1"
TS1170_PGA_DIR = TS1170_DIR / "pga"
TS1170_GRID_FNAME = "{measure}_{return_period_yr}yr_site_class_{site_class}.tif"

# The per-site-class column suffixes and the names they are returned under.
_PARAMETER_COLUMNS = {
    "PGA": "pga_g",
    "Sas": "sa_s_g",
    "Tc": "tc_s",
    "Td": "td_s",
}


def ts1170_table_3_2_path(*, copy_to_local: bool = True) -> Path:
    """Resolve the Table 3.2 CSV against its local cache mirror.

    Args:
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The path to read: the local cache copy where one exists, otherwise the
        file on ``R:``.
    """
    return tdrive_sync.get_cached(
        TS1170_DIR / TS1170_TABLE_3_2_FNAME, copy_to_local=copy_to_local
    )


def read_ts1170_table_3_2_csv(path: Path) -> pd.DataFrame:
    """Parse a Table 3.2 CSV into one row per grid point, APoE and site class.

    The delivered table is wide: one row per grid point and APoE, with four
    columns per site class (``I-PGA``, ``I-Sas``, ``I-Tc``, ``I-Td``, then
    ``II-PGA`` and so on). This stacks the site classes into rows, so a single
    site class is a filter rather than a choice of columns.

    Args:
        path: The CSV to read.

    Returns:
        A DataFrame carrying ``latitude`` and ``longitude`` (degrees, the grid
        point), ``apoe`` (as delivered, e.g. ``"1/2500"``),
        ``return_period_yr`` (the APoE's denominator), ``magnitude`` (M, clause
        3.3.2), ``fault_distance_km`` (D, the distance to the nearest Table 3.4
        major fault used for vertical spectra in clause 3.2, kept as the
        delivered text because it is capped at ``">20"``; missing where the
        table gives ``"n/a"``), ``site_class`` (1 to 6), ``pga_g``, ``sa_s_g``,
        ``tc_s`` and ``td_s``.
    """
    # The file starts with a UTF-8 byte order mark, which would otherwise end
    # up in the first column's name. D is pinned to text so its type does not
    # depend on whether a ">20" happens to be among the rows read.
    wide = pd.read_csv(path, encoding="utf-8-sig", na_values=["n/a"], dtype={"D": str})
    wide["apoe"] = wide["apoe"].str.strip()

    shared = pd.DataFrame(
        {
            "latitude": wide["latitude"],
            "longitude": wide["longitude"],
            "apoe": wide["apoe"],
            "return_period_yr": wide["apoe"].str.split("/").str[1].astype(int),
            "magnitude": wide["M"],
            "fault_distance_km": wide["D"],
        }
    )

    per_class = []
    for numeral, site_class in SITE_CLASS_NUMERALS.items():
        params = wide[[f"{numeral}-{suffix}" for suffix in _PARAMETER_COLUMNS]]
        params.columns = list(_PARAMETER_COLUMNS.values())
        per_class.append(shared.assign(site_class=site_class).join(params))

    return pd.concat(per_class, ignore_index=True)


def get_ts1170_table_3_2(*, copy_to_local: bool = True) -> pd.DataFrame:
    """Read TS1170.5:2025 Table 3.2, the site demand parameters by grid point.

    Source:
        SNZ TS 1170.5:2025 Table 3.2, on the T+T data library -- see the
        module docstring.

    Args:
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        One row per grid point, APoE and site class; see
        :func:`read_ts1170_table_3_2_csv` for the columns.
    """
    return read_ts1170_table_3_2_csv(ts1170_table_3_2_path(copy_to_local=copy_to_local))


def ts1170_grid_dir(measure: str) -> Path:
    """Return the folder one measure's grids are held in on ``R:``.

    Args:
        measure: One of :data:`TS1170_GRID_MEASURES`.

    Returns:
        The folder below :data:`TS1170_DIR`.

    Raises:
        ValueError: If no grids of that measure are generated.
    """
    if measure not in TS1170_GRID_MEASURES:
        msg = f"No TS1170.5 grids of {measure!r}; expected one of "
        msg += f"{TS1170_GRID_MEASURES}."
        raise ValueError(msg)
    return TS1170_DIR / measure


def ts1170_grid_fname(measure: str, return_period_yr: int, site_class: int) -> str:
    """Return the file name of one grid.

    Named as the NLM names its seismic-standard grids, e.g.
    ``pga_2500yr_site_class_5.tif``.

    Args:
        measure: One of :data:`TS1170_GRID_MEASURES`.
        return_period_yr: One of :data:`RETURN_PERIODS_YR`.
        site_class: The TS1170.5 site class, 1 to 6.

    Returns:
        The file name below :func:`ts1170_grid_dir`.

    Raises:
        ValueError: If no grids of that measure are generated, or the table
            carries no such return period or site class.
    """
    ts1170_grid_dir(measure)
    if return_period_yr not in RETURN_PERIODS_YR:
        msg = f"Return period {return_period_yr!r} is not one of "
        msg += f"{RETURN_PERIODS_YR}."
        raise ValueError(msg)
    if site_class not in SITE_CLASS_NUMERALS.values():
        msg = f"Site class {site_class!r} is not one of "
        msg += f"{tuple(SITE_CLASS_NUMERALS.values())}."
        raise ValueError(msg)
    return TS1170_GRID_FNAME.format(
        measure=measure, return_period_yr=return_period_yr, site_class=site_class
    )


def ts1170_sa_t1_fname(return_period_yr: int, site_class: int) -> str:
    """Return the file name of one Sa(1.0 s) grid; see :func:`ts1170_grid_fname`."""
    return ts1170_grid_fname("sa_t1", return_period_yr, site_class)


def ts1170_pga_fname(return_period_yr: int, site_class: int) -> str:
    """Return the file name of one PGA grid; see :func:`ts1170_grid_fname`."""
    return ts1170_grid_fname("pga", return_period_yr, site_class)


def get_ts1170_grid(
    measure: str,
    return_period_yr: int,
    site_class: int,
    *,
    copy_to_local: bool = True,
) -> xr.DataArray:
    """Read one TS1170.5 grid at a return period and site class.

    Built from Table 3.2 by ``gen_ts1170_grids.py`` on the same NZTM grid,
    about 9,930 m a cell, as the NLM's seismic-standard grids
    (:mod:`landloss.io.nlm`).

    Source:
        Derived from SNZ TS 1170.5:2025 Table 3.2 -- see the module
        docstring. The generating script is kept beside the grids on ``R:``.

    Args:
        measure: One of :data:`TS1170_GRID_MEASURES`.
        return_period_yr: One of :data:`RETURN_PERIODS_YR`.
        site_class: The TS1170.5 site class, 1 to 6.
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The grid in g, in EPSG:2193, nodata as NaN.
    """
    path = tdrive_sync.get_cached(
        ts1170_grid_dir(measure)
        / ts1170_grid_fname(measure, return_period_yr, site_class),
        copy_to_local=copy_to_local,
    )
    # Loaded inside a context manager for the reason given in
    # landloss.io.nlm.get_nlm_scenario_raster: a lazily-opened GDAL handle
    # finalised at interpreter shutdown fails noisily on Windows.
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def get_ts1170_sa_t1(
    return_period_yr: int, site_class: int, *, copy_to_local: bool = True
) -> xr.DataArray:
    """Read the TS1170.5 Sa(1.0 s) grid at one return period and site class.

    The spectral acceleration at a 1 second period from the clause 3.1.2
    spectrum, which the shaking module converts to PGV
    (``landloss.hazard.shaking.pgv``). See :func:`get_ts1170_grid`.

    Args:
        return_period_yr: One of :data:`RETURN_PERIODS_YR`.
        site_class: The TS1170.5 site class, 1 to 6.
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The Sa(1.0 s) grid in g, in EPSG:2193, nodata as NaN.
    """
    return get_ts1170_grid(
        "sa_t1", return_period_yr, site_class, copy_to_local=copy_to_local
    )


def get_ts1170_pga(
    return_period_yr: int, site_class: int, *, copy_to_local: bool = True
) -> xr.DataArray:
    """Read the TS1170.5 PGA grid at one return period and site class.

    PGA as Table 3.2 gives it (clause 3.3.1). At 2500 years and site class 5
    this is the NLM's ``pga_2500yr_site_class_5.tif``, cell for cell. See
    :func:`get_ts1170_grid`.

    Args:
        return_period_yr: One of :data:`RETURN_PERIODS_YR`.
        site_class: The TS1170.5 site class, 1 to 6.
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The PGA grid in g, in EPSG:2193, nodata as NaN.
    """
    return get_ts1170_grid(
        "pga", return_period_yr, site_class, copy_to_local=copy_to_local
    )
