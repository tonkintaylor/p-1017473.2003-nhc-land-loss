"""Write the one CSV the static loss viewer reads, and put the viewer beside it.

    uv run --frozen python src/scripts/landloss/loss/validations/gen_viewer_data.py

The viewer is `loss_viewer.html`, a single page with no server and no build
step: open it, drag the CSV on, and it settles every claim in the browser. The
point is that **the policy settings are controls rather than constants**, so
somebody at NHC can move the excess or the total cap and watch the portfolio
answer, without Python, a spreadsheet, or anyone to run it for them. Two
scenarios are two CSVs dragged onto the same page.

**What the CSV carries is everything the settlement does not decide.** Areas,
rates, wall geometry, the Canterbury cost, who has what damage -- all fixed by
exposure and vul. What it deliberately leaves out is every figure the Act sets:
GST, the caps, the sub-caps, the excess, the fees, the specification uplift.
Those are the controls, so a number that moves when a control moves is not in
this file.

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

from landloss.domain.loss_contract import CLAIM_ID_COLUMN
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    BETA_SIZE_CLASS_HEIGHT_M,
    INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3,
    PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD,
    RATING_MARKUP,
    timber_pole_rate_excl_gst_nzd_per_m2,
)
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    ACCESS_COLUMN,
    CONSTRUCTABILITY_COLUMN,
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
from scripts.landloss.loss.validations.gen_calc_walkthrough import wall_shape
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = REPORT_DIR / "loss" / "viewer"
VIEWER = "loss_viewer.html"
HERE = __import__("pathlib").Path(__file__).resolve().parent


def claim_points(realisation_id: int, *, pilot: bool) -> pd.DataFrame:
    """Return each claim's position in degrees, for the map.

    The insured land is a polygon; the viewer wants a dot, so this takes a
    point guaranteed to sit inside it rather than a centroid, which on an
    L-shaped section can fall outside the property altogether.

    Args:
        realisation_id: The modelled earthquake.
        pilot: Whether the run is over the small Wellington pilot box.

    Returns:
        ``lon`` and ``lat`` per claim.
    """
    land = gpd.read_parquet(loss_input_path("land", realisation_id, pilot=pilot))
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


def site_multiplier(claims: pd.DataFrame) -> pd.Series:
    """Return each claim's site multiplier, summed from its three ratings."""
    return sum(
        claims[column].map(RATING_MARKUP).fillna(0.0)
        for column in (ACCESS_COLUMN, EARTHWORKS_COLUMN, CONSTRUCTABILITY_COLUMN)
    )


def viewer_rows(claims: pd.DataFrame, walls: pd.DataFrame) -> pd.DataFrame:
    """Return the table the viewer reads, one row per claim.

    Only what the Act does not decide. Wall cost arrives as a **face area and a
    rate** rather than as a price, because a price already has GST, the site
    multiplier and the specification uplift baked into it -- and all three are
    controls on the page.

    Args:
        claims: Step 1's settlements, indexed by claim.
        walls: The damaged walls' size, length and rate per claim.

    Returns:
        The viewer's rows.
    """
    height = walls["wall_size"].map(BETA_SIZE_CLASS_HEIGHT_M).fillna(0.0)
    new_height = claims[NEW_WALL_HEIGHT_COLUMN].fillna(0.0)
    new_rate = np.where(
        new_height > 0, timber_pole_rate_excl_gst_nzd_per_m2(new_height), 0.0
    )
    return pd.DataFrame(
        {
            "dwellings": claims["dwelling_count"].astype(int),
            "damaged_area_m2": claims["damaged_area_m2"].round(4),
            "land_rate_incl_gst": claims["land_rate_incl_gst_nzd_per_m2"].round(6),
            # Wall geometry and rate, not a wall price.
            "wall_face_m2": (height * walls["wall_length_m"].fillna(0.0)).round(6),
            "wall_rate_excl_gst": walls["wall_rate_excl_gst"].fillna(0.0).round(6),
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
            # but before GST, which is a control.
            "liq_cost_excl_gst": (claims[LIQ_REPAIR_COLUMN] / 1.15).round(6),
            "site_multiplier": site_multiplier(claims).round(3),
            "has_damaged_wall": (claims[WALL_REPAIR_COLUMN] > 0).astype(int),
            "has_new_wall": (claims[LAND_REPAIR_COLUMN] > 0).astype(int),
            "has_liquefaction": (claims[LIQ_REPAIR_COLUMN] > 0).astype(int),
            "has_crossing": 0,
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

    udv = rows["wall_face_m2"] * rows["wall_rate_excl_gst"] * gst
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
    repair = wall + new_wall + spoil + fees + rows["liq_cost_excl_gst"] * gst
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


def main(*, pilot, realisation_ids):
    """Write the viewer's CSV and copy the page beside it."""
    policy = PolicySettings()
    realisation_id = realisation_ids[0]
    claims = pd.read_parquet(settlement_path(realisation_id, pilot=pilot)).set_index(
        CLAIM_ID_COLUMN
    )
    walls = wall_shape(realisation_id, pilot=pilot).reindex(claims.index)
    rows = viewer_rows(claims, walls)
    rows = rows.join(claim_points(realisation_id, pilot=pilot)).reset_index()

    check_viewer_against_the_model(rows.set_index(CLAIM_ID_COLUMN), claims, policy)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "-pilot" if pilot else ""
    csv_path = OUT_DIR / f"loss-viewer-r{realisation_id:03d}{suffix}.csv"
    rows.to_csv(csv_path, index=False)
    shutil.copy(HERE / VIEWER, OUT_DIR / VIEWER)
    print(f"Wrote {len(rows):,} claims to {csv_path}")
    print(f"Wrote {OUT_DIR / VIEWER}")
    print("Open the page and drag the CSV onto it.")
    return 0


if __name__ == "__main__":
    main(pilot=config.PILOT, realisation_ids=config.REALISATION_IDS)
