"""The lateral spreading adjustment to the land damage probabilities.

Ground near a free face -- a river bank, a lake shore, the coast -- spreads
towards it, and the National Liquefaction Model's land damage probabilities do
not know where the free faces are. The NLM's lateral spreading pilot
(``lats.gen.distance_correction.PiecewiseCorrection`` on its ``lateral-spread``
branch) reads a correction off its reliability plot against the observed
Canterbury damage, and this module applies the same correction (register task
T-47):

- it acts on **P(at least Major)** only, which is land damage states 4 to 6
  together. The NLM leaves the Moderate exceedance alone, finding the distance
  signal in the more severe damage;
- **near a free face**, within :data:`NEAR_FIELD_M`, the probability is raised:
  multiplied by :data:`NEAR_MULTIPLIER` below :data:`KNEE`, and above it lifted
  by the fixed amount that multiplier gives at the knee. A baseline 20% becomes
  35%;
- **far from one**, beyond :data:`FAR_FIELD_M`, it is lowered the same way:
  divided by :data:`FAR_DIVISOR` below the knee, and reduced by a fixed amount
  above it. A baseline 20% becomes 15%;
- **between the two** the NLM blends the near and far maps linearly in distance.

Here the zones are buffers rather than a distance grid, as agreed 2026-09-25:
buffering lines and polygons is quick, where the NLM's grid route took a day for
the lower Waikato. A buffer gives the band a point lies in, not its distance, so
the band between 100 m and 200 m takes the blend at its midpoint
(:data:`MIDDLE_BAND_FAR_WEIGHT`). That is the average of the NLM's blend across
the band, and differs from it by at most half the gap between the near and far
maps at the band's two edges.

**A cell is weighted by how much of it lies in each zone**, not by where its
centre falls (:func:`far_weight_grid`). The NLM grid over Wellington is about
100 m a cell, as wide as the near zone, so a centre rule would put the near zone
in a single row of cells and move it by up to half a cell either way. The zones
are burned at :data:`SUPERSAMPLE` times the resolution and averaged back, which
also comes closer to the NLM's own blend in distance than whole bands would.

**The Major exceedance is capped at the Moderate one.** Raising P(at least
Major) above P(at least Moderate) would leave the pair no longer an exceedance pair
-- :func:`landloss.hazard.liquefaction.land_damage.exceedance_to_bands` refuses
it. Capping moves probability from the Moderate band into Major and worse,
leaving P(at least Moderate) as the NLM gave it, which is consistent with the
NLM correcting the Major level alone.
"""

import geopandas as gpd
import numpy as np
import xarray as xr
from rasterio.features import rasterize
from rasterio.transform import Affine

from landloss.common.utils.raster import grid_transform

# The near field and the far field, in metres from a free face.
NEAR_FIELD_M = 100.0
FAR_FIELD_M = 200.0

# The NLM's piecewise map, read off its reliability plot. Below the knee the
# correction multiplies or divides; above it, it adds or subtracts the amount it
# reached at the knee, so the two branches meet and the lift saturates.
KNEE = 0.075
NEAR_MULTIPLIER = 3.0
FAR_DIVISOR = 3.0

# The zones the buffers make, by the value the zone grid carries.
ZONES = {0: "near", 1: "middle", 2: "far"}

# How far along the near to far blend each zone sits: 0 is the near map, 1 the
# far map. The middle band takes the blend at its midpoint.
MIDDLE_BAND_FAR_WEIGHT = 0.5
FAR_WEIGHTS = {0: 0.0, 1: MIDDLE_BAND_FAR_WEIGHT, 2: 1.0}

# How many sub-cells along each side a cell is burned at, before the weights are
# averaged back onto it: a hundred sub-cells, 10 m across on a 100 m grid.
SUPERSAMPLE = 10


def near_field(p: np.ndarray) -> np.ndarray:
    """Return the near-field map: tripled below the knee, then a fixed lift."""
    lift = (NEAR_MULTIPLIER - 1.0) * KNEE
    return np.where(p <= KNEE, NEAR_MULTIPLIER * p, p + lift)


def far_field(p: np.ndarray) -> np.ndarray:
    """Return the far-field map: a third below the knee, then a fixed drop."""
    drop = KNEE * (1.0 - 1.0 / FAR_DIVISOR)
    return np.where(p <= KNEE, p / FAR_DIVISOR, p - drop)


def correct_major_or_worse(
    major_or_worse: np.ndarray, far_weight: np.ndarray
) -> np.ndarray:
    """Apply the piecewise correction to P(at least Major).

    Args:
        major_or_worse: The baseline probability, per cell.
        far_weight: Where each cell sits between the near map (0) and the far
            map (1), per cell; see :data:`FAR_WEIGHTS`.

    Returns:
        The corrected probability, clipped to [0, 1]. A missing baseline stays
        missing.
    """
    p = np.asarray(major_or_worse, dtype=float)
    t = np.asarray(far_weight, dtype=float)
    blended = (1.0 - t) * near_field(p) + t * far_field(p)
    return np.clip(blended, 0.0, 1.0)


