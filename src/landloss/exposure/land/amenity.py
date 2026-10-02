"""The view of the sea from each address, how far the sea is, and its winter sun.

Three attributes, measured over the elevation model in one pass:

.. code-block:: text

    sea_view_share   = share of compass directions in which the sea is visible
                       within max_distance_m, from eye_height_m above the ground
    coast_distance_m = distance to the nearest sea cell along any of those
                       directions, seen or not; NaN beyond max_distance_m
    winter_sun_share = share of the winter sun the section receives: of the
                       time the sun is up on the sampled days, the share in
                       which it clears the terrain in its direction

Winter sun is what separates a good Wellington section from a bad one, and what
a plain aspect calculation misses: a north-facing slope in the shadow of a
higher ridge across the valley gets none. The rays the view is measured along
already give each address its horizon in every direction, so the sun's path is
run against that horizon, from garden height rather than the upper floor.

A ray is cast from the address in each of ``n_directions`` evenly spaced
bearings, stepping outwards over the DEM. A cell along the ray is visible when
the line from the eye to it clears every cell before it -- its elevation angle
is at least the highest seen so far -- and the direction counts as a sea view
when a visible cell is sea. A panorama across the harbour from Oriental Bay
scores about a half; a house looking at the hillside behind it scores nothing.

The coast distance is the first sea cell each ray reaches, whatever stands in
the way, taken over all the rays. It is the straight-line distance to the coast
to within the angle between two rays, and costs nothing beyond the view: the
rays already walk over every cell it needs. A beachfront house in Lyall Bay is
tens of metres from the coast whether or not the dune in front hides the water.

Sea is decided by :func:`sea_mask`: a cell outside the study area's land and no
higher than ``max_sea_elevation_m``, or one the DEM has no value for. Elevation
alone would not do, because the Petone flats and Rongotai stand only a few
metres above the harbour; the land polygons alone would not either, because the
DEM reaches beyond the study area onto land in Kapiti and the Wairarapa.

Two simplifications bound what the share can be used for. The DEM is bare earth,
so the houses and trees in front of an address do not block its view, which
overstates the view from flat land a few rows back from a beach. And the eye
height is one number for every address, so a single-storey house and an upper
floor are treated alike.

This module only measures. How the two attributes move a land value is
:func:`landloss.exposure.land.land_value.amenity_modifier`.
"""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from rasterio.features import geometry_mask
from rasterio.transform import Affine

from landloss.common.utils.raster import grid_transform

# The attribute columns this module produces, named here so the step script and
# the land value model agree on them.
SEA_VIEW_COLUMN = "sea_view_share"
COAST_DISTANCE_COLUMN = "coast_distance_m"
WINTER_SUN_COLUMN = "winter_sun_share"


@dataclass(frozen=True)
class WinterSun:
    """How the winter sun is sampled.

    Attributes:
        eye_height_m: How far above the ground the horizon is measured from --
            the garden and the living room, not the upper floor the view is
            taken from.
        days_of_year: The days the sun's path is run on.
        minutes_step: The spacing of the times sampled on each day.
    """

    eye_height_m: float
    days_of_year: tuple[int, ...]
    minutes_step: float


# The Earth's radius and the standard refraction coefficient, for the drop of a
# distant cell below the observer's horizontal: d^2 / 2R, less the share light
# bends back over it. About 1.7 m at 5 km, which is the difference between
# seeing the far side of the harbour's waterline and not.
EARTH_RADIUS_M = 6_371_000.0
REFRACTION_COEFFICIENT = 0.13


