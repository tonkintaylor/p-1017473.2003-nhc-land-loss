"""Tests for the urban slope realisation, on hand-built inputs.

Model rows are square faces in NZTM with their fixed geometry set by hand, so
every nesting and supersession can be worked out on paper; the PGV grid is a
few 100 m cells written where shaking step 5 would write it; the large-model
realisation is one circle. Fragilities are pushed to the ends -- a tiny median
fails under any shaking, a huge one never does -- where an outcome has to be
exact, and left in the middle where the draw itself is under test.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import Point, box

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    IMMINENT,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.hazard.landslide.urban import realisation as urban
from landloss.hazard.realisation import realisation_seed
from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    gen_wall_population,
)
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import (
    s1_simulate_landslides,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility import (
    gen_urban_slope_fragility,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import (
    fig_urban_slope_realisation as fig,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import (
    gen_urban_slope_realisation as step,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import (
    gen_pgv_realisations,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM; the PGV grid's top left.
X0 = 1_748_000.0
Y0 = 5_425_000.0
CELL_M = 100.0

# Medians that make the draw certain either way, and one in the middle.
ALWAYS_FAILS_M_S = 1e-6
NEVER_FAILS_M_S = 1e6
MIDDLE_M_S = 1.0
BETA = 0.6

WORLD = 0
EARTHQUAKE = 0


def make_grid(values, resolution=CELL_M):
    """Wrap an array as a north-up raster in NZTM with its top left at (X0, Y0)."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    eastings = X0 + resolution * (np.arange(columns) + 0.5)
    northings = Y0 - resolution * (np.arange(rows) + 0.5)
    grid = xr.DataArray(values, dims=("y", "x"), coords={"y": northings, "x": eastings})
    return grid.rio.write_crs(constants.DEFAULT_CRS)


def square(x, y, side):
    """A face with its lower-left corner at (x, y) metres into the grid."""
    return box(X0 + x, Y0 - y - side, X0 + x + side, Y0 - y)


def line_of(rw_id):
    """The wall line a synthetic wall stands on, named after the wall."""
    return f"WL-{rw_id}"


def model_rows(
    faces,
    *,
    theta,
    rw_ids=None,
    wall_states=None,
    wall_line_ids=None,
    edge_lines=None,
    rate_setting="medium",
):
    """Synthetic step 8 model rows, one per face, in slope_id order.

    Every state geometry is the face itself, so absorption and supersession
    are decided by the faces alone. Without ``wall_line_ids`` each row with an
    ``rw_id`` stands on that wall's line (:func:`line_of`); without
    ``edge_lines`` a row's only edge line that drew a wall is its own.
    """
    count = len(faces)
    theta = list(theta) if np.ndim(theta) else [theta] * count
    rw_ids = [None] * count if rw_ids is None else list(rw_ids)
    wall_states = ["no_wall"] * count if wall_states is None else list(wall_states)
    if wall_line_ids is None:
        wall_line_ids = [None if rw is None else line_of(rw) for rw in rw_ids]
    if edge_lines is None:
        edge_lines = [[] if line is None else [line] for line in wall_line_ids]
    faces = list(faces)
    frame = gpd.GeoDataFrame(
        {
            "slope_id": [f"SP{n:07d}" for n in range(1, count + 1)],
            "world_id": WORLD,
            "wall_line_id": list(wall_line_ids),
            "wall_line_ids": pd.Series(list(edge_lines), dtype=object),
            "rw_id": rw_ids,
            "wall_state": wall_states,
            "rate_setting": rate_setting,
            "rate_factor": constants.URBAN_RATE_FACTORS[rate_setting],
            "theta": theta,
            "beta": BETA,
            "scale_m": 3,
            "area_m2": [face.area for face in faces],
            "depth_evacuated_m": 1.0,
            "depth_inundated_m": 0.5,
            "rep_point": gpd.GeoSeries(
                [face.representative_point() for face in faces],
                crs=constants.DEFAULT_CRS,
            ),
            "evacuated": gpd.GeoSeries(faces, crs=constants.DEFAULT_CRS),
            "inundated": gpd.GeoSeries(faces, crs=constants.DEFAULT_CRS),
            "imminent": gpd.GeoSeries(faces, crs=constants.DEFAULT_CRS),
        },
        geometry=faces,
        crs=constants.DEFAULT_CRS,
    )
    return frame.sort_values("slope_id").reset_index(drop=True)


def wall_population(rw_ids, *, flat=(), wall_line_ids=None):
    """Synthetic step 6 walls, one per rw_id on its own line, flat where listed."""
    if wall_line_ids is None:
        wall_line_ids = [line_of(rw) for rw in rw_ids]
    return gpd.GeoDataFrame(
        {
            "rw_id": list(rw_ids),
            "claim_id": [rw.split("-")[0] for rw in rw_ids],
            "wall_line_id": list(wall_line_ids),
            "world_id": WORLD,
            "is_flatland": [rw in flat for rw in rw_ids],
        },
        geometry=[square(0, 0, 1).exterior for _ in rw_ids],
        crs=constants.DEFAULT_CRS,
    )


