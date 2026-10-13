"""Settle each claim: the repair cost, the cap, and what NHC pays.

    uv run --frozen python src/scripts/landloss/loss/steps/s1_settlement/s1_gen_settlement.py

Step 0 builds the cap. This step builds the **other half of the comparison** and
calls :func:`~landloss.loss.settlement.settle`, which pays
``min(repair cost, cap)`` less the excess.

How each repair cost is arrived at, and every one of them rests on an
assumption named here:

- **A damaged retaining wall** is replaced, priced on its face area at the beta
  wall rate -- concrete for a share of walls, otherwise the timber pole rate its
  height calls for -- with the site multiplier on top.
- **Each landslide is held by its own wall** (T-124, 2026-10-13). `vul`
  lists the landslides that reached each polygon, and the retaining wall each
  failed with, if any:

  - **A slip that came with a wall** is held by that wall's replacement,
    **sized against that slip** (2026-09-30): never smaller than the wall that
    was there, but larger in size class, length or both where the ground needs
    more wall.
  - **Every other slip gets a new wall** that was never there, sized by how
    much ground it took -- by area, and by volume where an inundated depth
    makes one available -- even on a claim whose own wall failed elsewhere:
    two separate failures want two walls. It is a remediation cost, not an
    asset, so it reaches the repair cost and **never the cap**: a wall that
    did not exist has no undepreciated value to contribute.

  A land table from before the lists were written pools each claim's ground
  as one slip of unknown origin, held as before: by the claim's largest
  damaged wall, or by one new wall where it has none (2026-09-29).
- **Professional fees are charged once per claim that involves a wall** --
  consent, design, engineering, health and safety, project management and
  survey: 20% of what the claim's walls cost to build, never less than $5,100
  excluding GST, the costing tool's own fee total (2026-10-12). A wall is what
  gets designed and consented:
  clearing spoil on its own does not attract them, and neither does a Canterbury
  liquefaction cost, that being a settled amount rather than a works estimate.
- **Landslide spoil is cleared at a rate per cubic metre**, on top of whatever
  wall the ground needs. The volume still sets the earthworks rating as well,
  which is worth watching for a double count -- the rating is how hard the site
  is to build on, this is carting material away. The rate is the costing tool's
  own "Clear site: Load, cart and tip material", $150 per cubic metre excluding
  GST (**L-33**).
- **Liquefaction land damage** carries its own settled cost from the Canterbury
  database, which `vul` now sends through the contract. It is added on top,
  because it is a different mechanism from the ground a landslide took.
- **A damaged culvert or bridge** is replaced, at $15,000 a metre of span over
  a 5 m default, or cleared for $1,000 where a landslide only buried it (John
  Leeves, 2026-10-13); a claim's crossings are summed. Its value, the
  replacement cost, goes to the cap through the sub-cap.

The three site ratings are **proxies off exposure layers**, not measurements:
driveway length for construction access, ground slope for constructability, and
the inundated volume for earthworks. See :mod:`landloss.loss.pricing`, where
every band is defined and marked as invented.

**The Canterbury costs are 2010/2011 dollars**, brought to today's by
:data:`~landloss.loss.pricing.LIQ_COST_ESCALATION` (1.42) before GST is added,
so they sit beside land values and wall rates on one basis. The factor is a
placeholder, on instruction: the growth in the construction Labour Cost Index
since March 2011 (L-23), which follows pay rates but not plant or materials
(L-74).

What it runs over comes from ``config.py`` beside it.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.gst import add_gst
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_FAILURE_COLUMNS,
    LIQ_LD_COST_COLUMN,
    REALISATION_ID_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    RW_TYPE_COLUMN,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    LIQ_COST_ESCALATION,
    SIZE_CLASSES,
    SiteRatings,
    beta_wall_face_area_m2,
    beta_wall_height_m,
    beta_wall_repair_cost_incl_gst_nzd,
    classify_constructability,
    classify_construction_access,
    classify_inundation_earthworks,
    classify_landslide_wall_size,
    inundation_removal_cost_incl_gst_nzd,
    inundation_volume_m3,
    landslide_wall_length_m,
    professional_fees_incl_gst_nzd,
    replacement_rate_excl_gst_nzd_per_m2,
    timber_pole_rate_excl_gst_nzd_per_m2,
    wall_face_area_m2,
)
from landloss.loss.settlement import DamagedClaim, settle
from landloss.vul.loss_input import PARENT_RW_ID_COLUMN, WORLD_ID_COLUMN
from scripts.landloss.loss.steps.s0_land_cover_cap.s0_gen_land_cover_cap import (
    CAP_COLUMN,
    RW_UDV_COLUMN,
    land_cover_cap_path,
    load_qv_land_values,
    value_land,
)
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "loss"
OUT_STEM = "settlement"
EXPOSURE_DIR = TEMP_DIR / "exposure"

RULE = "-" * 72

# The four tables this reads, in the order the contract lists them.
LOSS_TABLES = ("land", "rw", "culverts", "bridges")

# Exposure layers the site rating proxies come off. Read rather than imported
# through a path function, because they belong to steps this module does not
# otherwise depend on.
DRIVEWAYS_STEM = "driveways"
TERRAIN_STEM = "terrain-by-address"
ADDRESS_TO_CLAIM_STEM = "address-to-claim"
DRIVEWAY_LENGTH_COLUMN = "driveway_length_m"
SLOPE_COLUMN = "slope_deg"
ADDRESS_ID_COLUMN = "address_id"

# What the step writes beyond the claim key.
ACCESS_COLUMN = "construction_access"
EARTHWORKS_COLUMN = "earthworks_required"
CONSTRUCTABILITY_COLUMN = "constructability_reinstatement"
WALL_REPAIR_COLUMN = "wall_repair_cost_incl_gst_nzd"
LAND_REPAIR_COLUMN = "land_repair_cost_incl_gst_nzd"
LIQ_REPAIR_COLUMN = "liquefaction_repair_cost_incl_gst_nzd"
CROSSING_REPAIR_COLUMN = loss_claims.CROSSING_REPAIR_COLUMN
# What the claim's damaged crossings are worth, which builds the cap through the
# sub-cap; written so the viewer can build the same cap.
CROSSING_UDV_COLUMN = loss_claims.CROSSING_UDV_COLUMN
SPOIL_REPAIR_COLUMN = "spoil_removal_cost_incl_gst_nzd"
SPOIL_VOLUME_COLUMN = "inundated_volume_m3"
FEES_COLUMN = "professional_fees_incl_gst_nzd"
REPAIR_COST_COLUMN = "repair_cost_incl_gst_nzd"
SETTLEMENT_COLUMN = "settlement_incl_gst_nzd"
EXCESS_COLUMN = "excess_nzd"
CAPPED_COLUMN = "capped"
SYNTHETIC_WALL_COLUMN = "land_repaired_by_new_wall"
# The shape of the wall invented to reinstate landslide ground, written out so
# that the damaged area and the wall it buys can be read side by side. Whether
# they look reasonable together is the check nobody can do on a cost alone.
LANDSLIDE_REPAIR_AREA_COLUMN = "landslide_damaged_area_m2"
NEW_WALL_SIZE_COLUMN = "new_wall_size"
NEW_WALL_HEIGHT_COLUMN = "new_wall_height_m"
NEW_WALL_LENGTH_COLUMN = "new_wall_length_m"
# A claim can have a new wall for each separate slip. The size is the largest,
# the height the tallest, the length and face summed, and the rate the bare
# square metre rate face-weighted over them, so face by rate is the claim's bare
# new wall cost, as for the replacement walls.
NEW_WALL_COUNT_COLUMN = "new_wall_count"
NEW_WALL_FACE_COLUMN = "new_wall_face_m2"
NEW_WALL_RATE_COLUMN = "new_wall_rate_excl_gst_nzd_per_m2"
# The shape a damaged wall is replaced at, which a landslide on the claim can
# make larger than the wall that was there -- never smaller. The rate is the
# one it was priced at, face-weighted over a claim's walls, so face by rate is
# the claim's bare wall cost.
REPLACEMENT_WALL_SIZE_COLUMN = "replacement_wall_size"
REPLACEMENT_WALL_LENGTH_COLUMN = "replacement_wall_length_m"
REPLACEMENT_WALL_FACE_COLUMN = "replacement_wall_face_m2"
REPLACEMENT_WALL_RATE_COLUMN = "replacement_wall_rate_excl_gst_nzd_per_m2"
WALL_ENLARGED_COLUMN = "wall_enlarged_for_landslide"


def settlement_path(world_id: int, realisation_id: int, *, extent: str) -> Path:
    """Return the file a run writes one world and realisation's settlements to.

    Args:
        world_id: The exposure world, one draw of the wall population.
        realisation_id: The modelled earthquake.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The path, under ``temp/loss``.
    """
    suffix = extent_suffix(extent)
    stem = f"{OUT_STEM}-w{world_id:03d}-r{realisation_id:03d}"
    return WORK_DIR / f"{stem}{suffix}.parquet"


def _exposure(stem: str, *, extent: str, geo: bool) -> pd.DataFrame:
    """Read one exposure layer, geoparquet or plain."""
    suffix = extent_suffix(extent)
    extension = "geoparquet" if geo else "parquet"
    path = EXPOSURE_DIR / f"{stem}{suffix}.{extension}"
    return gpd.read_parquet(path) if geo else pd.read_parquet(path)


def site_ratings_by_claim(land: pd.DataFrame, *, extent: str) -> pd.DataFrame:
    """Return the three site ratings for every claim, from the proxies.

    Construction access comes from the **longest** driveway on the claim and
    constructability from the **steepest** address on it, both taking the worst
    case where a claim has several. Earthworks comes from the inundated volume
    summed over the claim's polygons, which is the one rating with a basis in
    the contract rather than in a proxy.

    A claim with no driveway routed and no address matched rates easy on both
    proxies, which flatters it. Nothing distinguishes that from a genuinely
    easy site.

    Args:
        land: The contract's land table.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        A frame indexed by ``claim_id`` carrying the three ratings.
    """
    claim_ids = pd.Index(land[CLAIM_ID_COLUMN].unique(), name=CLAIM_ID_COLUMN)

    driveways = _exposure(DRIVEWAYS_STEM, extent=extent, geo=True)
    longest = driveways.groupby(CLAIM_ID_COLUMN)[DRIVEWAY_LENGTH_COLUMN].max()

    terrain = _exposure(TERRAIN_STEM, extent=extent, geo=True)
    to_claim = _exposure(ADDRESS_TO_CLAIM_STEM, extent=extent, geo=False)
    steepest = (
        terrain[[ADDRESS_ID_COLUMN, SLOPE_COLUMN]]
        .merge(to_claim, on=ADDRESS_ID_COLUMN)
        .groupby(CLAIM_ID_COLUMN)[SLOPE_COLUMN]
        .max()
    )

    volume = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)["volume"]
        .sum()
    )

    return pd.DataFrame(
        {
            ACCESS_COLUMN: classify_construction_access(
                longest.reindex(claim_ids).fillna(0.0).to_numpy()
            ),
            CONSTRUCTABILITY_COLUMN: classify_constructability(
                steepest.reindex(claim_ids).fillna(0.0).to_numpy()
            ),
            EARTHWORKS_COLUMN: classify_inundation_earthworks(
                volume.reindex(claim_ids).fillna(0.0).to_numpy()
            ),
        },
        index=claim_ids,
    )


def ratings_for(frame: pd.DataFrame, ratings: pd.DataFrame) -> SiteRatings:
    """Return the site ratings of each row's claim, aligned to the frame."""
    aligned = ratings.reindex(frame[CLAIM_ID_COLUMN].to_numpy())
    return SiteRatings(
        construction_access=aligned[ACCESS_COLUMN].to_numpy(),
        earthworks_required=aligned[EARTHWORKS_COLUMN].to_numpy(),
        constructability_reinstatement=aligned[CONSTRUCTABILITY_COLUMN].to_numpy(),
    )


