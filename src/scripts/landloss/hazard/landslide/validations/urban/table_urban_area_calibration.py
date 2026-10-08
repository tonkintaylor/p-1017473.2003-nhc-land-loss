"""Calibrate the localised (no wall) urban fragility to the record and the polygon anchors.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/urban/table_urban_area_calibration.py

Run landslide steps 3, 4 and 12 (the topographic position, the ground map and
the bare zones), shaking steps 2 and 3 (the site class and PGV grids) and
landslide step 8 for ``config.WORLD_ID`` first, over ``config.EXTENT``.

**The adopted fit** is the one the project lead chose on 2026-10-07
(``area_calibration.fit_record_and_polygons``). It is fitted to two kinds of
target. The first is the Kaikoura record A16: an expected damaged share of
0.001 of the whole non-flat pilot at 0.15 g on rock. It weighs as much as the
polygon anchors together. The second is the polygon anchors A17 to A21: the
mean failure probability of the matching bare polygons over each anchor's PGA
range. Kingsbury's High scenario 2 share (A12, 0.25) is only an upper limit
the curve must stay under. His other zone shares are reported as checks.

**Two rejected alternatives** are kept beside it. Both fit Kingsbury's
damaged-area shares, and both are described below. The first is the method
first agreed with the lead (2026-10-07), fitted to A10 to A12 on the whole
non-flat pilot. The second is the same fit on only the footprint cells.
Kingsbury's Table 1 classes describe how much of a zone's ground is damaged.
So the zone fractions of ``urban-fragility-anchors.csv`` (``measure`` of
``zone_area``) are compared with the expected share of the non-flat ground
that lies in the evacuated or inundated zone of a failed bare polygon
(``landloss.hazard.landslide.urban.area_calibration``). Shared by every fit:

1. **The polygons.** Landslide step 12's bare zones (no wall anywhere), made
   into one row per polygon as step 8 makes a world's zones
   (``face_polygons.face_polygons`` and ``with_amplification``), every one
   on the localised curve. Step 8's model files are a world's walled zones,
   whose polygons differ, so they are not read for this.
2. **The reference area.** The non-flat pieces of the step 4 ground map on a
   2 m grid; runout onto flat land does not count. The whole non-flat pilot
   is treated as Kingsbury High (the lead's choice), so the fit is to the
   High zone fractions A10 to A12.
3. **The demand.** Kingsbury's PGAs are on bedrock: each polygon's PGV is the
   rock PGA times its site PGV per g of site class I PGA, both TS1170.5 grids
   at ``config.RETURN_PERIOD_YR``. Each scenario's share is averaged over five
   log-spaced PGAs across its range.
4. **The fit.** The median keeps its fall of five times from rating 0 to
   150; its scale and the dispersion are fitted by least squares on the
   logits.
5. **The checks.** Each fit reports the anchors it was not fitted to. These
   are the Kingsbury zone fractions: the High ones on the whole pilot, and
   each zone's on the non-flat cells nearest a polygon of that zone. They
   also include A16, the polygon anchors A17 to A21, the A12 upper limit,
   and the wall type medians of step 8's walled polygons against the no-wall
   median on the same polygons.

Prints the constants to adopt and every check, and writes eight CSVs under
``report/hazard/landslide/urban-fragility/tab/``. Results are written up in
``urban_area_calibration_findings.md`` beside this script. Changes nothing in
the model itself: an adopted pair goes into
``landloss.hazard.landslide.urban.fragility`` and the dispersion into
``landloss.domain.constants.LOCALISED_FRAGILITY_BETA`` by hand.
"""

import sys
from typing import NamedTuple

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.common.utils.terrain import sample_at_points
from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import (
    area_calibration,
    face_polygons,
    fragility,
    geometry,
)
from landloss.hazard.shaking.site_class import (
    ROCK_SITE_CLASS,
    demand_on_site_class_grid,
)
from landloss.io.area_of_interest import get_area_of_interest
from landloss.io.ts1170 import get_ts1170_pga
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility.gen_urban_slope_fragility import (
    read_grid,
    read_step12_inputs,
    representative_points,
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    zones_path,
)
from scripts.landloss.hazard.landslide.validations.urban import config
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    read_site_class,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv.gen_pgv import output_path
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TAB_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-fragility" / "tab"
FIT_NAME = "urban-area-calibration-fit.csv"
ZONE_SHARES_NAME = "urban-area-calibration-zone-shares.csv"
POLYGON_ANCHORS_NAME = "urban-area-calibration-polygon-anchors.csv"
WALLS_NAME = "urban-area-calibration-walls.csv"
FOOTPRINT_NAME = "urban-area-calibration-footprint-reference.csv"
POLYGONS_NAME = "urban-area-calibration-polygons.csv"
LIMITS_NAME = "urban-area-calibration-upper-limit.csv"