LARGE_COLUMNS = (
    "realisation_id",
    "landslide_id",
    "population",
    "slope_id",
    "unit_id",
    LAND_CLASS_COLUMN,
    "depth_m",
    "volume_m3",
    "source_area_m2",
    "failure_probability",
    "geometry",
)


def large_rows(circles, realisation_id=EARTHQUAKE):
    """Synthetic step 1 rows: an evacuated and an inundated row per circle."""
    circles = list(circles)
    rows = []
    for n, circle in enumerate(circles, 1):
        for land_class in (EVACUATED, INUNDATED):
            rows.append(
                {
                    "realisation_id": realisation_id,
                    "landslide_id": f"LS{n:07d}",
                    "population": urban.LARGE,
                    "slope_id": None,
                    "unit_id": "SU0000001",
                    LAND_CLASS_COLUMN: land_class,
                    "depth_m": 2.0,
                    "volume_m3": 2.0 * circle.area,
                    "source_area_m2": circle.area,
                    "failure_probability": 0.1,
                    "geometry": circle,
                }
            )
    frame = pd.DataFrame(rows, columns=list(LARGE_COLUMNS))
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=constants.DEFAULT_CRS)


def no_large():
    return large_rows([])


def draws_for(model, *, pgv=1.0, world_id=WORLD, realisation_id=EARTHQUAKE):
    rng = realisation_seed(
        constants.BASE_SEED, realisation_id, urban.URBAN_STREAM, world_id=world_id
    )
    pgv_series = pd.Series(pgv, index=model.index, dtype=float)
    return urban.draw_failures(model, pgv_series, rng)


# --- The draw ---------------------------------------------------------------


def test_the_fragility_is_the_lognormal_at_the_sampled_pgv():
    model = model_rows([square(0, 0, 10)], theta=MIDDLE_M_S)
    draws = draws_for(model, pgv=MIDDLE_M_S)
    # At PGV equal to the median the probability of failure is one half.
    assert draws["p_fail"].iloc[0] == pytest.approx(0.5)
    assert draws["pgv_m_s"].iloc[0] == MIDDLE_M_S
    assert draws["failed"].iloc[0] == (draws["uniform"].iloc[0] < 0.5)


def test_a_polygon_off_the_pgv_grid_is_not_drawn():
    model = model_rows([square(0, 0, 10)], theta=ALWAYS_FAILS_M_S)
    draws = draws_for(model, pgv=np.nan)
    assert np.isnan(draws["p_fail"].iloc[0])
    assert not draws["failed"].iloc[0]


def test_the_same_world_and_earthquake_reproduce_and_another_world_differs():
    model = model_rows([square(0, 0, 10)] * 6, theta=MIDDLE_M_S)
    again = draws_for(model)
    assert np.array_equal(draws_for(model)["uniform"], again["uniform"])
    other_world = draws_for(model, world_id=WORLD + 1)
    assert not np.array_equal(other_world["uniform"], again["uniform"])
    other_earthquake = draws_for(model, realisation_id=EARTHQUAKE + 1)
    assert not np.array_equal(other_earthquake["uniform"], again["uniform"])


def test_the_draw_is_in_model_order_so_a_uniform_is_tied_to_its_row():
    model = model_rows([square(0, 0, 10)] * 4, theta=MIDDLE_M_S)
    expected = realisation_seed(
        constants.BASE_SEED, EARTHQUAKE, urban.URBAN_STREAM, world_id=WORLD
    ).random(4)
    assert np.array_equal(draws_for(model)["uniform"], expected)


def test_rows_on_one_wall_line_read_one_uniform_and_fail_or_stand_together():
    # One wall line on polygons at two scales (rows 1 and 3), a polygon with no
    # wall between them, and a polygon on a second wall line. The two rows on
    # the first line read the first row's uniform; the others keep their own.
    model = model_rows(
        [square(0, 0, 10), square(20, 0, 10), square(2, 2, 3), square(40, 0, 10)],
        theta=MIDDLE_M_S,
        rw_ids=["A-RW01", None, "A-RW01", "B-RW01"],
        wall_states=["cut_wall", "no_wall", "cut_wall", "fill_wall"],
        wall_line_ids=["WL0000001", None, "WL0000001", "WL0000002"],
    )
    outcomes = set()
    for earthquake in range(20):
        own = realisation_seed(
            constants.BASE_SEED, earthquake, urban.URBAN_STREAM, world_id=WORLD
        ).random(len(model))
        draws = draws_for(model, pgv=MIDDLE_M_S, realisation_id=earthquake)
        uniform = draws["uniform"].to_numpy()
        assert uniform.tolist() == [own[0], own[1], own[0], own[3]]
        failed = draws["failed"].to_numpy()
        assert failed[0] == failed[2]
        outcomes.add(bool(failed[0]))
    # Over twenty earthquakes at p = 0.5 the shared wall both failed and stood.
    assert outcomes == {True, False}