def landslide_ground_by_claim(land: pd.DataFrame) -> pd.DataFrame:
    """Return the landslide ground each claim has to hold, and its spoil volume.

    The area is the landslide total, which `vul` has already unioned over the
    evacuated and inundated footprints -- so a claim whose slip evacuated ground
    outside the boundary, leaving no insured evacuated area, still has what was
    inundated inside it.

    Args:
        land: The contract's land table.

    Returns:
        A frame indexed by ``claim_id`` with ``area`` in square metres and
        ``volume`` in cubic metres.
    """
    per_claim = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "area": land[LANDSLIDE_AREA_COLUMN].fillna(0.0).to_numpy(),
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)[["area", "volume"]]
        .sum()
    )
    per_claim["area"] = per_claim["area"].clip(lower=0.0)
    return per_claim


def landslide_failures(land: pd.DataFrame) -> pd.DataFrame:
    """Return each separate landslide on each claim, and the wall it came with.

    `vul` lists the landslides that reached each insured land polygon
    (:data:`~landloss.domain.loss_contract.LANDSLIDE_FAILURE_COLUMNS`). A
    failure on two of a claim's polygons is one failure, its ground and spoil
    added. Its spoil volume is its own inundated area at its own depth.

    A land table from before the lists were written has one failure per claim,
    the claim's pooled ground, **unattributed**: no landslide id, no wall, held
    as the claim's ground was before (:func:`attach_failures_to_walls`).

    Args:
        land: The contract's land table.

    Returns:
        One row per claim and failure with landslide ground: ``claim_id``,
        ``landslide_id``, ``rw_id`` (missing where no wall failed with it),
        ``area`` in m2, ``volume`` in m3, and ``attributed``, false for the
        pooled ground of an older table.
    """
    columns = [
        CLAIM_ID_COLUMN,
        "landslide_id",
        RW_ID_COLUMN,
        "area",
        "volume",
        "attributed",
    ]
    if not all(column in land.columns for column in LANDSLIDE_FAILURE_COLUMNS):
        pooled = landslide_ground_by_claim(land).reset_index()
        pooled = pooled[pooled["area"] > 0]
        return pd.DataFrame(
            {
                CLAIM_ID_COLUMN: pooled[CLAIM_ID_COLUMN].to_numpy(),
                "landslide_id": None,
                RW_ID_COLUMN: None,
                "area": pooled["area"].to_numpy(dtype=float),
                "volume": pooled["volume"].to_numpy(dtype=float),
                "attributed": False,
            },
            columns=columns,
        )

    rows = []
    for record in land[[CLAIM_ID_COLUMN, *LANDSLIDE_FAILURE_COLUMNS]].itertuples(
        index=False
    ):
        claim, ids, walls, areas, inundated, depths = record
        rows.extend(
            {
                CLAIM_ID_COLUMN: claim,
                "landslide_id": failure,
                RW_ID_COLUMN: wall,
                "area": area,
                "inundated": wet,
                "depth": depth,
            }
            for failure, wall, area, wet, depth in zip(
                *(list(values) for values in (ids, walls, areas, inundated, depths)),
                strict=True,
            )
        )
    if not rows:
        return pd.DataFrame(columns=columns)
    pieces = pd.DataFrame(rows)
    pieces["area"] = pd.to_numeric(pieces["area"]).fillna(0.0)
    pieces["volume"] = inundation_volume_m3(
        pd.to_numeric(pieces["inundated"]).fillna(0.0).to_numpy(),
        pd.to_numeric(pieces["depth"]).fillna(0.0).to_numpy(),
    )
    # A wall id is a name, so an empty or missing one is no wall at all.
    pieces[RW_ID_COLUMN] = pieces[RW_ID_COLUMN].where(
        pieces[RW_ID_COLUMN].notna() & (pieces[RW_ID_COLUMN].astype(str) != ""), None
    )
    grouped = pieces.groupby([CLAIM_ID_COLUMN, "landslide_id"], sort=True)
    failures = grouped.agg(
        area=("area", "sum"),
        volume=("volume", "sum"),
        **{RW_ID_COLUMN: (RW_ID_COLUMN, "first")},
    ).reset_index()
    failures[RW_ID_COLUMN] = (
        failures[RW_ID_COLUMN]
        .astype(object)
        .where(failures[RW_ID_COLUMN].notna(), None)
    )
    failures["attributed"] = True
    failures = failures[failures["area"] > 0]
    return failures[columns].reset_index(drop=True)


