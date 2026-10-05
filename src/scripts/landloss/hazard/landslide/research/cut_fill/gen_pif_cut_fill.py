"""Class every pif as cut, fill, cut and fill, or natural ground.

A pif is a step in the 1 m DEM. Whether it is in cut or fill depends on where
the step sits against the ground that was there before the earthworks: a fill
batter stands above that natural surface, a cut face is dug below it and a
benched terrace's face straddles it. That surface is not measured, so it is
estimated two ways and both are kept:

- **rolling**: the DEM averaged over a ``config.ROLLING_WINDOW_M`` square
  window (:func:`rolling_mean`). Wider than one platform, so a terrace's cut
  and fill average out.
- **poly**: a quadratic surface fitted to the DEM within
  ``config.FIT_RADIUS_M`` of each pif's points (:func:`fit_quadratic`). It
  bends with the hill where the mean, on a crest or in a gully, does not.

A pip is the crest of a drop by definition, so on its own it nearly always
stands above a smoothed surface; the comparison needs the foot of the face as
well. Each pip is walked down its own fall direction to the first step flatter
than ``config.FOOT_SLOPE_DEG`` (:func:`face_feet`). Then, for each pif and each
surface, with the crest and foot residuals the medians over its pips of the
DEM minus the surface (:func:`classify`):

- the **excess drop** is crest residual minus foot residual: how much further
  the ground falls across the face than the natural surface does. No more than
  ``config.EXCESS_DROP_M`` is natural ground.
- the **position** is crest residual plus foot residual over the excess drop:
  +1 when all of the excess is above the natural surface (fill), -1 when all of
  it is below (cut), 0 when it straddles it. Beyond ``config.POSITION_SPLIT``
  either way is fill or cut, between is cut and fill.

The share of a pif's pips above the rolling mean (the first idea tried) is kept
too, as ``share_pips_above_rolling``.

Run from the repository root, after landslide step 12::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/cut_fill/gen_pif_cut_fill.py

Settings are in ``config.py``. Writes the pif and pip tables and the rolling
mean under ``temp/hazard/landslide/``, and the class counts and their agreement
with the GNS SLIDE cut slope and fill body polygons under
``research/hazard/landslide/pif_cut_fill/tab/``.
"""

import math
import time

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from scipy.spatial import cKDTree

from landloss.hazard.landslide.instability_zones import (
    DIRECTIONS,
    find_pips,
    read_siz_table,
)
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.research.cut_fill import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    WORK_DIR,
    get_inputs,
    siz_table_path,
)
from scripts.landloss.paths import RESEARCH_DIR

TAB_DIR = RESEARCH_DIR / "hazard" / "landslide" / "pif_cut_fill" / "tab"
METHODS = ("rolling", "poly")
CUT, FILL, CUT_AND_FILL, NATURAL = "cut", "fill", "cut_and_fill", "natural"
CLASSES = (CUT, CUT_AND_FILL, FILL, NATURAL)

# The siz table's own evidence carried onto the result, for the checks.
EVIDENCE = ["in_slide_cut", "in_slide_fill", "gns_wall", "ground_modification"]


def pif_table_path(*, extent):
    """Where the class of every pif is written."""
    return WORK_DIR / f"pif-cut-fill{extent_suffix(extent)}.parquet"


def pip_table_path(*, extent):
    """Where every pip, its foot and the natural surface at both are written."""
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


def face_feet(dem, rows, cols, direction, cell_m, *, slope_deg, max_m):
    """The foot of the face below each pip, down the pip's own fall direction.

    Walks a cell at a time while each step falls at least ``slope_deg``, so it
    stops on the first flatter ground (a platform, a road, the natural slope
    below a batter), at no data or after ``max_m``.

    Returns:
        ``(rows, cols)`` of the feet.
    """
    steps = np.array(DIRECTIONS)[direction]
    step_m = cell_m * np.hypot(steps[:, 0], steps[:, 1])
    need = math.tan(math.radians(slope_deg)) * step_m
    height, width = dem.shape
    r, c = rows.copy(), cols.copy()
    z = dem[r, c]
    travelled = np.zeros(len(r))
    active = np.ones(len(r), dtype=bool)
    while active.any():
        nr, nc = r + steps[:, 0], c + steps[:, 1]
        inside = (nr >= 0) & (nr < height) & (nc >= 0) & (nc < width)
        nz = np.full(len(r), np.nan)
        nz[inside] = dem[nr[inside], nc[inside]]
        with np.errstate(invalid="ignore"):
            go = active & inside & (z - nz >= need) & (travelled + step_m <= max_m)
        r, c = np.where(go, nr, r), np.where(go, nc, c)
        z = np.where(go, nz, z)
        travelled += np.where(go, step_m, 0.0)
        active = go
    return r, c


