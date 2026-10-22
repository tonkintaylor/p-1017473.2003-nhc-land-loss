"""Settle each claim: the repair cost, the cap, and what NHC pays.

    uv run --frozen python src/scripts/landloss/loss/steps/s1_settlement/s1_gen_settlement.py

Step 0 builds the cap. This step builds the **other half of the comparison** and
calls :func:`~landloss.loss.settlement.settle`, which pays
``min(repair cost, cap)`` less the excess.

How each repair cost is arrived at, and every one of them rests on an
assumption named here:

- **A damaged retaining wall** is replaced, priced on its face area at the beta
  wall rate -- concrete for a share of walls, otherwise the timber pole rate its
  height calls for -- with the site multiplier on top. It keeps its own height
  and type, and is replaced over its damaged length plus 1 m at each end, at
  least 3 m, worked once per wall (2026-10-14).
- **Each landslide is held by its own wall** (T-124, 2026-10-13). `vul`
  lists the landslides that reached each polygon, and the retaining wall each
  failed with, if any:

  - **A slip that came with a wall** is held by that wall's replacement, at
    the wall's own height and type. A slip no longer enlarges it (2026-10-14).
  - **Every other slip that evacuated ground on the claim gets a new wall**
    that was never there, even on a claim whose own wall failed elsewhere: two
    separate failures want two walls. A slip that only buried the claim gets
    none: its deposit is cleared as land, and inundated ground alone needs no
    wall (2026-10-14). The new wall is **the mapped wall where there is one**
    (section 4 of the property damage tweaks): `vul` hands the face height of the
    wall unit the slip's polygon stands on and the length of that unit's stretch
    on the claim alongside the failure's evacuated ground, and the wall is built
    at that height over the length plus the margin, priced as timber pole on the
    pile its height calls for (the unit's own wall type is not used). Where no
    mapped wall can be used, or the land table does not list one, the wall is
    sized by how much ground the slip took -- by area, and by volume where an
    inundated depth makes one available -- with the same margin. It is a
    remediation cost, not an asset, so it reaches the repair cost and **never
    the cap**: a wall that did not exist has no undepreciated value to
    contribute.

  A land table from before the lists were written pools each claim's ground
  as one slip of unknown origin, held as before: by the claim's largest
  damaged wall, or by one new wall where it has none (2026-09-29).
- **Professional fees are charged once per claim that involves a wall** --
  consent, design, engineering, health and safety, project management and
  survey: 20% of what the claim's walls cost to build, never less than $8,000
  excluding GST (2026-10-12; the floor raised from the costing tool's own fee
  total, $5,100, on NHC's feedback, 2026-10-23). A wall is what
  gets designed and consented:
  clearing spoil on its own does not attract them, and neither does a Canterbury
  liquefaction cost, that being a settled amount rather than a works estimate.
- **The same claims carry the wall works' on-costs** (2026-10-13), each built
  on the one before: mobilisation and demobilisation at 15% of the walls and
  fees, never less than $5,000; then project management at 10% of the walls,
  fees, mobilisation and culverts and bridges, which a claim whose only works
  are a crossing carries too.
- **Every claim carries a 20% contingency on its whole repair** (2026-10-13):
  walls, spoil, fees, on-costs, liquefaction and crossings, applied last.
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
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    INUNDATED_MEAN_DEPTH_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_EVACUATED_AREAS_COLUMN,
    LANDSLIDE_FAILURE_COLUMNS,
    LANDSLIDE_WALL_HEIGHTS_COLUMN,
    LANDSLIDE_WALL_LENGTHS_COLUMN,
    LANDSLIDE_WALL_SOURCES_COLUMN,
    LIQ_LD_COST_COLUMN,
    MAPPED_WALL,
    REALISATION_ID_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    RW_TYPE_COLUMN,
    SLIP_WALL,
)
from landloss.exposure.rw.beta_population import classify_wall_size
from landloss.io.area_of_interest import extent_suffix
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    LIQ_COST_ESCALATION,
    SIZE_CLASSES,
    SiteRatings,
    beta_wall_height_m,
    beta_wall_repair_cost_incl_gst_nzd,
    classify_constructability,
    classify_construction_access,
    classify_inundation_earthworks,
    classify_landslide_wall_size,
    contingency_incl_gst_nzd,
    inundation_removal_cost_incl_gst_nzd,
    inundation_volume_m3,
    landslide_wall_length_m,
    margin_rule_length_m,
    on_costs_incl_gst_nzd,
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
MOB_DEMOB_COLUMN = "mob_demob_incl_gst_nzd"
PROJECT_MANAGEMENT_COLUMN = "project_management_incl_gst_nzd"
CONTINGENCY_COLUMN = "contingency_incl_gst_nzd"
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
# How many of them stand on a mapped wall rather than being sized from the slip
# (section 4), for the viewer to say.
NEW_WALL_FROM_MAPPED_COLUMN = "new_wall_from_mapped_count"
NEW_WALL_FACE_COLUMN = "new_wall_face_m2"
NEW_WALL_RATE_COLUMN = "new_wall_rate_excl_gst_nzd_per_m2"
# The shape a damaged wall is replaced at: its own height and type, over its
# damaged length plus the margin. The rate is the one it was priced at,
# face-weighted over a claim's walls, so face by rate is the claim's bare wall
# cost.
REPLACEMENT_WALL_SIZE_COLUMN = "replacement_wall_size"
REPLACEMENT_WALL_LENGTH_COLUMN = "replacement_wall_length_m"
REPLACEMENT_WALL_FACE_COLUMN = "replacement_wall_face_m2"
REPLACEMENT_WALL_RATE_COLUMN = "replacement_wall_rate_excl_gst_nzd_per_m2"


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

    volume = spoil_by_claim(land)

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

    The evacuated ground is the insured ground the slip removed, which the
    length of its wall is taken from. A land table without it measures the wall
    off the whole landslide ground, as before.

    Args:
        land: The contract's land table.

    Returns:
        A frame indexed by ``claim_id`` with ``area`` and ``evacuated`` in
        square metres and ``volume`` in cubic metres.
    """
    area = land[LANDSLIDE_AREA_COLUMN].fillna(0.0).to_numpy()
    evacuated = (
        land[EVACUATED_AREA_COLUMN].fillna(0.0).to_numpy()
        if EVACUATED_AREA_COLUMN in land.columns
        else area
    )
    per_claim = (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "area": area,
                "evacuated": evacuated,
                "volume": inundation_volume_m3(
                    land[INUNDATED_AREA_COLUMN].fillna(0.0).to_numpy(),
                    land[INUNDATED_MEAN_DEPTH_COLUMN].fillna(0.0).to_numpy(),
                ),
            }
        )
        .groupby(CLAIM_ID_COLUMN)[["area", "evacuated", "volume"]]
        .sum()
    )
    per_claim[["area", "evacuated"]] = per_claim[["area", "evacuated"]].clip(lower=0.0)
    return per_claim


