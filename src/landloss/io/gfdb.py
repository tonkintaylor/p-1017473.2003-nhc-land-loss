r"""Readers for the USGS Ground Failure Database (GFDB), version 4.

A global, event-indexed compilation of earthquake-triggered landslide and
liquefaction inventories -- 1905 to 2021, 84 inventories from 375 candidate
earthquakes, 467,045 ground-failure polygons and 115,402 points. This is the
kind of inventory a global coseismic-landslide susceptibility model (e.g. the
USGS's Nowicki Jessee logistic regression) is fitted against; see the
``seismic-landslide-hazard-wellington`` skill for how that fits into this
study's own methodology. It is not a New Zealand dataset in its own right:
every NZ earthquake it carries (Darfield 2010, Christchurch 2011, Kaikoura
2016 among them) is recorded as an event only, with its ``landslide_status``/
``liquefaction_status`` set to "Inventory (not included)" -- no NZ ground
failures are actually mapped in :func:`get_gfdb_ground_failure_polygons` or
:func:`get_gfdb_ground_failure_points`. Its use here is as global calibration
and comparison data, the same role GNS's Kaikoura V3 inventory
(:mod:`landloss.io.kaikoura`) plays for New Zealand itself.

Held on the cross-project data library rather than under this project's own
``BASE_DIR`` or ``SOURCE_MATERIAL_DIR``, because it is a static published
dataset with utility well beyond this study -- see
``R:\DataLibrary\README.md`` for the catalogue's own indexing rules. A whole-
layer read goes straight off ``R:``, or off a copy of the delivery placed by hand
under ``.tdrivecache`` when there is one (:func:`gfdb_gdb_path`), rather than
through ``tdrive_sync.get_cached``: the dataset is a multi-file Esri file
geodatabase rather than a single file (or a shapefile's fixed set of sidecars),
which is the shape ``tdrive_sync``'s local cache mirroring is built around.

Filtering :func:`get_gfdb_ground_failure_polygons` or
:func:`get_gfdb_ground_failure_points` down to one ``event_name`` is a
different shape of problem: a small, derived extract rather than a mirror of
a source file. That goes through this project's own on-disk query cache
(:func:`landloss.io.koopcache_dir`) instead -- the same mechanism
:mod:`landloss.io.readers` uses for its own ArcGIS and DEM downloads -- so the
first read for an event comes off ``R:`` and every later one for that same
event comes off local disk. See each function's docstring for the
``event_name`` values it actually has rows under.

Read from the catalogue entry's ``v1/`` folder directly rather than through a
``Master/`` pointer -- see :data:`GFDB_V4_DIR`'s own comment for why.

Source:
    Schmitt, R.G., Tanyas, H., Nowicki Jessee, M.A., Zhu, J., Biegel, K.M.,
    Allstadt, K.E., Jibson, R.W., Thompson, E.M., van Westen, C.J., Sato, H.P.,
    Wald, D.J., Godt, J.W., Gorum, T., and Xu, C., 2022, An Open Repository of
    Earthquake-triggered Ground-Failure Inventories (ver 4.0, February 2022):
    U.S. Geological Survey data release, https://doi.org/10.5066/F7H70DB4.

    Methodology: Schmitt, R.G., Tanyas, H., Nowicki Jessee, M.A., Zhu, J.,
    Biegel, K.M., Allstadt, K.E., Jibson, R.W., Thompson, E.M., van Westen,
    C.J., Sato, H.P., Wald, D.J., Godt, J.W., Gorum, T., Xu, C., Rathje, E.M.,
    and Knudsen, K.L., 2017, An open repository of earthquake-triggered
    ground-failure inventories: U.S. Geological Survey Data Series 1064,
    https://doi.org/10.3133/ds1064.

Licence:
    Public domain -- a U.S. Government work, with the metadata's own access
    and use constraints both stated as "None" beyond reading the metadata for
    appropriate use and limitations. No attribution is legally required, but
    the citations above should still travel with anything derived from this
    data, both as good academic practice and because the component
    inventories were contributed by named original authors (credited per
    inventory in ``inventory_name``) whom USGS did not itself review for
    accuracy -- see ``distliab`` in the delivery's own FGDC metadata
    (``Metadata/*_FGDC.xml`` beside the geodatabase).

Two gotchas worth knowing before using the attributes:

- ``volume`` is entirely null in this version -- the metadata says no
  contributing inventory has yet supplied volume data.
- Use ``area`` for a polygon's area, not ``shape_area``. The geodatabase's
  native CRS is EPSG:3857 (Web Mercator), so ``shape_area``/``shape_length``
  -- Esri's own fields, in the layer's native CRS units -- carry Web
  Mercator's latitude-dependent area distortion. ``area`` is the producer's
  own field, calculated in square metres on the geodesic WGS84 ellipsoid, and
  is what the FGDC metadata documents as the trustworthy figure.
"""