def test_rows_sharing_any_wall_line_read_one_uniform_transitively():
    # Row 1 carries a wall split at a property boundary into two lines; row 2
    # carries the second line only, row 3 a line of its own. Rows 1 and 2 are
    # one wall and read row 1's uniform; row 3 keeps its own.
    model = model_rows(
        [square(0, 0, 10), square(2, 2, 3), square(40, 0, 10)],
        theta=MIDDLE_M_S,
        rw_ids=["A-RW01", "B-RW01", "C-RW01"],
        wall_states=["fill_wall", "fill_wall", "cut_wall"],
        wall_line_ids=["WL0000001", "WL0000002", "WL0000003"],
        edge_lines=[["WL0000001", "WL0000002"], ["WL0000002"], ["WL0000003"]],
    )
    own = realisation_seed(
        constants.BASE_SEED, EARTHQUAKE, urban.URBAN_STREAM, world_id=WORLD
    ).random(3)
    assert draws_for(model)["uniform"].tolist() == [own[0], own[0], own[2]]


def test_if_any_polygon_on_a_wall_fails_every_polygon_on_it_fails():
    """The wall fails once and takes all the ground it holds up (the lead's rule)."""
    model = model_rows(
        [square(0, 0, 20), square(5, 5, 5), square(60, 0, 10), square(90, 0, 10)],
        theta=[NEVER_FAILS_M_S, ALWAYS_FAILS_M_S, NEVER_FAILS_M_S, ALWAYS_FAILS_M_S],
        rw_ids=["A-RW01", "A-RW01", None, None],
        wall_states=["fill_wall", "fill_wall", "no_wall", "no_wall"],
        wall_line_ids=["WL0000001", "WL0000001", None, None],
    )
    draws = draws_for(model)
    # The bank on its own would never fail, but its wall failed through the face.
    assert draws[urban.FAILED_COLUMN].tolist() == [True, True, False, True]
    # Each row keeps its own probability.
    assert draws[urban.P_FAIL_COLUMN].iloc[0] == pytest.approx(0.0)


def test_a_wall_none_of_whose_polygons_fail_stands_for_all_of_them():
    """No polygon on a wall failing leaves every one of them standing."""
    model = model_rows(
        [square(0, 0, 20), square(5, 5, 5)],
        theta=NEVER_FAILS_M_S,
        rw_ids=["A-RW01", "A-RW01"],
        wall_states=["fill_wall", "fill_wall"],
        wall_line_ids=["WL0000001", "WL0000001"],
    )
    assert not draws_for(model)[urban.FAILED_COLUMN].any()


def test_a_walled_row_with_no_wall_line_keeps_its_own_uniform():
    model = model_rows(
        [square(0, 0, 10), square(2, 2, 3)],
        theta=MIDDLE_M_S,
        rw_ids=["A-RW01", "A-RW01"],
        wall_states=["cut_wall", "cut_wall"],
        wall_line_ids=[None, None],
    )
    own = realisation_seed(
        constants.BASE_SEED, EARTHQUAKE, urban.URBAN_STREAM, world_id=WORLD
    ).random(2)
    assert draws_for(model)["uniform"].tolist() == own.tolist()


# --- Absorption and supersession --------------------------------------------


def test_a_nested_pair_resolves_largest_first():
    faces = gpd.GeoSeries(
        [square(2, 2, 3), square(0, 0, 10)], crs=constants.DEFAULT_CRS
    )
    absorbed_by = urban.resolve_overlaps(faces, faces.area.to_numpy())
    assert absorbed_by.tolist() == [1, urban.NONE]


def test_an_absorbed_polygon_absorbs_nothing():
    # Three in a chain: the middle one touches the largest, the smallest
    # touches only the middle. The smallest survives, because the polygon
    # that would have taken it did not happen.
    faces = gpd.GeoSeries(
        [square(0, 0, 10), square(8, 0, 5), square(12, 0, 2)],
        crs=constants.DEFAULT_CRS,
    )
    absorbed_by = urban.resolve_overlaps(faces, faces.area.to_numpy())
    assert absorbed_by.tolist() == [urban.NONE, 0, urban.NONE]


def test_ties_resolve_in_incoming_order():
    faces = gpd.GeoSeries(
        [square(0, 0, 10), square(5, 0, 10)], crs=constants.DEFAULT_CRS
    )
    absorbed_by = urban.resolve_overlaps(faces, faces.area.to_numpy())
    assert absorbed_by.tolist() == [urban.NONE, 0]


def test_two_failures_that_only_share_an_edge_both_survive():
    # Neighbouring candidates of one scale tile the ground, so they touch;
    # touching is not nesting.
    faces = gpd.GeoSeries(
        [square(0, 0, 10), square(10, 0, 5)], crs=constants.DEFAULT_CRS
    )
    absorbed_by = urban.resolve_overlaps(faces, faces.area.to_numpy())
    assert absorbed_by.tolist() == [urban.NONE, urban.NONE]


