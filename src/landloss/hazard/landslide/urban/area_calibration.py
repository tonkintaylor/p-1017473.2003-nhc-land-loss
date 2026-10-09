"""Calibrate the localised (no wall) urban fragility to damaged-area shares.

What belongs here: the expected share of a reference area that the bare
(no wall) urban failure polygons damage at a demand, the conversion of a
scenario's bedrock PGA to each polygon's site PGV, the average over a
scenario's PGA range, and the fits of the localised median's scale and
dispersion. The adopted fit (:func:`fit_record_and_polygons`, the project
lead's choice of 2026-10-07) is to the Kaikoura record of no urban failures
(A16) and the GNS polygon anchors for cuts and fills (A17 to A21), with
Kingsbury's High scenario 2 share (A12) kept as an upper limit
(:func:`within_upper_limit`). The fit to [kingsbury_1995]'s zone shares
(:func:`fit_area_calibration`) was rejected: those shares cannot all be met
by the urban footprints, and his scenario 1 and intermediate classes conflict
with the Kaikoura record. Used by the urban validation
``hazard/landslide/validations/urban/table_urban_area_calibration.py`` and
its figure. Kept apart from :mod:`landloss.hazard.landslide.urban.fragility`,
which it imports and which does not import it.

Kingsbury's slope failure classes (Table 1) describe how much of a zone's
ground is damaged, not how many polygons fail, and his zones include the
runout below a steep slope (section 4.4.2). So a zone's fraction is compared
with the expected share of its non-flat area that lies in the evacuated or
inundated zone of a failed polygon. Each bare polygon's footprint (the union
of its evacuated and inundated zones) is rasterised on a grid of
:data:`AREA_CELL_SIZE_M` cells, keeping only cells on non-flat ground, so
runout onto flat land does not count. A cell is damaged when any polygon
covering it fails; the polygons fail independently, so
``P(cell) = 1 - prod(1 - p_i)``, and the expected damaged share is the mean of
``P(cell)`` over the reference cells (every cell has the same area).

A polygon fails on the localised lognormal of
:func:`landloss.hazard.landslide.urban.fragility.localised_theta_base_m_s`
divided by its amplification factor, against its site PGV. Kingsbury's
scenario PGAs are on bedrock, so the site PGV is the rock PGA times the
polygon's site PGV per g of rock PGA (:func:`pgv_per_rock_pga_m_s_per_g`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
import shapely
import xarray as xr
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine
from scipy import sparse
from scipy.optimize import least_squares

from landloss.hazard.landslide.urban import fragility
from landloss.hazard.landslide.urban.lognormal import lognormal_failure_probability

# The cell the damaged area is counted on, m: fine against a polygon's few
# metres of width, coarse enough to hold the pilot in memory.
AREA_CELL_SIZE_M = 2.0

# How many log-spaced demands a scenario's PGA range is averaged over.
SCENARIO_DEMAND_POINTS = 5

# The median at rating 0 over the median at the top of the scale, held fixed
# by the area calibration (the log-linear slope in rating it inherits from
# the placeholders, 3.0 over 0.6); only the overall scale is fitted.
FIXED_THETA_RATIO = 5.0

# The shares are fitted on the logit, which an expected share of exactly 0 or
# 1 would send to infinity.
_SHARE_FLOOR = 1e-12


class LocalisedCurve(NamedTuple):
    """The localised (no wall) fragility's three numbers.

    Attributes:
        theta_at_zero_rating_m_s: The median at a rating of 0, m/s.
        theta_at_max_rating_m_s: The median at ``MAX_RATING``, m/s.
        beta: The lognormal dispersion.
    """

    theta_at_zero_rating_m_s: float
    theta_at_max_rating_m_s: float
    beta: float


class LocalisedPolygons(NamedTuple):
    """What the localised fragility reads off each bare polygon.

    Attributes:
        rating: The continuous Kingsbury rating.
        amp_factor: The topographic amplification factor, 1.0 and up.
        pgv_per_g: The polygon's PGV per g of the demand's PGA, m/s per g:
            per g of rock PGA for a bedrock demand
            (:func:`pgv_per_rock_pga_m_s_per_g`), per g of site PGA for a
            recorded one.
    """

    rating: npt.NDArray[np.floating]
    amp_factor: npt.NDArray[np.floating]
    pgv_per_g: npt.NDArray[np.floating]

    def subset(self, mask: npt.NDArray[np.bool_]) -> "LocalisedPolygons":
        """Return the polygons where ``mask`` is true."""
        return LocalisedPolygons(*(np.asarray(values)[mask] for values in self))


class AreaFit(NamedTuple):
    """The localised fragility fitted to damaged-area shares.

    Attributes:
        curve: The fitted median pair and dispersion.
        targets: One row per target with ``predicted`` (the expected share
            at the fit) and ``logit_residual`` (predicted less target, on the
            logit) added.
        rms_logit_residual: The root mean square of the logit residuals.
    """

    curve: LocalisedCurve
    targets: pd.DataFrame
    rms_logit_residual: float


@dataclass(frozen=True)
class AreaGrid:
    """The cells a reference area is counted on.

    Attributes:
        west: The grid's west edge, m.
        north: The grid's north edge, m.
        cell_size_m: The cell side, m.
        reference: True where the cell centre lies on the reference ground,
            shape ``(rows, cols)``.
    """

    west: float
    north: float
    cell_size_m: float
    reference: npt.NDArray[np.bool_]

    @property
    def transform(self) -> Affine:
        """The grid's affine transform, north up."""
        return Affine(
            self.cell_size_m, 0.0, self.west, 0.0, -self.cell_size_m, self.north
        )

    @property
    def n_reference_cells(self) -> int:
        """How many cells lie on the reference ground."""
        return int(self.reference.sum())

    @property
    def reference_area_m2(self) -> float:
        """The reference ground's area as the grid counts it, m2."""
        return self.n_reference_cells * self.cell_size_m**2

    def reference_index(self) -> npt.NDArray[np.int64]:
        """Number the reference cells in row order; -1 off the reference."""
        index = np.full(self.reference.shape, -1, dtype=np.int64)
        index[self.reference] = np.arange(self.n_reference_cells)
        return index

    def reference_centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the x and y of every reference cell's centre, in row order."""
        rows, cols = np.nonzero(self.reference)
        xs = self.west + (cols + 0.5) * self.cell_size_m
        ys = self.north - (rows + 0.5) * self.cell_size_m
        return xs, ys