import re
from pathlib import Path

import geopandas as gpd

import tdrive_sync
from landloss.io import koopcache_dir

# v1 is also the catalogue entry's current recommended version. The README
# documents a Master/ pointer to whichever version is current, but directory
# junctions/symlinks are not supported on this R: share, and none of the
# catalogue's other entries have one either -- see release_notes.txt beside
# this dataset for the detail. Point at a later v<n>/data folder instead if a
# study genuinely needs to stay on this version once a newer one is added.
GFDB_V4_DIR = Path(
    r"R:\DataLibrary\130.10_ground_failure_inventory_INT_Schmitt2022\v1\data"
)

GFDB_V4_GDB_PATH = GFDB_V4_DIR / "Ground_Failure_Database_v4.gdb"


def gfdb_gdb_path() -> Path:
    """Return the geodatabase to read: the local cache mirror if present.

    ``tdrive_sync.get_cached`` copies single files, so it cannot mirror a
    geodatabase folder. The mirror is instead put in place by hand, copied from
    ``R:`` into the same relative place under ``.tdrivecache`` (the path of
    :data:`GFDB_V4_GDB_PATH` without its drive), and used from there when it
    exists.

    Returns:
        The mirror of :data:`GFDB_V4_GDB_PATH` under ``.tdrivecache`` if it is
        there, otherwise :data:`GFDB_V4_GDB_PATH` itself.
    """
    local = tdrive_sync.get_cached_local_path(GFDB_V4_GDB_PATH)
    return local if local.exists() else GFDB_V4_GDB_PATH


def _event_cache_path(layer: str, event_name: str) -> Path:
    """Return the on-disk cache file for one event's rows of one layer.

    Named from the layer and the event name alone, not hashed: unlike
    :func:`landloss.io.readers.arcgis_cache_path`'s arbitrary query strings,
    an ``event_name`` is already a short, stable key, so a readable slug of
    it is more useful sitting in the cache directory than a hex digest would
    be.

    Args:
        layer: The layer name inside :data:`GFDB_V4_GDB_PATH`.
        event_name: The exact ``event_name`` being cached.

    Returns:
        The path the event's extract is (or would be) cached at, under
        :func:`landloss.io.koopcache_dir`.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", event_name.lower()).strip("_")
    return koopcache_dir("gfdb") / f"{layer.lower()}_{slug}.gpkg"


def _read_layer(
    layer: str,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    where: str | None = None,
    event_name: str | None = None,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Read one layer of the geodatabase, lower-casing its column names.

    Every field in this geodatabase is already word-separated with
    underscores -- ``Event_Name``, ``SHAPE_Length`` -- so lower-casing alone
    gives snake_case throughout, without a per-layer rename table.

    Args:
        layer: The layer name inside :data:`GFDB_V4_GDB_PATH`.
        bbox: An optional (minx, miny, maxx, maxy) filter, in the layer's own
            CRS (EPSG:3857). Pushed down to the read when reading the whole
            layer; applied in memory, after the cache lookup, when
            ``event_name`` is given -- one event's rows are already few
            enough that filtering them in pandas costs nothing.
        where: An optional SQL WHERE clause, e.g. ``"type = 'Landslide'"``,
            pushed down the same way as ``bbox``. Mutually exclusive with
            ``event_name``.
        event_name: An exact ``event_name`` to read -- and cache locally, see
            :func:`_event_cache_path` -- instead of the whole layer. Mutually
            exclusive with ``where``.
        use_cache: Whether to read/write the on-disk cache when
            ``event_name`` is given. Ignored otherwise.

    Returns:
        The layer (or, with ``event_name``, just that event's rows of it),
        columns renamed to lower case.

    Raises:
        ValueError: If both ``where`` and ``event_name`` are given.
    """
    if event_name is None:
        gdf = gpd.read_file(gfdb_gdb_path(), layer=layer, bbox=bbox, where=where)
        return gdf.rename(columns=str.lower)

    if where is not None:
        msg = "Pass only one of `where` and `event_name`, not both."
        raise ValueError(msg)

    cache_path = _event_cache_path(layer, event_name)
    if use_cache and cache_path.exists():
        gdf = gpd.read_file(cache_path)
    else:
        # Doubling a literal single quote is FileGDB's own SQL escaping; none
        # of this database's event names carry one today, but the escape
        # costs nothing and means a future one would not silently break the
        # query.
        escaped_event_name = event_name.replace("'", "''")
        # LIKE, not =: an exact match on event_name goes through the
        # geodatabase's attribute index, which GDAL 3.12 fails on with a
        # FeatureError in filegdbindex.cpp. LIKE with no wildcard matches the
        # same rows, and the exact comparison below drops any a stray ``_``
        # in a name would let through.
        gdf = gpd.read_file(
            gfdb_gdb_path(),
            layer=layer,
            where=f"event_name LIKE '{escaped_event_name}'",
        ).rename(columns=str.lower)
        gdf = gdf[gdf["event_name"] == event_name]
        if use_cache:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            gdf.to_file(cache_path)

    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        gdf = gdf.cx[minx:maxx, miny:maxy]
    return gdf


