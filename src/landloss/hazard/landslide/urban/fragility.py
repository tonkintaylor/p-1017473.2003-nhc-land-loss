"""Fragility of an urban failure polygon on peak ground velocity.

What belongs here: the reader of the anchor table
(``urban-fragility-anchors.csv`` in :mod:`landloss.io.assets`), the
conversion of a PGA-based median by the PGV/PGA ratio, the localised (no
wall) median from the susceptibility rating, the rate factor, the row assembly
:func:`assign_fragility` that landslide step 8 writes out, and the fit of the
localised median to the anchor table that the urban validation draws. The
lognormal failure probability lives in
:mod:`landloss.hazard.landslide.urban.lognormal` and is re-exported here; the
wall curves are read from
:mod:`landloss.hazard.landslide.urban.wall_type_fragility`. Used by landslide
step 8 (``s8_urban_slope_fragility``), the urban validations and
``landloss.vul.shaking.fragility`` for flat-land walls.

Every fragility is a lognormal cumulative distribution on PGV in m/s,
``P(fail | PGV) = Phi(ln(PGV / theta) / beta)`` (contract section 6 of
``.agents/plans/urban-slope-build-contract.md``). A fragility returns a
probability because that is what a fragility is: the realisation draws
against it.

A polygon with a wall on its edge takes the wall type curve for the wall's
type and height class [koutsoupaki_2023], its PGA median scaled by the wall's own
fill or cut position, then converted from PGA to PGV by the study's own ratio
at the polygon's representative point. The wall is any the
world drew on the line, insured or not (decision 36 of the build contract):
an uninsured wall holds the slope all the same, and only its ``rw_id`` is
null. A polygon without a
wall takes a localised median that falls with its continuous Kingsbury rating
[kingsbury_1995]. Both are divided by the topographic amplification factor
and multiplied by the rate factor of the run's setting (plan sections 4.3 and
4.4).

The two localised constants are placeholders (contract section 7.7) until
the anchoring of plan section 6 sets them: :func:`fit_localised_fragility`
is the fit, run by ``hazard/landslide/validations/urban/``, and the numbers it
prints replace the constants here.
"""

from pathlib import Path
from typing import NamedTuple

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
import xarray as xr
from scipy.stats import norm

from landloss.domain import constants
from landloss.domain.loss_contract import RW_ID_COLUMN
from landloss.exposure.rw.beta_population import SIZE_CLASSES
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import geometry, wall_type_fragility
from landloss.hazard.landslide.urban.lognormal import (  # noqa: F401 -- re-exported
    PGA_IM,
    lognormal_failure_probability,
)
from landloss.io import ASSETS_DIR

# The intensity measure every urban fragility is on; the wall curves are
# published on PGA_IM and converted.
IM = "pgv_m_s"

# What a row's median came from (contract section 6).
FRAGILITY_BASES = ("wall", "localised")
WALL_BASIS, LOCALISED_BASIS = FRAGILITY_BASES

URBAN_FRAGILITY_ANCHORS_PATH = ASSETS_DIR / "urban-fragility-anchors.csv"

# The localised (no wall) median, m/s, at a rating of 0 and at MAX_RATING: a
# log-linear fall between them (contract section 7.7). Placeholders, set by the
# anchoring. The area calibration agreed with the project lead on 2026-10-07
# (hazard/landslide/validations/urban/table_urban_area_calibration.py) fits
# 0.334 and 0.0668 with a dispersion of 1.01, but every check rejects that fit
# (urban_area_calibration_findings.md beside the script), so it is not adopted
# here until the lead decides. The names are the contract's, so they carry no
# beta_ prefix although they are placeholders.
LOCALISED_THETA_AT_ZERO_RATING_M_S = 3.0
LOCALISED_THETA_AT_MAX_RATING_M_S = 0.6

# The columns of the anchor table (contract section 8.2), with the measure
# and polygon selection columns of the area calibration (2026-10-07).
ANCHOR_COLUMNS = (
    "anchor_id",
    "source",
    "measure",
    "zone",
    "rating_min",
    "rating_max",
    "applies_to",
    "slope_min_deg",
    "slope_max_deg",
    "material",
    "demand_at",
    "scenario",
    "pga_rock_g_min",
    "pga_rock_g_max",
    "class_word",
    "fail_fraction",
    "set_by",
    "basis",
)

# What an anchor's fail_fraction is a share of: the damaged share of a
# Kingsbury zone's non-flat area, or the share of the matching polygons that
# fail (landloss.hazard.landslide.urban.area_calibration).
ANCHOR_MEASURES = ("zone_area", "polygon")
ZONE_AREA_MEASURE, POLYGON_MEASURE = ANCHOR_MEASURES

# Which polygons a polygon anchor speaks about, by the cut or fill position of
# their wall unit; "all" takes every one.
ANCHOR_APPLIES_TO = ("all", "cut", "fill")

# Where an anchor's PGA was measured: on rock (a scenario's bedrock PGA,
# converted to the polygon's site and amplified), or at a recording site (a
# station value that already carries the amplification).
ANCHOR_DEMAND_AT = ("rock", "site")
ROCK_DEMAND, SITE_DEMAND = ANCHOR_DEMAND_AT