def sea_mask(
    dem: xr.DataArray, land: gpd.GeoDataFrame, max_sea_elevation_m: float
) -> np.ndarray:
    """Return which cells of the DEM are sea.

    Args:
        dem: The elevation model, with dimensions (y, x), NaN where it has no
            value.
        land: Polygons of land, in the DEM's CRS. Cells inside them are never
            sea.
        max_sea_elevation_m: The highest a cell outside the land can stand and
            still be sea.

    Returns:
        A boolean array shaped like the DEM.

    Raises:
        ValueError: If the land is in a different CRS from the DEM.
    """
    if land.crs != dem.rio.crs:
        msg = f"the land is in {land.crs} and the DEM in {dem.rio.crs}"
        raise ValueError(msg)

    outside_land = geometry_mask(
        land.geometry,
        out_shape=dem.shape,
        transform=grid_transform(dem),
        invert=False,
    )
    values = dem.to_numpy()
    low = np.isnan(values) | (values <= max_sea_elevation_m)
    return outside_land & low


def sea_view_share(
    dem: xr.DataArray,
    sea: np.ndarray,
    points: gpd.GeoSeries,
    *,
    eye_height_m: float,
    max_distance_m: float,
    n_directions: int,
    step_m: float,
    chunk: int = 250,
) -> pd.Series:
    """Return the share of directions in which each point can see the sea.

    The view half of :func:`measure_sea`; see it for the arguments.
    """
    return measure_sea(
        dem,
        sea,
        points,
        eye_height_m=eye_height_m,
        max_distance_m=max_distance_m,
        n_directions=n_directions,
        step_m=step_m,
        chunk=chunk,
    )[SEA_VIEW_COLUMN]


