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
the caps, the sub-caps, the excess, the fees, the specification uplift. Those
are the controls, so a number that moves when a control moves is not in this
file. GST is left out too but is not a control: the page fixes it at
:data:`~landloss.loss.policy.GST_RATE`, as the module does. The page also
scales the wall rates and the land value, to show how far an answer leans on
them; at a scale of one each, it is the module's answer.

The land cap scenarios NHC is weighing are drawn over the main histogram, with
the share of claims above each cap and the total settled under it. Those are
the page's own arithmetic over the same rows, not something this file carries.

That split is also what keeps the page honest. It cannot show a settlement that
the module would not produce, because it is running the same arithmetic on the
same inputs -- and `check_viewer_against_the_model` proves it, at the default
settings, before the file is written.
"""

import shutil
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN, LIQ_LD_STATE_COLUMN
from landloss.hazard.landslide.urban.realisation import FAILED_WITH_POLYGON
from landloss.hazard.liquefaction.land_damage import LD_STATES
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3,
    LIQ_COST_ESCALATION,
    PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD,
    RATING_MARKUP,
    timber_pole_rate_excl_gst_nzd_per_m2,
)
from scripts.landloss.loss.steps.s0_land_cover_cap.s0_gen_land_cover_cap import (
    wall_udv_by_claim,
)
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    ACCESS_COLUMN,
    CONSTRUCTABILITY_COLUMN,
    CROSSING_REPAIR_COLUMN,
    EARTHWORKS_COLUMN,
    LAND_REPAIR_COLUMN,
    LIQ_REPAIR_COLUMN,
    NEW_WALL_HEIGHT_COLUMN,
    NEW_WALL_LENGTH_COLUMN,
    REPLACEMENT_WALL_FACE_COLUMN,
    REPLACEMENT_WALL_RATE_COLUMN,
    SPOIL_VOLUME_COLUMN,
    WALL_REPAIR_COLUMN,
    settlement_path,
)
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import (
    gen_landslide_land_damage as landslide_land,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import (
    gen_wall_landslide_damage as wall_landslide,
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


def damaged_land(world_id: int, realisation_id: int, *, extent: str) -> pd.DataFrame:
    """Return each claim's evacuated and inundated land, and what caused it.

    The loss input carries one damaged area per claim, which is all settlement
    needs; the page also shows how it splits (T-123), read here from the vul
    tables the loss input was built from. The two are not additive: where the
    ground was both evacuated and inundated it counts in each.

    The cause names liquefaction, landslide, retaining wall failure, or a
    combination, without areas per cause. A claim's wall failure is a wall on it
    that failed and brought ground down with it; whether a given landslide came
    from that wall or from the slope is not yet passed down (T-124), so a claim
    with both reads as both.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent the run is over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        ``evacuated_m2``, ``inundated_m2``, ``cause`` and ``has_landslide`` per
        claim that has any.
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
    totals = pd.concat([liq[[CLAIM_ID_COLUMN, *areas]], slid])
    land = totals.groupby(CLAIM_ID_COLUMN)[areas].sum()
    land.columns = ["evacuated_m2", "inundated_m2"]

    def damaged(table: pd.DataFrame) -> set:
        return set(table.loc[table[areas].sum(axis=1) > 0, CLAIM_ID_COLUMN])

    by_liquefaction = damaged(liq)
    by_landslide = damaged(slid)
    by_wall = set(walls.loc[walls["outcome"] == FAILED_WITH_POLYGON, CLAIM_ID_COLUMN])
    land = land.reindex(sorted(by_liquefaction | by_landslide | by_wall), fill_value=0)
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
    new_height = claims[NEW_WALL_HEIGHT_COLUMN].fillna(0.0)
    new_rate = np.where(
        new_height > 0, timber_pole_rate_excl_gst_nzd_per_m2(new_height), 0.0
    )
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
            "new_wall_face_m2": (
                claims[NEW_WALL_HEIGHT_COLUMN] * claims[NEW_WALL_LENGTH_COLUMN]
            ).round(6),
            # An invented wall is priced at the timber pole rate its height
            # calls for rather than at the claim's own wall rate -- it has no
            # wall of its own to take a construction from, and a claim needing
            # one often has no damaged wall at all, so there is no rate to
            # borrow. Carried separately so the page does not silently price it
            # at zero.
            "new_wall_rate_excl_gst": np.round(new_rate, 6),
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
            # A damaged culvert or bridge is priced at its sub-cap, on both the
            # cap and the repair, so the page needs only whether there is one.
            "has_crossing": (claims[CROSSING_REPAIR_COLUMN] > 0).astype(int),
            "access": claims[ACCESS_COLUMN],
            "earthworks": claims[EARTHWORKS_COLUMN],
            "constructability": claims[CONSTRUCTABILITY_COLUMN],
        }
    )


def settled_in_python(rows: pd.DataFrame, policy: PolicySettings) -> pd.DataFrame:
    """Settle the viewer's rows the way the page will, as a check on it.

    A transcription of the JavaScript, kept here so the page can be shown to
    disagree with the module rather than trusted not to.

    Args:
        rows: The viewer's rows.
        policy: The settings the page opens on.

    Returns:
        The cap, repair cost and settlement per claim.
    """
    gst = 1.0 + policy.gst_rate
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
    fees = np.where(walled, PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD * mult * gst, 0.0)
    crossing_limit = rows["has_crossing"] * policy.bridge_culvert_limit_nzd(
        rows["dwellings"]
    )

    land_value = (
        np.minimum(rows["damaged_area_m2"], policy.area_cap_m2)
        * rows["land_rate_incl_gst"]
    )
    cap = (
        land_value
        + np.minimum(udv, policy.retaining_wall_limit_nzd(rows["dwellings"]))
        + crossing_limit
    )
    liq = rows["liq_cost_excl_gst"] * LIQ_COST_ESCALATION * gst
    repair = wall + new_wall + spoil + fees + liq
    repair = repair + crossing_limit
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
    rows[["evacuated_m2", "inundated_m2"]] = rows[
        ["evacuated_m2", "inundated_m2"]
    ].fillna(0.0)
    rows["cause"] = rows["cause"].fillna("")
    rows["has_landslide"] = rows["has_landslide"].fillna(0).astype(int)
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
    rows.to_csv(csv_path, index=False)
    # A copy beside the CSVs, so the folder can be sent as it is. The page in
    # this directory is the one kept in git; this copy is ignored.
    shutil.copy(HERE / VIEWER, OUT_DIR / VIEWER)
    print(f"Wrote {len(rows):,} claims to {csv_path}")
    print(f"Wrote {OUT_DIR / VIEWER}")
    print("Open the page and drag the CSV onto it.")
    return 0


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