# The model file's columns, less world_id, in the order contract section 3.8
# gives them; the step inserts world_id after slope_id.
STATE_COLUMN = "wall_state"
WALL_TYPE_COLUMN = "wall_type"
SIZE_CLASS_COLUMN = "size_class"
# The drawn wall's height, which picks its height class in the wall type
# table (the lead, 2026-10-07); read off the drawn walls, not carried onto the
# model file.
WALL_HEIGHT_COLUMN = "height_m"
MODEL_COLUMNS = (
    geometry.SLOPE_ID_COLUMN,
    geometry.WALL_LINE_ID_COLUMN,
    geometry.WALL_LINE_IDS_COLUMN,
    RW_ID_COLUMN,
    STATE_COLUMN,
    WALL_TYPE_COLUMN,
    SIZE_CLASS_COLUMN,
    "im",
    "theta_base",
    "theta_base_pga_g",
    "site_class",
    "pgv_pga_ratio_m_s_per_g",
    "amp_factor",
    "rate_setting",
    "rate_factor",
    "theta",
    "beta",
    "fragility_basis",
    "fragility_source",
    "kingsbury_rating",
    "kingsbury_zone",
    "continuous_rating",
    geometry.SCALE_COLUMN,
    geometry.AREA_COLUMN,
    geometry.SLOPE_COLUMN,
    geometry.MATERIAL_COLUMN,
    "modification",
    "face_height_10m",
    "depth_evacuated_m",
    "depth_inundated_m",
    geometry.REP_POINT_COLUMN,
    *geometry.GEOMETRY_KINDS,
    "geometry",
)

# The polygon columns copied onto the model file as they are.
_CARRIED_POLYGON_COLUMNS = (
    "kingsbury_rating",
    "kingsbury_zone",
    "continuous_rating",
    geometry.SCALE_COLUMN,
    geometry.AREA_COLUMN,
    geometry.SLOPE_COLUMN,
    geometry.MATERIAL_COLUMN,
    "modification",
    "face_height_10m",
)

# The drawn wall columns the join reads (contract section 3.7). ``rw_id`` is
# carried onto the model and is null on a wall that is not insured (decision
# 36); whether a polygon has a wall is read from the wall lines on its edge
# alone. The wall's ``height_m`` picks its height class in the wall type
# table. The wall's own ``wall_position`` shifts its curve; it is merged as
# _WALL_OWN_POSITION_COLUMN so it is never read for the polygon's position,
# which sets the wall state and can come from another edge line.
_WALL_COLUMNS = (
    RW_ID_COLUMN,
    geometry.WALL_LINE_ID_COLUMN,
    SIZE_CLASS_COLUMN,
    WALL_HEIGHT_COLUMN,
    WALL_TYPE_COLUMN,
    geometry.WALL_POSITION_COLUMN,
)
_WALL_OWN_POSITION_COLUMN = "wall_own_position"

# The drawn wall column that marks a wall on flat land (contract section
# 3.7). A flat-land wall is drawn by vul shaking rw step 9 and nowhere else
# (contract sections 3.11 and 5.1), so no polygon takes one.
IS_FLATLAND_COLUMN = "is_flatland"

# The stepped slope factor of [kingsbury_1995] read as a polyline: the origin,
# then each break of ``SLOPE_ANGLE_BREAKS_DEGREES`` at the value the stepped
# factor takes from that break up, so the two agree at every break and the
# interpolated factor rises between them.
INTERPOLATED_SLOPE_POINTS_DEG = (0.0, *susceptibility.SLOPE_ANGLE_BREAKS_DEGREES)
INTERPOLATED_SLOPE_VALUES = susceptibility.SLOPE_ANGLE_VALUES


class LocalisedFit(NamedTuple):
    """The localised fragility fitted to the anchor table.

    Attributes:
        theta_at_zero_rating_m_s: The median at a rating of 0, m/s.
        theta_at_max_rating_m_s: The median at ``MAX_RATING``, m/s.
        beta: The dispersion the anchors ask for.
        anchors_used: The ``anchor_id`` of every row the fit read.
    """

    theta_at_zero_rating_m_s: float
    theta_at_max_rating_m_s: float
    beta: float
    anchors_used: tuple[str, ...]


# --- the anchor table -----------------------------------------------------------


def _require_columns(table: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in table.columns]
    if missing:
        msg = f"{name} is missing the columns {missing}; expected {list(columns)}."
        raise ValueError(msg)


