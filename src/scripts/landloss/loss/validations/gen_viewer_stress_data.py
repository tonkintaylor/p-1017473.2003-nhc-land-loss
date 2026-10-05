"""Write a region-sized CSV for the viewer, to find out where the page slows down.

    uv run --frozen python src/scripts/landloss/loss/validations/gen_viewer_stress_data.py

The pilot is 4,388 properties in one Wellington box. The study area is four
territorial authorities, so the page will eventually be asked to draw something
closer to a hundred thousand dots. This writes that file now, before anyone
finds out the hard way in front of a client.

**Nothing here is a result and the file says so in its name.** The geography is
real -- every dot is an address the exposure module actually found, with its own
land rate and slope -- but the *damage* is drawn at random from the pilot's
claims. It is the right size and the right shape, and every number in it is
fiction. Read it for how the page performs and for nothing else.

The one thing it does preserve is the pilot's mix: how many claims carry
liquefaction, a wall, both or neither, and how their costs are distributed. A
stress file made of uniformly average claims would not exercise the histograms
the way the real thing will.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.loss.validations.gen_viewer_data import OUT_DIR
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ADDRESSES = TEMP_DIR / "exposure" / "land-value-by-address.geoparquet"
OUT_NAME = "loss-viewer-SYNTHETIC-region-stress.csv"

# Claims per address in the pilot: 4,388 claims over 8,591 addresses. A claim is
# a property and a property usually has one address, but a block of flats has
# many, so the region's claim count is well below its address count.
PILOT_CLAIMS_PER_ADDRESS = 4388 / 8591

# The damage columns are drawn from the pilot; everything else comes from the
# address itself. Splitting them this way is what keeps the geography honest.
DRAWN = [
    "dwellings",
    "damaged_area_m2",
    "wall_face_m2",
    "wall_rate_excl_gst",
    "replacement_face_m2",
    "replacement_rate_excl_gst",
    "new_wall_face_m2",
    "new_wall_rate_excl_gst",
    "spoil_m3",
    "liq_cost_excl_gst",
    "has_damaged_wall",
    "has_new_wall",
    "has_liquefaction",
    "has_crossing",
    "access",
    "earthworks",
]

SEED = 20260925


def pilot_csv() -> pd.DataFrame:
    """Return the pilot viewer CSV, which the damage is drawn from.

    Raises:
        FileNotFoundError: If it has not been generated yet.
    """
    matches = sorted(OUT_DIR.glob("loss-viewer-r*.csv"))
    if not matches:
        msg = (
            f"no pilot viewer CSV in {OUT_DIR}. Run gen_viewer_data.py first -- "
            "this draws its damage from that file."
        )
        raise FileNotFoundError(msg)
    return pd.read_csv(matches[0])


def constructability(slope_deg: pd.Series) -> pd.Series:
    """Return the constructability rating each address's own slope implies.

    Taken from the real slope rather than drawn, because slope is the one site
    rating the address layer can actually answer and it is what makes the map's
    colouring vary with the terrain rather than at random.
    """
    return pd.cut(
        slope_deg, bins=[-np.inf, 10.0, 20.0, np.inf], labels=["E", "M", "D"]
    ).astype(str)


def main(*, extent, realisation_ids):
    """Write the stress file. The arguments are ignored; it is not a run."""
    del extent, realisation_ids
    rng = np.random.default_rng(SEED)
    source = pilot_csv()

    addresses = gpd.read_parquet(ADDRESSES)
    wanted = round(len(addresses) * PILOT_CLAIMS_PER_ADDRESS)
    keep = addresses.iloc[
        rng.choice(len(addresses), size=wanted, replace=False)
    ].reset_index(drop=True)

    degrees = keep.geometry.to_crs(4326)
    drawn = source.iloc[rng.choice(len(source), size=wanted, replace=True)]
    drawn = drawn[DRAWN].reset_index(drop=True)

    out = pd.DataFrame(
        {
            CLAIM_ID_COLUMN: [f"SYNTHETIC-{n:06d}" for n in range(wanted)],
            **{column: drawn[column] for column in DRAWN},
            # The address's own rate and slope, not the pilot's.
            "land_rate_incl_gst": (keep["land_rate_nzd_per_m2"] * 1.15).round(6),
            "constructability": constructability(keep["slope_deg"]),
            "lon": degrees.x.to_numpy().round(6),
            "lat": degrees.y.to_numpy().round(6),
        }
    )
    # The site multiplier has to agree with the three ratings beside it, or the
    # page shows a cost the ratings do not explain.
    markup = {"E": 0.0, "M": 0.05, "D": 0.10}
    out["site_multiplier"] = (
        out["access"].map(markup)
        + out["earthworks"].map(markup)
        + out["constructability"].map(markup)
    ).round(3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / OUT_NAME
    out.to_csv(path, index=False)

    size_mb = path.stat().st_size / 1024 / 1024
    print(f"{len(addresses):,} addresses across four territorial authorities")
    for name, count in keep["territorial_authority"].value_counts().items():
        print(f"  {name:<18} {count:>7,}")
    print()
    print(f"Wrote {len(out):,} synthetic claims, {size_mb:.1f} MB, to {path}")
    print(
        "  SYNTHETIC. Real addresses, invented damage. For measuring how the "
        "page performs, and for nothing else."
    )
    return 0


if __name__ == "__main__":
    main(extent=config.EXTENT, realisation_ids=config.REALISATION_IDS)