def test_two_failures_that_only_share_a_corner_both_survive():
    faces = gpd.GeoSeries(
        [square(0, 0, 10), square(10, 10, 5)], crs=constants.DEFAULT_CRS
    )
    absorbed_by = urban.resolve_overlaps(faces, faces.area.to_numpy())
    assert absorbed_by.tolist() == [urban.NONE, urban.NONE]


def test_a_polygon_touching_a_large_landslide_is_not_superseded():
    # The first face shares an edge with the large polygon, the second a
    # corner; neither shares ground with it. The third overlaps it.
    faces = gpd.GeoSeries(
        [square(0, 0, 10), square(20, 10, 5), square(15, 0, 3)],
        crs=constants.DEFAULT_CRS,
    )
    large = gpd.GeoSeries([square(10, 0, 10)], crs=constants.DEFAULT_CRS)
    assert urban.supersede_by_large(faces, large).tolist() == [
        urban.NONE,
        urban.NONE,
        0,
    ]


def test_a_polygon_inside_a_large_landslide_is_superseded_by_it():
    faces = gpd.GeoSeries(
        [square(0, 0, 4), square(50, 50, 4)], crs=constants.DEFAULT_CRS
    )
    large = gpd.GeoSeries([Point(X0 + 2, Y0 - 2).buffer(10)], crs=constants.DEFAULT_CRS)
    assert urban.supersede_by_large(faces, large).tolist() == [0, urban.NONE]


def test_the_large_polygon_sharing_the_most_ground_takes_it():
    face = gpd.GeoSeries([square(0, 0, 10)], crs=constants.DEFAULT_CRS)
    large = gpd.GeoSeries(
        [square(9, 0, 10), square(5, 0, 10)], crs=constants.DEFAULT_CRS
    )
    assert urban.supersede_by_large(face, large).tolist() == [1]


def test_a_geographic_frame_is_refused():
    faces = gpd.GeoSeries([square(0, 0, 10)], crs="EPSG:4326")
    with pytest.raises(ValueError, match="projected"):
        urban.resolve_overlaps(faces, np.array([100.0]))


# --- Wall outcomes -----------------------------------------------------------


def outcomes_for(model, walls, large):
    rng = realisation_seed(
        constants.BASE_SEED, EARTHQUAKE, urban.URBAN_STREAM, world_id=WORLD
    )
    realised = step.realise(model, pd.Series(1.0, index=model.index), large, rng)
    outcomes = urban.wall_outcomes(
        model,
        walls,
        realised.draws,
        realised.absorbed_by,
        realised.superseded_by,
        realised.large_evacuated["landslide_id"],
    )
    return outcomes.set_index("rw_id"), realised


def test_the_outcome_values_are_exact():
    # Five walls: on a standing face, on a failed face that survives, on a
    # failed face absorbed by the larger failed face beside it, on the face
    # that absorbs it, and on a failed face a large landslide reaches.
    faces = [
        square(0, 0, 10),  # standing
        square(20, 0, 10),  # failed, survives
        square(42, 2, 3),  # failed, absorbed by the next
        square(40, 0, 10),  # failed, absorbs the one above
        square(200, 200, 4),  # failed, and a large landslide takes it
    ]
    rw_ids = ["A-RW01", "B-RW01", "C-RW01", "D-RW01", "E-RW01"]
    model = model_rows(
        faces,
        theta=[
            NEVER_FAILS_M_S,
            ALWAYS_FAILS_M_S,
            ALWAYS_FAILS_M_S,
            ALWAYS_FAILS_M_S,
            ALWAYS_FAILS_M_S,
        ],
        rw_ids=rw_ids,
        wall_states=["cut_wall"] * 5,
    )
    walls = wall_population([*rw_ids, "F-RW01", "G-RW01"], flat=("G-RW01",))
    large = large_rows([Point(X0 + 202, Y0 - 202).buffer(20)])

    outcomes, realised = outcomes_for(model, walls, large)

    assert outcomes.loc["A-RW01", "outcome"] == urban.STANDING
    assert outcomes.loc["A-RW01", "slope_id"] == "SP0000001"
    assert outcomes.loc["A-RW01", "taken_by"] is None
    assert outcomes.loc["B-RW01", "outcome"] == urban.FAILED_WITH_POLYGON
    assert outcomes.loc["B-RW01", "taken_by"] is None
    assert outcomes.loc["C-RW01", "outcome"] == urban.ABSORBED
    assert outcomes.loc["C-RW01", "taken_by"] == "SP0000004"
    assert outcomes.loc["D-RW01", "outcome"] == urban.FAILED_WITH_POLYGON
    assert outcomes.loc["E-RW01", "outcome"] == urban.SUPERSEDED
    assert outcomes.loc["E-RW01", "taken_by"] == "LS0000001"
    # A wall whose line's polygon was not delineated stands with no polygon.
    assert outcomes.loc["F-RW01", "outcome"] == urban.STANDING
    assert outcomes.loc["F-RW01", "slope_id"] is None
    # A flat-land wall never appears.
    assert "G-RW01" not in outcomes.index
    assert list(outcomes.columns) == [
        "wall_line_id",
        "claim_id",
        "slope_id",
        "outcome",
        "taken_by",
    ]
    assert outcomes["claim_id"].tolist() == ["A", "B", "C", "D", "E", "F"]
    assert set(outcomes["outcome"]) <= set(urban.OUTCOMES)
    # The survivors are the two failed faces nobody took.
    assert realised.survivors.tolist() == [False, True, False, True, False]


