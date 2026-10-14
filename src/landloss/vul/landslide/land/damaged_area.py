"""How much of a property's insured land a landslide takes, and from where.

The damage measure for a landslide on land is **geometric**, not a damage state.
A landslide either covers part of a property or it does not, and how much it
covers is the whole question, so this module intersects the hazard module's
polygons with the insured land and returns areas.

The two kinds of ground are kept apart all the way through, because the policy
settles them differently:

- **Evacuated** ground is what the failure removed -- loss of support, where the
  land under or beside the property went.
- **Inundated** ground is where the debris came to rest, which may have started
  on somebody else's property entirely.

Each carries the **depth** of the landslide it belongs to, from the volume-area
power law in :mod:`landloss.hazard.landslide.geometry`, because what a repair
costs depends on how much material has to be moved and not only on the footprint.

One asymmetry in the inputs drives the arithmetic here. Evacuated polygons are
guaranteed not to overlap one another; inundated polygons are not, because two
failures running into the same gully floor both land on it. Ground buried twice
is buried once, so **inundated area is measured on the union** rather than
summed across landslides. Doing otherwise would charge a property twice for the
same square metre.

The two kinds are also measured together, on their union, because the loss
contract's ``land_slide_total_insured_land_area`` is the ground taken by either
kind: ground that is both evacuated and inundated counts once there too.

The land classes themselves are the hazard module's,
:mod:`landloss.hazard.landslide.land_class`, so that the polygons are read here
under the names they were written with. The urban model writes a third class,
**imminent** ground left standing behind a headscarp. It is measured apart from
the damaged ground above and added to none of it (**T-45**, 2026-10-14):

- **Imminent evacuated** ground is the imminent polygon less any ground
  evacuated on the property by any failure, counted once. Ground that is only
  inundated is not taken off: buried ground can still be imminent for
  evacuation.
- **Re-inundated** ground is the inundated ground of the failures that have
  imminent land, buried again. Its area is the union over those failures, its
  volume sums each failure's area by its own depth, and its depth is the volume
  over the area, so area by depth is always the volume.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    LANDSLIDE_AREAS_COLUMN,
    LANDSLIDE_EVACUATED_AREAS_COLUMN,
    LANDSLIDE_IDS_COLUMN,
    LANDSLIDE_IMMINENT_AREAS_COLUMN,
    LANDSLIDE_INUNDATED_AREAS_COLUMN,
    LANDSLIDE_INUNDATED_DEPTHS_COLUMN,
    LANDSLIDE_REINUNDATED_AREAS_COLUMN,
    LANDSLIDE_RW_IDS_COLUMN,
    RW_ID_COLUMN,
)
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    IMMINENT,
    INUNDATED,
    LAND_CLASS_COLUMN,
)

DEPTH_COLUMN = "depth_m"
# Which failure a polygon belongs to: its evacuated and inundated polygons share
# it. The hazard realisation's name; urban failures also carry the wall they
# failed with as ``rw_id``.
LANDSLIDE_ID_COLUMN = "landslide_id"

# What the output calls each kind of damaged ground, matching the causes the
# vulnerability rows are keyed on.
AREA_COLUMNS = {
    EVACUATED: "evacuated_area_m2",
    INUNDATED: "inundated_area_m2",
}
DEPTH_COLUMNS = {
    EVACUATED: "evacuated_depth_m",
    INUNDATED: "inundated_depth_m",
}
# Imminent ground is not in AREA_COLUMNS, so no filter on that mapping sees it and
# the damaged ground above never includes it.
IMMINENT_EVACUATED_AREA_M2_COLUMN = "imminent_evacuated_area_m2"
REINUNDATED_AREA_M2_COLUMN = "reinundated_area_m2"
REINUNDATED_DEPTH_M_COLUMN = "reinundated_depth_m"
REINUNDATED_VOLUME_M3_COLUMN = "reinundated_volume_m3"
IMMINENT_GROUND_COLUMNS = (
    IMMINENT_EVACUATED_AREA_M2_COLUMN,
    REINUNDATED_AREA_M2_COLUMN,
    REINUNDATED_DEPTH_M_COLUMN,
    REINUNDATED_VOLUME_M3_COLUMN,
)
# The insured ground taken by either class, measured on the union so ground that
# is both evacuated and inundated counts once. This is what the contract's
# land_slide_total_insured_land_area is.
UNION_AREA_COLUMN = "landslide_area_m2"
# The part of that ground under the claim's buildings, which the loss module
# values at the full rate of its land value tiers (landloss.loss.qv_land_value).
FOOTPRINT_AREA_COLUMN = "landslide_footprint_area_m2"


def _overlay(
    insured: gpd.GeoDataFrame, slides: gpd.GeoDataFrame, id_column: str
) -> gpd.GeoDataFrame:
    """Return the parts of the insured land each landslide covers."""
    columns = [id_column, insured.geometry.name]
    pieces = gpd.overlay(
        insured[columns],
        slides,
        how="intersection",
        keep_geom_type=True,
    )
    return pieces[~pieces.geometry.is_empty]


def _accumulate_class(
    rows: dict[str, dict],
    insured: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    land_class: str,
    id_column: str,
) -> None:
    """Add one kind of damaged ground to the per-property rows, in place.

    Args:
        rows: The rows built so far, keyed by property, added to in place.
        insured: The insured land polygons.
        landslides: Every landslide polygon of every kind.
        land_class: The kind of ground to accumulate, a key of
            :data:`AREA_COLUMNS`.
        id_column: The property identifier.
    """
    slides = landslides[landslides[LAND_CLASS_COLUMN] == land_class]
    if slides.empty:
        return

    keep = [LAND_CLASS_COLUMN, DEPTH_COLUMN, slides.geometry.name]
    pieces = _overlay(insured, slides[keep], id_column)
    if pieces.empty:
        return
    pieces = pieces.assign(_piece_area=pieces.geometry.area)

    for address, group in pieces.groupby(id_column):
        row = rows.setdefault(address, {id_column: address})
        # Summing across landslides would double count ground two of them both
        # reached, which inundated polygons are allowed to do.
        row[AREA_COLUMNS[land_class]] = group.geometry.union_all().area
        # Depth belongs to a landslide, so a property covered by two takes the
        # depth each contributed, weighted by how much it contributed.
        weights = group["_piece_area"].to_numpy()
        depths = group[DEPTH_COLUMN].to_numpy(dtype=float)
        usable = np.isfinite(depths) & (weights > 0)
        row[DEPTH_COLUMNS[land_class]] = (
            float(np.average(depths[usable], weights=weights[usable]))
            if usable.any()
            else np.nan
        )


def _union_area(
    insured: gpd.GeoDataFrame, landslides: gpd.GeoDataFrame, id_column: str
) -> pd.Series:
    """Return the ground either kind of landslide takes on each property.

    Args:
        insured: The insured land polygons.
        landslides: Every landslide polygon of every kind.
        id_column: The property identifier.

    Returns:
        The area of the union of every piece on the property, indexed by
        ``id_column``; empty when no landslide touches the insured land.
    """
    slides = landslides[landslides[LAND_CLASS_COLUMN].isin(AREA_COLUMNS)]
    if slides.empty:
        return pd.Series(dtype=float)
    pieces = _overlay(insured, slides[[slides.geometry.name]], id_column)
    if pieces.empty:
        return pd.Series(dtype=float)
    return pieces.groupby(id_column).geometry.apply(
        lambda group: group.union_all().area
    )


def damaged_area_per_property(
    insured: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> pd.DataFrame:
    """Return the evacuated, inundated and combined area on each property.

    Args:
        insured: One insured land polygon per property, carrying ``id_column``.
            These must not overlap one another, which the exposure step
            guarantees; if they did, a landslide would be counted on two
            properties at once.
        landslides: The hazard module's polygons, carrying
            :data:`LAND_CLASS_COLUMN` and :data:`DEPTH_COLUMN`.
        id_column: The property identifier.

    Returns:
        One row per property that any landslide touched, carrying the area of
        each kind of ground, the area of their union as
        :data:`UNION_AREA_COLUMN`, and each kind's mean depth weighted by area.
        The union counts ground that is both evacuated and inundated once, so it
        is at least the larger of the two areas and at most their sum. A
        property no landslide reached is absent rather than present with zeros.

    Raises:
        ValueError: If the frames disagree on their coordinate reference system,
            or the landslides carry no land class.
    """
    if LAND_CLASS_COLUMN not in landslides.columns:
        msg = f"landslides carry no {LAND_CLASS_COLUMN!r} column"
        raise ValueError(msg)
    if not landslides.empty and insured.crs != landslides.crs:
        msg = f"insured land is {insured.crs} and landslides are {landslides.crs}"
        raise ValueError(msg)

    order = [
        id_column,
        *AREA_COLUMNS.values(),
        UNION_AREA_COLUMN,
        *DEPTH_COLUMNS.values(),
    ]
    rows: dict[str, dict] = {}
    for land_class in AREA_COLUMNS:
        _accumulate_class(rows, insured, landslides, land_class, id_column)

    if not rows:
        return pd.DataFrame({column: [] for column in order})

    damaged = pd.DataFrame(list(rows.values()))
    for column in (*AREA_COLUMNS.values(), *DEPTH_COLUMNS.values()):
        if column not in damaged.columns:
            damaged[column] = np.nan
    # An untouched kind of ground is zero area, not unknown area.
    for column in AREA_COLUMNS.values():
        damaged[column] = damaged[column].fillna(0.0)
    union = _union_area(insured, landslides, id_column)
    damaged[UNION_AREA_COLUMN] = damaged[id_column].map(union).fillna(0.0)
    return damaged[order].sort_values(id_column, kind="stable").reset_index(drop=True)


def _first_depth(group: gpd.GeoDataFrame) -> float:
    """Return the depth a failure's pieces carry, missing when none has one."""
    depths = group[DEPTH_COLUMN].to_numpy(dtype=float)
    depths = depths[np.isfinite(depths)]
    return float(depths[0]) if len(depths) else np.nan