def attach_failures_to_walls(
    failures: pd.DataFrame, damaged: pd.DataFrame
) -> np.ndarray:
    """Return which damaged wall holds each failure, by its row in ``damaged``.

    **A slip that came with a wall is held by that wall.** The failure names
    the whole wall (``rw_id``); the wall table names its piece on each property
    it crosses, and carries the whole wall as ``parent_rw_id`` -- so a slip is
    held by its wall's piece on the same claim. A wall table without
    ``parent_rw_id`` has no split walls, and each wall is its own parent.

    **The pooled ground of an older land table** is held by the claim's largest
    damaged wall by face area, as it always was, where the claim has one.

    Everything else -- a slip with no wall, or whose wall stood on another
    property -- is held by no damaged wall, and gets a new one.

    Args:
        failures: :func:`landslide_failures`.
        damaged: The damaged rows of the contract's retaining wall table.

    Returns:
        One position per failure into ``damaged`` (by row, from zero), or -1
        where no damaged wall holds it.
    """
    positions = np.full(len(failures), -1, dtype=int)
    if failures.empty or damaged.empty:
        return positions
    claims = damaged[CLAIM_ID_COLUMN].to_numpy(dtype=object)
    parents = (
        damaged[PARENT_RW_ID_COLUMN]
        if PARENT_RW_ID_COLUMN in damaged.columns
        else damaged[RW_ID_COLUMN]
    ).to_numpy(dtype=object)
    by_wall = {}
    for position, key in enumerate(zip(claims, parents, strict=True)):
        by_wall.setdefault(key, position)
    face = wall_face_area_m2(
        damaged[RW_HEIGHT_COLUMN].to_numpy(dtype=float),
        damaged[RW_LENGTH_COLUMN].to_numpy(dtype=float),
    )
    largest = (
        pd.Series(face).groupby(claims).idxmax().to_dict()
    )  # claim -> row of its largest wall

    for k, row in enumerate(failures.itertuples(index=False)):
        claim = getattr(row, CLAIM_ID_COLUMN)
        if not row.attributed:
            positions[k] = largest.get(claim, -1)
        elif pd.notna(getattr(row, RW_ID_COLUMN)):
            positions[k] = by_wall.get((claim, getattr(row, RW_ID_COLUMN)), -1)
    return positions


