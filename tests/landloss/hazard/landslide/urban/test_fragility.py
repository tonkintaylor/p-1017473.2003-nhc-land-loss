"""Tests for the urban failure fragility and landslide step 8.

The library is checked on the contract's unit cases (section 7.7 of
``.agents/plans/urban-slope-build-contract.md``), the packaged anchor table is
read and validated, the wall type curves are joined with the wall's own fill or
cut shift, step 12's zones are turned into the polygons step 8 reads
(``face_polygons``) and checked against the drawn walls, and the step's three
scripts and the two urban validation scripts are run end to end on synthetic
step 12 zones, elements and wall units, walls and 100 m grids written where
each step looks for them, with the TS1170.5 reader and the
basemap tiles faked, so nothing here touches a network drive or a real run.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scipy.stats import norm
from shapely.geometry import box

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import (
    face_polygons,
    fragility,
    geometry,
    wall_type_fragility,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import gen_wall_population
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_terrain_derivatives,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map import gen_ground_map
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    fig_urban_slope_model,
    table_urban_slope_model,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    gen_urban_slope_fragility as step,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    gen_urban_slope_faces,
    gen_urban_slope_wall_units,
)
from scripts.landloss.hazard.landslide.validations.urban import (
    fig_urban_fragility_anchors,
    table_urban_fragility_anchors,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class import gen_site_class
from scripts.landloss.hazard.shaking.steps.s3_pgv import gen_pgv

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, inside the wlg-pilot box (step 8
# leaves out polygons outside the extent), so the grids and the polygons sit
# where a Wellington run would put them.
X0 = 1_748_400.0
Y0 = 5_424_000.0
CELL_M = 100.0
RETURN_PERIOD_YR = 2500
WORLD = 0


# --- synthetic inputs -----------------------------------------------------------------


def make_grid(values, resolution=CELL_M):
    """Wrap an array as a north-up raster in NZTM, as the shaking steps write one."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    eastings = X0 + resolution * (np.arange(columns) + 0.5)
    northings = Y0 + resolution * (np.arange(rows)[::-1] + 0.5)
    grid = xr.DataArray(values, dims=("y", "x"), coords={"y": northings, "x": eastings})
    return grid.rio.write_crs(constants.DEFAULT_CRS)


def square(x, y, side):
    return box(X0 + x, Y0 + y, X0 + x + side, Y0 + y + side)


# The synthetic wall types: MODERN takes the size's median, OLD 0.6 of it.
MODERN = "block_rc_cantilever"
OLD = "gravity_masonry"


def wall_table():
    """Every wall type and size, as ``load_wall_type_fragility`` returns them.

    The medians are on PGA: 0.5, 0.8 and 1.0 g for the three sizes, times 0.6
    for :data:`OLD`.
    """
    rows = []
    for size_class, theta in (("small", 0.5), ("medium", 0.8), ("large", 1.0)):
        for wall_type in wall_type_fragility.WALL_TYPES:
            shift = 0.6 if wall_type == OLD else 1.0
            rows.append(
                {
                    "wall_type": wall_type,
                    "size_class": size_class,
                    "im": fragility.PGA_IM,
                    "theta": theta * shift,
                    "beta": 0.5,
                    "source": f"test_{size_class}_{wall_type}",
                }
            )
    return pd.DataFrame(rows)


def polygons(
    faces, *, wall_line_ids, wall_positions, ratings, amp=1.0, edge_lines=None
):
    """Synthetic step 7 polygons with every column the fragility reads.

    The state geometries are the face itself for the no-wall state and for
    the state matching the wall's position, ``None`` for the other. Without
    ``edge_lines`` each polygon's only edge line is its ``wall_line_id``.
    """
    faces = list(faces)
    count = len(faces)
    ratings = np.asarray(ratings, dtype=float)
    if edge_lines is None:
        edge_lines = [[] if line is None else [line] for line in wall_line_ids]
    frame = gpd.GeoDataFrame(
        {
            geometry.SLOPE_ID_COLUMN: [f"SP{n:07d}" for n in range(count, 0, -1)],
            geometry.WALL_LINE_ID_COLUMN: list(wall_line_ids),
            geometry.WALL_LINE_IDS_COLUMN: pd.Series(list(edge_lines), dtype=object),
            geometry.WALL_POSITION_COLUMN: list(wall_positions),
            "kingsbury_rating": ratings,
            "kingsbury_zone": pd.Series(
                susceptibility.susceptibility_zone(ratings)
            ).astype("Int64"),
            "continuous_rating": ratings,
            "amp_factor": np.full(count, amp, dtype=float),
            geometry.SCALE_COLUMN: 1,
            geometry.AREA_COLUMN: [face.area for face in faces],
            geometry.SLOPE_COLUMN: 40.0,
            geometry.MATERIAL_COLUMN: "colluvium",
            "modification": "natural",
            "face_height_10m": 6.0,
            "topographic_position_100m": 0.0,
            geometry.REP_POINT_COLUMN: gpd.GeoSeries(
                [face.representative_point() for face in faces],
                crs=constants.DEFAULT_CRS,
            ),
        },
        geometry=faces,
        crs=constants.DEFAULT_CRS,
    )
    for state in geometry.WALL_STATES:
        possible = [
            state == geometry.NO_WALL or position == state.removesuffix("_wall")
            for position in wall_positions
        ]
        for kind in geometry.GEOMETRY_KINDS:
            frame[f"{kind}_{state}"] = gpd.GeoSeries(
                [
                    face if ok else None
                    for face, ok in zip(faces, possible, strict=True)
                ],
                crs=constants.DEFAULT_CRS,
            )
        for kind in (geometry.EVACUATED, geometry.INUNDATED):
            depth = 1.0 if kind == geometry.EVACUATED else 0.5
            frame[f"depth_{kind}_{state}_m"] = [
                depth if ok else np.nan for ok in possible
            ]
    return frame


def wall_population(rw_ids, wall_line_ids, size_classes, wall_types, positions=None):
    """Synthetic exposure step 6 walls, one per rw_id.

    The walls' own positions are unknown (null) unless ``positions`` is given,
    so their curves are the table's unshifted.
    """
    count = len(rw_ids)
    if positions is None:
        positions = [None] * count
    return gpd.GeoDataFrame(
        {
            "rw_id": list(rw_ids),
            "claim_id": [rw.split("-")[0] for rw in rw_ids],
            "wall_line_id": list(wall_line_ids),
            "world_id": WORLD,
            "size_class": list(size_classes),
            "wall_type": list(wall_types),
            "age_bin": "pre_1970",
            "height_m": 1.5,
            "length_m": 10.0,
            "wall_position": pd.Series(list(positions), dtype=object),
            "is_flatland": False,
            "source": "terrain_break",
            "material": "colluvium",
        },
        geometry=[square(10 * n, 0, 1).exterior for n in range(count)],
        crs=constants.DEFAULT_CRS,
    )


