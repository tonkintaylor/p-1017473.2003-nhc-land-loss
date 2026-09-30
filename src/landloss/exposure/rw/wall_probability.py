"""The probability of a retaining wall on each insured property, and a draw from it.

A retaining wall inventory does not exist for the study area (**L-04**), so what
this module can say about a property is a probability, not a fact. The output is
therefore a table with one row per property carrying:

- ``p_wall``: the probability that the property carries a wall;
- the distribution of that wall's retained height -- a lognormal with a median
  and a log standard deviation -- and from it the probability of each size class
  given that a wall exists;
- ``p_poor``: the probability that a wall is in the poor initial condition.

:func:`draw_walls` then turns one such table into one realisation: a line per
wall, keyed to its claim. Keeping the two apart means the evidence is read and
the probabilities computed once, and any number of realisations are drawn from
them cheaply.

**The evidence is one-sided.** Three sources raise or cap the slope-driven
prevalence of :mod:`landloss.exposure.rw.beta_population`:

- Retaining walls mapped by GNS Science's SLIDE programme
  (:func:`landloss.io.readers.get_gns_slide_morphology`) are direct evidence of
  a wall. GNS mapped only the walls visible from above, in Wellington City
  only, so a property with no mapped wall is not evidence of none and the
  absence changes nothing.
- Cut slopes and fill bodies mapped by the SLIDE genesis layer
  (:func:`landloss.io.readers.get_slide_genesis`) mark ground that was shaped by
  people, which is where walls are built and which slope alone can miss once the
  cut has been made good.
- The National Liquefaction Model's landform class
  (:func:`landloss.io.readers.get_nlm_geomorphology`) caps the prevalence on
  plains and coastal lowlands, where a wall is a garden edge at most.

Every number that combines the evidence carries a ``beta`` name because it is
engineering judgement with no fit behind it; the real model is calibrated
against the SME suburb-by-suburb estimate (**T-19**) and replaces them.
"""

import math

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.exposure.coverage import RW_COVERAGE_BUFFER_M
from landloss.exposure.rw.beta_population import (
    AREA_COLUMN,
    BETA_LENGTH_SHARE,
    BETA_POOR_SHARE,
    COLUMNS,
    ID_COLUMN,
    INITIAL_CONDITIONS,
    MEDIUM_MAX_HEIGHT_M,
    SIZE_CLASSES,
    SMALL_MAX_HEIGHT_M,
    beta_wall_height_m,
    beta_wall_prevalence,
    classify_wall_size,
    wall_lines,
)

# The GNS SLIDE morphology ``Type`` that is a retaining wall.
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"

# The SLIDE genesis ``Type`` values that are ground shaped by earthworks.
ENGINEERED_GROUND_TYPES = ("Cut slope", "Fill body")

# The NLM ``l2_geomorphology`` classes that are flat depositional ground.
PLAIN_LANDFORMS = ("Alluvial plains and river flats", "Coastal lowlands")

# A mapped wall shorter than this inside the buffered property is a sliver where
# a line grazes the boundary, not a wall on the section.
MIN_MAPPED_WALL_LENGTH_M = 2.0

# The probability of a wall on a property with one mapped on or beside it. Not
# 1, because the mapping is from imagery and a line beside the boundary can be
# the neighbour's wall or a road batter.
BETA_MAPPED_WALL_PROBABILITY = 0.9

# The prevalence that a property wholly on a cut slope or fill body reaches, in
# proportion to the share of it that is. Below the slope-driven prevalence on
# steep ground it changes nothing.
BETA_ENGINEERED_PREVALENCE = 0.4

# The most a property on a plain can carry when nothing has been mapped on it.
BETA_PLAIN_MAX_PREVALENCE = 0.1

# The scatter of retained height about its slope-driven median, as a log
# standard deviation. A factor of about 1.5 either way at one sigma.
BETA_HEIGHT_LOG_SD = 0.4

# The tails of the lognormal are cut here, so a draw cannot produce a 9 m garden
# wall or a 10 cm one. Both bounds sit inside the end size classes, so the class
# probabilities are unaffected.
BETA_DRAWN_HEIGHT_BOUNDS_M = (0.2, 6.0)