def replacement_wall_shape(
    damaged: pd.DataFrame, failures: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the size class, height and length each wall is replaced at.

    **A replacement is never smaller than the wall it replaces, but its slip
    can make it larger.** Where a wall holds a slip
    (:func:`attach_failures_to_walls`), the wall that slip would need is worked
    out exactly as for a slip with no wall -- :func:`classify_landslide_wall_size`
    and :func:`landslide_wall_length_m` -- and the replacement takes the
    **larger of the two in each dimension**: the larger size class, the taller
    height and the longer length. The wall keeps its own height unless the
    slip's size class sets a taller one (:func:`beta_wall_height_m`). Ground
    that needed a two-metre wall still does, and a slip wider than the wall it
    broke needs a wall that spans it.

    Each wall is sized against its own slips only; a slip elsewhere on the
    claim has its own wall. A wall that holds no slip is replaced as it was.

    Args:
        damaged: The damaged rows of the contract's retaining wall table.
        failures: :func:`landslide_failures`.

    Returns:
        The replacement size class, height and length, one each per row of
        ``damaged``, in its order.
    """
    size = damaged[RW_SIZE_COLUMN].str.lower().to_numpy(dtype=object)
    height = damaged[RW_HEIGHT_COLUMN].to_numpy(dtype=float).copy()
    length = damaged[RW_LENGTH_COLUMN].to_numpy(dtype=float).copy()

    position = attach_failures_to_walls(failures, damaged)
    held_by = failures.assign(_wall=position)
    held_by = held_by[held_by["_wall"] >= 0]
    slips = held_by.groupby("_wall")[["area", "volume"]].sum()
    area = slips["area"].reindex(range(len(damaged))).fillna(0.0).to_numpy()
    volume = slips["volume"].reindex(range(len(damaged))).fillna(0.0).to_numpy()
    held = area > 0
    if not held.any():
        return size, height, length

    rank = {name: order for order, name in enumerate(SIZE_CLASSES)}
    slip_size = classify_landslide_wall_size(area[held], volume[held])
    slip_length = landslide_wall_length_m(area[held])
    size[held] = [
        max(existing, slip, key=rank.__getitem__)
        for existing, slip in zip(size[held], slip_size, strict=True)
    ]
    height[held] = np.maximum(height[held], beta_wall_height_m(slip_size))
    length[held] = np.maximum(length[held], slip_length)
    return size, height, length


def wall_repair_by_claim(
    rw: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    failures: pd.DataFrame,
    policy: PolicySettings,
) -> pd.DataFrame:
    """Return each claim's cost of replacing the retaining walls that failed.

    Each wall is replaced at :func:`replacement_wall_shape` -- as it was, or
    larger where the slip it came with calls for more wall.

    A failed wall is rebuilt as a timber pole wall, on the pile its
    **replacement** height calls for, unless its type is rebuilt in kind
    (:data:`~landloss.loss.pricing.REPLACED_IN_KIND`, T-122): a brick wall goes
    back as timber pole, a concrete block wall as concrete block. So a 1.8 m
    wall enlarged to 2.75 m goes from the 250 mm to the 300 mm pile.
    Undepreciated value stays on the wall as it was, at its own type, in step 0,
    because that is what the property had.

    Args:
        rw: The contract's retaining wall table.
        ratings: The site ratings per claim.
        failures: :func:`landslide_failures`.
        policy: The settings this scenario runs under.

    Returns:
        A frame indexed by ``claim_id`` with the cost, the replacement's size
        class, length and face area, the square metre rate it was priced at
        (face-weighted where a claim has several walls, so face by rate is the
        claim's bare wall cost), and whether a slip enlarged it. A claim with no
        damaged wall does not appear.
    """
    damaged = loss_claims.damaged_walls(rw)
    if damaged.empty:
        return pd.DataFrame(
            columns=[
                WALL_REPAIR_COLUMN,
                REPLACEMENT_WALL_SIZE_COLUMN,
                REPLACEMENT_WALL_LENGTH_COLUMN,
                REPLACEMENT_WALL_FACE_COLUMN,
                REPLACEMENT_WALL_RATE_COLUMN,
                WALL_ENLARGED_COLUMN,
            ]
        )
    size, height, length = replacement_wall_shape(damaged, failures)
    face_area = wall_face_area_m2(height, length)
    rate = replacement_rate_excl_gst_nzd_per_m2(
        damaged[RW_TYPE_COLUMN].to_numpy(), height
    )
    cost = beta_wall_repair_cost_incl_gst_nzd(
        face_area,
        ratings=ratings_for(damaged, ratings),
        rate_excl_gst_nzd_per_m2=rate,
        policy=policy,
    )
    enlarged = (height > damaged[RW_HEIGHT_COLUMN].to_numpy(dtype=float)) | (
        length > damaged[RW_LENGTH_COLUMN].to_numpy(dtype=float)
    )
    rank = {name: order for order, name in enumerate(SIZE_CLASSES)}
    walls = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: damaged[CLAIM_ID_COLUMN].to_numpy(),
            "cost": cost,
            "size_rank": [rank[value] for value in size],
            "length": length,
            "face": face_area,
            "bare": face_area * rate,
            "enlarged": enlarged,
        }
    )
    grouped = walls.groupby(CLAIM_ID_COLUMN)
    face = grouped["face"].sum()
    return pd.DataFrame(
        {
            WALL_REPAIR_COLUMN: grouped["cost"].sum(),
            REPLACEMENT_WALL_SIZE_COLUMN: grouped["size_rank"]
            .max()
            .map(dict(enumerate(SIZE_CLASSES))),
            REPLACEMENT_WALL_LENGTH_COLUMN: grouped["length"].sum(),
            REPLACEMENT_WALL_FACE_COLUMN: face,
            REPLACEMENT_WALL_RATE_COLUMN: (grouped["bare"].sum() / face).where(
                face > 0, 0.0
            ),
            WALL_ENLARGED_COLUMN: grouped["enlarged"].any(),
        }
    )


def filled_wall_repair(wall_repair: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Return :func:`wall_repair_by_claim` over every claim, blanks filled.

    A claim with no damaged wall costs nothing, has no replacement, and was not
    enlarged.

    Args:
        wall_repair: :func:`wall_repair_by_claim`.
        index: Every claim being settled.

    Returns:
        The same columns, one row per claim in ``index``.
    """
    aligned = wall_repair.reindex(index)
    out = pd.DataFrame(index=index)
    for column in (
        WALL_REPAIR_COLUMN,
        REPLACEMENT_WALL_LENGTH_COLUMN,
        REPLACEMENT_WALL_FACE_COLUMN,
        REPLACEMENT_WALL_RATE_COLUMN,
    ):
        out[column] = aligned[column].astype(float).fillna(0.0)
    out[REPLACEMENT_WALL_SIZE_COLUMN] = aligned[REPLACEMENT_WALL_SIZE_COLUMN].fillna("")
    out[WALL_ENLARGED_COLUMN] = (
        aligned[WALL_ENLARGED_COLUMN].fillna(value=False).astype(bool)
    )
    return out


def land_repair_by_claim(
    land: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    failures: pd.DataFrame,
    rw: pd.DataFrame,
    policy: PolicySettings,
) -> pd.DataFrame:
    """Return the cost of holding the land landslides took, by claim.

    **Each slip no damaged wall holds gets a new wall of its own**
    (:func:`attach_failures_to_walls`), sized on its own ground: two separate
    slips on one property want two walls, and a slip at the back of a section
    is not held by the wall that failed at the front (T-124). A slip that came
    with a wall is held by that wall's replacement instead, sized against it in
    :func:`replacement_wall_shape`, and costs nothing here -- pricing both
    charged twice for one structure, once at $74,302 against a slip of 1.4
    square metres.

    Args:
        land: The contract's land table.
        ratings: The site ratings per claim.
        failures: :func:`landslide_failures`.
        rw: The contract's retaining wall table.
        policy: The settings this scenario runs under.

    Returns:
        A frame indexed by ``claim_id``: the cost, whether a wall was invented,
        the claim's landslide ground, and its new walls -- how many, the
        largest size class, the tallest height, the length and face summed and
        the face-weighted bare rate.
    """
    index = pd.Index(land[CLAIM_ID_COLUMN].unique(), name=CLAIM_ID_COLUMN)
    ground = landslide_ground_by_claim(land).reindex(index).fillna(0.0)
    out = pd.DataFrame(
        {
            LAND_REPAIR_COLUMN: 0.0,
            SYNTHETIC_WALL_COLUMN: False,
            LANDSLIDE_REPAIR_AREA_COLUMN: ground["area"],
            NEW_WALL_COUNT_COLUMN: 0,
            NEW_WALL_SIZE_COLUMN: "",
            NEW_WALL_HEIGHT_COLUMN: 0.0,
            NEW_WALL_LENGTH_COLUMN: 0.0,
            NEW_WALL_FACE_COLUMN: 0.0,
            NEW_WALL_RATE_COLUMN: 0.0,
        },
        index=index,
    )
    position = attach_failures_to_walls(failures, loss_claims.damaged_walls(rw))
    building = failures[position < 0].reset_index(drop=True)
    if building.empty:
        return out

    size = classify_landslide_wall_size(
        building["area"].to_numpy(), building["volume"].to_numpy()
    )
    length = landslide_wall_length_m(building["area"].to_numpy())
    height = beta_wall_height_m(size)
    face = beta_wall_face_area_m2(size, length)
    # An invented wall has no id of its own to take a construction from, so
    # it is always timber pole, on the pile its height calls for.
    rate = timber_pole_rate_excl_gst_nzd_per_m2(height)
    cost = beta_wall_repair_cost_incl_gst_nzd(
        face,
        ratings=ratings_for(building, ratings),
        rate_excl_gst_nzd_per_m2=rate,
        policy=policy,
    )
    rank = {name: order for order, name in enumerate(SIZE_CLASSES)}
    walls = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: building[CLAIM_ID_COLUMN].to_numpy(),
            "cost": cost,
            "size_rank": [rank[value] for value in size],
            "height": height,
            "length": length,
            "face": face,
            "bare": face * rate,
        }
    )
    grouped = walls.groupby(CLAIM_ID_COLUMN)
    built = grouped["face"].sum()
    claims = built.index
    out.loc[claims, LAND_REPAIR_COLUMN] = grouped["cost"].sum()
    out.loc[claims, SYNTHETIC_WALL_COLUMN] = True
    out.loc[claims, NEW_WALL_COUNT_COLUMN] = grouped.size()
    out.loc[claims, NEW_WALL_SIZE_COLUMN] = (
        grouped["size_rank"].max().map(dict(enumerate(SIZE_CLASSES)))
    )
    out.loc[claims, NEW_WALL_HEIGHT_COLUMN] = grouped["height"].max()
    out.loc[claims, NEW_WALL_LENGTH_COLUMN] = grouped["length"].sum()
    out.loc[claims, NEW_WALL_FACE_COLUMN] = built
    out.loc[claims, NEW_WALL_RATE_COLUMN] = (grouped["bare"].sum() / built).where(
        built > 0, 0.0
    )
    return out