def three_polygons():
    """One polygon with a fill wall, one with a cut wall, one with no line."""
    faces = [square(10, 10, 20), square(110, 10, 20), square(210, 10, 20)]
    return polygons(
        faces,
        wall_line_ids=["WL0000001", "WL0000002", None],
        wall_positions=[geometry.FILL, geometry.CUT, None],
        ratings=[120.0, 80.0, 30.0],
        amp=1.25,
    )


def two_walls():
    return wall_population(
        ["C1-RW01", "C2-RW01"],
        ["WL0000001", "WL0000002"],
        ["small", "large"],
        [MODERN, OLD],
    )


def one_uninsured_wall():
    """The two walls with the first not insured: no claim, so no rw_id."""
    walls = two_walls()
    walls["rw_id"] = walls["rw_id"].astype(object)
    walls["claim_id"] = walls["claim_id"].astype(object)
    walls.loc[0, ["rw_id", "claim_id"]] = None
    return walls


# Step 12's files for one world: three polygons in the three 100 m cells left
# to right. Polygon 1 grew from pif 11, a member of the fill unit WU0000001;
# polygon 2 from pif 12, the cut unit WU0000002; polygon 3 from pif 13, in no
# unit and off the ground map. The world walled both units.
FACE_XS = (10, 110, 210)


def step12_zones(*, walled=(True, True, False)):
    """Step 12's zones of one world, one row per polygon and zone."""
    rows = []
    for polygon, (x, is_walled) in enumerate(zip(FACE_XS, walled, strict=True), 1):
        evacuated = square(x, 10, 20)
        common = {
            "polygon": polygon,
            "element": polygon,
            "element_type": "free_face" if is_walled else "bank",
            "height_m": 6.0,
            "area_m2": evacuated.area,
            "depth_m": 1.0,
            "volume_m3": evacuated.area,
            "scenario": f"w{WORLD:03d}",
        }
        rows.append({**common, "zone": "evacuated", "geometry": evacuated})
        rows.append({**common, "zone": "imminent", "geometry": square(x, 30, 5)})
        if polygon != 3:
            # 100 m2 under the toe: the 400 m3 spread 4 m deep.
            rows.append(
                {
                    **common,
                    "zone": "inundated",
                    "geometry": box(X0 + x, Y0 + 5, X0 + x + 20, Y0 + 10),
                }
            )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=constants.DEFAULT_CRS)


def step12_elements():
    return pd.DataFrame(
        {
            "siz_id": [11, 12, 13],
            "majority_ground_row": [0, 0, -1],
            "overall_angle_deg": [40.0, 40.0, 40.0],
        },
        index=pd.Index([1, 2, 3], name="label"),
    )


def step12_units():
    return gpd.GeoDataFrame(
        {
            "member_pif_ids": [[11], [12]],
            "is_fill": [True, False],
        },
        geometry=[square(x, 10, 20).boundary for x in FACE_XS[:2]],
        index=pd.Index(["WU0000001", "WU0000002"], name="wall_unit_id"),
        crs=constants.DEFAULT_CRS,
    )


def step12_ground_map():
    return gpd.GeoDataFrame(
        {
            "material": ["colluvium"],
            "modification": ["natural"],
            "geology_value": [susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM],
            "prior_failure": ["none"],
            "gw_depth_m": [4.0],
        },
        geometry=[square(0, 0, 200)],
        crs=constants.DEFAULT_CRS,
    )


def unit_walls():
    """Rw step 6's drawn walls of the two units, the fill one uninsured."""
    walls = wall_population(
        ["C1-RW01", "C2-RW01"],
        ["WU0000001", "WU0000002"],
        ["small", "large"],
        [MODERN, OLD],
        positions=[geometry.FILL, geometry.CUT],
    )
    walls["rw_id"] = walls["rw_id"].astype(object)
    walls["claim_id"] = walls["claim_id"].astype(object)
    walls.loc[0, ["rw_id", "claim_id"]] = None
    return walls


def three_face_polygons(**kwargs):
    return face_polygons.face_polygons(
        step12_zones(**kwargs), step12_elements(), step12_units(), step12_ground_map()
    )


def site_class_at(polygons_frame, value=3):
    return pd.Series(float(value), index=polygons_frame.index)


def ratio_at(polygons_frame, value=1.2):
    return pd.Series(float(value), index=polygons_frame.index)


# --- the continuous rating ------------------------------------------------------------


def test_interpolated_slope_value_equals_the_stepped_value_at_every_break():
    breaks = np.array([0.0, *susceptibility.SLOPE_ANGLE_BREAKS_DEGREES, 90.0])
    np.testing.assert_allclose(
        fragility.interpolated_slope_value(breaks),
        susceptibility.slope_angle_value(breaks),
    )


def test_interpolated_slope_value_rises_between_the_breaks_and_keeps_nan():
    values = fragility.interpolated_slope_value(np.array([10.0, 27.5, np.nan]))
    np.testing.assert_allclose(values[:2], [1.0, 3.0])
    assert np.isnan(values[2])


def test_continuous_rating_matches_the_stepped_rating_at_a_break():
    zeros = np.zeros(2)
    geology = np.array([10.0, 10.0])
    rating = fragility.continuous_rating(
        slope_degrees=np.array([45.0, 60.0]),
        modification=zeros,
        height=zeros,
        geology=geology,
        landslides=zeros,
        groundwater=zeros,
    )
    stepped = susceptibility.susceptibility_rating(
        slope=susceptibility.slope_angle_value(np.array([45.0, 60.0])),
        modification=zeros,
        height=zeros,
        geology=geology,
        landslides=zeros,
        groundwater=zeros,
    )
    np.testing.assert_allclose(rating, stepped)


# --- the curve and its pieces ---------------------------------------------------------


def test_the_lognormal_at_the_median_is_one_half_and_zero_demand_gives_zero():
    probability = fragility.lognormal_failure_probability(
        np.array([0.8, 0.0, -1.0, np.nan]),
        np.array([0.8, 0.8, 0.8, 0.8]),
        np.array([0.6] * 4),
    )
    np.testing.assert_allclose(probability[:3], [0.5, 0.0, 0.0])
    assert np.isnan(probability[3])


def test_the_lognormal_follows_the_standard_normal_of_the_log_ratio():
    probability = fragility.lognormal_failure_probability(
        np.array([2.0]), np.array([1.0]), np.array([0.5])
    )
    np.testing.assert_allclose(probability, norm.cdf(np.log(2.0) / 0.5))