EVIDENCE_COLUMNS = (
    "mapped_wall_length_m",
    "engineered_share",
    "landform",
    "on_plain",
)
PROBABILITY_COLUMNS = (
    "p_wall",
    "height_median_m",
    "height_log_sd",
    "p_small",
    "p_medium",
    "p_large",
    "p_poor",
    "length_m",
)


def mapped_wall_length_m(
    polygons: gpd.GeoSeries,
    morphology: gpd.GeoDataFrame,
    *,
    buffer_m: float = RW_COVERAGE_BUFFER_M,
) -> np.ndarray:
    """Return the length of GNS-mapped retaining wall on each property.

    The length is what lies inside the property buffered by ``buffer_m``, the
    same buffer the coverage rule applies to a wall, so a mapped wall counts
    where a wall of the property's would be kept.

    Args:
        polygons: One insured land polygon per property, in a projected CRS.
        morphology: The GNS SLIDE morphology lines, with a ``Type`` column, in
            the same CRS.
        buffer_m: How far outside the polygon a mapped wall still counts.

    Returns:
        Metres of mapped wall per property, aligned to ``polygons``. Zero where
        none is mapped, including everywhere outside the SLIDE study area.
    """
    lengths = np.zeros(len(polygons))
    walls = morphology[morphology["Type"] == MAPPED_WALL_TYPE]
    if walls.empty or polygons.empty:
        return lengths

    buffered = gpd.GeoDataFrame(
        {"position": np.arange(len(polygons))},
        geometry=polygons.buffer(buffer_m).to_numpy(),
        crs=polygons.crs,
    )
    pairs = gpd.sjoin(
        buffered, walls[["geometry"]], how="inner", predicate="intersects"
    )
    if pairs.empty:
        return lengths

    inside = walls.geometry.loc[pairs["index_right"]].intersection(
        pairs.geometry, align=False
    )
    summed = (
        pd.Series(inside.length.to_numpy()).groupby(pairs["position"].to_numpy()).sum()
    )
    lengths[summed.index.to_numpy()] = summed.to_numpy()
    return lengths


def engineered_share(polygons: gpd.GeoSeries, genesis: gpd.GeoDataFrame) -> np.ndarray:
    """Return the share of each property that lies on a cut slope or fill body.

    Args:
        polygons: One insured land polygon per property, in a projected CRS.
        genesis: The GNS SLIDE genesis polygons, with a ``Type`` column, in the
            same CRS.

    Returns:
        A share between 0 and 1 per property, aligned to ``polygons``. Zero
        outside the SLIDE study area. Overlapping genesis polygons are not
        merged, so the share is capped at 1.
    """
    shares = np.zeros(len(polygons))
    earthworks = genesis[genesis["Type"].isin(ENGINEERED_GROUND_TYPES)]
    if earthworks.empty or polygons.empty:
        return shares

    frame = gpd.GeoDataFrame(
        {"position": np.arange(len(polygons))},
        geometry=polygons.to_numpy(),
        crs=polygons.crs,
    )
    pairs = gpd.sjoin(
        frame, earthworks[["geometry"]], how="inner", predicate="intersects"
    )
    if pairs.empty:
        return shares

    covered = (
        earthworks.geometry.loc[pairs["index_right"]]
        .intersection(pairs.geometry, align=False)
        .area.to_numpy()
    )
    summed = pd.Series(covered).groupby(pairs["position"].to_numpy()).sum()
    areas = polygons.area.to_numpy()[summed.index.to_numpy()]
    shares[summed.index.to_numpy()] = np.clip(summed.to_numpy() / areas, 0.0, 1.0)
    return shares


def landform_at(points: gpd.GeoSeries, geomorphology: gpd.GeoDataFrame) -> np.ndarray:
    """Return the NLM landform class at each point.

    Args:
        points: One point per property, in a projected CRS.
        geomorphology: The NLM geomorphology polygons, with an
            ``l2_geomorphology`` column, in the same CRS.

    Returns:
        The landform class per point, aligned to ``points``, or an empty string
        where no polygon covers it.
    """
    frame = gpd.GeoDataFrame(
        {"position": np.arange(len(points))},
        geometry=points.to_numpy(),
        crs=points.crs,
    )
    joined = gpd.sjoin(
        frame,
        geomorphology[["l2_geomorphology", "geometry"]],
        how="left",
        predicate="within",
    )
    # A point on a shared edge lands in two polygons; either is as good as the
    # other at this resolution.
    first = joined.drop_duplicates("position").set_index("position")
    return (
        first["l2_geomorphology"].fillna("").reindex(np.arange(len(points))).to_numpy()
    )