def fit_quadratic(dem, transform, points_xy, radius_m):
    """A quadratic surface fitted to the DEM around some points.

    Every valid cell within ``radius_m`` of any of the points is fitted, by
    least squares, with ``z = a + b u + c v + d u^2 + e u v + f v^2`` in
    coordinates ``u, v`` centred on the points' mean and scaled by
    ``radius_m``.

    Returns:
        ``(coefficients, centre)``, the six coefficients and the ``(x, y)``
        centre, or ``(None, centre)`` where fewer than 12 cells were found.
    """
    cell = transform.a
    centre = points_xy.mean(axis=0)
    minx, miny = points_xy.min(axis=0) - radius_m
    maxx, maxy = points_xy.max(axis=0) + radius_m
    c0, r0 = (int(v) for v in ~transform * (minx, maxy))
    c1, r1 = (math.ceil(v) for v in ~transform * (maxx, miny))
    r0, c0 = max(r0, 0), max(c0, 0)
    r1, c1 = min(r1, dem.shape[0]), min(c1, dem.shape[1])
    window = dem[r0:r1, c0:c1]
    rr, cc = np.mgrid[r0:r1, c0:c1]
    x = transform.c + (cc + 0.5) * cell
    y = transform.f - (rr + 0.5) * cell
    near, _ = cKDTree(points_xy).query(
        np.column_stack([x.ravel(), y.ravel()]), distance_upper_bound=radius_m
    )
    keep = np.isfinite(near) & np.isfinite(window.ravel())
    if keep.sum() < 12:  # noqa: PLR2004 - twice the coefficients
        return None, centre
    u = (x.ravel()[keep] - centre[0]) / radius_m
    v = (y.ravel()[keep] - centre[1]) / radius_m
    design = np.column_stack([np.ones_like(u), u, v, u * u, u * v, v * v])
    coefficients, *_ = np.linalg.lstsq(design, window.ravel()[keep], rcond=None)
    return coefficients, centre


def eval_quadratic(coefficients, centre, radius_m, x, y):
    """The fitted quadratic at points."""
    u = (np.asarray(x) - centre[0]) / radius_m
    v = (np.asarray(y) - centre[1]) / radius_m
    a, b, c, d, e, f = coefficients
    return a + b * u + c * v + d * u * u + e * u * v + f * v * v


def classify(crest_residual, foot_residual, *, excess_drop_m, position_split):
    """The class of each pif from its crest and foot residuals.

    Returns:
        ``(excess_drop, position, classes)``.
    """
    excess = crest_residual - foot_residual
    with np.errstate(invalid="ignore", divide="ignore"):
        position = np.where(
            excess > 0, (crest_residual + foot_residual) / excess, np.nan
        )
    classes = np.full(len(excess), CUT_AND_FILL, dtype=object)
    classes[position > position_split] = FILL
    classes[position < -position_split] = CUT
    classes[~(excess > excess_drop_m)] = NATURAL
    return excess, position, classes


def pips_of(table, transform):
    """Every pip as a row: its pif, and its cell and centre."""
    pips = table[["geometry"]].explode(index_parts=False).reset_index()
    x, y = pips.geometry.x.to_numpy(), pips.geometry.y.to_numpy()
    col, row = ~transform * (x, y)
    return pd.DataFrame(
        {
            "pif_id": pips["pif_id"].to_numpy(),
            "row": np.floor(row).astype(int),
            "col": np.floor(col).astype(int),
            "x": x,
            "y": y,
        }
    )


def poly_surfaces(dem, transform, pips, radius_m):
    """Each pif's quadratic, evaluated at its pips' crests and feet.

    Returns:
        ``(crest, foot, fits)``: the surface at each pip and at its foot, on
        ``pips``' index, and one row of coefficients and centre per pif.
    """
    crest = np.full(len(pips), np.nan)
    foot = np.full(len(pips), np.nan)
    fits = {}
    for pif, group in pips.groupby("pif_id"):
        points = np.vstack(
            [group[["x", "y"]].to_numpy(), group[["foot_x", "foot_y"]].to_numpy()]
        )
        coefficients, centre = fit_quadratic(dem, transform, points, radius_m)
        if coefficients is None:
            continue
        at = group.index.to_numpy()
        crest[at] = eval_quadratic(coefficients, centre, radius_m, group.x, group.y)
        foot[at] = eval_quadratic(
            coefficients, centre, radius_m, group.foot_x, group.foot_y
        )
        fits[pif] = [*coefficients, *centre]
    columns = ["a", "b", "c", "d", "e", "f", "centre_x", "centre_y"]
    fits = pd.DataFrame.from_dict(fits, orient="index", columns=columns)
    return crest, foot, fits.add_prefix("poly_").rename_axis("pif_id")


