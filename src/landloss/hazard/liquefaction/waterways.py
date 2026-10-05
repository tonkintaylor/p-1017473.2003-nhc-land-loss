"""Waterways for the study area, split into named rivers and everything else.

Distance to a waterway free-face drives lateral spreading, but not every
watercourse is a free-face: a major river has banks metres high, while a piped
or shallow urban stream has effectively none. The split kept here is the one the
National Liquefaction Model uses -- a feature counts as a river when its name
says so -- so that the two studies classify the same watercourse the same way.

The smaller watercourses are kept rather than discarded, because the report has
to show what was considered and rejected, not only what was used.

The lateral spreading zones are buffered from a different, narrower layer: the
**free faces**, from :func:`get_free_faces`. It rebuilds the NLM's own layer
(``lats.gen.waterways.get_major_waterways`` on its ``lateral-spread`` branch)
from the same sources with the same filters, so that the two studies buffer the
same ground (register task T-46):

- the river name lines whose name contains "river", plus a short list kept by
  ID (:data:`EXTRA_RIVER_SECTION_IDS`);
- the topo50 river, lake, swamp and lagoon polygons of at least
  :data:`MIN_FREE_FACE_AREA_M2`, kept as areas rather than outlines, so a
  buffer drawn from them starts at the water's edge and covers the water too;
- the topo50 coastline, which the NLM counts as a free face because a harbour
  or estuary margin spreads like a river bank.
"""

from collections.abc import Callable

import geopandas as gpd
import pandas as pd
from shapely import is_empty, is_missing
from shapely.geometry.base import BaseGeometry

from landloss.domain import constants
from landloss.io.readers import get_nz_river_name_lines, get_nz_topo50_water

# A feature is treated as a river when this appears in its name, matched case
# insensitively. Crude, but it is what the source layer supports: ``feat_type``
# does not reliably separate a river from a stream across the country.
RIVER_NAME_PATTERN = "river"

# The values the ``wtype`` column takes.
WATERWAY_TYPES = ("river", "other")

# River name line features kept by ID as well as by name, because they are major
# watercourses whose name does not say "river". The NLM's list. All four lie
# around Bottle Lake in Christchurch, so none falls in this study's extent.
NLM_EXTRA_RIVER_SECTION_IDS = (7495748, 7189907, 7495747, 6974823)

# This study's additions to the NLM's list, for Wellington (register task T-48).
# Empty, so the free faces are the NLM's layer with nothing added.
#
# The Waiwhetu Stream was added here on 2026-10-02, both of its sections --
# river sections 6818507 and 7212609, 7.5 km to the harbour at Seaview -- since
# it crosses the liquefiable lower Hutt Valley floor to its mouth, as the Bottle
# Lake watercourses do in Christchurch. Taken out again on 2026-10-05, by Perrie
# Gilbert, pending Maxim Millen's view (Q-19). Those two IDs are what to put back
# if it is to count.
WELLINGTON_EXTRA_RIVER_SECTION_IDS: tuple[int, ...] = ()

EXTRA_RIVER_SECTION_IDS = NLM_EXTRA_RIVER_SECTION_IDS + (
    WELLINGTON_EXTRA_RIVER_SECTION_IDS
)

# The smallest water body polygon counted as a free face, in square metres: 5 ha.
# The NLM's, chosen there by an ablation over none, 0.5, 1 and 5 ha that found
# 5 ha gave the cleanest distance to damage signal. It drops the pond-sized
# majority of the topo50 lakes, which have no free face and dilute the lift
# near one. Lines -- the rivers and the coast -- are kept whatever their size.
MIN_FREE_FACE_AREA_M2 = 50_000.0

# The values the free faces' ``wtype`` column takes: the NLM's, in its order.
FREE_FACE_TYPES = ("river", "coast", "lake", "swamp", "lagoon")