BARE_SCENARIO = "bare"

# The adopted fit's record (Kaikoura, no urban failures at 0.15 g on rock)
# and the Kingsbury share it is held under (High, scenario 2).
RECORD_ANCHOR = "A16"
UPPER_LIMIT_ANCHOR = "A12"

# The rejected area fits read the High zone's three scenarios, with the whole
# non-flat pilot read as High.
FIT_ZONE = 4

# The zones the allocation check reports; Moderate is the one asked for.
MODERATE_ZONE = 3
CHECK_ZONES = (2, MODERATE_ZONE, 4)

# The placeholders the calibration replaced, kept to show what it moved.
PREVIOUS_CURVE = area_calibration.LocalisedCurve(3.0, 0.6, 0.6)

# A wall type's median within this factor of the no-wall median on the same
# polygons reads as about equal to it.
ABOUT_EQUAL_FACTOR = 1.25

# Kingsbury section 4.4.2: seismically designed retained slopes are not in the
# high category, poorly built crib, shotcrete and light walls are.
ENGINEERED_TYPES = (
    "engineered",
    "timber_pole_post_1992",
    "concrete_block",
    "reinforced_concrete",
)
POOR_TYPES = ("brick_rock", "garden_timber", "crib_gabion")

RULE = "-" * 72


class CalibrationInputs(NamedTuple):
    """Everything the calibration and its figure read, built once.

    Attributes:
        polygons: The bare polygons, one row each, with ``pgv_per_rock_pga``
            and ``pgv_per_site_pga``.
        grid: The non-flat reference grid.
        incidence: Which reference cells each polygon's footprint covers.
        zone_of_cell: The Kingsbury zone of the polygon nearest each
            reference cell.
        anchors: The packaged anchor table.
    """

    polygons: gpd.GeoDataFrame
    grid: area_calibration.AreaGrid
    incidence: object
    zone_of_cell: np.ndarray
    anchors: pd.DataFrame

    def on_rock(self) -> area_calibration.LocalisedPolygons:
        """The polygons for a bedrock demand."""
        return polygon_arrays(self.polygons, "pgv_per_rock_pga")

    def zone_area_anchors(self) -> pd.DataFrame:
        """The anchors whose fraction is a share of an area."""
        return self.anchors[self.anchors["measure"] == fragility.ZONE_AREA_MEASURE]


def polygon_arrays(polygons, ratio_column):
    """Pack the columns the localised fragility reads off each polygon."""
    return area_calibration.LocalisedPolygons(
        rating=polygons["continuous_rating"].to_numpy(dtype=float),
        amp_factor=polygons["amp_factor"].to_numpy(dtype=float),
        pgv_per_g=polygons[ratio_column].to_numpy(dtype=float),
    )


def committed_curve():
    """The localised curve the model carries now."""
    return area_calibration.LocalisedCurve(
        fragility.LOCALISED_THETA_AT_ZERO_RATING_M_S,
        fragility.LOCALISED_THETA_AT_MAX_RATING_M_S,
        constants.LOCALISED_FRAGILITY_BETA,
    )


# --- reading --------------------------------------------------------------------


def read_bare_polygons(*, extent):
    """Step 12's bare zones as one row per polygon, scored and amplified.

    The same path step 8 takes for a world's zones (``face_polygons`` with
    the extent's box, then the amplification on step 3's 100 m topographic
    position), on the bare scenario.

    Returns:
        ``(polygons, ground_map)``.
    """
    elements, units, ground_map = read_step12_inputs(extent=extent)
    zones = gpd.read_parquet(zones_path(BARE_SCENARIO, extent=extent))
    aoi = get_area_of_interest(extent)
    bbox = None if aoi is None else aoi.bbox(zones.crs)
    polygons = face_polygons.face_polygons(
        zones, elements, units, ground_map, bbox=bbox
    )
    tpi = sample_at_points(
        terrain_path("topographic-position-100m", extent=extent),
        representative_points(polygons),
    )
    polygons = face_polygons.with_amplification(polygons, tpi.to_numpy(dtype=float))
    print(
        f"{len(polygons):,} bare polygons inside the extent "
        f"(of {zones['polygon'].nunique():,} in the zones file)"
    )
    return polygons, ground_map


