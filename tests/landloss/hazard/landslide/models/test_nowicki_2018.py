import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr
from shapely.geometry import box

from landloss.hazard.landslide.models.nowicki_2018 import coefficients as c
from landloss.hazard.landslide.models.nowicki_2018 import inputs, model


def geographic(values, *, x0=174.0, y0=-41.0, res=1 / 480):
    """A small geographic grid, north-up, cell centres from (x0, y0)."""
    rows, cols = values.shape
    y = y0 - res * np.arange(rows)
    x = x0 + res * np.arange(cols)
    da = xr.DataArray(values.astype(float), coords={"y": y, "x": x}, dims=("y", "x"))
    return da.rio.write_crs("EPSG:4326")


def run_one(**overrides):
    kwargs = {
        "pgv_cm_s": np.array([50.0]),
        "slope_deg": np.array([30.0]),
        "rock_coefficient": np.array([c.GLIM_COEFFICIENTS["ss"]]),
        "landcover_coefficient": np.array([c.GLOBCOVER_COEFFICIENTS[140]]),
        "cti": np.array([5.0]),
        "operational": False,
    }
    kwargs.update(overrides)
    return model.run(**kwargs)


def test_coverage_runs_between_the_papers_bounds():
    assert model.areal_coverage(np.array(0.0)) == pytest.approx(0.000504, rel=1e-3)
    assert model.areal_coverage(np.array(1.0)) == pytest.approx(0.2561, rel=1e-3)


def test_worked_example_from_the_rebuild_note():
    # Siliciclastic rock, grassland, CTI 5, 50 cm/s on a 30 degree slope: the
    # 10.6% in the rebuild note's "What the numbers look like" table.
    assert run_one().coverage[0] == pytest.approx(0.1057, abs=5e-4)


def test_artificial_surfaces_halve_the_grassland_answer():
    grass = run_one().coverage[0]
    urban = run_one(
        landcover_coefficient=np.array([c.GLOBCOVER_COEFFICIENTS[190]])
    ).coverage[0]
    assert urban == pytest.approx(0.0525, abs=5e-4)
    assert urban < 0.6 * grass


def test_operational_raises_unconsolidated_sediments():
    weak = run_one(rock_coefficient=np.array([c.GLIM_COEFFICIENTS["su"]]))
    ops = run_one(
        rock_coefficient=np.array([c.GLIM_COEFFICIENTS["su"]]),
        pga_pct_g=np.array([30.0]),
        operational=True,
    )
    mixed = run_one(rock_coefficient=np.array([c.GLIM_COEFFICIENTS["sm"]]))
    assert ops.coverage[0] > weak.coverage[0]
    assert ops.coverage[0] == pytest.approx(round(mixed.coverage[0], 4))


def test_operational_masks_flat_ground_and_weak_shaking():
    res = run_one(
        pgv_cm_s=np.array([50.0, 50.0]),
        slope_deg=np.array([1.5, 30.0]),
        rock_coefficient=np.full(2, c.GLIM_COEFFICIENTS["ss"]),
        landcover_coefficient=np.full(2, 1.03),
        cti=np.full(2, 5.0),
        pga_pct_g=np.array([30.0, 1.0]),
        operational=True,
    )
    assert res.coverage[0] == 0.0
    assert np.isnan(res.coverage[1])


def test_operational_needs_pga():
    with pytest.raises(ValueError, match="pga_pct_g"):
        run_one(operational=True)


def test_uncertainty_grows_with_pgv_uncertainty():
    low = run_one(ln_pgv_std=np.array([0.1])).coverage_std[0]
    high = run_one(ln_pgv_std=np.array([0.6])).coverage_std[0]
    assert 0 < low < high


def test_gradient_of_a_north_facing_plane():
    # Elevation rising 0.1 m per metre southwards gives a gradient of 0.1
    # everywhere, whatever the latitude does to the east-west spacing.
    rows = np.arange(6)[:, None] * np.ones((1, 5))
    dem = geographic(rows)
    dy_m = inputs.EARTH_RADIUS_M * np.deg2rad(1 / 480)
    dem = dem.copy(data=rows * dy_m * 0.1)
    assert np.allclose(inputs.gen_gradient(dem).to_numpy(), 0.1)


def test_landcover_lookup_keeps_reference_and_unlisted_classes_at_zero():
    classes = geographic(np.array([[11, 140, 170], [190, 210, np.nan]]))
    out = inputs.gen_landcover_coefficient(classes).to_numpy()
    assert out[0, 0] == 0.0  # reference category
    assert out[0, 1] == pytest.approx(1.03)
    assert out[0, 2] == pytest.approx(1.19)  # 170 takes 180's, as the USGS does
    assert out[1, 0] == pytest.approx(0.30)
    assert out[1, 1] == 0.0  # water, no coefficient
    assert np.isnan(out[1, 2])


def test_rock_rasterisation_looks_up_table_3():
    template = geographic(np.zeros((4, 4)))
    left, right = 174.0 - 1 / 960, 174.0 + 3.5 / 480
    top, mid, bottom = -41.0 + 1 / 960, -41.0 - 1.5 / 480, -41.0 - 3.5 / 480
    glim = gpd.GeoDataFrame(
        {"xx": ["ss", "ev"]},
        geometry=[box(left, mid, right, top), box(left, bottom, right, mid)],
        crs="EPSG:4326",
    )
    out = inputs.gen_rock_coefficient(glim, template, class_column="xx").to_numpy()
    assert np.allclose(out[:2], -1.92)
    assert np.allclose(out[2:], 0.0)  # evaporites are the reference category


def test_cti_is_highest_where_the_valley_collects_water():
    # A V-shaped valley draining north to the sea along its centre line.
    rows, cols = 20, 11
    across = np.abs(np.arange(cols) - cols // 2)[None, :] * 20.0
    down = np.arange(rows)[:, None] * 5.0
    z = 10.0 + across + down
    z[0, :] = np.nan  # the sea
    cti = inputs.gen_cti(geographic(z, res=1 / 120)).to_numpy()
    centre = cti[1:, cols // 2]
    assert np.all(np.isfinite(cti[1:]))
    assert np.nanargmax(cti[1:, :].max(axis=0)) == cols // 2
    assert centre[0] > centre[-1]  # more area near the outlet


def test_the_model_grid_is_registered_as_the_usgs_slope_layer_is():
    # The USGS Loma Prieta slope raster: 432 x 672 cells over this extent, the
    # first cell centred half a cell in from -122.6, 37.3.
    grid = inputs.gen_model_grid((-122.6, 36.4, -121.2, 37.3))
    assert grid.shape == (432, 672)
    assert grid.x.values[0] == pytest.approx(-122.6 + 3.75 / 3600)
    assert grid.y.values[0] == pytest.approx(37.3 - 3.75 / 3600)