def load_urban_fragility_anchors(
    path: Path = URBAN_FRAGILITY_ANCHORS_PATH,
) -> pd.DataFrame:
    """Read the anchors the localised fragility is fitted to.

    One row per anchor point: what its fraction measures (``zone_area``, the
    damaged share of a Kingsbury zone's non-flat area, or ``polygon``, the
    share of the matching polygons failing), a zone or rating range or the
    polygons it applies to, a demand range on rock or at a recording site, the
    source's failure class word and the fraction it is read as, with who set
    the fraction and why (contract section 8.2; plan section 6). The fractions
    are judgement, and every row says so in ``set_by``.

    Args:
        path: The CSV to read; the packaged table by default.

    Returns:
        The table, one row per ``anchor_id``.

    Raises:
        ValueError: If a column is missing, an id repeats, a
            ``fail_fraction`` is outside ``[0, 1]``, or a ``measure``,
            ``applies_to`` or ``demand_at`` is blank or unknown.
    """
    table = pd.read_csv(path)
    _require_columns(table, ANCHOR_COLUMNS, "The urban fragility anchor table")
    if table["anchor_id"].duplicated().any():
        msg = "The urban fragility anchor table repeats an anchor_id."
        raise ValueError(msg)
    fraction = table["fail_fraction"].to_numpy(dtype=float)
    if not np.all(np.isfinite(fraction) & (fraction >= 0.0) & (fraction <= 1.0)):
        msg = (
            "Every fail_fraction in the urban fragility anchor table must be in [0, 1]."
        )
        raise ValueError(msg)
    for column, allowed in (
        ("measure", ANCHOR_MEASURES),
        ("applies_to", ANCHOR_APPLIES_TO),
        ("demand_at", ANCHOR_DEMAND_AT),
    ):
        unknown = sorted(set(table[column].dropna().astype(str)) - set(allowed))
        if unknown or table[column].isna().any():
            msg = (
                f"The urban fragility anchor table's {column} must be one of "
                f"{list(allowed)} on every row; found {unknown or 'a blank'}."
            )
            raise ValueError(msg)
    return table


# --- the curve ----------------------------------------------------------------