def test_a_non_positive_dispersion_is_refused():
    with pytest.raises(ValueError, match="positive"):
        fragility.lognormal_failure_probability(
            np.array([1.0]), np.array([1.0]), np.array([0.0])
        )


def test_a_half_g_median_at_a_ratio_of_1_2_is_0_6_m_s():
    np.testing.assert_allclose(
        fragility.pga_to_pgv_theta(np.array([0.5]), np.array([1.2])), [0.6]
    )
    assert np.isnan(fragility.pga_to_pgv_theta(np.array([0.5]), np.array([np.nan])))[0]


def test_the_medium_rate_factor_is_one_and_an_unknown_setting_is_refused():
    assert fragility.rate_factor("medium") == 1.0
    assert fragility.rate_factor("low") > 1.0 > fragility.rate_factor("high")
    with pytest.raises(ValueError, match="'low', 'medium', 'high'"):
        fragility.rate_factor("extreme")


def test_the_localised_median_runs_log_linearly_between_its_two_constants():
    ratings = np.array([0.0, susceptibility.MAX_RATING / 2, susceptibility.MAX_RATING])
    theta = fragility.localised_theta_base_m_s(ratings)
    low, high = (
        fragility.LOCALISED_THETA_AT_ZERO_RATING_M_S,
        fragility.LOCALISED_THETA_AT_MAX_RATING_M_S,
    )
    np.testing.assert_allclose(theta, [low, np.sqrt(low * high), high])
    assert np.isnan(fragility.localised_theta_base_m_s(np.array([np.nan])))[0]


def test_polygon_theta_divides_by_amplification_and_multiplies_by_the_rate():
    theta = fragility.polygon_theta(np.array([1.5]), np.array([1.5]), 1.5)
    np.testing.assert_allclose(theta, [1.5])


# --- the anchor table -----------------------------------------------------------------


def test_the_packaged_anchor_table_reads_with_fractions_in_range():
    anchors = fragility.load_urban_fragility_anchors()
    assert list(anchors.columns) == list(fragility.ANCHOR_COLUMNS)
    assert anchors["anchor_id"].is_unique
    assert anchors["fail_fraction"].between(0, 1).all()
    assert (anchors["set_by"].str.len() > 0).all()
    # The fifteen Kingsbury cells, zoned, and the GNS findings, unzoned.
    assert anchors["zone"].notna().sum() == 15
    assert anchors["zone"].isna().sum() >= 1


def test_an_anchor_table_with_a_fraction_out_of_range_is_refused(tmp_path):
    anchors = fragility.load_urban_fragility_anchors()
    bad = anchors.copy()
    bad.loc[0, "fail_fraction"] = 1.5
    path = tmp_path / "anchors.csv"
    bad.to_csv(path, index=False)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        fragility.load_urban_fragility_anchors(path)


def test_the_packaged_anchors_say_what_each_fraction_measures():
    anchors = fragility.load_urban_fragility_anchors()
    by_measure = anchors.groupby("measure")["anchor_id"].apply(list)
    assert by_measure[fragility.ZONE_AREA_MEASURE] == [
        f"A{n:02d}" for n in range(1, 17)
    ]
    assert by_measure[fragility.POLYGON_MEASURE] == [f"A{n}" for n in range(17, 22)]
    assert anchors.loc[anchors["anchor_id"] == "A17", "demand_at"].item() == "site"


def test_an_anchor_with_an_unknown_measure_is_refused(tmp_path):
    bad = fragility.load_urban_fragility_anchors()
    bad.loc[0, "measure"] = "volume"
    path = tmp_path / "anchors.csv"
    bad.to_csv(path, index=False)
    with pytest.raises(ValueError, match="measure"):
        fragility.load_urban_fragility_anchors(path)


# --- the PGV/PGA ratio ----------------------------------------------------------------


@ignore_affine_matmul
def test_the_ratio_is_read_at_the_cell_each_point_falls_in_and_nan_off_the_grid():
    pgv = make_grid([[0.6, 1.2], [1.8, np.nan]])
    pga = make_grid([[0.5, 1.0], [1.5, 1.0]])
    points = gpd.GeoSeries(
        [
            square(10, 110, 1).centroid,  # top-left cell
            square(150, 150, 1).centroid,  # top-right cell
            square(150, 50, 1).centroid,  # bottom-right, PGV NaN
            square(-50, 50, 1).centroid,  # off the grid
        ],
        index=[7, 3, 5, 1],
        crs=constants.DEFAULT_CRS,
    )
    ratio = fragility.pgv_pga_ratio_m_s_per_g(pgv, pga, points)
    assert list(ratio.index) == [7, 3, 5, 1]
    np.testing.assert_allclose(ratio.to_numpy()[:2], [1.2, 1.2])
    assert np.isnan(ratio.to_numpy()[2:]).all()


@ignore_affine_matmul
def test_grids_on_different_cells_are_refused():
    pgv = make_grid([[0.6, 1.2], [1.8, 1.0]])
    pga = make_grid([[0.5, 1.0], [1.5, 1.0]], resolution=50.0)
    points = gpd.GeoSeries([square(10, 10, 1).centroid], crs=constants.DEFAULT_CRS)
    with pytest.raises(ValueError, match="transforms"):
        fragility.pgv_pga_ratio_m_s_per_g(pgv, pga, points)


# --- the model rows -------------------------------------------------------------------


def test_the_wall_state_follows_the_draw_and_the_position():
    state = fragility.wall_state(
        np.array(["fill", "cut", "fill", None], dtype=object),
        np.array([True, True, False, False]),
    )
    assert list(state) == ["fill_wall", "cut_wall", "no_wall", "no_wall"]
    with pytest.raises(ValueError, match="position"):
        fragility.wall_state(np.array([None], dtype=object), np.array([True]))