def test_only_a_failed_polygon_under_a_large_landslide_is_superseded():
    # Two faces inside one large evacuated circle: the first fails, the second
    # never does. The failed one is superseded and names the large landslide;
    # the other stands, its wall left to vul step 11's line intersection.
    model = model_rows(
        [square(0, 0, 4), square(6, 0, 4)],
        theta=[ALWAYS_FAILS_M_S, NEVER_FAILS_M_S],
        rw_ids=["A-RW01", "B-RW01"],
        wall_states=["cut_wall", "cut_wall"],
    )
    walls = wall_population(["A-RW01", "B-RW01"])
    large = large_rows([Point(X0 + 5, Y0 - 2).buffer(20)])

    outcomes, realised = outcomes_for(model, walls, large)

    assert realised.superseded_by.tolist() == [0, urban.NONE]
    assert realised.survivors.tolist() == [False, False]
    assert outcomes.loc["A-RW01", "outcome"] == urban.SUPERSEDED
    assert outcomes.loc["A-RW01", "taken_by"] == "LS0000001"
    assert outcomes.loc["A-RW01", "slope_id"] == "SP0000001"
    assert outcomes.loc["B-RW01", "outcome"] == urban.STANDING
    assert outcomes.loc["B-RW01", "taken_by"] is None
    assert outcomes.loc["B-RW01", "slope_id"] == "SP0000002"


def test_a_superseder_set_on_a_polygon_that_did_not_fail_is_ignored():
    # Handed a position on a row that did not fail, the outcome table still
    # reads it standing: only a failed polygon is superseded or absorbed.
    model = model_rows([square(0, 0, 4)], theta=NEVER_FAILS_M_S, rw_ids=["A-RW01"])
    walls = wall_population(["A-RW01"])
    outcomes = urban.wall_outcomes(
        model,
        walls,
        draws_for(model),
        np.array([urban.NONE]),
        np.array([0]),
        pd.Series(["LS0000001"]),
    )
    assert outcomes["outcome"].tolist() == [urban.STANDING]
    assert outcomes["taken_by"].tolist() == [None]


def test_supersession_outranks_absorption_and_failure():
    small = square(2, 2, 3)
    big = square(0, 0, 10)
    model = model_rows(
        [small, big], theta=ALWAYS_FAILS_M_S, rw_ids=["A-RW01", "B-RW01"]
    )
    walls = wall_population(["A-RW01", "B-RW01"])
    large = large_rows([Point(X0 + 3, Y0 - 3).buffer(2)])

    outcomes, _ = outcomes_for(model, walls, large)

    assert outcomes.loc["A-RW01", "outcome"] == urban.SUPERSEDED
    assert outcomes.loc["A-RW01", "taken_by"] == "LS0000001"
    assert outcomes.loc["B-RW01", "outcome"] == urban.SUPERSEDED


def test_a_superseded_failure_absorbs_nothing_so_its_neighbour_survives():
    # A 30 m failure shares ground with a 20 m failure beside it, and a large
    # landslide takes the 30 m one but does not reach the 20 m one. The 20 m
    # failure survives: its ground is in neither the large polygon nor a
    # surviving urban one, so absorbing it would count it nowhere.
    bigger = square(0, 0, 30)
    smaller = square(25, 5, 20)
    model = model_rows(
        [bigger, smaller], theta=ALWAYS_FAILS_M_S, rw_ids=["A-RW01", "B-RW01"]
    )
    walls = wall_population(["A-RW01", "B-RW01"])
    large = large_rows([Point(X0 - 5, Y0 - 15).buffer(12)])
    assert not large.geometry.iloc[0].intersects(smaller)

    outcomes, realised = outcomes_for(model, walls, large)

    assert realised.superseded_by.tolist() == [0, urban.NONE]
    assert realised.absorbed_by.tolist() == [urban.NONE, urban.NONE]
    assert realised.survivors.tolist() == [False, True]
    assert outcomes.loc["A-RW01", "outcome"] == urban.SUPERSEDED
    assert outcomes.loc["A-RW01", "taken_by"] == "LS0000001"
    assert outcomes.loc["B-RW01", "outcome"] == urban.FAILED_WITH_POLYGON

    urban_rows = urban.to_landslide_rows(model, realised.draws, realised.survivors)
    urban_rows["realisation_id"] = EARTHQUAKE
    combined = urban.combine_with_large(urban_rows, large)
    written = set(combined["landslide_id"])
    assert "SP0000002" in written
    assert set(outcomes["taken_by"].dropna()) <= written