def interpolated_slope_value(
    slope_degrees: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Score the slope angle factor continuously rather than in steps.

    Linear through ``(0, 0), (20, 2), (35, 4), (45, 8), (60, 10)`` and flat at
    10 above 60 degrees, so a localised failure probability rises steadily with
    steepness instead of jumping at Kingsbury's class breaks. It equals
    :func:`susceptibility.slope_angle_value` at every break.

    Args:
        slope_degrees: Ground slope in degrees.

    Returns:
        The factor value, 0 to 10, NaN where the slope is NaN.
    """
    slope = np.asarray(slope_degrees, dtype=float)
    return np.interp(slope, INTERPOLATED_SLOPE_POINTS_DEG, INTERPOLATED_SLOPE_VALUES)


def continuous_rating(
    *,
    slope_degrees: npt.NDArray[np.floating],
    modification: npt.NDArray[np.floating],
    height: npt.NDArray[np.floating],
    geology: npt.NDArray[np.floating],
    landslides: npt.NDArray[np.floating],
    groundwater: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Sum the Kingsbury rating with the slope factor interpolated.

    :func:`susceptibility.susceptibility_rating` with
    :func:`interpolated_slope_value` in place of the stepped slope factor; the
    other five arguments are factor *values* on the 0 to 10 scale, as that
    function takes them.

    Args:
        slope_degrees: Ground slope in degrees, not a factor value.
        modification: F_modification.
        height: F_height.
        geology: F_geology.
        landslides: F_landslides.
        groundwater: F_groundwater.

    Returns:
        The rating, 0 to :data:`susceptibility.MAX_RATING`.
    """
    return susceptibility.susceptibility_rating(
        slope=interpolated_slope_value(slope_degrees),
        modification=modification,
        height=height,
        geology=geology,
        landslides=landslides,
        groundwater=groundwater,
    )


def localised_theta_base_m_s(
    rating: npt.NDArray[np.floating],
    *,
    theta_at_zero_rating_m_s: float = LOCALISED_THETA_AT_ZERO_RATING_M_S,
    theta_at_max_rating_m_s: float = LOCALISED_THETA_AT_MAX_RATING_M_S,
) -> npt.NDArray[np.floating]:
    """Return the localised (no wall) median from the continuous rating.

    ``theta_0 * (theta_max / theta_0) ** (rating / MAX_RATING)``: a log-linear
    fall from the median at rating 0 to the median at the top of the scale
    (contract section 7.7), so gentle ground takes a very high median rather
    than being dropped (plan section 4.2). The two constants are placeholders
    until the anchoring sets them; :func:`fit_localised_fragility` is the fit.

    Args:
        rating: The continuous Kingsbury rating, 0 to ``MAX_RATING``.
        theta_at_zero_rating_m_s: The median at a rating of 0.
        theta_at_max_rating_m_s: The median at ``MAX_RATING``.

    Returns:
        The median PGV in m/s, NaN where the rating is NaN.
    """
    scaled = np.asarray(rating, dtype=float) / susceptibility.MAX_RATING
    ratio = theta_at_max_rating_m_s / theta_at_zero_rating_m_s
    return theta_at_zero_rating_m_s * ratio**scaled


def rate_factor(setting: str) -> float:
    """Return the multiplier on every urban median for a rate setting.

    Args:
        setting: One of the keys of ``constants.URBAN_RATE_FACTORS``.

    Returns:
        The factor; 1.0 for ``medium`` by definition (plan section 4.4).

    Raises:
        ValueError: If the setting is not one of the three.
    """
    try:
        return float(constants.URBAN_RATE_FACTORS[setting])
    except KeyError:
        valid = ", ".join(repr(key) for key in constants.URBAN_RATE_FACTORS)
        msg = f"Unknown urban rate setting {setting!r}; expected one of {valid}."
        raise ValueError(msg) from None


def pga_to_pgv_theta(
    theta_pga_g: npt.NDArray[np.floating],
    ratio_m_s_per_g: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Convert a PGA-based median to PGV by the study's own ratio.

    Args:
        theta_pga_g: The published median, g.
        ratio_m_s_per_g: PGV (m/s) over PGA (g) at the point, from
            :func:`pgv_pga_ratio_m_s_per_g`.

    Returns:
        The median in m/s; NaN where either input is NaN.
    """
    return np.asarray(theta_pga_g, dtype=float) * np.asarray(
        ratio_m_s_per_g, dtype=float
    )


def polygon_theta(
    theta_base: npt.NDArray[np.floating],
    amp_factor: npt.NDArray[np.floating],
    rate_factor: float,
) -> npt.NDArray[np.floating]:
    """Adjust a base median for amplification and the rate setting.

    ``theta_base / amp_factor * rate_factor`` (contract section 6): a crest or
    a steep face lowers the median, a *low* rate setting raises it.

    Args:
        theta_base: The median before adjustment, m/s.
        amp_factor: The topographic amplification factor, 1.0 and up.
        rate_factor: The factor of the run's setting, from :func:`rate_factor`.

    Returns:
        The median the realisation draws against, m/s.
    """
    return (
        np.asarray(theta_base, dtype=float)
        / np.asarray(amp_factor, dtype=float)
        * rate_factor
    )


# --- the PGV/PGA ratio ---------------------------------------------------------


def _check_same_grid(pgv: xr.DataArray, pga: xr.DataArray) -> None:
    if pgv.shape != pga.shape:
        msg = f"The PGV grid is {pgv.shape} and the PGA grid {pga.shape}; match them."
        raise ValueError(msg)
    if pgv.rio.crs is None or pga.rio.crs is None:
        msg = "Both the PGV and the PGA grid must carry a coordinate reference system."
        raise ValueError(msg)
    if pgv.rio.crs != pga.rio.crs:
        msg = f"The PGV grid is in {pgv.rio.crs} and the PGA grid in {pga.rio.crs}."
        raise ValueError(msg)
    if not np.allclose(
        np.asarray(pgv.rio.transform())[:6], np.asarray(pga.rio.transform())[:6]
    ):
        msg = "The PGV and PGA grids have different transforms; they must share cells."
        raise ValueError(msg)


def pgv_pga_ratio_m_s_per_g(
    pgv: xr.DataArray, pga: xr.DataArray, points: gpd.GeoSeries
) -> pd.Series:
    """Sample PGV over PGA, cell by cell, at a set of points.

    Both grids are the step 2 site class grid: step 3's PGV at the return
    period and the unscaled TS1170.5 PGA on the same cells (contract section
    6). The ratio is realisation-free, because shaking steps 4 and 5 scale PGA
    and PGV by one factor. Each point reads the cell it falls in.

    Args:
        pgv: PGV in m/s, dims ``("y", "x")`` with a CRS.
        pga: PGA in g, on the same grid.
        points: Where to sample; reprojected to the grids' system if needed.

    Returns:
        The ratio in m/s per g on ``points.index``; NaN off the grid, or where
        either grid is NaN there.

    Raises:
        ValueError: If the grids differ in shape, transform or CRS.
    """
    _check_same_grid(pgv, pga)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.asarray(pgv.to_numpy(), dtype=float) / np.asarray(
            pga.to_numpy(), dtype=float
        )
    return _sample_cells(ratio, pgv, points)


def _sample_cells(
    values: np.ndarray, grid: xr.DataArray, points: gpd.GeoSeries
) -> pd.Series:
    """Read an array on a grid at the cell each point falls in."""
    located = points if points.crs is None else points.to_crs(grid.rio.crs)
    out = np.full(len(located), np.nan)
    if len(located) == 0:
        return pd.Series(out, index=points.index, dtype=float)
    inverse = ~grid.rio.transform()
    xs = located.x.to_numpy(dtype=float)
    ys = located.y.to_numpy(dtype=float)
    finite = np.isfinite(xs) & np.isfinite(ys)
    columns, rows = inverse * (xs[finite], ys[finite])
    col = np.floor(columns).astype(int)
    row = np.floor(rows).astype(int)
    inside = (row >= 0) & (row < values.shape[0]) & (col >= 0) & (col < values.shape[1])
    sampled = np.full(finite.sum(), np.nan)
    sampled[inside] = values[row[inside], col[inside]]
    out[finite] = sampled
    return pd.Series(out, index=points.index, dtype=float)


# --- the model file -------------------------------------------------------------


def wall_state(
    wall_position: npt.NDArray[np.object_], has_wall: npt.NDArray[np.bool_]
) -> npt.NDArray[np.object_]:
    """Name the state each polygon is in for the world's wall draw.

    Args:
        wall_position: The polygon's ``wall_position`` (``fill``, ``cut`` or
            null), from the wall line on its edge.
        has_wall: Whether the line drew a wall in this world.

    Returns:
        ``no_wall``, ``fill_wall`` or ``cut_wall`` per polygon.

    Raises:
        ValueError: If a polygon with a wall carries a position that is
            neither ``fill`` nor ``cut``.
    """
    position = np.asarray(wall_position, dtype=object)
    drawn = np.asarray(has_wall, dtype=bool)
    state = np.full(len(position), geometry.NO_WALL, dtype=object)
    state[drawn & (position == geometry.FILL)] = geometry.FILL_WALL
    state[drawn & (position == geometry.CUT)] = geometry.CUT_WALL
    bad = drawn & (state == geometry.NO_WALL)
    if bad.any():
        msg = (
            f"{int(bad.sum())} polygons carry a wall whose position is not "
            f"{geometry.FILL!r} or {geometry.CUT!r}."
        )
        raise ValueError(msg)
    return state


def _check_frames(polygons: gpd.GeoDataFrame, walls: pd.DataFrame) -> None:
    if polygons.crs is not None and polygons.crs.is_geographic:
        msg = f"{polygons.crs} is a geographic system; work in a projected one."
        raise ValueError(msg)
    _require_columns(
        polygons,
        (geometry.WALL_LINE_ID_COLUMN, geometry.WALL_LINE_IDS_COLUMN),
        "The polygons",
    )
    _require_columns(walls, (*_WALL_COLUMNS, IS_FLATLAND_COLUMN), "The drawn walls")
    repeated = walls[geometry.WALL_LINE_ID_COLUMN].duplicated()
    if repeated.any():
        ids = walls.loc[repeated, geometry.WALL_LINE_ID_COLUMN].unique().tolist()
        msg = f"A line drew more than one wall in this world: {ids[:5]}."
        raise ValueError(msg)
    unknown_size = set(walls[SIZE_CLASS_COLUMN].dropna()) - set(SIZE_CLASSES)
    unknown_type = set(walls[WALL_TYPE_COLUMN].dropna()) - set(
        wall_type_fragility.WALL_TYPES
    )
    if unknown_size or unknown_type:
        msg = (
            f"Unknown size class {sorted(unknown_size)} or wall type "
            f"{sorted(unknown_type)} in the wall population."
        )
        raise ValueError(msg)


def _wall_rows(
    walls_on_polygons: pd.DataFrame,
    wall_table: pd.DataFrame,
    has_wall: npt.NDArray[np.bool_],
) -> pd.DataFrame:
    """Look up the type curve of every polygon with a wall, on the polygons' index.

    The curve is the wall's type and height class; its PGA median is shifted
    by the wall's own position, not the polygon's.
    """
    out = pd.DataFrame(
        {
            "theta_pga_g": np.nan,
            "beta": np.nan,
            "source": pd.Series(None, index=walls_on_polygons.index, dtype=object),
        },
        index=walls_on_polygons.index,
    )
    with_wall = walls_on_polygons[has_wall]
    if with_wall.empty:
        return out
    curves = wall_type_fragility.wall_type_curves(
        with_wall[WALL_TYPE_COLUMN],
        with_wall[WALL_HEIGHT_COLUMN],
        with_wall[_WALL_OWN_POSITION_COLUMN],
        wall_table,
    )
    out.loc[curves.index, "theta_pga_g"] = curves["theta_pga_g"].to_numpy(dtype=float)
    out.loc[curves.index, "beta"] = curves["beta"].to_numpy(dtype=float)
    out.loc[curves.index, "source"] = curves["source"].to_numpy(dtype=object)
    return out


def _pick_state(
    polygons: gpd.GeoDataFrame, state: np.ndarray, kind: str
) -> gpd.GeoSeries:
    """Take the geometry of the polygon's own state, one column per kind.

    Polygons built for one world's walls (landslide step 12's zones, through
    :mod:`landloss.hazard.landslide.urban.face_polygons`) carry one geometry
    per kind, already the world's, and it is taken as it is.
    """
    if kind in polygons.columns:
        return gpd.GeoSeries(polygons[kind], index=polygons.index, crs=polygons.crs)
    picked = [
        polygons.loc[index, f"{kind}_{one_state}"]
        for index, one_state in zip(polygons.index, state, strict=True)
    ]
    return gpd.GeoSeries(picked, index=polygons.index, crs=polygons.crs)


def _pick_depth(polygons: pd.DataFrame, state: np.ndarray, kind: str) -> np.ndarray:
    """Take the depth of the polygon's own state; one column where there is one."""
    if f"depth_{kind}_m" in polygons.columns:
        return polygons[f"depth_{kind}_m"].to_numpy(dtype=float)
    return np.array(
        [
            float(polygons.loc[index, f"depth_{kind}_{one_state}_m"])
            for index, one_state in zip(polygons.index, state, strict=True)
        ],
        dtype=float,
    )