def add_demand_ratios(polygons, *, extent, return_period_yr):
    """Add each polygon's site PGV per g of rock PGA and of site PGA.

    The site PGV is shaking step 3's grid; the rock PGA the TS1170.5 site
    class I grid, the site PGA the grid of each cell's own class, as step 8
    reads it.
    """
    pgv = read_grid(
        output_path("pgv", return_period_yr=return_period_yr, extent=extent)
    )
    points = representative_points(polygons)
    rock = get_ts1170_pga(return_period_yr, ROCK_SITE_CLASS)
    per_rock = area_calibration.pgv_per_rock_pga_m_s_per_g(pgv, rock, points)
    site_pga = demand_on_site_class_grid(
        get_ts1170_pga,
        read_site_class(extent=extent),
        return_period_yr=return_period_yr,
    )
    per_site = fragility.pgv_pga_ratio_m_s_per_g(pgv, site_pga, points)
    out = polygons.copy()
    out["pgv_per_rock_pga"] = per_rock.to_numpy(dtype=float)
    out["pgv_per_site_pga"] = per_site.to_numpy(dtype=float)
    missing = ~np.isfinite(out[["pgv_per_rock_pga", "pgv_per_site_pga"]]).all(axis=1)
    if missing.any():
        msg = f"{int(missing.sum())} bare polygons read no demand ratio off the grids."
        raise ValueError(msg)
    return out


def read_inputs(*, extent, return_period_yr):
    """Build the polygons, the reference grid and the footprint incidence."""
    polygons, ground_map = read_bare_polygons(extent=extent)
    polygons = add_demand_ratios(
        polygons, extent=extent, return_period_yr=return_period_yr
    )
    non_flat = ground_map.loc[~ground_map["is_flatland"].astype(bool), "geometry"]
    grid = area_calibration.reference_grid(non_flat)
    footprints = area_calibration.damage_footprints(
        gpd.GeoSeries(polygons[geometry.EVACUATED], crs=polygons.crs),
        gpd.GeoSeries(polygons[geometry.INUNDATED], crs=polygons.crs),
    )
    incidence = area_calibration.footprint_incidence(footprints, grid)
    zone_of_cell = area_calibration.nearest_labels(
        grid,
        gpd.GeoSeries(polygons[geometry.EVACUATED], crs=polygons.crs),
        polygons["kingsbury_zone"].fillna(0).to_numpy(dtype=np.int64),
    )
    covered = np.asarray(incidence.sum(axis=1)).ravel() > 0
    print(
        f"Non-flat reference ground: {grid.reference_area_m2 / 1e6:.3f} km2 on "
        f"{grid.cell_size_m:g} m cells; {covered.mean():.1%} of it under a "
        "footprint (evacuated or inundated)"
    )
    return CalibrationInputs(
        polygons=polygons,
        grid=grid,
        incidence=incidence,
        zone_of_cell=zone_of_cell,
        anchors=fragility.load_urban_fragility_anchors(),
    )


# --- the fit and the checks -----------------------------------------------------


def fit_targets(inputs):
    """The High zone's three zone-area anchors."""
    zone_area = inputs.zone_area_anchors()
    return zone_area[zone_area["zone"] == FIT_ZONE].reset_index(drop=True)


def covered_cells(inputs):
    """The reference cells under at least one footprint."""
    return np.asarray(inputs.incidence.sum(axis=1)).ravel() > 0


def fit(inputs, *, cells=None):
    """Fit the localised curve to the High zone fractions (rejected).

    Args:
        inputs: From :func:`read_inputs`.
        cells: The reference cells; the whole non-flat pilot (the method first
            agreed) by default.

    Returns:
        The ``AreaFit``.
    """
    return area_calibration.fit_area_calibration(
        inputs.incidence, inputs.on_rock(), fit_targets(inputs), cells=cells
    )