# --- the reference area and the footprints ------------------------------------


def _valid_geometries(geometries: gpd.GeoSeries) -> list:
    return [g for g in geometries if g is not None and not g.is_empty]


def reference_grid(
    reference: gpd.GeoSeries, *, cell_size_m: float = AREA_CELL_SIZE_M
) -> AreaGrid:
    """Lay a grid over the reference ground and mark the cells on it.

    The grid's edges are snapped to multiples of the cell size, and a cell is
    on the reference ground where its centre lies inside any of the
    geometries.

    Args:
        reference: The reference ground, e.g. the non-flat pieces of the step
            4 ground map, in a projected system.
        cell_size_m: The cell side, m.

    Returns:
        The grid.

    Raises:
        ValueError: If there is no reference geometry.
    """
    geometries = _valid_geometries(reference)
    if not geometries:
        msg = "The reference ground has no geometry to lay a grid over."
        raise ValueError(msg)
    minx, miny, maxx, maxy = shapely.total_bounds(geometries)
    west = np.floor(minx / cell_size_m) * cell_size_m
    north = np.ceil(maxy / cell_size_m) * cell_size_m
    cols = max(int(np.ceil((maxx - west) / cell_size_m)), 1)
    rows = max(int(np.ceil((north - miny) / cell_size_m)), 1)
    transform = Affine(cell_size_m, 0.0, west, 0.0, -cell_size_m, north)
    mask = rasterize(
        ((g, 1) for g in geometries),
        out_shape=(rows, cols),
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    return AreaGrid(
        west=float(west), north=float(north), cell_size_m=cell_size_m, reference=mask
    )


def damage_footprints(
    evacuated: gpd.GeoSeries, inundated: gpd.GeoSeries
) -> gpd.GeoSeries:
    """Join each polygon's evacuated and inundated zones into one footprint.

    Args:
        evacuated: Each polygon's evacuated zone.
        inundated: Each polygon's inundated zone on the same index, None where
            it has none.

    Returns:
        The union of the two per polygon, on ``evacuated.index``.
    """
    empty = shapely.Polygon()
    first = np.array(
        [empty if g is None else g for g in evacuated.to_numpy()], dtype=object
    )
    second = np.array(
        [
            empty if g is None else g
            for g in inundated.reindex(evacuated.index).to_numpy()
        ],
        dtype=object,
    )
    return gpd.GeoSeries(
        shapely.union(first, second), index=evacuated.index, crs=evacuated.crs
    )


def footprint_incidence(footprints: gpd.GeoSeries, grid: AreaGrid) -> sparse.csr_array:
    """Find which reference cells each footprint covers.

    A footprint covers a cell where the cell's centre lies inside it; cells
    off the reference ground (flat land, in the calibration) are left out, so
    runout onto them does not count.

    Args:
        footprints: One geometry per polygon, from :func:`damage_footprints`.
        grid: The reference grid, from :func:`reference_grid`.

    Returns:
        A sparse 0/1 matrix, one row per reference cell (in the order of
        :meth:`AreaGrid.reference_index`) and one column per footprint.
    """
    index = grid.reference_index()
    n_rows, n_cols = grid.reference.shape
    size = grid.cell_size_m
    cell_ids: list[np.ndarray] = []
    polygon_ids: list[np.ndarray] = []
    for position, footprint in enumerate(footprints.to_numpy()):
        if footprint is None or footprint.is_empty:
            continue
        minx, miny, maxx, maxy = footprint.bounds
        col0 = max(int(np.floor((minx - grid.west) / size)), 0)
        col1 = min(int(np.ceil((maxx - grid.west) / size)), n_cols)
        row0 = max(int(np.floor((grid.north - maxy) / size)), 0)
        row1 = min(int(np.ceil((grid.north - miny) / size)), n_rows)
        if col1 <= col0 or row1 <= row0:
            continue
        window = Affine(
            size, 0.0, grid.west + col0 * size, 0.0, -size, grid.north - row0 * size
        )
        covered = rasterize(
            [(footprint, 1)],
            out_shape=(row1 - row0, col1 - col0),
            transform=window,
            fill=0,
            dtype="uint8",
        )
        rows, cols = np.nonzero(covered)
        cells = index[row0 + rows, col0 + cols]
        cells = cells[cells >= 0]
        cell_ids.append(cells)
        polygon_ids.append(np.full(len(cells), position, dtype=np.int64))
    cells = np.concatenate(cell_ids) if cell_ids else np.empty(0, dtype=np.int64)
    polygons = (
        np.concatenate(polygon_ids) if polygon_ids else np.empty(0, dtype=np.int64)
    )
    return sparse.csr_array(
        (np.ones(len(cells)), (cells, polygons)),
        shape=(grid.n_reference_cells, len(footprints)),
    )


def nearest_labels(
    grid: AreaGrid, geometries: gpd.GeoSeries, labels: npt.ArrayLike
) -> np.ndarray:
    """Give every reference cell the label of the geometry nearest its centre.

    A Voronoi-like allocation of the reference ground among the polygons,
    used to split it into the Kingsbury zones of the polygons on it.

    Args:
        grid: The reference grid.
        geometries: The polygons, in the grid's system.
        labels: One label per geometry, in its order.

    Returns:
        One label per reference cell, in the order of
        :meth:`AreaGrid.reference_index`.
    """
    values = np.asarray(labels)
    xs, ys = grid.reference_centres()
    tree = shapely.STRtree(geometries.to_numpy())
    points = shapely.points(xs, ys)
    pairs = tree.query_nearest(points, all_matches=False)
    out = np.empty(len(xs), dtype=values.dtype)
    out[pairs[0]] = values[pairs[1]]
    return out


# --- the demand -----------------------------------------------------------------


def pgv_per_rock_pga_m_s_per_g(
    pgv_site: xr.DataArray, pga_rock: xr.DataArray, points: gpd.GeoSeries
) -> pd.Series:
    """Sample a point's site PGV per g of rock PGA, from one return period's grids.

    The site PGV is shaking step 3's grid (Sa(1.0 s) of each cell's own site
    class, converted by ``pgv_m_s_from_sa_1s``) and the rock PGA the TS1170.5
    site class I grid at the same return period. The ratio turns a scenario's
    bedrock PGA into the PGV the polygon's site feels.

    Args:
        pgv_site: Site PGV in m/s, with a CRS.
        pga_rock: Rock (site class I) PGA in g, with a CRS; put on
            ``pgv_site``'s grid by nearest neighbour.
        points: Where to sample, e.g. the polygons' representative points.

    Returns:
        The ratio in m/s per g on ``points.index``; NaN off the grid.
    """
    rock = pga_rock.rio.reproject_match(pgv_site, resampling=Resampling.nearest)
    return fragility.pgv_pga_ratio_m_s_per_g(pgv_site, rock, points)


def demand_points(
    pga_min_g: float, pga_max_g: float, n_points: int = SCENARIO_DEMAND_POINTS
) -> np.ndarray:
    """Return ``n_points`` log-spaced PGAs across a scenario's range, g."""
    return np.geomspace(pga_min_g, pga_max_g, n_points)


def polygon_failure_probability(
    pga_g: float,
    polygons: LocalisedPolygons,
    curve: LocalisedCurve,
    *,
    rate_factor: float = 1.0,
    amplified: bool = True,
) -> np.ndarray:
    """Return each bare polygon's localised failure probability at a PGA.

    ``PGV_i = pga_g * pgv_per_g_i`` against the median
    ``localised_theta_base(rating_i) / amp_i * rate_factor``.

    Args:
        pga_g: The demand's PGA, g.
        polygons: The polygons' ratings, amplification and PGV per g.
        curve: The localised curve.
        rate_factor: The rate setting's factor (1.0 for medium).
        amplified: False to leave out the amplification factor, for a recorded
            demand that already carries it.

    Returns:
        The probability per polygon.
    """
    theta_base = fragility.localised_theta_base_m_s(
        polygons.rating,
        theta_at_zero_rating_m_s=curve.theta_at_zero_rating_m_s,
        theta_at_max_rating_m_s=curve.theta_at_max_rating_m_s,
    )
    amp = polygons.amp_factor if amplified else np.ones_like(polygons.amp_factor)
    theta = fragility.polygon_theta(theta_base, amp, rate_factor)
    pgv = pga_g * np.asarray(polygons.pgv_per_g, dtype=float)
    return lognormal_failure_probability(pgv, theta, np.full_like(theta, curve.beta))


# --- the damaged share ----------------------------------------------------------


def damaged_cell_probability(
    incidence: sparse.csr_array, probability: npt.ArrayLike
) -> np.ndarray:
    """Return each reference cell's probability of lying in a failed footprint.

    ``1 - prod(1 - p_i)`` over the polygons covering the cell, the polygons
    failing independently; 0 where none covers it.

    Args:
        incidence: From :func:`footprint_incidence`.
        probability: Each polygon's failure probability, in column order.

    Returns:
        One probability per reference cell.

    Raises:
        ValueError: If a probability is NaN or outside ``[0, 1]``.
    """
    p = np.asarray(probability, dtype=float)
    if not np.all(np.isfinite(p) & (p >= 0.0) & (p <= 1.0)):
        msg = "Every polygon's failure probability must be finite and in [0, 1]."
        raise ValueError(msg)
    with np.errstate(divide="ignore"):
        log_survive = incidence @ np.log1p(-p)
    return -np.expm1(log_survive)


def expected_damaged_share(
    incidence: sparse.csr_array,
    probability: npt.ArrayLike,
    *,
    cells: npt.NDArray[np.bool_] | None = None,
) -> float:
    """Return the expected share of the reference area that is damaged.

    ``sum(cell area * P(cell)) / reference area``, which on equal cells is the
    mean of :func:`damaged_cell_probability` over the reference cells.

    Args:
        incidence: From :func:`footprint_incidence`.
        probability: Each polygon's failure probability, in column order.
        cells: Which reference cells make up the reference area; all of them
            by default.

    Returns:
        The expected damaged share, 0 to 1.

    Raises:
        ValueError: If the reference area has no cell.
    """
    per_cell = damaged_cell_probability(incidence, probability)
    if cells is not None:
        per_cell = per_cell[np.asarray(cells, dtype=bool)]
    if per_cell.size == 0:
        msg = "The reference area has no cell."
        raise ValueError(msg)
    return float(per_cell.mean())


def scenario_share(
    incidence: sparse.csr_array,
    polygons: LocalisedPolygons,
    curve: LocalisedCurve,
    *,
    pga_rock_g_min: float,
    pga_rock_g_max: float,
    cells: npt.NDArray[np.bool_] | None = None,
    rate_factor: float = 1.0,
    n_points: int = SCENARIO_DEMAND_POINTS,
) -> float:
    """Average the expected damaged share over a scenario's PGA range on rock.

    Args:
        incidence: From :func:`footprint_incidence`.
        polygons: The bare polygons, with ``pgv_per_g`` per g of rock PGA.
        curve: The localised curve.
        pga_rock_g_min: The bottom of the scenario's range, g.
        pga_rock_g_max: The top of the scenario's range, g.
        cells: Which reference cells make up the reference area.
        rate_factor: The rate setting's factor.
        n_points: How many log-spaced demands to average over.

    Returns:
        The mean of the expected damaged share over the demands.
    """
    shares = [
        expected_damaged_share(
            incidence,
            polygon_failure_probability(pga, polygons, curve, rate_factor=rate_factor),
            cells=cells,
        )
        for pga in demand_points(pga_rock_g_min, pga_rock_g_max, n_points)
    ]
    return float(np.mean(shares))


def mean_polygon_failure(
    polygons: LocalisedPolygons,
    curve: LocalisedCurve,
    *,
    pga_g_min: float,
    pga_g_max: float,
    amplified: bool = True,
    n_points: int = SCENARIO_DEMAND_POINTS,
) -> float:
    """Average the failure probability over polygons and a PGA range.

    The share of a polygon anchor's matching polygons expected to fail.

    Args:
        polygons: The matching polygons.
        curve: The localised curve.
        pga_g_min: The bottom of the anchor's range, g.
        pga_g_max: The top of the anchor's range, g.
        amplified: False for a recorded demand that already carries the
            amplification.
        n_points: How many log-spaced demands to average over.

    Returns:
        The mean probability; NaN where no polygon matches.
    """
    if len(polygons.rating) == 0:
        return float("nan")
    return float(
        np.mean(
            [
                polygon_failure_probability(
                    pga, polygons, curve, amplified=amplified
                ).mean()
                for pga in demand_points(pga_g_min, pga_g_max, n_points)
            ]
        )
    )


def anchor_polygon_mask(
    anchor: pd.Series,
    *,
    position: npt.ArrayLike,
    slope_degrees: npt.ArrayLike,
    material: npt.ArrayLike,
) -> np.ndarray:
    """Pick the polygons a polygon anchor speaks about.

    Args:
        anchor: One row of the anchor table: ``applies_to`` (``all``, ``cut``
            or ``fill``, matched to ``position``), ``slope_min_deg``
            (exclusive) and ``slope_max_deg`` (inclusive), blank for no
            bound, and ``material``, blank for any.
        position: Each polygon's cut or fill position.
        slope_degrees: Each polygon's slope.
        material: Each polygon's ground material.

    Returns:
        True where the polygon matches.
    """
    where = np.asarray(position, dtype=object)
    slope = np.asarray(slope_degrees, dtype=float)
    mask = np.ones(len(slope), dtype=bool)
    if anchor["applies_to"] != "all":
        mask &= where == anchor["applies_to"]
    if pd.notna(anchor["slope_min_deg"]):
        mask &= slope > float(anchor["slope_min_deg"])
    if pd.notna(anchor["slope_max_deg"]):
        mask &= slope <= float(anchor["slope_max_deg"])
    if pd.notna(anchor["material"]):
        mask &= np.asarray(material, dtype=object) == anchor["material"]
    return mask


# --- the fit --------------------------------------------------------------------


def _logit(share: npt.ArrayLike) -> np.ndarray:
    clipped = np.clip(np.asarray(share, dtype=float), _SHARE_FLOOR, 1 - _SHARE_FLOOR)
    return np.log(clipped / (1.0 - clipped))


def fit_area_calibration(
    incidence: sparse.csr_array,
    polygons: LocalisedPolygons,
    targets: pd.DataFrame,
    *,
    theta_ratio: float = FIXED_THETA_RATIO,
    cells: npt.NDArray[np.bool_] | None = None,
    initial: LocalisedCurve | None = None,
) -> AreaFit:
    """Fit the localised median's scale and dispersion to damaged-area shares.

    The median keeps its log-linear fall in rating with
    ``theta_at_zero / theta_at_max = theta_ratio``; the median at rating 0 and
    the dispersion are found by least squares on the logit of the expected
    damaged share (:func:`scenario_share`) against the logit of each target's
    ``fail_fraction``.

    Args:
        incidence: From :func:`footprint_incidence`.
        polygons: The bare polygons, with ``pgv_per_g`` per g of rock PGA.
        targets: One row per target, with ``pga_rock_g_min``,
            ``pga_rock_g_max`` and ``fail_fraction``.
        theta_ratio: The median at rating 0 over the median at the top.
        cells: Which reference cells make up the reference area.
        initial: Where the search starts; 3.0 m/s and 0.6 by default.

    Returns:
        The fitted curve, the targets with the predicted shares, and the root
        mean square logit residual.

    Raises:
        ValueError: If fewer than two targets are given, or the search fails.
    """
    if len(targets) < 2:
        msg = f"Only {len(targets)} targets; the fit of two numbers needs two."
        raise ValueError(msg)
    ranges = targets[["pga_rock_g_min", "pga_rock_g_max"]].to_numpy(dtype=float)

    def predict(curve: LocalisedCurve) -> np.ndarray:
        return np.array(
            [
                scenario_share(
                    incidence,
                    polygons,
                    curve,
                    pga_rock_g_min=low,
                    pga_rock_g_max=high,
                    cells=cells,
                )
                for low, high in ranges
            ]
        )

    return _fit_scale_and_beta(
        predict,
        targets,
        weights=np.ones(len(targets)),
        theta_ratio=theta_ratio,
        initial=initial,
    )


def _fit_scale_and_beta(
    predict: Callable[[LocalisedCurve], np.ndarray],
    targets: pd.DataFrame,
    *,
    weights: np.ndarray,
    theta_ratio: float,
    initial: LocalisedCurve | None,
) -> AreaFit:
    """Fit the median at rating 0 and beta by weighted least squares on logits.

    Each target's logit residual is multiplied by the square root of its
    weight, so a weight of ``w`` counts as ``w`` targets of weight 1.
    """
    start = initial or LocalisedCurve(3.0, 3.0 / theta_ratio, 0.6)
    goal = _logit(targets["fail_fraction"].to_numpy(dtype=float))
    root_weight = np.sqrt(np.asarray(weights, dtype=float))

    def curve_of(x: np.ndarray) -> LocalisedCurve:
        theta_0 = float(np.exp(x[0]))
        return LocalisedCurve(theta_0, theta_0 / theta_ratio, float(np.exp(x[1])))

    result = least_squares(
        lambda x: root_weight * (_logit(predict(curve_of(x))) - goal),
        x0=np.log([start.theta_at_zero_rating_m_s, start.beta]),
        x_scale=1.0,
    )
    if not result.success:
        msg = f"The calibration did not converge: {result.message}"
        raise ValueError(msg)
    curve = curve_of(result.x)
    predicted = predict(curve)
    residual = _logit(predicted) - goal
    out = targets.copy()
    out["predicted"] = predicted
    out["logit_residual"] = residual
    out["weight"] = np.asarray(weights, dtype=float)
    return AreaFit(
        curve=curve,
        targets=out,
        rms_logit_residual=float(
            np.sqrt(np.sum(out["weight"] * residual**2) / out["weight"].sum())
        ),
    )


class PolygonTarget(NamedTuple):
    """One polygon anchor, ready for the fit.

    Attributes:
        anchor_id: The anchor's id.
        polygons: The matching polygons, with ``pgv_per_g`` for the anchor's
            demand (per g of rock PGA, or of site PGA for a recorded one).
        pga_g_min: The bottom of the anchor's PGA range, g.
        pga_g_max: The top of the anchor's PGA range, g.
        fail_fraction: The share of the matching polygons failing.
        amplified: False for a recorded demand that already carries the
            amplification.
    """

    anchor_id: str
    polygons: LocalisedPolygons
    pga_g_min: float
    pga_g_max: float
    fail_fraction: float
    amplified: bool = True


def fit_record_and_polygons(
    incidence: sparse.csr_array,
    polygons: LocalisedPolygons,
    record: pd.Series,
    polygon_targets: list[PolygonTarget],
    *,
    record_weight: float | None = None,
    theta_ratio: float = FIXED_THETA_RATIO,
    initial: LocalisedCurve | None = None,
) -> AreaFit:
    """Fit the localised curve to a low-demand record and the polygon anchors.

    The method the project lead chose on 2026-10-07. The record (the
    Kaikoura anchor A16) is the expected damaged share of the whole reference
    area at its demand (:func:`scenario_share`); each polygon anchor is the
    mean failure probability of its matching polygons over its PGA range
    (:func:`mean_polygon_failure`). The median keeps its fall of
    ``theta_ratio`` from rating 0 to the top; its scale and the dispersion are
    found by weighted least squares on the logits.

    The record weighs as much as the polygon anchors together by default:
    it is the one observation of the urban ground in Wellington itself, and
    the only one at low demand, while the five polygon anchors are judgement
    readings of forecasts and of another city's record, all at high demand.
    Equal weight stops their number alone from overruling it.

    Args:
        incidence: From :func:`footprint_incidence`.
        polygons: Every bare polygon, with ``pgv_per_g`` per g of rock PGA.
        record: The record's anchor row: ``anchor_id``, ``pga_rock_g_min``,
            ``pga_rock_g_max`` and ``fail_fraction``.
        polygon_targets: The polygon anchors, each with its matching polygons.
        record_weight: The record's weight against 1 for each polygon anchor;
            the number of polygon anchors by default.
        theta_ratio: The median at rating 0 over the median at the top.
        initial: Where the search starts; 3.0 m/s and 0.6 by default.

    Returns:
        The fitted curve, one target row per anchor (``kind`` ``zone_area``
        or ``polygon``) with ``predicted``, ``logit_residual`` and ``weight``,
        and the weighted root mean square logit residual.

    Raises:
        ValueError: If there is no polygon anchor, one matches no polygon, or
            the search fails.
    """
    if not polygon_targets:
        msg = "The fit needs at least one polygon anchor beside the record."
        raise ValueError(msg)
    empty = [t.anchor_id for t in polygon_targets if len(t.polygons.rating) == 0]
    if empty:
        msg = f"The polygon anchors {empty} match no polygon."
        raise ValueError(msg)
    weight = float(len(polygon_targets)) if record_weight is None else record_weight
    rows = [
        {
            "anchor_id": record["anchor_id"],
            "kind": "zone_area",
            "pga_g_min": float(record["pga_rock_g_min"]),
            "pga_g_max": float(record["pga_rock_g_max"]),
            "n_polygons": len(polygons.rating),
            "fail_fraction": float(record["fail_fraction"]),
        },
        *(
            {
                "anchor_id": t.anchor_id,
                "kind": "polygon",
                "pga_g_min": t.pga_g_min,
                "pga_g_max": t.pga_g_max,
                "n_polygons": len(t.polygons.rating),
                "fail_fraction": t.fail_fraction,
            }
            for t in polygon_targets
        ),
    ]

    def predict(curve: LocalisedCurve) -> np.ndarray:
        share = scenario_share(
            incidence,
            polygons,
            curve,
            pga_rock_g_min=float(record["pga_rock_g_min"]),
            pga_rock_g_max=float(record["pga_rock_g_max"]),
        )
        return np.array(
            [
                share,
                *(
                    mean_polygon_failure(
                        t.polygons,
                        curve,
                        pga_g_min=t.pga_g_min,
                        pga_g_max=t.pga_g_max,
                        amplified=t.amplified,
                    )
                    for t in polygon_targets
                ),
            ]
        )

    return _fit_scale_and_beta(
        predict,
        pd.DataFrame(rows),
        weights=np.array([weight, *np.ones(len(polygon_targets))]),
        theta_ratio=theta_ratio,
        initial=initial,
    )


def within_upper_limit(
    incidence: sparse.csr_array,
    polygons: LocalisedPolygons,
    curve: LocalisedCurve,
    limit: pd.Series,
    *,
    cells: npt.NDArray[np.bool_] | None = None,
) -> tuple[float, bool]:
    """Check a curve's damaged share against an anchor read as an upper limit.

    Kingsbury's High scenario 2 share (A12) is kept as a ceiling the adopted
    curve must not pass, not as a target.

    Args:
        incidence: From :func:`footprint_incidence`.
        polygons: The bare polygons, with ``pgv_per_g`` per g of rock PGA.
        curve: The curve to check.
        limit: The anchor row: ``pga_rock_g_min``, ``pga_rock_g_max`` and
            ``fail_fraction`` (the limit).
        cells: Which reference cells make up the reference area.

    Returns:
        ``(share, within)``: the expected share averaged over the anchor's
        range, and whether it is at or below the limit.
    """
    share = scenario_share(
        incidence,
        polygons,
        curve,
        pga_rock_g_min=float(limit["pga_rock_g_min"]),
        pga_rock_g_max=float(limit["pga_rock_g_max"]),
        cells=cells,
    )
    return share, bool(share <= float(limit["fail_fraction"]))