def sloping_walls(walls: pd.DataFrame) -> pd.DataFrame:
    """Keep the walls a polygon may take: on sloping land and with a line.

    A flat-land wall (``is_flatland`` true) is drawn on its own curve by vul
    shaking rw step 9 and nowhere else (contract sections 3.11 and 5.1), so a
    polygon whose edge line drew one stays in the ``no_wall`` state; taking it
    here as well would draw the same wall twice against two demands. A wall
    with no line is dropped too: a merge treats two nulls as equal, so it would
    otherwise land on every polygon without a line (exposure rw step 6 never writes
    one, but a hand-built frame might).

    Args:
        walls: The world's drawn walls, carrying ``wall_line_id`` and
            ``is_flatland``.

    Returns:
        The rows of ``walls`` with ``is_flatland`` false and a
        ``wall_line_id``, on their own index.
    """
    flat = walls[IS_FLATLAND_COLUMN].fillna(value=False).to_numpy(dtype=bool)
    has_line = walls[geometry.WALL_LINE_ID_COLUMN].notna().to_numpy()
    return walls[~flat & has_line]


def drawn_edge_walls(
    polygons: pd.DataFrame, walls: pd.DataFrame
) -> tuple[npt.NDArray[np.object_], list[list[str]]]:
    """Find, for each polygon, the lines on its edge that drew a wall.

    A polygon's edge can carry several wall lines (``wall_line_ids``, longest
    shared edge first), because the lines are split at property boundaries and
    the polygons are not; any of them that drew a wall in the world gives the
    polygon its wall, and every such wall fails with the polygon.

    Args:
        polygons: The polygons (step 12's zones, shaped by
            :mod:`~landloss.hazard.landslide.urban.face_polygons`; the old
            step 7 polygons were removed 2026-10-08), carrying ``wall_line_id`` and
            ``wall_line_ids``.
        walls: The walls a polygon may take (:func:`sloping_walls`), one per
            ``wall_line_id``.

    Returns:
        ``(chosen, drawn)``: per polygon, the line whose wall the polygon
        takes (the first of its edge lines that drew one; the polygon's own
        ``wall_line_id`` where none did), and the list of every edge line that
        drew a wall, in edge order (empty where none did).
    """
    drawn_lines = set(walls[geometry.WALL_LINE_ID_COLUMN].dropna())
    primary = polygons[geometry.WALL_LINE_ID_COLUMN].to_numpy(dtype=object)
    chosen = np.empty(len(polygons), dtype=object)
    drawn: list[list[str]] = []
    for position, cell in enumerate(polygons[geometry.WALL_LINE_IDS_COLUMN]):
        lines = list(geometry.edge_line_ids(cell))
        own = primary[position]
        if own is not None and not pd.isna(own) and own not in lines:
            lines.insert(0, str(own))
        on_edge = [line for line in lines if line in drawn_lines]
        drawn.append(on_edge)
        chosen[position] = on_edge[0] if on_edge else (None if pd.isna(own) else own)
    return chosen, drawn


