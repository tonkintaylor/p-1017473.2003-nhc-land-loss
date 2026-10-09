"""Example: download LINZ address data for a study extent.

Run this to see how the readers behave — what a first download costs, what the
extent cache saves on a repeat call, and where the cached files end up.

    uv run --frozen python src/scripts/landloss/example_download_linz_data.py

The first run downloads the whole NZ Addresses layer from LINZ, which takes a
while; later runs reuse it. Pass --fresh to ignore the extent cache, or --layer
to try a different Koordinates layer.

Requires TNT_KOORDINATES_API_KEY and LINZ_API_KEY in .env.
"""

import argparse
import time

import requests

from landloss.domain import constants
from landloss.io import koopcache_dir
from landloss.io.area_of_interest import SMALL_WLG_PILOT, WGS84
from landloss.io.readers import get_koordinates_layer_extent

RULE = "-" * 72


def describe_extent():
    """Print the study extent in both the CRS it is defined in and the one used."""
    print(RULE)
    print(f"Area of interest: {SMALL_WLG_PILOT.name}")

    west, south, east, north = SMALL_WLG_PILOT.bbox(WGS84)
    print(f"  WGS84 : {west:.6f}, {south:.6f} to {east:.6f}, {north:.6f}")

    minx, miny, maxx, maxy = SMALL_WLG_PILOT.bbox(constants.DEFAULT_CRS)
    print(f"  NZTM  : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size  : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")
    print(f"  Area  : {SMALL_WLG_PILOT.polygon().area / 1e6:.1f} km2")


def describe_cache():
    """Print where layers and clipped extents are cached, and how big that is."""
    print(RULE)
    root = koopcache_dir(create=False)
    print(f"Cache directory: {root.resolve()}")

    if not root.exists():
        print("  (nothing cached yet)")
        return

    for path in sorted(root.rglob("*.gpkg")):
        size_mb = path.stat().st_size / 1e6
        kind = "extent" if path.parent.name == "extents" else "layer "
        print(f"  {kind}  {size_mb:8,.1f} MB  {path.name}")


def fetch(label, layer, bbox, domain, *, use_cache):
    """Fetch one extent, printing how long it took and what came back."""
    start = time.perf_counter()
    gdf = get_koordinates_layer_extent(
        layer=layer, bbox=bbox, domain=domain, use_cache=use_cache
    )
    elapsed = time.perf_counter() - start
    print(f"  {label:<22} {len(gdf):>8,} features  {elapsed:>7.2f} s")
    return gdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layer",
        type=int,
        default=constants.NZ_ADDRESSES_LAYER_ID,
        help="Koordinates layer ID to download (default: NZ Addresses).",
    )
    parser.add_argument(
        "--domain",
        default=constants.LINZ_DOMAIN,
        choices=sorted(constants.API_KEY_ENV_VARS),
        help="Koordinates domain to download from (default: LINZ).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore the extent cache, to time an uncached read.",
    )
    args = parser.parse_args()

    describe_extent()
    bbox = SMALL_WLG_PILOT.bbox(constants.DEFAULT_CRS)

    print(RULE)
    print(f"Downloading layer {args.layer} from {args.domain}")
    print("The first run downloads the whole layer, which is slow; it is then")
    print("cached, and only the clip is repeated on later runs.")
    print()

    cache = not args.fresh
    try:
        gdf = fetch("first call", args.layer, bbox, args.domain, use_cache=cache)
        fetch("again (cached)", args.layer, bbox, args.domain, use_cache=cache)
        fetch("again (no cache)", args.layer, bbox, args.domain, use_cache=False)
    except ValueError as exc:
        # Raised by resolve_api_key when a key is missing.
        print(f"\nCould not read the layer: {exc}")
        return 1
    except requests.exceptions.RequestException as exc:
        print(f"\nThe request to {args.domain} failed: {exc}")
        print(
            "\nLINZ takes many minutes to build a national export, and an occasional\n"
            "status poll returns a 502 during that wait. ttpy treats the first bad\n"
            "response as fatal, so one blip loses the run — and because it always\n"
            "requests a new export, the one it abandoned is wasted. Re-running starts\n"
            "the wait over, so repeated attempts are not reliably better than one.\n"
            "\n"
            "The export usually completes on the server regardless. It can be pulled\n"
            "into the cache by ID rather than re-exported."
        )
        return 1

    print(RULE)
    print(f"Columns: {', '.join(list(gdf.columns)[:10])} ...")

    address_column = next(
        (name for name in ("full_address", "address", "full_road_name") if name in gdf),
        None,
    )
    if address_column is not None:
        print("\nFirst few addresses in the extent:")
        for value in gdf[address_column].head(5):
            print(f"  {value}")

    describe_cache()

    print(RULE)
    print("Note: the extent cache only applies when a bounding box is given.")
    print("Without one there is no clip to skip, so nothing is cached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