def test_every_absorber_is_written_to_the_combined_realisation():
    # A small failure nested in a larger one, both clear of the large
    # landslide: the larger absorbs the smaller and is itself written.
    model = model_rows(
        [square(2, 2, 3), square(0, 0, 10)],
        theta=ALWAYS_FAILS_M_S,
        rw_ids=["A-RW01", "B-RW01"],
    )
    walls = wall_population(["A-RW01", "B-RW01"])
    large = large_rows([Point(X0 + 500, Y0 - 500).buffer(10)])

    outcomes, realised = outcomes_for(model, walls, large)

    urban_rows = urban.to_landslide_rows(model, realised.draws, realised.survivors)
    urban_rows["realisation_id"] = EARTHQUAKE
    combined = urban.combine_with_large(urban_rows, large)
    assert outcomes.loc["A-RW01", "outcome"] == urban.ABSORBED
    assert outcomes.loc["A-RW01", "taken_by"] == "SP0000002"
    assert set(outcomes["taken_by"].dropna()) <= set(combined["landslide_id"])


def test_every_line_of_a_wall_split_at_a_property_boundary_takes_the_polygon():
    # One polygon edge carries a wall split at a property boundary into two
    # lines, WL0000001 (12 m, claim A) and WL0000002 (8 m, claim B). The
    # polygon fails: both walls fail with it, and neither is left without a
    # slope_id.
    model = model_rows(
        [square(0, 0, 20)],
        theta=ALWAYS_FAILS_M_S,
        rw_ids=["A-RW01"],
        wall_states=["cut_wall"],
        wall_line_ids=["WL0000001"],
        edge_lines=[["WL0000001", "WL0000002"]],
    )
    walls = wall_population(
        ["A-RW01", "B-RW01"], wall_line_ids=["WL0000001", "WL0000002"]
    )
    outcomes, _ = outcomes_for(model, walls, no_large())
    assert outcomes["slope_id"].tolist() == ["SP0000001", "SP0000001"]
    assert outcomes["outcome"].tolist() == [urban.FAILED_WITH_POLYGON] * 2
    assert outcomes["wall_line_id"].tolist() == ["WL0000001", "WL0000002"]


def test_a_wall_on_polygons_at_two_scales_takes_the_strongest_outcome():
    # The same wall on a fine face that failed and was absorbed, and on the
    # coarse face that absorbed it: the wall failed with the coarse polygon.
    model = model_rows(
        [square(2, 2, 3), square(0, 0, 10)],
        theta=ALWAYS_FAILS_M_S,
        rw_ids=["A-RW01", "A-RW01"],
    )
    walls = wall_population(["A-RW01"])
    outcomes, _ = outcomes_for(model, walls, no_large())
    assert outcomes.loc["A-RW01", "outcome"] == urban.FAILED_WITH_POLYGON
    assert outcomes.loc["A-RW01", "slope_id"] == "SP0000002"


# --- The landslide rows ------------------------------------------------------


def test_a_survivor_writes_three_rows_with_the_contract_columns():
    model = model_rows([square(0, 0, 10), square(50, 0, 10)], theta=ALWAYS_FAILS_M_S)
    draws = draws_for(model)
    rows = urban.to_landslide_rows(model, draws, np.array([True, False]))

    assert rows[LAND_CLASS_COLUMN].tolist() == [EVACUATED, IMMINENT, INUNDATED]
    assert rows["landslide_id"].tolist() == ["SP0000001"] * 3
    assert rows["slope_id"].tolist() == ["SP0000001"] * 3
    assert rows["population"].tolist() == [urban.URBAN] * 3
    assert rows["unit_id"].isna().all()
    by_class = rows.set_index(LAND_CLASS_COLUMN)
    assert by_class.loc[EVACUATED, "depth_m"] == 1.0
    assert by_class.loc[INUNDATED, "depth_m"] == 0.5
    assert np.isnan(by_class.loc[IMMINENT, "depth_m"])
    assert (rows["source_area_m2"] == 100.0).all()
    assert (rows["volume_m3"] == 100.0).all()
    assert (rows["pgv_m_s"] == 1.0).all()
    assert (rows["p_fail"] == draws["p_fail"].iloc[0]).all()
    assert (rows["uniform"] == draws["uniform"].iloc[0]).all()
    assert rows.crs == model.crs


def test_the_combined_realisation_puts_both_populations_in_one_schema():
    model = model_rows([square(0, 0, 10)], theta=ALWAYS_FAILS_M_S)
    urban_rows = urban.to_landslide_rows(model, draws_for(model), np.array([True]))
    urban_rows["realisation_id"] = EARTHQUAKE
    large = large_rows([Point(X0 + 500, Y0 - 500).buffer(10)])

    combined = urban.combine_with_large(urban_rows, large)

    assert list(combined.columns[: len(urban.COMBINED_COLUMNS)]) == list(
        urban.COMBINED_COLUMNS
    )
    assert "failure_probability" in combined.columns
    assert combined["landslide_id"].tolist() == [
        "LS0000001",
        "LS0000001",
        "SP0000001",
        "SP0000001",
        "SP0000001",
    ]
    large_part = combined[combined["population"] == urban.LARGE]
    assert large_part["pgv_m_s"].isna().all()
    assert large_part["slope_id"].isna().all()
    urban_part = combined[combined["population"] == urban.URBAN]
    assert urban_part["unit_id"].isna().all()
    assert urban_part["failure_probability"].isna().all()
    assert (combined["realisation_id"] == EARTHQUAKE).all()