def assign_fragility(
    polygons: gpd.GeoDataFrame,
    walls: gpd.GeoDataFrame,
    wall_table: pd.DataFrame,
    *,
    rate_setting: str,
    site_class: pd.Series,
    pgv_pga_ratio: pd.Series,
) -> gpd.GeoDataFrame:
    """Give every polygon its fragility row for one exposure world.

    Joins the wall lines on each polygon's edge (``wall_line_ids``) to the
    world's sloping-land walls (at most one wall per line; a flat-land wall on
    a polygon edge leaves the polygon in ``no_wall``). A polygon has a wall
    when any line on its edge drew one, whether or not that wall is insured:
    an uninsured wall still holds the slope, so it gives its polygon the wall
    state and curve with ``rw_id`` null (decision 36 of the build contract).
    The polygon takes the curve, ``rw_id``, type and size class of the first
    such line in edge order (longest shared edge first, :func:`drawn_edge_walls`),
    and the state of its own ``wall_position``, the position of the line
    sharing its longest edge, because the old step 7 polygons (removed
    2026-10-08) fixed one wall geometry per polygon. The model carries that line
    as ``wall_line_id`` and every edge
    line that drew a wall as ``wall_line_ids``, so step 9 can give each of
    those walls the polygon's outcome. It then sets the wall state, picks the
    state's fixed
    geometry and depths off the polygon file, and computes the row columns of
    contract section 6: the wall type curve, its PGA median scaled by the
    wall's own ``wall_position`` (fill or cut, which can differ from the
    polygon's when the chosen line is not the longest-edge one) and converted
    to PGV, where the polygon has a wall; the localised median from the
    continuous rating where it has none; both divided by the amplification
    factor and multiplied by the rate factor.

    Args:
        polygons: The polygons, carrying ``wall_line_ids`` beside
            ``wall_line_id``: in the pipeline, one world's landslide step 12
            zones from
            :func:`landloss.hazard.landslide.urban.face_polygons.face_polygons`,
            whose wall line is the polygon's wall unit and whose geometry is
            already the world's (one ``evacuated``, ``inundated`` and
            ``imminent`` column, and ``depth_evacuated_m`` and
            ``depth_inundated_m``); or the old step 7 polygons (contract section
            3.6, removed 2026-10-08), carrying every state's geometry for the
            state to pick.
        walls: Every wall exposure step 6 drew in this world, before the
            claim and coverage filters (``drawn_walls_path``, contract section
            3.7), carrying ``rw_id`` (null on a wall that is not insured),
            ``wall_line_id``, ``size_class``, ``height_m`` (which picks the
            wall's height class in ``wall_table``), ``wall_type``,
            ``wall_position`` and ``is_flatland``. Flat-land walls are left
            out of the join (:func:`sloping_walls`).
        wall_table: The table
            :func:`landloss.hazard.landslide.urban.wall_type_fragility.load_wall_type_fragility`
            returns.
        rate_setting: ``low``, ``medium`` or ``high``.
        site_class: The TS1170.5 site class at each ``rep_point``, on
            ``polygons.index``; NaN off the grid.
        pgv_pga_ratio: :func:`pgv_pga_ratio_m_s_per_g` at each ``rep_point``,
            on ``polygons.index``.

    Returns:
        The model file of contract section 3.8 less ``world_id``, with the
        columns :data:`MODEL_COLUMNS`, sorted by ``slope_id`` with a fresh
        index.

    Raises:
        ValueError: If the polygons are in a geographic system or carry no
            ``wall_line_ids``, a line drew two walls, a wall's size or
            type is unknown, its curve is missing from the table, or its
            position (or the polygon's) is not fill or cut.
    """
    _check_frames(polygons, walls)
    factor = rate_factor(rate_setting)

    walls = sloping_walls(walls)
    chosen, drawn = drawn_edge_walls(polygons, walls)
    # A match on the edge lines, not a non-null rw_id: an uninsured wall has
    # none. sloping_walls has dropped every null wall_line_id, so a polygon
    # with no line matches nothing.
    has_wall = np.array([bool(lines) for lines in drawn], dtype=bool)
    joined = pd.DataFrame(
        {geometry.WALL_LINE_ID_COLUMN: np.where(has_wall, chosen, None)}
    ).merge(
        walls[list(_WALL_COLUMNS)].rename(
            columns={geometry.WALL_POSITION_COLUMN: _WALL_OWN_POSITION_COLUMN}
        ),
        on=geometry.WALL_LINE_ID_COLUMN,
        how="left",
    )
    joined.index = polygons.index
    state = wall_state(polygons[geometry.WALL_POSITION_COLUMN].to_numpy(), has_wall)
    curves = _wall_rows(joined, wall_table, has_wall)

    ratio = pgv_pga_ratio.reindex(polygons.index).to_numpy(dtype=float)
    rating = polygons["continuous_rating"].to_numpy(dtype=float)
    # Every wall curve is on PGA: theta_pga_g is NaN where there is no wall.
    theta_base_pga_g = curves["theta_pga_g"].to_numpy(dtype=float)
    theta_base = np.where(
        has_wall,
        pga_to_pgv_theta(theta_base_pga_g, ratio),
        localised_theta_base_m_s(rating),
    )
    ratio_used = np.where(has_wall, ratio, np.nan)
    beta = np.where(
        has_wall,
        curves["beta"].to_numpy(dtype=float),
        constants.LOCALISED_FRAGILITY_BETA,
    )
    amp = polygons["amp_factor"].to_numpy(dtype=float)
    theta = polygon_theta(theta_base, amp, factor)

    basis = np.where(has_wall, WALL_BASIS, LOCALISED_BASIS)
    source = np.where(
        has_wall,
        curves["source"].to_numpy(dtype=object),
        np.array([f"localised:{value:.0f}" for value in rating], dtype=object),
    )

    out = gpd.GeoDataFrame(
        {
            geometry.SLOPE_ID_COLUMN: polygons[geometry.SLOPE_ID_COLUMN].to_numpy(),
            geometry.WALL_LINE_ID_COLUMN: chosen,
            geometry.WALL_LINE_IDS_COLUMN: pd.Series(
                drawn, index=polygons.index, dtype=object
            ),
            RW_ID_COLUMN: joined[RW_ID_COLUMN].to_numpy(),
            STATE_COLUMN: state,
            WALL_TYPE_COLUMN: joined[WALL_TYPE_COLUMN].to_numpy(),
            SIZE_CLASS_COLUMN: joined[SIZE_CLASS_COLUMN].to_numpy(),
            "im": IM,
            "theta_base": theta_base,
            "theta_base_pga_g": theta_base_pga_g,
            "site_class": site_class.reindex(polygons.index).to_numpy(dtype=float),
            "pgv_pga_ratio_m_s_per_g": ratio_used,
            "amp_factor": amp,
            "rate_setting": rate_setting,
            "rate_factor": factor,
            "theta": theta,
            "beta": beta,
            "fragility_basis": basis,
            "fragility_source": source,
            **{
                column: polygons[column].to_numpy()
                for column in _CARRIED_POLYGON_COLUMNS
            },
            "depth_evacuated_m": _pick_depth(polygons, state, geometry.EVACUATED),
            "depth_inundated_m": _pick_depth(polygons, state, geometry.INUNDATED),
            geometry.REP_POINT_COLUMN: gpd.GeoSeries(
                polygons[geometry.REP_POINT_COLUMN], crs=polygons.crs
            ),
            **{
                kind: _pick_state(polygons, state, kind)
                for kind in geometry.GEOMETRY_KINDS
            },
        },
        geometry=polygons.geometry.to_numpy(),
        crs=polygons.crs,
        index=polygons.index,
    )
    out["site_class"] = out["site_class"].round().astype("Int64")
    out["kingsbury_zone"] = out["kingsbury_zone"].astype("Int64")
    out = out[list(MODEL_COLUMNS)]
    return out.sort_values(geometry.SLOPE_ID_COLUMN, kind="mergesort").reset_index(
        drop=True
    )