def test_a_polygon_with_a_wall_takes_the_wall_curve_and_one_without_the_localised():
    frame = three_polygons()
    model = fragility.assign_fragility(
        frame,
        two_walls(),
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame, 1.2),
    )
    assert list(model.columns) == list(fragility.MODEL_COLUMNS)
    # Sorted by slope_id with a fresh index: the frame was built in reverse.
    assert list(model["slope_id"]) == ["SP0000001", "SP0000002", "SP0000003"]
    assert list(model.index) == [0, 1, 2]
    by_id = model.set_index("slope_id")

    no_wall = by_id.loc["SP0000001"]  # rating 30, no line
    assert no_wall["wall_state"] == "no_wall"
    assert no_wall["fragility_basis"] == "localised"
    assert no_wall["fragility_source"] == "localised:30"
    assert pd.isna(no_wall["rw_id"])
    assert pd.isna(no_wall["theta_base_pga_g"])
    assert pd.isna(no_wall["pgv_pga_ratio_m_s_per_g"])
    expected = fragility.localised_theta_base_m_s(np.array([30.0]))[0]
    assert no_wall["theta_base"] == pytest.approx(expected)
    assert no_wall["theta"] == pytest.approx(expected / 1.25)
    assert no_wall["beta"] == constants.LOCALISED_FRAGILITY_BETA

    cut = by_id.loc["SP0000002"]  # the large old wall, position unknown
    assert cut["wall_state"] == "cut_wall"
    assert cut["rw_id"] == "C2-RW01"
    assert cut["fragility_basis"] == "wall"
    assert cut["fragility_source"] == "test_large_gravity_masonry"
    assert cut["wall_type"] == OLD
    assert cut["theta_base_pga_g"] == pytest.approx(0.6)
    assert cut["pgv_pga_ratio_m_s_per_g"] == pytest.approx(1.2)
    assert cut["theta_base"] == pytest.approx(0.72)
    assert cut["beta"] == 0.5

    fill = by_id.loc["SP0000003"]  # the small modern wall, position unknown
    assert fill["wall_state"] == "fill_wall"
    assert fill["size_class"] == "small"
    assert fill["wall_type"] == MODERN
    assert fill["theta_base_pga_g"] == pytest.approx(0.5)
    assert fill["pgv_pga_ratio_m_s_per_g"] == pytest.approx(1.2)
    assert fill["theta_base"] == pytest.approx(0.6)
    assert fill["theta"] == pytest.approx(0.6 / 1.25)

    assert set(model["im"]) == {"pgv_m_s"}
    assert set(model["rate_setting"]) == {"medium"}
    assert set(model["rate_factor"]) == {1.0}
    assert model["site_class"].dtype == "Int64"
    assert model["kingsbury_zone"].dtype == "Int64"
    # The state's geometry and depths were picked: every row has them.
    assert model["evacuated"].notna().all()
    assert model["depth_evacuated_m"].to_numpy().tolist() == [1.0, 1.0, 1.0]


def test_the_rate_setting_scales_every_median():
    frame = three_polygons()
    kwargs = {
        "site_class": site_class_at(frame),
        "pgv_pga_ratio": ratio_at(frame),
    }
    medium = fragility.assign_fragility(
        frame, two_walls(), wall_table(), rate_setting="medium", **kwargs
    )
    low = fragility.assign_fragility(
        frame, two_walls(), wall_table(), rate_setting="low", **kwargs
    )
    factor = constants.URBAN_RATE_FACTORS["low"]
    np.testing.assert_allclose(low["theta"], medium["theta"] * factor)
    assert set(low["rate_factor"]) == {factor}


def test_a_line_that_drew_two_walls_or_an_unknown_size_is_refused():
    frame = three_polygons()
    walls = two_walls()
    doubled = pd.concat([walls, walls.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="more than one wall"):
        fragility.assign_fragility(
            frame,
            doubled,
            wall_table(),
            rate_setting="medium",
            site_class=site_class_at(frame),
            pgv_pga_ratio=ratio_at(frame),
        )
    walls.loc[0, "size_class"] = "huge"
    with pytest.raises(ValueError, match="Unknown size class"):
        fragility.assign_fragility(
            frame,
            walls,
            wall_table(),
            rate_setting="medium",
            site_class=site_class_at(frame),
            pgv_pga_ratio=ratio_at(frame),
        )


def test_an_unknown_wall_type_or_a_type_with_no_curve_is_refused():
    frame = three_polygons()
    kwargs = {
        "rate_setting": "medium",
        "site_class": site_class_at(frame),
        "pgv_pga_ratio": ratio_at(frame),
    }
    walls = two_walls()
    walls.loc[0, "wall_type"] = "dry_stone"
    with pytest.raises(ValueError, match="wall type"):
        fragility.assign_fragility(frame, walls, wall_table(), **kwargs)
    table = wall_table()
    table = table[~((table["wall_type"] == OLD) & (table["size_class"] == "large"))]
    with pytest.raises(ValueError, match="No wall type curve"):
        fragility.assign_fragility(frame, two_walls(), table, **kwargs)


@pytest.mark.parametrize(
    ("position", "factor"),
    [
        (geometry.FILL, wall_type_fragility.FILL_CAPACITY_FACTOR),
        (geometry.CUT, wall_type_fragility.CUT_CAPACITY_FACTOR),
        (None, 1.0),
    ],
)
def test_the_walls_own_position_scales_its_pgv_median(position, factor):
    # The polygons keep their own positions (fill, then cut) for the wall
    # state; each wall's own position alone shifts its curve.
    frame = three_polygons()
    walls = wall_population(
        ["C1-RW01", "C2-RW01"],
        ["WL0000001", "WL0000002"],
        ["small", "small"],
        [MODERN, MODERN],
        positions=[position, position],
    )
    model = fragility.assign_fragility(
        frame,
        walls,
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame, 1.2),
    )
    by_line = model.set_index("wall_line_id", drop=False)
    for line, state in (("WL0000001", "fill_wall"), ("WL0000002", "cut_wall")):
        row = by_line.loc[line]
        assert row["wall_state"] == state
        assert row["theta_base_pga_g"] == pytest.approx(0.5 * factor)
        assert row["theta_base"] == pytest.approx(0.5 * factor * 1.2)
        assert row["beta"] == 0.5


def test_a_wall_whose_line_is_not_a_polygon_edge_draws_nothing():
    frame = three_polygons()
    walls = wall_population(["C9-RW01"], ["WL0000099"], ["medium"], [MODERN])
    model = fragility.assign_fragility(
        frame,
        walls,
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame),
    )
    assert set(model["wall_state"]) == {"no_wall"}
    assert model["rw_id"].isna().all()


def test_an_uninsured_wall_gives_its_polygon_the_wall_curve_with_no_rw_id():
    frame = three_polygons()
    insured = fragility.assign_fragility(
        frame,
        two_walls(),
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame, 1.2),
    )
    model = fragility.assign_fragility(
        frame,
        one_uninsured_wall(),
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame, 1.2),
    )
    by_line = model.set_index("wall_line_id", drop=False)
    uninsured = by_line.loc["WL0000001"]
    # The wall holds the slope whether or not it is insured: the state, the
    # curve and the state's geometry are the insured run's, rw_id aside.
    assert pd.isna(uninsured["rw_id"])
    assert uninsured["wall_state"] == "fill_wall"
    assert uninsured["fragility_basis"] == fragility.WALL_BASIS
    assert uninsured["fragility_source"] == "test_small_block_rc_cantilever"
    assert uninsured["size_class"] == "small"
    assert uninsured["wall_type"] == MODERN
    assert uninsured["theta_base"] == pytest.approx(0.6)
    assert by_line.loc["WL0000002", "rw_id"] == "C2-RW01"
    pd.testing.assert_frame_equal(
        model.drop(columns="rw_id"), insured.drop(columns="rw_id")
    )


