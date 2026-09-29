"""Readers for the vector datasets the landloss models are built from.

Downloads are cached twice over. ttpy caches the whole downloaded layer, keyed by
layer ID, version and a hash of its details, so a layer is fetched from
Koordinates once. On top of that, this module caches the clipped extent, so
asking for the same extent of the same layer version a second time skips reading
and clipping the source.

Measured against the 809 MB NZ Addresses layer, that second cache saves little:
GeoPackage is spatially indexed, so pushing the bounding box down into the read
is already about as fast as reading a small cached copy back. The download is the
expensive step, and ttpy already caches it.

The extent cache only applies when a bounding box is given. Without one there is
no clip to skip, and caching would store a second full copy of a layer ttpy has
already cached.
"""

import hashlib
import os
from pathlib import Path

import dotenv
import geopandas as gpd
import pandas as pd
import requests
from shapely import box, make_valid
from ttpy.gis.koop import KoordinatesConnection, get_latest_layer

from landloss.domain import constants
from landloss.io import koopcache_dir

dotenv.load_dotenv()

# How long to wait on one ArcGIS REST page before giving up, in seconds. Council
# services are slower than Koordinates, and a full page is a real download.
ARCGIS_TIMEOUT_SECONDS = 120


def resolve_api_key(domain: str) -> str:
    """Return the API key for a Koordinates domain.

    Each domain has its own key, so the key is chosen by domain rather than read
    from a single variable.

    Args:
        domain: The Koordinates domain the key is needed for.

    Returns:
        The API key.

    Raises:
        ValueError: If the domain is unknown, or its variable is not set.
    """
    env_var = constants.API_KEY_ENV_VARS.get(domain)
    if env_var is None:
        known = ", ".join(sorted(constants.API_KEY_ENV_VARS))
        msg = (
            f"No API key variable is configured for {domain!r}. Known domains: {known}"
        )
        raise ValueError(msg)

    api_key = os.environ.get(env_var)
    if not api_key:
        msg = f"Set {env_var} in the .env file to read layers from {domain}."
        raise ValueError(msg)

    return api_key


def extent_cache_dir() -> Path:
    """Return the directory clipped extents are cached in, creating it if needed."""
    return koopcache_dir("extents")


def extent_cache_path(
    source: Path, crs: int | str, bbox: tuple[float, float, float, float] | None
) -> Path:
    """Return the cache file for one clipped extent of one layer.

    The source file name encodes the layer ID, its version and a hash of its
    details, so a cache entry cannot outlive the layer version it came from.

    Args:
        source: The file the extent was clipped out of.
        crs: The CRS the extent was reprojected to.
        bbox: The bounding box the extent was clipped to, if any.

    Returns:
        The path the clipped extent is cached at.
    """
    key = f"{source.name}|{crs}|{bbox}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return extent_cache_dir() / f"{source.stem}_{digest}.gpkg"


