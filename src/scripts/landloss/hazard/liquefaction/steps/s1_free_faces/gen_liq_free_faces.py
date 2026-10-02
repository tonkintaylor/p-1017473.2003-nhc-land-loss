"""Build the lateral spreading free-face layer over an extent.

The free faces are what the lateral spreading zones are buffered from: named
rivers, the water bodies of at least 5 ha, and the coast. The layer rebuilds the
National Liquefaction Model's own, from the same LINZ sources with the same
filters, so that the two studies buffer the same ground (register task T-46);
:mod:`landloss.hazard.liquefaction.waterways` holds the filters and says where
each came from.

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/steps/s1_free_faces/gen_liq_free_faces.py

What it runs over comes from ``config.py`` beside it. It writes one GeoPackage
under ``temp/hazard/liquefaction/``, which the buffer step (T-47) reads, and
prints a count and a length or area per type so that a run can be checked
without opening it.

Needs ``LINZ_API_KEY``. The first run downloads six national layers, which LINZ
takes minutes to export; later runs over the same extent read the cache.
"""

import sys

import geopandas as gpd

from landloss.domain import constants
from landloss.hazard.liquefaction.waterways import FREE_FACE_TYPES, get_free_faces
from landloss.io.area_of_interest import (
    LOWER_HUTT_PILOT,
    SMALL_WLG_PILOT,
    get_study_areas,
)
from scripts.landloss.hazard.liquefaction.steps.s1_free_faces import config
from scripts.landloss.paths import TEMP_DIR

# temp/ is gitignored: the layer is rebuildable from LINZ in minutes.
WORK_DIR = TEMP_DIR / "hazard" / "liquefaction"

# The pilot boxes, by the name config.EXTENT uses, and the suffix their output
# carries so that no run overwrites another's.
PILOTS = {"lower hutt": LOWER_HUTT_PILOT, "pilot": SMALL_WLG_PILOT}
SUFFIXES = {"lower hutt": "-lower-hutt", "pilot": "-pilot", "study": ""}

RULE = "-" * 72


def free_faces_path(extent: str):
    """Return the file a run over ``extent`` writes, and the buffer step reads.

    Args:
        extent: One of the keys of :data:`SUFFIXES`.

    Returns:
        The output path, under ``temp/hazard/liquefaction/``.
    """
    return WORK_DIR / f"free-faces{SUFFIXES[extent]}.gpkg"


def resolve_extent(extent: str):
    """Return the box to read, the boundary to clip to, and a label for the run.

    The four territorial authorities are clipped to their own boundary, because
    their bounding box takes in much of the Wairarapa. A pilot box is its own
    boundary, so it is not clipped again.

    Args:
        extent: One of the keys of :data:`SUFFIXES`.

    Returns:
        ``(bbox, clip_to, name)``.

    Raises:
        ValueError: If ``extent`` is not a known extent.
    """
    if extent in PILOTS:
        area = PILOTS[extent]
        return area.bbox(constants.DEFAULT_CRS), None, area.name
    if extent == "study":
        study_areas = get_study_areas(constants.DEFAULT_CRS)
        bbox = tuple(float(value) for value in study_areas.total_bounds)
        return bbox, study_areas, "the four territorial authorities"
    msg = f"EXTENT must be one of {sorted(SUFFIXES)}, not {extent!r}"
    raise ValueError(msg)


def describe(free_faces: gpd.GeoDataFrame) -> None:
    """Print a count, and a length or an area, per type and source.

    Lines are measured in kilometres and polygons in hectares, because the two
    are buffered alike but are not the same quantity.
    """
    print(RULE)
    print(f"{'type':<8} {'source':<10} {'features':>9} {'km':>8} {'ha':>9}")
    for (wtype, source), group in free_faces.groupby(["wtype", "source"], sort=False):
        is_area = group.geom_type.str.contains("Polygon")
        km = group.loc[~is_area].length.sum() / 1000
        ha = group.loc[is_area].area.sum() / 10_000
        print(f"{wtype:<8} {source:<10} {len(group):>9,} {km:>8.1f} {ha:>9.1f}")
    missing = sorted(set(FREE_FACE_TYPES) - set(free_faces["wtype"]))
    if missing:
        print(f"No {', '.join(missing)} within the extent.")

    rivers = free_faces.loc[free_faces["source"] == "name line", "name"].dropna()
    if not rivers.empty:
        print(RULE)
        print("River name lines kept, by name or by ID:")
        for name in sorted(rivers.unique()):
            print(f"  {name}")


def main(*, extent: str) -> None:
    """Build the free faces over ``extent`` and write them out.

    Args:
        extent: One of the keys of :data:`SUFFIXES`, from ``config.EXTENT``.
    """
    # LINZ names carry macrons (Waiwhetū), which the Windows console's code page
    # cannot print.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bbox, clip_to, name = resolve_extent(extent)
    print(f"Extent: {name}")
    print("Reading the river name lines and the topo50 water layers ...", flush=True)
    free_faces = get_free_faces(bbox, clip_to=clip_to)
    describe(free_faces)

    path = free_faces_path(extent)
    path.parent.mkdir(parents=True, exist_ok=True)
    free_faces.to_file(path, driver="GPKG")
    print(RULE)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(extent=config.EXTENT)
