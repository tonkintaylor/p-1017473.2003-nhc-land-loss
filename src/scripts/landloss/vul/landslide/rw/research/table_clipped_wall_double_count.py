"""Tabulate the claims charged twice for the ground a neighbour's landslide took.

    uv run --frozen python src/scripts/landloss/vul/landslide/rw/research/table_clipped_wall_double_count.py

The question is check 6.3 of ``.agents/plans/tweaks-to-property-damage.md``. A
retaining wall flagged ``is_evacuated`` or ``is_inundated`` (and not
``is_damaged_by_shaking``) is replaced over its whole length today. The slip
that clipped it is usually a failure that came with no wall of the claim's own,
so loss s1 gives it a new wall as well. One claim may then pay twice for the
same ground. This script counts those claims, prices both walls the way loss s1
prices them, and asks whether the clipped stretch and the slip's new wall stand
on the same line.

Nothing is read from T:. Each extent is settled in memory from the local
``temp/vul`` loss inputs, with loss s1's own functions (the QV land values the
full settlement needs are not used, because they touch only the cap and the
land rate). Where a settlement file is on disk, the in-memory wall and new wall
costs are checked against it.

**Where a new wall sits.** Loss gives a slip's new wall no geometry, only a
length (:func:`~landloss.loss.pricing.landslide_wall_length_m`). So the slip's
ground (its evacuated and inundated polygons, unioned) stands in for it, and two
tests are made of the clipped stretch (the part of the wall's line inside that
ground):

1. **Along the slip's edge:** the share of the stretch within
   :data:`EDGE_TOLERANCE_M` of the ground's boundary. A stretch that lies along
   the edge is "same structure"; one running through the ground's middle is
   not, because a wall holding a slip stands at its edge.
2. **Against a placed new wall:** a line of the new wall's length laid along the
   boundary, centred on the boundary point nearest the stretch. The distance
   from the stretch to it and the share of the stretch within the tolerance of
   it are written beside the verdict, but do not set it.

A pair whose slip does not clip the wall at all is "different structures" by
definition.

Output goes under ``temp/vul/research/clipped-wall-double-count/``: pairs and
claims per extent, and one summary. What it runs over is set by the constants
below.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString

from landloss.domain.loss_contract import (
    MAPPED_WALL,
    CLAIM_ID_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    RW_TYPE_COLUMN,
)
from landloss.exposure.rw.beta_population import classify_wall_size
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    LANDSLIDE_WALL_MARGIN_M,
    MIN_LANDSLIDE_WALL_LENGTH_M,
    beta_wall_face_area_m2,
    beta_wall_height_m,
    beta_wall_repair_cost_incl_gst_nzd,
    classify_landslide_wall_size,
    contingency_incl_gst_nzd,
    landslide_wall_length_m,
    margin_rule_length_m,
    on_costs_incl_gst_nzd,
    professional_fees_incl_gst_nzd,
    replacement_rate_excl_gst_nzd_per_m2,
    timber_pole_rate_excl_gst_nzd_per_m2,
    wall_face_area_m2,
)
from landloss.vul.landslide.flags import WALL_INSIDE_TOLERANCE_M
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    attach_failures_to_walls,
    landslide_failures,
    ratings_for,
    replacement_wall_shape,
    settlement_path,
    site_ratings_by_claim,
)
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SAME = "same structure"
DIFFERENT_CLIPPING = "different structures (slip clips the wall, not along its edge)"
DIFFERENT_APART = "different structures (slip does not touch the wall)"

# What the script runs over.
EXTENTS = ("lower-hutt", "upper-hutt", "porirua")
WORLD_ID = 0
REALISATION_ID = 0

# How close to the slip ground's boundary a stretch of wall must lie to be
# "along the slip's edge", in m. Kept at the 2 m the 6.4 check was first
# written with; loss's margin rule has since narrowed to 1 m at each end
# (LANDSLIDE_WALL_MARGIN_M), and the verdicts are not to move with it.
EDGE_TOLERANCE_M = 2.0
# The share of the clipped stretch that must lie within EDGE_TOLERANCE_M of the
# boundary for the pair to be the same structure.
SAME_STRUCTURE_SHARE = 0.5
# Spacing of the points a stretch is sampled at when measuring distances, in m.
SAMPLE_SPACING_M = 0.25
# The sample of pairs written beside each extent's table: how many of each
# verdict, drawn with this seed so a rerun gives the same ones.
SAMPLE_PER_VERDICT = {SAME: 5, DIFFERENT_CLIPPING: 2, DIFFERENT_APART: 2}
SAMPLE_SEED = 1
# A stretch shorter than this has no direction worth measuring, in m.
MIN_STRETCH_FOR_ANGLE_M = 2.0
# A stretch at more than this angle to the boundary beside it crosses the edge
# rather than running along it, in degrees. Counted in the summary, not used in
# the verdict.
SQUARE_ACROSS_DEG = 45.0

# The 2026-10-11 Porirua run, kept under temp/versions, which holds the wall of
# the worked example. It mirrors temp/'s layout, so the same reader serves it.
# The site ratings still come from the current exposure layers, which that
# run's claims share.
SNAPSHOT_EXTENT = "porirua"
SNAPSHOT_ROOT = TEMP_DIR / "versions" / "porirua" / "v3-20261011"
SNAPSHOT_LABEL = "porirua-v3-20261011"
EXAMPLE_WALL_ID = "4eef7bbf-bfe3-40c4-91eb-a29515837562-RW01"
EXAMPLE_SLIP_ID = "SP0003334"

# The tolerances the sensitivity columns repeat the edge test at, in m.
SENSITIVITY_TOLERANCES_M = (1.0, 5.0)

WORLD_STEM = f"w{WORLD_ID:03d}-r{REALISATION_ID:03d}"
OUT_DIR = TEMP_DIR / "vul" / "research" / "clipped-wall-double-count"

PARENT_RW_ID_COLUMN = "parent_rw_id"
SLOPE_ID_COLUMN = "slope_id"
LANDSLIDE_ID_COLUMN = "landslide_id"
RULE = "-" * 72



def _read(path: Path) -> gpd.GeoDataFrame:
    """Read a geoparquet or parquet table."""
    if path.name.endswith("geoparquet"):
        return gpd.read_parquet(path)
    return pd.read_parquet(path)


def settlement_inputs(extent: str, root: Path) -> dict[str, pd.DataFrame]:
    """Read the loss input tables, the realisation and the wall flags of an extent.

    Args:
        extent: A name from landloss.io.area_of_interest.EXTENTS.
        root: The folder holding ``vul`` and ``hazard/landslide``: ``temp``, or
            a saved run beneath ``temp/versions``.

    Returns:
        ``rw`` and ``land`` (the loss contract's tables), ``slides`` (the
        combined realisation) and ``flags`` (vul landslide rw s11's wall flags,
        which name each wall's own polygon).
    """
    suffix = extent_suffix(extent)
    vul_dir = root / "vul"
    hazard_dir = root / "hazard" / "landslide"
    rw = _read(vul_dir / f"loss-input-rw-{WORLD_STEM}{suffix}.geoparquet")
    if RW_HEIGHT_COLUMN not in rw.columns:
        # A saved run from before the contract carried a wall's type and height:
        # take both from that run's wall population, and treat each wall as its
        # own parent, as loss s1 does where no wall is split.
        population = _read(
            root / "exposure" / f"wall-population-{WORLD_STEM[:4]}{suffix}.geoparquet"
        )
        drawn = population.set_index(RW_ID_COLUMN)
        rw = rw.assign(
            **{
                RW_HEIGHT_COLUMN: rw[RW_ID_COLUMN].map(drawn["height_m"]).to_numpy(),
                RW_TYPE_COLUMN: rw[RW_ID_COLUMN].map(drawn["wall_type"]).to_numpy(),
                PARENT_RW_ID_COLUMN: rw[RW_ID_COLUMN].to_numpy(),
            }
        )
    return {
        "rw": rw,
        "land": _read(vul_dir / f"loss-input-land-{WORLD_STEM}{suffix}.geoparquet"),
        "slides": _read(
            hazard_dir / f"landslide-realisation-{WORLD_STEM}{suffix}.geoparquet"
        ),
        "flags": _read(vul_dir / f"wall-landslide-damage-{WORLD_STEM}{suffix}.parquet"),
    }


def slip_ground(slides: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return each landslide's damaged ground, evacuated and inundated unioned.

    Args:
        slides: The combined realisation, one row per landslide and land class.

    Returns:
        One row per landslide: ``landslide_id``, ``slope_id`` (missing for the
        large model's slips) and the unioned ground as geometry.
    """
    ground = slides[slides[LAND_CLASS_COLUMN].isin([EVACUATED, INUNDATED])]
    ground = ground[~ground.geometry.is_empty]
    own_slope = ground.groupby(LANDSLIDE_ID_COLUMN)[SLOPE_ID_COLUMN].first()
    merged = ground.groupby(LANDSLIDE_ID_COLUMN).geometry.agg(
        lambda part: shapely.union_all(part.to_numpy())
    )
    return gpd.GeoDataFrame(
        {
            LANDSLIDE_ID_COLUMN: merged.index.to_numpy(),
            SLOPE_ID_COLUMN: own_slope.reindex(merged.index)
            .astype(object)
            .to_numpy(),
        },
        geometry=merged.to_numpy(),
        crs=slides.crs,
    )


def clipped_pieces(rw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the wall pieces flagged by landslide ground alone, not by shaking.

    Args:
        rw: The loss contract's retaining wall table.

    Returns:
        The pieces with ``is_evacuated`` or ``is_inundated`` and no
        ``is_damaged_by_shaking``.
    """
    landslide = rw[IS_EVACUATED_COLUMN].to_numpy(bool) | rw[
        IS_INUNDATED_COLUMN
    ].to_numpy(bool)
    return rw[landslide & ~rw[IS_DAMAGED_BY_SHAKING_COLUMN].to_numpy(bool)]


def stretches_inside(
    pieces: gpd.GeoDataFrame, ground: gpd.GeoDataFrame, own_slope: pd.Series
) -> pd.DataFrame:
    """Return the stretch of each piece inside each other slip's ground.

    The test is flags.wall_flags': a stretch counts where more than
    :data:`WALL_INSIDE_TOLERANCE_M` of the line lies inside the ground shrunk by
    that distance, and a wall's own polygon never counts.

    Args:
        pieces: Wall pieces, keyed by ``rw_id`` and carrying ``parent_rw_id``.
        ground: :func:`slip_ground`.
        own_slope: Each whole wall's own polygon, by ``rw_id``.

    Returns:
        One row per piece and slip: ``rw_id``, ``landslide_id``, the stretch
        geometry and its length ``inside_m``.
    """
    shrunk = ground.geometry.buffer(-WALL_INSIDE_TOLERANCE_M)
    keep = ~shrunk.is_empty
    interiors = gpd.GeoDataFrame(
        {LANDSLIDE_ID_COLUMN: ground.loc[keep, LANDSLIDE_ID_COLUMN].to_numpy()},
        geometry=shrunk[keep].to_numpy(),
        crs=ground.crs,
    )
    lines = pieces[[RW_ID_COLUMN, PARENT_RW_ID_COLUMN, "geometry"]].reset_index(
        drop=True
    )
    joined = gpd.sjoin(lines, interiors, predicate="intersects", how="inner")
    if joined.empty:
        return pd.DataFrame(
            columns=[RW_ID_COLUMN, LANDSLIDE_ID_COLUMN, "stretch", "inside_m"]
        )
    stretch = shapely.intersection(
        lines.geometry.to_numpy()[joined.index.to_numpy()],
        interiors.geometry.to_numpy()[joined["index_right"].to_numpy()],
    )
    wall_own = joined[PARENT_RW_ID_COLUMN].map(own_slope).to_numpy()
    own = pd.notna(wall_own) & (joined[LANDSLIDE_ID_COLUMN].to_numpy() == wall_own)
    out = pd.DataFrame(
        {
            RW_ID_COLUMN: joined[RW_ID_COLUMN].to_numpy(),
            LANDSLIDE_ID_COLUMN: joined[LANDSLIDE_ID_COLUMN].to_numpy(),
            "stretch": stretch,
            "inside_m": shapely.length(stretch),
        }
    )
    return out[(out["inside_m"] > WALL_INSIDE_TOLERANCE_M) & ~own].reset_index(
        drop=True
    )


def _points_along(geometry: shapely.Geometry) -> np.ndarray:
    """Return points spaced along a line or multi-line, one per metre fraction."""
    parts = shapely.get_parts(geometry)
    points = []
    for part in parts:
        if part.geom_type != "LineString" or part.length == 0:
            continue
        count = max(int(np.ceil(part.length / SAMPLE_SPACING_M)), 1) + 1
        points.extend(
            shapely.line_interpolate_point(part, np.linspace(0, part.length, count))
        )
    return np.array(points, dtype=object)


def _outer_ring(ground: shapely.Geometry, near: shapely.Geometry) -> LineString:
    """Return the outer ring of the polygon of ``ground`` nearest ``near``."""
    polygons = [p for p in shapely.get_parts(ground) if p.geom_type == "Polygon"]
    nearest = min(polygons, key=lambda polygon: polygon.distance(near))
    return LineString(nearest.exterior.coords)


def _along_ring(ring: LineString, centre: float, length: float) -> LineString:
    """Return ``length`` m of a closed ring centred on a position along it."""
    if length >= ring.length:
        return ring
    positions = (
        np.linspace(centre - length / 2, centre + length / 2, max(int(length / 0.5), 2))
        % ring.length
    )
    return LineString(
        [(point.x, point.y) for point in shapely.line_interpolate_point(ring, positions)]
    )


def edge_geometry_test(
    stretch: shapely.Geometry, ground: shapely.Geometry, new_wall_length_m: float
) -> dict[str, float]:
    """Measure a clipped stretch against a slip's edge and a placed new wall.

    Args:
        stretch: The part of the wall's line inside the slip's ground.
        ground: The slip's ground.
        new_wall_length_m: The length loss would build the slip's new wall to.

    Returns:
        ``share_on_edge`` (share of the stretch within
        :data:`EDGE_TOLERANCE_M` of the ground's boundary),
        ``max_edge_distance_m`` and ``mean_edge_distance_m`` (from the stretch
        to the boundary), then ``placed_min_distance_m``,
        ``placed_max_distance_m`` and ``placed_overlap_share`` against a new
        wall of the given length laid on the boundary at the point nearest the
        stretch.
    """
    points = _points_along(stretch)
    boundary = shapely.boundary(ground)
    to_edge = shapely.distance(points, boundary)
    ring = _outer_ring(ground, stretch)
    centre = ring.project(shapely.centroid(stretch))
    placed = _along_ring(ring, centre, new_wall_length_m)
    to_placed = shapely.distance(points, placed)
    measures = {
        "share_on_edge": float(np.mean(to_edge <= EDGE_TOLERANCE_M)),
        "max_edge_distance_m": float(to_edge.max()),
        "mean_edge_distance_m": float(to_edge.mean()),
        "placed_min_distance_m": float(to_placed.min()),
        "placed_max_distance_m": float(to_placed.max()),
        "placed_overlap_share": float(np.mean(to_placed <= EDGE_TOLERANCE_M)),
        "angle_to_edge_deg": _angle_to_edge(stretch, ring, centre),
    }
    for tolerance in SENSITIVITY_TOLERANCES_M:
        measures[f"share_within_{tolerance:g}m"] = float(np.mean(to_edge <= tolerance))
    return measures


def _angle_to_edge(stretch: shapely.Geometry, ring: LineString, centre: float) -> float:
    """Return the angle between a stretch and the boundary beside it.

    The stretch's direction is the chord of its longest part; the boundary's is
    the chord of the ring a metre either side of ``centre``. A stretch shorter
    than :data:`MIN_STRETCH_FOR_ANGLE_M` has no direction worth reading.

    Args:
        stretch: The part of the wall's line inside the ground.
        ring: The ground's outer ring nearest the stretch.
        centre: The position along the ring nearest the stretch.

    Returns:
        The angle in degrees, 0 (parallel) to 90 (square across), or
        not-a-number for a short stretch.
    """
    longest = max(shapely.get_parts(stretch), key=lambda part: part.length)
    if longest.length < MIN_STRETCH_FOR_ANGLE_M:
        return float("nan")
    first, last = longest.coords[0], longest.coords[-1]
    behind = ring.interpolate((centre - 1.0) % ring.length)
    ahead = ring.interpolate((centre + 1.0) % ring.length)
    wall = np.arctan2(last[1] - first[1], last[0] - first[0])
    edge = np.arctan2(ahead.y - behind.y, ahead.x - behind.x)
    folded = np.degrees(abs(wall - edge)) % 180.0
    return float(min(folded, 180.0 - folded))


def clipped_piece_costs(
    rw: pd.DataFrame,
    pieces: pd.DataFrame,
    ratings: pd.DataFrame,
    policy: PolicySettings,
) -> pd.Series:
    """Price each clipped piece as loss s1 replaces it, by ``rw_id``.

    Each damaged wall is shaped by :func:`replacement_wall_shape` and priced as ``wall_repair_by_claim`` does: replacement
    rate by type and height, the site multiplier and GST. The cost is the wall
    alone, before professional fees, on-costs and contingency.

    Args:
        rw: The loss contract's retaining wall table.
        pieces: The clipped pieces, a subset of ``rw``.
        ratings: The site ratings per claim.
        policy: The scenario's settings.

    Returns:
        The cost including GST, with ``rw_id`` as the index, for the pieces.
    """
    damaged = loss_claims.damaged_walls(rw).reset_index(drop=True)
    _, height, length = replacement_wall_shape(damaged)
    face = wall_face_area_m2(height, length)
    rate = replacement_rate_excl_gst_nzd_per_m2(
        damaged[RW_TYPE_COLUMN].to_numpy(), height
    )
    cost = beta_wall_repair_cost_incl_gst_nzd(
        face,
        ratings=ratings_for(damaged, ratings),
        rate_excl_gst_nzd_per_m2=rate,
        policy=policy,
    )
    priced = pd.Series(cost, index=damaged[RW_ID_COLUMN].to_numpy())
    return priced.reindex(pieces[RW_ID_COLUMN].to_numpy())


def wanted_failures(failures: pd.DataFrame, damaged: pd.DataFrame) -> pd.DataFrame:
    """Return the failures that get a new wall, as ``land_repair_by_claim`` picks them.

    A failure is left out where a damaged wall holds it, where it evacuated no
    ground, or where it is mapped with no length of its own (it shares the wall
    another failure on its unit and claim has).

    Args:
        failures: loss s1's landslide failures.
        damaged: The damaged rows of the contract's retaining wall table.

    Returns:
        The failures that build a wall, with a fresh index.
    """
    held = attach_failures_to_walls(failures, damaged) >= 0
    mapped = (failures["wall_source"] == MAPPED_WALL).to_numpy()
    shares = mapped & (failures["wall_length"].fillna(0.0) <= 0.0).to_numpy()
    wanted = ~held & (failures["evacuated"] > 0).to_numpy() & ~shares
    return failures[wanted].reset_index(drop=True)


def new_wall_costs(
    building: pd.DataFrame, ratings: pd.DataFrame, policy: PolicySettings
) -> pd.DataFrame:
    """Price the new wall of each failure that gets one.

    The same steps as ``land_repair_by_claim``, kept per failure instead of per
    claim: a failure on a mapped wall takes that wall's height and its length
    through the margin rule, any other the slip's own size class and its
    evacuated ground's length.

    Args:
        building: The failures that get a new wall (:func:`wanted_failures`).
        ratings: The site ratings per claim.
        policy: The scenario's settings.

    Returns:
        The failures with ``new_wall_size``, ``new_wall_length_m``,
        ``new_wall_height_m``, ``new_wall_face_m2``, ``new_wall_rate`` and
        ``new_wall_cost`` (including GST, the wall alone).
    """
    from_mapped = (building["wall_source"] == MAPPED_WALL).to_numpy()
    slip_size = classify_landslide_wall_size(
        building["area"].to_numpy(), building["volume"].to_numpy()
    )
    mapped_height = building["wall_height"].fillna(0.0).to_numpy(dtype=float)
    size = np.where(from_mapped, classify_wall_size(mapped_height), slip_size)
    length = np.where(
        from_mapped,
        margin_rule_length_m(building["wall_length"].fillna(0.0).to_numpy()),
        landslide_wall_length_m(building["evacuated"].to_numpy()),
    )
    height = np.where(from_mapped, mapped_height, beta_wall_height_m(slip_size))
    face = beta_wall_face_area_m2(size, length)
    rate = timber_pole_rate_excl_gst_nzd_per_m2(height)
    cost = beta_wall_repair_cost_incl_gst_nzd(
        face,
        ratings=ratings_for(building, ratings),
        rate_excl_gst_nzd_per_m2=rate,
        policy=policy,
    )
    return building.assign(
        new_wall_size=size,
        new_wall_length_m=length,
        new_wall_height_m=height,
        new_wall_face_m2=face,
        new_wall_rate=rate,
        new_wall_cost=cost,
    )


def check_against_settlement(
    extent: str,
    rw: pd.DataFrame,
    ratings: pd.DataFrame,
    built: pd.DataFrame,
    policy: PolicySettings,
) -> str:
    """Compare the in-memory wall and new wall costs with a settlement on disk.

    Args:
        extent: The extent.
        rw: The loss contract's retaining wall table.
        ratings: The site ratings per claim.
        built: :func:`new_wall_costs` over the failures that get a new wall.
        policy: The scenario's settings.

    Returns:
        One line saying how the two agree, or that no settlement is on disk.
    """
    path = settlement_path(WORLD_ID, REALISATION_ID, extent=extent)
    if not path.exists():
        return "no local settlement file, so the costs are not cross-checked"
    disk = pd.read_parquet(path).set_index(CLAIM_ID_COLUMN)
    damaged = loss_claims.damaged_walls(rw).reset_index(drop=True)
    _, height, length = replacement_wall_shape(damaged)
    walls = pd.Series(
        beta_wall_repair_cost_incl_gst_nzd(
            wall_face_area_m2(height, length),
            ratings=ratings_for(damaged, ratings),
            rate_excl_gst_nzd_per_m2=replacement_rate_excl_gst_nzd_per_m2(
                damaged[RW_TYPE_COLUMN].to_numpy(), height
            ),
            policy=policy,
        )
    )
    mine_walls = walls.groupby(damaged[CLAIM_ID_COLUMN].to_numpy()).sum()
    mine_new = built.groupby(CLAIM_ID_COLUMN)["new_wall_cost"].sum()
    gap_walls = (
        (mine_walls.reindex(disk.index).fillna(0.0) - disk["wall_repair_cost_incl_gst_nzd"])
        .abs()
        .max()
    )
    gap_new = (
        (mine_new.reindex(disk.index).fillna(0.0) - disk["land_repair_cost_incl_gst_nzd"])
        .abs()
        .max()
    )
    return (
        f"agrees with {path.name}: wall repair to {gap_walls:,.4f} NZD and new "
        f"wall cost to {gap_new:,.4f} NZD at worst"
    )


def merged_wall_costs(
    pairs: pd.DataFrame, ratings: pd.DataFrame, policy: PolicySettings
) -> pd.DataFrame:
    """Price the two walls apart and as one, for each pair.

    **Apart** is what would be charged if section 6 replaced only the damaged
    stretch (the stretch inside the slip's ground widened by
    ``LANDSLIDE_WALL_MARGIN_M`` at each end, at least
    ``MIN_LANDSLIDE_WALL_LENGTH_M``, never longer than the piece) and the slip
    kept its own new wall. **As one** is a single replacement that also holds
    the slip, sized as ``replacement_wall_shape`` sizes a wall against its slip:
    the longer of the two lengths and the taller of the two heights, at the
    clipped wall's own type's replacement rate. Both are the wall alone,
    including GST and the site multiplier.

    Args:
        pairs: The pair rows, with the piece's type, height, length and the
            slip's new wall length and height. Only rows where the slip clips
            the wall carry a stretch.
        ratings: The site ratings per claim.
        policy: The scenario's settings.

    Returns:
        The frame's index with ``damaged_stretch_wall_cost``,
        ``merged_wall_cost`` and ``apart_wall_cost``.
    """
    types = pairs[RW_TYPE_COLUMN].to_numpy()
    height = pairs[RW_HEIGHT_COLUMN].to_numpy(float)
    piece = pairs[RW_LENGTH_COLUMN].to_numpy(float)
    inside = pairs["inside_m"].fillna(0.0).to_numpy(float)
    stretch_length = np.minimum(
        piece,
        np.maximum(inside + 2 * LANDSLIDE_WALL_MARGIN_M, MIN_LANDSLIDE_WALL_LENGTH_M),
    )
    merged_length = np.maximum(stretch_length, pairs["new_wall_length_m"].to_numpy(float))
    merged_height = np.maximum(height, pairs["new_wall_height_m"].to_numpy(float))

    def price(length: np.ndarray, tall: np.ndarray) -> np.ndarray:
        """Cost a replacement wall of this length and height."""
        return beta_wall_repair_cost_incl_gst_nzd(
            wall_face_area_m2(tall, length),
            ratings=ratings_for(pairs, ratings),
            rate_excl_gst_nzd_per_m2=replacement_rate_excl_gst_nzd_per_m2(types, tall),
            policy=policy,
        )

    stretch_cost = price(stretch_length, height)
    return pd.DataFrame(
        {
            "damaged_stretch_wall_cost": stretch_cost,
            "merged_wall_cost": price(merged_length, merged_height),
            "apart_wall_cost": stretch_cost + pairs["new_wall_cost"].to_numpy(float),
        },
        index=pairs.index,
    )


def classify_pair(row: pd.Series) -> str:
    """Return the verdict on one clipped piece and one new wall.

    Args:
        row: A pair row carrying ``clips`` and ``share_on_edge``.

    Returns:
        :data:`SAME`, :data:`DIFFERENT_CLIPPING` or :data:`DIFFERENT_APART`.
    """
    if not row["clips"]:
        return DIFFERENT_APART
    if row["share_on_edge"] >= SAME_STRUCTURE_SHARE:
        return SAME
    return DIFFERENT_CLIPPING


def analyse(
    extent: str, root: Path, label: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Find the claims carrying a clipped wall piece and a new wall, per extent.

    Args:
        extent: A name from landloss.io.area_of_interest.EXTENTS.
        root: The folder holding ``vul`` and ``hazard/landslide``.
        label: What the run is called in the outputs.

    Returns:
        The pair table (one row per clipped piece and new wall on a claim), the
        claim table (one row per claim carrying both) and the extent's summary
        figures.
    """
    tables = settlement_inputs(extent, root)
    rw, land, slides = tables["rw"], tables["land"], tables["slides"]
    own_slope = tables["flags"].set_index(RW_ID_COLUMN)[SLOPE_ID_COLUMN]
    policy = PolicySettings()

    ratings = site_ratings_by_claim(land, extent=extent)
    failures = landslide_failures(land)
    damaged = loss_claims.damaged_walls(rw).reset_index(drop=True)
    building = wanted_failures(failures, damaged)
    built = new_wall_costs(building, ratings, policy)
    if root == TEMP_DIR:
        check = check_against_settlement(extent, rw, ratings, built, policy)
    else:
        check = "a saved run, so there is no settlement file to check against"

    pieces = clipped_pieces(rw)
    pieces = pieces.assign(
        replace_cost=clipped_piece_costs(rw, pieces, ratings, policy).to_numpy()
    )
    ground = slip_ground(slides)
    inside = stretches_inside(pieces, ground, own_slope)
    ground_by_id = ground.set_index(LANDSLIDE_ID_COLUMN).geometry

    inside_by_piece = inside.groupby(RW_ID_COLUMN)["inside_m"].sum()
    pieces = pieces.assign(
        clipped_inside_m=inside_by_piece.reindex(pieces[RW_ID_COLUMN]).fillna(0.0).to_numpy(),
        # A split wall's pieces each carry the whole wall's line as geometry, and
        # the length on the claim as rw_length, so the stretch inside a slip's
        # ground is measured on the whole wall and may fall on another claim.
        wall_line_length_m=pieces.geometry.length.to_numpy(),
        piece_is_split=(pieces[RW_ID_COLUMN] != pieces[PARENT_RW_ID_COLUMN]).to_numpy(),
    )

    pairs = pieces.drop(columns="geometry").merge(
        built, on=CLAIM_ID_COLUMN, how="inner", suffixes=("", "_slip")
    )
    pairs = pairs.rename(columns={"landslide_id": "slip_id", "rw_id_slip": "slip_rw_id"})
    clips = inside.rename(columns={LANDSLIDE_ID_COLUMN: "slip_id"})
    pairs = pairs.merge(clips, on=[RW_ID_COLUMN, "slip_id"], how="left")
    pairs["clips"] = pairs["inside_m"].notna()
    measures = []
    for row in pairs.itertuples(index=False):
        if row.clips:
            measures.append(
                edge_geometry_test(
                    row.stretch, ground_by_id[row.slip_id], row.new_wall_length_m
                )
            )
        else:
            measures.append({})
    pairs = pairs.join(pd.DataFrame(measures, index=pairs.index))
    pairs["verdict"] = pairs.apply(classify_pair, axis=1)
    pairs = pairs.join(merged_wall_costs(pairs, ratings, policy))
    same_rows = pairs["verdict"] == SAME
    pairs.loc[~same_rows, ["damaged_stretch_wall_cost", "merged_wall_cost", "apart_wall_cost"]] = np.nan

    pair_columns = [
        CLAIM_ID_COLUMN,
        RW_ID_COLUMN,
        PARENT_RW_ID_COLUMN,
        RW_TYPE_COLUMN,
        RW_SIZE_COLUMN,
        RW_HEIGHT_COLUMN,
        RW_LENGTH_COLUMN,
        "wall_line_length_m",
        "piece_is_split",
        "clipped_inside_m",
        "replace_cost",
        "slip_id",
        "area",
        "new_wall_size",
        "new_wall_length_m",
        "new_wall_height_m",
        "new_wall_face_m2",
        "new_wall_cost",
        "clips",
        "inside_m",
        "share_on_edge",
        "max_edge_distance_m",
        "mean_edge_distance_m",
        "placed_min_distance_m",
        "placed_max_distance_m",
        "placed_overlap_share",
        "angle_to_edge_deg",
        "damaged_stretch_wall_cost",
        "merged_wall_cost",
        "apart_wall_cost",
        *(f"share_within_{t:g}m" for t in SENSITIVITY_TOLERANCES_M),
        "verdict",
    ]
    pairs = pairs[pair_columns].rename(
        columns={
            RW_LENGTH_COLUMN: "clipped_piece_length_m",
            "inside_m": "stretch_inside_this_slip_m",
            "area": "slip_area_on_claim_m2",
            "replace_cost": "clipped_wall_cost",
        }
    )
    pairs.insert(0, "extent", label)

    both = sorted(set(pairs[CLAIM_ID_COLUMN]))
    claim_pieces = pieces[pieces[CLAIM_ID_COLUMN].isin(both)]
    claim_new = built[built[CLAIM_ID_COLUMN].isin(both)]
    by_claim = pd.DataFrame(index=pd.Index(both, name=CLAIM_ID_COLUMN))
    by_claim["clipped_pieces"] = claim_pieces.groupby(CLAIM_ID_COLUMN).size()
    by_claim["clipped_wall_cost"] = claim_pieces.groupby(CLAIM_ID_COLUMN)[
        "replace_cost"
    ].sum()
    by_claim["clipped_wall_length_m"] = claim_pieces.groupby(CLAIM_ID_COLUMN)[
        RW_LENGTH_COLUMN
    ].sum()
    by_claim["clipped_inside_m"] = claim_pieces.groupby(CLAIM_ID_COLUMN)[
        "clipped_inside_m"
    ].sum()
    by_claim["new_walls"] = claim_new.groupby(CLAIM_ID_COLUMN).size()
    by_claim["new_wall_cost"] = claim_new.groupby(CLAIM_ID_COLUMN)["new_wall_cost"].sum()
    by_claim["new_wall_length_m"] = claim_new.groupby(CLAIM_ID_COLUMN)[
        "new_wall_length_m"
    ].sum()
    by_claim["total_cost"] = by_claim["clipped_wall_cost"] + by_claim["new_wall_cost"]
    rank = {SAME: 0, DIFFERENT_CLIPPING: 1, DIFFERENT_APART: 2}
    best = (
        pairs.assign(_rank=pairs["verdict"].map(rank))
        .groupby(CLAIM_ID_COLUMN)["_rank"]
        .min()
    )
    by_claim["verdict"] = best.map({value: key for key, value in rank.items()})
    by_claim = by_claim.reset_index()
    by_claim.insert(0, "extent", label)

    summary = {
        "extent": label,
        "claims_with_clipped_piece": int(pieces[CLAIM_ID_COLUMN].nunique()),
        "clipped_pieces": len(pieces),
        "clipped_pieces_touching_neighbour_ground": int((pieces["clipped_inside_m"] > 0).sum()),
        "claims_with_new_wall": int(built[CLAIM_ID_COLUMN].nunique()),
        "claims_with_both": len(both),
        "pairs": len(pairs),
        "pairs_where_slip_clips_wall": int(pairs["clips"].sum()),
        "clipped_wall_cost_all_pieces": float(pieces["replace_cost"].sum()),
        "clipped_wall_cost_claims_with_both": float(by_claim["clipped_wall_cost"].sum()),
        "new_wall_cost_claims_with_both": float(by_claim["new_wall_cost"].sum()),
        "total_cost_claims_with_both": float(by_claim["total_cost"].sum()),
        "clipped_wall_length_m": float(by_claim["clipped_wall_length_m"].sum()),
        "clipped_inside_m": float(by_claim["clipped_inside_m"].sum()),
        "new_wall_length_m": float(by_claim["new_wall_length_m"].sum()),
        "claims_same_structure": int((by_claim["verdict"] == SAME).sum()),
        "claims_different_slip_clips": int((by_claim["verdict"] == DIFFERENT_CLIPPING).sum()),
        "claims_different_apart": int((by_claim["verdict"] == DIFFERENT_APART).sum()),
        "same_structure_clipped_wall_cost": float(
            by_claim.loc[by_claim["verdict"] == SAME, "clipped_wall_cost"].sum()
        ),
        "same_structure_new_wall_cost": float(
            by_claim.loc[by_claim["verdict"] == SAME, "new_wall_cost"].sum()
        ),
        "check_against_settlement": check,
    }
    clipping = pairs[pairs["clips"]]
    summary["clipped_pieces_split"] = int(pieces["piece_is_split"].sum())
    summary["clipping_pairs_on_split_pieces"] = int(clipping["piece_is_split"].sum())
    summary["same_structure_pairs_on_split_pieces"] = int(
        (clipping["piece_is_split"] & (clipping["verdict"] == SAME)).sum()
    )
    summary["same_structure_pairs"] = int((pairs["verdict"] == SAME).sum())
    same_pairs = pairs[pairs["verdict"] == SAME]
    summary["same_pairs_apart_wall_cost"] = float(same_pairs["apart_wall_cost"].sum())
    summary["same_pairs_merged_wall_cost"] = float(same_pairs["merged_wall_cost"].sum())
    for tolerance in SENSITIVITY_TOLERANCES_M:
        column = f"share_within_{tolerance:g}m"
        same = clipping.loc[clipping[column] >= SAME_STRUCTURE_SHARE, CLAIM_ID_COLUMN]
        summary[f"claims_same_structure_at_{tolerance:g}m"] = int(same.nunique())
    square = clipping["angle_to_edge_deg"] > SQUARE_ACROSS_DEG
    summary["clipping_pairs_with_a_measurable_angle"] = int(
        clipping["angle_to_edge_deg"].notna().sum()
    )
    summary["clipping_pairs_square_across_the_edge"] = int(square.sum())
    return pairs, by_claim, summary


def loaded_repair_nzd(wall_cost: float, policy: PolicySettings) -> float:
    """Return a claim's repair cost with fees, on-costs and contingency on its walls.

    The same chain loss s1 applies to a claim whose only works are walls:
    professional fees, then mobilisation and project management, then the
    contingency on the whole.

    Args:
        wall_cost: The claim's wall cost including GST.
        policy: The scenario's settings.

    Returns:
        The repair cost including GST.
    """
    walls = np.array([wall_cost])
    fees = professional_fees_incl_gst_nzd(walls, policy=policy)
    on_costs = on_costs_incl_gst_nzd(walls, fees, np.zeros(1), policy=policy)
    before = walls + fees + on_costs.mob_demob + on_costs.project_management
    return float((before + contingency_incl_gst_nzd(before))[0])


def worked_example() -> pd.DataFrame:
    """Return the Porirua example, from the saved 2026-10-11 run.

    That run's land table lists no separate failures (it predates T-124), so
    loss held the claim's pooled ground on the wall itself and charged no new
    wall. The example is built as the current loss s1 would see it: the ground
    of :data:`EXAMPLE_SLIP_ID` on the claim, from the land table's area and
    inundated depth, is one failure held by no damaged wall, and the clipped
    wall is replaced as it was.

    Returns:
        One row, in the layout of the pair tables.
    """
    extent, root = SNAPSHOT_EXTENT, SNAPSHOT_ROOT
    tables = settlement_inputs(extent, root)
    rw, land, slides = tables["rw"], tables["land"], tables["slides"]
    own_slope = tables["flags"].set_index(RW_ID_COLUMN)[SLOPE_ID_COLUMN]
    policy = PolicySettings()
    ratings = site_ratings_by_claim(land, extent=extent)

    wall = rw[rw[RW_ID_COLUMN] == EXAMPLE_WALL_ID]
    claim = wall[CLAIM_ID_COLUMN].iloc[0]
    on_claim = land[land[CLAIM_ID_COLUMN] == claim]
    area = float(on_claim[LANDSLIDE_AREA_COLUMN].sum())
    wet = float(on_claim[INUNDATED_AREA_COLUMN].sum())
    depth = float(on_claim[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).max())
    none_held = pd.DataFrame(
        columns=[CLAIM_ID_COLUMN, "landslide_id", RW_ID_COLUMN, "area", "volume"]
    ).assign(attributed=pd.Series(dtype=bool))
    wall_cost = clipped_piece_costs(rw, wall, ratings, none_held, policy)
    building = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [claim],
            "landslide_id": [EXAMPLE_SLIP_ID],
            RW_ID_COLUMN: [None],
            "area": [area],
            "volume": [wet * depth],
            "attributed": [True],
        }
    )
    built = new_wall_costs(building, ratings, policy)

    ground = slip_ground(slides)
    inside = stretches_inside(wall, ground, own_slope)
    stretch = inside[inside[LANDSLIDE_ID_COLUMN] == EXAMPLE_SLIP_ID].iloc[0]
    measures = edge_geometry_test(
        stretch["stretch"],
        ground.set_index(LANDSLIDE_ID_COLUMN).geometry[EXAMPLE_SLIP_ID],
        float(built["new_wall_length_m"].iloc[0]),
    )
    row = {
        "claim_id": claim,
        "rw_id": EXAMPLE_WALL_ID,
        "rw_type": wall[RW_TYPE_COLUMN].iloc[0],
        "rw_height": float(wall[RW_HEIGHT_COLUMN].iloc[0]),
        "clipped_piece_length_m": float(wall[RW_LENGTH_COLUMN].iloc[0]),
        "clipped_inside_m": float(inside["inside_m"].sum()),
        "stretch_inside_this_slip_m": float(stretch["inside_m"]),
        "clipped_wall_cost": float(wall_cost.iloc[0]),
        "slip_id": EXAMPLE_SLIP_ID,
        "slip_area_on_claim_m2": area,
        "slip_inundated_area_m2": wet,
        "slip_inundated_depth_m": depth,
        "new_wall_size": built["new_wall_size"].iloc[0],
        "new_wall_length_m": float(built["new_wall_length_m"].iloc[0]),
        "new_wall_height_m": float(built["new_wall_height_m"].iloc[0]),
        "new_wall_cost": float(built["new_wall_cost"].iloc[0]),
        "loaded_repair_clipped_wall_only": loaded_repair_nzd(
            float(wall_cost.iloc[0]), policy
        ),
        "loaded_repair_both": loaded_repair_nzd(
            float(wall_cost.iloc[0] + built["new_wall_cost"].iloc[0]), policy
        ),
        "wall_own_slope": own_slope[EXAMPLE_WALL_ID],
        **measures,
    }
    row["verdict"] = classify_pair(pd.Series({"clips": True, **measures}))
    return pd.DataFrame([row])


def main() -> None:
    """Write the pair and claim tables per extent, the example and the summary."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for extent in EXTENTS:
        print(RULE)
        print(f"{extent}, world {WORLD_ID}, realisation {REALISATION_ID}", flush=True)
        pairs, by_claim, summary = analyse(extent, TEMP_DIR, extent)
        pairs.to_csv(OUT_DIR / f"pairs-{extent}.csv", index=False)
        sample = pd.concat(
            [
                pairs[pairs["verdict"] == verdict].sample(
                    min(count, int((pairs["verdict"] == verdict).sum())),
                    random_state=SAMPLE_SEED,
                )
                for verdict, count in SAMPLE_PER_VERDICT.items()
            ]
        )
        sample.to_csv(OUT_DIR / f"samples-{extent}.csv", index=False)
        by_claim.to_csv(OUT_DIR / f"claims-{extent}.csv", index=False)
        summaries.append(summary)
        for key, value in summary.items():
            shown = f"{value:,.0f}" if isinstance(value, float) else value
            print(f"  {key}: {shown}")
    pd.DataFrame(summaries).to_csv(OUT_DIR / "summary.csv", index=False)
    print(RULE)
    print(f"The worked example, from {SNAPSHOT_LABEL}:")
    example = worked_example()
    example.to_csv(OUT_DIR / "example-porirua-wall.csv", index=False)
    print(example.T.to_string())
    print(RULE)
    print(f"Wrote the tables to {OUT_DIR}")


if __name__ == "__main__":
    main()