def measure_sea(
    dem: xr.DataArray,
    sea: np.ndarray,
    points: gpd.GeoSeries,
    *,
    eye_height_m: float,
    max_distance_m: float,
    n_directions: int,
    step_m: float,
    winter_sun: "WinterSun | None" = None,
    chunk: int = 250,
) -> pd.DataFrame:
    """Return each point's view of the sea, distance to the coast and winter sun.

    Args:
        dem: The elevation model, with dimensions (y, x) and a regular,
            north-up grid in a projected CRS in metres. NaN cells -- open sea the
            model has no value for -- are taken as sea level.
        sea: Which cells are sea, as :func:`sea_mask` returns.
        points: The addresses, in the DEM's CRS.
        eye_height_m: How far above the ground at the address the view is taken.
        max_distance_m: How far each ray is cast.
        n_directions: How many evenly spaced bearings are cast.
        step_m: The spacing of the samples along each ray.
        winter_sun: The winter sun settings, or None to leave it out. With it,
            the horizon along each ray is measured from the garden and the sun's
            winter path is run against it (:func:`sunlit_share`).
        chunk: How many points are cast at once, which bounds the memory used.

    Returns:
        :data:`SEA_VIEW_COLUMN`, the share for each point between zero and one,
        and :data:`COAST_DISTANCE_COLUMN` in metres -- zero for a point standing
        on a sea cell, NaN when no ray reaches the sea within ``max_distance_m``
        -- indexed as ``points`` is, and :data:`WINTER_SUN_COLUMN` when
        ``winter_sun`` is given. All NaN for a point off the DEM or with no
        geometry.

    Raises:
        ValueError: If the points are in a different CRS from the DEM.
    """
    if points.crs != dem.rio.crs:
        msg = f"the points are in {points.crs} and the DEM in {dem.rio.crs}"
        raise ValueError(msg)

    transform = grid_transform(dem)
    cell_x, cell_y = transform.a, transform.e
    origin_x, origin_y = transform.c, transform.f
    rows_n, cols_n = dem.shape

    # Sea the model left as NaN is at sea level, so it can be seen across.
    elevation = np.where(np.isnan(dem.to_numpy()), 0.0, dem.to_numpy())

    bearings = np.linspace(0.0, 2 * np.pi, n_directions, endpoint=False)
    distances = np.arange(step_m, max_distance_m + step_m / 2, step_m)
    drop = (distances**2 / (2 * EARTH_RADIUS_M)) * (1 - REFRACTION_COEFFICIENT)
    dx = np.cos(bearings)[:, None] * distances[None, :]
    dy = np.sin(bearings)[:, None] * distances[None, :]

    share = pd.Series(np.nan, index=points.index, dtype=float)
    coast = pd.Series(np.nan, index=points.index, dtype=float)
    sun = pd.Series(np.nan, index=points.index, dtype=float)
    present = ~(points.isna() | points.is_empty)
    located = points[present]

    for start in range(0, len(located), chunk):
        batch = located.iloc[start : start + chunk]
        x = batch.x.to_numpy()[:, None, None]
        y = batch.y.to_numpy()[:, None, None]

        col = np.floor((x + dx[None] - origin_x) / cell_x).astype(np.int64)
        row = np.floor((y + dy[None] - origin_y) / cell_y).astype(np.int64)
        inside = (row >= 0) & (row < rows_n) & (col >= 0) & (col < cols_n)
        row_c = np.clip(row, 0, rows_n - 1)
        col_c = np.clip(col, 0, cols_n - 1)

        own_row, own_col, on_grid = _own_cell(
            x[:, 0, 0], y[:, 0, 0], transform, dem.shape
        )
        ground = elevation[own_row, own_col]
        eye = (ground + eye_height_m)[:, None, None]

        # The tangent of the elevation angle to each sample, which orders the
        # same way as the angle and needs no trigonometry.
        heights = elevation[row_c, col_c] - drop[None, None, :]
        tangent = (heights - eye) / distances
        tangent = np.where(inside, tangent, -np.inf)

        # A sample is visible when nothing nearer along the ray stands higher.
        highest_before = np.maximum.accumulate(tangent, axis=2)
        highest_before = np.concatenate(
            [np.full((*tangent.shape[:2], 1), -np.inf), highest_before[..., :-1]],
            axis=2,
        )
        visible = inside & (tangent >= highest_before)

        at_sea = inside & sea[row_c, col_c]
        sees_sea = (visible & at_sea).any(axis=2)
        result = sees_sea.mean(axis=1)
        share.loc[batch.index] = np.where(on_grid, result, np.nan)

        # The nearest sea along any ray, seen or not, and zero where the
        # address itself stands on a sea cell.
        nearest = np.where(at_sea, distances[None, None, :], np.inf).min(axis=(1, 2))
        nearest = np.where(sea[own_row, own_col], 0.0, nearest)
        nearest = np.where(np.isfinite(nearest), nearest, np.nan)
        coast.loc[batch.index] = np.where(on_grid, nearest, np.nan)

        if winter_sun is not None:
            lit = _winter_sun_for_batch(
                heights, inside, ground, distances, batch, winter_sun
            )
            sun.loc[batch.index] = np.where(on_grid, lit, np.nan)

    measured = pd.DataFrame({SEA_VIEW_COLUMN: share, COAST_DISTANCE_COLUMN: coast})
    if winter_sun is not None:
        measured[WINTER_SUN_COLUMN] = sun
    return measured