def landslide_failures(land: pd.DataFrame) -> pd.DataFrame:
    """Return each separate landslide on each claim, and the wall it came with.

    `vul` lists the landslides that reached each insured land polygon
    (:data:`~landloss.domain.loss_contract.LANDSLIDE_FAILURE_COLUMNS`). A
    failure on two of a claim's polygons is one failure, its ground and spoil
    added. Its spoil volume is its own inundated area at its own depth, and its
    evacuated ground is what its wall's length is taken from. A land table
    without the evacuated list takes each failure's whole ground instead. The
    mapped wall each failure is built on, where `vul` listed one, is carried
    too: its height and length (a failure's entries on a claim's polygons
    added, the shared failure's 0 included) and its source.

    A land table from before the lists were written has one failure per claim,
    the claim's pooled ground, **unattributed**: no landslide id, no wall, held
    as the claim's ground was before (:func:`attach_failures_to_walls`).

    Args:
        land: The contract's land table.

    Returns:
        One row per claim and failure with landslide ground: ``claim_id``,
        ``landslide_id``, ``rw_id`` (missing where no wall failed with it),
        ``area`` and ``evacuated`` in m2, ``volume`` in m3, and
        ``attributed``, false for the pooled ground of an older table, and
        ``wall_height``, ``wall_length`` and ``wall_source`` (``mapped wall`` or
        ``slip``; ``slip`` and no height or length where the table lists none).
    """
    columns = [
        CLAIM_ID_COLUMN,
        "landslide_id",
        RW_ID_COLUMN,
        "area",
        "evacuated",
        "volume",
        "attributed",
        "wall_height",
        "wall_length",
        "wall_source",
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
                "evacuated": pooled["evacuated"].to_numpy(dtype=float),
                "volume": pooled["volume"].to_numpy(dtype=float),
                "attributed": False,
                "wall_height": np.nan,
                "wall_length": np.nan,
                "wall_source": SLIP_WALL,
            },
            columns=columns,
        )

    has_evacuated = LANDSLIDE_EVACUATED_AREAS_COLUMN in land.columns
    mapped_columns = [
        LANDSLIDE_WALL_HEIGHTS_COLUMN,
        LANDSLIDE_WALL_LENGTHS_COLUMN,
        LANDSLIDE_WALL_SOURCES_COLUMN,
    ]
    has_mapped = all(column in land.columns for column in mapped_columns)
    lists = [*LANDSLIDE_FAILURE_COLUMNS]
    if has_evacuated:
        lists.append(LANDSLIDE_EVACUATED_AREAS_COLUMN)
    if has_mapped:
        lists += mapped_columns
    rows = []
    for record in land[[CLAIM_ID_COLUMN, *lists]].itertuples(index=False):
        claim, ids, walls, areas, inundated, depths, *rest = record
        # An older table has no evacuated list: each failure's whole ground.
        evacuated = rest.pop(0) if has_evacuated else areas
        # A table without the mapped walls sizes every new wall from the slip.
        heights, lengths, sources = (
            rest
            if has_mapped
            else ([None] * len(ids), [None] * len(ids), [SLIP_WALL] * len(ids))
        )
        rows.extend(
            {
                CLAIM_ID_COLUMN: claim,
                "landslide_id": failure,
                RW_ID_COLUMN: wall,
                "area": area,
                "evacuated": evac,
                "inundated": wet,
                "depth": depth,
                "wall_height": height,
                "wall_length": length,
                "wall_source": source,
            }
            for failure, wall, area, evac, wet, depth, height, length, source in zip(
                *(
                    list(values)
                    for values in (
                        ids,
                        walls,
                        areas,
                        evacuated,
                        inundated,
                        depths,
                        heights,
                        lengths,
                        sources,
                    )
                ),
                strict=True,
            )
        )
    if not rows:
        return pd.DataFrame(columns=columns)
    pieces = pd.DataFrame(rows)
    pieces["area"] = pd.to_numeric(pieces["area"]).fillna(0.0)
    pieces["evacuated"] = pd.to_numeric(pieces["evacuated"]).fillna(0.0)
    pieces["wall_height"] = pd.to_numeric(pieces["wall_height"])
    pieces["wall_length"] = pd.to_numeric(pieces["wall_length"])
    pieces["wall_source"] = pieces["wall_source"].where(
        pieces["wall_source"] == MAPPED_WALL, SLIP_WALL
    )
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
        evacuated=("evacuated", "sum"),
        volume=("volume", "sum"),
        wall_height=("wall_height", "max"),
        wall_length=("wall_length", lambda lengths: lengths.sum(min_count=1)),
        wall_source=("wall_source", "first"),
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
    damaged: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the size class, height and length each wall is replaced at.

    **A replacement keeps the wall's own size class, height and type, and takes
    its length from the margin rule** (2026-10-14), not from the slip it came
    with. The length is worked **per wall, not per piece**
    (:func:`~landloss.loss.claims.wall_lengths_by_piece`): the sum of the
    wall's damaged lengths plus 1 m at each end, at least 3 m, shared over its
    pieces in proportion to their damaged length. So a wall shared by two
    claims gets the margin once, a wall that failed whole is replaced over its
    length plus the margin, and a wall clipped by a neighbour's slip is
    replaced over the clipped length plus the margin. A replacement can be
    narrower than the slip it came with: the wall sits where the ground needs
    it. The damaged length of a piece is ``rw_damaged_length`` where the table
    carries one, else its whole length.

    Args:
        damaged: The damaged rows of the contract's retaining wall table.

    Returns:
        The replacement size class, height and length, one each per row of
        ``damaged``, in its order.
    """
    size = damaged[RW_SIZE_COLUMN].str.lower().to_numpy(dtype=object)
    height = damaged[RW_HEIGHT_COLUMN].to_numpy(dtype=float).copy()
    length = loss_claims.wall_lengths_by_piece(damaged)[
        loss_claims.REPLACED_LENGTH_COLUMN
    ].to_numpy()
    return size, height, length


def wall_repair_by_claim(
    rw: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    policy: PolicySettings,
) -> pd.DataFrame:
    """Return each claim's cost of replacing the retaining walls that failed.

    Each wall is replaced at :func:`replacement_wall_shape` -- at its own
    height and type, over its damaged length plus the margin.

    A failed wall is rebuilt as a timber pole wall, on the pile its height calls
    for, unless its type is rebuilt in kind
    (:data:`~landloss.loss.pricing.REPLACED_IN_KIND`, T-122): a brick wall goes
    back as timber pole, a concrete block wall as concrete block. Undepreciated
    value stays on the wall as it was, at its own type, in step 0, because that
    is what the property had.

    Args:
        rw: The contract's retaining wall table.
        ratings: The site ratings per claim.
        policy: The settings this scenario runs under.

    Returns:
        A frame indexed by ``claim_id`` with the cost, the replacement's size
        class, length and face area, and the square metre rate it was priced at
        (face-weighted where a claim has several walls, so face by rate is the
        claim's bare wall cost). A claim with no damaged wall does not
        appear.
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
            ]
        )
    size, height, length = replacement_wall_shape(damaged)
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
    rank = {name: order for order, name in enumerate(SIZE_CLASSES)}
    walls = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: damaged[CLAIM_ID_COLUMN].to_numpy(),
            "cost": cost,
            "size_rank": [rank[value] for value in size],
            "length": length,
            "face": face_area,
            "bare": face_area * rate,
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
        }
    )