def anchor_row(inputs, anchor_id):
    """One anchor's row."""
    return inputs.anchors[inputs.anchors["anchor_id"] == anchor_id].iloc[0]


def polygon_targets(inputs):
    """Every polygon anchor with its matching bare polygons.

    A recorded demand (``demand_at`` ``site``) reads the polygon's PGV per g
    of site PGA and is not amplified again; a bedrock one reads its PGV per g
    of rock PGA.
    """
    polygons = inputs.polygons
    anchors = inputs.anchors[inputs.anchors["measure"] == fragility.POLYGON_MEASURE]
    targets = []
    for _, anchor in anchors.iterrows():
        mask = area_calibration.anchor_polygon_mask(
            anchor,
            position=polygons[geometry.WALL_POSITION_COLUMN].to_numpy(dtype=object),
            slope_degrees=polygons[geometry.SLOPE_COLUMN].to_numpy(dtype=float),
            material=polygons[geometry.MATERIAL_COLUMN].to_numpy(dtype=object),
        )
        site = anchor["demand_at"] == fragility.SITE_DEMAND
        targets.append(
            area_calibration.PolygonTarget(
                anchor_id=str(anchor["anchor_id"]),
                polygons=polygon_arrays(
                    polygons, "pgv_per_site_pga" if site else "pgv_per_rock_pga"
                ).subset(mask),
                pga_g_min=float(anchor["pga_rock_g_min"]),
                pga_g_max=float(anchor["pga_rock_g_max"]),
                fail_fraction=float(anchor["fail_fraction"]),
                amplified=not site,
            )
        )
    return targets


def fit_adopted(inputs):
    """Fit the localised curve to the Kaikoura record and the polygon anchors.

    The project lead's choice of 2026-10-07; the record weighs as much as the
    polygon anchors together.
    """
    return area_calibration.fit_record_and_polygons(
        inputs.incidence,
        inputs.on_rock(),
        anchor_row(inputs, RECORD_ANCHOR),
        polygon_targets(inputs),
    )


class Fits(NamedTuple):
    """The adopted fit and the two rejected area fits.

    Attributes:
        adopted: To the Kaikoura record and the polygon anchors.
        area: To Kingsbury's High shares on the whole non-flat pilot.
        footprint: To the same shares on the footprint cells alone.
    """

    adopted: area_calibration.AreaFit
    area: area_calibration.AreaFit
    footprint: area_calibration.AreaFit


def fit_all(inputs):
    """Run the adopted fit and the two rejected ones."""
    return Fits(
        adopted=fit_adopted(inputs),
        area=fit(inputs),
        footprint=fit(inputs, cells=covered_cells(inputs)),
    )


def curves_to_compare(fits):
    """Every curve to report, by name.

    ``adopted``, ``committed`` (what the model carries now), ``previous``
    where it differs from the committed curve, and the rejected ``area`` and
    ``footprint`` fits.
    """
    curves = {"adopted": fits.adopted.curve, "committed": committed_curve()}
    if tuple(PREVIOUS_CURVE) != tuple(curves["committed"]):
        curves["previous"] = PREVIOUS_CURVE
    curves["area"] = fits.area.curve
    curves["footprint"] = fits.footprint.curve
    return curves


def upper_limit_table(inputs, curves):
    """Check each curve against Kingsbury's High scenario 2 share, a ceiling."""
    limit = anchor_row(inputs, UPPER_LIMIT_ANCHOR)
    rows = []
    for name, curve in curves.items():
        share, within = area_calibration.within_upper_limit(
            inputs.incidence, inputs.on_rock(), curve, limit
        )
        rows.append(
            {
                "curve": name,
                "anchor_id": UPPER_LIMIT_ANCHOR,
                "reference": "whole non-flat pilot",
                "pga_rock_g_min": limit["pga_rock_g_min"],
                "pga_rock_g_max": limit["pga_rock_g_max"],
                "upper_limit": limit["fail_fraction"],
                "footprint_coverage": covered_cells(inputs).mean(),
                "predicted": share,
                "within_limit": within,
            }
        )
    return pd.DataFrame(rows)