def _evacuated_ground(
    insured: gpd.GeoDataFrame, landslides: gpd.GeoDataFrame, id_column: str
) -> dict:
    """Return each property's evacuated ground, every failure's unioned."""
    evacuated = landslides[landslides[LAND_CLASS_COLUMN] == EVACUATED]
    if evacuated.empty:
        return {}
    pieces = _overlay(insured, evacuated[[evacuated.geometry.name]], id_column)
    return {
        address: group.geometry.union_all()
        for address, group in pieces.groupby(id_column)
    }


def evacuated_ground_per_failure(
    insured: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> dict:
    """Return each failure's evacuated ground on each property, as a geometry.

    The ground :func:`damaged_area_per_failure` measures as ``evacuated_area_m2``,
    kept as the shape, so a wall can be placed alongside it (section 4 of the
    property damage tweaks). With the claim as ``id_column``, a claim's polygons
    are one property.

    Args:
        insured: The insured land polygons, carrying ``id_column``.
        landslides: The hazard module's polygons, carrying
            :data:`LANDSLIDE_ID_COLUMN` and :data:`LAND_CLASS_COLUMN`.
        id_column: The property identifier.

    Returns:
        ``{(property id, landslide id): the evacuated ground unioned}``, for
        each failure with evacuated ground on the property.
    """
    evacuated = landslides[landslides[LAND_CLASS_COLUMN] == EVACUATED]
    if evacuated.empty:
        return {}
    pieces = _overlay(
        insured, evacuated[[LANDSLIDE_ID_COLUMN, evacuated.geometry.name]], id_column
    )
    return {
        key: group.geometry.union_all()
        for key, group in pieces.groupby([id_column, LANDSLIDE_ID_COLUMN])
    }


def imminent_ground_per_property(
    insured: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> pd.DataFrame:
    """Return the imminent evacuated and re-inundated ground on each property.

    Imminent evacuated ground is the imminent polygons' union on the property
    less the ground any failure evacuated there. Ground only inundated stays in
    it. Re-inundated ground is the inundated ground of the failures that have an
    imminent polygon anywhere, unioned for the area and summed over failures at
    each one's own depth for the volume.

    Args:
        insured: The insured land polygons, carrying ``id_column``.
        landslides: The hazard module's polygons, carrying
            :data:`LAND_CLASS_COLUMN`, :data:`DEPTH_COLUMN` and, where any
            imminent polygon exists, :data:`LANDSLIDE_ID_COLUMN`.
        id_column: The property identifier.

    Returns:
        One row per property imminent ground or a re-inundated failure reached:
        ``id_column`` and :data:`IMMINENT_GROUND_COLUMNS`. The depth is the
        volume over the area, 0 where the area is 0. Empty when no polygon is
        imminent.

    Raises:
        ValueError: If the landslides carry imminent polygons but no landslide
            id.
    """
    order = [id_column, *IMMINENT_GROUND_COLUMNS]
    imminent = landslides[landslides[LAND_CLASS_COLUMN] == IMMINENT]
    if imminent.empty:
        return pd.DataFrame({column: [] for column in order})
    if LANDSLIDE_ID_COLUMN not in landslides.columns:
        msg = f"landslides carry no {LANDSLIDE_ID_COLUMN!r} column"
        raise ValueError(msg)

    rows: dict[str, dict] = {}
    standing = _overlay(insured, imminent[[imminent.geometry.name]], id_column)
    evacuated = _evacuated_ground(insured, landslides, id_column)
    for address, group in standing.groupby(id_column):
        ground = group.geometry.union_all()
        if address in evacuated:
            ground = ground.difference(evacuated[address])
        row = rows.setdefault(address, {id_column: address})
        row[IMMINENT_EVACUATED_AREA_M2_COLUMN] = ground.area

    imminent_failures = set(imminent[LANDSLIDE_ID_COLUMN].dropna())
    buried = landslides[
        (landslides[LAND_CLASS_COLUMN] == INUNDATED)
        & landslides[LANDSLIDE_ID_COLUMN].isin(imminent_failures)
    ]
    if not buried.empty:
        keep = [LANDSLIDE_ID_COLUMN, DEPTH_COLUMN, buried.geometry.name]
        pieces = _overlay(insured, buried[keep], id_column)
        for address, group in pieces.groupby(id_column):
            volume = 0.0
            for _, failure in group.groupby(LANDSLIDE_ID_COLUMN):
                depth = _first_depth(failure)
                if np.isfinite(depth):
                    volume += failure.geometry.union_all().area * depth
            area = group.geometry.union_all().area
            row = rows.setdefault(address, {id_column: address})
            row[REINUNDATED_AREA_M2_COLUMN] = area
            row[REINUNDATED_VOLUME_M3_COLUMN] = volume
            row[REINUNDATED_DEPTH_M_COLUMN] = volume / area if area > 0 else 0.0

    if not rows:
        return pd.DataFrame({column: [] for column in order})
    ground = pd.DataFrame(list(rows.values())).reindex(columns=order).fillna(0.0)
    return ground.sort_values(id_column, kind="stable").reset_index(drop=True)


def with_imminent_ground(
    damaged: pd.DataFrame,
    imminent: pd.DataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> pd.DataFrame:
    """Return the damaged areas with each property's imminent ground beside them.

    A property only imminent ground reaches gets a row of its own, with no
    damaged ground, because the imminent ground is carried to loss all the same.

    Args:
        damaged: From :func:`damaged_area_per_property`.
        imminent: From :func:`imminent_ground_per_property`.
        id_column: The property identifier.

    Returns:
        ``damaged`` with :data:`IMMINENT_GROUND_COLUMNS` added, ordered by
        property; 0 where a property has no imminent ground. A property only
        imminent ground reached has zero damaged areas and no depths.
    """
    merged = damaged.merge(imminent, on=id_column, how="outer", validate="1:1")
    zeros = [*AREA_COLUMNS.values(), UNION_AREA_COLUMN, *IMMINENT_GROUND_COLUMNS]
    merged[zeros] = merged[zeros].fillna(0.0)
    return merged.sort_values(id_column, kind="stable").reset_index(drop=True)


def damaged_area_per_failure(
    insured: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> pd.DataFrame:
    """Return, per property, each landslide that reached it and what it took.

    The per-property areas pool every landslide; this keeps them apart, so a
    property two separate slips reached can be repaired with a wall for each
    (T-124). A failure's ground is its evacuated and inundated pieces on the
    property, unioned, so its own deposit over its own scar counts once; two
    failures that buried the same ground each count it, because each wall holds
    its own slip. The per-property union is unaffected. Its evacuated ground is
    kept as well, because the wall a slip needs runs across the scar, not the
    deposit.

    Its imminent ground and re-inundated ground are kept too (2026-10-14): the
    imminent ground is the failure's own imminent polygon on the property less
    the ground any failure evacuated there, and the re-inundated ground is its
    inundated ground when it has imminent land anywhere, else zero. A failure
    only imminent ground reaches on the property is not listed, so these lists
    stay in the order of the others, and its imminent ground is in the
    per-property total alone.

    Args:
        insured: The insured land polygons, carrying ``id_column``.
        landslides: The hazard module's polygons, carrying
            :data:`LANDSLIDE_ID_COLUMN`, :data:`LAND_CLASS_COLUMN` and
            :data:`DEPTH_COLUMN`, and :data:`RW_ID_COLUMN` where the failure
            took a retaining wall with it.
        id_column: The property identifier.

    Returns:
        One row per property and landslide: ``id_column``,
        :data:`LANDSLIDE_ID_COLUMN`, the wall's :data:`RW_ID_COLUMN` or
        missing, ``area_m2``, ``evacuated_area_m2``, ``inundated_area_m2`` and
        ``inundated_depth_m`` (missing with no inundated ground),
        ``imminent_area_m2`` and ``reinundated_area_m2``. Ordered by property
        and landslide.

    Raises:
        ValueError: If the landslides carry no landslide id.
    """
    columns = [
        id_column,
        LANDSLIDE_ID_COLUMN,
        RW_ID_COLUMN,
        "area_m2",
        "evacuated_area_m2",
        "inundated_area_m2",
        "inundated_depth_m",
        "imminent_area_m2",
        "reinundated_area_m2",
    ]
    if LANDSLIDE_ID_COLUMN not in landslides.columns:
        msg = f"landslides carry no {LANDSLIDE_ID_COLUMN!r} column"
        raise ValueError(msg)
    slides = landslides[landslides[LAND_CLASS_COLUMN].isin(AREA_COLUMNS)]
    if slides.empty:
        return pd.DataFrame({column: [] for column in columns})
    if RW_ID_COLUMN not in slides.columns:
        slides = slides.assign(**{RW_ID_COLUMN: None})
    keep = [
        LANDSLIDE_ID_COLUMN,
        RW_ID_COLUMN,
        LAND_CLASS_COLUMN,
        DEPTH_COLUMN,
        slides.geometry.name,
    ]
    pieces = _overlay(insured, slides[keep], id_column)
    if pieces.empty:
        return pd.DataFrame({column: [] for column in columns})

    imminent = landslides[landslides[LAND_CLASS_COLUMN] == IMMINENT]
    standing = {}
    if not imminent.empty:
        found = _overlay(
            insured, imminent[[LANDSLIDE_ID_COLUMN, imminent.geometry.name]], id_column
        )
        standing = {
            key: group.geometry.union_all()
            for key, group in found.groupby([id_column, LANDSLIDE_ID_COLUMN])
        }
    with_imminent = set(imminent[LANDSLIDE_ID_COLUMN].dropna())
    evacuated_by_any = _evacuated_ground(insured, landslides, id_column)

    rows = []
    for (address, failure), group in pieces.groupby(
        [id_column, LANDSLIDE_ID_COLUMN], sort=True
    ):
        evacuated = group[group[LAND_CLASS_COLUMN] == EVACUATED]
        inundated = group[group[LAND_CLASS_COLUMN] == INUNDATED]
        depths = inundated[DEPTH_COLUMN].to_numpy(dtype=float)
        depths = depths[np.isfinite(depths)]
        walls = group[RW_ID_COLUMN].dropna()
        ground = standing.get((address, failure))
        if ground is not None and address in evacuated_by_any:
            ground = ground.difference(evacuated_by_any[address])
        rows.append(
            {
                id_column: address,
                LANDSLIDE_ID_COLUMN: failure,
                RW_ID_COLUMN: walls.iloc[0] if len(walls) else None,
                "area_m2": group.geometry.union_all().area,
                "evacuated_area_m2": (
                    evacuated.geometry.union_all().area if len(evacuated) else 0.0
                ),
                "inundated_area_m2": (
                    inundated.geometry.union_all().area if len(inundated) else 0.0
                ),
                "inundated_depth_m": float(depths[0]) if len(depths) else np.nan,
                "imminent_area_m2": 0.0 if ground is None else ground.area,
                "reinundated_area_m2": (
                    inundated.geometry.union_all().area
                    if len(inundated) and failure in with_imminent
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def failures_per_property(
    per_failure: pd.DataFrame, *, id_column: str = CLAIM_ID_COLUMN
) -> pd.DataFrame:
    """Return :func:`damaged_area_per_failure` as one row per property, in lists.

    Args:
        per_failure: From :func:`damaged_area_per_failure`.
        id_column: The property identifier.

    Returns:
        Indexed by ``id_column``: the five
        :data:`~landloss.domain.loss_contract.LANDSLIDE_FAILURE_COLUMNS`,
        :data:`~landloss.domain.loss_contract.LANDSLIDE_EVACUATED_AREAS_COLUMN`,
        :data:`~landloss.domain.loss_contract.LANDSLIDE_IMMINENT_AREAS_COLUMN`
        and
        :data:`~landloss.domain.loss_contract.LANDSLIDE_REINUNDATED_AREAS_COLUMN`,
        each a list with one entry per failure, in the same order.
    """
    sources = {
        LANDSLIDE_IDS_COLUMN: LANDSLIDE_ID_COLUMN,
        LANDSLIDE_RW_IDS_COLUMN: RW_ID_COLUMN,
        LANDSLIDE_AREAS_COLUMN: "area_m2",
        LANDSLIDE_EVACUATED_AREAS_COLUMN: "evacuated_area_m2",
        LANDSLIDE_INUNDATED_AREAS_COLUMN: "inundated_area_m2",
        LANDSLIDE_INUNDATED_DEPTHS_COLUMN: "inundated_depth_m",
        LANDSLIDE_IMMINENT_AREAS_COLUMN: "imminent_area_m2",
        LANDSLIDE_REINUNDATED_AREAS_COLUMN: "reinundated_area_m2",
    }
    grouped = per_failure.groupby(id_column, sort=True)
    return pd.DataFrame(
        {
            name: grouped[source].agg(lambda values: [_plain(v) for v in values])
            for name, source in sources.items()
        }
    )


def _plain(value: object) -> object:
    """Return a value as a plain Python one, missing as None."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return value.item() if isinstance(value, np.generic) else value


def footprint_damaged_area(
    footprints: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> pd.Series:
    """Return the ground either kind of landslide takes under each footprint.

    Measured on the union, as :data:`UNION_AREA_COLUMN` is, so a footprint two
    landslides both reached counts once and the result never exceeds it.

    Args:
        footprints: The buildings on each property, merged per property and
            carrying ``id_column``.
        landslides: The hazard module's polygons, carrying
            :data:`LAND_CLASS_COLUMN`.
        id_column: The property identifier.

    Returns:
        The area in m2, indexed by ``id_column``, for every footprint a
        landslide reached; a footprint no landslide reached is absent.
    """
    return _union_area(footprints, landslides, id_column).rename(FOOTPRINT_AREA_COLUMN)


def check_within_insured_area(
    damaged: pd.DataFrame,
    insured: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    area_column: str = "area_m2",
) -> pd.DataFrame:
    """Return any property whose damaged ground exceeds its insured land.

    Evacuated and inundated ground may legitimately overlap each other, so the
    two summed can pass a property's own area without anything being wrong. What
    cannot happen is either one alone, or their union, exceeding it. A union
    smaller than the larger of the two kinds is flagged as well, since the union
    contains both.

    Args:
        damaged: The per-property areas.
        insured: The insured land, carrying ``area_column``.
        id_column: The property identifier.
        area_column: The insured area on ``insured``.

    Returns:
        The offending rows, empty when every property is within its own land and
        every union is consistent with its two kinds.
    """
    merged = damaged.merge(
        insured[[id_column, area_column]], on=id_column, how="left", validate="1:1"
    )
    # A rounding tolerance, not a modelling one: these are polygon areas.
    tolerance = 1e-6
    over = pd.Series(np.zeros(len(merged), dtype=bool), index=merged.index)
    for column in (*AREA_COLUMNS.values(), UNION_AREA_COLUMN):
        over |= merged[column] > merged[area_column] * (1 + tolerance)
    largest_class = merged[list(AREA_COLUMNS.values())].max(axis=1)
    over |= merged[UNION_AREA_COLUMN] < largest_class - tolerance
    return merged[over]