def test_large_rows_without_the_contract_columns_are_refused():
    model = model_rows([square(0, 0, 10)], theta=ALWAYS_FAILS_M_S)
    urban_rows = urban.to_landslide_rows(model, draws_for(model), np.array([True]))
    old_style = large_rows([Point(X0, Y0).buffer(5)]).drop(columns=["population"])
    with pytest.raises(ValueError, match="population"):
        urban.combine_with_large(urban_rows, old_style)


# --- The step end to end -----------------------------------------------------


@pytest.fixture
def work_dirs(tmp_path, monkeypatch):
    """Point every input and output of the step at tmp_path."""
    monkeypatch.setattr(step, "WORK_DIR", tmp_path / "landslide")
    monkeypatch.setattr(gen_urban_slope_fragility, "WORK_DIR", tmp_path / "landslide")
    monkeypatch.setattr(s1_simulate_landslides, "WORK_DIR", tmp_path / "landslide")
    monkeypatch.setattr(gen_pgv_realisations, "WORK_DIR", tmp_path / "shaking")
    monkeypatch.setattr(gen_wall_population, "WORK_DIR", tmp_path / "exposure")
    for path in (tmp_path / "landslide", tmp_path / "shaking", tmp_path / "exposure"):
        path.mkdir()
    return tmp_path


def write_inputs(model, walls, large, pgv):
    model.to_parquet(step.urban_slope_model_path(WORLD, pilot=True))
    walls.to_parquet(gen_wall_population.wall_population_path(WORLD, pilot=True))
    large.to_parquet(
        s1_simulate_landslides.realisation_path(pilot=True, realisation_id=EARTHQUAKE)
    )
    write_raster(
        make_grid(pgv).rename("pgv_m_s").astype("float32"),
        gen_pgv_realisations.pgv_path(EARTHQUAKE, pilot=True),
    )


def test_the_paths_carry_both_ids_world_first():
    assert step.combined_realisation_path(2, 13, pilot=True).name == (
        "landslide-realisation-w002-r013-pilot.geoparquet"
    )
    assert step.urban_wall_outcome_path(0, 1, pilot=False).name == (
        "urban-wall-outcome-w000-r001.parquet"
    )
    assert (
        step.urban_slope_model_path(0, pilot=True).name
        == "urban-slope-model-w000-pilot.geoparquet"
    )


@ignore_affine_matmul
def test_the_step_writes_the_two_outputs_with_the_contract_columns(work_dirs):
    # Two faces in the first PGV cell, which carries shaking; one in the third
    # cell, off the grid's finite values, which is not drawn.
    faces = [square(10, 10, 10), square(60, 10, 10), square(210, 10, 10)]
    rw_ids = ["A-RW01", None, "C-RW01"]
    model = model_rows(
        faces,
        theta=[ALWAYS_FAILS_M_S, NEVER_FAILS_M_S, ALWAYS_FAILS_M_S],
        rw_ids=rw_ids,
        wall_states=["fill_wall", "no_wall", "cut_wall"],
    )
    walls = wall_population(["A-RW01", "C-RW01", "D-RW01"], flat=("D-RW01",))
    large = large_rows([Point(X0 + 500, Y0 - 500).buffer(10)])
    write_inputs(model, walls, large, [[1.2, 1.2, np.nan], [0.8, 0.8, np.nan]])

    step.main(pilot=True, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])

    combined = gpd.read_parquet(
        step.combined_realisation_path(WORLD, EARTHQUAKE, pilot=True)
    )
    assert list(combined.columns[: len(urban.COMBINED_COLUMNS)]) == list(
        urban.COMBINED_COLUMNS
    )
    assert combined.crs == model.crs
    assert (combined["world_id"] == WORLD).all()
    assert (combined["realisation_id"] == EARTHQUAKE).all()
    urban_part = combined[combined["population"] == urban.URBAN]
    assert urban_part["slope_id"].tolist() == ["SP0000001"] * 3
    assert sorted(urban_part[LAND_CLASS_COLUMN]) == sorted(
        [EVACUATED, INUNDATED, IMMINENT]
    )
    # float32 on disk, so the sampled PGV reproduces the cell to that precision.
    assert np.allclose(urban_part["pgv_m_s"], 1.2, rtol=1e-6)
    assert (urban_part["wall_state"] == "fill_wall").all()
    assert (urban_part["rw_id"] == "A-RW01").all()
    assert len(combined[combined["population"] == urban.LARGE]) == 2

    outcomes = pd.read_parquet(
        step.urban_wall_outcome_path(WORLD, EARTHQUAKE, pilot=True)
    )
    assert list(outcomes.columns) == [
        "world_id",
        "realisation_id",
        "rw_id",
        "wall_line_id",
        "claim_id",
        "slope_id",
        "outcome",
        "taken_by",
    ]
    by_wall = outcomes.set_index("rw_id")
    assert by_wall.loc["A-RW01", "outcome"] == urban.FAILED_WITH_POLYGON
    # Off the PGV grid, not drawn, so standing with its polygon.
    assert by_wall.loc["C-RW01", "outcome"] == urban.STANDING
    assert by_wall.loc["C-RW01", "slope_id"] == "SP0000003"
    assert "D-RW01" not in by_wall.index
    assert (outcomes["world_id"] == WORLD).all()
    assert (outcomes["realisation_id"] == EARTHQUAKE).all()