def test_a_flat_land_wall_on_a_polygon_edge_leaves_the_polygon_no_wall():
    frame = three_polygons()
    walls = two_walls()
    walls.loc[0, "is_flatland"] = True
    model = fragility.assign_fragility(
        frame,
        walls,
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame),
    )
    by_line = model.set_index("wall_line_id", drop=False)
    flat_edge = by_line.loc["WL0000001"]
    assert flat_edge["wall_state"] == "no_wall"
    assert pd.isna(flat_edge["rw_id"])
    assert flat_edge["fragility_basis"] == fragility.LOCALISED_BASIS
    sloping_edge = by_line.loc["WL0000002"]
    assert sloping_edge["wall_state"] == "cut_wall"
    assert sloping_edge["rw_id"] == "C2-RW01"


def test_a_wall_on_any_line_of_the_edge_gives_the_polygon_its_wall():
    # One wall split at a property boundary into two lines along the fill
    # polygon's edge, WL0000001 (the longer) and WL0000003. Only the shorter
    # drew a wall: the polygon still takes it. Then both draw: the polygon
    # takes the longer line's wall and carries both lines.
    frame = polygons(
        [square(10, 10, 20), square(110, 10, 20)],
        wall_line_ids=["WL0000001", None],
        wall_positions=[geometry.FILL, None],
        ratings=[120.0, 30.0],
        edge_lines=[["WL0000001", "WL0000003"], []],
    )
    kwargs = {
        "rate_setting": "medium",
        "site_class": site_class_at(frame),
        "pgv_pga_ratio": ratio_at(frame),
    }
    shorter = wall_population(["C3-RW01"], ["WL0000003"], ["large"], [OLD])
    model = fragility.assign_fragility(frame, shorter, wall_table(), **kwargs)
    walled = model.set_index("slope_id").loc["SP0000002"]
    assert walled["wall_state"] == "fill_wall"
    assert walled["rw_id"] == "C3-RW01"
    assert walled["wall_line_id"] == "WL0000003"
    assert list(walled["wall_line_ids"]) == ["WL0000003"]
    assert walled["fragility_source"] == "test_large_gravity_masonry"

    both = wall_population(
        ["C1-RW01", "C3-RW01"],
        ["WL0000001", "WL0000003"],
        ["small", "large"],
        [MODERN, OLD],
    )
    model = fragility.assign_fragility(frame, both, wall_table(), **kwargs)
    walled = model.set_index("slope_id").loc["SP0000002"]
    assert walled["rw_id"] == "C1-RW01"
    assert walled["wall_line_id"] == "WL0000001"
    assert list(walled["wall_line_ids"]) == ["WL0000001", "WL0000003"]
    bare = model.set_index("slope_id").loc["SP0000001"]
    assert bare["wall_state"] == "no_wall"
    assert list(bare["wall_line_ids"]) == []


def test_polygons_without_the_edge_lines_are_refused():
    frame = three_polygons().drop(columns=geometry.WALL_LINE_IDS_COLUMN)
    with pytest.raises(ValueError, match="wall_line_ids"):
        fragility.assign_fragility(
            frame,
            two_walls(),
            wall_table(),
            rate_setting="medium",
            site_class=site_class_at(frame),
            pgv_pga_ratio=ratio_at(frame),
        )


def test_a_wall_population_without_is_flatland_is_refused():
    frame = three_polygons()
    walls = two_walls().drop(columns="is_flatland")
    with pytest.raises(ValueError, match="is_flatland"):
        fragility.assign_fragility(
            frame,
            walls,
            wall_table(),
            rate_setting="medium",
            site_class=site_class_at(frame),
            pgv_pga_ratio=ratio_at(frame),
        )


def test_sloping_walls_drops_flat_land_walls_and_walls_with_no_line():
    walls = wall_population(
        ["C1-RW01", "C2-RW01", "C3-RW01"],
        ["WL0000001", "WL0000002", None],
        ["small", "small", "small"],
        [MODERN, MODERN, MODERN],
    )
    walls.loc[1, "is_flatland"] = True
    kept = fragility.sloping_walls(walls)
    assert kept["rw_id"].tolist() == ["C1-RW01"]


# --- the anchoring --------------------------------------------------------------------


def synthetic_anchors(*, theta_0=2.0, theta_max=0.4, beta=0.5, ratio=1.0):
    """Anchors lying exactly on a known localised curve."""
    rows = []
    n = 0
    for rating in (10.0, 40.0, 80.0, 120.0, 145.0):
        theta = theta_0 * (theta_max / theta_0) ** (rating / susceptibility.MAX_RATING)
        for fraction in (0.02, 0.25, 0.6):
            n += 1
            pgv = theta * np.exp(beta * norm.ppf(fraction))
            rows.append(
                {
                    "anchor_id": f"A{n:02d}",
                    "source": "synthetic",
                    "zone": susceptibility.susceptibility_zone(np.array([rating]))[0],
                    "rating_min": rating - 5,
                    "rating_max": rating + 5,
                    "scenario": "synthetic",
                    "pga_rock_g_min": pgv / ratio,
                    "pga_rock_g_max": pgv / ratio,
                    "class_word": f"word_{fraction}",
                    "fail_fraction": fraction,
                    "set_by": "test",
                    "basis": "on the curve",
                }
            )
    return pd.DataFrame(rows)


def test_the_fit_recovers_a_curve_the_anchors_lie_on():
    fit = fragility.fit_localised_fragility(synthetic_anchors(), ratio_m_s_per_g=1.0)
    assert fit.theta_at_zero_rating_m_s == pytest.approx(2.0, rel=1e-6)
    assert fit.theta_at_max_rating_m_s == pytest.approx(0.4, rel=1e-6)
    assert fit.beta == pytest.approx(0.5, rel=1e-6)
    assert len(fit.anchors_used) == 15


def test_the_fit_on_the_packaged_anchors_gives_a_falling_median():
    fit = fragility.fit_localised_fragility(
        fragility.load_urban_fragility_anchors(), ratio_m_s_per_g=1.0
    )
    assert fit.theta_at_zero_rating_m_s > fit.theta_at_max_rating_m_s > 0
    assert fit.beta > 0


def test_too_few_anchors_are_refused():
    with pytest.raises(ValueError, match="at least 3"):
        fragility.fit_localised_fragility(
            synthetic_anchors().iloc[:2], ratio_m_s_per_g=1.0
        )