def filled_wall_repair(wall_repair: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Return :func:`wall_repair_by_claim` over every claim, blanks filled.

    A claim with no damaged wall costs nothing and has no replacement.

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
    (:func:`attach_failures_to_walls`): two separate slips on one property want
    two walls, and a slip at the back of a section is not held by the wall that
    failed at the front (T-124). A slip that came with a wall is held by that
    wall's replacement instead, sized by the margin rule in
    :func:`replacement_wall_shape`, and costs nothing here -- pricing both
    charged twice for one structure, once at $74,302 against a slip of 1.4
    square metres.

    **A slip that evacuated no ground on the claim gets no wall**
    (2026-10-14): buried ground needs clearing, which the spoil line prices, and
    no wall. A land table without the evacuated list measures each failure's
    whole ground as its evacuated ground, so an older table still builds one.

    **A new wall is built on the mapped wall where `vul` listed one**: at the
    mapped unit's height, over the length alongside the failure's evacuated
    ground and the margin rule's 1 m at each end, at least 3 m, as timber pole on
    the pile that height calls for (the unit's own type is not used). A
    mapped failure with no length of its own shares the wall another failure on
    its unit and claim has, and builds none. Any other failure, or a table
    without the lists, is sized on the slip's own ground, by its size class
    and the same margin rule.

    Args:
        land: The contract's land table.
        ratings: The site ratings per claim.
        failures: :func:`landslide_failures`.
        rw: The contract's retaining wall table.
        policy: The settings this scenario runs under.

    Returns:
        A frame indexed by ``claim_id``: the cost, whether a wall was invented,
        the claim's landslide ground, and its new walls -- how many, how many of
        them stand on a mapped wall, the largest size class, the tallest
        height, the length and face summed and the face-weighted bare rate.
    """
    index = pd.Index(land[CLAIM_ID_COLUMN].unique(), name=CLAIM_ID_COLUMN)
    ground = landslide_ground_by_claim(land).reindex(index).fillna(0.0)
    out = pd.DataFrame(
        {
            LAND_REPAIR_COLUMN: 0.0,
            SYNTHETIC_WALL_COLUMN: False,
            LANDSLIDE_REPAIR_AREA_COLUMN: ground["area"],
            NEW_WALL_COUNT_COLUMN: 0,
            NEW_WALL_FROM_MAPPED_COLUMN: 0,
            NEW_WALL_SIZE_COLUMN: "",
            NEW_WALL_HEIGHT_COLUMN: 0.0,
            NEW_WALL_LENGTH_COLUMN: 0.0,
            NEW_WALL_FACE_COLUMN: 0.0,
            NEW_WALL_RATE_COLUMN: 0.0,
        },
        index=index,
    )
    position = attach_failures_to_walls(failures, loss_claims.damaged_walls(rw))
    mapped = (failures["wall_source"] == MAPPED_WALL).to_numpy()
    # A mapped failure with no length of its own is built on another failure's
    # wall, on the same unit and claim.
    shares = mapped & (failures["wall_length"].fillna(0.0) <= 0.0).to_numpy()
    wanted = (position < 0) & (failures["evacuated"] > 0).to_numpy() & ~shares
    building = failures[wanted].reset_index(drop=True)
    if building.empty:
        return out

    from_mapped = (building["wall_source"] == MAPPED_WALL).to_numpy()
    slip_size = classify_landslide_wall_size(
        building["area"].to_numpy(), building["volume"].to_numpy()
    )
    slip_height = beta_wall_height_m(slip_size)
    slip_length = landslide_wall_length_m(building["evacuated"].to_numpy())
    mapped_height = building["wall_height"].fillna(0.0).to_numpy(dtype=float)
    mapped_length = margin_rule_length_m(building["wall_length"].fillna(0.0).to_numpy())
    height = np.where(from_mapped, mapped_height, slip_height)
    length = np.where(from_mapped, mapped_length, slip_length)
    size = np.where(from_mapped, classify_wall_size(mapped_height), slip_size)
    face = wall_face_area_m2(height, length)
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
            "mapped": from_mapped,
        }
    )
    grouped = walls.groupby(CLAIM_ID_COLUMN)
    built = grouped["face"].sum()
    claims = built.index
    out.loc[claims, LAND_REPAIR_COLUMN] = grouped["cost"].sum()
    out.loc[claims, SYNTHETIC_WALL_COLUMN] = True
    out.loc[claims, NEW_WALL_COUNT_COLUMN] = grouped.size()
    out.loc[claims, NEW_WALL_FROM_MAPPED_COLUMN] = grouped["mapped"].sum()
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

    **Each failure's spoil is added** (the lead, 2026-10-14): its own inundated
    area at its own depth (:func:`landslide_failures`), so two deposits on the
    same ground are both cleared. The area a claim is damaged over stays the
    union, which vul measures. A land table from before the failure lists
    takes the pooled volume, the inundated union at its mean depth.

    Args:
        land: The contract's land table.

    Returns:
        The volume per claim, indexed by ``claim_id``.
    """
    return landslide_failures(land).groupby(CLAIM_ID_COLUMN)["volume"].sum()


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
        (MOB_DEMOB_COLUMN, "mob/demob (15% of walls and fees, min $5,000)"),
        (
            PROJECT_MANAGEMENT_COLUMN,
            "project management (10% of walls, fees, mob/demob and crossings)",
        ),
        (
            LIQ_REPAIR_COLUMN,
            f"Canterbury liquefaction land costs, x{LIQ_COST_ESCALATION} to today",
        ),
        (CROSSING_REPAIR_COLUMN, "replacing or clearing culverts and bridges"),
        (CONTINGENCY_COLUMN, "contingency (20% of the whole repair)"),
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
    print(
        f"  {int(claims[NEW_WALL_COUNT_COLUMN].sum()):,} new walls on {invented:,} "
        f"claims, {several:,} of them with more than one; "
        f"{int(claims[NEW_WALL_FROM_MAPPED_COLUMN].sum()):,} stand on a mapped "
        f"wall and the rest are sized from the slip; {both:,} claims also "
        "replace a wall of their own, for a separate slip"
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
    buried = ~held & ~(failures["evacuated"] > 0).to_numpy()
    mapped = (failures["wall_source"] == MAPPED_WALL).to_numpy()
    shares = mapped & (failures["wall_length"].fillna(0.0) <= 0.0).to_numpy()
    builds = ~held & ~buried & ~shares
    print(
        f"Landslides: {len(failures):,} separate slips on {len(per_claim):,} "
        f"claims, {int((per_claim > 1).sum()):,} claims with more than one; "
        f"{int(held.sum()):,} came with a damaged wall that holds them, "
        f"{int(buried.sum()):,} only buried the claim (cleared, no wall), "
        f"{int((~held & ~buried & shares).sum()):,} stand on a mapped wall "
        f"another slip builds and {int(builds.sum()):,} get a new wall"
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
            # with a wall is held by that wall's replacement; every other slip
            # gets a new wall of its own.
            failures = landslide_failures(land)
            describe_failures(failures, rw)

            claims = claims.join(
                filled_wall_repair(
                    wall_repair_by_claim(rw, ratings, policy=policy),
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
            for column in (NEW_WALL_COUNT_COLUMN, NEW_WALL_FROM_MAPPED_COLUMN):
                claims[column] = land_repair[column].fillna(0).astype(int)
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
            # Mobilisation falls on the claims with wall works, as the fees do;
            # project management on those and on any claim with a crossing.
            on_costs = on_costs_incl_gst_nzd(
                wall_cost.to_numpy(),
                claims[FEES_COLUMN].to_numpy(),
                claims[CROSSING_REPAIR_COLUMN].to_numpy(),
                policy=policy,
            )
            claims[MOB_DEMOB_COLUMN] = on_costs.mob_demob
            claims[PROJECT_MANAGEMENT_COLUMN] = on_costs.project_management

            # The contingency goes on the whole repair, last, on every claim.
            before_contingency = (
                claims[WALL_REPAIR_COLUMN]
                + claims[LAND_REPAIR_COLUMN]
                + claims[SPOIL_REPAIR_COLUMN]
                + claims[FEES_COLUMN]
                + claims[MOB_DEMOB_COLUMN]
                + claims[PROJECT_MANAGEMENT_COLUMN]
                + claims[LIQ_REPAIR_COLUMN]
                + claims[CROSSING_REPAIR_COLUMN]
            )
            claims[CONTINGENCY_COLUMN] = contingency_incl_gst_nzd(
                before_contingency.to_numpy()
            )
            claims[REPAIR_COST_COLUMN] = before_contingency + claims[CONTINGENCY_COLUMN]

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