@ignore_affine_matmul
def test_the_run_prints_the_rate_setting_of_the_model_file(work_dirs, capsys):
    model = model_rows([square(10, 10, 10)], theta=NEVER_FAILS_M_S, rate_setting="low")
    write_inputs(model, wall_population([]), no_large(), [[1.0, 1.0], [1.0, 1.0]])

    step.main(pilot=True, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])

    factor = constants.URBAN_RATE_FACTORS["low"]
    assert f"Rate setting 'low', factor {factor:.4f}" in capsys.readouterr().out


def test_a_model_file_with_two_rate_settings_is_refused():
    model = pd.concat(
        [
            model_rows([square(0, 0, 10)], theta=MIDDLE_M_S, rate_setting="low"),
            model_rows([square(20, 0, 10)], theta=MIDDLE_M_S, rate_setting="high"),
        ],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="rate settings"):
        step.describe_rate_setting(model)


@ignore_affine_matmul
def test_nothing_failing_still_writes_both_files(work_dirs):
    model = model_rows([square(10, 10, 10)], theta=NEVER_FAILS_M_S, rw_ids=["A-RW01"])
    walls = wall_population(["A-RW01"])
    write_inputs(model, walls, no_large(), [[1.0, 1.0], [1.0, 1.0]])

    step.main(pilot=True, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])

    combined = gpd.read_parquet(
        step.combined_realisation_path(WORLD, EARTHQUAKE, pilot=True)
    )
    assert combined.empty
    assert list(combined.columns[: len(urban.COMBINED_COLUMNS)]) == list(
        urban.COMBINED_COLUMNS
    )
    outcomes = pd.read_parquet(
        step.urban_wall_outcome_path(WORLD, EARTHQUAKE, pilot=True)
    )
    assert outcomes["outcome"].tolist() == [urban.STANDING]


@ignore_affine_matmul
def test_the_figure_reads_what_the_run_wrote(work_dirs):
    # A surviving failure, a failure absorbed by it, a failure a large
    # landslide takes, and a standing one, all in the shaken cell.
    faces = [
        square(10, 10, 20),  # failed, survives
        square(12, 12, 5),  # failed, absorbed by the one above
        square(60, 10, 10),  # failed, superseded
        square(10, 60, 10),  # standing
    ]
    rw_ids = ["A-RW01", "B-RW01", "C-RW01", "D-RW01"]
    model = model_rows(
        faces,
        theta=[ALWAYS_FAILS_M_S, ALWAYS_FAILS_M_S, ALWAYS_FAILS_M_S, NEVER_FAILS_M_S],
        rw_ids=rw_ids,
        wall_states=["cut_wall"] * 4,
    )
    walls = wall_population(rw_ids)
    large = large_rows([Point(X0 + 65, Y0 - 15).buffer(8)])
    write_inputs(model, walls, large, [[1.0, 1.0], [1.0, 1.0]])
    step.main(pilot=True, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])

    layers, large_evacuated = fig.outcome_layers(
        *fig.read_outputs(WORLD, EARTHQUAKE, pilot=True)
    )

    assert set(layers) == set(fig.LAYER_COLOURS)
    assert len(layers[urban.STANDING]) == len(model)
    assert layers[urban.FAILED_WITH_POLYGON]["slope_id"].tolist() == ["SP0000001"]
    assert layers[urban.ABSORBED]["slope_id"].tolist() == ["SP0000002"]
    assert layers[urban.SUPERSEDED]["slope_id"].tolist() == ["SP0000003"]
    assert large_evacuated["landslide_id"].tolist() == ["LS0000001"]


@ignore_affine_matmul
def test_the_figure_refuses_a_model_file_rewritten_after_the_run(work_dirs):
    model = model_rows([square(10, 10, 10)], theta=ALWAYS_FAILS_M_S, rw_ids=["A-RW01"])
    walls = wall_population(["A-RW01"])
    write_inputs(model, walls, no_large(), [[1.0, 1.0], [1.0, 1.0]])
    step.main(pilot=True, world_ids=[WORLD], realisation_ids=[EARTHQUAKE])

    _, combined, outcomes = fig.read_outputs(WORLD, EARTHQUAKE, pilot=True)
    renumbered = model.assign(slope_id=["SP0000009"])
    with pytest.raises(ValueError, match="rerun"):
        fig.outcome_layers(renumbered, combined, outcomes)