# --- step 12's zones as polygons ------------------------------------------------------


def test_face_polygons_take_their_wall_from_their_elements_unit():
    frame = three_face_polygons()
    assert list(frame["slope_id"]) == ["SP0000001", "SP0000002", "SP0000003"]
    assert list(frame["polygon"]) == [1, 2, 3]
    assert list(frame["wall_line_id"]) == ["WU0000001", "WU0000002", None]
    assert [list(cell) for cell in frame["wall_line_ids"]] == [
        ["WU0000001"],
        ["WU0000002"],
        [],
    ]
    assert list(frame["wall_position"]) == ["fill", "cut", None]
    assert list(frame[face_polygons.IS_WALLED_COLUMN]) == [True, True, False]
    assert (frame[geometry.SCALE_COLUMN] == face_polygons.FACE_SCALE_M).all()


def test_a_face_on_a_gns_only_units_line_takes_that_unit():
    elements = step12_elements().assign(wall_unit_id=[None, None, "WU0000009"])
    units = pd.concat(
        [
            step12_units(),
            gpd.GeoDataFrame(
                {"member_pif_ids": [[]], "is_fill": [False]},
                geometry=[square(FACE_XS[2], 10, 20).boundary],
                index=pd.Index(["WU0000009"], name="wall_unit_id"),
                crs=constants.DEFAULT_CRS,
            ),
        ]
    )
    frame = face_polygons.face_polygons(
        step12_zones(), elements, units, step12_ground_map()
    )
    assert list(frame["wall_line_id"]) == ["WU0000001", "WU0000002", "WU0000009"]
    assert list(frame["wall_position"]) == ["fill", "cut", "cut"]


def test_face_polygons_outside_the_extent_are_left_out_before_the_ids():
    # The box ends at x = 150 m: the third face (x 210 to 230 m) is outside.
    frame = face_polygons.face_polygons(
        step12_zones(),
        step12_elements(),
        step12_units(),
        step12_ground_map(),
        bbox=(X0, Y0, X0 + 150.0, Y0 + 100.0),
    )
    assert list(frame["polygon"]) == [1, 2]
    assert list(frame["slope_id"]) == ["SP0000001", "SP0000002"]


def test_face_polygons_carry_the_worlds_zones_and_depths():
    frame = three_face_polygons()
    assert frame.geometry.iloc[0].equals(square(10, 10, 20))
    assert frame["evacuated"].iloc[0].equals(square(10, 10, 20))
    assert frame["imminent"].iloc[1].equals(square(110, 30, 5))
    assert frame["inundated"].iloc[2] is None
    np.testing.assert_allclose(frame["depth_evacuated_m"], 1.0)
    np.testing.assert_allclose(frame["depth_inundated_m"].iloc[:2], 4.0)
    assert np.isnan(frame["depth_inundated_m"].iloc[2])


def test_an_element_off_the_ground_map_is_scored_on_the_default_ground():
    frame = three_face_polygons()
    assert (
        frame["geology_value"].iloc[0] == susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM
    )
    assert (
        frame["geology_value"].iloc[2]
        == (face_polygons.BETA_OFF_MAP_GROUND["geology_value"])
    )
    assert frame["material"].iloc[2] == "rock"
    assert frame["continuous_rating"].notna().all()
    assert frame["kingsbury_rating"].iloc[2] < frame["kingsbury_rating"].iloc[0]


def test_the_amplification_reads_the_topographic_position():
    frame = face_polygons.with_amplification(three_face_polygons(), [0.0, 10.0, np.nan])
    top = constants.TOPOGRAPHIC_AMPLIFICATION_MAX
    steep = 1.0 + (top - 1.0) * (10.0 / 30.0)
    np.testing.assert_allclose(frame["amp_factor"], [steep, top, steep])


def test_a_pif_in_two_units_is_refused():
    units = step12_units()
    units["member_pif_ids"] = [[11], [11, 12]]
    with pytest.raises(ValueError, match="pifs in two wall units"):
        face_polygons.face_polygons(
            step12_zones(), step12_elements(), units, step12_ground_map()
        )


def test_zones_and_walls_of_one_draw_pass_the_check():
    face_polygons.check_zones_match_walls(three_face_polygons(), unit_walls())


def test_walls_named_by_old_line_ids_are_refused():
    walls = unit_walls()
    walls["wall_line_id"] = ["WL0000001", "WL0000002"]
    with pytest.raises(ValueError, match="walled in the zones but their unit is not"):
        face_polygons.check_zones_match_walls(three_face_polygons(), walls)


def test_a_bare_polygon_on_a_drawn_wall_is_refused():
    with pytest.raises(ValueError, match="bare in the zones but their unit is a drawn"):
        face_polygons.check_zones_match_walls(
            three_face_polygons(walled=(True, False, False)), unit_walls()
        )


def test_a_flat_land_wall_does_not_count_as_drawn_for_the_check():
    walls = unit_walls()
    walls.loc[1, "is_flatland"] = True
    with pytest.raises(ValueError, match="not a drawn wall"):
        face_polygons.check_zones_match_walls(three_face_polygons(), walls)


def test_face_polygons_take_the_wall_curve_and_keep_their_own_geometry():
    frame = face_polygons.with_amplification(three_face_polygons(), np.zeros(3))
    model = fragility.assign_fragility(
        frame,
        unit_walls(),
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame),
    )
    assert list(model["wall_state"]) == ["fill_wall", "cut_wall", "no_wall"]
    assert list(model["fragility_basis"]) == ["wall", "wall", "localised"]
    assert pd.isna(model["rw_id"].iloc[0])
    assert model["rw_id"].iloc[1] == "C2-RW01"
    assert [list(cell) for cell in model["wall_line_ids"]] == [
        ["WU0000001"],
        ["WU0000002"],
        [],
    ]
    assert model["evacuated"].iloc[2].equals(square(210, 10, 20))
    np.testing.assert_allclose(model["depth_inundated_m"].iloc[:2], 4.0)


# --- the step end to end --------------------------------------------------------------


