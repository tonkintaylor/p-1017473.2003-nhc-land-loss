"""Terrain cross-sections sampled from the LINZ 1 m LiDAR DEM.

A cross-section is the quickest way to see the shape of a valley: how wide the
flat floor is, how steeply the sides rise, and where a river sits within it. All
three matter here, because liquefaction concentrates on the flat alluvium and
slope failure on the sides, and a section shows the boundary between them
directly rather than through a derived slope raster.

Sections are defined by a centre, a bearing and a length rather than by two
endpoints, so that a perpendicular pair is perpendicular by construction instead
of by hand-checked coordinates.

All geometry is EPSG:2193, and bearings are degrees clockwise from grid north.
"""

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from landloss.domain import constants
from landloss.io.elevation import sample_elevation as sample_points

# Sampling a metre apart matches the DEM's native resolution; anything finer
# only interpolates between the same cells.
DEFAULT_SPACING_M = 1.0


@dataclass(frozen=True)
class CrossSection:
    """A straight line across the terrain, to be sampled against the DEM.

    Attributes:
        name: A human readable name, used in titles and file names.
        centre: The (easting, northing) the section is centred on, in NZTM.
        bearing: Direction of the section, in degrees clockwise from grid north.
        length_m: Total length of the section, in metres.
        description: What the section is meant to show.
    """

    name: str
    centre: tuple[float, float]
    bearing: float
    length_m: float
    description: str = ""

    @property
    def line(self) -> LineString:
        """Return the section as a line in NZTM."""
        # Bearings are clockwise from north, so easting follows sin and
        # northing cos -- the transpose of the usual maths convention.
        radians = math.radians(self.bearing)
        dx = math.sin(radians) * self.length_m / 2
        dy = math.cos(radians) * self.length_m / 2
        east, north = self.centre
        return LineString([(east - dx, north - dy), (east + dx, north + dy)])

    def perpendicular(
        self, name: str, length_m: float | None = None, description: str = ""
    ) -> "CrossSection":
        """Return a section at right angles to this one, through the same centre.

        Args:
            name: Name for the new section.
            length_m: Its length; defaults to this section's length.
            description: What the new section is meant to show.

        Returns:
            A section rotated 90 degrees clockwise from this one.
        """
        return CrossSection(
            name=name,
            centre=self.centre,
            bearing=(self.bearing + 90) % 360,
            length_m=self.length_m if length_m is None else length_m,
            description=description,
        )


def sample_elevation(
    section: CrossSection,
    *,
    spacing_m: float = DEFAULT_SPACING_M,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Sample the 1 m LiDAR DEM along a cross-section.

    Only the cells under the line are read, so the cost scales with the length
    of the section rather than with the area of its bounding box. That matters
    for a diagonal section, whose bounding box can be far larger than the line.

    See :func:`landloss.io.elevation.sample_elevation` for the data licence; the
    LINZ elevation catalogue is CC BY 4.0 and requires attribution on anything
    published from it, including these figures.

    Args:
        section: The section to sample.
        spacing_m: Distance between samples along the line, in metres.
        use_cache: Whether to read and write the STAC catalogue cache.

    Returns:
        A DataFrame with ``distance_m``, ``easting``, ``northing`` and
        ``elevation_m``, ordered from the start of the line. Elevation is NaN
        where no LiDAR survey covers the point.

    Raises:
        ValueError: If the section has no length.
    """
    line = section.line
    if line.length <= 0:
        msg = f"Section {section.name!r} has zero length."
        raise ValueError(msg)

    count = max(int(line.length / spacing_m) + 1, 2)
    distances = np.linspace(0.0, line.length, count)
    points = [line.interpolate(float(d)) for d in distances]
    eastings = np.array([p.x for p in points])
    northings = np.array([p.y for p in points])

    elevation = sample_points(eastings, northings, use_cache=use_cache)

    return pd.DataFrame(
        {
            "distance_m": distances,
            "easting": eastings,
            "northing": northings,
            "elevation_m": elevation,
        }
    )


def sections_to_geodataframe(sections: list[CrossSection]) -> gpd.GeoDataFrame:
    """Return the section lines as a GeoDataFrame, for drawing a locality map."""
    return gpd.GeoDataFrame(
        {
            "name": [s.name for s in sections],
            "bearing": [s.bearing for s in sections],
            "length_m": [s.length_m for s in sections],
            "description": [s.description for s in sections],
        },
        geometry=[s.line for s in sections],
        crs=constants.DEFAULT_CRS,
    )


def find_crossings(section: CrossSection, waterways: gpd.GeoDataFrame) -> pd.DataFrame:
    """Find where a section crosses mapped watercourses.

    A section is drawn to cut a particular valley, so the figure has to show
    where the river actually is; without it a reader is left guessing which of
    the low points in the profile is the channel.

    Args:
        section: The section to test.
        waterways: Watercourse centrelines in the same CRS, as returned by
            :func:`landloss.hazard.liquefaction.waterways.get_waterways`.

    Returns:
        A DataFrame of ``distance_m``, ``name`` and ``wtype``, one row per
        crossing, ordered along the section. Empty if nothing is crossed.
    """
    line = section.line
    hits = waterways.loc[waterways.intersects(line)]

    rows = []
    # Zipped rather than itertuples, because a column literally called "name"
    # is ambiguous with the namedtuple's own attribute.
    for geometry, name, wtype in zip(
        hits.geometry, hits["name"], hits["wtype"], strict=True
    ):
        intersection = geometry.intersection(line)
        geometries = (
            intersection.geoms if hasattr(intersection, "geoms") else [intersection]
        )
        for part in geometries:
            if part.is_empty:
                continue
            # A crossing is normally a point; take the representative point so a
            # short overlapping segment still yields one distance.
            point = part if part.geom_type == "Point" else part.representative_point()
            rows.append(
                {
                    "distance_m": line.project(point),
                    "name": name,
                    "wtype": wtype,
                }
            )

    if not rows:
        return pd.DataFrame(columns=["distance_m", "name", "wtype"])

    return pd.DataFrame(rows).sort_values("distance_m").reset_index(drop=True)
