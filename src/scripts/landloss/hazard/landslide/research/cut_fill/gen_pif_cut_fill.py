"""Compare three natural surfaces for classing the pifs as cut or fill.

The research behind ground step 5. Ground step 5 classes every pif against its
**anchor** surface, a robust quadratic fitted to the ground off the faces
(:mod:`landloss.hazard.landslide.pif_cut_fill`, where the method, its walk to
the foot of each face and its thresholds are written out). This script runs
that and two simpler surfaces beside it, so the three can be compared:

- **rolling**: the DEM averaged over a ``config.ROLLING_WINDOW_M`` square
  window (:func:`rolling_mean`). Wider than one platform, so a terrace's cut
  and fill average out.
- **poly**: a quadratic fitted by plain least squares to every DEM cell within
  ``config.FIT_RADIUS_M`` of each pif's points, faces included.

Both are classed by the same rule as the anchor surface
(:func:`landloss.hazard.landslide.pif_cut_fill.classify`), with no uncertain
class, as neither has a scatter to set one. The share of a pif's pips above the
rolling mean (the first idea tried) is kept too, as
``share_pips_above_rolling``.

Run from the repository root, after ground step 4::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/cut_fill/gen_pif_cut_fill.py

Settings are in ``config.py``. Writes the pif and pip tables and the rolling
mean under ``temp/ground/``, and the class counts and their agreement
with the GNS SLIDE cut slope and fill body polygons under
``research/hazard/landslide/pif_cut_fill/tab/``.
"""

import time

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

from landloss.hazard.landslide.instability_zones import find_pips, read_siz_table
from landloss.hazard.landslide.pif_cut_fill import (
    CLASSES,
    QUADRATIC_TERMS,
    classify,
    eval_quadratic,
    fit_quadratic,
    gen_pif_cut_fill,
)
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.research.cut_fill import config
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import WORK_DIR, get_dem
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import siz_table_path
from scripts.landloss.ground.steps.s5_pif_cut_fill.gen_pif_cut_fill import (
    pip_cells,
)
from scripts.landloss.paths import RESEARCH_DIR

TAB_DIR = RESEARCH_DIR / "hazard" / "landslide" / "pif_cut_fill" / "tab"
METHODS = ("rolling", "poly", "anchor")
FIT_COLUMNS = [*QUADRATIC_TERMS, "centre_x", "centre_y", "radius_m", "scale_m"]

# The siz table's own evidence carried onto the result, for the checks.
EVIDENCE = ["in_slide_cut", "in_slide_fill", "gns_wall", "ground_modification"]


def pif_table_path(*, extent):
    """Where the class of every pif, by every method, is written."""
    return WORK_DIR / f"pif-cut-fill{extent_suffix(extent)}.parquet"


def pip_table_path(*, extent):
    """Where every pip, its foot and every surface at both are written."""
    return WORK_DIR / f"pif-cut-fill-pips{extent_suffix(extent)}.parquet"


def rolling_mean_path(*, extent):
    """Where the rolling mean surface is written, on the 1 m DEM's grid."""
    return WORK_DIR / f"pif-cut-fill-rolling-mean{extent_suffix(extent)}.tif"