def get_gfdb_ground_failure_polygons(
    *,
    bbox: tuple[float, float, float, float] | None = None,
    where: str | None = None,
    event_name: str | None = None,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Read the GFDB's mapped ground-failure polygons.

    467,045 polygons across every included inventory. Reading the whole layer
    over ``R:`` is slow; pass ``bbox`` and/or ``where`` to push a filter down
    to the read instead of reading everything and filtering after, or pass
    ``event_name`` to read just one event's polygons and cache them locally
    (see ``use_cache``) so a second call for the same event never touches
    ``R:`` again.

    This layer's 34 available ``event_name`` values, earliest first (an event
    with no polygon here may still have rows in
    :func:`get_gfdb_ground_failure_points` instead, or in addition):

    - 1976: "M 7.5 - 7 km N of Los Amates, Guatemala"
    - 1976: "M 6.5 - Austria-Italy-Slovenia border region"
    - 1980: "M 6.1 - 8 km W of Aspen Springs, California"
    - 1983: "M 6.7 - 11 km NNE of Coalinga, California"
    - 1989: "M 6.9 - Loma Prieta, California"
    - 1991: "M 7.6 - 34 km S of Limón, Costa Rica"
    - 1994: "M 6.7 - 1km NNW of Reseda, CA"
    - 1995: "M 6.9 - 8 km S of Akashi, Japan"
    - 1998: "M 5.7 - 31 km ESE of Pizitou, Taiwan"
    - 1999: "M 7.7 - 21 km S of Puli, Taiwan"
    - 2002: "M 7.9 - 75 km E of Cantwell, Alaska"
    - 2003: "M 6.3 - 8 km S of Kanaláki, Greece"
    - 2003: "M 6.5 - 10 km NE of San Simeon, California"
    - 2004: "M 6.6 - 8 km SSW of Ojiya, Japan"
    - 2005: "M 7.6 - 21 km NNE of Muzaffar?b?d, Pakistan" (the "?"s are
      literal in the source data, not a rendering issue here)
    - 2006: "M 6.7 - 14 km SW of Puako, Hawaii"
    - 2007: "M 6.2 - 18 km N of Puerto Aysén, Chile"
    - 2008: "M 7.9 - 58 km W of Tianpeng, China"
    - 2008: "M 6.9 - 24 km WSW of Mizusawa, Japan"
    - 2009: "M 6.1 - 10 km NNE of Sabanilla, Costa Rica"
    - 2010: "M 7.0 - 10 km SE of Léogâne, Haiti"
    - 2011: "M 9.1 - near the east coast of Honshu, Japan"
    - 2011: "M 9.1 - 2011 Great Tohoku Earthquake, Japan"
    - 2013: "M 5.9 - 13km E of Chabu, China"
    - 2014: "M 6.2 - 11km W of Wenping, China"
    - 2015: "M 7.8 - 67 km NNE of Bharatpur, Nepal"
    - 2016: "M 5.3 - 9 km NE of Cot, Costa Rica"
    - 2017: "M 6.4 - 64km ENE of Nyingchi, China"
    - 2018: "M 7.5 - 32 km SW of Tari, Papua New Guinea"
    - 2018: "M 6.9 - 0km SW of Loloan, Indonesia"
    - 2018: "M 6.9 - 1km S of Belanting, Indonesia"
    - 2018: "M 7.5 - 72 km N of Palu, Indonesia"
    - 2019: "M 5.7 - 9 km NW of Mesetas, Colombia"
    - 2020: "M 6.4 - 13 km SSE of Maria Antonia, Puerto Rico"

    Args:
        bbox: An optional (minx, miny, maxx, maxy) filter in EPSG:3857.
        where: An optional SQL WHERE clause, e.g. ``"type = 'Liquefaction'"``.
            Mutually exclusive with ``event_name``.
        event_name: An exact match from the list above. The first read for it
            comes off ``R:``; every later one comes off a small local cache
            file instead -- see the module docstring. Mutually exclusive with
            ``where``.
        use_cache: Whether to read/write that local cache when ``event_name``
            is given. Ignored otherwise.

    Returns:
        A GeoDataFrame in EPSG:3857, carrying ``area`` (m2, geodesic WGS84 --
        see the module docstring on why this is preferred over
        ``shape_area``), ``event_name``, ``event_date``, ``epicentral_country``,
        ``type`` ("Landslide" or "Liquefaction"), ``description``, ``volume``
        (currently always null), ``event_link``, ``source_link``,
        ``inventory_name``, ``comments``, ``shape_length`` and ``shape_area``.

    Raises:
        ValueError: If both ``where`` and ``event_name`` are given.
    """
    return _read_layer(
        "Ground_Failure_Polygons",
        bbox=bbox,
        where=where,
        event_name=event_name,
        use_cache=use_cache,
    )


def get_gfdb_ground_failure_points(
    *,
    bbox: tuple[float, float, float, float] | None = None,
    where: str | None = None,
    event_name: str | None = None,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Read the GFDB's mapped ground-failure points.

    115,402 points -- ground failures recorded as a location rather than a
    mapped footprint. Reading the whole layer over ``R:`` is slow; pass
    ``bbox`` and/or ``where`` to push a filter down to the read instead of
    reading everything and filtering after, or pass ``event_name`` to read
    just one event's points and cache them locally (see ``use_cache``) so a
    second call for the same event never touches ``R:`` again.

    This layer's 35 available ``event_name`` values, earliest first (an event
    with no point here may still have rows in
    :func:`get_gfdb_ground_failure_polygons` instead, or in addition):

    - 1908: "M 7.1 - 7 km SE of Alì Terme, Italy"
    - 1915: "M 6.7 - 4 km WNW of San Benedetto dei Marsi, Italy"
    - 1949: "M 6.7 - 4 km WNW of Roy, Washington"
    - 1965: "M 6.7 - 3 km ESE of Browns Point, Washington"
    - 1971: "M 6.6 - 10km SSW of Agua Dulce, CA"
    - 1976: "M 6.5 - 3 km SW of Prato, Italy"
    - 1980: "M 5.8 - 8 km ENE of Blackhawk, California"
    - 1980: "M 6.9 - 2 km N of Cairano, Italy"
    - 1986: "M 5.7 - 5 km N of Tonacatepeque, El Salvador"
    - 1989: "M 6.9 - Loma Prieta, California Earthquake"
    - 1994: "M 6.7 - 1km NNW of Reseda, CA"
    - 1997: "M 6.0 - 3 km SSE of Nocera Umbra, Italy"
    - 1998: "M 5.6 - 2 km NNE of Castelluccio Superiore, Italy"
    - 1999: "M 7.7 - 21 km S of Puli, Taiwan"
    - 2001: "M 7.7 - 28 km SSW of Puerto El Triunfo, El Salvador"
    - 2001: "M 6.6 - 5 km S of Cojutepeque, El Salvador"
    - 2001: "M 6.8 - 7 km SSE of Longbranch, Washington"
    - 2003: "M 6.5 - 10 km NE of San Simeon, California"
    - 2007: "M 8.0 - 41 km SW of San Vicente de Cañete, Peru"
    - 2008: "M 7.9 - eastern Sichuan, China (Wenchuan)"
    - 2008: "M 7.9 - 58 km W of Tianpeng, China"
    - 2009: "M 6.3 - 3 km SE of Sassa, Italy"
    - 2011: "M 9.1 - near the east coast of Honshu, Japan"
    - 2011: "M 5.1 - 4 km NE of Lorca, Spain"
    - 2013: "M 6.6 - 56 km WSW of Linqiong, China"
    - 2015: "M 7.8 - 36km E of Khudi, Nepal"
    - 2015: "M 7.8 - 67 km NNE of Bharatpur, Nepal"
    - 2016: "M 6.2 - 5 km WNW of Accumoli, Italy"
    - 2016: "M 6.1 - 2 km NNW of Visso, Italy"
    - 2016: "M 6.6 - 5 km ESE of Preci, Italy"
    - 2017: "M 7.1 - 1 km S of Matzaco, Mexico"
    - 2018: "M 7.5 - 72 km N of Palu, Indonesia"
    - 2020: "M 6.4 - 13km S of Indios, Puerto Rico"
    - 2020: "M 6.4 - 13 km SSE of Maria Antonia, Puerto Rico"
    - 2021: "M 7.2 - Nippes, Haiti"

    Args:
        bbox: An optional (minx, miny, maxx, maxy) filter in EPSG:3857.
        where: An optional SQL WHERE clause, e.g. ``"type = 'Landslide'"``.
            Mutually exclusive with ``event_name``.
        event_name: An exact match from the list above. The first read for it
            comes off ``R:``; every later one comes off a small local cache
            file instead -- see the module docstring. Mutually exclusive with
            ``where``.
        use_cache: Whether to read/write that local cache when ``event_name``
            is given. Ignored otherwise.

    Returns:
        A GeoDataFrame in EPSG:3857, carrying ``inventory_name``, ``area``
        (usually null -- a point rarely carries an area), ``event_name``,
        ``event_date``, ``epicentral_country``, ``type`` ("Landslide" or
        "Liquefaction"), ``description``, ``volume`` (currently always null),
        ``event_link``, ``source_link`` and ``comments``.

    Raises:
        ValueError: If both ``where`` and ``event_name`` are given.
    """
    return _read_layer(
        "Ground_Failure_Points",
        bbox=bbox,
        where=where,
        event_name=event_name,
        use_cache=use_cache,
    )