def attach_evidence(
    properties: gpd.GeoDataFrame,
    *,
    morphology: gpd.GeoDataFrame,
    genesis: gpd.GeoDataFrame,
    geomorphology: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Return the properties with the three evidence columns attached.

    Args:
        properties: One row per property, with polygon geometry.
        morphology: The GNS SLIDE morphology lines.
        genesis: The GNS SLIDE genesis polygons.
        geomorphology: The NLM geomorphology polygons.

    Returns:
        A copy carrying :data:`EVIDENCE_COLUMNS`. The geometry is unchanged.
    """
    attached = properties.copy()
    polygons = properties.geometry
    attached["mapped_wall_length_m"] = mapped_wall_length_m(polygons, morphology)
    attached["engineered_share"] = engineered_share(polygons, genesis)
    landform = landform_at(polygons.representative_point(), geomorphology)
    attached["landform"] = landform
    attached["on_plain"] = np.isin(landform, PLAIN_LANDFORMS)
    return attached


def wall_probability(
    slope_deg: np.ndarray,
    *,
    mapped_length_m: np.ndarray,
    engineered: np.ndarray,
    on_plain: np.ndarray,
) -> np.ndarray:
    """Return the probability that each property carries a wall.

    Applied in this order: the slope-driven prevalence, lifted by the share of
    the property on earthworks; capped on a plain; then set to
    :data:`BETA_MAPPED_WALL_PROBABILITY` where a wall is mapped, because a wall
    seen from above outranks a prevalence guessed from the slope.

    Args:
        slope_deg: Ground slope at each property, in degrees. NaN where it could
            not be sampled, which gives NaN.
        mapped_length_m: Metres of GNS-mapped wall on each property.
        engineered: The share of each property on a cut slope or fill body.
        on_plain: Whether each property is on a plain landform.

    Returns:
        A probability per property.
    """
    slope_driven = beta_wall_prevalence(slope_deg)
    lifted = np.maximum(slope_driven, engineered * BETA_ENGINEERED_PREVALENCE)
    capped = np.where(on_plain, np.minimum(lifted, BETA_PLAIN_MAX_PREVALENCE), lifted)
    mapped = np.asarray(mapped_length_m) >= MIN_MAPPED_WALL_LENGTH_M
    probability = np.where(
        mapped, np.maximum(capped, BETA_MAPPED_WALL_PROBABILITY), capped
    )
    return np.where(
        np.isfinite(np.asarray(slope_deg, dtype=float)), probability, np.nan
    )


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    """Return the standard normal cumulative probability of each value."""
    return 0.5 * (
        1.0
        + np.array([math.erf(v / math.sqrt(2.0)) for v in z.ravel()]).reshape(z.shape)
    )


def size_class_probabilities(
    median_m: np.ndarray, log_sd: float = BETA_HEIGHT_LOG_SD
) -> np.ndarray:
    """Return the probability of each size class, given that a wall exists.

    Args:
        median_m: The median retained height of each wall, in metres.
        log_sd: The log standard deviation of the height.

    Returns:
        An array of shape ``(len(median_m), 3)`` in the order of
        :data:`~landloss.exposure.rw.beta_population.SIZE_CLASSES`, each row
        summing to 1.
    """
    log_median = np.log(np.asarray(median_m, dtype=float))
    below_small = _normal_cdf((np.log(SMALL_MAX_HEIGHT_M) - log_median) / log_sd)
    below_medium = _normal_cdf((np.log(MEDIUM_MAX_HEIGHT_M) - log_median) / log_sd)
    return np.column_stack(
        [below_small, below_medium - below_small, 1.0 - below_medium]
    )


def wall_probability_table(properties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the probabilistic retaining wall output, one row per property.

    Args:
        properties: One row per property with point geometry, carrying the
            claim id, ``area_m2``, ``slope_deg``, ``downhill_azimuth_deg`` and
            the :data:`EVIDENCE_COLUMNS`.

    Returns:
        A GeoDataFrame on the same rows and geometry, carrying the inputs and
        :data:`PROBABILITY_COLUMNS`.

    Raises:
        ValueError: If a required column is missing.
    """
    required = (
        ID_COLUMN,
        AREA_COLUMN,
        "slope_deg",
        "downhill_azimuth_deg",
        *EVIDENCE_COLUMNS,
    )
    missing = [column for column in required if column not in properties.columns]
    if missing:
        msg = f"properties is missing {missing}"
        raise ValueError(msg)

    table = properties.copy()
    slope = table["slope_deg"].to_numpy(dtype=float)
    table["p_wall"] = wall_probability(
        slope,
        mapped_length_m=table["mapped_wall_length_m"].to_numpy(dtype=float),
        engineered=table["engineered_share"].to_numpy(dtype=float),
        on_plain=table["on_plain"].to_numpy(dtype=bool),
    )
    median = beta_wall_height_m(slope)
    table["height_median_m"] = median
    table["height_log_sd"] = BETA_HEIGHT_LOG_SD
    classes = size_class_probabilities(median)
    for name, share in zip(SIZE_CLASSES, classes.T, strict=True):
        table[f"p_{name}"] = share
    table["p_poor"] = BETA_POOR_SHARE
    table["length_m"] = np.sqrt(table[AREA_COLUMN].to_numpy(dtype=float)) * (
        BETA_LENGTH_SHARE
    )
    return table


def draw_walls(
    probabilities: gpd.GeoDataFrame, rng: np.random.Generator
) -> gpd.GeoDataFrame:
    """Draw one realisation of the retaining wall population.

    A wall exists on a property with probability ``p_wall``. Its retained
    height is drawn from the lognormal in ``height_median_m`` and
    ``height_log_sd``, its size class follows from the height, and it is poor
    with probability ``p_poor``. It is drawn as a line along the contour.

    Args:
        probabilities: The output of :func:`wall_probability_table`.
        rng: The random generator, so a realisation reproduces exactly.

    Returns:
        A GeoDataFrame of one line per wall carrying
        :data:`~landloss.exposure.rw.beta_population.COLUMNS`. A property that
        drew no wall has no row; a property whose probability is NaN, because no
        slope was sampled, draws none either.

    Raises:
        ValueError: If a probability column is missing.
    """
    required = (ID_COLUMN, "downhill_azimuth_deg", *PROBABILITY_COLUMNS)
    missing = [column for column in required if column not in probabilities.columns]
    if missing:
        msg = f"probabilities is missing {missing}"
        raise ValueError(msg)

    p_wall = probabilities["p_wall"].to_numpy(dtype=float)
    azimuth = probabilities["downhill_azimuth_deg"].to_numpy(dtype=float)
    # NaN compares False, so an unplaceable property draws nothing.
    has_wall = np.isfinite(azimuth) & (rng.random(len(probabilities)) < p_wall)
    walls = probabilities.loc[has_wall]
    if walls.empty:
        return gpd.GeoDataFrame(
            {column: [] for column in COLUMNS},
            geometry=gpd.GeoSeries([], crs=probabilities.crs),
            crs=probabilities.crs,
        )

    height = np.clip(
        walls["height_median_m"].to_numpy(dtype=float)
        * np.exp(
            walls["height_log_sd"].to_numpy(dtype=float)
            * rng.standard_normal(len(walls))
        ),
        *BETA_DRAWN_HEIGHT_BOUNDS_M,
    )
    condition = np.where(
        rng.random(len(walls)) < walls["p_poor"].to_numpy(dtype=float),
        INITIAL_CONDITIONS[1],
        INITIAL_CONDITIONS[0],
    )
    length = walls["length_m"].to_numpy(dtype=float)

    return gpd.GeoDataFrame(
        {
            ID_COLUMN: walls[ID_COLUMN].to_numpy(),
            "size_class": classify_wall_size(height),
            "initial_condition": condition,
            "height_m": height,
            "length_m": length,
        },
        geometry=wall_lines(
            walls.geometry, walls["downhill_azimuth_deg"].to_numpy(dtype=float), length
        ).to_numpy(),
        crs=probabilities.crs,
    )