def rolling_mean(dem, window_cells):
    """The DEM averaged over a square window, ignoring no data.

    Args:
        dem: Elevation, NaN for no data.
        window_cells: The window's side in cells; made odd so it is centred.

    Returns:
        The mean of the valid cells in each window, NaN where the cell itself
        has no data.
    """
    size = int(window_cells) | 1
    valid = np.isfinite(dem)
    total = ndimage.uniform_filter(np.where(valid, dem, 0.0), size, mode="constant")
    count = ndimage.uniform_filter(valid.astype(float), size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(valid & (count > 0), total / count, np.nan)


def poly_surfaces(dem, transform, pips, radius_m):
    """Each pif's plain least squares quadratic, at its pips' crests and feet.

    Returns:
        ``(crest, foot, fits)``: the surface at each pip and at its foot, on
        ``pips``' index, and one row per pif of the fit, prefixed ``poly_``.
    """
    crest = np.full(len(pips), np.nan)
    foot = np.full(len(pips), np.nan)
    fits = {}
    for pif, at in pips.groupby("pif_id").indices.items():
        group = pips.iloc[at]
        coefficients, centre, scale = fit_quadratic(
            dem,
            transform,
            np.concatenate([group.row, group.foot_row]),
            np.concatenate([group.col, group.foot_col]),
            radius_m=radius_m,
        )
        if coefficients is None:
            continue
        crest[at] = eval_quadratic(coefficients, centre, radius_m, group.x, group.y)
        foot[at] = eval_quadratic(
            coefficients, centre, radius_m, group.foot_x, group.foot_y
        )
        fits[pif] = [*coefficients, *centre, radius_m, scale]
    fits = pd.DataFrame.from_dict(fits, orient="index", columns=FIT_COLUMNS)
    return crest, foot, fits.add_prefix("poly_").rename_axis("pif_id")


def residual_classes(pips, method):
    """A method's crest and foot residuals, excess drop, position and class."""
    crest = (pips.z - pips[f"crest_{method}"]).groupby(pips.pif_id).median()
    foot = (pips.foot_z - pips[f"foot_{method}"]).groupby(pips.pif_id).median()
    excess, position, classes = classify(crest.to_numpy(), foot.to_numpy())
    return pd.DataFrame(
        {
            f"crest_residual_{method}_m": crest,
            f"foot_residual_{method}_m": foot,
            f"excess_drop_{method}_m": excess,
            f"position_{method}": position,
            f"class_{method}": classes,
        },
        index=crest.index,
    )


def anchor_columns(anchor):
    """Step 13's per-pif result under this script's ``anchor`` names."""
    renamed = {f"surface_{c}": f"anchor_{c}" for c in FIT_COLUMNS}
    renamed |= {
        "crest_residual_m": "crest_residual_anchor_m",
        "foot_residual_m": "foot_residual_anchor_m",
        "excess_drop_m": "excess_drop_anchor_m",
        "uncertain_below_m": "uncertain_below_anchor_m",
        "position": "position_anchor",
        "cut_fill_class": "class_anchor",
    }
    return anchor.rename(columns=renamed)[list(renamed.values())]


def slide_reference(table):
    """What the GNS SLIDE genesis polygons say about each pif."""
    cut = table["in_slide_cut"].fillna(value=False).astype(bool)
    fill = table["in_slide_fill"].fillna(value=False).astype(bool)
    reference = np.select(
        [cut & fill, cut, fill], ["cut and fill", "cut", "fill"], "neither"
    )
    return pd.Series(reference, index=table.index, name="slide")


def checks(classes):
    """The class counts by method, and each method against the SLIDE polygons."""
    counts = pd.DataFrame(
        {m: classes[f"class_{m}"].value_counts() for m in METHODS}
    ).reindex(CLASSES)
    counts.loc["all"] = counts.sum()
    agreement = pd.concat(
        {
            m: pd.crosstab(classes["slide"], classes[f"class_{m}"]).reindex(
                columns=list(CLASSES), fill_value=0
            )
            for m in METHODS
        },
        names=["method"],
    )
    return counts, agreement


def write_rolling_mean(mean, transform, path):
    """Write the rolling mean as a float32 GeoTIFF on the DEM's grid."""
    profile = {
        "driver": "GTiff",
        "height": mean.shape[0],
        "width": mean.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:2193",
        "transform": transform,
        "nodata": np.nan,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(mean.astype("float32"), 1)


def main(*, extent, use_cached_layers, rolling_window_m, fit_radius_m):
    """Class every pif by all three methods and write the tables and the mean.

    Args:
        extent: The extent ground step 4 was run over.
        use_cached_layers: Whether to reuse the cached LINZ coastline.
        rolling_window_m: The side of the rolling mean's window, in metres.
        fit_radius_m: The plain quadratic is fitted to cells this close to
            the pif.
    """
    dem, transform, _ = get_dem(extent=extent, use_cached_layers=use_cached_layers)
    cell = transform.a
    table = read_siz_table(siz_table_path(extent=extent))
    pif_ids, rows, cols = pip_cells(table, transform)

    start = time.perf_counter()
    direction = find_pips(dem, cell).direction[rows, cols]
    anchor = gen_pif_cut_fill(dem, transform, pif_ids, rows, cols, direction)
    pips = anchor.pips.rename(
        columns={"crest_surface_z": "crest_anchor", "foot_surface_z": "foot_anchor"}
    )
    pips["row"], pips["col"] = rows, cols
    foot_col, foot_row = ~transform * (pips.foot_x.to_numpy(), pips.foot_y.to_numpy())
    pips["foot_row"] = np.floor(foot_row).astype(int)
    pips["foot_col"] = np.floor(foot_col).astype(int)

    mean = rolling_mean(dem, round(rolling_window_m / cell))
    pips["crest_rolling"] = mean[pips.row, pips.col]
    pips["foot_rolling"] = mean[pips.foot_row, pips.foot_col]
    pips["crest_poly"], pips["foot_poly"], poly_fits = poly_surfaces(
        dem, transform, pips, fit_radius_m
    )

    above = (pips.z > pips.crest_rolling).groupby(pips.pif_id).mean()
    classes = pd.concat(
        [
            anchor.pifs[["n_pips", "face_drop_m"]],
            above.rename("share_pips_above_rolling"),
            residual_classes(pips, "rolling"),
            residual_classes(pips, "poly"),
            poly_fits,
            anchor_columns(anchor.pifs),
        ],
        axis=1,
    )
    classes = classes.join(table[EVIDENCE]).join(slide_reference(table))
    elapsed = time.perf_counter() - start
    print(f"{len(classes):,} pifs, {len(pips):,} pips in {elapsed:.0f} s")

    counts, agreement = checks(classes)
    print(counts.to_string())
    print(agreement.to_string())

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    classes.to_parquet(pif_table_path(extent=extent))
    pips.to_parquet(pip_table_path(extent=extent))
    write_rolling_mean(mean, transform, rolling_mean_path(extent=extent))
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(TAB_DIR / "pif-classes.csv", index_label="class")
    agreement.to_csv(TAB_DIR / "pif-classes-vs-slide.csv")
    print(f"Written to {WORK_DIR} and {TAB_DIR}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        rolling_window_m=config.ROLLING_WINDOW_M,
        fit_radius_m=config.FIT_RADIUS_M,
    )