@pytest.fixture
def work_dirs(tmp_path, monkeypatch):
    """Point every input and output of the step at tmp_path."""
    landslide = tmp_path / "landslide"
    shaking = tmp_path / "shaking"
    exposure = tmp_path / "exposure"
    for path in (landslide, shaking, exposure):
        path.mkdir()
    monkeypatch.setattr(gen_urban_slope_faces, "WORK_DIR", landslide)
    monkeypatch.setattr(gen_urban_slope_wall_units, "WORK_DIR", landslide)
    monkeypatch.setattr(gen_ground_map, "WORK_DIR", landslide)
    monkeypatch.setattr(gen_terrain_derivatives, "TERRAIN_DIR", landslide / "terrain")
    monkeypatch.setattr(step, "WORK_DIR", landslide)
    monkeypatch.setattr(gen_site_class, "WORK_DIR", shaking)
    monkeypatch.setattr(gen_pgv, "WORK_DIR", shaking)
    monkeypatch.setattr(gen_wall_population, "WORK_DIR", exposure)
    monkeypatch.setattr(table_urban_slope_model, "TAB_DIR", tmp_path / "tab")
    monkeypatch.setattr(fig_urban_slope_model, "FIG_DIR", tmp_path / "fig")
    # The basemap needs the network; the panel is drawn without it.
    monkeypatch.setattr(fig_urban_slope_model, "style_basemap_ax", lambda *a, **k: None)
    return tmp_path


def write_inputs(monkeypatch):
    """Write step 12's files, the walls and the four grids where the step reads them."""
    extent = "wlg-pilot"
    step12_zones().to_parquet(
        gen_urban_slope_faces.zones_path(f"w{WORLD:03d}", extent=extent)
    )
    step12_elements().assign(wall_unit_id=None).to_parquet(
        gen_urban_slope_faces.wall_elements_path(extent=extent)
    )
    step12_units().to_parquet(gen_urban_slope_wall_units.wall_units_path(extent=extent))
    step12_ground_map().to_parquet(gen_ground_map.ground_map_path(extent=extent))
    tpi_path = gen_terrain_derivatives.terrain_path(
        "topographic-position-100m", extent=extent
    )
    tpi_path.parent.mkdir(parents=True, exist_ok=True)
    write_raster(make_grid(np.zeros((2, 3))).astype("float32"), tpi_path)
    unit_walls().to_parquet(gen_wall_population.drawn_walls_path(WORLD, extent=extent))
    # Two rows of three 100 m cells: the three polygons sit in the bottom row
    # left to right (a one-row grid has no y resolution to write).
    site_class = make_grid([[2.0, 2.0, 2.0], [1.0, 3.0, 5.0]])
    write_raster(
        site_class.astype("float32"), gen_site_class.site_class_path(extent="wlg-pilot")
    )
    pgv = make_grid([[1.0, 1.0, 1.0], [0.6, 1.2, 2.0]]).rename("pgv_m_s")
    write_raster(
        pgv.astype("float32"),
        gen_pgv.output_path(
            "pgv", return_period_yr=RETURN_PERIOD_YR, extent="wlg-pilot"
        ),
    )
    pga = make_grid([[1.0, 1.0, 1.0], [0.5, 1.0, 1.0]])
    monkeypatch.setattr(
        step, "demand_on_site_class_grid", lambda *_args, **_kwargs: pga
    )
    monkeypatch.setattr(step, "get_ts1170_pga", None)


def test_the_step_prints_the_flat_land_walls_it_skips(capsys):
    walls = wall_population(
        ["C1-RW01", "C2-RW01", "C9-RW01"],
        ["WL0000001", "WL0000002", "WL0000099"],
        ["small", "large", "small"],
        [MODERN, OLD, MODERN],
    )
    walls.loc[[0, 2], "is_flatland"] = True
    step.describe_flatland_walls(three_polygons(), walls)
    out = capsys.readouterr().out
    assert "2 flat-land walls skipped" in out
    assert "1 of them a polygon's unit" in out


def test_the_path_names_the_world_and_the_extent():
    assert step.urban_slope_model_path(3, extent="wlg-pilot").name == (
        "urban-slope-model-w003-pilot.geoparquet"
    )
    assert step.urban_slope_model_path(12, extent="full").name == (
        "urban-slope-model-w012.geoparquet"
    )


@ignore_affine_matmul
def test_the_step_writes_the_model_with_the_contract_columns(work_dirs, monkeypatch):
    write_inputs(monkeypatch)
    step.main(
        extent="wlg-pilot",
        world_ids=[WORLD],
        urban_rate="medium",
        return_period_yr=RETURN_PERIOD_YR,
    )

    written = gpd.read_parquet(step.urban_slope_model_path(WORLD, extent="wlg-pilot"))
    assert list(written.columns) == list(step.MODEL_COLUMNS)
    assert list(written.columns[:2]) == ["slope_id", "world_id"]
    assert written.crs == constants.DEFAULT_CRS
    assert list(written["slope_id"]) == ["SP0000001", "SP0000002", "SP0000003"]
    assert list(written.index) == [0, 1, 2]
    assert set(written["world_id"]) == {WORLD}
    assert written["world_id"].dtype == "int64"
    assert written["site_class"].dtype == "Int64"
    # The site class and the ratio were read at each polygon's cell: the
    # polygons sit in the three cells left to right, in id order.
    by_id = written.set_index("slope_id")
    assert by_id.loc["SP0000001", "site_class"] == 1
    assert by_id.loc["SP0000001", "pgv_pga_ratio_m_s_per_g"] == pytest.approx(1.2)
    # The packaged curve of the small modern wall, shifted for its unit's
    # fill, then converted at the cell's ratio.
    packaged = wall_type_fragility.load_wall_type_fragility().set_index(
        list(wall_type_fragility.TABLE_KEY)
    )
    assert by_id.loc["SP0000001", "wall_type"] == MODERN
    assert by_id.loc["SP0000001", "theta_base"] == pytest.approx(
        packaged.loc[(MODERN, "small"), "theta"]
        * wall_type_fragility.FILL_CAPACITY_FACTOR
        * 1.2
    )
    assert by_id.loc["SP0000003", "site_class"] == 5
    assert pd.isna(by_id.loc["SP0000003", "pgv_pga_ratio_m_s_per_g"])
    assert by_id.loc["SP0000003", "fragility_basis"] == "localised"
    assert by_id.loc["SP0000003", "wall_state"] == "no_wall"
    assert set(written["rate_setting"]) == {"medium"}
    assert written["evacuated"].notna().all()
    # The polygons are step 12's zones of the world: their geometry is the
    # zones' and their wall is their element's wall unit.
    assert by_id.loc["SP0000001", "evacuated"].equals(square(10, 10, 20))
    assert list(written["wall_line_id"].iloc[:2]) == ["WU0000001", "WU0000002"]
    # The drawn walls were read, not the insured population: the uninsured
    # wall unit of SP0000001 gives it the wall curve with rw_id null.
    assert pd.isna(by_id.loc["SP0000001", "rw_id"])
    assert by_id.loc["SP0000001", "wall_state"] == "fill_wall"
    assert by_id.loc["SP0000001", "fragility_basis"] == "wall"
    assert by_id.loc["SP0000002", "rw_id"] == "C2-RW01"
    assert by_id.loc["SP0000002", "wall_state"] == "cut_wall"


