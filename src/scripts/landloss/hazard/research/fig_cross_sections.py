"""Terrain cross-sections through the Wellington valleys, from the 1 m LiDAR DEM.

Four sections, each cutting across a valley rather than along it, so the width of
the flat floor and the steepness of the sides can be read off directly:

  1. Wainuiomata River  -- a settled valley floor, the case the model has to get
     right, with housing on alluvium between two steep sides.
  2. Ōrongorongo River  -- the same landform with no development on it, as a
     control for what the valley form looks like without land use on it.
  3. Lower Hutt across the valley -- the widest area of flat alluvium in the
     study area, and the largest concentration of insured land on it.
  4. Lower Hutt along the valley  -- perpendicular to section 3 by construction,
     showing the gradient down the valley to the harbour.

    uv run --frozen python src/scripts/landloss/hazard/research/fig_cross_sections.py

Elevation comes from the LINZ 1 m LiDAR DEM, licensed CC BY 4.0; see
landloss.io.elevation.sample_elevation. The first run walks the LINZ STAC
catalogue, which is slow; it is cached afterwards.
"""

import argparse
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.hazard.cross_sections import (
    CrossSection,
    find_crossings,
    sample_elevation,
    sections_to_geodataframe,
)
from landloss.hazard.liquefaction.waterways import get_waterways
from landloss.io.area_of_interest import get_study_areas
from scripts.landloss.paths import RESEARCH_DIR

# River names carry macrons, which the default Windows console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = RESEARCH_DIR / "hazard" / "cross_sections" / "fig"
DPI = 200

GROUND_COLOUR = "#8c6d46"
FILL_COLOUR = "#d9c7ad"
RIVER_COLOUR = "#1f78b4"
SECTION_COLOUR = "#c0392b"

# Sections are centred on a point and given a bearing, so the Lower Hutt pair is
# perpendicular by construction rather than by hand-checked endpoints.
#
# The Hutt Valley geometry is measured, not assumed. Sampling the DEM on a 250 m
# grid over Lower Hutt and fitting the principal axis of the land between 0.5 and
# 25 m -- the alluvial floor -- gives an axis of 52.6 degrees, a floor 3.0 km wide
# and 9.6 km long, centred on 1763243, 5438316. Points south of the Petone
# foreshore are excluded from that fit: the Eastbourne coastal strip is just as
# flat but belongs to the harbour edge rather than to the valley, and including it
# swings the axis and drags the centre into the sea.
HUTT_CENTRE = (1763243.0, 5438316.0)
HUTT_AXIS_BEARING = 52.6

HUTT_ACROSS = CrossSection(
    name="Lower Hutt across the valley",
    centre=HUTT_CENTRE,
    bearing=(HUTT_AXIS_BEARING + 90) % 360,
    length_m=7000.0,
    description="Across the Hutt Valley, western hills to eastern hills",
)

SECTIONS = [
    CrossSection(
        name="Wainuiomata River",
        centre=(1763000.0, 5426800.0),
        bearing=129.0,
        length_m=4000.0,
        description="Across the settled Wainuiomata valley floor",
    ),
    CrossSection(
        name="Ōrongorongo River",
        centre=(1763436.0, 5419000.0),
        bearing=134.0,
        length_m=4000.0,
        description="Across the undeveloped Ōrongorongo valley",
    ),
    HUTT_ACROSS,
    # 9.6 km is the measured length of the valley floor, so the section runs
    # from the Petone foreshore to the upper valley without ending in the
    # harbour, where the DEM reads a flat zero that looks like more floor.
    HUTT_ACROSS.perpendicular(
        name="Lower Hutt along the valley",
        length_m=9600.0,
        description=(
            "Down the Hutt Valley from its northeastern flank to the Petone "
            "foreshore, perpendicular to the section across it"
        ),
    ),
]

RULE = "-" * 72


def slugify(name):
    """Turn a section name into a file name stem."""
    cleaned = name.lower().replace("ō", "o").replace("ā", "a")
    return "".join(c if c.isalnum() else "_" for c in cleaned).strip("_")