def get_koordinates_layer_extent(
    layer: int | Path,
    crs: int | str = constants.DEFAULT_CRS,
    bbox: tuple[float, float, float, float] | None = None,
    domain: str = constants.TTGROUP_DOMAIN,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load a Koordinates vector layer, reprojected and clipped to an extent.

    Args:
        layer: The Koordinates ID of the layer to download, or a path to a local
            file to read instead. An integer is treated as a layer ID.
        crs: The coordinate reference system to reproject the layer to.
        bbox: Optionally, clip to this bounding box (minx, miny, maxx, maxy),
            expressed in ``crs``. Geometries straddling the edge are cut at it.
        domain: The Koordinates domain to download from. Only used when ``layer``
            is a layer ID; the matching API key is chosen from it.
        use_cache: Whether to read and write the clipped extent cache. Pass False
            to force the clip to be recomputed from the source.

    Returns:
        A GeoDataFrame containing the layer, in ``crs`` and clipped to ``bbox``.

    Raises:
        ValueError: If a layer ID is given and no API key is set for ``domain``.
    """
    if isinstance(layer, int):
        conn = KoordinatesConnection(api_key=resolve_api_key(domain), domain=domain)
        try:
            layer_path = get_latest_layer(conn=conn, layer_id=layer)
        finally:
            conn.close()
    else:
        layer_path = Path(layer)

    # Only an actual clip is worth caching. Without a bbox the cache would hold a
    # full duplicate of a layer ttpy has already cached — gigabytes, for a
    # national layer — to save only the reprojection, which measured slower than
    # reading the duplicate back.
    cache_wanted = use_cache and bbox is not None

    cache_path = extent_cache_path(layer_path, crs, bbox)
    if cache_wanted and cache_path.exists():
        return gpd.read_file(cache_path)

    layer_gdf = _read_extent(layer_path, crs, bbox)

    # An empty frame has no geometry type for the driver to write, so there is
    # nothing worth caching; recomputing an empty result is cheap anyway.
    if cache_wanted and not layer_gdf.empty:
        layer_gdf.to_file(cache_path)

    return layer_gdf


def _read_extent(
    layer_path: Path, crs: int | str, bbox: tuple[float, float, float, float] | None
) -> gpd.GeoDataFrame:
    """Read a layer from disk, reprojecting and clipping it to an extent."""
    if bbox is None:
        return gpd.read_file(layer_path).to_crs(crs)

    minx, miny, maxx, maxy = bbox

    # Push the bounding box down into the read so that a national layer is never
    # loaded whole. Passing a GeoSeries lets geopandas transform it into the
    # source CRS, which we do not otherwise need to know.
    bbox_filter = gpd.GeoSeries([box(minx, miny, maxx, maxy)], crs=crs)
    layer_gdf: gpd.GeoDataFrame = gpd.read_file(layer_path, bbox=bbox_filter)

    # Reproject before the final clip so the box is applied in the CRS asked for
    # rather than whatever the layer happened to be published in.
    layer_gdf = layer_gdf.to_crs(crs)

    # Cut the geometries at the bounding box; the read filter above is only a
    # coarse intersection test.
    return layer_gdf.clip(box(minx, miny, maxx, maxy))


def get_nz_addresses(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LINZ NZ Addresses layer for an extent.

    This is the address point layer at
    https://data.linz.govt.nz/layer/123113-nz-addresses/, used as the starting
    point for the exposure model.

    The layer covers the whole country, so passing a bounding box is strongly
    preferred; the first call for a given extent downloads and clips the layer,
    and later calls for the same extent are served from the cache.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every address in New Zealand.
        crs: The coordinate reference system to return the addresses in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of address points.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_ADDRESSES_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LINZ_DOMAIN,
        use_cache=use_cache,
    )


def get_nz_building_outlines(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LINZ NZ Building Outlines layer for an extent.

    The building footprint layer at
    https://data.linz.govt.nz/layer/101290-nz-building-outlines/, captured from
    aerial imagery. The insured land extent is buffered off these outlines,
    because NHC land cover attaches to the ground around the dwelling rather
    than to the whole parcel, so the building is what the extent is measured
    from.

    Each outline carries a ``building_id``, a ``use``, the suburb, town and
    territorial authority it sits in, and the capture source and date it was
    digitised from. Nothing distinguishes a dwelling from a garage or a shed, so
    an extent built from the layer covers every structure on a property.

    Licence:
        Creative Commons Attribution 4.0 International (CC BY 4.0),
        https://data.linz.govt.nz/license/attribution-4-0-international/. The
        data may be shared and adapted, including commercially, provided Land
        Information New Zealand is credited as the source, a link to the licence
        is given, and any changes made are indicated. So every figure, table or
        layer published from the insured land extent -- which is derived from
        these outlines -- has to carry that attribution with it.

    Source:
        Land Information New Zealand, National Topographic Office. No DOI is
        published for the layer.

    The layer covers the whole country at 3.2 million buildings, so passing a
    bounding box is strongly preferred; the first call for a given extent
    downloads and clips the layer, and later calls for the same extent are
    served from the cache.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every building outline in New Zealand.
        crs: The coordinate reference system to return the outlines in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of building footprint polygons.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_BUILDING_OUTLINES_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LINZ_DOMAIN,
        use_cache=use_cache,
    )


def get_nz_property_boundaries(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LINZ NZ Property Boundaries layer for an extent.

    The property polygons at
    https://data.linz.govt.nz/layer/122657-nz-property-boundaries/, LINZ's best
    available representation of a property. It is built from rating units where
    they exist, then spatialised titles, then primary parcels, so one polygon is
    one rateable property rather than one parcel or one title.

    The field this study reads it for is ``title_type``, which is the only
    statement anywhere in the exposure data of **how a property is held**:
    freehold, unit title, cross-lease, leasehold. That is what decides whether
    several addresses on one building outline own separate land or share it, and
    so whether the insured land around a block is one extent or several. Nothing
    else available distinguishes those.

    Each polygon also carries ``valuation_reference``, ``legal_description``,
    ``title_no``, the territorial authority, the rated ``area`` and the
    identifiers of the unit of property, parcel and untitled land it came from.

    Licence:
        Creative Commons Attribution 4.0 International (CC BY 4.0),
        https://data.linz.govt.nz/license/attribution-4-0-international/. The
        data may be shared and adapted, including commercially, provided Land
        Information New Zealand is credited as the source, a link to the licence
        is given, and any changes made are indicated. So any figure, table or
        layer published from these boundaries has to carry that attribution.

    Source:
        Land Information New Zealand. No DOI is published for the layer, which
        is rebuilt weekly, so a result taken from it should record the date it
        was read.

    The layer covers the whole country at 2.7 million properties, so passing a
    bounding box is strongly preferred; the first call for a given extent
    downloads and clips the layer, and later calls for the same extent are
    served from the cache.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every property boundary in New Zealand.
        crs: The coordinate reference system to return the boundaries in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of property boundary polygons.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_PROPERTY_BOUNDARIES_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LINZ_DOMAIN,
        use_cache=use_cache,
    )


def get_nz_address_roads(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LINZ NZ Addresses: Roads layer for an extent.

    The road centrelines of the LINZ addressing dataset,
    https://data.linz.govt.nz/layer/123110-nz-addresses-roads/. A driveway is
    generated as the shortest path from a building to a road, so this is the
    layer the insured land extent is routed to.

    Preferred over the topographic road centrelines because it belongs to the
    same addressing dataset as the address spine: a property's driveway meets
    the road its address is numbered on, so the road geometry and the address
    points already agree rather than having to be reconciled across two
    surveys at different generalisations.

    Licence:
        Creative Commons Attribution 4.0 International (CC BY 4.0),
        https://data.linz.govt.nz/license/attribution-4-0-international/. In
        practice that obliges us to credit LINZ in anything published that is
        derived from it -- which here means the insured land extent, and so
        every figure and table of land exposure, land damage or loss built on
        that extent, since the driveway is part of the insured area.

    Source:
        Land Information New Zealand, data.linz.govt.nz. No DOI is published
        for the layer.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``.
            Omitting it returns every road in New Zealand, 82,364 of them.
        crs: The coordinate reference system to return the roads in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of road centrelines.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_ADDRESS_ROADS_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LINZ_DOMAIN,
        use_cache=use_cache,
    )


def get_nz_river_name_lines(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LINZ NZ River Name Lines layer for an extent.

    This is the named watercourse centreline layer at
    https://data.linz.govt.nz/layer/103632-nz-river-name-lines-pilot/. Unlike the
    topo50 river centrelines it carries a ``name`` and a ``feat_type`` per
    feature, which is what allows the major named rivers to be separated from the
    streams and creeks.

    The layer covers the whole country, so passing a bounding box is strongly
    preferred; the first call for a given extent downloads and clips the layer,
    and later calls for the same extent are served from the cache.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every river name line in New Zealand.
        crs: The coordinate reference system to return the lines in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of watercourse centrelines.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_RIVER_NAME_LINES_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LINZ_DOMAIN,
        use_cache=use_cache,
    )


def get_nz_river_name_polygons(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LINZ NZ River Name Polygons (Pilot) layer for an extent.

    The areal extent of the wider rivers,
    https://data.linz.govt.nz/layer/103631-nz-river-name-polygons-pilot/,
    5,644 of them nationally. A narrow stream exists in the LINZ data only as a
    centreline, while a river wide enough to need a bridge has an area, so the
    culvert and bridge work tests an accessway against both this and
    :func:`get_nz_river_name_lines`. Testing against the lines alone would miss
    the crossings most likely to carry a bridge rather than a culvert.

    Published as a pilot, so its coverage over the study area should be
    confirmed before a crossing rate derived from it is quoted.

    Licence:
        Creative Commons Attribution 4.0 International (CC BY 4.0),
        https://data.linz.govt.nz/license/attribution-4-0-international/. That
        obliges us to credit LINZ in anything published that is derived from it,
        which here means the culvert and bridge population and any loss built on
        it.

    Source:
        Land Information New Zealand, data.linz.govt.nz. No DOI is published for
        the layer.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``.
        crs: The coordinate reference system to return the polygons in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of river extent polygons.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_RIVER_NAME_POLYGONS_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LINZ_DOMAIN,
        use_cache=use_cache,
    )


def get_gwrc_slope_failure(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load Greater Wellington's earthquake-induced slope failure zones.

    Source
    ------
    "Wellington Region Earthquake Induced Slope Failure", published by Greater
    Wellington Regional Council on the public Koordinates catalogue as layer
    4069:
    https://koordinates.com/layer/4069-wellington-region-earthquake-induced-slope-failure/

    The catalogue describes it as "Earthquake induced slope failure
    susceptibility zones for the Wellington Region. This dataset is compiled from
    the 'slope failure series' ArcInfo coverages. Refer to Publication
    WRC/PP-T-95/06 for accompanying notes." Those notes are Kingsbury (1995),
    which derived five susceptibility zones from slope angle and slope
    modification, and which excluded failures caused by liquefaction. The
    underlying mapping is therefore 1995 regional-scale work, published to
    Koordinates in 2012 — a qualitative zonation rather than a rate, and no
    substitute for site assessment.

    4,682 polygons covering the Wellington region in NZGD2000 / NZTM
    (EPSG:2193). Licensed Creative Commons Attribution-No Derivative Works 3.0,
    so reproducing it requires attribution to Greater Wellington, and publishing
    a modified version may require their permission.

    Reading it needs ``KOORDINATES_PUBLIC_API_KEY``; the T+T and LINZ keys do not
    work on this domain. The same data is also mirrored on a public ArcGIS
    FeatureServer that needs no key, which is a fallback if the Koordinates
    export stalls:
    https://services5.arcgis.com/n4qyP7iVOnJlCVth/arcgis/rest/services/WR_SlopeFailure/FeatureServer/0

    Notes:
    -----
    Two quirks of the source are corrected here. ``SEVERITY`` is a string whose
    labels are inconsistent — ``1 Low``, ``2``, ``3 Moderate``, ``4``,
    ``5 High`` — so a ``severity_rank`` integer is added for sorting and
    colouring. A minority of the polygons are invalid, which breaks clipping and
    overlays, so geometries are repaired on the way through.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns the whole region.
        crs: The coordinate reference system to return the zones in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of susceptibility polygons carrying the original
        ``SEVERITY`` and ``LSKEY``, plus a ``severity_rank`` of 1 (low) to 5
        (high).

    Raises:
        ValueError: If a ``SEVERITY`` value is not one of the five known classes,
            which would mean the source has changed.
    """
    zones = get_koordinates_layer_extent(
        layer=constants.GWRC_SLOPE_FAILURE_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.KOORDINATES_PUBLIC_DOMAIN,
        use_cache=use_cache,
    )

    if zones.empty:
        return zones

    unknown = set(zones["SEVERITY"]) - set(constants.GWRC_SEVERITY_RANKS)
    if unknown:
        known = ", ".join(repr(value) for value in constants.GWRC_SEVERITY_RANKS)
        msg = (
            f"Unrecognised SEVERITY values in layer "
            f"{constants.GWRC_SLOPE_FAILURE_LAYER_ID}: "
            f"{', '.join(repr(value) for value in sorted(unknown))}. Known: {known}"
        )
        raise ValueError(msg)

    zones = zones.copy()
    zones["severity_rank"] = zones["SEVERITY"].map(constants.GWRC_SEVERITY_RANKS)

    # A minority of the source polygons are self-intersecting, which makes any
    # later clip or overlay fail. Repairing only the broken ones leaves the rest
    # bit-identical to the source.
    invalid = ~zones.geometry.is_valid
    if invalid.any():
        zones.loc[invalid, "geometry"] = zones.loc[invalid, "geometry"].apply(
            make_valid
        )

    return zones


def get_wcc_cut_areas(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load Wellington City Council's mapped earthworks cut areas.

    "WCC Earthmoving - Cut Areas" at
    https://ttgroup.koordinates.com/layer/125307-wcc-earthmoving-cut-areas/,
    mirrored onto the T+T instance for this study. 203 polygons covering 2.8
    km2, all of them in Wellington City and nothing in Porirua, Lower Hutt or
    Upper Hutt. Most sit in the northern suburbs (Johnsonville, Newlands,
    Churton Park) and Karori, with smaller clusters in the southern suburbs
    (Island Bay, Brooklyn) and on the Miramar peninsula (Seatoun Heights).

    The record is far from a complete inventory of earthworked ground. Only
    about 30% of the cut/fill line length GNS mapped independently from imagery
    falls within 10 m of a WCC cut or fill polygon; see
    ``src/scripts/landloss/hazard/landslide/research/
    wcc_earthworks_completeness.md``. Ground with no polygon has not been shown
    to be natural.

    This is an index of the earthworks records the council holds, not a terrain
    model. Every attribute is a pointer back to an archived plan --
    ``CW_file_number``, ``SR_Number``, ``Aussies_drawer_number``,
    ``Archives_Online_Link``, ``TroveID`` -- with ``Comments`` naming the streets
    and usually the years the work was consented. So the layer says *that this
    ground was cut* and where the drawings are, and says nothing about how deep
    the cut is, how high the face is or what angle it stands at. A model needing
    cut height or cut angle has to derive them from the DEM inside these
    polygons; the layer only says where to look.

    Licence:
        Creative Commons Attribution-NoDerivatives 4.0 International
        (CC BY-ND 4.0), as recorded on the layer's own metadata. Attribution to
        Wellington City Council is required, and **publishing a modified version
        is not permitted** -- which catches anything derived from it, including a
        susceptibility layer that uses it as an input. Confirm the position with
        the council before any derived layer, figure or table leaves the
        project; the sister fill layer records no licence at all, which suggests
        the tagging on the mirror may not reflect what the council intended.

    Source:
        Wellington City Council, mirrored to the T+T Koordinates instance in the
        "NHC WTGN Land Damage Model" group, September 2026. No DOI.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every mapped cut area.
        crs: The coordinate reference system to return the areas in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of cut area polygons carrying the council's archive
        references.
    """
    return get_koordinates_layer_extent(
        layer=constants.WCC_CUT_AREAS_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.TTGROUP_DOMAIN,
        use_cache=use_cache,
    )


def get_wcc_fill_areas(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load Wellington City Council's mapped earthworks fill areas.

    "WCC Earthmoving - Fill Areas" at
    https://ttgroup.koordinates.com/layer/125311-wcc-earthmoving-fill-areas/,
    the companion to :func:`get_wcc_cut_areas` and carrying the same attributes.
    250 polygons covering 3.5 km2, spread over the same Wellington City suburbs
    as the cut areas, with the same incompleteness and the same absence of
    coverage in Porirua and the Hutt. The
    council describes it as the earthworks fill locations in Wellington City,
    predominantly carried out for subdivision purposes.

    Fill is read separately from cut because the two fail differently under
    shaking. A cut face loses support from below; a sidling fill slides on the
    contact it was placed on, which is the failure Kingsbury (1995) scored at
    the top of the slope modification factor. Nothing in the layer says how deep
    the fill is or how steep the ground beneath it was, so a thickness has to
    come from the DEM or from the archived plans the attributes point at.

    Licence:
        **None is recorded on the layer.** Its companion cut layer is tagged
        CC BY-ND 4.0, so the safe assumption until the council confirms
        otherwise is that the same terms apply: attribute Wellington City
        Council, and publish nothing derived from it. Treat the missing tag as
        an open question rather than as permission.

    Source:
        Wellington City Council, mirrored to the T+T Koordinates instance in the
        "NHC WTGN Land Damage Model" group, September 2026. No DOI.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every mapped fill area.
        crs: The coordinate reference system to return the areas in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of fill area polygons carrying the council's archive
        references.
    """
    return get_koordinates_layer_extent(
        layer=constants.WCC_FILL_AREAS_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.TTGROUP_DOMAIN,
        use_cache=use_cache,
    )


def get_gns_slide_morphology(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load GNS Science's mapped linear geomorphic features of urban Wellington.

    "GNS SLIDE Morphological Data" at
    https://ttgroup.koordinates.com/layer/125308-gns-slide-morphological-data/,
    from the "Geomorphological characterisation of the Wellington urban area"
    study within the MBIE-funded SLIDE (Stability of Land In Dynamic
    Environments) programme. 55,734 polylines totalling about 4,800 km, mapped
    from imagery and elevation models over Wellington City only
    (1,742,450 - 1,755,353 E, 5,420,845 - 5,439,977 N in NZTM); nothing in
    Porirua, Lower Hutt or Upper Hutt.

    Each line carries a ``Type`` and, for some types, a ``Subtype``. Breaks in
    slope dominate: concave and convex, each split ``rounded`` or ``sharp``,
    make up about two thirds of the mapped length. The rest are retaining walls
    (11,288 short segments, about 280 km), obscured contacts, cut/fill lines,
    drainage lines, ridgelines, streams, cliffs and a handful of tension
    cracks. Although the layer description mentions recent landslide scarps, no
    ``Type`` names them; the landslide bodies themselves are in the companion
    "Genesis" polygon layer (125309), which this reader does not read.

    The retaining walls are "some" rather than all, in GNS's own words: only
    those visible from above were captured, so the layer cannot stand in for a
    wall inventory. ``SHAPE_Length`` is the source's own length in metres and is
    not recomputed after clipping.

    Licence:
        Creative Commons Attribution 4.0 International (CC BY 4.0), as recorded
        on the layer's own metadata. Anything derived from it and published --
        a figure, a table, a susceptibility layer -- must attribute GNS Science
        and the SLIDE programme. Modification and redistribution are permitted.

    Source:
        GNS Science, SLIDE programme (MBIE), mirrored to the T+T Koordinates
        instance in the "NHC WTGN Land Damage Model" group, September 2026. No
        DOI.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns every mapped feature.
        crs: The coordinate reference system to return the features in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of geomorphic feature lines with ``Type``, ``Subtype``
        and ``SHAPE_Length`` columns.
    """
    return get_koordinates_layer_extent(
        layer=constants.GNS_SLIDE_MORPHOLOGY_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.TTGROUP_DOMAIN,
        use_cache=use_cache,
    )


def get_nlm_geomorphology(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the National Liquefaction Model's geomorphology polygons for an extent.

    "NLM Geomorphology" at
    https://ttgroup.koordinates.com/layer/121398-nlm-geomorphology/, 133,845
    polygons nationally. Each carries a landform class in ``l2_geomorphology``,
    the dominant material in ``main_rock``, a geological ``epoch``, a
    ``geomorph_liq_susc`` liquefaction susceptibility and a ``confidence``.

    Over the four territorial authorities the landform classes are "Hills,
    ranges and mountains" (72% by area), "Alluvial plains and river flats"
    (18%), "Coastal lowlands" (5%), "Loess", "Fill", "Landslide" and
    "Colluvium". That is 1,045 polygons over 3,200 km2, so it is a regional
    model rather than an engineering geology map -- ample for telling bedrock
    hill country from unconsolidated deposits, and far too coarse to say
    anything about a particular slope.

    Licence:
        Tonkin + Taylor Group project data licensing statement,
        https://ttgroup.koordinates.com/license/tonkin--taylor-group--project-data-licensing-statement/.
        This is T+T's own data rather than open data, and the National
        Liquefaction Model is built by the same team as this study, so it is
        used here as project data: no attribution obligation and no permission
        step. Nothing outside T+T may be given the layer itself.

    Source:
        Tonkin + Taylor, National Liquefaction Model, on the T+T Koordinates
        instance. No DOI.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns the whole country.
        crs: The coordinate reference system to return the polygons in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of geomorphology polygons.
    """
    return get_koordinates_layer_extent(
        layer=constants.NLM_GEOMORPHOLOGY_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.TTGROUP_DOMAIN,
        use_cache=use_cache,
    )


def get_koordinates_raster(layer: int, domain: str = constants.TTGROUP_DOMAIN) -> Path:
    """Download a Koordinates raster layer and return the file it is in.

    The sibling of :func:`get_koordinates_layer_extent` for grids. A path rather
    than an array, because a grid is reprojected onto whatever grid the caller
    is working on and doing that from a file is what rioxarray expects; and
    because ttpy already caches the download, which is the expensive part.

    There is no bounding box. ttpy fetches the layer whole and caches it by
    version, so clipping belongs to the caller, after it has decided which grid
    the values are wanted on.

    Args:
        layer: The Koordinates ID of the layer to download.
        domain: The Koordinates domain to download from; the matching API key is
            chosen from it.

    Returns:
        The path to the downloaded raster.

    Raises:
        ValueError: If no API key is set for ``domain``.
    """
    conn = KoordinatesConnection(api_key=resolve_api_key(domain), domain=domain)
    try:
        return get_latest_layer(conn=conn, layer_id=layer)
    finally:
        conn.close()


def get_gwd_median_depth() -> Path:
    """Download the National Liquefaction Model's median groundwater depth grid.

    "GWD median depth" at
    https://ttgroup.koordinates.com/layer/120794-gwd-median-depth/: the median
    current depth to groundwater in metres below ground, on a 100 m grid in
    NZGD2000 / NZTM.

    **It covers flat land only.** The grid spans the country, 1,048,576 to
    2,097,176 E and 4,718,600 to 6,226,800 N, but carries a value over about 7%
    of its cells -- the flat land the model is built for. Hill country is NaN,
    and that absence is a statement about the model's scope rather than missing
    data, so a caller has to decide what to assume off the footprint rather than
    propagate the gap.

    Where it does carry a value the depths run 0 to 16 m, median 2.7 m, with 97%
    of cells at 4 m or shallower.

    Licence:
        Tonkin + Taylor Group project data licensing statement, as for
        :func:`get_nlm_geomorphology`. Project data from the same team as this
        study, so used freely here; the layer itself stays inside T+T.

    Source:
        Tonkin + Taylor, National Liquefaction Model, on the T+T Koordinates
        instance. No DOI.

    Returns:
        The path to the grid, as a GeoTIFF with NaN nodata.
    """
    return get_koordinates_raster(constants.GWD_MEDIAN_DEPTH_LAYER_ID)


def arcgis_cache_path(
    service_url: str,
    layer: int,
    crs: int | str,
    bbox: tuple[float, float, float, float] | None,
) -> Path:
    """Return the file one ArcGIS layer read is cached at."""
    key = f"{service_url}|{layer}|{crs}|{bbox}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return koopcache_dir("arcgis") / f"arcgis_{layer}_{digest}.gpkg"


def get_arcgis_feature_layer(
    service_url: str,
    layer: int,
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
    page_size: int = 1000,
) -> gpd.GeoDataFrame:
    """Read a layer from an ArcGIS REST map or feature service.

    The sibling of :func:`get_koordinates_layer_extent` for the services that
    are not on Koordinates at all. Councils publish a good deal this way and it
    needs no key, but it also has no bulk download: the service caps how many
    features one request may return, so this pages through with ``resultOffset``
    until a page comes back short.

    Asking the service to project is deliberate. ``outSR`` makes it return the
    coordinate system wanted, so the geometry is never reprojected twice, and a
    bounding box is sent in that same system rather than converted here.

    Args:
        service_url: The service, up to and including ``MapServer`` or
            ``FeatureServer``.
        layer: The sub-layer id within that service.
        bbox: The extent to fetch (minx, miny, maxx, maxy) in ``crs``. Omitting
            it fetches the whole layer. **Features are selected by intersection
            and returned whole**, not cut at the box, which is the opposite of
            :func:`get_koordinates_layer_extent`. Clip afterwards if the
            difference matters.
        crs: The coordinate reference system to return the features in. Must be
            one the service can project to, which in practice means an EPSG code.
        use_cache: Whether to read and write the on-disk cache for this extent.
        page_size: How many features to ask for per request.

    Returns:
        A GeoDataFrame of the layer's features, in ``crs``. Empty if the layer
        has nothing in the extent.

    Raises:
        ValueError: If the service reports an error, which it does with an
            ordinary HTTP 200 and so would otherwise pass unnoticed.
    """
    cache_path = arcgis_cache_path(service_url, layer, crs, bbox)
    if use_cache and cache_path.exists():
        return gpd.read_file(cache_path)

    query_url = f"{service_url.rstrip('/')}/{layer}/query"
    out_sr = str(crs).removeprefix("EPSG:")

    params: dict[str, str | int] = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        "outSR": out_sr,
        "returnGeometry": "true",
    }
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        params["geometry"] = f"{minx},{miny},{maxx},{maxy}"
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = out_sr
        params["spatialRel"] = "esriSpatialRelIntersects"

    pages = []
    offset = 0
    while True:
        page = _read_arcgis_page(query_url, params, offset=offset, page_size=page_size)
        if page.empty:
            break

        pages.append(page)

        # A short page is the last page. Services disagree about whether they
        # set exceededTransferLimit, so the length is what is trusted.
        if len(page) < page_size:
            break
        offset += len(page)

    if not pages:
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    features = gpd.GeoDataFrame(
        pd.concat(pages, ignore_index=True), geometry="geometry", crs=crs
    )

    if use_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        features.to_file(cache_path)

    return features


def _read_arcgis_page(
    query_url: str,
    params: dict[str, str | int],
    *,
    offset: int,
    page_size: int,
) -> gpd.GeoDataFrame:
    """Read one page of an ArcGIS query, as a GeoDataFrame."""
    response = requests.get(
        query_url,
        params={**params, "resultOffset": offset, "resultRecordCount": page_size},
        timeout=ARCGIS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    # An ArcGIS service answers an error with HTTP 200 and an "error" object, so
    # raise_for_status above does not see it.
    if "error" in payload:
        message = payload["error"].get("message", payload["error"])
        msg = f"{query_url} returned an error: {message}"
        raise ValueError(msg)

    if not payload.get("features"):
        return gpd.GeoDataFrame(geometry=[])

    return gpd.GeoDataFrame.from_features(payload["features"])


def get_slide_interpreted_materials(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load GNS's SLIDE near-surface materials mapping of urban Wellington.

    Sub-layer 3 of :data:`landloss.domain.constants.GNS_SLIDE_SERVICE_URL`:
    9,215 polygons over 111 km2, each carrying the substrate or regolith
    material in ``Type`` and how sure the mapper was in ``confidence``. Mapped
    at nominally 1:500 from aerial photographs, LiDAR and limited fieldwork
    (GNS Science report 2019/28).

    Fourteen material classes, of which "Rock at/near surface" is 41% of the
    mapped area, then mixed fill and rock, fill, colluvium, alluvium, loess,
    talus, boulders and water. That is the finest statement this study can get
    of what is at the ground surface, and the nearest thing to a weathering map
    that exists for Wellington: where rock is at or near the surface there is no
    weathered regolith mantle to fail.

    **It is not a weathering grade map.** Nothing published for Wellington
    grades the weathering of the greywacke spatially. The grade is recorded
    borehole by borehole in the New Zealand Geotechnical Database and nowhere
    aggregated into a surface.

    Coverage is the catch. The SLIDE study area is 114.6 km2 and reaches 38% of
    Wellington City and none of Porirua, Lower Hutt or Upper Hutt, so a model
    reading this needs something coarser to fall back on -- which for this study
    is :func:`get_nlm_geomorphology`.

    This is a different layer from the SLIDE polygons mirrored on the T+T
    instance. Those say what *process* formed the ground -- cut slope, fill
    body, landslide -- and this says what the ground is *made of*. They come
    from the same study and are meant to be read together.

    Licence:
        Copyright MBIE, which funded the SLIDE programme, served publicly by
        Wellington City Council with no licence statement on the service
        itself. Credit GNS Science and MBIE in anything published from it, and
        confirm the terms with GNS before a derived layer is delivered to NHC.

    Source:
        GNS Science, "SLIDE (Wellington): geomorphological characterisation of
        the Wellington urban area", GNS Science report 2019/28, served from
        Wellington City Council's ArcGIS instance. No DOI on the service.

    Args:
        bbox: The extent to fetch (minx, miny, maxx, maxy) in ``crs``. Polygons
            are selected by intersection and returned whole, so clip afterwards
            if the extent has to be exact. Omitting it fetches the whole mapped
            area, which is only 111 km2 and takes a few seconds.
        crs: The coordinate reference system to return the polygons in.
        use_cache: Whether to read and write the on-disk cache for this extent.

    Returns:
        A GeoDataFrame of material polygons carrying ``Type`` and
        ``confidence``. Read the confidence: over the whole layer it is 51%
        "low", 45% "medium" and 4% "high", so a single polygon is a mapper's
        best guess from imagery far more often than it is a verified
        observation.
    """
    return get_arcgis_feature_layer(
        constants.GNS_SLIDE_SERVICE_URL,
        constants.GNS_SLIDE_INTERPRETED_MATERIALS_SUBLAYER,
        bbox=bbox,
        crs=crs,
        use_cache=use_cache,
    )


def get_nz_land_cover(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the LCDB v6.0 land cover polygons for an extent.

    The New Zealand Land Cover Database, version 6.0 (mainland), at
    https://lris.scinfo.org.nz/layer/123148-lcdb-v60-land-cover-database-version-60-mainland-new-zealand/.
    Each polygon carries a land cover class and name at six time steps -- summer
    1996/97, 2001/02, 2007/08, 2012/13, 2018/19 and 2023/24 -- in the paired
    ``Class_<year>`` and ``Name_<year>`` columns, so change over time is read
    across the columns of one feature rather than by joining separate layers.
    ``Wetland_<yy>`` and ``Onshore_<yy>`` flag wetland and coastal change.

    Licence:
        Creative Commons Attribution 4.0 International (CC BY 4.0),
        https://creativecommons.org/licenses/by/4.0/. The data may be shared and
        adapted, including commercially, provided Landcare Research is credited
        as the source, a link to the licence is given, and any changes made are
        indicated. Anything derived from this layer and published -- a figure in
        the report, a table, a layer handed to NHC -- therefore needs that
        attribution carried with it.

    Source:
        Landcare Research, via the LRIS portal. Cite as
        https://doi.org/10.26060/WM99-RY32.

    The layer covers the whole mainland (542,789 polygons), so passing a
    bounding box is strongly preferred; the first call for a given extent
    downloads and clips the layer, and later calls for the same extent are
    served from the cache.

    Args:
        bbox: The extent to clip to (minx, miny, maxx, maxy) in ``crs``. Omitting
            it returns land cover for the whole mainland.
        crs: The coordinate reference system to return the polygons in.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of land cover polygons.

    Raises:
        ValueError: If LRIS_API_KEY is not set. LRIS is a separate Koordinates
            instance from LINZ and T+T's, with its own account and key.
    """
    return get_koordinates_layer_extent(
        layer=constants.NZ_LCDB_V60_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.LRIS_DOMAIN,
        use_cache=use_cache,
    )


def dem_cache_path(
    bbox: tuple[float, float, float, float], resolution: int, crs: int | str
) -> Path:
    """Return the file one fetched DEM extent is cached at.

    Args:
        bbox: The extent the DEM covers (minx, miny, maxx, maxy) in ``crs``.
        resolution: The cell size in metres.
        crs: The coordinate reference system the DEM is in.

    Returns:
        The path the DEM is cached at, inside the Koordinates cache directory so
        that everything downloaded for this study sits under one root.
    """
    key = f"{bbox}|{resolution}|{crs}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return koopcache_dir("dem") / f"dem_{resolution}m_{digest}.tif"


def get_dem(
    bbox: tuple[float, float, float, float],
    resolution: int = constants.DEM_RESOLUTION_M,
    crs: int | str = constants.DEFAULT_CRS,
    *,
    use_cache: bool = True,
) -> Path:
    """Fetch the LINZ elevation model for an extent and return the file it is in.

    LINZ does not publish a DEM as a Koordinates layer -- only hillshades -- so
    this is the one dataset in the study that does not come through
    :func:`get_koordinates_layer_extent`. Elevation is served from LINZ's STAC
    catalogue instead, which ``linz_stac_utils`` reads: LiDAR where it has been
    flown, falling back to the 8 m contour-derived model where it has not. That
    is the same route the National Liquefaction Model takes, so the two studies
    stand on the same elevation data.

    A path is returned rather than an array because the sampling helper this
    study uses, ``ttpy.gis.raster.utils.extract_point_values``, reads from a
    file, and because a fetched DEM is worth keeping: the pilot extent alone
    takes over a minute to assemble from the source tiles.

    Carries limitation L-12: the LiDAR is a merge of surveys flown in different
    years across the study area -- Wellington in 2023, Hutt City in 2025, Porirua
    unknown -- so a slope derived from it is not of uniform vintage, and a
    difference across a survey boundary may be an artefact rather than a
    landform.

    Args:
        bbox: The extent to fetch (minx, miny, maxx, maxy), in ``crs``.
        resolution: The cell size in metres. The default is the study's working
            resolution; see :data:`landloss.domain.constants.DEM_RESOLUTION_M`
            for why it is not the native 1 m.
        crs: The coordinate reference system to return the DEM in.
        use_cache: Whether to reuse an already-fetched DEM for the same extent,
            resolution and CRS. Pass False to re-fetch.

    Returns:
        The path to the DEM, as a GeoTIFF.
    """
    # Imported here rather than at module scope because assembling the STAC
    # client is slow and every other reader in this module is a vector reader
    # that never needs it.
    from linz_stac_utils.elevation import load_elevation  # noqa: PLC0415

    cache_path = dem_cache_path(bbox, resolution, crs)
    if use_cache and cache_path.exists():
        return cache_path

    # load_elevation takes its bounding box in WGS84, whatever CRS it is asked to
    # return, so the extent is converted rather than passed through.
    minx, miny, maxx, maxy = bbox
    wgs84_bounds = (
        gpd.GeoSeries([box(minx, miny, maxx, maxy)], crs=crs)
        .to_crs("EPSG:4326")
        .total_bounds
    )

    load_elevation(
        bbox=tuple(float(value) for value in wgs84_bounds),
        resolution=resolution,
        crs=crs,
        output_path=cache_path,
        overwrite=True,
    )
    return cache_path
