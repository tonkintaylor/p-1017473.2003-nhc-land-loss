"""Named study extents the models are run over.

An area of interest is held in WGS84, because that is how extents get quoted and
compared between people, and converted to whatever CRS the caller works in on
demand. Keeping the definition in one place means an extent is never re-typed
from a map into a script.
"""

from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import Polygon, box

from landloss.domain import constants
from landloss.io import ASSETS_DIR

WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class AreaOfInterest:
    """A named rectangular study extent, defined in WGS84.

    Attributes:
        name: A human readable name, used in outputs and file names.
        west: Western boundary, as a WGS84 longitude.
        south: Southern boundary, as a WGS84 latitude.
        east: Eastern boundary, as a WGS84 longitude.
        north: Northern boundary, as a WGS84 latitude.
    """

    name: str
    west: float
    south: float
    east: float
    north: float

    def bbox(
        self, crs: int | str = constants.DEFAULT_CRS
    ) -> tuple[float, float, float, float]:
        """Return the extent as (minx, miny, maxx, maxy) in the given CRS.

        Args:
            crs: The coordinate reference system to express the extent in.

        Returns:
            The bounding box, ready to pass to a reader.
        """
        bounds = self.to_geoseries(crs).total_bounds
        minx, miny, maxx, maxy = (float(value) for value in bounds)
        return (minx, miny, maxx, maxy)

    def polygon(self, crs: int | str = constants.DEFAULT_CRS) -> Polygon:
        """Return the extent as a polygon in the given CRS."""
        return self.to_geoseries(crs).iloc[0]

    def to_geoseries(self, crs: int | str = constants.DEFAULT_CRS) -> gpd.GeoSeries:
        """Return the extent as a single-element GeoSeries in the given CRS."""
        return gpd.GeoSeries(
            [box(self.west, self.south, self.east, self.north)], crs=WGS84
        ).to_crs(crs)


# A small pilot area in Wellington, used to exercise the workflow end to end
# before it is run over the full study area.
SMALL_WLG_PILOT = AreaOfInterest(
    name="Small Wellington pilot",
    west=174.772318,
    south=-41.32486560367306,
    east=174.80616774743507,
    north=-41.309796,
)

# A pilot box over Johnsonville, Newlands and Paparangi, for the slope failure
# susceptibility work. SMALL_WLG_PILOT cannot be used for that: it sits over Mt
# Victoria and Hataitai, and holds not one polygon of the Wellington City
# earthworks record the slope modification factor is built from. This box is
# where that record is densest -- about 190 of the 453 cut and fill polygons,
# roughly 2.8 km2 of mapped earthworks in 16 km2 of hill suburb.
WLG_EARTHWORKS_PILOT = AreaOfInterest(
    name="Johnsonville and Newlands",
    west=174.78881496861425,
    south=-41.231493541571886,
    east=174.83750131663035,
    north=-41.194728870313334,
)

# The Canterbury earthquake sequence study area, covering Christchurch city and
# the flat land around it. This is the extent the observed land damage evidence
# is drawn from -- the only New Zealand dataset holding both settled land claims
# and mapped land damage -- rather than an area the Wellington model is run over.
#
# The flat versus sloping split inside it is not a rectangle and cannot be held
# here; see CHCH_FLAT_ONLY and CHCH_SLOPE_ONLY in
# landloss.exposure.land.landform.
CHRISTCHURCH = AreaOfInterest(
    name="Christchurch",
    west=172.22727348821033,
    south=-43.669039807974436,
    east=172.92244713169507,
    north=-43.28668860936209,
)

# The extents a model build can be run over, by the name a run setting gives
# them. A build's outputs carry the extent in their file names, so builds over
# different extents sit side by side rather than overwriting each other.
#
# FOR ANYONE WRITING A STEP: take `extent` (one of these names) rather than a
# `pilot` flag, choose the ground with `get_area_of_interest(extent)` (None
# means the four territorial authorities), and name every output with
# `extent_suffix(extent)`. Never write `"-pilot" if pilot else ""` or a
# `PILOT = True` setting; run settings say `EXTENT = "wlg-pilot"` (or "full").
# To add an extent, add an AreaOfInterest above and an entry here.
FULL_EXTENT = "full"
EXTENTS = {
    "wlg-pilot": SMALL_WLG_PILOT,
    "wlg-earthworks-pilot": WLG_EARTHWORKS_PILOT,
}