def spoil_by_claim(land: pd.DataFrame) -> pd.Series:
    """Return the volume of landslide spoil on each claim.

    Args:
        land: The contract's land table.

    Returns:
        The volume per claim, indexed by ``claim_id``.
    """
    return (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)["volume"]
        .sum()
    )


def liquefaction_repair_by_claim(land: pd.DataFrame) -> pd.Series:
    """Return each claim's Canterbury settled cost, in today's dollars with GST.

    The contract carries the cost excluding GST, in 2010/2011 dollars. It is
    brought to today's by :data:`~landloss.loss.pricing.LIQ_COST_ESCALATION`, a
    placeholder from construction labour cost growth, and grossed up for GST.

    Args:
        land: The contract's land table.

    Returns:
        The cost per claim, indexed by ``claim_id``.
    """
    costs = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "cost": land[LIQ_LD_COST_COLUMN].fillna(0.0).to_numpy(),
            }
        )
        .groupby(CLAIM_ID_COLUMN)["cost"]
        .sum()
    )
    return add_gst(costs * LIQ_COST_ESCALATION)


def describe_ratings(claims):
    """Print how the proxies rated the population."""
    print(RULE)
    print("Site ratings, all three proxied and none measured:")
    for column, label in (
        (ACCESS_COLUMN, "construction access (driveway length)"),
        (CONSTRUCTABILITY_COLUMN, "constructability (ground slope)"),
        (EARTHWORKS_COLUMN, "earthworks (inundated volume)"),
    ):
        counts = claims[column].value_counts().reindex(["E", "M", "D"]).fillna(0)
        spread = ", ".join(f"{int(n):,} {r}" for r, n in counts.items())
        print(f"  {label}: {spread}")


