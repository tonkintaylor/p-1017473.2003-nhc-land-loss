"""Write the one CSV the static loss viewer reads, and put the viewer beside it.

    uv run --frozen python src/scripts/landloss/loss/ui/gen_viewer_data.py

The viewer is `loss_viewer.html`, a single page with no server and no build
step: open it, drag the CSV on, and it settles every claim in the browser. The
point is that **the policy settings are controls rather than constants**, so
somebody at NHC can move the excess or the total cap and watch the portfolio
answer, without Python, a spreadsheet, or anyone to run it for them. Two
scenarios are two CSVs dragged onto the same page.

**What the CSV carries is everything the settlement does not decide.** Areas,
rates, wall geometry, the Canterbury cost, who has what damage -- all fixed by
exposure and vul. What it deliberately leaves out is every figure the Act sets:
the caps, the sub-caps, the excess, the fees, the specification uplift. Most
are the page's controls, so a number that moves when a control moves is not in
this file; the professional fees, the wall works' on-costs and the spoil removal
rate are fixed on the page rather than offered as controls. GST is
not a control either: the page works wholly excluding GST (2026-10-12), backing
it out of the land rate, while the module settles GST-inclusive as the Act
compares; :func:`settled_in_python` checks the two agree at the module's rate.
The page also scales the wall rates and the land value, to show how far an
answer leans on them; at a scale of one each, it is the module's answer, less
GST.

The land cap scenarios NHC is weighing are drawn over the main histogram, with
the share of claims above each cap and the total settled under it. Those are
the page's own arithmetic over the same rows, not something this file carries.

That split is also what keeps the page honest. It cannot show a settlement that
the module would not produce, because it is running the same arithmetic on the
same inputs -- and `check_viewer_against_the_model` proves it, at the default
settings, before the file is written.
"""