# The topo50 water body layers read for free faces. Each kind is also the
# ``wtype`` its features are given; the river polygons are rivers, the same as
# the river name lines.
FREE_FACE_POLYGON_KINDS = ("river", "lake", "swamp", "lagoon")


def classify_waterways(waterways: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Tag each watercourse as a named river or as other, and drop empty geometry.

    Kept separate from :func:`get_waterways` so that the classification can be
    exercised without reaching for the network.

    Args:
        waterways: Watercourse centrelines carrying a ``name`` column.

    Returns:
        A copy with a ``wtype`` column added, holding one of
        :data:`WATERWAY_TYPES`, and with null or empty geometry removed.
    """
    classified = waterways.copy()

    # ``na=False`` sends unnamed features to "other" rather than to NaN; an
    # unnamed watercourse is not one of the major rivers by definition.
    is_river = (
        classified["name"]
        .astype("string")
        .str.contains(RIVER_NAME_PATTERN, case=False, na=False)
    )
    classified["wtype"] = is_river.map({True: "river", False: "other"})

    # Tested at the shapely level rather than with GeoSeries.notna, which warns
    # when the series holds empty geometry -- and empty geometry is exactly the
    # case being looked for here.
    geometries = classified.geometry.to_numpy()
    keep = ~is_missing(geometries) & ~is_empty(geometries)
    return classified.loc[keep].reset_index(drop=True)


def get_waterways(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    clip_to: gpd.GeoDataFrame | gpd.GeoSeries | BaseGeometry | None = None,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the watercourses for an extent, tagged as named rivers or other.

    A bounding box is a rectangle, and the study area is not: reading the four
    Wellington territorial authorities by their bounds alone also picks up much
    of the Wairarapa, whose rivers are not part of this study. Pass ``clip_to``
    as well to cut the result back to the real boundary, while ``bbox`` keeps the
    read itself cheap.

    Args:
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``. Omitting it
            reads every watercourse in New Zealand, which is rarely wanted.
        crs: The coordinate reference system to return the watercourses in.
        clip_to: Optionally, a boundary to cut the watercourses back to, in
            ``crs``. Anything ``geopandas.clip`` accepts.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of watercourse centrelines with a ``wtype`` column.
    """
    waterways = get_nz_river_name_lines(bbox=bbox, crs=crs, use_cache=use_cache)

    if clip_to is not None:
        # Clip before classifying, so that the empty geometry a clip leaves
        # behind is dropped by classify_waterways rather than reaching the plot.
        waterways = waterways.clip(clip_to)

    return classify_waterways(waterways)


def _drop_empty(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop null and empty geometry, and reset the index."""
    geometries = frame.geometry.to_numpy()
    keep = ~is_missing(geometries) & ~is_empty(geometries)
    return frame.loc[keep].reset_index(drop=True)


def named_rivers(
    names: gpd.GeoDataFrame,
    extra_ids: tuple[int, ...] = EXTRA_RIVER_SECTION_IDS,
) -> gpd.GeoDataFrame:
    """Return the river name lines that count as free faces.

    Those whose name contains "river", matched as :func:`classify_waterways`
    matches it, and those whose ``river_section_id`` is in ``extra_ids``.

    Args:
        names: The river name lines, carrying ``name`` and ``river_section_id``.
        extra_ids: Features kept by ID whatever their name.

    Returns:
        The kept lines.
    """
    is_river = (
        names["name"]
        .astype("string")
        .str.contains(RIVER_NAME_PATTERN, case=False, na=False)
    )
    is_extra = pd.to_numeric(names["river_section_id"], errors="coerce").isin(extra_ids)
    return names.loc[is_river | is_extra]


def assemble_free_faces(
    names: gpd.GeoDataFrame,
    polygons: dict[str, gpd.GeoDataFrame],
    coast: gpd.GeoDataFrame,
    *,
    min_area_m2: float = MIN_FREE_FACE_AREA_M2,
    extra_ids: tuple[int, ...] = EXTRA_RIVER_SECTION_IDS,
) -> gpd.GeoDataFrame:
    """Combine the source layers into one free-face layer, filtered as the NLM does.

    Kept apart from :func:`get_free_faces` so that the filters can be exercised
    without reaching for the network.

    Args:
        names: The river name lines.
        polygons: The topo50 water body polygons, keyed by the ``wtype`` each is
            given: some or all of :data:`FREE_FACE_POLYGON_KINDS`.
        coast: The topo50 coastline.
        min_area_m2: The smallest water body polygon kept.
        extra_ids: River name line features kept by ID whatever their name.

    Returns:
        One row per feature, carrying ``wtype`` (one of
        :data:`FREE_FACE_TYPES`), ``source`` (``name line``, ``polygon`` or
        ``coastline``), ``name`` where the source layer has one, and the
        geometry, with null and empty geometry removed.

    Raises:
        ValueError: If a polygon layer is keyed by anything outside
            :data:`FREE_FACE_POLYGON_KINDS`, or the layers disagree on their CRS.
    """
    unknown = set(polygons) - set(FREE_FACE_POLYGON_KINDS)
    if unknown:
        msg = (
            f"polygon layers must be keyed by {FREE_FACE_POLYGON_KINDS}, "
            f"not {sorted(unknown)}"
        )
        raise ValueError(msg)
    crses = {frame.crs for frame in [names, coast, *polygons.values()]}
    if len(crses) > 1:
        msg = f"the layers are in more than one CRS: {crses}"
        raise ValueError(msg)

    def tagged(frame: gpd.GeoDataFrame, wtype: str, source: str) -> pd.DataFrame:
        name = frame["name"].to_numpy() if "name" in frame.columns else None
        return pd.DataFrame(
            {
                "wtype": wtype,
                "source": source,
                "name": name,
                "geometry": frame.geometry.to_numpy(),
            }
        )

    parts = [tagged(named_rivers(names, extra_ids), "river", "name line")]
    parts += [
        tagged(frame.loc[frame.geometry.area >= min_area_m2], wtype, "polygon")
        for wtype, frame in polygons.items()
    ]
    parts.append(tagged(coast, "coast", "coastline"))

    free_faces = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), geometry="geometry", crs=names.crs
    )
    return _drop_empty(free_faces)


def get_free_faces(
    bbox: tuple[float, float, float, float],
    crs: int | str = constants.DEFAULT_CRS,
    clip_to: gpd.GeoDataFrame | gpd.GeoSeries | BaseGeometry | None = None,
    *,
    use_cache: bool = True,
    read_water: Callable[..., gpd.GeoDataFrame] = get_nz_topo50_water,
) -> gpd.GeoDataFrame:
    """Load the lateral spreading free faces for an extent.

    The NLM's free-face layer, rebuilt from the same LINZ sources with the same
    filters: see the module docstring, and :func:`assemble_free_faces` for the
    columns.

    Args:
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``. Required,
            because every source is national.
        crs: The coordinate reference system to return the free faces in.
        clip_to: Optionally, a boundary to cut the result back to, in ``crs``.
        use_cache: Whether to read and write the clipped extent cache.
        read_water: Reads one topo50 water layer by kind; replaced in tests.

    Returns:
        The free faces within the extent.
    """
    names = get_nz_river_name_lines(bbox=bbox, crs=crs, use_cache=use_cache)
    polygons = {
        kind: read_water(kind, bbox=bbox, crs=crs, use_cache=use_cache)
        for kind in FREE_FACE_POLYGON_KINDS
    }
    coast = read_water("coast", bbox=bbox, crs=crs, use_cache=use_cache)

    # The area filter runs on what the bbox read left, so a lake cut by the edge
    # of the box is measured by the part inside it. The NLM filters after its
    # clip in the same way, and the edge of the extent is not where a buffer
    # matters, so it is let stand.
    free_faces = assemble_free_faces(names, polygons, coast)
    if clip_to is None:
        return free_faces
    return _drop_empty(free_faces.clip(clip_to))