def describe_repair(claims):
    """Print where the repair cost comes from."""
    print(RULE)
    invented = int(claims[SYNTHETIC_WALL_COLUMN].sum())
    print(f"Repair cost: {claims[REPAIR_COST_COLUMN].sum():,.0f} NZD including GST")
    for column, label in (
        (WALL_REPAIR_COLUMN, "replacing damaged retaining walls"),
        (LAND_REPAIR_COLUMN, "new walls to reinstate landslide ground"),
        (SPOIL_REPAIR_COLUMN, "clearing landslide spoil off the ground"),
        (FEES_COLUMN, "consent, design, engineering, H&S, PM and survey"),
        (
            LIQ_REPAIR_COLUMN,
            f"Canterbury liquefaction land costs, x{LIQ_COST_ESCALATION} to today",
        ),
        (CROSSING_REPAIR_COLUMN, "replacing or clearing culverts and bridges"),
    ):
        total = claims[column].sum()
        reached = int((claims[column] > 0).sum())
        print(f"  {total:>16,.0f} NZD  {label} ({reached:,} claims)")
    # A wall for each separate slip, so a claim can have a replaced wall for
    # the slip it came with and a new wall for another.
    both = int(
        ((claims[WALL_REPAIR_COLUMN] > 0) & (claims[LAND_REPAIR_COLUMN] > 0)).sum()
    )
    several = int((claims[NEW_WALL_COUNT_COLUMN] > 1).sum())
    enlarged = int(claims[WALL_ENLARGED_COLUMN].sum())
    print(
        f"  {int(claims[NEW_WALL_COUNT_COLUMN].sum()):,} new walls on {invented:,} "
        f"claims, {several:,} of them with more than one; {both:,} claims also "
        "replace a wall of their own, for a separate slip"
    )
    print(
        f"  {enlarged:,} replacements are built larger than the wall they "
        "replace, because the slip it came with needs more wall than was there"
    )


