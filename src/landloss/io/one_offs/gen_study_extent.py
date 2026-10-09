"""Generate the packaged study area boundaries.

Downloads the Territorial Authority 2025 boundaries, keeps the four authorities
the study covers, and writes them to the packaged asset the readers load:

    src/landloss/io/assets/study-areas.geoparquet

Run it only when the boundaries need regenerating — a new release of the
territorial authority layer, or a change to which authorities are in scope. The
asset is committed, so day to day nobody needs to download anything.

    uv run --frozen python src/landloss/io/one_offs/gen_study_extent.py

Note on the source: LINZ does not publish territorial authority boundaries.
They come from Stats NZ, and this uses the copy mirrored on T+T's Koordinates
instance, so TNT_KOORDINATES_API_KEY is what is needed rather than a LINZ key.
"""

import argparse
from pathlib import Path

import geopandas as gpd

from landloss.domain import constants
from landloss.io import ASSETS_DIR
from landloss.io.readers import get_koordinates_layer_extent

# Columns in the source layer.
CODE_COLUMN = "TA2025_V1_00"
NAME_COLUMN = "TA2025_V1_00_NAME"
LAND_AREA_COLUMN = "LAND_AREA_SQ_KM"

ASSET_PATH = ASSETS_DIR / "study-areas.geoparquet"


def build_study_areas(
    layer: int = constants.TERRITORIAL_AUTHORITY_LAYER_ID,
) -> gpd.GeoDataFrame:
    """Download the territorial authorities and keep the four in the study area.

    Each authority is kept as its own row, so the four can be reported on
    separately rather than dissolved into a single extent.

    Args:
        layer: Koordinates layer ID of the territorial authority boundaries.

    Returns:
        The four authorities, carrying ``ta_code``, ``name`` and
        ``land_area_sq_km``, sorted by code.

    Raises:
        ValueError: If an authority is missing from the layer, or its name no
            longer matches the code it is expected to carry.
    """
    territorial_authorities = get_koordinates_layer_extent(
        layer=layer, crs=constants.DEFAULT_CRS, domain=constants.TTGROUP_DOMAIN
    )

    codes = set(constants.STUDY_AREA_TA_CODES)
    study_areas = territorial_authorities.loc[
        territorial_authorities[CODE_COLUMN].isin(codes)
    ].copy()

    missing = codes - set(study_areas[CODE_COLUMN])
    if missing:
        wanted = ", ".join(
            f"{code} ({constants.STUDY_AREA_TA_CODES[code]})"
            for code in sorted(missing)
        )
        msg = f"Territorial authorities missing from layer {layer}: {wanted}"
        raise ValueError(msg)

    # Check the names in the source still match what we expect, so a silent
    # renumbering upstream cannot quietly change which areas are included.
    for code, expected in constants.STUDY_AREA_TA_CODES.items():
        actual = study_areas.loc[study_areas[CODE_COLUMN] == code, NAME_COLUMN].iloc[0]
        if actual != expected:
            msg = f"Code {code} is {actual!r} in layer {layer}, expected {expected!r}"
            raise ValueError(msg)

    study_areas = study_areas.rename(
        columns={
            CODE_COLUMN: "ta_code",
            NAME_COLUMN: "name",
            LAND_AREA_COLUMN: "land_area_sq_km",
        }
    )
    study_areas = study_areas[["ta_code", "name", "land_area_sq_km", "geometry"]]
    return study_areas.sort_values("ta_code").reset_index(drop=True)


def main() -> int:
    """Regenerate the packaged study area asset, and report what was written.

    Returns:
        A process exit code, zero on success.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layer",
        type=int,
        default=constants.TERRITORIAL_AUTHORITY_LAYER_ID,
        help="Koordinates layer ID of the territorial authority boundaries.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ASSET_PATH,
        help="Where to write the geoparquet.",
    )
    args = parser.parse_args()

    print(f"Reading territorial authorities from layer {args.layer} ...")
    study_areas = build_study_areas(layer=args.layer)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    study_areas.to_parquet(args.out, index=False)

    print(f"\nWrote {args.out}")
    print(f"  CRS  : {study_areas.crs.to_string()}")
    print(f"  Rows : {len(study_areas)}")
    for row in study_areas.itertuples():
        print(f"    {row.ta_code}  {row.name:<18} {row.land_area_sq_km:>9,.1f} km2")

    minx, miny, maxx, maxy = study_areas.total_bounds
    print(f"  Bounds: {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size  : {(maxx - minx) / 1000:.0f} x {(maxy - miny) / 1000:.0f} km")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