def zone_role(anchor_id, *, whole):
    """What a zone anchor on a reference is to the fits."""
    if not whole:
        return "check"
    if anchor_id == RECORD_ANCHOR:
        return "adopted fit"
    if anchor_id == UPPER_LIMIT_ANCHOR:
        return "upper limit; rejected area fit"
    return "rejected area fit"


def zone_share_table(inputs, curves):
    """The predicted share of each zone anchor's reference area, per curve.

    The fit's High anchors and Kaikoura are read on the whole non-flat pilot;
    every zone anchor of ``CHECK_ZONES`` is also read on the cells nearest a
    polygon of its own zone.
    """
    polygons = inputs.on_rock()
    zone_area = inputs.zone_area_anchors()
    references = [
        ("whole non-flat pilot", None, row)
        for _, row in zone_area.iterrows()
        if row["zone"] == FIT_ZONE or pd.isna(row["zone"])
    ]
    for zone in CHECK_ZONES:
        cells = inputs.zone_of_cell == zone
        if not cells.any():
            # No polygon of the zone, so no ground to read its anchors on.
            continue
        label = f"cells nearest a zone {zone} polygon"
        references += [
            (label, cells, row)
            for _, row in zone_area.iterrows()
            if row["zone"] == zone
        ]
    rows = []
    for reference, cells, anchor in references:
        role = zone_role(anchor["anchor_id"], whole=reference.startswith("whole"))
        row = {
            "anchor_id": anchor["anchor_id"],
            "role": role,
            "reference": reference,
            "reference_area_km2": (
                inputs.grid.reference_area_m2
                if cells is None
                else cells.sum() * inputs.grid.cell_size_m**2
            )
            / 1e6,
            "scenario": anchor["scenario"],
            "pga_rock_g_min": anchor["pga_rock_g_min"],
            "pga_rock_g_max": anchor["pga_rock_g_max"],
            "class_word": anchor["class_word"],
            "target": anchor["fail_fraction"],
        }
        for name, curve in curves.items():
            if name == "footprint":
                # Fitted on another reference; footprint_table reads it there.
                continue
            row[f"predicted_{name}"] = area_calibration.scenario_share(
                inputs.incidence,
                polygons,
                curve,
                pga_rock_g_min=anchor["pga_rock_g_min"],
                pga_rock_g_max=anchor["pga_rock_g_max"],
                cells=cells,
            )
        rows.append(row)
    return pd.DataFrame(rows)


def polygon_anchor_table(inputs, curves):
    """The mean failure probability of each polygon anchor's matching polygons.

    The adopted fit is fitted to these; for every other curve they are a check.
    """
    anchors = inputs.anchors.set_index("anchor_id")
    rows = []
    for target in polygon_targets(inputs):
        anchor = anchors.loc[target.anchor_id]
        row = {
            "anchor_id": target.anchor_id,
            "role": "adopted fit",
            "source": anchor["source"],
            "applies_to": anchor["applies_to"],
            "slope_min_deg": anchor["slope_min_deg"],
            "slope_max_deg": anchor["slope_max_deg"],
            "material": anchor["material"],
            "demand_at": anchor["demand_at"],
            "pga_g_min": target.pga_g_min,
            "pga_g_max": target.pga_g_max,
            "n_polygons": len(target.polygons.rating),
            "target": target.fail_fraction,
        }
        for name, curve in curves.items():
            row[f"predicted_{name}"] = area_calibration.mean_polygon_failure(
                target.polygons,
                curve,
                pga_g_min=target.pga_g_min,
                pga_g_max=target.pga_g_max,
                amplified=target.amplified,
            )
        rows.append(row)
    return pd.DataFrame(rows)


def wall_table(model, curves):
    """Compare each wall type's median with the no-wall median on its polygons.

    Both medians are the base, before the amplification and rate factors,
    which divide both alike: the wall's is its type curve converted to PGV at
    the polygon's site ratio, the no-wall one the localised median at the
    polygon's own rating on each curve of ``curves``.
    """
    return pd.concat(
        [_wall_rows(model, curve).assign(curve=name) for name, curve in curves.items()],
        ignore_index=True,
    )