def describe_failures(failures, rw):
    """Print how many separate slips there are and what holds them."""
    print(RULE)
    if failures.empty:
        print("Landslides: none on any claim")
        return
    if not failures["attributed"].any():
        print(
            "Landslides: the land table lists no separate failures, so each "
            "claim's ground is pooled as one slip, as before (T-124)"
        )
        return
    held = attach_failures_to_walls(failures, loss_claims.damaged_walls(rw)) >= 0
    per_claim = failures.groupby(CLAIM_ID_COLUMN).size()
    print(
        f"Landslides: {len(failures):,} separate slips on {len(per_claim):,} "
        f"claims, {int((per_claim > 1).sum()):,} claims with more than one; "
        f"{int(held.sum()):,} came with a damaged wall that holds them, and "
        f"{int((~held).sum()):,} get a new wall"
    )


def describe_settlement(claims, policy):
    """Print what is paid, and which constraint bound."""
    print(RULE)
    paid = claims[claims[SETTLEMENT_COLUMN] > 0]
    print(
        f"Settlement: {claims[SETTLEMENT_COLUMN].sum():,.0f} NZD over "
        f"{len(paid):,} claims that are paid anything"
    )
    # `capped` is true of almost every claim with no damaged land, by
    # construction: there the cap is the wall's undepreciated value and the
    # repair cost is that same value times one plus the site multiplier, so the
    # cap is below it whenever the multiplier is above zero. Reporting the total
    # alone would read as a finding when it is an artefact, so the two are split.
    capped = claims[CAPPED_COLUMN]
    with_land = capped & (claims[loss_claims.DAMAGED_AREA_COLUMN] > 0)
    print(
        f"  {int(capped.sum()):,} claims settle at the land cover cap, but only "
        f"{int(with_land.sum()):,} of them have damaged land. On the rest the cap "
        "is the wall's value and the repair cost is that value plus the site "
        "multiplier, so capping is arithmetic rather than a result."
    )
    damaged = claims[REPAIR_COST_COLUMN] > 0
    zeroed = int((damaged & (claims[SETTLEMENT_COLUMN] == 0)).sum())
    if policy.excess_per_dwelling_nzd is not None:
        rule = f"{policy.excess_per_dwelling_nzd:,.0f} NZD per dwelling"
    else:
        rule = (
            f"{policy.excess_rate:.0%} of what was payable, floored at "
            f"{policy.excess_min_nzd:,.0f} NZD"
        )
    print(
        f"  {zeroed:,} claims have damage but pay nothing, the excess of "
        f"{rule} and capped at {policy.excess_max_nzd:,.0f} NZD having taken "
        "all of it"
    )


def check_cap_against_step_0(claims, world_id, realisation_id, *, extent):
    """Compare this step's cap with step 0's, which built it independently."""
    path = land_cover_cap_path(world_id, realisation_id, extent=extent)
    if not path.exists():
        print(f"  Step 0's caps are not on disk at {path}; cap not cross-checked")
        return
    theirs = pd.read_parquet(path).set_index(CLAIM_ID_COLUMN)[CAP_COLUMN]
    ours = claims["land_cover_cap_incl_gst_nzd"]
    gap = (ours - theirs.reindex(ours.index)).abs().max()
    print(f"  Cap agrees with step 0 to {gap:,.6f} NZD at worst")