import subprocess
import sys
from datetime import UTC, datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from landloss.domain.gst import GST_RATE
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    IMMINENT_EVACUATED_AREA_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_FAILURE_COLUMNS,
    LIQ_LD_STATE_COLUMN,
    REINUNDATED_AREA_COLUMN,
    REINUNDATED_VOLUME_COLUMN,
    RW_HEIGHT_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
)
from landloss.hazard.landslide.urban.realisation import FAILED_WITH_POLYGON
from landloss.hazard.liquefaction.land_damage import LD_STATES
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3,
    LIQ_COST_ESCALATION,
    PROFESSIONAL_FEES_SHARE,
    PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD,
    RATING_MARKUP,
    contingency_incl_gst_nzd,
    on_costs_incl_gst_nzd,
)
from landloss.vul.loss_input import PARENT_RW_ID_COLUMN
from scripts.landloss.loss.steps.s0_land_cover_cap.s0_gen_land_cover_cap import (
    wall_udv_by_claim,
)
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    ACCESS_COLUMN,
    CONSTRUCTABILITY_COLUMN,
    CROSSING_REPAIR_COLUMN,
    CROSSING_UDV_COLUMN,
    EARTHWORKS_COLUMN,
    LAND_REPAIR_COLUMN,
    LIQ_REPAIR_COLUMN,
    NEW_WALL_COUNT_COLUMN,
    NEW_WALL_FACE_COLUMN,
    NEW_WALL_FROM_MAPPED_COLUMN,
    NEW_WALL_RATE_COLUMN,
    REPLACEMENT_WALL_FACE_COLUMN,
    REPLACEMENT_WALL_RATE_COLUMN,
    SPOIL_VOLUME_COLUMN,
    WALL_REPAIR_COLUMN,
    attach_failures_to_walls,
    landslide_failures,
    settlement_path,
)
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import (
    gen_landslide_land_damage as landslide_land,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import (
    gen_wall_landslide_damage as wall_landslide,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    config as liq_config,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    gen_liq_land_damage as liq_land,
)
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = REPORT_DIR / "loss" / "viewer"
VIEWER = "loss_viewer.html"
HERE = __import__("pathlib").Path(__file__).resolve().parent
# Where the page shows its version; the copy written beside the CSVs has it
# replaced (write_viewer).
VERSION_PLACEHOLDER = "__VIEWER_VERSION__"
# The liquefaction land damage state that is no damage at all: "None", the
# first of LD_STATES, numbered from one. A property drawn in it still carries
# the Canterbury cost for it -- an average with non-claimants in at $0 -- but
# has nothing to claim for.
NO_DAMAGE_LIQ_STATE = LD_STATES.index("None") + 1
# How the settled liquefaction cost was priced, as the page names it. Vul step
# 10 hands loss one or the other, and which depends on the code vul ran on, not
# on this script, so it is read off the data (liquefaction_method).
LOOKUP_METHOD = "Canterbury cost per damage state"
AREA_METHOD = "Priced from the ground lost, at rates fitted to claimant-only costs"


def claim_points(world_id: int, realisation_id: int, *, extent: str) -> pd.DataFrame:
    """Return each claim's position in degrees, for the map.

    The insured land is a polygon; the viewer wants a dot, so this takes a
    point guaranteed to sit inside it rather than a centroid, which on an
    L-shaped section can fall outside the property altogether.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        ``lon`` and ``lat`` per claim.
    """
    land = gpd.read_parquet(
        world_loss_input_path("land", world_id, realisation_id, extent=extent)
    )
    inside = land.geometry.representative_point()
    degrees = gpd.GeoSeries(inside, crs=land.crs).to_crs(4326)
    return (
        pd.DataFrame(
            {
                CLAIM_ID_COLUMN: land[CLAIM_ID_COLUMN].to_numpy(),
                "lon": degrees.x.to_numpy().round(6),
                "lat": degrees.y.to_numpy().round(6),
            }
        )
        .groupby(CLAIM_ID_COLUMN)
        .first()
    )


def liquefaction_ejecta(realisation_id: int, *, extent: str) -> pd.DataFrame:
    """Return the part of each claim's liquefaction cost that is clearing ejecta.

    So the page can switch the Student Volunteer Army on and off without the
    model being rerun: it takes out the part the run priced and puts in the
    part with or without volunteers. 2010/2011 dollars excluding GST, as the
    liquefaction cost the CSV carries. A step 2 run from before the parts were
    written gives none, and the page's switch then changes nothing.

    Args:
        realisation_id: The modelled earthquake.
        extent: The extent the run is over.

    Returns:
        Indexed by claim id: the clearing cost as the run priced it, with
        volunteers and without, and whether the run had them.
    """
    damage = pd.read_parquet(
        liq_land.liq_land_damage_path(realisation_id, extent=extent)
    )
    columns = {
        "liq_inundated_cost_excl_gst": liq_land.INUNDATED_COST_COLUMN,
        "liq_inundated_cost_sva_excl_gst": liq_land.INUNDATED_COST_SVA_COLUMN,
        "liq_inundated_cost_no_sva_excl_gst": liq_land.INUNDATED_COST_NO_SVA_COLUMN,
    }
    if not set(columns.values()) <= set(damage.columns):
        return pd.DataFrame(columns=[*columns, "liq_sva"])
    grouped = damage.groupby(CLAIM_ID_COLUMN)
    out = pd.DataFrame(
        {name: grouped[source].sum() for name, source in columns.items()}
    )
    out["liq_sva"] = grouped[liq_land.SVA_COLUMN].first().astype(int)
    return out


def liquefaction_states(
    world_id: int, realisation_id: int, *, extent: str
) -> pd.Series:
    """Return each claim's liquefaction land damage state, 0 where it has none.

    Sloping land has no state at all, because the liquefaction model covers
    flat land only. Where a claim has more than one land row, its worst state.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The state per claim, 1 (None) to 6 (Very severe), or 0.
    """
    land = pd.read_parquet(
        world_loss_input_path("land", world_id, realisation_id, extent=extent),
        columns=[CLAIM_ID_COLUMN, LIQ_LD_STATE_COLUMN],
    )
    return (
        land[LIQ_LD_STATE_COLUMN]
        .fillna(0)
        .astype(int)
        .groupby(land[CLAIM_ID_COLUMN])
        .max()
    )


def read_loss_input(path, columns: list[str]) -> pd.DataFrame:
    """Read the given columns of a loss input table, geometry aside.

    Args:
        path: The loss input parquet file.
        columns: The columns to read, all required.

    Returns:
        The table with just those columns.

    Raises:
        ValueError: If the file lacks any of the columns.
    """
    missing = [c for c in columns if c not in pq.read_schema(path).names]
    if missing:
        msg = f"{path} has no columns {missing}: rerun vul step 10 (gen_property_damage.py)"
        raise ValueError(msg)
    return pd.read_parquet(path, columns=columns)


def landslide_by_origin(land: pd.DataFrame, rw: pd.DataFrame) -> pd.DataFrame:
    """Split each claim's landslide ground by whether its own wall brought it down.

    A failure is the claim's own wall's when one of the claim's damaged walls
    holds it (:func:`attach_failures_to_walls`, the rule settlement uses to
    decide which slips get a new wall); otherwise it is another's, a
    neighbour's wall or a slope with no wall.

    Args:
        land: The loss input's land table, with the per-failure lists (T-124).
        rw: The loss input's retaining wall table: claim, wall and parent wall
            ids, height, length and the damage flags.

    Returns:
        ``wall_landslide_m2`` and ``other_landslide_m2`` per claim with any
        landslide ground. The wall ground is capped at the claim's pooled
        landslide ground, because two failures that buried the same ground each
        count it.

    Raises:
        ValueError: If the land table lacks any of the per-failure lists.
    """
    missing = [c for c in LANDSLIDE_FAILURE_COLUMNS if c not in land.columns]
    if missing:
        msg = (
            f"The land table has no per-failure lists {missing}: rerun vul "
            "step 10 (gen_property_damage.py)"
        )
        raise ValueError(msg)
    failures = landslide_failures(land)
    damaged = loss_claims.damaged_walls(rw).reset_index(drop=True)
    held = attach_failures_to_walls(failures, damaged) >= 0
    wall = failures[held].groupby(CLAIM_ID_COLUMN)["area"].sum()
    other = failures[~held].groupby(CLAIM_ID_COLUMN)["area"].sum()
    pooled = land.groupby(CLAIM_ID_COLUMN)[LANDSLIDE_AREA_COLUMN].sum()
    claims = wall.index.union(other.index)
    origin = pd.DataFrame(
        {
            "wall_landslide_m2": wall.reindex(claims, fill_value=0.0),
            "other_landslide_m2": other.reindex(claims, fill_value=0.0),
        }
    ).astype(float)
    origin["wall_landslide_m2"] = np.minimum(
        origin["wall_landslide_m2"], pooled.reindex(claims).fillna(0.0)
    )
    return origin


# What the page adds for imminent ground, per claim: the land table's column and
# the CSV's, in the order of the contract's IMMINENT_LAND_COLUMNS it is read from.
IMMINENT_VIEWER_COLUMNS = {
    IMMINENT_EVACUATED_AREA_COLUMN: "imminent_evacuated_m2",
    REINUNDATED_AREA_COLUMN: "reinundated_m2",
    REINUNDATED_VOLUME_COLUMN: "reinundated_m3",
}


def imminent_by_claim(path) -> pd.DataFrame:
    """Return each claim's imminent evacuated and re-inundated ground and volume.

    Imminent ground is not settled (loss does not price it), so it is carried
    apart from the damaged ground for the page to add (T-127). The land table
    holds it as optional extra columns, so one written before them gives none.

    Args:
        path: The loss input's land table.

    Returns:
        ``imminent_evacuated_m2``, ``reinundated_m2`` and ``reinundated_m3``
        per claim, summed over its polygons; empty, with those columns, when the
        table has none of them.
    """
    names = pq.read_schema(path).names
    present = [column for column in IMMINENT_VIEWER_COLUMNS if column in names]
    if not present:
        return pd.DataFrame(columns=list(IMMINENT_VIEWER_COLUMNS.values()), dtype=float)
    land = pd.read_parquet(path, columns=[CLAIM_ID_COLUMN, *present])
    by_claim = land.groupby(CLAIM_ID_COLUMN)[present].sum()
    return by_claim.rename(columns=IMMINENT_VIEWER_COLUMNS).reindex(
        columns=list(IMMINENT_VIEWER_COLUMNS.values()), fill_value=0.0
    )


def damaged_land(world_id: int, realisation_id: int, *, extent: str) -> pd.DataFrame:
    """Return each claim's evacuated and inundated land, and what caused it.

    The loss input carries one damaged area per claim, which is all settlement
    needs; the page also shows how it splits (T-123), read here from the vul
    tables the loss input was built from. The two are not additive: where the
    ground was both evacuated and inundated it counts in each.

    The cause names liquefaction, landslide, retaining wall failure, or a
    combination, without areas per cause. A claim's wall failure is a wall on it
    that failed and brought ground down with it, or any landslide ground that
    came down with one of its own damaged walls (T-124). Landslide is ground
    from a failure none of its own damaged walls came with, whether a
    neighbour's wall or a slope with no wall.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        ``evacuated_m2``, ``inundated_m2``, ``cause``, ``has_landslide``,
        ``wall_landslide_m2``, ``imminent_evacuated_m2``, ``reinundated_m2`` and
        ``reinundated_m3`` per claim that has any. ``wall_landslide_m2`` is the
        ground that came down with the claim's own walls, summed over failures
        and capped at the claim's landslide ground; it is not additive with
        ``evacuated_m2`` or ``inundated_m2``. The imminent evacuated ground is
        apart from both, the re-inundated ground is the same footprint as
        ground already inundated, and its volume is area by depth; none is
        settled in Python and zeros stand for a land table written before them
        (T-127).

    Raises:
        ValueError: If the loss input's land or wall table lacks a column read
            here, such as the per-failure lists (rerun vul step 10).
    """
    areas = ["evacuated_area_m2", "inundated_area_m2"]
    liq = pd.read_parquet(
        liq_land.liq_land_damage_path(realisation_id, extent=extent),
        columns=[CLAIM_ID_COLUMN, "ld_state", *areas],
    )
    # Only a claimed state worse than None has ground to show.
    liq = liq[liq["ld_state"].fillna(0) > NO_DAMAGE_LIQ_STATE]
    slid = pd.read_parquet(
        landslide_land.landslide_land_damage_path(
            world_id, realisation_id, extent=extent
        ),
        columns=[CLAIM_ID_COLUMN, *areas],
    )
    walls = pd.read_parquet(
        wall_landslide.wall_landslide_damage_path(
            world_id, realisation_id, extent=extent
        ),
        columns=[CLAIM_ID_COLUMN, "outcome"],
    )
    land_path = world_loss_input_path("land", world_id, realisation_id, extent=extent)
    land_in = read_loss_input(
        land_path,
        [CLAIM_ID_COLUMN, LANDSLIDE_AREA_COLUMN, *LANDSLIDE_FAILURE_COLUMNS],
    )
    imminent = imminent_by_claim(land_path)
    rw_in = read_loss_input(
        world_loss_input_path("rw", world_id, realisation_id, extent=extent),
        [
            CLAIM_ID_COLUMN,
            RW_ID_COLUMN,
            PARENT_RW_ID_COLUMN,
            RW_HEIGHT_COLUMN,
            RW_LENGTH_COLUMN,
            IS_DAMAGED_BY_SHAKING_COLUMN,
            IS_EVACUATED_COLUMN,
            IS_INUNDATED_COLUMN,
        ],
    )
    origin = landslide_by_origin(land_in, rw_in)
    totals = pd.concat([liq[[CLAIM_ID_COLUMN, *areas]], slid])
    land = totals.groupby(CLAIM_ID_COLUMN)[areas].sum()
    land.columns = ["evacuated_m2", "inundated_m2"]

    def damaged(table: pd.DataFrame) -> set:
        return set(table.loc[table[areas].sum(axis=1) > 0, CLAIM_ID_COLUMN])

    by_liquefaction = damaged(liq)
    with_ground = damaged(slid)
    by_wall = set(walls.loc[walls["outcome"] == FAILED_WITH_POLYGON, CLAIM_ID_COLUMN])
    by_landslide = set(origin.index[origin["other_landslide_m2"] > 0])
    by_wall |= set(origin.index[origin["wall_landslide_m2"] > 0])
    # A claim with any ground stays in the table, whatever typed it.
    # A claim only imminent ground reaches is kept too, with no damaged ground.
    kept = (
        by_liquefaction
        | with_ground
        | by_wall
        | set(imminent.index[imminent.any(axis=1)])
    )
    land = land.reindex(sorted(kept), fill_value=0)
    land["cause"] = [
        cause_label(
            liquefaction=claim in by_liquefaction,
            landslide=claim in by_landslide,
            wall=claim in by_wall,
        )
        for claim in land.index
    ]
    # Landslide ground as a flag too, so the page can type the claim by it.
    land["has_landslide"] = land.index.isin(by_landslide).astype(int)
    land["wall_landslide_m2"] = (
        origin["wall_landslide_m2"].reindex(land.index).fillna(0.0)
    )
    land[list(imminent.columns)] = (
        imminent.reindex(land.index).fillna(0.0).astype(float)
    )
    return land.round(4)


def cause_label(*, liquefaction: bool, landslide: bool, wall: bool) -> str:
    """Name what damaged a claim's land, in a sentence: "Landslide and ..."."""
    names = [
        name
        for name, present in (
            ("liquefaction", liquefaction),
            ("landslide", landslide),
            ("retaining wall failure", wall),
        )
        if present
    ]
    if not names:
        return ""
    text = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    return text[0].upper() + text[1:]


def within_territorial_authority(rows: pd.DataFrame, extent: str) -> pd.DataFrame:
    """Keep the claims in the territorial authority the extent is named for.

    An extent over one authority is its bounding box, so it also takes in the
    edges of its neighbours -- about a quarter of the claims in the Porirua box
    are in Wellington City or Lower Hutt. Those are counted again in their own
    authority's run, so a viewer for Porirua shows Porirua's claims only. A
    claim is placed by its map point, which sits inside its insured land, so a
    claim with no address point on it is placed too. The full study area and the
    pilot boxes are not one authority, and are kept whole.

    Args:
        rows: The viewer's rows, with ``lon`` and ``lat``.
        extent: The extent the run is over.

    Returns:
        The rows inside the authority, or every row.
    """
    aoi = get_area_of_interest(extent)
    authorities = get_study_areas(4326)
    if aoi is None or aoi.name not in set(authorities["name"]):
        return rows
    boundary = authorities.loc[authorities["name"] == aoi.name].union_all()
    points = gpd.GeoSeries(gpd.points_from_xy(rows["lon"], rows["lat"]), crs=4326)
    inside = points.within(boundary).to_numpy()
    print(
        f"  Kept {int(inside.sum()):,} claims in {aoi.name}; left out "
        f"{int((~inside).sum()):,} in the extent's box beyond it"
    )
    return rows[inside]


def liquefaction_method(
    claims: pd.DataFrame, realisation_id: int, *, extent: str
) -> str:
    """Return how the settled liquefaction cost was priced.

    Vul step 2 prices every claim both ways and step 10 hands loss one of them,
    so the method is whichever the settled cost matches. It is read off the data
    because runs from before 2026-10-08 settled the lookup, and the page has to
    say so rather than present the two as alike.
    """
    priced = (
        pd.read_parquet(
            liq_land.liq_land_damage_path(realisation_id, extent=extent),
            columns=[CLAIM_ID_COLUMN, "cost_nzd", liq_land.AREA_COST_COLUMN],
        )
        .groupby(CLAIM_ID_COLUMN)
        .sum()
    )
    settled = (
        (claims[LIQ_REPAIR_COLUMN] / (1.15 * LIQ_COST_ESCALATION))
        .reindex(priced.index)
        .fillna(0.0)
    )
    lookup_miss = (settled - priced["cost_nzd"]).abs().sum()
    area_miss = (settled - priced[liq_land.AREA_COST_COLUMN]).abs().sum()
    return AREA_METHOD if area_miss < lookup_miss else LOOKUP_METHOD


def viewer_version() -> str:
    """Return the version the page and its CSV are stamped with.

    The first six characters of the commit they are built from and the date,
    so an issued copy can be traced to the code that made it. Uncommitted
    changes under ``src`` mean the commit alone does not say what was issued,
    so the version says so.

    Returns:
        For example ``v1a2b3c, built 2026-10-09``, ending ``, with uncommitted
        changes`` when there are any, or ``unknown`` in place of the commit
        when git cannot be read.
    """

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    commit = git("rev-parse", "--short=6", "HEAD")
    built = datetime.now(UTC).astimezone().date().isoformat()
    version = f"v{commit}, built {built}" if commit else f"unknown, built {built}"
    if git("status", "--porcelain", "--", "src"):
        version += ", with uncommitted changes"
    return version


def write_viewer(out_dir, version: str):
    """Write the page beside the CSVs, with its version in place."""
    page = (HERE / VIEWER).read_text(encoding="utf-8")
    path = out_dir / VIEWER
    path.write_text(page.replace(VERSION_PLACEHOLDER, version), encoding="utf-8")
    return path


def site_multiplier(claims: pd.DataFrame) -> pd.Series:
    """Return each claim's site multiplier, summed from its three ratings."""
    return sum(
        claims[column].map(RATING_MARKUP).fillna(0.0)
        for column in (ACCESS_COLUMN, EARTHWORKS_COLUMN, CONSTRUCTABILITY_COLUMN)
    )


def wall_value_excl_gst(rw: pd.DataFrame, policy: PolicySettings) -> pd.Series:
    """Return each claim's damaged wall value before GST, summed wall by wall.

    Taken from step 0's own function, so the viewer's cap is built from the same
    value the module's is. A claim's walls are valued one by one and then added:
    a single size, length and rate per claim would price every metre of a claim
    with walls of mixed sizes at its tallest wall's size and highest rate.
    """
    return wall_udv_by_claim(rw, policy=policy) / (1.0 + policy.gst_rate)


def damaged_structure_counts(
    world_id: int, realisation_id: int, *, extent: str
) -> pd.DataFrame:
    """Return how many existing land structures each claim has damaged.

    Existing structures only: the retaining walls, culverts and bridges in the
    contract's tables with a damage flag set, as step 0 reads them. A wall the
    module invents to reinstate landslide ground is a remedy, not a damaged
    structure, and is not counted. A claim can carry several of each, but the
    settlement prices its walls together and its crossings at one sub-cap, so
    the page needs the counts only to report them.

    Returns:
        Indexed by claim: ``damaged_wall_count`` and ``damaged_crossing_count``.
        A claim with neither does not appear.
    """
    rw = gpd.read_parquet(
        world_loss_input_path("rw", world_id, realisation_id, extent=extent)
    )
    walls = loss_claims.damaged_walls(rw).groupby(CLAIM_ID_COLUMN).size()
    crossings = [
        loss_claims.damaged_crossings(
            gpd.read_parquet(
                world_loss_input_path(table, world_id, realisation_id, extent=extent)
            )
        )
        for table in ("culverts", "bridges")
    ]
    crossing_ids = pd.concat(
        [c[CLAIM_ID_COLUMN] for c in crossings if not c.empty]
        or [pd.Series(dtype=object)]
    )
    return pd.DataFrame(
        {
            "damaged_wall_count": walls,
            "damaged_crossing_count": crossing_ids.value_counts(),
        }
    )


def damaged_wall_length_by_claim(rw: pd.DataFrame) -> pd.Series:
    """Return the length of each claim's walls that are damaged, in metres.

    The sum over the claim's damaged pieces of the length each is damaged over
    (T-158): the clipped length of a wall a neighbour's landslide reached, the
    whole length of one that failed in shaking, and the whole length of every
    piece where the table has no ``rw_damaged_length``. It is the length the
    page shows, before the margin the replacement adds
    (:func:`~landloss.loss.claims.wall_lengths_by_piece`).

    Args:
        rw: The loss input's retaining wall table.

    Returns:
        Metres per claim, rounded as the viewer's other areas and lengths are;
        a claim with no damaged wall does not appear.
    """
    damaged = loss_claims.damaged_walls(rw)
    lengths = loss_claims.wall_lengths_by_piece(damaged)[
        loss_claims.DAMAGED_LENGTH_COLUMN
    ]
    return lengths.groupby(damaged[CLAIM_ID_COLUMN]).sum().round(4)


def viewer_rows(
    claims: pd.DataFrame, wall_value: pd.Series, liq_state: pd.Series
) -> pd.DataFrame:
    """Return the table the viewer reads, one row per claim.

    Only what the Act does not decide. Wall value and wall cost arrive **before
    GST**, and the repair as a face area and a rate rather than as a price,
    because a price already has GST, the site multiplier and the specification
    uplift baked into it -- and the page applies all three itself.

    Args:
        claims: Step 1's settlements, indexed by claim.
        wall_value: The damaged walls' value before GST per claim, as
            :func:`wall_value_excl_gst` returns.
        liq_state: The liquefaction land damage state per claim, as
            :func:`liquefaction_states` returns.

    Returns:
        The viewer's rows.
    """
    return pd.DataFrame(
        {
            "dwellings": claims["dwelling_count"].astype(int),
            "damaged_area_m2": claims["damaged_area_m2"].round(4),
            "land_rate_incl_gst": claims["land_rate_incl_gst_nzd_per_m2"].round(6),
            # What the damaged walls were worth, before GST: it builds the cap.
            "wall_value_excl_gst": wall_value.reindex(claims.index)
            .fillna(0.0)
            .round(6),
            # What the damaged wall is replaced at, which a landslide can make
            # larger than the wall that was there. The value above builds the
            # cap; this builds the repair.
            "replacement_face_m2": claims[REPLACEMENT_WALL_FACE_COLUMN].round(6),
            "replacement_rate_excl_gst": claims[REPLACEMENT_WALL_RATE_COLUMN].round(6),
            # A new wall for each slip no damaged wall holds (T-124): their
            # face summed and the bare rate face-weighted, so face by rate is
            # their bare cost, as for the replacements. An invented wall is
            # priced at the timber pole rate its height calls for rather than
            # at the claim's own wall rate -- it has no wall of its own to take
            # a construction from. Carried separately so the page does not
            # silently price it at zero.
            "new_wall_face_m2": claims[NEW_WALL_FACE_COLUMN].round(6),
            "new_wall_rate_excl_gst": claims[NEW_WALL_RATE_COLUMN].round(6),
            "new_wall_count": claims[NEW_WALL_COUNT_COLUMN].astype(int),
            # How many of them stand on a mapped wall (the height and length of
            # the wall unit the slip's polygon stands on) rather than being
            # sized from the slip, for the page to say. Counts only; the face
            # and rate above already price them.
            # A settlement written before loss s1 counted them has no column:
            # none are counted.
            "new_wall_from_mapped_count": claims.get(
                NEW_WALL_FROM_MAPPED_COLUMN, pd.Series(0, index=claims.index)
            ).astype(int),
            "spoil_m3": claims[SPOIL_VOLUME_COLUMN].round(6),
            # The Canterbury cost is a settled amount, so it arrives whole --
            # but in 2010/2011 dollars and before GST, because the page applies
            # both the escalation to today's and GST itself.
            "liq_cost_excl_gst": (
                claims[LIQ_REPAIR_COLUMN] / (1.15 * LIQ_COST_ESCALATION)
            ).round(6),
            # The module's escalation, which the page opens on.
            "liq_escalation": LIQ_COST_ESCALATION,
            "site_multiplier": site_multiplier(claims).round(3),
            "has_damaged_wall": (claims[WALL_REPAIR_COLUMN] > 0).astype(int),
            "has_new_wall": (claims[LAND_REPAIR_COLUMN] > 0).astype(int),
            # The state as well as the cost, because the cost alone cannot tell
            # a claim from a property with nothing to claim for: the None state
            # carries a Canterbury cost too. Liquefaction damage is a state worse
            # than None, and it is what makes a property a claim on the page.
            "liq_state": liq_state.reindex(claims.index).fillna(0).astype(int),
            "has_liquefaction": (
                liq_state.reindex(claims.index).fillna(0) > NO_DAMAGE_LIQ_STATE
            ).astype(int),
            # The claim's damaged culverts and bridges, replaced or cleared and
            # summed, and what they are worth, both before GST: the page builds
            # the repair from the one and the cap from the other, through the
            # sub-cap.
            "has_crossing": (claims[CROSSING_REPAIR_COLUMN] > 0).astype(int),
            "crossing_repair_excl_gst": (
                claims[CROSSING_REPAIR_COLUMN] / (1.0 + GST_RATE)
            ).round(6),
            "crossing_value_excl_gst": (
                claims[CROSSING_UDV_COLUMN] / (1.0 + GST_RATE)
            ).round(6),
            "access": claims[ACCESS_COLUMN],
            "earthworks": claims[EARTHWORKS_COLUMN],
            "constructability": claims[CONSTRUCTABILITY_COLUMN],
        }
    )


def settled_in_python(
    rows: pd.DataFrame, policy: PolicySettings, *, gst_rate: float | None = None
) -> pd.DataFrame:
    """Settle the viewer's rows the way the page will, as a check on it.

    A transcription of the JavaScript, kept here so the page can be shown to
    disagree with the module rather than trusted not to. The page runs it with
    no GST; the check runs it at the module's rate, where the two must agree.

    Args:
        rows: The viewer's rows.
        policy: The settings the page opens on.
        gst_rate: The GST rate to settle at; the module's when not given.

    Returns:
        The cap, repair cost and settlement per claim.
    """
    gst = 1.0 + (policy.gst_rate if gst_rate is None else gst_rate)
    spec = 1.0 + policy.replacement_spec_uplift
    mult = 1.0 + rows["site_multiplier"]

    udv = rows["wall_value_excl_gst"] * gst
    wall = (
        rows["replacement_face_m2"]
        * rows["replacement_rate_excl_gst"]
        * gst
        * mult
        * spec
    )
    new_wall = (
        rows["new_wall_face_m2"] * rows["new_wall_rate_excl_gst"] * gst * mult * spec
    )
    spoil = rows["spoil_m3"] * INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3 * gst
    walled = (rows["has_damaged_wall"] > 0) | (rows["has_new_wall"] > 0)
    fees = np.where(
        walled,
        np.maximum(
            PROFESSIONAL_FEES_SHARE * (wall + new_wall),
            PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD * gst,
        ),
        0.0,
    )

    land_rate = rows["land_rate_incl_gst"] / (1.0 + policy.gst_rate) * gst
    land_value = np.minimum(rows["damaged_area_m2"], policy.area_cap_m2) * land_rate
    # The sub-caps are stated before GST; the policy's limits carry it.
    to_page = gst / (1.0 + policy.gst_rate)
    crossing_repair = rows["crossing_repair_excl_gst"] * gst
    crossing_value = rows["crossing_value_excl_gst"] * gst
    # The page applies the module's GST-free floor at its own GST rate.
    on_costs = on_costs_incl_gst_nzd(
        np.where(walled, wall + new_wall, 0.0),
        fees,
        crossing_repair,
        policy=PolicySettings(gst_rate=gst - 1.0),
    )
    cap = (
        land_value
        + np.minimum(udv, policy.retaining_wall_limit_nzd(rows["dwellings"]) * to_page)
        + np.minimum(
            crossing_value, policy.bridge_culvert_limit_nzd(rows["dwellings"]) * to_page
        )
    )
    liq = rows["liq_cost_excl_gst"] * LIQ_COST_ESCALATION * gst
    repair = wall + new_wall + spoil + fees + on_costs.total + liq
    repair = repair + crossing_repair
    repair = repair + contingency_incl_gst_nzd(repair)
    payable = np.minimum(repair, cap)
    excess = np.minimum(
        rows["dwellings"].clip(lower=1) * policy.excess_per_dwelling_nzd,
        policy.excess_max_nzd,
    ) * (payable > 0)
    return pd.DataFrame(
        {
            "cap": cap,
            "repair": repair,
            "settlement": np.maximum(payable - excess, 0.0),
        },
        index=rows.index,
    )


def check_viewer_against_the_model(rows, claims, policy) -> float:
    """Print whether the viewer's arithmetic still matches what was settled."""
    mine = settled_in_python(rows, policy)
    worst = max(
        (mine["cap"] - claims["land_cover_cap_incl_gst_nzd"]).abs().max(),
        (mine["repair"] - claims["repair_cost_incl_gst_nzd"]).abs().max(),
        (mine["settlement"] - claims["settlement_incl_gst_nzd"]).abs().max(),
    )
    if worst > 1.0:
        print(f"  WARNING: the viewer would differ from the module by ${worst:,.2f}")
    else:
        print(f"  Viewer arithmetic agrees with the module to ${worst:,.2f} at worst")
    return worst


def main(*, extent, world_ids, realisation_ids):
    """Write the viewer's CSV for the first world and realisation, and the page."""
    policy = PolicySettings()
    world_id = world_ids[0]
    realisation_id = realisation_ids[0]
    claims = pd.read_parquet(
        settlement_path(world_id, realisation_id, extent=extent)
    ).set_index(CLAIM_ID_COLUMN)
    rw = gpd.read_parquet(
        world_loss_input_path("rw", world_id, realisation_id, extent=extent)
    )
    rows = viewer_rows(
        claims,
        wall_value_excl_gst(rw, policy),
        liquefaction_states(world_id, realisation_id, extent=extent),
    )
    land = damaged_land(world_id, realisation_id, extent=extent)
    rows = rows.join(land)
    ground = [
        "evacuated_m2",
        "inundated_m2",
        "wall_landslide_m2",
        *IMMINENT_VIEWER_COLUMNS.values(),
    ]
    rows[ground] = rows[ground].fillna(0.0)
    rows["cause"] = rows["cause"].fillna("")
    ejecta = liquefaction_ejecta(realisation_id, extent=extent)
    rows = rows.join(ejecta)
    for column in (
        "liq_inundated_cost_excl_gst",
        "liq_inundated_cost_sva_excl_gst",
        "liq_inundated_cost_no_sva_excl_gst",
    ):
        rows[column] = rows[column].fillna(0.0).round(6)
    rows["liq_sva"] = rows["liq_sva"].fillna(int(not liq_config.NO_SVA)).astype(int)
    rows["has_landslide"] = rows["has_landslide"].fillna(0).astype(int)
    counts = damaged_structure_counts(world_id, realisation_id, extent=extent)
    rows = rows.join(counts)
    for column in counts.columns:
        rows[column] = rows[column].fillna(0).astype(int)
    rows["damaged_wall_length_m"] = (
        damaged_wall_length_by_claim(rw).reindex(rows.index).fillna(0.0)
    )
    method = liquefaction_method(claims, realisation_id, extent=extent)
    print(f"  Liquefaction costs: {method}")
    rows["liq_method"] = method
    points = claim_points(world_id, realisation_id, extent=extent)
    rows = rows.join(points).reset_index()
    rows = within_territorial_authority(rows, extent)

    check_viewer_against_the_model(rows.set_index(CLAIM_ID_COLUMN), claims, policy)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = extent_suffix(extent)
    csv_path = (
        OUT_DIR / f"loss-viewer-w{world_id:03d}-r{realisation_id:03d}{suffix}.csv"
    )
    # Each CSV carries the version it was built with too: the page beside it is
    # rewritten on every run, so a CSV can be older than the page it sits with.
    version = viewer_version()
    rows["built_with"] = version
    rows.to_csv(csv_path, index=False)
    # A copy beside the CSVs, so the folder can be sent as it is. The page in
    # this directory is the one kept in git; this copy is ignored.
    page = write_viewer(OUT_DIR, version)
    print(f"Wrote {len(rows):,} claims to {csv_path}")
    print(f"Wrote {page}, version {version}")
    print("Open the page and drag the CSV onto it.")
    return 0


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