def _own_cell(
    x: np.ndarray, y: np.ndarray, transform: Affine, shape: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return each point's cell, clipped onto the grid, and whether it is on it."""
    rows_n, cols_n = shape
    col = np.floor((x - transform.c) / transform.a).astype(np.int64)
    row = np.floor((y - transform.f) / transform.e).astype(np.int64)
    on_grid = (row >= 0) & (row < rows_n) & (col >= 0) & (col < cols_n)
    return np.clip(row, 0, rows_n - 1), np.clip(col, 0, cols_n - 1), on_grid


def _winter_sun_for_batch(
    heights: np.ndarray,
    inside: np.ndarray,
    ground: np.ndarray,
    distances: np.ndarray,
    batch: gpd.GeoSeries,
    winter_sun: WinterSun,
) -> np.ndarray:
    """Return the winter sun share for one batch of the ray cast.

    The horizon is measured from the garden rather than the upper floor: the
    highest the terrain stands along each ray, as a tangent. It reuses the
    elevations the view already gathered, so it costs one subtraction.
    """
    garden = (ground + winter_sun.eye_height_m)[:, None, None]
    horizon = np.where(inside, (heights - garden) / distances, -np.inf).max(axis=2)
    latitude = batch.to_crs("EPSG:4326").y.to_numpy()
    return sunlit_share(horizon, latitude, winter_sun)


def solar_position(
    latitude_deg: np.ndarray, day_of_year: int, solar_hours: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return the sun's elevation and azimuth for points, on a day, at times.

    The standard approximations, which are well inside what a 5-degree ray
    spacing can resolve: Cooper's declination, ``23.44 sin(360 (284 + n) / 365)``,
    and the hour angle from local solar time, so noon is when the sun is due
    north (in the southern hemisphere) and no equation of time or time zone is
    needed. The sun's daily path is what matters here, not the clock.

    Args:
        latitude_deg: The latitude of each point, south negative, shape (N,).
        day_of_year: The day, 1 to 365.
        solar_hours: Local solar times, in hours from midnight, shape (T,).

    Returns:
        The elevation above the horizontal and the azimuth clockwise from north,
        both in radians, each shaped (N, T).
    """
    declination = np.radians(
        23.44 * np.sin(np.radians(360 * (284 + day_of_year) / 365))
    )
    latitude = np.radians(np.asarray(latitude_deg, dtype=float))[:, None]
    hour_angle = np.radians(15.0 * (np.asarray(solar_hours, dtype=float) - 12.0))[
        None, :
    ]

    sin_elevation = np.sin(latitude) * np.sin(declination) + np.cos(latitude) * np.cos(
        declination
    ) * np.cos(hour_angle)
    elevation = np.arcsin(np.clip(sin_elevation, -1.0, 1.0))

    cos_azimuth = (np.sin(declination) - np.sin(elevation) * np.sin(latitude)) / (
        np.cos(elevation) * np.cos(latitude)
    )
    azimuth = np.arccos(np.clip(cos_azimuth, -1.0, 1.0))
    # Morning is east of north, afternoon west of it.
    azimuth = np.where(hour_angle > 0, 2 * np.pi - azimuth, azimuth)
    return elevation, azimuth


def sunlit_share(
    horizon: np.ndarray, latitude_deg: np.ndarray, winter_sun: "WinterSun"
) -> np.ndarray:
    """Return the share of the winter sun each point actually receives.

    Of every sampled moment the sun is above the flat horizon on the configured
    days, the share in which it also clears the point's own horizon in that
    direction -- the terrain standing between the section and the sun.

    Args:
        horizon: The tangent of the horizon along each of K evenly spaced
            bearings, measured anticlockwise from east as the rays are, shape
            (N, K); minus infinity where nothing stands above the eye.
        latitude_deg: The latitude of each point, shape (N,).
        winter_sun: The days and time step to sample.

    Returns:
        The share for each point, between zero and one, shape (N,).
    """
    n_directions = horizon.shape[1]
    hours = np.arange(0.0, 24.0, winter_sun.minutes_step / 60.0)
    rows = np.arange(horizon.shape[0])[:, None]

    lit = np.zeros(horizon.shape[0])
    up = np.zeros(horizon.shape[0])
    for day in winter_sun.days_of_year:
        elevation, azimuth = solar_position(latitude_deg, day, hours)
        # The ray nearest the sun's bearing. The rays run anticlockwise from
        # east and the azimuth clockwise from north, so 90 degrees less it.
        bearing = (np.pi / 2 - azimuth) % (2 * np.pi)
        ray = (
            np.rint(bearing / (2 * np.pi / n_directions)).astype(np.int64)
            % n_directions
        )
        above = elevation > 0
        clears = np.tan(np.clip(elevation, 0.0, None)) > horizon[rows, ray]
        lit += (above & clears).sum(axis=1)
        up += above.sum(axis=1)

    return np.divide(lit, up, out=np.full_like(lit, np.nan), where=up > 0)