@ignore_affine_matmul
def test_the_table_and_the_figure_read_the_model_the_step_wrote(work_dirs, monkeypatch):
    write_inputs(monkeypatch)
    step.main(
        extent="wlg-pilot",
        world_ids=[WORLD],
        urban_rate="high",
        return_period_yr=RETURN_PERIOD_YR,
    )

    table_urban_slope_model.main(extent="wlg-pilot", world_ids=[WORLD])
    table_path = table_urban_slope_model.table_path(WORLD, extent="wlg-pilot")
    assert table_path.name == "urban-slope-model-medians-w000-pilot.csv"
    table = pd.read_csv(table_path)
    assert list(table.columns) == list(table_urban_slope_model.TABLE_COLUMNS)
    assert table["polygons"].sum() == 3
    assert set(table["wall_state"]) == {"no_wall", "fill_wall", "cut_wall"}
    np.testing.assert_allclose(
        table["rate_factor"], constants.URBAN_RATE_FACTORS["high"], atol=1e-4
    )

    fig_urban_slope_model.main(extent="wlg-pilot", world_ids=[WORLD])
    assert (work_dirs / "fig" / "urban-slope-model-w000-pilot.png").exists()


def test_a_polygon_with_no_zone_is_grouped_under_none():
    frame = three_polygons()
    model = fragility.assign_fragility(
        frame,
        two_walls(),
        wall_table(),
        rate_setting="medium",
        site_class=site_class_at(frame),
        pgv_pga_ratio=ratio_at(frame),
    )
    model["kingsbury_zone"] = pd.array([None, 3, 4], dtype="Int64")
    table = table_urban_slope_model.medians_by_zone_and_state(model)
    assert "none" in table["kingsbury_zone"].astype(str).tolist()
    assert table.loc[
        table["kingsbury_zone"].astype(str) == "none", "zone_label"
    ].tolist() == ["no rating"]


# --- the validation -------------------------------------------------------------------


def test_the_class_word_table_has_one_row_per_word():
    anchors = fragility.load_urban_fragility_anchors()
    table = table_urban_fragility_anchors.class_word_table(anchors)
    assert list(table.columns) == list(table_urban_fragility_anchors.TABLE_COLUMNS)
    assert table["class_word"].is_unique
    assert set(table["class_word"]) == set(anchors["class_word"])
    assert table["fail_fraction"].is_monotonic_increasing
    assert table["basis"].str.startswith("Anchors A").all()


def test_a_word_read_two_ways_is_refused():
    anchors = synthetic_anchors()
    anchors.loc[0, "fail_fraction"] = 0.03
    with pytest.raises(ValueError, match="one fraction per word"):
        table_urban_fragility_anchors.class_word_table(anchors)


def test_the_validation_table_script_writes_the_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(table_urban_fragility_anchors, "TAB_DIR", tmp_path)
    table_urban_fragility_anchors.main()
    written = pd.read_csv(tmp_path / "urban-fragility-anchors.csv")
    assert list(written.columns) == ["class_word", "fail_fraction", "set_by", "basis"]


@ignore_affine_matmul
def test_the_rock_site_ratio_is_the_median_over_the_cells_inside_the_extent():
    # PGV = 0.75 x Sa(1.0 s) in m/s, so Sa 1.0 g over PGA 0.5 g is 1.5 m/s per g.
    sa_t1 = make_grid([[1.0, 1.0, 4.0], [1.0, np.nan, 4.0]])
    pga = make_grid([[0.5, 0.5, 1.0], [0.5, 0.5, 1.0]])
    inside = box(X0, Y0, X0 + 2 * CELL_M, Y0 + 2 * CELL_M)
    ratio = fig_urban_fragility_anchors.rock_site_ratio_m_s_per_g(sa_t1, pga, inside)
    assert ratio == pytest.approx(1.5)
    # An extent no cell centre falls in takes the nearest finite cell.
    small = box(
        X0 + 2.6 * CELL_M, Y0 + 0.4 * CELL_M, X0 + 2.7 * CELL_M, Y0 + 0.5 * CELL_M
    )
    near = fig_urban_fragility_anchors.rock_site_ratio_m_s_per_g(sa_t1, pga, small)
    assert near == pytest.approx(3.0)
    empty = make_grid([[np.nan, np.nan, np.nan], [np.nan, np.nan, np.nan]])
    with pytest.raises(ValueError, match="no finite"):
        fig_urban_fragility_anchors.rock_site_ratio_m_s_per_g(empty, pga, small)


def test_the_zone_bands_tile_the_rating_scale():
    bands = fig_urban_fragility_anchors.zone_rating_bands()
    assert list(bands) == list(susceptibility.ZONE_RANKS)
    assert bands[1][0] == 0.0
    assert bands[5][1] == susceptibility.MAX_RATING
    for rank in susceptibility.ZONE_RANKS[1:]:
        assert bands[rank][0] == bands[rank - 1][1]


def test_the_validation_figure_script_runs_on_the_packaged_anchors(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fig_urban_fragility_anchors, "FIG_DIR", tmp_path)
    monkeypatch.setattr(
        fig_urban_fragility_anchors, "read_rock_site_ratio", lambda **_kwargs: 1.1
    )
    fig_urban_fragility_anchors.main()
    assert (tmp_path / "urban-fragility-anchors.png").exists()


def test_the_validation_figure_draws_without_a_fit():
    anchors = fragility.load_urban_fragility_anchors()
    fig = fig_urban_fragility_anchors.build_figure(
        anchors, ratio_m_s_per_g=1.0, fit=None
    )
    assert len(fig.axes) >= 5


@ignore_affine_matmul
def test_the_step_stops_on_zones_and_walls_from_different_draws(work_dirs, monkeypatch):
    write_inputs(monkeypatch)
    # Step 7's wall line ids, as rw step 6 wrote them before the wall units.
    old = unit_walls()
    old["wall_line_id"] = ["WL0000001", "WL0000002"]
    old.to_parquet(gen_wall_population.drawn_walls_path(WORLD, extent="wlg-pilot"))
    with pytest.raises(ValueError, match="not one wall draw"):
        step.main(
            extent="wlg-pilot",
            world_ids=[WORLD],
            urban_rate="medium",
            return_period_yr=RETURN_PERIOD_YR,
        )


@ignore_affine_matmul
def test_a_world_without_zones_is_refused(work_dirs, monkeypatch):
    write_inputs(monkeypatch)
    elements, units, ground_map = step.read_step12_inputs(extent="wlg-pilot")
    with pytest.raises(FileNotFoundError, match="gen_urban_slope_wall_zones"):
        step.read_polygons(
            7,
            extent="wlg-pilot",
            elements=elements,
            units=units,
            ground_map=ground_map,
        )