def pif_classes(pips, *, excess_drop_m, position_split):
    """One row per pif: its residuals, excess drop, position and class, by method."""
    grouped = pips.groupby("pif_id")
    out = pd.DataFrame(
        {
            "n_pips": grouped.size(),
            "face_drop_m": grouped.apply(lambda g: (g.z - g.foot_z).median()),
            "share_pips_above_rolling": grouped.apply(
                lambda g: (g.z > g.crest_rolling).mean()
            ),
        }
    )
    for method in METHODS:
        crest = (pips.z - pips[f"crest_{method}"]).groupby(pips.pif_id).median()
        foot = (pips.foot_z - pips[f"foot_{method}"]).groupby(pips.pif_id).median()
        excess, position, classes = classify(
            crest.to_numpy(),
            foot.to_numpy(),
            excess_drop_m=excess_drop_m,
            position_split=position_split,
        )
        out[f"crest_residual_{method}_m"] = crest
        out[f"foot_residual_{method}_m"] = foot
        out[f"excess_drop_{method}_m"] = excess
        out[f"position_{method}"] = position
        out[f"class_{method}"] = classes
    return out


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


def main(
    *,
    extent,
    use_cached_layers,
    rolling_window_m,
    fit_radius_m,
    foot_slope_deg,
    foot_max_m,
    excess_drop_m,
    position_split,
):
    """Class every pif of the extent and write the tables and the rolling mean.

    Args:
        extent: The extent landslide step 12 was run over.
        use_cached_layers: Whether to reuse the cached LINZ layers.
        rolling_window_m: The side of the rolling mean's window, in metres.
        fit_radius_m: The quadratic is fitted to cells this close to the pif.
        foot_slope_deg: The walk to a face's foot stops on flatter ground.
        foot_max_m: The walk stops after this many metres.
        excess_drop_m: At most this much excess drop is natural ground.
        position_split: The position beyond which a pif is a cut or a fill.
    """
    dem, transform, *_ = get_inputs(extent=extent, use_cached_layers=use_cached_layers)
    cell = transform.a
    table = read_siz_table(siz_table_path(extent=extent))

    start = time.perf_counter()
    mean = rolling_mean(dem, round(rolling_window_m / cell))
    pips = pips_of(table, transform)
    found = find_pips(dem, cell)
    direction = found.direction[pips.row, pips.col]
    if (direction < 0).any():
        msg = (
            f"{int((direction < 0).sum())} pips of the siz table are not pips of "
            "this DEM: rerun landslide step 12."
        )
        raise ValueError(msg)
    foot_r, foot_c = face_feet(
        dem,
        pips.row.to_numpy(),
        pips.col.to_numpy(),
        direction,
        cell,
        slope_deg=foot_slope_deg,
        max_m=foot_max_m,
    )
    pips["foot_x"] = transform.c + (foot_c + 0.5) * cell
    pips["foot_y"] = transform.f - (foot_r + 0.5) * cell
    pips["z"] = dem[pips.row, pips.col]
    pips["foot_z"] = dem[foot_r, foot_c]
    pips["crest_rolling"] = mean[pips.row, pips.col]
    pips["foot_rolling"] = mean[foot_r, foot_c]
    pips["crest_poly"], pips["foot_poly"], fits = poly_surfaces(
        dem, transform, pips, fit_radius_m
    )
    classes = pif_classes(
        pips, excess_drop_m=excess_drop_m, position_split=position_split
    )
    classes = classes.join(fits).join(table[EVIDENCE]).join(slide_reference(table))
    print(f"{len(classes):,} pifs, {len(pips):,} pips in {time.perf_counter() - start:.0f} s")

    counts, agreement = checks(classes)
    print(counts.to_string())
    print(agreement.to_string())

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    classes.to_parquet(pif_table_path(extent=extent))
    pips.to_parquet(pip_table_path(extent=extent))
    profile = {
        "driver": "GTiff",
        "height": dem.shape[0],
        "width": dem.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:2193",
        "transform": transform,
        "nodata": np.nan,
        "compress": "deflate",
    }
    with rasterio.open(rolling_mean_path(extent=extent), "w", **profile) as dst:
        dst.write(mean.astype("float32"), 1)
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
        foot_slope_deg=config.FOOT_SLOPE_DEG,
        foot_max_m=config.FOOT_MAX_M,
        excess_drop_m=config.EXCESS_DROP_M,
        position_split=config.POSITION_SPLIT,
    )