def _wall_rows(model, curve):
    walled = model[model["fragility_basis"] == fragility.WALL_BASIS].copy()
    walled["no_wall_theta_base"] = fragility.localised_theta_base_m_s(
        walled["continuous_rating"].to_numpy(dtype=float),
        theta_at_zero_rating_m_s=curve.theta_at_zero_rating_m_s,
        theta_at_max_rating_m_s=curve.theta_at_max_rating_m_s,
    )
    walled["ratio"] = walled["theta_base"] / walled["no_wall_theta_base"]
    rows = []
    for wall_type, group in walled.groupby(fragility.WALL_TYPE_COLUMN):
        ratio = float(group["ratio"].median())
        if ratio > ABOUT_EQUAL_FACTOR:
            reading = "stronger than no wall"
        elif ratio < 1.0 / ABOUT_EQUAL_FACTOR:
            reading = "weaker than no wall"
        else:
            reading = "about equal to no wall"
        expected = (
            "stronger"
            if wall_type in ENGINEERED_TYPES
            else "about equal"
            if wall_type in POOR_TYPES
            else "between"
        )
        rows.append(
            {
                "wall_type": wall_type,
                "n_polygons": len(group),
                "median_wall_theta_base_m_s": float(group["theta_base"].median()),
                "median_no_wall_theta_base_m_s": float(
                    group["no_wall_theta_base"].median()
                ),
                "median_ratio": ratio,
                "share_wall_stronger": float((group["ratio"] > 1.0).mean()),
                "median_wall_beta": float(group["beta"].median()),
                "no_wall_beta": curve.beta,
                "reading": reading,
                "kingsbury_expects": expected,
            }
        )
    return pd.DataFrame(rows).sort_values("median_ratio", ascending=False)


def polygon_summary(inputs):
    """Describe the bare polygons the calibration reads."""
    polygons = inputs.polygons
    rows = []
    for zone, group in polygons.groupby("kingsbury_zone", dropna=False):
        cells = inputs.zone_of_cell == (0 if pd.isna(zone) else int(zone))
        rows.append(
            {
                "kingsbury_zone": zone,
                "zone_label": susceptibility.ZONE_LABELS.get(zone, "no rating"),
                "n_polygons": len(group),
                "median_rating": float(group["continuous_rating"].median()),
                "median_amp_factor": float(group["amp_factor"].median()),
                "median_pgv_per_rock_pga_m_s_per_g": float(
                    group["pgv_per_rock_pga"].median()
                ),
                "allocated_area_km2": cells.sum() * inputs.grid.cell_size_m**2 / 1e6,
            }
        )
    return pd.DataFrame(rows)


def fit_table(fits):
    """The fitted constants beside the committed (and previous) ones."""
    residuals = {
        "adopted": fits.adopted.rms_logit_residual,
        "area": fits.area.rms_logit_residual,
        "footprint": fits.footprint.rms_logit_residual,
    }
    targets = {
        "adopted": "A16 on the whole non-flat pilot (weight 5) and A17-A21 "
        "(adopted, the lead 2026-10-07)",
        "area": "A10-A12 on the whole non-flat pilot (rejected)",
        "footprint": "A10-A12 on the non-flat cells under a footprint (rejected)",
    }
    rows = [
        {
            "curve": name,
            "targets": targets.get(name, ""),
            "theta_at_zero_rating_m_s": curve.theta_at_zero_rating_m_s,
            "theta_at_max_rating_m_s": curve.theta_at_max_rating_m_s,
            "beta": curve.beta,
            "rms_logit_residual": residuals.get(name, np.nan),
        }
        for name, curve in curves_to_compare(fits).items()
    ]
    return pd.DataFrame(rows)


def footprint_table(inputs, footprint_fit):
    """The footprint alternative's shares on its own reference.

    The High anchors it is fitted to and the Kaikoura record on every
    footprint cell, and the Moderate anchors on the footprint cells nearest a
    Moderate polygon.
    """
    covered = covered_cells(inputs)
    rows = []
    for _, anchor in inputs.zone_area_anchors().iterrows():
        if anchor["zone"] == FIT_ZONE or pd.isna(anchor["zone"]):
            cells, reference = covered, "footprint cells"
        elif anchor["zone"] == MODERATE_ZONE:
            cells = covered & (inputs.zone_of_cell == MODERATE_ZONE)
            reference = f"footprint cells nearest a zone {MODERATE_ZONE} polygon"
        else:
            continue
        rows.append(
            {
                "anchor_id": anchor["anchor_id"],
                "role": "rejected footprint fit"
                if anchor["zone"] == FIT_ZONE
                else "check",
                "reference": reference,
                "reference_area_km2": cells.sum() * inputs.grid.cell_size_m**2 / 1e6,
                "pga_rock_g_min": anchor["pga_rock_g_min"],
                "pga_rock_g_max": anchor["pga_rock_g_max"],
                "target": anchor["fail_fraction"],
                "predicted_footprint": area_calibration.scenario_share(
                    inputs.incidence,
                    inputs.on_rock(),
                    footprint_fit.curve,
                    pga_rock_g_min=anchor["pga_rock_g_min"],
                    pga_rock_g_max=anchor["pga_rock_g_max"],
                    cells=cells,
                ),
            }
        )
    return pd.DataFrame(rows)