# --- the anchoring ----------------------------------------------------------------


def anchor_points(anchors: pd.DataFrame, *, ratio_m_s_per_g: float) -> pd.DataFrame:
    """Place each anchor on the rating and PGV axes.

    The rating is the midpoint of the anchor's range and the demand the
    geometric mean of its PGA range on rock, converted to PGV by the rock-site
    ratio (contract section 3.16). Rows without a rating range, a demand
    range or a fraction strictly inside ``(0, 1)`` carry NaN in ``probit`` and
    are left out of the fit.

    Args:
        anchors: The table :func:`load_urban_fragility_anchors` returns.
        ratio_m_s_per_g: PGV over PGA on rock, m/s per g.

    Returns:
        The anchors with ``rating``, ``pgv_m_s``, ``pgv_min_m_s``,
        ``pgv_max_m_s`` and ``probit`` (the standard normal quantile of
        ``fail_fraction``) added.
    """
    placed = anchors.copy()
    rating_min = placed["rating_min"].to_numpy(dtype=float)
    rating_max = placed["rating_max"].to_numpy(dtype=float)
    pga_min = placed["pga_rock_g_min"].to_numpy(dtype=float)
    pga_max = placed["pga_rock_g_max"].to_numpy(dtype=float)
    fraction = placed["fail_fraction"].to_numpy(dtype=float)
    placed["rating"] = 0.5 * (rating_min + rating_max)
    placed["pgv_min_m_s"] = pga_min * ratio_m_s_per_g
    placed["pgv_max_m_s"] = pga_max * ratio_m_s_per_g
    placed["pgv_m_s"] = np.sqrt(pga_min * pga_max) * ratio_m_s_per_g
    with np.errstate(divide="ignore"):
        probit = norm.ppf(fraction)
    placed["probit"] = np.where(np.isfinite(probit), probit, np.nan)
    return placed