def lateral_spreading_zones(free_faces: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Buffer the free faces into the near and middle zones.

    Args:
        free_faces: The free faces, from
            :func:`landloss.hazard.liquefaction.waterways.get_free_faces`, in a
            projected CRS.

    Returns:
        Two rows, ``near`` (within :data:`NEAR_FIELD_M`) and ``middle`` (from
        there to :data:`FAR_FIELD_M`), carrying ``zone`` and ``zone_name``.
        Everywhere else is the far zone. Either row may be empty geometry when
        there are no free faces.
    """
    faces = free_faces.geometry.union_all()
    near = faces.buffer(NEAR_FIELD_M)
    middle = faces.buffer(FAR_FIELD_M).difference(near)
    return gpd.GeoDataFrame(
        {"zone": [0, 1], "zone_name": [ZONES[0], ZONES[1]]},
        geometry=[near, middle],
        crs=free_faces.crs,
    )


def _burn(zones: gpd.GeoDataFrame, like: xr.DataArray, supersample: int) -> np.ndarray:
    """Burn the zones at ``supersample`` times ``like``'s resolution.

    Each sub-cell takes the zone its centre falls in, and the far zone where
    no buffer reaches.

    Raises:
        ValueError: If the zones and the grid disagree on their CRS.
    """
    if zones.crs != like.rio.crs:
        msg = f"zones are {zones.crs} and the grid is {like.rio.crs}"
        raise ValueError(msg)
    rows, columns = like.shape
    shape = (rows * supersample, columns * supersample)
    far = max(ZONES)
    shapes = [
        (geometry, zone)
        for geometry, zone in zip(zones.geometry, zones["zone"], strict=True)
        if not geometry.is_empty
    ]
    if not shapes:
        return np.full(shape, far, dtype="uint8")
    transform = grid_transform(like) @ Affine.scale(1 / supersample)
    return rasterize(
        shapes, out_shape=shape, transform=transform, fill=far, dtype="uint8"
    )


def zone_grid(zones: gpd.GeoDataFrame, like: xr.DataArray) -> xr.DataArray:
    """Return the zone each cell's centre falls in, for describing a run.

    The correction itself reads :func:`far_weight_grid`; this is the coarse view
    a run prints its per-zone means over.

    Args:
        zones: From :func:`lateral_spreading_zones`, in ``like``'s CRS.
        like: The grid to burn onto, a two-dimensional north-up raster with a
            CRS, at least two cells along each side.

    Returns:
        The zone of each cell, as the keys of :data:`ZONES`, on ``like``'s grid.

    Raises:
        ValueError: If the zones and the grid disagree on their CRS.
    """
    return like.copy(data=_burn(zones, like, 1)).rename("ls_zone")


def far_weight_grid(
    zones: gpd.GeoDataFrame, like: xr.DataArray, supersample: int = SUPERSAMPLE
) -> xr.DataArray:
    """Return each cell's place between the near map (0) and the far map (1).

    The mean of :data:`FAR_WEIGHTS` over the cell's sub-cells, so a cell half in
    the near zone and half in the far zone sits halfway along the blend.

    Args:
        zones: From :func:`lateral_spreading_zones`, in ``like``'s CRS.
        like: The grid to weight, a two-dimensional north-up raster with a CRS,
            at least two cells along each side.
        supersample: Sub-cells along each side of a cell.

    Returns:
        The weight of each cell, on ``like``'s grid.

    Raises:
        ValueError: If the zones and the grid disagree on their CRS.
    """
    burned = _burn(zones, like, supersample)
    lookup = np.array([FAR_WEIGHTS[code] for code in sorted(FAR_WEIGHTS)])
    weights = lookup[burned]
    rows, columns = like.shape
    averaged = weights.reshape(rows, supersample, columns, supersample).mean(
        axis=(1, 3)
    )
    return like.copy(data=averaged).rename("ls_far_weight")


def apply_lateral_spreading(
    moderate_or_worse: xr.DataArray,
    major_or_worse: xr.DataArray,
    far_weight: xr.DataArray,
) -> tuple[xr.DataArray, xr.DataArray]:
    """Correct P(at least Major) for lateral spreading, capped at P(at least Moderate).

    Args:
        moderate_or_worse: P(at least Moderate), per cell, left as it is.
        major_or_worse: P(at least Major), per cell, on the same grid.
        far_weight: Each cell's place on the blend, from :func:`far_weight_grid`.

    Returns:
        The corrected P(at least Major), and a boolean grid of the cells where
        the cap bound.
    """
    corrected = correct_major_or_worse(major_or_worse.to_numpy(), far_weight.to_numpy())
    ceiling = moderate_or_worse.to_numpy()
    capped = corrected > ceiling
    corrected = np.where(capped, ceiling, corrected)
    return major_or_worse.copy(data=corrected), major_or_worse.copy(data=capped)