def main(*, extent, world_ids, realisation_ids):
    """Settle every claim and write the result, per world and realisation.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: Which exposure worlds to settle.
        realisation_ids: Which modelled earthquakes to settle.
    """
    policy = PolicySettings()
    qv_values = load_qv_land_values(extent=extent)

    for world_id in world_ids:
        for realisation_id in realisation_ids:
            print(
                f"\nSettling world {world_id}, realisation {realisation_id} ...",
                flush=True,
            )
            tables = {
                name: gpd.read_parquet(
                    world_loss_input_path(name, world_id, realisation_id, extent=extent)
                )
                for name in LOSS_TABLES
            }
            land = value_land(tables["land"], qv_values)
            rw = tables["rw"]

            claims = loss_claims.land_by_claim(land)
            ratings = site_ratings_by_claim(land, extent=extent)
            claims = claims.join(ratings)

            # Each separate slip, and the wall it came with. A slip that came
            # with a wall is held by that wall's replacement, enlarged where the
            # slip needs more; every other slip gets a new wall of its own.
            failures = landslide_failures(land)
            describe_failures(failures, rw)

            claims = claims.join(
                filled_wall_repair(
                    wall_repair_by_claim(rw, ratings, failures=failures, policy=policy),
                    claims.index,
                )
            )
            land_repair = land_repair_by_claim(
                land,
                ratings,
                failures=failures,
                rw=rw,
                policy=policy,
            ).reindex(claims.index)
            claims[LAND_REPAIR_COLUMN] = land_repair[LAND_REPAIR_COLUMN].fillna(0.0)
            claims[SYNTHETIC_WALL_COLUMN] = (
                land_repair[SYNTHETIC_WALL_COLUMN].fillna(value=False).astype(bool)
            )
            claims[LANDSLIDE_REPAIR_AREA_COLUMN] = land_repair[
                LANDSLIDE_REPAIR_AREA_COLUMN
            ].fillna(0.0)
            claims[NEW_WALL_SIZE_COLUMN] = land_repair[NEW_WALL_SIZE_COLUMN].fillna("")
            claims[NEW_WALL_HEIGHT_COLUMN] = land_repair[NEW_WALL_HEIGHT_COLUMN].fillna(
                0.0
            )
            claims[NEW_WALL_LENGTH_COLUMN] = land_repair[NEW_WALL_LENGTH_COLUMN].fillna(
                0.0
            )
            claims[NEW_WALL_COUNT_COLUMN] = (
                land_repair[NEW_WALL_COUNT_COLUMN].fillna(0).astype(int)
            )
            for column in (NEW_WALL_FACE_COLUMN, NEW_WALL_RATE_COLUMN):
                claims[column] = land_repair[column].fillna(0.0)
            claims[LIQ_REPAIR_COLUMN] = (
                liquefaction_repair_by_claim(land).reindex(claims.index).fillna(0.0)
            )
            # Clearing the spoil is now its own line as well as setting the
            # earthworks rating, so a claim with buried ground and no wall is no
            # longer charged nothing for it.
            claims[SPOIL_VOLUME_COLUMN] = (
                spoil_by_claim(land).reindex(claims.index).fillna(0.0)
            )
            claims[SPOIL_REPAIR_COLUMN] = inundation_removal_cost_incl_gst_nzd(
                claims[SPOIL_VOLUME_COLUMN].to_numpy(), policy=policy
            )

            n_dwellings = loss_claims.dwelling_counts(
                claims.index.to_numpy(), claims.reset_index()
            )

            # Each damaged crossing is replaced, or cleared where a landslide
            # only buried it, and the claim's are summed. Its value, the
            # replacement cost, is what it brings to the cap, which step 0 built.
            caps = pd.read_parquet(
                land_cover_cap_path(world_id, realisation_id, extent=extent)
            )
            crossings = loss_claims.crossing_costs_by_claim(
                tables["culverts"], tables["bridges"], policy=policy
            ).reindex(claims.index)
            claims[CROSSING_REPAIR_COLUMN] = (
                crossings[loss_claims.CROSSING_REPAIR_COLUMN].fillna(0.0).astype(float)
            )
            crossing_udv = (
                crossings[loss_claims.CROSSING_UDV_COLUMN].fillna(0.0).to_numpy(float)
            )
            claims[CROSSING_UDV_COLUMN] = crossing_udv

            # Professional fees are charged once on a claim that **involves a
            # wall**, whether one that failed or one invented to reinstate ground.
            # A wall is the thing that gets designed, consented and supervised.
            # Clearing spoil on its own does not: no consent, no producer statement,
            # no survey. Nor does a Canterbury liquefaction cost, which is what NHC
            # settled rather than a works estimate, so it already stands for
            # everything that claim cost.
            # They are a share of what the walls cost to build, failed and
            # invented together, with the tool's fee total as the floor.
            wall_cost = claims[WALL_REPAIR_COLUMN] + claims[LAND_REPAIR_COLUMN]
            works = wall_cost > 0
            claims[FEES_COLUMN] = np.where(
                works,
                professional_fees_incl_gst_nzd(wall_cost.to_numpy(), policy=policy),
                0.0,
            )

            claims[REPAIR_COST_COLUMN] = (
                claims[WALL_REPAIR_COLUMN]
                + claims[LAND_REPAIR_COLUMN]
                + claims[SPOIL_REPAIR_COLUMN]
                + claims[FEES_COLUMN]
                + claims[LIQ_REPAIR_COLUMN]
                + claims[CROSSING_REPAIR_COLUMN]
            )

            # The invented wall is a remediation cost and never an asset, so the
            # undepreciated value handed to the cap is the real walls' alone, taken
            # from what step 0 priced.
            rw_udv = (
                caps.set_index(CLAIM_ID_COLUMN)[RW_UDV_COLUMN]
                .reindex(claims.index)
                .fillna(0.0)
                .to_numpy()
            )
            claims[RW_UDV_COLUMN] = rw_udv

            settlement = settle(
                DamagedClaim(
                    damaged_area_m2=claims[loss_claims.DAMAGED_AREA_COLUMN].to_numpy(),
                    land_rate_incl_gst_nzd_per_m2=claims[
                        loss_claims.LAND_RATE_COLUMN
                    ].to_numpy(),
                    repair_cost_incl_gst_nzd=claims[REPAIR_COST_COLUMN].to_numpy(),
                    n_dwellings=n_dwellings,
                    retaining_wall_udv_incl_gst_nzd=rw_udv,
                    bridge_culvert_udv_incl_gst_nzd=crossing_udv,
                ),
                policy=policy,
            )
            claims["land_cover_cap_incl_gst_nzd"] = settlement.land_cover_cap_nzd
            claims[EXCESS_COLUMN] = settlement.excess_nzd
            claims[SETTLEMENT_COLUMN] = settlement.settlement_nzd
            claims[CAPPED_COLUMN] = settlement.capped

            describe_ratings(claims)
            describe_repair(claims)
            describe_settlement(claims, policy)
            check_cap_against_step_0(claims, world_id, realisation_id, extent=extent)

            out = claims.reset_index()
            out.insert(0, REALISATION_ID_COLUMN, realisation_id)
            out.insert(1, WORLD_ID_COLUMN, world_id)
            out_path = settlement_path(world_id, realisation_id, extent=extent)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out.to_parquet(out_path)
            print(RULE)
            print(f"Wrote {len(out):,} claims to {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