def get_gfdb_seismic_events(*, where: str | None = None) -> gpd.GeoDataFrame:
    """Read the GFDB's 375 candidate earthquake events.

    One row per earthquake considered for inclusion, whether or not a ground-
    failure inventory for it made it into the database --
    ``landslide_status``/``liquefaction_status`` says which; both read
    "Inventory (not included)" for every New Zealand event currently in the
    database (see the module docstring).

    Args:
        where: An optional SQL WHERE clause, e.g.
            ``"usgs_name LIKE '%New Zealand%'"``. ``country`` is blank for
            most rows in this version -- an event's place is only reliably
            findable through ``usgs_name``/``alternate_description``.

    Returns:
        A GeoDataFrame of point locations (Point Z; the Z is depth, also
        carried separately as ``depth_km``) in EPSG:3857, carrying
        ``event_time``, ``usgs_name``, ``alternate_description``,
        ``magnitude``, ``latitude``, ``longitude``, ``depth_km``,
        ``landslide_status``, ``liquefaction_status``, ``included_sources``,
        ``usgs_earthquake_event_page``, ``sciencebase_link`` and ``country``.
    """
    return _read_layer("seismic_event_locations", where=where)


def get_gfdb_inventory_centroids(*, where: str | None = None) -> gpd.GeoDataFrame:
    """Read the GFDB's per-inventory centroid index.

    One row per one of the 84 included inventories -- a lightweight index to
    browse what the database holds without reading the full point/polygon
    layers, each row giving a single representative location for one
    inventory rather than its mapped extent.

    Args:
        where: An optional SQL WHERE clause, e.g.
            ``"geo_type = 'Polygon'"``.

    Returns:
        A GeoDataFrame in EPSG:3857, carrying ``event_name``, ``event_date``,
        ``usgs_event_link``, ``inventory_name``, ``sb_link``,
        ``inventory_location``, ``gf_type`` ("Landslide" or "Liquefaction"),
        ``geo_type`` (the geometry type the inventory was mapped as, e.g.
        "Polygon" or "Point"), ``centroid_x`` and ``centroid_y``.
    """
    return _read_layer("event_inventory_centroids", where=where)