def fit_localised_fragility(
    anchors: pd.DataFrame, *, ratio_m_s_per_g: float
) -> LocalisedFit:
    """Fit the localised median's two constants and a dispersion to the anchors.

    The first reading of the anchors, each fraction as a share of polygons at
    the zone's mid rating. Superseded for the zone anchors by the area
    calibration (:mod:`landloss.hazard.landslide.urban.area_calibration`),
    which reads them as damaged shares of the zone's area; kept for the
    anchor figure. Rows without a rating range (the polygon anchors) are left
    out.

    With ``ln theta(r) = a + b r`` (the log-linear form of
    :func:`localised_theta_base_m_s`) and ``Phi(ln(pgv / theta) / beta) = f``
    at every anchor, ``ln pgv = a + b r + beta Phi^-1(f)``: an ordinary least
    squares fit of ``ln pgv`` on the rating and the probit of the fraction
    gives the two constants and the dispersion the anchors ask for.

    Args:
        anchors: The table :func:`load_urban_fragility_anchors` returns.
        ratio_m_s_per_g: PGV over PGA on rock, m/s per g.

    Returns:
        The fitted constants and dispersion, and which anchors were read.

    Raises:
        ValueError: If fewer than three anchors can be placed, or the fitted
            dispersion is not positive.
    """
    placed = anchor_points(anchors, ratio_m_s_per_g=ratio_m_s_per_g)
    usable = placed[
        placed["rating"].notna() & placed["pgv_m_s"].notna() & placed["probit"].notna()
    ]
    if len(usable) < 3:
        msg = f"Only {len(usable)} anchors can be placed; the fit needs at least 3."
        raise ValueError(msg)
    design = np.column_stack(
        [
            np.ones(len(usable)),
            usable["rating"].to_numpy(dtype=float),
            usable["probit"].to_numpy(dtype=float),
        ]
    )
    target = np.log(usable["pgv_m_s"].to_numpy(dtype=float))
    (a, b, beta), *_ = np.linalg.lstsq(design, target, rcond=None)
    if beta <= 0:
        msg = f"The anchors give a dispersion of {beta:.3f}; it must be positive."
        raise ValueError(msg)
    return LocalisedFit(
        theta_at_zero_rating_m_s=float(np.exp(a)),
        theta_at_max_rating_m_s=float(np.exp(a + b * susceptibility.MAX_RATING)),
        beta=float(beta),
        anchors_used=tuple(usable["anchor_id"].astype(str)),
    )