# --- printing -------------------------------------------------------------------


def show(title, table):
    """Print a titled table."""
    print(RULE)
    print(title)
    with pd.option_context(
        "display.width", 200, "display.max_columns", 30, "display.precision", 4
    ):
        print(table.to_string(index=False))


def report_fit(fits, limits):
    """Print the constants to adopt, the rejected fits and the upper limit."""
    print(RULE)
    for name, one_fit in fits._asdict().items():
        curve = one_fit.curve
        label = "ADOPTED" if name == "adopted" else f"rejected ({name})"
        print(
            f"{label}: {curve.theta_at_zero_rating_m_s:.4f} m/s at rating 0, "
            f"{curve.theta_at_max_rating_m_s:.4f} m/s at "
            f"{susceptibility.MAX_RATING}, beta {curve.beta:.4f}; RMS logit "
            f"residual {one_fit.rms_logit_residual:.4f}"
        )
    adopted = limits[limits["curve"] == "adopted"].iloc[0]
    print(
        f"{UPPER_LIMIT_ANCHOR} upper limit {adopted['upper_limit']:g}: the adopted "
        f"curve's share is {adopted['predicted']:.4f} "
        f"({'within' if adopted['within_limit'] else 'ABOVE'} the limit; the "
        f"footprints cover {adopted['footprint_coverage']:.1%})"
    )
    print(
        "To adopt: set LOCALISED_THETA_AT_ZERO_RATING_M_S and "
        "LOCALISED_THETA_AT_MAX_RATING_M_S in landloss.hazard.landslide.urban."
        "fragility, and LOCALISED_FRAGILITY_BETA in landloss.domain.constants, "
        "to the ADOPTED values."
    )


def write(table, name):
    """Write one table under the report's tab directory."""
    path = TAB_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    print(f"Wrote {path}")


def main(*, extent, world_id, return_period_yr):
    """Fit the localised curve, the adopted way and the rejected ones, and check.

    Args:
        extent: The extent to read, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        world_id: The exposure world whose step 8 model the walls are
            compared on.
        return_period_yr: The return period of the TS1170.5 grids.
    """
    inputs = read_inputs(extent=extent, return_period_yr=return_period_yr)
    write_tables(inputs, model_path=urban_slope_model_path(world_id, extent=extent))


def write_tables(inputs, *, model_path):
    """Fit, print and write every table from the built inputs.

    Args:
        inputs: From :func:`read_inputs`.
        model_path: Step 8's model of the world the walls are compared on;
            the wall table is skipped where it does not exist.
    """
    fits = fit_all(inputs)
    curves = curves_to_compare(fits)
    limits = upper_limit_table(inputs, curves)
    report_fit(fits, limits)

    tables = {
        FIT_NAME: fit_table(fits),
        LIMITS_NAME: limits,
        POLYGONS_NAME: polygon_summary(inputs),
        ZONE_SHARES_NAME: zone_share_table(inputs, curves),
        POLYGON_ANCHORS_NAME: polygon_anchor_table(inputs, curves),
        FOOTPRINT_NAME: footprint_table(inputs, fits.footprint),
    }
    if model_path.exists():
        model = gpd.read_parquet(model_path)
        tables[WALLS_NAME] = wall_table(
            model, {name: curves[name] for name in ("adopted", "committed", "area")}
        )
    else:
        print(f"{model_path} not found: run step 8 for the wall comparison.")
    for name, table in tables.items():
        show(name, table)
    print(RULE)
    for name, table in tables.items():
        write(table, name)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        return_period_yr=config.RETURN_PERIOD_YR,
    )