# The file name suffix of an extent whose outputs predate the extent names. The
# small Wellington pilot kept the `-pilot` suffix it had under the old boolean
# setting, so builds already on disk did not need re-running.
_LEGACY_SUFFIXES = {"wlg-pilot": "-pilot"}


def check_extent(extent: str) -> str:
    """Check an extent name is one a build can be run over, and return it.

    Args:
        extent: ``"full"`` for the four territorial authorities, or a key of
            :data:`EXTENTS`.

    Returns:
        The extent name, unchanged.

    Raises:
        KeyError: If the name is neither.
    """
    if extent != FULL_EXTENT and extent not in EXTENTS:
        known = ", ".join([FULL_EXTENT, *EXTENTS])
        msg = f"{extent!r} is not a known extent. Available: {known}"
        raise KeyError(msg)
    return extent


def is_full_extent(extent: str) -> bool:
    """Return whether an extent is the whole study area."""
    return check_extent(extent) == FULL_EXTENT


def get_area_of_interest(extent: str) -> AreaOfInterest | None:
    """Return the box an extent covers, or None for the whole study area.

    Args:
        extent: ``"full"`` or a key of :data:`EXTENTS`.

    Returns:
        The extent's area of interest, or None when the build runs over the four
        territorial authorities (read with :func:`get_study_areas`).
    """
    if is_full_extent(extent):
        return None
    return EXTENTS[extent]


def extent_suffix(extent: str) -> str:
    """Return the file name suffix that keeps an extent's outputs apart.

    Args:
        extent: ``"full"`` or a key of :data:`EXTENTS`.

    Returns:
        ``""`` for the whole study area, so its outputs keep their plain names;
        otherwise ``"-<extent>"``, or the legacy ``"-pilot"`` for the small
        Wellington pilot.
    """
    if is_full_extent(extent):
        return ""
    return _LEGACY_SUFFIXES.get(extent, f"-{extent}")


# The packaged study area boundaries, generated by
# landloss.io.one_offs.gen_study_extent.
STUDY_AREAS_PATH = ASSETS_DIR / "study-areas.geoparquet"


def get_study_areas(crs: int | str = constants.DEFAULT_CRS) -> gpd.GeoDataFrame:
    """Load the four territorial authorities making up the study area.

    Each authority is a separate row, so results can be reported per territorial
    authority rather than only for the study area as a whole. The boundaries are
    packaged with the library, so this reads from disk and needs no API key; run
    ``gen_study_extent.py`` to regenerate them.

    Args:
        crs: The coordinate reference system to return the boundaries in.

    Returns:
        A GeoDataFrame with one row per territorial authority, carrying
        ``ta_code``, ``name`` and ``land_area_sq_km``.

    Raises:
        FileNotFoundError: If the packaged asset is missing.
    """
    if not STUDY_AREAS_PATH.exists():
        msg = (
            f"Study area boundaries are missing from {STUDY_AREAS_PATH}. "
            "Regenerate them with landloss/io/one_offs/gen_study_extent.py."
        )
        raise FileNotFoundError(msg)

    return gpd.read_parquet(STUDY_AREAS_PATH).to_crs(crs)


def get_study_area(
    name: str, crs: int | str = constants.DEFAULT_CRS
) -> gpd.GeoDataFrame:
    """Load a single territorial authority by name.

    Args:
        name: The authority's name, e.g. "Wellington City". Matched case
            insensitively.
        crs: The coordinate reference system to return the boundary in.

    Returns:
        A GeoDataFrame with the one matching row.

    Raises:
        KeyError: If no authority of that name is in the study area.
    """
    study_areas = get_study_areas(crs)
    match = study_areas.loc[study_areas["name"].str.lower() == name.lower()]

    if match.empty:
        known = ", ".join(sorted(study_areas["name"]))
        msg = f"{name!r} is not in the study area. Available: {known}"
        raise KeyError(msg)

    return match.reset_index(drop=True)


def study_area_bbox(
    crs: int | str = constants.DEFAULT_CRS,
) -> tuple[float, float, float, float]:
    """Return the bounding box covering all four territorial authorities.

    Args:
        crs: The coordinate reference system to express the extent in.

    Returns:
        The bounding box (minx, miny, maxx, maxy), ready to pass to a reader.
    """
    minx, miny, maxx, maxy = get_study_areas(crs).total_bounds
    return (float(minx), float(miny), float(maxx), float(maxy))