def plot_section(section, profile, crossings):
    """Plot one elevation profile, marking where it crosses a watercourse."""
    fig, ax = plt.subplots(figsize=(9.0, 3.6))

    ax.fill_between(
        profile["distance_m"],
        profile["elevation_m"],
        profile["elevation_m"].min() - 5,
        color=FILL_COLOUR,
        zorder=1,
    )
    ax.plot(
        profile["distance_m"],
        profile["elevation_m"],
        color=GROUND_COLOUR,
        linewidth=1.0,
        zorder=2,
    )

    for row in crossings.itertuples():
        ax.axvline(
            row.distance_m, color=RIVER_COLOUR, linewidth=0.8, linestyle="--", zorder=3
        )

    if not crossings.empty:
        # One label for the legend rather than one per crossing, which for a
        # braided reach would be a wall of identical entries.
        ax.plot(
            [],
            [],
            color=RIVER_COLOUR,
            linewidth=0.8,
            linestyle="--",
            label=f"Watercourse crossing ({len(crossings)})",
        )
        ax.legend(loc="upper right", fontsize=8)

    ax.set_xlim(0, profile["distance_m"].max())
    ax.set_ylim(profile["elevation_m"].min() - 5, profile["elevation_m"].max() + 15)
    ax.set_xlabel(f"Distance along section (m), bearing {section.bearing:.0f}°")
    ax.set_ylabel("Elevation (m)")
    ax.grid(visible=True, linewidth=0.3, alpha=0.5)

    # Vertical exaggeration is the first thing a reader needs to know; without
    # it every valley looks like a gorge.
    span_x = profile["distance_m"].max()
    span_y = ax.get_ylim()[1] - ax.get_ylim()[0]
    exaggeration = (span_x / span_y) * (3.6 / 9.0)
    ax.set_title(
        f"{section.name} — {section.description}\n"
        f"1 m LiDAR DEM, vertical exaggeration approx {exaggeration:.0f}x",
        fontsize=9,
    )
    fig.tight_layout()
    return fig


def plot_locality(sections, waterways, study_areas):
    """Plot where the sections sit, so each profile can be placed on the ground."""
    lines = sections_to_geodataframe(sections)
    fig, ax = plt.subplots(figsize=(7.0, 7.0))

    waterways.plot(ax=ax, color=RIVER_COLOUR, linewidth=0.4, zorder=2)
    study_areas.boundary.plot(
        ax=ax, color="#4d4d4d", linewidth=0.6, linestyle="--", zorder=3
    )
    lines.plot(ax=ax, color=SECTION_COLOUR, linewidth=2.0, zorder=4)

    # Labelled at an end rather than the centroid: the Lower Hutt pair crosses at
    # its midpoint, so centroid labels print on top of one another.
    for index, (name, geom) in enumerate(
        zip(lines["name"], lines.geometry, strict=True)
    ):
        end = geom.coords[0] if index % 2 == 0 else geom.coords[-1]
        ax.annotate(
            name,
            xy=end,
            xytext=(6, 6 if index % 2 == 0 else -12),
            textcoords="offset points",
            fontsize=7,
            color=SECTION_COLOUR,
            weight="bold",
            path_effects=[pe.withStroke(linewidth=2.5, foreground="white")],
        )

    # Frame on the sections rather than the whole study area, with a margin.
    minx, miny, maxx, maxy = lines.total_bounds
    pad = 4000
    extent = study_areas.copy()
    style_basemap_ax(ax, extent, set_limits=False)
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_title("Cross-section locations", fontsize=10)
    fig.tight_layout()
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spacing",
        type=float,
        default=1.0,
        help="Sample spacing along each section, in metres.",
    )
    parser.add_argument(
        "--out", type=Path, default=FIG_DIR, help="Directory to write figures into."
    )
    parser.add_argument(
        "--locality-only",
        action="store_true",
        help="Redraw just the locality map, skipping the DEM sampling.",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    waterways = get_waterways(
        bbox=tuple(float(v) for v in study_areas.total_bounds), clip_to=study_areas
    )

    for section in [] if args.locality_only else SECTIONS:
        print(RULE)
        print(
            f"{section.name} — bearing {section.bearing:.0f}°, "
            f"{section.length_m:,.0f} m"
        )

        profile = sample_elevation(section, spacing_m=args.spacing)
        covered = profile["elevation_m"].notna().sum()
        print(f"  sampled {len(profile):,} points, {covered:,} with DEM coverage")

        if covered == 0:
            print("  no LiDAR coverage on this section; skipping")
            continue

        print(
            f"  elevation {profile['elevation_m'].min():.1f} to "
            f"{profile['elevation_m'].max():.1f} m"
        )

        crossings = find_crossings(section, waterways)
        named = sorted(set(crossings["name"].dropna()))
        print(
            f"  crosses {len(crossings)} watercourse(s)"
            + (f": {', '.join(named)}" if named else "")
        )

        fig = plot_section(section, profile, crossings)
        path = args.out / f"section_{slugify(section.name)}.png"
        fig.savefig(path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"  wrote {path.name}")

    print(RULE)
    fig = plot_locality(SECTIONS, waterways, study_areas)
    path = args.out / "section_locations.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
